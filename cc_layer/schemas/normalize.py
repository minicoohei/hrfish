"""Normalize SubAgent output to canonical form.

SubAgents (LLMs) produce JSON with field name variations.
This module absorbs those variations and produces canonical models.

Two entry points:
- normalize_session_in_memory(): for report_html.py (no file writes)
- normalize_session_to_disk(): for pipeline_run --phase normalize
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from cc_layer.schemas.canonical import (
    ExpandedPath,
    MultipathResult,
    SwarmAction,
    SwarmAgent,
)


def normalize_snapshot(raw: dict) -> dict:
    """Normalize snapshot field names and value ranges.

    - salary → annual_income
    - annual_income > 100000 → 円→万円変換（÷10000）
    - satisfaction/stress/work_life_balance: scale 0-100 → 0-1
    """
    out = dict(raw)
    if "salary" in out and "annual_income" not in out:
        out["annual_income"] = out.pop("salary")
    # 円→万円変換: 100000以上は円で入っている可能性が高い
    if "annual_income" in out and isinstance(out["annual_income"], (int, float)):
        if out["annual_income"] > 100000:
            print(
                f"WARN: annual_income={out['annual_income']} looks like yen, not 万円. "
                f"Converting to 万円 (÷10000)",
                file=sys.stderr,
            )
            out["annual_income"] = round(out["annual_income"] / 10000, 1)
    # Scale 0-100 values to 0-1 for percentage fields
    for key in ("satisfaction", "stress", "work_life_balance"):
        if key in out and isinstance(out[key], (int, float)) and out[key] > 1:
            out[key] = round(out[key] / 100, 4)
    return out


def _normalize_events(events_list):
    """Normalize events: string → Event dict."""
    result = []
    for ev in events_list:
        if isinstance(ev, str):
            result.append({"type": "", "description": ev})
        elif isinstance(ev, dict):
            result.append(ev)
    return result


def _normalize_scenarios_dict(scenarios):
    """Convert dict-style scenarios to list-style."""
    if isinstance(scenarios, dict):
        result = []
        for k, v in scenarios.items():
            if isinstance(v, dict):
                result.append({"scenario_id": k, **v})
            else:
                result.append({"scenario_id": k})
        return result
    return scenarios


def normalize_expanded_path(raw: dict) -> ExpandedPath:
    """Normalize a SubAgent path expansion output to canonical form."""
    data = copy.deepcopy(raw)

    # scenarios: dict → list
    if isinstance(data.get("scenarios"), dict):
        data["scenarios"] = _normalize_scenarios_dict(data["scenarios"])

    # path_label → label
    if "path_label" in data and "label" not in data:
        data["label"] = data.pop("path_label")

    # branch_point: dict → string
    bp = data.get("branch_point", "")
    if isinstance(bp, dict):
        # Extract description/timing text from dict
        parts = []
        if bp.get("timing"):
            parts.append(str(bp["timing"]))
        if bp.get("description"):
            parts.append(str(bp["description"]))
        if bp.get("trigger"):
            parts.append(str(bp["trigger"]))
        data["branch_point"] = "。".join(parts) if parts else str(bp)

    for s in data.get("scenarios", []):
        pid = data.get("path_id", "?")
        sid = s.get("scenario_id", "?")
        # probability: default by scenario_id if missing
        if "probability" not in s:
            defaults = {"best": 0.15, "likely": 0.45, "base": 0.25, "worst": 0.15}
            s["probability"] = defaults.get(sid, 0.25)
            print(f"WARN: {pid}/{sid}: probability missing, defaulting to {s['probability']}", file=sys.stderr)
        # label: default from scenario_id if missing
        if "label" not in s:
            s["label"] = {
                "best": "ベストケース", "likely": "標準ケース",
                "base": "ベースケース", "worst": "ワーストケース",
            }.get(sid, sid)
            print(f"WARN: {pid}/{sid}: label missing, defaulting to '{s['label']}'", file=sys.stderr)
        # final_salary/final_satisfaction → final_state, then normalize
        fs = s.get("final_state", {}) or {}
        s["final_state"] = normalize_snapshot({
            "annual_income": s.pop("final_salary", fs.get("annual_income", fs.get("salary", 0))),
            "satisfaction": s.pop("final_satisfaction", fs.get("satisfaction", 0.5)),
            "stress": s.pop("final_stress", fs.get("stress", 0.5)),
            "work_life_balance": s.pop("final_wlb", fs.get("work_life_balance", 0.5)),
            **{k: v for k, v in fs.items() if k not in ("annual_income", "salary", "satisfaction", "stress", "work_life_balance")},
        })

        # periods 内の snapshot + events 正規化
        for p in s.get("periods", []):
            if "snapshot" in p:
                p["snapshot"] = normalize_snapshot(p["snapshot"])
            if "events" in p:
                p["events"] = _normalize_events(p["events"])

        # snapshot が欠落している periods を補間（警告付き）
        # common_periods の最後の snapshot → final_state の間で線形補間
        scenario_periods = s.get("periods", [])
        missing_count = sum(1 for p in scenario_periods if "snapshot" not in p)
        if missing_count > 0 and s.get("final_state"):
            pid = data.get("path_id", "?")
            sid = s.get("scenario_id", "?")
            missing_names = [p.get("period_name", "?") for p in scenario_periods if "snapshot" not in p]
            print(
                f"WARN: {pid}/{sid}: {missing_count} periods missing snapshot "
                f"({', '.join(missing_names)}), interpolating from common_periods → final_state",
                file=sys.stderr,
            )
            # 起点: common_periods の最後の snapshot、なければ初期値
            common = data.get("common_periods", [])
            start_snap = {}
            for cp in reversed(common):
                if "snapshot" in cp:
                    start_snap = cp["snapshot"]
                    break
            end_snap = s["final_state"]
            total_steps = missing_count + 1  # final_state を含む
            for idx, p in enumerate(scenario_periods):
                if "snapshot" not in p:
                    t = (idx + 1) / total_steps
                    interp = {}
                    for key in ("annual_income", "satisfaction", "stress", "work_life_balance"):
                        sv = start_snap.get(key, 0)
                        ev = end_snap.get(key, 0)
                        interp[key] = round(sv + (ev - sv) * t, 4)
                    p["snapshot"] = interp

    # common_periods の snapshot + events 正規化
    for p in data.get("common_periods", []):
        if "snapshot" in p:
            p["snapshot"] = normalize_snapshot(p["snapshot"])
        if "events" in p:
            p["events"] = _normalize_events(p["events"])

    # upside/risk 自動生成（空の場合）
    scenarios = data.get("scenarios", [])
    if not data.get("upside") and scenarios:
        best = next((s for s in scenarios if s["scenario_id"] == "best"), None)
        if best:
            fs = best.get("final_state", {})
            sal = fs.get("annual_income", 0)
            prob = int(best.get("probability", 0) * 100)
            data["upside"] = f'{best.get("label", "Best")}: 年収{sal}万（確率{prob}%）'
    if not data.get("risk") and scenarios:
        # worst があれば worst、なければ base をリスクとして表示
        worst = next((s for s in scenarios if s["scenario_id"] == "worst"), None)
        risk_s = worst or next((s for s in scenarios if s["scenario_id"] == "base"), None)
        if risk_s:
            fs = risk_s.get("final_state", {})
            sal = fs.get("annual_income", 0)
            prob = int(risk_s.get("probability", 0) * 100)
            data["risk"] = f'{risk_s.get("label", "Worst")}: 年収{sal}万（確率{prob}%）'

    # Scenario ordering: best >= likely >= base >= worst for income and satisfaction.
    # Use sort-and-reassign instead of pairwise swaps to avoid partial-sort bugs.
    if scenarios:
        expected_order = ["best", "likely", "base", "worst"]
        pid = data.get("path_id", "?")
        scenario_map = {s["scenario_id"]: s for s in scenarios if s.get("scenario_id") in expected_order}
        present = [sid for sid in expected_order if sid in scenario_map]

        if len(present) >= 2:
            # --- P0-1a: Sort income values descending and reassign ---
            incomes = [scenario_map[sid]["final_state"].get("annual_income", 0) for sid in present]
            sorted_incomes = sorted(incomes, reverse=True)
            if incomes != sorted_incomes:
                print(
                    f"WARN: {pid}: scenario income inversion — "
                    f"reordering {dict(zip(present, incomes))} → {dict(zip(present, sorted_incomes))}",
                    file=sys.stderr,
                )
                for sid, val in zip(present, sorted_incomes):
                    scenario_map[sid]["final_state"]["annual_income"] = val

            # --- P0-1b: Sort satisfaction values descending and reassign ---
            sats = [scenario_map[sid]["final_state"].get("satisfaction", 0.5) for sid in present]
            sorted_sats = sorted(sats, reverse=True)
            if sats != sorted_sats:
                print(
                    f"WARN: {pid}: scenario satisfaction inversion — "
                    f"reordering {dict(zip(present, sats))} → {dict(zip(present, sorted_sats))}",
                    file=sys.stderr,
                )
                for sid, val in zip(present, sorted_sats):
                    scenario_map[sid]["final_state"]["satisfaction"] = val

            # --- P0-2: Warn when adjacent scenarios have identical income ---
            for j in range(len(present) - 1):
                inc_h = scenario_map[present[j]]["final_state"].get("annual_income", 0)
                inc_l = scenario_map[present[j + 1]]["final_state"].get("annual_income", 0)
                if inc_h == inc_l and inc_h > 0:
                    print(
                        f"WARN: {pid}: scenario income collapse — "
                        f"{present[j]} and {present[j+1]} both have annual_income={inc_h}万. "
                        f"Scenarios are not differentiated.",
                        file=sys.stderr,
                    )

    # path-level finals (空リストガード)
    if not scenarios:
        return ExpandedPath.model_validate(data)
    likely = next((s for s in scenarios if s["scenario_id"] == "likely"), scenarios[0])
    if data.get("final_salary") is None:
        data["final_salary"] = likely["final_state"].get("annual_income", 0)
        data["final_satisfaction"] = likely["final_state"].get("satisfaction", 0.5)

    return ExpandedPath.model_validate(data)


def normalize_swarm_action(raw: dict) -> SwarmAction:
    """Normalize swarm action output: round→round_num, content→action_args.content."""
    data = dict(raw)
    if "round_num" not in data and "round" in data:
        data["round_num"] = data.pop("round")
    # action_args が null/非dict の場合を正規化
    if not isinstance(data.get("action_args"), dict):
        data["action_args"] = {}
    if "content" in data and "content" not in data["action_args"]:
        data["action_args"]["content"] = data.pop("content")
    if "target" in data:
        data["action_args"]["target_post_id"] = data.pop("target")
    return SwarmAction.model_validate(data)


def normalize_swarm_agent(raw: dict) -> SwarmAgent:
    """Normalize swarm agent profile: background/personality → bio."""
    data = dict(raw)
    # bio フォールバック: background → personality → ""
    if not data.get("bio"):
        parts = []
        if data.get("background"):
            parts.append(data["background"])
        if data.get("personality"):
            parts.append(data["personality"])
        data["bio"] = "。".join(parts) if parts else ""
    # stance フォールバック
    if not data.get("stance") and data.get("stance_default"):
        data["stance"] = data.pop("stance_default")
    return SwarmAgent.model_validate(data)


def normalize_multipath_result(raw: dict) -> MultipathResult:
    """Normalize the entire multipath_result."""
    data = copy.deepcopy(raw)
    # ranking / rankings 統一
    if "rankings" in data and "ranking" not in data:
        data["ranking"] = data.pop("rankings")
    elif "ranking" not in data:
        data["ranking"] = {}
    # 各パスを正規化
    normalized_paths = []
    for p in data.get("paths", []):
        normalized_paths.append(normalize_expanded_path(p).model_dump())
    data["paths"] = normalized_paths
    return MultipathResult.model_validate(data)


def normalize_session_in_memory(session_dir: str) -> dict:
    """Normalize session data in memory (no file writes).

    Used by report_html.py to get canonical data without modifying files.

    Returns:
        dict with keys: "multipath_result", "swarm_agents", "swarm_actions"
    """
    sdir = Path(session_dir)
    result = {}

    mp_path = sdir / "multipath_result.json"
    if mp_path.exists():
        raw = json.loads(mp_path.read_text())
        result["multipath_result"] = normalize_multipath_result(raw)

    sa_path = sdir / "swarm_agents.json"
    if sa_path.exists():
        raw_agents = json.loads(sa_path.read_text())
        result["swarm_agents"] = [normalize_swarm_agent(a) for a in raw_agents]

    swarm_dir = sdir / "swarm"
    if swarm_dir.exists():
        all_actions = []
        for jsonl_file in sorted(swarm_dir.glob("all_actions_round_*.jsonl")):
            for line in jsonl_file.read_text().strip().split("\n"):
                if line.strip():
                    all_actions.append(normalize_swarm_action(json.loads(line)))
        result["swarm_actions"] = all_actions

    return result


def normalize_session_to_disk(session_dir: str) -> dict[str, str]:
    """Normalize session data and write to disk.

    Used by pipeline_run --phase normalize only.

    Returns:
        dict mapping filename to status string
    """
    sdir = Path(session_dir)
    results = {}
    data = normalize_session_in_memory(session_dir)

    if "multipath_result" in data:
        mp_path = sdir / "multipath_result.json"
        mp_path.write_text(json.dumps(
            data["multipath_result"].model_dump(), ensure_ascii=False, indent=2
        ))
        results["multipath_result.json"] = "normalized"

    if "swarm_agents" in data:
        sa_path = sdir / "swarm_agents.json"
        sa_path.write_text(json.dumps(
            [a.model_dump() for a in data["swarm_agents"]],
            ensure_ascii=False, indent=2
        ))
        results["swarm_agents.json"] = "normalized"

    if "swarm_actions" in data:
        from collections import defaultdict
        by_round: dict[int, list] = defaultdict(list)
        for a in data["swarm_actions"]:
            by_round[a.round_num].append(a)
        swarm_dir = sdir / "swarm"
        swarm_dir.mkdir(exist_ok=True)
        for round_num, actions in sorted(by_round.items()):
            fname = f"all_actions_round_{round_num:03d}.jsonl"
            lines = [json.dumps(a.model_dump(), ensure_ascii=False) for a in actions]
            (swarm_dir / fname).write_text("\n".join(lines) + "\n")
            results[f"swarm/{fname}"] = "normalized"

    return results
