"""
全局控制 API。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from flask import jsonify, request

from . import control_bp
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..services.map_seed_manager import MapSeedManager
from ..services.report_agent import ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..utils.logger import get_logger

logger = get_logger("envfish.api.control")


def _mark_cancelled_reports(cancelled_tasks: List[Dict[str, Any]], reason: str) -> List[str]:
    report_ids: List[str] = []
    for task in cancelled_tasks:
        if task.get("task_type") != "report_generate":
            continue
        report_id = (task.get("metadata") or {}).get("report_id")
        if not report_id:
            continue
        try:
            report = ReportManager.get_report(report_id)
            if report:
                report.status = ReportStatus.FAILED
                report.error = reason
                report.completed_at = datetime.now().isoformat()
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id=report_id,
                    status="failed",
                    progress=0,
                    message=reason,
                )
                report_ids.append(report_id)
        except Exception as exc:
            logger.warning(f"标记报告任务取消失败: report_id={report_id}, error={exc}")
    return report_ids


def _mark_cancelled_map_seeds(cancelled_tasks: List[Dict[str, Any]], reason: str) -> List[str]:
    seed_ids: List[str] = []
    manager = MapSeedManager()
    for task in cancelled_tasks:
        if task.get("task_type") != "map_seed_build":
            continue
        seed_id = (task.get("metadata") or {}).get("seed_id")
        if not seed_id:
            continue
        try:
            manager.update_seed(seed_id, status="failed", error=reason)
            seed_ids.append(seed_id)
        except Exception as exc:
            logger.warning(f"标记地图种子任务取消失败: seed_id={seed_id}, error={exc}")
    return seed_ids


def _mark_cancelled_projects(cancelled_tasks: List[Dict[str, Any]], reason: str) -> List[str]:
    cancelled_task_ids = {task.get("task_id") for task in cancelled_tasks if task.get("task_id")}
    project_ids: List[str] = []
    if not cancelled_task_ids:
        return project_ids

    for project in ProjectManager.list_projects(limit=500):
        if (
            project.status == ProjectStatus.GRAPH_BUILDING
            and project.graph_build_task_id in cancelled_task_ids
        ):
            project.status = ProjectStatus.FAILED
            project.error = reason
            ProjectManager.save_project(project)
            project_ids.append(project.project_id)

    return project_ids


def _mark_cancelled_simulations(cancelled_tasks: List[Dict[str, Any]], reason: str) -> List[str]:
    manager = SimulationManager()
    simulation_ids = {
        (task.get("metadata") or {}).get("simulation_id")
        for task in cancelled_tasks
        if task.get("task_type") == "simulation_prepare"
    }
    active_statuses = {
        SimulationStatus.PREPARING,
        SimulationStatus.RUNNING,
        SimulationStatus.PAUSED,
    }

    for state in manager.list_simulations():
        if state.status in active_statuses:
            simulation_ids.add(state.simulation_id)

    updated: List[str] = []
    for simulation_id in sorted(item for item in simulation_ids if item):
        try:
            if SimulationRunner.check_env_alive(simulation_id):
                try:
                    SimulationRunner.close_simulation_env(simulation_id=simulation_id, timeout=2.0)
                except Exception as exc:
                    logger.warning(f"关闭模拟环境失败: simulation_id={simulation_id}, error={exc}")

            state = manager.get_simulation(simulation_id)
            if state:
                state.status = SimulationStatus.STOPPED
                state.twitter_status = "stopped"
                state.reddit_status = "stopped"
                state.error = reason
                manager._save_simulation_state(state)
                updated.append(simulation_id)
        except Exception as exc:
            logger.warning(f"标记模拟停止失败: simulation_id={simulation_id}, error={exc}")

    return updated


@control_bp.route("/force-stop", methods=["POST"])
def force_stop_all():
    """
    强制停止所有 AI 推演任务。
    """
    try:
        data = request.get_json(silent=True) or {}
        reason = str(data.get("reason") or "用户强制停止").strip()[:200] or "用户强制停止"

        task_manager = TaskManager()
        cancelled_tasks = task_manager.cancel_active_tasks(reason=reason)
        stopped_runs = SimulationRunner.force_stop_all(reason=reason)

        updated = {
            "simulations": _mark_cancelled_simulations(cancelled_tasks, reason),
            "projects": _mark_cancelled_projects(cancelled_tasks, reason),
            "map_seeds": _mark_cancelled_map_seeds(cancelled_tasks, reason),
            "reports": _mark_cancelled_reports(cancelled_tasks, reason),
        }

        return jsonify(
            {
                "success": True,
                "data": {
                    "message": "强制停止指令已执行",
                    "reason": reason,
                    "cancelled_tasks": cancelled_tasks,
                    "cancelled_task_count": len(cancelled_tasks),
                    "stopped_runs": stopped_runs,
                    "updated": updated,
                },
            }
        )
    except Exception as exc:
        logger.exception("强制停止失败")
        return jsonify({"success": False, "error": str(exc)}), 500
