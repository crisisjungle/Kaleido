"""Evidence-bounded Step 2 Agent planning.

This module converts scenario RoleDemand rows and map evidence into a compact,
auditable AgentPlan. It deliberately treats the legacy profile generator as a
candidate producer, not as the authority on how many Agents must exist.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..effort_contract import effort_operation_limit, normalize_effort_snapshot
from ..envfish_models import (
    AgentRelationshipEdge,
    EnvAgentProfile,
    RegionNode,
    default_state_vector,
)
from ..zep_entity_reader import EntityNode
from .agent_archetypes import (
    AGENT_ARCHETYPE_CONTRACT_VERSION,
    archetype_for_demand,
    get_agent_archetype,
    infer_profile_archetype,
    list_agent_archetypes,
)
from .policy_execution_planner import PolicyExecutionPlanner


AGENT_PLAN_CONTRACT_VERSION = "agent-plan.v2"
PLACEMENT_PLAN_CONTRACT_VERSION = "agent-placement-plan.v2"
RESOLUTION_PLAN_CONTRACT_VERSION = "resolution-plan.v2"

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_FORMAL_SOURCE_KINDS = {"observed", "detected", "measured", "surveyed"}
_REFERENCE_SOURCE_KINDS = {"reference", "fallback", "contextual"}


def _mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return dict(result) if isinstance(result, Mapping) else {}
    return {}


def _strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = _content_hash(parts)[:18]
    return f"{prefix}_{digest}"


def _bounded_probability(value: Any, default: float = 0.5) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(1.0, parsed)), 3)


def _artifact_ref(
    artifact_id: str,
    contract_version: str,
    content_hash: str = "",
) -> Dict[str, str]:
    return {
        "artifact_id": str(artifact_id or ""),
        "contract_version": str(contract_version or ""),
        "content_hash": str(content_hash or ""),
    }


@dataclass
class AgentPlanningResult:
    profiles: List[EnvAgentProfile]
    relationships: List[AgentRelationshipEdge]
    role_demands: List[Dict[str, Any]]
    spatial_anchor_candidates: List[Dict[str, Any]]
    resolution_plan: Dict[str, Any]
    placement_plan: Dict[str, Any]
    agent_plan: Dict[str, Any]
    policy_execution_plan: Dict[str, Any]
    agent_archetypes: List[Dict[str, Any]]
    validated_relation_graph: Dict[str, Any]
    generation_summary: Dict[str, Any] = field(default_factory=dict)


class AgentPlannerV2:
    """Build a deterministic Agent plan from reviewed scenario inputs."""

    _RELATION_RULES: Sequence[Dict[str, Any]] = (
        {
            "source": "industry_regulator",
            "target": "critical_facility_operator",
            "type": "regulatory_oversight",
            "label_zh": "安全监管与事故监督",
            "trigger_zh": "设施进入异常或事故响应状态",
            "trust": 0.58,
            "dependency": 0.62,
            "coordination": 0.55,
        },
        {
            "source": "critical_facility_operator",
            "target": "industry_regulator",
            "type": "incident_reporting",
            "label_zh": "事故状态报告",
            "trigger_zh": "设施状态达到法定报告条件",
            "trust": 0.55,
            "dependency": 0.72,
            "coordination": 0.62,
        },
        {
            "source": "environmental_monitoring",
            "target": "industry_regulator",
            "type": "monitoring_report",
            "label_zh": "监测结果报告",
            "trigger_zh": "监测指标出现异常或达到预警阈值",
            "trust": 0.68,
            "dependency": 0.58,
            "coordination": 0.64,
        },
        {
            "source": "environmental_monitoring",
            "target": "local_government",
            "type": "early_warning_report",
            "label_zh": "技术监测与预警报告",
            "trigger_zh": "技术监测形成可核验的风险信号",
            "trust": 0.65,
            "dependency": 0.58,
            "coordination": 0.66,
        },
        {
            "source": "local_government",
            "target": "healthcare_provider",
            "type": "emergency_coordination",
            "label_zh": "医疗应急协调",
            "trigger_zh": "暴露或伤员需求超过常规医疗响应范围",
            "trust": 0.6,
            "dependency": 0.7,
            "coordination": 0.72,
        },
        {
            "source": "healthcare_provider",
            "target": "affected_population",
            "type": "medical_service",
            "label_zh": "医疗筛查与救治服务",
            "trigger_zh": "居民出现暴露、筛查或救治需求",
            "trust": 0.62,
            "dependency": 0.74,
            "coordination": 0.55,
        },
        {
            "source": "local_government",
            "target": "affected_population",
            "type": "public_warning",
            "label_zh": "公众预警与疏散协调",
            "trigger_zh": "区域达到预警或疏散触发条件",
            "trust": 0.52,
            "dependency": 0.68,
            "coordination": 0.58,
        },
        {
            "source": "community_organization",
            "target": "affected_population",
            "type": "community_support",
            "label_zh": "社区信息与支持服务",
            "trigger_zh": "社区出现信息、物资或脆弱群体支持需求",
            "trust": 0.66,
            "dependency": 0.52,
            "coordination": 0.7,
        },
        {
            "source": "local_government",
            "target": "transport_operator",
            "type": "evacuation_transport_coordination",
            "label_zh": "疏散交通协调",
            "trigger_zh": "疏散路线或运输能力需要统一调度",
            "trust": 0.58,
            "dependency": 0.7,
            "coordination": 0.72,
        },
        {
            "source": "supply_logistics",
            "target": "healthcare_provider",
            "type": "critical_supply",
            "label_zh": "医疗与应急物资供应",
            "trigger_zh": "医疗或防护物资低于响应需求",
            "trust": 0.56,
            "dependency": 0.76,
            "coordination": 0.6,
        },
        {
            "source": "media_information",
            "target": "affected_population",
            "type": "risk_communication",
            "label_zh": "风险信息传播",
            "trigger_zh": "已核验信息需要向公众传播",
            "trust": 0.48,
            "dependency": 0.4,
            "coordination": 0.45,
        },
    )

    def plan(
        self,
        *,
        candidate_profiles: Sequence[EnvAgentProfile],
        entities: Sequence[EntityNode],
        regions: Sequence[RegionNode],
        subregions: Sequence[RegionNode],
        role_demands: Sequence[Mapping[str, Any]],
        mechanism_graph: Mapping[str, Any],
        policy_plan: Sequence[Mapping[str, Any]],
        effort_snapshot: Mapping[str, Any],
        planning_input_ref: Mapping[str, Any],
    ) -> AgentPlanningResult:
        effort = normalize_effort_snapshot(effort_snapshot)
        planned_agent_limit = int(
            effort_operation_limit(effort, "step2", "planned_agent_limit")
        )
        relationship_limit = int(
            effort_operation_limit(
                effort,
                "step2",
                "relationship_candidates_per_agent",
            )
        )
        graph = dict(mechanism_graph or {})
        anchors = self._build_spatial_anchors(entities, regions, subregions)
        region_reference_index = self._build_region_reference_index(
            anchors=anchors,
            regions=regions,
            subregions=subregions,
        )
        foundation_ref = _mapping(planning_input_ref.get("foundation_ref"))
        scene_scope_refs = _strings([
            *(foundation_ref.get("region_ids") or []),
            foundation_ref.get("location"),
        ])
        default_scene_region_ids = _strings(region.region_id for region in regions)
        normalized_policy_plan = self._normalize_policy_region_refs(
            policy_plan,
            region_reference_index,
            scene_scope_refs=scene_scope_refs,
            default_region_ids=default_scene_region_ids,
        )
        normalized_role_demands = self._normalize_role_region_refs(
            role_demands,
            region_reference_index,
            scene_scope_refs=scene_scope_refs,
            default_region_ids=default_scene_region_ids,
        )
        demands = self._normalize_role_demands(
            role_demands=normalized_role_demands,
            mechanism_graph=graph,
            policy_plan=normalized_policy_plan,
            planning_input_ref=planning_input_ref,
        )
        profiles = [copy.deepcopy(item) for item in candidate_profiles]
        for profile in profiles:
            self._normalize_profile_region_refs(profile, region_reference_index)
        profile_archetypes = [infer_profile_archetype(item.to_dict()) for item in profiles]
        selected_indices: List[int] = []
        selected_profiles: List[EnvAgentProfile] = []
        placements: List[Dict[str, Any]] = []
        role_coverage: List[Dict[str, Any]] = []
        unresolved_demands: List[Dict[str, Any]] = []
        created_from_anchor = 0
        created_as_aggregate = 0

        ordered_demands = sorted(
            demands,
            key=lambda item: (
                _PRIORITY_RANK.get(str(item.get("priority") or "medium"), 2),
                str(item.get("role_demand_id") or ""),
            ),
        )
        for demand in ordered_demands:
            coverage_agent_ids: List[int] = []
            covered_regions: List[str] = []
            slot_results: List[Dict[str, Any]] = []
            unresolved_region_refs = _strings(demand.get("unresolved_region_refs") or [])
            if unresolved_region_refs and not _strings(demand.get("jurisdiction_region_ids") or []):
                reason_code = "unresolved_spatial_scope"
                unresolved_demands.append({
                    "unresolved_demand_id": _stable_id(
                        "unresolved_demand",
                        demand.get("role_demand_id"),
                        unresolved_region_refs,
                        reason_code,
                    ),
                    "role_demand_id": demand.get("role_demand_id"),
                    "role_key": demand.get("role_key"),
                    "label_zh": demand.get("label_zh"),
                    "target_region_id": "",
                    "priority": demand.get("priority"),
                    "reason_code": reason_code,
                    "reason_zh": "输入引用无法唯一映射到正式区域，未进行默认区域归属。",
                    "required_representation": demand.get("representation_requirement"),
                    "unresolved_region_refs": unresolved_region_refs,
                    "attempted_anchor_ids": [],
                })
                slot_results.append({
                    "target_region_id": "",
                    "status": "unresolved",
                    "reason_code": reason_code,
                    "unresolved_region_refs": unresolved_region_refs,
                })
                slots: List[str] = []
            else:
                slots = self._demand_slots(demand)
            for target_region in slots:
                reused_profile, candidate_score, candidate_anchor = self._best_selected_profile(
                    demand=demand,
                    target_region=target_region,
                    selected_profiles=selected_profiles,
                    anchors=anchors,
                )
                candidate_index: Optional[int] = None
                if reused_profile is None:
                    candidate_index, candidate_score, candidate_anchor = self._best_candidate(
                        demand=demand,
                        target_region=target_region,
                        profiles=profiles,
                        profile_archetypes=profile_archetypes,
                        anchors=anchors,
                        selected_indices=selected_indices,
                    )
                profile: Optional[EnvAgentProfile] = None
                archetype_key = archetype_for_demand(demand)
                placement_reason = ""
                if reused_profile is not None:
                    profile = reused_profile
                    placement_reason = "复用同一场景实例覆盖兼容的角色能力需求，避免重复 Agent。"
                elif candidate_index is not None:
                    profile = profiles[candidate_index]
                    if candidate_index not in selected_indices:
                        selected_indices.append(candidate_index)
                        selected_profiles.append(profile)
                    placement_reason = "复用已有地图或实体候选，并通过角色、区域和证据校验。"
                elif len(selected_profiles) < planned_agent_limit:
                    anchor = self._best_anchor(demand, target_region, anchors)
                    if anchor is not None:
                        profile = self._profile_from_anchor(
                            demand=demand,
                            target_region=target_region,
                            anchor=anchor,
                            archetype_key=archetype_key,
                            regions=regions,
                        )
                        selected_profiles.append(profile)
                        created_from_anchor += 1
                        candidate_anchor = anchor
                        candidate_score = 82.0
                        placement_reason = "由与角色需求匹配的正式空间锚点建立场景实例。"
                    elif self._aggregate_allowed(demand, target_region):
                        profile = self._aggregate_profile(
                            demand=demand,
                            target_region=target_region,
                            archetype_key=archetype_key,
                            regions=regions,
                        )
                        selected_profiles.append(profile)
                        created_as_aggregate += 1
                        candidate_score = 58.0
                        placement_reason = "缺少具体设施证据，按合同建立明确标记的区域聚合主体。"

                if profile is None:
                    reason_code = (
                        "budget_deferred"
                        if len(selected_profiles) >= planned_agent_limit
                        else "missing_required_spatial_evidence"
                    )
                    reason_zh = (
                        f"达到当前分析强度的 Agent 上限 {planned_agent_limit}。"
                        if reason_code == "budget_deferred"
                        else "未找到满足角色分辨率要求的正式空间或机构证据。"
                    )
                    unresolved = {
                        "unresolved_demand_id": _stable_id(
                            "unresolved_demand",
                            demand.get("role_demand_id"),
                            target_region,
                            reason_code,
                        ),
                        "role_demand_id": demand.get("role_demand_id"),
                        "role_key": demand.get("role_key"),
                        "label_zh": demand.get("label_zh"),
                        "target_region_id": target_region,
                        "priority": demand.get("priority"),
                        "reason_code": reason_code,
                        "reason_zh": reason_zh,
                        "required_representation": demand.get("representation_requirement"),
                        "attempted_anchor_ids": [
                            item["anchor_id"]
                            for item in anchors
                            if demand.get("role_key") in item.get("supported_role_keys", [])
                        ][:12],
                    }
                    unresolved_demands.append(unresolved)
                    slot_results.append({
                        "target_region_id": target_region,
                        "status": "unresolved",
                        "reason_code": reason_code,
                    })
                    continue

                self._apply_demand_to_profile(
                    profile=profile,
                    demand=demand,
                    archetype_key=archetype_key,
                    anchor=candidate_anchor,
                    target_region=target_region,
                    planning_input_ref=planning_input_ref,
                )
                provisional_id = id(profile)
                coverage_agent_ids.append(provisional_id)
                if target_region:
                    covered_regions.append(target_region)
                placements.append({
                    "placement_id": _stable_id(
                        "placement",
                        demand.get("role_demand_id"),
                        target_region,
                        candidate_anchor.get("anchor_id") if candidate_anchor else "aggregate",
                    ),
                    "role_demand_id": demand.get("role_demand_id"),
                    "role_key": demand.get("role_key"),
                    "profile_object_id": provisional_id,
                    "target_region_id": target_region,
                    "spatial_anchor_refs": (
                        [_artifact_ref(candidate_anchor["anchor_id"], "spatial-anchor.v2")]
                        if candidate_anchor
                        else []
                    ),
                    "representation_level": profile.representation_level,
                    "match_score": round(candidate_score, 2),
                    "reason_zh": placement_reason,
                })
                slot_results.append({
                    "target_region_id": target_region,
                    "status": "covered",
                    "profile_object_id": provisional_id,
                })

            covered_count = sum(1 for item in slot_results if item["status"] == "covered")
            status = "covered" if covered_count == len(slot_results) else ("partial" if covered_count else "unresolved")
            role_coverage.append({
                "role_coverage_id": _stable_id("role_coverage", demand.get("role_demand_id")),
                "role_demand_id": demand.get("role_demand_id"),
                "role_key": demand.get("role_key"),
                "label_zh": demand.get("label_zh"),
                "priority": demand.get("priority"),
                "status": status,
                "profile_object_ids": list(dict.fromkeys(coverage_agent_ids)),
                "covered_region_ids": _strings(covered_regions),
                "required_capabilities": list(demand.get("required_capabilities") or []),
                "slot_results": slot_results,
            })

        object_to_agent_id: Dict[int, int] = {}
        for agent_id, profile in enumerate(selected_profiles):
            object_to_agent_id[id(profile)] = agent_id
            profile.agent_id = agent_id
            profile.username = self._username(profile, agent_id)
            lifecycle = dict(profile.runtime_lifecycle or {})
            lifecycle.setdefault("lifecycle_status", profile.lifecycle_status or "active")
            lifecycle.setdefault("created_round", 0)
            lifecycle.setdefault("activation_round", profile.activation_round)
            lifecycle.setdefault("resolution_mode", "prepare_planned")
            lifecycle.setdefault("is_aggregate", bool(profile.is_aggregate))
            profile.runtime_lifecycle = lifecycle

        for placement in placements:
            object_id = int(placement.pop("profile_object_id"))
            placement["agent_id"] = object_to_agent_id.get(object_id)
        for coverage in role_coverage:
            object_ids = [int(value) for value in coverage.pop("profile_object_ids", [])]
            coverage["agent_ids"] = [
                object_to_agent_id[value]
                for value in object_ids
                if value in object_to_agent_id
            ]
            for slot in coverage.get("slot_results") or []:
                object_id = slot.pop("profile_object_id", None)
                if object_id is not None and int(object_id) in object_to_agent_id:
                    slot["agent_id"] = object_to_agent_id[int(object_id)]

        relationships = self._build_relationships(
            profiles=selected_profiles,
            role_demands=demands,
            per_agent_limit=relationship_limit,
        )
        relationship_refs_by_agent: Dict[int, List[str]] = {}
        for relationship in relationships:
            relationship_refs_by_agent.setdefault(relationship.source_agent_id, []).append(relationship.edge_id)
            relationship_refs_by_agent.setdefault(relationship.target_agent_id, []).append(relationship.edge_id)
        for profile in selected_profiles:
            profile.initial_relationship_refs = _strings(
                relationship_refs_by_agent.get(profile.agent_id, [])
            )

        policy_execution_plan = PolicyExecutionPlanner().build(
            policy_plan=normalized_policy_plan,
            profiles=selected_profiles,
            planning_input_ref=planning_input_ref,
        )

        placement_plan = self._placement_plan(
            placements=placements,
            role_coverage=role_coverage,
            unresolved_demands=unresolved_demands,
            planning_input_ref=planning_input_ref,
            effort=effort,
        )
        resolution_plan = self._resolution_plan(
            anchors=anchors,
            placements=placements,
            role_coverage=role_coverage,
            unresolved_demands=unresolved_demands,
            planning_input_ref=planning_input_ref,
            effort=effort,
        )
        agent_plan = self._agent_plan(
            profiles=selected_profiles,
            relationships=relationships,
            role_coverage=role_coverage,
            unresolved_demands=unresolved_demands,
            demands=demands,
            placement_plan=placement_plan,
            resolution_plan=resolution_plan,
            policy_execution_plan=policy_execution_plan,
            planning_input_ref=planning_input_ref,
            effort=effort,
            candidate_count=len(candidate_profiles),
            created_from_anchor=created_from_anchor,
            created_as_aggregate=created_as_aggregate,
            planned_agent_limit=planned_agent_limit,
        )
        validated_relation_graph = {
            "contract_version": "validated-agent-relations.v2",
            "source": "agent_plan_v2",
            "agent_plan_ref": _artifact_ref(
                agent_plan["agent_plan_id"],
                AGENT_PLAN_CONTRACT_VERSION,
                agent_plan["content_hash"],
            ),
            "edges": [item.to_dict() for item in relationships],
        }
        validated_relation_graph["content_hash"] = _content_hash(validated_relation_graph)
        summary = {
            "agent_plan_source": "agent_v2",
            "agent_plan_contract_version": AGENT_PLAN_CONTRACT_VERSION,
            "candidate_profile_count": len(candidate_profiles),
            "selected_agent_count": len(selected_profiles),
            "filtered_candidate_count": max(0, len(candidate_profiles) - len(selected_indices)),
            "created_from_anchor_count": created_from_anchor,
            "created_as_region_aggregate_count": created_as_aggregate,
            "resolved_spatial_anchor_count": sum(
                1 for item in anchors if item.get("region_resolution_status") == "resolved"
            ),
            "unresolved_spatial_anchor_count": sum(
                1 for item in anchors if item.get("region_resolution_status") == "unresolved"
            ),
            "role_demand_count": len(demands),
            "covered_role_demand_count": sum(1 for item in role_coverage if item["status"] == "covered"),
            "partially_covered_role_demand_count": sum(1 for item in role_coverage if item["status"] == "partial"),
            "unresolved_role_demand_count": len(unresolved_demands),
            "relationship_contract_count": len(relationships),
            "bound_policy_count": int(
                (policy_execution_plan.get("summary") or {}).get("bound_count") or 0
            ),
            "partially_bound_policy_count": int(
                (policy_execution_plan.get("summary") or {}).get("partial_count") or 0
            ),
            "unbound_policy_count": int(
                (policy_execution_plan.get("summary") or {}).get("unbound_count") or 0
            ),
            "planned_agent_limit": planned_agent_limit,
            "relationship_candidates_per_agent": relationship_limit,
            "target_agent_count_used": False,
        }
        return AgentPlanningResult(
            profiles=selected_profiles,
            relationships=relationships,
            role_demands=demands,
            spatial_anchor_candidates=anchors,
            resolution_plan=resolution_plan,
            placement_plan=placement_plan,
            agent_plan=agent_plan,
            policy_execution_plan=policy_execution_plan,
            agent_archetypes=list_agent_archetypes(),
            validated_relation_graph=validated_relation_graph,
            generation_summary=summary,
        )

    def _normalize_role_demands(
        self,
        *,
        role_demands: Sequence[Mapping[str, Any]],
        mechanism_graph: Mapping[str, Any],
        policy_plan: Sequence[Mapping[str, Any]],
        planning_input_ref: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        nodes = [dict(item) for item in (mechanism_graph.get("nodes") or []) if isinstance(item, Mapping)]
        edges = [dict(item) for item in (mechanism_graph.get("edges") or []) if isinstance(item, Mapping)]
        node_index = {
            str(item.get("event_id") or item.get("id") or ""): item
            for item in nodes
        }
        normalized: List[Dict[str, Any]] = []
        for raw in role_demands or []:
            item = dict(raw)
            role_key = str(item.get("role_key") or item.get("demand_key") or "").strip()
            if not role_key:
                continue
            archetype = get_agent_archetype(archetype_for_demand(item))
            demand_id = str(
                item.get("role_demand_id")
                or item.get("demand_id")
                or _stable_id("role_demand", role_key, item)
            )
            event_ids = _strings(item.get("caused_by_event_ids") or [])
            mechanism_ids = _strings(item.get("caused_by_mechanism_ids") or [])
            start_rounds = [
                int((node_index.get(event_id, {}).get("physical_time_window") or {}).get("start_round") or 0)
                for event_id in event_ids
            ]
            required_resolution = str(item.get("required_resolution") or "organization")
            representation = str(item.get("representation_requirement") or "") or {
                "specific_facility": "facility_required",
                "subunit": "subunit_required",
                "organization": "institution_required",
                "population_group": "aggregate_allowed",
                "ecological_receptor": "aggregate_allowed",
                "environmental_carrier": "aggregate_allowed",
            }.get(required_resolution, "aggregate_allowed")
            source_refs = _strings(
                [
                    *(item.get("source_refs") or []),
                    *(f"event:{value}" for value in event_ids),
                    *(f"mechanism:{value}" for value in mechanism_ids),
                ]
            )
            normalized.append({
                "role_demand_id": demand_id,
                "demand_id": demand_id,
                "role_key": role_key,
                "demand_key": role_key,
                "label_zh": str(item.get("label_zh") or archetype["label_zh"]),
                "source_type": str(item.get("source_type") or "mechanism"),
                "source_refs": source_refs,
                "caused_by_event_ids": event_ids,
                "caused_by_mechanism_ids": mechanism_ids,
                "required_capabilities": _strings(
                    item.get("required_capabilities")
                    or item.get("required_capability_keys")
                    or archetype["capabilities"]
                ),
                "required_capability_keys": _strings(
                    item.get("required_capability_keys")
                    or item.get("required_capabilities")
                    or archetype["capabilities"]
                ),
                "required_permissions": _strings(
                    item.get("required_permissions") or archetype["permissions"]
                ),
                "required_resource_types": _strings(
                    item.get("required_resource_types") or archetype["resource_types"]
                ),
                "jurisdiction_region_ids": _strings(item.get("jurisdiction_region_ids") or []),
                "affected_region_ids": _strings(
                    item.get("affected_region_ids")
                    or item.get("jurisdiction_region_ids")
                    or []
                ),
                "unresolved_region_refs": _strings(item.get("unresolved_region_refs") or []),
                "activation_phase": str(item.get("activation_phase") or "prepare"),
                "activation_round_hint": min(start_rounds) if start_rounds else 0,
                "priority": str(item.get("priority") or item.get("importance") or "medium").lower(),
                "importance": str(item.get("importance") or item.get("priority") or "medium").lower(),
                "representation_requirement": representation,
                "required_resolution": required_resolution,
                "multiplicity_rule": str(item.get("multiplicity_rule") or self._multiplicity(role_key, required_resolution)),
                "evidence_requirements": _strings(
                    item.get("evidence_requirements")
                    or self._evidence_requirements(representation, archetype_for_demand(item))
                ),
                "rationale_zh": str(item.get("rationale_zh") or "由已审阅事件机制提出角色能力需求。"),
                "archetype_key": archetype_for_demand(item),
                "planning_input_ref": _artifact_ref(
                    str(planning_input_ref.get("planning_input_id") or ""),
                    str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                    str(planning_input_ref.get("content_hash") or ""),
                ),
            })

        existing_keys = {item["role_key"] for item in normalized}
        propagation_edges = [
            item
            for item in edges
            if str(item.get("propagation_medium") or "").strip()
            not in {"", "system_coupling", "governance_action"}
        ]
        if propagation_edges and "environmental_carrier" not in existing_keys:
            normalized.append(self._derived_mechanism_demand(
                role_key="environmental_carrier",
                label_zh="环境传播载体",
                archetype_key="environmental_carrier",
                edges=propagation_edges,
                priority="medium",
                planning_input_ref=planning_input_ref,
            ))
        ecological_nodes = [
            item for item in nodes
            if str(item.get("atomic_key") or "") == "ecological_impact"
            or str(item.get("event_kind") or "") == "ecological"
        ]
        if ecological_nodes and "ecological_receptor" not in existing_keys:
            related_ids = {
                str(node.get("event_id") or node.get("id") or "")
                for node in ecological_nodes
            }
            ecological_edges = [
                edge for edge in edges
                if str(edge.get("source_event_id") or edge.get("source") or "") in related_ids
                or str(edge.get("target_event_id") or edge.get("target") or "") in related_ids
            ]
            normalized.append(self._derived_mechanism_demand(
                role_key="ecological_receptor",
                label_zh="生态受体响应",
                archetype_key="ecological_receptor",
                edges=ecological_edges,
                priority="medium",
                planning_input_ref=planning_input_ref,
            ))

        # A policy capability not represented by any role demand remains a real
        # planning gap instead of becoming a generic all-powerful government.
        demanded_capabilities = {
            capability
            for demand in normalized
            for capability in demand.get("required_capabilities") or []
        }
        uncovered_policy_capabilities = _strings(
            capability
            for policy in policy_plan or []
            for capability in policy.get("executor_capability_keys") or []
            if capability not in demanded_capabilities
        )
        if uncovered_policy_capabilities:
            fallback = {
                "demand_key": "policy_execution",
                "required_capability_keys": uncovered_policy_capabilities,
            }
            archetype = get_agent_archetype(archetype_for_demand(fallback))
            demand_id = _stable_id("role_demand", "policy_execution", uncovered_policy_capabilities)
            normalized.append({
                "role_demand_id": demand_id,
                "demand_id": demand_id,
                "role_key": "policy_execution",
                "demand_key": "policy_execution",
                "label_zh": "政策执行能力",
                "source_type": "policy",
                "source_refs": _strings(f"policy:{item.get('policy_id')}" for item in policy_plan if item.get("policy_id")),
                "caused_by_event_ids": [],
                "caused_by_mechanism_ids": [],
                "required_capabilities": uncovered_policy_capabilities,
                "required_capability_keys": uncovered_policy_capabilities,
                "required_permissions": list(archetype["permissions"]),
                "required_resource_types": list(archetype["resource_types"]),
                "jurisdiction_region_ids": _strings(
                    region
                    for item in policy_plan
                    for region in item.get("target_region_ids") or []
                ),
                "affected_region_ids": [],
                "activation_phase": "policy_triggered",
                "activation_round_hint": min(
                    [int(item.get("start_round") or 0) for item in policy_plan] or [0]
                ),
                "priority": "high",
                "importance": "high",
                "representation_requirement": "institution_required",
                "required_resolution": "organization",
                "multiplicity_rule": "single",
                "evidence_requirements": ["政策计划和执行能力引用"],
                "rationale_zh": "政策计划提出了尚未被其他角色覆盖的执行能力。",
                "archetype_key": archetype_for_demand(fallback),
                "planning_input_ref": _artifact_ref(
                    str(planning_input_ref.get("planning_input_id") or ""),
                    str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                    str(planning_input_ref.get("content_hash") or ""),
                ),
            })
        unique: Dict[str, Dict[str, Any]] = {}
        for demand in normalized:
            unique[str(demand["role_demand_id"])] = demand
        return list(unique.values())

    def _derived_mechanism_demand(
        self,
        *,
        role_key: str,
        label_zh: str,
        archetype_key: str,
        edges: Sequence[Mapping[str, Any]],
        priority: str,
        planning_input_ref: Mapping[str, Any],
    ) -> Dict[str, Any]:
        archetype = get_agent_archetype(archetype_key)
        mechanism_ids = _strings(
            item.get("mechanism_id") or item.get("id") for item in edges
        )
        event_ids = _strings(
            value
            for item in edges
            for value in (
                item.get("source_event_id") or item.get("source"),
                item.get("target_event_id") or item.get("target"),
            )
        )
        demand_id = _stable_id("role_demand", role_key, mechanism_ids)
        return {
            "role_demand_id": demand_id,
            "demand_id": demand_id,
            "role_key": role_key,
            "demand_key": role_key,
            "label_zh": label_zh,
            "source_type": "mechanism",
            "source_refs": _strings(f"mechanism:{item}" for item in mechanism_ids),
            "caused_by_event_ids": event_ids,
            "caused_by_mechanism_ids": mechanism_ids,
            "required_capabilities": list(archetype["capabilities"]),
            "required_capability_keys": list(archetype["capabilities"]),
            "required_permissions": list(archetype["permissions"]),
            "required_resource_types": list(archetype["resource_types"]),
            "jurisdiction_region_ids": [],
            "affected_region_ids": [],
            "activation_phase": "mechanism_active",
            "activation_round_hint": 0,
            "priority": priority,
            "importance": priority,
            "representation_requirement": "aggregate_allowed",
            "required_resolution": role_key,
            "multiplicity_rule": "single",
            "evidence_requirements": ["机制边引用", "区域环境证据"],
            "rationale_zh": "事件机制图包含需要独立表示的环境传播或受体端点。",
            "archetype_key": archetype_key,
            "planning_input_ref": _artifact_ref(
                str(planning_input_ref.get("planning_input_id") or ""),
                str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                str(planning_input_ref.get("content_hash") or ""),
            ),
        }

    def _build_spatial_anchors(
        self,
        entities: Sequence[EntityNode],
        regions: Sequence[RegionNode],
        subregions: Sequence[RegionNode],
    ) -> List[Dict[str, Any]]:
        formal_regions = [*regions, *subregions]
        region_ids = {str(item.region_id) for item in formal_regions}

        common_traditional_aliases = str.maketrans({
            "黃": "黄", "區": "区", "龍": "龙", "馬": "马", "遊": "游",
            "樂": "乐", "輝": "辉", "灣": "湾", "門": "门", "島": "岛",
            "體": "体", "廣": "广", "觀": "观", "醫": "医", "園": "园",
            "場": "场", "風": "风", "電": "电", "學": "学", "災": "灾",
            "應": "应", "對": "对", "業": "业", "務": "务", "臺": "台",
        })

        def alias_key(value: Any) -> str:
            normalized = str(value or "").translate(common_traditional_aliases).casefold()
            return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", normalized)

        def resolve_named_region(values: Iterable[Any]) -> str:
            candidate_keys = [alias_key(value) for value in values]
            candidate_keys = [value for value in candidate_keys if value]
            exact_matches = {
                str(region.region_id)
                for region in formal_regions
                if alias_key(region.region_id) in candidate_keys or alias_key(region.name) in candidate_keys
            }
            if len(exact_matches) == 1:
                return next(iter(exact_matches))
            fuzzy_matches = {
                str(region.region_id)
                for region in formal_regions
                for candidate in candidate_keys
                for region_alias in (alias_key(region.region_id), alias_key(region.name))
                if len(candidate) >= 3
                and len(region_alias) >= 3
                and (candidate in region_alias or region_alias in candidate)
            }
            return next(iter(fuzzy_matches)) if len(fuzzy_matches) == 1 else ""

        anchors: List[Dict[str, Any]] = []
        for entity in entities:
            attrs = dict(entity.attributes or {})
            source_kind = str(attrs.get("source_kind") or "observed").strip().lower()
            category = str(attrs.get("category") or "").strip().lower()
            subtype = str(attrs.get("subtype") or attrs.get("proxy_role") or "").strip().lower()
            role_keys = self._supported_role_keys(entity.name, entity.labels, category, subtype)
            explicit_region_refs = _strings([
                attrs.get("region_id"),
                attrs.get("parent_region_id"),
                attrs.get("home_region_id"),
            ])
            region_id = next((item for item in explicit_region_refs if item in region_ids), "")
            region_resolution_basis = "explicit_region_id" if region_id else ""
            if not region_id:
                region_id = next(
                    (
                        str(item.get("uuid") or "")
                        for item in entity.related_nodes or []
                        if str(item.get("uuid") or "") in region_ids
                    ),
                    "",
                )
                if region_id:
                    region_resolution_basis = "related_formal_region"
            if not region_id:
                region_id = resolve_named_region([
                    entity.name,
                    attrs.get("region_name"),
                    attrs.get("parent_region_name"),
                    attrs.get("district"),
                    attrs.get("admin_name"),
                    *(item.get("name") for item in entity.related_nodes or []),
                ])
                if region_id:
                    region_resolution_basis = "unique_formal_name_match"
            resolution = self._resolution_level(attrs, category, subtype, entity.labels)
            has_coordinates = attrs.get("lat") is not None and (
                attrs.get("lon") is not None or attrs.get("lng") is not None
            )
            spatial_precision = str(attrs.get("spatial_precision") or "").strip()
            if not spatial_precision:
                spatial_precision = (
                    "exact"
                    if has_coordinates and source_kind == "observed"
                    else "site_approximate"
                    if has_coordinates
                    else "area_only"
                )
            evidence_grade = (
                "formal"
                if source_kind == "observed"
                else "contextual"
                if source_kind == "detected"
                else "reference_only"
                if source_kind in _REFERENCE_SOURCE_KINDS
                else "synthetic"
            )
            capacity_hints = {}
            for key in ("capacity", "beds", "population", "service_capacity", "throughput"):
                try:
                    if attrs.get(key) is not None:
                        capacity_hints[key] = float(attrs[key])
                except (TypeError, ValueError):
                    continue
            anchor_id = _stable_id("anchor", entity.uuid, source_kind, resolution)
            anchors.append({
                "anchor_id": anchor_id,
                "entity_id": str(entity.uuid or ""),
                "spatial_feature_ref": _artifact_ref(str(entity.uuid or anchor_id), "spatial-evidence-feature.v2"),
                "display_name_zh": self._display_name(entity.name, "空间证据节点"),
                "region_id": region_id,
                "region_resolution_status": "resolved" if region_id else "unresolved",
                "region_resolution_basis": region_resolution_basis or "unresolved",
                "resolution_level": resolution,
                "supported_role_keys": role_keys,
                "source_kind": source_kind,
                "evidence_grade": evidence_grade,
                "spatial_precision": spatial_precision,
                "evidence_refs": [f"entity:{entity.uuid}"],
                "capacity_hints": capacity_hints,
                "entity_type": str(entity.get_entity_type() or "Entity"),
                "category": category,
                "subtype": subtype,
                "confidence": 0.9 if source_kind == "observed" else 0.72 if source_kind == "detected" else 0.45,
            })
        return anchors

    @staticmethod
    def _build_region_reference_index(
        *,
        anchors: Sequence[Mapping[str, Any]],
        regions: Sequence[RegionNode],
        subregions: Sequence[RegionNode],
    ) -> Dict[str, str]:
        index: Dict[str, str] = {}

        def register(alias: Any, region_id: Any) -> None:
            key = str(alias or "").strip()
            resolved = str(region_id or "").strip()
            if not key or not resolved:
                return
            index.setdefault(key, resolved)
            index.setdefault(key.lower(), resolved)

        for region in [*regions, *subregions]:
            register(region.region_id, region.region_id)
            register(region.name, region.region_id)
        for anchor in anchors:
            region_id = anchor.get("region_id")
            register(anchor.get("anchor_id"), region_id)
            register(anchor.get("entity_id"), region_id)
            register(anchor.get("display_name_zh"), region_id)
            if anchor.get("entity_id"):
                register(f"entity:{anchor.get('entity_id')}", region_id)
        return index

    @classmethod
    def _resolve_region_refs(
        cls,
        values: Iterable[Any],
        index: Mapping[str, str],
    ) -> Tuple[List[str], List[str]]:
        resolved: List[str] = []
        unresolved: List[str] = []
        for raw in _strings(values):
            candidates = [raw, raw.lower()]
            if "::" in raw:
                candidates.extend([raw.split("::", 1)[0], raw.split("::", 1)[0].lower()])
            region_id = next((str(index[item]) for item in candidates if item in index), "")
            if region_id:
                if region_id not in resolved:
                    resolved.append(region_id)
            elif raw not in unresolved:
                unresolved.append(raw)
        return resolved, unresolved

    @classmethod
    def _normalize_role_region_refs(
        cls,
        role_demands: Sequence[Mapping[str, Any]],
        index: Mapping[str, str],
        *,
        scene_scope_refs: Sequence[str] = (),
        default_region_ids: Sequence[str] = (),
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        scope_ref_set = set(_strings(scene_scope_refs))
        default_regions = _strings(default_region_ids)
        for raw in role_demands or []:
            item = copy.deepcopy(dict(raw))
            jurisdiction_raw = _strings(item.get("jurisdiction_region_ids") or [])
            affected_raw = _strings(
                item.get("affected_region_ids") or jurisdiction_raw
            )
            jurisdiction, unresolved_jurisdiction = cls._resolve_region_refs(
                jurisdiction_raw,
                index,
            )
            affected, unresolved_affected = cls._resolve_region_refs(
                affected_raw,
                index,
            )
            fallback_refs = _strings([
                *unresolved_jurisdiction,
                *unresolved_affected,
            ])
            if (
                not jurisdiction
                and fallback_refs
                and default_regions
                and set(fallback_refs).issubset(scope_ref_set)
            ):
                jurisdiction = list(default_regions)
                affected = list(default_regions)
                unresolved_jurisdiction = []
                unresolved_affected = []
                item["region_resolution_source"] = "scene_default_scope"
                item["scene_scope_fallback_refs"] = fallback_refs
            item["jurisdiction_region_ids"] = jurisdiction
            item["affected_region_ids"] = affected or jurisdiction
            item["unresolved_region_refs"] = _strings(
                [*unresolved_jurisdiction, *unresolved_affected]
            )
            normalized.append(item)
        return normalized

    @classmethod
    def _normalize_policy_region_refs(
        cls,
        policy_plan: Sequence[Mapping[str, Any]],
        index: Mapping[str, str],
        *,
        scene_scope_refs: Sequence[str] = (),
        default_region_ids: Sequence[str] = (),
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        scope_ref_set = set(_strings(scene_scope_refs))
        default_regions = _strings(default_region_ids)
        for raw in policy_plan or []:
            item = copy.deepcopy(dict(raw))
            target_regions, unresolved = cls._resolve_region_refs(
                item.get("target_region_ids") or [],
                index,
            )
            if (
                not target_regions
                and unresolved
                and default_regions
                and set(unresolved).issubset(scope_ref_set)
            ):
                item["scene_scope_fallback_refs"] = list(unresolved)
                item["target_region_resolution_source"] = "scene_default_scope"
                target_regions = list(default_regions)
                unresolved = []
            item["target_region_ids"] = target_regions
            item["unresolved_target_region_refs"] = unresolved
            normalized.append(item)
        return normalized

    @classmethod
    def _normalize_profile_region_refs(
        cls,
        profile: EnvAgentProfile,
        index: Mapping[str, str],
    ) -> None:
        resolved, _ = cls._resolve_region_refs(
            [
                profile.home_region_id,
                profile.primary_region,
                profile.home_subregion_id,
                *(profile.coverage_region_ids or []),
                *(profile.influenced_regions or []),
            ],
            index,
        )
        primary_candidates, _ = cls._resolve_region_refs(
            [profile.home_region_id, profile.primary_region],
            index,
        )
        primary_region = next(iter(primary_candidates or resolved), "")
        profile.primary_region = primary_region
        profile.home_region_id = primary_region
        profile.coverage_region_ids = list(resolved)
        profile.influenced_regions = list(resolved)
        subregions, _ = cls._resolve_region_refs([profile.home_subregion_id], index)
        profile.home_subregion_id = subregions[0] if subregions else ""

    def _best_candidate(
        self,
        *,
        demand: Mapping[str, Any],
        target_region: str,
        profiles: Sequence[EnvAgentProfile],
        profile_archetypes: Sequence[str],
        anchors: Sequence[Mapping[str, Any]],
        selected_indices: Sequence[int],
    ) -> Tuple[Optional[int], float, Optional[Dict[str, Any]]]:
        expected = archetype_for_demand(demand)
        best: Tuple[Optional[int], float, Optional[Dict[str, Any]]] = (None, -1.0, None)
        for index, profile in enumerate(profiles):
            profile_dict = profile.to_dict()
            archetype_key = profile_archetypes[index]
            if archetype_key != expected:
                continue
            anchor = self._profile_anchor(profile_dict, demand, anchors)
            if demand.get("representation_requirement") in {"facility_required", "subunit_required"} and (
                anchor is None or not anchor.get("region_id")
            ):
                continue
            profile_regions = set(_strings([
                profile.primary_region,
                profile.home_region_id,
                profile.home_subregion_id,
                *(profile.influenced_regions or []),
            ]))
            score = 52.0
            required = set(demand.get("required_capabilities") or [])
            available = set(profile.capability_keys or []) | set(get_agent_archetype(archetype_key)["capabilities"])
            score += min(22.0, len(required.intersection(available)) * 5.5)
            if target_region:
                score += 16.0 if target_region in profile_regions else -18.0
            if anchor:
                score += 12.0 if anchor.get("evidence_grade") == "formal" else 7.0
            score += _bounded_probability(profile.evidence_confidence, 0.5) * 8.0
            if index in selected_indices:
                score += 4.0
            if score > best[1]:
                best = (index, score, dict(anchor) if anchor else None)
        return best

    def _best_selected_profile(
        self,
        *,
        demand: Mapping[str, Any],
        target_region: str,
        selected_profiles: Sequence[EnvAgentProfile],
        anchors: Sequence[Mapping[str, Any]],
    ) -> Tuple[Optional[EnvAgentProfile], float, Optional[Dict[str, Any]]]:
        expected = archetype_for_demand(demand)
        representation = str(demand.get("representation_requirement") or "")
        ranked: List[Tuple[float, EnvAgentProfile, Optional[Dict[str, Any]]]] = []
        for profile in selected_profiles:
            if profile.archetype_key != expected:
                continue
            profile_regions = set(_strings([
                profile.primary_region,
                profile.home_region_id,
                *profile.coverage_region_ids,
            ]))
            if target_region and profile_regions and target_region not in profile_regions:
                continue
            anchor = self._profile_anchor(profile.to_dict(), demand, anchors)
            if representation in {"facility_required", "subunit_required"} and (
                anchor is None or not anchor.get("region_id")
            ):
                continue
            required = set(demand.get("required_capabilities") or [])
            available = set(profile.capability_keys or []) | set(
                get_agent_archetype(expected)["capabilities"]
            )
            score = 72.0 + min(18.0, len(required.intersection(available)) * 4.5)
            if anchor:
                score += 8.0
            ranked.append((score, profile, dict(anchor) if anchor else None))
        if not ranked:
            return None, -1.0, None
        score, profile, anchor = max(ranked, key=lambda item: item[0])
        return profile, score, anchor

    def _best_anchor(
        self,
        demand: Mapping[str, Any],
        target_region: str,
        anchors: Sequence[Mapping[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        representation = str(demand.get("representation_requirement") or "")
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for raw in anchors:
            anchor = dict(raw)
            if str(demand.get("role_key") or "") not in anchor.get("supported_role_keys", []):
                continue
            if representation in {"facility_required", "subunit_required"}:
                if anchor.get("resolution_level") not in {"R3", "R4"}:
                    continue
                if anchor.get("source_kind") not in _FORMAL_SOURCE_KINDS:
                    continue
                if not anchor.get("region_id"):
                    continue
            if anchor.get("evidence_grade") in {"reference_only", "synthetic"}:
                continue
            score = 60.0
            if target_region and anchor.get("region_id") == target_region:
                score += 20.0
            if anchor.get("evidence_grade") == "formal":
                score += 12.0
            score += float(anchor.get("confidence") or 0.0) * 8.0
            ranked.append((score, anchor))
        return max(ranked, key=lambda item: item[0])[1] if ranked else None

    def _profile_anchor(
        self,
        profile: Mapping[str, Any],
        demand: Mapping[str, Any],
        anchors: Sequence[Mapping[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        source_entity = str(profile.get("source_entity_uuid") or "")
        evidence_refs = " ".join(_strings(profile.get("evidence_refs") or [])).lower()
        profile_name = str(profile.get("name") or "").lower()
        candidates = []
        for raw in anchors:
            anchor = dict(raw)
            if str(demand.get("role_key") or "") not in anchor.get("supported_role_keys", []):
                continue
            entity_id = str(anchor.get("entity_id") or "")
            anchor_name = str(anchor.get("display_name_zh") or "").lower()
            matches = (
                source_entity == entity_id
                or (entity_id and entity_id.lower() in evidence_refs)
                or (anchor_name and anchor_name in profile_name)
            )
            if matches and anchor.get("source_kind") in _FORMAL_SOURCE_KINDS:
                candidates.append(anchor)
        return candidates[0] if candidates else None

    def _profile_from_anchor(
        self,
        *,
        demand: Mapping[str, Any],
        target_region: str,
        anchor: Mapping[str, Any],
        archetype_key: str,
        regions: Sequence[RegionNode],
    ) -> EnvAgentProfile:
        archetype = get_agent_archetype(archetype_key)
        region_id = target_region or str(anchor.get("region_id") or "") or (regions[0].region_id if regions else "")
        name = self._instance_name(archetype_key, str(anchor.get("display_name_zh") or ""), region_id, regions)
        confidence = _bounded_probability(anchor.get("confidence"), 0.7)
        return EnvAgentProfile(
            agent_id=-1,
            username="pending_agent",
            name=name,
            node_family=archetype["node_family"],
            role_type=str(demand.get("role_key") or archetype_key),
            bio=f"该主体依据{anchor.get('display_name_zh') or '正式空间证据'}建立，用于覆盖{demand.get('label_zh') or archetype['label_zh']}。",
            persona=f"该主体仅在已绑定区域和证据支持的能力、权限与资源范围内行动。",
            profession=archetype["label_zh"],
            primary_region=region_id,
            agent_type=archetype["agent_type"],
            agent_subtype=archetype["agent_subtype"],
            archetype_key=archetype_key,
            home_region_id=region_id,
            influenced_regions=[region_id] if region_id else [],
            goals=[f"履行{demand.get('label_zh') or archetype['label_zh']}职责"],
            sensitivities=list(archetype["observable_state_keys"][:4]),
            motivation_stack=["完成场景角色职责", "降低能力缺口"],
            capabilities=list(archetype["capability_labels_zh"]),
            constraints=list(archetype["decision_constraints_zh"]),
            action_space=list(archetype["available_action_keys"]),
            decision_policy={"policy_key": "capability_permission_resource_validated"},
            impact_profile={"panic_delta": 0.0, "trust_delta": 0.0, "economic_delta": 0.0, "ecology_delta": 0.0},
            stance_profile={"risk_aversion": 0.7, "cooperation": 0.65},
            resource_budget=dict(archetype["default_resources"]),
            spawn_weight=0.5,
            is_synthesized=True,
            state_vector=default_state_vector("disaster_mode", archetype["node_family"]),
            source_entity_uuid=str(anchor.get("entity_id") or "") or None,
            source_entity_type=str(anchor.get("entity_type") or "") or None,
            generation_mode="prepare_planned",
            evidence_refs=_strings(anchor.get("evidence_refs") or []),
            evidence_confidence=confidence,
            review_status="agent_plan_v2_anchored",
            grounding_reason="由角色需求与正式空间锚点匹配建立。",
        )

    def _aggregate_profile(
        self,
        *,
        demand: Mapping[str, Any],
        target_region: str,
        archetype_key: str,
        regions: Sequence[RegionNode],
    ) -> EnvAgentProfile:
        archetype = get_agent_archetype(archetype_key)
        region_id = target_region or (regions[0].region_id if regions else "")
        region_name = self._region_name(region_id, regions)
        name = f"{region_name}{archetype['label_zh']}" if region_name else archetype["label_zh"]
        return EnvAgentProfile(
            agent_id=-1,
            username="pending_agent",
            name=name,
            node_family=archetype["node_family"],
            role_type=str(demand.get("role_key") or archetype_key),
            bio=f"该主体代表{region_name or '当前区域'}范围内的{archetype['label_zh']}，不对应未经证实的具体机构。",
            persona="该聚合主体以区域级能力和资源区间参与推演，不宣称具体机构身份。",
            profession=archetype["label_zh"],
            primary_region=region_id,
            agent_type=archetype["agent_type"],
            agent_subtype=archetype["agent_subtype"],
            archetype_key=archetype_key,
            home_region_id=region_id,
            influenced_regions=[region_id] if region_id else [],
            goals=[f"覆盖{region_name or '区域'}的{demand.get('label_zh') or archetype['label_zh']}需求"],
            sensitivities=list(archetype["observable_state_keys"][:4]),
            motivation_stack=["维持区域服务连续性", "报告能力缺口"],
            capabilities=list(archetype["capability_labels_zh"]),
            constraints=[*archetype["decision_constraints_zh"], "区域聚合主体不等同于具体真实机构"],
            action_space=list(archetype["available_action_keys"]),
            decision_policy={"policy_key": "aggregate_capability_bounded"},
            impact_profile={"panic_delta": 0.0, "trust_delta": 0.0, "economic_delta": 0.0, "ecology_delta": 0.0},
            stance_profile={"risk_aversion": 0.65, "cooperation": 0.65},
            resource_budget=dict(archetype["default_resources"]),
            spawn_weight=0.45,
            is_synthesized=True,
            state_vector=default_state_vector("disaster_mode", archetype["node_family"]),
            generation_mode="prepare_planned",
            evidence_refs=_strings([
                *(demand.get("source_refs") or []),
                f"region:{region_id}" if region_id else "",
            ]),
            evidence_confidence=0.58,
            review_status="agent_plan_v2_area_aggregate",
            grounding_reason="缺少具体设施证据，按角色合同建立区域聚合主体。",
        )

    def _apply_demand_to_profile(
        self,
        *,
        profile: EnvAgentProfile,
        demand: Mapping[str, Any],
        archetype_key: str,
        anchor: Optional[Mapping[str, Any]],
        target_region: str,
        planning_input_ref: Mapping[str, Any],
    ) -> None:
        archetype = get_agent_archetype(archetype_key)
        profile.archetype_key = archetype_key
        profile.node_family = str(archetype["node_family"])
        profile.agent_type = str(archetype["agent_type"])
        profile.agent_subtype = str(archetype["agent_subtype"])
        profile.role_type = str(demand.get("role_key") or archetype_key)
        profile.profession = str(archetype["label_zh"])
        profile.capability_keys = _strings([
            *(profile.capability_keys or []),
            *(demand.get("required_capabilities") or []),
        ])
        profile.capabilities = _strings([
            *(profile.capabilities or []),
            *archetype["capability_labels_zh"],
        ])
        profile.permission_keys = _strings([
            *(profile.permission_keys or []),
            *(demand.get("required_permissions") or []),
        ])
        profile.resource_types = _strings([
            *(profile.resource_types or []),
            *(demand.get("required_resource_types") or []),
        ])
        profile.action_space = _strings([
            *(profile.action_space or []),
            *archetype["available_action_keys"],
        ])
        profile.action_space_zh = _strings([
            *(profile.action_space_zh or []),
            *archetype["available_action_labels_zh"],
        ])
        profile.resource_budget = {
            **dict(archetype["default_resources"]),
            **dict(profile.resource_budget or {}),
        }
        profile.constraints = _strings([
            *(profile.constraints or []),
            *archetype["decision_constraints_zh"],
        ])
        profile.role_demand_refs = _strings([
            *(profile.role_demand_refs or []),
            demand.get("role_demand_id"),
        ])
        region_id = (
            target_region
            or str((anchor or {}).get("region_id") or "")
            or profile.home_region_id
            or profile.primary_region
        )
        profile.primary_region = region_id
        profile.home_region_id = region_id
        profile.coverage_region_ids = _strings([
            *(profile.coverage_region_ids or []),
            region_id,
            *(demand.get("affected_region_ids") or []),
        ])
        profile.influenced_regions = _strings([
            *(profile.influenced_regions or []),
            *profile.coverage_region_ids,
        ])
        if anchor:
            profile.spatial_anchor_refs = _strings([
                *(profile.spatial_anchor_refs or []),
                anchor.get("anchor_id"),
            ])
            profile.represented_entity_ids = _strings([
                *(profile.represented_entity_ids or []),
                anchor.get("entity_id"),
            ])
            profile.spatial_precision = str(anchor.get("spatial_precision") or "site_approximate")
        elif not profile.spatial_precision:
            profile.spatial_precision = "area_only"
        representation = str(demand.get("representation_requirement") or "aggregate_allowed")
        if representation == "subunit_required":
            profile.representation_level = "subunit"
        elif representation == "facility_required":
            profile.representation_level = "facility"
        elif archetype_key in {"affected_population", "livelihood_group", "ecological_receptor"}:
            profile.representation_level = "group_representative"
        elif anchor:
            profile.representation_level = "institution"
        else:
            profile.representation_level = "region_aggregate"
        profile.is_aggregate = profile.representation_level in {"region_aggregate", "group_representative"}
        profile.aggregation_weight = max(0.01, float(profile.aggregation_weight or 1.0))
        ratio = float(archetype.get("default_uncertainty_ratio") or 0.2)
        profile.resource_uncertainty = {
            key: [
                round(max(0.0, float(value) * (1.0 - ratio)), 3),
                round(float(value) * (1.0 + ratio), 3),
            ]
            for key, value in profile.resource_budget.items()
            if isinstance(value, (int, float))
        }
        activation_round = max(0, int(demand.get("activation_round_hint") or 0))
        lifecycle_status = "dormant" if activation_round > 1 else "active"
        profile.lifecycle_status = lifecycle_status
        profile.activation_round = activation_round if lifecycle_status == "dormant" else 0
        profile.activation_triggers = [
            {
                "trigger_type": "event_or_mechanism_activation",
                "event_ids": list(demand.get("caused_by_event_ids") or []),
                "mechanism_edge_ids": list(demand.get("caused_by_mechanism_ids") or []),
                "earliest_round": activation_round,
            }
        ]
        profile.created_round = 0
        profile.scenario_version_ref = _artifact_ref(
            str(planning_input_ref.get("planning_input_id") or ""),
            str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
            str(planning_input_ref.get("content_hash") or ""),
        )
        profile.profile_confidence = max(
            _bounded_probability(profile.profile_confidence, 0.0),
            _bounded_probability(profile.evidence_confidence, 0.58),
        )
        profile.generation_reason = str(demand.get("rationale_zh") or profile.grounding_reason)
        profile.generation_mode = "prepare_planned"
        profile.runtime_lifecycle = {
            **dict(profile.runtime_lifecycle or {}),
            "lifecycle_status": lifecycle_status,
            "created_round": 0,
            "activation_round": profile.activation_round,
            "resolution_mode": "prepare_planned",
            "is_aggregate": bool(profile.is_aggregate),
        }

    def _build_relationships(
        self,
        *,
        profiles: Sequence[EnvAgentProfile],
        role_demands: Sequence[Mapping[str, Any]],
        per_agent_limit: int,
    ) -> List[AgentRelationshipEdge]:
        demand_index = {
            str(item.get("role_demand_id") or ""): dict(item)
            for item in role_demands
        }
        by_archetype: Dict[str, List[EnvAgentProfile]] = {}
        for profile in profiles:
            by_archetype.setdefault(profile.archetype_key, []).append(profile)
        degree: Dict[int, int] = {profile.agent_id: 0 for profile in profiles}
        edges: List[AgentRelationshipEdge] = []
        seen: set[str] = set()
        for rule in self._RELATION_RULES:
            sources = by_archetype.get(rule["source"], [])
            targets = by_archetype.get(rule["target"], [])
            for source in sources:
                ranked_targets = sorted(
                    [item for item in targets if item.agent_id != source.agent_id],
                    key=lambda item: (
                        0 if item.primary_region == source.primary_region else 1,
                        item.agent_id,
                    ),
                )
                for target in ranked_targets[:2]:
                    if degree[source.agent_id] >= per_agent_limit or degree[target.agent_id] >= per_agent_limit:
                        continue
                    key = f"{source.agent_id}:{target.agent_id}:{rule['type']}"
                    if key in seen:
                        continue
                    mechanism_ids = _strings(
                        mechanism_id
                        for ref in [*source.role_demand_refs, *target.role_demand_refs]
                        for mechanism_id in demand_index.get(ref, {}).get("caused_by_mechanism_ids") or []
                    )
                    if not mechanism_ids:
                        continue
                    evidence_refs = _strings([
                        *(source.evidence_refs or []),
                        *(target.evidence_refs or []),
                        *(f"role_demand:{item}" for item in [*source.role_demand_refs, *target.role_demand_refs]),
                    ])
                    confidence = round(
                        min(
                            _bounded_probability(source.profile_confidence or source.evidence_confidence, 0.58),
                            _bounded_probability(target.profile_confidence or target.evidence_confidence, 0.58),
                        ),
                        3,
                    )
                    edge_id = _stable_id("relationship_contract", key, mechanism_ids)
                    edges.append(AgentRelationshipEdge(
                        edge_id=edge_id,
                        source_agent_id=source.agent_id,
                        target_agent_id=target.agent_id,
                        relation_type=str(rule["type"]),
                        strength=round((float(rule["trust"]) + float(rule["coordination"])) / 2, 3),
                        interaction_channel="institutional",
                        rationale=f"由角色需求、能力边界和机制边共同建立：{rule['label_zh']}。",
                        source_region_id=source.primary_region,
                        target_region_id=target.primary_region,
                        relation_label=str(rule["label_zh"]),
                        mechanism=str(rule["label_zh"]),
                        trigger_conditions=[str(rule["trigger_zh"])],
                        latency="1轮",
                        direction="directed",
                        scope="same_region" if source.primary_region == target.primary_region else "cross_region",
                        evidence=evidence_refs,
                        confidence=confidence,
                        mechanism_edge_ids=mechanism_ids,
                        origin="role_demand_contract",
                        validation_status="agent_plan_v2_validated",
                        epistemic_status="inferred",
                        evidence_anchors=evidence_refs,
                        relationship_contract_id=edge_id,
                        contract_version="relationship-contract.v2",
                        initial_trust=float(rule["trust"]),
                        initial_dependency=float(rule["dependency"]),
                        initial_coordination=float(rule["coordination"]),
                        source_role_demand_refs=list(source.role_demand_refs),
                        target_role_demand_refs=list(target.role_demand_refs),
                    ))
                    seen.add(key)
                    degree[source.agent_id] += 1
                    degree[target.agent_id] += 1
        return edges

    def _placement_plan(
        self,
        *,
        placements: Sequence[Mapping[str, Any]],
        role_coverage: Sequence[Mapping[str, Any]],
        unresolved_demands: Sequence[Mapping[str, Any]],
        planning_input_ref: Mapping[str, Any],
        effort: Mapping[str, Any],
    ) -> Dict[str, Any]:
        payload = {
            "contract_version": PLACEMENT_PLAN_CONTRACT_VERSION,
            "scenario_planning_ref": _artifact_ref(
                str(planning_input_ref.get("planning_input_id") or ""),
                str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                str(planning_input_ref.get("content_hash") or ""),
            ),
            "effort_snapshot_ref": _artifact_ref(
                str(effort.get("effort_snapshot_id") or ""),
                str(effort.get("profile_version") or ""),
                str(effort.get("content_hash") or ""),
            ),
            "placements": [dict(item) for item in placements],
            "role_coverage": [dict(item) for item in role_coverage],
            "unresolved_demands": [dict(item) for item in unresolved_demands],
            "objective_zh": "在证据和预算内覆盖高优先级角色，同时避免无证据具体化与重复 Agent。",
        }
        payload["placement_plan_id"] = _stable_id("agent_placement_plan", payload)
        payload["content_hash"] = _content_hash(payload)
        return payload

    def _resolution_plan(
        self,
        *,
        anchors: Sequence[Mapping[str, Any]],
        placements: Sequence[Mapping[str, Any]],
        role_coverage: Sequence[Mapping[str, Any]],
        unresolved_demands: Sequence[Mapping[str, Any]],
        planning_input_ref: Mapping[str, Any],
        effort: Mapping[str, Any],
    ) -> Dict[str, Any]:
        selected_anchor_ids = {
            str(ref.get("artifact_id") or "")
            for placement in placements
            for ref in placement.get("spatial_anchor_refs") or []
            if isinstance(ref, Mapping)
        }
        payload = {
            "contract_version": RESOLUTION_PLAN_CONTRACT_VERSION,
            "scenario_planning_ref": _artifact_ref(
                str(planning_input_ref.get("planning_input_id") or ""),
                str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                str(planning_input_ref.get("content_hash") or ""),
            ),
            "effort_snapshot_ref": _artifact_ref(
                str(effort.get("effort_snapshot_id") or ""),
                str(effort.get("profile_version") or ""),
                str(effort.get("content_hash") or ""),
            ),
            "coverage_units": [
                {
                    "anchor_id": item.get("anchor_id"),
                    "region_id": item.get("region_id"),
                    "resolution_level": item.get("resolution_level"),
                    "display_name_zh": item.get("display_name_zh"),
                    "selected_for_agent_plan": item.get("anchor_id") in selected_anchor_ids,
                }
                for item in anchors
            ],
            "refinement_decisions": [
                {
                    "anchor_id": item.get("anchor_id"),
                    "decision": "retain",
                    "reason_zh": "该空间锚点被角色需求匹配使用。",
                }
                for item in anchors
                if item.get("anchor_id") in selected_anchor_ids
            ],
            "role_resolution_requirements": [dict(item) for item in role_coverage],
            "unresolved_evidence_gaps": [dict(item) for item in unresolved_demands],
            "estimated_cost": {
                "selected_anchor_count": len(selected_anchor_ids),
                "placement_count": len(placements),
                "effort_level": effort.get("effort_level"),
            },
            "stop_conditions": [
                "达到当前分析强度 Agent 上限",
                "没有更多满足证据门槛的空间锚点",
                "所有 critical 和 high 角色均已覆盖或明确记录缺口",
            ],
        }
        payload["resolution_plan_id"] = _stable_id("resolution_plan", payload)
        payload["content_hash"] = _content_hash(payload)
        return payload

    def _agent_plan(
        self,
        *,
        profiles: Sequence[EnvAgentProfile],
        relationships: Sequence[AgentRelationshipEdge],
        role_coverage: Sequence[Mapping[str, Any]],
        unresolved_demands: Sequence[Mapping[str, Any]],
        demands: Sequence[Mapping[str, Any]],
        placement_plan: Mapping[str, Any],
        resolution_plan: Mapping[str, Any],
        policy_execution_plan: Mapping[str, Any],
        planning_input_ref: Mapping[str, Any],
        effort: Mapping[str, Any],
        candidate_count: int,
        created_from_anchor: int,
        created_as_aggregate: int,
        planned_agent_limit: int,
    ) -> Dict[str, Any]:
        planned = [item.to_dict() for item in profiles if item.lifecycle_status != "dormant"]
        dormant = [item.to_dict() for item in profiles if item.lifecycle_status == "dormant"]
        relationship_demands = [
            {
                "relationship_contract_id": item.edge_id,
                "source_agent_id": item.source_agent_id,
                "target_agent_id": item.target_agent_id,
                "relationship_type": item.relation_type,
                "mechanism_edge_ids": list(item.mechanism_edge_ids),
                "evidence_refs": list(item.evidence_anchors),
            }
            for item in relationships
        ]
        payload = {
            "contract_version": AGENT_PLAN_CONTRACT_VERSION,
            "archetype_contract_version": AGENT_ARCHETYPE_CONTRACT_VERSION,
            "scenario_planning_ref": _artifact_ref(
                str(planning_input_ref.get("planning_input_id") or ""),
                str(planning_input_ref.get("contract_version") or "scenario_planning.v2"),
                str(planning_input_ref.get("content_hash") or ""),
            ),
            "resolution_plan_ref": _artifact_ref(
                str(resolution_plan.get("resolution_plan_id") or ""),
                RESOLUTION_PLAN_CONTRACT_VERSION,
                str(resolution_plan.get("content_hash") or ""),
            ),
            "placement_plan_ref": _artifact_ref(
                str(placement_plan.get("placement_plan_id") or ""),
                PLACEMENT_PLAN_CONTRACT_VERSION,
                str(placement_plan.get("content_hash") or ""),
            ),
            "policy_execution_plan_ref": _artifact_ref(
                str(policy_execution_plan.get("policy_execution_plan_id") or ""),
                str(policy_execution_plan.get("contract_version") or ""),
                str(policy_execution_plan.get("content_hash") or ""),
            ),
            "effort_snapshot_ref": _artifact_ref(
                str(effort.get("effort_snapshot_id") or ""),
                str(effort.get("profile_version") or ""),
                str(effort.get("content_hash") or ""),
            ),
            "role_demands": [dict(item) for item in demands],
            "planned_agents": planned,
            "dormant_agents": dormant,
            "role_coverage": [dict(item) for item in role_coverage],
            "unresolved_demands": [dict(item) for item in unresolved_demands],
            "relationship_demands": relationship_demands,
            "generation_audit": {
                "source": "agent_v2",
                "candidate_profile_count": candidate_count,
                "selected_agent_count": len(profiles),
                "created_from_anchor_count": created_from_anchor,
                "created_as_region_aggregate_count": created_as_aggregate,
                "planned_agent_limit": planned_agent_limit,
                "target_agent_count_used": False,
                "resource_unit": "normalized_relative_capacity_0_100",
                "critical_high_demands_accounted_for": all(
                    item.get("status") in {"covered", "partial", "unresolved"}
                    for item in role_coverage
                    if item.get("priority") in {"critical", "high"}
                ),
            },
        }
        payload["agent_plan_id"] = _stable_id("agent_plan", payload)
        payload["content_hash"] = _content_hash(payload)
        return payload

    @staticmethod
    def _demand_slots(demand: Mapping[str, Any]) -> List[str]:
        regions = _strings(demand.get("jurisdiction_region_ids") or [])
        if demand.get("multiplicity_rule") == "per_region" and regions:
            return regions
        return [regions[0] if regions else ""]

    @staticmethod
    def _multiplicity(role_key: str, required_resolution: str) -> str:
        if role_key in {"affected_population", "fisheries_stakeholders"}:
            return "per_region"
        if role_key in {"emergency_medical_response", "healthcare_capacity_coordination", "critical_facility_operator"}:
            return "per_independent_capacity"
        if required_resolution in {"environmental_carrier", "ecological_receptor"}:
            return "adaptive"
        return "single"

    @staticmethod
    def _evidence_requirements(representation: str, archetype_key: str) -> List[str]:
        if representation in {"facility_required", "subunit_required"}:
            return ["正式设施或内部单元空间证据", "角色与设施类型匹配证据"]
        if archetype_key in {"local_government", "industry_regulator"}:
            return ["行政管辖或法定职责证据"]
        return ["机制需求引用", "区域或群体范围证据"]

    @staticmethod
    def _aggregate_allowed(demand: Mapping[str, Any], target_region: str = "") -> bool:
        representation = str(demand.get("representation_requirement") or "")
        if representation == "aggregate_allowed":
            return True
        # A resolved region can support a bounded capability aggregate without
        # claiming that a specific real institution exists. Facility and
        # subunit demands still require concrete evidence.
        return representation == "institution_required" and bool(str(target_region or "").strip())

    @staticmethod
    def _resolution_level(
        attrs: Mapping[str, Any],
        category: str,
        subtype: str,
        labels: Sequence[str],
    ) -> str:
        raw = attrs.get("spatial_level")
        if isinstance(raw, str) and raw.upper() in {"R0", "R1", "R2", "R3", "R4"}:
            return raw.upper()
        try:
            if raw is not None:
                return f"R{max(0, min(4, int(raw)))}"
        except (TypeError, ValueError):
            pass
        label_text = " ".join(str(item).lower() for item in labels)
        if category == "region" or "区域" in label_text:
            return "R1"
        if category == "facility" or subtype in {
            "hospital", "clinic", "power_plant", "nuclear_power_plant",
            "wastewater_plant", "monitoring_station", "shelter",
        }:
            return "R3"
        if category == "human_proxy":
            return "R2"
        return "R2"

    @staticmethod
    def _supported_role_keys(
        name: str,
        labels: Sequence[str],
        category: str,
        subtype: str,
    ) -> List[str]:
        text = " ".join([name, category, subtype, *labels]).lower()
        roles: List[str] = []
        if any(token in text for token in ("核电", "nuclear", "power_plant", "电厂", "工业设施", "factory", "plant")):
            roles.append("critical_facility_operator")
        if any(token in text for token in ("医院", "医疗", "hospital", "clinic", "health")):
            roles.extend(["emergency_medical_response", "healthcare_capacity_coordination"])
        if any(token in text for token in ("监测", "气象", "水文", "实验室", "monitor", "weather", "laboratory")):
            roles.extend(["hazard_monitoring", "environmental_monitoring", "geological_emergency_monitoring"])
        if any(token in text for token in ("监管", "监察", "regulator", "safety", "government")):
            roles.extend(["nuclear_safety_regulator", "public_emergency_command", "policy_execution"])
        if any(token in text for token in ("道路", "交通", "港口", "机场", "road", "transport", "port", "airport")):
            roles.append("transport_continuity")
        if any(token in text for token in ("仓库", "物流", "物资", "warehouse", "logistics", "supply")):
            roles.append("critical_supply_coordination")
        if any(token in text for token in ("居民", "社区", "住宅", "resident", "community", "residential")):
            roles.extend(["affected_population", "community_coordination"])
        if any(token in text for token in ("渔", "农业", "农田", "fish", "farm", "agriculture")):
            roles.append("fisheries_stakeholders")
        if any(token in text for token in ("媒体", "新闻", "media", "news")):
            roles.append("public_information")
        if category in {"water", "weather"} or any(token in text for token in ("水体", "河流", "海湾", "current", "runoff")):
            roles.append("environmental_carrier")
        if category == "ecology" or any(token in text for token in ("生态", "湿地", "物种", "habitat", "species", "wetland")):
            roles.append("ecological_receptor")
        return _strings(roles)

    @staticmethod
    def _display_name(value: Any, fallback: str) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        return text if re.search(r"[\u3400-\u9fff]", text) else fallback

    @staticmethod
    def _region_name(region_id: str, regions: Sequence[RegionNode]) -> str:
        for region in regions:
            if str(region.region_id) == str(region_id):
                return str(region.name or region.region_id)
        return str(region_id or "")

    def _instance_name(
        self,
        archetype_key: str,
        anchor_name: str,
        region_id: str,
        regions: Sequence[RegionNode],
    ) -> str:
        base = anchor_name or self._region_name(region_id, regions) or "场景"
        suffix = {
            "critical_facility_operator": "应急运营主体",
            "healthcare_provider": "医疗应急主体",
            "environmental_monitoring": "监测响应主体",
            "industry_regulator": "安全监管主体",
            "transport_operator": "交通运营主体",
            "supply_logistics": "物资供应主体",
            "affected_population": "受影响居民代表",
            "livelihood_group": "生计群体代表",
            "ecological_receptor": "生态受体",
            "environmental_carrier": "环境传播载体",
        }.get(archetype_key, get_agent_archetype(archetype_key)["label_zh"])
        return f"{base}·{suffix}"

    @staticmethod
    def _username(profile: EnvAgentProfile, agent_id: int) -> str:
        token = _content_hash([
            profile.archetype_key,
            profile.primary_region,
            profile.source_entity_uuid,
            profile.name,
        ])[:10]
        return f"agent_{agent_id}_{token}"


__all__ = [
    "AGENT_PLAN_CONTRACT_VERSION",
    "AgentPlannerV2",
    "AgentPlanningResult",
    "PLACEMENT_PLAN_CONTRACT_VERSION",
    "RESOLUTION_PLAN_CONTRACT_VERSION",
]
