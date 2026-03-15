"""
swarm_sync: Round synchronization for multi-session Agent Swarm.

Coordinates 10 Tmux CC sessions (each running 5 character agents)
via file-based IPC. No network required.

Usage:
    # Initialize swarm state (Orchestrator runs once)
    python -m cc_layer.cli.swarm_sync --mode init \
        --session-dir cc_layer/state/session_xxx \
        --agents-file agents.json \
        --num-workers 10

    # Write timeline for next round (Orchestrator runs per round)
    python -m cc_layer.cli.swarm_sync --mode prepare-round \
        --session-dir cc_layer/state/session_xxx \
        --round-num 1

    # Check if all workers completed a round (Orchestrator polls)
    python -m cc_layer.cli.swarm_sync --mode check-round \
        --session-dir cc_layer/state/session_xxx \
        --round-num 1 --num-workers 10

    # Merge worker actions into timeline (Orchestrator runs after all done)
    python -m cc_layer.cli.swarm_sync --mode merge \
        --session-dir cc_layer/state/session_xxx \
        --round-num 1 --num-workers 10

    # Read current timeline (Worker reads at round start)
    python -m cc_layer.cli.swarm_sync --mode read-timeline \
        --session-dir cc_layer/state/session_xxx \
        --round-num 1

    # Write worker actions (Worker writes at round end)
    python -m cc_layer.cli.swarm_sync --mode write-actions \
        --session-dir cc_layer/state/session_xxx \
        --round-num 1 --worker-id 0 \
        --actions-file /path/to/actions.jsonl

    # Export all actions to Zep format (Orchestrator runs at end)
    python -m cc_layer.cli.swarm_sync --mode export-zep \
        --session-dir cc_layer/state/session_xxx

    # Export round actions as conversation JSON (Phase B→C adapter)
    python -m cc_layer.cli.swarm_sync --mode export-conversation \
        --session-dir cc_layer/state/session_xxx \
        --round-num 1

Output:
    JSON status on stdout
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime


def _swarm_dir(session_dir):
    return os.path.join(session_dir, "swarm")


def _timeline_path(session_dir, round_num):
    return os.path.join(_swarm_dir(session_dir), f"timeline_round_{round_num:03d}.json")


def _actions_path(session_dir, worker_id, round_num):
    return os.path.join(
        _swarm_dir(session_dir), f"actions_w{worker_id}_r{round_num:03d}.jsonl"
    )


def _ready_path(session_dir, round_num):
    return os.path.join(_swarm_dir(session_dir), f"round_{round_num:03d}_ready")


def _init(args):
    """Initialize swarm directory and assign agents to workers."""
    swarm = _swarm_dir(args.session_dir)
    os.makedirs(swarm, exist_ok=True)

    # Load agent definitions
    with open(args.agents_file, "r", encoding="utf-8") as f:
        agents = json.load(f)

    agent_list = agents if isinstance(agents, list) else agents.get("agents", [])
    num_workers = args.num_workers
    total = len(agent_list)

    # Distribute agents across workers (round-robin)
    worker_assignments = {i: [] for i in range(num_workers)}
    for idx, agent in enumerate(agent_list):
        worker_id = idx % num_workers
        agent["agent_id"] = idx
        worker_assignments[worker_id].append(agent)

    # Write worker assignment files
    for wid, assigned in worker_assignments.items():
        path = os.path.join(swarm, f"worker_{wid}_agents.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(assigned, f, ensure_ascii=False, indent=2)

    # Write initial empty timeline
    timeline = {"round": 0, "posts": [], "follows": [], "stats": {}}
    with open(_timeline_path(args.session_dir, 0), "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

    # Write swarm config
    config = {
        "num_workers": num_workers,
        "total_agents": total,
        "agents_per_worker": [len(worker_assignments[i]) for i in range(num_workers)],
        "created_at": datetime.now().isoformat(),
    }
    with open(os.path.join(swarm, "swarm_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "status": "ok",
        "swarm_dir": swarm,
        "num_workers": num_workers,
        "total_agents": total,
        "agents_per_worker": config["agents_per_worker"],
    }, ensure_ascii=False))


def _prepare_round(args):
    """Signal that a round is ready for workers to process."""
    ready_file = _ready_path(args.session_dir, args.round_num)
    with open(ready_file, "w") as f:
        f.write(datetime.now().isoformat())

    print(json.dumps({
        "status": "ok",
        "round": args.round_num,
        "ready_file": ready_file,
    }, ensure_ascii=False))


def _check_round(args):
    """Check if all workers have submitted actions for a round."""
    completed = []
    missing = []
    for wid in range(args.num_workers):
        path = _actions_path(args.session_dir, wid, args.round_num)
        if os.path.exists(path):
            completed.append(wid)
        else:
            missing.append(wid)

    print(json.dumps({
        "round": args.round_num,
        "all_done": len(missing) == 0,
        "completed": completed,
        "missing": missing,
        "progress": f"{len(completed)}/{args.num_workers}",
    }, ensure_ascii=False))


def _merge(args):
    """Merge all worker actions into the next round's timeline."""
    swarm = _swarm_dir(args.session_dir)

    # Load current timeline
    prev_timeline_path = _timeline_path(args.session_dir, args.round_num - 1)
    if os.path.exists(prev_timeline_path):
        with open(prev_timeline_path, "r", encoding="utf-8") as f:
            timeline = json.load(f)
    else:
        timeline = {"round": args.round_num - 1, "posts": [], "follows": [], "stats": {}}

    # Collect all worker actions
    all_actions = []
    new_posts = []
    new_follows = []

    for wid in range(args.num_workers):
        path = _actions_path(args.session_dir, wid, args.round_num)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                action = json.loads(line)
                action["worker_id"] = wid
                all_actions.append(action)

                if action.get("action_type") == "CREATE_POST":
                    new_posts.append({
                        "post_id": f"r{args.round_num}_w{wid}_a{action.get('agent_id', 0)}",
                        "agent_id": action.get("agent_id"),
                        "agent_name": action.get("agent_name", ""),
                        "content": action.get("action_args", {}).get("content", ""),
                        "round": args.round_num,
                        "likes": 0,
                        "reposts": 0,
                    })
                elif action.get("action_type") == "LIKE_POST":
                    target = action.get("action_args", {}).get("post_id")
                    for post in timeline["posts"] + new_posts:
                        if post.get("post_id") == target:
                            post["likes"] = post.get("likes", 0) + 1
                elif action.get("action_type") == "FOLLOW":
                    new_follows.append({
                        "follower": action.get("agent_name", ""),
                        "target": action.get("action_args", {}).get("target_user_name", ""),
                        "round": args.round_num,
                    })

    # Build new timeline
    new_timeline = {
        "round": args.round_num,
        "posts": timeline.get("posts", []) + new_posts,
        "follows": timeline.get("follows", []) + new_follows,
        "stats": {
            "total_posts": len(timeline.get("posts", [])) + len(new_posts),
            "total_follows": len(timeline.get("follows", [])) + len(new_follows),
            "actions_this_round": len(all_actions),
            "new_posts_this_round": len(new_posts),
        },
    }

    # Keep only last 50 posts in active timeline (older ones are archived)
    if len(new_timeline["posts"]) > 50:
        # Archive older posts
        archive_path = os.path.join(swarm, f"archive_round_{args.round_num:03d}.json")
        archived = new_timeline["posts"][:-50]
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(archived, f, ensure_ascii=False, indent=2)
        new_timeline["posts"] = new_timeline["posts"][-50:]

    # Write merged timeline
    out_path = _timeline_path(args.session_dir, args.round_num)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(new_timeline, f, ensure_ascii=False, indent=2)

    # Write all actions log
    actions_log = os.path.join(swarm, f"all_actions_round_{args.round_num:03d}.jsonl")
    with open(actions_log, "w", encoding="utf-8") as f:
        for action in all_actions:
            f.write(json.dumps(action, ensure_ascii=False) + "\n")

    print(json.dumps({
        "status": "ok",
        "round": args.round_num,
        "actions_merged": len(all_actions),
        "new_posts": len(new_posts),
        "new_follows": len(new_follows),
        "timeline_file": out_path,
    }, ensure_ascii=False))


def _read_timeline(args):
    """Read current timeline for a worker."""
    path = _timeline_path(args.session_dir, max(0, args.round_num - 1))
    if not os.path.exists(path):
        path = _timeline_path(args.session_dir, 0)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            timeline = json.load(f)
    else:
        timeline = {"round": 0, "posts": [], "follows": [], "stats": {}}

    # Also load this worker's agent assignments if worker_id given
    if args.worker_id is not None:
        agents_path = os.path.join(
            _swarm_dir(args.session_dir), f"worker_{args.worker_id}_agents.json"
        )
        if os.path.exists(agents_path):
            with open(agents_path, "r", encoding="utf-8") as f:
                timeline["my_agents"] = json.load(f)

    print(json.dumps(timeline, ensure_ascii=False, indent=2))


def _write_actions(args):
    """Write a worker's actions for a round."""
    out_path = _actions_path(args.session_dir, args.worker_id, args.round_num)

    if args.actions_file:
        # Copy from file
        with open(args.actions_file, "r", encoding="utf-8") as src:
            content = src.read()
    else:
        # Read from stdin
        content = sys.stdin.read()

    # アトミック書き込み: 一時ファイルに書いてからリネーム
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, out_path)

    # Count actions
    count = sum(1 for line in content.strip().split("\n") if line.strip())
    print(json.dumps({
        "status": "ok",
        "worker_id": args.worker_id,
        "round": args.round_num,
        "actions_written": count,
        "file": out_path,
    }, ensure_ascii=False))


def _export_zep(args):
    """Export all swarm actions to Zep-compatible format."""
    swarm = _swarm_dir(args.session_dir)
    pattern = os.path.join(swarm, "all_actions_round_*.jsonl")

    all_activities = []
    for fpath in sorted(glob.glob(pattern)):
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_activities.append(json.loads(line))

    # Convert to Zep episode text format
    episodes = []
    for act in all_activities:
        agent_name = act.get("agent_name", f"Agent_{act.get('agent_id', 0)}")
        action_type = act.get("action_type", "DO_NOTHING")
        args_data = act.get("action_args", {})

        if action_type == "CREATE_POST":
            text = f"{agent_name}: Published a post: \"{args_data.get('content', '')}\""
        elif action_type == "LIKE_POST":
            text = f"{agent_name}: Liked a post by {args_data.get('post_author_name', 'someone')}"
        elif action_type == "REPOST":
            text = f"{agent_name}: Reposted content from {args_data.get('original_author_name', 'someone')}"
        elif action_type == "FOLLOW":
            text = f"{agent_name}: Started following {args_data.get('target_user_name', 'someone')}"
        elif action_type == "CREATE_COMMENT":
            text = f"{agent_name}: Commented: \"{args_data.get('content', '')}\""
        else:
            text = f"{agent_name}: Performed {action_type}"

        episodes.append({
            "text": text,
            "round": act.get("round_num", 0),
            "agent_name": agent_name,
            "action_type": action_type,
        })

    output = {
        "total_activities": len(episodes),
        "episodes": episodes,
    }

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(json.dumps({
            "status": "ok",
            "total_activities": len(episodes),
            "output_file": args.output_file,
        }, ensure_ascii=False))
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))


def _action_to_text(agent_name, action_type, action_args):
    """Convert a single action to human-readable conversation text."""
    if action_type == "CREATE_POST":
        return f"{agent_name}: {action_args.get('content', '')}"
    elif action_type == "CREATE_COMMENT":
        target = action_args.get("target_author_name", "")
        content = action_args.get("content", "")
        return f"{agent_name} → {target}: {content}"
    elif action_type == "LIKE_POST":
        author = action_args.get("post_author_name", "")
        return f"{agent_name} が {author} の投稿にいいね"
    elif action_type == "REPOST":
        author = action_args.get("original_author_name", "")
        return f"{agent_name} が {author} の投稿をリポスト"
    elif action_type == "FOLLOW":
        target = action_args.get("target_user_name", "")
        return f"{agent_name} が {target} をフォロー"
    elif action_type == "QUOTE_POST":
        author = action_args.get("original_author_name", "")
        quote = action_args.get("quote_content", "")
        return f"{agent_name} が {author} の投稿を引用: {quote}"
    else:
        return f"{agent_name}: {action_type}"


def _export_conversation(args):
    """Export a round's actions as conversation-formatted JSON (Phase B→C adapter)."""
    swarm = _swarm_dir(args.session_dir)
    actions_file = os.path.join(swarm, f"all_actions_round_{args.round_num:03d}.jsonl")

    conversations = []
    if os.path.exists(actions_file):
        with open(actions_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                action = json.loads(line)
                action_type = action.get("action_type", "DO_NOTHING")
                if action_type == "DO_NOTHING":
                    continue
                agent_name = action.get("agent_name", f"Agent_{action.get('agent_id', 0)}")
                action_args = action.get("action_args", {})
                text = _action_to_text(agent_name, action_type, action_args)
                conversations.append({
                    "agent_name": agent_name,
                    "action_type": action_type,
                    "text": text,
                    "round": action.get("round_num", args.round_num),
                })

    output = {
        "round": args.round_num,
        "conversations": conversations,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Swarm round synchronization for multi-session Agent Swarm"
    )
    parser.add_argument(
        "--mode",
        choices=["init", "prepare-round", "check-round", "merge",
                 "read-timeline", "write-actions", "export-zep",
                 "export-conversation"],
        required=True,
    )
    parser.add_argument("--session-dir", required=True, help="Session state directory")
    parser.add_argument("--agents-file", help="Agents JSON file (mode=init)")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of workers")
    parser.add_argument("--round-num", type=int, help="Round number")
    parser.add_argument("--worker-id", type=int, help="Worker ID (0-9)")
    parser.add_argument("--actions-file", help="Actions JSONL file (mode=write-actions)")
    parser.add_argument("--output-file", help="Output file (mode=export-zep)")

    args = parser.parse_args()

    try:
        if args.mode == "init":
            if not args.agents_file:
                parser.error("--agents-file required for mode=init")
            _init(args)
        elif args.mode == "prepare-round":
            _prepare_round(args)
        elif args.mode == "check-round":
            _check_round(args)
        elif args.mode == "merge":
            _merge(args)
        elif args.mode == "read-timeline":
            _read_timeline(args)
        elif args.mode == "write-actions":
            if args.worker_id is None:
                parser.error("--worker-id required for mode=write-actions")
            _write_actions(args)
        elif args.mode == "export-zep":
            _export_zep(args)
        elif args.mode == "export-conversation":
            _export_conversation(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
