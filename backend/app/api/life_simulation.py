"""
P9+P10: Life Simulation API endpoints

POST /api/life-sim/initialize  — Initialize life simulation from profile + form
POST /api/life-sim/chat        — Interactive chat after simulation
GET  /api/life-sim/summary/<simulation_id>  — Get simulation path summary
"""

from flask import Blueprint, request, jsonify

from ..models.life_simulator import FamilyMember, LifeEvent, LifeEventType
from ..services.life_simulation_loop import (
    LifeSimulationOrchestrator, FormInput,
)
from ..services.multipath_simulator import (
    MultiPathSimulator, PathConfig, build_default_paths,
)
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.life_simulation')

life_sim_bp = Blueprint('life_simulation', __name__)

# In-memory orchestrators per simulation
_orchestrators = {}
_multipath_sims = {}


@life_sim_bp.route('/initialize', methods=['POST'])
def initialize_life_simulation():
    """
    Initialize life simulation with profile data + life context form.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No request body"}), 400

        simulation_id = data.get("simulation_id")
        agent_id = data.get("agent_id", "agent_0")
        profile = data.get("profile", {})
        life_ctx = data.get("life_context", {})

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id required"}), 400

        # Build family members from life_context
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

        form_input = FormInput(
            family_members=family_members,
            marital_status=life_ctx.get("marital_status", "single"),
            mortgage_remaining=life_ctx.get("mortgage_remaining", 0),
            cash_buffer_range=life_ctx.get("cash_buffer_range", "500未満"),
        )

        orchestrator = LifeSimulationOrchestrator(seed=42)
        orchestrator.initialize_from_profile(agent_id, profile, form_input)

        _orchestrators[simulation_id] = {
            "orchestrator": orchestrator,
            "agent_id": agent_id,
        }

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
    """
    Interactive chat for post-simulation preference gathering.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No request body"}), 400

        simulation_id = data.get("simulation_id")
        message = data.get("message", "")
        preferences = data.get("preferences", {})

        if simulation_id not in _orchestrators:
            return jsonify({
                "success": False,
                "error": "Simulation not found. Initialize first."
            }), 404

        entry = _orchestrators[simulation_id]
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
        if simulation_id not in _orchestrators:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        entry = _orchestrators[simulation_id]
        orchestrator = entry["orchestrator"]
        agent_id = entry["agent_id"]

        summary = orchestrator.get_simulation_summary(agent_id)

        return jsonify({"success": True, "data": summary})

    except Exception as e:
        logger.error(f"Get summary failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@life_sim_bp.route('/multipath/run', methods=['POST'])
def run_multipath_simulation():
    """
    Run 3 career paths in parallel from the same starting state.

    Request body:
    {
        "simulation_id": "sim_123",
        "profile": { ... },
        "life_context": { ... },
        "round_count": 40,
        "paths": [  // optional custom paths
            {"path_id": "path_a", "path_label": "...", "events": [...]}
        ]
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No request body"}), 400

        simulation_id = data.get("simulation_id")
        profile = data.get("profile", {})
        life_ctx = data.get("life_context", {})
        round_count = data.get("round_count", 40)

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id required"}), 400

        # Build identity
        from ..models.life_simulator import BaseIdentity, CareerState
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

        # Build family members
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

        from ..services.life_simulation_loop import cash_range_to_value
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

        simulator = MultiPathSimulator(base_seed=42)
        simulator.initialize(identity, initial_state, round_count=round_count)
        simulator.run_all()

        _multipath_sims[simulation_id] = simulator

        report = simulator.generate_comparison_report()

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
        if simulation_id not in _multipath_sims:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        simulator = _multipath_sims[simulation_id]
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
        if simulation_id not in _multipath_sims:
            return jsonify({"success": False, "error": "Simulation not found"}), 404

        simulator = _multipath_sims[simulation_id]
        report = simulator.generate_comparison_report()

        return jsonify({"success": True, "data": report})

    except Exception as e:
        logger.error(f"Get report failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

