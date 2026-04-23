"""
Map-first seed APIs.
"""

from __future__ import annotations

import json
import threading
import traceback

from flask import jsonify, request

from . import map_bp
from ..models.task import TaskCancelledError, TaskManager, TaskStatus
from ..services.map_seed_manager import MapSeedManager
from ..services.simulation_manager import SimulationManager
from ..utils.logger import get_logger

logger = get_logger("envfish.api.map_seed")


@map_bp.route("/geocode", methods=["POST"])
def geocode_location():
    try:
        data = request.get_json() or {}
        query = str(data.get("query") or data.get("location") or "").strip()
        radius_m = int(data.get("radius_m") or 3000)
        if not query:
            return jsonify({"success": False, "error": "请提供 query 或 location"}), 400

        seed_manager = MapSeedManager()
        candidates = seed_manager.geocode_location(query, limit=int(data.get("limit") or 5), radius_m=radius_m)
        return jsonify(
            {
                "success": True,
                "data": {
                    "query": query,
                    "candidates": candidates,
                    "primary": candidates[0] if candidates else None,
                },
            }
        )
    except Exception as exc:
        logger.error(f"地点地理编码失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


@map_bp.route("/reverse-geocode", methods=["POST"])
def reverse_geocode_location():
    try:
        data = request.get_json() or {}
        lat = data.get("lat")
        lon = data.get("lon")
        radius_m = int(data.get("radius_m") or 3000)
        if lat is None or lon is None:
            return jsonify({"success": False, "error": "请提供 lat 和 lon"}), 400

        seed_manager = MapSeedManager()
        context = seed_manager.resolve_area_context(lat=float(lat), lon=float(lon), radius_m=radius_m)
        return jsonify({"success": True, "data": context})
    except Exception as exc:
        logger.error(f"点位逆地理解析失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


@map_bp.route("/seed", methods=["POST"])
def create_map_seed():
    try:
        data = request.get_json() or {}
        lat = data.get("lat")
        lon = data.get("lon")
        radius_m = data.get("radius_m", 2000)

        if lat is None or lon is None:
            return jsonify({"success": False, "error": "请提供 lat 和 lon"}), 400

        seed_manager = MapSeedManager()
        seed = seed_manager.create_seed(
            lat=float(lat),
            lon=float(lon),
            radius_m=int(radius_m),
            simulation_requirement=str(data.get("simulation_requirement") or "").strip(),
            title=str(data.get("title") or "").strip(),
        )

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="map_seed_build",
            metadata={"seed_id": seed["seed_id"]},
        )

        def run_seed() -> None:
            try:
                def ensure_running() -> None:
                    task_manager.ensure_not_cancelled(task_id)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=2,
                    message="启动地图种子任务",
                )
                ensure_running()

                def progress_callback(stage: str, progress: int, message: str) -> None:
                    ensure_running()
                    task_manager.update_task(
                        task_id,
                        progress=max(0, min(100, int(progress))),
                        message=message,
                        progress_detail={
                            "stage": stage,
                            "progress": progress,
                            "message": message,
                            "seed_id": seed["seed_id"],
                        },
                    )

                ensure_running()
                result = seed_manager.build_seed(seed["seed_id"], progress_callback=progress_callback)
                ensure_running()
                task_manager.complete_task(
                    task_id,
                    result={
                        "seed_id": seed["seed_id"],
                        "status": result.get("status"),
                        "summary": result.get("summary"),
                    },
                )
            except Exception as exc:
                if isinstance(exc, TaskCancelledError) or task_manager.is_cancelled(task_id):
                    cancel_reason = str(exc) or "用户强制停止"
                    logger.info(f"Map seed build cancelled: task_id={task_id}, seed_id={seed['seed_id']}")
                    seed_manager.update_seed(seed["seed_id"], status="failed", error=cancel_reason)
                    return

                logger.exception("Map seed build failed")
                task_manager.fail_task(task_id, str(exc))

        threading.Thread(target=run_seed, daemon=True).start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "seed_id": seed["seed_id"],
                    "task_id": task_id,
                    "status": "processing",
                    "message": "地图种子任务已启动",
                },
            }
        )
    except Exception as exc:
        logger.error(f"启动 map seed 失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


@map_bp.route("/seed/status", methods=["POST"])
def get_map_seed_status():
    try:
        data = request.get_json() or {}
        task_id = data.get("task_id")
        seed_id = data.get("seed_id")

        seed = MapSeedManager.get_seed(seed_id) if seed_id else None
        if seed and seed.get("status") == "ready":
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "seed_id": seed_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "地图种子图谱已生成",
                        "summary": seed.get("summary"),
                    },
                }
            )
        if seed and seed.get("status") == "failed":
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "seed_id": seed_id,
                        "status": "failed",
                        "progress": 100,
                        "message": seed.get("error") or "地图种子任务失败",
                        "error": seed.get("error"),
                    },
                }
            )

        if not task_id:
            return jsonify({"success": False, "error": "请提供 task_id 或 seed_id"}), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": f"任务不存在: {task_id}"}), 404

        payload = task.to_dict()
        if seed_id:
            payload["seed_id"] = seed_id
        return jsonify({"success": True, "data": payload})
    except Exception as exc:
        logger.error(f"获取 map seed 状态失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


@map_bp.route("/seed/<seed_id>", methods=["GET"])
def get_map_seed(seed_id: str):
    try:
        seed = MapSeedManager.get_seed(seed_id)
        if not seed:
            return jsonify({"success": False, "error": f"地图种子不存在: {seed_id}"}), 404

        graph_snapshot = MapSeedManager.get_graph_snapshot(seed_id)
        if graph_snapshot:
            seed["graph"] = graph_snapshot
            seed["graph_data"] = graph_snapshot.get("graph_data")

        report_text = MapSeedManager.get_report_text(seed_id)
        if report_text:
            seed["report_text"] = report_text

        return jsonify({"success": True, "data": seed})
    except Exception as exc:
        logger.error(f"获取 map seed 失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


@map_bp.route("/seed/<seed_id>/layers", methods=["GET"])
def get_map_seed_layers(seed_id: str):
    try:
        layers = MapSeedManager.get_layers(seed_id)
        if not layers:
            return jsonify({"success": False, "error": f"图层不存在: {seed_id}"}), 404
        return jsonify({"success": True, "data": layers})
    except Exception as exc:
        logger.error(f"获取 map seed 图层失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


@map_bp.route("/seed/<seed_id>/to-simulation", methods=["POST"])
def map_seed_to_simulation(seed_id: str):
    try:
        seed_manager = MapSeedManager()
        seed = seed_manager.get_seed(seed_id)
        if not seed:
            return jsonify({"success": False, "error": f"地图种子不存在: {seed_id}"}), 404
        if seed.get("status") != "ready":
            return jsonify({"success": False, "error": "地图种子尚未生成完成"}), 400

        if seed.get("simulation_id"):
            manager = SimulationManager()
            state = manager.get_simulation(seed["simulation_id"])
            if state:
                return jsonify(
                    {
                        "success": True,
                        "data": {
                            "seed_id": seed_id,
                            "project_id": seed.get("project_id"),
                            "simulation_id": state.simulation_id,
                            "status": state.status.value,
                            "already_created": True,
                        },
                    }
                )

        project_info = seed_manager.create_project_from_seed(seed_id)
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_info["project_id"],
            graph_id=f"mapseed_{seed_id}",
            enable_twitter=True,
            enable_reddit=True,
            engine_mode="envfish",
            scenario_mode="baseline_mode",
            diffusion_template=_suggest_diffusion_template(seed),
            source_mode="map_seed",
            map_seed_id=seed_id,
        )

        MapSeedManager.update_seed(seed_id, project_id=project_info["project_id"], simulation_id=state.simulation_id)
        return jsonify(
            {
                "success": True,
                "data": {
                    "seed_id": seed_id,
                    "project_id": project_info["project_id"],
                    "simulation_id": state.simulation_id,
                    "status": state.status.value,
                    "source_mode": "map_seed",
                },
            }
        )
    except Exception as exc:
        logger.error(f"map seed 转 simulation 失败: {exc}")
        return jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ), 500


def _suggest_diffusion_template(seed: Dict[str, Any]) -> str:
    scene = (seed.get("scene_classification") or {}).get("primary_scene")
    if scene == "coastal":
        return "marine_current"
    if scene in {"wetland", "inland_water"}:
        return "inland_water_network"
    return "generic"
