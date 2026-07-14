"""Runtime Agent emergence with evidence gates, lineage, and hard Effort caps."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .effort_contract import effort_operation_limit, normalize_effort_snapshot
from .envfish_models import default_state_vector, normalize_state_vector
from .scenario_planning.agent_archetypes import (
    archetype_for_demand,
    get_agent_archetype,
    infer_profile_archetype,
)


AGENT_EMERGENCE_CONTRACT_VERSION = "agent-emergence.v2"

_CAPABILITY_LABELS = {
    "meteorological_monitoring": "气象监测",
    "coastal_flood_forecasting": "沿海洪涝预测",
    "risk_early_warning": "风险预警",
    "facility_safety_operation": "设施安全运行",
    "emergency_shutdown": "应急停机",
    "cooling_system_recovery": "冷却系统恢复",
    "nuclear_safety_regulation": "核安全监管",
    "radiation_emergency_oversight": "辐射应急监督",
    "regulatory_enforcement": "监管核查",
    "environmental_monitoring": "环境监测",
    "radiation_monitoring": "辐射监测",
    "laboratory_analysis": "实验室分析",
    "data_analysis": "数据研判",
    "emergency_medical_response": "医疗应急响应",
    "radiation_injury_treatment": "辐射损伤救治",
    "patient_transport": "患者转运",
    "emergency_command": "应急指挥",
    "evacuation_coordination": "疏散协调",
    "resource_dispatch": "资源调度",
    "public_information": "公众信息发布",
    "public_risk_response": "公众风险响应",
    "evacuation_participation": "疏散配合",
    "local_information_reporting": "本地信息反馈",
    "hospital_capacity_management": "医院容量管理",
    "patient_triage": "患者分诊",
    "medical_supply_dispatch": "医疗物资调度",
    "traffic_control": "交通管制",
    "evacuation_routing": "疏散路径规划",
    "transport_dispatch": "运力调度",
    "road_clearance": "道路清障",
    "supply_chain_monitoring": "供应链监测",
    "inventory_allocation": "库存分配",
    "logistics_dispatch": "物流调度",
    "emergency_procurement": "应急采购",
    "cross_region_coordination": "跨区域协同",
}

_DEMAND_PROFILE_TOKENS = {
    "hazard_monitoring": {"environment_bureau", "remote_monitor", "meteorological", "气象", "监测", "预警"},
    "geological_emergency_monitoring": {"safety_inspector", "environment_bureau", "地质", "震后", "监测"},
    "critical_facility_operator": {"plant_operator", "facility_operator", "运营方", "核电", "电厂"},
    "nuclear_safety_regulator": {"nuclear_regulator", "核安全", "辐射监管"},
    "environmental_monitoring": {"environment_bureau", "remote_monitor", "research_lab", "环境监测", "辐射监测"},
    "emergency_medical_response": {"hospital", "clinic", "medical", "医院", "医疗", "救治"},
    "public_emergency_command": {"emergency_office", "emergency_command", "应急指挥", "应急协调"},
    "affected_population": {"resident", "community", "居民", "社区"},
    "fisheries_stakeholders": {"field_observer", "fisher", "渔民", "渔业"},
    "healthcare_capacity_coordination": {"hospital", "clinic", "medical", "医院", "医疗", "分诊"},
    "transport_continuity": {"transport_operator", "transport_node", "交通", "运力", "道路"},
    "critical_supply_coordination": {"logistics_operator", "supply", "物流", "供应", "物资"},
    "cross_region_coordination": {"emergency_office", "public_agency", "应急协调", "跨区域协同"},
}


@dataclass
class AgentEmergenceResult:
    actor_profiles: List[Dict[str, Any]]
    state: Dict[str, Any]
    events: List[Dict[str, Any]] = field(default_factory=list)
    lineage: List[Dict[str, Any]] = field(default_factory=list)
    candidate_ledger: List[Dict[str, Any]] = field(default_factory=list)
    created_agent_ids: List[int] = field(default_factory=list)
    split_agent_ids: List[int] = field(default_factory=list)
    activated_agent_ids: List[int] = field(default_factory=list)


class AgentEmergenceDetector:
    """Resolve uncovered runtime role demands without rewriting prior rounds."""

    def evaluate(
        self,
        *,
        current_round: int,
        actor_profiles: Sequence[Mapping[str, Any]],
        effort_snapshot: Mapping[str, Any],
        role_demands: Optional[Sequence[Mapping[str, Any]]] = None,
        runtime_signals: Optional[Mapping[str, Any]] = None,
        previous_state: Optional[Mapping[str, Any]] = None,
    ) -> AgentEmergenceResult:
        round_num = max(0, int(current_round or 0))
        profiles = [copy.deepcopy(dict(item)) for item in actor_profiles if isinstance(item, Mapping)]
        resolved_effort = normalize_effort_snapshot(effort_snapshot)
        total_limit = int(
            effort_operation_limit(
                resolved_effort, "step3", "runtime_agent_total_limit"
            )
        )
        per_round_limit = int(
            effort_operation_limit(
                resolved_effort, "step3", "runtime_agent_per_round_limit"
            )
        )
        previous = dict(previous_state or {})
        previous_candidates = {
            str(key): dict(value)
            for key, value in (previous.get("candidates") or {}).items()
            if isinstance(value, Mapping)
        }
        resolved_signatures = set(_strings(previous.get("resolved_signatures") or []))
        created_or_split_count = int(previous.get("created_or_split_count") or 0)
        next_candidates: Dict[str, Dict[str, Any]] = {}
        events: List[Dict[str, Any]] = []
        lineage: List[Dict[str, Any]] = []
        ledger: List[Dict[str, Any]] = []
        created_ids: List[int] = []
        split_ids: List[int] = []
        activated_ids: List[int] = []
        created_this_round = 0

        demands = self._collect_demands(
            role_demands=role_demands or [],
            runtime_signals=runtime_signals or {},
            round_num=round_num,
        )
        demands.sort(
            key=lambda item: (
                -self._impact_score(item),
                -self._evidence_score(item),
                str(item.get("demand_id") or item.get("demand_key") or ""),
            )
        )

        next_agent_id = self._next_agent_id(profiles)
        for demand in demands:
            signature = self._signature(demand)
            if not signature or signature in resolved_signatures:
                continue
            if self._is_covered(demand, profiles):
                resolved_signatures.add(signature)
                ledger.append(self._ledger_item(demand, signature, "covered", "现有 Agent 已覆盖该能力需求", round_num))
                continue

            if not self._has_runtime_evidence(demand):
                ledger.append(
                    self._ledger_item(
                        demand,
                        signature,
                        "waiting_runtime_evidence",
                        "准备阶段的静态能力缺口尚无新增运行证据，不创建临时 Agent",
                        round_num,
                    )
                )
                continue

            evidence_score = self._evidence_score(demand)
            impact_score = self._impact_score(demand)
            prior = previous_candidates.get(signature) or {}
            consecutive = (
                int(prior.get("consecutive_rounds") or 0) + 1
                if int(prior.get("last_round") or -2) == round_num - 1
                else 1
            )
            candidate = {
                "demand_signature": signature,
                "demand_id": str(demand.get("demand_id") or ""),
                "demand_key": str(demand.get("demand_key") or "runtime_capability_gap"),
                "label_zh": self._label(demand),
                "required_capability_keys": _strings(demand.get("required_capability_keys") or []),
                "jurisdiction_region_ids": _strings(demand.get("jurisdiction_region_ids") or []),
                "evidence_score": evidence_score,
                "impact_score": impact_score,
                "importance": str(demand.get("importance") or "medium"),
                "last_round": round_num,
                "consecutive_rounds": consecutive,
                "source_refs": self._source_refs(demand),
            }
            next_candidates[signature] = candidate
            immediate = (
                str(demand.get("importance") or "").lower() == "critical"
                and evidence_score >= 80
                and impact_score >= 80
            )
            ordinary_ready = consecutive >= 2 and evidence_score >= 60 and impact_score >= 50
            if not immediate and not ordinary_ready:
                reason = (
                    "证据或影响未达到创建门槛"
                    if consecutive >= 2
                    else "普通候选需连续两轮出现"
                )
                ledger.append(self._ledger_item(demand, signature, "pending", reason, round_num))
                continue

            dormant_index = self._matching_dormant_index(demand, profiles)
            if dormant_index is not None:
                activated = profiles[dormant_index]
                lifecycle = dict(activated.get("runtime_lifecycle") or {})
                lifecycle.update(
                    {
                        "lifecycle_status": "pending_activation",
                        "demand_signature": signature,
                        "discovered_round": round_num,
                        "activation_round": round_num + 1,
                        "resolution_mode": "activate_dormant",
                    }
                )
                activated["runtime_lifecycle"] = lifecycle
                activated["lifecycle_status"] = "pending_activation"
                activated["activation_round"] = round_num + 1
                agent_id = int(activated.get("agent_id"))
                activated_ids.append(agent_id)
                resolved_signatures.add(signature)
                events.append(
                    self._event(
                        event_type="agent_reactivated",
                        agent_id=agent_id,
                        demand=demand,
                        signature=signature,
                        round_num=round_num,
                        summary=f"已唤醒休眠 Agent：{activated.get('name') or self._label(demand)}，下一轮开始参与推演。",
                    )
                )
                ledger.append(self._ledger_item(demand, signature, "reactivated", "优先复用休眠 Agent", round_num))
                continue

            if created_or_split_count + created_this_round >= total_limit:
                ledger.append(
                    self._ledger_item(
                        demand,
                        signature,
                        "capacity_gap",
                        "运行期 Agent 总上限已达到，保留能力缺口但不扩容",
                        round_num,
                    )
                )
                continue
            if created_this_round >= per_round_limit:
                ledger.append(
                    self._ledger_item(
                        demand,
                        signature,
                        "deferred",
                        "本轮 Agent 新增上限已达到，候选延后处理",
                        round_num,
                    )
                )
                continue

            aggregate_index = self._matching_aggregate_index(demand, profiles)
            if aggregate_index is not None:
                parent = profiles[aggregate_index]
                child = self._split_aggregate(
                    parent=parent,
                    demand=demand,
                    signature=signature,
                    agent_id=next_agent_id,
                    round_num=round_num,
                    evidence_score=evidence_score,
                )
                profiles.append(child)
                split_ids.append(next_agent_id)
                lineage.append(
                    self._lineage(
                        child=child,
                        parent_agent_id=int(parent.get("agent_id")),
                        demand=demand,
                        signature=signature,
                        round_num=round_num,
                        mode="split_aggregate",
                    )
                )
                events.append(
                    self._event(
                        event_type="agent_split",
                        agent_id=next_agent_id,
                        demand=demand,
                        signature=signature,
                        round_num=round_num,
                        summary=f"聚合 Agent 已拆分出 {child['name']}，下一轮开始参与推演。",
                    )
                )
                ledger.append(self._ledger_item(demand, signature, "split", "从现有聚合 Agent 拆分", round_num))
            else:
                child = self._create_provisional(
                    demand=demand,
                    signature=signature,
                    agent_id=next_agent_id,
                    round_num=round_num,
                    evidence_score=evidence_score,
                )
                profiles.append(child)
                created_ids.append(next_agent_id)
                lineage.append(
                    self._lineage(
                        child=child,
                        parent_agent_id=None,
                        demand=demand,
                        signature=signature,
                        round_num=round_num,
                        mode="create_provisional",
                    )
                )
                events.append(
                    self._event(
                        event_type="agent_created",
                        agent_id=next_agent_id,
                        demand=demand,
                        signature=signature,
                        round_num=round_num,
                        summary=f"已创建临时 Agent：{child['name']}，下一轮开始参与推演。",
                    )
                )
                ledger.append(self._ledger_item(demand, signature, "created", "未找到可复用或可拆分主体，创建临时 Agent", round_num))

            resolved_signatures.add(signature)
            created_this_round += 1
            next_agent_id += 1

        for signature, candidate in previous_candidates.items():
            if signature in resolved_signatures or signature in next_candidates:
                continue
            if round_num - int(candidate.get("last_round") or round_num) <= 1:
                next_candidates[signature] = dict(candidate)

        state = {
            "contract_version": AGENT_EMERGENCE_CONTRACT_VERSION,
            "effort_snapshot_ref": {
                "effort_snapshot_id": resolved_effort["effort_snapshot_id"],
                "content_hash": resolved_effort["content_hash"],
                "effort_level": resolved_effort["effort_level"],
            },
            "last_round": round_num,
            "candidates": next_candidates,
            "resolved_signatures": sorted(resolved_signatures),
            "created_or_split_count": created_or_split_count + created_this_round,
            "runtime_agent_total_limit": total_limit,
            "runtime_agent_per_round_limit": per_round_limit,
        }
        return AgentEmergenceResult(
            actor_profiles=profiles,
            state=state,
            events=events,
            lineage=lineage,
            candidate_ledger=ledger,
            created_agent_ids=created_ids,
            split_agent_ids=split_ids,
            activated_agent_ids=activated_ids,
        )

    def _collect_demands(
        self,
        *,
        role_demands: Sequence[Mapping[str, Any]],
        runtime_signals: Mapping[str, Any],
        round_num: int,
    ) -> List[Dict[str, Any]]:
        demands = [copy.deepcopy(dict(item)) for item in role_demands if isinstance(item, Mapping)]
        for key in ("capability_gaps", "emergent_role_demands"):
            for item in runtime_signals.get(key) or []:
                if isinstance(item, Mapping):
                    runtime_item = copy.deepcopy(dict(item))
                    runtime_item["runtime_discovered"] = True
                    demands.append(runtime_item)
        for container_key in ("interactions", "feedback", "policy_execution"):
            container = runtime_signals.get(container_key) or {}
            if not isinstance(container, Mapping):
                continue
            for key in ("capability_gaps", "emergent_role_demands"):
                for item in container.get(key) or []:
                    if isinstance(item, Mapping):
                        runtime_item = copy.deepcopy(dict(item))
                        runtime_item["runtime_discovered"] = True
                        demands.append(runtime_item)
        for variable in runtime_signals.get("active_variables") or []:
            if isinstance(variable, Mapping):
                demands.extend(self._variable_demands(variable, round_num))
        relation_demand = self._relationship_demand(runtime_signals, round_num)
        if relation_demand:
            demands.append(relation_demand)

        unique: Dict[str, Dict[str, Any]] = {}
        for demand in demands:
            normalized = self._normalize_demand(demand, round_num)
            signature = self._signature(normalized)
            if not signature:
                continue
            existing = unique.get(signature)
            if not existing or self._evidence_score(normalized) > self._evidence_score(existing):
                unique[signature] = normalized
        return list(unique.values())

    def _normalize_demand(self, demand: Mapping[str, Any], round_num: int) -> Dict[str, Any]:
        item = copy.deepcopy(dict(demand))
        item["demand_key"] = str(item.get("demand_key") or item.get("role_key") or "runtime_capability_gap")
        item["demand_id"] = str(item.get("demand_id") or f"runtime_demand_{self._signature(item)}")
        item["label_zh"] = self._label(item)
        item["required_capability_keys"] = _strings(
            item.get("required_capability_keys") or item.get("capability_keys") or []
        )
        item["jurisdiction_region_ids"] = _strings(
            item.get("jurisdiction_region_ids") or item.get("target_region_ids") or []
        )
        item["created_round"] = int(item.get("created_round") or round_num)
        item["required_permissions"] = _strings(item.get("required_permissions") or [])
        item["required_resource_types"] = _strings(item.get("required_resource_types") or [])
        item["evidence_refs"] = self._source_refs(item)
        return item

    def _variable_demands(self, variable: Mapping[str, Any], round_num: int) -> List[Dict[str, Any]]:
        text = " ".join(
            str(variable.get(key) or "")
            for key in ("name", "title", "description", "template", "type")
        ).lower()
        variable_id = str(variable.get("variable_id") or variable.get("id") or f"round_{round_num}")
        regions = _strings(variable.get("target_regions") or variable.get("target_region_ids") or [])
        intensity = _score(variable.get("intensity_0_100", variable.get("intensity", 60)))
        specs: List[tuple[str, str, List[str], str, str]] = []
        if any(token in text for token in ("核", "辐射", "radioactive", "nuclear")):
            specs.extend(
                [
                    ("nuclear_safety_regulator", "核安全监管能力", ["nuclear_safety_regulation", "radiation_emergency_oversight"], "organization", "critical"),
                    ("environmental_monitoring", "环境与辐射监测能力", ["environmental_monitoring", "radiation_monitoring"], "organization", "critical"),
                ]
            )
        if any(token in text for token in ("暴露", "伤员", "医疗", "health", "medical", "casualty")):
            specs.append(("emergency_medical_response", "医疗应急响应能力", ["emergency_medical_response", "patient_transport"], "specific_facility", "high"))
        if any(token in text for token in ("台风", "暴雨", "洪水", "风暴潮", "typhoon", "flood", "storm")):
            specs.append(("hazard_monitoring", "气象与水文监测能力", ["meteorological_monitoring", "risk_early_warning"], "organization", "high"))
        if any(token in text for token in ("供应", "物资", "物流", "supply", "logistics")):
            specs.append(("critical_supply_coordination", "关键物资供应协调能力", ["supply_chain_monitoring", "logistics_dispatch"], "organization", "high"))
        result = []
        for demand_key, label, capabilities, resolution, importance in specs:
            result.append(
                {
                    "demand_id": f"runtime_variable_{variable_id}_{demand_key}",
                    "demand_key": demand_key,
                    "label_zh": label,
                    "required_capability_keys": capabilities,
                    "jurisdiction_region_ids": regions,
                    "required_resolution": resolution,
                    "importance": importance,
                    "evidence_score": min(95, max(65, intensity)),
                    "impact_score": min(95, max(55, intensity)),
                    "evidence_refs": [f"runtime_variable:{variable_id}"],
                    "created_round": round_num,
                }
            )
        return result

    def _relationship_demand(
        self, runtime_signals: Mapping[str, Any], round_num: int
    ) -> Optional[Dict[str, Any]]:
        interactions = runtime_signals.get("interactions") or {}
        edges = list(runtime_signals.get("new_dynamic_edges") or [])
        if isinstance(interactions, Mapping):
            edges.extend(interactions.get("new_dynamic_edges") or [])
        cross_region = []
        for edge in edges:
            if not isinstance(edge, Mapping):
                continue
            source_region = str(edge.get("source_region_id") or "")
            target_region = str(edge.get("target_region_id") or "")
            if source_region and target_region and source_region != target_region:
                cross_region.append(edge)
        if len(cross_region) < 2:
            return None
        regions = _strings(
            value
            for edge in cross_region
            for value in (edge.get("source_region_id"), edge.get("target_region_id"))
        )
        return {
            "demand_id": f"runtime_relation_coordination_{round_num}",
            "demand_key": "cross_region_coordination",
            "label_zh": "跨区域应急协调能力",
            "required_capability_keys": ["cross_region_coordination", "resource_dispatch"],
            "jurisdiction_region_ids": regions,
            "required_resolution": "organization",
            "importance": "high",
            "evidence_score": min(85, 58 + len(cross_region) * 4),
            "impact_score": min(80, 52 + len(regions) * 4),
            "evidence_refs": _strings(
                f"dynamic_edge:{edge.get('edge_id')}" for edge in cross_region if edge.get("edge_id")
            ),
            "created_round": round_num,
        }

    def _is_covered(self, demand: Mapping[str, Any], profiles: Sequence[Mapping[str, Any]]) -> bool:
        for profile in profiles:
            lifecycle = profile.get("runtime_lifecycle") or {}
            if str(lifecycle.get("lifecycle_status") or "active") in {"dormant", "retired"}:
                continue
            aggregation = profile.get("aggregation") or {}
            is_aggregate = bool(
                profile.get("is_aggregate")
                or lifecycle.get("is_aggregate")
                or aggregation.get("is_aggregate")
            )
            if is_aggregate and bool(demand.get("requires_independent_agent")):
                continue
            if self._profile_matches(demand, profile):
                return True
        return False

    def _profile_matches(self, demand: Mapping[str, Any], profile: Mapping[str, Any]) -> bool:
        demand_regions = set(_strings(demand.get("jurisdiction_region_ids") or []))
        profile_regions = set(
            _strings(
                [
                    profile.get("primary_region"),
                    profile.get("home_region_id"),
                    profile.get("home_subregion_id"),
                    *(profile.get("influenced_regions") or []),
                ]
            )
        )
        if demand_regions and profile_regions and not demand_regions.intersection(profile_regions):
            return False
        required = set(_strings(demand.get("required_capability_keys") or []))
        profile_capability_keys = set(_strings(profile.get("capability_keys") or []))
        if required and required.intersection(profile_capability_keys):
            return True
        haystack = " ".join(
            str(profile.get(key) or "")
            for key in (
                "name",
                "role_type",
                "agent_type",
                "agent_subtype",
                "archetype_key",
                "profession",
            )
        ).lower()
        haystack = f"{haystack} {' '.join(str(item).lower() for item in profile.get('capabilities') or [])}"
        aliases = _DEMAND_PROFILE_TOKENS.get(str(demand.get("demand_key") or ""), set())
        return any(str(token).lower() in haystack for token in aliases)

    def _has_runtime_evidence(self, demand: Mapping[str, Any]) -> bool:
        if bool(demand.get("runtime_discovered")):
            return True
        if str(demand.get("source_type") or "").lower() in {
            "runtime",
            "runtime_signal",
            "runtime_event",
            "injected_event",
        }:
            return True
        runtime_prefixes = (
            "runtime:",
            "runtime_",
            "dynamic_edge:",
            "interaction:",
            "feedback:",
        )
        return any(
            str(reference or "").strip().lower().startswith(runtime_prefixes)
            for reference in self._source_refs(demand)
        )

    def _matching_dormant_index(
        self, demand: Mapping[str, Any], profiles: Sequence[Mapping[str, Any]]
    ) -> Optional[int]:
        for index, profile in enumerate(profiles):
            lifecycle = profile.get("runtime_lifecycle") or {}
            if str(lifecycle.get("lifecycle_status") or "") != "dormant":
                continue
            if self._profile_matches(demand, profile):
                return index
        return None

    def _matching_aggregate_index(
        self, demand: Mapping[str, Any], profiles: Sequence[Mapping[str, Any]]
    ) -> Optional[int]:
        resolution = str(demand.get("required_resolution") or "")
        expected_archetype = archetype_for_demand(demand)
        for index, profile in enumerate(profiles):
            lifecycle = profile.get("runtime_lifecycle") or {}
            aggregation = profile.get("aggregation") or {}
            is_aggregate = bool(
                profile.get("is_aggregate")
                or lifecycle.get("is_aggregate")
                or aggregation.get("is_aggregate")
            )
            if not is_aggregate:
                continue
            profile_archetype = str(
                profile.get("archetype_key") or infer_profile_archetype(profile)
            )
            if profile_archetype != expected_archetype:
                continue
            if resolution == "population_group" and str(profile.get("agent_type") or "") != "human":
                continue
            demand_regions = set(_strings(demand.get("jurisdiction_region_ids") or []))
            profile_regions = set(
                _strings([profile.get("primary_region"), profile.get("home_region_id")])
            )
            if demand_regions and profile_regions and not demand_regions.intersection(profile_regions):
                continue
            return index
        return None

    def _split_aggregate(
        self,
        *,
        parent: Dict[str, Any],
        demand: Mapping[str, Any],
        signature: str,
        agent_id: int,
        round_num: int,
        evidence_score: float,
    ) -> Dict[str, Any]:
        child = copy.deepcopy(parent)
        archetype_key = archetype_for_demand(demand)
        archetype = get_agent_archetype(archetype_key)
        role_label = self._runtime_role_label(demand)
        child_name = f"{role_label}专业响应单元"
        capability_keys = _strings(
            demand.get("required_capability_keys") or archetype["capabilities"]
        )
        requested_permissions = _strings(
            demand.get("required_permissions") or archetype["permissions"]
        )
        parent_budget = dict(parent.get("resource_budget") or {})
        child_budget: Dict[str, float] = {}
        for key, raw_value in parent_budget.items():
            try:
                value = max(0.0, float(raw_value))
            except (TypeError, ValueError):
                continue
            transferred = round(value * 0.35, 6)
            child_budget[key] = transferred
            parent_budget[key] = round(value - transferred, 6)
        parent["resource_budget"] = parent_budget
        parent_lifecycle = dict(parent.get("runtime_lifecycle") or {})
        parent_lifecycle["split_count"] = int(parent_lifecycle.get("split_count") or 0) + 1
        parent_lifecycle["last_split_round"] = round_num
        parent["runtime_lifecycle"] = parent_lifecycle

        child.update(
            {
                "agent_id": agent_id,
                "username": f"runtime_split_{agent_id}",
                "agent_name": child_name,
                "name": child_name,
                "node_family": archetype["node_family"],
                "agent_type": archetype["agent_type"],
                "role_type": str(demand.get("demand_key") or "runtime_specialist"),
                "agent_subtype": archetype["agent_subtype"],
                "archetype_key": archetype_key,
                "bio": f"推演第 {round_num} 轮发现{role_label}能力缺口后，从同类聚合主体拆分建立。",
                "persona": "仅在继承的资源、权限与证据范围内执行专业响应，并持续接受后续轮次校验。",
                "profession": role_label,
                "sensitivities": ["能力缺口变化", "父级资源余量", "服务范围与证据变化"],
                "motivation_stack": ["补足专业能力", "维持响应连续性", "避免重复计算资源"],
                "capability_keys": capability_keys,
                "capabilities": self._capability_labels(demand)
                or list(archetype["capability_labels_zh"]),
                "permission_keys": _strings(
                    permission
                    for permission in requested_permissions
                    if permission in set(parent.get("permission_keys") or [])
                ),
                "resource_types": _strings(
                    demand.get("required_resource_types")
                    or archetype["resource_types"]
                ),
                "goals": [f"补足{role_label}能力缺口", "向现有协同网络提供可验证响应"],
                "constraints": _strings([
                    *archetype["decision_constraints_zh"],
                    "资源由原聚合 Agent 拆分而来，不得重复计算",
                    "下一轮起才可采取行动",
                ]),
                "action_space": list(archetype["available_action_keys"]),
                "action_space_zh": list(archetype["available_action_labels_zh"]),
                "decision_policy": {
                    "policy_key": "evidence_bounded_runtime_specialist",
                    "authority_scope": "inherited_evidence_only",
                    "activation_round": round_num + 1,
                },
                "impact_profile": {
                    "panic_delta": -0.2,
                    "trust_delta": 0.3,
                    "economic_delta": 0.0,
                    "ecology_delta": 0.0,
                },
                "stance_profile": {"risk_aversion": 0.75, "cooperation": 0.75},
                "resource_budget": child_budget,
                "resource_uncertainty": self._resource_uncertainty(child_budget),
                "counterpart_agent_ids": [],
                "social_links": [],
                "ecology_links": [],
                "is_aggregate": False,
                "aggregation_weight": round(max(0.01, float(parent.get("aggregation_weight") or 1.0) * 0.35), 4),
                "parent_agent_id": int(parent.get("agent_id")),
                "representation_level": "runtime_specialist",
                "coverage_region_ids": _strings(
                    demand.get("jurisdiction_region_ids")
                    or parent.get("coverage_region_ids")
                    or [parent.get("primary_region")]
                ),
                "spatial_anchor_refs": self._spatial_anchor_refs(demand)
                or copy.deepcopy(parent.get("spatial_anchor_refs") or []),
                "represented_entity_ids": _strings(
                    demand.get("represented_entity_ids")
                    or parent.get("represented_entity_ids")
                    or []
                ),
                "spatial_precision": str(parent.get("spatial_precision") or "area_only"),
                "role_demand_refs": self._role_demand_refs(demand),
                "initial_relationship_refs": [],
                "activation_triggers": [self._activation_trigger(demand, round_num + 1)],
                "created_round": round_num,
                "activation_round": round_num + 1,
                "lifecycle_status": "pending_activation",
                "scenario_version_ref": self._scenario_version_ref(demand),
                "profile_confidence": round(min(0.95, evidence_score / 100), 3),
                "generation_reason": str(demand.get("rationale_zh") or "运行中发现未覆盖能力需求。"),
                "is_synthesized": True,
                "generation_mode": "runtime_aggregate_split",
                "evidence_refs": self._source_refs(demand),
                "evidence_confidence": round(min(0.95, evidence_score / 100), 3),
                "review_status": "runtime_provisional",
                "grounding_reason": str(demand.get("rationale_zh") or "运行中发现未覆盖能力需求。"),
                "runtime_lifecycle": {
                    "lifecycle_status": "pending_activation",
                    "demand_signature": signature,
                    "discovered_round": round_num,
                    "created_round": round_num,
                    "activation_round": round_num + 1,
                    "resolution_mode": "split_aggregate",
                    "parent_agent_id": int(parent.get("agent_id")),
                    "is_aggregate": False,
                },
                "created_at": datetime.now().strftime("%Y-%m-%d"),
            }
        )
        child["state_vector"] = normalize_state_vector(child.get("state_vector") or {})
        return child

    def _create_provisional(
        self,
        *,
        demand: Mapping[str, Any],
        signature: str,
        agent_id: int,
        round_num: int,
        evidence_score: float,
    ) -> Dict[str, Any]:
        archetype_key = archetype_for_demand(demand)
        archetype = get_agent_archetype(archetype_key)
        role_label = self._runtime_role_label(demand)
        resolution = str(demand.get("required_resolution") or "organization")
        if resolution == "population_group":
            agent_type, node_family = "human", "HumanActor"
        elif resolution in {"ecology", "ecological_receptor"}:
            agent_type, node_family = "ecology", "EcologicalReceptor"
        else:
            # Provisional entities cannot inherit unsupported enforcement power.
            agent_type, node_family = archetype["agent_type"], archetype["node_family"]
        region_ids = _strings(demand.get("jurisdiction_region_ids") or [])
        primary_region = region_ids[0] if region_ids else ""
        label = role_label
        display_name = f"{label}临时响应主体"
        return {
            "agent_id": agent_id,
            "username": f"runtime_provisional_{agent_id}",
            "agent_name": display_name,
            "name": display_name,
            "node_family": node_family,
            "role_type": str(demand.get("demand_key") or "runtime_specialist"),
            "bio": f"推演第 {round_num} 轮发现能力缺口后建立的临时响应主体。",
            "persona": "仅依据当前证据开展监测、协调和信息反馈，不主张未经证实的权限。",
            "profession": label,
            "primary_region": primary_region,
            "home_region_id": primary_region,
            "home_subregion_id": "",
            "influenced_regions": region_ids or ([primary_region] if primary_region else []),
            "agent_type": agent_type,
            "agent_subtype": archetype["agent_subtype"],
            "archetype_key": archetype_key,
            "goals": [f"补足{label}缺口", "持续验证该角色是否需要长期保留"],
            "sensitivities": ["证据强度变化", "服务范围变化", "既有主体能力恢复"],
            "motivation_stack": ["降低未覆盖风险", "维持响应连续性"],
            "capability_keys": _strings(
                demand.get("required_capability_keys") or archetype["capabilities"]
            ),
            "capabilities": self._capability_labels(demand)
            or list(archetype["capability_labels_zh"]),
            "permission_keys": [],
            "resource_types": _strings(
                demand.get("required_resource_types") or archetype["resource_types"]
            ),
            "constraints": _strings([
                *archetype["decision_constraints_zh"],
                "权限仅限观察、协调和建议",
                "不得执行无证据支持的强制措施",
                "下一轮起才可采取行动",
            ]),
            "action_space": list(archetype["available_action_keys"]),
            "action_space_zh": list(archetype["available_action_labels_zh"]),
            "decision_policy": {
                "policy_key": "evidence_bounded_runtime_response",
                "authority_scope": "observation_and_coordination_only",
                "activation_round": round_num + 1,
            },
            "impact_profile": {
                "panic_delta": -0.2,
                "trust_delta": 0.3,
                "economic_delta": 0.0,
                "ecology_delta": 0.0,
            },
            "stance_profile": {"risk_aversion": 0.75, "cooperation": 0.7},
            "resource_budget": {"attention": 20.0, "coordination": 15.0, "authority": 0.0},
            "resource_uncertainty": {
                "attention": [10.0, 30.0],
                "coordination": [7.5, 22.5],
                "authority": [0.0, 0.0],
            },
            "counterpart_agent_ids": [],
            "social_links": [],
            "ecology_links": [],
            "organization_id": None,
            "spawn_weight": 0.25,
            "is_synthesized": True,
            "is_aggregate": False,
            "aggregation_weight": 1.0,
            "parent_agent_id": None,
            "representation_level": "runtime_provisional",
            "coverage_region_ids": region_ids or ([primary_region] if primary_region else []),
            "spatial_anchor_refs": self._spatial_anchor_refs(demand),
            "represented_entity_ids": _strings(demand.get("represented_entity_ids") or []),
            "spatial_precision": str(demand.get("spatial_precision") or "area_only"),
            "role_demand_refs": self._role_demand_refs(demand),
            "initial_relationship_refs": [],
            "activation_triggers": [self._activation_trigger(demand, round_num + 1)],
            "created_round": round_num,
            "activation_round": round_num + 1,
            "lifecycle_status": "pending_activation",
            "scenario_version_ref": self._scenario_version_ref(demand),
            "profile_confidence": round(min(0.8, evidence_score / 100), 3),
            "generation_reason": str(demand.get("rationale_zh") or "运行中发现未覆盖能力需求。"),
            "state_vector": default_state_vector("disaster_mode", node_family),
            "source_entity_uuid": None,
            "source_entity_type": None,
            "generation_mode": "runtime_provisional_agent",
            "evidence_refs": self._source_refs(demand),
            "evidence_confidence": round(min(0.95, evidence_score / 100), 3),
            "review_status": "runtime_provisional",
            "grounding_reason": str(demand.get("rationale_zh") or "运行中发现未覆盖能力需求。"),
            "authority_evidence_refs": _strings(demand.get("authority_evidence_refs") or []),
            "runtime_lifecycle": {
                "lifecycle_status": "pending_activation",
                "demand_signature": signature,
                "discovered_round": round_num,
                "created_round": round_num,
                "activation_round": round_num + 1,
                "resolution_mode": "create_provisional",
                "parent_agent_id": None,
                "is_aggregate": False,
            },
            "created_at": datetime.now().strftime("%Y-%m-%d"),
        }

    def _evidence_score(self, demand: Mapping[str, Any]) -> float:
        if demand.get("evidence_score") is not None:
            return _score(demand.get("evidence_score"))
        event_count = len(_strings(demand.get("caused_by_event_ids") or []))
        mechanism_count = len(_strings(demand.get("caused_by_mechanism_ids") or []))
        evidence_count = len(_strings(demand.get("evidence_refs") or []))
        return min(95.0, 40.0 + min(20, event_count * 10) + min(20, mechanism_count * 10) + min(15, evidence_count * 5))

    def _impact_score(self, demand: Mapping[str, Any]) -> float:
        if demand.get("impact_score") is not None:
            return _score(demand.get("impact_score"))
        return {
            "critical": 85.0,
            "high": 65.0,
            "medium": 50.0,
            "low": 35.0,
        }.get(str(demand.get("importance") or "medium").lower(), 50.0)

    def _signature(self, demand: Mapping[str, Any]) -> str:
        payload = {
            "demand_key": str(demand.get("demand_key") or demand.get("role_key") or ""),
            "capabilities": sorted(_strings(demand.get("required_capability_keys") or demand.get("capability_keys") or [])),
            "regions": sorted(_strings(demand.get("jurisdiction_region_ids") or demand.get("target_region_ids") or [])),
            "resolution": str(demand.get("required_resolution") or "organization"),
        }
        if not payload["demand_key"] and not payload["capabilities"]:
            return ""
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    def _source_refs(self, demand: Mapping[str, Any]) -> List[str]:
        return _strings(
            [
                *(demand.get("evidence_refs") or []),
                *(f"event:{item}" for item in demand.get("caused_by_event_ids") or []),
                *(f"mechanism:{item}" for item in demand.get("caused_by_mechanism_ids") or []),
            ]
        )

    @staticmethod
    def _role_demand_refs(demand: Mapping[str, Any]) -> List[str]:
        return _strings(
            [
                demand.get("role_demand_id"),
                demand.get("demand_id"),
                *(demand.get("role_demand_refs") or []),
            ]
        )

    @staticmethod
    def _spatial_anchor_refs(demand: Mapping[str, Any]) -> List[Dict[str, Any]]:
        return [
            copy.deepcopy(dict(item))
            for item in demand.get("spatial_anchor_refs") or []
            if isinstance(item, Mapping)
        ]

    @staticmethod
    def _scenario_version_ref(demand: Mapping[str, Any]) -> Dict[str, Any]:
        raw = demand.get("scenario_version_ref") or demand.get("planning_input_ref") or {}
        return copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}

    @staticmethod
    def _activation_trigger(demand: Mapping[str, Any], activation_round: int) -> Dict[str, Any]:
        return {
            "trigger_type": "runtime_evidence_confirmed",
            "event_ids": _strings(demand.get("caused_by_event_ids") or []),
            "mechanism_edge_ids": _strings(demand.get("caused_by_mechanism_ids") or []),
            "evidence_refs": _strings(demand.get("evidence_refs") or []),
            "earliest_round": activation_round,
        }

    @staticmethod
    def _resource_uncertainty(resource_budget: Mapping[str, Any]) -> Dict[str, List[float]]:
        uncertainty: Dict[str, List[float]] = {}
        for key, raw_value in resource_budget.items():
            try:
                value = max(0.0, float(raw_value))
            except (TypeError, ValueError):
                continue
            uncertainty[str(key)] = [round(value * 0.7, 3), round(value * 1.3, 3)]
        return uncertainty

    def _capability_labels(self, demand: Mapping[str, Any]) -> List[str]:
        labels = [
            _CAPABILITY_LABELS[key]
            for key in _strings(demand.get("required_capability_keys") or [])
            if key in _CAPABILITY_LABELS
        ]
        if labels:
            return _strings(labels)
        archetype = get_agent_archetype(archetype_for_demand(demand))
        return _strings(archetype.get("capability_labels_zh") or []) or [self._label(demand)]

    def _runtime_role_label(self, demand: Mapping[str, Any]) -> str:
        label = self._label(demand)
        for suffix in ("能力需求", "角色需求", "能力", "需求"):
            if label.endswith(suffix) and len(label) > len(suffix):
                return label[: -len(suffix)]
        return label

    @staticmethod
    def _label(demand: Mapping[str, Any]) -> str:
        label = str(demand.get("label_zh") or demand.get("label") or "").strip()
        return label if label and any("\u4e00" <= char <= "\u9fff" for char in label) else "运行期专项响应能力"

    @staticmethod
    def _next_agent_id(profiles: Sequence[Mapping[str, Any]]) -> int:
        identifiers = []
        for profile in profiles:
            try:
                identifiers.append(int(profile.get("agent_id")))
            except (TypeError, ValueError):
                continue
        return max(identifiers, default=-1) + 1

    def _event(
        self,
        *,
        event_type: str,
        agent_id: int,
        demand: Mapping[str, Any],
        signature: str,
        round_num: int,
        summary: str,
    ) -> Dict[str, Any]:
        return {
            "event_id": f"agent_event_{uuid.uuid4().hex[:16]}",
            "event_type": event_type,
            "agent_id": agent_id,
            "demand_id": str(demand.get("demand_id") or ""),
            "demand_signature": signature,
            "round": round_num,
            "effective_round": round_num + 1,
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
        }

    def _lineage(
        self,
        *,
        child: Mapping[str, Any],
        parent_agent_id: Optional[int],
        demand: Mapping[str, Any],
        signature: str,
        round_num: int,
        mode: str,
    ) -> Dict[str, Any]:
        return {
            "lineage_id": f"agent_lineage_{uuid.uuid4().hex[:16]}",
            "agent_id": int(child.get("agent_id")),
            "parent_agent_id": parent_agent_id,
            "resolution_mode": mode,
            "demand_id": str(demand.get("demand_id") or ""),
            "demand_signature": signature,
            "created_round": round_num,
            "effective_round": round_num + 1,
            "evidence_refs": self._source_refs(demand),
            "timestamp": datetime.now().isoformat(),
        }

    def _ledger_item(
        self,
        demand: Mapping[str, Any],
        signature: str,
        status: str,
        reason: str,
        round_num: int,
    ) -> Dict[str, Any]:
        return {
            "ledger_id": f"agent_candidate_{uuid.uuid4().hex[:16]}",
            "round": round_num,
            "demand_id": str(demand.get("demand_id") or ""),
            "demand_signature": signature,
            "label_zh": self._label(demand),
            "status": status,
            "reason": reason,
            "evidence_score": self._evidence_score(demand),
            "impact_score": self._impact_score(demand),
            "timestamp": datetime.now().isoformat(),
        }


def _strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _score(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "AGENT_EMERGENCE_CONTRACT_VERSION",
    "AgentEmergenceDetector",
    "AgentEmergenceResult",
]
