"""
Frozen golden-case restore APIs.
"""

from __future__ import annotations

from flask import jsonify, request

from . import golden_cases_bp
from ..services.display_localization import public_error_message, sanitize_public_dto
from ..services.golden_case_service import GoldenCaseService
from ..utils.logger import get_logger

logger = get_logger("envfish.api.golden_cases")


@golden_cases_bp.route("", methods=["GET"])
def list_golden_cases():
    """List available official replay cases."""
    try:
        return jsonify({"success": True, "data": sanitize_public_dto(GoldenCaseService.list_cases())})
    except Exception as exc:
        logger.exception("列出演示案例失败")
        return jsonify({"success": False, "error": public_error_message(exc, "读取演示案例失败，请稍后重试。")}), 500


@golden_cases_bp.route("/<case_id>/artifacts/<artifact_name>", methods=["GET"])
def get_golden_case_artifact(case_id: str, artifact_name: str):
    """Return a stable Step 1-4 business artifact for a frozen showcase."""
    try:
        payload = GoldenCaseService.read_artifact(case_id, artifact_name)
        return jsonify({"success": True, "data": sanitize_public_dto(payload)})
    except ValueError as exc:
        return jsonify({"success": False, "error": public_error_message(exc, "演示案例产物不存在。")}), 404
    except Exception as exc:
        logger.exception(f"读取演示案例产物失败: {case_id}/{artifact_name}")
        return jsonify({"success": False, "error": public_error_message(exc, "读取演示案例产物失败，请稍后重试。")}), 500


@golden_cases_bp.route("/<case_id>/restore", methods=["POST"])
def restore_golden_case(case_id: str):
    """
    Restore a frozen case as lightweight project/simulation/report handles.

    This does not call LLM, Zep, or simulation runners. It only creates local
    handles that point to the immutable golden artifact directory.
    """
    try:
        data = request.get_json(silent=True) or {}
        fresh = str(request.args.get("fresh") or data.get("fresh") or "").lower() in {"1", "true", "yes", "on"}
        reuse = not fresh and str(data.get("reuse", "true")).lower() not in {"0", "false", "no", "off"}
        payload = GoldenCaseService.restore_case(case_id, reuse=reuse)
        return jsonify({"success": True, "data": sanitize_public_dto(payload)})
    except ValueError as exc:
        return jsonify({"success": False, "error": public_error_message(exc, "演示案例不存在。")}), 404
    except Exception as exc:
        logger.exception(f"恢复演示案例失败: {case_id}")
        return jsonify({"success": False, "error": public_error_message(exc, "恢复演示案例失败，请稍后重试。")}), 500
