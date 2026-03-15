"""
zep_write: Write facts/activities to Zep knowledge graph.

Usage:
    # Write state as facts
    python -m cc_layer.cli.zep_write \
        --graph-id mirofish_xxx \
        --facts-file cc_layer/state/session_xxx/zep_facts.json

    # Write a single activity (SNS post, action, etc.)
    python -m cc_layer.cli.zep_write \
        --graph-id mirofish_xxx \
        --activity '{"agent_name":"田中太郎","action":"Published a post","content":"昇進の知らせを受けた"}'

    # Write state_export output directly
    python -m cc_layer.cli.state_export --state-file ... --format zep-facts | \
    python -m cc_layer.cli.zep_write --graph-id mirofish_xxx --stdin-facts

Output (stdout JSON):
    {"status": "ok", "facts_written": N}
"""
import argparse
import json
import sys

import cc_layer.cli  # noqa: F401

from zep_cloud.client import Zep
from app.config import Config


def write_facts_to_zep(graph_id: str, facts: list[str]) -> int:
    """Write fact strings to Zep graph as a text episode."""
    client = Zep(api_key=Config.ZEP_API_KEY)
    combined_text = "\n".join(facts)
    client.graph.add(
        graph_id=graph_id,
        type="text",
        data=combined_text,
    )
    return len(facts)


def write_activity_to_zep(graph_id: str, activity: dict) -> int:
    """Write a single activity to Zep graph."""
    agent_name = activity.get("agent_name", "Agent")
    action = activity.get("action", "did something")
    content = activity.get("content", "")
    text = f"{agent_name}: {action}: \"{content}\""

    client = Zep(api_key=Config.ZEP_API_KEY)
    client.graph.add(
        graph_id=graph_id,
        type="text",
        data=text,
    )
    return 1


def main():
    parser = argparse.ArgumentParser(description="Write to Zep knowledge graph")
    parser.add_argument("--graph-id", required=True, help="Zep graph ID")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--facts-file", help="Path to JSON array of fact strings")
    group.add_argument("--activity", help="Single activity JSON string")
    group.add_argument("--stdin-facts", action="store_true",
                       help="Read facts JSON array from stdin")
    args = parser.parse_args()

    if args.facts_file:
        with open(args.facts_file, "r", encoding="utf-8") as f:
            facts = json.load(f)
        count = write_facts_to_zep(args.graph_id, facts)

    elif args.stdin_facts:
        facts = json.load(sys.stdin)
        count = write_facts_to_zep(args.graph_id, facts)

    elif args.activity:
        activity = json.loads(args.activity)
        count = write_activity_to_zep(args.graph_id, activity)

    print(json.dumps({"status": "ok", "facts_written": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
