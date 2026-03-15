"""
inject_event: Inject suggestion events into CareerState (Phase D).

After Opus SubAgent extracts suggestions from Swarm conversations (Phase C),
this CLI validates and applies them to the CareerState with Layer 3 validation.

Usage:
    python -m cc_layer.cli.inject_event \
        --state-file path/state.json \
        --path-id path_c \
        --round-num 5 \
        --suggestion '{"type":"pivot","confidence":0.82,...}'

Output:
    {"injected": true/false, "type": "...", "reason": "...", "path_id": "..."}
"""
import argparse
import json
import sys
from datetime import datetime

import cc_layer.cli  # noqa: F401

# ── L3 validation constants ──────────────────────────────────────────

ALLOWED_TYPES = frozenset([
    "pivot", "opportunity", "risk", "blocker", "acceleration",
    "deceleration", "network", "skill_shift", "lifestyle_change",
])

ALLOWED_STATE_FIELDS = frozenset([
    "role", "employer", "industry", "salary_annual", "skills",
    "stress_level", "job_satisfaction", "work_life_balance",
    "side_business", "years_in_role",
])

CONFIDENCE_THRESHOLD = 0.6
SALARY_ANOMALY_RATIO = 3.0


# ── Helpers ──────────────────────────────────────────────────────────

def _result(injected: bool, stype: str, reason: str, path_id: str) -> dict:
    return {
        "injected": injected,
        "type": stype,
        "reason": reason,
        "path_id": path_id,
    }


def validate_and_inject(state: dict, suggestion: dict | str,
                        path_id: str, round_num: int) -> dict:
    """Validate suggestion against L3 rules and inject into state if valid.

    Returns result dict. Mutates *state* in-place when injection succeeds.
    """
    # Handle "null" string
    if suggestion == "null" or suggestion is None:
        return _result(False, "null", "null_suggestion", path_id)

    if isinstance(suggestion, str):
        suggestion = json.loads(suggestion)

    stype = suggestion.get("type", "unknown")

    # ── type check ──
    if stype not in ALLOWED_TYPES:
        return _result(False, stype, "invalid_type", path_id)

    # ── confidence check ──
    confidence = suggestion.get("confidence")
    if confidence is None or not (0.0 <= confidence <= 1.0):
        return _result(False, stype, "invalid_confidence", path_id)
    if confidence < CONFIDENCE_THRESHOLD:
        return _result(False, stype, "low_confidence", path_id)

    # ── state_changes field validation ──
    state_changes = suggestion.get("state_changes", {})
    invalid_fields = set(state_changes.keys()) - ALLOWED_STATE_FIELDS
    if invalid_fields:
        return _result(False, stype, f"invalid_fields:{','.join(sorted(invalid_fields))}", path_id)

    # ── salary anomaly check ──
    career = state.get("career_state", {})
    current_salary = career.get("salary_annual", 0)
    new_salary = state_changes.get("salary_annual")
    if new_salary is not None and current_salary > 0:
        if new_salary > current_salary * SALARY_ANOMALY_RATIO:
            return _result(False, stype, "salary_anomaly", path_id)

    # ── All checks passed — apply ──
    for field, value in state_changes.items():
        if field == "skills" and isinstance(value, list):
            existing = career.get("skills", [])
            career["skills"] = list(dict.fromkeys(existing + value))
        else:
            career[field] = value

    # Add event log entry
    events = career.setdefault("events_this_round", [])
    events.append({
        "type": stype,
        "confidence": confidence,
        "path_id": path_id,
        "round": round_num,
        "state_changes": state_changes,
        "injected_at": datetime.now().isoformat(),
    })

    return _result(True, stype, "accepted", path_id)


def main():
    parser = argparse.ArgumentParser(
        description="Inject suggestion events into CareerState (Phase D)"
    )
    parser.add_argument("--state-file", required=True, help="Path to state JSON file")
    parser.add_argument("--path-id", required=True, help="Path identifier (e.g. path_c)")
    parser.add_argument("--round-num", type=int, required=True, help="Current round number")
    parser.add_argument("--suggestion", required=True,
                        help='Suggestion JSON string or "null"')

    args = parser.parse_args()

    try:
        # Read state
        with open(args.state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        # Parse suggestion
        suggestion = args.suggestion
        if suggestion != "null":
            try:
                suggestion = json.loads(suggestion)
            except json.JSONDecodeError as e:
                print(json.dumps(_result(False, "unknown", f"json_parse_error:{e}", args.path_id)))
                sys.exit(0)

        result = validate_and_inject(state, suggestion, args.path_id, args.round_num)

        # Write back state if injected
        if result["injected"]:
            with open(args.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
