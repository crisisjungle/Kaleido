"""
LLM-led mechanism planning for EnvFish.

This module is intentionally additive: the legacy EnvFish pipeline remains the
default, while llm_mechanism_v1 can replace the relationship graph and emit
mechanism/trace artifacts for live evaluation.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .envfish_models import AgentRelationshipEdge, EnvAgentProfile, RegionNode, clamp_probability, dump_json
from .zep_entity_reader import EntityNode

logger = get_logger("envfish.mechanism")

LEGACY_SIMULATION_ARCHITECTURE = "legacy_envfish_v1"
LLM_MECHANISM_ARCHITECTURE = "llm_mechanism_v1"
SUPPORTED_SIMULATION_ARCHITECTURES = {LEGACY_SIMULATION_ARCHITECTURE, LLM_MECHANISM_ARCHITECTURE}


def normalize_simulation_architecture(value: Optional[str]) -> str:
    normalized = str(value or Config.ENVFISH_SIMULATION_ARCHITECTURE or LEGACY_SIMULATION_ARCHITECTURE)
    normalized = normalized.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"legacy", "envfish", "legacy_envfish"}:
        return LEGACY_SIMULATION_ARCHITECTURE
    if normalized in {"mechanism", "llm_mechanism", "llm_mechanism_v1"}:
        return LLM_MECHANISM_ARCHITECTURE
    if normalized in SUPPORTED_SIMULATION_ARCHITECTURES:
        return normalized
    return LEGACY_SIMULATION_ARCHITECTURE


def is_llm_mechanism_architecture(value: Optional[str]) -> bool:
    return normalize_simulation_architecture(value) == LLM_MECHANISM_ARCHITECTURE


@dataclass
class MechanismArtifacts:
    scenario_model: Dict[str, Any]
    mechanism_graph: Dict[str, Any]
    agent_blueprints: List[Dict[str, Any]]
    relation_edges: List[AgentRelationshipEdge]
    relation_ledger: List[Dict[str, Any]]
    validated_relation_graph: Dict[str, Any]
    simulation_audit: Dict[str, Any]
    scenario_state_schema: Dict[str, Any] = field(default_factory=dict)


class MechanismSimulationPlanner:
    """Build scenario-local mechanisms, agents, and relationships with LLM help."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client
        if self.llm_client is None and Config.LLM_API_KEY:
            try:
                self.llm_client = LLMClient()
            except Exception as exc:
                logger.warning(f"Mechanism planner LLM init failed; explicit fallback will be used: {exc}")

    def build_prepare_artifacts(
        self,
        *,
        sim_dir: str,
        simulation_id: str,
        graph_id: str,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        regions: List[RegionNode],
        subregions: List[RegionNode],
        profiles: List[EnvAgentProfile],
        existing_relationships: List[AgentRelationshipEdge],
        scenario_mode: str,
        diffusion_template: str,
        hazard_template_id: str,
        time_plan: Dict[str, Any],
    ) -> MechanismArtifacts:
        context = self._build_context(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities,
            regions=regions,
            subregions=subregions,
            profiles=profiles,
            existing_relationships=existing_relationships,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
            hazard_template_id=hazard_template_id,
            time_plan=time_plan,
        )
        raw_payload, llm_error = self._generate_with_llm(context)
        if raw_payload:
            payload = self._normalize_payload(raw_payload, context=context, fallback_used=False, fallback_reason="")
        else:
            payload = self._fallback_payload(context=context, fallback_reason=llm_error or "llm_unavailable")

        relation_edges, relation_ledger = self._validate_relations(payload.get("relation_candidates") or [], profiles)
        fallback_relation_count = 0
        desired_relation_count = min(max(8, len(profiles)), max(8, len(profiles) * 3), 360)
        if len(relation_edges) < desired_relation_count:
            fallback_edges, fallback_ledger = self._fallback_relation_edges(
                profiles=profiles,
                existing_relationships=existing_relationships,
                already_seen={(edge.source_agent_id, edge.target_agent_id) for edge in relation_edges},
                mechanism_graph=payload["mechanism_graph"],
                target_count=desired_relation_count - len(relation_edges),
            )
            relation_edges.extend(fallback_edges)
            relation_ledger.extend(fallback_ledger)
            fallback_relation_count = len(fallback_edges)

        self._apply_profile_links(profiles, relation_edges)
        scenario_state_schema = self._scenario_state_schema(payload["scenario_model"])
        validated_relation_graph = self._validated_relation_graph(relation_edges)
        simulation_audit = self._build_audit(
            simulation_id=simulation_id,
            graph_id=graph_id,
            payload=payload,
            relation_edges=relation_edges,
            relation_ledger=relation_ledger,
            fallback_relation_count=fallback_relation_count,
        )

        artifacts = MechanismArtifacts(
            scenario_model=payload["scenario_model"],
            mechanism_graph=payload["mechanism_graph"],
            agent_blueprints=payload["agent_blueprints"],
            relation_edges=relation_edges,
            relation_ledger=relation_ledger,
            validated_relation_graph=validated_relation_graph,
            simulation_audit=simulation_audit,
            scenario_state_schema=scenario_state_schema,
        )
        self.write_artifacts(sim_dir, artifacts)
        return artifacts

    def write_artifacts(self, sim_dir: str, artifacts: MechanismArtifacts) -> None:
        dump_json(os.path.join(sim_dir, "scenario_model.json"), artifacts.scenario_model)
        dump_json(os.path.join(sim_dir, "mechanism_graph.json"), artifacts.mechanism_graph)
        dump_json(os.path.join(sim_dir, "agent_blueprints.json"), artifacts.agent_blueprints)
        dump_json(os.path.join(sim_dir, "validated_relation_graph.json"), artifacts.validated_relation_graph)
        dump_json(os.path.join(sim_dir, "simulation_audit.json"), artifacts.simulation_audit)
        ledger_path = os.path.join(sim_dir, "relation_discovery_ledger.jsonl")
        with open(ledger_path, "w", encoding="utf-8") as handle:
            for record in artifacts.relation_ledger:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _build_context(
        self,
        *,
        simulation_requirement: str,
        document_text: str,
        entities: List[EntityNode],
        regions: List[RegionNode],
        subregions: List[RegionNode],
        profiles: List[EnvAgentProfile],
        existing_relationships: List[AgentRelationshipEdge],
        scenario_mode: str,
        diffusion_template: str,
        hazard_template_id: str,
        time_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        profile_samples = []
        for profile in profiles[:120]:
            profile_samples.append(
                {
                    "agent_id": profile.agent_id,
                    "name": profile.name,
                    "agent_type": profile.agent_type,
                    "agent_subtype": profile.agent_subtype,
                    "node_family": profile.node_family,
                    "role_type": profile.role_type,
                    "home_region_id": profile.home_region_id or profile.primary_region,
                    "home_subregion_id": profile.home_subregion_id,
                    "influenced_regions": list(profile.influenced_regions or [])[:4],
                    "goals": list(profile.goals or [])[:4],
                    "capabilities": list(profile.capabilities or [])[:4],
                    "bio": profile.bio[:240],
                }
            )

        return {
            "simulation_requirement": simulation_requirement[:2200],
            "document_excerpt": document_text[:7000],
            "scenario_mode": scenario_mode,
            "diffusion_template": diffusion_template,
            "hazard_template_id": hazard_template_id,
            "time_plan": dict(time_plan or {}),
            "entities": [self._entity_context(item) for item in entities[:80]],
            "regions": [item.to_dict() for item in regions[:30]],
            "subregions": [item.to_dict() for item in subregions[:60]],
            "profiles": profile_samples,
            "existing_relationships": [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in existing_relationships[:120]
            ],
            "profile_count": len(profiles),
            "region_count": len(regions),
            "subregion_count": len(subregions),
        }

    def _entity_context(self, entity: EntityNode) -> Dict[str, Any]:
        return {
            "uuid": entity.uuid,
            "name": entity.name,
            "labels": list(entity.labels or [])[:5],
            "summary": entity.summary[:360],
            "related_edges": [
                {
                    "name": edge.get("name"),
                    "fact": str(edge.get("fact") or "")[:220],
                    "source_node_uuid": edge.get("source_node_uuid"),
                    "target_node_uuid": edge.get("target_node_uuid"),
                }
                for edge in (entity.related_edges or [])[:8]
                if isinstance(edge, dict)
            ],
            "related_nodes": list(entity.related_nodes or [])[:8],
        }

    def _generate_with_llm(self, context: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.llm_client:
            return None, "llm_unavailable"
        prompt = {
            "task": "Design a scenario-specific ecological simulation mechanism model for EnvFish.",
            "context": context,
            "output_schema": {
                "scenario_model": {
                    "scenario_title": "string",
                    "scenario_summary": "string",
                    "core_processes": ["ecological/physical/social/governance process"],
                    "state_variables": [
                        {
                            "key": "snake_case_key",
                            "label": "display label",
                            "description": "what this variable means",
                            "polarity": "higher_is_worse|higher_is_better|neutral",
                            "legacy_metric": "optional existing metric projection",
                        }
                    ],
                    "key_uncertainties": ["uncertainty"],
                    "assumptions": ["assumption"],
                },
                "mechanism_graph": {
                    "nodes": [
                        {
                            "id": "mech_1",
                            "name": "string",
                            "node_type": "place|agent_role|species|infrastructure|source|process|governance|receptor|data_signal",
                            "description": "string",
                            "evidence": ["source hints"],
                            "confidence": 0.0,
                        }
                    ],
                    "edges": [
                        {
                            "id": "mech_edge_1",
                            "source": "mechanism node id",
                            "target": "mechanism node id",
                            "relation_label": "open label",
                            "mechanism": "why this causal/functional relation exists",
                            "trigger_conditions": ["condition"],
                            "latency": "immediate|hours|days|weeks|months|unknown",
                            "direction": "positive|negative|bidirectional|conditional",
                            "scope": "local|cross_region|cross_scale|systemic",
                            "evidence": ["source hints"],
                            "confidence": 0.0,
                        }
                    ],
                },
                "agent_blueprints": [
                    {
                        "blueprint_id": "role key",
                        "name": "agent/process role",
                        "agent_kind": "human|institution|infrastructure|ecological|physical_process|data_signal",
                        "derived_from_mechanisms": ["mechanism node id"],
                        "observables": ["what it observes"],
                        "capabilities": ["what it can change"],
                        "relationship_instructions": ["how to propose relationships"],
                    }
                ],
                "relation_candidates": [
                    {
                        "source_agent_id": 1,
                        "target_agent_id": 2,
                        "relation_label": "open label",
                        "interaction_channel": "open channel",
                        "mechanism": "why these agents/processes are related",
                        "trigger_conditions": ["condition"],
                        "latency": "immediate|hours|days|weeks|months|unknown",
                        "direction": "positive|negative|bidirectional|conditional",
                        "scope": "local|cross_region|cross_scale|systemic",
                        "evidence": ["source hints"],
                        "confidence": 0.0,
                        "mechanism_edge_ids": ["mech_edge_1"],
                    }
                ],
            },
            "rules": [
                "Do not use a fixed taxonomy of relationship types; relation_label is scenario-local.",
                "Include cross-region and cross-scale relations when mechanisms justify them.",
                "Avoid repeating the same local motif for every subregion.",
                "Every relation candidate must cite a mechanism and evidence.",
                "Use only provided agent_id values for relation_candidates.",
                "Return valid JSON only.",
            ],
        }
        try:
            payload = self.llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an ecological simulation architect. Return compact JSON only.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.35,
                max_tokens=7000,
            )
            return payload, ""
        except Exception as exc:
            logger.warning(f"Mechanism LLM planning failed; explicit fallback will be used: {exc}")
            return None, str(exc)

    def _normalize_payload(
        self,
        raw_payload: Dict[str, Any],
        *,
        context: Dict[str, Any],
        fallback_used: bool,
        fallback_reason: str,
    ) -> Dict[str, Any]:
        scenario_model = raw_payload.get("scenario_model") if isinstance(raw_payload.get("scenario_model"), dict) else {}
        scenario_model = {
            "architecture": LLM_MECHANISM_ARCHITECTURE,
            "llm_participation": "fallback_explicit" if fallback_used else "live",
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
            "scenario_title": str(scenario_model.get("scenario_title") or "EnvFish mechanism scenario"),
            "scenario_summary": str(
                scenario_model.get("scenario_summary")
                or context.get("simulation_requirement")
                or "Scenario-local mechanism model."
            )[:1600],
            "core_processes": self._string_list(scenario_model.get("core_processes"), limit=12),
            "state_variables": self._normalize_state_variables(scenario_model.get("state_variables")),
            "key_uncertainties": self._string_list(scenario_model.get("key_uncertainties"), limit=10),
            "assumptions": self._string_list(scenario_model.get("assumptions"), limit=10),
            "generated_at": datetime.now().isoformat(),
        }

        mechanism_graph = raw_payload.get("mechanism_graph") if isinstance(raw_payload.get("mechanism_graph"), dict) else {}
        mechanism_graph = {
            "architecture": LLM_MECHANISM_ARCHITECTURE,
            "nodes": self._normalize_mechanism_nodes(mechanism_graph.get("nodes")),
            "edges": self._normalize_mechanism_edges(mechanism_graph.get("edges")),
        }
        if not mechanism_graph["nodes"]:
            mechanism_graph["nodes"] = self._fallback_mechanism_nodes(context)
        if not mechanism_graph["edges"]:
            mechanism_graph["edges"] = self._fallback_mechanism_edges(mechanism_graph["nodes"])

        agent_blueprints = self._normalize_agent_blueprints(raw_payload.get("agent_blueprints"))
        if not agent_blueprints:
            agent_blueprints = self._fallback_agent_blueprints(context, mechanism_graph)

        return {
            "scenario_model": scenario_model,
            "mechanism_graph": mechanism_graph,
            "agent_blueprints": agent_blueprints,
            "relation_candidates": raw_payload.get("relation_candidates") if isinstance(raw_payload.get("relation_candidates"), list) else [],
        }

    def _fallback_payload(self, *, context: Dict[str, Any], fallback_reason: str) -> Dict[str, Any]:
        raw = {
            "scenario_model": {
                "scenario_title": "EnvFish explicit fallback mechanism model",
                "scenario_summary": context.get("simulation_requirement") or "Fallback mechanism model generated without LLM.",
                "core_processes": [
                    "source pressure accumulation",
                    "environmental or mobility-mediated transport",
                    "exposed receptor response",
                    "livelihood and service stress",
                    "governance or institutional response",
                ],
                "state_variables": [
                    {
                        "key": "source_pressure",
                        "label": "源头压力",
                        "description": "扰动源或风险源的局部强度。",
                        "polarity": "higher_is_worse",
                        "legacy_metric": "spread_pressure",
                    },
                    {
                        "key": "receptor_exposure",
                        "label": "受体暴露",
                        "description": "生态、基础设施或人群受体受到影响的程度。",
                        "polarity": "higher_is_worse",
                        "legacy_metric": "exposure_score",
                    },
                    {
                        "key": "response_gap",
                        "label": "响应缺口",
                        "description": "治理、服务和协同响应相对压力的不足。",
                        "polarity": "higher_is_worse",
                        "legacy_metric": "vulnerability_score",
                    },
                ],
                "key_uncertainties": ["LLM unavailable, scenario-specific mechanisms require live regeneration."],
                "assumptions": ["Fallback is for contract continuity only, not simulation quality evaluation."],
            },
            "mechanism_graph": {
                "nodes": self._fallback_mechanism_nodes(context),
                "edges": [],
            },
            "agent_blueprints": [],
            "relation_candidates": [],
        }
        raw["mechanism_graph"]["edges"] = self._fallback_mechanism_edges(raw["mechanism_graph"]["nodes"])
        return self._normalize_payload(raw, context=context, fallback_used=True, fallback_reason=fallback_reason)

    def _validate_relations(
        self,
        candidates: Iterable[Dict[str, Any]],
        profiles: List[EnvAgentProfile],
    ) -> Tuple[List[AgentRelationshipEdge], List[Dict[str, Any]]]:
        profile_lookup = {int(profile.agent_id): profile for profile in profiles}
        seen: set[tuple[int, int, str]] = set()
        edges: List[AgentRelationshipEdge] = []
        ledger: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates or []):
            if not isinstance(candidate, dict):
                continue
            source_id = self._to_int(candidate.get("source_agent_id"))
            target_id = self._to_int(candidate.get("target_agent_id"))
            relation_label = self._relation_label(candidate.get("relation_label") or candidate.get("relation_type"))
            record = {
                "index": index,
                "candidate": candidate,
                "source_agent_id": source_id,
                "target_agent_id": target_id,
                "relation_label": relation_label,
                "status": "rejected",
                "reason": "",
                "origin": "llm_relation_discovery",
            }
            if source_id is None or target_id is None:
                record["reason"] = "missing_agent_id"
                ledger.append(record)
                continue
            if source_id == target_id:
                record["reason"] = "self_edge"
                ledger.append(record)
                continue
            source = profile_lookup.get(source_id)
            target = profile_lookup.get(target_id)
            if not source or not target:
                record["reason"] = "agent_not_found"
                ledger.append(record)
                continue
            if not relation_label:
                record["reason"] = "missing_relation_label"
                ledger.append(record)
                continue
            key = (source_id, target_id, relation_label)
            if key in seen:
                record["reason"] = "duplicate"
                ledger.append(record)
                continue
            seen.add(key)
            confidence = clamp_probability(candidate.get("confidence", 0.62))
            mechanism = str(candidate.get("mechanism") or candidate.get("rationale") or "").strip()
            evidence = self._string_list(candidate.get("evidence"), limit=6)
            if not mechanism:
                mechanism = f"{source.name} 与 {target.name} 在场景机制图中存在待验证影响关系。"
            if not evidence:
                evidence = ["llm_relation_candidate"]
            scope = str(candidate.get("scope") or "").strip()
            if not scope:
                scope = "cross_region" if (source.home_region_id or source.primary_region) != (target.home_region_id or target.primary_region) else "local"
            edge = AgentRelationshipEdge(
                edge_id=f"rel_mech_{source_id}_{target_id}_{relation_label}",
                source_agent_id=source_id,
                target_agent_id=target_id,
                relation_type=relation_label,
                strength=confidence,
                interaction_channel=str(candidate.get("interaction_channel") or scope or "mechanism"),
                rationale=mechanism,
                source_region_id=source.home_region_id or source.primary_region,
                target_region_id=target.home_region_id or target.primary_region,
                relation_label=relation_label,
                mechanism=mechanism,
                trigger_conditions=self._string_list(candidate.get("trigger_conditions"), limit=6),
                latency=str(candidate.get("latency") or "unknown"),
                direction=str(candidate.get("direction") or "conditional"),
                scope=scope,
                evidence=evidence,
                confidence=confidence,
                mechanism_edge_ids=self._string_list(candidate.get("mechanism_edge_ids"), limit=6),
                origin="llm_relation_discovery",
                validation_status="accepted",
            )
            edges.append(edge)
            record["status"] = "accepted"
            record["reason"] = "validated"
            record["edge_id"] = edge.edge_id
            ledger.append(record)
        return edges, ledger

    def _fallback_relation_edges(
        self,
        *,
        profiles: List[EnvAgentProfile],
        existing_relationships: List[AgentRelationshipEdge],
        already_seen: set[tuple[int, int]],
        mechanism_graph: Dict[str, Any],
        target_count: int,
    ) -> Tuple[List[AgentRelationshipEdge], List[Dict[str, Any]]]:
        del existing_relationships
        edges: List[AgentRelationshipEdge] = []
        ledger: List[Dict[str, Any]] = []
        profile_by_id = {profile.agent_id: profile for profile in profiles}
        by_region: Dict[str, List[EnvAgentProfile]] = {}
        for profile in profiles:
            region_id = profile.home_region_id or profile.primary_region or "unknown"
            by_region.setdefault(region_id, []).append(profile)
        regions = list(by_region.keys())
        mechanism_edge_ids = [str(edge.get("id")) for edge in mechanism_graph.get("edges") or [] if edge.get("id")]

        def add(source: EnvAgentProfile, target: EnvAgentProfile, label: str, mechanism: str, scope: str) -> None:
            if len(edges) >= target_count:
                return
            if source.agent_id == target.agent_id or (source.agent_id, target.agent_id) in already_seen:
                return
            already_seen.add((source.agent_id, target.agent_id))
            confidence = 0.42 if scope == "cross_region" else 0.38
            edge = AgentRelationshipEdge(
                edge_id=f"rel_mech_fallback_{source.agent_id}_{target.agent_id}_{label}",
                source_agent_id=source.agent_id,
                target_agent_id=target.agent_id,
                relation_type=label,
                strength=confidence,
                interaction_channel=scope,
                rationale=mechanism,
                source_region_id=source.home_region_id or source.primary_region,
                target_region_id=target.home_region_id or target.primary_region,
                relation_label=label,
                mechanism=mechanism,
                trigger_conditions=["fallback_explicit_low_confidence"],
                latency="unknown",
                direction="conditional",
                scope=scope,
                evidence=["fallback_explicit", source.name, target.name],
                confidence=confidence,
                mechanism_edge_ids=mechanism_edge_ids[:2],
                origin="fallback_explicit",
                validation_status="accepted_low_confidence",
            )
            edges.append(edge)
            ledger.append(
                {
                    "status": "accepted",
                    "reason": "fallback_explicit_low_confidence",
                    "origin": "fallback_explicit",
                    "edge_id": edge.edge_id,
                    "source_agent_id": source.agent_id,
                    "target_agent_id": target.agent_id,
                    "relation_label": label,
                }
            )

        for region_id, members in by_region.items():
            if len(edges) >= target_count:
                break
            humans = [item for item in members if item.agent_type == "human"]
            non_humans = [item for item in members if item.agent_type != "human"]
            if humans and non_humans:
                add(
                    humans[0],
                    non_humans[0],
                    "local_mechanism_coupling",
                    f"{humans[0].name} 与 {non_humans[0].name} 位于同一区域，存在低置信场景耦合。",
                    "local",
                )
            other_region = next((item for item in regions if item != region_id), "")
            if not other_region:
                continue
            source = members[0] if members else None
            target = next((item for item in by_region.get(other_region, []) if item.agent_id in profile_by_id), None)
            if source and target:
                add(
                    source,
                    target,
                    "cross_region_mechanism_bridge",
                    f"{source.name} 与 {target.name} 分属不同区域，作为显式降级的跨区机制占位边。",
                    "cross_region",
                )

        if len(edges) < target_count and len(regions) > 1:
            ordered_profiles = sorted(profiles, key=lambda item: (item.home_region_id or item.primary_region, item.agent_id))
            for index, source in enumerate(ordered_profiles):
                if len(edges) >= target_count:
                    break
                source_region = source.home_region_id or source.primary_region
                candidate_targets = [
                    target for target in ordered_profiles
                    if target.agent_id != source.agent_id and (target.home_region_id or target.primary_region) != source_region
                ]
                if not candidate_targets:
                    continue
                target = candidate_targets[(index * 3) % len(candidate_targets)]
                label = self._relation_label(f"fallback_{source.agent_type}_to_{target.agent_type}_cross_scale")
                add(
                    source,
                    target,
                    label,
                    f"{source.name} 与 {target.name} 被补为跨区低置信机制边；正式质量评估必须使用 LLM 重新发现关系。",
                    "cross_region",
                )

        if len(edges) < target_count:
            ordered_profiles = sorted(profiles, key=lambda item: item.agent_id)
            for index, source in enumerate(ordered_profiles):
                if len(edges) >= target_count:
                    break
                same_region_targets = [
                    target for target in ordered_profiles
                    if target.agent_id != source.agent_id
                    and (target.home_region_id or target.primary_region) == (source.home_region_id or source.primary_region)
                ]
                if not same_region_targets:
                    continue
                target = same_region_targets[index % len(same_region_targets)]
                label = self._relation_label(f"fallback_{source.agent_type}_to_{target.agent_type}_local_mechanism")
                add(
                    source,
                    target,
                    label,
                    f"{source.name} 与 {target.name} 被补为局部低置信机制边；用于保持回放和运行时结构完整。",
                    "local",
                )

        return edges, ledger

    def _apply_profile_links(self, profiles: List[EnvAgentProfile], edges: List[AgentRelationshipEdge]) -> None:
        profile_lookup = {profile.agent_id: profile for profile in profiles}
        for profile in profiles:
            profile.counterpart_agent_ids = []
            profile.social_links = []
            profile.ecology_links = []
        for edge in edges:
            source = profile_lookup.get(edge.source_agent_id)
            target = profile_lookup.get(edge.target_agent_id)
            if not source or not target:
                continue
            source.counterpart_agent_ids = list(dict.fromkeys([*source.counterpart_agent_ids, target.agent_id]))
            target.counterpart_agent_ids = list(dict.fromkeys([*target.counterpart_agent_ids, source.agent_id]))
            if target.agent_type in {"ecology", "carrier"}:
                source.ecology_links = list(dict.fromkeys([*source.ecology_links, target.agent_id]))
            else:
                source.social_links = list(dict.fromkeys([*source.social_links, target.agent_id]))

    def _validated_relation_graph(self, edges: List[AgentRelationshipEdge]) -> Dict[str, Any]:
        edge_payloads = [edge.to_dict() for edge in edges]
        cross_region_count = sum(1 for edge in edge_payloads if edge.get("source_region_id") != edge.get("target_region_id"))
        evidence_count = sum(1 for edge in edge_payloads if edge.get("evidence"))
        mechanism_count = sum(1 for edge in edge_payloads if edge.get("mechanism"))
        return {
            "architecture": LLM_MECHANISM_ARCHITECTURE,
            "edge_count": len(edge_payloads),
            "cross_region_edge_count": cross_region_count,
            "evidence_coverage": round(evidence_count / max(1, len(edge_payloads)), 3),
            "mechanism_coverage": round(mechanism_count / max(1, len(edge_payloads)), 3),
            "edges": edge_payloads,
        }

    def _build_audit(
        self,
        *,
        simulation_id: str,
        graph_id: str,
        payload: Dict[str, Any],
        relation_edges: List[AgentRelationshipEdge],
        relation_ledger: List[Dict[str, Any]],
        fallback_relation_count: int,
    ) -> Dict[str, Any]:
        accepted_count = sum(1 for item in relation_ledger if item.get("status") == "accepted")
        rejected_count = sum(1 for item in relation_ledger if item.get("status") == "rejected")
        cross_region_count = sum(1 for edge in relation_edges if edge.source_region_id != edge.target_region_id)
        relation_labels = sorted({edge.relation_type for edge in relation_edges if edge.relation_type})
        return {
            "simulation_id": simulation_id,
            "graph_id": graph_id,
            "architecture": LLM_MECHANISM_ARCHITECTURE,
            "generated_at": datetime.now().isoformat(),
            "llm_participation": payload["scenario_model"].get("llm_participation"),
            "fallback_used": bool(payload["scenario_model"].get("fallback_used") or fallback_relation_count),
            "fallback_reason": payload["scenario_model"].get("fallback_reason") or "",
            "fallback_relation_count": fallback_relation_count,
            "mechanism_node_count": len(payload["mechanism_graph"].get("nodes") or []),
            "mechanism_edge_count": len(payload["mechanism_graph"].get("edges") or []),
            "agent_blueprint_count": len(payload.get("agent_blueprints") or []),
            "accepted_relation_count": accepted_count,
            "rejected_relation_count": rejected_count,
            "cross_region_relation_count": cross_region_count,
            "relation_label_count": len(relation_labels),
            "relation_labels": relation_labels[:80],
            "quality_flags": self._quality_flags(relation_edges, fallback_relation_count),
        }

    def _quality_flags(self, relation_edges: List[AgentRelationshipEdge], fallback_relation_count: int) -> List[str]:
        flags: List[str] = []
        if fallback_relation_count:
            flags.append("fallback_relations_present")
        if not relation_edges:
            flags.append("no_valid_relations")
            return flags
        cross_region_ratio = sum(1 for edge in relation_edges if edge.source_region_id != edge.target_region_id) / len(relation_edges)
        if cross_region_ratio < 0.15:
            flags.append("low_cross_region_ratio")
        labels = [edge.relation_type for edge in relation_edges]
        if len(set(labels)) <= max(2, len(labels) // 12):
            flags.append("low_relation_label_diversity")
        if any(not edge.mechanism for edge in relation_edges):
            flags.append("missing_mechanism_on_some_relations")
        return flags

    def _scenario_state_schema(self, scenario_model: Dict[str, Any]) -> Dict[str, Any]:
        schema: Dict[str, Any] = {}
        for item in scenario_model.get("state_variables") or []:
            if not isinstance(item, dict):
                continue
            key = self._slug(item.get("key") or item.get("label") or "state_variable")
            schema[key] = {
                "label": str(item.get("label") or key),
                "description": str(item.get("description") or ""),
                "polarity": str(item.get("polarity") or "neutral"),
                "legacy_metric": str(item.get("legacy_metric") or ""),
                "source": "scenario_model",
            }
        return schema

    def _normalize_state_variables(self, values: Any) -> List[Dict[str, Any]]:
        variables: List[Dict[str, Any]] = []
        for item in values or []:
            if not isinstance(item, dict):
                continue
            key = self._slug(item.get("key") or item.get("label") or f"state_{len(variables) + 1}")
            variables.append(
                {
                    "key": key,
                    "label": str(item.get("label") or key),
                    "description": str(item.get("description") or ""),
                    "polarity": str(item.get("polarity") or "neutral"),
                    "legacy_metric": str(item.get("legacy_metric") or ""),
                }
            )
        if variables:
            return variables[:16]
        return [
            {
                "key": "source_pressure",
                "label": "源头压力",
                "description": "扰动源或风险源的局部强度。",
                "polarity": "higher_is_worse",
                "legacy_metric": "spread_pressure",
            },
            {
                "key": "receptor_exposure",
                "label": "受体暴露",
                "description": "生态、基础设施或人群受体受到影响的程度。",
                "polarity": "higher_is_worse",
                "legacy_metric": "exposure_score",
            },
        ]

    def _normalize_mechanism_nodes(self, values: Any) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in values or []:
            if not isinstance(item, dict):
                continue
            node_id = self._slug(item.get("id") or item.get("name") or f"mech_{len(nodes) + 1}")
            if node_id in seen:
                continue
            seen.add(node_id)
            nodes.append(
                {
                    "id": node_id,
                    "name": str(item.get("name") or node_id),
                    "node_type": str(item.get("node_type") or "process"),
                    "description": str(item.get("description") or ""),
                    "evidence": self._string_list(item.get("evidence"), limit=6),
                    "confidence": clamp_probability(item.get("confidence", 0.6)),
                }
            )
        return nodes[:80]

    def _normalize_mechanism_edges(self, values: Any) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in values or []:
            if not isinstance(item, dict):
                continue
            source = self._slug(item.get("source") or "")
            target = self._slug(item.get("target") or "")
            relation_label = self._relation_label(item.get("relation_label") or item.get("relation_type"))
            if not source or not target or not relation_label:
                continue
            edge_id = self._slug(item.get("id") or f"mech_edge_{source}_{target}_{relation_label}")
            if edge_id in seen:
                continue
            seen.add(edge_id)
            edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "relation_label": relation_label,
                    "mechanism": str(item.get("mechanism") or ""),
                    "trigger_conditions": self._string_list(item.get("trigger_conditions"), limit=6),
                    "latency": str(item.get("latency") or "unknown"),
                    "direction": str(item.get("direction") or "conditional"),
                    "scope": str(item.get("scope") or "systemic"),
                    "evidence": self._string_list(item.get("evidence"), limit=6),
                    "confidence": clamp_probability(item.get("confidence", 0.6)),
                }
            )
        return edges[:160]

    def _normalize_agent_blueprints(self, values: Any) -> List[Dict[str, Any]]:
        blueprints: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in values or []:
            if not isinstance(item, dict):
                continue
            blueprint_id = self._slug(item.get("blueprint_id") or item.get("name") or f"blueprint_{len(blueprints) + 1}")
            if blueprint_id in seen:
                continue
            seen.add(blueprint_id)
            blueprints.append(
                {
                    "blueprint_id": blueprint_id,
                    "name": str(item.get("name") or blueprint_id),
                    "agent_kind": str(item.get("agent_kind") or "human"),
                    "derived_from_mechanisms": self._string_list(item.get("derived_from_mechanisms"), limit=8),
                    "observables": self._string_list(item.get("observables"), limit=8),
                    "capabilities": self._string_list(item.get("capabilities"), limit=8),
                    "relationship_instructions": self._string_list(item.get("relationship_instructions"), limit=8),
                }
            )
        return blueprints[:80]

    def _fallback_mechanism_nodes(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = [
            {
                "id": "source_pressure",
                "name": "扰动源压力",
                "node_type": "source",
                "description": "场景中最初积累或突然释放的生态/物理/社会压力。",
                "evidence": ["simulation_requirement"],
                "confidence": 0.35,
            },
            {
                "id": "transport_pathway",
                "name": "传输路径",
                "node_type": "process",
                "description": "压力通过环境、交通、供应链或信息路径跨区移动。",
                "evidence": ["diffusion_template"],
                "confidence": 0.35,
            },
            {
                "id": "receptor_response",
                "name": "受体响应",
                "node_type": "receptor",
                "description": "生态、人群、基础设施或机构受体产生状态变化。",
                "evidence": ["profiles"],
                "confidence": 0.35,
            },
        ]
        for region in context.get("regions", [])[:8]:
            region_id = self._slug(region.get("region_id") or region.get("name"))
            nodes.append(
                {
                    "id": f"place_{region_id}",
                    "name": region.get("name") or region_id,
                    "node_type": "place",
                    "description": region.get("description") or "区域机制锚点。",
                    "evidence": ["region_graph"],
                    "confidence": 0.4,
                }
            )
        return nodes

    def _fallback_mechanism_edges(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        node_ids = [item.get("id") for item in nodes if item.get("id")]
        edges = [
            {
                "id": "mech_source_to_transport",
                "source": "source_pressure",
                "target": "transport_pathway",
                "relation_label": "pressure_enters_transport_pathway",
                "mechanism": "源头压力通过场景中的传输路径向外扩散。",
                "trigger_conditions": ["source pressure exceeds local buffering"],
                "latency": "unknown",
                "direction": "positive",
                "scope": "cross_region",
                "evidence": ["fallback_explicit"],
                "confidence": 0.35,
            },
            {
                "id": "mech_transport_to_receptor",
                "source": "transport_pathway",
                "target": "receptor_response",
                "relation_label": "pathway_exposes_receptors",
                "mechanism": "传输路径改变受体暴露水平并引发反馈。",
                "trigger_conditions": ["pathway active", "receptor present"],
                "latency": "unknown",
                "direction": "positive",
                "scope": "cross_scale",
                "evidence": ["fallback_explicit"],
                "confidence": 0.35,
            },
        ]
        for node_id in node_ids:
            if not str(node_id).startswith("place_"):
                continue
            edges.append(
                {
                    "id": f"mech_transport_to_{node_id}",
                    "source": "transport_pathway",
                    "target": node_id,
                    "relation_label": "pathway_reaches_place",
                    "mechanism": "传输路径与区域锚点存在低置信连接。",
                    "trigger_conditions": ["fallback region adjacency"],
                    "latency": "unknown",
                    "direction": "conditional",
                    "scope": "cross_region",
                    "evidence": ["region_graph"],
                    "confidence": 0.32,
                }
            )
        return edges

    def _fallback_agent_blueprints(self, context: Dict[str, Any], mechanism_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        del mechanism_graph
        kinds = []
        for profile in context.get("profiles", []):
            kind = str(profile.get("agent_type") or profile.get("node_family") or "human")
            if kind not in kinds:
                kinds.append(kind)
        return [
            {
                "blueprint_id": self._slug(f"blueprint_{kind}"),
                "name": f"{kind} mechanism role",
                "agent_kind": kind,
                "derived_from_mechanisms": ["source_pressure", "transport_pathway", "receptor_response"],
                "observables": ["local state change", "relationship activation"],
                "capabilities": ["propagate signal", "buffer or amplify risk"],
                "relationship_instructions": ["propose relations only when a mechanism and evidence are available"],
            }
            for kind in kinds[:10]
        ]

    def _string_list(self, value: Any, *, limit: int) -> List[str]:
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, list):
            items = value
        else:
            items = []
        result: List[str] = []
        for item in items:
            text = str(item or "").strip()
            if text:
                result.append(text[:500])
            if len(result) >= limit:
                break
        return list(dict.fromkeys(result))

    def _relation_label(self, value: Any) -> str:
        return self._slug(value or "related_by_mechanism")[:80]

    def _slug(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text or "item"

    def _to_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None
