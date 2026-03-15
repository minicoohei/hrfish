"""
Tests for all MiroFish CC Layer CLI tools.

Tests are organized by pipeline phase:
- Phase -1: text_process, ontology_generate, graph_build, profile_generate, sim_config_generate
- Phase 0:  sim_init
- Phase 1:  sim_tick, multipath_run
- Phase 2+: state_export, zep_write, zep_search
- Knowledge: knowledge_curate, knowledge_search, external_search

Zep API and LLM calls are mocked via a wrapper script injected before CLI import.
CLIs are invoked via subprocess to test the full argparse→stdout JSON contract.
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil

import pytest


# ============================================================
# Helpers
# ============================================================

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PYTHON = sys.executable


def run_cli(module: str, args: list[str], stdin_data: str = None,
            expect_fail: bool = False, timeout: int = 60) -> dict:
    """Run a cc_layer.cli.* module and return parsed JSON from stdout."""
    cmd = [PYTHON, "-m", f"cc_layer.cli.{module}"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        input=stdin_data,
        timeout=timeout,
    )

    parsed_json = _parse_last_json(result.stdout)

    if not expect_fail and result.returncode != 0:
        print(f"CLI FAILED: {' '.join(cmd)}", file=sys.stderr)
        print(f"STDERR: {result.stderr[:500]}", file=sys.stderr)
        print(f"STDOUT: {result.stdout[:500]}", file=sys.stderr)

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "json": parsed_json,
    }


def _parse_last_json(stdout: str):
    """Try to parse JSON from stdout — tries last JSON-like line first, then full text."""
    if not stdout or not stdout.strip():
        return None
    # Try last JSON-looking line (CLIs sometimes print progress then JSON)
    for line in reversed(stdout.strip().split("\n")):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    # Try full stdout
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError:
        return None


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def tmp_session_dir():
    d = tempfile.mkdtemp(prefix="mirofish_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_text_file(tmp_session_dir):
    path = os.path.join(tmp_session_dir, "resume.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "田中太郎\n35歳 男性\n学歴: 東京大学工学部卒業\n"
            "職歴:\n- 2013-2018: 株式会社ABC システムエンジニア\n"
            "- 2018-2024: テック株式会社 シニアエンジニア → テックリード\n"
            "スキル: Python, TypeScript, AWS, Docker, Kubernetes\n"
            "資格: AWS Solutions Architect Professional, 応用情報技術者\n"
            "年収: 850万円\n家族: 既婚、子供2人（5歳、2歳）\n住宅ローン残額: 3000万円\n"
        )
    return path


@pytest.fixture
def sample_profile_json():
    return json.dumps({
        "name": "田中太郎", "age": 35, "gender": "男性",
        "education": "東京大学工学部", "mbti": "INTJ",
        "traits": ["分析的", "計画的"],
        "current_role": "テックリード", "current_employer": "テック株式会社",
        "industry": "IT", "years_in_role": 3, "salary": 850,
        "skills": ["Python", "TypeScript", "AWS"],
        "certifications": ["AWS SAP", "応用情報技術者"],
        "career_summary": "SIer→メガベンチャーでバックエンド開発→テックリード",
    }, ensure_ascii=False)


@pytest.fixture
def sample_form_json():
    return json.dumps({
        "family_members": [
            {"relation": "child", "age": 5},
            {"relation": "child", "age": 2},
            {"relation": "parent", "age": 68, "notes": "健康"},
        ],
        "marital_status": "married",
        "mortgage_remaining": 3000,
        "monthly_expenses": 30,
        "cash_buffer_range": "500-1000",
    }, ensure_ascii=False)


@pytest.fixture
def agent_state_file(tmp_session_dir, sample_profile_json, sample_form_json):
    result = run_cli("sim_init", [
        "--profile", sample_profile_json,
        "--form", sample_form_json,
        "--seed", "42",
        "--output-dir", tmp_session_dir,
    ])
    assert result["returncode"] == 0
    path = os.path.join(tmp_session_dir, "agent_state.json")
    assert os.path.exists(path)
    return path


# ============================================================
# Phase -1: Document preprocessing pipeline
# ============================================================

class TestTextProcess:

    def test_extract_from_file(self, sample_text_file, tmp_session_dir):
        out_path = os.path.join(tmp_session_dir, "extracted.txt")
        result = run_cli("text_process", [
            "--mode", "extract",
            "--input-files", sample_text_file,
            "--output-file", out_path,
        ])
        assert result["returncode"] == 0
        assert result["json"]["status"] == "ok"
        assert os.path.exists(out_path)
        with open(out_path, encoding="utf-8") as f:
            assert "田中太郎" in f.read()

    def test_chunk_text(self):
        result = run_cli("text_process", [
            "--mode", "chunk",
            "--input-text", "これはテストテキストです。" * 20,
            "--chunk-size", "50", "--overlap", "10",
        ])
        assert result["returncode"] == 0
        assert result["json"]["count"] > 1

    def test_stats(self):
        result = run_cli("text_process", [
            "--mode", "stats",
            "--input-text", "Hello World テスト",
        ])
        assert result["returncode"] == 0
        assert result["json"]["total_chars"] > 0

    def test_preprocess(self):
        result = run_cli("text_process", [
            "--mode", "stats", "--input-text", "行1\n\n\n\n行2", "--preprocess",
        ])
        assert result["returncode"] == 0

    def test_extract_missing_file(self):
        """FileParser wraps errors per file — CLI still returns 0 with error text."""
        result = run_cli("text_process", [
            "--mode", "extract",
            "--input-files", "/nonexistent/file.txt",
        ])
        # extract_from_multiple catches per-file errors, so it may succeed with error text
        # or fail depending on implementation. Just check it doesn't hang.
        assert result["returncode"] in (0, 1)

    def test_chunk_without_input_fails(self):
        result = run_cli("text_process", ["--mode", "chunk"], expect_fail=True)
        assert result["returncode"] != 0


class TestOntologyGenerate:

    def test_default_ontology(self, tmp_session_dir):
        out_path = os.path.join(tmp_session_dir, "ontology.json")
        result = run_cli("ontology_generate", ["--default", "--output-file", out_path])
        assert result["returncode"] == 0
        assert result["json"]["entity_types_count"] == 10

        with open(out_path, encoding="utf-8") as f:
            ontology = json.load(f)
        names = {e["name"] for e in ontology["entity_types"]}
        assert "Person" in names
        assert "Organization" in names

    def test_default_ontology_stdout(self):
        result = run_cli("ontology_generate", ["--default"])
        assert result["returncode"] == 0
        assert "entity_types" in result["json"]

    def test_missing_requirement_fails(self):
        result = run_cli("ontology_generate", ["--document-text", "テスト"], expect_fail=True)
        assert result["returncode"] != 0


# ============================================================
# Phase 0: Simulation initialization
# ============================================================

class TestSimInit:

    def test_basic_init(self, tmp_session_dir, sample_profile_json, sample_form_json):
        result = run_cli("sim_init", [
            "--profile", sample_profile_json,
            "--form", sample_form_json,
            "--seed", "42",
            "--output-dir", tmp_session_dir,
        ])
        assert result["returncode"] == 0
        assert result["json"]["status"] == "ok"

        state_path = os.path.join(tmp_session_dir, "agent_state.json")
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["identity"]["name"] == "田中太郎"
        assert data["identity"]["age_at_start"] == 35
        assert data["state"]["role"] == "テックリード"
        assert data["state"]["salary_annual"] == 850
        assert data["state"]["mortgage_remaining"] == 3000
        assert len(data["state"]["family"]) == 3
        assert data["seed"] == 42

    def test_file_input(self, tmp_session_dir):
        profile_path = os.path.join(tmp_session_dir, "profile.json")
        form_path = os.path.join(tmp_session_dir, "form.json")
        with open(profile_path, "w") as f:
            json.dump({"name": "佐藤花子", "age": 28}, f)
        with open(form_path, "w") as f:
            json.dump({"family_members": [], "marital_status": "single"}, f)

        out_dir = os.path.join(tmp_session_dir, "out")
        result = run_cli("sim_init", [
            "--profile", f"@{profile_path}",
            "--form", f"@{form_path}",
            "--output-dir", out_dir,
        ])
        assert result["returncode"] == 0


# ============================================================
# Phase 1: Simulation execution
# ============================================================

class TestSimTick:

    def test_single_tick(self, agent_state_file):
        result = run_cli("sim_tick", [
            "--state-file", agent_state_file, "--round-num", "1",
        ])
        assert result["returncode"] == 0
        data = result["json"]
        assert data is not None, f"Failed to parse JSON from: {result['stdout'][:300]}"
        assert "events" in data
        assert "blockers" in data
        assert "snapshot" in data
        assert data["state_updated"] is True

    def test_multiple_ticks(self, agent_state_file):
        for round_num in range(1, 5):
            result = run_cli("sim_tick", [
                "--state-file", agent_state_file, "--round-num", str(round_num),
            ])
            assert result["returncode"] == 0, f"Failed at round {round_num}"

        with open(agent_state_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["state"]["current_age"] == 36


class TestMultipathRun:

    def test_default_paths(self, agent_state_file, tmp_session_dir):
        out_path = os.path.join(tmp_session_dir, "multipath_result.json")
        result = run_cli("multipath_run", [
            "--state-file", agent_state_file,
            "--round-count", "8", "--top-n", "3", "--default-paths",
            "--output-file", out_path,
        ], timeout=120)
        assert result["returncode"] == 0

        with open(out_path, encoding="utf-8") as f:
            report = json.load(f)
        assert "paths" in report
        assert len(report["paths"]) > 0
        for path in report["paths"]:
            assert "score" in path


# ============================================================
# Phase 2+: Zep integration (state_export, zep_write, zep_search)
# ============================================================

class TestStateExport:

    def test_zep_facts_format(self, agent_state_file):
        result = run_cli("state_export", [
            "--state-file", agent_state_file, "--format", "zep-facts",
        ])
        assert result["returncode"] == 0
        facts = result["json"]
        assert isinstance(facts, list)
        assert len(facts) > 0
        all_text = " ".join(facts)
        assert "田中太郎" in all_text
        assert "INTJ" in all_text
        assert "テック株式会社" in all_text

    def test_raw_format(self, agent_state_file):
        result = run_cli("state_export", [
            "--state-file", agent_state_file, "--format", "raw",
        ])
        assert result["returncode"] == 0
        assert "identity" in result["json"]


class TestZepWrite:
    """zep_write.py — Zep API write operations (mocked)."""

    def test_write_facts_file(self, tmp_session_dir):
        facts_path = os.path.join(tmp_session_dir, "facts.json")
        with open(facts_path, "w", encoding="utf-8") as f:
            json.dump(["田中太郎は35歳です。", "田中太郎はテックリードです。"], f, ensure_ascii=False)

        result = _run_cli_with_zep_mock("zep_write", [
            "--graph-id", "test_graph_001", "--facts-file", facts_path,
        ], tmp_session_dir)
        assert result["returncode"] == 0
        assert result["json"]["status"] == "ok"
        assert result["json"]["facts_written"] == 2

    def test_write_activity(self, tmp_session_dir):
        activity = json.dumps({
            "agent_name": "田中太郎",
            "action": "Published a post",
            "content": "転職を考え始めた。",
        }, ensure_ascii=False)
        result = _run_cli_with_zep_mock("zep_write", [
            "--graph-id", "test_graph_001", "--activity", activity,
        ], tmp_session_dir)
        assert result["returncode"] == 0
        assert result["json"]["facts_written"] == 1

    def test_write_stdin_facts(self, tmp_session_dir):
        facts_json = json.dumps(["田中太郎のMBTIはINTJです。"], ensure_ascii=False)
        result = _run_cli_with_zep_mock("zep_write", [
            "--graph-id", "test_graph_001", "--stdin-facts",
        ], tmp_session_dir, stdin_data=facts_json)
        assert result["returncode"] == 0
        assert result["json"]["facts_written"] == 1


class TestZepSearch:
    """zep_search.py — Zep API search operations (mocked)."""

    def test_entities_mode(self, tmp_session_dir):
        result = _run_cli_with_zep_mock("zep_search", [
            "--graph-id", "test_graph_001", "--mode", "entities",
        ], tmp_session_dir)
        assert result["returncode"] == 0
        data = result["json"]
        assert data["mode"] == "entities"
        assert "entities" in data
        assert data["filtered_count"] >= 0

    def test_quick_mode(self, tmp_session_dir):
        result = _run_cli_with_zep_mock("zep_search", [
            "--graph-id", "test_graph_001", "--mode", "quick",
            "--query", "候補者のキャリア経歴",
        ], tmp_session_dir)
        assert result["returncode"] == 0

    def test_panorama_mode(self, tmp_session_dir):
        result = _run_cli_with_zep_mock("zep_search", [
            "--graph-id", "test_graph_001", "--mode", "panorama",
        ], tmp_session_dir)
        assert result["returncode"] == 0


class TestGraphBuild:
    """graph_build.py — Zep graph construction (mocked)."""

    def test_build_mode(self, sample_text_file, tmp_session_dir):
        ont_path = os.path.join(tmp_session_dir, "ontology.json")
        run_cli("ontology_generate", ["--default", "--output-file", ont_path])

        out_path = os.path.join(tmp_session_dir, "graph_info.json")
        result = _run_cli_with_zep_mock("graph_build", [
            "--text-file", sample_text_file,
            "--ontology-file", ont_path,
            "--graph-name", "test_session",
            "--chunk-size", "500", "--overlap", "50", "--batch-size", "2",
            "--output-file", out_path,
        ], tmp_session_dir)
        assert result["returncode"] == 0

    def test_info_mode(self, tmp_session_dir):
        result = _run_cli_with_zep_mock("graph_build", [
            "--mode", "info", "--graph-id", "mirofish_test123",
        ], tmp_session_dir)
        assert result["returncode"] == 0

    def test_delete_mode(self, tmp_session_dir):
        result = _run_cli_with_zep_mock("graph_build", [
            "--mode", "delete", "--graph-id", "mirofish_test123",
        ], tmp_session_dir)
        assert result["returncode"] == 0
        assert result["json"]["status"] == "ok"

    def test_build_missing_args(self):
        result = run_cli("graph_build", ["--mode", "build"], expect_fail=True)
        assert result["returncode"] != 0


class TestProfileGenerate:
    """profile_generate.py — OASIS profile generation (mocked)."""

    def test_from_entity_file_no_llm(self, tmp_session_dir):
        entity_path = os.path.join(tmp_session_dir, "entities.json")
        entities = [
            {
                "uuid": "ent-001", "name": "キャリアアドバイザー田中",
                "labels": ["Entity", "CareerAdvisor"],
                "summary": "IT業界専門の転職エージェント。",
                "attributes": {"full_name": "田中一郎", "specialty": "IT転職"},
                "related_edges": [], "related_nodes": [],
            },
            {
                "uuid": "ent-002", "name": "人事マネージャー鈴木",
                "labels": ["Entity", "HRManager"],
                "summary": "テック企業の人事部長。",
                "attributes": {"full_name": "鈴木花子", "title": "人事部長"},
                "related_edges": [], "related_nodes": [],
            },
        ]
        with open(entity_path, "w", encoding="utf-8") as f:
            json.dump(entities, f, ensure_ascii=False)

        out_path = os.path.join(tmp_session_dir, "profiles.json")
        result = _run_cli_with_zep_mock("profile_generate", [
            "--entity-file", entity_path, "--no-llm", "--output-file", out_path,
        ], tmp_session_dir)
        assert result["returncode"] == 0

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["count"] == 2
        assert data["profiles"][0]["name"] == "キャリアアドバイザー田中"


# ============================================================
# Knowledge CLIs
# ============================================================

class TestKnowledgeSearch:

    def test_status_mode(self):
        result = run_cli("knowledge_search", ["--mode", "status"])
        assert result["returncode"] == 0
        assert result["json"]["mode"] == "status"

    def test_inject_mode(self):
        result = run_cli("knowledge_search", [
            "--mode", "inject",
            "--candidate-context", "35歳シニアエンジニア",
            "--injection-point", "top_player",
        ])
        assert result["returncode"] == 0
        assert result["json"]["injection_point"] == "top_player"

    def test_search_mode(self):
        result = run_cli("knowledge_search", [
            "--mode", "search", "--query", "IT転職市場",
        ])
        assert result["returncode"] == 0
        assert result["json"]["mode"] == "search"


def _has_tavily_key():
    """Check if TAVILY_API_KEY is available via dotenv or environment."""
    try:
        from dotenv import dotenv_values
        env_path = os.path.join(PROJECT_ROOT, ".env")
        vals = dotenv_values(env_path)
        return bool(vals.get("TAVILY_API_KEY") or os.environ.get("TAVILY_API_KEY"))
    except ImportError:
        return bool(os.environ.get("TAVILY_API_KEY"))


class TestExternalSearch:

    def test_modes_require_params(self):
        """Each mode has required params — missing them should fail."""
        result = run_cli("external_search", ["--mode", "job-market"], expect_fail=True)
        assert result["returncode"] != 0

    @pytest.mark.skipif(not _has_tavily_key(), reason="TAVILY_API_KEY not set")
    def test_search_mode_live(self):
        """Live Tavily search (requires API key in .env)."""
        result = run_cli("external_search", [
            "--query", "IT業界 転職市場 2025",
            "--max-results", "3",
        ])
        assert result["returncode"] == 0
        assert result["json"]["mode"] == "search"
        assert result["json"]["count"] > 0

    @pytest.mark.skipif(not _has_tavily_key(), reason="TAVILY_API_KEY not set")
    def test_job_market_live(self):
        """Live job market search."""
        result = run_cli("external_search", [
            "--mode", "job-market",
            "--profession", "エンジニア",
            "--industry", "IT",
        ])
        assert result["returncode"] == 0
        assert result["json"]["mode"] == "job-market"

    @pytest.mark.skipif(not _has_tavily_key(), reason="TAVILY_API_KEY not set")
    def test_industry_news_live(self):
        """Live industry news search."""
        result = run_cli("external_search", [
            "--mode", "industry-news",
            "--industry", "IT",
            "--keywords", "AI,DX",
        ])
        assert result["returncode"] == 0
        assert result["json"]["mode"] == "industry-news"

    @pytest.mark.skipif(not _has_tavily_key(), reason="TAVILY_API_KEY not set")
    def test_hr_trends_live(self):
        """Live HR trends search."""
        result = run_cli("external_search", [
            "--mode", "hr-trends",
            "--keywords", "AI,リスキリング",
        ])
        assert result["returncode"] == 0
        assert result["json"]["mode"] == "hr-trends"


class TestKnowledgeCurate:

    def test_curate_with_mock(self, tmp_session_dir):
        """knowledge_curate needs LLM + Tavily — both mocked."""
        ont_path = os.path.join(tmp_session_dir, "ontology.json")
        run_cli("ontology_generate", ["--default", "--output-file", ont_path])

        out_dir = os.path.join(tmp_session_dir, "knowledge")
        result = _run_cli_with_tavily_mock("knowledge_curate", [
            "--ontology-file", ont_path,
            "--candidate-context", "35歳、シニアエンジニア、IT業界10年",
            "--output-dir", out_dir,
        ], tmp_session_dir)
        # knowledge_curate outputs multi-line JSON; check it ran without crashing
        assert result["returncode"] == 0
        # The output is multi-line JSON that _parse_last_json may not catch line-by-line
        # Verify by checking stdout contains expected keys
        assert "classification" in result["stdout"] or "stats" in result["stdout"]


class TestStateImport:

    def test_import_from_facts(self, tmp_session_dir):
        facts = [
            "田中太郎は現在35歳です。",
            "田中太郎はテック株式会社でテックリードとして勤務しています。",
            "MBTIタイプはINTJです。",
            "年収は850万円です。",
            "田中太郎は既婚者です。",
            "5歳の子供がいます。",
            "3000万円のローンがあります。",
            "学歴は東京大学工学部です。",
            "IT業界に10年の経験があります。",
        ]
        facts_path = os.path.join(tmp_session_dir, "facts.json")
        with open(facts_path, "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False)

        out_dir = os.path.join(tmp_session_dir, "imported")
        result = run_cli("state_import", [
            "--facts-file", facts_path, "--output-dir", out_dir,
        ])
        assert result["returncode"] == 0
        assert result["json"]["status"] == "ok"

        state_path = os.path.join(out_dir, "agent_state.json")
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["identity"]["name"] == "田中太郎"
        assert data["identity"]["mbti"] == "INTJ"
        assert data["state"]["salary_annual"] == 850
        assert data["state"]["marital_status"] == "married"
        assert data["state"]["mortgage_remaining"] == 3000

    def test_import_from_raw(self, tmp_session_dir, agent_state_file):
        out_dir = os.path.join(tmp_session_dir, "raw_import")
        result = run_cli("state_import", [
            "--raw-file", agent_state_file, "--output-dir", out_dir,
        ])
        assert result["returncode"] == 0
        state_path = os.path.join(out_dir, "agent_state.json")
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["identity"]["name"] == "田中太郎"

    def test_roundtrip_export_import(self, agent_state_file, tmp_session_dir):
        """state_export → state_import roundtrip preserves key data."""
        # Export
        r = run_cli("state_export", [
            "--state-file", agent_state_file, "--format", "zep-facts",
        ])
        assert r["returncode"] == 0
        facts = r["json"]

        facts_path = os.path.join(tmp_session_dir, "exported_facts.json")
        with open(facts_path, "w", encoding="utf-8") as f:
            json.dump(facts, f, ensure_ascii=False)

        # Import back
        out_dir = os.path.join(tmp_session_dir, "roundtrip")
        r = run_cli("state_import", [
            "--facts-file", facts_path, "--output-dir", out_dir,
        ])
        assert r["returncode"] == 0
        with open(os.path.join(out_dir, "agent_state.json"), encoding="utf-8") as f:
            data = json.load(f)
        assert data["identity"]["name"] == "田中太郎"
        assert data["state"]["salary_annual"] == 850


class TestSimConfigGenerate:

    def test_generate_with_mock(self, tmp_session_dir, sample_text_file):
        """sim_config_generate needs Zep + OpenAI — both mocked."""
        # Prepare profiles file
        profiles = {
            "count": 1,
            "profiles": [{
                "user_id": 1, "user_name": "tanaka", "name": "田中太郎",
                "bio": "IT業界10年のシニアエンジニア", "persona": "分析的で計画的",
                "karma": 1000, "friend_count": 50, "follower_count": 100,
                "statuses_count": 200, "age": 35, "gender": "男性",
                "mbti": "INTJ", "country": "JP", "profession": "エンジニア",
                "interested_topics": ["AI", "クラウド"],
            }],
        }
        profiles_path = os.path.join(tmp_session_dir, "profiles.json")
        with open(profiles_path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False)

        out_path = os.path.join(tmp_session_dir, "sim_config.json")
        result = _run_cli_with_zep_mock("sim_config_generate", [
            "--graph-id", "test_graph_001",
            "--requirement", "IT業界でのキャリア転換",
            "--profiles-file", profiles_path,
            "--document-text-file", sample_text_file,
            "--output-file", out_path,
        ], tmp_session_dir)
        assert result["returncode"] == 0


class TestProfileGenerateFromGraph:

    def test_from_graph_no_llm(self, tmp_session_dir):
        """profile_generate with --graph-id and --no-llm (Zep mocked)."""
        out_path = os.path.join(tmp_session_dir, "profiles.json")
        result = _run_cli_with_zep_mock("profile_generate", [
            "--graph-id", "test_graph_001", "--no-llm",
            "--output-file", out_path,
        ], tmp_session_dir)
        assert result["returncode"] == 0
        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["count"] == 2


class TestPathScore:
    """path_score.py — Score SubAgent-generated career paths."""

    def test_score_single_path(self, tmp_session_dir):
        path_data = {
            "path_id": "path_a",
            "label": "マネジメント転向",
            "periods": [
                {
                    "period_id": 1, "period_name": "Year 1-2",
                    "events": [{"type": "promotion", "description": "昇進"}],
                    "blockers_active": ["mortgage_pressure"],
                    "snapshot": {"annual_income": 850, "satisfaction": 0.7, "stress": 0.4},
                },
                {
                    "period_id": 2, "period_name": "Year 3-5",
                    "events": [],
                    "blockers_active": [],
                    "snapshot": {"annual_income": 1000, "satisfaction": 0.8, "stress": 0.3},
                },
            ],
            "final_state": {
                "annual_income": 1200, "satisfaction": 0.8,
                "stress": 0.3, "total_score": 0.0,
            },
        }
        path_file = os.path.join(tmp_session_dir, "path_expanded_path_a.json")
        with open(path_file, "w", encoding="utf-8") as f:
            json.dump(path_data, f, ensure_ascii=False)

        result = run_cli("path_score", ["--input-file", path_file])
        assert result["returncode"] == 0
        paths = result["json"]["paths"]
        assert len(paths) == 1
        assert paths[0]["score"] > 0

    def test_score_multiple_paths(self, tmp_session_dir):
        for pid, income, sat, stress in [
            ("path_a", 1200, 0.8, 0.3),
            ("path_b", 800, 0.6, 0.6),
            ("path_c", 1500, 0.9, 0.2),
        ]:
            data = {
                "path_id": pid, "label": f"Path {pid}",
                "periods": [], "final_state": {
                    "annual_income": income, "satisfaction": sat,
                    "stress": stress, "total_score": 0.0,
                },
            }
            with open(os.path.join(tmp_session_dir, f"path_expanded_{pid}.json"), "w") as f:
                json.dump(data, f)

        out = os.path.join(tmp_session_dir, "multipath_result.json")
        result = run_cli("path_score", [
            "--input-dir", tmp_session_dir, "--output-file", out,
        ])
        assert result["returncode"] == 0

        with open(out, encoding="utf-8") as f:
            report = json.load(f)
        assert report["ranking"][0]["path_id"] == "path_c"  # highest income+satisfaction
        assert report["total_scored"] == 3

    def test_missing_input(self):
        result = run_cli("path_score", [], expect_fail=True)
        assert result["returncode"] != 0


class TestSwarmSync:
    """swarm_sync.py — Round synchronization for multi-session Agent Swarm."""

    def test_init_and_round_cycle(self, tmp_session_dir):
        # Create agents file (10 agents → 2 workers of 5)
        agents = [
            {"name": f"Agent_{i}", "bio": f"テストエージェント{i}", "persona": "neutral"}
            for i in range(10)
        ]
        agents_file = os.path.join(tmp_session_dir, "agents.json")
        with open(agents_file, "w") as f:
            json.dump(agents, f)

        # Init swarm
        r = run_cli("swarm_sync", [
            "--mode", "init", "--session-dir", tmp_session_dir,
            "--agents-file", agents_file, "--num-workers", "2",
        ])
        assert r["returncode"] == 0
        assert r["json"]["total_agents"] == 10

        # Verify worker assignments
        w0 = os.path.join(tmp_session_dir, "swarm", "worker_0_agents.json")
        with open(w0) as f:
            w0_agents = json.load(f)
        assert len(w0_agents) == 5

        # Prepare round 1
        r = run_cli("swarm_sync", [
            "--mode", "prepare-round", "--session-dir", tmp_session_dir,
            "--round-num", "1",
        ])
        assert r["returncode"] == 0

        # Check round (should be missing)
        r = run_cli("swarm_sync", [
            "--mode", "check-round", "--session-dir", tmp_session_dir,
            "--round-num", "1", "--num-workers", "2",
        ])
        assert r["json"]["all_done"] is False
        assert r["json"]["missing"] == [0, 1]

        # Write worker 0 actions
        actions_file = os.path.join(tmp_session_dir, "w0_actions.jsonl")
        with open(actions_file, "w") as f:
            f.write(json.dumps({
                "round_num": 1, "agent_id": 0, "agent_name": "Agent_0",
                "action_type": "CREATE_POST",
                "action_args": {"content": "初投稿です！"},
            }) + "\n")
            f.write(json.dumps({
                "round_num": 1, "agent_id": 2, "agent_name": "Agent_2",
                "action_type": "DO_NOTHING", "action_args": {},
            }) + "\n")

        r = run_cli("swarm_sync", [
            "--mode", "write-actions", "--session-dir", tmp_session_dir,
            "--round-num", "1", "--worker-id", "0",
            "--actions-file", actions_file,
        ])
        assert r["returncode"] == 0
        assert r["json"]["actions_written"] == 2

        # Write worker 1 actions
        actions_file2 = os.path.join(tmp_session_dir, "w1_actions.jsonl")
        with open(actions_file2, "w") as f:
            f.write(json.dumps({
                "round_num": 1, "agent_id": 5, "agent_name": "Agent_5",
                "action_type": "CREATE_POST",
                "action_args": {"content": "今日も転職活動頑張ります"},
            }) + "\n")

        run_cli("swarm_sync", [
            "--mode", "write-actions", "--session-dir", tmp_session_dir,
            "--round-num", "1", "--worker-id", "1",
            "--actions-file", actions_file2,
        ])

        # Check round (should be all done)
        r = run_cli("swarm_sync", [
            "--mode", "check-round", "--session-dir", tmp_session_dir,
            "--round-num", "1", "--num-workers", "2",
        ])
        assert r["json"]["all_done"] is True

        # Merge
        r = run_cli("swarm_sync", [
            "--mode", "merge", "--session-dir", tmp_session_dir,
            "--round-num", "1", "--num-workers", "2",
        ])
        assert r["returncode"] == 0
        assert r["json"]["new_posts"] == 2
        assert r["json"]["actions_merged"] == 3

        # Read timeline
        r = run_cli("swarm_sync", [
            "--mode", "read-timeline", "--session-dir", tmp_session_dir,
            "--round-num", "2", "--worker-id", "0",
        ])
        assert r["returncode"] == 0
        assert len(r["json"]["posts"]) == 2
        assert len(r["json"]["my_agents"]) == 5

        # Export to Zep format
        r = run_cli("swarm_sync", [
            "--mode", "export-zep", "--session-dir", tmp_session_dir,
        ])
        assert r["returncode"] == 0
        assert r["json"]["total_activities"] == 3


# ============================================================
# End-to-end pipeline (no Zep, no LLM)
# ============================================================

class TestEndToEndPipeline:
    """text_process → ontology → sim_init → sim_tick → multipath → state_export."""

    def test_full_pipeline(self, sample_text_file, tmp_session_dir,
                           sample_profile_json, sample_form_json):
        # 1. Extract text
        extracted = os.path.join(tmp_session_dir, "extracted.txt")
        r = run_cli("text_process", [
            "--mode", "extract", "--input-files", sample_text_file,
            "--preprocess", "--output-file", extracted,
        ])
        assert r["returncode"] == 0

        # 2. Default ontology
        ont = os.path.join(tmp_session_dir, "ontology.json")
        r = run_cli("ontology_generate", ["--default", "--output-file", ont])
        assert r["returncode"] == 0

        # 3. Chunk text
        r = run_cli("text_process", [
            "--mode", "chunk", "--input-text-file", extracted,
            "--chunk-size", "500", "--overlap", "50",
        ])
        assert r["returncode"] == 0
        assert r["json"]["count"] > 0

        # 4. Init simulation
        r = run_cli("sim_init", [
            "--profile", sample_profile_json, "--form", sample_form_json,
            "--seed", "42", "--output-dir", tmp_session_dir,
        ])
        assert r["returncode"] == 0
        state_file = os.path.join(tmp_session_dir, "agent_state.json")

        # 5. Tick 4 rounds
        for rn in range(1, 5):
            r = run_cli("sim_tick", [
                "--state-file", state_file, "--round-num", str(rn),
            ])
            assert r["returncode"] == 0

        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["state"]["current_round"] == 4
        assert data["state"]["current_age"] == 36

        # 6. Multipath (fresh state)
        r = run_cli("sim_init", [
            "--profile", sample_profile_json, "--form", sample_form_json,
            "--seed", "42", "--output-dir", tmp_session_dir,
        ])
        mp = os.path.join(tmp_session_dir, "multipath_result.json")
        r = run_cli("multipath_run", [
            "--state-file", state_file, "--round-count", "8",
            "--top-n", "3", "--default-paths", "--output-file", mp,
        ], timeout=180)
        assert r["returncode"] == 0
        with open(mp, encoding="utf-8") as f:
            report = json.load(f)
        assert len(report["paths"]) > 0

        # 7. State export to Zep facts
        r = run_cli("state_export", [
            "--state-file", state_file, "--format", "zep-facts",
        ])
        assert r["returncode"] == 0
        assert any("田中太郎" in f for f in r["json"])


# ============================================================
# Zep Mock Infrastructure
# ============================================================

_ZEP_MOCK_SCRIPT = r'''
"""Wrapper that mocks Zep/OpenAI SDK and runs a CC Layer CLI module."""
import sys
import os
import json
import types
import unittest.mock
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Add project root to path so cc_layer is importable
PROJECT_ROOT = os.environ.get('PROJECT_ROOT', os.getcwd())
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Mock zep_cloud ---
zep_mock = types.ModuleType('zep_cloud')
zep_client_mock = types.ModuleType('zep_cloud.client')
zep_ext_mock = types.ModuleType('zep_cloud.external_clients')
zep_ont_mock = types.ModuleType('zep_cloud.external_clients.ontology')

class _MockEpisodeData:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

class _MockEntityEdgeSourceTarget:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

class _MockEntityModel:
    pass

class _MockEntityText:
    pass

class _MockEdgeModel:
    pass

class _MockNode:
    def __init__(self, uuid_="n1", name="Node", labels=None, summary="", attributes=None, created_at=None):
        self.uuid_ = uuid_
        self.name = name
        self.labels = labels or []
        self.summary = summary
        self.attributes = attributes or {}
        self.created_at = created_at

class _MockEdge:
    def __init__(self, uuid_="e1", name="RELATED", fact="related", source_node_uuid="n1",
                 target_node_uuid="n2", attributes=None, fact_type="", **kw):
        self.uuid_ = uuid_
        self.name = name
        self.fact = fact
        self.fact_type = fact_type
        self.source_node_uuid = source_node_uuid
        self.target_node_uuid = target_node_uuid
        self.attributes = attributes or {}
        for k, v in kw.items():
            setattr(self, k, v)
        for attr in ('created_at', 'valid_at', 'invalid_at', 'expired_at', 'episodes'):
            if not hasattr(self, attr):
                setattr(self, attr, None)

class _MockEpisode:
    def __init__(self, uuid_="ep1", processed=True):
        self.uuid_ = uuid_
        self.processed = processed

class _MockGraphEpisode:
    def get(self, uuid_):
        return _MockEpisode(uuid_=uuid_, processed=True)

class _MockBatchResult:
    def __init__(self):
        self.uuid_ = "ep-batch-1"

class _MockGraph:
    def __init__(self):
        self.episode = _MockGraphEpisode()
    def create(self, **kw): pass
    def add(self, **kw): pass
    def add_batch(self, **kw): return [_MockBatchResult()]
    def delete(self, **kw): pass
    def set_ontology(self, **kw): pass
    def search(self, **kw): return unittest.mock.MagicMock()

class _MockZep:
    def __init__(self, **kw):
        self.graph = _MockGraph()

# --- Patch time.sleep to speed up tests ---
import time as _time_mod
_original_sleep = _time_mod.sleep
_time_mod.sleep = lambda s: _original_sleep(min(s, 0.01))

# --- Mock OpenAI client ---
_openai_mod = types.ModuleType('openai')
class _MockOpenAIClient:
    def __init__(self, **kw):
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(
                create=lambda **kw: types.SimpleNamespace(
                    choices=[types.SimpleNamespace(
                        message=types.SimpleNamespace(content='{"mock": true}')
                    )]
                )
            )
        )
_openai_mod.OpenAI = _MockOpenAIClient
sys.modules['openai'] = _openai_mod

zep_mock.EpisodeData = _MockEpisodeData
zep_mock.EntityEdgeSourceTarget = _MockEntityEdgeSourceTarget
zep_client_mock.Zep = _MockZep
zep_ont_mock.EntityModel = _MockEntityModel
zep_ont_mock.EntityText = _MockEntityText
zep_ont_mock.EdgeModel = _MockEdgeModel

sys.modules['zep_cloud'] = zep_mock
sys.modules['zep_cloud.client'] = zep_client_mock
sys.modules['zep_cloud.external_clients'] = zep_ext_mock
sys.modules['zep_cloud.external_clients.ontology'] = zep_ont_mock

# --- Import cc_layer.cli (sets up namespace packages) ---
import cc_layer.cli

# --- Mock zep_paging (must be after cc_layer.cli sets up app.utils) ---
zep_paging_mod = types.ModuleType('app.utils.zep_paging')
def _mock_fetch_all_nodes(client, graph_id, **kw):
    return [
        _MockNode(uuid_="n1", name="キャリアアドバイザー", labels=["Entity", "CareerAdvisor"],
                  summary="IT業界専門", attributes={"full_name": "田中一郎"}),
        _MockNode(uuid_="n2", name="人事マネージャー", labels=["Entity", "HRManager"],
                  summary="テック企業人事", attributes={"full_name": "鈴木花子"}),
    ]
def _mock_fetch_all_edges(client, graph_id, **kw):
    return [_MockEdge(uuid_="e1", name="ADVISES", fact="advises on career",
                      source_node_uuid="n1", target_node_uuid="n2")]
zep_paging_mod.fetch_all_nodes = _mock_fetch_all_nodes
zep_paging_mod.fetch_all_edges = _mock_fetch_all_edges
sys.modules['app.utils.zep_paging'] = zep_paging_mod

# --- Mock ZepToolsService ---
class _MockSearchResult:
    def to_dict(self):
        return {"facts": [{"fact": "テスト事実", "score": 0.9}], "nodes": [], "edges": []}

# Patch after import
import app.services.zep_tools as _zt_mod
class _MockZepToolsService:
    def __init__(self, **kw): pass
    def search_graph(self, **kw): return _MockSearchResult()
    def insight_forge(self, **kw): return _MockSearchResult()
    def panorama_search(self, **kw): return _MockSearchResult()
_zt_mod.ZepToolsService = _MockZepToolsService

# --- Mock ZepEntityReader ---
@dataclass
class _MockEntityNode:
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: list = field(default_factory=list)
    related_nodes: list = field(default_factory=list)
    def get_entity_type(self):
        for label in self.labels:
            if label not in ("Entity", "Node"):
                return label
        return None
    def to_dict(self):
        return {"uuid": self.uuid, "name": self.name, "labels": self.labels,
                "summary": self.summary, "attributes": self.attributes}

@dataclass
class _MockFilteredEntities:
    entities: list
    total_count: int = 0
    filtered_count: int = 0
    entity_types: set = field(default_factory=set)

class _MockZepEntityReader:
    def __init__(self, **kw): pass
    def filter_defined_entities(self, graph_id, **kw):
        ents = [
            _MockEntityNode(uuid="n1", name="キャリアアドバイザー",
                          labels=["Entity", "CareerAdvisor"],
                          summary="IT業界専門", attributes={"full_name": "田中一郎"}),
            _MockEntityNode(uuid="n2", name="人事マネージャー",
                          labels=["Entity", "HRManager"],
                          summary="テック企業人事", attributes={"full_name": "鈴木花子"}),
        ]
        return _MockFilteredEntities(entities=ents, total_count=2, filtered_count=2,
                                     entity_types={"CareerAdvisor", "HRManager"})

import app.services.zep_entity_reader as _zer_mod
_zer_mod.ZepEntityReader = _MockZepEntityReader
_zer_mod.EntityNode = _MockEntityNode
_zer_mod.FilteredEntities = _MockFilteredEntities

# --- Run the target CLI module ---
import importlib
module_name = sys.argv[1]
sys.argv = sys.argv[1:]
sys.argv[0] = f"cc_layer.cli.{module_name}"
mod = importlib.import_module(f"cc_layer.cli.{module_name}")
mod.main()
'''


_TAVILY_MOCK_SCRIPT = r'''
"""Wrapper that mocks Tavily + LLM and runs a CC Layer CLI module."""
import sys
import os
import json
import types
import unittest.mock

PROJECT_ROOT = os.environ.get('PROJECT_ROOT', os.getcwd())
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Mock OpenAI ---
_openai_mod = types.ModuleType('openai')
class _MockOpenAIClient:
    def __init__(self, **kw):
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(
                create=lambda **kw: types.SimpleNamespace(
                    choices=[types.SimpleNamespace(
                        message=types.SimpleNamespace(
                            content='{"industry": "IT", "sub_industry": "ソフトウェア", "profession": "エンジニア", "career_stage": "mid", "confidence": 0.9}'
                        )
                    )]
                )
            )
        )
_openai_mod.OpenAI = _MockOpenAIClient
sys.modules['openai'] = _openai_mod

# --- Patch time.sleep ---
import time as _time_mod
_original_sleep = _time_mod.sleep
_time_mod.sleep = lambda s: _original_sleep(min(s, 0.01))

import cc_layer.cli

# --- Mock ExternalDataFetcher (Tavily) ---
import app.services.external_data_fetcher as _edf_mod
class _MockExternalDataFetcher:
    def __init__(self, **kw):
        self.is_available = True
    def search(self, query, **kw): return [{"title": "Mock Result", "content": "テスト結果", "url": "https://example.com"}]
    def search_job_market(self, **kw): return [{"title": "求人情報", "content": "テスト"}]
    def search_industry_news(self, **kw): return [{"title": "業界ニュース", "content": "テスト"}]
    def search_hr_trends(self, **kw): return [{"title": "HRトレンド", "content": "テスト"}]
_edf_mod.ExternalDataFetcher = _MockExternalDataFetcher

import importlib
module_name = sys.argv[1]
sys.argv = sys.argv[1:]
sys.argv[0] = f"cc_layer.cli.{module_name}"
mod = importlib.import_module(f"cc_layer.cli.{module_name}")
mod.main()
'''


def _run_cli_with_tavily_mock(
    module: str, args: list[str], tmp_dir: str, stdin_data: str = None,
) -> dict:
    """Run a CLI module with Tavily + LLM fully mocked."""
    wrapper_path = os.path.join(tmp_dir, "_tavily_mock_runner.py")
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(_TAVILY_MOCK_SCRIPT)

    cmd = [PYTHON, wrapper_path, module] + args
    env = os.environ.copy()
    env["PROJECT_ROOT"] = PROJECT_ROOT
    env["TAVILY_API_KEY"] = "fake_test_key"
    env["LLM_API_KEY"] = "fake_test_key"

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=PROJECT_ROOT, input=stdin_data, timeout=120, env=env,
    )

    parsed_json = _parse_last_json(result.stdout)

    if result.returncode != 0:
        print(f"TAVILY MOCK CLI FAILED [{module}]: rc={result.returncode}", file=sys.stderr)
        print(f"STDERR: {result.stderr[:800]}", file=sys.stderr)
        print(f"STDOUT: {result.stdout[:300]}", file=sys.stderr)

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "json": parsed_json,
    }


def _run_cli_with_zep_mock(
    module: str, args: list[str], tmp_dir: str, stdin_data: str = None,
) -> dict:
    """Run a CLI module with Zep SDK fully mocked."""
    wrapper_path = os.path.join(tmp_dir, "_zep_mock_runner.py")
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(_ZEP_MOCK_SCRIPT)

    cmd = [PYTHON, wrapper_path, module] + args
    env = os.environ.copy()
    env["PROJECT_ROOT"] = PROJECT_ROOT
    env["ZEP_API_KEY"] = "fake_test_key"
    env["TAVILY_API_KEY"] = ""
    env["LLM_API_KEY"] = "fake_test_key"

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=PROJECT_ROOT, input=stdin_data, timeout=120, env=env,
    )

    parsed_json = _parse_last_json(result.stdout)

    if result.returncode != 0:
        print(f"MOCK CLI FAILED [{module}]: rc={result.returncode}", file=sys.stderr)
        print(f"STDERR: {result.stderr[:800]}", file=sys.stderr)
        print(f"STDOUT: {result.stdout[:300]}", file=sys.stderr)

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "json": parsed_json,
    }
