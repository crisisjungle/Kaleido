"""
模拟相关API路由
Step2: Zep实体读取与过滤、OASIS模拟准备与运行（全程自动化）
"""

import hashlib
import json
import os
import re
import traceback
from contextlib import contextmanager
from typing import Any, Dict

import fcntl
from flask import request, jsonify, send_file

from . import simulation_bp
from ..config import Config
from ..services.map_seed_manager import MapSeedManager
from ..services.effort_contract import (
    EffortContractError,
    assert_effort_reference,
    assert_effort_snapshot_consistency,
    build_effort_snapshot,
    normalize_effort_snapshot,
)
from ..services.agent_planning_port import AgentPlanningPortError, plan_scenario_agents
from ..services.graph_builder import GraphBuilderService
from ..services.env_simulation_config_generator import normalize_search_mode
from ..services.mechanism_simulation_service import (
    LEGACY_SIMULATION_ARCHITECTURE,
    LLM_MECHANISM_ARCHITECTURE,
    normalize_simulation_architecture,
)
from ..services.scenario_planner import AGENT_V2_PLAN_SOURCE, ScenarioPlanner
from ..services.scenario_foundation_resolver import (
    FoundationResolutionError,
    ScenarioFoundationResolver,
)
from ..services.mechanism_aware_spatial_refiner import MechanismAwareSpatialRefiner
from ..services.spatial_catalog import SQLiteSpatialCatalog, SpatialCatalogFeature
from ..services.spatial_evidence import (
    build_spatial_refinement_snapshot,
    compile_facility_query_plan,
    normalize_spatial_catalog_candidate,
)
from ..services.semantic_input import SemanticArtifactStore, SemanticInputNormalizer
from ..services.scene_material_generator import SceneMaterialGenerator
from ..services.envfish_models import normalize_time_plan, normalize_transport_family
from ..services.risk_artifact_store import load_risk_artifacts, write_risk_artifacts
from ..services.risk_definition_builder import RiskDefinitionBuilder
from ..services.risk_event_engine import RiskEventEngine
from ..services.risk_runtime_tracker import RiskRuntimeTracker
from ..services.simulation_animation_service import SimulationAnimationService
from ..services.simulation_map_projection import SimulationMapProjectionBuilder
from ..services.simulation_realtime_graph import SimulationRealtimeGraphBuilder
from ..services.task_executor import TaskExecutor
from ..services.zep_entity_reader import ZepEntityReader
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..services.display_localization import public_error_message, sanitize_public_dto
from ..utils.atomic_file import read_json_file, write_json_file
from ..utils.logger import get_logger
from ..models.project import ProjectManager

logger = get_logger('envfish.api.simulation')


@simulation_bp.after_request
def _sanitize_simulation_public_response(response):
    """Apply one non-bypassable display boundary to every JSON route.

    The simulation blueprint contains legacy endpoints with slightly different
    response shapes.  Keeping the projection here preserves those contracts
    while ensuring no route can accidentally return raw display copy,
    traceback/debug fields, internal labels, paths, or exception details.
    Download/stream responses are intentionally left untouched.
    """

    if not response.is_json:
        return response
    payload = response.get_json(silent=True)
    if not isinstance(payload, (dict, list)):
        return response

    projected = sanitize_public_dto(payload)
    if isinstance(projected, dict) and projected.get("success") is False:
        projected["error"] = public_error_message(
            payload.get("error"),
            "请求未能完成，请稍后重试。",
        )

    response.set_data(json.dumps(projected, ensure_ascii=False, separators=(",", ":")))
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


def _public_runtime_success(data: Any):
    """Serialize a Step 3 runtime DTO through the public display boundary."""

    return jsonify({"success": True, "data": sanitize_public_dto(data)})


PREPARE_STAGE_LABELS = {
    "resolving_foundation": "核对并补充现实范围",
    "reading": "读取角色所需实体",
    "generating_profiles": "生成代理体与关系",
    "generating_config": "装配和校验场景",
    "copying_scripts": "完成运行工件",
    "completed": "已完成",
}

_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_INTERNAL_DISPLAY_PATTERN = re.compile(
    r"(?:(?:agent|entity|region|snapshot|fallback|unknown|unnamed)(?![A-Za-z0-9])|"
    r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+|"
    r"[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]+)+|"
    r"[0-9a-f]{8}-[0-9a-f-]{20,})",
    re.IGNORECASE,
)

_GROUNDING_SOURCE_LABELS = {
    "osm": "开放地图",
    "openstreetmap": "开放地图",
    "overpass": "开放地图要素",
    "worldcover": "全球地表覆盖资料",
    "esa_worldcover": "全球地表覆盖资料",
    "open_meteo": "公开气象资料",
    "noaa": "海洋与大气资料",
    "usgs": "地质与水文资料",
    "reverse_geocode": "地名检索资料",
}


def _chinese_display_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if (
        not text
        or not _CJK_PATTERN.search(text)
        or re.search(r"[A-Za-z]", text)
        or _INTERNAL_DISPLAY_PATTERN.search(text)
    ):
        return fallback
    return text


def _grounding_source_labels(values: Any) -> list[str]:
    labels = []
    for value in values if isinstance(values, list) else []:
        label = _GROUNDING_SOURCE_LABELS.get(str(value or "").strip().lower(), "外部资料")
        if label not in labels:
            labels.append(label)
    return labels


@contextmanager
def _prepare_reservation_lock(manager: SimulationManager, simulation_id: str):
    """Serialize prepare task reservation across web workers for one simulation."""

    lock_path = os.path.join(manager._get_simulation_dir(simulation_id), ".prepare-reservation.lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _injection_request_lock(manager: SimulationManager, simulation_id: str):
    """Serialize runtime injection and idempotency receipts per simulation."""

    lock_path = os.path.join(manager._get_simulation_dir(simulation_id), ".injection-request.lock")
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _normalize_injection_idempotency_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    if len(key) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key):
        raise ValueError("干预请求标识格式不正确。")
    return key


def _injection_receipt_path(manager: SimulationManager, simulation_id: str) -> str:
    return os.path.join(manager._get_simulation_dir(simulation_id), "injection_receipts.json")


def _read_injection_receipt(
    manager: SimulationManager,
    simulation_id: str,
    idempotency_key: str,
) -> Dict[str, Any] | None:
    if not idempotency_key:
        return None
    receipts = read_json_file(_injection_receipt_path(manager, simulation_id), default={})
    if not isinstance(receipts, dict):
        return None
    receipt = receipts.get(idempotency_key)
    return dict(receipt) if isinstance(receipt, dict) else None


def _write_injection_receipt(
    manager: SimulationManager,
    simulation_id: str,
    idempotency_key: str,
    receipt: Dict[str, Any],
) -> None:
    if not idempotency_key:
        return
    path = _injection_receipt_path(manager, simulation_id)
    receipts = read_json_file(path, default={})
    if not isinstance(receipts, dict):
        receipts = {}
    receipts[idempotency_key] = receipt
    if len(receipts) > 128:
        receipts = dict(list(receipts.items())[-128:])
    write_json_file(path, receipts)


def _find_active_prepare_task(task_manager: Any, state: Any) -> Any:
    """Return the latest pending/processing prepare task for this simulation."""

    from ..models.task import TaskStatus

    active_statuses = {TaskStatus.PENDING, TaskStatus.PROCESSING}
    task_id = str(getattr(state, "prepare_task_id", "") or "").strip()
    if task_id:
        task = task_manager.get_task(task_id)
        if task and task.task_type == "simulation_prepare" and task.status in active_statuses:
            return task

    for item in task_manager.list_tasks():
        if item.get("task_type") != "simulation_prepare":
            continue
        if str((item.get("metadata") or {}).get("simulation_id") or "") != state.simulation_id:
            continue
        if item.get("status") not in {status.value for status in active_statuses}:
            continue
        return task_manager.get_task(str(item.get("task_id") or ""))
    return None


def _active_prepare_hash(task: Any, state: Any) -> str:
    metadata = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
    if "planning_content_hash" in metadata:
        return str(metadata.get("planning_content_hash") or "")
    return str(getattr(state, "planning_content_hash", "") or "")


def _active_prepare_response(
    *,
    task: Any,
    state: Any,
    scenario_planning_input: Dict[str, Any],
    uses_scenario_planner: bool,
) -> Dict[str, Any]:
    progress_detail = task.progress_detail if isinstance(task.progress_detail, dict) else {}
    generation_stage = str(
        progress_detail.get("current_stage")
        or ("generating_profiles" if uses_scenario_planner else "reading")
    )
    payload = {
        "simulation_id": state.simulation_id,
        "task_id": task.task_id,
        "status": "preparing",
        "task_status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "message": "相同场景输入正在生成，已复用当前准备任务。",
        "progress": int(task.progress or (62 if uses_scenario_planner else 0)),
        "generation_stage": generation_stage,
        "generation_stage_label": _prepare_stage_label(generation_stage),
        "already_prepared": False,
        "reused_task": True,
        "effort_snapshot": state.effort_snapshot,
        "agent_plan_source": state.agent_plan_source or (AGENT_V2_PLAN_SOURCE if uses_scenario_planner else ""),
    }
    if uses_scenario_planner:
        payload["scenario_planning_input"] = scenario_planning_input
    return payload


def _prepare_stage_label(stage: Any) -> str:
    key = str(stage or "").strip()
    return PREPARE_STAGE_LABELS.get(key, "正在准备场景")


def _build_scenario_foundation(
    project: Any,
    state: Any,
    *,
    map_seed_id: str = "",
) -> Dict[str, Any]:
    """Create the immutable Step 1 reference consumed by the Step 2 planner."""

    effective_map_seed_id = str(map_seed_id or state.map_seed_id or "").strip()
    map_seed = MapSeedManager.get_seed(effective_map_seed_id) if effective_map_seed_id else None
    map_graph = (
        MapSeedManager.get_graph_snapshot(effective_map_seed_id, allow_unavailable=True)
        if effective_map_seed_id
        else None
    )
    map_input = (map_seed or {}).get("input") if isinstance((map_seed or {}).get("input"), dict) else {}
    region_ids = []
    target_catalog = []
    map_nodes = (
        (map_graph or {}).get("nodes")
        or ((map_graph or {}).get("graph_data") or {}).get("nodes")
        or []
    )
    for node in map_nodes:
        labels = [str(item).lower() for item in (node.get("labels") or [])]
        raw_type = " ".join(
            str(item or "").lower()
            for item in (
                node.get("label"),
                node.get("type"),
                node.get("entity_type"),
                (node.get("attributes") or {}).get("category"),
            )
        )
        node_id = str(node.get("uuid") or node.get("id") or "").strip()
        if not node_id:
            continue
        is_region = "region" in labels or "region" in raw_type
        attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        tags = attributes.get("tags") if isinstance(attributes.get("tags"), dict) else {}
        facility_class_keys = attributes.get("facility_class_keys") or []
        if isinstance(facility_class_keys, str):
            facility_class_keys = [facility_class_keys]
        elif not isinstance(facility_class_keys, list):
            facility_class_keys = []
        target_catalog.append({
            "id": node_id,
            "name": str(node.get("name") or node.get("label") or node_id),
            "aliases": list(attributes.get("aliases") or []),
            "kind": "region" if is_region else "entity",
            "category": str(attributes.get("category") or ""),
            "subtype": str(attributes.get("subtype") or ""),
            "facility_class_keys": list(facility_class_keys),
            "node_family": str(attributes.get("node_family") or ""),
            "spatial_level": str(attributes.get("spatial_level") or ""),
            "source_kind": str(attributes.get("source_kind") or ""),
            "source_key": str(
                attributes.get("source_key")
                or attributes.get("source_provider")
                or tags.get("provider")
                or attributes.get("provider")
                or ""
            ),
            "provider": str(
                tags.get("provider")
                or attributes.get("source_provider")
                or attributes.get("provider")
                or ""
            ),
            "source_record_id": str(attributes.get("source_record_id") or node_id),
            "evidence_grade": str(attributes.get("evidence_grade") or ""),
            "dataset_version": str(attributes.get("dataset_version") or ""),
            "coordinate_system": str(attributes.get("coordinate_system") or "WGS84"),
            "confidence": attributes.get("confidence"),
            "lat": attributes.get("lat"),
            "lon": attributes.get("lon"),
            "tags": dict(tags),
        })
        if is_region and node_id not in region_ids:
            region_ids.append(node_id)

    semantic_ref = (
        getattr(state, "semantic_artifact_ref", None)
        or getattr(project, "semantic_artifact_ref", None)
        or {}
    )
    semantic_artifact = SemanticArtifactStore.get_by_ref(semantic_ref)
    if not semantic_artifact:
        scene_seed = (
            SceneMaterialGenerator.get_seed(getattr(project, "scene_id", None))
            if getattr(project, "scene_id", None)
            else None
        ) or {}
        scene_input = scene_seed.get("input") if isinstance(scene_seed.get("input"), dict) else {}
        legacy_variables = (
            scene_seed.get("initial_variables")
            or list(getattr(state, "injected_variables", None) or [])
        )
        semantic_artifact = SemanticInputNormalizer().normalize_scene(
            payload={
                "location": (
                    scene_input.get("location")
                    or map_input.get("requested_location")
                    or (map_seed or {}).get("title")
                    or project.name
                ),
                "time_scope": scene_input.get("time_scope") or "",
                "event_or_baseline": scene_input.get("event_or_baseline") or "",
                "additional_context": (
                    scene_input.get("additional_context")
                    or getattr(project, "analysis_summary", "")
                    or ""
                ),
                "known_entities": scene_input.get("known_entities") or "",
                "analysis_boundaries": scene_input.get("analysis_boundaries") or "",
                "report_questions": scene_input.get("report_questions") or "",
                "simulation_requirement": (
                    scene_input.get("simulation_requirement")
                    or getattr(project, "simulation_requirement", "")
                    or ""
                ),
                "initial_variables": legacy_variables,
            },
            document_texts=[ProjectManager.get_extracted_text(project.project_id) or ""],
            map_context={
                "map_seed_id": effective_map_seed_id,
                "seed": map_seed or {},
                "graph_data": map_graph or {},
                "report_text": (
                    MapSeedManager.get_report_text(effective_map_seed_id)
                    if effective_map_seed_id else ""
                ),
            },
        )
        semantic_ref = SemanticArtifactStore.public_ref(semantic_artifact)
        state.semantic_artifact_ref = dict(semantic_ref)
        project.semantic_artifact_ref = dict(semantic_ref)
        ProjectManager.save_project(project)
    latest_semantic_artifact = semantic_artifact
    while (
        semantic_artifact
        and semantic_artifact.input_kind not in {"scene_definition", "scene_revision"}
        and semantic_artifact.previous_artifact_ref
    ):
        parent = SemanticArtifactStore.get_by_ref(semantic_artifact.previous_artifact_ref)
        if not parent:
            break
        semantic_artifact = parent
    if semantic_artifact:
        semantic_ref = SemanticArtifactStore.public_ref(semantic_artifact)
    elif latest_semantic_artifact:
        semantic_artifact = latest_semantic_artifact
        semantic_ref = SemanticArtifactStore.public_ref(latest_semantic_artifact)

    spatial_scope: Dict[str, Any] = {}
    try:
        center_lat = float(map_input.get("lat"))
        center_lon = float(map_input.get("lon"))
        radius_m = max(1, int(float(map_input.get("radius_m") or 3000)))
    except (TypeError, ValueError):
        pass
    else:
        if -90 <= center_lat <= 90 and -180 <= center_lon <= 180:
            spatial_scope = {
                "center_lat": center_lat,
                "center_lon": center_lon,
                "radius_m": radius_m,
                "coordinate_system": "WGS84",
            }

    foundation = {
        "artifact_id": effective_map_seed_id or project.project_id,
        "contract_version": "foundation.step1.v4",
        "project_id": project.project_id,
        "graph_id": state.graph_id,
        "map_seed_id": effective_map_seed_id,
        "location": (
            map_input.get("requested_location")
            or (map_seed or {}).get("title")
            or project.name
        ),
        "region_ids": region_ids,
        "target_catalog": target_catalog,
        "spatial_scope": spatial_scope,
        "semantic_artifact_ref": semantic_ref,
        "scene_semantics": (
            semantic_artifact.scene.model_dump(mode="json") if semantic_artifact else {}
        ),
        "semantic_events": (
            [item.model_dump(mode="json") for item in semantic_artifact.events]
            if semantic_artifact else []
        ),
        "semantic_policies": (
            [item.model_dump(mode="json") for item in semantic_artifact.policies]
            if semantic_artifact else []
        ),
        "evidence_sources": _foundation_evidence_sources(map_seed or {}),
    }
    canonical = json.dumps(foundation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    foundation["content_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return foundation


def _foundation_evidence_sources(map_seed: Dict[str, Any]) -> list[Dict[str, Any]]:
    quality = map_seed.get("data_quality") if isinstance(map_seed.get("data_quality"), dict) else {}
    providers = quality.get("providers") if isinstance(quality.get("providers"), dict) else {}
    return [
        {
            "source": str(name),
            "status": str((details or {}).get("status") or ""),
        }
        for name, details in providers.items()
        if isinstance(details, dict)
    ]


def _refine_spatial_evidence(
    facility_query_plan: Any,
    *,
    foundation: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute the R3 local-catalog pass without making Step 2 depend on it.

    Catalog construction can fail because of local storage permissions or a
    damaged database.  That is an operational failure, not evidence that the
    requested facility does not exist.  Preserve the scenario and emit an
    explicit failed provider attempt while leaving requirements uncovered.
    """

    try:
        with SQLiteSpatialCatalog(Config.SPATIAL_CATALOG_PATH) as catalog:
            reusable_features = _foundation_spatial_catalog_features(foundation)
            if reusable_features:
                catalog.upsert_many(reusable_features)
            return MechanismAwareSpatialRefiner(
                catalog,
                query_limit=Config.SPATIAL_CATALOG_QUERY_LIMIT,
            ).refine(
                facility_query_plan,
                foundation=foundation,
            ).to_dict()
    except Exception as exc:
        logger.exception(
            "spatial_refinement.catalog_unavailable catalog=%s error_type=%s",
            Config.SPATIAL_CATALOG_PATH,
            type(exc).__name__,
        )
        return build_spatial_refinement_snapshot(
            facility_query_plan,
            target_catalog=foundation.get("target_catalog") or [],
            provider_attempts=[
                {
                    "provider_key": "controlled_spatial_catalog",
                    "status": "failed",
                    "reason_code": "catalog_unavailable",
                    "error_type": type(exc).__name__,
                    "result_count": 0,
                }
            ],
            source_versions=foundation.get("evidence_sources") or [],
        ).to_dict()


def _foundation_spatial_catalog_features(
    foundation: Dict[str, Any],
) -> list[SpatialCatalogFeature]:
    """Project traceable Step 1 point evidence into the reusable local index."""

    features: list[SpatialCatalogFeature] = []
    dataset_version = str(
        foundation.get("map_seed_id")
        or foundation.get("content_hash")
        or "unversioned"
    ).strip()
    for raw in foundation.get("target_catalog") or []:
        item = normalize_spatial_catalog_candidate(raw)
        if item is None or str(item.get("kind") or "").lower() == "region":
            continue
        if not item.get("facility_class_keys"):
            continue
        try:
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        coordinate_system = str(item.get("coordinate_system") or "WGS84").strip().upper()
        if coordinate_system != "WGS84":
            continue
        feature_id = str(item.get("feature_id") or "").strip()
        display_name = str(
            item.get("display_name")
            or item.get("name")
            or item.get("label_zh")
            or ""
        ).strip()
        if not feature_id or not display_name:
            continue
        source_key = str(
            item.get("source_key") or item.get("provider") or "step1_map_seed"
        ).strip()
        provider = str(item.get("provider") or source_key).strip()
        properties = {
            key: item.get(key)
            for key in (
                "aliases",
                "category",
                "subtype",
                "node_family",
                "spatial_level",
                "source_kind",
                "confidence",
            )
            if item.get(key) not in (None, "", [], {})
        }
        try:
            features.append(
                SpatialCatalogFeature(
                    feature_id=feature_id,
                    display_name=display_name,
                    facility_class_keys=tuple(item.get("facility_class_keys") or []),
                    geometry={"type": "Point", "coordinates": [lon, lat]},
                    bbox=(lon, lat, lon, lat),
                    source_key=source_key,
                    provider=provider,
                    source_record_id=str(item.get("source_record_id") or feature_id),
                    evidence_grade=str(item.get("evidence_grade") or "D"),
                    dataset_version=str(item.get("dataset_version") or dataset_version),
                    coordinate_system="WGS84",
                    tags=dict(item.get("tags") or {}),
                    properties=properties,
                )
            )
        except (TypeError, ValueError):
            logger.debug(
                "spatial_catalog.skip_invalid_foundation_feature feature_id=%s",
                feature_id,
            )
    return features


def _assert_workflow_effort_consistency(project: Any, state: Any) -> Dict[str, Any]:
    simulation_snapshot = normalize_effort_snapshot(state.effort_snapshot)
    if getattr(project, "effort_snapshot", None):
        assert_effort_snapshot_consistency(
            project.effort_snapshot,
            simulation_snapshot,
            reference_name="项目",
            candidate_name="模拟",
        )
    if state.map_seed_id:
        seed = MapSeedManager.get_seed(state.map_seed_id)
        if not seed:
            raise EffortContractError("模拟引用的第一步地图种子不存在")
        seed_snapshot = seed.get("effort_snapshot")
        if not isinstance(seed_snapshot, dict):
            raise EffortContractError("第一步地图种子缺少已锁定的分析强度快照")
        assert_effort_snapshot_consistency(
            seed_snapshot,
            simulation_snapshot,
            reference_name="第一步地图种子",
            candidate_name="模拟",
        )
    return simulation_snapshot


def _scenario_temporal_payload(scenario: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    plan = dict(scenario.get("temporal_plan") or {})
    step_unit = str(plan.get("step_unit") or "day")
    step_size = max(1, int(plan.get("step_value") or 1))
    total_rounds = max(4, int(plan.get("total_rounds") or 12))
    time_plan = {
        "step_unit": step_unit,
        "step_size": step_size,
        "total_rounds": total_rounds,
        "total_coverage_label": str(plan.get("coverage_label_zh") or ""),
        "reasoning_summary": str(plan.get("generation_reason_zh") or ""),
        "source": "scenario_planner",
    }
    normalized = normalize_time_plan(time_plan, total_rounds=total_rounds, source="scenario_planner")
    temporal_profile = {
        "preset": normalized.get("preset") or "standard",
        "total_rounds": normalized["total_rounds"],
        "minutes_per_round": normalized["minutes_per_round"],
    }
    return normalized, temporal_profile


def _validate_step2_planning_request(data: Dict[str, Any]) -> None:
    missing_fields = [field for field in ("event_inputs", "policy_inputs") if field not in data]
    if missing_fields:
        raise ValueError("生成配置时必须提交完整的灾害事件和政策措施")
    for field_name, label in (("event_inputs", "灾害事件"), ("policy_inputs", "政策措施")):
        # One source sentence may legitimately project into both an event and a
        # policy. IDs only need to be unique within each semantic collection.
        seen_ids = set()
        values = data.get(field_name, [])
        if values is None:
            values = []
        if not isinstance(values, list):
            raise ValueError(f"{label}必须使用数组格式")
        for index, item in enumerate(values, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"{label}第 {index} 项格式无效")
            if field_name == "event_inputs" and not str(
                item.get("name") or item.get("title") or item.get("description") or ""
            ).strip():
                raise ValueError(f"灾害事件第 {index} 项缺少事件内容")
            input_id = str(item.get("input_id") or "").strip()
            if input_id:
                if input_id in seen_ids:
                    raise ValueError(f"输入标识重复: {input_id}")
                seen_ids.add(input_id)
            for target_field, target_label in (
                ("target_region_ids", "目标区域"),
                ("target_entity_ids", "目标设施或对象"),
            ):
                targets = item.get(target_field, [])
                if targets is not None and not isinstance(targets, list):
                    raise ValueError(f"{label}第 {index} 项的{target_label}必须使用数组格式")
            target_labels = item.get("target_labels", [])
            if target_labels is not None and not isinstance(target_labels, list):
                raise ValueError(f"{label}第 {index} 项的目标名称必须使用数组格式")
    if not data.get("event_inputs"):
        raise ValueError("至少需要一个有效灾害事件才能生成配置")
    overrides = data.get("advanced_overrides", {})
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("高级设置必须使用对象格式")


def _authoritative_step2_snapshot(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "input_kind": "scenario_configuration",
        "authority": "authoritative",
        "event_inputs": list(data.get("event_inputs") or []),
        "policy_inputs": list(data.get("policy_inputs") or []),
        "advanced_overrides": dict(data.get("advanced_overrides") or {}),
        "scenario_location": str(data.get("scenario_location") or "").strip(),
    }


def _snapshot_hash(value: Dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _planning_input_matches_existing(
    manager: SimulationManager,
    simulation_id: str,
    scenario_planning_input: Dict[str, Any],
) -> bool:
    existing = read_json_file(
        os.path.join(manager._get_simulation_dir(simulation_id), "scenario_planning_input.json"),
        default={},
    )
    if not isinstance(existing, dict) or not existing:
        return False
    return bool(
        existing.get("content_hash")
        and existing.get("content_hash") == scenario_planning_input.get("content_hash")
    )


# Interview prompt 优化前缀
# 添加此前缀可以避免Agent调用工具，直接用文本回复
INTERVIEW_PROMPT_PREFIX = "结合你的人设、所有的过往记忆与行动，不调用任何工具直接用文本回复我："


def optimize_interview_prompt(prompt: str) -> str:
    """
    优化Interview提问，添加前缀避免Agent调用工具
    
    Args:
        prompt: 原始提问

    Returns:
        优化后的提问
    """
    if not prompt:
        return prompt
    # 避免重复添加前缀
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def _load_risk_bundle(simulation_id: str) -> tuple[str, Dict[str, Any]]:
    manager = SimulationManager()
    sim_dir = manager.resolve_artifact_dir(simulation_id, create_if_missing=False)
    if not sim_dir:
        sim_dir = manager._get_simulation_dir(simulation_id)
    return sim_dir, load_risk_artifacts(sim_dir)


def _sync_risk_fields_to_config(sim_dir: str, risk_bundle: Dict[str, Any]) -> None:
    config_path = os.path.join(sim_dir, "simulation_config.json")
    if not os.path.exists(config_path):
        return
    config = read_json_file(config_path, default=None)
    if not config:
        return
    config["risk_definitions"] = risk_bundle.get("risk_definitions", [])
    config["risk_contract_version"] = int(risk_bundle.get("risk_contract_version") or 1)
    config["risk_generation_audit"] = risk_bundle.get("risk_generation_audit", {})
    config["latest_risk_runtime_state"] = risk_bundle.get("latest_risk_runtime_state", {})
    config["risk_objects"] = risk_bundle.get("risk_objects", [])
    summary = risk_bundle.get("risk_objects_summary") or {}
    config["primary_risk_object_id"] = summary.get("primary_risk_object_id") or config.get("primary_risk_object_id", "")
    config["primary_active_risk_id"] = (
        risk_bundle.get("latest_risk_runtime_state", {}).get("primary_active_risk_id")
        or config.get("primary_active_risk_id", "")
    )
    write_json_file(config_path, config)


# ============== 实体读取接口 ==============

@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    获取图谱中的所有实体（已过滤）
    
    只返回符合预定义实体类型的节点（Labels不只是Entity的节点）
    
    Query参数：
        entity_types: 逗号分隔的实体类型列表（可选，用于进一步过滤）
        enrich: 是否获取相关边信息（默认true）
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "图谱服务凭证未配置"
            }), 500
        
        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        logger.info(f"获取图谱实体: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")
        
        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(f"获取图谱实体失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """获取单个实体的详细信息"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "图谱服务凭证未配置"
            }), 500
        
        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)
        
        if not entity:
            return jsonify({
                "success": False,
                "error": f"实体不存在: {entity_uuid}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })
        
    except Exception as e:
        logger.error(f"获取实体详情失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """获取指定类型的所有实体"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "图谱服务凭证未配置"
            }), 500
        
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })
        
    except Exception as e:
        logger.error(f"获取实体失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 模拟管理接口 ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """
    创建新的模拟
    
    注意：max_rounds等参数由LLM智能生成，无需手动设置
    
    请求（JSON）：
        {
            "project_id": "proj_xxxx",      // 必填
            "graph_id": "envfish_xxxx",    // 可选，如不提供则从project获取
            "enable_twitter": true,          // 可选，默认true
            "enable_reddit": true            // 可选，默认true
        }
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "envfish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "请提供项目编号"
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"项目不存在: {project_id}"
            }), 404
        
        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "项目尚未构建图谱，请先完成项目图谱构建。"
            }), 400

        if project.effort_snapshot:
            effort_snapshot = normalize_effort_snapshot(project.effort_snapshot)
        else:
            effort_snapshot = build_effort_snapshot("high")
            project.effort_snapshot = effort_snapshot
            ProjectManager.save_project(project)
        map_seed_id = str(data.get('map_seed_id') or getattr(project, 'map_seed_id', '') or '').strip()
        if map_seed_id:
            map_seed = MapSeedManager.get_seed(map_seed_id)
            if not map_seed:
                return jsonify({
                    "success": False,
                    "error": f"第一步地图种子不存在: {map_seed_id}",
                }), 404
            seed_snapshot = map_seed.get("effort_snapshot")
            if not isinstance(seed_snapshot, dict):
                raise EffortContractError("第一步地图种子缺少已锁定的分析强度快照")
            assert_effort_snapshot_consistency(
                effort_snapshot,
                seed_snapshot,
                reference_name="项目",
                candidate_name="第一步地图种子",
            )
        if data.get('effort_snapshot_id'):
            assert_effort_reference(
                effort_snapshot,
                effort_snapshot_id=data.get('effort_snapshot_id'),
                requested_level=data.get('effort_level'),
            )
        
        manager = SimulationManager()
        time_plan = normalize_time_plan(
            data.get('time_plan'),
            total_rounds=data.get('configured_total_rounds', data.get('max_rounds', 12)),
            minutes_per_round=data.get('configured_minutes_per_round', data.get('minutes_per_round', 60)),
            preset=data.get('temporal_preset', 'standard'),
            reference_time=data.get('reference_time', ''),
            source=data.get('time_plan_mode', 'auto'),
        )
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
            engine_mode=data.get('engine_mode', 'envfish'),
            simulation_architecture=normalize_simulation_architecture(
                data.get('simulation_architecture', LEGACY_SIMULATION_ARCHITECTURE)
            ),
            scenario_mode=data.get('scenario_mode', 'baseline_mode'),
            diffusion_template=normalize_transport_family(data.get('diffusion_template', 'marine')),
            hazard_template_id=data.get('hazard_template_id', ''),
            search_mode=normalize_search_mode(data.get('search_mode', 'fast')),
            temporal_preset=time_plan.get('preset', data.get('temporal_preset', 'standard')),
            configured_total_rounds=time_plan.get('total_rounds', data.get('configured_total_rounds', data.get('max_rounds', 12))),
            configured_minutes_per_round=time_plan.get('minutes_per_round', data.get('configured_minutes_per_round', data.get('minutes_per_round', 60))),
            time_plan_mode=data.get('time_plan_mode', 'auto'),
            time_plan=time_plan,
            reference_time=data.get('reference_time', ''),
            diffusion_provider=data.get('diffusion_provider', 'auto'),
            source_mode=data.get('source_mode', 'graph'),
            map_seed_id=map_seed_id or None,
            effort_snapshot=effort_snapshot,
            semantic_artifact_ref=(
                data.get('semantic_artifact_ref')
                or getattr(project, 'semantic_artifact_ref', None)
                or {}
            ),
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except EffortContractError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "code": "effort_snapshot_conflict",
        }), 409
    except Exception as e:
        logger.error(f"创建模拟失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": "创建模拟失败，请稍后重试。",
            "code": "simulation_create_failed",
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    检查模拟是否已经准备完成
    
    检查条件：
    1. state.json 存在且 status 为 "ready"
    2. 必要文件存在：reddit_profiles.json, twitter_profiles.csv, simulation_config.json
    
    注意：运行脚本(run_*.py)保留在 backend/scripts/ 目录，不再复制到模拟目录
    
    Args:
        simulation_id: 模拟ID
        
    Returns:
        (is_prepared: bool, info: dict)
    """
    import os
    from ..config import Config
    
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    
    # 检查目录是否存在
    if not os.path.exists(simulation_dir):
        return False, {"reason": "模拟目录不存在"}
    
    # 必要文件列表（不包括脚本，脚本位于 backend/scripts/）
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]
    
    # 检查文件是否存在
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": "缺少必要文件",
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    # 检查state.json中的状态
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        state_data = read_json_file(state_file, default={})
        if not state_data:
            return False, {"reason": "读取状态文件失败"}
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        
        # 详细日志
        logger.debug(f"检测模拟准备状态: {simulation_id}, status={status}, config_generated={config_generated}")
        
        # 如果 config_generated=True 且文件存在，认为准备完成
        # 以下状态都说明准备工作已完成：
        # - ready: 准备完成，可以运行
        # - preparing: 如果 config_generated=True 说明已完成
        # - running: 正在运行，说明准备早就完成了
        # - completed: 运行完成，说明准备早就完成了
        # - stopped: 已停止，说明准备早就完成了
        # - failed: 运行失败（但准备是完成的）
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            # 获取文件统计信息
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")
            
            profiles_count = 0
            if os.path.exists(profiles_file):
                profiles_data = read_json_file(profiles_file, default=[])
                profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
            
            # 如果状态是preparing但文件已完成，自动更新状态为ready
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    write_json_file(state_file, state_data)
                    logger.info(f"自动更新模拟状态: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"自动更新状态失败: {e}")
            
            logger.info(f"模拟 {simulation_id} 检测结果: 已准备完成 (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"模拟 {simulation_id} 检测结果: 未准备完成 (status={status}, config_generated={config_generated})")
            return False, {
                "reason": "当前场景尚未完成准备，配置文件仍在生成或校验中。",
                "status": status,
                "config_generated": config_generated
            }
            
    except Exception as e:
        return False, {"reason": f"读取状态文件失败: {str(e)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """
    准备模拟环境（异步任务，LLM智能生成所有参数）
    
    这是一个耗时操作，接口会立即返回task_id，
    使用 GET /api/simulation/prepare/status 查询进度
    
    特性：
    - 自动检测已完成的准备工作，避免重复生成
    - 如果已准备完成，直接返回已有结果
    - 支持强制重新生成（force_regenerate=true）
    
    步骤：
    1. 检查是否已有完成的准备工作
    2. 从Zep图谱读取并过滤实体
    3. 为每个实体生成代理体画像（带重试机制）
    4. LLM智能生成模拟配置（带重试机制）
    5. 保存配置文件和预设脚本
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",                   // 必填，模拟ID
            "entity_types": ["Student", "PublicFigure"],  // 可选，指定实体类型
            "use_llm_for_profiles": true,                 // 可选，是否用LLM生成人设
            "parallel_profile_count": 5,                  // 可选，并行生成人设数量，默认5
            "force_regenerate": false                     // 可选，强制重新生成，默认false
        }
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // 新任务时返回
                "status": "preparing|ready",
                "message": "准备任务已启动|已有完成的准备工作",
                "already_prepared": true|false    // 是否已准备完成
            }
        }
    """
    from ..models.task import TaskCancelledError, TaskManager, TaskStatus

    task_id = None
    task_manager = None
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": "未找到对应的模拟任务。"
            }), 404

        uses_new_scenario_contract = 'event_inputs' in data or 'policy_inputs' in data
        uses_scenario_planner = uses_new_scenario_contract or 'injected_variables' in data
        if uses_new_scenario_contract:
            _validate_step2_planning_request(data)
        
        if state.is_replay_only:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "status": "ready",
                    "message": "冻结演示案例已准备完成，无需再次生成外部资料与代理体。",
                    "already_prepared": True,
                    "scenario_mode": state.scenario_mode,
                    "diffusion_template": state.diffusion_template,
                    "hazard_template_id": state.hazard_template_id,
                    "search_mode": state.search_mode,
                    "temporal_preset": state.temporal_preset,
                    "configured_total_rounds": state.configured_total_rounds,
                    "configured_minutes_per_round": state.configured_minutes_per_round,
                    "reference_time": state.reference_time,
                    "is_replay_only": True,
                    "effort_snapshot": state.effort_snapshot,
                },
            })

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"项目不存在: {state.project_id}"
            }), 404

        effort_snapshot = _assert_workflow_effort_consistency(project, state)
        state.effort_snapshot = effort_snapshot
        force_regenerate = bool(data.get('force_regenerate', False))
        submitted_snapshot: Dict[str, Any] = {}
        submitted_snapshot_hash = ""
        if uses_new_scenario_contract:
            assert_effort_reference(
                effort_snapshot,
                effort_snapshot_id=data.get('effort_snapshot_id'),
                requested_level=data.get('effort_level'),
            )
            submitted_snapshot = _authoritative_step2_snapshot(data)
            submitted_snapshot_hash = _snapshot_hash(submitted_snapshot)
            if state.config_generated and state.status in {
                SimulationStatus.READY,
                SimulationStatus.RUNNING,
                SimulationStatus.PAUSED,
                SimulationStatus.STOPPED,
                SimulationStatus.COMPLETED,
                SimulationStatus.FAILED,
            }:
                snapshot_path = os.path.join(
                    manager._get_simulation_dir(simulation_id),
                    'scenario_configuration_input.json',
                )
                existing_snapshot = read_json_file(snapshot_path, default={}) or {}
                if (
                    not force_regenerate
                    and submitted_snapshot_hash
                    and submitted_snapshot_hash == str(existing_snapshot.get('submitted_input_hash') or '')
                ):
                    existing_config = read_json_file(
                        os.path.join(manager._get_simulation_dir(simulation_id), 'simulation_config.json'),
                        default={},
                    ) or {}
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "status": state.status.value,
                            "already_prepared": True,
                            "event_inputs": list(existing_config.get('event_inputs') or []),
                            "policy_inputs": list(existing_config.get('policy_inputs') or []),
                            "resolved_foundation_ref": dict(existing_config.get('resolved_foundation_ref') or {}),
                            "step1_suggestion_ref": dict(existing_config.get('step1_suggestion_ref') or {}),
                            "scenario_input_authority": "authoritative",
                        },
                    })
                return jsonify({
                    "success": False,
                    "error": "推演配置生成后已锁定，不能覆盖或重新生成。",
                    "code": "scenario_configuration_locked",
                    "stage": "场景输入校验",
                }), 409

        scenario_artifact = None
        scenario_planning_input: Dict[str, Any] = {}
        facility_query_plan: Dict[str, Any] = {}
        spatial_refinement_snapshot: Dict[str, Any] = {}
        if uses_scenario_planner:
            base_seed_id = str(state.base_map_seed_id or state.map_seed_id or "").strip()
            foundation = _build_scenario_foundation(project, state, map_seed_id=base_seed_id)
            if uses_new_scenario_contract:
                semantic_event_inputs = data.get('event_inputs') or []
                semantic_policy_inputs = data.get('policy_inputs') or []
                requested_foundation_ref = data.get('foundation_ref')
                if isinstance(requested_foundation_ref, dict):
                    requested_seed_id = str(requested_foundation_ref.get('map_seed_id') or '').strip()
                    requested_hash = str(requested_foundation_ref.get('content_hash') or '').strip()
                    if (
                        (requested_seed_id and requested_seed_id != str(foundation.get('map_seed_id') or ''))
                        or (requested_hash and requested_hash != str(foundation.get('content_hash') or ''))
                    ):
                        return jsonify({
                            "success": False,
                            "error": "现实背景已发生变化，请重新进入场景配置。",
                            "code": "foundation_reference_stale",
                            "stage": "核对现实范围",
                        }), 409
                try:
                    resolution = ScenarioFoundationResolver().resolve(
                        base_foundation=foundation,
                        event_inputs=semantic_event_inputs,
                        policy_inputs=semantic_policy_inputs,
                        simulation_id=simulation_id,
                        effort_snapshot=effort_snapshot,
                        scenario_location=str(data.get('scenario_location') or ''),
                        foundation_builder=lambda seed_id: _build_scenario_foundation(
                            project,
                            state,
                            map_seed_id=seed_id,
                        ),
                    )
                except FoundationResolutionError as exc:
                    write_json_file(
                        os.path.join(manager._get_simulation_dir(simulation_id), 'foundation_resolution.json'),
                        exc.artifact,
                    )
                    logger.warning(
                        "foundation.resolve blocked simulation_id=%s code=%s reasons=%s unresolved=%s",
                        simulation_id,
                        exc.code,
                        exc.artifact.get('enrichment_reasons'),
                        exc.artifact.get('unresolved_targets'),
                    )
                    return jsonify({
                        "success": False,
                        "error": "当前输入中的地点或对象无法从现实资料中确认，请返回背景定义明确地点或对象。",
                        "code": exc.code,
                        "stage": "核对现实范围",
                    }), 409
                foundation = resolution.foundation
                semantic_event_inputs = resolution.event_inputs
                semantic_policy_inputs = resolution.policy_inputs
                write_json_file(
                    os.path.join(manager._get_simulation_dir(simulation_id), 'foundation_resolution.json'),
                    resolution.artifact,
                )
                state.base_map_seed_id = base_seed_id or state.map_seed_id
                if resolution.resolved_map_seed_id:
                    state.map_seed_id = resolution.resolved_map_seed_id
                state.resolved_foundation_ref = dict(
                    resolution.artifact.get('resolved_foundation_ref') or {}
                )
                state.step1_suggestion_ref = dict(foundation.get('semantic_artifact_ref') or {})
                state.scenario_input_authority = 'authoritative'
            else:
                legacy_events, legacy_policies = ScenarioPlanner.convert_legacy_injected_variables(
                    data.get('injected_variables') or []
                )
                semantic_event_inputs = [item.to_dict() for item in legacy_events]
                semantic_policy_inputs = [item.to_dict() for item in legacy_policies]
            semantic_artifact = SemanticInputNormalizer().normalize_scenario(
                foundation=foundation,
                event_inputs=semantic_event_inputs,
                policy_inputs=semantic_policy_inputs,
                previous_artifact_ref=(
                    foundation.get('semantic_artifact_ref')
                    or data.get('semantic_artifact_ref')
                ),
            )
            normalized_payload = {
                **data,
                'event_inputs': [item.model_dump(mode='json') for item in semantic_artifact.events],
                'policy_inputs': [item.model_dump(mode='json') for item in semantic_artifact.policies],
                'semantic_artifact_ref': SemanticArtifactStore.public_ref(semantic_artifact),
                'step1_suggestion_ref': dict(foundation.get('semantic_artifact_ref') or {}),
                'resolved_foundation_ref': dict(
                    state.resolved_foundation_ref
                    or {
                        key: foundation.get(key)
                        for key in (
                            'artifact_id', 'contract_version', 'project_id', 'graph_id',
                            'map_seed_id', 'content_hash',
                        )
                        if foundation.get(key) not in (None, '')
                    }
                ),
            }
            scenario_artifact = ScenarioPlanner().build_from_payload(
                foundation,
                normalized_payload,
                effort_snapshot_ref=effort_snapshot,
            )
            scenario_planning_input = scenario_artifact.to_dict()
            compiled_facility_plan = compile_facility_query_plan(scenario_artifact)
            facility_query_plan = compiled_facility_plan.to_dict()
            spatial_refinement_snapshot = _refine_spatial_evidence(
                compiled_facility_plan,
                foundation=foundation,
            )
            state.semantic_artifact_ref = SemanticArtifactStore.public_ref(semantic_artifact)
            manager._save_simulation_state(state)
            if not uses_new_scenario_contract and hasattr(project, 'semantic_artifact_ref'):
                project.semantic_artifact_ref = dict(state.semantic_artifact_ref)
                ProjectManager.save_project(project)

        logger.info(f"开始处理 /prepare 请求: simulation_id={simulation_id}, force_regenerate={force_regenerate}")
        
        # 获取模拟需求
        simulation_requirement = (
            project.simulation_requirement
            or f"围绕{project.name or '已确认背景'}进行场景推演。"
        )
        
        # 获取文档文本
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)
        scenario_mode = data.get('scenario_mode', state.scenario_mode or 'baseline_mode')
        agent_planning_request: Dict[str, Any] = {}

        if uses_scenario_planner:
            if scenario_artifact is None:
                raise ValueError("场景规划工件尚未生成")
            agent_planning_request = plan_scenario_agents(scenario_artifact)
            agent_planning_request["facility_query_plan_ref"] = {
                key: facility_query_plan.get(key)
                for key in ("contract_version", "plan_id", "content_hash")
            }
            agent_planning_request["spatial_refinement_snapshot_ref"] = {
                key: spatial_refinement_snapshot.get(key)
                for key in ("contract_version", "snapshot_id", "content_hash")
            }
            agent_planning_request["spatial_evidence_summary"] = {
                "request_count": len(facility_query_plan.get("requests") or []),
                "required_r3_count": len(facility_query_plan.get("required_r3_request_ids") or []),
                "required_r4_count": len(facility_query_plan.get("required_r4_request_ids") or []),
                "covered_r3_count": sum(
                    1
                    for item in spatial_refinement_snapshot.get("request_coverage") or []
                    if item.get("resolution_level") == "R3" and item.get("status") == "covered"
                ),
                "blocking_gap_count": sum(
                    1
                    for item in spatial_refinement_snapshot.get("evidence_gaps") or []
                    if item.get("blocking") is True
                ),
            }
            injected_variables = list(agent_planning_request.get('injected_variables') or [])
            adapter_requirement = str(agent_planning_request.get('simulation_requirement') or '').strip()
            if adapter_requirement:
                simulation_requirement = (
                    f"{simulation_requirement}\n\n"
                    f"Step 2 场景规划补充：{adapter_requirement}"
                )
            simulation_architecture = LLM_MECHANISM_ARCHITECTURE
            search_mode = 'deep_search'
            diffusion_template = 'generic'
            hazard_template_id = 'generic'
            hazard_template_mode = 'auto'
            time_plan, temporal_profile = _scenario_temporal_payload(scenario_planning_input)
            time_plan_mode = 'scenario_planner'
            reference_time = str(data.get('reference_time') or state.reference_time or '')
            diffusion_provider = 'auto'
            target_agent_count = None
            search_profile_overrides = None
        else:
            simulation_architecture = normalize_simulation_architecture(
                data.get('simulation_architecture', state.simulation_architecture or LEGACY_SIMULATION_ARCHITECTURE)
            )
            diffusion_template = normalize_transport_family(data.get('diffusion_template', state.diffusion_template or 'marine'))
            hazard_template_id = str(data.get('hazard_template_id') or state.hazard_template_id or '')
            hazard_template_mode = str(data.get('hazard_template_mode') or state.hazard_template_mode or 'auto')
            search_mode = normalize_search_mode(data.get('search_mode', state.search_mode or 'fast'))
            temporal_profile = dict(data.get('temporal_profile') or {})
            if data.get('temporal_preset') and not temporal_profile.get('preset'):
                temporal_profile['preset'] = data.get('temporal_preset')
            if data.get('max_rounds') and not temporal_profile.get('total_rounds'):
                temporal_profile['total_rounds'] = data.get('max_rounds')
            if data.get('minutes_per_round') and not temporal_profile.get('minutes_per_round'):
                temporal_profile['minutes_per_round'] = data.get('minutes_per_round')
            temporal_profile.setdefault('preset', state.temporal_preset or 'standard')
            temporal_profile.setdefault('total_rounds', state.configured_total_rounds or 12)
            temporal_profile.setdefault('minutes_per_round', state.configured_minutes_per_round or 60)
            reference_time = str(data.get('reference_time') or state.reference_time or '')
            time_plan_mode = str(data.get('time_plan_mode') or state.time_plan_mode or 'auto')
            time_plan = normalize_time_plan(
                data.get('time_plan'),
                total_rounds=temporal_profile.get('total_rounds'),
                minutes_per_round=temporal_profile.get('minutes_per_round'),
                preset=temporal_profile.get('preset'),
                reference_time=reference_time,
                source=time_plan_mode,
            )
            diffusion_provider = str(data.get('diffusion_provider') or state.diffusion_provider or 'auto')
            injected_variables = data.get('injected_variables') or []
            target_agent_count = data.get('target_agent_count')
            search_profile_overrides = data.get('search_profile_overrides') or None

        # Task reservation is the only boundary allowed to transition a simulation
        # into PREPARING. Persist the input hash before any prepare artifact is
        # written so retries cannot start a second writer for the same directory.
        task_manager = TaskManager()
        with _prepare_reservation_lock(manager, simulation_id):
            fresh_manager = SimulationManager()
            fresh_state = fresh_manager.get_simulation(simulation_id)
            if not fresh_state:
                return jsonify({
                    "success": False,
                    "error": "未找到对应的模拟任务。",
                }), 404

            active_task = _find_active_prepare_task(task_manager, fresh_state)
            incoming_hash = str(scenario_planning_input.get("content_hash") or "")
            if active_task:
                active_hash = _active_prepare_hash(active_task, fresh_state)
                if (incoming_hash or active_hash) and incoming_hash != active_hash:
                    return jsonify({
                        "success": False,
                        "error": "当前场景正在按另一组输入生成，请等待完成后再明确重新生成。",
                        "code": "scenario_input_changed",
                        "stage": "场景输入校验",
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": active_task.task_id,
                            "status": "preparing",
                        },
                    }), 409
                logger.info(
                    "复用进行中的准备任务: simulation_id=%s, task_id=%s",
                    simulation_id,
                    active_task.task_id,
                )
                return jsonify({
                    "success": True,
                    "data": _active_prepare_response(
                        task=active_task,
                        state=fresh_state,
                        scenario_planning_input=scenario_planning_input,
                        uses_scenario_planner=uses_scenario_planner,
                    ),
                })

            if not force_regenerate:
                logger.debug(f"检查模拟 {simulation_id} 是否已准备完成...")
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                logger.debug(f"检查结果: is_prepared={is_prepared}, prepare_info={prepare_info}")
                if is_prepared:
                    if uses_scenario_planner and not _planning_input_matches_existing(
                        fresh_manager,
                        simulation_id,
                        scenario_planning_input,
                    ):
                        return jsonify({
                            "success": False,
                            "error": "当前输入与已生成场景不一致；如需替换，请明确执行重新生成。",
                            "code": "scenario_input_changed",
                            "stage": "场景输入校验",
                        }), 409
                    logger.info(f"模拟 {simulation_id} 已准备完成，跳过重复生成")
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "status": "ready",
                            "message": "已有完成的准备工作，无需重复生成",
                            "already_prepared": True,
                            "prepare_info": prepare_info,
                            "scenario_mode": fresh_state.scenario_mode,
                            "diffusion_template": fresh_state.diffusion_template,
                            "search_mode": fresh_state.search_mode,
                            "temporal_preset": fresh_state.temporal_preset,
                            "configured_total_rounds": fresh_state.configured_total_rounds,
                            "configured_minutes_per_round": fresh_state.configured_minutes_per_round,
                            "reference_time": fresh_state.reference_time,
                            "diffusion_provider": fresh_state.diffusion_provider,
                            "effort_snapshot": fresh_state.effort_snapshot,
                            **({
                                "scenario_planning_input": scenario_planning_input,
                                "agent_plan_source": fresh_state.agent_plan_source or "legacy_adapter",
                            } if uses_scenario_planner else {}),
                        },
                    })

            manager = fresh_manager
            state = fresh_state
            task_id = task_manager.create_task(
                name=f"准备模拟: {simulation_id}",
                task_type="simulation_prepare",
                metadata={
                    "simulation_id": simulation_id,
                    "project_id": state.project_id,
                    "planning_input_id": str(scenario_planning_input.get("planning_input_id") or ""),
                    "planning_content_hash": incoming_hash,
                },
            )

            state.scenario_mode = scenario_mode
            state.simulation_architecture = simulation_architecture
            state.diffusion_template = diffusion_template
            state.hazard_template_id = hazard_template_id or state.hazard_template_id
            state.hazard_template_mode = hazard_template_mode
            state.search_mode = search_mode
            state.temporal_preset = str(time_plan.get('preset') or temporal_profile.get('preset') or 'standard')
            state.configured_total_rounds = max(4, int(time_plan.get('total_rounds') or temporal_profile.get('total_rounds') or 12))
            state.configured_minutes_per_round = max(10, int(time_plan.get('minutes_per_round') or temporal_profile.get('minutes_per_round') or 60))
            state.time_plan_mode = time_plan_mode
            state.time_plan = time_plan
            state.reference_time = reference_time
            state.diffusion_provider = diffusion_provider
            state.planning_input_id = str(scenario_planning_input.get("planning_input_id") or "")
            state.planning_content_hash = incoming_hash
            state.agent_plan_source = str(agent_planning_request.get("agent_plan_source") or "")
            state.prepare_task_id = task_id
            state.status = SimulationStatus.PREPARING
            state.error = None
            manager._save_simulation_state(state)
            if uses_new_scenario_contract:
                write_json_file(
                    os.path.join(
                        manager._get_simulation_dir(simulation_id),
                        'scenario_configuration_input.json',
                    ),
                    {
                        "contract_version": "scenario_configuration_input.v1",
                        "input_kind": "scenario_configuration",
                        "authority": "authoritative",
                        "submitted_input_hash": submitted_snapshot_hash,
                        "event_inputs": list(
                            scenario_planning_input.get('normalized_user_events') or []
                        ),
                        "policy_inputs": list(
                            scenario_planning_input.get('normalized_user_policies') or []
                        ),
                        "resolved_foundation_ref": dict(
                            scenario_planning_input.get('resolved_foundation_ref') or {}
                        ),
                        "step1_suggestion_ref": dict(
                            scenario_planning_input.get('step1_suggestion_ref') or {}
                        ),
                        "semantic_artifact_ref": dict(
                            scenario_planning_input.get('semantic_artifact_ref') or {}
                        ),
                    },
                )

        if uses_scenario_planner:
            write_json_file(
                os.path.join(manager._get_simulation_dir(simulation_id), 'agent_planning_request.json'),
                agent_planning_request,
            )
            write_json_file(
                os.path.join(manager._get_simulation_dir(simulation_id), 'facility_query_plan.json'),
                facility_query_plan,
            )
            write_json_file(
                os.path.join(
                    manager._get_simulation_dir(simulation_id),
                    'spatial_refinement_snapshot.json',
                ),
                spatial_refinement_snapshot,
            )

        # ========== 同步获取实体数量（在后台任务启动前） ==========
        # 这样前端在调用prepare后立即就能获取到预期Agent总数
        try:
            logger.info(f"同步获取实体数量: graph_id={state.graph_id}")
            reader = ZepEntityReader()
            # 快速读取实体（不需要边信息，只统计数量）
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # 不获取边信息，加快速度
            )
            # 保存实体数量到状态（供前端立即获取）
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"预期实体数量: {filtered_preview.filtered_count}, 类型: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"同步获取实体数量失败（将在后台任务中重试）: {e}")
            # 失败不影响后续流程，后台任务会重新获取

        # 保存预览统计；任务已在原子预约阶段登记，随后才允许启动写入。
        manager._save_simulation_state(state)
        
        # 定义后台任务
        def run_prepare():
            try:
                def ensure_running():
                    task_manager.ensure_not_cancelled(task_id)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=62 if uses_scenario_planner else 0,
                    message=(
                        "复合事件、机制图、时间空间计划与角色能力需求已生成，开始生成代理体与关系。"
                        if uses_scenario_planner
                        else "开始准备模拟环境..."
                    )
                )
                ensure_running()
                
                # 准备模拟（带进度回调）
                # 存储阶段进度详情
                stage_details = {}
                
                def progress_callback(stage, progress, message, **kwargs):
                    ensure_running()

                    # 计算总进度
                    stage_weights = {
                        "reading": ((62, 66) if uses_scenario_planner else (0, 20)),
                        "generating_profiles": ((66, 85) if uses_scenario_planner else (20, 70)),
                        "generating_config": ((85, 99) if uses_scenario_planner else (70, 90)),
                        "copying_scripts": ((99, 100) if uses_scenario_planner else (90, 100)),
                    }
                    
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    
                    # 构建详细进度信息
                    stage_names = PREPARE_STAGE_LABELS
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)
                    
                    # 更新阶段详情
                    stage_details[stage] = {
                        "stage_name": _prepare_stage_label(stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }
                    
                    # 构建详细进度信息
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": _prepare_stage_label(stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }
                    
                    # 构建简洁消息
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {_prepare_stage_label(stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {_prepare_stage_label(stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                ensure_running()
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count,
                    scenario_mode=scenario_mode,
                    diffusion_template=diffusion_template,
                    hazard_template_id=hazard_template_id,
                    hazard_template_mode=hazard_template_mode,
                    simulation_architecture=simulation_architecture,
                    search_mode=search_mode,
                    temporal_profile=temporal_profile,
                    time_plan_mode=time_plan_mode,
                    time_plan=time_plan,
                    reference_time=reference_time,
                    diffusion_provider=diffusion_provider,
                    injected_variables=injected_variables,
                    target_agent_count=target_agent_count,
                    search_profile_overrides=search_profile_overrides,
                    scenario_planning_input=scenario_planning_input or None,
                    agent_plan_source=str(agent_planning_request.get('agent_plan_source') or ''),
                )
                ensure_running()
                
                # 任务完成
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )
                
            except Exception as e:
                if isinstance(e, TaskCancelledError) or task_manager.is_cancelled(task_id):
                    logger.info(f"准备模拟已取消: task_id={task_id}, simulation_id={simulation_id}")
                    state = manager.get_simulation(simulation_id)
                    if state:
                        state.status = SimulationStatus.STOPPED
                        state.error = str(e) or "用户强制停止"
                        manager._save_simulation_state(state)
                    return

                logger.error(f"准备模拟失败: {str(e)}")
                task_manager.fail_task(task_id, str(e))
                
                # 更新模拟状态为失败
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)
        
        TaskExecutor(task_manager).start(task_id=task_id, target=run_prepare)
        
        response_data = {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "准备任务已启动，可在当前页面查看生成进度。",
                "progress": 62 if uses_scenario_planner else 0,
                "generation_stage": "generating_profiles" if uses_scenario_planner else "reading",
                "generation_stage_label": _prepare_stage_label(
                    "generating_profiles" if uses_scenario_planner else "reading"
                ),
                "already_prepared": False,
                "expected_entities_count": state.entities_count,
                **({
                    "event_inputs": list(scenario_planning_input.get('normalized_user_events') or []),
                    "policy_inputs": list(scenario_planning_input.get('normalized_user_policies') or []),
                    "resolved_foundation_ref": dict(
                        scenario_planning_input.get('resolved_foundation_ref') or {}
                    ),
                    "step1_suggestion_ref": dict(
                        scenario_planning_input.get('step1_suggestion_ref') or {}
                    ),
                    "scenario_input_authority": "authoritative",
                } if uses_new_scenario_contract else {}),
                "entity_types": state.entity_types,
                "scenario_mode": scenario_mode,
                "diffusion_template": diffusion_template,
                "hazard_template_id": hazard_template_id,
                "hazard_template_mode": hazard_template_mode,
                "search_mode": search_mode,
                "simulation_architecture": simulation_architecture,
                "temporal_profile": temporal_profile,
                "time_plan_mode": time_plan_mode,
                "time_plan": time_plan,
                "reference_time": reference_time,
                "diffusion_provider": diffusion_provider,
                "injected_variables_count": len(injected_variables),
                "effort_snapshot": effort_snapshot,
            }
        if uses_scenario_planner:
            response_data.update({
                "scenario_planning_input": scenario_planning_input,
                "agent_plan_source": agent_planning_request.get('agent_plan_source'),
                "projection_warnings": agent_planning_request.get('projection_warnings') or [],
                "facility_query_plan_ref": agent_planning_request.get('facility_query_plan_ref') or {},
                "spatial_refinement_snapshot_ref": agent_planning_request.get('spatial_refinement_snapshot_ref') or {},
                "spatial_evidence_summary": agent_planning_request.get('spatial_evidence_summary') or {},
            })
        if not uses_new_scenario_contract:
            response_data["target_agent_count"] = data.get('target_agent_count')

        return jsonify({
            "success": True,
            "data": response_data,
        })
        
    except EffortContractError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "code": "effort_snapshot_conflict",
        }), 409
    except AgentPlanningPortError as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "code": "agent_planning_failed",
            "stage": "提取角色能力需求并生成代理体规划",
        }), 502
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"启动准备任务失败: {str(e)}")
        if task_id and task_manager:
            try:
                task_manager.fail_task(task_id, "准备任务启动失败", message="准备任务启动失败，请重试。")
                cleanup_manager = SimulationManager()
                failed_state = cleanup_manager.get_simulation(simulation_id)
                if failed_state and failed_state.prepare_task_id == task_id:
                    failed_state.status = SimulationStatus.FAILED
                    failed_state.error = "准备任务启动失败"
                    cleanup_manager._save_simulation_state(failed_state)
            except Exception as cleanup_error:
                logger.warning(f"清理未启动的准备任务失败: {cleanup_error}")
        return jsonify({
            "success": False,
            "error": "启动场景准备任务失败，请稍后重试。",
            "code": "prepare_start_failed",
            "stage": "启动场景生成",
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    查询准备任务进度
    
    支持两种查询方式：
    1. 通过task_id查询正在进行的任务进度
    2. 通过simulation_id检查是否已有完成的准备工作
    
    请求（JSON）：
        {
            "task_id": "task_xxxx",          // 可选，prepare返回的task_id
            "simulation_id": "sim_xxxx"      // 可选，模拟ID（用于检查已完成的准备）
        }
    
    返回：
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // 是否已有完成的准备
                "prepare_info": {...}            // 已准备完成时的详细信息
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')

        # When a caller supplies the task created by a forced regeneration, that
        # task is authoritative.  Looking at existing simulation artifacts first
        # can otherwise return an older READY result while the new task is still
        # generating profiles and risk definitions.
        if task_id:
            current_task = TaskManager().get_task(task_id)
            if current_task:
                task_dict = current_task.to_dict()
                task_dict["already_prepared"] = False
                return _public_runtime_success(task_dict)
        
        # 如果提供了simulation_id，先检查是否已准备完成
        if simulation_id:
            prepared_state = SimulationManager().get_simulation(simulation_id)
            if prepared_state and prepared_state.is_replay_only:
                return _public_runtime_success({
                    "simulation_id": simulation_id,
                    "status": "ready",
                    "progress": 100,
                    "message": "冻结演示案例已准备完成",
                    "already_prepared": True,
                    "scenario_mode": prepared_state.scenario_mode,
                    "diffusion_template": prepared_state.diffusion_template,
                    "search_mode": prepared_state.search_mode,
                    "is_replay_only": True,
                })
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return _public_runtime_success({
                    "simulation_id": simulation_id,
                    "status": "ready",
                    "progress": 100,
                    "message": "已有完成的准备工作",
                    "already_prepared": True,
                    "prepare_info": prepare_info,
                    "scenario_mode": prepared_state.scenario_mode if prepared_state else None,
                    "diffusion_template": prepared_state.diffusion_template if prepared_state else None,
                    "search_mode": prepared_state.search_mode if prepared_state else None,
                })
        
        # 如果没有task_id，返回错误
        if not task_id:
            if simulation_id:
                # 有simulation_id但未准备完成
                return _public_runtime_success({
                    "simulation_id": simulation_id,
                    "status": "not_started",
                    "progress": 0,
                    "message": "尚未开始准备，请先启动场景准备。",
                    "already_prepared": False,
                })
            return jsonify({
                "success": False,
                "error": "请提供准备任务编号或模拟任务编号"
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # 任务不存在，但如果有simulation_id，检查是否已准备完成
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    prepared_state = SimulationManager().get_simulation(simulation_id)
                    return _public_runtime_success({
                        "simulation_id": simulation_id,
                        "task_id": task_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "任务已完成（准备工作已存在）",
                        "already_prepared": True,
                        "prepare_info": prepare_info,
                        "scenario_mode": prepared_state.scenario_mode if prepared_state else None,
                        "diffusion_template": prepared_state.diffusion_template if prepared_state else None,
                        "search_mode": prepared_state.search_mode if prepared_state else None,
                    })
            
            return jsonify({"success": False, "error": "准备任务不存在"}), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return _public_runtime_success(task_dict)
        
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "查询准备状态失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """获取模拟状态"""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": "未找到对应的模拟任务。"
            }), 404
        
        result = state.to_dict()
        result["report_id"] = _get_report_id_for_simulation(simulation_id)

        # 如果模拟已准备好，附加运行说明
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)

        sim_dir, risk_bundle = _load_risk_bundle(simulation_id)
        result["risk_definitions"] = risk_bundle.get("risk_definitions", [])
        result["risk_contract_version"] = int(risk_bundle.get("risk_contract_version") or 1)
        result["risk_generation_audit"] = risk_bundle.get("risk_generation_audit", {})
        result["latest_risk_runtime_state"] = risk_bundle.get("latest_risk_runtime_state", {})
        result["risk_events"] = risk_bundle.get("risk_events", [])
        result["risk_objects"] = risk_bundle.get("risk_objects", [])
        summary = risk_bundle.get("risk_objects_summary") or {}
        result["risk_objects_summary"] = summary
        result["primary_risk_object"] = summary.get("primary_risk_object")
        result["primary_active_risk_id"] = (
            risk_bundle.get("latest_risk_runtime_state", {}).get("primary_active_risk_id")
            or summary.get("primary_active_risk_id")
            or ""
        )

        if state.source_mode == "map_seed" and state.map_seed_id:
            graph_snapshot = MapSeedManager.get_graph_snapshot(state.map_seed_id)
            if graph_snapshot:
                result["map_graph"] = graph_snapshot
                result["map_graph_data"] = graph_snapshot.get("graph_data") or graph_snapshot
            layers = MapSeedManager.get_layers(state.map_seed_id)
            if layers:
                result["map_layers"] = layers
            report_text = MapSeedManager.get_report_text(state.map_seed_id)
            if report_text:
                result["map_report_text"] = report_text
        
        return _public_runtime_success(result)
        
    except Exception as e:
        logger.error(f"获取模拟状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取模拟状态失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/graph/realtime', methods=['GET'])
def get_simulation_graph_realtime(simulation_id: str):
    """
    实时获取 EnvFish 推演图谱（Step2/Step3 专用）

    优先返回 simulation artifacts 投影出的图谱；当 artifacts 尚未就绪时，
    回退到 map_seed 图谱或项目原始 graph_id 图谱。
    """
    try:
        include_map = request.args.get("include_map", "false").lower() in {"1", "true", "yes", "on"}
        key_edges_only = request.args.get("key_edges_only", "true").lower() not in {"0", "false", "no", "off"}

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify({
                "success": False,
                "error": "模拟不存在",
            }), 404

        sim_dir = manager.resolve_artifact_dir(state, create_if_missing=False)
        if not sim_dir:
            sim_dir = manager._get_simulation_dir(simulation_id)
        realtime_graph = SimulationRealtimeGraphBuilder(sim_dir).build()
        source = "envfish_realtime"
        has_envfish_projection = bool(realtime_graph.get("nodes") or realtime_graph.get("edges"))
        fallback_used = False

        if not has_envfish_projection:
            fallback_graph = None
            if state.source_mode == "map_seed" and state.map_seed_id:
                snapshot = MapSeedManager.get_graph_snapshot(state.map_seed_id)
                if snapshot:
                    fallback_graph = snapshot.get("graph_data") or snapshot
                    source = "map_seed_snapshot"

            if fallback_graph is None and state.graph_id and Config.ZEP_API_KEY:
                try:
                    builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                    fallback_graph = builder.get_graph_data(state.graph_id)
                    source = "project_graph"
                except Exception as exc:
                    logger.warning(f"实时图谱回退到 project graph 失败: simulation_id={simulation_id}, error={exc}")

            if fallback_graph:
                realtime_graph = {
                    "nodes": list(fallback_graph.get("nodes") or []),
                    "edges": list(fallback_graph.get("edges") or []),
                    "meta": {
                        "node_count": len(list(fallback_graph.get("nodes") or [])),
                        "edge_count": len(list(fallback_graph.get("edges") or [])),
                    },
                }
                fallback_used = True

        map_projection = None
        if include_map:
            projection_builder = SimulationMapProjectionBuilder(
                sim_dir=sim_dir,
                simulation_id=simulation_id,
                map_seed_id=state.map_seed_id if state.map_seed_id else None,
                source_mode=state.source_mode,
            )
            map_projection = projection_builder.build(
                realtime_graph,
                key_edges_only=key_edges_only,
            )

        return _public_runtime_success({
            "simulation_id": simulation_id,
            "source": source,
            "fallback_used": fallback_used,
            "has_envfish_projection": has_envfish_projection,
            "graph_data": realtime_graph,
            "map_projection": map_projection,
        })

    except Exception as e:
        logger.error(f"获取实时图谱失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取实时图谱失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/animation', methods=['GET'])
def get_simulation_animation(simulation_id: str):
    """Return live/frozen animation or an incremental playback window.

    ``after_cursor`` (legacy alias ``since_cursor``) advances timeline events.
    ``after_round`` (legacy-style alias ``since_round``) advances committed
    frames, including completed rounds that contain no timeline event. Clients
    may send both watermarks in one poll. ``timeline_id`` pins a delta request
    to one playback epoch; a changed identity returns an empty window with
    ``reset_required=true`` instead of mixing two histories.
    """
    try:
        raw_cursor = request.args.get("after_cursor")
        if raw_cursor is None:
            raw_cursor = request.args.get("since_cursor")
        raw_round = request.args.get("after_round")
        if raw_round is None:
            raw_round = request.args.get("since_round")
        requested_timeline_id = (
            str(request.args.get("timeline_id") or "").strip() or None
        )
        after_cursor = None
        after_round = None
        if raw_cursor is not None:
            try:
                after_cursor = int(raw_cursor)
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "动画游标必须是非负整数。",
                }), 400
            if after_cursor < 0:
                return jsonify({
                    "success": False,
                    "error": "动画游标必须是非负整数。",
                }), 400
        if raw_round is not None:
            try:
                after_round = int(raw_round)
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "动画轮次必须是非负整数。",
                }), 400
            if after_round < 0:
                return jsonify({
                    "success": False,
                    "error": "动画轮次必须是非负整数。",
                }), 400
        animation_service = SimulationAnimationService(simulation_id)
        if (
            after_cursor is None
            and after_round is None
            and requested_timeline_id is None
        ):
            payload = animation_service.get_animation()
        else:
            request_kwargs = {
                "after_cursor": after_cursor,
                "after_round": after_round,
            }
            if requested_timeline_id is not None:
                request_kwargs["timeline_id"] = requested_timeline_id
            payload = animation_service.get_animation(**request_kwargs)
        return _public_runtime_success(payload)
    except ValueError as exc:
        return jsonify({
            "success": False,
            "error": public_error_message(exc, "推演动画不存在。"),
        }), 404
    except Exception as exc:
        logger.error(f"获取推演动画失败: {exc}")
        return jsonify({
            "success": False,
            "error": public_error_message(exc, "获取推演动画失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/risk/definitions', methods=['GET'])
def get_risk_definitions(simulation_id: str):
    try:
        _, risk_bundle = _load_risk_bundle(simulation_id)
        return _public_runtime_success({
            "simulation_id": simulation_id,
            "risk_definitions": risk_bundle.get("risk_definitions", []),
            "count": len(risk_bundle.get("risk_definitions", [])),
            "risk_contract_version": int(risk_bundle.get("risk_contract_version") or 1),
            "risk_generation_audit": risk_bundle.get("risk_generation_audit", {}),
            "primary_risk_id": (
                risk_bundle.get("risk_objects_summary", {}).get("primary_risk_object_id")
                or risk_bundle.get("latest_risk_runtime_state", {}).get("primary_active_risk_id")
                or ""
            ),
        })
    except Exception as e:
        logger.error(f"获取风险定义失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取风险定义失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/risk/runtime', methods=['GET'])
def get_risk_runtime(simulation_id: str):
    try:
        _, risk_bundle = _load_risk_bundle(simulation_id)
        runtime_history = list(risk_bundle.get("risk_runtime_history") or [])
        latest_runtime = dict(risk_bundle.get("latest_risk_runtime_state") or {})
        requested_round = request.args.get("round", type=int)
        if requested_round is not None and runtime_history:
            matched = next((item for item in reversed(runtime_history) if int(item.get("round") or -1) == requested_round), None)
            if matched:
                latest_runtime = matched
        risk_states = list(latest_runtime.get("risk_states") or [])
        pinned_ids = set(latest_runtime.get("pinned_risk_ids") or [])
        active_only = request.args.get("active_only", "false").lower() == "true"
        pinned_only = request.args.get("pinned_only", "false").lower() == "true"
        if active_only:
            risk_states = [
                item for item in risk_states
                if str(item.get("status") or "watch") not in {"dormant", "resolved"}
            ]
        if pinned_only:
            risk_states = [item for item in risk_states if str(item.get("risk_id") or "") in pinned_ids]
        latest_runtime["risk_states"] = risk_states
        return _public_runtime_success({
            "simulation_id": simulation_id,
            "latest_risk_runtime_state": latest_runtime,
            "count": len(risk_states),
        })
    except Exception as e:
        logger.error(f"获取风险运行态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取风险运行态失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/risk/events', methods=['GET'])
def get_risk_events(simulation_id: str):
    try:
        _, risk_bundle = _load_risk_bundle(simulation_id)
        risk_id = str(request.args.get("risk_id") or "").strip()
        limit = request.args.get("limit", type=int)
        events = list(risk_bundle.get("risk_events") or [])
        if risk_id:
            events = [item for item in events if str(item.get("risk_id") or "") == risk_id]
        if limit is not None and limit > 0 and len(events) > limit:
            events = events[-limit:]
        return _public_runtime_success({
            "simulation_id": simulation_id,
            "risk_events": events,
            "count": len(events),
        })
    except Exception as e:
        logger.error(f"获取风险事件失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取风险事件失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/risk/pin', methods=['POST'])
def update_risk_pin(simulation_id: str):
    try:
        data = request.get_json() or {}
        sim_dir, risk_bundle = _load_risk_bundle(simulation_id)
        if int(risk_bundle.get("risk_contract_version") or 1) >= 2:
            return jsonify({
                "success": False,
                "error": "新版风险对象由系统自动维护，当前为只读。",
                "code": "risk_definitions_read_only",
            }), 409
        latest_runtime = dict(risk_bundle.get("latest_risk_runtime_state") or {})
        pinned_risk_ids = []
        for item in data.get("pinned_risk_ids") or []:
            risk_id = str(item or "").strip()
            if risk_id and risk_id not in pinned_risk_ids:
                pinned_risk_ids.append(risk_id)
        latest_runtime["pinned_risk_ids"] = pinned_risk_ids
        if not latest_runtime.get("primary_active_risk_id") and pinned_risk_ids:
            latest_runtime["primary_active_risk_id"] = pinned_risk_ids[0]
        runtime_history = list(risk_bundle.get("risk_runtime_history") or [])
        if runtime_history and int(runtime_history[-1].get("round") or -1) == int(latest_runtime.get("round") or -2):
            runtime_history[-1] = latest_runtime
        else:
            runtime_history.append(latest_runtime)
        updated = write_risk_artifacts(
            sim_dir=sim_dir,
            risk_definitions=risk_bundle.get("risk_definitions", []),
            latest_runtime_bundle=latest_runtime,
            primary_risk_id=str(
                (risk_bundle.get("risk_objects_summary") or {}).get("primary_risk_object_id")
                or latest_runtime.get("primary_active_risk_id")
                or ""
            ),
            generation_notes=list((risk_bundle.get("risk_objects_summary") or {}).get("generation_notes") or []),
            risk_events=risk_bundle.get("risk_events", []),
            rewrite_runtime_history=runtime_history,
        )
        _sync_risk_fields_to_config(sim_dir, updated)
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "pinned_risk_ids": pinned_risk_ids,
                "primary_active_risk_id": latest_runtime.get("primary_active_risk_id"),
            }
        })
    except Exception as e:
        logger.error(f"更新风险 pin 失败: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route('/<simulation_id>/risk/reframe', methods=['POST'])
def reframe_risks(simulation_id: str):
    try:
        data = request.get_json() or {}
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id) or {}
        sim_dir, risk_bundle = _load_risk_bundle(simulation_id)
        if int(risk_bundle.get("risk_contract_version") or 1) >= 2:
            return jsonify({
                "success": False,
                "error": "新版风险对象由系统自动维护，当前为只读。",
                "code": "risk_definitions_read_only",
            }), 409
        regions = []
        profiles = []
        region_graph_path = os.path.join(sim_dir, "region_graph_snapshot.json")
        profiles_path = os.path.join(sim_dir, "profiles_full.json")
        latest_snapshot_path = os.path.join(sim_dir, "latest_round_snapshot.json")
        injected_variables_path = os.path.join(sim_dir, "injected_variables.json")
        if os.path.exists(region_graph_path):
            regions = read_json_file(region_graph_path, default=[])
        else:
            regions = config.get("region_graph") or []
        if os.path.exists(profiles_path):
            profiles = read_json_file(profiles_path, default=[])
        else:
            profiles = config.get("actor_profiles") or []
        if os.path.exists(injected_variables_path):
            injected_variables = read_json_file(injected_variables_path, default=[])
        else:
            injected_variables = config.get("injected_variables") or []
        latest_snapshot = {}
        if os.path.exists(latest_snapshot_path):
            latest_snapshot = read_json_file(latest_snapshot_path, default={})

        builder = RiskDefinitionBuilder()
        tracker = RiskRuntimeTracker()
        event_engine = RiskEventEngine()
        reframe_result = builder.reframe_runtime(
            existing_definitions=risk_bundle.get("risk_definitions", []),
            regions=regions,
            profiles=profiles,
            injected_variables=injected_variables,
            current_round=int(
                data.get("round")
                or (risk_bundle.get("latest_risk_runtime_state") or {}).get("round")
                or 0
            ),
            scenario_mode=str(config.get("scenario_mode") or "baseline_mode"),
            diffusion_template=str(config.get("diffusion_template") or "marine"),
        )
        latest_runtime = tracker.refresh(
            risk_definitions=reframe_result.get("risk_definitions", []),
            snapshot=latest_snapshot or None,
            previous_bundle=risk_bundle.get("latest_risk_runtime_state", {}),
            risk_events=risk_bundle.get("risk_events", []),
            primary_hint=str(
                (risk_bundle.get("latest_risk_runtime_state") or {}).get("primary_active_risk_id")
                or reframe_result.get("primary_risk_id")
                or ""
            ),
            pinned_risk_ids=list((risk_bundle.get("latest_risk_runtime_state") or {}).get("pinned_risk_ids") or []),
            refresh_reason="manual_reframe",
        ) if latest_snapshot else tracker.build_initial_bundle(
            risk_definitions=reframe_result.get("risk_definitions", []),
            primary_risk_id=str(
                reframe_result.get("primary_risk_id")
                or (risk_bundle.get("latest_risk_runtime_state") or {}).get("primary_active_risk_id")
                or ""
            ),
            source_risk_objects=risk_bundle.get("risk_objects", []),
        )

        risk_events = list(risk_bundle.get("risk_events") or [])
        for risk_id in reframe_result.get("created_risk_ids") or []:
            risk_events.append(
                event_engine.build_reframed_event(
                    risk_id=risk_id,
                    round_num=int(latest_runtime.get("round") or 0),
                    source_ref="manual:reframe",
                    summary="手动重新框定后创建新的风险链路。",
                )
            )
        for risk_id in reframe_result.get("updated_risk_ids") or []:
            risk_events.append(
                event_engine.build_reframed_event(
                    risk_id=risk_id,
                    round_num=int(latest_runtime.get("round") or 0),
                    source_ref="manual:reframe",
                    summary="手动重新框定后刷新已有风险链路。",
                )
            )
        runtime_history = list(risk_bundle.get("risk_runtime_history") or [])
        if runtime_history and int(runtime_history[-1].get("round") or -1) == int(latest_runtime.get("round") or -2):
            runtime_history[-1] = latest_runtime
        else:
            runtime_history.append(latest_runtime)
        updated = write_risk_artifacts(
            sim_dir=sim_dir,
            risk_definitions=reframe_result.get("risk_definitions", []),
            latest_runtime_bundle=latest_runtime,
            primary_risk_id=str(
                (risk_bundle.get("risk_objects_summary") or {}).get("primary_risk_object_id")
                or reframe_result.get("primary_risk_id")
                or latest_runtime.get("primary_active_risk_id")
                or ""
            ),
            generation_notes=list((risk_bundle.get("risk_objects_summary") or {}).get("generation_notes") or []),
            risk_events=risk_events,
            rewrite_runtime_history=runtime_history,
        )
        _sync_risk_fields_to_config(sim_dir, updated)
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "created_risk_ids": reframe_result.get("created_risk_ids", []),
                "updated_risk_ids": reframe_result.get("updated_risk_ids", []),
                "primary_active_risk_id": latest_runtime.get("primary_active_risk_id"),
                "pinned_risk_ids": latest_runtime.get("pinned_risk_ids", []),
            }
        })
    except Exception as e:
        logger.error(f"重新框定风险失败: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """
    列出所有模拟
    
    Query参数：
        project_id: 按项目ID过滤（可选）
    """
    try:
        project_id = request.args.get('project_id')
        
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)
        
        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })
        
    except Exception as e:
        logger.error(f"列出模拟失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """
    获取 simulation 对应的最新 report_id
    
    遍历 reports 目录，找出 simulation_id 匹配的 report，
    如果有多个则返回最新的（按 created_at 排序）
    
    Args:
        simulation_id: 模拟ID
        
    Returns:
        report_id 或 None
    """
    # reports 目录路径：backend/uploads/reports
    # __file__ 是 app/api/simulation.py，需要向上两级到 backend/
    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None
    
    matching_reports = []
    
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue
            
            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue
            
            try:
                meta = read_json_file(meta_file, default={})
                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue
        
        if not matching_reports:
            return None
        
        # 按创建时间倒序排序，返回最新的
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")
        
    except Exception as e:
        logger.warning(f"查找 simulation {simulation_id} 的 report 失败: {e}")
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """
    获取历史模拟列表（带项目详情）
    
    用于首页历史项目展示，返回包含项目名称、描述等丰富信息的模拟列表
    
    Query参数：
        limit: 返回数量限制（默认20）
    
    返回：
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "武大舆情分析",
                    "simulation_requirement": "如果武汉大学发布...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]
        
        # 增强模拟数据，只从 Simulation 文件读取
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()
            
            # 获取模拟配置信息（从 simulation_config.json 读取 simulation_requirement）
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # 推荐轮数（后备值）
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 / 
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0
            
            # 获取运行状态（从 run_state.json 读取用户设置的实际轮数）
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # 使用用户设置的 total_rounds，若无则使用推荐轮数
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds
            
            # 获取关联项目的文件列表（最多3个）
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", "未知文件")} 
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []
            
            # 获取关联的 report_id（查找该 simulation 最新的 report）
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)
            
            # 添加版本号
            sim_dict["version"] = "v1.0.2"
            
            # 格式化日期
            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except:
                sim_dict["created_date"] = ""
            
            enriched_simulations.append(sim_dict)
        
        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })
        
    except Exception as e:
        logger.error(f"获取历史模拟失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """
    获取模拟的代理体画像
    
    Query参数：
        platform: 平台类型（reddit/twitter，默认reddit）
    """
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"获取代理体画像失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """
    实时获取模拟的代理体画像（用于在生成过程中实时查看进度）
    
    与 /profiles 接口的区别：
    - 直接读取文件，不经过 SimulationManager
    - 适用于生成过程中的实时查看
    - 返回额外的元数据（如文件修改时间、是否正在生成等）
    
    Query参数：
        platform: 平台类型（reddit/twitter，默认reddit）
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,  // 预期总数（如果有）
                "is_generating": true,  // 是否正在生成
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import csv
    from datetime import datetime
    
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        sim_dir = manager.resolve_artifact_dir(simulation_id, create_if_missing=False)
        if not sim_dir:
            sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": "未找到对应的模拟任务。"
            }), 404
        
        # 确定文件路径
        if platform == "envfish":
            profiles_file = os.path.join(sim_dir, "profiles_full.json")
        elif platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")
        
        # 检查文件是否存在
        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None
        
        if file_exists:
            # 获取文件修改时间
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                if platform in {"reddit", "envfish"}:
                    profiles = read_json_file(profiles_file, default=[])
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except Exception as e:
                logger.warning(f"读取 profiles 文件失败（可能正在写入中）: {e}")
                profiles = []
        
        # 检查是否正在生成（通过 state.json 判断）
        is_generating = False
        total_expected = None
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                state_data = read_json_file(state_file, default={})
                status = state_data.get("status", "")
                is_generating = status == "preparing"
                total_expected = state_data.get("entities_count")
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        })
        
    except Exception as e:
        logger.error(f"实时获取Profile失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """
    实时获取模拟配置（用于在生成过程中实时查看进度）
    
    与 /config 接口的区别：
    - 直接读取文件，不经过 SimulationManager
    - 适用于生成过程中的实时查看
    - 返回额外的元数据（如文件修改时间、是否正在生成等）
    - 即使配置还没生成完也能返回部分信息
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,  // 是否正在生成
                "generation_stage": "generating_config",  // 当前生成阶段
                "config": {...}  // 配置内容（如果存在）
            }
        }
    """
    from datetime import datetime
    
    try:
        manager = SimulationManager()
        sim_dir = manager.resolve_artifact_dir(simulation_id, create_if_missing=False)
        if not sim_dir:
            sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": "未找到对应的模拟任务。"
            }), 404
        
        # 配置文件路径
        config_file = os.path.join(sim_dir, "simulation_config.json")
        
        # 检查文件是否存在
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None
        
        if file_exists:
            # 获取文件修改时间
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            config = read_json_file(config_file, default=None)
        
        # 检查是否正在生成（通过 state.json 判断）
        is_generating = False
        generation_stage = None
        config_generated = False
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                state_data = read_json_file(state_file, default={})
                status = state_data.get("status", "")
                is_generating = status == "preparing"
                config_generated = state_data.get("config_generated", False)
                
                # 判断当前阶段
                if is_generating:
                    if state_data.get("profiles_generated", False):
                        generation_stage = "generating_config"
                    else:
                        generation_stage = "generating_profiles"
                elif status == "ready":
                    generation_stage = "completed"
            except Exception:
                pass
        
        # 构建返回数据
        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "generation_stage_label": _prepare_stage_label(generation_stage),
            "current_stage_name": _prepare_stage_label(generation_stage),
            "config_generated": config_generated,
            "config": config
        }
        
        # 如果配置存在，提取一些关键统计信息
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "total_regions": len(config.get("region_graph", [])),
                "total_subregions": len(config.get("subregion_graph", [])),
                "total_transport_edges": len(config.get("transport_edges", [])),
                "total_relationships": len(config.get("agent_relationship_graph", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }
            response_data["engine_mode"] = config.get("engine_mode")
            response_data["scenario_mode"] = config.get("scenario_mode")
            response_data["diffusion_template"] = config.get("diffusion_template")
            response_data["hazard_template_id"] = config.get("hazard_template_id")
            response_data["hazard_template_mode"] = config.get("hazard_template_mode")
            response_data["hazard_template_reasoning"] = config.get("hazard_template_reasoning")
            response_data["hazard_template_recommendation"] = config.get("hazard_template_recommendation")
            response_data["transport_profile"] = config.get("transport_profile")
            response_data["search_mode"] = config.get("search_mode")
            response_data["time_plan_mode"] = config.get("time_plan_mode")
            response_data["time_plan"] = config.get("time_plan")
            response_data["temporal_profile"] = config.get("temporal_profile")
            response_data["reference_time"] = config.get("reference_time")
            response_data["diffusion_context"] = config.get("diffusion_context")

            grounding_summary = config.get("data_grounding_summary") or {}
            if isinstance(grounding_summary, dict):
                successful_sources = grounding_summary.get("successful_sources") or grounding_summary.get("sources_attempted") or []
                response_data["grounding_sources"] = successful_sources
                source_labels = _grounding_source_labels(successful_sources)
                response_data["grounding_source_labels"] = source_labels
                note = grounding_summary.get("note")
                if successful_sources:
                    response_data["data_grounding_summary"] = f"场景资料已由{'、'.join(source_labels)}提供依据。"
                elif note:
                    response_data["data_grounding_summary"] = _chinese_display_text(
                        note,
                        "场景基础资料已完成校验。",
                    )
            elif grounding_summary:
                response_data["data_grounding_summary"] = _chinese_display_text(
                    grounding_summary,
                    "场景基础资料已完成校验。",
                )

        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(f"实时获取Config失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """
    获取模拟配置（LLM智能生成的完整配置）
    
    返回包含：
        - time_config: 时间配置（模拟时长、轮次、高峰/低谷时段）
        - agent_configs: 每个Agent的活动配置（活跃度、发言频率、立场等）
        - event_config: 事件配置（初始帖子、热点话题）
        - platform_configs: 平台配置
        - generation_reasoning: LLM的配置推理说明
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        
        if not config:
            return jsonify({
                "success": False,
                "error": "模拟配置不存在，请先启动场景准备。"
            }), 404
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """下载模拟配置文件"""
    try:
        manager = SimulationManager()
        sim_dir = manager.resolve_artifact_dir(simulation_id, create_if_missing=False)
        if not sim_dir:
            sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": "配置文件不存在，请先启动场景准备。"
            }), 404
        
        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )
        
    except Exception as e:
        logger.error(f"下载配置失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """
    下载模拟运行脚本文件（通用脚本，位于 backend/scripts/）
    
    script_name可选值：
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # 脚本位于 backend/scripts/ 目录
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))
        
        # 验证脚本名称
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py", 
            "run_parallel_simulation.py",
            "run_envfish_simulation.py",
            "action_logger.py"
        ]
        
        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": f"未知脚本: {script_name}，可选: {allowed_scripts}"
            }), 400
        
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": f"脚本文件不存在: {script_name}"
            }), 404
        
        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )
        
    except Exception as e:
        logger.error(f"下载脚本失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Profile生成接口（独立使用） ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    [已停用] OASIS 社交模拟已退役，此端点不再生成代理体画像。

    返回 410 Gone，提示调用方该功能已被移除。
    """
    return jsonify({
        "success": False,
        "error": "功能已退役",
        "error_code": "retired",
        "message": "旧版社交模拟已退役；该端点不再支持生成代理体画像。",
        "deprecated": True
    }), 410


# ============== 模拟运行控制接口 ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    开始运行模拟

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",          // 必填，模拟ID
            "platform": "parallel",                // 可选: twitter / reddit / parallel (默认)
            "max_rounds": 100,                     // 可选: 最大模拟轮数，用于截断过长的模拟
            "enable_graph_memory_update": false,   // 可选: 是否将Agent活动动态更新到Zep图谱记忆
            "force": false                         // 可选: 强制重新开始（会停止运行中的模拟并清理日志）
        }

    关于 force 参数：
        - 启用后，如果模拟正在运行或已完成，会先停止并清理运行日志
        - 清理的内容包括：run_state.json, actions.jsonl, simulation.log 等
        - 不会清理配置文件（simulation_config.json）和 profile 文件
        - 适用于需要重新运行模拟的场景

    关于 enable_graph_memory_update：
        - 启用后，模拟中所有Agent的活动（发帖、评论、点赞等）都会实时更新到Zep图谱
        - 这可以让图谱"记住"模拟过程，用于后续分析或AI对话
        - 需要模拟关联的项目有有效的 graph_id
        - 采用批量更新机制，减少API调用次数

    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // 是否启用了图谱记忆更新
                "force_restarted": true               // 是否是强制重新开始
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # 可选：最大模拟轮数
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # 可选：是否启用图谱记忆更新
        force = data.get('force', False)  # 可选：强制重新开始

        # 验证 max_rounds 参数
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "最大轮数必须是正整数"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "最大轮数必须是有效整数"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel', 'envfish']:
            return jsonify({
                "success": False,
                "error": "平台类型无效，请选择单平台、双平台或环境推演模式。"
            }), 400

        # 检查模拟是否已准备好
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": "未找到对应的模拟任务。"
            }), 404

        if state.is_replay_only:
            total_rounds = int(state.configured_total_rounds or state.current_round or 0)
            total_hours = round(total_rounds * int(state.configured_minutes_per_round or 60) / 60, 1)
            state.status = SimulationStatus.COMPLETED
            state.current_round = total_rounds
            manager._save_simulation_state(state)
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "completed",
                    "current_round": total_rounds,
                    "total_rounds": total_rounds,
                    "progress_percent": 100,
                    "total_simulation_hours": total_hours,
                    "simulated_hours": total_hours,
                    "twitter_running": False,
                    "reddit_running": False,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                    "engine_mode": state.engine_mode,
                    "scenario_mode": state.scenario_mode,
                    "diffusion_template": state.diffusion_template,
                    "search_mode": state.search_mode,
                    "is_replay_only": True,
                    "message": "冻结演示案例直接进入回放，不启动模拟进程。",
                },
            })

        if (state.engine_mode or '').lower() == 'envfish':
            platform = 'parallel'
            enable_graph_memory_update = False

        force_restarted = False

        if force:
            logger.info(f"强制模式：关闭既有模拟环境 {simulation_id}")
            try:
                SimulationRunner.stop_existing_environment(simulation_id)
            except Exception as e:
                logger.warning(f"关闭既有模拟环境时出现警告: {str(e)}")
                return jsonify({
                    "success": False,
                    "error": "现有推演仍在结束处理中，请稍后重试。",
                }), 409

        # A fresh prepare resets the simulation state to READY but intentionally
        # leaves prior run artifacts available for history/report reads.  A
        # forced start must still clear those artifacts, otherwise the runner can
        # resume an old final-round checkpoint and report an instant completion.
        if force and state.status == SimulationStatus.READY:
            logger.info(f"强制模式：清理已准备模拟的旧运行日志 {simulation_id}")
            cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
            if not cleanup_result.get("success"):
                logger.warning(f"清理日志时出现警告: {cleanup_result.get('errors')}")
            force_restarted = True
        
        # 智能处理状态：如果准备工作已完成，允许重新启动
        if state.status != SimulationStatus.READY:
            # 检查准备工作是否已完成
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # 准备工作已完成，检查是否有正在运行的进程
                if state.status == SimulationStatus.RUNNING:
                    # 检查模拟进程是否真的在运行
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # 进程确实在运行
                        if force:
                            # 强制模式：停止运行中的模拟
                            logger.info(f"强制模式：停止运行中的模拟 {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"停止模拟时出现警告: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": "模拟正在运行中，请先停止当前推演，或启用强制重启选项。"
                            }), 400

                # 如果是强制模式，清理运行日志
                if force:
                    logger.info(f"强制模式：清理模拟日志 {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"清理日志时出现警告: {cleanup_result.get('errors')}")
                    force_restarted = True

                # 进程不存在或已结束，重置状态为 ready
                logger.info(f"模拟 {simulation_id} 准备工作已完成，重置状态为 ready（原状态: {state.status.value}）")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # 准备工作未完成
                return jsonify({
                    "success": False,
                    "error": "模拟尚未准备完成，请先完成场景准备。"
                }), 400
        
        # 获取图谱ID（用于图谱记忆更新）
        graph_id = None
        if enable_graph_memory_update:
            # 从模拟状态或项目中获取 graph_id
            graph_id = state.graph_id
            if not graph_id:
                # 尝试从项目中获取
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "启用图谱记忆更新需要有效的图谱编号，请确保项目已构建图谱。"
                }), 400
            
            logger.info(f"启用图谱记忆更新: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # 启动模拟
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # 更新模拟状态
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        response_data['engine_mode'] = state.engine_mode
        response_data['scenario_mode'] = state.scenario_mode
        response_data['diffusion_template'] = state.diffusion_template
        response_data['search_mode'] = state.search_mode
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"启动模拟失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    停止模拟
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx"  // 必填，模拟ID
        }
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400
        
        run_state = SimulationRunner.stop_simulation(simulation_id)
        
        # 更新模拟状态
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"停止模拟失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/inject', methods=['POST'])
def inject_simulation_variable():
    """
    向运行中的 EnvFish 模拟注入变量
    """
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify({
                "success": False,
                "error": "未找到对应的模拟任务。",
            }), 404
        idempotency_key = _normalize_injection_idempotency_key(
            data.get("idempotency_key") or request.headers.get("Idempotency-Key")
        )

        with _injection_request_lock(manager, simulation_id):
            receipt = _read_injection_receipt(manager, simulation_id, idempotency_key)
            if receipt:
                artifact_ref = receipt.get("semantic_artifact_ref") or {}
                logger.info(
                    "semantic.inject_replay simulation_id=%s key=%s hash=%s",
                    simulation_id,
                    idempotency_key,
                    artifact_ref.get("content_hash", ""),
                )
                return jsonify({"success": True, "data": receipt}), 200

            project = ProjectManager.get_project(state.project_id)
            if not project:
                return jsonify({
                    "success": False,
                    "error": "未找到对应的场景项目。",
                }), 404
            foundation = _build_scenario_foundation(project, state)
            semantic_artifact = SemanticInputNormalizer().normalize_intervention(
                payload=data,
                target_catalog=foundation.get("target_catalog") or [],
                default_region_ids=foundation.get("region_ids") or [],
                current_round=int(state.current_round or 0),
                previous_artifact_ref=(
                    data.get("semantic_artifact_ref")
                    or state.semantic_artifact_ref
                    or getattr(project, "semantic_artifact_ref", None)
                ),
            )
            normalized = semantic_artifact.interventions[-1]
            artifact_ref = SemanticArtifactStore.public_ref(semantic_artifact)

            variable = {
                "variable_id": normalized.input_id,
                "type": normalized.type,
                "template": data.get("template") or (normalized.atomic_keys[0] if normalized.atomic_keys else "generic"),
                "name": normalized.name,
                "description": normalized.description,
                "target_regions": list(normalized.target_region_ids),
                "target_nodes": list(normalized.target_entity_ids),
                "start_round": normalized.time.start_round,
                "duration_rounds": normalized.time.duration_rounds or 1,
                "intensity_0_100": normalized.intensity.score if normalized.intensity.score is not None else 50,
                "policy_mode": normalized.policy_mode or data.get("policy_mode"),
                "atomic_keys": list(normalized.atomic_keys),
                "action_primitives": list(normalized.action_primitives),
                "semantic_artifact_ref": artifact_ref,
            }

            result = SimulationRunner.inject_variable(
                simulation_id=simulation_id,
                variable=variable,
                timeout=float(data.get("timeout", 30)),
            )
            response_data = {
                **result,
                "normalized_intervention": variable,
                "semantic_artifact_ref": artifact_ref,
                "semantic_revision": semantic_artifact.revision,
            }

            if result.get("success"):
                state.semantic_artifact_ref = artifact_ref
                manager._save_simulation_state(state)
                if hasattr(project, "semantic_artifact_ref"):
                    project.semantic_artifact_ref = dict(state.semantic_artifact_ref)
                    ProjectManager.save_project(project)
                _write_injection_receipt(
                    manager,
                    simulation_id,
                    idempotency_key,
                    response_data,
                )

            return jsonify({
                "success": result.get("success", False),
                "data": response_data,
            }), 200 if result.get("success") else 400

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        logger.error(f"注入变量失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 实时状态监控接口 ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """
    获取模拟运行实时状态（用于前端轮询）
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            manager = SimulationManager()
            simulation_state = manager.get_simulation(simulation_id)
            if simulation_state and simulation_state.is_replay_only:
                total_rounds = int(simulation_state.configured_total_rounds or simulation_state.current_round or 0)
                total_hours = round(total_rounds * int(simulation_state.configured_minutes_per_round or 60) / 60, 1)
                return _public_runtime_success({
                    "simulation_id": simulation_id,
                    "runner_status": "completed",
                    "current_round": total_rounds,
                    "total_rounds": total_rounds,
                    "progress_percent": 100,
                    "simulated_hours": total_hours,
                    "total_simulation_hours": total_hours,
                    "twitter_running": False,
                    "reddit_running": False,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                    "engine_mode": simulation_state.engine_mode,
                    "scenario_mode": simulation_state.scenario_mode,
                    "diffusion_template": simulation_state.diffusion_template,
                    "search_mode": simulation_state.search_mode,
                    "artifact_mode": simulation_state.artifact_mode,
                    "golden_case_id": simulation_state.golden_case_id,
                    "is_replay_only": True,
                    "message": "冻结演示案例已完成，可直接播放。",
                })
            return _public_runtime_success({
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                    "engine_mode": simulation_state.engine_mode if simulation_state else None,
                    "scenario_mode": simulation_state.scenario_mode if simulation_state else None,
                    "diffusion_template": simulation_state.diffusion_template if simulation_state else None,
                    "search_mode": simulation_state.search_mode if simulation_state else None,
                })
        
        result = run_state.to_dict()
        manager = SimulationManager()
        simulation_state = manager.get_simulation(simulation_id)
        if simulation_state:
            result["engine_mode"] = simulation_state.engine_mode
            result["scenario_mode"] = simulation_state.scenario_mode
            result["diffusion_template"] = simulation_state.diffusion_template
            result["search_mode"] = simulation_state.search_mode
        return _public_runtime_success(result)
        
    except Exception as e:
        logger.error(f"获取运行状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取运行状态失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """
    获取模拟运行详细状态（包含所有动作）
    
    用于前端展示实时动态
    
    Query参数：
        platform: 过滤平台（twitter/reddit，可选）
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # Twitter 平台的所有动作
                "reddit_actions": [...]    # Reddit 平台的所有动作
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        include_actions = request.args.get("include_actions", "true").lower() not in {"0", "false", "no", "off"}
        include_envfish_raw = request.args.get("include_envfish_raw", "false").lower() not in {"0", "false", "no", "off"}
        
        if not run_state:
            manager = SimulationManager()
            simulation_state = manager.get_simulation(simulation_id)
            if simulation_state and simulation_state.is_replay_only:
                simulation_config = manager.get_simulation_config(simulation_id) or {}
                total_rounds = int(
                    simulation_config.get("time_config", {}).get("total_rounds")
                    or simulation_state.configured_total_rounds
                    or simulation_state.current_round
                    or 0
                )
                total_hours = round(total_rounds * int(simulation_state.configured_minutes_per_round or 60) / 60, 1)
                result = {
                    "simulation_id": simulation_id,
                    "runner_status": "completed",
                    "current_round": total_rounds,
                    "total_rounds": total_rounds,
                    "progress_percent": 100,
                    "simulated_hours": total_hours,
                    "total_simulation_hours": total_hours,
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": [],
                    "recent_actions": [],
                    "rounds_count": total_rounds,
                    "engine_mode": simulation_state.engine_mode,
                    "scenario_mode": simulation_state.scenario_mode,
                    "diffusion_template": simulation_state.diffusion_template,
                    "search_mode": simulation_state.search_mode,
                    "artifact_mode": simulation_state.artifact_mode,
                    "golden_case_id": simulation_state.golden_case_id,
                    "is_replay_only": True,
                    "message": "冻结演示案例已完成，可直接播放。",
                }
                envfish_artifacts = SimulationRunner.get_envfish_artifacts(simulation_id)
                if include_envfish_raw:
                    result["envfish"] = envfish_artifacts
                result["region_graph"] = envfish_artifacts.get("region_graph", [])
                result["subregion_graph"] = envfish_artifacts.get("subregion_graph", [])
                result["risk_definitions"] = envfish_artifacts.get("risk_definitions", [])
                result["latest_risk_runtime_state"] = envfish_artifacts.get("latest_risk_runtime_state", {})
                result["risk_runtime_history"] = envfish_artifacts.get("risk_runtime_history", [])
                result["risk_events"] = envfish_artifacts.get("risk_events", [])
                result["primary_active_risk_id"] = (
                    envfish_artifacts.get("latest_risk_runtime_state", {}).get("primary_active_risk_id")
                    or (envfish_artifacts.get("risk_objects_summary") or {}).get("primary_active_risk_id")
                    or ""
                )
                result["risk_objects"] = envfish_artifacts.get("risk_objects", [])
                result["risk_objects_summary"] = envfish_artifacts.get("risk_objects_summary") or {}
                result["primary_risk_object"] = envfish_artifacts.get("primary_risk_object")
                result["round_snapshots"] = envfish_artifacts.get("round_snapshots", [])
                result["latest_snapshot"] = envfish_artifacts.get("latest_snapshot")
                result["latest_round_snapshot"] = envfish_artifacts.get("latest_snapshot")
                result["spread_events"] = envfish_artifacts.get("spread_events", [])
                result["agent_interactions"] = envfish_artifacts.get("agent_interactions", [])
                result["dynamic_edge_events"] = envfish_artifacts.get("dynamic_edge_events", [])
                result["relationship_events"] = envfish_artifacts.get("relationship_events", [])
                result["relationship_states"] = envfish_artifacts.get("relationship_states", [])
                result["agent_action_decisions"] = envfish_artifacts.get("agent_action_decisions", [])
                result["state_mutations"] = envfish_artifacts.get("state_mutations", [])
                result["agent_emergence_events"] = envfish_artifacts.get("agent_emergence_events", [])
                result["agent_lineage"] = envfish_artifacts.get("agent_lineage", [])
                result["agent_candidate_events"] = envfish_artifacts.get("agent_candidate_events", [])
                result["policy_execution_events"] = envfish_artifacts.get("policy_execution_events", [])
                result["policy_execution_runtime_state"] = envfish_artifacts.get("policy_execution_runtime_state", {})
                result["interventions"] = envfish_artifacts.get("interventions", [])
                result["regional_scores"] = envfish_artifacts.get("regional_scores", [])
                latest_snapshot = envfish_artifacts.get("latest_snapshot") or {}
                feedback = latest_snapshot.get("feedback") or {}
                result["feedback_loops"] = [
                    item.get("loop")
                    for item in feedback.get("feedback_propagation") or []
                    if item.get("loop")
                ]
                return _public_runtime_success(result)
            return _public_runtime_success({
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                })
        
        manager = SimulationManager()
        simulation_state = manager.get_simulation(simulation_id)
        simulation_config = manager.get_simulation_config(simulation_id) or {}
        engine_mode = (
            (simulation_state.engine_mode if simulation_state else None)
            or simulation_config.get("engine_mode")
            or "oasis"
        )

        current_round = run_state.current_round
        all_actions = []
        twitter_actions = []
        reddit_actions = []
        recent_actions = []
        if include_actions:
            # 获取完整的动作列表
            all_actions = SimulationRunner.get_all_actions(
                simulation_id=simulation_id,
                platform=platform_filter
            )

            # 分平台获取动作
            twitter_actions = SimulationRunner.get_all_actions(
                simulation_id=simulation_id,
                platform="twitter"
            ) if not platform_filter or platform_filter == "twitter" else []

            reddit_actions = SimulationRunner.get_all_actions(
                simulation_id=simulation_id,
                platform="reddit"
            ) if not platform_filter or platform_filter == "reddit" else []

            # 获取当前轮次的动作（recent_actions 只展示最新一轮）
            recent_actions = SimulationRunner.get_all_actions(
                simulation_id=simulation_id,
                platform=platform_filter,
                round_num=current_round
            ) if current_round > 0 else []
        
        # 获取基础状态信息
        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        # recent_actions 只展示当前最新一轮两个平台的内容
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        result["engine_mode"] = engine_mode

        if engine_mode == "envfish":
            envfish_artifacts = SimulationRunner.get_envfish_artifacts(simulation_id)
            if include_envfish_raw:
                result["envfish"] = envfish_artifacts
            result["region_graph"] = envfish_artifacts.get("region_graph", [])
            result["subregion_graph"] = envfish_artifacts.get("subregion_graph", [])
            result["risk_definitions"] = envfish_artifacts.get("risk_definitions", [])
            result["latest_risk_runtime_state"] = envfish_artifacts.get("latest_risk_runtime_state", {})
            result["risk_runtime_history"] = envfish_artifacts.get("risk_runtime_history", [])
            result["risk_events"] = envfish_artifacts.get("risk_events", [])
            result["primary_active_risk_id"] = (
                envfish_artifacts.get("latest_risk_runtime_state", {}).get("primary_active_risk_id")
                or (envfish_artifacts.get("risk_objects_summary") or {}).get("primary_active_risk_id")
                or ""
            )
            result["risk_objects"] = envfish_artifacts.get("risk_objects", [])
            result["risk_objects_summary"] = envfish_artifacts.get("risk_objects_summary") or {}
            result["primary_risk_object"] = envfish_artifacts.get("primary_risk_object")
            result["round_snapshots"] = envfish_artifacts.get("round_snapshots", [])
            result["latest_snapshot"] = envfish_artifacts.get("latest_snapshot")
            result["spread_events"] = envfish_artifacts.get("spread_events", [])
            result["agent_interactions"] = envfish_artifacts.get("agent_interactions", [])
            result["dynamic_edge_events"] = envfish_artifacts.get("dynamic_edge_events", [])
            result["relationship_events"] = envfish_artifacts.get("relationship_events", [])
            result["relationship_states"] = envfish_artifacts.get("relationship_states", [])
            result["agent_action_decisions"] = envfish_artifacts.get("agent_action_decisions", [])
            result["state_mutations"] = envfish_artifacts.get("state_mutations", [])
            result["agent_emergence_events"] = envfish_artifacts.get("agent_emergence_events", [])
            result["agent_lineage"] = envfish_artifacts.get("agent_lineage", [])
            result["agent_candidate_events"] = envfish_artifacts.get("agent_candidate_events", [])
            result["policy_execution_events"] = envfish_artifacts.get("policy_execution_events", [])
            result["policy_execution_runtime_state"] = envfish_artifacts.get("policy_execution_runtime_state", {})
            result["interventions"] = envfish_artifacts.get("interventions", [])
            result["regional_scores"] = envfish_artifacts.get("regional_scores", [])
            latest_snapshot = envfish_artifacts.get("latest_snapshot") or {}
            feedback = latest_snapshot.get("feedback") or {}
            loops = []
            for item in feedback.get("feedback_propagation") or []:
                loop_name = item.get("loop")
                if loop_name and loop_name not in loops:
                    loops.append(loop_name)
            result["feedback_loops"] = loops
            if latest_snapshot.get("round"):
                result["latest_round_snapshot"] = latest_snapshot
                result["current_round"] = max(result.get("current_round", 0), latest_snapshot.get("round", 0))
            regional_scores = envfish_artifacts.get("regional_scores", [])
            if regional_scores:
                confidences = [
                    item.get("uncertainty_band", {}).get("confidence")
                    for item in regional_scores
                    if isinstance(item.get("uncertainty_band"), dict)
                ]
                if confidences:
                    result["uncertainty_band"] = round(sum(confidences) / len(confidences), 2)

        return _public_runtime_success(result)
        
    except Exception as e:
        logger.error(f"获取详细状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取详细状态失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """
    获取模拟中的Agent动作历史
    
    Query参数：
        limit: 返回数量（默认100）
        offset: 偏移量（默认0）
        platform: 过滤平台（twitter/reddit）
        agent_id: 过滤Agent ID
        round_num: 过滤轮次
    
    返回：
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(f"获取动作历史失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """
    获取模拟时间线（按轮次汇总）
    
    用于前端展示进度条和时间线视图
    
    Query参数：
        start_round: 起始轮次（默认0）
        end_round: 结束轮次（默认全部）
    
    返回每轮的汇总信息
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(f"获取时间线失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """
    获取每个Agent的统计信息
    
    用于前端展示Agent活跃度排行、动作分布等
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(f"获取Agent统计失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 数据库查询接口 ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """
    获取模拟中的帖子
    
    Query参数：
        platform: 平台类型（twitter/reddit）
        limit: 返回数量（默认50）
        offset: 偏移量
    
    返回帖子列表（从SQLite数据库读取）
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "数据库不存在，模拟可能尚未运行"
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(f"获取帖子失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """
    获取模拟中的评论（仅Reddit）
    
    Query参数：
        post_id: 过滤帖子ID（可选）
        limit: 返回数量
        offset: 偏移量
    """
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(f"获取评论失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interview 采访接口 ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """
    采访单个Agent

    注意：此功能需要模拟环境处于运行状态（完成模拟循环后进入等待命令模式）

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",       // 必填，模拟ID
            "agent_id": 0,                     // 必填，Agent ID
            "prompt": "你对这件事有什么看法？",  // 必填，采访问题
            "platform": "twitter",             // 可选，指定平台（twitter/reddit）
                                               // 不指定时：双平台模拟同时采访两个平台
            "timeout": 60                      // 可选，超时时间（秒），默认60
        }

    返回（不指定platform，双平台模式）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "你对这件事有什么看法？",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    返回（指定platform）：
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "你对这件事有什么看法？",
                "result": {
                    "agent_id": 0,
                    "response": "我认为...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # 可选：twitter/reddit/None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": "请提供代理体编号"
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": "请提供采访问题"
            }), 400
        
        # 验证platform参数
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "平台参数无效，请选择已支持的单一社交平台。"
            }), 400
        
        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "模拟环境未运行或已关闭。请确保模拟已完成并进入等待命令模式。"
            }), 400
        
        # 优化prompt，添加前缀避免Agent调用工具
        optimized_prompt = optimize_interview_prompt(prompt)
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": "等待采访响应超时，请稍后重试。"
        }), 504
        
    except Exception as e:
        logger.error(f"Interview失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """
    批量采访多个Agent

    注意：此功能需要模拟环境处于运行状态

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",       // 必填，模拟ID
            "interviews": [                    // 必填，采访列表
                {
                    "agent_id": 0,
                    "prompt": "你对A有什么看法？",
                    "platform": "twitter"      // 可选，指定该Agent的采访平台
                },
                {
                    "agent_id": 1,
                    "prompt": "你对B有什么看法？"  // 不指定platform则使用默认值
                }
            ],
            "platform": "reddit",              // 可选，默认平台（被每项的platform覆盖）
                                               // 不指定时：双平台模拟每个Agent同时采访两个平台
            "timeout": 120                     // 可选，超时时间（秒），默认120
        }

    返回：
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  # 可选：twitter/reddit/None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": "请提供采访列表"
            }), 400

        # 验证platform参数
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "平台参数无效，请选择已支持的单一社交平台。"
            }), 400

        # 验证每个采访项
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"采访列表第 {i + 1} 项缺少代理体编号"
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": f"采访列表第 {i + 1} 项缺少采访问题"
                }), 400
            # 验证每项的platform（如果有）
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"采访列表第 {i + 1} 项的平台参数无效"
                }), 400

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "模拟环境未运行或已关闭。请确保模拟已完成并进入等待命令模式。"
            }), 400

        # 优化每个采访项的prompt，添加前缀避免Agent调用工具
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": "等待批量采访响应超时，请稍后重试。"
        }), 504

    except Exception as e:
        logger.error(f"批量Interview失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """
    全局采访 - 使用相同问题采访所有Agent

    注意：此功能需要模拟环境处于运行状态

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",            // 必填，模拟ID
            "prompt": "你对这件事整体有什么看法？",  // 必填，采访问题（所有Agent使用相同问题）
            "platform": "reddit",                   // 可选，指定平台（twitter/reddit）
                                                    // 不指定时：双平台模拟每个Agent同时采访两个平台
            "timeout": 180                          // 可选，超时时间（秒），默认180
        }

    返回：
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # 可选：twitter/reddit/None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": "请提供采访问题"
            }), 400

        # 验证platform参数
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": "平台参数无效，请选择已支持的单一社交平台。"
            }), 400

        # 检查环境状态
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "模拟环境未运行或已关闭。请确保模拟已完成并进入等待命令模式。"
            }), 400

        # 优化prompt，添加前缀避免Agent调用工具
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": "等待全局采访响应超时，请稍后重试。"
        }), 504

    except Exception as e:
        logger.error(f"全局Interview失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """
    获取Interview历史记录

    从模拟数据库中读取所有Interview记录

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",  // 必填，模拟ID
            "platform": "reddit",          // 可选，平台类型（reddit/twitter）
                                           // 不指定则返回两个平台的所有历史
            "agent_id": 0,                 // 可选，只获取该Agent的采访历史
            "limit": 100                   // 可选，返回数量，默认100
        }

    返回：
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "我认为...",
                        "prompt": "你对这件事有什么看法？",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # 不指定则返回两个平台的历史
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(f"获取Interview历史失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """
    获取模拟环境状态

    检查模拟环境是否存活（可以接收访谈命令）

    请求（JSON）：
        {
            "simulation_id": "sim_xxxx"  // 必填，模拟ID
        }

    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "环境正在运行，可以接收访谈命令"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)
        
        # 获取更详细的状态信息
        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = "环境正在运行，可以接收访谈命令"
        else:
            message = "环境未运行或已关闭"

        return _public_runtime_success({
            "simulation_id": simulation_id,
            "env_alive": env_alive,
            "twitter_available": env_status.get("twitter_available", False),
            "reddit_available": env_status.get("reddit_available", False),
            "message": message,
        })

    except Exception as e:
        logger.error(f"获取环境状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": public_error_message(e, "获取环境状态失败，请稍后重试。"),
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """
    关闭模拟环境
    
    向模拟发送关闭环境命令，使其优雅退出等待命令模式。
    
    注意：这不同于 /stop 接口，/stop 会强制终止进程，
    而此接口会让模拟优雅地关闭环境并退出。
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",  // 必填，模拟ID
            "timeout": 30                  // 可选，超时时间（秒），默认30
        }
    
    返回：
        {
            "success": true,
            "data": {
                "message": "环境关闭命令已发送",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "请提供模拟任务编号"
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        # 更新模拟状态
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"关闭环境失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
