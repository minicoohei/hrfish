"""
Life Simulator domain models (v7 architecture)

BaseIdentity (immutable) + CareerState (mutable) separation.
Used by PersonaRenderer to generate dynamic system messages
for OASIS agents via ChatAgent.update_system_message().
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, List, Optional
from copy import deepcopy


# ============================================================
# Enums
# ============================================================

class BlockerType(str, Enum):
    """6 blocker categories that constrain career decisions"""
    CHILDCARE = "childcare"           # 育児（子0-6歳）→ 海外赴任/起業ブロック
    EXAM_PERIOD = "exam_period"       # 受験期（中3/高3）→ 引越し転職ブロック
    EDUCATION_COST = "education_cost" # 教育費ピーク（大学）→ 年収ダウン転職ブロック
    MORTGAGE = "mortgage"             # ローン（残額>年収x3）→ 起業ブロック
    ELDER_CARE = "elder_care"         # 介護 → 遠方転勤ブロック
    AGE_WALL = "age_wall"             # 年齢の壁（35/45歳）→ 未経験転職成功率低下


class LifeEventType(str, Enum):
    """Types of life events that can occur during simulation"""
    # Career events
    PROMOTION = "promotion"
    DEMOTION = "demotion"
    JOB_CHANGE = "job_change"
    STARTUP = "startup"
    LAYOFF = "layoff"
    TRANSFER = "transfer"           # 転勤
    OVERSEAS_ASSIGNMENT = "overseas" # 海外赴任
    SKILL_ACQUISITION = "skill_acquisition"

    # Family events
    MARRIAGE = "marriage"
    CHILD_BIRTH = "child_birth"
    DIVORCE = "divorce"

    # Financial events
    SALARY_INCREASE = "salary_increase"
    SALARY_DECREASE = "salary_decrease"
    INHERITANCE = "inheritance"
    MARKET_CRASH = "market_crash"

    # Care events
    ELDER_CARE_START = "elder_care_start"
    ELDER_CARE_END = "elder_care_end"

    # Phase transition
    CAREER_PHASE_CHANGE = "career_phase_change"


class ActionTypeMiroFish(str, Enum):
    """3 new ActionTypes added to OASIS (v7 minimal extension)"""
    INTERNAL_MONOLOGUE = "internal_monologue"  # 内的独白
    CONSULT = "consult"                         # 双方向相談
    DECIDE = "decide"                           # 状態変更決断


# ============================================================
# Data models
# ============================================================

@dataclass
class FamilyMember:
    """Family member info (for blocker engine)"""
    relation: str          # spouse / child / parent
    age: int
    notes: str = ""        # e.g. "大学1年" or "要介護2"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BaseIdentity:
    """
    Immutable attributes set at simulation initialization.
    Derived from resume + Zep graph.
    """
    name: str
    age_at_start: int
    gender: str = ""
    education: str = ""                        # 最終学歴
    mbti: str = ""
    stable_traits: List[str] = field(default_factory=list)  # e.g. ["慎重", "分析的"]
    certifications: List[str] = field(default_factory=list)
    career_history_summary: str = ""           # 職歴要約

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActiveBlocker:
    """Currently active blocker"""
    blocker_type: BlockerType
    reason: str                    # Human-readable reason
    blocked_actions: List[str]     # What actions are blocked
    started_round: int
    expires_round: Optional[int] = None  # None = until condition changes

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["blocker_type"] = self.blocker_type.value
        return d


@dataclass
class CareerState:
    """
    Mutable attributes updated every round.
    Represents the agent's current life situation.
    """
    # Current round
    current_round: int = 0
    current_age: int = 30

    # Career
    role: str = ""                  # 現在の役職
    employer: str = ""              # 現在の勤務先
    industry: str = ""              # 業界
    years_in_role: int = 0
    salary_annual: int = 0          # 年収（万円）
    skills: List[str] = field(default_factory=list)

    # Family
    family: List[FamilyMember] = field(default_factory=list)
    marital_status: str = "single"  # single / married / divorced

    # Financial
    cash_buffer: int = 0            # 金融資産（万円）
    mortgage_remaining: int = 0     # ローン残額（万円）
    monthly_expenses: int = 0       # 月間支出（万円）

    # Stress & well-being
    stress_level: float = 0.3       # 0.0-1.0
    job_satisfaction: float = 0.5   # 0.0-1.0
    work_life_balance: float = 0.5  # 0.0-1.0

    # Active blockers
    blockers: List[ActiveBlocker] = field(default_factory=list)

    # Event log for this round
    events_this_round: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["blockers"] = [b.to_dict() for b in self.blockers]
        d["family"] = [f.to_dict() for f in self.family]
        return d

    def get_children(self) -> List[FamilyMember]:
        return [f for f in self.family if f.relation == "child"]

    def get_parents(self) -> List[FamilyMember]:
        return [f for f in self.family if f.relation == "parent"]

    def has_blocker(self, blocker_type: BlockerType) -> bool:
        return any(b.blocker_type == blocker_type for b in self.blockers)

    def is_action_blocked(self, action: str) -> bool:
        for b in self.blockers:
            if action in b.blocked_actions:
                return True
        return False


@dataclass
class LifeEvent:
    """A life event that occurred or is scheduled"""
    event_type: LifeEventType
    round_number: int
    description: str
    state_changes: Dict[str, Any] = field(default_factory=dict)
    probability: float = 1.0  # 1.0 = scheduled, <1.0 = probabilistic

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


@dataclass
class AgentSnapshot:
    """Snapshot of agent state at a specific round (for history tracking)"""
    round_number: int
    age: int
    role: str
    employer: str
    salary_annual: int
    cash_buffer: int
    stress_level: float
    active_blockers: List[str]
    events: List[str]
    internal_monologue: str = ""
    decision_made: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationPath:
    """One simulation path (3 paths run in parallel for multi-path)"""
    path_id: str
    path_label: str                # e.g. "現職継続", "転職", "起業"
    snapshots: List[AgentSnapshot] = field(default_factory=list)
    final_state: Optional[CareerState] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "path_label": self.path_label,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "final_state": self.final_state.to_dict() if self.final_state else None,
        }
