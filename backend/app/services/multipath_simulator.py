"""
P10: Multi-Path Parallel Simulator

Runs 3 career paths simultaneously from the same starting state,
each with different scheduled career events, and produces a comparison report.
"""

import os
from typing import Dict, Any, List, Optional
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from ..models.life_simulator import (
    BaseIdentity, CareerState, LifeEvent, LifeEventType,
    AgentSnapshot, SimulationPath,
)
from .agent_state_store import AgentStateStore
from .persona_renderer import PersonaRenderer
from .life_event_engine import LifeEventEngine
from .blocker_engine import BlockerEngine
from ..utils.logger import get_logger

logger = get_logger('mirofish.multipath_simulator')


@dataclass
class PathConfig:
    """Configuration for a single simulation path."""
    path_id: str
    path_label: str
    scheduled_events: List[LifeEvent] = field(default_factory=list)
    seed_offset: int = 0


def build_default_paths(state: CareerState, round_count: int) -> List[PathConfig]:
    """
    Build 3 default career path configurations based on current state.

    Path A: 現職継続 — stay at current employer, aim for promotion
    Path B: 同業転職 — change employer within same industry
    Path C: 異業種/起業 — career change or startup attempt
    """
    mid_round = round_count // 2

    path_a = PathConfig(
        path_id="path_a",
        path_label="現職継続",
        scheduled_events=[
            LifeEvent(
                event_type=LifeEventType.PROMOTION,
                round_number=8,
                description=f"{state.employer}で昇進",
                state_changes={
                    "role": f"シニア{state.role}" if state.role else "シニアスタッフ",
                    "salary_annual": int(state.salary_annual * 1.15),
                },
            ),
            LifeEvent(
                event_type=LifeEventType.SALARY_INCREASE,
                round_number=mid_round,
                description="定期昇給",
                state_changes={"salary_increase_pct": 5},
            ),
        ],
        seed_offset=0,
    )

    path_b = PathConfig(
        path_id="path_b",
        path_label="同業転職",
        scheduled_events=[
            LifeEvent(
                event_type=LifeEventType.JOB_CHANGE,
                round_number=4,
                description=f"{state.industry}業界内で転職",
                state_changes={
                    "employer": f"{state.industry}大手企業",
                    "role": state.role,
                    "salary_annual": int(state.salary_annual * 1.2),
                    "industry": state.industry,
                },
            ),
        ],
        seed_offset=100,
    )

    path_c_label = "起業挑戦" if not state.is_action_blocked("startup") else "異業種転職"
    if not state.is_action_blocked("startup"):
        path_c_events = [
            LifeEvent(
                event_type=LifeEventType.JOB_CHANGE,
                round_number=4,
                description="起業を決断",
                state_changes={
                    "employer": "自営業",
                    "role": "代表",
                    "salary_annual": int(state.salary_annual * 0.4),
                },
            ),
            LifeEvent(
                event_type=LifeEventType.SALARY_INCREASE,
                round_number=mid_round,
                description="事業成長による収入増",
                state_changes={"salary_increase_pct": 80},
            ),
        ]
    else:
        path_c_events = [
            LifeEvent(
                event_type=LifeEventType.JOB_CHANGE,
                round_number=4,
                description="異業種へキャリアチェンジ",
                state_changes={
                    "employer": "異業種企業",
                    "role": state.role,
                    "salary_annual": int(state.salary_annual * 0.85),
                    "industry": "IT" if state.industry != "IT" else "コンサルティング",
                },
            ),
        ]

    path_c = PathConfig(
        path_id="path_c",
        path_label=path_c_label,
        scheduled_events=path_c_events,
        seed_offset=200,
    )

    return [path_a, path_b, path_c]


class MultiPathSimulator:
    """
    Runs multiple career simulation paths from the same starting point.
    Each path has its own AgentStateStore, EventEngine, and BlockerEngine
    to ensure isolation.
    """

    def __init__(self, base_seed: Optional[int] = None):
        self.base_seed = base_seed if base_seed is not None else int.from_bytes(os.urandom(4), "big") % (2**31)
        self.paths: Dict[str, SimulationPath] = {}
        self._base_identity: Optional[BaseIdentity] = None
        self._base_state: Optional[CareerState] = None

    def initialize(
        self,
        identity: BaseIdentity,
        initial_state: CareerState,
        path_configs: Optional[List[PathConfig]] = None,
        round_count: int = 40,
    ) -> List[str]:
        """
        Initialize multi-path simulation.

        Args:
            identity: Shared immutable identity
            initial_state: Starting state (will be deep-copied per path)
            path_configs: Custom path configurations (default: 3 auto-generated)
            round_count: Total rounds to simulate (default: 40 = 10 years)

        Returns:
            List of path IDs
        """
        self._base_identity = identity
        self._base_state = initial_state

        if path_configs is None:
            path_configs = build_default_paths(initial_state, round_count)

        for config in path_configs:
            self.paths[config.path_id] = SimulationPath(
                path_id=config.path_id,
                path_label=config.path_label,
            )

        self._path_configs = path_configs
        self._round_count = round_count

        logger.info(
            f"Multi-path simulation initialized: {len(path_configs)} paths, "
            f"{round_count} rounds ({round_count / 4:.0f} years)"
        )

        return [c.path_id for c in path_configs]

    def _run_single_path(self, config: PathConfig) -> SimulationPath:
        """Run one simulation path to completion."""
        state_store = AgentStateStore()
        persona_renderer = PersonaRenderer()
        event_engine = LifeEventEngine(seed=self.base_seed + config.seed_offset)
        blocker_engine = BlockerEngine()

        agent_id = f"agent_{config.path_id}"
        state_copy = deepcopy(self._base_state)
        identity_copy = deepcopy(self._base_identity)

        state_store.initialize_agent(agent_id, identity_copy, state_copy)

        if config.scheduled_events:
            event_engine.add_scheduled_events(config.scheduled_events)

        path = SimulationPath(
            path_id=config.path_id,
            path_label=config.path_label,
        )

        for round_num in range(1, self._round_count + 1):
            state = state_store.tick_round(agent_id)
            events = event_engine.evaluate(agent_id, state)
            for event in events:
                state_store.apply_event(agent_id, event)

            state.blockers = blocker_engine.evaluate(state)
            snapshot = state_store.snapshot(agent_id)
            path.snapshots.append(snapshot)

        path.final_state = state_store.get_state(agent_id)

        logger.info(
            f"Path {config.path_id} ({config.path_label}) complete: "
            f"age={path.final_state.current_age}, "
            f"salary={path.final_state.salary_annual}万, "
            f"cash={path.final_state.cash_buffer}万"
        )

        return path

    def run_all(self) -> Dict[str, SimulationPath]:
        """Run all paths in parallel using ThreadPoolExecutor.

        If a path fails, its error is logged and remaining paths continue.
        Failed paths are removed from self.paths.

        Returns:
            Dict of completed paths. self.errors contains any failures.
        """
        self.errors: Dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self._run_single_path, config): config.path_id
                for config in self._path_configs
            }
            for future in as_completed(futures):
                path_id = futures[future]
                try:
                    result = future.result()
                    self.paths[path_id] = result
                except Exception as e:
                    logger.error(f"Path {path_id} failed: {e}", exc_info=True)
                    self.errors[path_id] = str(e)

        # Remove shell entries for failed paths
        for path_id in self.errors:
            if path_id in self.paths and self.paths[path_id].final_state is None:
                del self.paths[path_id]

        if not self.paths:
            raise RuntimeError(f"All simulation paths failed: {self.errors}")

        return self.paths

    def generate_comparison_report(self) -> Dict[str, Any]:
        """Generate a comparison report across all paths."""
        if not self.paths or not any(p.final_state for p in self.paths.values()):
            return {"error": "No simulation results available"}

        path_summaries = []
        for path in self.paths.values():
            if not path.final_state:
                continue
            fs = path.final_state
            snapshots = path.snapshots

            # Calculate metrics
            salary_history = [s.salary_annual for s in snapshots]
            cash_history = [s.cash_buffer for s in snapshots]
            stress_history = [s.stress_level for s in snapshots]
            event_count = sum(len(s.events) for s in snapshots)
            blocker_rounds = sum(1 for s in snapshots if s.active_blockers)

            path_summaries.append({
                "path_id": path.path_id,
                "path_label": path.path_label,
                "final_age": fs.current_age,
                "final_role": fs.role,
                "final_employer": fs.employer,
                "final_salary": fs.salary_annual,
                "final_cash_buffer": fs.cash_buffer,
                "final_stress": round(fs.stress_level, 2),
                "final_satisfaction": round(fs.job_satisfaction, 2),
                "final_wlb": round(fs.work_life_balance, 2),
                "peak_salary": max(salary_history) if salary_history else 0,
                "min_cash": min(cash_history) if cash_history else 0,
                "avg_stress": round(
                    sum(stress_history) / len(stress_history), 2
                ) if stress_history else 0,
                "total_events": event_count,
                "rounds_with_blockers": blocker_rounds,
                "total_rounds": len(snapshots),
            })

        # Determine best path per dimension
        rankings = {}
        if path_summaries:
            rankings["highest_salary"] = max(
                path_summaries, key=lambda p: p["final_salary"]
            )["path_id"]
            rankings["most_cash"] = max(
                path_summaries, key=lambda p: p["final_cash_buffer"]
            )["path_id"]
            rankings["lowest_stress"] = min(
                path_summaries, key=lambda p: p["avg_stress"]
            )["path_id"]
            rankings["best_wlb"] = max(
                path_summaries, key=lambda p: p["final_wlb"]
            )["path_id"]

        result = {
            "identity": self._base_identity.to_dict() if self._base_identity else {},
            "simulation_years": self._round_count / 4,
            "total_rounds": self._round_count,
            "paths": path_summaries,
            "rankings": rankings,
        }
        if hasattr(self, 'errors') and self.errors:
            result["failed_paths"] = self.errors
        return result

    def get_path_timeline(self, path_id: str) -> List[Dict[str, Any]]:
        """Get detailed timeline for a specific path."""
        path = self.paths.get(path_id)
        if not path:
            return []
        return [s.to_dict() for s in path.snapshots]
