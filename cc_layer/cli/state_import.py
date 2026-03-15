"""
state_import: Reconstruct agent_state.json from Zep facts or raw JSON.

Usage:
    python -m cc_layer.cli.state_import \
        --facts-file facts.json \
        --output-dir cc_layer/state/session_xxx

    python -m cc_layer.cli.state_import \
        --raw-file raw_state.json \
        --output-dir cc_layer/state/session_xxx

Output:
    Creates agent_state.json in output-dir
"""
import argparse
import json
import os
import re

import cc_layer.cli  # noqa: F401


def parse_zep_facts_to_state(facts: list[str]) -> dict:
    """Parse Zep fact strings back into identity + state structure.

    This is a best-effort reconstruction. Zep facts are natural language,
    so parsing is approximate. For accurate state transfer, use raw format.
    """
    identity = {
        "name": "Unknown",
        "age_at_start": 30,
        "gender": "",
        "education": "",
        "mbti": "",
        "stable_traits": [],
        "certifications": [],
        "career_history_summary": "",
    }
    state = {
        "current_round": 0,
        "current_age": 30,
        "role": "",
        "employer": "",
        "industry": "",
        "years_in_role": 0,
        "salary_annual": 0,
        "skills": [],
        "family": [],
        "marital_status": "single",
        "cash_buffer": 0,
        "mortgage_remaining": 0,
        "monthly_expenses": 25,
        "stress_level": 0.3,
        "job_satisfaction": 0.5,
        "work_life_balance": 0.5,
        "blockers": [],
        "events_this_round": [],
    }

    for fact in facts:
        # Extract name from first fact mentioning a person
        name_match = re.match(r"^(.+?)(?:は|の|に)", fact)
        if name_match and identity["name"] == "Unknown":
            identity["name"] = name_match.group(1)

        # Age
        age_match = re.search(r"現在(\d+)歳", fact)
        if age_match:
            state["current_age"] = int(age_match.group(1))
            identity["age_at_start"] = state["current_age"]

        # Education
        if "学歴" in fact:
            edu_match = re.search(r"学歴は(.+?)です", fact)
            if edu_match:
                identity["education"] = edu_match.group(1)

        # MBTI
        if "MBTI" in fact:
            mbti_match = re.search(r"MBTIタイプは([A-Z]{4})", fact)
            if mbti_match:
                identity["mbti"] = mbti_match.group(1)

        # Employment
        if "勤務" in fact:
            emp_match = re.search(r"(.+?)で(.+?)として勤務", fact)
            if emp_match:
                state["employer"] = emp_match.group(1).split("は")[-1]
                state["role"] = emp_match.group(2)

        # Industry
        if "業界" in fact:
            ind_match = re.search(r"(.+?)業界", fact)
            if ind_match:
                state["industry"] = ind_match.group(1).split("は")[-1]

        # Salary
        salary_match = re.search(r"年収は(\d+)万円", fact)
        if salary_match:
            state["salary_annual"] = int(salary_match.group(1))

        # Marital status
        if "既婚" in fact:
            state["marital_status"] = "married"
        elif "離婚" in fact:
            state["marital_status"] = "divorced"

        # Children
        child_match = re.search(r"(\d+)歳の子供", fact)
        if child_match:
            state["family"].append({
                "relation": "child",
                "age": int(child_match.group(1)),
                "notes": "",
            })

        # Cash buffer
        cash_match = re.search(r"金融資産は約(\d+)万円", fact)
        if cash_match:
            state["cash_buffer"] = int(cash_match.group(1))

        # Mortgage
        mortgage_match = re.search(r"(\d+)万円のローン", fact)
        if mortgage_match:
            state["mortgage_remaining"] = int(mortgage_match.group(1))

        # Certifications
        cert_match = re.search(r"(.+?)の資格を保有", fact)
        if cert_match:
            identity["certifications"].append(cert_match.group(1).split("は")[-1])

    return {"identity": identity, "state": state, "seed": None}


def main():
    parser = argparse.ArgumentParser(description="Import state from Zep facts or raw JSON")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--facts-file", help="Path to Zep facts JSON array file")
    group.add_argument("--raw-file", help="Path to raw agent_state.json")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    args = parser.parse_args()

    if args.raw_file:
        with open(args.raw_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        with open(args.facts_file, "r", encoding="utf-8") as f:
            facts = json.load(f)
        data = parse_zep_facts_to_state(facts)

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, "agent_state.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(json.dumps({"status": "ok", "output_path": output_path}, ensure_ascii=False))


if __name__ == "__main__":
    main()
