import uuid

from flask import jsonify, request

from . import report_bp
from ..models.task import TaskManager
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.report_analysis import ReportAnalysisService
from ..services.simulation_manager import SimulationManager
from ..services.task_executor import TaskExecutor
from ..utils.logger import get_logger

logger = get_logger("envfish.api.report")


def _success(data=None, **extra):
    payload = {"success": True, "data": data if data is not None else {}}
    payload.update(extra)
    return jsonify(payload)


def _error(message, status=400):
    return jsonify({"success": False, "error": message}), status


def _resolve_report_context(data):
    simulation_id = data.get("simulation_id")
    graph_id = data.get("graph_id") or data.get("graphId") or ""
    simulation_requirement = data.get("simulation_requirement") or data.get("requirement") or ""

    if not simulation_id:
        return graph_id, simulation_requirement

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    config = manager.get_simulation_config(simulation_id) or {}

    if not graph_id:
        graph_id = (state.graph_id if state else "") or config.get("graph_id") or ""
    if not simulation_requirement:
        simulation_requirement = (
            config.get("simulation_requirement")
            or config.get("scenario_summary")
            or (state.config_reasoning if state else "")
            or ""
        )

    return graph_id, simulation_requirement


@report_bp.route("/generate", methods=["POST"])
def generate_report():
    data = request.get_json(silent=True) or {}
    simulation_id = data.get("simulation_id")
    graph_id = data.get("graph_id")
    force_regenerate = bool(data.get("force_regenerate", False))

    if not simulation_id:
        return _error("simulation_id 不能为空")

    existing = None if force_regenerate else ReportManager.get_report_by_simulation(simulation_id)
    if existing:
        return _success(existing.to_dict())

    graph_id, simulation_requirement = _resolve_report_context(data)
    agent = ReportAgent(
        graph_id=graph_id,
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
    )
    report = agent.generate_report()
    return _success(report.to_dict())


@report_bp.route("/generate/async", methods=["POST"])
def generate_report_async():
    data = request.get_json(silent=True) or {}
    simulation_id = data.get("simulation_id")
    if not simulation_id:
        return _error("simulation_id 不能为空")

    report_id = data.get("report_id") or f"report_{uuid.uuid4().hex[:12]}"
    graph_id, simulation_requirement = _resolve_report_context(data)
    agent = ReportAgent(
        graph_id=graph_id,
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
    )
    task_manager = TaskManager()
    task_id = task_manager.create_task(
        name=f"生成报告: {report_id}",
        task_type="report_generate",
        metadata={"report_id": report_id, "simulation_id": simulation_id},
    )

    def runner():
        report = agent.generate_report(report_id=report_id)
        if report.status == ReportStatus.FAILED:
            task_manager.fail_task(task_id, report.error or "报告生成失败")
            return
        task_manager.complete_task(task_id, report.to_dict(), message="报告生成完成")

    TaskExecutor(task_manager).start(task_id=task_id, target=runner)
    return _success({"report_id": report_id, "status": "started"})


@report_bp.route("/<report_id>", methods=["GET"])
def get_report(report_id):
    report = ReportManager.get_report(report_id)
    if not report:
        return _error("报告不存在", 404)
    return _success(report.to_dict())


@report_bp.route("/<report_id>/progress", methods=["GET"])
def get_report_progress(report_id):
    return _success(ReportManager.get_progress(report_id) or {})


@report_bp.route("/<report_id>/sections", methods=["GET"])
def get_report_sections(report_id):
    return _success(ReportManager.get_generated_sections(report_id))


@report_bp.route("/<report_id>/console-log", methods=["GET"])
def get_report_console_log(report_id):
    from_line = int(request.args.get("from_line", 0) or 0)
    return _success(ReportManager.get_console_log(report_id, from_line=from_line))


@report_bp.route("/<report_id>/agent-log", methods=["GET"])
def get_report_agent_log(report_id):
    from_line = int(request.args.get("from_line", 0) or 0)
    return _success(ReportManager.get_agent_log(report_id, from_line=from_line))


@report_bp.route("/<report_id>/analysis/graph", methods=["GET"])
def get_report_analysis_graph(report_id):
    service = ReportAnalysisService(report_id)
    return _success(service.get_graph_data())


@report_bp.route("/<report_id>/analysis/overview", methods=["GET"])
def get_report_analysis_overview(report_id):
    service = ReportAnalysisService(report_id)
    return _success(service.get_overview())


@report_bp.route("/<report_id>/analysis/tab/<tab_id>", methods=["GET"])
def get_report_analysis_tab(report_id, tab_id):
    service = ReportAnalysisService(report_id)
    return _success(service.get_tab_data(tab_id))


@report_bp.route("/<report_id>/analysis/node/context", methods=["POST"])
def get_report_node_context(report_id):
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id") or data.get("nodeId")
    if not node_id:
        return _error("node_id 不能为空")
    service = ReportAnalysisService(report_id)
    return _success(service.get_node_context(node_id, data.get("round_range")))


@report_bp.route("/<report_id>/analysis/node/explore", methods=["POST"])
def explore_report_node(report_id):
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id") or data.get("nodeId")
    if not node_id:
        return _error("node_id 不能为空")
    service = ReportAnalysisService(report_id)
    return _success(service.explore_node(node_id, data.get("round_range")))


@report_bp.route("/<report_id>/analysis/node/chat", methods=["POST"])
def chat_with_report_node(report_id):
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id") or data.get("nodeId")
    message = data.get("message")
    if not node_id or not message:
        return _error("node_id 和 message 不能为空")
    service = ReportAnalysisService(report_id)
    return _success(service.chat_on_node(node_id, message, data.get("chat_history") or [], data.get("round_range")))
