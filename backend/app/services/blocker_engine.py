"""
P5: BlockerEngine — evaluates 6 categories of career blockers.

Blockers constrain which career decisions an agent can make,
adding realism to the simulation (e.g. can't start a business
with young children and a large mortgage).
"""

from typing import List

from ..models.life_simulator import (
    CareerState, ActiveBlocker, BlockerType,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.blocker_engine')


class BlockerEngine:
    """
    Evaluates agent state each round and activates/deactivates blockers.
    """

    def evaluate(self, state: CareerState) -> List[ActiveBlocker]:
        """
        Evaluate all 6 blocker categories against current state.
        Returns the full list of currently active blockers.
        """
        blockers: List[ActiveBlocker] = []

        blockers.extend(self._check_childcare(state))
        blockers.extend(self._check_exam_period(state))
        blockers.extend(self._check_education_cost(state))
        blockers.extend(self._check_mortgage(state))
        blockers.extend(self._check_elder_care(state))
        blockers.extend(self._check_age_wall(state))

        return blockers

    def _check_childcare(self, state: CareerState) -> List[ActiveBlocker]:
        """育児（子0-6歳）→ 海外赴任/起業ブロック"""
        young_children = [c for c in state.get_children() if c.age <= 6]
        if not young_children:
            return []
        ages = ", ".join(f"{c.age}歳" for c in young_children)
        return [ActiveBlocker(
            blocker_type=BlockerType.CHILDCARE,
            reason=f"育児中（子供: {ages}）",
            blocked_actions=["overseas_assignment", "startup", "long_business_trip"],
            started_round=state.current_round,
        )]

    def _check_exam_period(self, state: CareerState) -> List[ActiveBlocker]:
        """受験期（子が中3=15歳 or 高3=18歳）→ 引越し伴う転職ブロック"""
        exam_children = [c for c in state.get_children() if c.age in (15, 18)]
        if not exam_children:
            return []
        return [ActiveBlocker(
            blocker_type=BlockerType.EXAM_PERIOD,
            reason=f"子供の受験期（{exam_children[0].age}歳）",
            blocked_actions=["relocation_transfer", "overseas_assignment"],
            started_round=state.current_round,
            expires_round=state.current_round + 4,  # 1 year
        )]

    def _check_education_cost(self, state: CareerState) -> List[ActiveBlocker]:
        """教育費ピーク（子が大学生 19-22歳）→ 年収ダウン転職ブロック"""
        college_children = [c for c in state.get_children() if 19 <= c.age <= 22]
        if not college_children:
            return []
        return [ActiveBlocker(
            blocker_type=BlockerType.EDUCATION_COST,
            reason=f"教育費ピーク（大学生の子供あり）",
            blocked_actions=["salary_decrease_job_change", "startup"],
            started_round=state.current_round,
        )]

    def _check_mortgage(self, state: CareerState) -> List[ActiveBlocker]:
        """ローン（残額 > 年収 x 3）→ 起業ブロック"""
        if state.salary_annual <= 0:
            return []
        if state.mortgage_remaining <= state.salary_annual * 3:
            return []
        return [ActiveBlocker(
            blocker_type=BlockerType.MORTGAGE,
            reason=f"住宅ローン残額が大きい（{state.mortgage_remaining}万円 > 年収の3倍）",
            blocked_actions=["startup", "salary_decrease_job_change"],
            started_round=state.current_round,
        )]

    def _check_elder_care(self, state: CareerState) -> List[ActiveBlocker]:
        """介護中 → 遠方転勤ブロック"""
        caring_parents = [p for p in state.get_parents()
                          if p.notes and "介護" in p.notes]
        if not caring_parents:
            return []
        return [ActiveBlocker(
            blocker_type=BlockerType.ELDER_CARE,
            reason=f"親の介護中",
            blocked_actions=["relocation_transfer", "overseas_assignment", "long_business_trip"],
            started_round=state.current_round,
        )]

    def _check_age_wall(self, state: CareerState) -> List[ActiveBlocker]:
        """年齢の壁（35歳/45歳）→ 未経験転職成功率低下"""
        if state.current_age < 35:
            return []

        if state.current_age >= 45:
            return [ActiveBlocker(
                blocker_type=BlockerType.AGE_WALL,
                reason=f"45歳超：未経験分野への転職は極めて困難",
                blocked_actions=["career_change_to_new_field"],
                started_round=state.current_round,
            )]
        else:
            return [ActiveBlocker(
                blocker_type=BlockerType.AGE_WALL,
                reason=f"35歳超：未経験転職の成功率が低下",
                blocked_actions=["career_change_to_new_field_easy"],
                started_round=state.current_round,
            )]
