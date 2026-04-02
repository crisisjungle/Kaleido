"""
EnvFish actor and region generation from Zep entities.
"""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .data_grounding import PublicDataGroundingService
from .envfish_models import (
    AgentRelationshipEdge,
    DIFFUSION_TEMPLATES,
    EnvAgentProfile,
    EnvProfileGenerationResult,
    RegionNode,
    TransportEdge,
    default_state_vector,
    ensure_unique_slug,
    infer_node_family,
    normalize_state_vector,
)
from .transport_context_resolver import TransportContextResolver
from .zep_entity_reader import EntityNode

logger = get_logger("envfish.envfish_profile")


@dataclass
class PreparedEntityContext:
    entity: EntityNode
    entity_type: str
    node_family: str
    summary: str
    relation_hints: List[str]


class EnvProfileGenerator:
    """
    Builds an EnvFish region graph and mixed eco-social actor set.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        grounding_service: Optional[PublicDataGroundingService] = None,
    ):
        self.llm_client = llm_client
        self.grounding_service = grounding_service or PublicDataGroundingService()
        self.transport_context_resolver = TransportContextResolver()
        if self.llm_client is None and Config.LLM_API_KEY:
            try:
                self.llm_client = LLMClient()
            except Exception as exc:
                logger.warning(f"EnvProfileGenerator LLM init failed, will use fallbacks: {exc}")

    def generate_from_entities(
        self,
        entities: List[EntityNode],
        simulation_requirement: str,
        document_text: str,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        reference_time: str = "",
        diffusion_provider: str = "auto",
        use_llm: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        profile_created_callback: Optional[Callable[[EnvAgentProfile, int, int, str], None]] = None,
        parallel_count: int = 3,
    ) -> EnvProfileGenerationResult:
        prepared_entities = [self._prepare_entity(entity) for entity in entities]
        regions = self._build_regions(
            prepared_entities=prepared_entities,
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
        )
        grounding_summary = self.grounding_service.ground(
            regions=[region.to_dict() for region in regions],
            diffusion_template=diffusion_template,
            document_text=document_text,
        )
        self._apply_grounding_priors(regions, grounding_summary)
        diffusion_context = self.transport_context_resolver.resolve(
            regions=regions,
            diffusion_template=diffusion_template,
            reference_time=reference_time,
            preferred_provider=diffusion_provider,
        )
        transport_edges = self._build_transport_edges(
            regions=regions,
            diffusion_template=diffusion_template,
            diffusion_context=diffusion_context,
        )

        subregions = self._build_subregions(
            regions=regions,
            prepared_entities=prepared_entities,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
        )

        anchor_profiles: List[EnvAgentProfile] = []
        total = len(prepared_entities)
        target_count = self._target_agent_count(
            prepared_entities=prepared_entities,
            regions=regions,
            subregions=subregions,
        )
        generated_count = 0

        def emit_profile(profile: EnvAgentProfile, stage: str) -> None:
            nonlocal generated_count
            generated_count += 1
            if profile_created_callback:
                profile_created_callback(profile, generated_count, target_count, stage)

        if progress_callback:
            progress_callback(0, max(total, 1), "开始生成 EnvFish 基础角色")

        def build_profile(args: Tuple[int, PreparedEntityContext]) -> EnvAgentProfile:
            index, prepared = args
            return self._build_profile(
                index=index,
                prepared=prepared,
                regions=regions,
                subregions=subregions,
                scenario_mode=scenario_mode,
                simulation_requirement=simulation_requirement,
                use_llm=use_llm,
            )

        if parallel_count > 1 and total > 1:
            with ThreadPoolExecutor(max_workers=min(parallel_count, total)) as executor:
                future_map = {
                    executor.submit(build_profile, item): item[0] for item in enumerate(prepared_entities)
                }
                completed = 0
                ordered: Dict[int, EnvAgentProfile] = {}
                for future in as_completed(future_map):
                    profile = future.result()
                    ordered[future_map[future]] = profile
                    completed += 1
                    emit_profile(profile, "anchor")
                    if progress_callback:
                        progress_callback(completed, total, f"已生成 {completed}/{total} 个基础角色")
                anchor_profiles = [ordered[index] for index in sorted(ordered.keys())]
        else:
            for index, prepared in enumerate(prepared_entities):
                profile = build_profile((index, prepared))
                anchor_profiles.append(profile)
                emit_profile(profile, "anchor")
                if progress_callback:
                    progress_callback(index + 1, total, f"已生成 {index + 1}/{total} 个基础角色")

        synthesized_profiles = self._expand_synthetic_agents(
            regions=regions,
            subregions=subregions,
            existing_profiles=anchor_profiles,
            target_count=target_count,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
            profile_created_callback=lambda profile: emit_profile(profile, "synthesized"),
        )
        profiles = anchor_profiles + synthesized_profiles
        relationships = self._build_agent_relationships(
            regions=regions,
            subregions=subregions,
            profiles=profiles,
        )
        self._attach_agents_to_regions(regions=regions, subregions=subregions, profiles=profiles)
        region_agent_index = self._compose_region_agent_index(
            regions=regions,
            subregions=subregions,
            profiles=profiles,
        )

        notes = [
            f"Generated {len(regions)} macro regions, {len(subregions)} subregions, and {len(profiles)} agent profiles.",
            f"Anchor entities preserved: {len(anchor_profiles)}; synthesized agents added: {len(synthesized_profiles)}.",
            f"Diffusion template: {diffusion_template}",
            f"Scenario mode: {scenario_mode}",
            f"Transport edges: {len(transport_edges)} via {diffusion_context.get('provider') or 'heuristic'}",
        ]
        if grounding_summary.get("successful_sources"):
            notes.append(f"Grounding sources: {', '.join(grounding_summary['successful_sources'])}")
        if diffusion_context.get("note"):
            notes.append(diffusion_context["note"])

        return EnvProfileGenerationResult(
            regions=regions,
            subregions=subregions,
            profiles=profiles,
            agent_relationships=relationships,
            transport_edges=transport_edges,
            region_agent_index=region_agent_index,
            grounding_summary=grounding_summary,
            diffusion_context=diffusion_context,
            generation_notes=notes,
            generation_summary={
                "macro_region_count": len(regions),
                "subregion_count": len(subregions),
                "anchor_agent_count": len(anchor_profiles),
                "synthesized_agent_count": len(synthesized_profiles),
                "agent_count": len(profiles),
                "relationship_count": len(relationships),
                "transport_edge_count": len(transport_edges),
                "target_agent_count": target_count,
            },
        )

    def _prepare_entity(self, entity: EntityNode) -> PreparedEntityContext:
        entity_type = entity.get_entity_type() or "Entity"
        relation_hints = []
        for item in entity.related_nodes[:6]:
            related_name = item.get("name")
            related_label = item.get("entity_type") or ""
            if related_name:
                relation_hints.append(f"{related_name} ({related_label})")
        summary = entity.summary or entity.attributes.get("description") or entity.attributes.get("summary") or entity.name
        return PreparedEntityContext(
            entity=entity,
            entity_type=entity_type,
            node_family=infer_node_family(entity_type, entity.name, summary),
            summary=summary,
            relation_hints=relation_hints,
        )

    def _build_regions(
        self,
        prepared_entities: List[PreparedEntityContext],
        simulation_requirement: str,
        document_text: str,
        scenario_mode: str,
        diffusion_template: str,
    ) -> List[RegionNode]:
        if diffusion_template not in DIFFUSION_TEMPLATES:
            diffusion_template = "generic"

        region_candidates = self._region_candidates_from_entities(prepared_entities)
        llm_regions = self._build_regions_with_llm(
            region_candidates=region_candidates,
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
        )
        if llm_regions:
            return llm_regions
        return self._build_regions_rule_based(region_candidates, scenario_mode, diffusion_template)

    def _region_candidates_from_entities(self, prepared_entities: List[PreparedEntityContext]) -> List[Dict[str, Any]]:
        candidates = []
        for prepared in prepared_entities:
            haystack = f"{prepared.entity_type} {prepared.entity.name} {prepared.summary}".lower()
            if prepared.node_family == "Region" or any(
                token in haystack for token in ("region", "city", "county", "district", "province", "coast", "bay", "port", "river")
            ):
                lat = self._coerce_float(prepared.entity.attributes.get("lat"))
                lon = self._coerce_float(prepared.entity.attributes.get("lon"))
                candidates.append(
                    {
                        "name": prepared.entity.name,
                        "description": prepared.summary,
                        "entity_type": prepared.entity_type,
                        "tags": [prepared.entity_type, prepared.node_family],
                        "lat": lat,
                        "lon": lon,
                    }
                )

        if not candidates and prepared_entities:
            first = prepared_entities[0]
            candidates.append(
                {
                    "name": first.entity.attributes.get("location")
                    or first.entity.attributes.get("region")
                    or "Core Region",
                    "description": "Fallback region synthesized from the seed report.",
                    "entity_type": "Region",
                    "tags": ["fallback"],
                    "lat": self._coerce_float(first.entity.attributes.get("lat")),
                    "lon": self._coerce_float(first.entity.attributes.get("lon")),
                }
            )
        return candidates[:12]

    def _coerce_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return round(float(value), 6)
        except (TypeError, ValueError):
            return None

    def _build_regions_with_llm(
        self,
        region_candidates: List[Dict[str, Any]],
        simulation_requirement: str,
        document_text: str,
        scenario_mode: str,
        diffusion_template: str,
    ) -> List[RegionNode]:
        if not self.llm_client or not document_text.strip():
            return []

        prompt = {
            "task": "Build a region-level adjacency graph for an eco-social disaster simulation.",
            "scenario_mode": scenario_mode,
            "diffusion_template": diffusion_template,
            "region_candidates": region_candidates,
            "requirement": simulation_requirement[:1500],
            "document_excerpt": document_text[:6000],
            "output_schema": {
                "regions": [
                    {
                        "name": "Region name",
                        "region_type": "coastal_zone/city/river_basin/port/industrial_zone/residential_zone",
                        "description": "short explanation",
                        "neighbors": ["neighbor names"],
                        "carriers": ["air_mass/river_segment/coastal_current/soil_zone"],
                        "tags": ["coastal", "fishery", "urban"],
                        "lat": 0.0,
                        "lon": 0.0,
                    }
                ]
            },
            "rules": [
                "Return 3-8 regions whenever information allows, otherwise return at least one.",
                "Neighbors must refer to other listed regions.",
                "Prefer region-level units, not single buildings.",
                "If information is sparse, still return at least one region.",
            ],
        }

        try:
            result = self.llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You produce compact, valid JSON for a region-level eco-social simulation graph.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=2500,
            )
        except Exception as exc:
            logger.warning(f"Region graph LLM generation failed, falling back: {exc}")
            return []

        raw_regions = result.get("regions") or []
        if not isinstance(raw_regions, list) or not raw_regions:
            return []

        used: set[str] = set()
        regions: List[RegionNode] = []
        name_to_id: Dict[str, str] = {}
        candidate_lookup = {str(item.get("name") or "").strip(): item for item in region_candidates}
        for item in raw_regions[:8]:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            region_id = ensure_unique_slug(name, used)
            name_to_id[name] = region_id
            candidate = candidate_lookup.get(name, {})
            regions.append(
                RegionNode(
                    region_id=region_id,
                    name=name,
                    region_type=str(item.get("region_type") or "region"),
                    description=str(item.get("description") or ""),
                    carriers=[str(carrier) for carrier in (item.get("carriers") or [])[:4]],
                    tags=[str(tag) for tag in (item.get("tags") or [])[:6]],
                    lat=self._coerce_float(item.get("lat")) or self._coerce_float(candidate.get("lat")),
                    lon=self._coerce_float(item.get("lon")) or self._coerce_float(candidate.get("lon")),
                    state_vector=default_state_vector(scenario_mode, "Region"),
                )
            )

        if not regions:
            return []

        raw_lookup = {str(item.get("name") or "").strip(): item for item in raw_regions}
        for region in regions:
            raw_item = raw_lookup.get(region.name, {})
            for neighbor_name in raw_item.get("neighbors") or []:
                neighbor_id = name_to_id.get(str(neighbor_name).strip())
                if neighbor_id and neighbor_id != region.region_id:
                    region.neighbors.append(neighbor_id)
        self._ensure_region_connectivity(regions, diffusion_template)
        return regions

    def _build_regions_rule_based(
        self,
        region_candidates: List[Dict[str, Any]],
        scenario_mode: str,
        diffusion_template: str,
    ) -> List[RegionNode]:
        if not region_candidates:
            region_candidates = [{"name": "Core Region", "description": "Fallback region", "tags": ["fallback"]}]

        used: set[str] = set()
        regions: List[RegionNode] = []
        for item in region_candidates[:6]:
            name = str(item.get("name") or "Region").strip()
            region_id = ensure_unique_slug(name, used)
            regions.append(
                RegionNode(
                    region_id=region_id,
                    name=name,
                    region_type=str(item.get("entity_type") or "region"),
                    description=str(item.get("description") or ""),
                    carriers=self._default_carriers(diffusion_template),
                    tags=[str(tag) for tag in (item.get("tags") or [])[:4]],
                    lat=self._coerce_float(item.get("lat")),
                    lon=self._coerce_float(item.get("lon")),
                    state_vector=default_state_vector(scenario_mode, "Region"),
                )
            )

        self._ensure_region_connectivity(regions, diffusion_template)
        return regions

    def _ensure_region_connectivity(self, regions: List[RegionNode], diffusion_template: str) -> None:
        if len(regions) <= 1:
            return
        for index, region in enumerate(regions):
            if not region.carriers:
                region.carriers = self._default_carriers(diffusion_template)
            if index > 0 and regions[index - 1].region_id not in region.neighbors:
                region.neighbors.append(regions[index - 1].region_id)
            if index < len(regions) - 1 and regions[index + 1].region_id not in region.neighbors:
                region.neighbors.append(regions[index + 1].region_id)

    def _default_carriers(self, diffusion_template: str) -> List[str]:
        if diffusion_template == "air":
            return ["air_mass"]
        if diffusion_template == "inland_water":
            return ["river_segment"]
        if diffusion_template == "marine":
            return ["coastal_current"]
        return ["environmental_link"]

    def _build_transport_edges(
        self,
        regions: List[RegionNode],
        diffusion_template: str,
        diffusion_context: Dict[str, Any],
    ) -> List[TransportEdge]:
        if len(regions) <= 1:
            return []
        if diffusion_template == "inland_water":
            return self._build_inland_water_transport_edges(regions)
        if diffusion_template == "air":
            return self._build_projected_transport_edges(
                regions=regions,
                flow_direction_deg=diffusion_context.get("flow_direction_deg"),
                channel_type="air_corridor",
                attenuation_rate=0.18,
                travel_time_rounds=1,
                retention_factor=0.06,
                directionality="directed",
                evidence={"transport_context": diffusion_context},
                rationale="Atmospheric transport follows dominant wind-driven downwind ordering.",
            )
        if diffusion_template == "marine":
            return self._build_projected_transport_edges(
                regions=regions,
                flow_direction_deg=diffusion_context.get("flow_direction_deg"),
                channel_type="coastal_current",
                attenuation_rate=0.1,
                travel_time_rounds=2,
                retention_factor=0.42,
                directionality="asymmetric",
                evidence={"transport_context": diffusion_context},
                rationale="Marine transport follows coastal-current ordering with stronger retention in enclosed zones.",
            )
        return self._build_neighbor_transport_edges(regions, channel_type="environmental_link")

    def _build_inland_water_transport_edges(self, regions: List[RegionNode]) -> List[TransportEdge]:
        order_lookup = {
            region.region_id: (
                self._river_rank(region),
                index,
            )
            for index, region in enumerate(regions)
        }
        edges: List[TransportEdge] = []
        seen: set[tuple[str, str, str]] = set()
        region_lookup = {region.region_id: region for region in regions}

        for region in regions:
            ordered_neighbors = sorted(
                [region_lookup[item] for item in region.neighbors if item in region_lookup and item != region.region_id],
                key=lambda item: order_lookup[item.region_id],
            )
            downstream_neighbors = [
                item for item in ordered_neighbors if order_lookup[item.region_id] > order_lookup[region.region_id]
            ]
            if not downstream_neighbors:
                downstream_neighbors = [item for item in ordered_neighbors[:1] if item.region_id != region.region_id]
            for neighbor in downstream_neighbors[:2]:
                self._append_transport_edge(
                    edges=edges,
                    seen=seen,
                    source=region,
                    target=neighbor,
                    channel_type="river_reach",
                    directionality="directed",
                    attenuation_rate=0.14,
                    travel_time_rounds=1,
                    retention_factor=0.18 if self._is_retention_region(neighbor) else 0.08,
                    barrier_factor=0.24 if self._is_barrier_region(neighbor) else 0.0,
                    confidence=0.72,
                    evidence={"ordering": "river_rank", "source_rank": order_lookup[region.region_id][0], "target_rank": order_lookup[neighbor.region_id][0]},
                    rationale="Inland-water routing follows directed upstream-to-downstream topology.",
                )

        if not edges:
            ordered_regions = sorted(regions, key=lambda item: order_lookup[item.region_id])
            for source, target in zip(ordered_regions, ordered_regions[1:]):
                self._append_transport_edge(
                    edges=edges,
                    seen=seen,
                    source=source,
                    target=target,
                    channel_type="river_reach",
                    directionality="directed",
                    attenuation_rate=0.14,
                    travel_time_rounds=1,
                    retention_factor=0.08,
                    confidence=0.62,
                    evidence={"ordering": "fallback_chain"},
                    rationale="Fallback inland-water routing follows ordered basin chain.",
                )
        return edges

    def _build_projected_transport_edges(
        self,
        *,
        regions: List[RegionNode],
        flow_direction_deg: Optional[float],
        channel_type: str,
        attenuation_rate: float,
        travel_time_rounds: int,
        retention_factor: float,
        directionality: str,
        evidence: Dict[str, Any],
        rationale: str,
    ) -> List[TransportEdge]:
        if flow_direction_deg is None:
            return self._build_neighbor_transport_edges(
                regions,
                channel_type=channel_type,
                attenuation_rate=attenuation_rate,
                travel_time_rounds=travel_time_rounds,
                retention_factor=retention_factor,
                confidence=0.46,
                rationale=f"{rationale} Fallback to topology-only ordering because directional data is unavailable.",
            )

        coords = [region for region in regions if region.lat is not None and region.lon is not None]
        if len(coords) < 2:
            return self._build_neighbor_transport_edges(
                regions,
                channel_type=channel_type,
                attenuation_rate=attenuation_rate,
                travel_time_rounds=travel_time_rounds,
                retention_factor=retention_factor,
                confidence=0.46,
                rationale=f"{rationale} Fallback to topology-only ordering because region coordinates are unavailable.",
            )

        ordered_regions = sorted(
            regions,
            key=lambda item: self._projection_along_direction(item, float(flow_direction_deg)),
        )
        edges: List[TransportEdge] = []
        seen: set[tuple[str, str, str]] = set()
        for source, target in zip(ordered_regions, ordered_regions[1:]):
            if source.region_id == target.region_id:
                continue
            retention = retention_factor
            if self._is_retention_region(source) or self._is_retention_region(target):
                retention = min(0.85, retention_factor + 0.18)
            self._append_transport_edge(
                edges=edges,
                seen=seen,
                source=source,
                target=target,
                channel_type=channel_type,
                directionality=directionality,
                attenuation_rate=attenuation_rate,
                travel_time_rounds=travel_time_rounds,
                retention_factor=retention,
                confidence=0.68,
                evidence={
                    **evidence,
                    "ordering": "directional_projection",
                    "flow_direction_deg": round(float(flow_direction_deg), 2),
                },
                rationale=rationale,
            )
        return edges or self._build_neighbor_transport_edges(regions, channel_type=channel_type)

    def _build_neighbor_transport_edges(
        self,
        regions: List[RegionNode],
        channel_type: str,
        attenuation_rate: float = 0.16,
        travel_time_rounds: int = 1,
        retention_factor: float = 0.08,
        confidence: float = 0.52,
        rationale: Optional[str] = None,
    ) -> List[TransportEdge]:
        edges: List[TransportEdge] = []
        seen: set[tuple[str, str, str]] = set()
        region_lookup = {region.region_id: region for region in regions}

        for region in regions:
            targets = [region_lookup[item] for item in region.neighbors if item in region_lookup and item != region.region_id]
            if not targets:
                continue
            for target in targets:
                self._append_transport_edge(
                    edges=edges,
                    seen=seen,
                    source=region,
                    target=target,
                    channel_type=channel_type,
                    directionality="directed",
                    attenuation_rate=attenuation_rate,
                    travel_time_rounds=travel_time_rounds,
                    retention_factor=retention_factor,
                    confidence=confidence,
                    evidence={"ordering": "neighbor_fallback"},
                    rationale=rationale or "Transport falls back to existing neighbor adjacency.",
                )

        if edges:
            return edges

        for source, target in zip(regions, regions[1:]):
            self._append_transport_edge(
                edges=edges,
                seen=seen,
                source=source,
                target=target,
                channel_type=channel_type,
                directionality="directed",
                attenuation_rate=attenuation_rate,
                travel_time_rounds=travel_time_rounds,
                retention_factor=retention_factor,
                confidence=confidence,
                evidence={"ordering": "chain_fallback"},
                rationale=rationale or "Transport falls back to ordered region chain.",
            )
        return edges

    def _append_transport_edge(
        self,
        *,
        edges: List[TransportEdge],
        seen: set[tuple[str, str, str]],
        source: RegionNode,
        target: RegionNode,
        channel_type: str,
        directionality: str,
        attenuation_rate: float,
        travel_time_rounds: int,
        retention_factor: float,
        confidence: float,
        evidence: Dict[str, Any],
        rationale: str,
        barrier_factor: float = 0.0,
    ) -> None:
        if source.region_id == target.region_id:
            return
        key = (source.region_id, target.region_id, channel_type)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            TransportEdge(
                edge_id=f"transport_{channel_type}_{source.region_id}_{target.region_id}",
                source_region_id=source.region_id,
                target_region_id=target.region_id,
                channel_type=channel_type,
                directionality=directionality,
                attenuation_rate=attenuation_rate,
                travel_time_rounds=travel_time_rounds,
                retention_factor=retention_factor,
                barrier_factor=barrier_factor,
                strength=max(0.28, 1.0 - attenuation_rate),
                confidence=confidence,
                evidence=evidence,
                rationale=rationale,
            )
        )

    def _river_rank(self, region: RegionNode) -> int:
        text = f"{region.name} {' '.join(region.tags)} {region.description}".lower()
        if any(token in text for token in ("upstream", "headwater", "源头", "上游")):
            return -3
        if any(token in text for token in ("midstream", "中游")):
            return 0
        if any(token in text for token in ("downstream", "estuary", "delta", "下游", "入海口", "河口")):
            return 4
        if any(token in text for token in ("reservoir", "basin", "湖", "库")):
            return 2
        return 0

    def _is_retention_region(self, region: RegionNode) -> bool:
        text = f"{region.name} {' '.join(region.tags)} {region.description}".lower()
        return any(token in text for token in ("bay", "harbor", "port", "lagoon", "reservoir", "basin", "湾", "港", "库", "湖"))

    def _is_barrier_region(self, region: RegionNode) -> bool:
        text = f"{region.name} {' '.join(region.tags)} {region.description}".lower()
        return any(token in text for token in ("dam", "gate", "sluice", "levee", "坝", "闸", "堤"))

    def _projection_along_direction(self, region: RegionNode, flow_direction_deg: float) -> float:
        if region.lat is None or region.lon is None:
            return float("inf")
        radians = math.radians(flow_direction_deg)
        x = float(region.lon) * math.cos(math.radians(float(region.lat)))
        y = float(region.lat)
        return round(x * math.sin(radians) + y * math.cos(radians), 6)

    def _apply_grounding_priors(self, regions: List[RegionNode], grounding_summary: Dict[str, Any]) -> None:
        records = grounding_summary.get("records") or []
        lookup = {region.name: region for region in regions}
        for record in records:
            region_name = record.get("metadata", {}).get("region")
            region = lookup.get(region_name)
            if not region:
                continue
            merged = dict(region.state_vector)
            for key, value in (record.get("priors") or {}).items():
                if key in merged:
                    merged[key] = max(0.0, min(100.0, (merged[key] + float(value)) / 2))
            region.state_vector = normalize_state_vector(merged)

    def _target_agent_count(
        self,
        prepared_entities: List[PreparedEntityContext],
        regions: List[RegionNode],
        subregions: List[RegionNode],
    ) -> int:
        base = len(prepared_entities)
        layered = max(len(subregions) * 4, len(regions) * 12)
        return min(180, max(84, base + layered))

    def _build_subregions(
        self,
        regions: List[RegionNode],
        prepared_entities: List[PreparedEntityContext],
        scenario_mode: str,
        diffusion_template: str,
    ) -> List[RegionNode]:
        del prepared_entities
        used: set[str] = set()
        subregions: List[RegionNode] = []

        for region in regions:
            local_subregions: List[RegionNode] = []
            for blueprint in self._subregion_blueprints(region, diffusion_template):
                subregion_id = ensure_unique_slug(f"{region.name}_{blueprint['slug']}", used)
                state_vector = default_state_vector(scenario_mode, "Region")
                if blueprint["distance_band"] == "near":
                    state_vector["exposure_score"] += 12
                    state_vector["spread_pressure"] += 10
                    state_vector["vulnerability_score"] += 8
                if blueprint["land_use_class"] == "industrial":
                    state_vector["economic_stress"] += 10
                    state_vector["ecosystem_integrity"] -= 8
                if blueprint["land_use_class"] == "ecology":
                    state_vector["ecosystem_integrity"] += 6
                    state_vector["vulnerability_score"] += 6
                    state_vector["livelihood_stability"] -= 4
                local_subregions.append(
                    RegionNode(
                        region_id=subregion_id,
                        name=f"{region.name}·{blueprint['label']}",
                        region_type=blueprint["region_type"],
                        description=blueprint["description"],
                        parent_region_id=region.region_id,
                        layer="subregion",
                        land_use_class=blueprint["land_use_class"],
                        distance_band=blueprint["distance_band"],
                        neighbors=[],
                        carriers=blueprint["carriers"] or list(region.carriers),
                        tags=[region.region_type, blueprint["land_use_class"], blueprint["distance_band"], *region.tags],
                        ecology_assets=blueprint["ecology_assets"],
                        industry_tags=blueprint["industry_tags"],
                        region_constraints=blueprint["region_constraints"],
                        exposure_channels=blueprint["exposure_channels"],
                        population_capacity=blueprint["population_capacity"],
                        state_vector=normalize_state_vector(state_vector),
                    )
                )

            for index, item in enumerate(local_subregions):
                if index > 0:
                    item.neighbors.append(local_subregions[index - 1].region_id)
                if index < len(local_subregions) - 1:
                    item.neighbors.append(local_subregions[index + 1].region_id)
            subregions.extend(local_subregions)

        return subregions

    def _subregion_blueprints(self, region: RegionNode, diffusion_template: str) -> List[Dict[str, Any]]:
        ecology_focus = {
            "marine": {
                "label": "滨海生态带",
                "ecology_assets": ["mangrove", "seabird", "shellfish"],
                "carriers": ["coastal_current", "shore_wind"],
            },
            "inland_water": {
                "label": "河岸生态带",
                "ecology_assets": ["riparian_plants", "freshwater_fish", "wetland_birds"],
                "carriers": ["river_segment", "groundwater_exchange"],
            },
            "air": {
                "label": "下风向生态缓冲区",
                "ecology_assets": ["tree_canopy", "urban_birds", "soil_microbiome"],
                "carriers": ["air_mass", "dust_pathway"],
            },
            "generic": {
                "label": "生态缓冲带",
                "ecology_assets": ["wetland_plants", "indicator_species"],
                "carriers": ["environmental_link"],
            },
        }.get(diffusion_template, {})

        return [
            {
                "slug": "near_residential",
                "label": "近污染居民区",
                "region_type": "residential_zone",
                "land_use_class": "residential",
                "distance_band": "near",
                "description": f"{region.name} 中最先感知环境异常和生活压力的居住片区。",
                "ecology_assets": ["street_trees", "pet_animals"],
                "industry_tags": ["community_services"],
                "region_constraints": ["密集人口", "信息敏感"],
                "exposure_channels": ["air", "water", "daily_contact"],
                "population_capacity": 18,
                "carriers": list(region.carriers),
            },
            {
                "slug": "commercial_service",
                "label": "商业服务区",
                "region_type": "commercial_zone",
                "land_use_class": "commercial",
                "distance_band": "transition",
                "description": f"{region.name} 的办公、零售和物流服务节点。",
                "ecology_assets": ["urban_birds"],
                "industry_tags": ["retail", "logistics"],
                "region_constraints": ["供给波动", "舆情敏感"],
                "exposure_channels": ["consumer_flow", "supply_chain"],
                "population_capacity": 14,
                "carriers": list(region.carriers),
            },
            {
                "slug": "industrial_interface",
                "label": "工业作业区",
                "region_type": "industrial_zone",
                "land_use_class": "industrial",
                "distance_band": "near",
                "description": f"{region.name} 中与排放、生产和基础设施相连的工业片区。",
                "ecology_assets": ["soil_microbiome"],
                "industry_tags": ["manufacturing", "heavy_equipment"],
                "region_constraints": ["合规压力", "停工成本"],
                "exposure_channels": ["waste_stream", "transport", "surface_contact"],
                "population_capacity": 12,
                "carriers": list(region.carriers),
            },
            {
                "slug": "civic_response",
                "label": "治理响应区",
                "region_type": "civic_zone",
                "land_use_class": "civic",
                "distance_band": "transition",
                "description": f"{region.name} 中公共服务、治理与媒体响应集中的片区。",
                "ecology_assets": ["monitoring_plots"],
                "industry_tags": ["governance", "healthcare", "education"],
                "region_constraints": ["协调摩擦", "资源分配"],
                "exposure_channels": ["policy", "public_communication"],
                "population_capacity": 10,
                "carriers": list(region.carriers),
            },
            {
                "slug": "eco_buffer",
                "label": ecology_focus.get("label", "生态缓冲带"),
                "region_type": "ecology_zone",
                "land_use_class": "ecology",
                "distance_band": "far",
                "description": f"{region.name} 中承载典型生态受体和自然修复潜力的生态片区。",
                "ecology_assets": ecology_focus.get("ecology_assets", ["indicator_species"]),
                "industry_tags": ["habitat"],
                "region_constraints": ["恢复缓慢", "阈值脆弱"],
                "exposure_channels": ecology_focus.get("carriers", list(region.carriers)),
                "population_capacity": 8,
                "carriers": ecology_focus.get("carriers", list(region.carriers)),
            },
        ]

    def _expand_synthetic_agents(
        self,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        existing_profiles: List[EnvAgentProfile],
        target_count: int,
        scenario_mode: str,
        diffusion_template: str,
        profile_created_callback: Optional[Callable[[EnvAgentProfile], None]] = None,
    ) -> List[EnvAgentProfile]:
        region_lookup = {region.region_id: region for region in regions}
        profiles: List[EnvAgentProfile] = []
        next_index = len(existing_profiles)
        desired = max(0, target_count - len(existing_profiles))

        for subregion in subregions:
            parent_region = region_lookup.get(subregion.parent_region_id or "", regions[0])
            for blueprint in self._synthetic_agent_blueprints(subregion, parent_region, diffusion_template):
                if len(profiles) >= desired:
                    break
                profiles.append(
                    self._build_synthetic_profile(
                        index=next_index,
                        blueprint=blueprint,
                        region=parent_region,
                        subregion=subregion,
                        scenario_mode=scenario_mode,
                    )
                )
                if profile_created_callback:
                    profile_created_callback(profiles[-1])
                next_index += 1
            if len(profiles) >= desired:
                break
        return profiles

    def _synthetic_agent_blueprints(
        self,
        subregion: RegionNode,
        region: RegionNode,
        diffusion_template: str,
    ) -> List[Dict[str, Any]]:
        ecology_name = {
            "marine": "红树林观察点" if subregion.land_use_class == "ecology" else "海鸥群",
            "inland_water": "河岸鱼群" if subregion.land_use_class == "ecology" else "湿地鸟群",
            "air": "城市树冠层" if subregion.land_use_class == "ecology" else "下风向鸟群",
            "generic": "指示物种群",
        }.get(diffusion_template, "指示物种群")

        blueprints_by_land_use = {
            "residential": [
                {"name": "居民代表", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "resident", "role_type": "Resident"},
                {"name": "环保志愿者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "activist", "role_type": "EnvironmentalVolunteer"},
                {"name": "社区委员会", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "community_committee", "role_type": "CommunityCommittee"},
                {"name": ecology_name, "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "urban_ecology", "role_type": "EcologySentinel"},
            ],
            "commercial": [
                {"name": "白领", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "white_collar", "role_type": "WhiteCollar"},
                {"name": "店主", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "shop_owner", "role_type": "ShopOwner"},
                {"name": "商圈协会", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "market_association", "role_type": "MarketAssociation"},
                {"name": "城市鸟群", "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "urban_birds", "role_type": "UrbanBirds"},
            ],
            "industrial": [
                {"name": "工人", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "worker", "role_type": "Worker"},
                {"name": "厂区经营方", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "plant_operator", "role_type": "PlantOperator"},
                {"name": "安全监察员", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "safety_inspector", "role_type": "SafetyInspector"},
                {"name": "土壤微生境", "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "soil_biome", "role_type": "SoilBiome"},
            ],
            "civic": [
                {"name": "环保部门", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "environment_bureau", "role_type": "EnvironmentBureau"},
                {"name": "应急协调员", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "emergency_office", "role_type": "EmergencyOffice"},
                {"name": "科研人员", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "scientist", "role_type": "Scientist"},
                {"name": "新闻记者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "journalist", "role_type": "Journalist"},
            ],
            "ecology": [
                {"name": "渔民/田间观察者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "field_observer", "role_type": "FieldObserver"},
                {"name": "保育站", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "conservation_station", "role_type": "ConservationStation"},
                {"name": ecology_name, "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "habitat_species", "role_type": "HabitatSpecies"},
                {"name": "水体/空气载体", "node_family": "EnvironmentalCarrier", "agent_type": "carrier", "agent_subtype": diffusion_template or "environmental_link", "role_type": "CarrierNode"},
            ],
        }
        return blueprints_by_land_use.get(subregion.land_use_class, blueprints_by_land_use["residential"])

    def _build_synthetic_profile(
        self,
        index: int,
        blueprint: Dict[str, Any],
        region: RegionNode,
        subregion: RegionNode,
        scenario_mode: str,
    ) -> EnvAgentProfile:
        display_name = f"{subregion.name}{blueprint['name']}"
        behavior = self._behavior_bundle(
            node_family=blueprint["node_family"],
            agent_subtype=blueprint["agent_subtype"],
            region_name=region.name,
            subregion_name=subregion.name,
            land_use_class=subregion.land_use_class,
        )
        return EnvAgentProfile(
            agent_id=index,
            username=self._username_from_name(display_name, index),
            name=display_name,
            node_family=blueprint["node_family"],
            role_type=blueprint["role_type"],
            bio=behavior["bio"],
            persona=behavior["persona"],
            profession=blueprint["name"],
            primary_region=region.region_id,
            agent_type=blueprint["agent_type"],
            agent_subtype=blueprint["agent_subtype"],
            archetype_key=f"{subregion.land_use_class}:{blueprint['agent_subtype']}",
            home_region_id=region.region_id,
            home_subregion_id=subregion.region_id,
            influenced_regions=[region.region_id, *region.neighbors[:2]],
            goals=behavior["goals"],
            sensitivities=behavior["sensitivities"],
            motivation_stack=behavior["motivation_stack"],
            capabilities=behavior["capabilities"],
            constraints=behavior["constraints"],
            action_space=behavior["action_space"],
            decision_policy=behavior["decision_policy"],
            impact_profile=behavior["impact_profile"],
            stance_profile=behavior["stance_profile"],
            resource_budget=behavior["resource_budget"],
            spawn_weight=behavior["spawn_weight"],
            is_synthesized=True,
            state_vector=default_state_vector(scenario_mode, blueprint["node_family"]),
            source_entity_uuid=None,
            source_entity_type=blueprint["role_type"],
        )

    def _build_agent_relationships(
        self,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        profiles: List[EnvAgentProfile],
    ) -> List[AgentRelationshipEdge]:
        del regions
        edges: List[AgentRelationshipEdge] = []
        edge_seen: set[tuple[int, int, str]] = set()
        by_subregion: Dict[str, List[EnvAgentProfile]] = {}
        for profile in profiles:
            if profile.home_subregion_id:
                by_subregion.setdefault(profile.home_subregion_id, []).append(profile)

        for subregion in subregions:
            members = by_subregion.get(subregion.region_id, [])
            if not members:
                continue
            humans = [item for item in members if item.agent_type == "human"]
            orgs = [item for item in members if item.agent_type in {"organization", "governance"}]
            ecology = [item for item in members if item.agent_type in {"ecology", "carrier"}]
            for source in humans[:3]:
                if orgs:
                    self._append_relationship(
                        edges,
                        edge_seen,
                        source,
                        orgs[0],
                        relation_type="reports_to" if orgs[0].agent_type == "governance" else "depends_on",
                        interaction_channel="governance",
                        rationale=f"{source.name} 将风险感知和诉求传递给 {orgs[0].name}。",
                    )
                if ecology:
                    self._append_relationship(
                        edges,
                        edge_seen,
                        source,
                        ecology[0],
                        relation_type="impacts_or_observes",
                        interaction_channel="ecology",
                        rationale=f"{source.name} 与 {ecology[0].name} 共享同一生态压力现场。",
                    )
            for source in orgs[:2]:
                for target in ecology[:2]:
                    self._append_relationship(
                        edges,
                        edge_seen,
                        source,
                        target,
                        relation_type="regulates_or_alters",
                        interaction_channel="environment",
                        rationale=f"{source.name} 的决策可直接改变 {target.name} 的环境条件。",
                    )
            for pair_index in range(max(0, len(humans) - 1)):
                self._append_relationship(
                    edges,
                    edge_seen,
                    humans[pair_index],
                    humans[pair_index + 1],
                    relation_type="community_link",
                    interaction_channel="social",
                    rationale="同一子区域内的个体会相互传递观察、情绪和行动建议。",
                )

        profile_lookup = {profile.agent_id: profile for profile in profiles}
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
        return edges

    def _append_relationship(
        self,
        edges: List[AgentRelationshipEdge],
        edge_seen: set[tuple[int, int, str]],
        source: EnvAgentProfile,
        target: EnvAgentProfile,
        relation_type: str,
        interaction_channel: str,
        rationale: str,
    ) -> None:
        if source.agent_id == target.agent_id:
            return
        key = (source.agent_id, target.agent_id, relation_type)
        if key in edge_seen:
            return
        edge_seen.add(key)
        edges.append(
            AgentRelationshipEdge(
                edge_id=f"rel_{source.agent_id}_{target.agent_id}_{relation_type}",
                source_agent_id=source.agent_id,
                target_agent_id=target.agent_id,
                relation_type=relation_type,
                strength=0.58 if interaction_channel == "social" else 0.66,
                interaction_channel=interaction_channel,
                rationale=rationale,
                source_region_id=source.home_region_id or source.primary_region,
                target_region_id=target.home_region_id or target.primary_region,
            )
        )

    def _attach_agents_to_regions(
        self,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        profiles: List[EnvAgentProfile],
    ) -> None:
        region_lookup = {region.region_id: region for region in [*regions, *subregions]}
        for region in region_lookup.values():
            region.resident_agent_ids = []
            region.organization_agent_ids = []
            region.ecology_agent_ids = []

        for profile in profiles:
            target_ids = [profile.home_region_id or profile.primary_region]
            if profile.home_subregion_id:
                target_ids.append(profile.home_subregion_id)
            for region_id in target_ids:
                region = region_lookup.get(region_id)
                if not region:
                    continue
                if profile.agent_type == "human":
                    region.resident_agent_ids.append(profile.agent_id)
                elif profile.agent_type in {"organization", "governance", "infrastructure"}:
                    region.organization_agent_ids.append(profile.agent_id)
                else:
                    region.ecology_agent_ids.append(profile.agent_id)

    def _compose_region_agent_index(
        self,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        profiles: List[EnvAgentProfile],
    ) -> Dict[str, Any]:
        subregions_by_parent: Dict[str, List[RegionNode]] = {}
        for subregion in subregions:
            subregions_by_parent.setdefault(subregion.parent_region_id or "", []).append(subregion)

        profiles_by_region: Dict[str, List[EnvAgentProfile]] = {}
        for profile in profiles:
            profiles_by_region.setdefault(profile.home_region_id or profile.primary_region, []).append(profile)

        profiles_by_subregion: Dict[str, List[EnvAgentProfile]] = {}
        for profile in profiles:
            if profile.home_subregion_id:
                profiles_by_subregion.setdefault(profile.home_subregion_id, []).append(profile)

        def summarize(items: List[EnvAgentProfile]) -> Dict[str, int]:
            counts = {"human": 0, "organization": 0, "governance": 0, "ecology": 0, "carrier": 0}
            for item in items:
                counts[item.agent_type] = counts.get(item.agent_type, 0) + 1
            return counts

        return {
            "regions": {
                region.region_id: {
                    "region_name": region.name,
                    "subregion_ids": [item.region_id for item in subregions_by_parent.get(region.region_id, [])],
                    "agent_ids": [item.agent_id for item in profiles_by_region.get(region.region_id, [])],
                    "counts": summarize(profiles_by_region.get(region.region_id, [])),
                }
                for region in regions
            },
            "subregions": {
                subregion.region_id: {
                    "subregion_name": subregion.name,
                    "parent_region_id": subregion.parent_region_id,
                    "agent_ids": [item.agent_id for item in profiles_by_subregion.get(subregion.region_id, [])],
                    "counts": summarize(profiles_by_subregion.get(subregion.region_id, [])),
                }
                for subregion in subregions
            },
        }

    def _behavior_bundle(
        self,
        node_family: str,
        agent_subtype: str,
        region_name: str,
        subregion_name: str,
        land_use_class: str,
    ) -> Dict[str, Any]:
        defaults = {
            "goals": [f"稳住 {subregion_name} 的局部秩序", f"降低 {region_name} 的次生损失"],
            "sensitivities": ["风险感知滞后", "跨部门协作失灵"],
            "motivation_stack": ["保全生计", "减少暴露", "维护局部秩序"],
            "capabilities": ["local_observation", "resource_mobilization"],
            "constraints": ["信息不完全", "资源有限"],
            "action_space": ["monitor", "signal", "adapt"],
            "decision_policy": {"activation_threshold": 48, "coordination_bias": 0.5, "ecology_weight": 0.4},
            "impact_profile": {"panic_delta": 1.0, "trust_delta": 0.0, "economic_delta": 0.0, "ecology_delta": 0.0},
            "stance_profile": {"risk_aversion": 0.6, "development_bias": 0.0, "ecology_commitment": 0.4},
            "resource_budget": {"attention": 0.5, "mobility": 0.5, "response": 0.5},
            "spawn_weight": 0.6,
            "bio": f"{subregion_name} 的典型节点，持续感知并响应人与自然互动带来的局部变化。",
            "persona": f"该节点扎根于{subregion_name}，会根据环境暴露、制度信号和周边主体行为调整自身策略。",
        }
        presets = {
            "resident": {
                "action_space": ["observe", "complain", "volunteer_cleanup", "panic_buy"],
                "motivation_stack": ["保护家人", "维持日常生活", "避免健康损失"],
                "impact_profile": {"panic_delta": 2.0, "trust_delta": -1.0, "economic_delta": 0.5, "ecology_delta": 0.2},
            },
            "activist": {
                "action_space": ["sample_collect", "public_campaign", "petition", "volunteer_cleanup"],
                "motivation_stack": ["推动治理", "保护生态", "公开透明"],
                "stance_profile": {"risk_aversion": 0.8, "development_bias": -0.3, "ecology_commitment": 0.95},
                "impact_profile": {"panic_delta": 1.0, "trust_delta": 1.2, "economic_delta": -0.2, "ecology_delta": 1.5},
            },
            "white_collar": {
                "action_space": ["share_update", "remote_work", "market_shift"],
                "motivation_stack": ["保证收入", "降低通勤暴露", "保护资产"],
                "impact_profile": {"panic_delta": 0.8, "trust_delta": -0.4, "economic_delta": 1.0, "ecology_delta": 0.0},
            },
            "worker": {
                "action_space": ["report_hazard", "halt_line", "continue_production"],
                "motivation_stack": ["保住工作", "避免事故", "争取补偿"],
                "impact_profile": {"panic_delta": 1.2, "trust_delta": -0.2, "economic_delta": 1.4, "ecology_delta": -0.6},
            },
            "scientist": {
                "action_space": ["monitor", "publish_assessment", "advise_policy"],
                "motivation_stack": ["证据优先", "解释风险", "促进修复"],
                "stance_profile": {"risk_aversion": 0.7, "development_bias": -0.1, "ecology_commitment": 0.85},
                "impact_profile": {"panic_delta": -0.4, "trust_delta": 1.4, "economic_delta": -0.1, "ecology_delta": 0.9},
            },
            "journalist": {
                "action_space": ["verify", "broadcast", "question_authority"],
                "motivation_stack": ["公开信息", "追踪责任", "扩大影响"],
                "impact_profile": {"panic_delta": 1.6, "trust_delta": 0.3, "economic_delta": 0.0, "ecology_delta": 0.1},
            },
            "community_committee": {
                "action_space": ["coordinate_cleanup", "issue_notice", "resource_queue"],
                "capabilities": ["local_coordination", "resource_dispatch"],
                "impact_profile": {"panic_delta": -0.6, "trust_delta": 1.0, "economic_delta": 0.0, "ecology_delta": 0.8},
            },
            "market_association": {
                "action_space": ["adjust_supply", "price_signal", "public_briefing"],
                "impact_profile": {"panic_delta": 0.6, "trust_delta": 0.2, "economic_delta": 1.4, "ecology_delta": -0.3},
            },
            "plant_operator": {
                "action_space": ["mitigate_emission", "continue_output", "shutdown_line"],
                "motivation_stack": ["控制成本", "保持运转", "规避责任"],
                "stance_profile": {"risk_aversion": 0.45, "development_bias": 0.8, "ecology_commitment": 0.2},
                "impact_profile": {"panic_delta": 0.5, "trust_delta": -0.8, "economic_delta": 1.8, "ecology_delta": -1.6},
            },
            "environment_bureau": {
                "action_space": ["issue_alert", "enforce_restriction", "deploy_remediation"],
                "capabilities": ["enforcement", "monitoring", "public_briefing"],
                "impact_profile": {"panic_delta": -0.8, "trust_delta": 1.2, "economic_delta": -0.6, "ecology_delta": 1.4},
            },
            "emergency_office": {
                "action_space": ["coordinate_response", "evacuate", "stabilize_services"],
                "capabilities": ["response_command", "resource_dispatch"],
                "impact_profile": {"panic_delta": -1.1, "trust_delta": 1.0, "economic_delta": -0.4, "ecology_delta": 0.6},
            },
            "safety_inspector": {
                "action_space": ["inspect", "fine_operator", "halt_line"],
                "capabilities": ["inspection", "compliance_enforcement"],
                "impact_profile": {"panic_delta": -0.2, "trust_delta": 0.7, "economic_delta": -0.8, "ecology_delta": 1.0},
            },
            "conservation_station": {
                "action_space": ["restore_habitat", "restrict_access", "sample_collect"],
                "impact_profile": {"panic_delta": -0.2, "trust_delta": 0.8, "economic_delta": -0.2, "ecology_delta": 1.7},
            },
            "urban_ecology": {
                "action_space": ["stress_signal", "partial_recovery"],
                "motivation_stack": ["维持栖息地", "恢复功能"],
                "impact_profile": {"panic_delta": 0.3, "trust_delta": 0.0, "economic_delta": 0.0, "ecology_delta": 1.2},
            },
            "urban_birds": {
                "action_space": ["migration_shift", "stress_signal"],
                "impact_profile": {"panic_delta": 0.2, "trust_delta": 0.0, "economic_delta": 0.0, "ecology_delta": -0.4},
            },
            "soil_biome": {
                "action_space": ["bioaccumulate", "partial_recovery"],
                "impact_profile": {"panic_delta": 0.0, "trust_delta": 0.0, "economic_delta": -0.1, "ecology_delta": -0.9},
            },
            "habitat_species": {
                "action_space": ["migrate", "breed_decline", "signal_loss"],
                "impact_profile": {"panic_delta": 0.0, "trust_delta": 0.0, "economic_delta": -0.3, "ecology_delta": -1.2},
            },
        }
        merged = dict(defaults)
        merged.update(presets.get(agent_subtype, {}))
        if node_family == "EnvironmentalCarrier":
            merged["stance_profile"] = {"risk_aversion": 0.2, "development_bias": 0.0, "ecology_commitment": 0.8}
            merged["impact_profile"] = {"panic_delta": 0.0, "trust_delta": 0.0, "economic_delta": 0.0, "ecology_delta": -1.0}
            merged["action_space"] = ["transport_pressure", "retain_pollutant", "dilute"]
        if land_use_class == "industrial":
            merged["decision_policy"] = {**merged["decision_policy"], "economic_weight": 0.85, "ecology_weight": 0.25}
        if land_use_class == "ecology":
            merged["decision_policy"] = {**merged["decision_policy"], "economic_weight": 0.1, "ecology_weight": 0.95}
        return merged

    def _build_profile(
        self,
        index: int,
        prepared: PreparedEntityContext,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        scenario_mode: str,
        simulation_requirement: str,
        use_llm: bool,
    ) -> EnvAgentProfile:
        primary_region = self._match_region(prepared, regions)
        primary_subregion = self._match_subregion(prepared, primary_region, subregions)
        state_vector = default_state_vector(scenario_mode, prepared.node_family)
        base_goals = self._default_goals(prepared.node_family, primary_region.name)
        sensitivities = self._default_sensitivities(prepared.node_family, primary_region.name)

        llm_payload = None
        if use_llm and self.llm_client:
            llm_payload = self._generate_profile_with_llm(
                prepared=prepared,
                primary_region=primary_region,
                simulation_requirement=simulation_requirement,
            )

        username = self._username_from_name(prepared.entity.name, index)
        profession = (
            (llm_payload or {}).get("profession")
            or prepared.entity.attributes.get("role")
            or prepared.entity.attributes.get("profession")
            or prepared.entity_type
        )
        bio = (
            (llm_payload or {}).get("bio")
            or f"{prepared.entity.name} is a {prepared.entity_type} rooted in {primary_region.name}."
        )
        persona = (
            (llm_payload or {}).get("persona")
            or f"{prepared.entity.name} tracks local ecological change, social pressure, and risk trade-offs."
        )
        goals = [str(item) for item in ((llm_payload or {}).get("goals") or base_goals)][:6]
        sensitivities = [str(item) for item in ((llm_payload or {}).get("sensitivities") or sensitivities)][:6]
        influenced_regions = [primary_region.region_id] + [
            region.region_id
            for region in regions
            if region.region_id != primary_region.region_id and region.region_id in primary_region.neighbors[:2]
        ]
        agent_type, agent_subtype = self._agent_identity(prepared)
        behavior = self._behavior_bundle(
            node_family=prepared.node_family,
            agent_subtype=agent_subtype,
            region_name=primary_region.name,
            subregion_name=primary_subregion.name,
            land_use_class=primary_subregion.land_use_class or "residential",
        )

        return EnvAgentProfile(
            agent_id=index,
            username=username,
            name=prepared.entity.name,
            node_family=prepared.node_family,
            role_type=prepared.entity_type,
            bio=bio,
            persona=persona,
            profession=str(profession),
            primary_region=primary_region.region_id,
            agent_type=agent_type,
            agent_subtype=agent_subtype,
            archetype_key=f"seed:{agent_subtype}",
            home_region_id=primary_region.region_id,
            home_subregion_id=primary_subregion.region_id,
            influenced_regions=influenced_regions,
            goals=goals,
            sensitivities=sensitivities,
            motivation_stack=behavior["motivation_stack"],
            capabilities=behavior["capabilities"],
            constraints=behavior["constraints"],
            action_space=behavior["action_space"],
            decision_policy=behavior["decision_policy"],
            impact_profile=behavior["impact_profile"],
            stance_profile=behavior["stance_profile"],
            resource_budget=behavior["resource_budget"],
            spawn_weight=behavior["spawn_weight"],
            state_vector=state_vector,
            source_entity_uuid=prepared.entity.uuid,
            source_entity_type=prepared.entity_type,
        )

    def _match_region(self, prepared: PreparedEntityContext, regions: List[RegionNode]) -> RegionNode:
        haystack = f"{prepared.entity.name} {prepared.summary} {json.dumps(prepared.entity.attributes, ensure_ascii=False)}".lower()
        for region in regions:
            if region.name.lower() in haystack or region.region_id.replace("_", " ") in haystack:
                return region
        return regions[0]

    def _match_subregion(
        self,
        prepared: PreparedEntityContext,
        region: RegionNode,
        subregions: List[RegionNode],
    ) -> RegionNode:
        candidates = [item for item in subregions if item.parent_region_id == region.region_id]
        if not candidates:
            return RegionNode(
                region_id=region.region_id,
                name=region.name,
                region_type=region.region_type,
                description=region.description,
                parent_region_id=region.parent_region_id,
                layer=region.layer,
                land_use_class=region.land_use_class or "residential",
                distance_band=region.distance_band or "transition",
                neighbors=list(region.neighbors),
                carriers=list(region.carriers),
                tags=list(region.tags),
                ecology_assets=list(region.ecology_assets),
                industry_tags=list(region.industry_tags),
                region_constraints=list(region.region_constraints),
                exposure_channels=list(region.exposure_channels),
                population_capacity=region.population_capacity,
                state_vector=dict(region.state_vector),
            )

        haystack = f"{prepared.entity_type} {prepared.entity.name} {prepared.summary}".lower()
        preferred_land_use = "residential"
        if prepared.node_family in {"EcologicalReceptor", "EnvironmentalCarrier"}:
            preferred_land_use = "ecology"
        elif prepared.node_family == "GovernmentActor":
            preferred_land_use = "civic"
        elif prepared.node_family == "OrganizationActor":
            preferred_land_use = "commercial"
        elif "worker" in haystack or "factory" in haystack or "industrial" in haystack:
            preferred_land_use = "industrial"
        elif "office" in haystack or "company" in haystack or "commerce" in haystack:
            preferred_land_use = "commercial"

        for subregion in candidates:
            if subregion.land_use_class == preferred_land_use:
                return subregion
        return candidates[0]

    def _agent_identity(self, prepared: PreparedEntityContext) -> Tuple[str, str]:
        haystack = f"{prepared.entity_type} {prepared.entity.name} {prepared.summary}".lower()
        if prepared.node_family == "GovernmentActor":
            if "emergency" in haystack:
                return ("governance", "emergency_office")
            if "environment" in haystack or "ecology" in haystack:
                return ("governance", "environment_bureau")
            return ("governance", "public_agency")
        if prepared.node_family == "OrganizationActor":
            if "media" in haystack or "news" in haystack:
                return ("organization", "media_outlet")
            if "school" in haystack or "lab" in haystack or "research" in haystack:
                return ("organization", "research_lab")
            if "company" in haystack or "enterprise" in haystack or "market" in haystack:
                return ("organization", "market_association")
            return ("organization", "community_committee")
        if prepared.node_family == "EcologicalReceptor":
            if "mangrove" in haystack:
                return ("ecology", "habitat_species")
            if "bird" in haystack or "gull" in haystack:
                return ("ecology", "urban_birds")
            return ("ecology", "urban_ecology")
        if prepared.node_family == "EnvironmentalCarrier":
            return ("carrier", self._default_carriers("generic")[0])
        if "scient" in haystack or "research" in haystack:
            return ("human", "scientist")
        if "journal" in haystack or "media" in haystack or "reporter" in haystack:
            return ("human", "journalist")
        if "worker" in haystack or "factory" in haystack:
            return ("human", "worker")
        if "fisher" in haystack or "farmer" in haystack:
            return ("human", "field_observer")
        if "activist" in haystack or "volunteer" in haystack or "ngo" in haystack:
            return ("human", "activist")
        if "white" in haystack or "office" in haystack or "staff" in haystack:
            return ("human", "white_collar")
        return ("human", "resident")

    def _generate_profile_with_llm(
        self,
        prepared: PreparedEntityContext,
        primary_region: RegionNode,
        simulation_requirement: str,
    ) -> Optional[Dict[str, Any]]:
        prompt = {
            "task": "Create a compact eco-social simulation role profile as JSON.",
            "entity_name": prepared.entity.name,
            "entity_type": prepared.entity_type,
            "node_family": prepared.node_family,
            "summary": prepared.summary,
            "attributes": prepared.entity.attributes,
            "relation_hints": prepared.relation_hints,
            "primary_region": primary_region.to_dict(),
            "requirement": simulation_requirement[:800],
            "schema": {
                "profession": "short string",
                "bio": "1-2 sentences",
                "persona": "2-3 sentences in third person",
                "goals": ["goal 1", "goal 2"],
                "sensitivities": ["sensitivity 1", "sensitivity 2"],
            },
        }
        try:
            return self.llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "Return only valid JSON. Keep descriptions grounded and concise.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.3,
                max_tokens=900,
            )
        except Exception as exc:
            logger.debug(f"Profile LLM generation failed for {prepared.entity.name}: {exc}")
            return None

    def _default_goals(self, node_family: str, region_name: str) -> List[str]:
        defaults = {
            "EnvironmentalCarrier": [f"propagate changes across {region_name}", "reflect current transport conditions"],
            "EcologicalReceptor": [f"maintain habitat quality in {region_name}", "avoid prolonged exposure"],
            "GovernmentActor": [f"stabilize {region_name}", "coordinate response legitimacy"],
            "OrganizationActor": [f"protect operations in {region_name}", "manage reputational risk"],
            "Infrastructure": [f"keep services operating in {region_name}", "reduce disruption spillover"],
        }
        return defaults.get(node_family, [f"protect interests in {region_name}", "adapt to changing environmental conditions"])

    def _default_sensitivities(self, node_family: str, region_name: str) -> List[str]:
        defaults = {
            "EnvironmentalCarrier": ["upstream/downstream pressure", "weather and current shifts"],
            "EcologicalReceptor": ["toxicity persistence", "habitat fragmentation"],
            "GovernmentActor": ["trust collapse", "resource constraints"],
            "OrganizationActor": ["consumer sentiment", "supply chain interruption"],
            "Infrastructure": ["service overload", "contamination shutdowns"],
        }
        return defaults.get(node_family, [f"rapid sentiment change in {region_name}", "policy uncertainty"])

    def _username_from_name(self, name: str, index: int) -> str:
        normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
        normalized = "_".join(part for part in normalized.split("_") if part) or "agent"
        return f"{normalized[:20]}_{index}"
