"""
P9+P10: Life Simulation API endpoints

POST /api/life-sim/initialize  — Initialize life simulation from profile + form
POST /api/life-sim/chat        — Interactive chat after simulation
GET  /api/life-sim/summary/<simulation_id>  — Get simulation path summary
POST /api/life-sim/multipath/run — Run 3 career paths in parallel
GET  /api/life-sim/multipath/timeline/<sim_id>/<path_id>
GET  /api/life-sim/multipath/report/<sim_id>
"""

import time
import uuid
from collections import OrderedDict
from threading import Lock
from flask import Blueprint, request, jsonify

from ..models.life_simulator import (
    FamilyMember, LifeEvent, LifeEventType, BaseIdentity, CareerState,
)
from ..services.life_simulation_loop import (
    LifeSimulationOrchestrator, FormInput, cash_range_to_value,
)
from ..services.multipath_simulator import (
    MultiPathSimulator, PathConfig, build_default_paths,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.life_simulation')

life_sim_bp = Blueprint('life_simulation', __name__)

# --- TTL-limited LRU cache for simulation state ---
_MAX_SESSIONS = 100
_SESSION_TTL_SECONDS = 3600  # 1 hour
_cache_lock = Lock()


class _TTLCache:
    """Simple TTL + size-limited OrderedDict cache."""

    def __init__(self, max_size: int = _MAX_SESSIONS, ttl: int = _SESSION_TTL_SECONDS):
        self._store: OrderedDict = OrderedDict()
        self._timestamps: dict = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str):
        with _cache_lock:
            self._evict_expired()
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def put(self, key: str, value) -> str:
        with _cache_lock:
            self._evict_expired()
            if key in self._store:
                del self._store[key]
            self._store[key] = value
            self._timestamps[key] = time.monotonic()
            while len(self._store) > self._max_size:
                oldest_key, _ = self._store.popitem(last=False)
                self._timestamps.pop(oldest_key, None)
        return key

    def __contains__(self, key: str) -> bool:
        with _cache_lock:
            self._evict_expired()
            return key in self._store

    def _evict_expired(self):
        """Remove expired entries. Must be called with _cache_lock held."""
        now = time.monotonic()
        expired = [k for k, t in self._timestamps.items() if now - t > self._ttl]
        for k in expired:
            self._store.pop(k, None)
            self._timestamps.pop(k, None)


_orchestrators = _TTLCache()
_multipath_sims = _TTLCache()


def _generate_sim_id() -> str:
    """Generate a server-side simulation ID."""
    return f"sim_{uuid.uuid4().hex[:12]}"


def _build_family_members(life_ctx: dict, profile: dict) -> list:
    """Build FamilyMember list from life_context."""
    family_members = []
    for child in life_ctx.get("children", []):
        family_members.append(FamilyMember(
            relation="child", age=child.get("age", 0),
        ))
    for parent in life_ctx.get("parents", []):
        family_members.append(FamilyMember(
            relation="parent", age=parent.get("age", 65),
        ))
    if life_ctx.get("marital_status") == "married":
        family_members.append(FamilyMember(relation="spouse", age=profile.get("age", 30)))
    return family_members


@life_sim_bp.route('/initialize', methods=['POST'])
def initialize_life_simulation():
    """Initialize life simulation with profile data + life context form."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No request body"}), 400

        agent_id = data.get("agent_id", "agent_0")
        profile = data.get("profile", {})
        life_ctx = data.get("life_context", {})
        seed = data.get("seed")  # None → random seed for non-deterministic simulation

        simulation_id = _generate_sim_id()
        family_members = _build_family_members(life_ctx, profile)

        form_input = FormInput(
            family_members=family_members,
            marital_status=life_ctx.get("marital_status", "single"),
            mortgage_remaining=life_ctx.get("mortgage_remaining", 0),
            cash_buffer_range=life_ctx.get("cash_buffer_range", "500未満"),
            monthly_expenses=life_ctx.get("monthly_expenses", 25),
        )

        orchestrator = LifeSimulationOrchestrator(seed=seed)
        orchestrator.initialize_from_profile(agent_id, profile, form_input)

        _orchestrators.put(simulation_id, {
            "orchestrator": orchestrator,
            "agent_id": agent_id,
        })

        state = orchestrator.state_store.get_state(agent_id)

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "agent_id": agent_id,
                "initial_state": state.to_dict(),
                "identity": orchestrator.state_store.get_identity(agent_id).to_dict(),
            }
        })

    except Exception as e:
        logger.error(f"Life simulation init failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@life_sim_bp.route('/chat', methods=['POST'])
def life_simulation_chat():
    """Interactive chat for post-simulation preference gathering."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No request body"}), 400

        simulation_id = data.get("simulation_id")
        message = data.get("message", "")
        preferences = data.get("preferences", {})

        entry = _orchestrators.get(simulation_id)
        if entry is None:
            return jsonify({
                "success": False,
                "error": "Simulation not found. Initialize first."
            }), 404

        orchestrator = entry["orchestrator"]
        agent_id = entry["agent_id"]
        state = orchestrator.state_store.get_state(agent_id)

        response_parts = []

        if message:
            response_parts.append(f"ご意向を承りました: 「{message}」")

        if preferences:
            direction = preferences.get("career_direction", "")
            risk = preferences.get("risk_tolerance", "")
            relocation = preferences.get("relocation_ok")
            if direction:
                response_parts.append(f"キャリア方向性: {direction}")
            if risk:
                response_parts.append(f"リスク許容度: {risk}")
            if relocation is not None:
                response_parts.append(f"転勤可否: {'可' if relocation else '不可'}")

        response_parts.append(
            f"\n現在のシミュレーション状況: "
            f"{state.current_age}歳、{state.role}@{state.employer}、"
            f"年収{state.salary_annual}万円"
        )

        if state.blockers:
            response_parts.append("現在の制約:")
            for b in state.blockers:
                response_parts.append(f"  - {b.reason}")

        return jsonify({
            "success": True,
            "data": {
                "response": "\n".join(response_parts),
                "current_state": state.to_dict(),
                "preferences_applied": preferences,
                "can_resimulate": True,
                "suggested_paths": [
                    {"id": "path_a", "label": "現職継続", "description": "社内昇進を目指す"},
                    {"id": "path_b", "label": "同業転職", "description": "同業界でステップアップ"},
                    {"id": "path_c", "label": "異業種挑戦", "description": "新分野へのキャリアチェンジ"},
                ],
            }
        })

    except Exception as e:
        logger.error(f"Life simulation chat failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@life_sim_bp.route('/summary/<simulation_id>', methods=['GET'])
def get_life_simulation_summary(simulation_id):
    """Get full simulation path summary with history."""
    try:
        entry = _orchestrators.get(simulation_id)
        if entry is None:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        orchestrator = entry["orchestrator"]
        agent_id = entry["agent_id"]
        summary = orchestrator.get_simulation_summary(agent_id)

        return jsonify({"success": True, "data": summary})

    except Exception as e:
        logger.error(f"Get summary failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@life_sim_bp.route('/multipath/run', methods=['POST'])
def run_multipath_simulation():
    """Run 3 career paths in parallel from the same starting state."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No request body"}), 400

        profile = data.get("profile", {})
        life_ctx = data.get("life_context", {})
        round_count = data.get("round_count", 40)
        seed = data.get("seed")  # None → random seed for non-deterministic simulation

        simulation_id = _generate_sim_id()

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

        family_members = _build_family_members(life_ctx, profile)

        initial_state = CareerState(
            current_round=0,
            current_age=identity.age_at_start,
            role=profile.get("current_role", ""),
            employer=profile.get("current_employer", ""),
            industry=profile.get("industry", ""),
            years_in_role=profile.get("years_in_role", 0),
            salary_annual=profile.get("salary", 0),
            skills=profile.get("skills", []),
            family=family_members,
            marital_status=life_ctx.get("marital_status", "single"),
            cash_buffer=cash_range_to_value(life_ctx.get("cash_buffer_range", "500未満")),
            mortgage_remaining=life_ctx.get("mortgage_remaining", 0),
            monthly_expenses=life_ctx.get("monthly_expenses", 25),
        )

        simulator = MultiPathSimulator(base_seed=seed)
        simulator.initialize(identity, initial_state, round_count=round_count)
        simulator.run_all()

        _multipath_sims.put(simulation_id, simulator)

        report = simulator.generate_comparison_report()
        report["simulation_id"] = simulation_id

        return jsonify({
            "success": True,
            "data": report,
        })

    except Exception as e:
        logger.error(f"Multi-path simulation failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@life_sim_bp.route('/multipath/timeline/<simulation_id>/<path_id>', methods=['GET'])
def get_multipath_timeline(simulation_id, path_id):
    """Get detailed timeline for a specific path."""
    try:
        simulator = _multipath_sims.get(simulation_id)
        if simulator is None:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        timeline = simulator.get_path_timeline(path_id)

        if not timeline:
            return jsonify({"success": False, "error": f"Path {path_id} not found"}), 404

        return jsonify({"success": True, "data": {"path_id": path_id, "timeline": timeline}})

    except Exception as e:
        logger.error(f"Get timeline failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@life_sim_bp.route('/multipath/report/<simulation_id>', methods=['GET'])
def get_multipath_report(simulation_id):
    """Get comparison report for a completed multi-path simulation."""
    try:
        simulator = _multipath_sims.get(simulation_id)
        if simulator is None:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        report = simulator.generate_comparison_report()

        return jsonify({"success": True, "data": report})

    except Exception as e:
        logger.error(f"Get report failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
