"""
P2: AgentStateStore — manages agent lifecycle state during simulation.

Responsibilities:
- Initialize agent state from BaseIdentity + form input
- Apply life events to update CareerState
- Take snapshots each round for history tracking
"""

from typing import Dict, Any, List, Optional
from copy import deepcopy

from ..models.life_simulator import (
    BaseIdentity, CareerState, LifeEvent, LifeEventType,
    AgentSnapshot, ActiveBlocker, BlockerType, FamilyMember,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.agent_state_store')


class AgentStateStore:
    """
    Manages BaseIdentity (immutable) + CareerState (mutable) for each agent.
    """

    def __init__(self):
        self._identities: Dict[str, BaseIdentity] = {}
        self._states: Dict[str, CareerState] = {}
        self._history: Dict[str, List[AgentSnapshot]] = {}

    def initialize_agent(
        self,
        agent_id: str,
        identity: BaseIdentity,
        initial_state: CareerState,
    ) -> None:
        """Register an agent with its immutable identity and initial mutable state."""
        self._identities[agent_id] = identity
        self._states[agent_id] = initial_state
        self._history[agent_id] = []
        logger.info(f"Initialized agent {agent_id}: {identity.name}, age={identity.age_at_start}")

    def get_identity(self, agent_id: str) -> BaseIdentity:
        return self._identities[agent_id]

    def get_state(self, agent_id: str) -> CareerState:
        return self._states[agent_id]

    def apply_event(self, agent_id: str, event: LifeEvent) -> CareerState:
        """
        Apply a life event to an agent's CareerState.
        Returns the updated state.
        """
        state = self._states[agent_id]

        # Apply state_changes dict directly
        for key, value in event.state_changes.items():
            if hasattr(state, key):
                setattr(state, key, value)

        # Type-specific logic
        if event.event_type == LifeEventType.PROMOTION:
            state.years_in_role = 0
            state.job_satisfaction = min(1.0, state.job_satisfaction + 0.2)
            state.stress_level = min(1.0, state.stress_level + 0.1)

        elif event.event_type == LifeEventType.JOB_CHANGE:
            state.years_in_role = 0
            state.stress_level = min(1.0, state.stress_level + 0.15)
            state.job_satisfaction = 0.6  # Reset to moderate

        elif event.event_type == LifeEventType.LAYOFF:
            state.employer = ""
            state.role = "求職中"
            state.salary_annual = 0
            state.stress_level = min(1.0, state.stress_level + 0.4)
            state.job_satisfaction = 0.1

        elif event.event_type == LifeEventType.CHILD_BIRTH:
            state.monthly_expenses += 8  # ~8万/月 increase
            state.work_life_balance = max(0.0, state.work_life_balance - 0.2)

        elif event.event_type == LifeEventType.ELDER_CARE_START:
            state.stress_level = min(1.0, state.stress_level + 0.3)
            state.work_life_balance = max(0.0, state.work_life_balance - 0.3)

        elif event.event_type == LifeEventType.SALARY_INCREASE:
            increase = event.state_changes.get("salary_increase_pct", 10)
            state.salary_annual = int(state.salary_annual * (1 + increase / 100))

        elif event.event_type == LifeEventType.MARKET_CRASH:
            state.cash_buffer = int(state.cash_buffer * 0.7)  # 30% loss

        state.events_this_round.append(event.description)
        logger.info(f"Applied event to {agent_id}: {event.event_type.value} - {event.description}")
        return state

    def tick_round(self, agent_id: str) -> CareerState:
        """
        Advance one round: age up, update family ages, clear round events.
        Called at the start of each round.
        """
        state = self._states[agent_id]
        state.current_round += 1
        state.events_this_round = []

        # Age up every 4 rounds (1 round ≈ 3 months, 4 rounds = 1 year)
        if state.current_round % 4 == 0:
            state.current_age += 1
            state.years_in_role += 1

            # Age up family members
            for member in state.family:
                member.age += 1

        # Financial: quarterly salary → cash buffer (minus expenses)
        quarterly_salary = state.salary_annual / 4
        quarterly_expenses = state.monthly_expenses * 3
        state.cash_buffer += int(quarterly_salary - quarterly_expenses)

        # Mortgage payment
        if state.mortgage_remaining > 0:
            quarterly_payment = min(state.mortgage_remaining, 75)  # ~25万/月
            state.mortgage_remaining -= quarterly_payment
            state.cash_buffer -= quarterly_payment

        # Stress natural decay
        state.stress_level = max(0.1, state.stress_level * 0.95)

        return state

    def snapshot(self, agent_id: str) -> AgentSnapshot:
        """Take a snapshot of current state for history."""
        state = self._states[agent_id]
        snap = AgentSnapshot(
            round_number=state.current_round,
            age=state.current_age,
            role=state.role,
            employer=state.employer,
            salary_annual=state.salary_annual,
            cash_buffer=state.cash_buffer,
            stress_level=state.stress_level,
            active_blockers=[b.blocker_type.value for b in state.blockers],
            events=list(state.events_this_round),
        )
        self._history[agent_id].append(snap)
        return snap

    def get_history(self, agent_id: str) -> List[AgentSnapshot]:
        return self._history.get(agent_id, [])

    def clone_state(self, agent_id: str) -> CareerState:
        """Deep copy current state (used for multi-path branching)."""
        return deepcopy(self._states[agent_id])
