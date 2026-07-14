"""Step 2 scenario planning contracts and deterministic fallback planner.

This module intentionally stops at the Agent planning boundary.  It turns the
user's event and policy intent into a versioned scenario-planning artifact, then
exposes a small port consumed by the Agent V2 evidence-placement planner.  The
legacy projection remains available only for frozen artifacts and explicit
compatibility checks.  Agent profile generation and runtime behaviour remain
owned by the Agent subsystem.

The planner is deterministic and network-free so that it can also serve as the
honest fallback when an LLM-based planner is unavailable.  Generated display
text is Simplified Chinese; machine-facing keys remain stable English enums.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable


SCENARIO_PLANNING_CONTRACT_VERSION = "scenario_planning.v2"
SIMULATION_ARCHITECTURE = "llm_mechanism_v1"
LEGACY_SEARCH_MODE = "deep_search"
LEGACY_AGENT_PLAN_SOURCE = "legacy_adapter"
AGENT_V2_PLAN_SOURCE = "agent_v2"


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


def _normalize_id_list(value: Any, field_label: str) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_label}必须使用数组格式")
    return _unique_strings(value)


def _canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(_canonical_json(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _as_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        return dict(converted) if isinstance(converted, Mapping) else {}
    return {}


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_score(value: Any, default: float = 65.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(100.0, parsed)), 2)


@dataclass(frozen=True)
class UserEventInput:
    input_id: str
    name: str
    description: str
    order: int
    target_region_ids: List[str] = field(default_factory=list)
    target_entity_ids: List[str] = field(default_factory=list)
    atomic_keys: List[str] = field(default_factory=list)
    open_concept: str = ""
    expected_effects: List[str] = field(default_factory=list)
    intensity_score: Optional[float] = None
    intensity_direction: str = ""
    intensity_label_zh: str = ""
    start_round: Optional[int] = None
    duration_rounds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UserPolicyInput:
    input_id: str
    name: str
    intent: str
    order: int = 1
    target_region_ids: List[str] = field(default_factory=list)
    target_entity_ids: List[str] = field(default_factory=list)
    action_primitives: List[str] = field(default_factory=list)
    executor_capability_keys: List[str] = field(default_factory=list)
    expected_effects: List[str] = field(default_factory=list)
    target_event_keys: List[str] = field(default_factory=list)
    intensity_score: Optional[float] = None
    intensity_direction: str = ""
    intensity_label_zh: str = ""
    start_round: Optional[int] = None
    duration_rounds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EventMechanismGraph:
    graph_id: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    primary_event_ids: List[str]
    branching_event_ids: List[str]
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TemporalPlan:
    plan_id: str
    step_unit: str
    step_unit_label_zh: str
    step_value: int
    total_rounds: int
    coverage_label_zh: str
    event_windows: List[Dict[str, Any]]
    policy_windows: List[Dict[str, Any]]
    generation_reason_zh: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioPlanningInput:
    contract_version: str
    planning_input_id: str
    revision: int
    foundation_ref: Dict[str, Any]
    effort_snapshot_ref: Dict[str, Any]
    normalized_user_events: List[Dict[str, Any]]
    normalized_user_policies: List[Dict[str, Any]]
    event_mechanism_graph: Dict[str, Any]
    temporal_plan: Dict[str, Any]
    policy_plan: List[Dict[str, Any]]
    role_demands: List[Dict[str, Any]]
    assumptions: List[str]
    semantic_artifact_ref: Dict[str, Any] = field(default_factory=dict)
    simulation_architecture: str = SIMULATION_ARCHITECTURE
    compatibility: Dict[str, Any] = field(
        default_factory=lambda: {
            "search_mode": LEGACY_SEARCH_MODE,
            "hazard_template_id": "generic",
            "说明": "兼容字段不参与新场景规划。",
        }
    )
    agent_planning_contract: Dict[str, Any] = field(
        default_factory=lambda: {
            "port": "AgentPlanningPort",
            "current_adapter": AGENT_V2_PLAN_SOURCE,
            "说明": "Step 2 仅输出角色能力需求，具体 Agent 由 Agent 模块规划。",
        }
    )
    content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@runtime_checkable
class AgentPlanningPort(Protocol):
    """Boundary consumed by Step 2 without owning Agent generation."""

    def plan(self, scenario: ScenarioPlanningInput | Mapping[str, Any]) -> Dict[str, Any]:
        """Return an Agent planning result or a request for an external generator."""


class LegacyAgentPlanningAdapter:
    """Project the new Step 2 contract into the existing generator's input shape.

    The adapter deliberately does not invoke the existing generator.  Its result
    is a transport contract and carries an explicit source marker, making the
    future Agent V2 replacement a single-port change.
    """

    adapter_key = LEGACY_AGENT_PLAN_SOURCE

    def plan(self, scenario: ScenarioPlanningInput | Mapping[str, Any]) -> Dict[str, Any]:
        payload = scenario.to_dict() if isinstance(scenario, ScenarioPlanningInput) else dict(scenario)
        events = list(payload.get("normalized_user_events") or [])
        policies = list(payload.get("normalized_user_policies") or [])
        temporal_plan = dict(payload.get("temporal_plan") or {})
        event_graph = dict(payload.get("event_mechanism_graph") or {})

        injected_variables: List[Dict[str, Any]] = []
        windows_by_event = {
            str(item.get("event_id")): item for item in (temporal_plan.get("event_windows") or [])
        }
        graph_nodes_by_input: Dict[str, List[Dict[str, Any]]] = {}
        for node in event_graph.get("nodes") or []:
            graph_nodes_by_input.setdefault(str(node.get("source_input_id") or ""), []).append(node)

        for index, event in enumerate(events, start=1):
            source_nodes = graph_nodes_by_input.get(str(event.get("input_id") or ""), [])
            first_window = windows_by_event.get(str(source_nodes[0].get("event_id"))) if source_nodes else None
            injected_variables.append(
                {
                    "variable_id": str(event.get("input_id") or f"event_{index}"),
                    "type": "disaster",
                    "template": self._legacy_template(source_nodes),
                    "name": event.get("name") or f"灾害事件 {index}",
                    "description": event.get("description") or "",
                    "target_regions": list(event.get("target_region_ids") or []),
                    "target_nodes": list(event.get("target_entity_ids") or []),
                    "start_round": int((first_window or {}).get("start_round") or 0),
                    "duration_rounds": int((first_window or {}).get("duration_rounds") or 1),
                    "intensity_0_100": self._legacy_intensity(source_nodes),
                    "source_origin": "manual",
                }
            )

        policy_plan_by_id = {
            str(item.get("source_input_id") or ""): item for item in (payload.get("policy_plan") or [])
        }
        for index, policy in enumerate(policies, start=1):
            planned = policy_plan_by_id.get(str(policy.get("input_id") or ""), {})
            injected_variables.append(
                {
                    "variable_id": str(policy.get("input_id") or f"policy_{index}"),
                    "type": "policy",
                    "template": "generic",
                    "name": policy.get("name") or f"政策措施 {index}",
                    "description": policy.get("intent") or "",
                    "target_regions": list(policy.get("target_region_ids") or []),
                    "target_nodes": list(policy.get("target_entity_ids") or []),
                    "start_round": int(planned.get("start_round") or 0),
                    "duration_rounds": int(planned.get("duration_rounds") or 1),
                    "intensity_0_100": 60,
                    "policy_mode": self._legacy_policy_mode(planned),
                    "source_origin": "manual",
                }
            )

        summary_parts = [str(item.get("name") or "") for item in events]
        summary_parts.extend(str(item.get("name") or "") for item in policies)
        role_demand_parts = []
        for item in payload.get("role_demands") or []:
            label = str(item.get("label_zh") or "").strip()
            if not label:
                continue
            capabilities = "、".join(str(value) for value in (item.get("required_capability_keys") or []))
            jurisdictions = "、".join(str(value) for value in (item.get("jurisdiction_region_ids") or []))
            detail = [
                f"能力键 {capabilities}" if capabilities else "",
                f"辖区 {jurisdictions}" if jurisdictions else "",
                f"分辨率 {item.get('required_resolution')}" if item.get("required_resolution") else "",
            ]
            role_demand_parts.append(
                f"{label}（{'；'.join(value for value in detail if value)}）"
                if any(detail)
                else label
            )
        requirement = "；".join(part for part in summary_parts if part)
        if role_demand_parts:
            requirement = f"{requirement}。需要覆盖的角色能力：{'、'.join(role_demand_parts)}".lstrip("。")
        propagation_media = {
            str(edge.get("propagation_medium") or "")
            for edge in (event_graph.get("edges") or [])
            if str(edge.get("propagation_medium") or "") in {"marine_current", "atmospheric_plume"}
        }
        projection_warnings = []
        if len(propagation_media) > 1:
            projection_warnings.append(
                "旧版生成器只能接收一个兼容模板；正式机制图仍保留海洋与大气等全部传播分支。"
            )
        return {
            "agent_plan_source": self.adapter_key,
            "adapter_contract_version": "agent_planning_port.v1",
            "status": "等待旧版代理体生成器处理",
            "simulation_architecture": SIMULATION_ARCHITECTURE,
            "search_mode": LEGACY_SEARCH_MODE,
            "simulation_requirement": requirement,
            "injected_variables": injected_variables,
            "role_demands": list(payload.get("role_demands") or []),
            "effort_profile": dict(payload.get("effort_snapshot_ref") or {}),
            "projection_warnings": projection_warnings,
            "scenario_planning_ref": {
                "planning_input_id": payload.get("planning_input_id") or "",
                "content_hash": payload.get("content_hash") or "",
            },
        }

    @staticmethod
    def _legacy_template(nodes: Sequence[Mapping[str, Any]]) -> str:
        atomic_keys = {str(item.get("atomic_key") or "") for item in nodes}
        families = {str(item.get("hazard_family") or "") for item in nodes}
        # Project only an explicitly planned propagation medium.  A radioactive
        # release by itself must not be silently reinterpreted as marine spread.
        if "marine_spread" in atomic_keys or "marine" in families:
            return "marine"
        if "air_spread" in atomic_keys or "atmospheric" in families:
            return "air"
        if "flood" in atomic_keys or "hydrological" in families:
            return "inland_water"
        if "typhoon" in atomic_keys or "strong_wind" in atomic_keys or "heavy_rain" in atomic_keys or "meteorological" in families:
            return "air"
        return "generic"

    @staticmethod
    def _legacy_intensity(nodes: Sequence[Mapping[str, Any]]) -> float:
        scores = [
            _bounded_score((item.get("intensity") or {}).get("score"), 65)
            for item in nodes
            if isinstance(item.get("intensity"), Mapping)
        ]
        return round(sum(scores) / len(scores), 2) if scores else 65.0

    @staticmethod
    def _legacy_policy_mode(policy: Mapping[str, Any]) -> str:
        primitives = set(policy.get("effect_primitives") or [])
        if "population_relocation" in primitives:
            return "relocate"
        if "economic_compensation" in primitives:
            return "subsidize"
        if "environmental_monitoring" in primitives:
            return "monitor"
        if primitives.intersection({
            "activity_restriction",
            "school_closure",
            "workplace_shutdown",
            "transport_restriction",
            "shelter_in_place",
        }):
            return "restrict"
        if "resource_dispatch" in primitives:
            return "dispatch"
        if "infrastructure_repair" in primitives:
            return "repair"
        return "disclose"


class AgentV2PlanningAdapter(LegacyAgentPlanningAdapter):
    """Submit RoleDemand to Agent V2 while keeping runtime compatibility data.

    The injected-variable projection is transport-only.  Agent identity, count,
    placement, capabilities and initial relationships are produced later by
    ``AgentPlannerV2`` from role demands and spatial evidence.
    """

    adapter_key = AGENT_V2_PLAN_SOURCE

    def plan(self, scenario: ScenarioPlanningInput | Mapping[str, Any]) -> Dict[str, Any]:
        result = super().plan(scenario)
        result.update(
            {
                "agent_plan_source": self.adapter_key,
                "adapter_contract_version": "agent_planning_port.v2",
                "agent_plan_contract_version": "agent-plan.v2",
                "planning_mode": "role_demand_evidence_placement",
                "status": "角色需求已提交，等待空间证据匹配",
                "projection_warnings": [],
            }
        )
        return result


@dataclass(frozen=True)
class _EventSpec:
    key: str
    label_zh: str
    event_kind: str
    hazard_family: str
    keywords: Tuple[str, ...]
    default_score: float


_EVENT_SPECS: Tuple[_EventSpec, ...] = (
    _EventSpec("typhoon", "台风影响", "natural_hazard", "meteorological", ("台风", "热带气旋", "热带风暴", "飓风", "风球", "袭港"), 78),
    _EventSpec("strong_wind", "持续强风影响", "hazard_propagation", "meteorological", ("强风", "烈风", "暴风", "阵风", "风球"), 74),
    _EventSpec("heavy_rain", "强降雨过程", "natural_hazard", "meteorological", ("暴雨", "强降雨", "极端降雨"), 74),
    _EventSpec("earthquake", "地震冲击", "natural_hazard", "geological", ("地震", "强震"), 78),
    _EventSpec("tsunami", "海啸冲击", "secondary_hazard", "marine", ("海啸",), 82),
    _EventSpec("landslide", "滑坡与崩塌", "secondary_hazard", "geological", ("滑坡", "崩塌", "山体垮塌"), 74),
    _EventSpec("liquefaction", "地基液化", "secondary_hazard", "geological", ("液化", "地基失稳"), 72),
    _EventSpec("secondary_fire", "次生火灾", "secondary_hazard", "fire", ("次生火灾", "震后火灾"), 76),
    _EventSpec("storm_surge", "风暴潮与沿海淹没", "secondary_hazard", "hydrological", ("风暴潮", "沿海淹没", "海水倒灌"), 76),
    _EventSpec("flood", "洪水与积涝", "secondary_hazard", "hydrological", ("洪水", "内涝", "积涝"), 72),
    _EventSpec("facility_ingress", "关键设施进水", "infrastructure_failure", "infrastructure", ("进水", "淹水", "水淹"), 72),
    _EventSpec("power_loss", "外部电源中断", "infrastructure_failure", "infrastructure", ("断电", "电源失效", "电力中断", "失去外部电源"), 76),
    _EventSpec("cooling_failure", "冷却系统失效", "infrastructure_failure", "infrastructure", ("冷却失效", "冷却系统失效", "失去冷却"), 82),
    _EventSpec("chemical_release", "有毒化学物质释放", "hazardous_release", "chemical", ("化学品泄漏", "有毒物质释放", "有毒气体泄漏"), 78),
    _EventSpec("radioactive_release", "放射性物质释放", "hazardous_release", "radiological", ("放射性释放", "放射性物质", "核泄漏", "核电站泄漏", "辐射泄漏"), 86),
    _EventSpec("marine_spread", "污染物海洋传播", "hazard_propagation", "marine", ("海洋传播", "海流传播", "近海扩散", "通过海洋", "海洋和大气", "海洋及大气"), 70),
    _EventSpec("air_spread", "污染物大气传播", "hazard_propagation", "atmospheric", ("大气传播", "空气传播", "羽流扩散", "通过大气", "海洋和大气", "海洋及大气"), 72),
    _EventSpec("river_spread", "污染物河流传播", "hazard_propagation", "river", ("河流传播", "沿河扩散", "进入河道", "通过河流"), 70),
    _EventSpec("surface_spread", "污染物地表传播", "hazard_propagation", "surface", ("地表传播", "地表径流", "土壤扩散", "地表扩散"), 68),
    _EventSpec("human_exposure", "受影响人群", "impact", "public_health", ("人群暴露", "居民暴露", "辐射暴露", "人员中毒"), 70),
    _EventSpec("ecological_impact", "敏感生态系统", "impact", "ecological", ("生态影响", "生态受损", "生态风险"), 68),
    _EventSpec(
        "resource_contamination",
        "渔业水域与食品供应链",
        "impact",
        "resource_supply",
        ("海产品污染", "水产品污染", "渔业污染", "食品污染", "饮用水污染"),
        72,
    ),
    _EventSpec("medical_pressure", "医疗服务系统", "system_pressure", "public_health", ("医疗压力", "医院承压", "医疗挤兑", "救治压力"), 72),
    _EventSpec("traffic_pressure", "交通与疏散系统", "system_pressure", "mobility", ("交通压力", "交通中断", "疏散拥堵", "道路中断"), 70),
    _EventSpec("supply_pressure", "关键物资供应体系", "system_pressure", "supply", ("供应压力", "物资短缺", "供应中断", "能源短缺"), 70),
    _EventSpec("governance_pressure", "应急治理与跨部门协同体系", "system_pressure", "governance", ("治理压力", "应急协调压力", "政府承压", "跨部门协调"), 68),
)

_SPEC_BY_KEY = {item.key: item for item in _EVENT_SPECS}


_PAIR_MECHANISMS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("typhoon", "strong_wind"): {
        "primitive_key": "typhoon_wind_field",
        "propagation_medium": "atmospheric_wind_field",
        "trigger_conditions": ["热带气旋风场使场景区域持续出现烈风或暴风"],
        "latency_rounds": 0,
        "duration_rounds": 3,
        "attenuation": 0.94,
        "label_zh": "台风风场形成持续强风",
    },
    ("typhoon", "storm_surge"): {
        "primitive_key": "coastal_inundation",
        "propagation_medium": "coastal_water",
        "trigger_conditions": ["台风风场和低气压共同推高近岸水位"],
        "latency_rounds": 1,
        "duration_rounds": 3,
        "attenuation": 0.88,
        "label_zh": "台风驱动风暴潮",
    },
    ("typhoon", "facility_ingress"): {
        "primitive_key": "extreme_weather_facility_impact",
        "propagation_medium": "coastal_surface",
        "trigger_conditions": ["极端风雨或增水超过设施防护能力"],
        "latency_rounds": 1,
        "duration_rounds": 2,
        "attenuation": 0.86,
        "label_zh": "极端天气冲击关键设施",
    },
    ("strong_wind", "traffic_pressure"): {
        "primitive_key": "wind_mobility_disruption",
        "propagation_medium": "transport_network",
        "trigger_conditions": ["持续强风超过道路、桥梁、轮渡或公共交通的安全运行条件"],
        "latency_rounds": 0,
        "duration_rounds": 3,
        "attenuation": 0.9,
        "label_zh": "持续强风降低交通与疏散能力",
    },
    ("heavy_rain", "flood"): {
        "primitive_key": "rainfall_runoff_accumulation",
        "propagation_medium": "surface_water",
        "trigger_conditions": ["降雨强度超过排水和地表滞蓄能力"],
        "latency_rounds": 1,
        "duration_rounds": 3,
        "attenuation": 0.9,
        "label_zh": "强降雨形成洪涝",
    },
    ("earthquake", "tsunami"): {
        "primitive_key": "seismic_tsunami_generation",
        "propagation_medium": "marine_wave",
        "trigger_conditions": ["海底或近海地震造成显著水体位移"],
        "latency_rounds": 1,
        "duration_rounds": 2,
        "attenuation": 0.9,
        "label_zh": "地震触发海啸",
    },
    ("earthquake", "landslide"): {
        "primitive_key": "seismic_slope_failure",
        "propagation_medium": "ground_motion",
        "trigger_conditions": ["地震动超过边坡稳定阈值"],
        "latency_rounds": 0,
        "duration_rounds": 2,
        "attenuation": 0.86,
        "label_zh": "地震触发滑坡崩塌",
    },
    ("earthquake", "liquefaction"): {
        "primitive_key": "seismic_soil_liquefaction",
        "propagation_medium": "ground_motion",
        "trigger_conditions": ["饱和松散土层在强震下失稳"],
        "latency_rounds": 0,
        "duration_rounds": 2,
        "attenuation": 0.88,
        "label_zh": "地震触发地基液化",
    },
    ("earthquake", "secondary_fire"): {
        "primitive_key": "seismic_secondary_fire",
        "propagation_medium": "infrastructure_damage",
        "trigger_conditions": ["燃气、电气或易燃设施在震动中破坏"],
        "latency_rounds": 1,
        "duration_rounds": 4,
        "attenuation": 0.84,
        "label_zh": "地震损伤引发次生火灾",
    },
    ("storm_surge", "facility_ingress"): {
        "primitive_key": "coastal_water_ingress",
        "propagation_medium": "coastal_water",
        "trigger_conditions": ["外部水位超过设施防洪边界"],
        "latency_rounds": 0,
        "duration_rounds": 3,
        "attenuation": 0.92,
        "label_zh": "沿海淹没导致设施进水",
    },
    ("storm_surge", "ecological_impact"): {
        "primitive_key": "storm_surge_wetland_disturbance",
        "propagation_medium": "coastal_ecosystem",
        "trigger_conditions": ["沿海增水和高能波浪进入潮间带、湿地或其他敏感生态空间"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.86,
        "label_zh": "风暴潮扰动沿海湿地生态受体",
    },
    ("tsunami", "facility_ingress"): {
        "primitive_key": "coastal_water_ingress",
        "propagation_medium": "coastal_water",
        "trigger_conditions": ["海啸水位和冲击超过设施防护边界"],
        "latency_rounds": 0,
        "duration_rounds": 2,
        "attenuation": 0.9,
        "label_zh": "海啸导致设施进水",
    },
    ("flood", "facility_ingress"): {
        "primitive_key": "surface_flood_ingress",
        "propagation_medium": "surface_water",
        "trigger_conditions": ["积水深度超过设施入口或排水能力"],
        "latency_rounds": 0,
        "duration_rounds": 3,
        "attenuation": 0.9,
        "label_zh": "洪涝导致设施进水",
    },
    ("facility_ingress", "power_loss"): {
        "primitive_key": "water_intrusion_power_failure",
        "propagation_medium": "infrastructure_dependency",
        "trigger_conditions": ["进水影响供电设备、配电系统或备用电源"],
        "latency_rounds": 1,
        "duration_rounds": 4,
        "attenuation": 0.94,
        "label_zh": "进水导致供电失效",
    },
    ("facility_ingress", "cooling_failure"): {
        "primitive_key": "water_intrusion_cooling_failure",
        "propagation_medium": "infrastructure_dependency",
        "trigger_conditions": ["进水影响冷却设备或其支持系统"],
        "latency_rounds": 1,
        "duration_rounds": 4,
        "attenuation": 0.92,
        "label_zh": "进水导致冷却能力下降",
    },
    ("power_loss", "cooling_failure"): {
        "primitive_key": "power_dependent_cooling_loss",
        "propagation_medium": "energy_dependency",
        "trigger_conditions": ["冷却系统失去持续可靠电源"],
        "latency_rounds": 0,
        "duration_rounds": 4,
        "attenuation": 0.96,
        "label_zh": "断电导致冷却失效",
    },
    ("power_loss", "radioactive_release"): {
        "primitive_key": "loss_of_safety_functions",
        "propagation_medium": "facility_safety_system",
        "trigger_conditions": ["供电恢复失败并削弱关键安全功能"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.88,
        "label_zh": "安全功能丧失增加释放风险",
    },
    ("cooling_failure", "radioactive_release"): {
        "primitive_key": "thermal_control_failure_release",
        "propagation_medium": "facility_safety_system",
        "trigger_conditions": ["冷却能力持续不足并突破安全屏障"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.92,
        "label_zh": "冷却失效导致放射性释放",
    },
    ("radioactive_release", "marine_spread"): {
        "primitive_key": "marine_dispersion",
        "propagation_medium": "marine_current",
        "trigger_conditions": ["放射性物质进入近岸水体"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.9,
        "label_zh": "放射性物质随海流传播",
    },
    ("chemical_release", "marine_spread"): {
        "primitive_key": "marine_dispersion",
        "propagation_medium": "marine_current",
        "trigger_conditions": ["污染物进入近岸水体"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.88,
        "label_zh": "污染物随海流传播",
    },
    ("radioactive_release", "air_spread"): {
        "primitive_key": "atmospheric_dispersion",
        "propagation_medium": "atmospheric_plume",
        "trigger_conditions": ["放射性物质以气溶胶或气体形式进入大气"],
        "latency_rounds": 0,
        "duration_rounds": 5,
        "attenuation": 0.84,
        "label_zh": "放射性物质随大气传播",
    },
    ("chemical_release", "air_spread"): {
        "primitive_key": "atmospheric_dispersion",
        "propagation_medium": "atmospheric_plume",
        "trigger_conditions": ["挥发性或颗粒态污染物进入大气"],
        "latency_rounds": 0,
        "duration_rounds": 4,
        "attenuation": 0.82,
        "label_zh": "污染物随大气传播",
    },
    ("radioactive_release", "river_spread"): {
        "primitive_key": "river_network_dispersion",
        "propagation_medium": "river_flow",
        "trigger_conditions": ["放射性物质进入河流或排水网络"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.87,
        "label_zh": "放射性物质沿河传播",
    },
    ("chemical_release", "river_spread"): {
        "primitive_key": "river_network_dispersion",
        "propagation_medium": "river_flow",
        "trigger_conditions": ["化学污染物进入河流或排水网络"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.86,
        "label_zh": "化学污染物沿河传播",
    },
    ("radioactive_release", "surface_spread"): {
        "primitive_key": "surface_runoff_dispersion",
        "propagation_medium": "surface_runoff",
        "trigger_conditions": ["沉降物经降雨和地表径流迁移"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.82,
        "label_zh": "放射性沉降物经地表迁移",
    },
    ("chemical_release", "surface_spread"): {
        "primitive_key": "surface_runoff_dispersion",
        "propagation_medium": "surface_runoff",
        "trigger_conditions": ["泄漏物进入地表径流或土壤"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.82,
        "label_zh": "化学污染物经地表迁移",
    },
    ("air_spread", "human_exposure"): {
        "primitive_key": "inhalation_exposure",
        "propagation_medium": "human_contact",
        "trigger_conditions": ["污染羽流覆盖人口活动区域"],
        "latency_rounds": 0,
        "duration_rounds": 4,
        "attenuation": 0.9,
        "label_zh": "大气传播造成人群暴露",
    },
    ("marine_spread", "human_exposure"): {
        "primitive_key": "marine_contact_exposure",
        "propagation_medium": "human_contact",
        "trigger_conditions": ["海洋污染物通过近岸活动、饮食或接触路径作用于人群"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.86,
        "label_zh": "海洋传播造成人群暴露",
    },
    ("marine_spread", "ecological_impact"): {
        "primitive_key": "marine_ecosystem_exposure",
        "propagation_medium": "marine_ecosystem",
        "trigger_conditions": ["污染带进入湿地、近岸水体或其他敏感生态受体"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.88,
        "label_zh": "海洋传播影响生态受体",
    },
    ("marine_spread", "resource_contamination"): {
        "primitive_key": "marine_food_chain_contamination",
        "propagation_medium": "marine_food_chain",
        "trigger_conditions": ["海洋污染物进入渔业水域或水产品食物链"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.86,
        "label_zh": "海洋传播污染渔业与食品资源",
    },
    ("marine_spread", "traffic_pressure"): {
        "primitive_key": "marine_incident_mobility_control",
        "propagation_medium": "mobility_control",
        "trigger_conditions": ["污染边界、监测或应急管制影响港口、机场及疏散通道运行"],
        "latency_rounds": 1,
        "duration_rounds": 4,
        "attenuation": 0.82,
        "label_zh": "海洋污染事件推高交通与疏散压力",
    },
    ("marine_spread", "governance_pressure"): {
        "primitive_key": "marine_incident_governance_coordination",
        "propagation_medium": "governance_coordination",
        "trigger_conditions": ["跨区域污染监测、管制和信息发布需要多部门协同"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.88,
        "label_zh": "海洋污染事件增加跨部门治理压力",
    },
    ("river_spread", "ecological_impact"): {
        "primitive_key": "river_ecosystem_exposure",
        "propagation_medium": "aquatic_ecosystem",
        "trigger_conditions": ["污染带进入敏感河流生态受体"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.86,
        "label_zh": "河流传播影响生态受体",
    },
    ("river_spread", "human_exposure"): {
        "primitive_key": "river_contact_exposure",
        "propagation_medium": "human_contact",
        "trigger_conditions": ["受污染河段与居民取水、生产或日常接触路径相交"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.84,
        "label_zh": "河流传播造成人群暴露",
    },
    ("river_spread", "resource_contamination"): {
        "primitive_key": "river_resource_contamination",
        "propagation_medium": "water_resource_network",
        "trigger_conditions": ["污染带进入饮用水、灌溉或淡水渔业资源"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.84,
        "label_zh": "河流传播污染水与食品资源",
    },
    ("surface_spread", "ecological_impact"): {
        "primitive_key": "terrestrial_ecosystem_exposure",
        "propagation_medium": "terrestrial_ecosystem",
        "trigger_conditions": ["污染物进入土壤、农田或陆地栖息地"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.84,
        "label_zh": "地表传播影响生态受体",
    },
    ("surface_spread", "human_exposure"): {
        "primitive_key": "surface_contact_exposure",
        "propagation_medium": "human_contact",
        "trigger_conditions": ["地表污染进入居民活动、生产或扬尘接触路径"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.82,
        "label_zh": "地表传播造成人群暴露",
    },
    ("surface_spread", "resource_contamination"): {
        "primitive_key": "surface_resource_contamination",
        "propagation_medium": "food_resource_network",
        "trigger_conditions": ["地表污染进入农田、水源或食品生产环节"],
        "latency_rounds": 1,
        "duration_rounds": 6,
        "attenuation": 0.82,
        "label_zh": "地表传播污染水与食品资源",
    },
    ("human_exposure", "medical_pressure"): {
        "primitive_key": "exposure_healthcare_demand",
        "propagation_medium": "healthcare_system",
        "trigger_conditions": ["暴露人群的筛查、转运和救治需求集中增加"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.92,
        "label_zh": "人群暴露推高医疗压力",
    },
    ("traffic_pressure", "supply_pressure"): {
        "primitive_key": "mobility_supply_disruption",
        "propagation_medium": "logistics_network",
        "trigger_conditions": ["道路中断或疏散拥堵影响关键物资运输"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.88,
        "label_zh": "交通受阻传导至物资供应",
    },
    ("supply_pressure", "governance_pressure"): {
        "primitive_key": "resource_coordination_pressure",
        "propagation_medium": "governance_coordination",
        "trigger_conditions": ["稀缺资源需要跨部门调配并出现竞争"],
        "latency_rounds": 1,
        "duration_rounds": 5,
        "attenuation": 0.9,
        "label_zh": "供应压力增加治理协调负担",
    },
}


_POLICY_RULES: Tuple[Dict[str, Any], ...] = (
    {
        "keywords": ("疏散", "撤离", "转移安置"),
        "effect_primitives": ["population_relocation", "exposure_reduction"],
        "capabilities": ["emergency_command", "evacuation_coordination", "transport_dispatch"],
        "expected_effects": ["降低高风险区域的人群暴露", "改善脆弱人群的转移效率"],
        "side_effects": ["短期交通和安置资源压力上升", "部分居民可能出现生计中断"],
    },
    {
        "keywords": ("监测", "检测", "采样", "预警"),
        "effect_primitives": ["environmental_monitoring", "risk_early_warning"],
        "capabilities": ["environmental_monitoring", "radiation_monitoring", "data_analysis"],
        "expected_effects": ["提高风险边界和传播方向的可见性", "为管控和公众沟通提供依据"],
        "side_effects": ["增加采样、实验室和信息处理负荷"],
    },
    {
        "keywords": ("禁捕", "渔业限制", "暂停捕捞", "捕捞限制"),
        "effect_primitives": ["activity_restriction", "food_chain_exposure_reduction"],
        "capabilities": ["regulatory_enforcement", "fisheries_management", "public_information"],
        "expected_effects": ["降低污染水产品进入市场的概率", "减少渔业活动造成的持续暴露"],
        "side_effects": ["渔民和相关经营主体的收入短期下降"],
    },
    {
        "keywords": ("补偿", "补贴", "赔偿", "救助"),
        "effect_primitives": ["economic_compensation", "livelihood_stabilization"],
        "capabilities": ["compensation_administration", "fiscal_resource_allocation", "beneficiary_verification"],
        "expected_effects": ["缓解受影响群体的生计和经营压力", "提高限制措施的可执行性"],
        "side_effects": ["增加财政支出和资格审核负担"],
    },
    {
        "keywords": ("修复", "抢修", "恢复供电", "恢复冷却"),
        "effect_primitives": ["infrastructure_repair", "response_capacity_recovery"],
        "capabilities": ["infrastructure_repair", "facility_emergency_operation", "resource_dispatch"],
        "expected_effects": ["恢复关键设施功能", "降低事故继续升级的概率"],
        "side_effects": ["抢修人员可能面临额外暴露和作业风险"],
    },
    {
        "keywords": ("通报", "公开", "信息发布", "风险沟通"),
        "effect_primitives": ["public_information", "risk_communication"],
        "capabilities": ["public_information", "risk_communication", "data_validation"],
        "expected_effects": ["减少信息不对称并支持公众采取防护行动"],
        "side_effects": ["信息不完整或表述不当可能加剧恐慌"],
    },
)

_SEMANTIC_POLICY_RULES: Dict[str, Dict[str, Any]] = {
    "school_closure": {
        "effect_primitives": ["school_closure", "exposure_reduction"],
        "capabilities": ["education_emergency_management", "school_closure_execution", "student_safety_communication"],
        "expected_effects": ["降低学生集中活动和通勤暴露", "为学校和家庭提供一致的安全安排"],
        "side_effects": ["家庭照护和远程教学压力上升"],
    },
    "workplace_shutdown": {
        "effect_primitives": ["workplace_shutdown", "exposure_reduction"],
        "capabilities": ["workplace_safety_enforcement", "business_continuity_coordination", "labor_communication"],
        "expected_effects": ["降低工作场所聚集与通勤压力", "减少高风险岗位暴露"],
        "side_effects": ["企业经营和劳动收入短期承压"],
    },
    "transport_restriction": {
        "effect_primitives": ["transport_restriction", "mobility_reduction"],
        "capabilities": ["traffic_control", "transport_dispatch", "public_information"],
        "expected_effects": ["减少高风险交通活动", "保障应急和疏散通道"],
        "side_effects": ["部分区域可达性和物流效率下降"],
    },
    "shelter_in_place": {
        "effect_primitives": ["shelter_in_place", "exposure_reduction"],
        "capabilities": ["public_safety_guidance", "community_coordination", "public_information"],
        "expected_effects": ["减少户外暴露并稳定社区行动"],
        "side_effects": ["独居者和脆弱群体需要额外保障"],
    },
    "evacuation": dict(_POLICY_RULES[0]),
    "environmental_monitoring": dict(_POLICY_RULES[1]),
    "activity_restriction": dict(_POLICY_RULES[2]),
    "economic_compensation": dict(_POLICY_RULES[3]),
    "infrastructure_repair": dict(_POLICY_RULES[4]),
    "information_release": dict(_POLICY_RULES[5]),
    "resource_dispatch": {
        "effect_primitives": ["resource_dispatch", "response_capacity_recovery"],
        "capabilities": ["resource_dispatch", "inventory_allocation", "logistics_dispatch"],
        "expected_effects": ["补充关键资源并提高响应能力"],
        "side_effects": ["跨区域调配可能形成新的供应压力"],
    },
    "governance_intervention": {
        "effect_primitives": ["governance_intervention"],
        "capabilities": ["policy_coordination", "public_information"],
        "expected_effects": ["按照用户意图调整场景响应能力"],
        "side_effects": ["具体副作用取决于执行主体、资源和实施范围"],
    },
}


class ScenarioPlanner:
    """Build the Step 2 scenario-planning artifact without generating Agents."""

    def build_from_payload(
        self,
        foundation: Optional[Mapping[str, Any]],
        payload: Optional[Mapping[str, Any]],
        effort_snapshot_ref: Optional[Mapping[str, Any] | str] = None,
    ) -> ScenarioPlanningInput:
        """Route a prepare-style payload through the new or legacy input contract.

        Presence of either new input key is intentional: an explicitly empty
        ``event_inputs`` list must not unexpectedly revive stale legacy variables.
        """

        raw = dict(payload or {})
        resolved_effort = effort_snapshot_ref
        if resolved_effort is None:
            resolved_effort = raw.get("effort_snapshot_ref") or raw.get("effort_snapshot_id")
        overrides = raw.get("advanced_overrides") if isinstance(raw.get("advanced_overrides"), Mapping) else {}
        if "event_inputs" in raw or "policy_inputs" in raw:
            return self.build(
                foundation=foundation,
                effort_snapshot_ref=resolved_effort,
                user_events=raw.get("event_inputs") or [],
                user_policies=raw.get("policy_inputs") or [],
                advanced_overrides=overrides,
                semantic_artifact_ref=raw.get("semantic_artifact_ref"),
            )
        return self.build_from_legacy(
            foundation=foundation,
            effort_snapshot_ref=resolved_effort,
            injected_variables=raw.get("injected_variables") or [],
            advanced_overrides=overrides,
        )

    def build(
        self,
        foundation: Optional[Mapping[str, Any]],
        effort_snapshot_ref: Optional[Mapping[str, Any] | str],
        user_events: Optional[Sequence[UserEventInput | Mapping[str, Any]]],
        user_policies: Optional[Sequence[UserPolicyInput | Mapping[str, Any]]],
        advanced_overrides: Optional[Mapping[str, Any]] = None,
        semantic_artifact_ref: Optional[Mapping[str, Any]] = None,
    ) -> ScenarioPlanningInput:
        foundation_ref = self._normalize_foundation_ref(foundation)
        effort_ref, effort_assumptions = self._normalize_effort_ref(effort_snapshot_ref)
        events = self.normalize_user_events(user_events or [])
        policies = self.normalize_user_policies(user_policies or [])
        assumptions: List[str] = list(effort_assumptions)

        graph, graph_assumptions = self._build_event_graph(events, foundation_ref, advanced_overrides or {})
        assumptions.extend(graph_assumptions)
        temporal_plan = self._build_temporal_plan(graph, policies, advanced_overrides or {})
        self._apply_temporal_windows(graph, temporal_plan)
        policy_plan = self._build_policy_plan(policies, graph, temporal_plan)
        role_demands = self._build_role_demands(graph, policy_plan, foundation_ref)

        if not events:
            assumptions.append("当前未提供灾害事件，场景规划仅保留政策与背景能力需求。")
        if events and not any(item.target_region_ids or item.target_entity_ids for item in events):
            assumptions.append("用户未指定事件目标区域或设施，当前沿用 Step 1 背景范围，需在结果审阅中确认。")
        assumptions = _unique_strings(assumptions)

        semantic_payload = {
            "foundation_ref": foundation_ref,
            "effort_snapshot_ref": effort_ref,
            "events": [item.to_dict() for item in events],
            "policies": [item.to_dict() for item in policies],
            "event_mechanism_graph": graph.to_dict(),
            "temporal_plan": temporal_plan.to_dict(),
            "policy_plan": policy_plan,
            "role_demands": role_demands,
            "assumptions": assumptions,
            "semantic_artifact_ref": dict(semantic_artifact_ref or {}),
        }
        planning_input_id = _stable_id("scenario_plan", semantic_payload)
        artifact = ScenarioPlanningInput(
            contract_version=SCENARIO_PLANNING_CONTRACT_VERSION,
            planning_input_id=planning_input_id,
            revision=1,
            foundation_ref=foundation_ref,
            effort_snapshot_ref=effort_ref,
            normalized_user_events=[item.to_dict() for item in events],
            normalized_user_policies=[item.to_dict() for item in policies],
            event_mechanism_graph=graph.to_dict(),
            temporal_plan=temporal_plan.to_dict(),
            policy_plan=policy_plan,
            role_demands=role_demands,
            assumptions=assumptions,
            semantic_artifact_ref=dict(semantic_artifact_ref or {}),
        )
        payload_without_hash = artifact.to_dict()
        payload_without_hash["content_hash"] = ""
        artifact.content_hash = _content_hash(payload_without_hash)
        return artifact

    def build_from_legacy(
        self,
        foundation: Optional[Mapping[str, Any]],
        effort_snapshot_ref: Optional[Mapping[str, Any] | str],
        injected_variables: Optional[Sequence[Mapping[str, Any] | Any]],
        advanced_overrides: Optional[Mapping[str, Any]] = None,
    ) -> ScenarioPlanningInput:
        events, policies = self.convert_legacy_injected_variables(injected_variables or [])
        return self.build(
            foundation=foundation,
            effort_snapshot_ref=effort_snapshot_ref,
            user_events=events,
            user_policies=policies,
            advanced_overrides=advanced_overrides,
            semantic_artifact_ref=None,
        )

    @staticmethod
    def normalize_user_events(
        values: Sequence[UserEventInput | Mapping[str, Any]],
    ) -> List[UserEventInput]:
        if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Sequence):
            raise ValueError("灾害事件必须使用数组格式")
        normalized: List[UserEventInput] = []
        seen_ids: set[str] = set()
        for index, value in enumerate(values, start=1):
            if isinstance(value, UserEventInput):
                raw = value.to_dict()
            else:
                raw = _as_mapping(value)
            name = _clean_text(raw.get("name") or raw.get("title")) or f"灾害事件 {index}"
            description = _clean_text(raw.get("description") or raw.get("detail") or name)
            order = _bounded_int(raw.get("order"), index, 1, 9999)
            target_region_ids = _normalize_id_list(
                raw.get("target_region_ids") if raw.get("target_region_ids") is not None else raw.get("target_regions"),
                f"灾害事件 {index} 的目标区域",
            )
            target_entity_ids = _normalize_id_list(
                raw.get("target_entity_ids") if raw.get("target_entity_ids") is not None else raw.get("target_nodes"),
                f"灾害事件 {index} 的目标设施或对象",
            )
            atomic_keys = _unique_strings(raw.get("atomic_keys") or [])
            intensity = raw.get("intensity") if isinstance(raw.get("intensity"), Mapping) else {}
            time_data = raw.get("time") if isinstance(raw.get("time"), Mapping) else {}
            input_id = _clean_text(raw.get("input_id") or raw.get("variable_id"))
            if not input_id:
                input_id = _stable_id("event_input", index, name, description, target_region_ids, target_entity_ids)
            if input_id in seen_ids:
                raise ValueError(f"灾害事件输入标识重复: {input_id}")
            seen_ids.add(input_id)
            normalized.append(
                UserEventInput(
                    input_id=input_id,
                    name=name,
                    description=description,
                    order=order,
                    target_region_ids=target_region_ids,
                    target_entity_ids=target_entity_ids,
                    atomic_keys=atomic_keys,
                    open_concept=_clean_text(raw.get("open_concept")),
                    expected_effects=_unique_strings(raw.get("expected_effects") or []),
                    intensity_score=(
                        _bounded_score(intensity.get("score"), 65.0)
                        if intensity.get("score") is not None
                        else None
                    ),
                    intensity_direction=_clean_text(intensity.get("direction")),
                    intensity_label_zh=_clean_text(intensity.get("label_zh")),
                    start_round=(
                        _bounded_int(time_data.get("start_round"), 0, 0, 9999)
                        if time_data.get("start_round") is not None
                        else None
                    ),
                    duration_rounds=(
                        _bounded_int(time_data.get("duration_rounds"), 1, 1, 9999)
                        if time_data.get("duration_rounds") is not None
                        else None
                    ),
                )
            )
        return sorted(normalized, key=lambda item: (item.order, item.input_id))

    @staticmethod
    def normalize_user_policies(
        values: Sequence[UserPolicyInput | Mapping[str, Any]],
    ) -> List[UserPolicyInput]:
        if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Sequence):
            raise ValueError("政策措施必须使用数组格式")
        normalized: List[UserPolicyInput] = []
        seen_ids: set[str] = set()
        for index, value in enumerate(values, start=1):
            if isinstance(value, UserPolicyInput):
                raw = value.to_dict()
            else:
                raw = _as_mapping(value)
            name = _clean_text(raw.get("name") or raw.get("title")) or f"政策措施 {index}"
            intent = _clean_text(raw.get("intent") or raw.get("description") or name)
            order = _bounded_int(raw.get("order"), index, 1, 9999)
            target_region_ids = _normalize_id_list(
                raw.get("target_region_ids") if raw.get("target_region_ids") is not None else raw.get("target_regions"),
                f"政策措施 {index} 的目标区域",
            )
            target_entity_ids = _normalize_id_list(
                raw.get("target_entity_ids") if raw.get("target_entity_ids") is not None else raw.get("target_nodes"),
                f"政策措施 {index} 的目标设施或对象",
            )
            input_id = _clean_text(raw.get("input_id") or raw.get("variable_id"))
            if not input_id:
                input_id = _stable_id("policy_input", index, name, intent, target_region_ids, target_entity_ids)
            if input_id in seen_ids:
                raise ValueError(f"政策措施输入标识重复: {input_id}")
            seen_ids.add(input_id)
            normalized.append(
                UserPolicyInput(
                    input_id=input_id,
                    name=name,
                    intent=intent,
                    order=order,
                    target_region_ids=target_region_ids,
                    target_entity_ids=target_entity_ids,
                    action_primitives=_unique_strings(raw.get("action_primitives") or []),
                    executor_capability_keys=_unique_strings(raw.get("executor_capability_keys") or []),
                    expected_effects=_unique_strings(raw.get("expected_effects") or []),
                    target_event_keys=_unique_strings(raw.get("target_event_keys") or []),
                    intensity_score=(
                        _bounded_score((raw.get("intensity") or {}).get("score"), 60.0)
                        if isinstance(raw.get("intensity"), Mapping)
                        and (raw.get("intensity") or {}).get("score") is not None
                        else None
                    ),
                    intensity_direction=_clean_text((raw.get("intensity") or {}).get("direction"))
                    if isinstance(raw.get("intensity"), Mapping) else "",
                    intensity_label_zh=_clean_text((raw.get("intensity") or {}).get("label_zh"))
                    if isinstance(raw.get("intensity"), Mapping) else "",
                    start_round=(
                        _bounded_int((raw.get("time") or {}).get("start_round"), 0, 0, 9999)
                        if isinstance(raw.get("time"), Mapping)
                        and (raw.get("time") or {}).get("start_round") is not None
                        else None
                    ),
                    duration_rounds=(
                        _bounded_int((raw.get("time") or {}).get("duration_rounds"), 1, 1, 9999)
                        if isinstance(raw.get("time"), Mapping)
                        and (raw.get("time") or {}).get("duration_rounds") is not None
                        else None
                    ),
                )
            )
        return sorted(normalized, key=lambda item: (item.order, item.input_id))

    @classmethod
    def convert_legacy_injected_variables(
        cls,
        values: Sequence[Mapping[str, Any] | Any],
    ) -> Tuple[List[UserEventInput], List[UserPolicyInput]]:
        event_values: List[Dict[str, Any]] = []
        policy_values: List[Dict[str, Any]] = []
        for index, value in enumerate(values, start=1):
            raw = _as_mapping(value)
            legacy_regions = raw.get("target_regions") or raw.get("target_region_ids") or []
            legacy_entities = raw.get("target_nodes") or raw.get("target_entity_ids") or []
            if isinstance(legacy_regions, (str, bytes)):
                legacy_regions = [legacy_regions]
            if isinstance(legacy_entities, (str, bytes)):
                legacy_entities = [legacy_entities]
            converted = {
                "input_id": raw.get("variable_id") or raw.get("input_id") or f"legacy_variable_{index}",
                "name": raw.get("name") or raw.get("title") or f"历史变量 {index}",
                "description": raw.get("description") or "",
                "intent": raw.get("description") or raw.get("name") or "",
                "order": index,
                "target_region_ids": legacy_regions,
                "target_entity_ids": legacy_entities,
            }
            if _clean_text(raw.get("type")).lower() == "policy":
                policy_values.append(converted)
            else:
                event_values.append(converted)
        return cls.normalize_user_events(event_values), cls.normalize_user_policies(policy_values)

    def _build_event_graph(
        self,
        events: Sequence[UserEventInput],
        foundation_ref: Mapping[str, Any],
        overrides: Mapping[str, Any],
    ) -> Tuple[EventMechanismGraph, List[str]]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        assumptions: List[str] = []
        groups: List[List[Dict[str, Any]]] = []
        foundation_region_ids = self._foundation_region_ids(foundation_ref)

        for event in events:
            text = f"{event.name} {event.description}"
            semantic_keys = [key for key in event.atomic_keys if key in _SPEC_BY_KEY or key == "generic_event"]
            matched_keys = semantic_keys or [
                spec.key for spec in _EVENT_SPECS if any(keyword in text for keyword in spec.keywords)
            ]
            if len(matched_keys) > 1 and "generic_event" in matched_keys:
                matched_keys = [key for key in matched_keys if key != "generic_event"]
            inferred_keys: set[str] = set()

            nuclear_compound = "核电" in text or "核泄漏" in text or "放射性" in text
            if nuclear_compound and "typhoon" in matched_keys and "radioactive_release" in matched_keys:
                for bridge in ("facility_ingress", "power_loss", "cooling_failure"):
                    if bridge not in matched_keys:
                        matched_keys.append(bridge)
                        inferred_keys.add(bridge)
                assumptions.append(
                    "台风与核设施释放之间缺少完整过渡描述时，系统暂按设施进水、供电中断和冷却失效补全机制链。"
                )

            specialized_typhoon_keys = {
                "heavy_rain",
                "flood",
                "facility_ingress",
                "power_loss",
                "cooling_failure",
                "chemical_release",
                "radioactive_release",
                "marine_spread",
                "air_spread",
                "river_spread",
                "surface_spread",
                "human_exposure",
                "medical_pressure",
                "supply_pressure",
                "governance_pressure",
            }
            if "typhoon" in matched_keys and not specialized_typhoon_keys.intersection(matched_keys):
                inferred_defaults = ["traffic_pressure"]
                if "strong_wind" not in matched_keys:
                    inferred_defaults.insert(0, "strong_wind")
                coastal_context = " ".join(
                    item
                    for item in (
                        _clean_text(text),
                        _clean_text(foundation_ref.get("location")),
                        _clean_text(foundation_ref.get("area_label")),
                    )
                    if item
                )
                if any(
                    token in coastal_context
                    for token in ("沿海", "滨海", "海湾", "海岸", "近岸", "香港", "袭港", "港岛", "深圳湾")
                ):
                    inferred_defaults.extend(["storm_surge", "ecological_impact"])
                for inferred_key in inferred_defaults:
                    if inferred_key not in matched_keys:
                        matched_keys.append(inferred_key)
                        inferred_keys.add(inferred_key)
                assumptions.append(
                    "用户仅描述台风或风球本体时，系统按受控气象机制补全强风、交通影响；沿海场景同时补全风暴潮与敏感生态受体路径。"
                )

            matched_keys = self._ordered_event_keys(matched_keys)
            if not matched_keys:
                matched_keys = ["generic_event"]

            group: List[Dict[str, Any]] = []
            input_override = _as_mapping(
                (overrides.get("event_overrides") or {}).get(event.input_id)
                if isinstance(overrides.get("event_overrides"), Mapping)
                else {}
            )
            for key in matched_keys:
                if key == "generic_event":
                    label_zh = event.name
                    event_kind = "external_disturbance"
                    hazard_family = "generic"
                    score = 65.0
                else:
                    spec = _SPEC_BY_KEY[key]
                    label_zh = event.name if len(matched_keys) == 1 else spec.label_zh
                    event_kind = spec.event_kind
                    hazard_family = spec.hazard_family
                    score = spec.default_score

                override_score = (
                    input_override.get("intensity")
                    if input_override.get("intensity") is not None
                    else (
                        (overrides.get("intensity_overrides") or {}).get(key)
                        if isinstance(overrides.get("intensity_overrides"), Mapping)
                        else None
                    )
                )
                if override_score is None and event.intensity_score is not None:
                    override_score = event.intensity_score
                target_regions = list(event.target_region_ids or foundation_region_ids)
                event_id = _stable_id("event", event.input_id, key, label_zh)
                runtime_node_type = {
                    "natural_hazard": "hazard",
                    "secondary_hazard": "hazard",
                    "external_disturbance": "source",
                    "hazardous_release": "hazard",
                    "hazard_propagation": "process",
                    "infrastructure_failure": "infrastructure",
                    "impact": "receptor",
                    "system_pressure": "service",
                }.get(event_kind, "process")
                node = {
                    "id": event_id,
                    "event_id": event_id,
                    "source_input_id": event.input_id,
                    "atomic_key": key,
                    "name": label_zh,
                    "label": label_zh,
                    "label_zh": label_zh,
                    "description": self._event_description(event, key, label_zh, key in inferred_keys),
                    "description_zh": self._event_description(event, key, label_zh, key in inferred_keys),
                    "node_type": runtime_node_type,
                    "event_kind": event_kind,
                    "hazard_family": hazard_family,
                    "origin": "system_inferred" if key in inferred_keys else "user_input",
                    "target_region_ids": target_regions,
                    "region_id": target_regions[0] if target_regions else "",
                    "target_entity_ids": list(event.target_entity_ids),
                    "physical_time_window": {},
                    "requested_start_round": event.start_round,
                    "requested_duration_rounds": event.duration_rounds,
                    "intensity": {
                        "score": _bounded_score(override_score, score),
                        "level_zh": self._intensity_label(_bounded_score(override_score, score)),
                        "source_zh": "用户高级设置" if override_score is not None else "系统根据事件类型推导",
                    },
                    "evidence_refs": [event.input_id],
                    "confidence": 0.7 if key in inferred_keys else 0.82,
                    "epistemic_status": "待审阅的系统推断" if key in inferred_keys else "用户明确输入",
                }
                nodes.append(node)
                group.append(node)
            groups.append(group)
            if len(group) > 1:
                assumptions.append("系统根据用户描述中的因果词和灾害关键词拆分复合事件链，需在结果审阅中确认。")

        for group in groups:
            edges.extend(self._connect_event_group(group))
        cross_input_edges, cross_input_assumptions = self._connect_ordered_event_groups(groups)
        edges.extend(cross_input_edges)
        assumptions.extend(cross_input_assumptions)

        incoming = {str(edge["target_event_id"]) for edge in edges}
        outgoing_counts: Dict[str, int] = {}
        for edge in edges:
            source_id = str(edge["source_event_id"])
            outgoing_counts[source_id] = outgoing_counts.get(source_id, 0) + 1

        graph_id = _stable_id(
            "mechanism_graph",
            [(item["event_id"], item["atomic_key"]) for item in nodes],
            [(item["source_event_id"], item["target_event_id"], item["primitive_key"]) for item in edges],
        )
        graph = EventMechanismGraph(
            graph_id=graph_id,
            nodes=nodes,
            edges=edges,
            primary_event_ids=[str(item["event_id"]) for item in nodes if str(item["event_id"]) not in incoming],
            branching_event_ids=[event_id for event_id, count in outgoing_counts.items() if count > 1],
            assumptions=_unique_strings(assumptions),
        )
        return graph, assumptions

    def _connect_ordered_event_groups(
        self,
        groups: Sequence[Sequence[Mapping[str, Any]]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Connect adjacent user inputs without pretending order is always cause.

        Known atomic pairs use the same mechanism catalog as intra-input chains.
        When no catalogued mechanism can connect the two inputs, a low-confidence
        order edge preserves the user's sequence while explicitly flagging that
        causality still requires review.
        """

        edges: List[Dict[str, Any]] = []
        assumptions: List[str] = []
        non_empty = [list(group) for group in groups if group]
        for previous, current in zip(non_empty, non_empty[1:]):
            known_pairs: List[Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = []
            for source in previous:
                for target in current:
                    pair = (str(source.get("atomic_key") or ""), str(target.get("atomic_key") or ""))
                    rule = _PAIR_MECHANISMS.get(pair)
                    if rule:
                        known_pairs.append((source, target, rule))
            if known_pairs:
                for source, target, rule in known_pairs:
                    edges.append(self._mechanism_edge(source, target, rule))
                continue

            source = previous[-1]
            target = current[0]
            edge = self._mechanism_edge(
                source,
                target,
                {
                    "primitive_key": "user_order_transition",
                    "propagation_medium": "user_defined_sequence",
                    "trigger_conditions": ["用户将下游事件排在上游事件之后，但尚无足够信息确认具体因果机制"],
                    "latency_rounds": 1,
                    "duration_rounds": 1,
                    "attenuation": 0.7,
                    "label_zh": f"用户顺序：{source.get('label_zh')}之后发生{target.get('label_zh')}",
                    "origin": "user_order",
                    "confidence": 0.42,
                    "epistemic_status": "仅确认先后顺序，因果关系待审阅",
                },
            )
            edges.append(edge)
            assumptions.append(
                f"“{source.get('label_zh')}”与“{target.get('label_zh')}”按用户顺序连接；当前仅确认先后关系，具体因果机制待审阅。"
            )
        return edges, assumptions

    @staticmethod
    def _ordered_event_keys(keys: Sequence[str]) -> List[str]:
        requested = set(keys)
        canonical = [spec.key for spec in _EVENT_SPECS]
        return [key for key in canonical if key in requested]

    @staticmethod
    def _event_description(event: UserEventInput, key: str, label_zh: str, inferred: bool) -> str:
        if inferred:
            return f"为连接“{event.name}”中的复合灾害因果链，系统暂推断存在{label_zh}环节。"
        if key == "generic_event" or label_zh == event.name:
            return event.description or event.name
        source_text = event.description or event.name
        spec = _SPEC_BY_KEY.get(key)
        clauses = [
            re.sub(r"^(?:可能造成|可能导致|并造成|并导致|造成|导致)", "", item).strip()
            for item in re.split(r"[。！？；;，,、]|(?:以及|并且|随后|继而)|和(?=跨部门)", source_text)
            if item.strip()
        ]
        if spec:
            matching = [
                clause
                for clause in clauses
                if any(keyword in clause for keyword in spec.keywords)
            ]
            if matching:
                clause = min(matching, key=lambda item: (len(item), clauses.index(item)))
                return f"用户描述中的“{clause}”明确指向{label_zh}环节。"
        return f"用户描述明确包含{label_zh}环节。"

    @staticmethod
    def _intensity_label(score: float) -> str:
        if score >= 85:
            return "很高"
        if score >= 70:
            return "高"
        if score >= 50:
            return "中"
        return "低"

    def _connect_event_group(self, group: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        if len(group) < 2:
            return []
        by_key = {str(item.get("atomic_key")): item for item in group}
        edges: List[Dict[str, Any]] = []
        connected_pairs: set[Tuple[str, str]] = set()

        for pair, rule in _PAIR_MECHANISMS.items():
            if pair[0] not in by_key or pair[1] not in by_key:
                continue
            edges.append(self._mechanism_edge(by_key[pair[0]], by_key[pair[1]], rule))
            connected_pairs.add(pair)

        incoming_keys = {
            str(edge["target_atomic_key"])
            for edge in edges
        }
        ordered = list(group)
        for index in range(1, len(ordered)):
            target = ordered[index]
            target_key = str(target.get("atomic_key"))
            if target_key in incoming_keys:
                continue
            previous = ordered[:index]
            target_kind = str(target.get("event_kind") or "")
            if target_kind in {"impact", "system_pressure"}:
                upstream = [
                    item
                    for item in previous
                    if str(item.get("event_kind") or "") not in {"impact", "system_pressure"}
                ]
                source = upstream[-1] if upstream else previous[-1]
            else:
                source = previous[-1]
            pair = (str(source.get("atomic_key")), target_key)
            if pair in connected_pairs:
                continue
            rule = {
                "primitive_key": "causal_transition",
                "propagation_medium": "system_coupling",
                "trigger_conditions": ["上游事件达到影响下游环节的条件"],
                "latency_rounds": 1,
                "duration_rounds": 2,
                "attenuation": 0.86,
                "label_zh": f"{source.get('label_zh')}可能影响{target.get('label_zh')}",
                "origin": "structural_fallback",
                "confidence": 0.48,
                "epistemic_status": "仅根据事件结构推断，具体因果机制待审阅",
            }
            edge = self._mechanism_edge(source, target, rule)
            edges.append(edge)
            incoming_keys.add(target_key)
        return edges

    @staticmethod
    def _mechanism_edge(
        source: Mapping[str, Any],
        target: Mapping[str, Any],
        rule: Mapping[str, Any],
    ) -> Dict[str, Any]:
        source_id = str(source.get("event_id") or "")
        target_id = str(target.get("event_id") or "")
        primitive_key = str(rule.get("primitive_key") or "causal_transition")
        inferred_confidence = round(
            min(float(source.get("confidence") or 0.6), float(target.get("confidence") or 0.6)), 2
        )
        return {
            "id": _stable_id("mechanism", source_id, target_id, primitive_key),
            "mechanism_id": _stable_id("mechanism", source_id, target_id, primitive_key),
            "source": source_id,
            "target": target_id,
            "label": str(rule.get("label_zh") or "事件因果传导"),
            "relation_label": str(rule.get("label_zh") or "事件因果传导"),
            "mechanism": str(rule.get("label_zh") or "事件因果传导"),
            "label_zh": str(rule.get("label_zh") or "事件因果传导"),
            "primitive_key": primitive_key,
            "source_event_id": source_id,
            "target_event_id": target_id,
            "source_atomic_key": source.get("atomic_key") or "",
            "target_atomic_key": target.get("atomic_key") or "",
            "propagation_medium": str(rule.get("propagation_medium") or "system_coupling"),
            "trigger_conditions": list(rule.get("trigger_conditions") or ["上游事件达到触发条件"]),
            "evidence": list(rule.get("trigger_conditions") or ["上游事件达到触发条件"]),
            "latency": {
                "rounds": int(rule.get("latency_rounds") or 0),
                "description_zh": "达到触发条件后按所列轮次延迟显现。",
            },
            "duration": {
                "rounds": max(1, int(rule.get("duration_rounds") or 1)),
                "description_zh": "影响在所列轮次内持续，并可受干预改变。",
            },
            "attenuation": {
                "factor": float(rule.get("attenuation") or 0.85),
                "description_zh": "传播强度会随距离、防护和处置能力衰减。",
            },
            "evidence_refs": _unique_strings(
                list(source.get("evidence_refs") or []) + list(target.get("evidence_refs") or [])
            ),
            "confidence": round(float(rule.get("confidence", inferred_confidence)), 2),
            "direction": str(rule.get("direction") or "positive"),
            "origin": str(rule.get("origin") or "system_inferred"),
            "epistemic_status": str(rule.get("epistemic_status") or "系统根据原子机制规则推导"),
        }

    def _build_temporal_plan(
        self,
        graph: EventMechanismGraph,
        policies: Sequence[UserPolicyInput],
        overrides: Mapping[str, Any],
    ) -> TemporalPlan:
        step_unit = str(overrides.get("step_unit") or "day")
        unit_labels = {
            "hour": "小时",
            "day": "天",
            "week": "周",
            "month": "月",
            "quarter": "季度",
            "year": "年",
        }
        if step_unit not in unit_labels:
            step_unit = "day"
        step_value = _bounded_int(overrides.get("step_value"), 1, 1, 30)
        default_rounds = max(8, min(24, len(graph.nodes) + 4 + (2 if policies else 0)))
        total_rounds = _bounded_int(overrides.get("total_rounds"), default_rounds, 3, 120)

        inbound: Dict[str, List[Dict[str, Any]]] = {}
        for edge in graph.edges:
            inbound.setdefault(str(edge.get("target_event_id") or ""), []).append(edge)
        starts: Dict[str, int] = {}
        for node in graph.nodes:
            event_id = str(node.get("event_id") or "")
            predecessors = inbound.get(event_id) or []
            if not predecessors:
                starts[event_id] = 0
                continue
            candidate_starts = []
            for edge in predecessors:
                source_start = starts.get(str(edge.get("source_event_id") or ""), 0)
                latency = int((edge.get("latency") or {}).get("rounds") or 0)
                candidate_starts.append(source_start + max(1, latency))
            starts[event_id] = min(total_rounds - 1, max(candidate_starts or [1]))

        override_windows = overrides.get("event_windows") if isinstance(overrides.get("event_windows"), Mapping) else {}
        input_overrides = overrides.get("event_overrides") if isinstance(overrides.get("event_overrides"), Mapping) else {}
        event_windows: List[Dict[str, Any]] = []
        for node in graph.nodes:
            event_id = str(node.get("event_id") or "")
            node_override = {
                **_as_mapping((input_overrides or {}).get(str(node.get("source_input_id") or ""))),
                **_as_mapping((override_windows or {}).get(event_id)),
            }
            if node_override.get("start_round") is None and node.get("requested_start_round") is not None:
                node_override["start_round"] = node.get("requested_start_round")
            if node_override.get("duration_rounds") is None and node.get("requested_duration_rounds") is not None:
                node_override["duration_rounds"] = node.get("requested_duration_rounds")
            has_window_override = any(
                node_override.get(key) is not None
                for key in ("start_round", "duration_rounds")
            )
            start_round = _bounded_int(node_override.get("start_round"), starts.get(event_id, 0), 0, total_rounds - 1)
            base_duration = 4 if str(node.get("event_kind")) == "hazard_propagation" else 3
            duration = _bounded_int(node_override.get("duration_rounds"), base_duration, 1, total_rounds)
            if start_round + duration > total_rounds:
                duration = max(1, total_rounds - start_round)
            event_windows.append(
                {
                    "event_id": event_id,
                    "label_zh": node.get("label_zh") or "事件",
                    "start_round": start_round,
                    "duration_rounds": duration,
                    "end_round": start_round + duration - 1,
                    "source_zh": "用户高级设置" if has_window_override else "系统根据因果顺序推导",
                }
            )

        policy_windows = []
        for item in policies:
            start_round = (
                min(total_rounds - 1, item.start_round)
                if item.start_round is not None
                else min(2, total_rounds - 1)
            )
            duration_rounds = (
                min(total_rounds - start_round, item.duration_rounds)
                if item.duration_rounds is not None
                else max(1, total_rounds - start_round)
            )
            policy_windows.append({
                "policy_input_id": item.input_id,
                "label_zh": item.name,
                "start_round": start_round,
                "duration_rounds": max(1, duration_rounds),
                "end_round": start_round + max(1, duration_rounds) - 1,
                "source_zh": "用户设置" if item.start_round is not None or item.duration_rounds is not None else "系统根据响应阶段推导",
            })
        coverage_label = f"共 {total_rounds} 轮，每轮 {step_value} {unit_labels[step_unit]}"
        plan_id = _stable_id(
            "temporal_plan", step_unit, step_value, total_rounds, event_windows, policy_windows
        )
        return TemporalPlan(
            plan_id=plan_id,
            step_unit=step_unit,
            step_unit_label_zh=unit_labels[step_unit],
            step_value=step_value,
            total_rounds=total_rounds,
            coverage_label_zh=coverage_label,
            event_windows=event_windows,
            policy_windows=policy_windows,
            generation_reason_zh="系统依据事件因果顺序、传播延迟和政策响应阶段自动安排时间。",
        )

    @staticmethod
    def _apply_temporal_windows(graph: EventMechanismGraph, temporal_plan: TemporalPlan) -> None:
        windows = {str(item["event_id"]): dict(item) for item in temporal_plan.event_windows}
        for node in graph.nodes:
            window = windows.get(str(node.get("event_id") or ""), {})
            node["physical_time_window"] = {
                "start_round": window.get("start_round", 0),
                "end_round": window.get("end_round", 0),
                "duration_rounds": window.get("duration_rounds", 1),
                "step_unit": temporal_plan.step_unit,
                "step_value": temporal_plan.step_value,
                "source_zh": window.get("source_zh") or "系统推导",
            }

    def _build_policy_plan(
        self,
        policies: Sequence[UserPolicyInput],
        graph: EventMechanismGraph,
        temporal_plan: TemporalPlan,
    ) -> List[Dict[str, Any]]:
        policy_windows = {str(item["policy_input_id"]): item for item in temporal_plan.policy_windows}
        plans: List[Dict[str, Any]] = []
        for policy in policies:
            text = f"{policy.name} {policy.intent}"
            semantic_primitives = [
                item for item in policy.action_primitives if item in _SEMANTIC_POLICY_RULES
            ]
            matched_rules = [
                _SEMANTIC_POLICY_RULES[item] for item in semantic_primitives
            ] or [rule for rule in _POLICY_RULES if any(keyword in text for keyword in rule["keywords"])]
            has_specific_rule = bool(matched_rules)
            if not matched_rules:
                matched_rules = [
                    {
                        "effect_primitives": ["governance_intervention"],
                        "capabilities": ["policy_coordination", "public_information"],
                        "expected_effects": ["按照用户意图调整场景响应能力"],
                        "side_effects": ["具体副作用取决于执行主体、资源和实施范围"],
                    }
                ]
            effect_primitives = _unique_strings(
                primitive for rule in matched_rules for primitive in rule["effect_primitives"]
            )
            capabilities = _unique_strings(
                capability for rule in matched_rules for capability in rule["capabilities"]
            )
            capabilities = _unique_strings([*capabilities, *policy.executor_capability_keys])
            expected_effects = _unique_strings(
                effect for rule in matched_rules for effect in rule["expected_effects"]
            )
            expected_effects = _unique_strings([*expected_effects, *policy.expected_effects])
            side_effects = _unique_strings(
                effect for rule in matched_rules for effect in rule["side_effects"]
            )
            target_event_ids = self._policy_target_events(
                text,
                graph.nodes,
                target_event_keys=policy.target_event_keys,
            )
            target_mechanism_ids = [
                str(edge["mechanism_id"])
                for edge in graph.edges
                if str(edge.get("source_event_id")) in target_event_ids
                or str(edge.get("target_event_id")) in target_event_ids
            ]
            window = policy_windows.get(policy.input_id) or {}
            plans.append(
                {
                    "policy_id": _stable_id("policy", policy.input_id, effect_primitives),
                    "source_input_id": policy.input_id,
                    "label_zh": policy.name,
                    "user_intent": policy.intent,
                    "effect_primitives": effect_primitives,
                    "target_event_ids": target_event_ids,
                    "target_mechanism_ids": _unique_strings(target_mechanism_ids),
                    "target_region_ids": list(policy.target_region_ids),
                    "target_entity_ids": list(policy.target_entity_ids),
                    "executor_capability_keys": capabilities,
                    "trigger_conditions": ["相关风险事件已经发生或达到预警阈值", "具备权限和资源的执行主体可用"],
                    "expected_effects": expected_effects,
                    "side_effects": side_effects,
                    "start_round": int(window.get("start_round") or 0),
                    "duration_rounds": int(window.get("duration_rounds") or 1),
                    "intensity_0_100": policy.intensity_score,
                    "semantic_action_primitives": semantic_primitives,
                    "confidence": 0.76 if has_specific_rule else 0.48,
                    "epistemic_status": (
                        "系统根据已知政策机制推导，待 Agent 模块校验执行能力"
                        if has_specific_rule
                        else "未匹配到专用政策机制，当前按通用治理措施低置信度推导"
                    ),
                }
            )
        return plans

    @staticmethod
    def _policy_target_events(
        text: str,
        nodes: Sequence[Mapping[str, Any]],
        *,
        target_event_keys: Optional[Sequence[str]] = None,
    ) -> List[str]:
        keys: set[str]
        if target_event_keys:
            keys = {str(item) for item in target_event_keys}
        elif any(keyword in text for keyword in ("渔", "海洋", "捕捞")):
            keys = {"marine_spread", "ecological_impact", "radioactive_release", "chemical_release"}
        elif any(keyword in text for keyword in ("疏散", "撤离", "医院", "医疗")):
            keys = {"radioactive_release", "chemical_release", "air_spread", "human_exposure"}
        elif any(keyword in text for keyword in ("监测", "采样", "预警")):
            keys = {"radioactive_release", "chemical_release", "marine_spread", "air_spread"}
        elif any(keyword in text for keyword in ("修复", "供电", "冷却")):
            keys = {"facility_ingress", "power_loss", "cooling_failure"}
        else:
            keys = {str(item.get("atomic_key") or "") for item in nodes}
        result = [str(item.get("event_id") or "") for item in nodes if str(item.get("atomic_key") or "") in keys]
        return result or [str(item.get("event_id") or "") for item in nodes]

    def _build_role_demands(
        self,
        graph: EventMechanismGraph,
        policy_plan: Sequence[Mapping[str, Any]],
        foundation_ref: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        nodes_by_key: Dict[str, List[Dict[str, Any]]] = {}
        for item in graph.nodes:
            nodes_by_key.setdefault(str(item.get("atomic_key") or ""), []).append(item)
        mechanisms_by_event_id: Dict[str, List[str]] = {}
        for edge in graph.edges:
            mechanism_id = str(edge.get("mechanism_id") or "")
            for event_id in (str(edge.get("source_event_id") or ""), str(edge.get("target_event_id") or "")):
                mechanisms_by_event_id.setdefault(event_id, []).append(mechanism_id)

        demands: List[Dict[str, Any]] = []

        def add_demand(
            demand_key: str,
            label_zh: str,
            capabilities: Sequence[str],
            event_keys: Sequence[str],
            resolution: str,
            importance: str,
            rationale_zh: str,
        ) -> None:
            cause_nodes = [
                node
                for key in event_keys
                for node in nodes_by_key.get(key, [])
            ]
            event_ids = _unique_strings(str(node.get("event_id") or "") for node in cause_nodes)
            mechanism_ids = _unique_strings(
                mechanism_id
                for event_id in event_ids
                for mechanism_id in mechanisms_by_event_id.get(event_id, [])
            )
            if not event_ids and not capabilities:
                return
            jurisdiction_region_ids = _unique_strings(
                region_id
                for node in cause_nodes
                for region_id in (node.get("target_region_ids") or [])
            )
            if not jurisdiction_region_ids:
                jurisdiction_region_ids = self._foundation_region_ids(foundation_ref)
            demand_id = _stable_id(
                "role_demand", demand_key, event_ids, capabilities, jurisdiction_region_ids
            )
            demands.append(
                {
                    "demand_id": demand_id,
                    "demand_key": demand_key,
                    "label_zh": label_zh,
                    "caused_by_event_ids": event_ids,
                    "caused_by_mechanism_ids": mechanism_ids,
                    "required_capability_keys": _unique_strings(capabilities),
                    "jurisdiction_region_ids": jurisdiction_region_ids,
                    "required_resolution": resolution,
                    "importance": importance,
                    "rationale_zh": rationale_zh,
                }
            )

        if any(key in nodes_by_key for key in ("typhoon", "strong_wind", "heavy_rain", "storm_surge", "flood", "tsunami")):
            add_demand(
                "hazard_monitoring",
                "气象与水文监测能力",
                ["meteorological_monitoring", "coastal_flood_forecasting", "risk_early_warning"],
                ["typhoon", "strong_wind", "heavy_rain", "storm_surge", "flood", "tsunami"],
                "organization",
                "high",
                "极端天气和沿海水位变化需要持续监测与预警。",
            )

        if any(key in nodes_by_key for key in ("earthquake", "tsunami", "landslide", "liquefaction", "secondary_fire")):
            add_demand(
                "geological_emergency_monitoring",
                "地质灾害与震后评估能力",
                ["seismic_monitoring", "geological_hazard_assessment", "infrastructure_damage_assessment"],
                ["earthquake", "tsunami", "landslide", "liquefaction", "secondary_fire"],
                "organization",
                "high",
                "地震及其次生灾害需要持续监测、现场核查与基础设施损伤评估。",
            )

        nuclear_keys = ["facility_ingress", "power_loss", "cooling_failure", "radioactive_release"]
        if any(key in nodes_by_key for key in nuclear_keys):
            add_demand(
                "critical_facility_operator",
                "关键设施应急运行能力",
                ["facility_safety_operation", "emergency_shutdown", "cooling_system_recovery"],
                nuclear_keys,
                "specific_facility",
                "critical",
                "设施进水、供电与冷却失效需要由具备现场权限的运营主体处置。",
            )
        if "radioactive_release" in nodes_by_key:
            add_demand(
                "nuclear_safety_regulator",
                "核安全监管能力",
                ["nuclear_safety_regulation", "radiation_emergency_oversight", "regulatory_enforcement"],
                ["radioactive_release", "power_loss", "cooling_failure"],
                "organization",
                "critical",
                "放射性释放需要独立监管、事故分级和应急监督。",
            )

        if any(key in nodes_by_key for key in (
            "radioactive_release", "chemical_release", "marine_spread", "air_spread", "river_spread", "surface_spread"
        )):
            add_demand(
                "environmental_monitoring",
                "环境与辐射监测能力",
                ["environmental_monitoring", "radiation_monitoring", "laboratory_analysis", "data_analysis"],
                ["radioactive_release", "chemical_release", "marine_spread", "air_spread", "river_spread", "surface_spread"],
                "organization",
                "critical",
                "污染释放和多介质传播需要采样、检测和传播边界判断。",
            )
            add_demand(
                "emergency_medical_response",
                "医疗应急响应能力",
                ["emergency_medical_response", "radiation_injury_treatment", "patient_transport"],
                ["radioactive_release", "chemical_release", "air_spread", "human_exposure"],
                "specific_facility",
                "high",
                "潜在人群暴露需要医疗筛查、救治和转运能力。",
            )
            add_demand(
                "public_emergency_command",
                "地方应急指挥能力",
                ["emergency_command", "evacuation_coordination", "resource_dispatch", "public_information"],
                ["radioactive_release", "chemical_release", "marine_spread", "air_spread"],
                "organization",
                "critical",
                "跨区域风险需要统一指挥、资源协调和公众沟通。",
            )
            add_demand(
                "affected_population",
                "受影响居民响应能力",
                ["public_risk_response", "evacuation_participation", "local_information_reporting"],
                ["radioactive_release", "chemical_release", "air_spread", "human_exposure"],
                "population_group",
                "high",
                "居民既是风险受体，也是疏散、信息反馈和自我防护的参与者。",
            )

        if "marine_spread" in nodes_by_key or any(
            "fisheries_management" in (item.get("executor_capability_keys") or []) for item in policy_plan
        ):
            add_demand(
                "fisheries_stakeholders",
                "渔业群体与行业协作能力",
                ["livelihood_impact_reporting", "fisheries_self_organization", "restriction_compliance"],
                ["marine_spread", "ecological_impact"],
                "population_group",
                "high",
                "海洋污染和捕捞限制会直接影响渔民及相关经营主体。",
            )

        if "medical_pressure" in nodes_by_key:
            add_demand(
                "healthcare_capacity_coordination",
                "医疗容量与转运协调能力",
                ["hospital_capacity_management", "patient_triage", "patient_transport", "medical_supply_dispatch"],
                ["human_exposure", "medical_pressure"],
                "specific_facility",
                "critical",
                "集中暴露和救治需求需要医院容量、分诊、转运及医疗物资协同。",
            )
        if "traffic_pressure" in nodes_by_key:
            add_demand(
                "transport_continuity",
                "交通连续性与疏散调度能力",
                ["traffic_control", "evacuation_routing", "transport_dispatch", "road_clearance"],
                ["traffic_pressure"],
                "organization",
                "high",
                "道路中断和疏散拥堵需要动态交通管制、路线规划与运力调度。",
            )
        if "supply_pressure" in nodes_by_key:
            add_demand(
                "critical_supply_coordination",
                "关键物资供应协调能力",
                ["supply_chain_monitoring", "inventory_allocation", "logistics_dispatch", "emergency_procurement"],
                ["supply_pressure"],
                "organization",
                "high",
                "关键物资短缺需要识别库存、安排物流并协调跨区域调拨。",
            )
        if "governance_pressure" in nodes_by_key:
            add_demand(
                "cross_agency_governance",
                "跨部门治理与协同能力",
                ["cross_agency_coordination", "resource_dispatch", "public_information", "conflict_resolution"],
                ["governance_pressure"],
                "organization",
                "high",
                "复杂灾害中的资源竞争和职责交叉需要稳定的跨部门协调机制。",
            )

        semantic_policy_actions = {
            action
            for policy in policy_plan
            for action in (policy.get("semantic_action_primitives") or [])
        }
        all_event_keys = [str(item.get("atomic_key") or "") for item in graph.nodes]
        if "school_closure" in semantic_policy_actions:
            add_demand(
                "education_emergency_execution",
                "教育系统停课与学生安全协调能力",
                ["education_emergency_management", "school_closure_execution", "student_safety_communication"],
                all_event_keys,
                "organization",
                "high",
                "停课需要教育主管、学校执行和家庭信息沟通，不能由通用治理角色替代。",
            )
        if "workplace_shutdown" in semantic_policy_actions:
            add_demand(
                "workplace_shutdown_execution",
                "工作场所停工与连续性协调能力",
                ["workplace_safety_enforcement", "business_continuity_coordination", "labor_communication"],
                all_event_keys,
                "organization",
                "high",
                "停工需要劳动安全、企业连续性和员工沟通权限，不能与教育执行合并。",
            )
        if "transport_restriction" in semantic_policy_actions:
            add_demand(
                "transport_restriction_execution",
                "交通限制与应急通行协调能力",
                ["traffic_control", "transport_dispatch", "emergency_route_protection"],
                all_event_keys,
                "organization",
                "high",
                "交通限制需要道路管制和应急通行权限。",
            )
        if "shelter_in_place" in semantic_policy_actions:
            add_demand(
                "community_shelter_coordination",
                "社区避险与脆弱群体保障能力",
                ["public_safety_guidance", "community_coordination", "vulnerable_group_support"],
                all_event_keys,
                "population_group",
                "high",
                "就地避险需要社区执行和脆弱群体保障。",
            )
        if "resource_dispatch" in semantic_policy_actions:
            add_demand(
                "emergency_resource_dispatch",
                "应急资源调度能力",
                ["resource_dispatch", "inventory_allocation", "logistics_dispatch"],
                all_event_keys,
                "organization",
                "high",
                "资源调度需要库存、物流和跨区域调配权限。",
            )

        policy_capabilities = _unique_strings(
            capability
            for policy in policy_plan
            for capability in (policy.get("executor_capability_keys") or [])
        )
        covered = {capability for demand in demands for capability in demand["required_capability_keys"]}
        uncovered = [capability for capability in policy_capabilities if capability not in covered]
        if uncovered:
            add_demand(
                "policy_execution",
                "政策执行与资源协调能力",
                uncovered,
                [str(item.get("atomic_key") or "") for item in graph.nodes],
                "organization",
                "high",
                "用户提出的政策措施需要具备相应权限和资源的执行主体，具体主体由 Agent 模块匹配。",
            )
        return demands

    @staticmethod
    def _normalize_foundation_ref(foundation: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        raw = dict(foundation or {})
        reference_id = _clean_text(
            raw.get("artifact_id")
            or raw.get("foundation_id")
            or raw.get("scene_id")
            or raw.get("seed_id")
            or raw.get("project_id")
        )
        if not reference_id:
            reference_id = _stable_id("foundation", raw)
        content_hash = _clean_text(raw.get("content_hash")) or _content_hash(raw)
        result = {
            "artifact_id": reference_id,
            "content_hash": content_hash,
            "contract_version": _clean_text(raw.get("contract_version")) or "foundation.legacy",
        }
        for key in ("region_ids", "regions", "selected_regions", "location", "project_id", "graph_id"):
            if key in raw:
                result[key] = raw[key]
        return result

    @staticmethod
    def _normalize_effort_ref(
        effort_snapshot_ref: Optional[Mapping[str, Any] | str],
    ) -> Tuple[Dict[str, Any], List[str]]:
        assumptions: List[str] = []
        if isinstance(effort_snapshot_ref, str):
            raw: Dict[str, Any] = {"effort_snapshot_id": effort_snapshot_ref}
        else:
            raw = dict(effort_snapshot_ref or {})
        snapshot_id = _clean_text(raw.get("effort_snapshot_id") or raw.get("snapshot_id"))
        if not snapshot_id:
            raw = {
                "effort_snapshot_id": "effort_fixture_high",
                "effort_level": "high",
                "profile_version": "fixture.v1",
                "content_hash": _content_hash({"effort_level": "high", "profile_version": "fixture.v1"}),
                "source": "contract_fixture",
            }
            assumptions.append("共享分析投入底座尚未提供快照时，当前使用“深入”合同样例；正式生成前必须替换为已锁定快照。")
        else:
            raw = {
                "effort_snapshot_id": snapshot_id,
                "effort_level": _clean_text(raw.get("effort_level") or raw.get("level")) or "high",
                "effort_label": _clean_text(raw.get("effort_label")),
                "profile_version": _clean_text(raw.get("profile_version")) or "pending",
                "content_hash": _clean_text(raw.get("content_hash")) or _content_hash(raw),
                "source": _clean_text(raw.get("source")) or "locked_snapshot",
                "stage_budgets": dict(raw.get("stage_budgets") or {}),
                "compatibility": dict(raw.get("compatibility") or {}),
                "locked": bool(raw.get("locked", True)),
            }
        return raw, assumptions

    @staticmethod
    def _foundation_region_ids(foundation_ref: Mapping[str, Any]) -> List[str]:
        direct = list(foundation_ref.get("region_ids") or [])
        for key in ("regions", "selected_regions"):
            for item in foundation_ref.get(key) or []:
                if isinstance(item, Mapping):
                    direct.append(item.get("region_id") or item.get("id") or item.get("name"))
                else:
                    direct.append(item)
        return _unique_strings(direct)


__all__ = [
    "AGENT_V2_PLAN_SOURCE",
    "AgentPlanningPort",
    "AgentV2PlanningAdapter",
    "EventMechanismGraph",
    "LEGACY_AGENT_PLAN_SOURCE",
    "LEGACY_SEARCH_MODE",
    "LegacyAgentPlanningAdapter",
    "SCENARIO_PLANNING_CONTRACT_VERSION",
    "SIMULATION_ARCHITECTURE",
    "ScenarioPlanner",
    "ScenarioPlanningInput",
    "TemporalPlan",
    "UserEventInput",
    "UserPolicyInput",
]
