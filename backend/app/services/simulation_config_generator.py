"""
Intelligent simulation config generator
Uses LLM to auto-generate detailed simulation parameters from requirements, documents, and graph info
Fully automated, no manual parameter setup needed

Uses step-by-step generation to avoid overly long outputs:
1. Generate time config
2. Generate event config
3. Generate agent configs in batches
4. Generate platform config
"""

import json
import math
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, ZepEntityReader
from .oasis_profile_generator import OasisAgentProfile

logger = get_logger('mirofish.simulation_config')

# Work-hours-based activity time settings (for career simulation)
WORK_HOURS_CONFIG = {
    # Nighttime (no activity)
    "dead_hours": [0, 1, 2, 3, 4, 5, 22, 23],
    # Morning hours (before work)
    "morning_hours": [6, 7, 8],
    # Work hours (most active - recruitment, interviews, evaluations happen here)
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    # Evening (activity decreases)
    "peak_hours": [19, 20, 21],
    # Activity coefficients
    "activity_multipliers": {
        "dead": 0.05,      # Almost no activity at night
        "morning": 0.8,    # Morning: commute prep, email check, etc.
        "work": 1.5,       # Work hours most active (interviews, evaluations, meetings)
        "peak": 0.3,       # Evening: activity decreases
        "night": 0.05      # Late night: almost none
    }
}


@dataclass
class AgentActivityConfig:
    """Single agent activity config"""
    agent_id: int
    entity_uuid: str
    entity_name: str
    entity_type: str
    
    # Activity level (0.0-1.0)
    activity_level: float = 0.5  # Overall activity level
    
    # Posting frequency (expected posts per hour)
    posts_per_hour: float = 1.0
    comments_per_hour: float = 2.0
    
    # Active hours (24h format, 0-23)
    active_hours: List[int] = field(default_factory=lambda: list(range(8, 23)))
    
    # Response speed (reaction delay to hot events, in simulated minutes)
    response_delay_min: int = 5
    response_delay_max: int = 60
    
    # Sentiment bias (-1.0 negative to 1.0 positive)
    sentiment_bias: float = 0.0
    
    # Stance (attitude toward specific topics)
    stance: str = "neutral"  # supportive, opposing, neutral, observer
    
    # Influence weight (probability of posts being seen by other agents)
    influence_weight: float = 1.0


@dataclass  
class TimeSimulationConfig:
    """Time simulation config"""
    # Total simulation duration (simulated hours)
    total_simulation_hours: int = 72  # Default 72 hours (3 days)
    
    # Time per round (simulated minutes) - default 60 min (1 hour)
    minutes_per_round: int = 60
    
    # Agent activation count per hour range
    agents_per_hour_min: int = 5
    agents_per_hour_max: int = 20
    
    # Peak hours (evening 19-22)
    peak_hours: List[int] = field(default_factory=lambda: [19, 20, 21, 22])
    peak_activity_multiplier: float = 1.5
    
    # Off-peak hours (midnight 0-5, minimal activity)
    off_peak_hours: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    off_peak_activity_multiplier: float = 0.05  # Very low late-night activity
    
    # Morning hours
    morning_hours: List[int] = field(default_factory=lambda: [6, 7, 8])
    morning_activity_multiplier: float = 0.4
    
    # Work hours
    work_hours: List[int] = field(default_factory=lambda: [9, 10, 11, 12, 13, 14, 15, 16, 17, 18])
    work_activity_multiplier: float = 0.7


@dataclass
class CareerPhase:
    """Career timeline phase for future simulation"""
    phase_id: int  # 1=current, 2=short-term, 3=mid-term
    phase_name: str  # e.g. "現在の評価", "1-2年後", "3-5年後"
    trigger_round: int  # Round number when this phase activates
    scenario_description: str  # What changed in this phase
    evaluation_focus: str  # What evaluators should focus on
    career_developments: List[str] = field(default_factory=list)  # Key changes
    injected_posts: List[Dict[str, Any]] = field(default_factory=list)  # Phase trigger posts


@dataclass
class EventConfig:
    """Event config"""
    # Initial events (trigger events at simulation start)
    initial_posts: List[Dict[str, Any]] = field(default_factory=list)

    # Timed events (events triggered at specific times)
    scheduled_events: List[Dict[str, Any]] = field(default_factory=list)

    # Hot topic keywords
    hot_topics: List[str] = field(default_factory=list)

    # Narrative direction
    narrative_direction: str = ""

    # Career timeline phases (future simulation)
    career_phases: List[CareerPhase] = field(default_factory=list)


@dataclass
class PlatformConfig:
    """Platform-specific config"""
    platform: str  # twitter or reddit
    
    # Recommendation algorithm weights
    recency_weight: float = 0.4  # Time freshness
    popularity_weight: float = 0.3  # Popularity
    relevance_weight: float = 0.3  # Relevance
    
    # Viral threshold (interactions needed to trigger spread)
    viral_threshold: int = 10
    
    # Echo chamber strength (degree of similar opinion clustering)
    echo_chamber_strength: float = 0.5


@dataclass
class SimulationParameters:
    """Full simulation parameter config"""
    # Basic info
    simulation_id: str
    project_id: str
    graph_id: str
    simulation_requirement: str
    
    # Time config
    time_config: TimeSimulationConfig = field(default_factory=TimeSimulationConfig)
    
    # Agent config list
    agent_configs: List[AgentActivityConfig] = field(default_factory=list)
    
    # Event config
    event_config: EventConfig = field(default_factory=EventConfig)
    
    # Platform config
    twitter_config: Optional[PlatformConfig] = None
    reddit_config: Optional[PlatformConfig] = None
    
    # LLM config
    llm_model: str = ""
    llm_base_url: str = ""
    
    # Generation metadata
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    generation_reasoning: str = ""  # LLM reasoning explanation
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        time_dict = asdict(self.time_config)
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "time_config": time_dict,
            "agent_configs": [asdict(a) for a in self.agent_configs],
            "event_config": asdict(self.event_config),
            "twitter_config": asdict(self.twitter_config) if self.twitter_config else None,
            "reddit_config": asdict(self.reddit_config) if self.reddit_config else None,
            "llm_model": self.llm_model,
            "llm_base_url": self.llm_base_url,
            "generated_at": self.generated_at,
            "generation_reasoning": self.generation_reasoning,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class SimulationConfigGenerator:
    """
    Simulation config intelligent generator
    
    Uses LLM to analyze simulation requirements, document content, and graph entity info,
    Auto-generate optimal simulation parameter config
    
    Uses step-by-step generation strategy:
    1. Generate time config and event config (lightweight)
    2. Batch generate Agent configs (10-20 per batch)
    3. Generate platform config
    """
    
    # Max context characters
    MAX_CONTEXT_LENGTH = 50000
    # Agents per batch
    AGENTS_PER_BATCH = 15
    
    # Context truncation length per step (characters)
    TIME_CONFIG_CONTEXT_LENGTH = 10000   # Time config
    EVENT_CONFIG_CONTEXT_LENGTH = 8000   # Event config
    ENTITY_SUMMARY_LENGTH = 300          # Entity summary
    AGENT_SUMMARY_LENGTH = 300           # Entity summary in agent config
    ENTITIES_PER_TYPE_DISPLAY = 20       # Entities to display per type
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        # シナリオ設計・フェーズ生成は品質重視 → チャットモデル（gpt-5.4）を使用
        self.model_name = model_name or getattr(Config, 'LLM_CHAT_MODEL_NAME', None) or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        profiles: Optional[List['OasisAgentProfile']] = None,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> SimulationParameters:
        """
        Intelligently generate complete simulation config (step by step)
        
        Args:
            simulation_id: Simulation ID
            project_id: Project ID
            graph_id: Graph ID
            simulation_requirement: Simulation requirement description
            document_text: Original document content
            entities: Filtered entity list
            enable_twitter: Whether to enable Twitter
            enable_reddit: Whether to enable Reddit
            progress_callback: Progress callback(current_step, total_steps, message)
            
        Returns:
            SimulationParameters: Complete simulation parameters
        """
        logger.info(f"Starting intelligent config generation: simulation_id={simulation_id}, entities={len(entities)}")
        
        # Calculate total steps
        num_batches = math.ceil(len(entities) / self.AGENTS_PER_BATCH)
        total_steps = 3 + num_batches  # time config + event config + N batches of agents + platform config
        current_step = 0
        
        def report_progress(step: int, message: str):
            nonlocal current_step
            current_step = step
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")
        
        # 1. Build base context info
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities
        )
        
        reasoning_parts = []
        
        # ========== Step 1: Generate time config ==========
        report_progress(1, "Generating time config...")
        num_entities = len(entities)
        time_config_result = self._generate_time_config(context, num_entities)
        time_config = self._parse_time_config(time_config_result, num_entities)
        reasoning_parts.append(f"Time config: {time_config_result.get('reasoning', 'success')}")
        
        # ========== Step 2: Generate event config ==========
        report_progress(2, "Generating event config and hot topics...")
        event_config_result = self._generate_event_config(context, simulation_requirement, entities)
        # Calculate total rounds for phase trigger timing
        total_hours = time_config.total_simulation_hours
        minutes_per_round = time_config.minutes_per_round
        total_rounds = (total_hours * 60) // minutes_per_round
        event_config = self._parse_event_config(event_config_result, total_rounds=total_rounds)
        reasoning_parts.append(f"Event config: {event_config_result.get('reasoning', 'success')}")
        if event_config.career_phases:
            phase_info = ", ".join([f"{p.phase_name}(round {p.trigger_round})" for p in event_config.career_phases])
            reasoning_parts.append(f"Career phases: {phase_info}")
        
        # ========== Steps 3-N: Batch generate Agent configs ==========
        all_agent_configs = []
        if profiles:
            # New architecture: generate configs from HR agent profiles
            num_batches = math.ceil(len(profiles) / self.AGENTS_PER_BATCH)
            total_steps = 3 + num_batches
            for batch_idx in range(num_batches):
                start_idx = batch_idx * self.AGENTS_PER_BATCH
                end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(profiles))
                batch_profiles = profiles[start_idx:end_idx]

                report_progress(
                    3 + batch_idx,
                    f"Generating Agent configs ({start_idx + 1}-{end_idx}/{len(profiles)})..."
                )

                batch_configs = self._generate_agent_configs_from_profiles(
                    profiles=batch_profiles,
                    simulation_requirement=simulation_requirement
                )
                all_agent_configs.extend(batch_configs)
        else:
            # Legacy: generate configs from graph entities
            for batch_idx in range(num_batches):
                start_idx = batch_idx * self.AGENTS_PER_BATCH
                end_idx = min(start_idx + self.AGENTS_PER_BATCH, len(entities))
                batch_entities = entities[start_idx:end_idx]

                report_progress(
                    3 + batch_idx,
                    f"Generating Agent configs ({start_idx + 1}-{end_idx}/{len(entities)})..."
                )

                batch_configs = self._generate_agent_configs_batch(
                    entities=batch_entities,
                    start_idx=start_idx,
                    simulation_requirement=simulation_requirement
                )
                all_agent_configs.extend(batch_configs)

        reasoning_parts.append(f"Agent configs: successfully generated {len(all_agent_configs)}")
        
        # ========== Assign publisher agents for initial posts ==========
        logger.info("Assigning suitable publisher agents for initial posts...")
        event_config = self._assign_initial_post_agents(event_config, all_agent_configs)
        assigned_count = len([p for p in event_config.initial_posts if p.get("poster_agent_id") is not None])
        reasoning_parts.append(f"Initial post assignment: {assigned_count} posts assigned publishers")

        # ========== Assign publisher agents for career phase posts ==========
        for phase in event_config.career_phases:
            if phase.injected_posts:
                phase.injected_posts = self._assign_poster_agent_ids(phase.injected_posts, all_agent_configs)
        # Also update scheduled_events with assigned agent IDs
        for evt in event_config.scheduled_events:
            if evt.get("posts"):
                evt["posts"] = self._assign_poster_agent_ids(evt["posts"], all_agent_configs)
        
        # ========== Final step: Generate platform config ==========
        report_progress(total_steps, "Generating platform config...")
        twitter_config = None
        reddit_config = None
        
        if enable_twitter:
            twitter_config = PlatformConfig(
                platform="twitter",
                recency_weight=0.4,
                popularity_weight=0.3,
                relevance_weight=0.3,
                viral_threshold=10,
                echo_chamber_strength=0.5
            )
        
        if enable_reddit:
            reddit_config = PlatformConfig(
                platform="reddit",
                recency_weight=0.3,
                popularity_weight=0.4,
                relevance_weight=0.3,
                viral_threshold=15,
                echo_chamber_strength=0.6
            )
        
        # Build final parameters
        params = SimulationParameters(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            time_config=time_config,
            agent_configs=all_agent_configs,
            event_config=event_config,
            twitter_config=twitter_config,
            reddit_config=reddit_config,
            llm_model=self.model_name,
            llm_base_url=self.base_url,
            generation_reasoning=" | ".join(reasoning_parts)
        )
        
        logger.info(f"Simulation config generation complete: {len(params.agent_configs)} Agent configs")
        
        return params
    
    def _build_context(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode]
    ) -> str:
        """Build LLM context, truncated to max length"""
        
        # Entity summary
        entity_summary = self._summarize_entities(entities)
        
        # Build context
        context_parts = [
            f"## Simulation Requirement\n{simulation_requirement}",
            f"\n## Entity Info ({len(entities)} entities)\n{entity_summary}",
        ]
        
        current_length = sum(len(p) for p in context_parts)
        remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500  # Reserve 500 char margin
        
        if remaining_length > 0 and document_text:
            doc_text = document_text[:remaining_length]
            if len(document_text) > remaining_length:
                doc_text += "\n...(document truncated)"
            context_parts.append(f"\n## Original Document Content\n{doc_text}")
        
        return "\n".join(context_parts)
    
    def _summarize_entities(self, entities: List[EntityNode]) -> str:
        """Generate entity summary"""
        lines = []
        
        # Group by type
        by_type: Dict[str, List[EntityNode]] = {}
        for e in entities:
            t = e.get_entity_type() or "Unknown"
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(e)
        
        for entity_type, type_entities in by_type.items():
            lines.append(f"\n### {entity_type} ({len(type_entities)} entities)")
            # Use configured display count and summary length
            display_count = self.ENTITIES_PER_TYPE_DISPLAY
            summary_len = self.ENTITY_SUMMARY_LENGTH
            for e in type_entities[:display_count]:
                summary_preview = (e.summary[:summary_len] + "...") if len(e.summary) > summary_len else e.summary
                lines.append(f"- {e.name}: {summary_preview}")
            if len(type_entities) > display_count:
                lines.append(f"  ... and {len(type_entities) - display_count} more")
        
        return "\n".join(lines)
    
    def _call_llm_with_retry(self, prompt: str, system_prompt: str) -> Dict[str, Any]:
        """LLM call with retry, includes JSON fix logic"""
        import re
        
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    # gpt-5-mini does not support custom temperature
                )
                
                content = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason
                
                # Check if truncated
                if finish_reason == 'length':
                    logger.warning(f"LLM output truncated (attempt {attempt+1})")
                    content = self._fix_truncated_json(content)
                
                # Try to parse JSON
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed (attempt {attempt+1}): {str(e)[:80]}")
                    
                    # Try to fix JSON
                    fixed = self._try_fix_config_json(content)
                    if fixed:
                        return fixed
                    
                    last_error = e
                    
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt+1}): {str(e)[:80]}")
                last_error = e
                import time
                time.sleep(2 * (attempt + 1))
        
        raise last_error or Exception("LLM call failed")
    
    def _fix_truncated_json(self, content: str) -> str:
        """Fix truncated JSON"""
        content = content.strip()
        
        # Count unclosed brackets
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')
        
        # Check for unclosed strings
        if content and content[-1] not in '",}]':
            content += '"'
        
        # Close brackets
        content += ']' * open_brackets
        content += '}' * open_braces
        
        return content
    
    def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Try to fix config JSON"""
        import re
        
        # Fix truncated cases
        content = self._fix_truncated_json(content)
        
        # Extract JSON part
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            json_str = json_match.group()
            
            # Remove newlines in strings
            def fix_string(match):
                s = match.group(0)
                s = s.replace('\n', ' ').replace('\r', ' ')
                s = re.sub(r'\s+', ' ', s)
                return s
            
            json_str = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', fix_string, json_str)
            
            try:
                return json.loads(json_str)
            except:
                # Try to remove all control characters
                json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', json_str)
                json_str = re.sub(r'\s+', ' ', json_str)
                try:
                    return json.loads(json_str)
                except:
                    pass
        
        return None
    
    def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
        """Generate time config"""
        # Use configured context truncation length
        context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
        
        # Calculate max allowed value (90% of agent count)
        max_agents_allowed = max(1, int(num_entities * 0.9))
        
        prompt = f"""Based on the following simulation requirement, generate time simulation config.

{context_truncated}

## Task
Please generate time config JSON.

### Basic principles (for reference only, adjust flexibly based on event and participant groups):
- User group is Chinese, must follow Beijing time daily routine
- 0-5 AM almost no activity（activity coefficient0.05）
- 6-8 AM gradually active (activity coefficient 0.4)
- 9-18 work hours moderately active (activity coefficient 0.7)
- 19-22 evening peak hours (activity coefficient 1.5)
- After 23:00 activity decreases (activity coefficient 0.5)
- General pattern: low activity at dawn, gradually increasing in morning, moderate during work hours, peak in evening
- **Important**: Example values below are for reference only, adjust specific time periods based on event nature and participant group characteristics
  - e.g.: Student peak may be 21-23; media active all day; officials only during work hours
  - e.g.: Breaking news may cause late-night discussion, off_peak_hours can be shortened

### Return JSON format (no markdown)

Example:
{{
    "total_simulation_hours": 72,
    "minutes_per_round": 60,
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 50,
    "peak_hours": [19, 20, 21, 22],
    "off_peak_hours": [0, 1, 2, 3, 4, 5],
    "morning_hours": [6, 7, 8],
    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "reasoning": "Time configuration explanation for this event"
}}

Field descriptions:
- total_simulation_hours (int): Total simulation duration, 24-168 hours, shorter for breaking events, longer for sustained topics
- minutes_per_round (int): Duration per round, 30-120 minutes, recommended 60 minutes
- agents_per_hour_min (int): Min agents activated per hour (range: 1-{max_agents_allowed}）
- agents_per_hour_max (int): Max agents activated per hour (range: 1-{max_agents_allowed}）
- peak_hours (int array): Peak hours, adjust based on event participant groups
- off_peak_hours (int array): Off-peak hours, usually late night/early morning
- morning_hours (int array): Morning hours
- work_hours (int array): Work hours
- reasoning (string): Brief explanation for this configuration"""

        system_prompt = "あなたはキャリアシミュレーションの専門家です。純粋なJSON形式で返してください。時間設定はビジネスアワー（9-18時）をピークとする勤務時間ベースにしてください。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Time config LLM generation failed: {e}, using defaults")
            return self._get_default_time_config(num_entities)
    
    def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
        """Get default time config"""
        return {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,  # 1 hour per round, faster time flow
            "agents_per_hour_min": max(1, num_entities // 15),
            "agents_per_hour_max": max(5, num_entities // 5),
            "peak_hours": [19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
            "reasoning": "Using default config (1 hour per round)"
        }
    
    def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
        """Parse time config result, validate agents_per_hour does not exceed total agent count"""
        # Get raw values
        agents_per_hour_min = result.get("agents_per_hour_min", max(1, num_entities // 15))
        agents_per_hour_max = result.get("agents_per_hour_max", max(5, num_entities // 5))
        
        # Validate and fix: ensure not exceeding total agent count
        if agents_per_hour_min > num_entities:
            logger.warning(f"agents_per_hour_min ({agents_per_hour_min}) exceeds total agents ({num_entities}), corrected")
            agents_per_hour_min = max(1, num_entities // 10)
        
        if agents_per_hour_max > num_entities:
            logger.warning(f"agents_per_hour_max ({agents_per_hour_max}) exceeds total agents ({num_entities}), corrected")
            agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
        
        # Ensure min < max
        if agents_per_hour_min >= agents_per_hour_max:
            agents_per_hour_min = max(1, agents_per_hour_max // 2)
            logger.warning(f"agents_per_hour_min >= max, corrected to {agents_per_hour_min}")
        
        return TimeSimulationConfig(
            total_simulation_hours=result.get("total_simulation_hours", 72),
            minutes_per_round=result.get("minutes_per_round", 60),  # Default 1 hour per round
            agents_per_hour_min=agents_per_hour_min,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=result.get("peak_hours", [19, 20, 21, 22]),
            off_peak_hours=result.get("off_peak_hours", [0, 1, 2, 3, 4, 5]),
            off_peak_activity_multiplier=0.05,  # Almost no one at midnight
            morning_hours=result.get("morning_hours", [6, 7, 8]),
            morning_activity_multiplier=0.4,
            work_hours=result.get("work_hours", list(range(9, 19))),
            work_activity_multiplier=0.7,
            peak_activity_multiplier=1.5
        )
    
    def _generate_event_config(
        self, 
        context: str, 
        simulation_requirement: str,
        entities: List[EntityNode]
    ) -> Dict[str, Any]:
        """Generate event config"""
        
        # List representative entity names per type
        type_examples = {}
        for e in entities:
            etype = e.get_entity_type() or "Unknown"
            if etype not in type_examples:
                type_examples[etype] = []
            if len(type_examples[etype]) < 3:
                type_examples[etype].append(e.name)
        
        type_info = "\n".join([
            f"- {t}: {', '.join(examples)}" 
            for t, examples in type_examples.items()
        ])
        
        # Use configured context truncation length
        context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
        
        prompt = f"""Based on the following career simulation requirement, generate the evaluation scenario config.

Simulation requirement: {simulation_requirement}

{context_truncated}

## Available stakeholder types and examples
{type_info}

## Task
This is an **HR Career Simulator**. Each stakeholder evaluates a candidate's resume from their professional perspective.

Please generate the evaluation scenario config JSON:
- Extract key career evaluation topics (skills, experience, market fit, etc.)
- Describe the evaluation direction (how stakeholders will assess this candidate)
- Design initial evaluation statements. Each statement is a stakeholder's professional assessment or feedback about the candidate.

**重要ルール**:
- poster_type must be selected from "Available stakeholder types" above
- 内容は**キャリア評価**に関するものであること。SNS的な投稿や「一緒に働きましょう」のような勧誘メッセージは不可
- 辞めた企業からの復帰勧誘のような非現実的なシナリオは生成しない
- ステークホルダーは3カテゴリに分かれ、それぞれ異なる視点で評価する:
  * 【選考する側】（採用担当・人事マネージャー・現場マネージャー・経営層）: 「採るか採らないか」の判断。書類選考所見、面接での懸念点、オファー条件の考慮
  * 【仲介・助言する側】（キャリアアドバイザー・ヘッドハンター・コーチ）: 市場価値の見立て、マッチする求人候補、面接対策の助言
  * 【観察・分析する側】（同職種Topプレイヤー・研究者・ジャーナリスト・元同僚・元クライアント）: 業界内での相対的評価、労働市場トレンドとの整合性、客観的な所見
- **元同僚・元上司・前職企業からの発言は「証言・リファレンス」形式であること**:
  * 「彼は○○プロジェクトでこういう仕事をしていた」「あのときの判断力は評価できる」「チームマネジメントでこういう課題があった」等の実体験に基づく証言
  * 退職済み企業からの復帰勧誘は不可だが、元同僚としての業務実態の証言・評価は積極的に含めること
  * 候補者の経歴に記載された企業名が poster_type にある場合、その企業の「元同僚」視点でリファレンス的な発言を生成すること
- **クライアント企業からの発言は「発注者評価」形式であること**:
  * 候補者にサービスを依頼した側として、成果物の品質・納期・コミュニケーション・提案力を評価
  * 「○○案件で依頼した際の成果は期待以上だった」「提案力は高いがレスポンスに課題があった」等の具体的なフィードバック
  * リピート発注の意向や他ベンダーとの比較も含めること
- **同職種のTopプレイヤーからの発言は「業界基準との比較」形式であること**:
  * 同職種の最高水準から見た候補者のスキルレベル・実績の相対評価
  * 「この分野で一流になるには○○が必要」「候補者の○○は業界平均以上だが、トップ層には○○が不足」等

Return JSON format (no markdown)：
{{
    "hot_topics": ["evaluation_topic1", "evaluation_topic2", ...],
    "narrative_direction": "<career evaluation direction: how stakeholders assess this candidate>",
    "initial_posts": [
        {{"content": "Professional evaluation statement from this stakeholder's perspective", "poster_type": "Stakeholder type (must select from available types)"}},
        ...
    ],
    "career_phases": [
        {{
            "phase_id": 1,
            "phase_name": "現在の評価",
            "scenario_description": "候補者の現時点での経歴・スキルに対する各ステークホルダーの評価",
            "evaluation_focus": "現在のスキルセット、職歴の妥当性、市場価値の現状分析",
            "career_developments": ["現職での実績", "保有スキルの市場評価"],
            "injected_posts": [
                {{"content": "Phase 1の評価コメント", "poster_type": "利用可能なタイプから選択"}}
            ]
        }},
        {{
            "phase_id": 2,
            "phase_name": "1-2年後の予測",
            "scenario_description": "候補者が転職・スキルアップした1-2年後の想定シナリオ。具体的な成長仮説を立てる",
            "evaluation_focus": "短期的なキャリア成長の可能性、転職先でのフィット、スキルギャップの解消見込み",
            "career_developments": ["想定される転職先での成果", "新スキル習得の見込み", "市場価値の変化"],
            "injected_posts": [
                {{"content": "1-2年後の想定に基づく評価コメント。『もし○○に転職して△△を経験すれば...』のような仮説ベース", "poster_type": "利用可能なタイプから選択"}}
            ]
        }},
        {{
            "phase_id": 3,
            "phase_name": "3-5年後の展望",
            "scenario_description": "候補者のキャリアパスの分岐点。複数の可能性と到達点を予測",
            "evaluation_focus": "中長期のキャリア天井、マネジメント vs スペシャリスト、業界変化への適応力",
            "career_developments": ["キャリアパスA: マネジメント路線", "キャリアパスB: 専門特化路線", "業界トレンドとの整合性"],
            "injected_posts": [
                {{"content": "3-5年後の展望に基づく評価。『この方向に進めば○○クラスの人材になれる』のような将来予測", "poster_type": "利用可能なタイプから選択"}}
            ]
        }}
    ],
    "reasoning": "<brief explanation>"
}}

**career_phases のルール**:
- 必ず3フェーズ（現在→1-2年後→3-5年後）を生成すること
- 各フェーズの injected_posts は3-5件。フェーズが進むにつれ「予測」「仮説」「分岐シナリオ」の要素が増える
- Phase 2以降は具体的な仮説（「もし○○すれば」「△△を経験した場合」）に基づく評価
- Phase 3では複数のキャリアパス分岐を提示し、それぞれの到達点をステークホルダーが評価
- poster_type は available stakeholder types から選択すること"""

        system_prompt = "あなたはHRキャリアシミュレーションの専門家です。候補者の履歴書に対する各ステークホルダーの専門的評価を生成してください。純粋なJSON形式で返してください。poster_type は利用可能なステークホルダータイプと正確に一致させてください。SNS的な投稿や勧誘メッセージではなく、採用・評価の文脈に沿った専門的コメントを生成すること。"
        
        try:
            return self._call_llm_with_retry(prompt, system_prompt)
        except Exception as e:
            logger.warning(f"Event config LLM generation failed: {e}, using defaults")
            return {
                "hot_topics": [],
                "narrative_direction": "",
                "initial_posts": [],
                "reasoning": "Using default config"
            }
    
    def _parse_event_config(self, result: Dict[str, Any], total_rounds: int = 72) -> EventConfig:
        """Parse event config result"""
        # Parse career phases
        career_phases = []
        raw_phases = result.get("career_phases", [])
        for phase_data in raw_phases:
            phase_id = phase_data.get("phase_id", 1)
            # Calculate trigger round: Phase 1 = round 0, Phase 2 = 1/3, Phase 3 = 2/3
            if phase_id == 1:
                trigger_round = 0
            elif phase_id == 2:
                trigger_round = total_rounds // 3
            else:
                trigger_round = (total_rounds * 2) // 3

            career_phases.append(CareerPhase(
                phase_id=phase_id,
                phase_name=phase_data.get("phase_name", f"Phase {phase_id}"),
                trigger_round=trigger_round,
                scenario_description=phase_data.get("scenario_description", ""),
                evaluation_focus=phase_data.get("evaluation_focus", ""),
                career_developments=phase_data.get("career_developments", []),
                injected_posts=phase_data.get("injected_posts", []),
            ))

        # Build scheduled_events from career phases (Phase 2 and 3)
        scheduled_events = []
        for phase in career_phases:
            if phase.phase_id > 1:
                scheduled_events.append({
                    "trigger_round": phase.trigger_round,
                    "phase_id": phase.phase_id,
                    "phase_name": phase.phase_name,
                    "scenario_description": phase.scenario_description,
                    "evaluation_focus": phase.evaluation_focus,
                    "career_developments": phase.career_developments,
                    "posts": phase.injected_posts,
                })

        return EventConfig(
            initial_posts=result.get("initial_posts", []),
            scheduled_events=scheduled_events,
            hot_topics=result.get("hot_topics", []),
            narrative_direction=result.get("narrative_direction", ""),
            career_phases=career_phases,
        )
    
    def _assign_initial_post_agents(
        self,
        event_config: EventConfig,
        agent_configs: List[AgentActivityConfig]
    ) -> EventConfig:
        """
        Assign suitable publisher agents for initial posts

        Match the most suitable agent_id based on each post's poster_type.
        Uses role_category (gatekeeper/agent/researcher) for HR architecture alignment.
        """
        if not event_config.initial_posts:
            return event_config

        # Build agent index by entity_type
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        agents_by_role: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)

        # Type mapping table (handle different formats LLM may output)
        # Includes HR role_category mappings
        type_aliases = {
            "official": ["official", "university", "governmentagency", "government"],
            "university": ["university", "official"],
            "mediaoutlet": ["mediaoutlet", "media"],
            "student": ["student", "person"],
            "professor": ["professor", "expert", "teacher"],
            "alumni": ["alumni", "person"],
            "organization": ["organization", "ngo", "company", "group"],
            "person": ["person", "student", "alumni"],
            # HR role_category mappings
            "gatekeeper": ["gatekeeper", "recruiter", "hr_manager"],
            "agent": ["agent", "career_advisor", "headhunter", "coach"],
            "researcher": ["researcher", "economist", "journalist", "top_player", "colleague", "client"],
        }
        
        # Track used agent index per type, avoid reusing same agent
        used_indices: Dict[str, int] = {}
        
        updated_posts = []
        for post in event_config.initial_posts:
            poster_type = post.get("poster_type", "").lower()
            content = post.get("content", "")
            
            # Try to find matching agent
            matched_agent_id = None
            
            # 1. Direct match
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1
            else:
                # 2. Match using aliases
                for alias_key, aliases in type_aliases.items():
                    if poster_type in aliases or alias_key == poster_type:
                        for alias in aliases:
                            if alias in agents_by_type:
                                agents = agents_by_type[alias]
                                idx = used_indices.get(alias, 0) % len(agents)
                                matched_agent_id = agents[idx].agent_id
                                used_indices[alias] = idx + 1
                                break
                    if matched_agent_id is not None:
                        break
            
            # 3. If still not found, use highest influence agent
            if matched_agent_id is None:
                logger.warning(f"No matching Agent found for type '{poster_type}', using highest influence Agent")
                if agent_configs:
                    # Sort by influence, select highest
                    sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                    matched_agent_id = sorted_agents[0].agent_id
                else:
                    matched_agent_id = 0
            
            updated_posts.append({
                "content": content,
                "poster_type": post.get("poster_type", "Unknown"),
                "poster_agent_id": matched_agent_id
            })
            
            logger.info(f"Initial post assignment: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
        
        event_config.initial_posts = updated_posts
        return event_config

    def _assign_poster_agent_ids(
        self,
        posts: List[Dict[str, Any]],
        agent_configs: List[AgentActivityConfig]
    ) -> List[Dict[str, Any]]:
        """Assign agent_ids to a list of posts based on poster_type"""
        if not posts or not agent_configs:
            return posts

        # Build agent index by entity_type
        agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
        for agent in agent_configs:
            etype = agent.entity_type.lower()
            if etype not in agents_by_type:
                agents_by_type[etype] = []
            agents_by_type[etype].append(agent)

        used_indices: Dict[str, int] = {}
        updated = []
        for post in posts:
            poster_type = post.get("poster_type", "").lower()
            matched_agent_id = None

            # 1. Exact entity_type match
            if poster_type in agents_by_type:
                agents = agents_by_type[poster_type]
                idx = used_indices.get(poster_type, 0) % len(agents)
                matched_agent_id = agents[idx].agent_id
                used_indices[poster_type] = idx + 1

            # 2. Last resort: highest influence agent
            if matched_agent_id is None and agent_configs:
                sorted_agents = sorted(agent_configs, key=lambda a: a.influence_weight, reverse=True)
                matched_agent_id = sorted_agents[0].agent_id

            updated.append({
                **post,
                "poster_agent_id": matched_agent_id if matched_agent_id is not None else 0,
            })
        return updated

    def _generate_agent_configs_from_profiles(
        self,
        profiles: List['OasisAgentProfile'],
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Generate Agent configs from HR agent profiles (new architecture)"""

        # Build profile info for LLM
        profile_list = []
        for p in profiles:
            role_category = getattr(p, "role_category", None) or p.source_entity_type or "researcher"
            profile_list.append({
                "agent_id": p.user_id,
                "name": p.name,
                "role_category": role_category,
                "profession": p.profession or "",
                "bio": p.bio[:200] if p.bio else ""
            })

        prompt = f"""以下のHRキャリアシミュレーションのエージェント情報を基に、各エージェントのキャリア活動設定を生成してください。

シミュレーション要件: {simulation_requirement}

## エージェントリスト
```json
{json.dumps(profile_list, ensure_ascii=False, indent=2)}
```

## role_category別の活動パターン
- **gatekeeper**（採用担当/人事）: 中活動(0.3-0.5)、ビジネスアワー(9-18)、応答遅め(30-120分)、高影響力(2.0-3.0)、stance=neutral
- **agent**（キャリアアドバイザー/ヘッドハンター）: 高活動(0.5-0.7)、長時間(8-21)、応答速め(10-60分)、中影響力(1.5-2.0)、stance=supportive
- **researcher**（元同僚/クライアント/Topプレイヤー/エコノミスト）: 低〜中活動(0.2-0.5)、不規則(10-22)、応答遅め(30-180分)、中影響力(1.0-2.0)、stance=neutral/observer

候補者ミラー（agent_id=0）は特別:
- 低活動(0.2)、応答速め(5-30分)、影響力中(1.5)、stance=neutral

Return JSON format (no markdown):
{{
    "agent_configs": [
        {{
            "agent_id": <Must match input>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <Post frequency>,
            "comments_per_hour": <Comment frequency>,
            "active_hours": [<Active hours list>],
            "response_delay_min": <Min response delay in minutes>,
            "response_delay_max": <Max response delay in minutes>,
            "sentiment_bias": <-1.0 to 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <Influence weight>
        }},
        ...
    ]
}}"""

        system_prompt = "あなたはキャリアシミュレーションの行動分析専門家です。純粋なJSONを返してください。role_categoryに基づいた活動パターンを厳密に守ってください。"

        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Profile-based agent config LLM generation failed: {e}, using rule-based generation")
            llm_configs = {}

        # Build AgentActivityConfig objects
        configs = []
        for profile in profiles:
            agent_id = profile.user_id
            cfg = llm_configs.get(agent_id, {})
            role_category = getattr(profile, "role_category", None) or profile.source_entity_type or "researcher"

            # If LLM did not generate, use role_category-based rules
            if not cfg:
                cfg = self._generate_agent_config_by_role_category(role_category, agent_id)

            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=profile.source_entity_uuid or "",
                entity_name=profile.name,
                entity_type=role_category,
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 18))),
                response_delay_min=cfg.get("response_delay_min", 15),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)

        return configs

    def _generate_agent_config_by_role_category(self, role_category: str, agent_id: int) -> Dict[str, Any]:
        """Generate agent config by role_category (HR architecture)"""
        if agent_id == 0:
            # Candidate mirror: passive, responds to evaluations
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.5,
                "active_hours": list(range(9, 22)),
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.5
            }
        elif role_category == "gatekeeper":
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.2,
                "comments_per_hour": 0.3,
                "active_hours": list(range(9, 18)),
                "response_delay_min": 30,
                "response_delay_max": 120,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.5
            }
        elif role_category == "agent":
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": list(range(8, 21)),
                "response_delay_min": 10,
                "response_delay_max": 60,
                "sentiment_bias": 0.1,
                "stance": "supportive",
                "influence_weight": 1.8
            }
        else:
            # researcher (default)
            return {
                "activity_level": 0.3,
                "posts_per_hour": 0.2,
                "comments_per_hour": 0.5,
                "active_hours": list(range(10, 22)),
                "response_delay_min": 30,
                "response_delay_max": 180,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 1.5
            }

    def _generate_agent_configs_batch(
        self,
        entities: List[EntityNode],
        start_idx: int,
        simulation_requirement: str
    ) -> List[AgentActivityConfig]:
        """Batch generate Agent configs"""
        
        # Build entity info (using configured summary length)
        entity_list = []
        summary_len = self.AGENT_SUMMARY_LENGTH
        for i, e in enumerate(entities):
            entity_list.append({
                "agent_id": start_idx + i,
                "entity_name": e.name,
                "entity_type": e.get_entity_type() or "Unknown",
                "summary": e.summary[:summary_len] if e.summary else ""
            })
        
        prompt = f"""Based on the following info, generate social media activity config for each entity.

Simulation requirement: {simulation_requirement}

## Entity list
```json
{json.dumps(entity_list, ensure_ascii=False, indent=2)}
```

## Task
Generate activity config for each entity, note:
- **Follow Chinese daily routine**: almost no activity 0-5 AM, most active 19-22 PM
- **Officials**（University/GovernmentAgency）：low activity(0.1-0.3),work hours(9-17), slow response(60-240minutes),high influence(2.5-3.0)
- **Media**（MediaOutlet）：medium activity(0.4-0.6),all-day activity(8-23),fast response(5-30minutes),high influence(2.0-2.5)
- **Individuals**（Student/Person/Alumni）：high activity(0.6-0.9),mainly evening activity(18-23),fast response(1-15minutes),low influence(0.8-1.2)
- **Public figures/experts**: medium activity(0.4-0.6), medium-high influence(1.5-2.0)

Return JSON format (no markdown)：
{{
    "agent_configs": [
        {{
            "agent_id": <Must match input>,
            "activity_level": <0.0-1.0>,
            "posts_per_hour": <Post frequency>,
            "comments_per_hour": <Comment frequency>,
            "active_hours": [<Active hours list, considering Chinese daily routine>],
            "response_delay_min": <Min response delay in minutes>,
            "response_delay_max": <Max response delay in minutes>,
            "sentiment_bias": <-1.0 to 1.0>,
            "stance": "<supportive/opposing/neutral/observer>",
            "influence_weight": <Influence weight>
        }},
        ...
    ]
}}"""

        system_prompt = "あなたはキャリアシミュレーションの行動分析専門家です。純粋なJSONを返してください。設定はビジネスアワーベースの活動パターンに準拠してください。"
        
        try:
            result = self._call_llm_with_retry(prompt, system_prompt)
            llm_configs = {cfg["agent_id"]: cfg for cfg in result.get("agent_configs", [])}
        except Exception as e:
            logger.warning(f"Agent config batch LLM generation failed: {e}, using rule-based generation")
            llm_configs = {}
        
        # Build AgentActivityConfig objects
        configs = []
        for i, entity in enumerate(entities):
            agent_id = start_idx + i
            cfg = llm_configs.get(agent_id, {})
            
            # If LLM did not generate, use rule-based generation
            if not cfg:
                cfg = self._generate_agent_config_by_rule(entity)
            
            config = AgentActivityConfig(
                agent_id=agent_id,
                entity_uuid=entity.uuid,
                entity_name=entity.name,
                entity_type=entity.get_entity_type() or "Unknown",
                activity_level=cfg.get("activity_level", 0.5),
                posts_per_hour=cfg.get("posts_per_hour", 0.5),
                comments_per_hour=cfg.get("comments_per_hour", 1.0),
                active_hours=cfg.get("active_hours", list(range(9, 23))),
                response_delay_min=cfg.get("response_delay_min", 5),
                response_delay_max=cfg.get("response_delay_max", 60),
                sentiment_bias=cfg.get("sentiment_bias", 0.0),
                stance=cfg.get("stance", "neutral"),
                influence_weight=cfg.get("influence_weight", 1.0)
            )
            configs.append(config)
        
        return configs
    
    def _generate_agent_config_by_rule(self, entity: EntityNode) -> Dict[str, Any]:
        """Generate single Agent config by rules"""
        entity_type = (entity.get_entity_type() or "Unknown").lower()
        
        if entity_type in ["university", "governmentagency", "ngo"]:
            # Official org: work hours activity, low frequency, high influence
            return {
                "activity_level": 0.2,
                "posts_per_hour": 0.1,
                "comments_per_hour": 0.05,
                "active_hours": list(range(9, 18)),  # 9:00-17:59
                "response_delay_min": 60,
                "response_delay_max": 240,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 3.0
            }
        elif entity_type in ["mediaoutlet"]:
            # Media: all-day activity, medium frequency, high influence
            return {
                "activity_level": 0.5,
                "posts_per_hour": 0.8,
                "comments_per_hour": 0.3,
                "active_hours": list(range(7, 24)),  # 7:00-23:59
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "observer",
                "influence_weight": 2.5
            }
        elif entity_type in ["professor", "expert", "official"]:
            # Expert/Professor: work + evening activity, medium frequency
            return {
                "activity_level": 0.4,
                "posts_per_hour": 0.3,
                "comments_per_hour": 0.5,
                "active_hours": list(range(8, 22)),  # 8:00-21:59
                "response_delay_min": 15,
                "response_delay_max": 90,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 2.0
            }
        elif entity_type in ["student"]:
            # Student: mainly evening, high frequency
            return {
                "activity_level": 0.8,
                "posts_per_hour": 0.6,
                "comments_per_hour": 1.5,
                "active_hours": [8, 9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Morning + evening
                "response_delay_min": 1,
                "response_delay_max": 15,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 0.8
            }
        elif entity_type in ["alumni"]:
            # Alumni: mainly evening
            return {
                "activity_level": 0.6,
                "posts_per_hour": 0.4,
                "comments_per_hour": 0.8,
                "active_hours": [12, 13, 19, 20, 21, 22, 23],  # Lunch break + evening
                "response_delay_min": 5,
                "response_delay_max": 30,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
        else:
            # Regular person: evening peak
            return {
                "activity_level": 0.7,
                "posts_per_hour": 0.5,
                "comments_per_hour": 1.2,
                "active_hours": [9, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23],  # Daytime + evening
                "response_delay_min": 2,
                "response_delay_max": 20,
                "sentiment_bias": 0.0,
                "stance": "neutral",
                "influence_weight": 1.0
            }
    

