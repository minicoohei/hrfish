#!/usr/bin/env python3
"""MiroFish ファクトチェック CLI

確率・統計主張の抽出と検証結果の管理。

Usage:
    # Step 1: multipath_result.jsonから確率主張を抽出
    python -m cc_layer.cli.fact_check extract \
        --session-dir cc_layer/state/demo_session \
        --output cc_layer/state/demo_session/fact_check_claims.json

    # Step 2: FactCheckerAgentが検証後、結果を統合
    python -m cc_layer.cli.fact_check merge \
        --session-dir cc_layer/state/demo_session \
        --checks cc_layer/state/demo_session/fact_check.json

    # Step 3: 検証結果のサマリーを表示
    python -m cc_layer.cli.fact_check summary \
        --session-dir cc_layer/state/demo_session
"""
import argparse
import json
import os
import sys
from datetime import datetime


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_claims(session_dir: str) -> list:
    """multipath_result.json から全ての確率・統計主張を抽出"""
    result_path = os.path.join(session_dir, "multipath_result.json")
    if not os.path.exists(result_path):
        print(f"Error: {result_path} not found", file=sys.stderr)
        sys.exit(1)

    result = load_json(result_path)
    claims = []
    claim_id = 0

    for p in result.get("paths", []):
        pid = p.get("path_id", f"path_{claim_id}")

        # Scenario-level probabilities
        for s in p.get("scenarios", []):
            sid = s.get("scenario_id", "unknown")
            claims.append({
                "claim_id": f"{pid}_{sid}_prob",
                "location": f"{pid} > scenarios > {sid}",
                "type": "scenario_probability",
                "claimed_value": s.get("probability"),
                "claimed_note": s.get("probability_note", ""),
                "path_label": p.get("label", ""),
                "scenario_label": s.get("label", ""),
            })

            # Event-level probabilities within scenario periods
            for period in s.get("periods", []):
                for ev in period.get("events", []):
                    if "probability" in ev:
                        claim_id += 1
                        claims.append({
                            "claim_id": f"{pid}_{sid}_ev_{claim_id}",
                            "location": f"{pid} > {sid} > {period.get('period_name', '')} > {ev.get('type', '')}",
                            "type": "event_probability",
                            "claimed_value": ev.get("probability"),
                            "claimed_note": ev.get("probability_note", ""),
                            "event_type": ev.get("type", ""),
                            "event_desc": ev.get("description", ""),
                        })

        # Common period events
        for period in p.get("common_periods", []):
            for ev in period.get("events", []):
                if "probability" in ev:
                    claim_id += 1
                    claims.append({
                        "claim_id": f"{pid}_common_ev_{claim_id}",
                        "location": f"{pid} > common > {period.get('period_name', '')} > {ev.get('type', '')}",
                        "type": "event_probability",
                        "claimed_value": ev.get("probability"),
                        "claimed_note": ev.get("probability_note", ""),
                        "event_type": ev.get("type", ""),
                        "event_desc": ev.get("description", ""),
                    })

        # Overall path probability
        if "overall_probability" in p:
            claims.append({
                "claim_id": f"{pid}_overall",
                "location": f"{pid} > overall_probability",
                "type": "overall_probability",
                "claimed_value": p.get("overall_probability"),
                "claimed_note": p.get("probability_rationale", ""),
                "path_label": p.get("label", ""),
            })

    # Extract embedded statistics from probability_notes
    embedded = extract_embedded_stats(claims)

    return {
        "extracted_at": datetime.now().isoformat(),
        "source": "multipath_result.json",
        "total_claims": len(claims),
        "total_embedded_stats": len(embedded),
        "claims": claims,
        "embedded_stats": embedded,
    }


def extract_embedded_stats(claims: list) -> list:
    """probability_note内の具体的数値を抽出"""
    import re
    stats = []
    seen = set()

    for c in claims:
        note = c.get("claimed_note", "")
        if not note:
            continue

        # Match patterns like "10-20%", "年間50件", "1社に1席"
        patterns = [
            r'(\d+[-〜~]\d+%)',           # "10-20%"
            r'(\d+%)',                     # "30%"
            r'(年間\d+[-〜~]?\d*件?)',     # "年間50件"
            r'(1社に\d+席)',               # "1社に1席"
            r'(\d+[-〜~]\d+万)',           # "1000-1400万"
            r'(\d+[-〜~]\d+倍)',           # "100-300倍"
        ]
        for pat in patterns:
            for match in re.finditer(pat, note):
                stat_text = match.group(1)
                key = f"{stat_text}|{note[:30]}"
                if key not in seen:
                    seen.add(key)
                    stats.append({
                        "stat": stat_text,
                        "context": note[:100],
                        "source_claim": c["claim_id"],
                    })

    return stats


def merge_checks(session_dir: str, checks_path: str):
    """FactCheckerAgentの結果をfact_check_result.jsonとして統合保存"""
    checks = load_json(checks_path)
    result_path = os.path.join(session_dir, "fact_check_result.json")
    save_json(result_path, checks)
    meta = checks.get("fact_check_metadata", {})
    print(f"Merged {meta.get('total_claims', '?')} claims: "
          f"verified={meta.get('verified', 0)}, "
          f"adjusted={meta.get('adjusted', 0)}, "
          f"unverified={meta.get('unverified', 0)}, "
          f"disputed={meta.get('disputed', 0)}")
    print(f"Saved to: {result_path}")


def show_summary(session_dir: str):
    """ファクトチェック結果のサマリーを表示"""
    result_path = os.path.join(session_dir, "fact_check_result.json")
    if not os.path.exists(result_path):
        print("No fact-check results found. Run FactCheckerAgent first.")
        return

    result = load_json(result_path)
    meta = result.get("fact_check_metadata", {})
    checks = result.get("checks", [])

    print(f"\n=== Fact Check Summary ===")
    print(f"Checked at: {meta.get('checked_at', 'N/A')}")
    print(f"Total claims: {meta.get('total_claims', len(checks))}")
    print(f"  ✅ Verified:   {meta.get('verified', 0)}")
    print(f"  ⚠️  Adjusted:   {meta.get('adjusted', 0)}")
    print(f"  ❓ Unverified: {meta.get('unverified', 0)}")
    print(f"  ❌ Disputed:   {meta.get('disputed', 0)}")

    # Show disputed/adjusted items
    flagged = [c for c in checks if c.get("status") in ("disputed", "adjusted")]
    if flagged:
        print(f"\n--- Flagged Items ({len(flagged)}) ---")
        for c in flagged:
            icon = "❌" if c["status"] == "disputed" else "⚠️"
            print(f"\n{icon} {c['location']}")
            print(f"   Original: {c.get('original_value')} — {c.get('original_note', '')[:60]}")
            print(f"   Verified: {c.get('verified_value', 'N/A')}")
            if c.get("suggested_correction"):
                sc = c["suggested_correction"]
                print(f"   Suggested: {sc.get('value')} — {sc.get('note_addition', '')[:60]}")
            for src in c.get("sources", [])[:2]:
                print(f"   Source: {src.get('title', '')} [{src.get('reliability', '')}]")


def main():
    parser = argparse.ArgumentParser(description="MiroFish Fact Check CLI")
    sub = parser.add_subparsers(dest="command")

    # extract
    p_ext = sub.add_parser("extract", help="Extract probability claims from multipath_result.json")
    p_ext.add_argument("--session-dir", required=True)
    p_ext.add_argument("--output", default=None)

    # merge
    p_merge = sub.add_parser("merge", help="Merge FactCheckerAgent results")
    p_merge.add_argument("--session-dir", required=True)
    p_merge.add_argument("--checks", required=True)

    # summary
    p_sum = sub.add_parser("summary", help="Show fact-check summary")
    p_sum.add_argument("--session-dir", required=True)

    args = parser.parse_args()

    if args.command == "extract":
        result = extract_claims(args.session_dir)
        output = args.output or os.path.join(args.session_dir, "fact_check_claims.json")
        save_json(output, result)
        print(f"Extracted {result['total_claims']} claims, {result['total_embedded_stats']} embedded stats")
        print(f"Saved to: {output}")

    elif args.command == "merge":
        merge_checks(args.session_dir, args.checks)

    elif args.command == "summary":
        show_summary(args.session_dir)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
