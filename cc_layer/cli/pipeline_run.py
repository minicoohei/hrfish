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
    """normalize (to disk) → validate → report_html with Rich progress."""
    from cc_layer.cli.cli_ui import show_report_progress, show_completion_banner

    if output:
        # Custom output path — override default
        result = show_report_progress(session_dir)
        if result["output_file"]:
            # Move to custom path
            src = Path(result["output_file"])
            dst = Path(output)
            if src.exists() and str(src) != str(dst):
                dst.write_text(src.read_text())
                result["output_file"] = str(dst)
    else:
        result = show_report_progress(session_dir)

    show_completion_banner(session_dir, result)


def run_status(session_dir: str):
    """Show pipeline progress and next action with Rich UI."""
    from cc_layer.cli.cli_ui import show_pipeline_status, show_next_action
    show_pipeline_status(session_dir)
    show_next_action(session_dir)


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
