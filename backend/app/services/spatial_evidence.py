"""Mechanism-aware R3/R4 spatial evidence contracts and pure compiler.

The Step 1 map seed is a spatial skeleton, not proof that every facility needed
by a Step 2 scenario has been found.  This module defines the boundary for the
second, mechanism-aware refinement pass.  It is deliberately network-free: it
compiles an authoritative ``ScenarioPlanningInput`` (or its serialized shape)
into deterministic evidence requests that provider adapters may execute later.

The compiler describes facilities, institutions, internal units and population
segments.  It never creates Agents, Agent identifiers, or Agent target counts.
R4 model units always retain an explicit source kind so inferred capacity can
never masquerade as observed facility data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple


SPATIAL_EVIDENCE_CONTRACT_VERSION = "spatial_evidence.v1"
FACILITY_QUERY_PLAN_CONTRACT_VERSION = "facility_query_plan.v1"
SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION = "spatial_refinement_snapshot.v1"

ResolutionLevel = Literal["R3", "R4"]
R4SourceKind = Literal["authoritative", "user_supplied", "synthetic_model"]

_R4_SOURCE_KINDS = {"authoritative", "user_supplied", "synthetic_model"}
_R3_SOURCE_KINDS = {
    "authoritative",
    "user_supplied",
    "controlled_spatial_index",
    "licensed_provider",
}
_IMPORTANCE_PRIORITY = {"critical": 100, "high": 80, "medium": 60, "low": 40}


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique_strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        serialized = value.to_dict()
        return dict(serialized) if isinstance(serialized, Mapping) else {}
    return {}


def _mapping_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    result: List[Dict[str, Any]] = []
    for item in value:
        mapped = _mapping(item)
        if mapped:
            result.append(mapped)
    return result


def _canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{_content_hash(parts)[:16]}"


def _bounded_priority(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 60
    return max(0, min(100, parsed))


def _assert_no_agent_contract_fields(payload: Mapping[str, Any]) -> None:
    forbidden = {"agent_id", "agent_ids", "target_agent_count", "agent_count"}

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            overlap = forbidden.intersection(str(key) for key in value)
            if overlap:
                raise ValueError(f"空间证据合同不能包含 Agent 字段：{', '.join(sorted(overlap))}")
            for nested in value.values():
                walk(nested)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for nested in value:
                walk(nested)

    walk(payload)


@dataclass(frozen=True)
class SpatialEvidenceRequest:
    """One traceable R3 discovery or R4 modelling requirement."""

    request_id: str
    label_zh: str
    request_kind: str
    resolution_level: ResolutionLevel
    priority: int
    importance: str
    caused_by_event_ids: List[str] = field(default_factory=list)
    caused_by_mechanism_ids: List[str] = field(default_factory=list)
    caused_by_role_demand_ids: List[str] = field(default_factory=list)
    required_capability_keys: List[str] = field(default_factory=list)
    target_region_ids: List[str] = field(default_factory=list)
    target_entity_ids: List[str] = field(default_factory=list)
    facility_class_keys: List[str] = field(default_factory=list)
    parent_r3_request_ids: List[str] = field(default_factory=list)
    representation_requirement: str = "facility_required"
    minimum_evidence_grade: str = "C"
    allowed_source_kinds: List[str] = field(default_factory=list)
    r4_unit_type_keys: List[str] = field(default_factory=list)
    query_reason_zh: str = ""
    stop_conditions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.resolution_level not in {"R3", "R4"}:
            raise ValueError("空间证据请求的分辨率只能是 R3 或 R4")
        object.__setattr__(self, "priority", _bounded_priority(self.priority))
        if self.resolution_level == "R4":
            source_kinds = set(self.allowed_source_kinds)
            if not source_kinds or not source_kinds.issubset(_R4_SOURCE_KINDS):
                raise ValueError("R4 请求必须明确限定 authoritative、user_supplied 或 synthetic_model 来源")
            if not self.parent_r3_request_ids:
                raise ValueError("R4 请求必须引用父级 R3 取证请求")
        elif not set(self.allowed_source_kinds).issubset(_R3_SOURCE_KINDS):
            raise ValueError("R3 请求包含不受支持的数据来源类型")
        _assert_no_agent_contract_fields(asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SpatialEvidenceRequest":
        return cls(**dict(value))


@dataclass(frozen=True)
class FacilityQueryPlan:
    """Deterministic request plan consumed by future spatial provider adapters."""

    plan_id: str
    scenario_planning_ref: Dict[str, Any]
    event_mechanism_graph_ref: Dict[str, Any]
    effort_snapshot_ref: Dict[str, Any]
    requests: List[SpatialEvidenceRequest]
    required_r3_request_ids: List[str]
    required_r4_request_ids: List[str]
    role_demand_refs: List[str]
    assumptions: List[str] = field(default_factory=list)
    contract_version: str = FACILITY_QUERY_PLAN_CONTRACT_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        request_ids = [item.request_id for item in self.requests]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("设施查询计划存在重复请求标识")
        known = set(request_ids)
        if not set(self.required_r3_request_ids).issubset(known):
            raise ValueError("R3 请求索引引用了计划外请求")
        if not set(self.required_r4_request_ids).issubset(known):
            raise ValueError("R4 请求索引引用了计划外请求")
        _assert_no_agent_contract_fields(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "plan_id": self.plan_id,
            "scenario_planning_ref": dict(self.scenario_planning_ref),
            "event_mechanism_graph_ref": dict(self.event_mechanism_graph_ref),
            "effort_snapshot_ref": dict(self.effort_snapshot_ref),
            "requests": [item.to_dict() for item in self.requests],
            "required_r3_request_ids": list(self.required_r3_request_ids),
            "required_r4_request_ids": list(self.required_r4_request_ids),
            "role_demand_refs": list(self.role_demand_refs),
            "assumptions": list(self.assumptions),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FacilityQueryPlan":
        raw = dict(value)
        raw["requests"] = [SpatialEvidenceRequest.from_dict(item) for item in raw.get("requests") or []]
        return cls(**raw)


@dataclass(frozen=True)
class R4ModelUnit:
    """One internal unit or population segment attached to observed R3 evidence."""

    unit_id: str
    parent_r3_feature_id: str
    label_zh: str
    unit_type_key: str
    source_kind: R4SourceKind
    capability_keys: List[str] = field(default_factory=list)
    resource_profile: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    spatial_precision: str = "parent_facility_only"

    def __post_init__(self) -> None:
        if self.source_kind not in _R4_SOURCE_KINDS:
            raise ValueError("R4 单元必须明确标记 authoritative、user_supplied 或 synthetic_model")
        if not _clean_text(self.parent_r3_feature_id):
            raise ValueError("R4 单元必须绑定父级 R3 设施证据")
        if self.source_kind == "synthetic_model" and not _unique_strings(self.assumptions):
            raise ValueError("synthetic_model R4 单元必须记录建模假设")
        try:
            confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("R4 单元置信度必须是数值") from exc
        object.__setattr__(self, "confidence", round(max(0.0, min(1.0, confidence)), 4))
        _assert_no_agent_contract_fields(asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "R4ModelUnit":
        return cls(**dict(value))


@dataclass(frozen=True)
class SpatialRefinementSnapshot:
    """Versionable result envelope for a completed/partial provider pass."""

    snapshot_id: str
    facility_query_plan_ref: Dict[str, Any]
    selected_r3_features: List[Dict[str, Any]] = field(default_factory=list)
    r4_model_units: List[R4ModelUnit] = field(default_factory=list)
    request_coverage: List[Dict[str, Any]] = field(default_factory=list)
    evidence_gaps: List[Dict[str, Any]] = field(default_factory=list)
    provider_attempts: List[Dict[str, Any]] = field(default_factory=list)
    source_versions: List[Dict[str, Any]] = field(default_factory=list)
    contract_version: str = SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            payload = self.to_dict()
            payload["content_hash"] = ""
            object.__setattr__(self, "content_hash", _content_hash(payload))
        _assert_no_agent_contract_fields(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "snapshot_id": self.snapshot_id,
            "facility_query_plan_ref": dict(self.facility_query_plan_ref),
            "selected_r3_features": [dict(item) for item in self.selected_r3_features],
            "r4_model_units": [item.to_dict() for item in self.r4_model_units],
            "request_coverage": [dict(item) for item in self.request_coverage],
            "evidence_gaps": [dict(item) for item in self.evidence_gaps],
            "provider_attempts": [dict(item) for item in self.provider_attempts],
            "source_versions": [dict(item) for item in self.source_versions],
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SpatialRefinementSnapshot":
        raw = dict(value)
        raw["r4_model_units"] = [R4ModelUnit.from_dict(item) for item in raw.get("r4_model_units") or []]
        return cls(**raw)


@dataclass(frozen=True)
class _EvidenceRule:
    facility_class_keys: Tuple[str, ...]
    request_kind: str = "institution_discovery"
    r4_unit_type_keys: Tuple[str, ...] = ()


_DEMAND_RULES: Dict[str, _EvidenceRule] = {
    "hazard_monitoring": _EvidenceRule(
        ("meteorological_station", "hydrological_station", "coastal_monitoring_station")
    ),
    "geological_emergency_monitoring": _EvidenceRule(
        ("seismic_monitoring_station", "geological_hazard_monitoring_station")
    ),
    "critical_facility_operator": _EvidenceRule(
        ("nuclear_power_facility", "critical_infrastructure_facility"),
        "facility_discovery",
        ("backup_power_unit", "cooling_system_unit", "safety_system_unit"),
    ),
    "nuclear_safety_regulator": _EvidenceRule(("nuclear_safety_regulator",)),
    "environmental_monitoring": _EvidenceRule(
        ("radiation_monitoring_station", "environmental_monitoring_station", "analytical_laboratory")
    ),
    "emergency_medical_response": _EvidenceRule(
        ("emergency_hospital", "emergency_medical_center"), "facility_discovery"
    ),
    "healthcare_capacity_coordination": _EvidenceRule(
        ("hospital", "emergency_medical_center"),
        "facility_discovery",
        ("emergency_department", "intensive_care_unit", "bed_capacity_pool", "backup_power_unit"),
    ),
    "public_emergency_command": _EvidenceRule(
        ("emergency_management_authority", "local_government_command_center")
    ),
    "affected_population": _EvidenceRule(
        ("residential_community", "evacuation_shelter"),
        "population_anchor_discovery",
        ("vulnerable_population_segment", "evacuation_population_segment"),
    ),
    "fisheries_stakeholders": _EvidenceRule(
        ("fishing_port", "fisheries_cooperative", "seafood_market"),
        "population_anchor_discovery",
        ("fisher_household_segment", "fisheries_worker_segment"),
    ),
    "transport_continuity": _EvidenceRule(
        ("transport_command_center", "road_network_node", "public_transport_hub")
    ),
    "transport_restriction_execution": _EvidenceRule(
        ("traffic_management_authority", "public_transport_operator")
    ),
    "critical_supply_coordination": _EvidenceRule(
        ("emergency_warehouse", "logistics_hub", "critical_supply_depot"), "facility_discovery"
    ),
    "emergency_resource_dispatch": _EvidenceRule(
        ("emergency_warehouse", "logistics_hub", "emergency_command_center")
    ),
    "cross_agency_governance": _EvidenceRule(
        ("local_government_command_center", "emergency_management_authority")
    ),
    "education_emergency_execution": _EvidenceRule(
        ("education_authority", "school"), "institution_discovery"
    ),
    "workplace_shutdown_execution": _EvidenceRule(
        ("labor_safety_authority", "industrial_facility", "business_association")
    ),
    "community_shelter_coordination": _EvidenceRule(
        ("residential_community", "evacuation_shelter"),
        "population_anchor_discovery",
        ("vulnerable_population_segment",),
    ),
    "policy_execution": _EvidenceRule(
        ("responsible_public_authority",), "institution_discovery"
    ),
}

_EVENT_FACILITY_CLASSES: Dict[str, Tuple[str, ...]] = {
    "facility_ingress": ("critical_infrastructure_facility",),
    "power_loss": ("power_dependent_critical_facility",),
    "cooling_failure": ("nuclear_power_facility", "industrial_cooling_facility"),
    "radioactive_release": ("nuclear_power_facility", "radiological_facility"),
    "chemical_release": ("chemical_industrial_facility",),
    "medical_pressure": ("hospital", "emergency_medical_center"),
    "traffic_pressure": ("public_transport_hub", "road_network_node"),
    "supply_pressure": ("emergency_warehouse", "logistics_hub"),
}


_SUBTYPE_FACILITY_CLASSES: Dict[str, Tuple[str, ...]] = {
    "hospital": ("hospital", "emergency_hospital", "emergency_medical_center"),
    "emergency_hospital": ("hospital", "emergency_hospital", "emergency_medical_center"),
    "clinic": ("hospital", "emergency_medical_center"),
    "doctors": ("hospital", "emergency_medical_center"),
    "fire_station": ("emergency_response_facility",),
    "police": ("emergency_response_facility", "responsible_public_authority"),
    "townhall": (
        "local_government_command_center",
        "emergency_management_authority",
        "responsible_public_authority",
    ),
    "government": (
        "local_government_command_center",
        "emergency_management_authority",
        "responsible_public_authority",
    ),
    "power_plant": ("critical_infrastructure_facility", "power_dependent_critical_facility"),
    "wastewater_plant": ("critical_infrastructure_facility",),
    "industrial": ("industrial_facility", "critical_infrastructure_facility"),
    "rail_station": ("public_transport_hub", "road_network_node"),
    "transit_stop": ("public_transport_hub",),
    "bus_station": ("public_transport_hub",),
    "ferry_terminal": ("public_transport_hub", "fishing_port"),
    "port": ("fishing_port", "logistics_hub"),
    "harbour": ("fishing_port", "logistics_hub"),
    "road_corridor": ("road_network_node",),
    "residential": ("residential_community",),
    "shelter": ("emergency_shelter", "evacuation_shelter", "community_shelter"),
    "community_centre": ("community_service_center", "responsible_institution"),
    "marketplace": ("seafood_market",),
    "pier": ("fishing_port",),
    "marina": ("fishing_port",),
    "school": ("school",),
    "university": ("school",),
}

_EVIDENCE_GRADE_RANK = {"S": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def _catalog_facility_classes(item: Mapping[str, Any]) -> List[str]:
    raw_classes = item.get("facility_class_keys") or []
    if isinstance(raw_classes, str):
        raw_classes = [raw_classes]
    explicit = _unique_strings(raw_classes)
    subtype = _clean_text(item.get("subtype")).lower()
    classes = [*explicit, *_SUBTYPE_FACILITY_CLASSES.get(subtype, ())]
    tags = _mapping(item.get("tags"))
    power_source = _clean_text(
        tags.get("plant:source") or tags.get("generator:source") or tags.get("source")
    ).lower()
    name = _clean_text(item.get("name") or item.get("label_zh"))
    if subtype == "power_plant" and (
        power_source in {"nuclear", "atomic"} or any(token in name for token in ("核电", "核能"))
    ):
        classes.extend(("nuclear_power_facility", "radiological_facility"))
    if any(token in subtype for token in ("monitor", "weather_station", "hydrological")):
        classes.extend(("monitoring_institution", "environmental_monitoring_station"))
    return _unique_strings(classes)


def _catalog_evidence_grade(item: Mapping[str, Any]) -> str:
    explicit = _clean_text(item.get("evidence_grade")).upper()
    if explicit in _EVIDENCE_GRADE_RANK:
        return explicit
    source_kind = _clean_text(item.get("source_kind")).lower()
    provider = _clean_text(item.get("provider")).lower()
    if source_kind in {"authoritative", "user_confirmed", "user_supplied"}:
        return "A"
    if source_kind == "cross_verified":
        return "B"
    if source_kind in {"observed", "detected"} and provider in {
        "osm_overpass",
        "overpass",
        "overture",
        "overture_places",
        "licensed_provider",
        "controlled_spatial_index",
    }:
        return "C"
    return "D"


def normalize_spatial_catalog_candidate(raw: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize one Step 1/provider record for catalog storage or evaluation.

    This keeps subtype-to-facility classification and evidence grading at one
    boundary.  A caller may persist the normalized record, but the function
    itself performs no I/O and never upgrades a weak source.
    """

    if not isinstance(raw, Mapping):
        return None
    item = dict(raw)
    feature_id = _clean_text(item.get("feature_id") or item.get("id"))
    if not feature_id:
        return None
    item["feature_id"] = feature_id
    item["facility_class_keys"] = _catalog_facility_classes(item)
    item["evidence_grade"] = _catalog_evidence_grade(item)
    return item


def _grade_meets(candidate: str, minimum: str) -> bool:
    return _EVIDENCE_GRADE_RANK.get(candidate, -1) >= _EVIDENCE_GRADE_RANK.get(minimum, 99)


def build_spatial_refinement_snapshot(
    plan: FacilityQueryPlan | Mapping[str, Any],
    *,
    target_catalog: Sequence[Mapping[str, Any]],
    provider_attempts: Optional[Sequence[Mapping[str, Any]]] = None,
    source_versions: Optional[Sequence[Mapping[str, Any]]] = None,
) -> SpatialRefinementSnapshot:
    """Evaluate the current controlled catalog against a facility query plan.

    This function performs no network access and never fabricates R4 facts.  It
    records which requirements are already grounded, which have only weak
    candidates, and which must be sent to a provider/local-index refinement
    worker.  Later provider passes can call it again with an expanded catalog.
    """

    compiled_plan = (
        plan if isinstance(plan, FacilityQueryPlan) else FacilityQueryPlan.from_dict(plan)
    )
    catalog: List[Dict[str, Any]] = []
    for raw in target_catalog or []:
        item = normalize_spatial_catalog_candidate(raw)
        if item is None:
            continue
        catalog.append(item)

    catalog_by_id = {item["feature_id"]: item for item in catalog}
    coverage: List[Dict[str, Any]] = []
    gaps: List[Dict[str, Any]] = []
    selected_by_id: Dict[str, Dict[str, Any]] = {}
    covered_r3_requests: set[str] = set()

    for request in compiled_plan.requests:
        if request.resolution_level == "R4":
            parents_ready = bool(request.parent_r3_request_ids) and all(
                parent_id in covered_r3_requests for parent_id in request.parent_r3_request_ids
            )
            status = "model_input_required" if parents_ready else "parent_r3_missing"
            coverage.append({
                "request_id": request.request_id,
                "resolution_level": "R4",
                "status": status,
                "matched_feature_ids": [],
                "minimum_evidence_grade": request.minimum_evidence_grade,
                "r4_unit_type_keys": list(request.r4_unit_type_keys),
            })
            gaps.append({
                "request_id": request.request_id,
                "resolution_level": "R4",
                "reason_code": status,
                "message_zh": (
                    "父级真实设施已确认，仍需机构资料、用户资料或显式合成模型建立内部单元。"
                    if parents_ready
                    else "尚未确认父级 R3 设施，不能建立内部单元。"
                ),
                "blocking": request.representation_requirement == "subunit_required",
            })
            continue

        candidates: List[Dict[str, Any]] = []
        if request.target_entity_ids:
            candidates = [
                catalog_by_id[item_id]
                for item_id in request.target_entity_ids
                if item_id in catalog_by_id
            ]
        else:
            requested_classes = set(request.facility_class_keys)
            candidates = [
                item
                for item in catalog
                if requested_classes.intersection(item.get("facility_class_keys") or [])
            ]
        accepted = [
            item
            for item in candidates
            if _grade_meets(str(item.get("evidence_grade") or "D"), request.minimum_evidence_grade)
        ]
        for item in accepted:
            selected_by_id[item["feature_id"]] = item
        if accepted:
            status = "covered"
            covered_r3_requests.add(request.request_id)
        elif candidates:
            status = "insufficient_evidence"
        else:
            status = "missing"
        coverage.append({
            "request_id": request.request_id,
            "resolution_level": "R3",
            "status": status,
            "matched_feature_ids": [item["feature_id"] for item in accepted],
            "candidate_feature_ids": [item["feature_id"] for item in candidates],
            "minimum_evidence_grade": request.minimum_evidence_grade,
        })
        if status != "covered":
            gaps.append({
                "request_id": request.request_id,
                "resolution_level": "R3",
                "reason_code": status,
                "message_zh": (
                    "当前目录存在候选对象，但证据等级不足，需要交叉验证或权威来源。"
                    if candidates
                    else "当前目录尚未找到满足该场景需求的真实设施或机构。"
                ),
                "blocking": request.importance == "critical"
                and request.representation_requirement in {"facility_required", "subunit_required"},
            })

    plan_ref = {
        "contract_version": compiled_plan.contract_version,
        "plan_id": compiled_plan.plan_id,
        "content_hash": compiled_plan.content_hash,
    }
    snapshot_seed = {
        "facility_query_plan_ref": plan_ref,
        "selected_r3_features": list(selected_by_id.values()),
        "request_coverage": coverage,
        "evidence_gaps": gaps,
        "provider_attempts": [dict(item) for item in (provider_attempts or [])],
        "source_versions": [dict(item) for item in (source_versions or [])],
    }
    snapshot_id = _stable_id("spatial_refinement", snapshot_seed)
    payload_without_hash = {
        "contract_version": SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION,
        "snapshot_id": snapshot_id,
        **snapshot_seed,
        "r4_model_units": [],
        "content_hash": "",
    }
    return SpatialRefinementSnapshot(
        snapshot_id=snapshot_id,
        facility_query_plan_ref=plan_ref,
        selected_r3_features=list(selected_by_id.values()),
        request_coverage=coverage,
        evidence_gaps=gaps,
        provider_attempts=[dict(item) for item in (provider_attempts or [])],
        source_versions=[dict(item) for item in (source_versions or [])],
        content_hash=_content_hash(payload_without_hash),
    )


def _event_refs(
    event_ids: Sequence[str],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    mechanisms_by_event_id: Mapping[str, Sequence[str]],
) -> Tuple[List[str], List[str], List[str]]:
    region_ids = _unique_strings(
        region_id
        for event_id in event_ids
        for region_id in (nodes_by_id.get(event_id, {}).get("target_region_ids") or [])
    )
    entity_ids = _unique_strings(
        entity_id
        for event_id in event_ids
        for entity_id in (nodes_by_id.get(event_id, {}).get("target_entity_ids") or [])
    )
    mechanism_ids = _unique_strings(
        mechanism_id
        for event_id in event_ids
        for mechanism_id in mechanisms_by_event_id.get(event_id, [])
    )
    return region_ids, entity_ids, mechanism_ids


def _fallback_facility_classes(demand: Mapping[str, Any]) -> List[str]:
    capabilities = _unique_strings(demand.get("required_capability_keys") or [])
    classes: List[str] = []
    for capability in capabilities:
        if any(token in capability for token in ("hospital", "medical", "patient", "triage")):
            classes.append("hospital")
        elif any(token in capability for token in ("monitor", "laboratory", "forecast")):
            classes.append("monitoring_institution")
        elif any(token in capability for token in ("transport", "traffic", "road")):
            classes.append("transport_institution")
        elif any(token in capability for token in ("supply", "inventory", "logistics")):
            classes.append("logistics_facility")
        elif any(token in capability for token in ("community", "population", "public_risk")):
            classes.append("residential_community")
        else:
            classes.append("responsible_institution")
    return _unique_strings(classes) or ["responsible_institution"]


def _representation_requirement(demand: Mapping[str, Any]) -> str:
    explicit = _clean_text(demand.get("representation_requirement"))
    if explicit:
        return explicit
    resolution = _clean_text(demand.get("required_resolution")).lower()
    return {
        "specific_facility": "facility_required",
        "facility": "facility_required",
        "r3": "facility_required",
        "organization": "institution_required",
        "institution": "institution_required",
        "population_group": "aggregate_allowed",
        "subunit": "subunit_required",
        "r4": "subunit_required",
    }.get(resolution, "institution_required")


def _minimum_grade(importance: str, representation: str) -> str:
    if importance == "critical" or representation in {"facility_required", "subunit_required"}:
        return "B"
    return "C"


def _r3_stop_conditions(target_entity_ids: Sequence[str], minimum_grade: str) -> List[str]:
    if target_entity_ids:
        return [
            f"已确认用户指定设施且证据等级达到 {minimum_grade}",
            "所有指定设施均有可追溯来源，或形成明确空间证据缺口",
        ]
    return [
        f"场景作用区域内已找到证据等级达到 {minimum_grade} 的适配设施或机构",
        "受控数据源已完成查询，或形成明确空间证据缺口",
    ]


def _scenario_ref(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "planning_input_id": _clean_text(payload.get("planning_input_id")),
        "contract_version": _clean_text(payload.get("contract_version")) or "scenario_planning.unknown",
        "content_hash": _clean_text(payload.get("content_hash")),
    }


def compile_facility_query_plan(
    scenario: Optional[Any] = None,
    *,
    event_mechanism_graph: Optional[Any] = None,
    role_demands: Optional[Sequence[Mapping[str, Any] | Any]] = None,
    foundation_ref: Optional[Mapping[str, Any]] = None,
    effort_snapshot_ref: Optional[Mapping[str, Any]] = None,
    scenario_planning_ref: Optional[Mapping[str, Any]] = None,
) -> FacilityQueryPlan:
    """Compile a deterministic R3/R4 query plan without provider I/O.

    Callers normally pass ``ScenarioPlanningInput``.  Standalone graph and
    RoleDemand arguments keep the boundary usable by future pipeline workers
    without importing the Step 2 planner class.
    """

    scenario_payload = _mapping(scenario)
    graph = _mapping(event_mechanism_graph or scenario_payload.get("event_mechanism_graph"))
    demands = _mapping_list(role_demands if role_demands is not None else scenario_payload.get("role_demands"))
    foundation = dict(foundation_ref or _mapping(scenario_payload.get("foundation_ref")))
    effort = dict(effort_snapshot_ref or _mapping(scenario_payload.get("effort_snapshot_ref")))
    planning_ref = dict(scenario_planning_ref or _scenario_ref(scenario_payload))

    nodes = _mapping_list(graph.get("nodes"))
    edges = _mapping_list(graph.get("edges"))
    nodes_by_id = {
        _clean_text(item.get("event_id") or item.get("id")): item
        for item in nodes
        if _clean_text(item.get("event_id") or item.get("id"))
    }
    mechanisms_by_event_id: Dict[str, List[str]] = {}
    for edge in edges:
        mechanism_id = _clean_text(edge.get("mechanism_id") or edge.get("id"))
        if not mechanism_id:
            continue
        for event_id in (
            _clean_text(edge.get("source_event_id")),
            _clean_text(edge.get("target_event_id")),
        ):
            if event_id:
                mechanisms_by_event_id.setdefault(event_id, []).append(mechanism_id)

    foundation_regions = _unique_strings(
        foundation.get("region_ids")
        or [item.get("region_id") for item in _mapping_list(foundation.get("regions"))]
    )
    requests: List[SpatialEvidenceRequest] = []

    # Explicit user-targeted entities are always checked before inferred role
    # demands.  Multiple mechanism nodes inherited from one user event share a
    # single request, avoiding redundant provider calls.
    explicit_groups: Dict[Tuple[Tuple[str, ...], Tuple[str, ...]], List[Dict[str, Any]]] = {}
    for node in nodes:
        target_entities = tuple(sorted(_unique_strings(node.get("target_entity_ids") or [])))
        if not target_entities:
            continue
        target_regions = tuple(sorted(_unique_strings(node.get("target_region_ids") or foundation_regions)))
        explicit_groups.setdefault((target_entities, target_regions), []).append(node)

    for (target_entities, target_regions), group in sorted(explicit_groups.items()):
        event_ids = _unique_strings(item.get("event_id") or item.get("id") for item in group)
        mechanism_ids = _unique_strings(
            mechanism_id
            for event_id in event_ids
            for mechanism_id in mechanisms_by_event_id.get(event_id, [])
        )
        facility_classes = _unique_strings(
            class_key
            for item in group
            for class_key in _EVENT_FACILITY_CLASSES.get(_clean_text(item.get("atomic_key")), ())
        ) or ["user_specified_facility"]
        request_id = _stable_id(
            "spatial_request", "explicit_target", target_entities, target_regions, facility_classes
        )
        requests.append(
            SpatialEvidenceRequest(
                request_id=request_id,
                label_zh="确认事件链明确指定的具体设施",
                request_kind="explicit_target_facility",
                resolution_level="R3",
                priority=100,
                importance="critical",
                caused_by_event_ids=event_ids,
                caused_by_mechanism_ids=mechanism_ids,
                target_region_ids=list(target_regions),
                target_entity_ids=list(target_entities),
                facility_class_keys=facility_classes,
                representation_requirement="facility_required",
                minimum_evidence_grade="B",
                allowed_source_kinds=sorted(_R3_SOURCE_KINDS),
                query_reason_zh="事件输入明确指定了受影响设施，必须先确认真实设施证据再进行角色和内部单元规划。",
                stop_conditions=_r3_stop_conditions(target_entities, "B"),
            )
        )

    for demand in demands:
        demand_id = _clean_text(demand.get("demand_id") or demand.get("role_demand_id"))
        demand_key = _clean_text(demand.get("demand_key") or demand.get("role_key")) or "unknown_demand"
        importance = _clean_text(demand.get("importance") or demand.get("priority")).lower() or "medium"
        representation = _representation_requirement(demand)
        event_ids = _unique_strings(demand.get("caused_by_event_ids") or [])
        region_ids, event_entity_ids, mechanism_ids = _event_refs(
            event_ids, nodes_by_id, mechanisms_by_event_id
        )
        region_ids = _unique_strings(demand.get("jurisdiction_region_ids") or region_ids or foundation_regions)
        entity_ids = _unique_strings(demand.get("target_entity_ids") or event_entity_ids)
        mechanism_ids = _unique_strings(
            [*(demand.get("caused_by_mechanism_ids") or []), *mechanism_ids]
        )
        capabilities = _unique_strings(
            demand.get("required_capability_keys") or demand.get("required_capabilities") or []
        )
        rule = _DEMAND_RULES.get(demand_key)
        facility_classes = list(rule.facility_class_keys) if rule else _fallback_facility_classes(demand)
        required_resolution = _clean_text(demand.get("required_resolution")).lower()
        request_kind = rule.request_kind if rule else (
            "population_anchor_discovery"
            if required_resolution == "population_group"
            else ("facility_discovery" if representation == "facility_required" else "institution_discovery")
        )
        priority = _IMPORTANCE_PRIORITY.get(importance, 60)
        if entity_ids:
            priority = min(100, priority + 10)
        minimum_grade = _minimum_grade(importance, representation)
        r3_request_id = _stable_id(
            "spatial_request", "role_demand", demand_id or demand_key, "R3", region_ids, entity_ids, facility_classes
        )
        label = _clean_text(demand.get("label_zh")) or "场景角色空间证据"
        rationale = _clean_text(demand.get("rationale_zh"))
        requests.append(
            SpatialEvidenceRequest(
                request_id=r3_request_id,
                label_zh=f"{label}的设施与机构证据",
                request_kind=request_kind,
                resolution_level="R3",
                priority=priority,
                importance=importance,
                caused_by_event_ids=event_ids,
                caused_by_mechanism_ids=mechanism_ids,
                caused_by_role_demand_ids=[demand_id] if demand_id else [],
                required_capability_keys=capabilities,
                target_region_ids=region_ids,
                target_entity_ids=entity_ids,
                facility_class_keys=facility_classes,
                representation_requirement=(
                    "facility_required" if representation == "subunit_required" else representation
                ),
                minimum_evidence_grade=minimum_grade,
                allowed_source_kinds=sorted(_R3_SOURCE_KINDS),
                query_reason_zh=rationale or "场景机制要求先定位具备相应能力的真实设施或机构。",
                stop_conditions=_r3_stop_conditions(entity_ids, minimum_grade),
            )
        )

        r4_types = list(rule.r4_unit_type_keys) if rule else []
        needs_r4 = (
            bool(r4_types)
            or representation == "subunit_required"
            or required_resolution in {"r4", "population_group"}
        )
        if not needs_r4:
            continue
        if not r4_types:
            r4_types = [
                "population_segment"
                if request_kind == "population_anchor_discovery"
                else "facility_capability_unit"
            ]
        r4_request_id = _stable_id(
            "spatial_request", "role_demand", demand_id or demand_key, "R4", r3_request_id, r4_types
        )
        requests.append(
            SpatialEvidenceRequest(
                request_id=r4_request_id,
                label_zh=f"{label}的内部单元与细分群体模型",
                request_kind=(
                    "population_segment_model"
                    if request_kind == "population_anchor_discovery"
                    else "internal_unit_model"
                ),
                resolution_level="R4",
                priority=max(0, priority - 5),
                importance=importance,
                caused_by_event_ids=event_ids,
                caused_by_mechanism_ids=mechanism_ids,
                caused_by_role_demand_ids=[demand_id] if demand_id else [],
                required_capability_keys=capabilities,
                target_region_ids=region_ids,
                target_entity_ids=entity_ids,
                facility_class_keys=facility_classes,
                parent_r3_request_ids=[r3_request_id],
                representation_requirement="subunit_required",
                minimum_evidence_grade=minimum_grade,
                allowed_source_kinds=["authoritative", "user_supplied", "synthetic_model"],
                r4_unit_type_keys=r4_types,
                query_reason_zh=(
                    "只有在父级 R3 设施得到确认后，才能使用机构数据、用户资料或显式合成模型建立内部单元。"
                ),
                stop_conditions=[
                    "父级 R3 设施已经确认",
                    "每个 R4 单元均明确标记来源类型和假设，或形成明确建模缺口",
                ],
            )
        )

    # Stable priority ordering is part of the contract; explicit and critical
    # R3 evidence is resolved before lower-priority or R4 modelling requests.
    requests.sort(
        key=lambda item: (
            0 if item.resolution_level == "R3" else 1,
            0 if item.request_kind == "explicit_target_facility" else 1,
            -item.priority,
            item.request_id,
        )
    )
    role_demand_refs = _unique_strings(
        item.get("demand_id") or item.get("role_demand_id") for item in demands
    )
    graph_ref = {
        "graph_id": _clean_text(graph.get("graph_id")),
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
    assumptions = [
        "R3 请求用于确认真实设施和机构；R4 请求只能依附已确认的 R3 证据。",
        "synthetic_model 只表示显式建模假设，不能作为真实设施内部数据展示。",
    ]
    plan_seed = {
        "scenario_planning_ref": planning_ref,
        "event_mechanism_graph_ref": graph_ref,
        "effort_snapshot_ref": effort,
        "requests": [item.to_dict() for item in requests],
        "role_demand_refs": role_demand_refs,
        "assumptions": assumptions,
    }
    plan_id = _stable_id("facility_query_plan", plan_seed)
    payload_without_hash = {
        "contract_version": FACILITY_QUERY_PLAN_CONTRACT_VERSION,
        "plan_id": plan_id,
        **plan_seed,
        "required_r3_request_ids": [item.request_id for item in requests if item.resolution_level == "R3"],
        "required_r4_request_ids": [item.request_id for item in requests if item.resolution_level == "R4"],
        "content_hash": "",
    }
    plan = FacilityQueryPlan(
        plan_id=plan_id,
        scenario_planning_ref=planning_ref,
        event_mechanism_graph_ref=graph_ref,
        effort_snapshot_ref=effort,
        requests=requests,
        required_r3_request_ids=payload_without_hash["required_r3_request_ids"],
        required_r4_request_ids=payload_without_hash["required_r4_request_ids"],
        role_demand_refs=role_demand_refs,
        assumptions=assumptions,
        content_hash=_content_hash(payload_without_hash),
    )
    return plan


class MechanismAwareSpatialEvidenceCompiler:
    """Small injectable wrapper around :func:`compile_facility_query_plan`."""

    def compile(self, scenario: Any) -> FacilityQueryPlan:
        return compile_facility_query_plan(scenario)


__all__ = [
    "FACILITY_QUERY_PLAN_CONTRACT_VERSION",
    "SPATIAL_EVIDENCE_CONTRACT_VERSION",
    "SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION",
    "FacilityQueryPlan",
    "MechanismAwareSpatialEvidenceCompiler",
    "R4ModelUnit",
    "SpatialEvidenceRequest",
    "SpatialRefinementSnapshot",
    "build_spatial_refinement_snapshot",
    "compile_facility_query_plan",
    "normalize_spatial_catalog_candidate",
]
