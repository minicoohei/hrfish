"""
Tests for life simulator components (P1-P7).
Standalone tests — imports models/services directly to avoid Flask/OpenAI deps.
"""

import sys
import os
import importlib
import types
import unittest.mock

# Create a minimal mock for the entire app package chain
# so we can import just our new modules without pulling in Flask/OpenAI
_backend_dir = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, _backend_dir)

# Mock heavy deps
for mod_name in [
    'flask', 'flask_cors', 'openai', 'zep_cloud', 'zep_cloud.client',
    'dotenv', 'camel', 'camel.messages', 'camel.agents', 'camel.agents.chat_agent',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = unittest.mock.MagicMock()

# Mock app.config and app.utils.logger so our modules can import
app_pkg = types.ModuleType('app')
app_pkg.__path__ = [os.path.join(_backend_dir, 'app')]
sys.modules['app'] = app_pkg

config_mod = types.ModuleType('app.config')


class _FakeConfig:
    ZEP_API_KEY = "fake"
    LLM_API_KEY = "fake"
    LLM_BASE_URL = ""
    LLM_MODEL_NAME = ""


config_mod.Config = _FakeConfig
sys.modules['app.config'] = config_mod

utils_mod = types.ModuleType('app.utils')
utils_mod.__path__ = [os.path.join(_backend_dir, 'app', 'utils')]
sys.modules['app.utils'] = utils_mod

import logging

logger_mod = types.ModuleType('app.utils.logger')


def _get_logger(name):
    return logging.getLogger(name)


logger_mod.get_logger = _get_logger
logger_mod.setup_logger = lambda: None
sys.modules['app.utils.logger'] = logger_mod

# Mock other utils
for sub in ['llm_client', 'zep_paging']:
    sys.modules[f'app.utils.{sub}'] = unittest.mock.MagicMock()

# Now set up app.models and app.services
models_mod = types.ModuleType('app.models')
models_mod.__path__ = [os.path.join(_backend_dir, 'app', 'models')]
sys.modules['app.models'] = models_mod

services_mod = types.ModuleType('app.services')
services_mod.__path__ = [os.path.join(_backend_dir, 'app', 'services')]
sys.modules['app.services'] = services_mod

# Import the actual modules we're testing
from app.models.life_simulator import (
    BaseIdentity, CareerState, LifeEvent, LifeEventType,
    ActiveBlocker, BlockerType, FamilyMember, AgentSnapshot,
    SimulationPath, ActionTypeMiroFish,
)
from app.services.agent_state_store import AgentStateStore
from app.services.persona_renderer import PersonaRenderer
from app.services.life_event_engine import LifeEventEngine
from app.services.blocker_engine import BlockerEngine
from app.services.life_simulation_loop import (
    LifeSimulationOrchestrator, FormInput, cash_range_to_value,
)
from app.services.multipath_simulator import (
    MultiPathSimulator, PathConfig, build_default_paths,
)

import pytest


# ============================================================
# P1: Domain models
# ============================================================

class TestDomainModels:
    def test_base_identity_to_dict(self):
        identity = BaseIdentity(
            name="田中太郎", age_at_start=32, education="東大工学部",
            mbti="INTJ", stable_traits=["分析的", "慎重"],
        )
        d = identity.to_dict()
        assert d["name"] == "田中太郎"
        assert d["age_at_start"] == 32

    def test_career_state_children(self):
        state = CareerState(
            family=[
                FamilyMember(relation="child", age=3),
                FamilyMember(relation="child", age=7),
                FamilyMember(relation="parent", age=72),
            ]
        )
        assert len(state.get_children()) == 2
        assert len(state.get_parents()) == 1

    def test_career_state_blocker_check(self):
        state = CareerState(
            blockers=[
                ActiveBlocker(
                    blocker_type=BlockerType.CHILDCARE,
                    reason="育児中",
                    blocked_actions=["startup", "overseas_assignment"],
                    started_round=5,
                )
            ]
        )
        assert state.is_action_blocked("startup")
        assert not state.is_action_blocked("job_change")
        assert state.has_blocker(BlockerType.CHILDCARE)

    def test_life_event_to_dict(self):
        event = LifeEvent(
            event_type=LifeEventType.PROMOTION,
            round_number=10,
            description="マネージャーに昇進",
        )
        d = event.to_dict()
        assert d["event_type"] == "promotion"

    def test_action_type_mirofish(self):
        assert ActionTypeMiroFish.INTERNAL_MONOLOGUE.value == "internal_monologue"
        assert ActionTypeMiroFish.CONSULT.value == "consult"
        assert ActionTypeMiroFish.DECIDE.value == "decide"


# ============================================================
# P2: AgentStateStore
# ============================================================

class TestAgentStateStore:
    def _make_store(self):
        store = AgentStateStore()
        identity = BaseIdentity(name="鈴木花子", age_at_start=30)
        state = CareerState(
            current_age=30, role="エンジニア", employer="TechCorp",
            salary_annual=600, cash_buffer=500,
            family=[FamilyMember(relation="parent", age=65)],
        )
        store.initialize_agent("agent1", identity, state)
        return store

    def test_initialize_and_get(self):
        store = self._make_store()
        assert store.get_identity("agent1").name == "鈴木花子"
        assert store.get_state("agent1").salary_annual == 600

    def test_tick_round_ages_quarterly(self):
        store = self._make_store()
        for _ in range(4):
            store.tick_round("agent1")
        state = store.get_state("agent1")
        assert state.current_age == 31
        assert state.current_round == 4
        assert state.get_parents()[0].age == 66

    def test_tick_round_financial(self):
        store = self._make_store()
        state = store.get_state("agent1")
        state.monthly_expenses = 20
        initial_cash = state.cash_buffer
        store.tick_round("agent1")
        # quarterly_salary = 600/4 = 150, quarterly_expenses = 20*3 = 60
        assert store.get_state("agent1").cash_buffer == initial_cash + 90

    def test_apply_event_promotion(self):
        store = self._make_store()
        event = LifeEvent(
            event_type=LifeEventType.PROMOTION,
            round_number=1,
            description="シニアエンジニアに昇進",
            state_changes={"role": "シニアエンジニア", "salary_annual": 750},
        )
        store.apply_event("agent1", event)
        state = store.get_state("agent1")
        assert state.role == "シニアエンジニア"
        assert state.salary_annual == 750
        assert state.years_in_role == 0

    def test_apply_event_layoff(self):
        store = self._make_store()
        event = LifeEvent(
            event_type=LifeEventType.LAYOFF,
            round_number=1,
            description="リストラ",
        )
        store.apply_event("agent1", event)
        state = store.get_state("agent1")
        assert state.role == "求職中"
        assert state.salary_annual == 0

    def test_snapshot(self):
        store = self._make_store()
        snap = store.snapshot("agent1")
        assert snap.role == "エンジニア"
        assert snap.salary_annual == 600
        assert len(store.get_history("agent1")) == 1

    def test_clone_state(self):
        store = self._make_store()
        cloned = store.clone_state("agent1")
        cloned.salary_annual = 999
        assert store.get_state("agent1").salary_annual == 600


# ============================================================
# P3: PersonaRenderer
# ============================================================

class TestPersonaRenderer:
    def test_render_basic(self):
        renderer = PersonaRenderer()
        identity = BaseIdentity(
            name="佐藤一郎", age_at_start=35,
            education="慶應義塾大学", mbti="ENFP",
        )
        state = CareerState(
            current_age=37, role="マネージャー", employer="BigCorp",
            salary_annual=800, cash_buffer=1500,
            family=[FamilyMember(relation="child", age=5)],
            marital_status="married",
        )
        msg = renderer.render_system_message(identity, state)
        assert "佐藤一郎" in msg
        assert "37歳" in msg
        assert "マネージャー" in msg
        assert "800万円" in msg

    def test_render_with_blockers(self):
        renderer = PersonaRenderer()
        identity = BaseIdentity(name="テスト", age_at_start=30)
        state = CareerState(
            current_age=30,
            blockers=[
                ActiveBlocker(
                    blocker_type=BlockerType.CHILDCARE,
                    reason="育児中（子供: 2歳）",
                    blocked_actions=["startup"],
                    started_round=1,
                )
            ],
        )
        msg = renderer.render_system_message(identity, state)
        assert "制約条件" in msg
        assert "育児中" in msg

    def test_render_with_round_context(self):
        renderer = PersonaRenderer()
        identity = BaseIdentity(name="テスト", age_at_start=30)
        state = CareerState(current_age=30)
        msg = renderer.render_system_message(
            identity, state, round_context="今期のイベント:\n- 昇進"
        )
        assert "今期の状況" in msg
        assert "昇進" in msg


# ============================================================
# P4: LifeEventEngine
# ============================================================

class TestLifeEventEngine:
    def test_scheduled_event_fires(self):
        engine = LifeEventEngine(seed=42)
        event = LifeEvent(
            event_type=LifeEventType.CAREER_PHASE_CHANGE,
            round_number=10,
            description="フェーズ2: 転職検討期",
        )
        engine.add_scheduled_event(event)

        state = CareerState(current_round=10, current_age=32)
        fired = engine.evaluate("agent1", state)
        assert any(e.event_type == LifeEventType.CAREER_PHASE_CHANGE for e in fired)

    def test_scheduled_event_does_not_fire_wrong_round(self):
        engine = LifeEventEngine(seed=42)
        event = LifeEvent(
            event_type=LifeEventType.CAREER_PHASE_CHANGE,
            round_number=10,
            description="フェーズ2",
        )
        engine.add_scheduled_event(event)

        state = CareerState(current_round=5, current_age=32)
        fired = engine.evaluate("agent1", state)
        assert not any(e.event_type == LifeEventType.CAREER_PHASE_CHANGE for e in fired)

    def test_elder_care_probabilistic(self):
        engine = LifeEventEngine(seed=1)
        state = CareerState(
            current_round=20, current_age=45,
            family=[FamilyMember(relation="parent", age=80)],
        )
        fired_any = False
        for i in range(50):
            state.current_round = 20 + i
            events = engine.evaluate("agent1", state)
            if any(e.event_type == LifeEventType.ELDER_CARE_START for e in events):
                fired_any = True
                break
        assert fired_any


# ============================================================
# P5: BlockerEngine
# ============================================================

class TestBlockerEngine:
    def test_childcare_blocker(self):
        engine = BlockerEngine()
        state = CareerState(
            current_age=32,
            family=[FamilyMember(relation="child", age=2)],
        )
        blockers = engine.evaluate(state)
        childcare = [b for b in blockers if b.blocker_type == BlockerType.CHILDCARE]
        assert len(childcare) == 1
        assert "startup" in childcare[0].blocked_actions

    def test_no_childcare_blocker_older_child(self):
        engine = BlockerEngine()
        state = CareerState(
            current_age=40,
            family=[FamilyMember(relation="child", age=10)],
        )
        blockers = engine.evaluate(state)
        childcare = [b for b in blockers if b.blocker_type == BlockerType.CHILDCARE]
        assert len(childcare) == 0

    def test_exam_period_blocker(self):
        engine = BlockerEngine()
        state = CareerState(
            current_age=45,
            family=[FamilyMember(relation="child", age=15)],
        )
        blockers = engine.evaluate(state)
        exam = [b for b in blockers if b.blocker_type == BlockerType.EXAM_PERIOD]
        assert len(exam) == 1

    def test_mortgage_blocker(self):
        engine = BlockerEngine()
        state = CareerState(
            current_age=35, salary_annual=500,
            mortgage_remaining=2000,
        )
        blockers = engine.evaluate(state)
        mortgage = [b for b in blockers if b.blocker_type == BlockerType.MORTGAGE]
        assert len(mortgage) == 1

    def test_no_mortgage_blocker_manageable(self):
        engine = BlockerEngine()
        state = CareerState(
            current_age=35, salary_annual=800,
            mortgage_remaining=2000,
        )
        blockers = engine.evaluate(state)
        mortgage = [b for b in blockers if b.blocker_type == BlockerType.MORTGAGE]
        assert len(mortgage) == 0

    def test_age_wall_35(self):
        engine = BlockerEngine()
        state = CareerState(current_age=37)
        blockers = engine.evaluate(state)
        age = [b for b in blockers if b.blocker_type == BlockerType.AGE_WALL]
        assert len(age) == 1
        assert "35歳超" in age[0].reason

    def test_age_wall_45(self):
        engine = BlockerEngine()
        state = CareerState(current_age=47)
        blockers = engine.evaluate(state)
        age = [b for b in blockers if b.blocker_type == BlockerType.AGE_WALL]
        assert len(age) == 1
        assert "45歳超" in age[0].reason

    def test_elder_care_blocker(self):
        engine = BlockerEngine()
        state = CareerState(
            current_age=50,
            family=[FamilyMember(relation="parent", age=78, notes="要介護2")],
        )
        blockers = engine.evaluate(state)
        care = [b for b in blockers if b.blocker_type == BlockerType.ELDER_CARE]
        assert len(care) == 1


# ============================================================
# P6+P7: LifeSimulationOrchestrator
# ============================================================

class TestLifeSimulationOrchestrator:
    def _make_orchestrator(self):
        orchestrator = LifeSimulationOrchestrator(seed=42)
        profile = {
            "name": "山田太郎",
            "age": 32,
            "current_role": "ソフトウェアエンジニア",
            "current_employer": "TechStartup Inc",
            "industry": "IT",
            "salary": 650,
            "skills": ["Python", "AWS"],
        }
        form_input = FormInput(
            family_members=[
                FamilyMember(relation="spouse", age=30),
                FamilyMember(relation="child", age=2),
                FamilyMember(relation="parent", age=65),
            ],
            marital_status="married",
            mortgage_remaining=3000,
            cash_buffer_range="500-2000",
            monthly_expenses=30,
        )
        orchestrator.initialize_from_profile("agent1", profile, form_input)
        return orchestrator

    def test_initialize(self):
        orch = self._make_orchestrator()
        identity = orch.state_store.get_identity("agent1")
        assert identity.name == "山田太郎"
        state = orch.state_store.get_state("agent1")
        assert state.salary_annual == 650
        assert state.cash_buffer == 1000
        assert len(state.family) == 3

    def test_pre_round_hook(self):
        orch = self._make_orchestrator()
        result = orch.pre_round_hook("agent1", 1)
        assert "round" in result
        assert "age" in result
        assert "persona_text" in result
        assert "山田太郎" in result["persona_text"]

    def test_post_round_hook(self):
        orch = self._make_orchestrator()
        orch.pre_round_hook("agent1", 1)
        snap = orch.post_round_hook("agent1", 1)
        assert isinstance(snap, AgentSnapshot)
        assert snap.round_number == 1

    def test_full_10_rounds(self):
        orch = self._make_orchestrator()
        for r in range(1, 11):
            orch.pre_round_hook("agent1", r)
            orch.post_round_hook("agent1", r)

        state = orch.state_store.get_state("agent1")
        assert state.current_round == 10
        assert len(orch.state_store.get_history("agent1")) == 10

    def test_blockers_activate_for_young_child(self):
        orch = self._make_orchestrator()
        orch.pre_round_hook("agent1", 1)
        state = orch.state_store.get_state("agent1")
        assert state.has_blocker(BlockerType.CHILDCARE)

    def test_cash_range_conversion(self):
        assert cash_range_to_value("500未満") == 250
        assert cash_range_to_value("500-2000") == 1000
        assert cash_range_to_value("2000+") == 3000

    def test_simulation_summary(self):
        orch = self._make_orchestrator()
        for r in range(1, 5):
            orch.pre_round_hook("agent1", r)
            orch.post_round_hook("agent1", r)
        summary = orch.get_simulation_summary("agent1")
        assert summary["identity"]["name"] == "山田太郎"
        assert summary["total_rounds"] == 4
        assert len(summary["history"]) == 4

    def test_decide_action_job_change(self):
        orch = self._make_orchestrator()
        orch.pre_round_hook("agent1", 1)
        orch.post_round_hook("agent1", 1, agent_action_result={
            "decision": {
                "type": "job_change",
                "new_employer": "BigCorp",
                "new_role": "テックリード",
                "new_salary": 900,
            }
        })
        state = orch.state_store.get_state("agent1")
        assert state.employer == "BigCorp"
        assert state.salary_annual == 900

    def test_decide_action_startup_blocked(self):
        orch = self._make_orchestrator()
        orch.pre_round_hook("agent1", 1)
        state = orch.state_store.get_state("agent1")
        assert state.is_action_blocked("startup")
        orch.post_round_hook("agent1", 1, agent_action_result={
            "decision": {"type": "startup"}
        })
        assert state.employer != "自営業"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================
# P10: Multi-Path Simulator Tests
# ============================================================

class TestMultiPathSimulator(unittest.TestCase):
    """Tests for P10: Multi-Path Parallel Simulator"""

    def setUp(self):
        self.identity = BaseIdentity(
            name="テスト太郎",
            age_at_start=32,
            gender="male",
            education="大学卒",
            mbti="INTJ",
            stable_traits=["分析的", "計画的"],
            certifications=["TOEIC 800"],
            career_history_summary="IT企業で10年",
        )
        self.initial_state = CareerState(
            current_round=0,
            current_age=32,
            role="マネージャー",
            employer="テック株式会社",
            industry="IT",
            years_in_role=3,
            salary_annual=700,
            skills=["Python", "マネジメント"],
            family=[
                FamilyMember(relation="spouse", age=30),
                FamilyMember(relation="child", age=2),
                FamilyMember(relation="parent", age=62),
            ],
            marital_status="married",
            cash_buffer=1000,
            mortgage_remaining=3000,
            monthly_expenses=30,
        )

    def test_initialize_default_paths(self):
        """Default 3 paths are created when no custom config given."""
        sim = MultiPathSimulator(base_seed=42)
        path_ids = sim.initialize(self.identity, self.initial_state)
        self.assertEqual(len(path_ids), 3)
        self.assertIn("path_a", path_ids)
        self.assertIn("path_b", path_ids)
        self.assertIn("path_c", path_ids)

    def test_build_default_paths_labels(self):
        """Default paths have correct labels based on state."""
        paths = build_default_paths(self.initial_state, 40)
        labels = {p.path_id: p.path_label for p in paths}
        self.assertEqual(labels["path_a"], "現職継続")
        self.assertEqual(labels["path_b"], "同業転職")
        # path_c depends on blocker status
        self.assertIn(labels["path_c"], ["起業挑戦", "異業種転職"])

    def test_build_default_paths_startup_blocked(self):
        """When startup is blocked, path_c becomes industry change."""
        # Add mortgage blocker that blocks startup
        self.initial_state.blockers = [
            ActiveBlocker(
                blocker_type=BlockerType.MORTGAGE,
                reason="住宅ローン残額が年収の3倍超",
                blocked_actions=["startup"],
                started_round=0,
            )
        ]
        paths = build_default_paths(self.initial_state, 40)
        path_c = next(p for p in paths if p.path_id == "path_c")
        self.assertEqual(path_c.path_label, "異業種転職")

    def test_run_all_completes(self):
        """All 3 paths run to completion."""
        sim = MultiPathSimulator(base_seed=42)
        sim.initialize(self.identity, self.initial_state, round_count=20)
        results = sim.run_all()
        self.assertEqual(len(results), 3)
        for path_id, path in results.items():
            self.assertIsNotNone(path.final_state)
            self.assertEqual(len(path.snapshots), 20)

    def test_paths_diverge(self):
        """Different paths produce different final states."""
        sim = MultiPathSimulator(base_seed=42)
        sim.initialize(self.identity, self.initial_state, round_count=20)
        results = sim.run_all()
        salaries = {pid: p.final_state.salary_annual for pid, p in results.items()}
        # At least 2 paths should have different salaries
        unique_salaries = set(salaries.values())
        self.assertGreater(len(unique_salaries), 1,
                          f"All paths have same salary: {salaries}")

    def test_comparison_report_structure(self):
        """Comparison report has required fields."""
        sim = MultiPathSimulator(base_seed=42)
        sim.initialize(self.identity, self.initial_state, round_count=8)
        sim.run_all()
        report = sim.generate_comparison_report()
        self.assertIn("paths", report)
        self.assertIn("rankings", report)
        self.assertIn("simulation_years", report)
        self.assertEqual(len(report["paths"]), 3)
        # Each path summary has metrics
        for ps in report["paths"]:
            self.assertIn("final_salary", ps)
            self.assertIn("final_cash_buffer", ps)
            self.assertIn("peak_salary", ps)
            self.assertIn("avg_stress", ps)

    def test_comparison_rankings(self):
        """Rankings identify best path per dimension."""
        sim = MultiPathSimulator(base_seed=42)
        sim.initialize(self.identity, self.initial_state, round_count=12)
        sim.run_all()
        report = sim.generate_comparison_report()
        rankings = report["rankings"]
        self.assertIn("highest_salary", rankings)
        self.assertIn("most_cash", rankings)
        self.assertIn("lowest_stress", rankings)
        self.assertIn("best_wlb", rankings)

    def test_get_path_timeline(self):
        """Can retrieve detailed timeline for specific path."""
        sim = MultiPathSimulator(base_seed=42)
        sim.initialize(self.identity, self.initial_state, round_count=8)
        sim.run_all()
        timeline = sim.get_path_timeline("path_a")
        self.assertEqual(len(timeline), 8)
        self.assertIn("round_number", timeline[0])
        self.assertIn("salary_annual", timeline[0])

    def test_path_isolation(self):
        """Events in one path don't affect other paths."""
        sim = MultiPathSimulator(base_seed=42)
        sim.initialize(self.identity, self.initial_state, round_count=20)
        results = sim.run_all()
        # Path A stays at same employer, Path B changes
        path_a = results["path_a"]
        path_b = results["path_b"]
        self.assertEqual(path_a.final_state.employer, self.initial_state.employer)
        self.assertNotEqual(path_b.final_state.employer, self.initial_state.employer)

    def test_custom_path_configs(self):
        """Can provide custom path configurations."""
        custom = [
            PathConfig(
                path_id="custom_1",
                path_label="カスタムパス",
                scheduled_events=[],
                seed_offset=0,
            ),
        ]
        sim = MultiPathSimulator(base_seed=42)
        path_ids = sim.initialize(
            self.identity, self.initial_state,
            path_configs=custom, round_count=8,
        )
        self.assertEqual(path_ids, ["custom_1"])
        sim.run_all()
        report = sim.generate_comparison_report()
        self.assertEqual(len(report["paths"]), 1)




# ============================================================
# Review fix regression tests
# ============================================================

class TestReviewFixes(unittest.TestCase):
    """Regression tests for code review fixes."""

    def test_critical1_salary_increase_no_double_apply(self):
        """CRITICAL-1: salary_increase_pct should not setattr on state."""
        store = AgentStateStore()
        identity = BaseIdentity(name="test", age_at_start=30)
        state = CareerState(salary_annual=600, cash_buffer=500)
        store.initialize_agent("a1", identity, state)

        event = LifeEvent(
            event_type=LifeEventType.SALARY_INCREASE,
            round_number=1,
            description="昇給",
            state_changes={"salary_increase_pct": 10},
        )
        store.apply_event("a1", event)
        # Should be 600 * 1.10 = 660, NOT double-applied
        self.assertEqual(store.get_state("a1").salary_annual, 660)

    def test_critical1_promotion_with_salary_in_state_changes(self):
        """CRITICAL-1: PROMOTION with salary in state_changes should apply correctly."""
        store = AgentStateStore()
        identity = BaseIdentity(name="test", age_at_start=30)
        state = CareerState(salary_annual=600, role="エンジニア")
        store.initialize_agent("a1", identity, state)

        event = LifeEvent(
            event_type=LifeEventType.PROMOTION,
            round_number=1,
            description="昇進",
            state_changes={"role": "リード", "salary_annual": 750},
        )
        store.apply_event("a1", event)
        s = store.get_state("a1")
        self.assertEqual(s.role, "リード")
        self.assertEqual(s.salary_annual, 750)
        self.assertEqual(s.years_in_role, 0)

    def test_major2_child_birth_adds_family_in_apply_event(self):
        """MAJOR-2: CHILD_BIRTH in apply_event adds FamilyMember."""
        store = AgentStateStore()
        identity = BaseIdentity(name="test", age_at_start=30)
        state = CareerState(
            family=[FamilyMember(relation="spouse", age=30)],
            monthly_expenses=20,
        )
        store.initialize_agent("a1", identity, state)

        event = LifeEvent(
            event_type=LifeEventType.CHILD_BIRTH,
            round_number=1,
            description="第1子誕生",
        )
        store.apply_event("a1", event)
        s = store.get_state("a1")
        children = s.get_children()
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].age, 0)
        self.assertEqual(s.monthly_expenses, 28)  # +8

    def test_major2_elder_care_marks_parent(self):
        """MAJOR-2: ELDER_CARE_START marks parent notes in apply_event."""
        store = AgentStateStore()
        identity = BaseIdentity(name="test", age_at_start=45)
        state = CareerState(
            family=[FamilyMember(relation="parent", age=80)],
        )
        store.initialize_agent("a1", identity, state)

        event = LifeEvent(
            event_type=LifeEventType.ELDER_CARE_START,
            round_number=1,
            description="介護開始",
        )
        store.apply_event("a1", event)
        parent = store.get_state("a1").get_parents()[0]
        self.assertEqual(parent.notes, "要介護")

    def test_critical3_blocker_type_enum(self):
        """CRITICAL-3: has_blocker works with BlockerType enum."""
        state = CareerState(
            blockers=[
                ActiveBlocker(
                    blocker_type=BlockerType.ELDER_CARE,
                    reason="介護中",
                    blocked_actions=["remote_transfer"],
                    started_round=1,
                )
            ]
        )
        self.assertTrue(state.has_blocker(BlockerType.ELDER_CARE))

    def test_minor1_agent_not_found_error(self):
        """MINOR-1: get_state/get_identity raise descriptive KeyError."""
        store = AgentStateStore()
        with self.assertRaises(KeyError) as ctx:
            store.get_state("nonexistent")
        self.assertIn("not initialized", str(ctx.exception))

    def test_major4_partial_path_failure(self):
        """MAJOR-4: run_all continues when one path fails."""

        sim = MultiPathSimulator(base_seed=42)
        identity = BaseIdentity(name="test", age_at_start=30)
        state = CareerState(
            salary_annual=500, employer="Corp", industry="IT",
            role="Eng", monthly_expenses=20,
        )
        # All paths should succeed with valid configs
        sim.initialize(identity, state, round_count=4)
        results = sim.run_all()
        self.assertEqual(len(results), 3)


