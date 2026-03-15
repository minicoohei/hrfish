"""Validate MiroFish session directory completeness."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationReport:
    """Result of validating a session directory."""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def format(self) -> str:
        lines = []
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def validate_session(session_dir: str) -> ValidationReport:
    """Validate that a session directory has all required files."""
    sdir = Path(session_dir)
    report = ValidationReport()

    required = ["agent_state.json", "multipath_result.json", "swarm_agents.json"]
    optional = ["fact_check_result.json", "macro_trends.json", "profile.json", "form.json"]

    for f in required:
        fpath = sdir / f
        if not fpath.exists():
            report.errors.append(f"{f} not found (required)")
        else:
            try:
                json.loads(fpath.read_text())
            except json.JSONDecodeError as e:
                report.errors.append(f"{f}: invalid JSON: {e}")

    for f in optional:
        fpath = sdir / f
        if not fpath.exists():
            report.warnings.append(f"{f} not found (optional)")
        else:
            try:
                json.loads(fpath.read_text())
            except json.JSONDecodeError as e:
                report.warnings.append(f"{f}: invalid JSON (optional): {e}")

    # multipath_result.json 構造チェック
    mp_path = sdir / "multipath_result.json"
    if mp_path.exists():
        try:
            mp = json.loads(mp_path.read_text())
            _validate_multipath_structure(mp, report)
        except json.JSONDecodeError:
            pass  # Already caught above

    swarm_dir = sdir / "swarm"
    jsonl_files = sorted(swarm_dir.glob("all_actions_round_*.jsonl")) if swarm_dir.exists() else []
    if not jsonl_files:
        report.warnings.append("swarm/ directory empty or missing")
    else:
        for jf in jsonl_files:
            for line_num, line in enumerate(jf.read_text().strip().split("\n"), 1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    report.errors.append(f"{jf.name}:{line_num}: invalid JSONL: {e}")

    return report


SNAPSHOT_REQUIRED_FIELDS = {"annual_income", "satisfaction", "stress", "work_life_balance"}


def _validate_period(period: dict, path_id: str, location: str, report: ValidationReport):
    """Validate a single period's structure."""
    snap = period.get("snapshot")
    pname = period.get("period_name", "?")
    if snap is None:
        report.warnings.append(
            f"{path_id}/{location}/{pname}: snapshot missing (will be interpolated)"
        )
    elif isinstance(snap, dict):
        missing = SNAPSHOT_REQUIRED_FIELDS - set(snap.keys())
        if missing:
            report.warnings.append(
                f"{path_id}/{location}/{pname}: snapshot missing fields: {missing}"
            )
        # 0-100 scale detection
        for key in ("satisfaction", "stress", "work_life_balance"):
            val = snap.get(key)
            if isinstance(val, (int, float)) and val > 1:
                report.warnings.append(
                    f"{path_id}/{location}/{pname}: {key}={val} looks like 0-100 scale (will be auto-scaled)"
                )
    # events: string vs dict
    for ev in period.get("events", []):
        if isinstance(ev, str):
            report.warnings.append(
                f"{path_id}/{location}/{pname}: event is string, not dict (will be auto-converted)"
            )
            break


def _validate_scenario(scenario: dict, path_id: str, report: ValidationReport):
    """Validate a single scenario's structure."""
    sid = scenario.get("scenario_id", "?")
    if "final_state" not in scenario:
        report.errors.append(f"{path_id}/{sid}: final_state missing (required)")
    elif isinstance(scenario["final_state"], dict):
        missing = SNAPSHOT_REQUIRED_FIELDS - set(scenario["final_state"].keys())
        if missing:
            report.warnings.append(
                f"{path_id}/{sid}/final_state: missing fields: {missing}"
            )
    if "probability" not in scenario:
        report.warnings.append(
            f"{path_id}/{sid}: probability missing (will use default)"
        )
    if "label" not in scenario:
        report.warnings.append(
            f"{path_id}/{sid}: label missing (will use default)"
        )
    for p in scenario.get("periods", []):
        _validate_period(p, path_id, f"scenario/{sid}", report)


def _validate_multipath_structure(mp: dict, report: ValidationReport):
    """Validate multipath_result.json internal structure."""
    paths = mp.get("paths", [])
    if not paths:
        report.warnings.append("multipath_result.json: paths is empty")
        return

    for path in paths:
        pid = path.get("path_id", "?")
        if not path.get("label") and not path.get("path_label"):
            report.warnings.append(f"{pid}: label missing")

        # scenarios type check
        scenarios = path.get("scenarios", [])
        if isinstance(scenarios, dict):
            report.warnings.append(
                f"{pid}: scenarios is dict, not list (will be auto-converted)"
            )
            scenarios = [{"scenario_id": k, **v} if isinstance(v, dict) else {"scenario_id": k}
                         for k, v in scenarios.items()]

        if not scenarios:
            report.warnings.append(f"{pid}: scenarios is empty")

        # branch_point type check
        bp = path.get("branch_point")
        if isinstance(bp, dict):
            report.warnings.append(
                f"{pid}: branch_point is dict, not string (will be auto-converted)"
            )

        # common_periods
        for p in path.get("common_periods", []):
            _validate_period(p, pid, "common_periods", report)

        # each scenario
        for s in scenarios:
            _validate_scenario(s, pid, report)

        # ダウンサイド欠如チェック
        if len(scenarios) >= 2:
            incomes = {}
            for s in scenarios:
                fs = s.get("final_state", {})
                inc = fs.get("annual_income", fs.get("salary", 0))
                incomes[s.get("scenario_id", "?")] = inc
            best_inc = incomes.get("best", 0)
            base_inc = incomes.get("base", 0)
            worst_inc = incomes.get("worst", 0)
            # base vs best
            if best_inc > 0 and base_inc > 0:
                ratio = base_inc / best_inc
                if ratio > 0.85:
                    report.warnings.append(
                        f"{pid}: base income ({base_inc}) is {ratio:.0%} of best ({best_inc}). "
                        f"Downside scenario may be too optimistic"
                    )
            # worst vs best
            if best_inc > 0 and worst_inc > 0:
                ratio = worst_inc / best_inc
                if ratio > 0.7:
                    report.warnings.append(
                        f"{pid}: worst income ({worst_inc}) is {ratio:.0%} of best ({best_inc}). "
                        f"Need more realistic downside (target: worst < 50% of best)"
                    )

        # 単位エラーチェック: annual_income > 100000 は円の可能性
        for s in scenarios:
            fs = s.get("final_state", {})
            inc = fs.get("annual_income", 0)
            if isinstance(inc, (int, float)) and inc > 100000:
                report.errors.append(
                    f"{pid}/{s.get('scenario_id','?')}: annual_income={inc} "
                    f"looks like yen, not 万円 (will be auto-converted)"
                )
