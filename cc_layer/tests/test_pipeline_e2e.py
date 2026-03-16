"""End-to-end test: fixtures → normalize → validate → report_html."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures" / "session_demo"


@pytest.fixture
def session_copy(tmp_path):
    """Copy fixtures to tmp dir (don't pollute original data)."""
    if not FIXTURES.exists():
        pytest.skip("Demo fixtures not yet created")
    dest = tmp_path / "session"
    shutil.copytree(FIXTURES, dest)
    return dest


def test_e2e_report_generation(session_copy):
    """fixtures から report.html が生成できる"""
    result = subprocess.run(
        ["python", "-m", "cc_layer.cli.pipeline_run",
         "--session-dir", str(session_copy), "--phase", "report"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"STDERR: {result.stderr}"
    html_path = session_copy / "report.html"
    assert html_path.exists()
    html = html_path.read_text()
    # 主要セクションの存在確認
    assert "path_a" in html
    assert "&#165;" in html  # yen amounts exist


def test_e2e_normalize_idempotent(session_copy):
    """normalize を2回実行しても結果が同じ"""
    def run_normalize():
        return subprocess.run(
            ["python", "-m", "cc_layer.cli.pipeline_run",
             "--session-dir", str(session_copy), "--phase", "normalize"],
            capture_output=True, text=True,
        )

    run_normalize()
    mp1 = json.loads((session_copy / "multipath_result.json").read_text())
    run_normalize()
    mp2 = json.loads((session_copy / "multipath_result.json").read_text())
    assert mp1 == mp2


def test_e2e_status(session_copy):
    """status コマンドが正常動作する"""
    result = subprocess.run(
        ["python", "-m", "cc_layer.cli.pipeline_run",
         "--session-dir", str(session_copy), "--phase", "status"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "OK" in combined


def test_e2e_validate(session_copy):
    """validate コマンドが正常動作する"""
    result = subprocess.run(
        ["python", "-m", "cc_layer.cli.pipeline_run",
         "--session-dir", str(session_copy), "--phase", "validate"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "Validation OK" in result.stdout


def test_e2e_no_zero_yen(session_copy):
    """レポートに ¥0万 が含まれていない"""
    subprocess.run(
        ["python", "-m", "cc_layer.cli.pipeline_run",
         "--session-dir", str(session_copy), "--phase", "report"],
        capture_output=True, text=True,
    )
    html = (session_copy / "report.html").read_text()
    assert "&#165;0万" not in html
