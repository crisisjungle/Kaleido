"""
EnvFish simulation config synthesis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .envfish_models import (
    ENVFISH_ENGINE_MODE,
    EnvAgentProfile,
    HAZARD_TEMPLATE_CATALOG,
    InjectedVariable,
    RegionNode,
    RiskDefinition,
    RiskObject,
    STATE_VECTOR_SCHEMA,
    TIME_PLAN_UNIT_MINUTES,
    TransportEdge,
    build_transport_profile,
    compatibility_diffusion_template,
    default_hazard_template_for_family,
    get_hazard_template_definition,
    normalize_hazard_template_id,
    normalize_temporal_profile,
    normalize_time_plan,
    normalize_transport_family,
    suggest_temporal_preset,
)
from .mechanism_simulation_service import (
    LEGACY_SIMULATION_ARCHITECTURE,
    normalize_simulation_architecture,
)

logger = get_logger("envfish.envfish_config")


SCENARIO_PLANNER_REPORT_FOCUS_ZH = [
    "事件链与传播机制",
    "风险对象与关键暴露",
    "区域脆弱性变化",
    "代理体行动与关系演化",
    "政策措施效果与副作用",
    "假设、置信度与模型边界",
]


def _contains_chinese_text(value: Any) -> bool:
    text = str(value or "")
    return any("\u3400" <= char <= "\u9fff" for char in text)


def build_scenario_planner_display_projection(
    scenario_planning_input: Optional[Dict[str, Any]],
    *,
    scenario_model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build Chinese display copy from the reviewed Step 2 artifact.

    The ScenarioPlanner contract contains machine identifiers alongside display
    fields.  Persisted config/report surfaces must not render those identifiers
    (or an English legacy-LLM fallback) as user-facing copy, so this projection
    derives a compact Chinese header from the authoritative mechanism graph.
    It does not alter any planning decision.
    """

    planning = dict(scenario_planning_input or {})
    graph = dict(planning.get("event_mechanism_graph") or {})
    nodes = [item for item in (graph.get("nodes") or []) if isinstance(item, dict)]
    edges = [item for item in (graph.get("edges") or []) if isinstance(item, dict)]
    policies = [
        item
        for item in (planning.get("normalized_user_policies") or planning.get("policy_plan") or [])
        if isinstance(item, dict)
    ]
    role_demands = [item for item in (planning.get("role_demands") or []) if isinstance(item, dict)]

    labels: List[str] = []
    for node in nodes:
        label = str(node.get("label_zh") or "").strip()
        if label and _contains_chinese_text(label) and label not in labels:
            labels.append(label)

    event_phrase = "、".join(labels[:4])
    if event_phrase:
        scenario_title = " → ".join(labels[:3])
        scenario_summary = (
            f"本场景围绕{event_phrase}展开，系统已规划 {len(nodes)} 个事件节点、"
            f"{len(edges)} 条机制链路和 {len(policies)} 项政策措施。"
        )
    else:
        scenario_title = "复合事件推演场景"
        scenario_summary = (
            f"本场景已规划 {len(nodes)} 个事件节点、{len(edges)} 条机制链路和"
            f" {len(policies)} 项政策措施，具体内容以第二步审阅结果为准。"
        )

    generation_reasoning = (
        "系统采用第二步已审阅的事件机制图作为场景事实源，并据此生成时间阶段、"
        f"政策作用计划和 {len(role_demands)} 项角色能力需求；旧模板仅保留为运行时兼容投影。"
    )
    localized_model = dict(scenario_model or {})
    localized_model.update(
        {
            "scenario_title": scenario_title,
            "scenario_summary": scenario_summary,
            "core_processes": labels[:16],
        }
    )
    return {
        "scenario_title": scenario_title,
        "scenario_summary": scenario_summary,
        "generation_reasoning": generation_reasoning,
        "round_label": "推演轮次",
        "report_focus": list(SCENARIO_PLANNER_REPORT_FOCUS_ZH),
        "uncertainty_explanation": "置信度反映当前证据、系统推断与模型一致性，不代表物理确定性。",
        "scenario_model": localized_model,
    }


def build_scenario_temporal_runtime_projection(
    temporal_plan: Optional[Dict[str, Any]],
    *,
    reference_time: str = "",
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Project Step 2 ``TemporalPlan`` without changing its decisions.

    ``TemporalPlan`` uses ``step_value`` while the legacy runtime calls the same
    value ``step_size``.  This adapter only translates field names and derives
    minutes/hours; it never applies a hazard-template preset or chooses a new
    round count.
    """

    canonical = dict(temporal_plan or {})
    step_unit = str(canonical.get("step_unit") or "day")
    if step_unit not in TIME_PLAN_UNIT_MINUTES:
        raise ValueError(f"Step 2 时间单位无效: {step_unit}")
    step_value = max(1, int(canonical.get("step_value") or canonical.get("step_size") or 1))
    total_rounds = max(1, int(canonical.get("total_rounds") or 1))
    minutes_per_round = TIME_PLAN_UNIT_MINUTES[step_unit] * step_value
    total_hours = round(total_rounds * minutes_per_round / 60, 1)
    preset = suggest_temporal_preset(minutes_per_round)

    temporal_profile = normalize_temporal_profile(
        {
            "preset": preset,
            "total_rounds": total_rounds,
            "minutes_per_round": minutes_per_round,
        },
        total_rounds=total_rounds,
    )
    # normalize_temporal_profile keeps the legacy four-round minimum.  A
    # ScenarioPlanner plan is already validated and must remain exact, including
    # the planner's supported three-round lower boundary.
    temporal_profile.update(
        {
            "total_rounds": total_rounds,
            "minutes_per_round": minutes_per_round,
            "total_simulation_hours": total_hours,
            "source": "scenario_planner",
            "temporal_plan_id": str(canonical.get("plan_id") or ""),
        }
    )
    time_plan = {
        "step_unit": step_unit,
        "step_size": step_value,
        "step_value": step_value,
        "total_rounds": total_rounds,
        "total_coverage_label": str(canonical.get("coverage_label_zh") or ""),
        "reference_time": str(reference_time or ""),
        "reasoning_summary": str(canonical.get("generation_reason_zh") or ""),
        "source": "scenario_planner",
        "minutes_per_round": minutes_per_round,
        "total_simulation_hours": total_hours,
        "preset": preset,
        "temporal_plan_id": str(canonical.get("plan_id") or ""),
    }
    time_config = {
        "total_rounds": total_rounds,
        "minutes_per_round": minutes_per_round,
        "total_simulation_hours": total_hours,
        "round_label": "推演轮次",
        "temporal_preset": preset,
        "source": "scenario_planner",
        "temporal_plan_id": str(canonical.get("plan_id") or ""),
    }
    return time_plan, temporal_profile, time_config


def build_mechanism_transport_profile(
    mechanism_graph: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a non-exclusive transport projection from mechanism graph edges.

    The old config selected one hazard template and one primary transport
    family.  A compound event can carry several simultaneous media, so the
    compatibility runtime now receives a neutral primary family plus every
    reviewed mechanism medium as a structured channel.  The mechanism graph,
    not this projection, remains authoritative.
    """

    graph = dict(mechanism_graph or {})
    media: List[str] = []
    channels: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        medium = str(edge.get("propagation_medium") or "").strip()
        if not medium or medium in seen:
            continue
        seen.add(medium)
        media.append(medium)
        normalized = medium.lower()
        if any(token in normalized for token in ("marine", "river", "water", "runoff", "coastal")):
            receptor_dim = "spread_pressure"
        elif any(token in normalized for token in ("ecosystem", "ecological")):
            receptor_dim = "ecosystem_integrity"
        else:
            receptor_dim = "exposure_score"
        channels.append(
            {
                "channel_id": medium,
                "label": str(edge.get("label_zh") or medium),
                "receptor_dim": receptor_dim,
                "gain": 1.0,
                "mechanism": str(edge.get("label_zh") or edge.get("primitive_key") or ""),
                "confidence": edge.get("confidence", 0.5),
                "epistemic_status": str(edge.get("epistemic_status") or "inferred"),
                "evidence_anchors": list(edge.get("evidence_refs") or []),
            }
        )

    profile = build_transport_profile(
        primary_family="generic",
        extra_propagation_channels=channels,
    )
    profile.update(
        {
            "primary_family": "generic",
            "secondary_channels": media,
            "propagation_media": media,
            "source": "event_mechanism_graph",
            "authoritative": False,
            "mechanism_graph_id": str(graph.get("graph_id") or ""),
            "说明": "运行时兼容投影；并列传播介质以 Step 2 事件机制图为准。",
        }
    )
    return profile

SEARCH_MODE_ALIASES = {
    "deep": "deep_search",
    "deepsearch": "deep_search",
    "deep_search": "deep_search",
    "deep-search": "deep_search",
    "fast": "fast",
}

SEARCH_MODE_PROFILES: Dict[str, Dict[str, Any]] = {
    "fast": {
        "cross_region_candidates_per_agent": 4,
        "max_new_dynamic_edges_per_agent": 1,
        "dynamic_edge_ttl_rounds": 2,
        "dynamic_edge_decay_per_round": 0.24,
        "allowed_cross_region_hops": 1,
        "max_relationship_hops": 2,
        "llm_relation_search_budget": 2,
        "llm_batch_size": 10,
        "edge_promotion_enabled": False,
        "link_follow_probability": 0.64,
    },
    "deep_search": {
        "cross_region_candidates_per_agent": 6,
        "max_new_dynamic_edges_per_agent": 2,
        "dynamic_edge_ttl_rounds": 3,
        "dynamic_edge_decay_per_round": 0.16,
        "allowed_cross_region_hops": 2,
        "max_relationship_hops": 3,
        "llm_relation_search_budget": 6,
        "llm_batch_size": 14,
        "edge_promotion_enabled": True,
        "link_follow_probability": 0.78,
    },
}


def normalize_search_mode(value: Optional[str]) -> str:
    normalized = str(value or "fast").strip().lower().replace("-", "_").replace(" ", "_")
    return SEARCH_MODE_ALIASES.get(normalized, "fast")


def build_search_mode_profile(search_mode: Optional[str], actor_count: int) -> Dict[str, Any]:
    canonical_mode = normalize_search_mode(search_mode)
    profile = dict(SEARCH_MODE_PROFILES.get(canonical_mode, SEARCH_MODE_PROFILES["fast"]))
    if canonical_mode == "deep_search":
        max_active = min(42, max(14, actor_count // 3 if actor_count else 14))
    else:
        max_active = min(24, max(10, actor_count // 5 if actor_count else 10))
    profile["search_mode"] = canonical_mode
    profile["max_active_agents_per_round"] = min(max_active, actor_count) if actor_count else 0
    return profile


def apply_search_profile_overrides(profile: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not overrides:
        return profile
    resolved = dict(profile)
    for key, value in dict(overrides or {}).items():
        if value is None:
            continue
        resolved[key] = value
    if actor_count := resolved.get("max_active_agents_per_round"):
        resolved["max_active_agents_per_round"] = max(0, int(actor_count))
    return resolved


@dataclass
class EnvSimulationConfig:
    simulation_id: str
    project_id: str
    graph_id: str
    engine_mode: str = ENVFISH_ENGINE_MODE
    simulation_architecture: str = LEGACY_SIMULATION_ARCHITECTURE
    scenario_mode: str = "baseline_mode"
    diffusion_template: str = "marine"
    hazard_template_id: str = "generic"
    hazard_template_mode: str = "auto"
    hazard_template_reasoning: str = ""
    hazard_template_recommendation: Dict[str, Any] = field(default_factory=dict)
    transport_profile: Dict[str, Any] = field(default_factory=dict)
    search_mode: str = "fast"
    simulation_requirement: str = ""
    document_digest: str = ""
    generation_reasoning: str = ""
    scenario_summary: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    llm_model: str = field(default_factory=lambda: Config.LLM_MODEL_NAME)
    reference_time: str = ""
    time_plan_mode: str = "auto"
    time_plan: Dict[str, Any] = field(default_factory=dict)
    temporal_plan: Dict[str, Any] = field(default_factory=dict)
    temporal_profile: Dict[str, Any] = field(default_factory=dict)
    time_config: Dict[str, Any] = field(default_factory=dict)
    round_policies: Dict[str, Any] = field(default_factory=dict)
    state_vector_schema: Dict[str, Any] = field(default_factory=lambda: dict(STATE_VECTOR_SCHEMA))
    scenario_state_schema: Dict[str, Any] = field(default_factory=dict)
    scenario_model: Dict[str, Any] = field(default_factory=dict)
    mechanism_graph: Dict[str, Any] = field(default_factory=dict)
    agent_blueprints: List[Dict[str, Any]] = field(default_factory=list)
    validated_relation_graph: Dict[str, Any] = field(default_factory=dict)
    simulation_audit: Dict[str, Any] = field(default_factory=dict)
    effort_snapshot: Dict[str, Any] = field(default_factory=dict)
    scenario_planning_input: Dict[str, Any] = field(default_factory=dict)
    agent_plan_source: str = ""
    agent_plan_contract_version: str = ""
    agent_plan: Dict[str, Any] = field(default_factory=dict)
    agent_placement_plan: Dict[str, Any] = field(default_factory=dict)
    resolution_plan: Dict[str, Any] = field(default_factory=dict)
    spatial_anchor_candidates: List[Dict[str, Any]] = field(default_factory=list)
    role_demands: List[Dict[str, Any]] = field(default_factory=list)
    policy_plan: List[Dict[str, Any]] = field(default_factory=list)
    policy_execution_plan: Dict[str, Any] = field(default_factory=dict)
    region_graph: List[Dict[str, Any]] = field(default_factory=list)
    subregion_graph: List[Dict[str, Any]] = field(default_factory=list)
    transport_edges: List[Dict[str, Any]] = field(default_factory=list)
    actor_profiles: List[Dict[str, Any]] = field(default_factory=list)
    agent_configs: List[Dict[str, Any]] = field(default_factory=list)
    agent_relationship_graph: List[Dict[str, Any]] = field(default_factory=list)
    region_agent_index: Dict[str, Any] = field(default_factory=dict)
    agent_archetypes: List[Dict[str, Any]] = field(default_factory=list)
    agent_generation_summary: Dict[str, Any] = field(default_factory=dict)
    interaction_policies: Dict[str, Any] = field(default_factory=dict)
    agent_action_catalog: List[Dict[str, Any]] = field(default_factory=list)
    runtime_limits: Dict[str, Any] = field(default_factory=dict)
    aggregation_rules: Dict[str, Any] = field(default_factory=dict)
    injected_variables: List[Dict[str, Any]] = field(default_factory=list)
    risk_definitions: List[Dict[str, Any]] = field(default_factory=list)
    risk_contract_version: int = 1
    risk_generation_audit: Dict[str, Any] = field(default_factory=dict)
    latest_risk_runtime_state: Dict[str, Any] = field(default_factory=dict)
    risk_objects: List[Dict[str, Any]] = field(default_factory=list)
    primary_risk_object_id: str = ""
    primary_active_risk_id: str = ""
    data_grounding_summary: Dict[str, Any] = field(default_factory=dict)
    diffusion_context: Dict[str, Any] = field(default_factory=dict)
    report_focus: List[str] = field(default_factory=list)
    uncertainty_policy: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "engine_mode": self.engine_mode,
            "simulation_architecture": self.simulation_architecture,
            "scenario_mode": self.scenario_mode,
            "diffusion_template": self.diffusion_template,
            "hazard_template_id": self.hazard_template_id,
            "hazard_template_mode": self.hazard_template_mode,
            "hazard_template_reasoning": self.hazard_template_reasoning,
            "hazard_template_recommendation": self.hazard_template_recommendation,
            "transport_profile": self.transport_profile,
            "search_mode": self.search_mode,
            "simulation_requirement": self.simulation_requirement,
            "document_digest": self.document_digest,
            "generation_reasoning": self.generation_reasoning,
            "scenario_summary": self.scenario_summary,
            "generated_at": self.generated_at,
            "llm_model": self.llm_model,
            "reference_time": self.reference_time,
            "time_plan_mode": self.time_plan_mode,
            "time_plan": self.time_plan,
            "temporal_plan": self.temporal_plan,
            "temporal_profile": self.temporal_profile,
            "time_config": self.time_config,
            "round_policies": self.round_policies,
            "state_vector_schema": self.state_vector_schema,
            "scenario_state_schema": self.scenario_state_schema,
            "scenario_model": self.scenario_model,
            "mechanism_graph": self.mechanism_graph,
            "agent_blueprints": self.agent_blueprints,
            "validated_relation_graph": self.validated_relation_graph,
            "simulation_audit": self.simulation_audit,
            "effort_snapshot": self.effort_snapshot,
            "scenario_planning_input": self.scenario_planning_input,
            "agent_plan_source": self.agent_plan_source,
            "agent_plan_contract_version": self.agent_plan_contract_version,
            "agent_plan": self.agent_plan,
            "agent_placement_plan": self.agent_placement_plan,
            "resolution_plan": self.resolution_plan,
            "spatial_anchor_candidates": self.spatial_anchor_candidates,
            "role_demands": self.role_demands,
            "policy_plan": self.policy_plan,
            "policy_execution_plan": self.policy_execution_plan,
            "region_graph": self.region_graph,
            "subregion_graph": self.subregion_graph,
            "transport_edges": self.transport_edges,
            "actor_profiles": self.actor_profiles,
            "agent_configs": self.agent_configs,
            "agent_relationship_graph": self.agent_relationship_graph,
            "region_agent_index": self.region_agent_index,
            "agent_archetypes": self.agent_archetypes,
            "agent_generation_summary": self.agent_generation_summary,
            "interaction_policies": self.interaction_policies,
            "agent_action_catalog": self.agent_action_catalog,
            "runtime_limits": self.runtime_limits,
            "aggregation_rules": self.aggregation_rules,
            "injected_variables": self.injected_variables,
            "risk_definitions": self.risk_definitions,
            "risk_contract_version": self.risk_contract_version,
            "risk_generation_audit": self.risk_generation_audit,
            "latest_risk_runtime_state": self.latest_risk_runtime_state,
            "risk_objects": self.risk_objects,
            "primary_risk_object_id": self.primary_risk_object_id,
            "primary_active_risk_id": self.primary_active_risk_id,
            "data_grounding_summary": self.data_grounding_summary,
            "diffusion_context": self.diffusion_context,
            "report_focus": self.report_focus,
            "uncertainty_policy": self.uncertainty_policy,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class EnvSimulationConfigGenerator:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
        if self.llm_client is None and Config.LLM_API_KEY:
            try:
                self.llm_client = LLMClient()
            except Exception as exc:
                logger.warning(f"Env config LLM init failed, using fallback config: {exc}")

    def generate_config(
        self,
        simulation_id: str,
        project_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        transport_edges: Optional[List[TransportEdge]],
        profiles: List[EnvAgentProfile],
        agent_relationships: List[Dict[str, Any]],
        region_agent_index: Optional[Dict[str, Any]] = None,
        agent_generation_summary: Optional[Dict[str, Any]] = None,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        hazard_template_id: str = "",
        hazard_template_mode: str = "auto",
        search_mode: str = "fast",
        temporal_profile: Optional[Dict[str, Any]] = None,
        time_plan_mode: str = "auto",
        time_plan: Optional[Dict[str, Any]] = None,
        reference_time: str = "",
        diffusion_context: Optional[Dict[str, Any]] = None,
        injected_variables: Optional[List[InjectedVariable]] = None,
        search_profile_overrides: Optional[Dict[str, Any]] = None,
        data_grounding_summary: Optional[Dict[str, Any]] = None,
        risk_definitions: Optional[List[RiskDefinition]] = None,
        risk_contract_version: int = 1,
        risk_generation_audit: Optional[Dict[str, Any]] = None,
        latest_risk_runtime_state: Optional[Dict[str, Any]] = None,
        risk_objects: Optional[List[RiskObject]] = None,
        primary_risk_object_id: str = "",
        primary_active_risk_id: str = "",
        simulation_architecture: str = LEGACY_SIMULATION_ARCHITECTURE,
        scenario_model: Optional[Dict[str, Any]] = None,
        mechanism_graph: Optional[Dict[str, Any]] = None,
        agent_blueprints: Optional[List[Dict[str, Any]]] = None,
        validated_relation_graph: Optional[Dict[str, Any]] = None,
        simulation_audit: Optional[Dict[str, Any]] = None,
        scenario_state_schema: Optional[Dict[str, Any]] = None,
        scenario_planning_input: Optional[Dict[str, Any]] = None,
    ) -> EnvSimulationConfig:
        search_mode = normalize_search_mode(search_mode)
        simulation_architecture = normalize_simulation_architecture(simulation_architecture)
        canonical_diffusion_template = normalize_transport_family(diffusion_template)
        planning = dict(scenario_planning_input or {})
        canonical_temporal_plan = dict(planning.get("temporal_plan") or {})
        authoritative_graph = dict(mechanism_graph or planning.get("event_mechanism_graph") or {})
        has_scenario_plan = bool(planning)
        display_projection: Dict[str, Any] = {}
        visible_simulation_requirement = simulation_requirement
        localized_scenario_model = dict(scenario_model or {})
        if has_scenario_plan:
            # ScenarioPlanner has already completed the planning decision.  Do
            # not ask the legacy config LLM/fallback to choose another hazard,
            # transport family, or cadence afterwards.
            display_projection = build_scenario_planner_display_projection(
                planning,
                scenario_model=scenario_model,
            )
            localized_scenario_model = dict(display_projection["scenario_model"])
            # The legacy Agent adapter appends machine capability keys to the
            # generation prompt.  They are useful to the old generator but must
            # not be persisted as the user-facing scenario description.
            visible_simulation_requirement = str(simulation_requirement or "").split(
                "Step 2 场景规划补充：",
                1,
            )[0].strip() or str(display_projection["scenario_summary"])
            plan = {
                "scenario_summary": display_projection["scenario_summary"],
                "generation_reasoning": display_projection["generation_reasoning"],
                "round_label": display_projection["round_label"],
                "report_focus": display_projection["report_focus"],
            }
            hazard_template_id = normalize_hazard_template_id(hazard_template_id)
            hazard_template_mode = "compatibility_projection"
            hazard_template_reasoning = "兼容字段，仅供旧运行时识别；不参与复合事件机制与传播路径决策。"
        else:
            llm_plan = self._generate_plan_with_llm(
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                regions=regions,
                subregions=subregions,
                profiles=profiles,
                scenario_mode=scenario_mode,
                diffusion_template=canonical_diffusion_template,
                reference_time=reference_time,
                injected_variables=injected_variables or [],
            )
            fallback = self._fallback_plan(
                scenario_mode=scenario_mode,
                region_count=len(regions),
                actor_count=len(profiles),
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                diffusion_template=canonical_diffusion_template,
                injected_variables=injected_variables or [],
            )
            plan = {**fallback, **(llm_plan or {})}
            hazard_template_id, hazard_template_reasoning = self._resolve_hazard_template(
                plan=plan,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                injected_variables=injected_variables or [],
                fallback_family=canonical_diffusion_template,
                override_hazard_template_id=hazard_template_id,
                hazard_template_mode=hazard_template_mode,
            )
        template_definition = get_hazard_template_definition(hazard_template_id)
        if has_scenario_plan:
            transport_profile = build_mechanism_transport_profile(authoritative_graph)
            time_plan, normalized_temporal, authoritative_time_config = (
                build_scenario_temporal_runtime_projection(
                    canonical_temporal_plan,
                    reference_time=reference_time,
                )
            )
        else:
            primary_family = self._resolve_primary_family(
                hazard_template_id=hazard_template_id,
                plan=plan,
                fallback_family=canonical_diffusion_template,
            )
            # M6: surface a structured propagation-channel graph so the runtime can
            # actually modulate diffusion by channel (previously secondary_channels /
            # impact_chain were dead strings). Caller-supplied channels in
            # diffusion_context or the LLM plan are merged in additively.
            plan_transport_profile = plan.get("transport_profile") or {}
            extra_propagation_channels = (
                (diffusion_context or {}).get("propagation_channels")
                or plan_transport_profile.get("propagation_channels")
                or []
            )
            transport_profile = build_transport_profile(
                primary_family=primary_family,
                secondary_channels=template_definition.get("secondary_channels"),
                context_provider=plan_transport_profile.get("context_provider"),
                impact_chain=template_definition.get("impact_chain"),
                extra_propagation_channels=extra_propagation_channels,
            )
            time_plan = self._resolve_time_plan(
                plan=plan,
                hazard_template_id=hazard_template_id,
                scenario_mode=scenario_mode,
                temporal_profile=temporal_profile,
                override_time_plan=time_plan,
                time_plan_mode=time_plan_mode,
                reference_time=reference_time,
                injected_variables=injected_variables or [],
            )
            normalized_temporal = normalize_temporal_profile(
                {
                    "preset": time_plan.get("preset"),
                    "total_rounds": time_plan.get("total_rounds"),
                    "minutes_per_round": time_plan.get("minutes_per_round"),
                },
                total_rounds=max(4, int(time_plan.get("total_rounds") or 12)),
            )
            authoritative_time_config = {}
        total_rounds = normalized_temporal["total_rounds"]
        minutes_per_round = normalized_temporal["minutes_per_round"]
        total_hours = normalized_temporal["total_simulation_hours"]
        search_profile = apply_search_profile_overrides(
            build_search_mode_profile(search_mode, len(profiles)),
            search_profile_overrides,
        )

        config = EnvSimulationConfig(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            simulation_architecture=simulation_architecture,
            scenario_mode=scenario_mode,
            diffusion_template=transport_profile["primary_family"],
            hazard_template_id=hazard_template_id,
            hazard_template_mode=hazard_template_mode or "auto",
            hazard_template_reasoning=hazard_template_reasoning,
            hazard_template_recommendation=(
                {
                    "hazard_template_id": hazard_template_id,
                    "label": template_definition.get("label"),
                    "authoritative": False,
                    "projection_only": True,
                    "mechanism_graph_id": str(authoritative_graph.get("graph_id") or ""),
                    "propagation_media": list(transport_profile.get("propagation_media") or []),
                    "reasoning_summary": hazard_template_reasoning,
                }
                if has_scenario_plan
                else {
                    "hazard_template_id": hazard_template_id,
                    "label": template_definition.get("label"),
                    "description": template_definition.get("description"),
                    "impact_chain": template_definition.get("impact_chain"),
                    "primary_family": transport_profile["primary_family"],
                    "secondary_channels": transport_profile.get("secondary_channels", []),
                    "propagation_channels": transport_profile.get("propagation_channels", []),
                    "reasoning_summary": hazard_template_reasoning,
                }
            ),
            transport_profile=transport_profile,
            search_mode=search_mode,
            simulation_requirement=visible_simulation_requirement,
            document_digest=document_text[:2000],
            generation_reasoning=str(
                plan.get("generation_reasoning")
                or f"系统采用{template_definition.get('label')}配置 {len(regions)} 个区域和 {len(profiles)} 个代理体。"
            ),
            scenario_summary=str(
                plan.get("scenario_summary")
                or f"区域级生态社会推演采用{template_definition.get('label')}配置。"
            ),
            reference_time=str(reference_time or ""),
            time_plan_mode="scenario_planner" if has_scenario_plan else (time_plan_mode or "auto"),
            time_plan=time_plan,
            temporal_plan=canonical_temporal_plan,
            temporal_profile=normalized_temporal,
            time_config=(
                authoritative_time_config
                if has_scenario_plan
                else {
                    "total_rounds": total_rounds,
                    "minutes_per_round": minutes_per_round,
                    "total_simulation_hours": total_hours,
                    "round_label": plan.get("round_label", "推演轮次"),
                    "temporal_preset": normalized_temporal["preset"],
                }
            ),
            round_policies={
                "diffusion_decay": transport_profile["default_decay"],
                "default_lag_rounds": transport_profile["default_lag_rounds"],
                "default_persistence": transport_profile["default_persistence"],
                "max_neighbor_spread": transport_profile["max_neighbor_spread"],
                "score_update_limit": 18,
            },
            scenario_state_schema=dict(scenario_state_schema or {}),
            scenario_model=localized_scenario_model,
            mechanism_graph=dict(mechanism_graph or {}),
            agent_blueprints=list(agent_blueprints or []),
            validated_relation_graph=dict(validated_relation_graph or {}),
            simulation_audit=dict(simulation_audit or {}),
            scenario_planning_input=planning,
            region_graph=[region.to_dict() for region in regions],
            subregion_graph=[subregion.to_dict() for subregion in subregions],
            transport_edges=[item.to_dict() if hasattr(item, "to_dict") else item for item in (transport_edges or [])],
            actor_profiles=[profile.to_dict() for profile in profiles],
            agent_configs=[profile.to_agent_config() for profile in profiles],
            agent_relationship_graph=[
                item.to_dict() if hasattr(item, "to_dict") else item for item in (agent_relationships or [])
            ],
            region_agent_index=region_agent_index or {},
            agent_archetypes=self._build_agent_archetypes(profiles),
            agent_generation_summary=agent_generation_summary or {},
            interaction_policies={
                "activation_mode": "stress_weighted_round_robin",
                "max_actions_per_round": search_profile["max_active_agents_per_round"],
                "link_follow_probability": search_profile["link_follow_probability"],
                "ecology_feedback_enabled": True,
                "cross_region_candidates_per_agent": search_profile["cross_region_candidates_per_agent"],
                "max_new_dynamic_edges_per_agent": search_profile["max_new_dynamic_edges_per_agent"],
                "dynamic_edge_ttl_rounds": search_profile["dynamic_edge_ttl_rounds"],
                "dynamic_edge_decay_per_round": search_profile["dynamic_edge_decay_per_round"],
                "allowed_cross_region_hops": search_profile["allowed_cross_region_hops"],
                "llm_relation_search_budget": search_profile["llm_relation_search_budget"],
                "edge_promotion_enabled": search_profile["edge_promotion_enabled"],
                "candidate_route_sources": [
                    "neighbor_region",
                    "shared_risk_object",
                    "governance_hierarchy",
                    "media_reach",
                ],
            },
            agent_action_catalog=self._build_action_catalog(),
            runtime_limits={
                "max_agents": len(profiles),
                "max_active_agents_per_round": search_profile["max_active_agents_per_round"],
                "max_relationship_hops": search_profile["max_relationship_hops"],
                "llm_batch_size": search_profile["llm_batch_size"],
                "cross_region_candidates_per_agent": search_profile["cross_region_candidates_per_agent"],
                "max_new_dynamic_edges_per_agent": search_profile["max_new_dynamic_edges_per_agent"],
            },
            aggregation_rules={
                "agent_to_region": {
                    "panic_delta": "public_trust,panic_level",
                    "economic_delta": "economic_stress,livelihood_stability",
                    "ecology_delta": "ecosystem_integrity,vulnerability_score",
                },
                "subregion_rollup": "mean_then_weighted_by_population_capacity",
            },
            injected_variables=[item.to_dict() for item in (injected_variables or [])],
            risk_definitions=[item.to_dict() if hasattr(item, "to_dict") else item for item in (risk_definitions or [])],
            risk_contract_version=max(1, int(risk_contract_version or 1)),
            risk_generation_audit=dict(risk_generation_audit or {}),
            latest_risk_runtime_state=dict(latest_risk_runtime_state or {}),
            risk_objects=[item.to_dict() if hasattr(item, "to_dict") else item for item in (risk_objects or [])],
            primary_risk_object_id=primary_risk_object_id,
            primary_active_risk_id=primary_active_risk_id or primary_risk_object_id,
            data_grounding_summary=data_grounding_summary or {},
            diffusion_context=diffusion_context or {},
            report_focus=plan.get(
                "report_focus",
                [
                    "风险对象摘要",
                    "区域传播预测",
                    "人与自然反馈链",
                    "脆弱区域与代理体",
                    "干预措施对比",
                    "不确定性与模型边界",
                ],
            ),
            uncertainty_policy={
                "display_band": True,
                "per_round_confidence": True,
                "explanation": (
                    display_projection.get("uncertainty_explanation")
                    or "置信度反映受约束模型的一致性，不代表物理确定性。"
                ),
            },
        )
        return config

    def _generate_plan_with_llm(
        self,
        simulation_requirement: str,
        document_text: str,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        profiles: List[EnvAgentProfile],
        scenario_mode: str,
        diffusion_template: str,
        reference_time: str,
        injected_variables: List[InjectedVariable],
    ) -> Optional[Dict[str, Any]]:
        if not self.llm_client:
            return None

        prompt = {
            "task": "规划区域级生态社会场景推演配置。",
            "scenario_mode": scenario_mode,
            "diffusion_template": diffusion_template,
            "simulation_requirement": simulation_requirement[:1500],
            "document_excerpt": document_text[:5000],
            "region_graph": [region.to_dict() for region in regions[:6]],
            "subregion_graph": [region.to_dict() for region in subregions[:8]],
            "actor_samples": [profile.to_agent_config() for profile in profiles[:12]],
            "reference_time": reference_time,
            "hazard_templates": {
                key: {
                    "label": value.get("label"),
                    "description": value.get("description"),
                    "primary_family": value.get("primary_family"),
                    "secondary_channels": value.get("secondary_channels"),
                }
                for key, value in HAZARD_TEMPLATE_CATALOG.items()
            },
            "injected_variables": [item.to_dict() if hasattr(item, "to_dict") else item for item in injected_variables[:8]],
            "schema": {
                "scenario_summary": "简体中文文本",
                "generation_reasoning": "简体中文文本",
                "hazard_template_id": "string",
                "hazard_template_reasoning": "简体中文文本",
                "transport_profile": {
                    "primary_family": "string",
                    "context_provider": "string",
                },
                "time_plan": {
                    "step_unit": "day",
                    "step_size": 1,
                    "total_rounds": 12,
                    "reasoning_summary": "string",
                },
                "round_label": "简体中文文本",
                "report_focus": ["简体中文条目 1", "简体中文条目 2"],
            },
            "rules": [
                "Choose exactly one hazard_template_id from the provided catalog.",
                "Use the hazard template to recommend one primary transport family.",
                "Pick a time plan that matches fast, medium, or slow ecological change.",
                "Favor explainability over realism.",
                "所有面向用户展示的摘要、原因、轮次标签和报告重点必须使用简体中文；机器标识符和枚举值可保留英文。",
                "Return valid JSON only.",
            ],
        }
        try:
            return self.llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "你为区域场景推演生成紧凑 JSON；所有展示字段必须使用简体中文。",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.25,
                max_tokens=1300,
            )
        except Exception as exc:
            logger.warning(f"Env config LLM generation failed, using fallback: {exc}")
            return None

    def _fallback_plan(
        self,
        scenario_mode: str,
        region_count: int,
        actor_count: int,
        simulation_requirement: str,
        document_text: str,
        diffusion_template: str,
        injected_variables: List[InjectedVariable],
    ) -> Dict[str, Any]:
        hazard_template_id, hazard_reasoning = self._heuristic_hazard_template(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            injected_variables=injected_variables,
            fallback_family=diffusion_template,
        )
        time_plan = self._heuristic_time_plan(hazard_template_id, scenario_mode, injected_variables)
        return {
            "scenario_summary": (
                f"半定量场景包含 {region_count} 个区域和 {actor_count} 个生态社会代理体。"
            ),
            "generation_reasoning": (
                "系统根据场景描述、变量节奏和灾害传播速度，确定兼容模板、传播方式与时间计划。"
            ),
            "hazard_template_id": hazard_template_id,
            "hazard_template_reasoning": hazard_reasoning,
            "transport_profile": {
                "primary_family": get_hazard_template_definition(hazard_template_id).get("primary_family"),
                "context_provider": "auto",
            },
            "time_plan": time_plan,
            "round_label": "推演轮次",
            "report_focus": [
                "区域传播预测",
                "人与自然反馈链",
                "脆弱性排序",
                "干预效果差异",
                "不确定性范围",
            ],
        }

    def _resolve_hazard_template(
        self,
        *,
        plan: Dict[str, Any],
        simulation_requirement: str,
        document_text: str,
        injected_variables: List[InjectedVariable],
        fallback_family: str,
        override_hazard_template_id: str = "",
        hazard_template_mode: str = "auto",
    ) -> tuple[str, str]:
        if str(hazard_template_mode or "auto") == "manual" and str(override_hazard_template_id or "").strip():
            planned_id = normalize_hazard_template_id(override_hazard_template_id)
            return planned_id, f"用户手动选择危机模板：{get_hazard_template_definition(planned_id).get('label')}。"
        planned_id = normalize_hazard_template_id(plan.get("hazard_template_id"))
        if planned_id != "generic" or str(plan.get("hazard_template_id") or "").strip():
            reasoning = str(plan.get("hazard_template_reasoning") or plan.get("generation_reasoning") or "")
            return planned_id, reasoning or get_hazard_template_definition(planned_id).get("description", "")
        return self._heuristic_hazard_template(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            injected_variables=injected_variables,
            fallback_family=fallback_family,
        )

    def _resolve_primary_family(
        self,
        *,
        hazard_template_id: str,
        plan: Dict[str, Any],
        fallback_family: str,
    ) -> str:
        planned_family = normalize_transport_family((plan.get("transport_profile") or {}).get("primary_family"))
        if planned_family != "generic" or str((plan.get("transport_profile") or {}).get("primary_family") or "").strip():
            return planned_family
        definition = get_hazard_template_definition(hazard_template_id)
        primary_family = normalize_transport_family(definition.get("primary_family"))
        if definition.get("allow_auto_primary_family"):
            fallback_normalized = normalize_transport_family(fallback_family)
            if fallback_normalized != "generic":
                return fallback_normalized
        return primary_family

    def _resolve_time_plan(
        self,
        *,
        plan: Dict[str, Any],
        hazard_template_id: str,
        scenario_mode: str,
        temporal_profile: Optional[Dict[str, Any]],
        override_time_plan: Optional[Dict[str, Any]],
        time_plan_mode: str,
        reference_time: str,
        injected_variables: List[InjectedVariable],
    ) -> Dict[str, Any]:
        if str(time_plan_mode or "auto") == "manual" and isinstance(override_time_plan, dict) and override_time_plan:
            return normalize_time_plan(
                override_time_plan,
                total_rounds=(temporal_profile or {}).get("total_rounds"),
                minutes_per_round=(temporal_profile or {}).get("minutes_per_round"),
                preset=(temporal_profile or {}).get("preset"),
                reference_time=reference_time,
                reasoning_summary=str(override_time_plan.get("reasoning_summary") or "用户手动设置时间计划。"),
                source="manual",
            )
        raw_plan = plan.get("time_plan")
        if isinstance(raw_plan, dict) and raw_plan:
            return normalize_time_plan(
                raw_plan,
                total_rounds=(temporal_profile or {}).get("total_rounds"),
                minutes_per_round=(temporal_profile or {}).get("minutes_per_round"),
                preset=(temporal_profile or {}).get("preset"),
                reference_time=reference_time,
                reasoning_summary=str(raw_plan.get("reasoning_summary") or plan.get("generation_reasoning") or ""),
                source="auto",
            )
        heuristic = self._heuristic_time_plan(
            hazard_template_id=hazard_template_id,
            scenario_mode=scenario_mode,
            injected_variables=injected_variables,
            temporal_profile=temporal_profile,
        )
        return normalize_time_plan(
            heuristic,
            total_rounds=(temporal_profile or {}).get("total_rounds"),
            minutes_per_round=(temporal_profile or {}).get("minutes_per_round"),
            preset=(temporal_profile or {}).get("preset"),
            reference_time=reference_time,
            reasoning_summary=str(heuristic.get("reasoning_summary") or plan.get("generation_reasoning") or ""),
            source="auto",
        )

    def _heuristic_hazard_template(
        self,
        *,
        simulation_requirement: str,
        document_text: str,
        injected_variables: List[InjectedVariable],
        fallback_family: str,
    ) -> tuple[str, str]:
        corpus = " ".join(
            [
                simulation_requirement or "",
                document_text[:5000] or "",
                " ".join(f"{item.name} {item.description}" for item in injected_variables),
            ]
        ).lower()
        checks = [
            ("coastal_radioactive_release", ("核废水", "海洋放射", "福岛", "treated water")),
            ("radioactive_fallout", ("核爆", "核弹", "辐射沉降", "fallout")),
            ("industrial_toxic_release", ("化工", "危险品", "有毒", "chemical spill", "toxic release")),
            ("inland_water_contamination", ("河流污染", "湖库", "尾矿", "污水", "流域污染")),
            ("marine_pollution_bloom", ("赤潮", "富营养化", "近海污染", "藻华", "bloom")),
            ("wildfire_smoke_ash", ("山火", "野火", "烟尘", "灰烬", "wildfire")),
            ("volcanic_eruption", ("火山", "火山灰", "火山泥流", "volcanic", "lahar")),
            ("earthquake_secondary_cascade", ("地震", "滑坡", "液化", "earthquake")),
            ("tsunami_inundation", ("海啸", "盐水入侵", "tsunami")),
            ("flood_storm_surge", ("洪水", "风暴潮", "内涝", "flood", "storm surge")),
            ("drought_ecosystem_stress", ("干旱", "热浪", "缺水", "drought", "heatwave")),
            ("invasive_species_spread", ("外来物种", "入侵物种", "invasive", "扩散走廊")),
            ("pest_disease_ecology", ("虫害", "疫病", "病害", "pest", "disease")),
            ("asteroid_impact_cascade", ("小行星", "陨石", "撞击", "asteroid", "impact")),
        ]
        for template_id, tokens in checks:
            if any(token in corpus for token in tokens):
                return template_id, get_hazard_template_definition(template_id).get("description", "")
        family = normalize_transport_family(fallback_family)
        template_id = default_hazard_template_for_family(family)
        return template_id, f"根据当前传播介质偏好，回退到 {get_hazard_template_definition(template_id).get('label')}。"

    def _heuristic_time_plan(
        self,
        hazard_template_id: str,
        scenario_mode: str,
        injected_variables: List[InjectedVariable],
        temporal_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        fast_templates = {
            "radioactive_fallout",
            "tsunami_inundation",
            "earthquake_secondary_cascade",
            "flood_storm_surge",
            "industrial_toxic_release",
            "asteroid_impact_cascade",
        }
        medium_templates = {
            "volcanic_eruption",
            "wildfire_smoke_ash",
            "inland_water_contamination",
            "marine_pollution_bloom",
        }
        slow_templates = {
            "coastal_radioactive_release",
            "drought_ecosystem_stress",
            "invasive_species_spread",
            "pest_disease_ecology",
        }
        preferred = {
            "fast": ("hour", 6, 16 if scenario_mode == "crisis_mode" else 12, "快过程危机优先使用小时级步长观察级联响应。"),
            "medium": ("day", 1, 14 if scenario_mode == "crisis_mode" else 10, "中过程危机使用天级步长平衡扩散和恢复过程。"),
            "slow": ("week", 1, 16 if injected_variables else 12, "慢过程危机使用周级步长覆盖建立、累积和长期反馈。"),
        }
        speed = "medium"
        if hazard_template_id in fast_templates:
            speed = "fast"
        elif hazard_template_id in slow_templates:
            speed = "slow"
        elif hazard_template_id in medium_templates:
            speed = "medium"
        step_unit, step_size, total_rounds, reasoning = preferred[speed]
        if temporal_profile and temporal_profile.get("minutes_per_round"):
            return normalize_time_plan(
                {
                    "total_rounds": temporal_profile.get("total_rounds"),
                    "minutes_per_round": temporal_profile.get("minutes_per_round"),
                    "reasoning_summary": reasoning,
                },
                total_rounds=temporal_profile.get("total_rounds"),
                minutes_per_round=temporal_profile.get("minutes_per_round"),
                preset=temporal_profile.get("preset"),
                source="auto",
            )
        return {
            "step_unit": step_unit,
            "step_size": step_size,
            "total_rounds": total_rounds,
            "reasoning_summary": reasoning,
        }

    def _build_agent_archetypes(self, profiles: List[EnvAgentProfile]) -> List[Dict[str, Any]]:
        archetypes: Dict[str, Dict[str, Any]] = {}
        for profile in profiles:
            key = profile.archetype_key or f"{profile.agent_type}:{profile.agent_subtype or profile.role_type}"
            entry = archetypes.setdefault(
                key,
                {
                    "archetype_key": key,
                    "agent_type": profile.agent_type,
                    "agent_subtype": profile.agent_subtype,
                    "sample_names": [],
                    "count": 0,
                    "common_actions": set(),
                    "common_motivations": set(),
                },
            )
            entry["count"] += 1
            if len(entry["sample_names"]) < 3:
                entry["sample_names"].append(profile.name)
            entry["common_actions"].update(profile.action_space[:4])
            entry["common_motivations"].update(profile.motivation_stack[:4])
        return [
            {
                **value,
                "common_actions": sorted(value["common_actions"]),
                "common_motivations": sorted(value["common_motivations"]),
            }
            for value in archetypes.values()
        ]

    def _build_action_catalog(self) -> List[Dict[str, Any]]:
        return [
            {"action_type": "monitor", "channel": "information", "effect_targets": ["trust", "ecology"]},
            {"action_type": "volunteer_cleanup", "channel": "environment", "effect_targets": ["ecology", "trust"]},
            {"action_type": "panic_buy", "channel": "market", "effect_targets": ["panic", "economy"]},
            {"action_type": "market_shift", "channel": "market", "effect_targets": ["economy", "livelihood"]},
            {"action_type": "enforce_restriction", "channel": "governance", "effect_targets": ["exposure", "economy"]},
            {"action_type": "deploy_remediation", "channel": "environment", "effect_targets": ["ecology", "service"]},
            {"action_type": "continue_output", "channel": "production", "effect_targets": ["economy", "ecology"]},
            {"action_type": "stress_signal", "channel": "ecology", "effect_targets": ["ecology", "panic"]},
        ]
