"""
multipath_run: Run all career paths in parallel and return comparison report.

Usage:
    python -m cc_layer.cli.multipath_run \
        --state-file cc_layer/state/session_xxx/agent_state.json \
        --round-count 40 \
        --top-n 5 \
        --document-text-file resume.txt \
        --requirement "IT業界でのキャリア転換"

Output (stdout JSON):
    Full comparison report from MultiPathSimulator.run_expanded_and_select()
"""
import argparse
import json
import sys
import os

import cc_layer.cli  # noqa: F401

from app.models.life_simulator import (
    BaseIdentity, CareerState, FamilyMember, ActiveBlocker, BlockerType,
)
from app.services.multipath_simulator import MultiPathSimulator


def reconstruct_identity(d: dict) -> BaseIdentity:
    return BaseIdentity(**d)


def reconstruct_state(d: dict) -> CareerState:
    family = [FamilyMember(**f) for f in d.get("family", [])]
    blockers = [
        ActiveBlocker(
            blocker_type=BlockerType(b["blocker_type"]),
            reason=b["reason"],
            blocked_actions=b["blocked_actions"],
            started_round=b["started_round"],
            expires_round=b.get("expires_round"),
        )
        for b in d.get("blockers", [])
    ]
    state_dict = {k: v for k, v in d.items() if k not in ("family", "blockers")}
    state = CareerState(**state_dict)
    state.family = family
    state.blockers = blockers
    return state


def main():
    parser = argparse.ArgumentParser(description="Run multi-path career simulation")
    parser.add_argument("--state-file", required=True, help="Path to agent_state.json")
    parser.add_argument("--round-count", type=int, default=40, help="Rounds to simulate (default: 40 = 10 years)")
    parser.add_argument("--top-n", type=int, default=5, help="Top N paths to return (default: 5)")
    parser.add_argument("--document-text-file", default=None, help="Path to resume/CV text file")
    parser.add_argument("--requirement", default="", help="Simulation requirement text")
    parser.add_argument("--seed", type=int, default=None, help="Override random seed")
    parser.add_argument("--output-file", default=None, help="Write result to file instead of stdout")
    parser.add_argument("--default-paths", action="store_true",
                        help="Use default 3 paths instead of LLM-generated paths")
    args = parser.parse_args()

    # Load state
    with open(args.state_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    identity = reconstruct_identity(data["identity"])
    state = reconstruct_state(data["state"])
    seed = args.seed if args.seed is not None else data.get("seed")

    # Load document text
    document_text = ""
    if args.document_text_file and os.path.isfile(args.document_text_file):
        with open(args.document_text_file, "r", encoding="utf-8") as f:
            document_text = f.read()

    # Run simulation
    simulator = MultiPathSimulator(base_seed=seed)

    if args.default_paths:
        from app.services.multipath_simulator import build_default_paths
        path_configs = build_default_paths(state, args.round_count)
        simulator.initialize(identity, state, path_configs=path_configs, round_count=args.round_count)
        simulator.run_all()
        report = simulator.generate_comparison_report()
        # Score paths
        from app.services.multipath_simulator import score_path
        for p in report.get("paths", []):
            p["score"] = round(score_path(p), 3)
        report["paths"] = sorted(report.get("paths", []), key=lambda p: p["score"], reverse=True)[:args.top_n]
    else:
        report = simulator.run_expanded_and_select(
            identity=identity,
            initial_state=state,
            round_count=args.round_count,
            top_n=args.top_n,
            document_text=document_text,
            simulation_requirement=args.requirement,
        )

    result_json = json.dumps(report, ensure_ascii=False, indent=2, default=str)

    if args.output_file:
        os.makedirs(os.path.dirname(args.output_file) or ".", exist_ok=True)
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(result_json)
        print(json.dumps({"status": "ok", "output_file": args.output_file}, ensure_ascii=False))
    else:
        print(result_json)


if __name__ == "__main__":
    main()
