"""
OASIS simulation manager
Manages Twitter and Reddit dual-platform parallel simulation
Uses preset scripts + LLM-generated config parameters
"""

import os
import json
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from .zep_entity_reader import ZepEntityReader, FilteredEntities
from .oasis_profile_generator import OasisProfileGenerator, OasisAgentProfile
from .simulation_config_generator import SimulationConfigGenerator, SimulationParameters

logger = get_logger('mirofish.simulation')


class SimulationStatus(str, Enum):
    """Simulation status"""
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"      # Manually stopped
    COMPLETED = "completed"  # Completed naturally
    FAILED = "failed"


class PlatformType(str, Enum):
    """Platform type"""
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    """Simulation state"""
    simulation_id: str
    project_id: str
    graph_id: str
    
    # Platform enable flags
    enable_twitter: bool = True
    enable_reddit: bool = True
    
    # Status
    status: SimulationStatus = SimulationStatus.CREATED
    
    # Preparation phase data
    entities_count: int = 0
    profiles_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    
    # Config generation info
    config_generated: bool = False
    config_reasoning: str = ""
    
    # Runtime data
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Error info
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Full state dict (internal use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
    
    def to_simple_dict(self) -> Dict[str, Any]:
        """Simplified state dict (API response use)"""
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "error": self.error,
        }


class SimulationManager:
    """
    Simulation manager
    
    Core features:
    1. Read and filter entities from Zep graph
    2. Generate OASIS Agent Profile
    3. Use LLM to intelligently generate simulation config parameters
    4. Prepare all files needed by preset scripts
    """
    
    # Simulation data storage directory
    SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__), 
        '../../uploads/simulations'
    )
    
    def __init__(self):
        # Ensure directory exists
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        
        # In-memory simulation state cache
        self._simulations: Dict[str, SimulationState] = {}
    
    def _get_simulation_dir(self, simulation_id: str) -> str:
        """Get simulation data directory"""
        from ..utils.validators import validate_safe_id
        validate_safe_id(simulation_id, "simulation_id")
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir
    
    def _save_simulation_state(self, state: SimulationState):
        """Save simulation state to file"""
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        state.updated_at = datetime.now().isoformat()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)
        
        self._simulations[state.simulation_id] = state
    
    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        """Load simulation state from file"""
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]
        
        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        
        self._simulations[simulation_id] = state
        return state
    
    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
    ) -> SimulationState:
        """
        Create new simulation
        
        Args:
            project_id: Project ID
            graph_id: Zep graph ID
            enable_twitter: Whether to enable Twitter simulation
            enable_reddit: Whether to enable Reddit simulation
            
        Returns:
            SimulationState
        """
        import uuid
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            status=SimulationStatus.CREATED,
        )
        
        self._save_simulation_state(state)
        logger.info(f"Created simulation: {simulation_id}, project={project_id}, graph={graph_id}")
        
        return state
    
    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3
    ) -> SimulationState:
        """
        Prepare simulation environment (fully automated)
        
        Steps:
        1. Read and filter entities from Zep graph
        2. Generate OASIS Agent Profile for each entity (optional LLM enhancement, parallel support)
        3. Use LLM to intelligently generate simulation config parameters (time, activity, posting frequency, etc.)
        4. Save config files and Profile files
        5. Copy preset scripts to simulation directory
        
        Args:
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description (for LLM config generation)
            document_text: Original document content (for LLM background understanding)
            defined_entity_types: Predefined entity types (optional)
            use_llm_for_profiles: Whether to use LLM to generate detailed personas
            progress_callback: Progress callback (stage, progress, message)
            parallel_profile_count: Number of profiles to generate in parallel, default 3
            
        Returns:
            SimulationState
        """
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation not found: {simulation_id}")
        
        try:
            state.status = SimulationStatus.PREPARING
            self._save_simulation_state(state)
            
            sim_dir = self._get_simulation_dir(simulation_id)
            
            # ========== Phase 1: Read and filter entities ==========
            if progress_callback:
                progress_callback("reading", 0, "Connecting to Zep graph...")
            
            reader = ZepEntityReader()
            
            if progress_callback:
                progress_callback("reading", 30, "Reading node data...")
            
            filtered = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=True
            )
            
            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            
            if progress_callback:
                progress_callback(
                    "reading", 100, 
                    f"Complete, {filtered.filtered_count} entities",
                    current=filtered.filtered_count,
                    total=filtered.filtered_count
                )
            
            if filtered.filtered_count == 0:
                state.status = SimulationStatus.FAILED
                state.error = "No matching entities found. Please check if the graph was built correctly."
                self._save_simulation_state(state)
                return state
            
            # ========== Phase 2: HR Agent Generation (New Architecture) ==========
            # Graph = 候補者の事実DB（RAGソース）
            # Agent = 候補者ミラー（1名）+ 評価者群（関係者/HR専門家/転職先/Topプレイヤー）

            generator = OasisProfileGenerator(graph_id=state.graph_id)
            # 両方を結合: simulation_requirement（シナリオ）+ document_text（履歴書）
            context_parts = []
            if simulation_requirement:
                context_parts.append(f"シミュレーション要件:\n{simulation_requirement}")
            if document_text:
                context_parts.append(f"候補者ドキュメント:\n{document_text}")
            candidate_context = "\n\n".join(context_parts) if context_parts else ""

            profiles = generator.generate_all_hr_agents(
                entities=filtered.entities,
                candidate_context=candidate_context,
                graph_id=state.graph_id,
                use_llm=use_llm_for_profiles,
                progress_callback=progress_callback,
            )

            state.profiles_count = len(profiles)
            
            # Save profile files (note: Twitter uses CSV, Reddit uses JSON)
            # Reddit already saved during generation, save again here for completeness
            if progress_callback:
                progress_callback(
                    "generating_profiles", 95, 
                    "Saving Profile files...",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            if state.enable_reddit:
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "reddit_profiles.json"),
                    platform="reddit"
                )
            
            if state.enable_twitter:
                # Twitter uses CSV format! This is required by OASIS
                generator.save_profiles(
                    profiles=profiles,
                    file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
                    platform="twitter"
                )
            
            if progress_callback:
                progress_callback(
                    "generating_profiles", 100, 
                    f"Complete, {len(profiles)} Profiles total",
                    current=len(profiles),
                    total=len(profiles)
                )
            
            # ========== Phase 3: LLM intelligent config generation ==========
            if progress_callback:
                progress_callback(
                    "generating_config", 0, 
                    "Analyzing simulation requirements...",
                    current=0,
                    total=3
                )
            
            config_generator = SimulationConfigGenerator()
            
            if progress_callback:
                progress_callback(
                    "generating_config", 30, 
                    "Calling LLM to generate config...",
                    current=1,
                    total=3
                )
            
            sim_params = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                profiles=profiles,
                enable_twitter=state.enable_twitter,
                enable_reddit=state.enable_reddit
            )
            
            if progress_callback:
                progress_callback(
                    "generating_config", 70, 
                    "Saving config files...",
                    current=2,
                    total=3
                )
            
            # Save config files
            config_path = os.path.join(sim_dir, "simulation_config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(sim_params.to_json())
            
            state.config_generated = True
            state.config_reasoning = sim_params.generation_reasoning
            
            if progress_callback:
                progress_callback(
                    "generating_config", 100, 
                    "Config generation complete",
                    current=3,
                    total=3
                )
            
            # Note: Run scripts remain in backend/scripts/, no longer copied to simulation dir
            # When starting simulation, simulation_runner runs scripts from scripts/ dir
            
            # Update status
            state.status = SimulationStatus.READY
            self._save_simulation_state(state)
            
            logger.info(f"Simulation preparation complete: {simulation_id}, "
                       f"entities={state.entities_count}, profiles={state.profiles_count}")
            
            return state
            
        except Exception as e:
            logger.exception(f"Simulation preparation failed: {simulation_id}, error={str(e)}")
            state.status = SimulationStatus.FAILED
            state.error = str(e)
            self._save_simulation_state(state)
            raise
    
    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        """Get simulation state"""
        return self._load_simulation_state(simulation_id)
    
    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        """List all simulations"""
        simulations = []
        
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                # Skip hidden files (e.g. .DS_Store) and non-directory files
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith('.') or not os.path.isdir(sim_path):
                    continue
                
                state = self._load_simulation_state(sim_id)
                if state:
                    if project_id is None or state.project_id == project_id:
                        simulations.append(state)
        
        return simulations
    
    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        """Get simulation Agent Profiles"""
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation not found: {simulation_id}")
        
        sim_dir = self._get_simulation_dir(simulation_id)
        profile_path = os.path.join(sim_dir, f"{platform}_profiles.json")
        
        if not os.path.exists(profile_path):
            return []
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        """Get simulation config"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        """Get run instructions"""
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "twitter": f"python {scripts_dir}/run_twitter_simulation.py --config {config_path}",
                "reddit": f"python {scripts_dir}/run_reddit_simulation.py --config {config_path}",
                "parallel": f"python {scripts_dir}/run_parallel_simulation.py --config {config_path}",
            },
            "instructions": (
                f"1. Activate conda env: conda activate MiroFish\n"
                f"2. Run simulation (scripts in {scripts_dir}):\n"
                f"   - Run Twitter only: python {scripts_dir}/run_twitter_simulation.py --config {config_path}\n"
                f"   - Run Reddit only: python {scripts_dir}/run_reddit_simulation.py --config {config_path}\n"
                f"   - Run both platforms in parallel: python {scripts_dir}/run_parallel_simulation.py --config {config_path}"
            )
        }
