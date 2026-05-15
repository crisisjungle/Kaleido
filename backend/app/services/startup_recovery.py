"""
Startup recovery for interrupted in-process tasks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..utils.logger import get_logger
from .map_seed_manager import MapSeedManager
from .report_agent import ReportManager, ReportStatus
from .simulation_manager import SimulationManager, SimulationStatus

logger = get_logger("envfish.startup_recovery")


DEFAULT_RECOVERY_REASON = "服务重启后任务已中断，请重新提交"


def recover_interrupted_tasks(reason: str = DEFAULT_RECOVERY_REASON) -> List[Dict[str, Any]]:
    task_manager = TaskManager()
    interrupted = task_manager.fail_active_tasks(reason=reason)
    if not interrupted:
        return []

    task_ids = {item.get("task_id") for item in interrupted if item.get("task_id")}
    logger.warning("Recovered %s interrupted tasks after startup", len(task_ids))

    _recover_projects(task_ids, reason)
    _recover_simulations(interrupted, reason)
    _recover_map_seeds(interrupted, reason)
    _recover_reports(interrupted, reason)
    return interrupted


def _recover_projects(task_ids: set[str], reason: str) -> None:
    for project in ProjectManager.list_projects(limit=500):
        if project.status == ProjectStatus.GRAPH_BUILDING and project.graph_build_task_id in task_ids:
            project.status = ProjectStatus.FAILED
            project.error = reason
            ProjectManager.save_project(project)


def _recover_simulations(tasks: List[Dict[str, Any]], reason: str) -> None:
    manager = SimulationManager()
    simulation_ids = {
        (item.get("metadata") or {}).get("simulation_id")
        for item in tasks
        if item.get("task_type") == "simulation_prepare"
    }
    for simulation_id in sorted(item for item in simulation_ids if item):
        state = manager.get_simulation(simulation_id)
        if state and state.status == SimulationStatus.PREPARING:
            state.status = SimulationStatus.STOPPED
            state.error = reason
            manager._save_simulation_state(state)


def _recover_map_seeds(tasks: List[Dict[str, Any]], reason: str) -> None:
    seed_ids = {
        (item.get("metadata") or {}).get("seed_id")
        for item in tasks
        if item.get("task_type") == "map_seed_build"
    }
    for seed_id in sorted(item for item in seed_ids if item):
        try:
            MapSeedManager.update_seed(seed_id, status="failed", error=reason)
        except Exception as exc:
            logger.warning("Failed to recover map seed %s: %s", seed_id, exc)


def _recover_reports(tasks: List[Dict[str, Any]], reason: str) -> None:
    report_ids = {
        (item.get("metadata") or {}).get("report_id")
        for item in tasks
        if item.get("task_type") == "report_generate"
    }
    for report_id in sorted(item for item in report_ids if item):
        report = ReportManager.get_report(report_id)
        if report:
            report.status = ReportStatus.FAILED
            report.error = reason
            report.completed_at = datetime.now().isoformat()
            ReportManager.save_report(report)
        ReportManager.update_progress(report_id, "failed", -1, reason)
