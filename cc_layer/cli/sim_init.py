"""
sim_init: Initialize simulation state from profile + form JSON.

Usage:
    python -m cc_layer.cli.sim_init \
        --profile '{"name":"田中","age":35,...}' \
        --form '{"family_members":[...],"mortgage_remaining":3000}' \
        --seed 42 \
        --output-dir cc_layer/state/session_xxx

Output:
    Creates agent_state.json in output-dir containing:
    {"identity": {...}, "state": {...}, "seed": 42}
"""
import argparse
import json
import os
import sys

# Ensure backend is importable
import cc_layer.cli  # noqa: F401

from app.models.life_simulator import BaseIdentity, CareerState, FamilyMember
from app.services.life_simulation_loop import FormInput, cash_range_to_value


def build_identity(profile: dict) -> BaseIdentity:
    return BaseIdentity(
        name=profile.get("name", "Unknown"),
        age_at_start=profile.get("age", 30),
        gender=profile.get("gender", ""),
        education=profile.get("education", ""),
        mbti=profile.get("mbti", ""),
        stable_traits=profile.get("traits", []),
        certifications=profile.get("certifications", []),
        career_history_summary=profile.get("career_summary", ""),
    )


def build_initial_state(profile: dict, form: dict) -> CareerState:
    family_members = [
        FamilyMember(
            relation=f.get("relation", "child"),
            age=f.get("age", 0),
            notes=f.get("notes", ""),
        )
        for f in form.get("family_members", [])
    ]

    cash_range = form.get("cash_buffer_range", "500未満")
    cash_buffer = form.get("cash_buffer")
    if cash_buffer is None:
        cash_buffer = cash_range_to_value(cash_range)

    return CareerState(
        current_round=0,
        current_age=profile.get("age", 30),
        role=profile.get("current_role", ""),
        employer=profile.get("current_employer", ""),
        industry=profile.get("industry", ""),
        years_in_role=profile.get("years_in_role", 0),
        salary_annual=profile.get("salary", 0),
        skills=profile.get("skills", []),
        family=family_members,
        marital_status=form.get("marital_status", "single"),
        cash_buffer=cash_buffer,
        mortgage_remaining=form.get("mortgage_remaining", 0),
        monthly_expenses=form.get("monthly_expenses", 25),
    )


def main():
    parser = argparse.ArgumentParser(description="Initialize MiroFish simulation state")
    parser.add_argument("--profile", required=True, help="Profile JSON string or @filepath")
    parser.add_argument("--form", required=True, help="Form input JSON string or @filepath")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--output-dir", required=True, help="Output directory for state files")
    args = parser.parse_args()

    # Parse JSON inputs (support @file syntax)
    def load_json(val: str) -> dict:
        if val.startswith("@"):
            with open(val[1:], "r") as f:
                return json.load(f)
        return json.loads(val)

    profile = load_json(args.profile)
    form = load_json(args.form)

    identity = build_identity(profile)
    state = build_initial_state(profile, form)

    # Write output
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, "agent_state.json")

    output = {
        "identity": identity.to_dict(),
        "state": state.to_dict(),
        "seed": args.seed,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print result to stdout
    print(json.dumps({"status": "ok", "output_path": output_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
