"""
EnvFish shared domain models and helper utilities.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


ENVFISH_ENGINE_MODE = "envfish"

SCENARIO_MODES = {"baseline_mode", "crisis_mode"}
LEGACY_DIFFUSION_TEMPLATES = {"air", "inland_water", "marine", "generic"}
TRANSPORT_FAMILIES = {
    "atmospheric_plume",
    "marine_current",
    "inland_water_network",
    "surface_flood_flow",
    "coastal_inundation",
    "ecological_mobility",
    "bio_ecological_transmission",
    "ash_plume",
    "infrastructure_failure",
    "impact_blast",
    "slow_ecosystem_decline",
    "terrestrial_surface",
    "generic",
}
DIFFUSION_TEMPLATES = LEGACY_DIFFUSION_TEMPLATES | TRANSPORT_FAMILIES
VARIABLE_TYPES = {"disaster", "policy"}
TEMPORAL_PRESETS = {"rapid", "standard", "slow"}
TIME_PLAN_UNITS = {"hour", "day", "week", "month", "quarter", "year"}
POLICY_MODES = {
    "restrict",
    "relocate",
    "subsidize",
    "monitor",
    "disclose",
    "repair",
    "ban",
    "reopen",
}

STATE_VECTOR_SCHEMA = {
    "exposure_score": {
        "label": "Exposure",
        "description": "Regional or actor exposure to the hazard.",
    },
    "spread_pressure": {
        "label": "Spread Pressure",
        "description": "Local pressure that can propagate to neighbors.",
    },
    "ecosystem_integrity": {
        "label": "Ecosystem Integrity",
        "description": "Overall ecological health and resilience.",
    },
    "livelihood_stability": {
        "label": "Livelihood Stability",
        "description": "Stability of jobs, fisheries, farming, and incomes.",
    },
    "public_trust": {
        "label": "Public Trust",
        "description": "Trust in institutions and public information.",
    },
    "panic_level": {
        "label": "Panic Level",
        "description": "Social fear, rumor, and emotional escalation.",
    },
    "service_capacity": {
        "label": "Service Capacity",
        "description": "Capacity of infrastructure and public services.",
    },
    "response_capacity": {
        "label": "Response Capacity",
        "description": "Operational response capacity of authorities and organizations.",
    },
    "economic_stress": {
        "label": "Economic Stress",
        "description": "Pressure on production, trade, and consumption.",
    },
    "vulnerability_score": {
        "label": "Vulnerability",
        "description": "Composite fragility of the actor or region.",
    },
}

BASELINE_STATE_VECTOR = {
    "exposure_score": 12,
    "spread_pressure": 10,
    "ecosystem_integrity": 78,
    "livelihood_stability": 74,
    "public_trust": 64,
    "panic_level": 16,
    "service_capacity": 72,
    "response_capacity": 66,
    "economic_stress": 24,
    "vulnerability_score": 34,
}

CRISIS_STATE_VECTOR = {
    "exposure_score": 58,
    "spread_pressure": 54,
    "ecosystem_integrity": 43,
    "livelihood_stability": 36,
    "public_trust": 28,
    "panic_level": 66,
    "service_capacity": 40,
    "response_capacity": 38,
    "economic_stress": 61,
    "vulnerability_score": 72,
}

LEGACY_TEMPLATE_TO_FAMILY = {
    "air": "atmospheric_plume",
    "inland_water": "inland_water_network",
    "marine": "marine_current",
    "generic": "generic",
}

PRIMARY_FAMILY_TO_LEGACY = {
    "atmospheric_plume": "air",
    "ash_plume": "air",
    "marine_current": "marine",
    "coastal_inundation": "marine",
    "surface_flood_flow": "inland_water",
    "inland_water_network": "inland_water",
    "ecological_mobility": "generic",
    "bio_ecological_transmission": "generic",
    "infrastructure_failure": "generic",
    "impact_blast": "generic",
    "slow_ecosystem_decline": "generic",
    "terrestrial_surface": "generic",
    "generic": "generic",
}

DEFAULT_TEMPLATE_RULES = {
    "air": {
        "default_lag_rounds": 1,
        "default_decay": 0.84,
        "default_persistence": 48,
        "max_neighbor_spread": 3,
    },
    "inland_water": {
        "default_lag_rounds": 1,
        "default_decay": 0.9,
        "default_persistence": 62,
        "max_neighbor_spread": 2,
    },
    "marine": {
        "default_lag_rounds": 2,
        "default_decay": 0.92,
        "default_persistence": 70,
        "max_neighbor_spread": 4,
    },
    "generic": {
        "default_lag_rounds": 1,
        "default_decay": 0.88,
        "default_persistence": 55,
        "max_neighbor_spread": 2,
    },
    "atmospheric_plume": {
        "default_lag_rounds": 1,
        "default_decay": 0.84,
        "default_persistence": 48,
        "max_neighbor_spread": 3,
    },
    "marine_current": {
        "default_lag_rounds": 2,
        "default_decay": 0.92,
        "default_persistence": 70,
        "max_neighbor_spread": 4,
    },
    "inland_water_network": {
        "default_lag_rounds": 1,
        "default_decay": 0.9,
        "default_persistence": 62,
        "max_neighbor_spread": 2,
    },
    "surface_flood_flow": {
        "default_lag_rounds": 1,
        "default_decay": 0.86,
        "default_persistence": 52,
        "max_neighbor_spread": 3,
    },
    "coastal_inundation": {
        "default_lag_rounds": 1,
        "default_decay": 0.82,
        "default_persistence": 40,
        "max_neighbor_spread": 3,
    },
    "ecological_mobility": {
        "default_lag_rounds": 2,
        "default_decay": 0.95,
        "default_persistence": 82,
        "max_neighbor_spread": 2,
    },
    "bio_ecological_transmission": {
        "default_lag_rounds": 1,
        "default_decay": 0.9,
        "default_persistence": 68,
        "max_neighbor_spread": 3,
    },
    "ash_plume": {
        "default_lag_rounds": 1,
        "default_decay": 0.8,
        "default_persistence": 64,
        "max_neighbor_spread": 3,
    },
    "infrastructure_failure": {
        "default_lag_rounds": 1,
        "default_decay": 0.9,
        "default_persistence": 46,
        "max_neighbor_spread": 2,
    },
    "impact_blast": {
        "default_lag_rounds": 0,
        "default_decay": 0.76,
        "default_persistence": 36,
        "max_neighbor_spread": 4,
    },
    "slow_ecosystem_decline": {
        "default_lag_rounds": 3,
        "default_decay": 0.97,
        "default_persistence": 88,
        "max_neighbor_spread": 2,
    },
    "terrestrial_surface": {
        "default_lag_rounds": 1,
        "default_decay": 0.89,
        "default_persistence": 58,
        "max_neighbor_spread": 2,
    },
}

TEMPORAL_PRESET_DEFAULTS = {
    "rapid": {
        "label": "Rapid",
        "minutes_per_round": 20,
        "recommended_templates": ["air"],
        "description": "Short response windows for fast-moving atmospheric or immediate-response scenarios.",
    },
    "standard": {
        "label": "Standard",
        "minutes_per_round": 60,
        "recommended_templates": ["air", "inland_water", "marine"],
        "description": "Balanced hour-scale stepping for most region-level simulations.",
    },
    "slow": {
        "label": "Slow",
        "minutes_per_round": 180,
        "recommended_templates": ["marine"],
        "description": "Longer steps for slower hydrological and coastal propagation.",
    },
}

DIFFUSION_PROVIDER_DEFAULTS = {
    "air": "open_meteo",
    "inland_water": "topology",
    "marine": "open_meteo",
    "generic": "heuristic",
    "atmospheric_plume": "open_meteo",
    "marine_current": "open_meteo",
    "inland_water_network": "topology",
    "surface_flood_flow": "topology",
    "coastal_inundation": "open_meteo",
    "ecological_mobility": "heuristic",
    "bio_ecological_transmission": "heuristic",
    "ash_plume": "open_meteo",
    "infrastructure_failure": "heuristic",
    "impact_blast": "heuristic",
    "slow_ecosystem_decline": "heuristic",
    "terrestrial_surface": "heuristic",
}

TIME_PLAN_UNIT_MINUTES = {
    "hour": 60,
    "day": 1440,
    "week": 10080,
    "month": 43200,
    "quarter": 129600,
    "year": 525600,
}

HAZARD_TEMPLATE_CATALOG: Dict[str, Dict[str, Any]] = {
    "coastal_radioactive_release": {
        "label": "核废水/近海放射性释放",
        "description": "围绕近海放射性物质释放、海流输运、生物累积与岸线暴露展开。",
        "impact_chain": ["海流输运", "沉积物滞留", "食物网累积", "岸线暴露"],
        "primary_family": "marine_current",
        "secondary_channels": ["sediment_retention", "food_web_bioaccumulation", "shoreline_exposure"],
    },
    "radioactive_fallout": {
        "label": "放射性沉降",
        "description": "围绕大气羽流、干湿沉降、地表径流和土壤累积展开。",
        "impact_chain": ["大气羽流", "干湿沉降", "地表径流", "土壤累积"],
        "primary_family": "atmospheric_plume",
        "secondary_channels": ["dry_wet_deposition", "surface_runoff", "soil_accumulation"],
    },
    "industrial_toxic_release": {
        "label": "工业有毒物质释放",
        "description": "适用于化工泄漏、危险品散逸以及生产设施释放场景。",
        "impact_chain": ["介质释放", "土壤或水体累积", "食物链暴露", "服务能力受压"],
        "primary_family": "terrestrial_surface",
        "secondary_channels": ["soil_accumulation", "food_chain_exposure", "service_disruption"],
        "allow_auto_primary_family": True,
    },
    "inland_water_contamination": {
        "label": "内陆水体污染",
        "description": "适用于河流、湖库、尾矿或污水外泄导致的流域污染。",
        "impact_chain": ["沿河输运", "库区滞留", "地下水交换", "灌溉暴露"],
        "primary_family": "inland_water_network",
        "secondary_channels": ["reservoir_retention", "groundwater_exchange", "irrigation_exposure"],
    },
    "marine_pollution_bloom": {
        "label": "海洋污染/赤潮",
        "description": "适用于近海污染、富营养化、赤潮与低氧链路。",
        "impact_chain": ["近海输运", "营养盐累积", "低氧区", "渔业暴露"],
        "primary_family": "marine_current",
        "secondary_channels": ["nutrient_accumulation", "hypoxia", "fishery_exposure"],
    },
    "wildfire_smoke_ash": {
        "label": "山火烟尘与灰烬",
        "description": "适用于山火烟尘扩散、灰烬径流、土壤疏水化与栖息地丧失。",
        "impact_chain": ["烟羽扩散", "灰烬径流", "土壤疏水化", "栖息地损失"],
        "primary_family": "atmospheric_plume",
        "secondary_channels": ["ash_runoff", "soil_hydrophobicity", "habitat_loss"],
    },
    "volcanic_eruption": {
        "label": "火山喷发",
        "description": "适用于火山灰、火山泥流、酸性沉降与下游泥沙压力。",
        "impact_chain": ["火山灰扩散", "火山泥流", "酸性沉降", "河道淤积"],
        "primary_family": "ash_plume",
        "secondary_channels": ["lahar_runoff", "acid_deposition", "river_siltation"],
    },
    "earthquake_secondary_cascade": {
        "label": "地震次生级联",
        "description": "适用于地震引发滑坡、液化、基础设施中断和次生泄漏。",
        "impact_chain": ["基础设施失效", "滑坡", "液化", "次生泄漏"],
        "primary_family": "infrastructure_failure",
        "secondary_channels": ["landslide", "liquefaction", "pipeline_release"],
    },
    "tsunami_inundation": {
        "label": "海啸淹没",
        "description": "适用于海啸、沿海淹没、盐水入侵和漂浮碎片冲击。",
        "impact_chain": ["沿海淹没", "盐水入侵", "漂浮碎片", "港湾污染"],
        "primary_family": "coastal_inundation",
        "secondary_channels": ["saline_intrusion", "debris_transport", "harbor_contamination"],
    },
    "flood_storm_surge": {
        "label": "洪水/风暴潮",
        "description": "适用于河洪、内涝、风暴潮和复合淹没场景。",
        "impact_chain": ["地表洪流", "污水外溢", "沉积再悬浮", "沿海回灌"],
        "primary_family": "surface_flood_flow",
        "secondary_channels": ["sewage_overflow", "sediment_rework", "coastal_backflow"],
    },
    "drought_ecosystem_stress": {
        "label": "干旱生态压力",
        "description": "适用于干旱、热浪和长期水资源压力驱动的生态退化。",
        "impact_chain": ["水资源短缺", "植被衰退", "生态脆弱性上升", "火险易感"],
        "primary_family": "slow_ecosystem_decline",
        "secondary_channels": ["water_shortage", "vegetation_dieback", "wildfire_susceptibility"],
    },
    "invasive_species_spread": {
        "label": "外来物种入侵",
        "description": "适用于物种扩散、建立、走廊传播和治理摩擦。",
        "impact_chain": ["扩散走廊", "人为携带", "种群建立", "治理摩擦"],
        "primary_family": "ecological_mobility",
        "secondary_channels": ["habitat_corridor", "human_transport_vector", "establishment_feedback"],
    },
    "pest_disease_ecology": {
        "label": "虫害/生态病害",
        "description": "适用于虫害、野生动物疫病和生态系统病害传播。",
        "impact_chain": ["宿主密度", "传播媒介移动", "栖息地破碎化", "生态受体损伤"],
        "primary_family": "bio_ecological_transmission",
        "secondary_channels": ["host_density", "vector_mobility", "habitat_fragmentation"],
    },
    "asteroid_impact_cascade": {
        "label": "小行星撞击级联",
        "description": "适用于撞击冲击波、抛射物、火灾和海啸级联。",
        "impact_chain": ["冲击波", "抛射物沉降", "次生火灾", "撞击海啸"],
        "primary_family": "impact_blast",
        "secondary_channels": ["ejecta_fallout", "wildfire_trigger", "impact_tsunami"],
    },
    "generic": {
        "label": "通用生态危机",
        "description": "在识别失败或输入过弱时使用的兜底模板。",
        "impact_chain": ["局地扩散", "生态受体承压", "社会响应波动"],
        "primary_family": "generic",
        "secondary_channels": ["environmental_link"],
    },
}

NODE_FAMILY_KEYWORDS = {
    "Region": ("region", "city", "county", "district", "province", "coast", "bay", "port", "island"),
    "EnvironmentalCarrier": ("current", "river", "air", "wind", "soil", "water", "ocean", "stream"),
    "EcologicalReceptor": ("fish", "bird", "habitat", "species", "crop", "reef", "forest", "wetland"),
    "HumanActor": ("resident", "fisher", "farmer", "consumer", "worker", "tourist", "citizen", "family"),
    "OrganizationActor": ("enterprise", "company", "ngo", "media", "school", "hospital", "market", "association"),
    "GovernmentActor": ("gov", "government", "agency", "authority", "bureau", "office", "regulator"),
    "Infrastructure": ("port", "plant", "hub", "road", "transport", "pipeline", "market", "hospital"),
}


def utcnow_iso() -> str:
    return datetime.now().isoformat()


def clamp_score(value: Any, lower: float = 0.0, upper: float = 100.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    if math.isnan(number) or math.isinf(number):
        number = lower
    return round(max(lower, min(upper, number)), 2)


def clamp_probability(value: Any) -> float:
    return clamp_score(value, 0.0, 1.0)


def normalize_state_vector(values: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    values = values or {}
    normalized = {}
    for field_name in STATE_VECTOR_SCHEMA:
        normalized[field_name] = clamp_score(values.get(field_name, BASELINE_STATE_VECTOR[field_name]))
    return normalized


def normalize_temporal_profile(
    profile: Optional[Dict[str, Any]] = None,
    total_rounds: Optional[int] = None,
) -> Dict[str, Any]:
    profile = dict(profile or {})
    preset = str(profile.get("preset") or "standard").strip().lower()
    if preset not in TEMPORAL_PRESETS:
        preset = "standard"
    defaults = TEMPORAL_PRESET_DEFAULTS[preset]
    minutes_per_round = max(10, int(profile.get("minutes_per_round") or defaults["minutes_per_round"]))
    resolved_total_rounds = total_rounds if total_rounds is not None else profile.get("total_rounds")
    resolved_total_rounds = max(4, int(resolved_total_rounds or 12))
    total_hours = round(resolved_total_rounds * minutes_per_round / 60, 1)
    return {
        "preset": preset,
        "label": defaults["label"],
        "description": defaults["description"],
        "minutes_per_round": minutes_per_round,
        "total_rounds": resolved_total_rounds,
        "total_simulation_hours": total_hours,
        "recommended_templates": list(defaults["recommended_templates"]),
    }


def normalize_transport_family(value: Optional[str]) -> str:
    normalized = str(value or "generic").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in LEGACY_TEMPLATE_TO_FAMILY:
        return LEGACY_TEMPLATE_TO_FAMILY[normalized]
    if normalized in TRANSPORT_FAMILIES:
        return normalized
    return "generic"


def compatibility_diffusion_template(value: Optional[str]) -> str:
    family = normalize_transport_family(value)
    return PRIMARY_FAMILY_TO_LEGACY.get(family, "generic")


def get_template_rules(value: Optional[str]) -> Dict[str, Any]:
    family = normalize_transport_family(value)
    return dict(DEFAULT_TEMPLATE_RULES.get(family, DEFAULT_TEMPLATE_RULES["generic"]))


def normalize_hazard_template_id(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in HAZARD_TEMPLATE_CATALOG:
        return normalized
    return "generic"


def get_hazard_template_definition(value: Optional[str]) -> Dict[str, Any]:
    template_id = normalize_hazard_template_id(value)
    return {"id": template_id, **dict(HAZARD_TEMPLATE_CATALOG.get(template_id, HAZARD_TEMPLATE_CATALOG["generic"]))}


def default_hazard_template_for_family(value: Optional[str]) -> str:
    family = normalize_transport_family(value)
    for template_id, definition in HAZARD_TEMPLATE_CATALOG.items():
        if normalize_transport_family(definition.get("primary_family")) == family:
            return template_id
    return "generic"


def build_transport_profile(
    primary_family: Optional[str],
    secondary_channels: Optional[List[str]] = None,
    context_provider: Optional[str] = None,
) -> Dict[str, Any]:
    family = normalize_transport_family(primary_family)
    rules = get_template_rules(family)
    provider = str(context_provider or DIFFUSION_PROVIDER_DEFAULTS.get(family, "heuristic"))
    return {
        "primary_family": family,
        "secondary_channels": list(secondary_channels or []),
        "default_lag_rounds": max(0, int(rules.get("default_lag_rounds", 1))),
        "default_decay": clamp_probability(rules.get("default_decay", 0.88)),
        "default_persistence": clamp_score(rules.get("default_persistence", 55)),
        "max_neighbor_spread": max(1, int(rules.get("max_neighbor_spread", 2))),
        "context_provider": provider,
    }


def suggest_temporal_preset(minutes_per_round: int) -> str:
    if minutes_per_round <= 30:
        return "rapid"
    if minutes_per_round >= 120:
        return "slow"
    return "standard"


def minutes_to_time_plan_unit(minutes_per_round: int) -> tuple[str, int]:
    rounded = max(10, int(minutes_per_round or 60))
    for unit, unit_minutes in (
        ("year", TIME_PLAN_UNIT_MINUTES["year"]),
        ("quarter", TIME_PLAN_UNIT_MINUTES["quarter"]),
        ("month", TIME_PLAN_UNIT_MINUTES["month"]),
        ("week", TIME_PLAN_UNIT_MINUTES["week"]),
        ("day", TIME_PLAN_UNIT_MINUTES["day"]),
        ("hour", TIME_PLAN_UNIT_MINUTES["hour"]),
    ):
        if rounded >= unit_minutes and rounded % unit_minutes == 0:
            return unit, max(1, rounded // unit_minutes)
    if rounded % 60 == 0:
        return "hour", max(1, rounded // 60)
    return "hour", max(1, round(rounded / 60))


def format_total_coverage(total_rounds: int, step_unit: str, step_size: int) -> str:
    unit_labels = {
        "hour": "小时",
        "day": "天",
        "week": "周",
        "month": "个月",
        "quarter": "个季度",
        "year": "年",
    }
    total_units = max(1, int(total_rounds or 1)) * max(1, int(step_size or 1))
    return f"{total_units} {unit_labels.get(step_unit, step_unit)}"


def normalize_time_plan(
    time_plan: Optional[Dict[str, Any]] = None,
    *,
    total_rounds: Optional[int] = None,
    minutes_per_round: Optional[int] = None,
    preset: Optional[str] = None,
    reference_time: str = "",
    reasoning_summary: str = "",
    source: str = "auto",
) -> Dict[str, Any]:
    payload = dict(time_plan or {})
    resolved_rounds = max(4, int(payload.get("total_rounds") or total_rounds or 12))
    if payload.get("step_unit") in TIME_PLAN_UNITS:
        step_unit = str(payload.get("step_unit"))
        step_size = max(1, int(payload.get("step_size") or 1))
        resolved_minutes = TIME_PLAN_UNIT_MINUTES[step_unit] * step_size
    else:
        resolved_minutes = max(10, int(payload.get("minutes_per_round") or minutes_per_round or 60))
        step_unit, step_size = minutes_to_time_plan_unit(resolved_minutes)
    resolved_preset = str(payload.get("preset") or preset or suggest_temporal_preset(resolved_minutes))
    total_hours = round(resolved_rounds * resolved_minutes / 60, 1)
    return {
        "step_unit": step_unit,
        "step_size": step_size,
        "total_rounds": resolved_rounds,
        "total_coverage_label": str(
            payload.get("total_coverage_label") or format_total_coverage(resolved_rounds, step_unit, step_size)
        ),
        "reference_time": str(payload.get("reference_time") or reference_time or ""),
        "reasoning_summary": str(payload.get("reasoning_summary") or reasoning_summary or ""),
        "source": str(payload.get("source") or source or "auto"),
        "minutes_per_round": resolved_minutes,
        "total_simulation_hours": total_hours,
        "preset": resolved_preset if resolved_preset in TEMPORAL_PRESETS else suggest_temporal_preset(resolved_minutes),
    }


def merge_state_vectors(base: Dict[str, Any], delta: Optional[Dict[str, Any]]) -> Dict[str, float]:
    result = normalize_state_vector(base)
    for field_name, value in (delta or {}).items():
        if field_name in result:
            result[field_name] = clamp_score(result[field_name] + float(value))
    return result


def default_state_vector(
    scenario_mode: str = "baseline_mode",
    node_family: str = "HumanActor",
) -> Dict[str, float]:
    family_offsets = {
        "EnvironmentalCarrier": {
            "spread_pressure": 14,
            "ecosystem_integrity": -6,
            "vulnerability_score": -8,
        },
        "EcologicalReceptor": {
            "ecosystem_integrity": -12,
            "livelihood_stability": -4,
            "vulnerability_score": 12,
        },
        "GovernmentActor": {
            "public_trust": 8,
            "response_capacity": 12,
            "panic_level": -6,
        },
        "OrganizationActor": {
            "service_capacity": 8,
            "economic_stress": 6,
        },
        "Infrastructure": {
            "service_capacity": 10,
            "vulnerability_score": 8,
        },
        "Region": {
            "response_capacity": 4,
            "service_capacity": 4,
        },
    }
    vector = dict(CRISIS_STATE_VECTOR if scenario_mode == "crisis_mode" else BASELINE_STATE_VECTOR)
    for key, delta in family_offsets.get(node_family, {}).items():
        vector[key] = clamp_score(vector[key] + delta)
    return normalize_state_vector(vector)


def ensure_unique_slug(name: str, used: set[str]) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_") or "region"
    slug = "_".join(part for part in slug.split("_") if part)
    candidate = slug
    index = 2
    while candidate in used:
        candidate = f"{slug}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def infer_node_family(entity_type: Optional[str], name: str = "", summary: str = "") -> str:
    haystack = f"{entity_type or ''} {name} {summary}".lower()
    for family, keywords in NODE_FAMILY_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return family
    return "HumanActor"


def score_band(value: Any) -> str:
    score = clamp_score(value)
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


@dataclass
class RegionNode:
    region_id: str
    name: str
    region_type: str = "region"
    description: str = ""
    parent_region_id: Optional[str] = None
    layer: str = "macro"
    land_use_class: str = ""
    distance_band: str = ""
    neighbors: List[str] = field(default_factory=list)
    carriers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    ecology_assets: List[str] = field(default_factory=list)
    industry_tags: List[str] = field(default_factory=list)
    resident_agent_ids: List[int] = field(default_factory=list)
    organization_agent_ids: List[int] = field(default_factory=list)
    ecology_agent_ids: List[int] = field(default_factory=list)
    region_constraints: List[str] = field(default_factory=list)
    exposure_channels: List[str] = field(default_factory=list)
    population_capacity: int = 0
    lat: Optional[float] = None
    lon: Optional[float] = None
    state_vector: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state_vector"] = normalize_state_vector(self.state_vector)
        payload["neighbors"] = sorted(set(self.neighbors))
        payload["carriers"] = sorted(set(self.carriers))
        payload["tags"] = sorted(set(self.tags))
        payload["ecology_assets"] = sorted(set(self.ecology_assets))
        payload["industry_tags"] = sorted(set(self.industry_tags))
        payload["resident_agent_ids"] = sorted(set(self.resident_agent_ids))
        payload["organization_agent_ids"] = sorted(set(self.organization_agent_ids))
        payload["ecology_agent_ids"] = sorted(set(self.ecology_agent_ids))
        payload["region_constraints"] = sorted(set(self.region_constraints))
        payload["exposure_channels"] = sorted(set(self.exposure_channels))
        payload["population_capacity"] = max(0, int(self.population_capacity or 0))
        payload["lat"] = round(float(self.lat), 6) if self.lat is not None else None
        payload["lon"] = round(float(self.lon), 6) if self.lon is not None else None
        return payload


@dataclass
class TransportEdge:
    edge_id: str
    source_region_id: str
    target_region_id: str
    channel_type: str = "environmental_link"
    directionality: str = "directed"
    origin: str = "rule_inferred"
    travel_time_rounds: int = 1
    attenuation_rate: float = 0.15
    retention_factor: float = 0.0
    barrier_factor: float = 0.0
    strength: float = 0.6
    confidence: float = 0.6
    evidence: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_region_id": self.source_region_id,
            "target_region_id": self.target_region_id,
            "channel_type": self.channel_type or "environmental_link",
            "directionality": self.directionality or "directed",
            "origin": self.origin or "rule_inferred",
            "travel_time_rounds": max(0, int(self.travel_time_rounds or 0)),
            "attenuation_rate": clamp_probability(self.attenuation_rate),
            "retention_factor": clamp_probability(self.retention_factor),
            "barrier_factor": clamp_probability(self.barrier_factor),
            "strength": clamp_probability(self.strength),
            "confidence": clamp_probability(self.confidence),
            "evidence": dict(self.evidence or {}),
            "rationale": self.rationale or "",
            "metadata": dict(self.metadata or {}),
        }


@dataclass
class InjectedVariable:
    variable_id: str
    type: str
    template: str
    name: str
    description: str = ""
    target_regions: List[str] = field(default_factory=list)
    target_nodes: List[int] = field(default_factory=list)
    start_round: int = 0
    duration_rounds: int = 1
    intensity_0_100: float = 50.0
    policy_mode: Optional[str] = None
    source_origin: str = "manual"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "type": self.type if self.type in VARIABLE_TYPES else "disaster",
            "template": self.template if self.template in DIFFUSION_TEMPLATES else "generic",
            "name": self.name,
            "description": self.description,
            "target_regions": self.target_regions,
            "target_nodes": self.target_nodes,
            "start_round": max(0, int(self.start_round)),
            "duration_rounds": max(1, int(self.duration_rounds)),
            "intensity_0_100": clamp_score(self.intensity_0_100),
            "policy_mode": self.policy_mode if self.policy_mode in POLICY_MODES else None,
            "source_origin": self.source_origin if self.source_origin in {"seed", "manual", "runtime"} else "manual",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_index: int = 1) -> "InjectedVariable":
        return cls(
            variable_id=str(data.get("variable_id") or f"var_{default_index}"),
            type=str(data.get("type") or "disaster"),
            template=str(data.get("template") or "generic"),
            name=str(data.get("name") or data.get("title") or f"Variable {default_index}"),
            description=str(data.get("description") or ""),
            target_regions=list(data.get("target_regions") or []),
            target_nodes=[int(item) for item in (data.get("target_nodes") or []) if str(item).isdigit()],
            start_round=int(data.get("start_round") or 0),
            duration_rounds=int(data.get("duration_rounds") or 1),
            intensity_0_100=clamp_score(data.get("intensity_0_100", data.get("intensity", 50))),
            policy_mode=data.get("policy_mode"),
            source_origin=str(data.get("source_origin") or "manual"),
        )


@dataclass
class EnvAgentProfile:
    agent_id: int
    username: str
    name: str
    node_family: str
    role_type: str
    bio: str
    persona: str
    profession: str
    primary_region: str
    agent_type: str = "human"
    agent_subtype: str = ""
    archetype_key: str = ""
    home_region_id: str = ""
    home_subregion_id: str = ""
    influenced_regions: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    sensitivities: List[str] = field(default_factory=list)
    motivation_stack: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    action_space: List[str] = field(default_factory=list)
    decision_policy: Dict[str, Any] = field(default_factory=dict)
    impact_profile: Dict[str, float] = field(default_factory=dict)
    stance_profile: Dict[str, float] = field(default_factory=dict)
    resource_budget: Dict[str, float] = field(default_factory=dict)
    counterpart_agent_ids: List[int] = field(default_factory=list)
    social_links: List[int] = field(default_factory=list)
    ecology_links: List[int] = field(default_factory=list)
    organization_id: Optional[int] = None
    spawn_weight: float = 1.0
    is_synthesized: bool = False
    state_vector: Dict[str, float] = field(default_factory=dict)
    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None
    generation_mode: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    evidence_confidence: float = 0.0
    review_status: str = ""
    grounding_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state_vector"] = normalize_state_vector(self.state_vector)
        primary_region = self.primary_region or self.home_region_id
        payload["influenced_regions"] = list(dict.fromkeys(self.influenced_regions or [primary_region]))
        payload["home_region_id"] = self.home_region_id or primary_region
        payload["counterpart_agent_ids"] = sorted(set(self.counterpart_agent_ids))
        payload["social_links"] = sorted(set(self.social_links))
        payload["ecology_links"] = sorted(set(self.ecology_links))
        payload["motivation_stack"] = list(dict.fromkeys(self.motivation_stack))
        payload["capabilities"] = list(dict.fromkeys(self.capabilities))
        payload["constraints"] = list(dict.fromkeys(self.constraints))
        payload["action_space"] = list(dict.fromkeys(self.action_space))
        payload["goals"] = list(dict.fromkeys(self.goals))
        payload["sensitivities"] = list(dict.fromkeys(self.sensitivities))
        payload["spawn_weight"] = clamp_probability(self.spawn_weight)
        payload["evidence_refs"] = list(dict.fromkeys(self.evidence_refs))
        payload["evidence_confidence"] = clamp_probability(self.evidence_confidence)
        return payload

    def to_agent_config(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.username,
            "name": self.name,
            "node_family": self.node_family,
            "role_type": self.role_type,
            "agent_type": self.agent_type,
            "agent_subtype": self.agent_subtype,
            "archetype_key": self.archetype_key,
            "profession": self.profession,
            "primary_region": self.primary_region,
            "home_region_id": self.home_region_id or self.primary_region,
            "home_subregion_id": self.home_subregion_id,
            "influenced_regions": list(dict.fromkeys(self.influenced_regions or [self.primary_region])),
            "goals": self.goals,
            "sensitivities": self.sensitivities,
            "motivation_stack": self.motivation_stack,
            "capabilities": self.capabilities,
            "constraints": self.constraints,
            "action_space": self.action_space,
            "decision_policy": self.decision_policy,
            "impact_profile": self.impact_profile,
            "stance_profile": self.stance_profile,
            "resource_budget": self.resource_budget,
            "counterpart_agent_ids": sorted(set(self.counterpart_agent_ids)),
            "social_links": sorted(set(self.social_links)),
            "ecology_links": sorted(set(self.ecology_links)),
            "organization_id": self.organization_id,
            "spawn_weight": clamp_probability(self.spawn_weight),
            "is_synthesized": bool(self.is_synthesized),
            "state_vector": normalize_state_vector(self.state_vector),
            "bio": self.bio,
            "persona": self.persona,
            "source_entity_uuid": self.source_entity_uuid,
            "source_entity_type": self.source_entity_type,
            "generation_mode": self.generation_mode,
            "evidence_refs": list(dict.fromkeys(self.evidence_refs)),
            "evidence_confidence": clamp_probability(self.evidence_confidence),
            "review_status": self.review_status,
            "grounding_reason": self.grounding_reason,
        }

    def to_reddit_format(self) -> Dict[str, Any]:
        profile = {
            "user_id": self.agent_id,
            "username": self.username,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "profession": self.profession,
            "primary_region": self.primary_region,
            "node_family": self.node_family,
            "role_type": self.role_type,
            "agent_type": self.agent_type,
            "agent_subtype": self.agent_subtype,
            "home_subregion_id": self.home_subregion_id,
            "generation_mode": self.generation_mode,
            "evidence_confidence": clamp_probability(self.evidence_confidence),
            "interested_topics": self.goals[:6],
            "created_at": self.created_at,
        }
        profile.update(normalize_state_vector(self.state_vector))
        return profile

    def to_twitter_format(self) -> Dict[str, Any]:
        profile = {
            "user_id": self.agent_id,
            "username": self.username,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "profession": self.profession,
            "primary_region": self.primary_region,
            "node_family": self.node_family,
            "role_type": self.role_type,
            "agent_type": self.agent_type,
            "agent_subtype": self.agent_subtype,
            "home_subregion_id": self.home_subregion_id,
            "generation_mode": self.generation_mode,
            "evidence_confidence": clamp_probability(self.evidence_confidence),
            "friend_count": 80 + self.agent_id * 3,
            "follower_count": 120 + self.agent_id * 5,
            "statuses_count": 40 + self.agent_id * 4,
            "created_at": self.created_at,
        }
        profile.update(normalize_state_vector(self.state_vector))
        return profile


@dataclass
class AgentRelationshipEdge:
    edge_id: str
    source_agent_id: int
    target_agent_id: int
    relation_type: str
    strength: float = 0.5
    interaction_channel: str = "social"
    rationale: str = ""
    source_region_id: str = ""
    target_region_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_agent_id": int(self.source_agent_id),
            "target_agent_id": int(self.target_agent_id),
            "relation_type": self.relation_type,
            "strength": clamp_probability(self.strength),
            "interaction_channel": self.interaction_channel,
            "rationale": self.rationale,
            "source_region_id": self.source_region_id,
            "target_region_id": self.target_region_id,
        }


@dataclass
class EnvProfileGenerationResult:
    regions: List[RegionNode]
    subregions: List[RegionNode]
    profiles: List[EnvAgentProfile]
    agent_relationships: List[AgentRelationshipEdge]
    transport_edges: List[TransportEdge]
    region_agent_index: Dict[str, Any]
    grounding_summary: Dict[str, Any]
    diffusion_context: Dict[str, Any] = field(default_factory=dict)
    generation_notes: List[str] = field(default_factory=list)
    generation_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regions": [region.to_dict() for region in self.regions],
            "subregions": [region.to_dict() for region in self.subregions],
            "profiles": [profile.to_dict() for profile in self.profiles],
            "agent_relationships": [edge.to_dict() for edge in self.agent_relationships],
            "transport_edges": [edge.to_dict() for edge in self.transport_edges],
            "region_agent_index": self.region_agent_index,
            "grounding_summary": self.grounding_summary,
            "diffusion_context": self.diffusion_context,
            "generation_notes": self.generation_notes,
            "generation_summary": self.generation_summary,
        }


@dataclass
class RiskEvidence:
    evidence_id: str
    source_type: str
    title: str
    summary: str
    confidence: float = 0.6
    source_ref: str = ""
    related_chain_steps: List[str] = field(default_factory=list)
    region_scope: List[str] = field(default_factory=list)
    entity_refs: List[str] = field(default_factory=list)
    extracted_facts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["confidence"] = clamp_probability(self.confidence)
        payload["related_chain_steps"] = list(dict.fromkeys(self.related_chain_steps))
        payload["region_scope"] = list(dict.fromkeys(self.region_scope))
        payload["entity_refs"] = list(dict.fromkeys(self.entity_refs))
        payload["extracted_facts"] = list(dict.fromkeys(self.extracted_facts))
        return payload


@dataclass
class RiskAffectedCluster:
    cluster_id: str
    name: str
    cluster_type: str
    primary_regions: List[str] = field(default_factory=list)
    actor_ids: List[int] = field(default_factory=list)
    dependency_profile: List[str] = field(default_factory=list)
    early_loss_signals: List[str] = field(default_factory=list)
    vulnerability_score: float = 0.0
    mismatch_risk: float = 0.0
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["primary_regions"] = list(dict.fromkeys(self.primary_regions))
        payload["actor_ids"] = sorted(set(self.actor_ids))
        payload["dependency_profile"] = list(dict.fromkeys(self.dependency_profile))
        payload["early_loss_signals"] = list(dict.fromkeys(self.early_loss_signals))
        payload["vulnerability_score"] = clamp_score(self.vulnerability_score)
        payload["mismatch_risk"] = clamp_score(self.mismatch_risk)
        return payload


@dataclass
class RiskInterventionOption:
    intervention_id: str
    name: str
    policy_type: str
    description: str = ""
    target_chain_steps: List[str] = field(default_factory=list)
    expected_direct_effects: List[str] = field(default_factory=list)
    expected_second_order_effects: List[str] = field(default_factory=list)
    benefit_clusters: List[str] = field(default_factory=list)
    hurt_clusters: List[str] = field(default_factory=list)
    friction_points: List[str] = field(default_factory=list)
    confidence: float = 0.55
    source_variable_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["policy_type"] = self.policy_type if self.policy_type in POLICY_MODES else "monitor"
        payload["target_chain_steps"] = list(dict.fromkeys(self.target_chain_steps))
        payload["expected_direct_effects"] = list(dict.fromkeys(self.expected_direct_effects))
        payload["expected_second_order_effects"] = list(dict.fromkeys(self.expected_second_order_effects))
        payload["benefit_clusters"] = list(dict.fromkeys(self.benefit_clusters))
        payload["hurt_clusters"] = list(dict.fromkeys(self.hurt_clusters))
        payload["friction_points"] = list(dict.fromkeys(self.friction_points))
        payload["confidence"] = clamp_probability(self.confidence)
        return payload


@dataclass
class RiskScenarioBranch:
    branch_id: str
    name: str
    description: str
    assumptions: List[str] = field(default_factory=list)
    target_interventions: List[str] = field(default_factory=list)
    comparison_focus: List[str] = field(default_factory=list)
    branch_type: str = "baseline"

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["assumptions"] = list(dict.fromkeys(self.assumptions))
        payload["target_interventions"] = list(dict.fromkeys(self.target_interventions))
        payload["comparison_focus"] = list(dict.fromkeys(self.comparison_focus))
        return payload


@dataclass
class RiskObject:
    risk_object_id: str
    title: str
    summary: str
    why_now: str
    risk_type: str
    mode: str = "watch"
    status: str = "candidate"
    time_horizon: str = "30d"
    region_scope: List[str] = field(default_factory=list)
    primary_regions: List[str] = field(default_factory=list)
    severity_score: float = 0.0
    confidence_score: float = 0.0
    actionability_score: float = 0.0
    novelty_score: float = 0.0
    root_pressures: List[str] = field(default_factory=list)
    chain_steps: List[str] = field(default_factory=list)
    turning_points: List[str] = field(default_factory=list)
    amplifiers: List[str] = field(default_factory=list)
    buffers: List[str] = field(default_factory=list)
    source_entity_uuids: List[str] = field(default_factory=list)
    source_variable_ids: List[str] = field(default_factory=list)
    evidence: List[RiskEvidence] = field(default_factory=list)
    affected_clusters: List[RiskAffectedCluster] = field(default_factory=list)
    intervention_options: List[RiskInterventionOption] = field(default_factory=list)
    scenario_branches: List[RiskScenarioBranch] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_object_id": self.risk_object_id,
            "title": self.title,
            "summary": self.summary,
            "why_now": self.why_now,
            "risk_type": self.risk_type,
            "mode": self.mode,
            "status": self.status,
            "time_horizon": self.time_horizon,
            "region_scope": list(dict.fromkeys(self.region_scope)),
            "primary_regions": list(dict.fromkeys(self.primary_regions)),
            "severity_score": clamp_score(self.severity_score),
            "confidence_score": clamp_probability(self.confidence_score),
            "actionability_score": clamp_score(self.actionability_score),
            "novelty_score": clamp_score(self.novelty_score),
            "root_pressures": list(dict.fromkeys(self.root_pressures)),
            "chain_steps": list(dict.fromkeys(self.chain_steps)),
            "turning_points": list(dict.fromkeys(self.turning_points)),
            "amplifiers": list(dict.fromkeys(self.amplifiers)),
            "buffers": list(dict.fromkeys(self.buffers)),
            "source_entity_uuids": list(dict.fromkeys(self.source_entity_uuids)),
            "source_variable_ids": list(dict.fromkeys(self.source_variable_ids)),
            "evidence": [item.to_dict() for item in self.evidence],
            "affected_clusters": [item.to_dict() for item in self.affected_clusters],
            "intervention_options": [item.to_dict() for item in self.intervention_options],
            "scenario_branches": [item.to_dict() for item in self.scenario_branches],
            "created_at": self.created_at,
        }


@dataclass
class RiskObjectBuildResult:
    risk_objects: List[RiskObject]
    primary_risk_object_id: str = ""
    generation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        primary = None
        if self.primary_risk_object_id:
            for item in self.risk_objects:
                if item.risk_object_id == self.primary_risk_object_id:
                    primary = item.to_dict()
                    break
        return {
            "primary_risk_object_id": self.primary_risk_object_id,
            "risk_objects_count": len(self.risk_objects),
            "risk_objects": [item.to_dict() for item in self.risk_objects],
            "primary_risk_object": primary,
            "generation_notes": self.generation_notes,
        }


@dataclass
class RiskScopeRegionRef:
    region_id: str
    region_name: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": str(self.region_id or ""),
            "region_name": str(self.region_name or self.region_id or ""),
        }


@dataclass
class RiskScopeEntityRef:
    entity_uuid: str
    entity_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_uuid": str(self.entity_uuid or ""),
            "entity_name": str(self.entity_name or self.entity_uuid or ""),
        }


@dataclass
class RiskScopeActorRef:
    actor_id: int
    actor_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actor_id": int(self.actor_id),
            "actor_name": str(self.actor_name or self.actor_id),
        }


@dataclass
class RiskChainStepDefinition:
    step_id: str
    label: str
    step_type: str = "generic"
    monitor_metrics: List[str] = field(default_factory=list)
    threshold_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "label": self.label,
            "step_type": self.step_type or "generic",
            "monitor_metrics": list(dict.fromkeys(self.monitor_metrics)),
            "threshold_notes": list(dict.fromkeys(self.threshold_notes)),
        }


@dataclass
class RiskDefinition:
    risk_id: str
    title: str
    summary: str
    category: str = "baseline"
    risk_type: str = ""
    status: str = "tracked"
    mode: str = "watch"
    time_horizon: str = "30d"
    legacy_risk_object_id: str = ""
    priority_seed: float = 0.0
    scope_regions: List[RiskScopeRegionRef] = field(default_factory=list)
    scope_entities: List[RiskScopeEntityRef] = field(default_factory=list)
    scope_actors: List[RiskScopeActorRef] = field(default_factory=list)
    chain_template: List[RiskChainStepDefinition] = field(default_factory=list)
    root_pressures: List[str] = field(default_factory=list)
    turning_point_candidates: List[str] = field(default_factory=list)
    amplifiers: List[str] = field(default_factory=list)
    buffers: List[str] = field(default_factory=list)
    source_entity_uuids: List[str] = field(default_factory=list)
    source_variable_ids: List[str] = field(default_factory=list)
    evidence: List[RiskEvidence] = field(default_factory=list)
    affected_clusters: List[RiskAffectedCluster] = field(default_factory=list)
    intervention_templates: List[RiskInterventionOption] = field(default_factory=list)
    branch_templates: List[RiskScenarioBranch] = field(default_factory=list)
    trigger_rules: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "legacy_risk_object_id": self.legacy_risk_object_id or self.risk_id,
            "category": self.category or "baseline",
            "risk_type": self.risk_type,
            "title": self.title,
            "summary": self.summary,
            "status": self.status or "tracked",
            "mode": self.mode or "watch",
            "time_horizon": self.time_horizon or "30d",
            "priority_seed": clamp_probability(self.priority_seed),
            "scope": {
                "regions": [item.to_dict() for item in self.scope_regions],
                "entities": [item.to_dict() for item in self.scope_entities],
                "actors": [item.to_dict() for item in self.scope_actors],
            },
            "chain_template": [item.to_dict() for item in self.chain_template],
            "root_pressures": list(dict.fromkeys(self.root_pressures)),
            "turning_point_candidates": list(dict.fromkeys(self.turning_point_candidates)),
            "amplifiers": list(dict.fromkeys(self.amplifiers)),
            "buffers": list(dict.fromkeys(self.buffers)),
            "source_entity_uuids": list(dict.fromkeys(self.source_entity_uuids)),
            "source_variable_ids": list(dict.fromkeys(self.source_variable_ids)),
            "evidence": [item.to_dict() for item in self.evidence],
            "affected_clusters": [item.to_dict() for item in self.affected_clusters],
            "intervention_templates": [item.to_dict() for item in self.intervention_templates],
            "branch_templates": [item.to_dict() for item in self.branch_templates],
            "trigger_rules": dict(self.trigger_rules or {}),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class RiskStepRuntimeState:
    step_id: str
    label: str
    status: str = "inactive"
    score: float = 0.0
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "label": self.label,
            "status": self.status or "inactive",
            "score": clamp_probability(self.score),
            "evidence_refs": list(dict.fromkeys(self.evidence_refs)),
        }


@dataclass
class RiskRuntimeState:
    risk_id: str
    title: str
    round: int
    category: str = "baseline"
    risk_type: str = ""
    severity_score: float = 0.0
    confidence_score: float = 0.0
    trend: str = "stable"
    runtime_priority: float = 0.0
    active_step_ids: List[str] = field(default_factory=list)
    step_states: List[RiskStepRuntimeState] = field(default_factory=list)
    impacted_regions: List[RiskScopeRegionRef] = field(default_factory=list)
    impacted_actors: List[RiskScopeActorRef] = field(default_factory=list)
    related_dynamic_edge_ids: List[str] = field(default_factory=list)
    drivers: List[str] = field(default_factory=list)
    buffers: List[str] = field(default_factory=list)
    turning_points: List[str] = field(default_factory=list)
    explanation: str = ""
    triggered_by_event_ids: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "title": self.title,
            "round": max(0, int(self.round or 0)),
            "category": self.category or "baseline",
            "risk_type": self.risk_type,
            "severity_score": clamp_score(self.severity_score),
            "confidence_score": clamp_probability(self.confidence_score),
            "trend": self.trend or "stable",
            "runtime_priority": clamp_probability(self.runtime_priority),
            "active_step_ids": list(dict.fromkeys(self.active_step_ids)),
            "step_states": [item.to_dict() for item in self.step_states],
            "impacted_regions": [item.to_dict() for item in self.impacted_regions],
            "impacted_actors": [item.to_dict() for item in self.impacted_actors],
            "related_dynamic_edge_ids": list(dict.fromkeys(self.related_dynamic_edge_ids)),
            "drivers": list(dict.fromkeys(self.drivers)),
            "buffers": list(dict.fromkeys(self.buffers)),
            "turning_points": list(dict.fromkeys(self.turning_points)),
            "explanation": self.explanation,
            "triggered_by_event_ids": list(dict.fromkeys(self.triggered_by_event_ids)),
            "updated_at": self.updated_at,
        }


@dataclass
class RiskEvent:
    event_id: str
    round: int
    event_type: str
    risk_id: str
    source_ref: str = ""
    summary: str = ""
    delta: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "round": max(0, int(self.round or 0)),
            "event_type": self.event_type,
            "risk_id": self.risk_id,
            "source_ref": self.source_ref,
            "summary": self.summary,
            "delta": dict(self.delta or {}),
            "evidence_refs": list(dict.fromkeys(self.evidence_refs)),
            "timestamp": self.timestamp,
        }


@dataclass
class RiskDefinitionBuildResult:
    risk_definitions: List[RiskDefinition]
    primary_risk_id: str = ""
    generation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        primary = None
        if self.primary_risk_id:
            for item in self.risk_definitions:
                if item.risk_id == self.primary_risk_id:
                    primary = item.to_dict()
                    break
        return {
            "primary_risk_id": self.primary_risk_id,
            "risk_definition_count": len(self.risk_definitions),
            "risk_definitions": [item.to_dict() for item in self.risk_definitions],
            "primary_risk_definition": primary,
            "generation_notes": self.generation_notes,
        }


@dataclass
class RiskRuntimeStateBundle:
    round: int
    risk_states: List[RiskRuntimeState]
    primary_active_risk_id: str = ""
    pinned_risk_ids: List[str] = field(default_factory=list)
    refresh_reason: str = ""
    updated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        primary = None
        for item in self.risk_states:
            if item.risk_id == self.primary_active_risk_id:
                primary = item.to_dict()
                break
        return {
            "round": max(0, int(self.round or 0)),
            "updated_at": self.updated_at,
            "refresh_reason": self.refresh_reason,
            "primary_active_risk_id": self.primary_active_risk_id,
            "pinned_risk_ids": list(dict.fromkeys(self.pinned_risk_ids)),
            "risk_states": [item.to_dict() for item in self.risk_states],
            "primary_active_risk": primary,
        }


def dump_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_profiles_csv(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    rows = list(rows)
    fieldnames: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
