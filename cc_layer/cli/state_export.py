"""
state_export: Convert simulation state to Zep-compatible facts format.

Usage:
    python -m cc_layer.cli.state_export \
        --state-file cc_layer/state/session_xxx/agent_state.json \
        --format zep-facts

Output (stdout JSON):
    Array of fact strings suitable for Zep graph.add()
"""
import argparse
import json

import cc_layer.cli  # noqa: F401


def state_to_zep_facts(identity: dict, state: dict) -> list[str]:
    """Convert identity + state into natural language facts for Zep."""
    facts = []
    name = identity.get("name", "候補者")

    # Identity facts
    if identity.get("education"):
        facts.append(f"{name}の最終学歴は{identity['education']}です。")
    if identity.get("mbti"):
        facts.append(f"{name}のMBTIタイプは{identity['mbti']}です。")
    if identity.get("career_history_summary"):
        facts.append(f"{name}の職歴概要: {identity['career_history_summary']}")
    for cert in identity.get("certifications", []):
        facts.append(f"{name}は{cert}の資格を保有しています。")

    # Current state facts
    age = state.get("current_age", 0)
    facts.append(f"{name}は現在{age}歳です。")

    if state.get("employer") and state.get("role"):
        facts.append(f"{name}は{state['employer']}で{state['role']}として勤務しています。")
    if state.get("industry"):
        facts.append(f"{name}は{state['industry']}業界で働いています。")
    if state.get("salary_annual"):
        facts.append(f"{name}の年収は{state['salary_annual']}万円です。")

    # Family facts
    marital = state.get("marital_status", "single")
    if marital == "married":
        facts.append(f"{name}は既婚です。")
    elif marital == "divorced":
        facts.append(f"{name}は離婚経験があります。")

    for fm in state.get("family", []):
        rel = fm.get("relation", "")
        fm_age = fm.get("age", 0)
        notes = fm.get("notes", "")
        if rel == "child":
            facts.append(f"{name}には{fm_age}歳の子供がいます。{notes}")
        elif rel == "parent":
            desc = f"{name}の親（{fm_age}歳）"
            if notes:
                desc += f"は{notes}です"
            facts.append(desc + "。")
        elif rel == "spouse":
            facts.append(f"{name}の配偶者は{fm_age}歳です。")

    # Financial facts
    if state.get("cash_buffer"):
        facts.append(f"{name}の金融資産は約{state['cash_buffer']}万円です。")
    if state.get("mortgage_remaining", 0) > 0:
        facts.append(f"{name}には{state['mortgage_remaining']}万円のローン残額があります。")

    # Well-being facts
    stress = state.get("stress_level", 0.3)
    if stress > 0.7:
        facts.append(f"{name}は高いストレスを感じています（{stress:.1f}/1.0）。")
    satisfaction = state.get("job_satisfaction", 0.5)
    if satisfaction < 0.3:
        facts.append(f"{name}は仕事に対する満足度が低い状態です。")
    elif satisfaction > 0.7:
        facts.append(f"{name}は仕事に高い満足感を持っています。")

    # Blocker facts
    for b in state.get("blockers", []):
        facts.append(f"{name}の制約: {b.get('reason', '')}")

    # Recent events
    for evt in state.get("events_this_round", []):
        facts.append(f"{name}に起きた出来事: {evt}")

    return facts


def main():
    parser = argparse.ArgumentParser(description="Export simulation state to Zep facts")
    parser.add_argument("--state-file", required=True, help="Path to agent_state.json")
    parser.add_argument("--format", default="zep-facts", choices=["zep-facts", "raw"],
                        help="Output format")
    args = parser.parse_args()

    with open(args.state_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if args.format == "zep-facts":
        facts = state_to_zep_facts(data["identity"], data["state"])
        print(json.dumps(facts, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
