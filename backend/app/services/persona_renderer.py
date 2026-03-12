"""
P3: PersonaRenderer — converts BaseIdentity + CareerState into a system message.

This is the bridge between our state management and OASIS agents.
Generates the persona text and calls agent.update_system_message()
using the existing camel-ai API (no OASIS fork needed).
"""

from typing import Optional

from ..models.life_simulator import (
    BaseIdentity, CareerState, BlockerType, ActiveBlocker,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.persona_renderer')


class PersonaRenderer:
    """
    Renders BaseIdentity + CareerState → system message text.
    Then applies it to a SocialAgent via update_system_message().
    """

    def render_system_message(
        self,
        identity: BaseIdentity,
        state: CareerState,
        round_context: str = "",
    ) -> str:
        """
        Generate a full system message for the agent.

        Args:
            identity: Immutable base attributes
            state: Current mutable state
            round_context: Optional context about what's happening this round
        """
        sections = []

        # Identity section
        sections.append(self._render_identity(identity))

        # Current situation
        sections.append(self._render_current_situation(state))

        # Family & constraints
        if state.family:
            sections.append(self._render_family(state))

        # Financial situation
        sections.append(self._render_financial(state))

        # Active blockers
        if state.blockers:
            sections.append(self._render_blockers(state))

        # Well-being
        sections.append(self._render_wellbeing(state))

        # Round context
        if round_context:
            sections.append(f"## 今期の状況\n{round_context}")

        return "\n\n".join(sections)

    def apply_to_agent(
        self,
        agent,  # SocialAgent instance
        identity: BaseIdentity,
        state: CareerState,
        round_context: str = "",
    ) -> None:
        """
        Update the OASIS agent's system message and user_info.

        Uses ChatAgent.update_system_message() — existing camel-ai API.
        Also updates user_info.profile and user_info.description
        so OASIS internal references stay consistent.
        """
        new_message = self.render_system_message(identity, state, round_context)

        # Update system message via camel-ai API
        from camel.messages import BaseMessage
        sys_msg = BaseMessage.make_assistant_message(
            role_name=identity.name,
            content=new_message,
        )
        agent.update_system_message(sys_msg)

        # Also update user_info for OASIS consistency
        if hasattr(agent, 'user_info') and agent.user_info is not None:
            agent.user_info.description = new_message
            agent.user_info.profile = {
                "name": identity.name,
                "age": state.current_age,
                "role": state.role,
                "employer": state.employer,
                "industry": state.industry,
                "salary": state.salary_annual,
                "round": state.current_round,
            }

        logger.debug(f"Updated persona for {identity.name} (round {state.current_round})")

    def apply_to_agent_with_text(
        self,
        agent,
        identity: BaseIdentity,
        state: CareerState,
        persona_text: str,
    ) -> None:
        """
        Apply a pre-rendered persona text to the agent.
        Avoids re-calling render_system_message.
        """
        from camel.messages import BaseMessage
        sys_msg = BaseMessage.make_assistant_message(
            role_name=identity.name,
            content=persona_text,
        )
        agent.update_system_message(sys_msg)

        if hasattr(agent, 'user_info') and agent.user_info is not None:
            agent.user_info.description = persona_text
            agent.user_info.profile = {
                "name": identity.name,
                "age": state.current_age,
                "role": state.role,
                "employer": state.employer,
                "industry": state.industry,
                "salary": state.salary_annual,
                "round": state.current_round,
            }

        logger.debug(f"Updated persona (pre-rendered) for {identity.name} (round {state.current_round})")

    # ---- Private rendering methods ----

    def _render_identity(self, identity: BaseIdentity) -> str:
        lines = [f"## 基本プロフィール"]
        lines.append(f"名前: {identity.name}")
        if identity.education:
            lines.append(f"学歴: {identity.education}")
        if identity.mbti:
            lines.append(f"性格タイプ: {identity.mbti}")
        if identity.stable_traits:
            lines.append(f"特性: {', '.join(identity.stable_traits)}")
        if identity.certifications:
            lines.append(f"資格: {', '.join(identity.certifications)}")
        if identity.career_history_summary:
            lines.append(f"\n### 職歴要約\n{identity.career_history_summary}")
        return "\n".join(lines)

    def _render_current_situation(self, state: CareerState) -> str:
        lines = [f"## 現在の状況（{state.current_age}歳）"]
        if state.employer:
            lines.append(f"勤務先: {state.employer}")
        if state.role:
            lines.append(f"役職: {state.role}（{state.years_in_role}年目）")
        if state.industry:
            lines.append(f"業界: {state.industry}")
        if state.skills:
            lines.append(f"主要スキル: {', '.join(state.skills[:5])}")
        return "\n".join(lines)

    def _render_family(self, state: CareerState) -> str:
        lines = ["## 家族構成"]
        lines.append(f"婚姻状況: {state.marital_status}")
        for member in state.family:
            desc = f"- {member.relation}: {member.age}歳"
            if member.notes:
                desc += f"（{member.notes}）"
            lines.append(desc)
        return "\n".join(lines)

    def _render_financial(self, state: CareerState) -> str:
        lines = ["## 財務状況"]
        lines.append(f"年収: {state.salary_annual}万円")
        lines.append(f"金融資産: {state.cash_buffer}万円")
        if state.mortgage_remaining > 0:
            lines.append(f"ローン残額: {state.mortgage_remaining}万円")
        return "\n".join(lines)

    def _render_blockers(self, state: CareerState) -> str:
        lines = ["## 現在の制約条件"]
        for blocker in state.blockers:
            blocked = ", ".join(blocker.blocked_actions)
            lines.append(f"- {blocker.reason}（制限: {blocked}）")
        return "\n".join(lines)

    def _render_wellbeing(self, state: CareerState) -> str:
        def level(v: float) -> str:
            if v < 0.3:
                return "低"
            elif v < 0.6:
                return "中"
            else:
                return "高"

        return (
            f"## コンディション\n"
            f"ストレス: {level(state.stress_level)} / "
            f"仕事満足度: {level(state.job_satisfaction)} / "
            f"WLB: {level(state.work_life_balance)}"
        )
