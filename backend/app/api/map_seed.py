"""
Map-first seed APIs.
"""

from __future__ import annotations

from flask import jsonify, request

from . import map_bp
from ..models.task import TaskCancelledError, TaskManager, TaskStatus
from ..services.effort_contract import EffortContractError, build_effort_snapshot
from ..services.display_localization import public_error_message, sanitize_public_dto
from ..services.map_seed_manager import MapSeedManager
from ..services.simulation_manager import SimulationManager
from ..services.task_executor import TaskExecutor
from ..utils.logger import get_logger

logger = get_logger("envfish.api.map_seed")


def _public_success(data):
    return jsonify({"success": True, "data": sanitize_public_dto(data)})


def _public_failure(error, fallback: str, status: int = 500, *, code: str | None = None):
    payload = {"success": False, "error": public_error_message(error, fallback)}
    if code:
        payload["code"] = code
    return jsonify(payload), status


@map_bp.route("/geocode", methods=["POST"])
def geocode_location():
    try:
        data = request.get_json() or {}
        query = str(data.get("query") or data.get("location") or "").strip()
        radius_m = int(data.get("radius_m") or 3000)
        if not query:
            return jsonify({"success": False, "error": "请输入地点"}), 400

        seed_manager = MapSeedManager()
        candidates = seed_manager.geocode_location(query, limit=int(data.get("limit") or 5), radius_m=radius_m)
        return _public_success({
            "query": query,
            "candidates": candidates,
            "primary": candidates[0] if candidates else None,
        })
    except Exception as exc:
        logger.error(f"地点地理编码失败: {exc}")
        return _public_failure(exc, "地点解析失败，请稍后重试。")


@map_bp.route("/reverse-geocode", methods=["POST"])
def reverse_geocode_location():
    try:
        data = request.get_json() or {}
        lat = data.get("lat")
        lon = data.get("lon")
        radius_m = int(data.get("radius_m") or 3000)
        if lat is None or lon is None:
            return jsonify({"success": False, "error": "请先在地图上选择点位"}), 400

        seed_manager = MapSeedManager()
        context = seed_manager.resolve_area_context(lat=float(lat), lon=float(lon), radius_m=radius_m)
        return _public_success(context)
    except Exception as exc:
        logger.error(f"点位逆地理解析失败: {exc}")
        return _public_failure(exc, "点位解析失败，请稍后重试。")


@map_bp.route("/seed", methods=["POST"])
def create_map_seed():
    try:
        data = request.get_json() or {}
        lat = data.get("lat")
        lon = data.get("lon")
        radius_m = data.get("radius_m", 2000)

        if lat is None or lon is None:
            return jsonify({"success": False, "error": "请先在地图上选择点位"}), 400

        effort_snapshot = build_effort_snapshot(
            data.get("effort_level") or "high",
            effort_snapshot_id=data.get("effort_snapshot_id"),
        )
        seed_manager = MapSeedManager()
        seed = seed_manager.create_seed(
            lat=float(lat),
            lon=float(lon),
            radius_m=int(radius_m),
            simulation_requirement=str(data.get("simulation_requirement") or "").strip(),
            title=str(data.get("title") or "").strip(),
            requested_location=str(data.get("requested_location") or data.get("location") or "").strip(),
            focus_text=str(data.get("focus_text") or "").strip(),
            known_entities=str(data.get("known_entities") or "").strip(),
            analysis_boundaries=str(data.get("analysis_boundaries") or "").strip(),
            focus_mode=str(data.get("focus_mode") or "auto").strip(),
            golden_case_profile=str(data.get("golden_case_profile") or "").strip(),
            effort_snapshot=effort_snapshot,
        )

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            name="地图种子分析",
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
                task_result = {
                    "seed_id": seed["seed_id"],
                    "status": result.get("status"),
                    "summary": result.get("summary"),
                    "availability": seed_manager.seed_availability(result),
                    "data_quality": result.get("data_quality"),
                    "selection_summary": result.get("selection_summary"),
                }
                if seed_manager.is_formal_seed_ready(result):
                    task_manager.complete_task(
                        task_id,
                        result=task_result,
                        message="正式地理数据已生成",
                    )
                else:
                    availability = task_result["availability"]
                    message = str(availability.get("message") or "正式地理数据不可用")
                    task_manager.update_task(
                        task_id,
                        status=TaskStatus.FAILED,
                        progress=100,
                        message=message,
                        error=message,
                        result=task_result,
                    )
            except Exception as exc:
                if isinstance(exc, TaskCancelledError) or task_manager.is_cancelled(task_id):
                    cancel_reason = str(exc) or "用户强制停止"
                    logger.info(f"Map seed build cancelled: task_id={task_id}, seed_id={seed['seed_id']}")
                    seed_manager.update_seed(seed["seed_id"], status="failed", error=cancel_reason)
                    return

                logger.exception("Map seed build failed")
                task_manager.fail_task(
                    task_id,
                    public_error_message(exc, "地图区域分析失败，请稍后重试。"),
                )

        TaskExecutor(task_manager).start(task_id=task_id, target=run_seed)

        return _public_success({
            "seed_id": seed["seed_id"],
            "task_id": task_id,
            "status": "processing",
            "message": "地图区域分析已启动",
            "effort_snapshot_id": effort_snapshot["effort_snapshot_id"],
            "effort_snapshot": effort_snapshot,
        })
    except EffortContractError as exc:
        return _public_failure(exc, "分析投入配置无效，请重新选择。", 400, code="invalid_effort_snapshot")
    except Exception as exc:
        logger.error(f"启动 map seed 失败: {exc}")
        return _public_failure(exc, "地图区域分析启动失败，请稍后重试。")


@map_bp.route("/seed/status", methods=["POST"])
def get_map_seed_status():
    try:
        data = request.get_json() or {}
        task_id = data.get("task_id")
        seed_id = data.get("seed_id")

        seed = MapSeedManager.get_seed(seed_id) if seed_id else None
        if seed and MapSeedManager.is_formal_seed_ready(seed):
            return _public_success({
                        "seed_id": seed_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "地图种子图谱已生成",
                        "summary": seed.get("summary"),
                        "available": True,
                        "retryable": False,
                        "availability": MapSeedManager.seed_availability(seed),
                        "data_quality": seed.get("data_quality"),
                        "selection_summary": seed.get("selection_summary"),
            })
        if seed and seed.get("status") in {"ready", "unavailable"}:
            availability = MapSeedManager.seed_availability(seed)
            return _public_success({
                        "seed_id": seed_id,
                        "status": "unavailable",
                        "available": False,
                        "retryable": bool(availability.get("retryable")),
                        "progress": 100,
                        "message": availability.get("message") or "正式地理数据不可用",
                        "reason_code": availability.get("reason_code"),
                        "availability": availability,
                        "data_quality": seed.get("data_quality"),
                        "selection_summary": seed.get("selection_summary"),
            })
        if seed and seed.get("status") == "failed":
            return _public_success({
                        "seed_id": seed_id,
                        "status": "failed",
                        "progress": 100,
                        "message": seed.get("error") or "地图种子任务失败",
                        "error": seed.get("error"),
            })

        if not task_id:
            return jsonify({"success": False, "error": "缺少地图分析任务信息"}), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "地图分析任务不存在"}), 404

        payload = task.to_dict()
        if seed_id:
            payload["seed_id"] = seed_id
        return _public_success(payload)
    except Exception as exc:
        logger.error(f"获取 map seed 状态失败: {exc}")
        return _public_failure(exc, "获取地图分析状态失败，请稍后重试。")


@map_bp.route("/seed/<seed_id>", methods=["GET"])
def get_map_seed(seed_id: str):
    try:
        seed = MapSeedManager.get_seed(seed_id)
        if not seed:
            return jsonify({"success": False, "error": "地图区域分析结果不存在"}), 404

        availability = MapSeedManager.seed_availability(seed)
        if not MapSeedManager.is_formal_seed_ready(seed):
            seed["status"] = "unavailable" if seed.get("status") == "ready" else seed.get("status")
        seed["available"] = bool(availability.get("available"))
        seed["retryable"] = bool(availability.get("retryable"))
        seed["availability"] = availability

        graph_snapshot = MapSeedManager.get_graph_snapshot(seed_id, allow_unavailable=True)
        if graph_snapshot:
            seed["graph"] = graph_snapshot
            seed["graph_data"] = graph_snapshot.get("graph_data")

        report_text = MapSeedManager.get_report_text(seed_id, allow_unavailable=True)
        if report_text:
            seed["report_text"] = report_text

        return _public_success(seed)
    except Exception as exc:
        logger.error(f"获取 map seed 失败: {exc}")
        return _public_failure(exc, "获取地图区域分析结果失败，请稍后重试。")


@map_bp.route("/seed/<seed_id>/layers", methods=["GET"])
def get_map_seed_layers(seed_id: str):
    try:
        layers = MapSeedManager.get_layers(seed_id, allow_unavailable=True)
        if not layers:
            return jsonify({"success": False, "error": "地图图层不存在"}), 404
        return _public_success(layers)
    except Exception as exc:
        logger.error(f"获取 map seed 图层失败: {exc}")
        return _public_failure(exc, "获取地图图层失败，请稍后重试。")


@map_bp.route("/seed/<seed_id>/to-simulation", methods=["POST"])
def map_seed_to_simulation(seed_id: str):
    try:
        seed_manager = MapSeedManager()
        seed = seed_manager.get_seed(seed_id)
        if not seed:
            return jsonify({"success": False, "error": "地图区域分析结果不存在"}), 404
        if not seed_manager.is_formal_seed_ready(seed):
            availability = seed_manager.seed_availability(seed)
            return jsonify(
                {
                    "success": False,
                    "error": public_error_message(availability.get("message"), "正式地理数据不可用"),
                    "code": "formal_spatial_data_unavailable",
                    "data": {
                        "seed_id": seed_id,
                        "status": availability.get("status") or "unavailable",
                        "available": False,
                        "retryable": bool(availability.get("retryable")),
                        "reason_code": availability.get("reason_code"),
                        "provider_failures": availability.get("provider_failures") or [],
                    },
                }
            ), 409

        if seed.get("simulation_id"):
            manager = SimulationManager()
            state = manager.get_simulation(seed["simulation_id"])
            if state:
                return _public_success({
                            "seed_id": seed_id,
                            "project_id": seed.get("project_id"),
                            "simulation_id": state.simulation_id,
                            "status": state.status.value,
                            "already_created": True,
                })

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
            effort_snapshot=project_info.get("effort_snapshot") or seed.get("effort_snapshot"),
        )

        MapSeedManager.update_seed(seed_id, project_id=project_info["project_id"], simulation_id=state.simulation_id)
        return _public_success({
                    "seed_id": seed_id,
                    "project_id": project_info["project_id"],
                    "simulation_id": state.simulation_id,
                    "status": state.status.value,
                    "source_mode": "map_seed",
                    "effort_snapshot": state.effort_snapshot,
        })
    except Exception as exc:
        logger.error(f"map seed 转 simulation 失败: {exc}")
        return _public_failure(exc, "创建推演入口失败，请稍后重试。")


def _suggest_diffusion_template(seed: Dict[str, Any]) -> str:
    scene = (seed.get("scene_classification") or {}).get("primary_scene")
    if scene == "coastal":
        return "marine_current"
    if scene in {"wetland", "inland_water"}:
        return "inland_water_network"
    return "generic"
