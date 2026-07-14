"""
Scene material generator APIs.
"""

from __future__ import annotations

import json
from flask import jsonify, request

from . import scene_bp
from ..services.display_localization import public_error_message, sanitize_public_dto
from ..services.scene_material_generator import SceneMaterialGenerator
from ..utils.logger import get_logger

logger = get_logger("envfish.api.scene_material")


def _public_success(data):
    return jsonify({"success": True, "data": sanitize_public_dto(data)})


def _public_failure(error, fallback: str, status: int = 500):
    return jsonify({
        "success": False,
        "error": public_error_message(error, fallback),
    }), status


def _request_payload() -> dict:
    if request.content_type and "multipart/form-data" in request.content_type:
        payload = dict(request.form.items())
        for key in ("selected_points", "initial_variables", "semantic_artifact_ref"):
            if key in payload:
                try:
                    payload[key] = json.loads(payload[key])
                except Exception:
                    pass
        return payload
    return request.get_json(silent=True) or {}


def _wants_llm(payload: dict) -> bool:
    raw = str(payload.get("use_llm", "true")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


@scene_bp.route("/compose", methods=["POST"])
def compose_scene_material():
    try:
        payload = _request_payload()
        files = request.files.getlist("files") if request.files else []

        if not any(
            str(payload.get(key) or "").strip()
            for key in ("location", "event_or_baseline", "focus", "simulation_requirement")
        ) and not files and not payload.get("selected_points") and not payload.get("map_seed_id"):
            return jsonify({"success": False, "error": "请至少提供地点、事件/稳态描述、关注问题、文档或地图点位之一"}), 400

        generator = SceneMaterialGenerator(use_llm=_wants_llm(payload))
        seed = generator.compose(payload=payload, uploaded_files=files)
        return _public_success(seed)
    except Exception as exc:
        logger.error(f"生成场景素材失败: {exc}")
        return _public_failure(exc, "生成场景素材失败，请稍后重试。")


@scene_bp.route("/seed/<scene_id>", methods=["GET"])
def get_scene_material(scene_id: str):
    try:
        seed = SceneMaterialGenerator.get_seed(scene_id)
        if not seed:
            return jsonify({"success": False, "error": "场景素材不存在"}), 404
        report = SceneMaterialGenerator.get_report_text(scene_id)
        if report:
            seed["report_markdown"] = report
        return _public_success(seed)
    except Exception as exc:
        logger.error(f"读取场景素材失败: {exc}")
        return _public_failure(exc, "读取场景素材失败，请稍后重试。")


@scene_bp.route("/seed/<scene_id>/revise", methods=["POST"])
def revise_scene_material(scene_id: str):
    try:
        payload = request.get_json(silent=True) or {}
        instruction = str(payload.get("instruction") or "").strip()
        generator = SceneMaterialGenerator(use_llm=_wants_llm(payload))
        seed = generator.revise(scene_id=scene_id, instruction=instruction, payload=payload)
        return _public_success(seed)
    except Exception as exc:
        logger.error(f"修订场景素材失败: {exc}")
        return _public_failure(exc, "修订场景素材失败，请稍后重试。")
