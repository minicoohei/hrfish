"""
P6+P7: Life Simulation Loop — v7 round loop integrating all components.

Wraps the existing OASIS simulation loop with:
- AgentStateStore (P2) for state management
- PersonaRenderer (P3) for dynamic persona updates
- LifeEventEngine (P4) for event generation
- BlockerEngine (P5) for constraint evaluation
- 3 new ActionTypes: INTERNAL_MONOLOGUE, CONSULT, DECIDE

This module provides hooks that plug into the existing
TwitterSimulationRunner without modifying it.
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..models.life_simulator import (
    BaseIdentity, CareerState, LifeEvent, LifeEventType,
    FamilyMember, AgentSnapshot, SimulationPath, ActionTypeMiroFish,
)
from .agent_state_store import AgentStateStore
from .persona_renderer import PersonaRenderer
from .life_event_engine import LifeEventEngine
from .blocker_engine import BlockerEngine
from ..utils.logger import get_logger

logger = get_logger('mirofish.life_simulation_loop')


@dataclass
class FormInput:
    """Input from the simple questionnaire form (3-4 questions)."""
    family_members: List[FamilyMember]
    marital_status: str = "single"
    mortgage_remaining: int = 0         # 万円
    cash_buffer_range: str = "500未満"  # "500未満" / "500-2000" / "2000+"
    monthly_expenses: int = 25          # 万円


def cash_range_to_value(range_str: str) -> int:
    """Convert cash range string to representative value."""
    mapping = {
        "500未満": 250,
        "500-2000": 1000,
        "2000+": 3000,
    }
    value = mapping.get(range_str)
    if value is None:
        logger.warning(f"Unknown cash_buffer_range '{range_str}', defaulting to 250")
        return 250
    return value


class LifeSimulationOrchestrator:
    """
    Orchestrates the v7 life simulation loop.

    Usage:
        orchestrator = LifeSimulationOrchestrator()
        orchestrator.initialize_from_profile(profile, form_input)

        # Inside the existing OASIS round loop:
        for round_num in range(total_rounds):
            orchestrator.pre_round_hook(agent_id, round_num, agent)
            # ... existing env.step() ...
            orchestrator.post_round_hook(agent_id, round_num)
    """

    def __init__(self, seed: Optional[int] = None):
        self.state_store = AgentStateStore()
        self.persona_renderer = PersonaRenderer()
        self.event_engine = LifeEventEngine(seed=seed)
        self.blocker_engine = BlockerEngine()

    def initialize_from_profile(
        self,
        agent_id: str,
        profile: Dict[str, Any],
        form_input: FormInput,
        scheduled_events: Optional[List[LifeEvent]] = None,
    ) -> None:
        """
        Initialize agent state from OASIS profile + form input.

        Args:
            agent_id: Agent identifier
            profile: OasisAgentProfile data (from existing pipeline)
            form_input: User's form input (family, mortgage, assets)
            scheduled_events: Pre-planned career phase events
        """
        # Build BaseIdentity from profile
        identity = BaseIdentity(
            name=profile.get("name", "Unknown"),
            age_at_start=profile.get("age", 30),
            gender=profile.get("gender", ""),
            education=profile.get("education", ""),
            mbti=profile.get("mbti", ""),
            stable_traits=profile.get("traits", []),
            certifications=profile.get("certifications", []),
            career_history_summary=profile.get("career_summary", ""),
        )

        # Build initial CareerState from profile + form
        initial_state = CareerState(
            current_round=0,
            current_age=identity.age_at_start,
            role=profile.get("current_role", ""),
            employer=profile.get("current_employer", ""),
            industry=profile.get("industry", ""),
            years_in_role=profile.get("years_in_role", 0),
            salary_annual=profile.get("salary", 0),
            skills=profile.get("skills", []),
            family=form_input.family_members,
            marital_status=form_input.marital_status,
            cash_buffer=cash_range_to_value(form_input.cash_buffer_range),
            mortgage_remaining=form_input.mortgage_remaining,
            monthly_expenses=form_input.monthly_expenses,
        )

        self.state_store.initialize_agent(agent_id, identity, initial_state)

        # Register scheduled events
        if scheduled_events:
            self.event_engine.add_scheduled_events(scheduled_events)

        logger.info(
            f"Initialized life simulation for {identity.name}: "
            f"age={identity.age_at_start}, salary={initial_state.salary_annual}万, "
            f"family={len(form_input.family_members)} members"
        )

    def pre_round_hook(
        self,
        agent_id: str,
        round_num: int,
        agent=None,  # SocialAgent (optional, for persona update)
    ) -> Dict[str, Any]:
        """
        Called BEFORE env.step() each round.
        Implements Phase 1 (環境変化) and Phase 2 (ペルソナ同期).

        Returns:
            Round context dict with events, blockers, and persona text.
        """
        # Phase 1: 環境変化
        # 1a. Tick round (age up, financial calculation)
        state = self.state_store.tick_round(agent_id)

        # 1b. Evaluate life events
        events = self.event_engine.evaluate(agent_id, state)
        for event in events:
            self.state_store.apply_event(agent_id, event)

        # 1c. Evaluate blockers
        state.blockers = self.blocker_engine.evaluate(state)

        # Phase 2: ペルソナ同期
        identity = self.state_store.get_identity(agent_id)
        round_context = self._build_round_context(state, events)

        persona_text = self.persona_renderer.render_system_message(
            identity, state, round_context
        )

        if agent is not None:
            self.persona_renderer.apply_to_agent_with_text(
                agent, identity, state, persona_text
            )

        return {
            "round": round_num,
            "age": state.current_age,
            "events": [e.description for e in events],
            "blockers": [b.reason for b in state.blockers],
            "persona_text": persona_text,
        }

    def post_round_hook(
        self,
        agent_id: str,
        round_num: int,
        agent_action_result: Optional[Dict[str, Any]] = None,
    ) -> AgentSnapshot:
        """
        Called AFTER env.step() each round.
        Implements Phase 4 (資産計算 — already done in tick_round)
        and Phase 5 (スナップショット).

        Args:
            agent_id: Agent identifier
            round_num: Current round number
            agent_action_result: Result from OASIS env.step (optional)
        """
        state = self.state_store.get_state(agent_id)

        # Handle DECIDE action results
        if agent_action_result:
            decision = agent_action_result.get("decision")
            if decision:
                self._handle_decide_action(agent_id, decision)

        # Phase 5: Snapshot
        snapshot = self.state_store.snapshot(agent_id)

        if round_num % 10 == 0:
            logger.info(
                f"Round {round_num}: {state.current_age}歳, "
                f"salary={state.salary_annual}万, "
                f"cash={state.cash_buffer}万, "
                f"blockers={len(state.blockers)}"
            )

        return snapshot

    def _handle_decide_action(self, agent_id: str, decision: Dict[str, Any]) -> None:
        """Process a DECIDE action — agent made a state-changing decision."""
        decision_type = decision.get("type", "")
        state = self.state_store.get_state(agent_id)

        if decision_type == "job_change":
            event = LifeEvent(
                event_type=LifeEventType.JOB_CHANGE,
                round_number=state.current_round,
                description=f"転職を決断: {decision.get('details', '')}",
                state_changes={
                    "employer": decision.get("new_employer", state.employer),
                    "role": decision.get("new_role", state.role),
                    "salary_annual": decision.get("new_salary", state.salary_annual),
                    "industry": decision.get("new_industry", state.industry),
                },
            )
            self.state_store.apply_event(agent_id, event)

        elif decision_type == "startup":
            if state.is_action_blocked("startup"):
                state.events_this_round.append(
                    f"起業を検討したが、制約条件により断念: "
                    f"{[b.reason for b in state.blockers if 'startup' in b.blocked_actions]}"
                )
            else:
                event = LifeEvent(
                    event_type=LifeEventType.JOB_CHANGE,
                    round_number=state.current_round,
                    description="起業を決断",
                    state_changes={
                        "employer": "自営業",
                        "role": "代表",
                        "salary_annual": int(state.salary_annual * 0.5),
                    },
                )
                self.state_store.apply_event(agent_id, event)

        logger.info(f"Agent {agent_id} DECIDE: {decision_type}")

    def _build_round_context(self, state: CareerState, events: List[LifeEvent]) -> str:
        """Build context string for this round's events."""
        parts = []
        if events:
            parts.append("今期のイベント:")
            for e in events:
                parts.append(f"- {e.description}")
        if state.blockers:
            parts.append("\n現在の制約:")
            for b in state.blockers:
                parts.append(f"- {b.reason}")
        return "\n".join(parts) if parts else ""

    def get_simulation_summary(self, agent_id: str) -> Dict[str, Any]:
        """Get full simulation history for reporting."""
        identity = self.state_store.get_identity(agent_id)
        state = self.state_store.get_state(agent_id)
        history = self.state_store.get_history(agent_id)

        return {
            "identity": identity.to_dict(),
            "final_state": state.to_dict(),
            "history": [s.to_dict() for s in history],
            "total_rounds": state.current_round,
            "years_simulated": state.current_round / 4,
        }
