"""Bind planned policies to evidence-bounded Agent V2 executors."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Sequence


POLICY_EXECUTION_PLAN_CONTRACT_VERSION = "policy-execution-plan.v2"


_PERMISSION_GROUPS = {
    "school_closure": [
        ["issue_school_closure", "issue_regulatory_order"],
        ["publish_student_safety_guidance", "issue_public_warning", "publish_verified_information"],
    ],
    "workplace_shutdown": [
        ["issue_workplace_shutdown", "issue_regulatory_order"],
        ["coordinate_business_continuity", "coordinate_emergency_resources"],
    ],
    "transport_restriction": [["manage_assigned_transport_network", "reroute_traffic"], ["issue_regulatory_order"]],
    "mobility_reduction": [["manage_assigned_transport_network", "reroute_traffic"]],
    "shelter_in_place": [["issue_public_warning"], ["coordinate_emergency_resources"]],
    "resource_dispatch": [["coordinate_emergency_resources", "deploy_rescue_resources"]],
    "population_relocation": [
        ["order_area_evacuation"],
        ["manage_assigned_transport_network", "reroute_traffic"],
    ],
    "exposure_reduction": [["order_area_evacuation", "issue_regulatory_order"]],
    "environmental_monitoring": [["collect_environmental_samples"], ["publish_monitoring_result"]],
    "risk_early_warning": [["issue_public_warning", "issue_technical_warning"]],
    "activity_restriction": [["issue_regulatory_order", "order_area_evacuation"]],
    "food_chain_exposure_reduction": [["issue_regulatory_order"]],
    "economic_compensation": [["administer_compensation"]],
    "livelihood_stabilization": [["administer_compensation", "coordinate_emergency_resources"]],
    "infrastructure_repair": [["deploy_internal_response_resources", "deploy_rescue_resources"]],
    "response_capacity_recovery": [["deploy_internal_response_resources", "coordinate_emergency_resources"]],
    "public_information": [["issue_public_warning", "publish_verified_information", "publish_monitoring_result"]],
    "risk_communication": [["issue_public_warning", "publish_verified_information"]],
}


_RESOURCE_REQUIREMENTS = {
    "school_closure": {"authority": 1.0, "attention": 0.5},
    "workplace_shutdown": {"authority": 1.0, "coordination": 0.5},
    "transport_restriction": {"authority": 1.0, "coordination": 1.0},
    "mobility_reduction": {"coordination": 0.5},
    "shelter_in_place": {"attention": 0.5, "coordination": 0.5},
    "resource_dispatch": {"coordination": 1.0, "response": 1.0},
    "population_relocation": {"coordination": 1.0, "response": 1.0},
    "exposure_reduction": {"coordination": 0.5},
    "environmental_monitoring": {"monitoring": 1.0, "analysis": 0.5},
    "risk_early_warning": {"attention": 0.5},
    "activity_restriction": {"authority": 1.0, "attention": 0.5},
    "food_chain_exposure_reduction": {"authority": 1.0},
    "economic_compensation": {"fiscal": 1.0, "coordination": 0.5},
    "livelihood_stabilization": {"fiscal": 0.5},
    "infrastructure_repair": {"response": 1.0, "technical": 1.0},
    "response_capacity_recovery": {"response": 1.0},
    "public_information": {"attention": 0.5},
    "risk_communication": {"attention": 0.5},
}


_STATE_EFFECTS = {
    "school_closure": {"exposure_score": -0.5, "service_capacity": -0.15, "economic_stress": 0.15},
    "workplace_shutdown": {"exposure_score": -0.4, "economic_stress": 0.5, "livelihood_stability": -0.3},
    "transport_restriction": {"exposure_score": -0.3, "service_capacity": -0.2, "response_capacity": 0.2},
    "mobility_reduction": {"exposure_score": -0.25},
    "shelter_in_place": {"exposure_score": -0.45, "panic_level": -0.1},
    "resource_dispatch": {"response_capacity": 0.7, "service_capacity": 0.4},
    "population_relocation": {"exposure_score": -1.0, "economic_stress": 0.4, "service_capacity": -0.2},
    "exposure_reduction": {"exposure_score": -0.8},
    "environmental_monitoring": {"response_capacity": 0.5, "public_trust": 0.2},
    "risk_early_warning": {"response_capacity": 0.4, "public_trust": 0.2, "panic_level": 0.1},
    "activity_restriction": {"exposure_score": -0.6, "economic_stress": 0.6, "livelihood_stability": -0.5},
    "food_chain_exposure_reduction": {"exposure_score": -0.5, "economic_stress": 0.3},
    "economic_compensation": {"economic_stress": -0.6, "livelihood_stability": 0.8, "public_trust": 0.4},
    "livelihood_stabilization": {"livelihood_stability": 0.6, "panic_level": -0.2},
    "infrastructure_repair": {"service_capacity": 0.9, "response_capacity": 0.5},
    "response_capacity_recovery": {"response_capacity": 0.8, "service_capacity": 0.4},
    "public_information": {"public_trust": 0.5, "panic_level": -0.25},
    "risk_communication": {"public_trust": 0.4, "panic_level": -0.2},
    "governance_intervention": {"response_capacity": 0.3},
}


class PolicyExecutionPlanner:
    def build(
        self,
        *,
        policy_plan: Sequence[Mapping[str, Any]],
        profiles: Sequence[Any],
        planning_input_ref: Mapping[str, Any],
    ) -> Dict[str, Any]:
        actor_profiles = [_mapping(item) for item in profiles]
        bindings = [self._bind_policy(dict(policy), actor_profiles) for policy in policy_plan or []]
        payload = {
            "contract_version": POLICY_EXECUTION_PLAN_CONTRACT_VERSION,
            "scenario_planning_ref": {
                "artifact_id": str(planning_input_ref.get("planning_input_id") or ""),
                "contract_version": str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                "content_hash": str(planning_input_ref.get("content_hash") or ""),
            },
            "policy_bindings": bindings,
            "summary": {
                "policy_count": len(bindings),
                "bound_count": sum(1 for item in bindings if item["binding_status"] == "bound"),
                "partial_count": sum(1 for item in bindings if item["binding_status"] == "partial"),
                "unbound_count": sum(1 for item in bindings if item["binding_status"] == "unbound"),
            },
            "execution_rule_zh": "政策只有在执行者能力、权限、辖区、生命周期和资源均满足时才进入运行状态。",
        }
        payload["policy_execution_plan_id"] = _stable_id("policy_execution_plan", payload)
        payload["content_hash"] = _content_hash(payload)
        return payload

    def _bind_policy(
        self,
        policy: Dict[str, Any],
        profiles: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        required_capabilities = set(_strings(policy.get("executor_capability_keys") or []))
        target_regions = set(_strings(policy.get("target_region_ids") or []))
        execution_primitives = _strings(
            policy.get("semantic_action_primitives")
            or policy.get("action_primitives")
            or policy.get("effect_primitives")
            or []
        )
        permission_groups = self._permission_groups(execution_primitives)
        resource_requirements = self._resource_requirements(execution_primitives)
        candidates = []
        for profile in profiles:
            lifecycle = str(
                profile.get("lifecycle_status")
                or (profile.get("runtime_lifecycle") or {}).get("lifecycle_status")
                or "active"
            )
            if lifecycle in {"retired", "merged"}:
                continue
            regions = set(
                _strings(
                    [
                        profile.get("primary_region"),
                        profile.get("home_region_id"),
                        *(profile.get("coverage_region_ids") or []),
                        *(profile.get("influenced_regions") or []),
                    ]
                )
            )
            if target_regions and regions and not target_regions.intersection(regions):
                continue
            capabilities = set(_strings(profile.get("capability_keys") or []))
            overlap = required_capabilities.intersection(capabilities)
            if required_capabilities and not overlap:
                continue
            candidates.append(
                {
                    "profile": profile,
                    "capability_overlap": overlap,
                    "permission_keys": set(_strings(profile.get("permission_keys") or [])),
                    "resource_budget": dict(profile.get("resource_budget") or {}),
                    "score": len(overlap) * 20
                    + int(bool(target_regions.intersection(regions))) * 10
                    + int(lifecycle == "active") * 5,
                }
            )
        selected = []
        remaining = set(required_capabilities)
        for candidate in sorted(candidates, key=lambda item: item["score"], reverse=True):
            contribution = remaining.intersection(candidate["capability_overlap"])
            if not contribution and required_capabilities:
                continue
            selected.append(candidate)
            remaining.difference_update(contribution)
            if not remaining:
                break

        union_permissions = set().union(
            *(item["permission_keys"] for item in selected)
        ) if selected else set()
        missing_permission_groups = [
            group for group in permission_groups if not union_permissions.intersection(group)
        ]
        available_resources: Dict[str, float] = {}
        for item in selected:
            for key, value in item["resource_budget"].items():
                if isinstance(value, (int, float)):
                    available_resources[str(key)] = available_resources.get(str(key), 0.0) + float(value)
        missing_resources = [
            key
            for key, minimum in resource_requirements.items()
            if available_resources.get(key, 0.0) < minimum
        ]
        unresolved = []
        unresolved_target_region_refs = _strings(
            policy.get("unresolved_target_region_refs") or []
        )
        if remaining:
            unresolved.append(f"缺少能力：{'、'.join(sorted(remaining))}")
        if missing_permission_groups:
            unresolved.append("缺少政策执行所需权限")
        if missing_resources:
            unresolved.append("缺少政策执行所需资源")
        if unresolved_target_region_refs:
            unresolved.append("部分政策目标无法映射到正式区域")
        executor_ids = [
            int(item["profile"].get("agent_id"))
            for item in selected
            if item["profile"].get("agent_id") is not None
            and str(item["profile"].get("agent_id")).lstrip("-").isdigit()
        ]
        inferred_target_regions = sorted(
            {
                region
                for item in selected
                for region in _strings(
                    [
                        item["profile"].get("primary_region"),
                        item["profile"].get("home_region_id"),
                        *(item["profile"].get("coverage_region_ids") or []),
                    ]
                )
            }
        )
        resolved_target_regions = sorted(target_regions) or inferred_target_regions
        target_scope_source = (
            "policy_explicit"
            if target_regions
            else "executor_jurisdiction_inferred"
            if resolved_target_regions
            else "unresolved"
        )
        if not resolved_target_regions:
            unresolved.append("缺少可执行的目标区域")
        if not executor_ids:
            status = "unbound"
        elif unresolved:
            status = "partial"
        else:
            status = "bound"
        policy_id = str(policy.get("policy_id") or _stable_id("policy", policy))
        return {
            "policy_id": policy_id,
            "label_zh": str(policy.get("label_zh") or "政策措施"),
            "binding_status": status,
            "executor_agent_ids": executor_ids,
            "required_capability_keys": sorted(required_capabilities),
            "covered_capability_keys": sorted(required_capabilities.difference(remaining)),
            "missing_capability_keys": sorted(remaining),
            "required_permission_groups": [sorted(group) for group in permission_groups],
            "missing_permission_groups": [sorted(group) for group in missing_permission_groups],
            "resource_requirements": resource_requirements,
            "missing_resource_keys": missing_resources,
            "target_region_ids": resolved_target_regions,
            "unresolved_target_region_refs": unresolved_target_region_refs,
            "target_scope_source": target_scope_source,
            "target_scope_confidence": 1.0 if target_regions else 0.7 if resolved_target_regions else 0.0,
            "target_entity_ids": _strings(policy.get("target_entity_ids") or []),
            "target_event_ids": _strings(policy.get("target_event_ids") or []),
            "target_mechanism_ids": _strings(policy.get("target_mechanism_ids") or []),
            "effect_primitives": _strings(policy.get("effect_primitives") or []),
            "state_effect_template": self._state_effects(policy.get("effect_primitives") or []),
            "expected_effects_zh": _strings(policy.get("expected_effects") or []),
            "side_effects_zh": _strings(policy.get("side_effects") or []),
            "intensity_0_100": max(
                0.0,
                min(100.0, _number(policy.get("intensity_0_100"), 100.0)),
            ),
            "start_round": int(policy.get("start_round") or 0),
            "duration_rounds": max(1, int(policy.get("duration_rounds") or 1)),
            "binding_reason_zh": (
                "已由具备互补能力、权限和资源的 Agent 联合执行。"
                if status == "bound"
                else "当前仅完成部分执行条件绑定。"
                if status == "partial"
                else "当前没有满足执行条件的 Agent，政策不会自动生效。"
            ),
            "unresolved_constraints": unresolved,
            "source_policy": deepcopy(policy),
        }

    @staticmethod
    def _permission_groups(primitives: Iterable[Any]) -> List[set[str]]:
        groups: List[set[str]] = []
        for primitive in _strings(primitives):
            for raw_group in _PERMISSION_GROUPS.get(primitive, []):
                group = set(raw_group)
                if group and group not in groups:
                    groups.append(group)
        return groups

    @staticmethod
    def _resource_requirements(primitives: Iterable[Any]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for primitive in _strings(primitives):
            for key, value in _RESOURCE_REQUIREMENTS.get(primitive, {}).items():
                result[key] = max(result.get(key, 0.0), float(value))
        return result

    @staticmethod
    def _state_effects(primitives: Iterable[Any]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for primitive in _strings(primitives):
            for key, value in _STATE_EFFECTS.get(primitive, {}).items():
                result[key] = round(result.get(key, 0.0) + float(value), 4)
        return result


def _mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        raw = value.to_dict()
        return dict(raw) if isinstance(raw, Mapping) else {}
    return {}


def _strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _content_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{_content_hash(parts)[:20]}"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


__all__ = [
    "POLICY_EXECUTION_PLAN_CONTRACT_VERSION",
    "PolicyExecutionPlanner",
]
