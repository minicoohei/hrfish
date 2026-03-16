"""Rich-based CLI UI for MiroFish pipeline.

Provides colorful terminal output when Rich is installed.
Falls back to plain print() otherwise.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.columns import Columns
    from rich.style import Style
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console(stderr=True) if HAS_RICH else None

# Path colors
PATH_COLORS = {
    "path_a": "#fbbf24",
    "path_b": "#34d399",
    "path_c": "#f472b6",
    "path_d": "#fb923c",
    "path_e": "#a78bfa",
}


def _score_bar(score: float, width: int = 12) -> str:
    filled = int(score * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def show_pipeline_status(session_dir: str) -> None:
    """Show pipeline status with Rich table or plain text."""
    sdir = Path(session_dir)

    phases = [
        ("profile.json", "Profile"),
        ("form.json", "Form"),
        ("resume.txt", "Resume"),
        ("agent_state.json", "Phase 0: Init (sim_init)"),
        ("path_designs.json", "Phase 1a: Path Design (SubAgent)"),
        ("multipath_result.json", "Phase 1b-2: Expand + Score"),
        ("swarm_agents.json", "Phase 3: Swarm Agents"),
        ("fact_check_claims.json", "Phase 5: Fact Check Extract"),
        ("fact_check_result.json", "Phase 6: Fact Check Complete"),
        ("macro_trends.json", "Phase 7: Macro Trends (SubAgent)"),
    ]
    swarm_dir = sdir / "swarm"
    swarm_count = len(list(swarm_dir.glob("all_actions_round_*.jsonl"))) if swarm_dir.exists() else 0

    if not HAS_RICH:
        # Fallback to plain text
        print(f"\nMiroFish Pipeline Status: {session_dir}\n")
        for fname, desc in phases:
            mark = "OK" if (sdir / fname).exists() else "--"
            print(f"  [{mark}] {desc}: {fname}")
        print(f"  [{'OK' if swarm_count > 0 else '--'}] Phase 4: Swarm ({swarm_count} rounds)")
        print(f"  [{'OK' if (sdir / 'report.html').exists() else '--'}] Phase 8: HTML Report")
        return

    table = Table(
        title=f"MiroFish Pipeline",
        title_style="bold bright_blue",
        box=box.ROUNDED,
        border_style="bright_blue",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Phase", style="white", min_width=32)
    table.add_column("Status", justify="center", min_width=8)
    table.add_column("File", style="dim")

    for fname, desc in phases:
        exists = (sdir / fname).exists()
        status = Text("\u2713 OK", style="bold green") if exists else Text("--", style="dim red")
        table.add_row(desc, status, fname)

    # Swarm
    swarm_ok = swarm_count > 0
    table.add_row(
        f"Phase 4: Swarm",
        Text(f"\u2713 {swarm_count}R", style="bold green") if swarm_ok else Text("--", style="dim red"),
        f"swarm/ ({swarm_count} rounds)",
    )

    # Report
    report_ok = (sdir / "report.html").exists()
    table.add_row(
        "Phase 8: HTML Report",
        Text("\u2713 OK", style="bold green") if report_ok else Text("--", style="dim red"),
        "report.html",
    )

    console.print()
    console.print(table)
    console.print(f"  [dim]Session: {session_dir}[/dim]")


def show_report_progress(session_dir: str) -> dict:
    """Run normalize -> validate -> report with Rich progress spinner.

    Returns: {"output_file": str, "multipath_result": dict or None}
    """
    result = {"output_file": "", "multipath_result": None}

    if not HAS_RICH:
        # Fallback
        print("[1/3] Normalizing session data...")
        from cc_layer.schemas.normalize import normalize_session_to_disk
        norm_results = normalize_session_to_disk(session_dir)
        for fname, status in norm_results.items():
            print(f"  [{status}] {fname}")

        print("[2/3] Validating session data...")
        from cc_layer.schemas.validate import validate_session
        report = validate_session(session_dir)
        if report.has_errors:
            print("Validation FAILED:")
            print(report.format())
            sys.exit(1)

        print("[3/3] Generating HTML report...")
        from cc_layer.cli.report_html import build_html
        html = build_html(session_dir)
        out_path = str(Path(session_dir) / "report.html")
        Path(out_path).write_text(html)
        result["output_file"] = out_path
        print(f"Report generated: {out_path}")
        return result

    steps = [
        ("Normalizing SubAgent outputs...", "normalize"),
        ("Validating session data...", "validate"),
        ("Generating HTML report...", "report"),
    ]

    with Progress(
        SpinnerColumn("dots", style="bright_blue"),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30, style="bright_blue", complete_style="green"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("", total=len(steps))

        # Step 1: Normalize
        progress.update(task, description="[cyan]Normalizing SubAgent outputs...")
        from cc_layer.schemas.normalize import normalize_session_to_disk
        norm_results = normalize_session_to_disk(session_dir)
        progress.advance(task)

        # Step 2: Validate
        progress.update(task, description="[cyan]Validating session data...")
        from cc_layer.schemas.validate import validate_session
        report = validate_session(session_dir)
        if report.has_errors:
            progress.stop()
            console.print(Panel(
                report.format(),
                title="Validation FAILED",
                border_style="red",
            ))
            sys.exit(1)
        progress.advance(task)

        # Step 3: Generate report
        progress.update(task, description="[cyan]Generating HTML report...")
        from cc_layer.cli.report_html import build_html
        html = build_html(session_dir)
        out_path = str(Path(session_dir) / "report.html")
        Path(out_path).write_text(html)
        result["output_file"] = out_path
        progress.advance(task)

    # Load result data for banner
    mp_path = Path(session_dir) / "multipath_result.json"
    if mp_path.exists():
        result["multipath_result"] = json.loads(mp_path.read_text())

    return result


def show_completion_banner(session_dir: str, result: dict) -> None:
    """Show colorful completion banner with path ranking."""
    if not HAS_RICH:
        print(f"\nReport generated: {result.get('output_file', '')}")
        return

    mp = result.get("multipath_result")
    session_name = Path(session_dir).name

    # Build content
    lines = []

    if mp:
        paths = mp.get("paths", [])
        ranking = mp.get("ranking", [])
        total_scored = mp.get("total_scored", len(paths))

        # Stats row
        n_scenarios = sum(len(p.get("scenarios", [])) for p in paths)
        swarm_dir = Path(session_dir) / "swarm"
        swarm_count = 0
        if swarm_dir.exists():
            for jf in swarm_dir.glob("all_actions_round_*.jsonl"):
                swarm_count += sum(1 for line in jf.read_text().strip().split("\n") if line.strip())

        stats = Text()
        stats.append(f"  {len(paths)}", style="bold bright_yellow")
        stats.append(" Paths   ", style="dim")
        stats.append(f"{n_scenarios}", style="bold bright_green")
        stats.append(" Scenarios   ", style="dim")
        if swarm_count > 0:
            stats.append(f"{swarm_count}", style="bold bright_magenta")
            stats.append(" Swarm Actions", style="dim")
        lines.append(stats)
        lines.append(Text())

        # Ranking table
        rank_data = ranking if isinstance(ranking, list) else []
        if not rank_data and paths:
            rank_data = [
                {"rank": i + 1, "path_id": p.get("path_id", ""), "label": p.get("label", ""), "score": p.get("score", 0)}
                for i, p in enumerate(paths)
            ]

        for item in rank_data[:5]:
            pid = item.get("path_id", "")
            color = PATH_COLORS.get(pid, "white")
            score = item.get("score", 0)
            label = item.get("label", pid)
            if len(label) > 14:
                label = label[:12] + "..."

            line = Text()
            line.append(f"  #{item.get('rank', '?')}  ", style="bold white")
            line.append(f"{pid:<8}", style=Style(color=color, bold=True))
            line.append(f" {_score_bar(score)} ", style=Style(color=color))
            line.append(f" {score:.2f}  ", style="bold white")
            line.append(label, style="dim")
            lines.append(line)

    lines.append(Text())
    out = result.get("output_file", "")
    output_line = Text()
    output_line.append("  Output: ", style="dim")
    output_line.append(out, style="bold bright_green underline")
    lines.append(output_line)

    # Build panel
    content = Text("\n")
    for line in lines:
        if isinstance(line, Text):
            content.append_text(line)
        else:
            content.append(str(line))
        content.append("\n")

    panel = Panel(
        content,
        title="[bold bright_white]MiroFish Report Complete[/bold bright_white]",
        subtitle=f"[dim]{session_name}[/dim]",
        border_style="bright_blue",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    )
    console.print()
    console.print(panel)
    console.print()


def show_next_action(session_dir: str) -> None:
    """Show the next recommended action."""
    sdir = Path(session_dir)

    if not HAS_RICH:
        # Handled by pipeline_run.py fallback
        return

    if not (sdir / "profile.json").exists():
        msg = "Place profile.json, form.json, resume.txt in session directory"
    elif not (sdir / "agent_state.json").exists():
        msg = f"python -m cc_layer.cli.sim_init --profile @{session_dir}/profile.json --form @{session_dir}/form.json --output-dir {session_dir}"
    elif not (sdir / "path_designs.json").exists():
        msg = "Launch SubAgent PathDesignerAgent (cc_layer/prompts/path_designer_agent.md)"
    elif not (sdir / "multipath_result.json").exists():
        msg = "Launch SubAgent PathExpanderAgent x5 -> path_score"
    elif not list((sdir / "swarm").glob("all_actions_round_*.jsonl")) if (sdir / "swarm").exists() else True:
        msg = f"python -m cc_layer.cli.generate_swarm_agents --session-dir {session_dir}"
    elif not (sdir / "report.html").exists():
        msg = f"python -m cc_layer.cli.pipeline_run --session-dir {session_dir} --phase report"
    else:
        console.print(Panel(
            "[bold bright_green]Pipeline complete![/bold bright_green] report.html is ready.",
            border_style="green",
        ))
        return

    console.print()
    console.print(Panel(
        f"[bold]{msg}[/bold]",
        title="[bright_yellow]Next Step[/bright_yellow]",
        border_style="bright_yellow",
    ))
