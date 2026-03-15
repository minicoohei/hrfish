"""
Report API routes
Provides simulation report generation, retrieval, and conversation APIs
"""

import json as _json
import os
import re
import traceback
import threading
from flask import request, jsonify, send_file

from . import report_bp
from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..services.multipath_simulator import MultiPathSimulator
from ..models.life_simulator import BaseIdentity, CareerState
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.report')


# ============== Report generation endpoint ==============

@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    Generate simulation analysis report (async task)
    
    This is a time-consuming operation; the API returns task_id immediately,
    Use GET /api/report/generate/status to check progress
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx",    // Required,Simulation ID
            "force_regenerate": false        // Optional, force regenerate
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "Report generation task started"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        force_regenerate = data.get('force_regenerate', False)
        
        # Retrieve simulation info
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation not found: {simulation_id}"
            }), 404
        
        # Check if report already exists
        if not force_regenerate:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "message": "Report already exists",
                        "already_generated": True
                    }
                })
        
        # Retrieve project info
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project not found: {state.project_id}"
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Missing graph ID, ensure graph is built"
            }), 400
        
        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Missing simulation requirement"
            }), 400
        
        # Pre-generate report_id for immediate frontend return
        import uuid
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        
        # Create async task
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "report_id": report_id
            }
        )
        
        # Extract candidate profile from project for multipath sim
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""

        # Define background task
        def run_generate():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Running career path simulations..."
                )

                # Phase 0: Run multipath life simulation
                career_paths_context = ""
                career_paths_data = None
                try:
                    career_paths_data = _run_career_path_simulation(
                        document_text, simulation_requirement
                    )
                    if career_paths_data:
                        career_paths_context = _format_paths_for_llm(career_paths_data)
                        logger.info(
                            f"Career path simulation complete: "
                            f"{career_paths_data.get('total_paths_simulated', 0)} paths → "
                            f"top {career_paths_data.get('top_n', 5)}"
                        )
                except Exception as e:
                    logger.warning(f"Career path simulation failed (continuing without): {e}")

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=5,
                    message="Initializing Report Agent..."
                )

                # Create Report Agent with career path context
                agent = ReportAgent(
                    graph_id=graph_id,
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    career_paths_context=career_paths_context,
                    career_paths_data=career_paths_data,
                )
                
                # Progress callback
                def progress_callback(stage, progress, message):
                    task_manager.update_task(
                        task_id,
                        progress=progress,
                        message=f"[{stage}] {message}"
                    )
                
                # Generate report (pass pre-generated report_id)
                report = agent.generate_report(
                    progress_callback=progress_callback,
                    report_id=report_id
                )
                
                # Save report
                ReportManager.save_report(report)

                # Save career paths data alongside report for frontend
                if career_paths_data and report.report_id:
                    try:
                        paths_dir = os.path.join(
                            Config.UPLOAD_FOLDER, 'reports', report.report_id
                        )
                        os.makedirs(paths_dir, exist_ok=True)
                        paths_file = os.path.join(paths_dir, 'career_paths.json')
                        with open(paths_file, 'w', encoding='utf-8') as f:
                            _json.dump(career_paths_data, f, ensure_ascii=False, indent=2)
                        logger.info(f"Career paths data saved: {paths_file}")
                    except Exception as e:
                        logger.warning(f"Failed to save career paths data: {e}")

                if report.status == ReportStatus.COMPLETED:
                    task_manager.complete_task(
                        task_id,
                        result={
                            "report_id": report.report_id,
                            "simulation_id": simulation_id,
                            "status": "completed"
                        }
                    )
                else:
                    task_manager.fail_task(task_id, report.error or "Report generation failed")
                
            except Exception as e:
                logger.error(f"Report generation failed: {str(e)}")
                task_manager.fail_task(task_id, str(e))
        
        # Start background thread
        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "task_id": task_id,
                "status": "generating",
                "message": "Report generation task started, query progress via /api/report/generate/status",
                "already_generated": False
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to start report generation task: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/generate/status', methods=['POST'])
def get_generate_status():
    """
    Query report generation task progress
    
    Request (JSON):
        {
            "task_id": "task_xxxx",         // optional, task_id returned by generate
            "simulation_id": "sim_xxxx"     // Optional, simulation ID
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "..."
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # If simulation_id provided, check for existing completed report
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": "Report already generated",
                        "already_completed": True
                    }
                })
        
        if not task_id:
            return jsonify({
                "success": False,
                "error": "Please provide task_id or simulation_id"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            return jsonify({
                "success": False,
                "error": f"Task not found: {task_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": task.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Failed to query task status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== Report retrieval endpoint ==============

@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    """
    Retrieve report details
    
    Returns:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "simulation_id": "sim_xxxx",
                "status": "completed",
                "outline": {...},
                "markdown_content": "...",
                "created_at": "...",
                "completed_at": "..."
            }
        }
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": f"Report not found: {report_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": report.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Failed to get report: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    """
    Retrieve report by simulation ID
    
    Returns:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                ...
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": f"No report available for this simulation: {simulation_id}",
                "has_report": False
            }), 404
        
        return jsonify({
            "success": True,
            "data": report.to_dict(),
            "has_report": True
        })
        
    except Exception as e:
        logger.error(f"Failed to get report: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """
    List all reports
    
    QueryParameters:
        simulation_id: Filter by simulation ID (optional)
        limit: Result count limit (default 50)
    
    Returns:
        {
            "success": true,
            "data": [...],
            "count": 10
        }
    """
    try:
        simulation_id = request.args.get('simulation_id')
        limit = request.args.get('limit', 50, type=int)
        
        reports = ReportManager.list_reports(
            simulation_id=simulation_id,
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "data": [r.to_dict() for r in reports],
            "count": len(reports)
        })
        
    except Exception as e:
        logger.error(f"Failed to list reports: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    """
    Download report (Markdown format)
    
    Returns Markdown file
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": f"Report not found: {report_id}"
            }), 404
        
        md_path = ReportManager._get_report_markdown_path(report_id)
        
        if not os.path.exists(md_path):
            # If MD file does not exist, generate a temporary one
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"{report_id}.md"
            )
        
        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{report_id}.md"
        )
        
    except Exception as e:
        logger.error(f"Failed to download report: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    """Delete report"""
    try:
        success = ReportManager.delete_report(report_id)
        
        if not success:
            return jsonify({
                "success": False,
                "error": f"Report not found: {report_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "message": f"Report deleted: {report_id}"
        })
        
    except Exception as e:
        logger.error(f"Failed to delete report: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Report Agent Chat API ==============

@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    """
    Chat with Report Agent
    
    Report Agent can autonomously call retrieval tools to answer questions during conversation
    
    Request (JSON):
        {
            "simulation_id": "sim_xxxx",        // Required,Simulation ID
            "message": "Please explain the opinion trend",    // required, user message
            "chat_history": [                   // optional, chat history
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }
    
    Returns:
        {
            "success": true,
            "data": {
                "response": "Agent response...",
                "tool_calls": [list of tools called],
                "sources": [Information sources]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Please provide simulation_id"
            }), 400
        
        if not message:
            return jsonify({
                "success": False,
                "error": "Please provide message"
            }), 400
        
        # Get simulation and project info
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulation not found: {simulation_id}"
            }), 404
        
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project not found: {state.project_id}"
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Missing graph ID"
            }), 400
        
        simulation_requirement = project.simulation_requirement or ""
        
        # Create agent and conduct conversation
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement
        )
        
        result = agent.chat(message=message, chat_history=chat_history)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Chat failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Report progress and sections API ==============

@report_bp.route('/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    """
    Retrieve report generation progress (realtime)
    
    Returns:
        {
            "success": true,
            "data": {
                "status": "generating",
                "progress": 45,
                "message": "Generating section: Key Findings",
                "current_section": "Key Findings",
                "completed_sections": ["Executive Summary", "Simulation Background"],
                "updated_at": "2025-12-09T..."
            }
        }
    """
    try:
        progress = ReportManager.get_progress(report_id)
        
        if not progress:
            return jsonify({
                "success": False,
                "error": f"Report not found or progress info unavailable: {report_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": progress
        })
        
    except Exception as e:
        logger.error(f"Failed to retrieve report progress: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    """
    Get list of generated sections (per-section output)
    
    Frontend can poll this endpoint to get generated section content without waiting for full report
    
    Returns:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "sections": [
                    {
                        "filename": "section_01.md",
                        "section_index": 1,
                        "content": "## Executive Summary\\n\\n..."
                    },
                    ...
                ],
                "total_sections": 3,
                "is_complete": false
            }
        }
    """
    try:
        sections = ReportManager.get_generated_sections(report_id)
        
        # Retrieve report status
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "report_id": report_id,
                "sections": sections,
                "total_sections": len(sections),
                "is_complete": is_complete
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to retrieve section list: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    """
    Get single section content
    
    Returns:
        {
            "success": true,
            "data": {
                "filename": "section_01.md",
                "content": "## Executive Summary\\n\\n..."
            }
        }
    """
    try:
        section_path = ReportManager._get_section_path(report_id, section_index)
        
        if not os.path.exists(section_path):
            return jsonify({
                "success": False,
                "error": f"Section not found: section_{section_index:02d}.md"
            }), 404
        
        with open(section_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            "success": True,
            "data": {
                "filename": f"section_{section_index:02d}.md",
                "section_index": section_index,
                "content": content
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to retrieve section content: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Report status check endpoints ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    """
    Check if simulation has report and report status
    
    For frontend to determine if Interview feature is unlocked
    
    Returns:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "has_report": true,
                "report_status": "completed",
                "report_id": "report_xxxx",
                "interview_unlocked": true
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None
        
        # Interview is only unlocked after report is complete
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to check report status: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Agent log endpoints ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    """
    Get Report Agent detailed execution log
    
    Get each step action during report generation in real-time, including:
    - Report start, planning start/complete
    - Each section start, tool calls, LLM responses, completion
    - Report complete or failed
    
    QueryParameters:
        from_line: Starting line number (optional, default 0, for incremental fetch)
    
    Returns:
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "timestamp": "2025-12-13T...",
                        "elapsed_seconds": 12.5,
                        "report_id": "report_xxxx",
                        "action": "tool_call",
                        "stage": "generating",
                        "section_title": "Executive Summary",
                        "section_index": 1,
                        "details": {
                            "tool_name": "insight_forge",
                            "parameters": {...},
                            ...
                        }
                    },
                    ...
                ],
                "total_lines": 25,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get agent log: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    """
    Get complete agent log (one-time full fetch)
    
    Returns:
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 25
            }
        }
    """
    try:
        logs = ReportManager.get_agent_log_stream(report_id)
        
        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get agent log: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Console log endpoints ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    """
    Get Report Agent console output log
    
    Get console output (INFO, WARNING, etc.) during report generation in real-time,
    different from the structured JSON log returned by agent-log endpoint,
    this is plain-text console-style log.
    
    QueryParameters:
        from_line: Starting line number (optional, default 0, for incremental fetch)
    
    Returns:
        {
            "success": true,
            "data": {
                "logs": [
                    "[19:46:14] INFO: Search complete: Found 15 related facts",
                    "[19:46:14] INFO: Graph search: graph_id=xxx, query=...",
                    ...
                ],
                "total_lines": 100,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_console_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"Failed to retrieve console logs: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    """
    Get complete console log (one-time full fetch)
    
    Returns:
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 100
            }
        }
    """
    try:
        logs = ReportManager.get_console_log_stream(report_id)
        
        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to retrieve console logs: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Tool call endpoints (for debugging)==============

@report_bp.route('/tools/search', methods=['POST'])
def search_graph_tool():
    """
    Graph search tool endpoint (for debugging)
    
    Request (JSON):
        {
            "graph_id": "mirofish_xxxx",
            "query": "Search query",
            "limit": 10
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        query = data.get('query')
        limit = data.get('limit', 10)
        
        if not graph_id or not query:
            return jsonify({
                "success": False,
                "error": "Please provide graph_id and query"
            }), 400
        
        from ..services.zep_tools import ZepToolsService
        
        tools = ZepToolsService()
        result = tools.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Graph search failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    """
    Graph statistics tool endpoint (for debugging)
    
    Request (JSON):
        {
            "graph_id": "mirofish_xxxx"
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Please provide graph_id"
            }), 400
        
        from ..services.zep_tools import ZepToolsService
        
        tools = ZepToolsService()
        result = tools.get_graph_statistics(graph_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"Failed to retrieve graph statistics: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Career Path Simulation Helpers ==============

def _run_career_path_simulation(document_text: str, simulation_requirement: str) -> dict:
    """
    Run expanded career path simulation from document text.
    Extracts candidate profile, runs 10+ paths, returns top 5.
    """
    # Extract basic profile info from document text
    age = 30
    salary = 500
    role = ""
    employer = ""
    industry = "IT"

    # Simple extraction heuristics from resume text
    defaults_used = []
    age_match = re.search(r'(\d{2})歳', document_text)
    if age_match:
        extracted_age = int(age_match.group(1))
        if 20 <= extracted_age <= 65:
            age = extracted_age
        else:
            defaults_used.append(f"age (extracted {extracted_age} out of range)")
    else:
        defaults_used.append("age")

    salary_match = re.search(r'年収[：:]?\s*(\d+)', document_text)
    if salary_match:
        extracted_salary = int(salary_match.group(1))
        if 100 <= extracted_salary <= 5000:
            salary = extracted_salary
        else:
            defaults_used.append(f"salary (extracted {extracted_salary} out of range)")
    else:
        defaults_used.append("salary")

    # Extract from simulation requirement as fallback context
    for text in [document_text, simulation_requirement]:
        if not role:
            role_match = re.search(r'(エンジニア|マネージャー|デザイナー|営業|コンサルタント|マーケター|データサイエンティスト|PM|プロダクトマネージャー)', text)
            if role_match:
                role = role_match.group(1)
        if not employer:
            emp_match = re.search(r'(株式会社[^\s、。]+|[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)', text)
            if emp_match:
                employer = emp_match.group(1)
    if not role:
        defaults_used.append("role")
    if not employer:
        defaults_used.append("employer")

    if defaults_used:
        logger.warning(
            f"Career path simulation using defaults for: {', '.join(defaults_used)}. "
            f"Profile extraction from document text ({len(document_text)} chars) was incomplete."
        )

    identity = BaseIdentity(
        name="候補者",
        age_at_start=age,
        gender="",
        education="",
        mbti="",
        stable_traits=[],
        certifications=[],
        career_history_summary=document_text[:500] if document_text else "",
    )

    initial_state = CareerState(
        current_round=0,
        current_age=age,
        role=role or "スタッフ",
        employer=employer or "現職企業",
        industry=industry,
        years_in_role=3,
        salary_annual=salary,
        skills=[],
        family=[],
        marital_status="single",
        cash_buffer=500,
        mortgage_remaining=0,
        monthly_expenses=25,
    )

    simulator = MultiPathSimulator()
    return simulator.run_expanded_and_select(
        identity=identity,
        initial_state=initial_state,
        round_count=40,  # 10 years
        top_n=5,
        document_text=document_text,
        simulation_requirement=simulation_requirement,
    )


def _format_paths_for_llm(paths_data: dict) -> str:
    """Format career path simulation results as context for LLM report generation."""
    lines = []
    lines.append("=" * 60)
    lines.append("【キャリアパス シミュレーション結果】")
    lines.append(f"シミュレーション期間: {paths_data.get('simulation_years', 10)}年間")
    lines.append(f"検証パス数: {paths_data.get('total_paths_simulated', 0)}パス → 上位{paths_data.get('top_n', 5)}パスを選出")
    lines.append("=" * 60)

    for i, path in enumerate(paths_data.get("paths", []), 1):
        lines.append(f"\n--- パス{i}: {path['path_label']} (スコア: {path.get('score', 0)}) ---")
        lines.append(f"最終年齢: {path.get('final_age', '?')}歳")
        lines.append(f"最終役職: {path.get('final_role', '?')} @ {path.get('final_employer', '?')}")
        lines.append(f"最終年収: {path.get('final_salary', 0)}万円 (ピーク: {path.get('peak_salary', 0)}万円)")
        lines.append(f"資産: {path.get('final_cash_buffer', 0)}万円")
        lines.append(f"ストレス: {path.get('avg_stress', 0)} / 満足度: {path.get('final_satisfaction', 0)} / WLB: {path.get('final_wlb', 0)}")

        events = path.get("key_events", [])
        if events:
            lines.append("主要ライフイベント:")
            for evt in events:
                lines.append(f"  - {evt.get('age', '?')}歳: {evt.get('event', '')}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)
