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


def build_llm_paths(
    state: CareerState,
    round_count: int,
    document_text: str = "",
    simulation_requirement: str = "",
    num_paths: int = 12,
) -> List[PathConfig]:
    """
    Use LLM to generate career paths personalized to the candidate's background.

    The LLM designs diverse, context-specific scenarios (e.g. M&A for entrepreneurs,
    tenure loss for academics, regulatory change for finance professionals).
    Falls back to hardcoded base paths on failure.
    """
    from ..utils.llm_client import LLMClient
    import json as _json

    role = state.role or "スタッフ"
    employer = state.employer or "現職"
    industry = state.industry or "不明"
    salary = state.salary_annual
    age = state.current_age
    mid = round_count // 2
    q3 = (round_count * 3) // 4

    # Map event type names for LLM output
    valid_event_types = {e.value: e for e in LifeEventType}

    # Fetch real hiring companies via Tavily
    hiring_context = ""
    try:
        from .external_data_fetcher import ExternalDataFetcher
        fetcher = ExternalDataFetcher()
        if fetcher.is_available:
            results = fetcher.search(
                f"{industry} {role} 求人 採用強化 中途採用 2025 2026",
                search_depth="advanced", max_results=5, include_answer=True,
            )
            if results:
                lines = []
                for r in results:
                    if r["type"] == "answer":
                        lines.append(r["content"])
                    elif r.get("title"):
                        lines.append(f"- {r['title']}: {r.get('content', '')[:200]}")
                hiring_context = "\n".join(lines)
                logger.info(f"Fetched hiring context: {len(hiring_context)} chars")
    except Exception as e:
        logger.warning(f"Failed to fetch hiring context: {e}")

    hiring_section = ""
    if hiring_context:
        hiring_section = f"""
【現在の求人市場情報（Web検索結果）】
{hiring_context[:2000]}

上記の求人市場情報を参考に、転職先企業名は可能な限り実在の企業名（バイネーム）を使ってください。
特に採用を強化している企業がある場合、その企業への転職パスを優先的に含めてください。
"""

    system_prompt = f"""\
あなたはキャリアシミュレーションの専門家です。
候補者のプロフィールに基づいて、{num_paths}個の多様なキャリアパスを設計してください。

【候補者プロフィール】
- 年齢: {age}歳
- 現職: {role} @ {employer}
- 業界: {industry}
- 年収: {salary}万円
- シミュレーション期間: {round_count}ラウンド（{round_count // 4}年間）

【職務経歴・背景】
{document_text[:1500]}

【シミュレーション要件】
{simulation_requirement[:500]}
{hiring_section}
【設計指針】
1. その人のキャリアから自然に派生するパスを中心に（王道〜挑戦的まで幅広く）
2. 転職先の企業名は可能な限り実在の企業名を使う（「同業大手」ではなく「Google」「リクルート」等）
3. ユーザーが思いもしないような意外なパスも2-3個含める
4. 業界・職種固有のリスクイベントを含める:
   - 起業家なら: 資金調達失敗、倒産、M&A、IPO
   - エンジニアなら: 技術陳腐化、OSS活動からの転機
   - 研究者なら: 任期切れ、企業R&D移籍、特許収入
   - 営業なら: 大口顧客喪失、独立代理店化
   - 金融なら: 規制変更、フィンテック転身
5. ライフイベント（結婚、出産、介護、健康問題、住宅購入、離婚等）は
   LifeEventEngine が確率的に自動生成するので、パスのスケジュールイベントに含めない
6. 各パスには2-4個のスケジュールイベント（キャリア転機）を設定

【利用可能なイベントタイプ】
promotion, job_change, salary_increase, salary_decrease, skill_acquisition,
startup, layoff, transfer, overseas, overseas_migration, rural_migration,
reskilling, side_business

【出力形式】純粋なJSON配列で出力:
[
  {{
    "path_id": "英字スネークケース",
    "path_label": "日本語ラベル（15文字以内）",
    "events": [
      {{
        "type": "イベントタイプ（上記から選択）",
        "round": ラウンド番号（1-{round_count}）,
        "description": "何が起きたか（日本語）",
        "state_changes": {{
          "role": "新しい役職",
          "employer": "新しい勤務先",
          "industry": "新しい業界",
          "salary_annual": 新年収（万円、整数）
        }}
      }}
    ]
  }}
]

注意:
- state_changes は変更があるフィールドのみ含める
- salary_increase タイプの場合は "salary_increase_pct": 数値 を使う
- 最後に「現状維持」パス（events空）を1つ含める
- path_id はユニークに"""

    try:
        llm = LLMClient(use_chat_model=True)
        result = None
        last_err = None
        for attempt in range(2):
            try:
                result = llm.chat_json(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "上記のプロフィールに基づいて、多様なキャリアパスをJSON配列で生成してください。"}
                    ],
                    temperature=0.7,
                    max_tokens=8192,
                )
                break
            except Exception as retry_err:
                last_err = retry_err
                if attempt == 0:
                    logger.warning(f"LLM path generation attempt {attempt+1} failed, retrying: {retry_err}")
        if result is None:
            raise last_err or ValueError("LLM returned no result")

        # Parse: result could be a list directly or {"paths": [...]}
        if isinstance(result, list):
            raw_paths = result
        elif isinstance(result, dict) and "paths" in result:
            raw_paths = result["paths"]
        else:
            raw_paths = result if isinstance(result, list) else []

        if not raw_paths:
            raise ValueError("LLM returned empty paths")

        configs = []
        for i, rp in enumerate(raw_paths):
            path_id = rp.get("path_id", f"llm_path_{i}")
            path_label = rp.get("path_label", f"パス{i+1}")

            events = []
            for ev in rp.get("events", []):
                evt_type_str = ev.get("type", "")
                if evt_type_str not in valid_event_types:
                    # Try common aliases
                    aliases = {"job_change": "job_change", "overseas_transfer": "overseas"}
                    evt_type_str = aliases.get(evt_type_str, evt_type_str)
                if evt_type_str not in valid_event_types:
                    logger.warning(f"Skipping unknown event type: {evt_type_str}")
                    continue

                sc = ev.get("state_changes", {})
                # Ensure salary_annual is int if present
                if "salary_annual" in sc:
                    sc["salary_annual"] = int(sc["salary_annual"])

                events.append(LifeEvent(
                    event_type=valid_event_types[evt_type_str],
                    round_number=int(ev.get("round", 4)),
                    description=ev.get("description", ""),
                    state_changes=sc,
                ))

            configs.append(PathConfig(
                path_id=path_id,
                path_label=path_label,
                scheduled_events=events,
                seed_offset=i * 100,
            ))

        logger.info(f"LLM generated {len(configs)} career paths for {role}@{employer}")
        return configs

    except (ValueError, KeyError) as e:
        logger.warning(f"LLM path parsing failed, generating fallback paths: {e}")
    except Exception as e:
        logger.error(f"LLM path generation failed ({type(e).__name__}), generating fallback paths: {e}")

    # Fallback paths — reached when any except branch catches
    salary = state.salary_annual
    role = state.role or "スタッフ"
    employer = state.employer or "現職"
    mid = round_count // 2
    return [
        PathConfig(path_id="stay_promote", path_label="現職で昇進",
                   scheduled_events=[
                       LifeEvent(event_type=LifeEventType.PROMOTION, round_number=8,
                                 description=f"{employer}で昇進",
                                 state_changes={"role": f"シニア{role}", "salary_annual": int(salary * 1.2)})
                   ], seed_offset=0),
        PathConfig(path_id="lateral", path_label="同業転職",
                   scheduled_events=[
                       LifeEvent(event_type=LifeEventType.JOB_CHANGE, round_number=4,
                                 description="同業他社へ転職",
                                 state_changes={"employer": "同業他社", "salary_annual": int(salary * 1.2)})
                   ], seed_offset=100),
        PathConfig(path_id="career_change", path_label="異業種転職",
                   scheduled_events=[
                       LifeEvent(event_type=LifeEventType.JOB_CHANGE, round_number=6,
                                 description="異業種へ転職",
                                 state_changes={"employer": "異業種企業", "salary_annual": int(salary * 0.85)})
                   ], seed_offset=200),
        PathConfig(path_id="freelance", path_label="フリーランス独立",
                   scheduled_events=[
                       LifeEvent(event_type=LifeEventType.JOB_CHANGE, round_number=4,
                                 description="フリーランスとして独立",
                                 state_changes={"employer": "フリーランス", "salary_annual": int(salary * 0.7)}),
                       LifeEvent(event_type=LifeEventType.SALARY_INCREASE, round_number=mid,
                                 description="基盤安定化",
                                 state_changes={"salary_increase_pct": 40})
                   ], seed_offset=300),
        PathConfig(path_id="baseline", path_label="現状維持",
                   scheduled_events=[], seed_offset=999),
    ]


def _safe_float(env_key: str, default: float) -> float:
    """Parse env var as float, falling back to default on invalid values."""
    try:
        return float(os.environ.get(env_key, str(default)))
    except (ValueError, TypeError):
        logger.warning(f"Invalid value for {env_key}, using default {default}")
        return default


# Default score weights — can be overridden via environment variables
DEFAULT_SCORE_WEIGHTS = {
    "salary": _safe_float("SCORE_WEIGHT_SALARY", 0.25),
    "cash": _safe_float("SCORE_WEIGHT_CASH", 0.15),
    "low_stress": _safe_float("SCORE_WEIGHT_LOW_STRESS", 0.15),
    "satisfaction": _safe_float("SCORE_WEIGHT_SATISFACTION", 0.25),
    "wlb": _safe_float("SCORE_WEIGHT_WLB", 0.20),
}


def score_path(summary: dict, weights: Optional[Dict[str, float]] = None) -> float:
    """
    Score a completed path for ranking. Higher = better overall outcome.

    Balances salary growth, financial stability, stress, satisfaction, and WLB.
    Weights can be customized per user preference or via env vars.
    """
    w = weights or DEFAULT_SCORE_WEIGHTS
    salary_score = min(summary.get("final_salary", 0) / 1500, 1.0)  # cap at 1500万
    cash_score = min(max(summary.get("final_cash_buffer", 0), 0) / 5000, 1.0)
    stress_penalty = summary.get("avg_stress", 0.5)  # lower is better
    satisfaction = summary.get("final_satisfaction", 0.5)
    wlb = summary.get("final_wlb", 0.5)

    return (
        salary_score * w.get("salary", 0.25)
        + cash_score * w.get("cash", 0.15)
        + (1.0 - stress_penalty) * w.get("low_stress", 0.15)
        + satisfaction * w.get("satisfaction", 0.25)
        + wlb * w.get("wlb", 0.20)
    )


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
        max_workers = min(len(self._path_configs), 6)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
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

    def run_expanded_and_select(
        self,
        identity: BaseIdentity,
        initial_state: CareerState,
        round_count: int = 40,
        top_n: int = 5,
        document_text: str = "",
        simulation_requirement: str = "",
    ) -> Dict[str, Any]:
        """
        Run LLM-generated career paths, score them, and return top N with full report.

        Uses build_llm_paths() to generate personalized paths based on the candidate's
        resume. Falls back to minimal hardcoded paths if LLM fails.

        Returns:
            Dict with 'paths' (top N summaries), 'all_paths' (all scored), 'rankings', etc.
        """
        expanded = build_llm_paths(
            initial_state, round_count,
            document_text=document_text,
            simulation_requirement=simulation_requirement,
        )
        self.initialize(identity, initial_state, path_configs=expanded, round_count=round_count)
        self.run_all()
        report = self.generate_comparison_report()

        # Score and rank all paths
        for p in report.get("paths", []):
            p["score"] = round(score_path(p), 3)

        all_paths_sorted = sorted(report.get("paths", []), key=lambda p: p["score"], reverse=True)
        top_paths = all_paths_sorted[:top_n]

        # Collect events and salary trajectory for top paths
        for p in top_paths:
            timeline = self.get_path_timeline(p["path_id"])
            events = []
            salary_trajectory = []
            for snap in timeline:
                for evt_desc in snap.get("events", []):
                    events.append({"round": snap["round_number"], "age": snap["age"], "event": evt_desc})
                salary_trajectory.append({
                    "round": snap["round_number"],
                    "age": snap["age"],
                    "salary": snap["salary_annual"],
                })
            p["key_events"] = events
            p["salary_trajectory"] = salary_trajectory

        report["paths"] = top_paths
        report["all_paths_scored"] = [
            {"path_id": p["path_id"], "path_label": p["path_label"], "score": p["score"]}
            for p in all_paths_sorted
        ]
        report["top_n"] = top_n
        report["total_paths_simulated"] = len(all_paths_sorted)

        return report

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
