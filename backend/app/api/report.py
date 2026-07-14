import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List

from flask import jsonify, request

from . import report_bp
from ..models.task import TaskManager
from ..services.display_localization import public_error_message, sanitize_public_dto
from ..services.report_agent import Report, ReportAgent, ReportManager, ReportStatus
from ..services.report_analysis import ReportAnalysisService
from ..services.simulation_manager import SimulationManager
from ..services.task_executor import TaskExecutor
from ..utils.logger import get_logger

logger = get_logger("envfish.api.report")


_CONSOLE_LOG_RE = re.compile(
    r"^\s*(?:\[(?P<time>\d{2}:\d{2}:\d{2})\]\s*)?"
    r"(?:(?P<level>INFO|WARNING|ERROR|DEBUG|CRITICAL)\s*:\s*)?"
    r"(?P<body>.*)$",
    re.IGNORECASE,
)
_TECHNICAL_LOG_RE = re.compile(
    r"(?:Traceback|\b[A-Za-z]+(?:Error|Exception)\b|"
    r"\b(?:GET|POST|PUT|PATCH|DELETE)\b|/api/|https?://|"
    r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])|"
    r"/(?:tmp|var|private|Users|home|opt|srv|app|etc)/|"
    r"\\(?:Users|Windows)\\)",
    re.IGNORECASE,
)
_TOOL_EVENT_RE = re.compile(
    r"(?:(?:执行|调用)\s*工具\s*[:：]|"
    r"\btool[\s_-]*(?:call|result)\b|<tool_calls?\b)",
    re.IGNORECASE,
)
_PATH_OR_ENDPOINT_RE = re.compile(
    r"(?:https?://\S+|"
    r"/api(?:/[A-Za-z0-9_./?=&%:\-]+)?|"
    r"/(?:tmp|var|private|Users|home|opt|srv|app|etc)"
    r"(?:/[^\s，。；：！？、\"'`<>{}\[\]()]*)+|"
    r"\\(?:Users|Windows)\\[^\s，。；：！？、\"'`<>{}\[\]()]*(?:\\[^\s，。；：！？、\"'`<>{}\[\]()]*)*|"
    r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])(?::\d{1,5})?(?:/\S*)?)",
    re.IGNORECASE,
)
_PREFIXED_LOG_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:sim|risk|region|agent|node|object|edge|mech|feature|context|"
    r"report|graph|mapseed|task|scenario|planning)[_:\-][A-Za-z0-9_.:\-]+"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_UUID_LOG_RE = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])",
    re.IGNORECASE,
)

_LOG_LEVEL_LABELS = {
    "INFO": "信息",
    "WARNING": "提醒",
    "ERROR": "异常",
    "DEBUG": "调试信息",
    "CRITICAL": "严重异常",
}
_AGENT_ACTION_LABELS = {
    "report_start": "报告生成开始",
    "planning_start": "开始规划报告大纲",
    "planning_context": "正在整理模拟上下文",
    "planning_complete": "报告大纲规划完成",
    "section_start": "开始生成章节",
    "react_thought": "正在整理章节内容",
    "tool_call": "正在执行内部分析步骤",
    "tool_result": "内部分析步骤已完成",
    "llm_response": "报告内容生成状态已更新",
    "section_content": "章节内容已生成",
    "section_complete": "章节生成完成",
    "report_complete": "报告生成完成",
    "error": "报告生成异常",
}
_AGENT_STAGE_LABELS = {
    "pending": "等待中",
    "planning": "规划中",
    "generating": "生成中",
    "completed": "已完成",
    "failed": "失败",
    "error": "异常",
}
_SAFE_AGENT_DETAIL_NUMBERS = {
    "iteration",
    "content_length",
    "response_length",
    "result_length",
    "total_sections",
    "total_time_seconds",
}


def _has_chinese_text(value: Any) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(value or "")))


def _sanitize_public_log_text(value: Any) -> str:
    """Keep readable Chinese log copy while removing diagnostic internals."""

    text = str(value or "").strip()
    if not text:
        return ""

    text = re.sub(
        r"<tool_calls?\b[^>]*>[\s\S]*?</tool_calls?>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = _PATH_OR_ENDPOINT_RE.sub("", text)
    text = re.sub(r"\b(?:GET|POST|PUT|PATCH|DELETE)\b", "", text, flags=re.IGNORECASE)
    text = _PREFIXED_LOG_ID_RE.sub("", text)
    text = _UUID_LOG_RE.sub("", text)
    text = re.sub(r"参数\s*[:：][\s\S]*$", "", text)
    text = re.sub(r"\{[^{}]*\}|\[[^\[\]]*\]", "", text)
    text = re.sub(
        r"(?<![A-Za-z0-9_])ReACT\s*生成章节",
        "开始生成章节",
        text,
        flags=re.IGNORECASE,
    )

    replacements = {
        "ReACT": "报告生成",
        "LLM": "模型",
        "Agent": "代理体",
        "True": "是",
        "False": "否",
    }
    for token, label in replacements.items():
        text = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
            label,
            text,
            flags=re.IGNORECASE,
        )
    text = text.replace("工具调用", "内部分析步骤")

    # The public log is prose, not a machine protocol. Remove every remaining
    # Latin token so new backend class names and tool identifiers cannot leak by
    # merely bypassing a finite translation table.
    text = re.sub(
        r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_.\-]*(?![A-Za-z0-9_])",
        "",
        text,
    )
    text = re.sub(r"[\"'`{}\[\]<>]", " ", text)
    text = re.sub(r"\(\s*\)|（\s*）", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([，。；：！？、])", r"\1", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s*:\s*(?=[\u3400-\u9fff])", "：", text)
    text = re.sub(r"([:：])(?:\s*[:：,，;；])+$", "", text)
    text = text.strip(" \t\r\n,，;；:：-_/\\.。|()（）")
    if not _has_chinese_text(text):
        return ""
    return text


def _project_console_log_line(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    match = _CONSOLE_LOG_RE.match(raw)
    timestamp = (match.group("time") if match else "") or ""
    level = ((match.group("level") if match else "") or "INFO").upper()
    body = (match.group("body") if match else raw) or ""
    technical = bool(_TECHNICAL_LOG_RE.search(body))

    if _TOOL_EVENT_RE.search(body):
        body = "正在执行内部分析步骤"
    else:
        body = _sanitize_public_log_text(body)

    if not body:
        if not technical:
            return ""
        body = "内部处理异常，详细信息已隐藏"

    prefix = f"[{timestamp}] " if timestamp else ""
    level_label = _LOG_LEVEL_LABELS.get(level, "信息")
    return f"{prefix}{level_label}：{body}"


def _public_log_metadata(payload: Any) -> Dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    return {
        "total_lines": max(0, int(source.get("total_lines") or 0)),
        "from_line": max(0, int(source.get("from_line") or 0)),
        "has_more": bool(source.get("has_more", False)),
    }


def _project_console_log_payload(payload: Any) -> Dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    logs: List[str] = []
    for item in source.get("logs") or []:
        projected = _project_console_log_line(item)
        if projected and (not logs or logs[-1] != projected):
            logs.append(projected)
    return {"logs": logs, **_public_log_metadata(source)}


def _safe_log_number(value: Any) -> Any:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _project_agent_log_entry(value: Any) -> Dict[str, Any] | None:
    if not isinstance(value, Mapping):
        message = _sanitize_public_log_text(value)
        if not message:
            return None
        return {
            "action": "报告状态已更新",
            "stage": "处理中",
            "section_title": "",
            "section_index": None,
            "details": {"message": message},
        }

    raw_action = str(value.get("action") or "").strip().lower()
    raw_stage = str(value.get("stage") or "").strip().lower()
    action = _AGENT_ACTION_LABELS.get(raw_action, "报告状态已更新")
    stage = _AGENT_STAGE_LABELS.get(raw_stage, "处理中")
    details = value.get("details") if isinstance(value.get("details"), Mapping) else {}
    section_title = _sanitize_public_log_text(value.get("section_title"))

    if raw_action in {"tool_call", "tool_result", "llm_response", "react_thought"}:
        message = action
    elif raw_action == "error":
        message = "报告生成出现异常，详细信息已隐藏"
    else:
        message = _sanitize_public_log_text(details.get("message") or value.get("message")) or action

    public_details: Dict[str, Any] = {"message": message}
    for key in _SAFE_AGENT_DETAIL_NUMBERS:
        number = _safe_log_number(details.get(key))
        if number is not None:
            public_details[key] = number

    timestamp = str(value.get("timestamp") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?", timestamp):
        timestamp = ""

    elapsed_seconds = _safe_log_number(value.get("elapsed_seconds"))
    section_index = _safe_log_number(value.get("section_index"))
    return {
        "timestamp": timestamp,
        "elapsed_seconds": elapsed_seconds,
        "action": action,
        "stage": stage,
        "section_title": section_title,
        "section_index": section_index,
        "details": public_details,
    }


def _project_agent_log_payload(payload: Any) -> Dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    logs: List[Dict[str, Any]] = []
    for item in source.get("logs") or []:
        projected = _project_agent_log_entry(item)
        if projected:
            logs.append(projected)
    return {"logs": logs, **_public_log_metadata(source)}


def _success(data=None, **extra):
    payload = {"success": True, "data": sanitize_public_dto(data if data is not None else {})}
    payload.update(extra)
    return jsonify(payload)


def _error(message, status=400):
    return jsonify({
        "success": False,
        "error": public_error_message(message, "请求信息不完整，请检查后重试。"),
    }), status


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
    existing = ReportManager.get_report(report_id)
    if not existing:
        placeholder = Report(
            report_id=report_id,
            simulation_id=simulation_id,
            graph_id=graph_id,
            simulation_requirement=simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat(),
        )
        ReportManager.save_report(placeholder)
        ReportManager.update_progress(
            report_id,
            "pending",
            0,
            "初始化报告...",
            completed_sections=[],
        )

    agent = ReportAgent(
        graph_id=graph_id,
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
    )
    task_manager = TaskManager()
    task_id = task_manager.create_task(
        name="生成正式报告",
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
    raw_log = ReportManager.get_console_log(report_id, from_line=from_line)
    return _success(_project_console_log_payload(raw_log))


@report_bp.route("/<report_id>/agent-log", methods=["GET"])
def get_report_agent_log(report_id):
    from_line = int(request.args.get("from_line", 0) or 0)
    raw_log = ReportManager.get_agent_log(report_id, from_line=from_line)
    return _success(_project_agent_log_payload(raw_log))


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
