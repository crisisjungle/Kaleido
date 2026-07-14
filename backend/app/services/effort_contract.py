"""Shared, immutable analysis-effort contract.

Step 1 creates one snapshot and every later step only references it. The
snapshot stores product-level limits instead of exposing model tokens,
relationship search knobs, or Agent counts as editable frontend fields.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Mapping, Optional


EFFORT_PROFILE_VERSION = "effort-profile-v2"
LEGACY_EFFORT_PROFILE_VERSION = "effort-profile-v1"
DEFAULT_EFFORT_LEVEL = "high"
EFFORT_STAGES = ("step1", "step2", "step3", "step4")

_STAGE_TOKEN_SHARES = {
    "step1": 0.15,
    "step2": 0.30,
    "step3": 0.40,
    "step4": 0.15,
}

_DEGRADATION_ORDER = [
    "reduce_peripheral_action_candidates",
    "shorten_peripheral_relationship_search",
    "use_cached_or_deterministic_peripheral_policy",
    "reduce_alternative_explanations_and_noncritical_counterfactuals",
    "defer_low_priority_spatial_refinement",
    "preserve_critical_agents_core_mechanisms_evidence_and_snapshots",
]


def _stage_execution(
    step1: tuple[int, int, int],
    step2: tuple[int, int, int],
    step3: tuple[int, int, int],
    step4: tuple[int, int, int],
) -> Dict[str, Dict[str, int]]:
    return {
        stage: {
            "call_limit": values[0],
            "concurrency_limit": values[1],
            "timeout_seconds": values[2],
        }
        for stage, values in zip(EFFORT_STAGES, (step1, step2, step3, step4))
    }


def _profile(
    *,
    label: str,
    multiplier: float,
    token_min: int,
    token_max: int,
    stage_execution: Mapping[str, Mapping[str, int]],
    step1: Mapping[str, Any],
    step2: Mapping[str, Any],
    step3: Mapping[str, Any],
    step4: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "label": label,
        "budget_multiplier": multiplier,
        "recommended_total_token_min": token_min,
        "recommended_total_token_max": token_max,
        "stage_execution": {key: dict(value) for key, value in stage_execution.items()},
        "operation_limits": {
            "step1": dict(step1),
            "step2": dict(step2),
            "step3": dict(step3),
            "step4": dict(step4),
        },
    }


# These values are the executable counterpart of the canonical effort table in
# docs/plans/agent-architecture-v2-plan.md. Evidence, authority, AOI, severity,
# real-world duration, and the global active-risk cap do not loosen by tier.
EFFORT_LEVELS: Dict[str, Dict[str, Any]] = {
    "light": _profile(
        label="轻量",
        multiplier=0.2,
        token_min=80_000,
        token_max=200_000,
        stage_execution=_stage_execution((8, 1, 90), (16, 1, 180), (40, 2, 120), (8, 1, 180)),
        step1={
            "map_resolution_scale": 0.55,
            "base_spatial_level": 1,
            "hotspot_spatial_level": 3,
            "planning_anchor_limit": 12,
            "candidate_pool_limit": 36,
            "targeted_refinement_slots": 2,
            "spatial_hypothesis_limit": 1,
            "broad_r4_scan_allowed": 0,
        },
        step2={
            "mechanism_path_limit": 1,
            "alternative_path_limit": 1,
            "planned_agent_limit": 20,
            "relationship_candidates_per_agent": 4,
            "risk_candidate_scan_limit": 24,
            "active_risk_limit": 8,
            "profile_review_passes": 1,
        },
        step3={
            "deep_agents_per_round": 4,
            "actions_per_deep_agent": 2,
            "relationship_hops": 1,
            "critical_relationship_hops": 1,
            "dynamic_relationship_validations_per_round": 8,
            "scenario_branch_limit": 1,
            "runtime_agent_total_limit": 1,
            "runtime_agent_per_round_limit": 1,
        },
        step4={
            "evidence_review_passes": 1,
            "alternative_explanation_limit": 1,
            "counterfactual_runs": 0,
            "policy_comparison_runs": 0,
            "sensitivity_runs": 0,
        },
    ),
    "medium": _profile(
        label="标准",
        multiplier=0.5,
        token_min=250_000,
        token_max=600_000,
        stage_execution=_stage_execution((16, 2, 120), (32, 2, 240), (100, 4, 150), (16, 2, 240)),
        step1={
            "map_resolution_scale": 0.78,
            "base_spatial_level": 2,
            "hotspot_spatial_level": 3,
            "planning_anchor_limit": 24,
            "candidate_pool_limit": 72,
            "targeted_refinement_slots": 4,
            "spatial_hypothesis_limit": 1,
            "broad_r4_scan_allowed": 0,
        },
        step2={
            "mechanism_path_limit": 3,
            "alternative_path_limit": 2,
            "planned_agent_limit": 50,
            "relationship_candidates_per_agent": 8,
            "risk_candidate_scan_limit": 60,
            "active_risk_limit": 8,
            "profile_review_passes": 1,
        },
        step3={
            "deep_agents_per_round": 10,
            "actions_per_deep_agent": 3,
            "relationship_hops": 1,
            "critical_relationship_hops": 2,
            "dynamic_relationship_validations_per_round": 24,
            "scenario_branch_limit": 1,
            "runtime_agent_total_limit": 3,
            "runtime_agent_per_round_limit": 1,
        },
        step4={
            "evidence_review_passes": 1,
            "alternative_explanation_limit": 2,
            "counterfactual_runs": 0,
            "policy_comparison_runs": 1,
            "sensitivity_runs": 0,
        },
    ),
    "high": _profile(
        label="深入",
        multiplier=1.0,
        token_min=700_000,
        token_max=1_800_000,
        stage_execution=_stage_execution((32, 3, 150), (64, 4, 300), (240, 8, 180), (32, 3, 300)),
        step1={
            "map_resolution_scale": 1.0,
            "base_spatial_level": 2,
            "hotspot_spatial_level": 3,
            "planning_anchor_limit": 40,
            "candidate_pool_limit": 120,
            "targeted_refinement_slots": 8,
            "spatial_hypothesis_limit": 1,
            "broad_r4_scan_allowed": 0,
        },
        step2={
            "mechanism_path_limit": 6,
            "alternative_path_limit": 3,
            "planned_agent_limit": 120,
            "relationship_candidates_per_agent": 12,
            "risk_candidate_scan_limit": 120,
            "active_risk_limit": 8,
            "profile_review_passes": 2,
        },
        step3={
            "deep_agents_per_round": 24,
            "actions_per_deep_agent": 5,
            "relationship_hops": 2,
            "critical_relationship_hops": 2,
            "dynamic_relationship_validations_per_round": 60,
            "scenario_branch_limit": 2,
            "runtime_agent_total_limit": 8,
            "runtime_agent_per_round_limit": 2,
        },
        step4={
            "evidence_review_passes": 2,
            "alternative_explanation_limit": 3,
            "counterfactual_runs": 1,
            "policy_comparison_runs": 1,
            "sensitivity_runs": 0,
        },
    ),
    "extra_high": _profile(
        label="高强度",
        multiplier=2.5,
        token_min=2_000_000,
        token_max=5_000_000,
        stage_execution=_stage_execution((64, 6, 180), (128, 8, 360), (600, 16, 240), (64, 6, 360)),
        step1={
            "map_resolution_scale": 1.45,
            "base_spatial_level": 3,
            "hotspot_spatial_level": 4,
            "planning_anchor_limit": 80,
            "candidate_pool_limit": 240,
            "targeted_refinement_slots": 16,
            "spatial_hypothesis_limit": 1,
            "broad_r4_scan_allowed": 0,
        },
        step2={
            "mechanism_path_limit": 12,
            "alternative_path_limit": 6,
            "planned_agent_limit": 250,
            "relationship_candidates_per_agent": 20,
            "risk_candidate_scan_limit": 240,
            "active_risk_limit": 8,
            "profile_review_passes": 3,
        },
        step3={
            "deep_agents_per_round": 60,
            "actions_per_deep_agent": 7,
            "relationship_hops": 3,
            "critical_relationship_hops": 3,
            "dynamic_relationship_validations_per_round": 160,
            "scenario_branch_limit": 4,
            "runtime_agent_total_limit": 20,
            "runtime_agent_per_round_limit": 4,
        },
        step4={
            "evidence_review_passes": 3,
            "alternative_explanation_limit": 6,
            "counterfactual_runs": 3,
            "policy_comparison_runs": 3,
            "sensitivity_runs": 1,
        },
    ),
    "ultra": _profile(
        label="极致",
        multiplier=6.0,
        token_min=6_000_000,
        token_max=15_000_000,
        stage_execution=_stage_execution((120, 10, 240), (240, 12, 480), (1_400, 32, 300), (120, 10, 480)),
        step1={
            "map_resolution_scale": 1.9,
            "base_spatial_level": 3,
            "hotspot_spatial_level": 4,
            "planning_anchor_limit": 120,
            "candidate_pool_limit": 360,
            "targeted_refinement_slots": 32,
            "spatial_hypothesis_limit": 3,
            "broad_r4_scan_allowed": 0,
        },
        step2={
            "mechanism_path_limit": 24,
            "alternative_path_limit": 12,
            "planned_agent_limit": 500,
            "relationship_candidates_per_agent": 32,
            "risk_candidate_scan_limit": 240,
            "active_risk_limit": 8,
            "profile_review_passes": 5,
        },
        step3={
            "deep_agents_per_round": 120,
            "actions_per_deep_agent": 10,
            "relationship_hops": 4,
            "critical_relationship_hops": 4,
            "dynamic_relationship_validations_per_round": 400,
            "scenario_branch_limit": 8,
            "runtime_agent_total_limit": 50,
            "runtime_agent_per_round_limit": 8,
        },
        step4={
            "evidence_review_passes": 5,
            "alternative_explanation_limit": 12,
            "counterfactual_runs": 8,
            "policy_comparison_runs": 8,
            "sensitivity_runs": 3,
        },
    ),
}

# V1 is retained only for validating already persisted immutable snapshots.
_LEGACY_V1_LEVELS: Dict[str, Dict[str, Any]] = {
    "light": {"label": "轻量", "map_resolution_scale": 0.55, "mechanism_candidate_limit": 8, "alternative_chain_limit": 1, "spatial_detail_level": 1, "profile_detail_level": 1, "relationship_validation_hops": 1, "runtime_reasoning_depth": 1, "counterfactual_runs": 0, "report_review_passes": 1},
    "medium": {"label": "标准", "map_resolution_scale": 0.78, "mechanism_candidate_limit": 12, "alternative_chain_limit": 1, "spatial_detail_level": 2, "profile_detail_level": 2, "relationship_validation_hops": 2, "runtime_reasoning_depth": 2, "counterfactual_runs": 0, "report_review_passes": 1},
    "high": {"label": "深入", "map_resolution_scale": 1.0, "mechanism_candidate_limit": 18, "alternative_chain_limit": 2, "spatial_detail_level": 3, "profile_detail_level": 3, "relationship_validation_hops": 3, "runtime_reasoning_depth": 3, "counterfactual_runs": 1, "report_review_passes": 2},
    "extra_high": {"label": "极高", "map_resolution_scale": 1.45, "mechanism_candidate_limit": 26, "alternative_chain_limit": 3, "spatial_detail_level": 4, "profile_detail_level": 4, "relationship_validation_hops": 4, "runtime_reasoning_depth": 4, "counterfactual_runs": 2, "report_review_passes": 3},
    "ultra": {"label": "最高", "map_resolution_scale": 1.9, "mechanism_candidate_limit": 36, "alternative_chain_limit": 4, "spatial_detail_level": 5, "profile_detail_level": 5, "relationship_validation_hops": 5, "runtime_reasoning_depth": 5, "counterfactual_runs": 3, "report_review_passes": 4},
}

_LEVEL_ALIASES = {
    "extra-high": "extra_high",
    "extra high": "extra_high",
    "extrahigh": "extra_high",
}
_SNAPSHOT_ID_RE = re.compile(r"^effort_[a-zA-Z0-9_-]{6,80}$")
_VALID_SOURCES = {"user", "default", "legacy_migration", "legacy_frozen"}
_PROFILE_FIELDS = (
    "effort_level",
    "effort_label",
    "profile_version",
    "budget_multiplier",
    "recommended_total_token_min",
    "recommended_total_token_max",
    "stage_budgets",
    "invariants",
    "compatibility",
)
_LEGACY_PROFILE_FIELDS = (
    "effort_level",
    "effort_label",
    "profile_version",
    "stage_budgets",
    "compatibility",
)


class EffortContractError(ValueError):
    """Base error for invalid or conflicting effort snapshots."""


class EffortLockedError(EffortContractError):
    """Raised when a later step attempts to change the Step 1 snapshot."""


def normalize_effort_level(value: Any, *, default: str = DEFAULT_EFFORT_LEVEL) -> str:
    raw = str(value or default).strip().lower()
    normalized = _LEVEL_ALIASES.get(raw, raw.replace("-", "_").replace(" ", "_"))
    if normalized not in EFFORT_LEVELS:
        raise EffortContractError(f"不支持的分析强度档位: {value}")
    return normalized


def effort_label(value: Any) -> str:
    level = normalize_effort_level(value)
    return str(EFFORT_LEVELS[level]["label"])


def _build_stage_budget(
    *,
    stage: str,
    token_min: int,
    token_max: int,
    execution: Mapping[str, int],
    operation_limits: Mapping[str, Any],
) -> Dict[str, Any]:
    share = _STAGE_TOKEN_SHARES[stage]
    return {
        "stage": stage,
        "token_soft_limit": int(token_min * share),
        "token_hard_limit": int(token_max * share),
        "call_limit": int(execution["call_limit"]),
        "concurrency_limit": int(execution["concurrency_limit"]),
        "timeout_seconds": int(execution["timeout_seconds"]),
        "operation_limits": dict(operation_limits),
        "degradation_order": list(_DEGRADATION_ORDER),
    }


def _profile_payload(level: str) -> Dict[str, Any]:
    profile = copy.deepcopy(EFFORT_LEVELS[level])
    label = str(profile["label"])
    token_min = int(profile["recommended_total_token_min"])
    token_max = int(profile["recommended_total_token_max"])
    stage_budgets = {
        stage: _build_stage_budget(
            stage=stage,
            token_min=token_min,
            token_max=token_max,
            execution=profile["stage_execution"][stage],
            operation_limits=profile["operation_limits"][stage],
        )
        for stage in EFFORT_STAGES
    }
    return {
        "effort_level": level,
        "effort_label": label,
        "profile_version": EFFORT_PROFILE_VERSION,
        "budget_multiplier": float(profile["budget_multiplier"]),
        "recommended_total_token_min": token_min,
        "recommended_total_token_max": token_max,
        "stage_budgets": stage_budgets,
        "invariants": {
            "aoi_locked": True,
            "hazard_severity_not_scaled": True,
            "real_duration_not_scaled": True,
            "evidence_thresholds_not_scaled": True,
            "authority_thresholds_not_scaled": True,
            "active_risk_limit": 8,
            "broad_r4_scan_allowed": False,
        },
        "compatibility": {
            "simulation_architecture": "event_mechanism_graph_v2",
            "search_mode": "deep_search",
            "legacy_adapter": "llm_mechanism_v1",
        },
    }


def _legacy_profile_payload(level: str) -> Dict[str, Any]:
    profile = dict(_LEGACY_V1_LEVELS[level])
    label = str(profile.pop("label"))
    return {
        "effort_level": level,
        "effort_label": label,
        "profile_version": LEGACY_EFFORT_PROFILE_VERSION,
        "stage_budgets": profile,
        "compatibility": {
            "simulation_architecture": "llm_mechanism_v1",
            "search_mode": "deep_search",
        },
    }


def _profile_content_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def effort_content_hash(level: Any) -> str:
    return _profile_content_hash(_profile_payload(normalize_effort_level(level)))


def build_effort_snapshot(
    level: Any = DEFAULT_EFFORT_LEVEL,
    *,
    effort_snapshot_id: Optional[str] = None,
    source: str = "user",
    selected_at: Optional[str] = None,
    locked_at: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = normalize_effort_level(level)
    snapshot_id = str(effort_snapshot_id or "").strip()
    if snapshot_id and not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise EffortContractError("分析强度快照标识格式无效")
    normalized_source = str(source or "user").strip().lower()
    if normalized_source not in _VALID_SOURCES:
        raise EffortContractError(f"不支持的分析强度来源: {source}")
    now = datetime.now().isoformat()
    payload = _profile_payload(normalized)
    payload.update(
        {
            "effort_snapshot_id": snapshot_id or f"effort_{uuid.uuid4().hex[:16]}",
            "content_hash": effort_content_hash(normalized),
            "source": normalized_source,
            "selected_at": selected_at or locked_at or now,
            "locked": True,
            "locked_at": locked_at or now,
        }
    )
    return payload


def _validate_profile_hash(
    *,
    data: Mapping[str, Any],
    expected: Mapping[str, Any],
    fields: tuple[str, ...],
) -> None:
    provided_hash = str(data.get("content_hash") or "").strip()
    if not provided_hash:
        return
    expected_hash = _profile_content_hash(expected)
    if provided_hash == expected_hash:
        return
    persisted_profile = {key: data.get(key, expected[key]) for key in fields}
    persisted_semantics = {
        key: value for key, value in persisted_profile.items() if key != "effort_label"
    }
    expected_semantics = {
        key: value for key, value in expected.items() if key != "effort_label"
    }
    label_only_migration = (
        _profile_content_hash(persisted_profile) == provided_hash
        and persisted_semantics == expected_semantics
    )
    if not label_only_migration:
        raise EffortContractError("分析强度快照内容校验失败")


def _normalize_legacy_snapshot(data: Mapping[str, Any], level: str) -> Dict[str, Any]:
    expected = _legacy_profile_payload(level)
    _validate_profile_hash(data=data, expected=expected, fields=_LEGACY_PROFILE_FIELDS)
    snapshot_id = str(data.get("effort_snapshot_id") or data.get("snapshot_id") or "").strip()
    if snapshot_id and not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise EffortContractError("分析强度快照标识格式无效")
    locked_at = str(data.get("locked_at") or datetime.now().isoformat())
    expected.update(
        {
            "effort_snapshot_id": snapshot_id or f"effort_{uuid.uuid4().hex[:16]}",
            "content_hash": _profile_content_hash(expected),
            "source": "legacy_frozen",
            "selected_at": str(data.get("selected_at") or locked_at),
            "locked": True,
            "locked_at": locked_at,
        }
    )
    return expected


def normalize_effort_snapshot(
    snapshot: Optional[Mapping[str, Any]],
    *,
    default_level: Any = DEFAULT_EFFORT_LEVEL,
) -> Dict[str, Any]:
    data = dict(snapshot or {})
    level = normalize_effort_level(
        data.get("effort_level") or data.get("level") or default_level
    )
    profile_version = str(data.get("profile_version") or "").strip()
    stage_budgets = data.get("stage_budgets")
    looks_legacy = isinstance(stage_budgets, Mapping) and "step1" not in stage_budgets
    if profile_version == LEGACY_EFFORT_PROFILE_VERSION or looks_legacy:
        return _normalize_legacy_snapshot(data, level)
    if profile_version and profile_version != EFFORT_PROFILE_VERSION:
        raise EffortContractError(f"不支持的分析强度合同版本: {profile_version}")

    expected = _profile_payload(level)
    _validate_profile_hash(data=data, expected=expected, fields=_PROFILE_FIELDS)
    return build_effort_snapshot(
        level,
        effort_snapshot_id=data.get("effort_snapshot_id") or data.get("snapshot_id"),
        source=str(data.get("source") or "default"),
        selected_at=data.get("selected_at"),
        locked_at=data.get("locked_at"),
    )


def assert_effort_reference(
    snapshot: Mapping[str, Any],
    *,
    effort_snapshot_id: Any,
    requested_level: Any = None,
) -> Dict[str, Any]:
    resolved = normalize_effort_snapshot(snapshot)
    reference = str(effort_snapshot_id or "").strip()
    if not reference:
        raise EffortContractError("缺少已锁定的分析强度快照")
    if reference != resolved["effort_snapshot_id"]:
        raise EffortLockedError("分析强度已在第一步锁定，当前请求引用了其他快照")
    if requested_level not in (None, ""):
        level = normalize_effort_level(requested_level)
        if level != resolved["effort_level"]:
            raise EffortLockedError("分析强度已在第一步锁定，后续步骤不能修改")
    return resolved


def assert_effort_snapshot_consistency(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    reference_name: str = "上游任务",
    candidate_name: str = "当前任务",
) -> Dict[str, Any]:
    """Ensure two persisted stages point at the same immutable Effort snapshot."""

    resolved_reference = normalize_effort_snapshot(reference)
    resolved_candidate = normalize_effort_snapshot(candidate)
    same_id = (
        resolved_reference["effort_snapshot_id"]
        == resolved_candidate["effort_snapshot_id"]
    )
    same_hash = resolved_reference["content_hash"] == resolved_candidate["content_hash"]
    if not same_id or not same_hash:
        raise EffortLockedError(
            f"{candidate_name}使用的分析强度与{reference_name}已锁定快照不一致"
        )
    return resolved_reference


def effort_stage_budget(snapshot: Optional[Mapping[str, Any]], stage: str) -> Dict[str, Any]:
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in EFFORT_STAGES:
        raise EffortContractError(f"不支持的预算阶段: {stage}")
    resolved = normalize_effort_snapshot(snapshot)
    budgets = resolved.get("stage_budgets") or {}
    nested = budgets.get(normalized_stage) if isinstance(budgets, Mapping) else None
    if isinstance(nested, Mapping):
        return copy.deepcopy(dict(nested))
    # V1 projects did not own stage budgets. They remain immutable, while new
    # execution reads the v2 limits for the same user-selected level.
    return copy.deepcopy(_profile_payload(resolved["effort_level"])["stage_budgets"][normalized_stage])


def effort_operation_limit(
    snapshot: Optional[Mapping[str, Any]],
    stage: str,
    operation: str,
) -> Any:
    budget = effort_stage_budget(snapshot, stage)
    limits = budget.get("operation_limits") or {}
    if operation not in limits:
        raise EffortContractError(f"阶段 {stage} 未定义限制项: {operation}")
    return copy.deepcopy(limits[operation])


def map_limit_scale(snapshot: Optional[Mapping[str, Any]]) -> float:
    return float(effort_operation_limit(snapshot, "step1", "map_resolution_scale"))
