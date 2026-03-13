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
        for parent in state.get_parents():
            if parent.notes and "介護" in parent.notes:
                if self._rng.random() < 0.10:
                    parent.notes = ""
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

        # Child birth: married, < 2 children, 25-40, 4% per round
        children = state.get_children()
        if (state.marital_status == "married"
                and len(children) < 2
                and 25 <= state.current_age <= 40
                and self._rng.random() < 0.04):
            events.append(LifeEvent(
                event_type=LifeEventType.CHILD_BIRTH,
                round_number=state.current_round,
                description=f"第{len(children) + 1}子が誕生した",
                state_changes={},
            ))

        return events
