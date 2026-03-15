"""MiroFish Pipeline Runner — single entry point for deterministic steps.

This CLI orchestrates the Python-side (deterministic) steps of the pipeline.
SubAgent steps are indicated as PAUSE points with guidance on what to run next.

Usage:
    python -m cc_layer.cli.pipeline_run --session-dir SESSION_DIR --phase PHASE

Phases:
    status    - Show pipeline progress and next action
    normalize - Normalize SubAgent output to canonical form (writes to disk)
    validate  - Validate session data completeness
    report    - normalize → validate → generate HTML report
    all       - Same as status (shows what to do next)
"""
import argparse
import json
import sys
from pathlib import Path


def run_normalize(session_dir: str):
    """Normalize all session files to canonical form."""
    from cc_layer.schemas.normalize import normalize_session_to_disk
    results = normalize_session_to_disk(session_dir)
    if results:
        for fname, status in results.items():
            print(f"  [{status}] {fname}")
    else:
        print("  No files to normalize")


def run_validate(session_dir: str):
    """Validate session directory completeness."""
    from cc_layer.schemas.validate import validate_session
    report = validate_session(session_dir)
    if report.has_errors:
        print("Validation FAILED:")
        print(report.format())
        sys.exit(1)
    else:
        print("Validation OK")
        if report.warnings:
            print(report.format())


def run_report(session_dir: str, output: str | None = None):
    """normalize (to disk) → validate → report_html."""
    print("[1/3] Normalizing session data...")
    run_normalize(session_dir)
    print("[2/3] Validating session data...")
    from cc_layer.schemas.validate import validate_session
    report = validate_session(session_dir)
    if report.has_errors:
        print("Validation FAILED:")
        print(report.format())
        sys.exit(1)
    if report.warnings:
        print(report.format())
    print("[3/3] Generating HTML report...")
    from cc_layer.cli.report_html import build_html
    html = build_html(session_dir)
    out_path = output or str(Path(session_dir) / "report.html")
    Path(out_path).write_text(html)
    print(f"Report generated: {out_path}")


def run_status(session_dir: str):
    """Show pipeline progress and next action."""
    sdir = Path(session_dir)
    phases = [
        ("profile.json",             "入力: プロフィール"),
        ("form.json",                "入力: フォーム"),
        ("resume.txt",               "入力: 履歴書"),
        ("agent_state.json",         "Phase 0: 初期化 (sim_init)"),
        ("path_designs.json",        "Phase 1a: パス設計 (SubAgent)"),
        ("multipath_result.json",    "Phase 1b-2: パス展開+スコアリング"),
        ("swarm_agents.json",        "Phase 3: Swarmエージェント生成"),
        ("fact_check_claims.json",   "Phase 5: ファクトチェック抽出"),
        ("fact_check_result.json",   "Phase 6: ファクトチェック完了"),
        ("macro_trends.json",        "Phase 7: マクロトレンド (SubAgent)"),
    ]
    swarm_dir = sdir / "swarm"
    swarm_count = len(list(swarm_dir.glob("all_actions_round_*.jsonl"))) if swarm_dir.exists() else 0

    print(f"\nMiroFish Pipeline Status: {session_dir}\n")
    for fname, desc in phases:
        exists = (sdir / fname).exists()
        mark = "OK" if exists else "--"
        print(f"  [{mark}] {desc}: {fname}")
    print(f"  [{'OK' if swarm_count > 0 else '--'}] Phase 4: Swarm会話 ({swarm_count} rounds)")
    print(f"  [{'OK' if (sdir / 'report.html').exists() else '--'}] Phase 8: HTMLレポート")

    # 次のアクション提示
    print()
    if not (sdir / "profile.json").exists():
        print("次: profile.json, form.json, resume.txt を配置してください")
    elif not (sdir / "agent_state.json").exists():
        print(f"次: python -m cc_layer.cli.sim_init --profile @{session_dir}/profile.json --form @{session_dir}/form.json --output-dir {session_dir}")
    elif not (sdir / "path_designs.json").exists():
        print("次: SubAgent PathDesignerAgent を起動 (cc_layer/prompts/path_designer_agent.md)")
    elif not (sdir / "multipath_result.json").exists():
        print("次: SubAgent PathExpanderAgent x5 → multipath_run")
    elif swarm_count == 0:
        print(f"次: python -m cc_layer.cli.generate_swarm_agents --session-dir {session_dir}")
    elif not (sdir / "report.html").exists():
        print(f"次: python -m cc_layer.cli.pipeline_run --session-dir {session_dir} --phase report")
    else:
        print("パイプライン完了! report.html が生成済みです。")


def main():
    parser = argparse.ArgumentParser(
        description="MiroFish Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--session-dir", required=True, help="Session directory path")
    parser.add_argument("--phase", required=True,
                        choices=["status", "normalize", "validate", "report", "all"],
                        help="Pipeline phase to execute")
    parser.add_argument("--output", default=None, help="Output file path (for report phase)")
    args = parser.parse_args()

    if args.phase == "status" or args.phase == "all":
        run_status(args.session_dir)
    elif args.phase == "normalize":
        run_normalize(args.session_dir)
    elif args.phase == "validate":
        run_validate(args.session_dir)
    elif args.phase == "report":
        run_report(args.session_dir, args.output)


if __name__ == "__main__":
    main()
