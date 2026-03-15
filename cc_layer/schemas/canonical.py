"""Canonical data models for MiroFish pipeline intermediate files.

All SubAgent output is normalized to these models before consumption
by report_html.py and other deterministic Python code.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Snapshot(BaseModel):
    """Canonical snapshot of career state at a point in time."""
    annual_income: float = 0          # 万円
    satisfaction: float = Field(default=0.5, ge=0, le=1)
    stress: float = Field(default=0.5, ge=0, le=1)
    work_life_balance: float = Field(default=0.5, ge=0, le=1)


class Event(BaseModel):
    """A career event within a period."""
    model_config = ConfigDict(extra="allow")
    type: str = ""
    description: str = ""
    probability: float | None = Field(default=None, ge=0, le=1)
    probability_note: str = ""


class Period(BaseModel):
    """A time period within a career path scenario."""
    model_config = ConfigDict(extra="allow")
    period_id: int | None = None
    period_name: str = ""
    narrative: str = ""
    snapshot: Snapshot = Field(default_factory=Snapshot)
    events: list[Event] = []


class Scenario(BaseModel):
    """A scenario branch within a path."""
    model_config = ConfigDict(extra="allow")
    scenario_id: str                  # "best" | "likely" | "base" | "worst"
    label: str
    probability: float = Field(ge=0, le=1)
    probability_note: str = ""
    periods: list[Period] = []
    final_state: Snapshot             # REQUIRED


class ExpandedPath(BaseModel):
    """A fully expanded career path with scenarios."""
    model_config = ConfigDict(extra="allow")  # 未知フィールド保持
    path_id: str
    label: str
    direction: str = ""
    risk: str = ""
    upside: str = ""
    score: float = 0
    overall_probability: float | None = None
    probability_rationale: str = ""
    common_periods: list[Period] = []
    branch_point: str = ""
    scenarios: list[Scenario] = []
    # path-level finals (for quick access)
    final_salary: float = 0
    final_satisfaction: float = 0
    final_age: int | None = None
    final_role: str = ""
    final_employer: str = ""
    final_cash_buffer: float = 0
    peak_salary: float = 0


class MultipathResult(BaseModel):
    """Top-level simulation result containing all paths."""
    model_config = ConfigDict(extra="allow")
    identity: dict = {}
    simulation_years: float = 10.0
    total_rounds: int = 40
    paths: list[ExpandedPath]
    ranking: list | dict = {}


class SwarmAction(BaseModel):
    """A single swarm agent action (post/comment)."""
    model_config = ConfigDict(extra="allow")
    round_num: int
    agent_id: int | str
    agent_name: str = ""
    role: str = ""
    action_type: str                  # CREATE_POST | CREATE_COMMENT
    action_args: dict = {}            # {"content": "...", "target_post_id": "..."}
    timestamp: str = ""


class SwarmAgent(BaseModel):
    """A swarm agent profile definition."""
    model_config = ConfigDict(extra="allow")
    agent_id: int | str
    name: str
    bio: str = ""
    role: str = ""
    category: str = ""
    personality: str = ""
    speaking_style: str = ""
    background: str = ""
    stance: str = "neutral"
    path_ref: str = ""
    is_copy_agent: bool = False


class FactCheckItem(BaseModel):
    """A single fact-check result."""
    model_config = ConfigDict(extra="allow")
    claim_id: str = ""
    location: str = ""
    original_value: str | float = ""
    original_note: str = ""
    status: str = ""                  # verified | adjusted | unverified | disputed
    verified_value: str = ""
    sources: list[dict] = []
    note: str = ""
    suggested_correction: dict = {}


class FactCheckResult(BaseModel):
    """Aggregated fact-check results."""
    model_config = ConfigDict(extra="allow")
    fact_check_metadata: dict = {}
    checks: list[FactCheckItem] = []


class MacroTrend(BaseModel):
    """A macro-economic/social trend."""
    model_config = ConfigDict(extra="allow")
    trend_id: str
    label: str
    category: str = ""
    description: str = ""
    probability: float = Field(default=0.5, ge=0, le=1)
    timeframe: str = ""
    impact_by_path: dict = {}
    sources: list[dict] = []


class MacroTrends(BaseModel):
    """Collection of macro trends and salary benchmarks."""
    model_config = ConfigDict(extra="allow")
    trends: list[MacroTrend] = []
    salary_benchmarks: list[dict] = []
