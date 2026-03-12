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
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.life_simulation')

life_sim_bp = Blueprint('life_simulation', __name__)

# In-memory orchestrators per simulation
_orchestrators = {}


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
