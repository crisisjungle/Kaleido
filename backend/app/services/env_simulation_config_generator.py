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
    DEFAULT_TEMPLATE_RULES,
    ENVFISH_ENGINE_MODE,
    EnvAgentProfile,
    InjectedVariable,
    RegionNode,
    RiskDefinition,
    RiskObject,
    STATE_VECTOR_SCHEMA,
    TransportEdge,
    normalize_temporal_profile,
)

logger = get_logger("envfish.envfish_config")

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


@dataclass
class EnvSimulationConfig:
    simulation_id: str
    project_id: str
    graph_id: str
    engine_mode: str = ENVFISH_ENGINE_MODE
    scenario_mode: str = "baseline_mode"
    diffusion_template: str = "marine"
    search_mode: str = "fast"
    simulation_requirement: str = ""
    document_digest: str = ""
    generation_reasoning: str = ""
    scenario_summary: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    llm_model: str = field(default_factory=lambda: Config.LLM_MODEL_NAME)
    reference_time: str = ""
    temporal_profile: Dict[str, Any] = field(default_factory=dict)
    time_config: Dict[str, Any] = field(default_factory=dict)
    round_policies: Dict[str, Any] = field(default_factory=dict)
    state_vector_schema: Dict[str, Any] = field(default_factory=lambda: dict(STATE_VECTOR_SCHEMA))
    region_graph: List[Dict[str, Any]] = field(default_factory=list)
    subregion_graph: List[Dict[str, Any]] = field(default_factory=list)
    transport_edges: List[Dict[str, Any]] = field(default_factory=list)
    actor_profiles: List[Dict[str, Any]] = field(default_factory=list)
    agent_configs: List[Dict[str, Any]] = field(default_factory=list)
    agent_relationship_graph: List[Dict[str, Any]] = field(default_factory=list)
    region_agent_index: Dict[str, Any] = field(default_factory=dict)
    agent_archetypes: List[Dict[str, Any]] = field(default_factory=list)
    interaction_policies: Dict[str, Any] = field(default_factory=dict)
    agent_action_catalog: List[Dict[str, Any]] = field(default_factory=list)
    runtime_limits: Dict[str, Any] = field(default_factory=dict)
    aggregation_rules: Dict[str, Any] = field(default_factory=dict)
    injected_variables: List[Dict[str, Any]] = field(default_factory=list)
    risk_definitions: List[Dict[str, Any]] = field(default_factory=list)
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
            "scenario_mode": self.scenario_mode,
            "diffusion_template": self.diffusion_template,
            "search_mode": self.search_mode,
            "simulation_requirement": self.simulation_requirement,
            "document_digest": self.document_digest,
            "generation_reasoning": self.generation_reasoning,
            "scenario_summary": self.scenario_summary,
            "generated_at": self.generated_at,
            "llm_model": self.llm_model,
            "reference_time": self.reference_time,
            "temporal_profile": self.temporal_profile,
            "time_config": self.time_config,
            "round_policies": self.round_policies,
            "state_vector_schema": self.state_vector_schema,
            "region_graph": self.region_graph,
            "subregion_graph": self.subregion_graph,
            "transport_edges": self.transport_edges,
            "actor_profiles": self.actor_profiles,
            "agent_configs": self.agent_configs,
            "agent_relationship_graph": self.agent_relationship_graph,
            "region_agent_index": self.region_agent_index,
            "agent_archetypes": self.agent_archetypes,
            "interaction_policies": self.interaction_policies,
            "agent_action_catalog": self.agent_action_catalog,
            "runtime_limits": self.runtime_limits,
            "aggregation_rules": self.aggregation_rules,
            "injected_variables": self.injected_variables,
            "risk_definitions": self.risk_definitions,
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
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        search_mode: str = "fast",
        temporal_profile: Optional[Dict[str, Any]] = None,
        reference_time: str = "",
        diffusion_context: Optional[Dict[str, Any]] = None,
        injected_variables: Optional[List[InjectedVariable]] = None,
        data_grounding_summary: Optional[Dict[str, Any]] = None,
        risk_definitions: Optional[List[RiskDefinition]] = None,
        latest_risk_runtime_state: Optional[Dict[str, Any]] = None,
        risk_objects: Optional[List[RiskObject]] = None,
        primary_risk_object_id: str = "",
        primary_active_risk_id: str = "",
    ) -> EnvSimulationConfig:
        search_mode = normalize_search_mode(search_mode)
        llm_plan = self._generate_plan_with_llm(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            regions=regions,
            subregions=subregions,
            profiles=profiles,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
        )
        fallback = self._fallback_plan(
            scenario_mode=scenario_mode,
            region_count=len(regions),
            actor_count=len(profiles),
        )
        plan = {**fallback, **(llm_plan or {})}

        template_rules = DEFAULT_TEMPLATE_RULES.get(diffusion_template, DEFAULT_TEMPLATE_RULES["generic"])
        search_profile = build_search_mode_profile(search_mode, len(profiles))
        normalized_temporal = normalize_temporal_profile(
            temporal_profile,
            total_rounds=max(4, int((temporal_profile or {}).get("total_rounds") or plan.get("total_rounds", fallback["total_rounds"]))),
        )
        total_rounds = normalized_temporal["total_rounds"]
        minutes_per_round = normalized_temporal["minutes_per_round"]
        total_hours = normalized_temporal["total_simulation_hours"]

        config = EnvSimulationConfig(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
            search_mode=search_mode,
            simulation_requirement=simulation_requirement,
            document_digest=document_text[:2000],
            generation_reasoning=str(
                plan.get("generation_reasoning")
                or f"Used {diffusion_template} template with {len(regions)} regions and {len(profiles)} actors."
            ),
            scenario_summary=str(
                plan.get("scenario_summary")
                or f"Region-level eco-social stress test in {scenario_mode} using {diffusion_template} diffusion."
            ),
            reference_time=str(reference_time or ""),
            temporal_profile=normalized_temporal,
            time_config={
                "total_rounds": total_rounds,
                "minutes_per_round": minutes_per_round,
                "total_simulation_hours": total_hours,
                "round_label": plan.get("round_label", "simulation round"),
                "temporal_preset": normalized_temporal["preset"],
            },
            round_policies={
                "diffusion_decay": template_rules["default_decay"],
                "default_lag_rounds": template_rules["default_lag_rounds"],
                "default_persistence": template_rules["default_persistence"],
                "max_neighbor_spread": template_rules["max_neighbor_spread"],
                "score_update_limit": 18,
            },
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
            latest_risk_runtime_state=dict(latest_risk_runtime_state or {}),
            risk_objects=[item.to_dict() if hasattr(item, "to_dict") else item for item in (risk_objects or [])],
            primary_risk_object_id=primary_risk_object_id,
            primary_active_risk_id=primary_active_risk_id or primary_risk_object_id,
            data_grounding_summary=data_grounding_summary or {},
            diffusion_context=diffusion_context or {},
            report_focus=plan.get(
                "report_focus",
                [
                    "risk object summary",
                    "regional spread forecast",
                    "human-nature feedback loops",
                    "vulnerable regions and actors",
                    "intervention comparison",
                    "uncertainty and model limits",
                ],
            ),
            uncertainty_policy={
                "display_band": True,
                "per_round_confidence": True,
                "explanation": "Confidence reflects constrained LLM consistency, not physical certainty.",
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
    ) -> Optional[Dict[str, Any]]:
        if not self.llm_client:
            return None

        prompt = {
            "task": "Plan an EnvFish region-level scenario simulation configuration.",
            "scenario_mode": scenario_mode,
            "diffusion_template": diffusion_template,
            "simulation_requirement": simulation_requirement[:1500],
            "document_excerpt": document_text[:5000],
            "region_graph": [region.to_dict() for region in regions[:6]],
            "subregion_graph": [region.to_dict() for region in subregions[:8]],
            "actor_samples": [profile.to_agent_config() for profile in profiles[:12]],
            "schema": {
                "scenario_summary": "string",
                "generation_reasoning": "string",
                "total_rounds": 8,
                "minutes_per_round": 30,
                "round_label": "string",
                "report_focus": ["item 1", "item 2"],
            },
            "rules": [
                "Keep total_rounds between 4 and 16.",
                "Keep minutes_per_round between 10 and 180.",
                "Favor explainability over realism.",
                "Return valid JSON only.",
            ],
        }
        try:
            return self.llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You return compact JSON for an EnvFish simulation config.",
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
    ) -> Dict[str, Any]:
        total_rounds = 10 if scenario_mode == "baseline_mode" else 8
        return {
            "scenario_summary": (
                f"Semi-quantitative scenario with "
                f"{region_count} regions and {actor_count} eco-social actors."
            ),
            "generation_reasoning": (
                "Fallback deterministic plan: keep the simulation short, region-level, and centered on "
                "spread, vulnerability, intervention friction, and human-nature feedback."
            ),
            "total_rounds": total_rounds,
            "round_label": "EnvFish simulation round",
            "report_focus": [
                "regional spread forecast",
                "human-nature feedback loops",
                "vulnerability ranking",
                "intervention deltas",
                "uncertainty bands",
            ],
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
