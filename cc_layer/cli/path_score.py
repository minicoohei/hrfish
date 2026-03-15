"""
path_score: Score SubAgent-generated career paths and produce ranking.

Usage:
    # Score all expanded path files in a directory
    python -m cc_layer.cli.path_score \
        --input-dir cc_layer/state/session_xxx/ \
        --output-file cc_layer/state/session_xxx/multipath_result.json

    # Score a single path file
    python -m cc_layer.cli.path_score \
        --input-file cc_layer/state/session_xxx/path_expanded_path_a.json

Reads path_expanded_*.json files (SubAgent output) and scores them using
the same weights as multipath_simulator.score_path().

Output:
    Ranked paths with scores, compatible with Phase 2 SubAgents.
"""
import argparse
import glob
import json
import os
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401


DEFAULT_SCORE_WEIGHTS = {
    "salary": 0.25,
    "cash": 0.15,
    "low_stress": 0.15,
    "satisfaction": 0.25,
    "wlb": 0.20,
}


def _score_path(final_state: dict, weights: dict = None) -> float:
    """
    Score a path's final state. Higher = better.

    Maps SubAgent snapshot fields to the scoring function:
      annual_income → salary_score (capped at 3000万)
      satisfaction  → satisfaction (0-1)
      stress        → stress_penalty (lower is better)
    """
    w = weights or DEFAULT_SCORE_WEIGHTS

    income = final_state.get("annual_income", 0)
    salary_score = min(max(income / 3000, 0), 1.0)

    # SubAgent output may not have cash_buffer; default mid-range
    cash_score = min(
        max(final_state.get("cash_buffer", 2500), 0) / 5000, 1.0
    )

    stress = max(0.0, min(1.0, final_state.get("stress", 0.5)))
    satisfaction = max(0.0, min(1.0, final_state.get("satisfaction", 0.5)))

    # WLB: check both field names, infer from stress if not provided
    wlb = max(0.0, min(1.0, final_state.get("work_life_balance", final_state.get("wlb", 1.0 - stress))))

    return (
        salary_score * w.get("salary", 0.25)
        + cash_score * w.get("cash", 0.15)
        + (1.0 - stress) * w.get("low_stress", 0.15)
        + satisfaction * w.get("satisfaction", 0.25)
        + wlb * w.get("wlb", 0.20)
    )


def normalize_overall_probabilities(scored: list[dict]) -> None:
    """Normalize overall_probability across paths to sum to ~1.0.

    Mutates the dicts in place. Paths with None overall_probability are skipped.
    """
    probs = [p.get("overall_probability") for p in scored]
    valid_probs = [p for p in probs if p is not None and p > 0]
    if not valid_probs:
        return
    total = sum(valid_probs)
    if total <= 0:
        return
    if abs(total - 1.0) > 0.01:  # more than 1% off
        print(
            f"WARN: overall_probability sum={total:.2f} (expected ~1.0). "
            f"Normalizing {len(valid_probs)} paths.",
            file=sys.stderr,
        )
        for p in scored:
            op = p.get("overall_probability")
            if op is not None and op > 0:
                p["overall_probability"] = round(op / total, 4)


def _process_path(path_data: dict) -> dict:
    """Process a single expanded path and add score.

    Preserves all SubAgent output fields (scenarios, common_periods, etc.)
    and adds a composite score.
    """
    # Score using likely scenario's final_state, or path-level final_state
    scenarios = path_data.get("scenarios", [])
    # Normalize dict-style scenarios to list
    if isinstance(scenarios, dict):
        scenarios = [{"scenario_id": k, **v} for k, v in scenarios.items()]
        path_data["scenarios"] = scenarios
    if scenarios:
        likely = next((s for s in scenarios if s.get("scenario_id") == "likely"), scenarios[0])
        final_state = likely.get("final_state", {})
    else:
        final_state = path_data.get("final_state", {})

    score = _score_path(final_state)

    # Count events across all periods (common + scenario)
    all_events = []
    all_blockers = set()
    for period in path_data.get("common_periods", []):
        all_events.extend(period.get("events", []))
        all_blockers.update(period.get("blockers_active", []))
    for period in path_data.get("periods", []):
        all_events.extend(period.get("events", []))
        all_blockers.update(period.get("blockers_active", []))
    for s in scenarios:
        for period in s.get("periods", []):
            all_events.extend(period.get("events", []))
            all_blockers.update(period.get("blockers_active", []))

    # Preserve all original fields and add score
    result = dict(path_data)
    result["score"] = round(score, 4)
    result["event_count"] = len(all_events)
    result["blockers_encountered"] = sorted(all_blockers)
    if "final_state" not in result:
        result["final_state"] = final_state
    result["final_state"]["total_score"] = round(score, 4)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Score SubAgent-generated career paths"
    )
    parser.add_argument(
        "--input-dir",
        help="Directory containing path_expanded_*.json files"
    )
    parser.add_argument(
        "--input-file",
        help="Single expanded path JSON file"
    )
    parser.add_argument(
        "--designs-file",
        help="path_designs.json (PathDesignerAgent output, merged into result)"
    )
    parser.add_argument("--output-file", help="Write output to file")
    parser.add_argument(
        "--state-file",
        help="agent_state.json (for current_income cross-check)"
    )
    parser.add_argument("--top-n", type=int, default=5, help="Top N paths")

    args = parser.parse_args()

    try:
        paths = []

        if args.input_file:
            with open(args.input_file, "r", encoding="utf-8") as f:
                paths.append(json.load(f))
        elif args.input_dir:
            pattern = os.path.join(args.input_dir, "path_expanded_*.json")
            for fpath in sorted(glob.glob(pattern)):
                with open(fpath, "r", encoding="utf-8") as f:
                    paths.append(json.load(f))
        else:
            parser.error("--input-dir or --input-file required")

        if not paths:
            print("No path files found", file=sys.stderr)
            sys.exit(1)

        # Load designs if provided (for label/direction metadata)
        designs_map = {}
        if args.designs_file and os.path.exists(args.designs_file):
            with open(args.designs_file, "r", encoding="utf-8") as f:
                designs = json.load(f)
            for d in designs.get("paths", []):
                designs_map[d["path_id"]] = d

        # Normalize all paths before scoring
        from cc_layer.schemas.normalize import normalize_expanded_path, warn_likely_below_current
        paths = [normalize_expanded_path(p).model_dump() for p in paths]

        # Cross-check likely income vs current income
        identity = {}
        agent_state = {}
        if args.state_file and os.path.exists(args.state_file):
            with open(args.state_file, "r", encoding="utf-8") as f:
                agent_state = json.load(f)
            identity = agent_state.get("identity", {})
            current_income = agent_state.get("state", {}).get("salary_annual", 0)
            warn_likely_below_current(paths, current_income)

        # Score and rank
        scored = []
        for path_data in paths:
            result = _process_path(path_data)
            # Merge design metadata
            design = designs_map.get(result["path_id"], {})
            result["direction"] = design.get("direction", "")
            result["risk"] = design.get("risk", "")
            result["upside"] = design.get("upside", "")
            scored.append(result)

        scored.sort(key=lambda x: x["score"], reverse=True)
        normalize_overall_probabilities(scored)
        ranked = scored[: args.top_n]

        output = {
            "identity": identity,
            "simulation_years": 10.0,
            "total_rounds": 40,
            "paths": ranked,
            "total_scored": len(scored),
            "top_n": len(ranked),
            "ranking": [
                {"rank": i + 1, "path_id": p["path_id"],
                 "label": p["label"], "score": p["score"]}
                for i, p in enumerate(ranked)
            ],
        }

        output_json = json.dumps(output, ensure_ascii=False, indent=2)
        if args.output_file:
            with open(args.output_file, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(json.dumps({
                "status": "ok",
                "output_file": args.output_file,
                "top_path": ranked[0]["path_id"] if ranked else None,
                "top_score": ranked[0]["score"] if ranked else None,
            }, ensure_ascii=False))
        else:
            print(output_json)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
