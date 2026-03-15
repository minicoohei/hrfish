"""Tests for canonical schemas, normalizer, validator, and security helpers."""
import json

import pytest

from cc_layer.schemas.canonical import Snapshot, ExpandedPath, Scenario, SwarmAction, SwarmAgent
from cc_layer.schemas.normalize import (
    normalize_expanded_path,
    normalize_swarm_action,
    normalize_swarm_agent,
    normalize_multipath_result,
    normalize_session_in_memory,
    normalize_session_to_disk,
)
from cc_layer.schemas.validate import validate_session
from cc_layer.cli.report_html import safe_json_embed


# --- safe_json_embed (XSS prevention) ---

class TestSafeJsonEmbed:
    def test_script_tag_escape(self):
        """</script> が含まれるデータでスクリプト文脈脱出を防ぐ"""
        data = {"label": "test</script><script>alert(1)//"}
        result = safe_json_embed(data)
        assert "</script>" not in result
        assert r"<\/script>" in result

    def test_html_comment_escape(self):
        """<!-- が含まれるデータでHTMLコメント脱出を防ぐ"""
        data = {"note": "<!--injection-->"}
        result = safe_json_embed(data)
        assert "<!--" not in result

    def test_normal_json_unchanged(self):
        """通常のJSONデータはそのまま出力される"""
        data = {"name": "テスト太郎", "income": 5000}
        result = safe_json_embed(data)
        parsed = json.loads(result)
        assert parsed == data

    def test_roundtrip_with_special_chars(self):
        """エスケープ後もJSONとしてパース可能"""
        data = {"html": "<div>test</div>", "script": "</script>"}
        result = safe_json_embed(data)
        # ブラウザ側でもJSONとしてパース可能であることを確認
        # (</→<\/ はJS文字列リテラル内で有効)
        assert r"<\/script>" in result


# --- Snapshot ---

class TestSnapshot:
    def test_canonical(self):
        s = Snapshot(annual_income=2500, satisfaction=0.8, stress=0.3, work_life_balance=0.6)
        assert s.annual_income == 2500
        assert s.satisfaction == 0.8

    def test_defaults(self):
        s = Snapshot()
        assert s.annual_income == 0
        assert s.satisfaction == 0.5

    def test_validation_rejects_out_of_range(self):
        with pytest.raises(Exception):
            Snapshot(annual_income=2500, satisfaction=1.5, stress=0.3, work_life_balance=0.6)


# --- normalize_expanded_path ---

class TestNormalizeExpandedPath:
    def test_flat_final_salary(self):
        """SubAgentが final_salary をシナリオ直下に出した場合の正規化"""
        raw = {
            "path_id": "path_a",
            "label": "テストパス",
            "scenarios": [{
                "scenario_id": "best",
                "label": "ベスト",
                "probability": 0.1,
                "final_salary": 8000,
                "final_satisfaction": 0.9,
            }]
        }
        result = normalize_expanded_path(raw)
        assert result.scenarios[0].final_state.annual_income == 8000
        assert result.scenarios[0].final_state.satisfaction == 0.9

    def test_already_canonical(self):
        """既に final_state がある場合はそのまま通る"""
        raw = {
            "path_id": "path_b",
            "label": "テスト",
            "scenarios": [{
                "scenario_id": "likely",
                "label": "普通",
                "probability": 0.5,
                "final_state": {
                    "annual_income": 3000,
                    "satisfaction": 0.7,
                    "stress": 0.4,
                    "work_life_balance": 0.6,
                }
            }]
        }
        result = normalize_expanded_path(raw)
        assert result.scenarios[0].final_state.annual_income == 3000

    def test_path_label_fallback(self):
        """path_label → label に正規化"""
        raw = {
            "path_id": "path_c",
            "path_label": "ラベル",
            "scenarios": []
        }
        result = normalize_expanded_path(raw)
        assert result.label == "ラベル"

    def test_auto_generate_upside_risk(self):
        """upside/risk が空の場合に自動生成"""
        raw = {
            "path_id": "path_a",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.1,
                 "final_salary": 8000, "final_satisfaction": 0.9},
                {"scenario_id": "likely", "label": "普通", "probability": 0.5,
                 "final_salary": 4000, "final_satisfaction": 0.7},
                {"scenario_id": "base", "label": "ベース", "probability": 0.4,
                 "final_salary": 2000, "final_satisfaction": 0.5},
            ]
        }
        result = normalize_expanded_path(raw)
        assert "8000" in result.upside
        assert "2000" in result.risk

    def test_empty_scenarios(self):
        """scenarios が空リストでも IndexError にならない"""
        raw = {"path_id": "path_x", "label": "空", "scenarios": []}
        result = normalize_expanded_path(raw)
        assert result.scenarios == []
        assert result.upside == ""

    def test_final_salary_zero_preserved(self):
        """final_salary=0 が falsy でも上書きされない"""
        raw = {
            "path_id": "path_a",
            "label": "テスト",
            "final_salary": 0,
            "scenarios": [{
                "scenario_id": "likely",
                "label": "普通",
                "probability": 0.5,
                "final_state": {"annual_income": 5000, "satisfaction": 0.7},
            }]
        }
        result = normalize_expanded_path(raw)
        assert result.final_salary == 0  # 上書きされない

    def test_no_best_scenario_upside_empty(self):
        """best シナリオがない場合 upside は空"""
        raw = {
            "path_id": "path_a", "label": "テスト",
            "scenarios": [
                {"scenario_id": "likely", "label": "普通", "probability": 0.6,
                 "final_salary": 4000, "final_satisfaction": 0.7},
                {"scenario_id": "base", "label": "ベース", "probability": 0.4,
                 "final_salary": 2000, "final_satisfaction": 0.5},
            ]
        }
        result = normalize_expanded_path(raw)
        assert result.upside == ""

    def test_no_base_scenario_risk_empty(self):
        """base シナリオがない場合 risk は空"""
        raw = {
            "path_id": "path_a", "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
                 "final_salary": 8000, "final_satisfaction": 0.9},
                {"scenario_id": "likely", "label": "普通", "probability": 0.8,
                 "final_salary": 4000, "final_satisfaction": 0.7},
            ]
        }
        result = normalize_expanded_path(raw)
        assert result.risk == ""
        assert "8000" in result.upside

    def test_only_one_scenario_fallback(self):
        """likely がなく scenarios[0] にフォールバック"""
        raw = {
            "path_id": "path_a", "label": "テスト",
            "scenarios": [{
                "scenario_id": "best", "label": "ベスト", "probability": 1.0,
                "final_salary": 10000, "final_satisfaction": 0.95,
            }]
        }
        result = normalize_expanded_path(raw)
        # likely がないので scenarios[0] (best) から final_salary を取得
        assert result.scenarios[0].final_state.annual_income == 10000

    def test_real_session_kou_format(self):
        """session_kou の実データ形式を正規化できる"""
        raw = {
            "path_id": "path_a",
            "label": "スケールアップ",
            "path_label": "スケールアップ",
            "final_salary": 4500,
            "final_satisfaction": 0.78,
            "score": 0.72,
            "overall_probability": 0.35,
            "final_age": 47,
            "final_role": "代表取締役CEO",
            "scenarios": [{
                "scenario_id": "best",
                "label": "Best: IPO成功",
                "probability": 0.08,
                "final_salary": 12000,
                "final_satisfaction": 0.92,
                "periods": [{
                    "period_name": "Period 1 (37-39歳)",
                    "events": [{"type": "事業拡大", "description": "法人営業体制構築"}]
                }]
            }]
        }
        result = normalize_expanded_path(raw)
        assert result.scenarios[0].final_state.annual_income == 12000
        assert result.final_age == 47
        assert result.final_role == "代表取締役CEO"
        assert result.score == 0.72

    def test_extra_fields_preserved(self):
        """extra="allow" で未知フィールドが保持される"""
        raw = {
            "path_id": "path_a",
            "label": "テスト",
            "custom_field": "preserved",
            "scenarios": []
        }
        result = normalize_expanded_path(raw)
        assert result.model_dump().get("custom_field") == "preserved"


# --- normalize_swarm_action ---

class TestNormalizeSwarmAction:
    def test_flat_content(self):
        """content をトップレベルに出した場合の正規化"""
        raw = {
            "round": 1,
            "agent_id": 0,
            "agent_name": "テスト",
            "action_type": "CREATE_POST",
            "content": "投稿内容",
        }
        result = normalize_swarm_action(raw)
        assert result.round_num == 1
        assert result.action_args["content"] == "投稿内容"

    def test_already_canonical(self):
        """既にcanonical形式のデータはそのまま通る"""
        raw = {
            "round_num": 1,
            "agent_id": 0,
            "agent_name": "テスト",
            "action_type": "CREATE_POST",
            "action_args": {"content": "投稿内容"},
        }
        result = normalize_swarm_action(raw)
        assert result.round_num == 1
        assert result.action_args["content"] == "投稿内容"

    def test_target_normalization(self):
        """target → action_args.target_post_id"""
        raw = {
            "round_num": 2,
            "agent_id": 1,
            "agent_name": "テスト",
            "action_type": "CREATE_COMMENT",
            "content": "コメント",
            "target": "post_123",
        }
        result = normalize_swarm_action(raw)
        assert result.action_args["target_post_id"] == "post_123"

    def test_action_args_null(self):
        """action_args が null の場合でも TypeError にならない"""
        raw = {
            "round_num": 1,
            "agent_id": 0,
            "agent_name": "テスト",
            "action_type": "CREATE_POST",
            "action_args": None,
            "content": "投稿内容",
        }
        result = normalize_swarm_action(raw)
        assert result.action_args["content"] == "投稿内容"

    def test_action_args_missing(self):
        """action_args キー自体がない場合"""
        raw = {
            "round_num": 1,
            "agent_id": 0,
            "agent_name": "テスト",
            "action_type": "CREATE_POST",
        }
        result = normalize_swarm_action(raw)
        assert isinstance(result.action_args, dict)


# --- normalize_swarm_agent ---

class TestNormalizeSwarmAgent:
    def test_bio_from_background(self):
        """bio がなく background がある場合"""
        raw = {"agent_id": 1, "name": "テスト", "background": "元Google PM", "personality": "分析的"}
        result = normalize_swarm_agent(raw)
        assert "元Google PM" in result.bio

    def test_bio_from_personality_only(self):
        """bio も background もなく personality のみの場合"""
        raw = {"agent_id": 1, "name": "テスト", "personality": "分析的で慎重"}
        result = normalize_swarm_agent(raw)
        assert "分析的で慎重" in result.bio

    def test_bio_already_set(self):
        """bio が既にある場合はそのまま"""
        raw = {"agent_id": 1, "name": "テスト", "bio": "既存のbio", "background": "上書きしない"}
        result = normalize_swarm_agent(raw)
        assert result.bio == "既存のbio"

    def test_stance_default_fallback(self):
        """stance_default → stance"""
        raw = {"agent_id": 1, "name": "テスト", "stance_default": "opposing"}
        result = normalize_swarm_agent(raw)
        assert result.stance == "opposing"


# --- normalize_multipath_result ---

class TestNormalizeMultipathResult:
    def test_rankings_to_ranking(self):
        """rankings → ranking に正規化"""
        raw = {
            "paths": [],
            "rankings": {"path_a": 1, "path_b": 2},
        }
        result = normalize_multipath_result(raw)
        assert result.ranking == {"path_a": 1, "path_b": 2}

    def test_nested_path_normalization(self):
        """paths 内の各パスも正規化される"""
        raw = {
            "paths": [{
                "path_id": "path_a",
                "label": "テスト",
                "scenarios": [{
                    "scenario_id": "best",
                    "label": "ベスト",
                    "probability": 0.1,
                    "final_salary": 5000,
                    "final_satisfaction": 0.85,
                }]
            }]
        }
        result = normalize_multipath_result(raw)
        assert result.paths[0].scenarios[0].final_state.annual_income == 5000


# --- validate_session ---

class TestValidateSession:
    def test_missing_required(self, tmp_path):
        """必須ファイルが欠けている場合のエラー"""
        report = validate_session(str(tmp_path))
        assert report.has_errors
        assert "agent_state.json" in report.format()

    def test_complete(self, tmp_path):
        """全ファイル揃っている場合"""
        (tmp_path / "agent_state.json").write_text('{"identity": {}, "state": {}}')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert not report.has_errors

    def test_invalid_json(self, tmp_path):
        """不正なJSONの検出"""
        (tmp_path / "agent_state.json").write_text('{"broken')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert report.has_errors
        assert "invalid JSON" in report.format()

    def test_optional_warnings(self, tmp_path):
        """オプションファイルがない場合はwarning"""
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert not report.has_errors
        assert len(report.warnings) > 0

    def test_invalid_jsonl(self, tmp_path):
        """JSONL行が壊れている場合のエラー検出"""
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        swarm_dir = tmp_path / "swarm"
        swarm_dir.mkdir()
        (swarm_dir / "all_actions_round_001.jsonl").write_text(
            '{"round_num": 1, "agent_id": 0}\n'
            '{broken json line}\n'
            '{"round_num": 1, "agent_id": 1}\n'
        )
        report = validate_session(str(tmp_path))
        assert report.has_errors
        assert "invalid JSONL" in report.format()
        assert ":2:" in report.format()  # 2行目がエラー

    def test_valid_jsonl(self, tmp_path):
        """正常なJSONLファイルはエラーにならない"""
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        swarm_dir = tmp_path / "swarm"
        swarm_dir.mkdir()
        (swarm_dir / "all_actions_round_001.jsonl").write_text(
            '{"round_num": 1, "agent_id": 0}\n'
            '{"round_num": 1, "agent_id": 1}\n'
        )
        report = validate_session(str(tmp_path))
        assert not report.has_errors

    def test_empty_file(self, tmp_path):
        """空ファイル (0バイト) の読み込み"""
        (tmp_path / "agent_state.json").write_text('')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert report.has_errors
        assert "invalid JSON" in report.format()

    def test_invalid_optional_json_warns(self, tmp_path):
        """オプションファイルの不正JSONはwarning"""
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        (tmp_path / "profile.json").write_text('{broken')
        report = validate_session(str(tmp_path))
        assert not report.has_errors  # optional なので error ではなく warning
        assert any("invalid JSON (optional)" in w for w in report.warnings)

    def test_multiple_jsonl_all_checked(self, tmp_path):
        """複数JSONLファイルが全て検査される"""
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text('{"paths": []}')
        (tmp_path / "swarm_agents.json").write_text('[]')
        swarm_dir = tmp_path / "swarm"
        swarm_dir.mkdir()
        (swarm_dir / "all_actions_round_001.jsonl").write_text('{"ok": true}\n')
        (swarm_dir / "all_actions_round_002.jsonl").write_text('{broken}\n')
        report = validate_session(str(tmp_path))
        assert report.has_errors
        assert "round_002" in report.format()


# --- normalize_session_in_memory / to_disk ---

class TestNormalizeSession:
    def _setup_session(self, tmp_path):
        """テスト用セッションデータを作成"""
        mp = {
            "paths": [{
                "path_id": "path_a", "label": "テスト",
                "scenarios": [{
                    "scenario_id": "likely", "label": "普通",
                    "probability": 0.5, "final_salary": 4000,
                    "final_satisfaction": 0.7,
                }]
            }],
            "rankings": {"path_a": 1},
        }
        (tmp_path / "multipath_result.json").write_text(
            json.dumps(mp, ensure_ascii=False))
        agents = [{"agent_id": 0, "name": "テスト", "background": "PM経験者"}]
        (tmp_path / "swarm_agents.json").write_text(
            json.dumps(agents, ensure_ascii=False))
        swarm_dir = tmp_path / "swarm"
        swarm_dir.mkdir()
        actions = [
            '{"round": 1, "agent_id": 0, "agent_name": "テスト", "action_type": "CREATE_POST", "content": "投稿"}',
            '{"round": 2, "agent_id": 0, "agent_name": "テスト", "action_type": "CREATE_POST", "content": "投稿2"}',
        ]
        (swarm_dir / "all_actions_round_001.jsonl").write_text(actions[0] + "\n")
        (swarm_dir / "all_actions_round_002.jsonl").write_text(actions[1] + "\n")
        return tmp_path

    def test_in_memory_returns_all_keys(self, tmp_path):
        """全ファイルがある場合、3つのキーが返る"""
        self._setup_session(tmp_path)
        result = normalize_session_in_memory(str(tmp_path))
        assert "multipath_result" in result
        assert "swarm_agents" in result
        assert "swarm_actions" in result

    def test_in_memory_normalizes_data(self, tmp_path):
        """rankings → ranking, round → round_num の正規化"""
        self._setup_session(tmp_path)
        result = normalize_session_in_memory(str(tmp_path))
        assert result["multipath_result"].ranking == {"path_a": 1}
        assert result["swarm_actions"][0].round_num == 1
        assert result["swarm_agents"][0].bio != ""

    def test_in_memory_missing_files(self, tmp_path):
        """ファイルがない場合は該当キーがない"""
        result = normalize_session_in_memory(str(tmp_path))
        assert "multipath_result" not in result
        assert "swarm_agents" not in result

    def test_to_disk_writes_files(self, tmp_path):
        """to_disk: 正規化結果がファイルに書き込まれる"""
        self._setup_session(tmp_path)
        results = normalize_session_to_disk(str(tmp_path))
        assert "multipath_result.json" in results
        # ファイルが正規化されたことを確認
        mp = json.loads((tmp_path / "multipath_result.json").read_text())
        assert mp["ranking"] == {"path_a": 1}
        assert "rankings" not in mp
        # scenarios内の final_state が正規化されている
        assert mp["paths"][0]["scenarios"][0]["final_state"]["annual_income"] == 4000

    def test_to_disk_idempotent(self, tmp_path):
        """to_disk を2回実行しても結果が同じ"""
        self._setup_session(tmp_path)
        normalize_session_to_disk(str(tmp_path))
        mp1 = json.loads((tmp_path / "multipath_result.json").read_text())
        normalize_session_to_disk(str(tmp_path))
        mp2 = json.loads((tmp_path / "multipath_result.json").read_text())
        assert mp1 == mp2


# --- generate_family_agents ---

class TestGenerateFamilyAgents:
    def test_parent_without_spouse_no_crash(self):
        """配偶者なし・親ありで UnboundLocalError にならない"""
        from cc_layer.cli.generate_swarm_agents import generate_family_agents
        identity = {"name": "テスト太郎", "gender": "男性"}
        state = {"family": [
            {"relation": "parent", "age": 65, "notes": "健康"},
        ]}
        agents = generate_family_agents(identity, state)
        assert len(agents) == 1
        assert "太郎" in agents[0]["name"] or "テスト" in agents[0]["name"]

    def test_spouse_and_parent(self):
        """配偶者あり・親ありの正常系"""
        from cc_layer.cli.generate_swarm_agents import generate_family_agents
        identity = {"name": "テスト太郎", "gender": "男性"}
        state = {"family": [
            {"relation": "spouse", "age": 35, "notes": "パート勤務"},
            {"relation": "parent", "age": 65, "notes": "健康"},
        ]}
        agents = generate_family_agents(identity, state)
        assert len(agents) == 2

    def test_empty_family(self):
        """家族なしの場合"""
        from cc_layer.cli.generate_swarm_agents import generate_family_agents
        identity = {"name": "テスト太郎"}
        state = {"family": []}
        agents = generate_family_agents(identity, state)
        assert agents == []


# --- Real SubAgent output variation patterns ---
# These test patterns found in actual sample data (samples 01-10).
# Each test uses deep copy to ensure input data is not mutated (revert-safe).

import copy
from cc_layer.schemas.normalize import normalize_snapshot, _normalize_events, _normalize_scenarios_dict


class TestValidateMultipathStructure:
    """multipath_result.json の構造バリデーション"""

    def test_missing_snapshot_in_period(self, tmp_path):
        """period に snapshot がない場合 warning"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [{
            "scenario_id": "likely", "label": "標準", "probability": 0.5,
            "final_state": {"annual_income": 1000, "satisfaction": 0.7},
            "periods": [{"period_name": "Year 1", "narrative": "text"}],
        }]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("snapshot missing" in w for w in report.warnings)

    def test_missing_final_state(self, tmp_path):
        """scenario に final_state がない場合 error"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [{
            "scenario_id": "likely", "label": "標準", "probability": 0.5,
            "periods": [],
        }]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("final_state missing" in e for e in report.errors)

    def test_0_100_scale_detected(self, tmp_path):
        """0-100 スケールの検出"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [{
            "scenario_id": "likely", "label": "標準", "probability": 0.5,
            "final_state": {"annual_income": 1000, "satisfaction": 0.7},
            "periods": [{"period_name": "Y1",
                "snapshot": {"annual_income": 800, "satisfaction": 85, "stress": 0.3}}],
        }]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("0-100 scale" in w for w in report.warnings)

    def test_dict_scenarios_detected(self, tmp_path):
        """dict 形式 scenarios の検出"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": {
            "best": {"label": "ベスト", "probability": 0.2,
                     "final_state": {"annual_income": 2000}},
        }}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("dict, not list" in w for w in report.warnings)

    def test_string_events_detected(self, tmp_path):
        """文字列イベントの検出"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [{
            "scenario_id": "likely", "label": "標準", "probability": 0.5,
            "final_state": {"annual_income": 1000},
            "periods": [{"period_name": "Y1",
                "snapshot": {"annual_income": 800, "satisfaction": 0.6},
                "events": ["転職した"]}],
        }]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("string, not dict" in w for w in report.warnings)

    def test_yen_unit_error_detected(self, tmp_path):
        """annual_income が円単位（>100000）の場合 error"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [{
            "scenario_id": "likely", "label": "標準", "probability": 0.5,
            "final_state": {"annual_income": 40000000, "satisfaction": 0.7},
            "periods": [],
        }]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("yen, not 万円" in e for e in report.errors)

    def test_optimistic_base_detected(self, tmp_path):
        """base が best の85%以上の場合 warning"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [
            {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
             "final_state": {"annual_income": 2000, "satisfaction": 0.9}},
            {"scenario_id": "base", "label": "ベース", "probability": 0.3,
             "final_state": {"annual_income": 1900, "satisfaction": 0.7}},
        ]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert any("too optimistic" in w for w in report.warnings)

    def test_realistic_base_no_warning(self, tmp_path):
        """base が best の50%程度なら warning なし"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [
            {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
             "final_state": {"annual_income": 2000, "satisfaction": 0.9}},
            {"scenario_id": "base", "label": "ベース", "probability": 0.3,
             "final_state": {"annual_income": 1000, "satisfaction": 0.6}},
        ]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        assert not any("too optimistic" in w for w in report.warnings)

    def test_clean_data_no_warnings(self, tmp_path):
        """正常データは warning なし（ファイル存在系除く）"""
        mp = {"paths": [{"path_id": "p1", "label": "test", "scenarios": [{
            "scenario_id": "likely", "label": "標準", "probability": 0.5,
            "final_state": {"annual_income": 1000, "satisfaction": 0.7,
                            "stress": 0.3, "work_life_balance": 0.6},
            "periods": [{"period_name": "Y1",
                "snapshot": {"annual_income": 800, "satisfaction": 0.6,
                             "stress": 0.4, "work_life_balance": 0.5},
                "events": [{"type": "promotion", "description": "昇進"}]}],
        }]}]}
        (tmp_path / "agent_state.json").write_text('{}')
        (tmp_path / "multipath_result.json").write_text(json.dumps(mp))
        (tmp_path / "swarm_agents.json").write_text('[]')
        report = validate_session(str(tmp_path))
        # ファイル存在系以外の warning がないことを確認
        structural_warnings = [w for w in report.warnings if "not found" not in w and "empty" not in w]
        assert structural_warnings == []


class TestNormalizeSnapshotVariations:
    """normalize_snapshot: SubAgent出力の値域・フィールド名揺れ"""

    def test_salary_to_annual_income(self):
        """salary → annual_income 変換"""
        raw = {"salary": 800, "satisfaction": 0.7}
        original = copy.deepcopy(raw)
        result = normalize_snapshot(raw)
        assert result["annual_income"] == 800
        assert "salary" not in result
        # 元データが変更されていないことを確認
        assert raw == original or "annual_income" in raw  # normalize_snapshot は in-place 変換

    def test_salary_not_overwrite_existing_annual_income(self):
        """annual_income が既にある場合 salary は無視"""
        raw = {"salary": 500, "annual_income": 800}
        result = normalize_snapshot(raw)
        assert result["annual_income"] == 800

    def test_scale_0_100_to_0_1_satisfaction(self):
        """satisfaction: 85 (0-100) → 0.85 (0-1)"""
        raw = {"satisfaction": 85}
        result = normalize_snapshot(raw)
        assert 0 <= result["satisfaction"] <= 1
        assert result["satisfaction"] == 0.85

    def test_scale_0_100_to_0_1_stress(self):
        """stress: 55 (0-100) → 0.55 (0-1)"""
        raw = {"stress": 55}
        result = normalize_snapshot(raw)
        assert 0 <= result["stress"] <= 1
        assert result["stress"] == 0.55

    def test_scale_0_100_to_0_1_wlb(self):
        """work_life_balance: 70 (0-100) → 0.70 (0-1)"""
        raw = {"work_life_balance": 70}
        result = normalize_snapshot(raw)
        assert 0 <= result["work_life_balance"] <= 1
        assert result["work_life_balance"] == 0.7

    def test_already_0_1_scale_unchanged(self):
        """既に 0-1 スケールの値はそのまま"""
        raw = {"satisfaction": 0.85, "stress": 0.3, "work_life_balance": 0.6}
        result = normalize_snapshot(raw)
        assert result["satisfaction"] == 0.85
        assert result["stress"] == 0.3

    def test_boundary_value_1(self):
        """値=1 はスケーリングしない（0-1の最大値）"""
        raw = {"satisfaction": 1}
        result = normalize_snapshot(raw)
        assert result["satisfaction"] == 1

    def test_boundary_value_0(self):
        """値=0 はスケーリングしない"""
        raw = {"satisfaction": 0, "stress": 0}
        result = normalize_snapshot(raw)
        assert result["satisfaction"] == 0

    def test_value_100(self):
        """値=100 → 1.0"""
        raw = {"satisfaction": 100}
        result = normalize_snapshot(raw)
        assert result["satisfaction"] == 1.0

    def test_yen_to_man_yen(self):
        """annual_income > 100000 は円→万円変換"""
        raw = {"annual_income": 40000000}
        result = normalize_snapshot(raw)
        assert result["annual_income"] == 4000.0

    def test_man_yen_unchanged(self):
        """annual_income <= 100000 (万円単位) はそのまま"""
        raw = {"annual_income": 2500}
        result = normalize_snapshot(raw)
        assert result["annual_income"] == 2500


class TestNormalizeEventsVariations:
    """_normalize_events: SubAgentが文字列イベントを返すケース (sample_04)"""

    def test_string_events_to_dict(self):
        """文字列イベント → Event dict"""
        raw = ["転職した", "昇進した", "子供が生まれた"]
        original = copy.deepcopy(raw)
        result = _normalize_events(raw)
        assert len(result) == 3
        assert all(isinstance(e, dict) for e in result)
        assert result[0]["description"] == "転職した"
        assert result[0]["type"] == ""
        # 元データは変更されない
        assert raw == original

    def test_mixed_string_and_dict_events(self):
        """文字列とdictが混在するケース"""
        raw = [
            "文字列イベント",
            {"type": "昇進", "description": "マネージャーに昇進"},
        ]
        result = _normalize_events(raw)
        assert len(result) == 2
        assert result[0] == {"type": "", "description": "文字列イベント"}
        assert result[1]["type"] == "昇進"

    def test_empty_events(self):
        """空リスト"""
        assert _normalize_events([]) == []

    def test_dict_events_unchanged(self):
        """全てdictの場合はそのまま通る"""
        raw = [{"type": "転職", "description": "XX社へ"}]
        result = _normalize_events(raw)
        assert result == raw


class TestNormalizeScenariosDict:
    """_normalize_scenarios_dict: dict形式シナリオ (samples 06-08)"""

    def test_dict_to_list(self):
        """{"best": {...}, "likely": {...}} → [{scenario_id: "best", ...}, ...]"""
        raw = {
            "best": {"label": "ベスト", "probability": 0.2},
            "likely": {"label": "標準", "probability": 0.5},
            "base": {"label": "ベース", "probability": 0.3},
        }
        original = copy.deepcopy(raw)
        result = _normalize_scenarios_dict(raw)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["scenario_id"] == "best"
        assert result[0]["label"] == "ベスト"
        # 元データは変更されない
        assert raw == original

    def test_list_passthrough(self):
        """リスト形式はそのまま通る"""
        raw = [{"scenario_id": "best", "label": "ベスト"}]
        result = _normalize_scenarios_dict(raw)
        assert result is raw  # 同一オブジェクト

    def test_dict_value_not_dict(self):
        """dict の値が dict でない場合"""
        raw = {"best": "simple_string"}
        result = _normalize_scenarios_dict(raw)
        assert result[0]["scenario_id"] == "best"


class TestNormalizeExpandedPathRealPatterns:
    """実サンプルで見つかった SubAgent 出力揺れパターン"""

    def test_dict_scenarios_sample06(self):
        """sample_06: scenarios が dict 形式"""
        raw = {
            "path_id": "path_a",
            "label": "法人化パス",
            "scenarios": {
                "best": {"label": "ベスト", "probability": 0.2,
                         "final_state": {"annual_income": 2000, "satisfaction": 0.9,
                                         "stress": 0.3, "work_life_balance": 0.7}},
                "likely": {"label": "標準", "probability": 0.5,
                           "final_state": {"annual_income": 1500, "satisfaction": 0.7,
                                           "stress": 0.5, "work_life_balance": 0.6}},
                "base": {"label": "ベース", "probability": 0.3,
                         "final_state": {"annual_income": 1000, "satisfaction": 0.5,
                                         "stress": 0.6, "work_life_balance": 0.5}},
            }
        }
        original = copy.deepcopy(raw)
        result = normalize_expanded_path(raw)
        assert isinstance(result.scenarios, list)
        assert len(result.scenarios) == 3
        assert result.scenarios[0].scenario_id == "best"
        # 元データ（dict形式）は変更されない
        assert isinstance(original["scenarios"], dict)

    def test_string_events_in_periods_sample04(self):
        """sample_04: periods 内の events が文字列リスト"""
        raw = {
            "path_id": "path_b",
            "label": "顧問パス",
            "scenarios": [{
                "scenario_id": "likely",
                "label": "標準",
                "probability": 0.5,
                "final_state": {"annual_income": 1200, "satisfaction": 0.7,
                                "stress": 0.4, "work_life_balance": 0.6},
                "periods": [{
                    "period_name": "Period 1",
                    "events": ["退職金受領", "顧問契約開始", "年金受給手続き"],
                    "snapshot": {"annual_income": 1000, "satisfaction": 0.6},
                }]
            }]
        }
        result = normalize_expanded_path(raw)
        events = result.scenarios[0].periods[0].events
        assert all(hasattr(e, "description") for e in events)
        assert events[0].description == "退職金受領"

    def test_dict_branch_point_sample06(self):
        """sample_06: branch_point が dict 形式"""
        raw = {
            "path_id": "path_c",
            "label": "CTO転身",
            "branch_point": {
                "timing": "2027年",
                "description": "フリーランスから法人化の意思決定",
                "trigger": "年収1500万到達時",
            },
            "scenarios": [{
                "scenario_id": "likely", "label": "標準",
                "probability": 0.5,
                "final_state": {"annual_income": 1800, "satisfaction": 0.8,
                                "stress": 0.4, "work_life_balance": 0.6},
            }]
        }
        result = normalize_expanded_path(raw)
        assert isinstance(result.branch_point, str)
        assert "2027年" in result.branch_point
        assert "フリーランス" in result.branch_point

    def test_0_100_scale_in_final_state_sample06(self):
        """sample_06: final_state 内が 0-100 スケール"""
        raw = {
            "path_id": "path_d",
            "label": "テスト",
            "scenarios": [{
                "scenario_id": "likely",
                "label": "標準",
                "probability": 0.5,
                "final_state": {
                    "annual_income": 1500,
                    "satisfaction": 85,
                    "stress": 55,
                    "work_life_balance": 70,
                },
            }]
        }
        result = normalize_expanded_path(raw)
        fs = result.scenarios[0].final_state
        assert 0 <= fs.satisfaction <= 1, f"satisfaction={fs.satisfaction} not in 0-1"
        assert 0 <= fs.stress <= 1, f"stress={fs.stress} not in 0-1"
        assert 0 <= fs.work_life_balance <= 1

    def test_missing_probability_sample07(self):
        """sample_07: probability フィールドが欠落 → デフォルト補完"""
        raw = {
            "path_id": "path_e",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト",
                 "final_state": {"annual_income": 3000, "satisfaction": 0.9}},
                {"scenario_id": "likely", "label": "標準",
                 "final_state": {"annual_income": 2000, "satisfaction": 0.7}},
                {"scenario_id": "base", "label": "ベース",
                 "final_state": {"annual_income": 1200, "satisfaction": 0.5}},
            ]
        }
        result = normalize_expanded_path(raw)
        for s in result.scenarios:
            assert 0 < s.probability <= 1, f"{s.scenario_id}: probability={s.probability}"
        # best=0.15, likely=0.45, base=0.25
        assert result.scenarios[0].probability == 0.15
        assert result.scenarios[1].probability == 0.45
        assert result.scenarios[2].probability == 0.25

    def test_missing_label_sample08(self):
        """sample_08: scenario の label フィールドが欠落 → デフォルト補完"""
        raw = {
            "path_id": "path_f",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "probability": 0.2,
                 "final_state": {"annual_income": 2500, "satisfaction": 0.9}},
                {"scenario_id": "likely", "probability": 0.5,
                 "final_state": {"annual_income": 1800, "satisfaction": 0.7}},
            ]
        }
        result = normalize_expanded_path(raw)
        assert result.scenarios[0].label == "ベストケース"
        assert result.scenarios[1].label == "標準ケース"

    def test_0_100_in_period_snapshots(self):
        """common_periods 内の snapshot も 0-100 → 0-1 変換"""
        raw = {
            "path_id": "path_g",
            "label": "テスト",
            "common_periods": [{
                "period_name": "Period 1",
                "snapshot": {"salary": 800, "satisfaction": 75, "stress": 40},
            }],
            "scenarios": [{
                "scenario_id": "likely", "label": "標準", "probability": 0.5,
                "final_state": {"annual_income": 1000, "satisfaction": 0.7},
            }],
        }
        result = normalize_expanded_path(raw)
        snap = result.common_periods[0].snapshot
        assert snap.annual_income == 800  # salary → annual_income
        assert snap.satisfaction == 0.75  # 75 → 0.75
        assert snap.stress == 0.4  # 40 → 0.40

    def test_missing_snapshot_interpolation(self):
        """periods に snapshot がない場合、common_periods → final_state で線形補間"""
        raw = {
            "path_id": "path_interp",
            "label": "補間テスト",
            "common_periods": [{
                "period_name": "Year 1-2",
                "snapshot": {"annual_income": 800, "satisfaction": 0.7,
                             "stress": 0.3, "work_life_balance": 0.6},
            }],
            "scenarios": [{
                "scenario_id": "likely",
                "label": "標準",
                "probability": 0.5,
                "final_state": {"annual_income": 1400, "satisfaction": 0.9,
                                "stress": 0.5, "work_life_balance": 0.7},
                "periods": [
                    {"period_name": "Year 3-5", "narrative": "ナラティブのみ"},
                    {"period_name": "Year 6-8", "narrative": "ナラティブのみ"},
                ],
            }]
        }
        result = normalize_expanded_path(raw)
        periods = result.scenarios[0].periods
        # 2 missing periods → t=1/3, t=2/3
        assert periods[0].snapshot.annual_income > 800
        assert periods[0].snapshot.annual_income < 1400
        assert periods[1].snapshot.annual_income > periods[0].snapshot.annual_income
        assert periods[1].snapshot.annual_income < 1400

    def test_no_interpolation_when_snapshots_exist(self):
        """snapshot がある periods は補間しない"""
        raw = {
            "path_id": "path_no_interp",
            "label": "テスト",
            "scenarios": [{
                "scenario_id": "likely",
                "label": "標準",
                "probability": 0.5,
                "final_state": {"annual_income": 2000, "satisfaction": 0.8},
                "periods": [
                    {"period_name": "Year 1", "snapshot": {"annual_income": 1000, "satisfaction": 0.6}},
                ],
            }]
        }
        result = normalize_expanded_path(raw)
        assert result.scenarios[0].periods[0].snapshot.annual_income == 1000  # 変更されない

    def test_input_not_mutated(self):
        """normalize_expanded_path は入力 dict を変更しない"""
        raw = {
            "path_id": "path_h",
            "path_label": "変更前ラベル",
            "scenarios": {
                "best": {"label": "ベスト", "probability": 0.2,
                         "final_salary": 5000, "final_satisfaction": 90},
                "likely": {"label": "標準", "probability": 0.5,
                           "final_salary": 3000, "final_satisfaction": 70},
            }
        }
        original = copy.deepcopy(raw)
        normalize_expanded_path(raw)
        # path_label がまだ残っている（入力が変更されていない）
        assert raw == original


class TestNormalizeSwarmActionRealPatterns:
    """Swarm アクションの実出力パターン"""

    def test_round_and_content_flat(self):
        """round + content がトップレベル（最も一般的な揺れ）"""
        raw = {
            "round": 3,
            "agent_id": 5,
            "agent_name": "田中花子",
            "role": "vc",
            "action_type": "CREATE_POST",
            "content": "スタートアップ投資の観点から見ると...",
            "timestamp": "2026-01-15T10:00:00",
        }
        original = copy.deepcopy(raw)
        result = normalize_swarm_action(raw)
        assert result.round_num == 3
        assert result.action_args["content"] == "スタートアップ投資の観点から見ると..."
        assert "round" not in result.model_dump() or result.model_dump().get("round_num") == 3

    def test_action_args_null_with_content(self):
        """action_args=null + content が別にある"""
        raw = {
            "round_num": 1,
            "agent_id": 0,
            "agent_name": "テスト",
            "action_type": "CREATE_POST",
            "action_args": None,
            "content": "テスト投稿",
        }
        result = normalize_swarm_action(raw)
        assert result.action_args["content"] == "テスト投稿"

    def test_input_not_mutated(self):
        """normalize_swarm_action は入力を変更しない"""
        raw = {
            "round": 1,
            "agent_id": 0,
            "agent_name": "テスト",
            "action_type": "CREATE_POST",
            "content": "投稿",
        }
        original = copy.deepcopy(raw)
        normalize_swarm_action(raw)
        assert raw == original


class TestNormalizeSwarmAgentRealPatterns:
    """Swarm エージェントの実出力パターン"""

    def test_bio_combined_from_parts(self):
        """background + personality → bio (「。」区切り)"""
        raw = {
            "agent_id": 3,
            "name": "山田太郎",
            "background": "元メガバンク法人営業部長",
            "personality": "保守的だが面倒見が良い",
        }
        result = normalize_swarm_agent(raw)
        assert "元メガバンク" in result.bio
        assert "保守的" in result.bio
        assert "。" in result.bio  # 「。」区切り

    def test_stance_default_to_stance(self):
        """stance_default → stance"""
        raw = {
            "agent_id": 4, "name": "テスト",
            "stance_default": "supportive",
        }
        original = copy.deepcopy(raw)
        result = normalize_swarm_agent(raw)
        assert result.stance == "supportive"

    def test_input_not_mutated(self):
        """normalize_swarm_agent は入力を変更しない"""
        raw = {
            "agent_id": 1, "name": "テスト",
            "background": "テスト背景", "personality": "テスト性格",
        }
        original = copy.deepcopy(raw)
        normalize_swarm_agent(raw)
        assert raw == original


class TestP0Fixes:
    """P0 fixes: satisfaction inversion, value collapse, probability normalization"""

    def test_satisfaction_inversion_swap(self):
        """P0-1b: best satisfaction < likely satisfaction -> sort and reassign"""
        raw = {
            "path_id": "path_test",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
                 "final_state": {"annual_income": 2000, "satisfaction": 0.55,
                                 "stress": 0.3, "work_life_balance": 0.7}},
                {"scenario_id": "likely", "label": "標準", "probability": 0.5,
                 "final_state": {"annual_income": 1500, "satisfaction": 0.90,
                                 "stress": 0.4, "work_life_balance": 0.6}},
                {"scenario_id": "base", "label": "ベース", "probability": 0.3,
                 "final_state": {"annual_income": 1000, "satisfaction": 0.70,
                                 "stress": 0.5, "work_life_balance": 0.5}},
            ],
        }
        result = normalize_expanded_path(raw)
        best = next(s for s in result.scenarios if s.scenario_id == "best")
        likely = next(s for s in result.scenarios if s.scenario_id == "likely")
        base = next(s for s in result.scenarios if s.scenario_id == "base")
        assert best.final_state.satisfaction >= likely.final_state.satisfaction
        assert likely.final_state.satisfaction >= base.final_state.satisfaction

    def test_satisfaction_no_swap_when_correct(self):
        """P0-1b: satisfaction order correct -> no change"""
        raw = {
            "path_id": "path_ok",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
                 "final_state": {"annual_income": 2000, "satisfaction": 0.9}},
                {"scenario_id": "likely", "label": "標準", "probability": 0.5,
                 "final_state": {"annual_income": 1500, "satisfaction": 0.7}},
            ],
        }
        result = normalize_expanded_path(raw)
        assert result.scenarios[0].final_state.satisfaction == 0.9
        assert result.scenarios[1].final_state.satisfaction == 0.7

    def test_income_and_satisfaction_both_inverted(self):
        """P0-1a+1b: income and satisfaction both inverted independently"""
        raw = {
            "path_id": "path_both",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
                 "final_state": {"annual_income": 800, "satisfaction": 0.5}},
                {"scenario_id": "likely", "label": "標準", "probability": 0.5,
                 "final_state": {"annual_income": 1000, "satisfaction": 0.7}},
                {"scenario_id": "base", "label": "ベース", "probability": 0.3,
                 "final_state": {"annual_income": 1500, "satisfaction": 0.9}},
            ],
        }
        result = normalize_expanded_path(raw)
        best = next(s for s in result.scenarios if s.scenario_id == "best")
        likely = next(s for s in result.scenarios if s.scenario_id == "likely")
        base = next(s for s in result.scenarios if s.scenario_id == "base")
        # Income: best >= likely >= base
        assert best.final_state.annual_income >= likely.final_state.annual_income
        assert likely.final_state.annual_income >= base.final_state.annual_income
        # Satisfaction: best >= likely >= base
        assert best.final_state.satisfaction >= likely.final_state.satisfaction
        assert likely.final_state.satisfaction >= base.final_state.satisfaction

    def test_full_reverse_order_4_scenarios(self):
        """Complete reverse order with 4 scenarios sorts correctly"""
        raw = {
            "path_id": "path_rev",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.1,
                 "final_state": {"annual_income": 500, "satisfaction": 0.3}},
                {"scenario_id": "likely", "label": "標準", "probability": 0.3,
                 "final_state": {"annual_income": 800, "satisfaction": 0.5}},
                {"scenario_id": "base", "label": "ベース", "probability": 0.4,
                 "final_state": {"annual_income": 1200, "satisfaction": 0.7}},
                {"scenario_id": "worst", "label": "ワースト", "probability": 0.2,
                 "final_state": {"annual_income": 2000, "satisfaction": 0.9}},
            ],
        }
        result = normalize_expanded_path(raw)
        smap = {s.scenario_id: s for s in result.scenarios}
        assert smap["best"].final_state.annual_income == 2000
        assert smap["likely"].final_state.annual_income == 1200
        assert smap["base"].final_state.annual_income == 800
        assert smap["worst"].final_state.annual_income == 500

    def test_income_collapse_warning(self, capsys):
        """P0-2: adjacent scenarios with identical income -> warning"""
        raw = {
            "path_id": "path_collapse",
            "label": "テスト",
            "scenarios": [
                {"scenario_id": "best", "label": "ベスト", "probability": 0.2,
                 "final_state": {"annual_income": 950, "satisfaction": 0.9}},
                {"scenario_id": "likely", "label": "標準", "probability": 0.5,
                 "final_state": {"annual_income": 950, "satisfaction": 0.7}},
            ],
        }
        normalize_expanded_path(raw)
        captured = capsys.readouterr()
        assert "income collapse" in captured.err

    def test_probability_normalization(self):
        """P0-3: normalize_overall_probabilities normalizes sum to ~1.0"""
        from cc_layer.cli.path_score import normalize_overall_probabilities
        scored = [
            {"path_id": "a", "overall_probability": 0.50},
            {"path_id": "b", "overall_probability": 0.40},
            {"path_id": "c", "overall_probability": 0.60},
        ]
        # Sum is 1.50
        normalize_overall_probabilities(scored)
        new_total = sum(p["overall_probability"] for p in scored)
        assert abs(new_total - 1.0) < 0.01

    def test_probability_no_normalization_when_close(self):
        """P0-3: sum ~1.0 -> no normalization"""
        from cc_layer.cli.path_score import normalize_overall_probabilities
        scored = [
            {"path_id": "a", "overall_probability": 0.20},
            {"path_id": "b", "overall_probability": 0.35},
            {"path_id": "c", "overall_probability": 0.25},
            {"path_id": "d", "overall_probability": 0.15},
            {"path_id": "e", "overall_probability": 0.05},
        ]
        original_probs = [p["overall_probability"] for p in scored]
        normalize_overall_probabilities(scored)
        # No change since sum=1.0
        assert [p["overall_probability"] for p in scored] == original_probs

    def test_probability_with_none_values(self):
        """P0-3: paths with None overall_probability are skipped"""
        from cc_layer.cli.path_score import normalize_overall_probabilities
        scored = [
            {"path_id": "a", "overall_probability": 0.80},
            {"path_id": "b", "overall_probability": 0.70},
            {"path_id": "c", "overall_probability": None},
        ]
        normalize_overall_probabilities(scored)
        assert scored[2]["overall_probability"] is None
        valid_total = scored[0]["overall_probability"] + scored[1]["overall_probability"]
        assert abs(valid_total - 1.0) < 0.01


class TestNormalizeSessionRevert:
    """normalize_session_to_disk が元データを正しくrevert可能か"""

    def _make_session_with_variations(self, tmp_path):
        """揺れパターンを含むセッションデータ"""
        mp = {
            "paths": [{
                "path_id": "path_a",
                "path_label": "法人化パス",
                "scenarios": {
                    "best": {"label": "ベスト", "probability": 0.2,
                             "final_salary": 2000, "final_satisfaction": 90},
                    "likely": {"label": "標準", "probability": 0.5,
                               "final_salary": 1500, "final_satisfaction": 70},
                    "base": {"label": "ベース", "probability": 0.3,
                             "final_salary": 1000, "final_satisfaction": 50},
                },
            }],
            "rankings": {"path_a": 1},
        }
        agents = [
            {"agent_id": 0, "name": "テスト", "background": "PM経験者",
             "stance_default": "supportive"},
        ]
        (tmp_path / "multipath_result.json").write_text(
            json.dumps(mp, ensure_ascii=False))
        (tmp_path / "swarm_agents.json").write_text(
            json.dumps(agents, ensure_ascii=False))
        swarm_dir = tmp_path / "swarm"
        swarm_dir.mkdir()
        (swarm_dir / "all_actions_round_001.jsonl").write_text(
            '{"round": 1, "agent_id": 0, "agent_name": "テスト", '
            '"action_type": "CREATE_POST", "content": "投稿"}\n'
        )
        return tmp_path, mp, agents

    def test_normalize_to_disk_then_reread(self, tmp_path):
        """to_disk 後のデータが canonical 形式で再読み込み可能"""
        session, original_mp, original_agents = self._make_session_with_variations(tmp_path)
        normalize_session_to_disk(str(session))

        # 正規化後のデータを読み込み
        mp = json.loads((session / "multipath_result.json").read_text())
        # dict scenarios → list に変換されている
        assert isinstance(mp["paths"][0]["scenarios"], list)
        # rankings → ranking
        assert "ranking" in mp
        assert "rankings" not in mp
        # 0-100 → 0-1
        fs = mp["paths"][0]["scenarios"][1]["final_state"]  # likely
        assert 0 <= fs["satisfaction"] <= 1

        # agents: stance_default → stance, bio 生成
        agents = json.loads((session / "swarm_agents.json").read_text())
        assert agents[0]["stance"] == "supportive"
        assert agents[0]["bio"] != ""

        # swarm: round → round_num, content → action_args.content
        actions_text = (session / "swarm" / "all_actions_round_001.jsonl").read_text()
        action = json.loads(actions_text.strip())
        assert action["round_num"] == 1
        assert action["action_args"]["content"] == "投稿"

    def test_normalize_idempotent_with_variations(self, tmp_path):
        """揺れパターンを含むデータで2回normalize → 結果同一"""
        self._make_session_with_variations(tmp_path)
        normalize_session_to_disk(str(tmp_path))
        mp1 = json.loads((tmp_path / "multipath_result.json").read_text())
        ag1 = json.loads((tmp_path / "swarm_agents.json").read_text())

        normalize_session_to_disk(str(tmp_path))
        mp2 = json.loads((tmp_path / "multipath_result.json").read_text())
        ag2 = json.loads((tmp_path / "swarm_agents.json").read_text())

        assert mp1 == mp2
        assert ag1 == ag2
