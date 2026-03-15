"""
P4: LifeEventEngine — generates scheduled and probabilistic life events.

Two event sources:
1. Scheduled events: CareerPhase transitions at predefined rounds
2. Probabilistic events: Random events based on agent state (e.g. elder care)
"""

import random
from typing import List, Optional

from ..models.life_simulator import (
    CareerState, LifeEvent, LifeEventType, FamilyMember, BlockerType,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.life_event_engine')


class LifeEventEngine:
    """
    Evaluates and generates life events each round based on agent state.
    """

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._scheduled_events: List[LifeEvent] = []

    def add_scheduled_event(self, event: LifeEvent) -> None:
        """Register a scheduled event (e.g. career phase transition)."""
        self._scheduled_events.append(event)

    def add_scheduled_events(self, events: List[LifeEvent]) -> None:
        self._scheduled_events.extend(events)

    def clear_scheduled_events(self) -> None:
        """Clear all scheduled events (use before re-initializing for a new agent)."""
        self._scheduled_events.clear()

    def evaluate(self, agent_id: str, state: CareerState) -> List[LifeEvent]:
        """
        Evaluate all possible events for this round.
        Returns list of events that fire this round.
        """
        fired_events: List[LifeEvent] = []

        # 1. Check scheduled events
        for event in self._scheduled_events:
            if event.round_number == state.current_round:
                fired_events.append(event)
                logger.info(f"Scheduled event fired for {agent_id}: {event.description}")

        # 2. Evaluate probabilistic events
        probabilistic = self._evaluate_probabilistic(state)
        fired_events.extend(probabilistic)

        return fired_events

    def _evaluate_probabilistic(self, state: CareerState) -> List[LifeEvent]:
        """Check probability-based events against current state."""
        events: List[LifeEvent] = []

        # Elder care: parents 75+ → 5% per round to start
        for parent in state.get_parents():
            if parent.age >= 75 and not state.has_blocker(BlockerType.ELDER_CARE):
                if "介護" not in parent.notes and self._rng.random() < 0.05:
                    events.append(LifeEvent(
                        event_type=LifeEventType.ELDER_CARE_START,
                        round_number=state.current_round,
                        description=f"{parent.relation}（{parent.age}歳）の介護が必要になった",
                        state_changes={},
                    ))

        # Elder care end: 10% per round if caring (avg ~2.5 years)
        # Note: parent.notes is unchanged at evaluate() time (updated in apply_event),
        # so a same-round START→END is not possible.
        # Note clearing is handled in AgentStateStore.apply_event(), not here.
        for parent in state.get_parents():
            if parent.notes and "介護" in parent.notes:
                if self._rng.random() < 0.10:
                    events.append(LifeEvent(
                        event_type=LifeEventType.ELDER_CARE_END,
                        round_number=state.current_round,
                        description=f"{parent.relation}（{parent.age}歳）の介護が終了した",
                        state_changes={},
                    ))

        # Market crash: 2% per round (expected ~once every 50 rounds / 12.5 years)
        if state.cash_buffer > 500 and self._rng.random() < 0.02:
            events.append(LifeEvent(
                event_type=LifeEventType.MARKET_CRASH,
                round_number=state.current_round,
                description="市場の急落により金融資産が目減りした",
                state_changes={},
            ))

        # Natural salary increase: 3% per year if employed (fires every 4th round)
        if (state.current_round % 4 == 0
                and state.salary_annual > 0
                and state.employer != ""
                and self._rng.random() < 0.6):
            events.append(LifeEvent(
                event_type=LifeEventType.SALARY_INCREASE,
                round_number=state.current_round,
                description="定期昇給",
                state_changes={"salary_increase_pct": 3},
            ))

        # Stress-induced events: high stress → job satisfaction drops
        if state.stress_level > 0.8 and self._rng.random() < 0.15:
            events.append(LifeEvent(
                event_type=LifeEventType.SALARY_DECREASE,
                round_number=state.current_round,
                description="ストレスによるパフォーマンス低下で評価が下がった",
                state_changes={"job_satisfaction": max(0.1, state.job_satisfaction - 0.2)},
            ))

        # Marriage probability: single, 28-38, 3% per round
        if (state.marital_status == "single"
                and 28 <= state.current_age <= 38
                and self._rng.random() < 0.03):
            events.append(LifeEvent(
                event_type=LifeEventType.MARRIAGE,
                round_number=state.current_round,
                description="結婚した",
                state_changes={
                    "marital_status": "married",
                    "monthly_expenses": state.monthly_expenses + 5,
                },
            ))

        # Child birth: < 2 children, 25-42, probability varies by marital status
        children = state.get_children()
        if (len(children) < 2
                and 25 <= state.current_age <= 42):
            # Married: 4% per round, unmarried: 1.5% per round
            birth_prob = 0.04 if state.marital_status == "married" else 0.015
            if self._rng.random() < birth_prob:
                events.append(LifeEvent(
                    event_type=LifeEventType.CHILD_BIRTH,
                    round_number=state.current_round,
                    description=f"第{len(children) + 1}子が誕生した",
                    state_changes={},
                ))

        # Divorce: married, 2% per round (higher if stress > 0.7)
        if (state.marital_status == "married"
                and self._rng.random() < (0.04 if state.stress_level > 0.7 else 0.02)):
            events.append(LifeEvent(
                event_type=LifeEventType.DIVORCE,
                round_number=state.current_round,
                description="離婚した",
                state_changes={
                    "marital_status": "divorced",
                    "monthly_expenses": max(10, state.monthly_expenses - 3),
                    "cash_buffer": int(state.cash_buffer * 0.6),
                },
            ))

        # Health issue: 2% per round, higher if stress > 0.8
        if self._rng.random() < (0.05 if state.stress_level > 0.8 else 0.02):
            events.append(LifeEvent(
                event_type=LifeEventType.HEALTH_ISSUE,
                round_number=state.current_round,
                description="健康上の問題（バーンアウト・体調不良）が発生した",
                state_changes={
                    "stress_level": min(1.0, state.stress_level + 0.3),
                    "work_life_balance": max(0.0, state.work_life_balance - 0.2),
                },
            ))

        # Side business: employed, 30-45, low stress, 2% per round
        if (state.employer
                and 30 <= state.current_age <= 45
                and state.stress_level < 0.5
                and self._rng.random() < 0.02):
            events.append(LifeEvent(
                event_type=LifeEventType.SIDE_BUSINESS,
                round_number=state.current_round,
                description="副業を開始した",
                state_changes={
                    "cash_buffer": state.cash_buffer + 30,
                    "stress_level": min(1.0, state.stress_level + 0.1),
                },
            ))

        # Reskilling: 3% per round, more likely at career transition ages
        reskill_prob = 0.04 if 28 <= state.current_age <= 40 else 0.02
        if self._rng.random() < reskill_prob:
            events.append(LifeEvent(
                event_type=LifeEventType.RESKILLING,
                round_number=state.current_round,
                description="リスキリング・学び直しを開始した（オンライン講座・大学院等）",
                state_changes={
                    "monthly_expenses": state.monthly_expenses + 3,
                    "job_satisfaction": min(1.0, state.job_satisfaction + 0.1),
                },
            ))

        # Housing purchase: employed, 28-42, not already mortgaged, 2% per round
        if (state.employer
                and state.mortgage_remaining == 0
                and 28 <= state.current_age <= 42
                and state.salary_annual >= 400
                and self._rng.random() < 0.02):
            mortgage_amount = int(state.salary_annual * 5)
            events.append(LifeEvent(
                event_type=LifeEventType.HOUSING_PURCHASE,
                round_number=state.current_round,
                description=f"住宅を購入した（ローン{mortgage_amount}万円）",
                state_changes={
                    "mortgage_remaining": mortgage_amount,
                    "monthly_expenses": state.monthly_expenses + 5,
                    "job_satisfaction": min(1.0, state.job_satisfaction + 0.1),
                },
            ))

        # Parental leave: child born within last 4 rounds, 30% chance
        has_infant = any(c.age == 0 for c in children)
        if has_infant and self._rng.random() < 0.30:
            events.append(LifeEvent(
                event_type=LifeEventType.PARENTAL_LEAVE,
                round_number=state.current_round,
                description="育児休業を取得した",
                state_changes={
                    "work_life_balance": min(1.0, state.work_life_balance + 0.3),
                    "stress_level": max(0.0, state.stress_level - 0.1),
                },
            ))

        # Rural migration: 1.5% per round, higher if WLB is low and stress is high
        rural_prob = 0.03 if (state.stress_level > 0.6 and state.work_life_balance < 0.4) else 0.015
        if (state.employer
                and not state.is_action_blocked("overseas_assignment")
                and self._rng.random() < rural_prob):
            events.append(LifeEvent(
                event_type=LifeEventType.RURAL_MIGRATION,
                round_number=state.current_round,
                description="地方移住を決断した（リモートワーク活用）",
                state_changes={
                    "monthly_expenses": max(10, state.monthly_expenses - 8),
                    "work_life_balance": min(1.0, state.work_life_balance + 0.3),
                    "stress_level": max(0.0, state.stress_level - 0.2),
                    "salary_annual": int(state.salary_annual * 0.85),
                },
            ))

        # Overseas migration: 1% per round, more likely if young and no blockers
        overseas_prob = 0.02 if state.current_age <= 35 else 0.008
        if (not state.is_action_blocked("overseas_assignment")
                and not state.is_action_blocked("startup")
                and self._rng.random() < overseas_prob):
            events.append(LifeEvent(
                event_type=LifeEventType.OVERSEAS_MIGRATION,
                round_number=state.current_round,
                description="海外移住を決断した",
                state_changes={
                    "salary_annual": int(state.salary_annual * 1.3),
                    "stress_level": min(1.0, state.stress_level + 0.2),
                    "monthly_expenses": state.monthly_expenses + 10,
                },
            ))

        # C-1 fix: Filter mutually exclusive events in the same round
        events = self._filter_conflicting_events(events)

        return events

    @staticmethod
    def _filter_conflicting_events(events: List[LifeEvent]) -> List[LifeEvent]:
        """Remove conflicting event pairs from a single round.

        Rules:
        - MARRIAGE and DIVORCE cannot co-occur (keep whichever came first)
        - MARRIAGE and CHILD_BIRTH in same round is fine (natural)
        - RURAL_MIGRATION and OVERSEAS_MIGRATION cannot co-occur
        """
        types = {e.event_type for e in events}

        conflicts = [
            (LifeEventType.MARRIAGE, LifeEventType.DIVORCE),
            (LifeEventType.RURAL_MIGRATION, LifeEventType.OVERSEAS_MIGRATION),
        ]

        remove_types: set = set()
        for a, b in conflicts:
            if a in types and b in types:
                # Keep the first (a), remove the second (b)
                remove_types.add(b)

        if not remove_types:
            return events
        return [e for e in events if e.event_type not in remove_types]
