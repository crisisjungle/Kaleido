"""
EnvFish actor and region generation from Zep entities.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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
    normalize_transport_family,
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


HUMAN_ACTIVITY_SUBTYPES = {
    "residential",
    "commercial",
    "commercial_hub",
    "office_cluster",
    "hospital",
    "school",
    "university",
    "tourism",
    "shop",
    "worldcover_50",
}

TRANSPORT_SUBTYPES = {
    "road_corridor",
    "transit_stop",
    "rail_station",
    "pier",
    "marina",
    "ferry_terminal",
    "breakwater",
    "groyne",
}

INDUSTRY_SUBTYPES = {
    "industrial",
    "wastewater_plant",
    "power_plant",
    "warehouse",
}

WATER_SUBTYPES = {
    "worldcover_80",
    "water",
    "river",
    "stream",
    "canal",
    "ditch",
    "reservoir",
    "basin",
    "coastline",
    "beach",
}

ECOLOGY_SUBTYPES = {
    "worldcover_10",
    "worldcover_90",
    "worldcover_95",
    "forest",
    "wetland",
    "nature_reserve",
    "protected_area",
    "park",
    "garden",
}

AGRICULTURE_SUBTYPES = {"worldcover_40", "farmland", "farmyard"}
OPEN_SUBTYPES = {"worldcover_20", "worldcover_30", "worldcover_60", "meadow"}


@dataclass
class MapEvidenceContext:
    human_activity_score: float
    industry_score: float
    transport_score: float
    ecology_score: float
    water_score: float
    agriculture_score: float
    open_score: float
    evidence_level: str
    environment_archetype: str
    target_count_range: Tuple[int, int]
    target_agent_count: int
    allowed_roles: List[str] = field(default_factory=list)
    forbidden_roles: List[str] = field(default_factory=list)
    evidence_refs_by_role: Dict[str, List[str]] = field(default_factory=dict)
    feature_subtype_counts: Dict[str, int] = field(default_factory=dict)
    source_kind_counts: Dict[str, int] = field(default_factory=dict)
    dominant_subtypes: List[str] = field(default_factory=list)
    admin_context: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "human_activity_score": round(self.human_activity_score, 3),
            "industry_score": round(self.industry_score, 3),
            "transport_score": round(self.transport_score, 3),
            "ecology_score": round(self.ecology_score, 3),
            "water_score": round(self.water_score, 3),
            "agriculture_score": round(self.agriculture_score, 3),
            "open_score": round(self.open_score, 3),
            "evidence_level": self.evidence_level,
            "environment_archetype": self.environment_archetype,
            "target_count_range": list(self.target_count_range),
            "target_agent_count": self.target_agent_count,
            "allowed_roles": list(self.allowed_roles),
            "forbidden_roles": list(self.forbidden_roles),
            "evidence_refs_by_role": {key: list(value) for key, value in self.evidence_refs_by_role.items()},
            "feature_subtype_counts": dict(self.feature_subtype_counts),
            "source_kind_counts": dict(self.source_kind_counts),
            "dominant_subtypes": list(self.dominant_subtypes),
            "admin_context": dict(self.admin_context),
            "warnings": list(self.warnings),
        }


@dataclass
class AgentCandidatePlan:
    candidate_id: str
    role_name: str
    node_family: str
    agent_type: str
    agent_subtype: str
    role_type: str
    home_region_id: str
    home_subregion_id: str
    evidence_refs: List[str]
    confidence: float
    why_this_agent: str
    action_space_hint: List[str] = field(default_factory=list)
    generation_mode: str = "map_rule"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "role_name": self.role_name,
            "node_family": self.node_family,
            "agent_type": self.agent_type,
            "agent_subtype": self.agent_subtype,
            "role_type": self.role_type,
            "home_region_id": self.home_region_id,
            "home_subregion_id": self.home_subregion_id,
            "evidence_refs": list(dict.fromkeys(self.evidence_refs)),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 3),
            "why_this_agent": self.why_this_agent,
            "action_space_hint": list(dict.fromkeys(self.action_space_hint)),
            "generation_mode": self.generation_mode,
        }


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
        search_mode: str = "fast",
        reference_time: str = "",
        diffusion_provider: str = "auto",
        injected_variables: Optional[List[InjectedVariable]] = None,
        use_llm: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        profile_created_callback: Optional[Callable[[EnvAgentProfile, int, int, str], None]] = None,
        parallel_count: int = 3,
    ) -> EnvProfileGenerationResult:
        injected_variables = injected_variables or []
        prepared_entities = [self._prepare_entity(entity) for entity in entities]
        is_map_seed = self._looks_like_map_seed_context(prepared_entities)
        regions = self._build_regions(
            prepared_entities=prepared_entities,
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
            search_mode=search_mode,
            injected_variables=injected_variables,
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

        map_evidence_context = (
            self._build_map_evidence_context(
                prepared_entities=prepared_entities,
                regions=regions,
                subregions=subregions,
                diffusion_template=diffusion_template,
                search_mode=search_mode,
            )
            if is_map_seed
            else None
        )
        anchor_profiles: List[EnvAgentProfile] = []
        synthesized_profiles: List[EnvAgentProfile] = []
        map_generation_summary: Dict[str, Any] = {}
        total = len(prepared_entities)
        target_count = self._target_agent_count(
            prepared_entities=prepared_entities,
            regions=regions,
            subregions=subregions,
            map_evidence_context=map_evidence_context,
        )
        generated_count = 0

        def emit_profile(profile: EnvAgentProfile, stage: str) -> None:
            nonlocal generated_count
            generated_count += 1
            if profile_created_callback:
                profile_created_callback(profile, generated_count, target_count, stage)

        if progress_callback:
            progress_callback(0, max(total, 1), "开始生成 EnvFish 基础角色")

        if map_evidence_context is not None:
            profiles, synthesized_profiles, map_generation_summary = self._generate_map_seed_agent_profiles(
                prepared_entities=prepared_entities,
                regions=regions,
                subregions=subregions,
                scenario_mode=scenario_mode,
                diffusion_template=diffusion_template,
                simulation_requirement=simulation_requirement,
                evidence_context=map_evidence_context,
                target_count=target_count,
                injected_variables=injected_variables,
                use_llm=use_llm,
                profile_created_callback=lambda profile: emit_profile(profile, "map_evidence"),
            )
        else:
            def build_profile(args: Tuple[int, PreparedEntityContext]) -> EnvAgentProfile:
                index, prepared = args
                return self._build_profile(
                    index=index,
                    prepared=prepared,
                    regions=regions,
                    subregions=subregions,
                    scenario_mode=scenario_mode,
                    simulation_requirement=simulation_requirement,
                    injected_variables=injected_variables,
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
            f"Agent generation mode: {'map_evidence_driven' if map_evidence_context else 'entity_template'}.",
            f"Diffusion template: {diffusion_template}",
            f"Scenario mode: {scenario_mode}",
            f"Transport edges: {len(transport_edges)} via {diffusion_context.get('provider') or 'heuristic'}",
        ]
        if injected_variables:
            notes.append(f"Injected variables available during region/agent generation: {', '.join(item.name for item in injected_variables[:4])}")
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
                "generation_mode": "map_evidence_driven" if map_evidence_context else "entity_template",
                **map_generation_summary,
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
        search_mode: str,
        injected_variables: Optional[List[InjectedVariable]] = None,
    ) -> List[RegionNode]:
        diffusion_template = normalize_transport_family(diffusion_template)
        if diffusion_template not in DIFFUSION_TEMPLATES:
            diffusion_template = "generic"

        if self._looks_like_map_seed_context(prepared_entities):
            map_seed_regions = self._build_regions_from_map_seed(
                prepared_entities=prepared_entities,
                scenario_mode=scenario_mode,
                diffusion_template=diffusion_template,
                search_mode=search_mode,
            )
            if map_seed_regions:
                return map_seed_regions

        region_candidates = self._region_candidates_from_entities(prepared_entities)
        llm_regions = self._build_regions_with_llm(
            region_candidates=region_candidates,
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
            max_regions=self._region_cap_for_search_mode(search_mode),
            injected_variables=injected_variables or [],
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

    def _region_cap_for_search_mode(self, search_mode: str) -> int:
        normalized = str(search_mode or "fast").strip().lower().replace("-", "_")
        return 16 if normalized == "deep_search" else 8

    def _looks_like_map_seed_context(self, prepared_entities: List[PreparedEntityContext]) -> bool:
        has_seed_root = False
        physical_count = 0
        for prepared in prepared_entities:
            attrs = prepared.entity.attributes or {}
            if prepared.node_family == "Region" and isinstance(attrs.get("admin_context"), dict):
                has_seed_root = True
                continue
            if self._coerce_float(attrs.get("lat")) is None or self._coerce_float(attrs.get("lon")) is None:
                continue
            if str(attrs.get("source_kind") or "").lower() in {"observed", "detected"}:
                physical_count += 1
        return has_seed_root and physical_count >= 3

    def _build_regions_from_map_seed(
        self,
        prepared_entities: List[PreparedEntityContext],
        scenario_mode: str,
        diffusion_template: str,
        search_mode: str,
    ) -> List[RegionNode]:
        root = next(
            (
                prepared
                for prepared in prepared_entities
                if prepared.node_family == "Region"
                and isinstance((prepared.entity.attributes or {}).get("admin_context"), dict)
            ),
            None,
        )
        if root is None:
            return []

        root_attrs = root.entity.attributes or {}
        admin_context = root_attrs.get("admin_context") or {}
        center_lat = self._coerce_float(root_attrs.get("lat")) or self._coerce_float(admin_context.get("lat"))
        center_lon = self._coerce_float(root_attrs.get("lon")) or self._coerce_float(admin_context.get("lon"))
        if center_lat is None or center_lon is None:
            return []
        radius_m = max(1500, int(root_attrs.get("radius_m") or 12000))
        max_regions = self._region_cap_for_search_mode(search_mode)

        weighted_features: List[Dict[str, Any]] = []
        class_totals: Dict[str, float] = defaultdict(float)
        for prepared in prepared_entities:
            attrs = prepared.entity.attributes or {}
            if prepared is root:
                continue
            lat = self._coerce_float(attrs.get("lat"))
            lon = self._coerce_float(attrs.get("lon"))
            if lat is None or lon is None:
                continue
            source_kind = str(attrs.get("source_kind") or "").lower()
            if source_kind not in {"observed", "detected"}:
                continue
            class_info = self._classify_map_seed_feature(prepared)
            if not class_info:
                continue
            weight = self._map_seed_feature_weight(
                prepared=prepared,
                macro_class=class_info["macro_class"],
                radius_m=radius_m,
            )
            feature_payload = {
                "prepared": prepared,
                "attrs": attrs,
                "lat": lat,
                "lon": lon,
                "weight": weight,
                "macro_class": class_info["macro_class"],
                "label": class_info["label"],
                "region_type": class_info["region_type"],
                "carriers": class_info["carriers"],
                "evidence_tags": class_info["evidence_tags"],
            }
            weighted_features.append(feature_payload)
            class_totals[class_info["macro_class"]] += weight

        if not weighted_features:
            return []

        weighted_features.sort(key=lambda item: item["weight"], reverse=True)
        clusters: List[Dict[str, Any]] = []
        for feature in weighted_features:
            threshold_m = max(
                1800.0,
                radius_m
                * (
                    0.16
                    if feature["macro_class"] in {"transport", "industrial"}
                    else 0.24
                ),
            )
            target_cluster = None
            for cluster in clusters:
                if cluster["macro_class"] != feature["macro_class"]:
                    continue
                distance = self._haversine_m(
                    feature["lat"],
                    feature["lon"],
                    cluster["lat"],
                    cluster["lon"],
                )
                if distance <= threshold_m:
                    target_cluster = cluster
                    break
            if target_cluster is None:
                clusters.append(
                    {
                        "macro_class": feature["macro_class"],
                        "label": feature["label"],
                        "region_type": feature["region_type"],
                        "lat": feature["lat"],
                        "lon": feature["lon"],
                        "weight_sum": feature["weight"],
                        "features": [feature],
                        "carriers": set(feature["carriers"]),
                        "evidence_tags": set(feature["evidence_tags"]),
                    }
                )
                continue

            total_weight = target_cluster["weight_sum"] + feature["weight"]
            target_cluster["lat"] = round(
                (
                    target_cluster["lat"] * target_cluster["weight_sum"]
                    + feature["lat"] * feature["weight"]
                )
                / max(total_weight, 1e-6),
                6,
            )
            target_cluster["lon"] = round(
                (
                    target_cluster["lon"] * target_cluster["weight_sum"]
                    + feature["lon"] * feature["weight"]
                )
                / max(total_weight, 1e-6),
                6,
            )
            target_cluster["weight_sum"] = total_weight
            target_cluster["features"].append(feature)
            target_cluster["carriers"].update(feature["carriers"])
            target_cluster["evidence_tags"].update(feature["evidence_tags"])

        clusters.sort(key=lambda item: item["weight_sum"], reverse=True)
        selected_clusters: List[Dict[str, Any]] = []
        selected_keys: set[int] = set()
        selected_classes: set[str] = set()

        for index, cluster in enumerate(clusters):
            if cluster["macro_class"] in selected_classes:
                continue
            selected_clusters.append(cluster)
            selected_keys.add(index)
            selected_classes.add(cluster["macro_class"])
            if len(selected_clusters) >= max_regions:
                break

        for index, cluster in enumerate(clusters):
            if len(selected_clusters) >= max_regions:
                break
            if index in selected_keys:
                continue
            selected_clusters.append(cluster)

        water_share = 0.0
        for feature in weighted_features:
            if feature["macro_class"] != "water":
                continue
            share = self._coerce_float((feature["attrs"].get("tags") or {}).get("pixel_share_pct")) or 0.0
            water_share = max(water_share, share)

        used: set[str] = set()
        regions: List[RegionNode] = []
        for cluster in selected_clusters[:max_regions]:
            state_vector = default_state_vector(scenario_mode, "Region")
            state_vector = self._adjust_state_vector_for_macro_class(
                state_vector=state_vector,
                macro_class=cluster["macro_class"],
            )
            name = self._name_map_seed_region(
                cluster=cluster,
                admin_context=admin_context,
                center_lat=center_lat,
                center_lon=center_lon,
                radius_m=radius_m,
                water_share=water_share,
            )
            region_id = ensure_unique_slug(name, used)
            regions.append(
                RegionNode(
                    region_id=region_id,
                    name=name,
                    region_type=cluster["region_type"],
                    description=self._describe_map_seed_region(
                        cluster=cluster,
                        admin_context=admin_context,
                    ),
                    layer="macro",
                    land_use_class=self._macro_land_use_class(cluster["macro_class"]),
                    carriers=sorted(cluster["carriers"]),
                    tags=self._map_seed_region_tags(cluster, center_lat, center_lon, radius_m),
                    ecology_assets=self._macro_ecology_assets(cluster),
                    industry_tags=self._macro_industry_tags(cluster),
                    region_constraints=self._macro_region_constraints(cluster["macro_class"]),
                    exposure_channels=self._macro_exposure_channels(cluster["macro_class"], cluster["carriers"]),
                    population_capacity=self._macro_population_capacity(cluster["macro_class"]),
                    lat=cluster["lat"],
                    lon=cluster["lon"],
                    state_vector=normalize_state_vector(state_vector),
                )
            )

        self._connect_regions_by_proximity(regions)
        return regions

    def _classify_map_seed_feature(self, prepared: PreparedEntityContext) -> Optional[Dict[str, Any]]:
        attrs = prepared.entity.attributes or {}
        subtype = str(attrs.get("subtype") or "").lower()
        name = prepared.entity.name.lower()
        if subtype in {"", "weather_baseline"}:
            return None

        if subtype in {"road_corridor", "transit_stop", "rail_station", "pier", "marina", "ferry_terminal"} or any(
            token in name for token in ("桥", "bridge", "corridor", "terminal")
        ):
            return {
                "macro_class": "transport",
                "label": "交通走廊",
                "region_type": "infrastructure_corridor",
                "carriers": ["transport_flow"],
                "evidence_tags": [subtype or "transport"],
            }

        if subtype in {"industrial", "wastewater_plant", "power_plant", "warehouse"}:
            return {
                "macro_class": "industrial",
                "label": "工业设施带",
                "region_type": "industrial_zone",
                "carriers": ["surface_contact", "waste_stream"],
                "evidence_tags": [subtype],
            }

        if subtype in {
            "worldcover_80",
            "water",
            "river",
            "stream",
            "canal",
            "reservoir",
            "basin",
            "coastline",
            "beach",
            "breakwater",
            "groyne",
        }:
            return {
                "macro_class": "water",
                "label": "近岸水域",
                "region_type": "coastal_zone",
                "carriers": ["water_flow"],
                "evidence_tags": [subtype],
            }

        if subtype in {
            "worldcover_10",
            "worldcover_90",
            "worldcover_95",
            "forest",
            "wetland",
            "nature_reserve",
            "protected_area",
            "park",
            "garden",
        }:
            label = "树木覆盖带" if subtype == "worldcover_10" else "生态斑块"
            if subtype in {"worldcover_90", "worldcover_95", "wetland"}:
                label = "湿地生态带"
            return {
                "macro_class": "ecology",
                "label": label,
                "region_type": "ecology_zone",
                "carriers": ["ecology_feedback"],
                "evidence_tags": [subtype],
            }

        if subtype in {
            "worldcover_50",
            "residential",
            "commercial",
            "commercial_hub",
            "office_cluster",
            "hospital",
            "school",
            "university",
        }:
            return {
                "macro_class": "urban",
                "label": "建成片区",
                "region_type": "urban_zone",
                "carriers": ["daily_contact", "service_flow"],
                "evidence_tags": [subtype],
            }

        if subtype in {"worldcover_20", "worldcover_30", "worldcover_40", "worldcover_60", "farmland", "farmyard", "meadow"}:
            label = "草地开放区"
            if subtype in {"worldcover_40", "farmland", "farmyard"}:
                label = "农地开放区"
            if subtype == "worldcover_60":
                label = "裸地稀疏地表"
            return {
                "macro_class": "open",
                "label": label,
                "region_type": "open_space_zone",
                "carriers": ["surface_runoff"],
                "evidence_tags": [subtype],
            }

        return None

    def _map_seed_feature_weight(
        self,
        prepared: PreparedEntityContext,
        macro_class: str,
        radius_m: int,
    ) -> float:
        attrs = prepared.entity.attributes or {}
        share = self._coerce_float((attrs.get("tags") or {}).get("pixel_share_pct")) or 0.0
        importance = float(attrs.get("importance") or 4)
        distance_m = self._coerce_float(attrs.get("distance_m")) or 0.0
        distance_factor = max(0.2, 1.0 - distance_m / max(float(radius_m), 1.0))
        weight = importance + share * 0.85 + distance_factor * 4.0
        if str(attrs.get("source_kind") or "").lower() == "observed":
            weight += 1.2
        if macro_class == "transport" and distance_m <= radius_m * 0.18:
            weight += 3.0
        if macro_class == "water" and share >= 20:
            weight += 2.0
        return round(weight, 3)

    def _adjust_state_vector_for_macro_class(
        self,
        state_vector: Dict[str, float],
        macro_class: str,
    ) -> Dict[str, float]:
        if macro_class == "water":
            state_vector["spread_pressure"] += 10
            state_vector["ecosystem_integrity"] += 4
            state_vector["vulnerability_score"] += 4
        elif macro_class == "transport":
            state_vector["service_capacity"] += 8
            state_vector["exposure_score"] += 8
            state_vector["economic_stress"] += 6
        elif macro_class == "industrial":
            state_vector["economic_stress"] += 12
            state_vector["ecosystem_integrity"] -= 8
            state_vector["vulnerability_score"] += 8
        elif macro_class == "ecology":
            state_vector["ecosystem_integrity"] += 10
            state_vector["livelihood_stability"] -= 2
            state_vector["vulnerability_score"] += 6
        elif macro_class == "urban":
            state_vector["service_capacity"] += 6
            state_vector["public_trust"] -= 2
            state_vector["vulnerability_score"] += 4
        elif macro_class == "open":
            state_vector["ecosystem_integrity"] += 2
            state_vector["livelihood_stability"] -= 2
        return state_vector

    def _name_map_seed_region(
        self,
        cluster: Dict[str, Any],
        admin_context: Dict[str, Any],
        center_lat: float,
        center_lon: float,
        radius_m: int,
        water_share: float,
    ) -> str:
        road = str(admin_context.get("road") or "").strip()
        city = str(admin_context.get("city") or "").strip()
        macro_class = cluster["macro_class"]
        orientation = self._orientation_label(cluster["lat"], cluster["lon"], center_lat, center_lon, radius_m)
        label = cluster["label"]
        center_distance = self._haversine_m(cluster["lat"], cluster["lon"], center_lat, center_lon)

        if macro_class == "transport" and road:
            return f"{road}{label}"
        if macro_class == "water" and road and ("桥" in road or "bridge" in road.lower()) and center_distance <= radius_m * 0.2:
            return f"{road}桥区水域"
        if city and macro_class in {"urban", "industrial"} and center_distance <= radius_m * 0.18 and water_share < 45:
            return f"{city}{label}"
        if orientation:
            return f"{orientation}{label}"
        if city:
            return f"{city}{label}"
        return label

    def _describe_map_seed_region(
        self,
        cluster: Dict[str, Any],
        admin_context: Dict[str, Any],
    ) -> str:
        features = sorted(cluster["features"], key=lambda item: item["weight"], reverse=True)
        lead = features[0]
        lead_name = lead["prepared"].entity.name
        subtype_labels = [item["prepared"].entity.name for item in features[1:3]]
        tags = lead["attrs"].get("tags") or {}
        share = self._coerce_float(tags.get("pixel_share_pct"))
        area_label = admin_context.get("display_name") or admin_context.get("city") or "当前 AOI"
        summary = f"由 {lead_name}"
        if subtype_labels:
            summary += f"、{'、'.join(subtype_labels)}"
        summary += f" 等 {len(features)} 个空间要素归并出的{cluster['label']}。"
        if share:
            summary += f" 其中主导斑块约占分析像元的 {round(share, 1)}%。"
        summary += f" 用于表达 {area_label} 内更接近真实空间结构的主导分区。"
        return summary

    def _macro_land_use_class(self, macro_class: str) -> str:
        return {
            "water": "water",
            "transport": "transport",
            "industrial": "industrial",
            "ecology": "ecology",
            "urban": "urban",
            "open": "open",
        }.get(macro_class, "urban")

    def _map_seed_region_tags(
        self,
        cluster: Dict[str, Any],
        center_lat: float,
        center_lon: float,
        radius_m: int,
    ) -> List[str]:
        tags = {
            "map_seed_physical",
            cluster["macro_class"],
            self._orientation_label(cluster["lat"], cluster["lon"], center_lat, center_lon, radius_m) or "center",
        }
        tags.update(cluster["evidence_tags"])
        return sorted(tag for tag in tags if tag)

    def _macro_ecology_assets(self, cluster: Dict[str, Any]) -> List[str]:
        macro_class = cluster["macro_class"]
        if macro_class == "water":
            return ["nearshore_habitat", "water_column"]
        if macro_class == "ecology":
            return ["habitat_patch", "indicator_species"]
        if macro_class == "open":
            return ["open_ground", "edge_species"]
        return []

    def _macro_industry_tags(self, cluster: Dict[str, Any]) -> List[str]:
        macro_class = cluster["macro_class"]
        if macro_class == "transport":
            return ["transport", "logistics"]
        if macro_class == "industrial":
            return ["industrial_operations", "compliance"]
        if macro_class == "urban":
            return ["mixed_use", "services"]
        return []

    def _macro_region_constraints(self, macro_class: str) -> List[str]:
        return {
            "water": ["跨域流动", "边界模糊"],
            "transport": ["线性扩散", "中断敏感"],
            "industrial": ["停摆成本高", "合规压力"],
            "ecology": ["恢复缓慢", "阈值脆弱"],
            "urban": ["人口活动密集", "服务耦合高"],
            "open": ["用途混杂", "边缘效应明显"],
        }.get(macro_class, ["空间异质性"])

    def _macro_exposure_channels(self, macro_class: str, carriers: set[str]) -> List[str]:
        base = {
            "water": ["water_flow", "shore_contact"],
            "transport": ["traffic_flow", "surface_contact"],
            "industrial": ["waste_stream", "surface_contact"],
            "ecology": ["habitat_disturbance"],
            "urban": ["daily_contact", "service_flow"],
            "open": ["surface_runoff", "wind_rework"],
        }.get(macro_class, ["environmental_link"])
        return sorted(set([*base, *list(carriers)]))

    def _macro_population_capacity(self, macro_class: str) -> int:
        return {
            "water": 10,
            "transport": 12,
            "industrial": 14,
            "ecology": 8,
            "urban": 18,
            "open": 6,
        }.get(macro_class, 10)

    def _orientation_label(
        self,
        lat: float,
        lon: float,
        center_lat: float,
        center_lon: float,
        radius_m: int,
    ) -> str:
        distance = self._haversine_m(lat, lon, center_lat, center_lon)
        if distance <= max(1200.0, radius_m * 0.12):
            return "中心"
        dx = (lon - center_lon) * math.cos(math.radians(center_lat))
        dy = lat - center_lat
        if abs(dx) > abs(dy) * 1.4:
            return "东侧" if dx > 0 else "西侧"
        if abs(dy) > abs(dx) * 1.4:
            return "北侧" if dy > 0 else "南侧"
        if dx >= 0 and dy >= 0:
            return "东北侧"
        if dx >= 0 and dy < 0:
            return "东南侧"
        if dx < 0 and dy >= 0:
            return "西北侧"
        return "西南侧"

    def _connect_regions_by_proximity(self, regions: List[RegionNode]) -> None:
        if len(regions) <= 1:
            return
        for region in regions:
            candidates: List[tuple[float, str]] = []
            for other in regions:
                if other.region_id == region.region_id:
                    continue
                if None in {region.lat, region.lon, other.lat, other.lon}:
                    continue
                candidates.append(
                    (
                        self._haversine_m(float(region.lat), float(region.lon), float(other.lat), float(other.lon)),
                        other.region_id,
                    )
                )
            for _, neighbor_id in sorted(candidates, key=lambda item: item[0])[:2]:
                region.neighbors.append(neighbor_id)

        transport_regions = [region for region in regions if region.region_type == "infrastructure_corridor"]
        for region in transport_regions:
            candidates: List[tuple[float, str]] = []
            for other in regions:
                if other.region_id == region.region_id:
                    continue
                if None in {region.lat, region.lon, other.lat, other.lon}:
                    continue
                candidates.append(
                    (
                        self._haversine_m(float(region.lat), float(region.lon), float(other.lat), float(other.lon)),
                        other.region_id,
                    )
                )
            for _, neighbor_id in sorted(candidates, key=lambda item: item[0])[:3]:
                region.neighbors.append(neighbor_id)

        for region in regions:
            region.neighbors = list(dict.fromkeys(neighbor for neighbor in region.neighbors if neighbor != region.region_id))
        region_lookup = {region.region_id: region for region in regions}
        for region in regions:
            for neighbor_id in list(region.neighbors):
                neighbor = region_lookup.get(neighbor_id)
                if neighbor and region.region_id not in neighbor.neighbors:
                    neighbor.neighbors.append(region.region_id)
        self._ensure_region_connectivity(regions, "generic")

    def _haversine_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1 - a)))

    def _build_regions_with_llm(
        self,
        region_candidates: List[Dict[str, Any]],
        simulation_requirement: str,
        document_text: str,
        scenario_mode: str,
        diffusion_template: str,
        max_regions: int,
        injected_variables: List[InjectedVariable],
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
            "injected_variables": self._summarize_injected_variables(injected_variables),
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
                f"Return 3-{max_regions} regions whenever information allows, otherwise return at least one.",
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
        for item in raw_regions[:max_regions]:
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
        diffusion_template = normalize_transport_family(diffusion_template)
        if diffusion_template in {"air", "atmospheric_plume", "ash_plume"}:
            return ["air_mass"]
        if diffusion_template in {"inland_water", "inland_water_network", "surface_flood_flow"}:
            return ["river_segment"]
        if diffusion_template in {"marine", "marine_current", "coastal_inundation"}:
            return ["coastal_current"]
        if diffusion_template in {"ecological_mobility", "bio_ecological_transmission"}:
            return ["habitat_corridor"]
        if diffusion_template == "infrastructure_failure":
            return ["infrastructure_corridor"]
        if diffusion_template == "impact_blast":
            return ["impact_wave"]
        if diffusion_template == "slow_ecosystem_decline":
            return ["ecological_stress_gradient"]
        if diffusion_template == "terrestrial_surface":
            return ["surface_runoff"]
        return ["environmental_link"]

    def _build_transport_edges(
        self,
        regions: List[RegionNode],
        diffusion_template: str,
        diffusion_context: Dict[str, Any],
    ) -> List[TransportEdge]:
        diffusion_template = normalize_transport_family(diffusion_template)
        if len(regions) <= 1:
            return []
        if diffusion_template in {"inland_water", "inland_water_network", "surface_flood_flow"}:
            return self._build_inland_water_transport_edges(regions)
        if diffusion_template in {"air", "atmospheric_plume", "ash_plume"}:
            return self._build_projected_transport_edges(
                regions=regions,
                flow_direction_deg=diffusion_context.get("flow_direction_deg"),
                channel_type="ash_plume" if diffusion_template == "ash_plume" else "air_corridor",
                attenuation_rate=0.22 if diffusion_template == "ash_plume" else 0.18,
                travel_time_rounds=1,
                retention_factor=0.1 if diffusion_template == "ash_plume" else 0.06,
                directionality="directed",
                evidence={"transport_context": diffusion_context},
                rationale="Atmospheric transport follows dominant wind-driven downwind ordering.",
            )
        if diffusion_template in {"marine", "marine_current", "coastal_inundation"}:
            return self._build_projected_transport_edges(
                regions=regions,
                flow_direction_deg=diffusion_context.get("flow_direction_deg"),
                channel_type="storm_surge_front" if diffusion_template == "coastal_inundation" else "coastal_current",
                attenuation_rate=0.08 if diffusion_template == "coastal_inundation" else 0.1,
                travel_time_rounds=1 if diffusion_template == "coastal_inundation" else 2,
                retention_factor=0.28 if diffusion_template == "coastal_inundation" else 0.42,
                directionality="directed" if diffusion_template == "coastal_inundation" else "asymmetric",
                evidence={"transport_context": diffusion_context},
                rationale="Marine transport follows coastal-current ordering with stronger retention in enclosed zones.",
            )
        if diffusion_template == "ecological_mobility":
            return self._build_neighbor_transport_edges(regions, channel_type="habitat_corridor")
        if diffusion_template == "bio_ecological_transmission":
            return self._build_neighbor_transport_edges(regions, channel_type="bio_vector")
        if diffusion_template == "infrastructure_failure":
            return self._build_neighbor_transport_edges(regions, channel_type="infrastructure_corridor")
        if diffusion_template == "impact_blast":
            return self._build_neighbor_transport_edges(regions, channel_type="impact_wave")
        if diffusion_template == "slow_ecosystem_decline":
            return self._build_neighbor_transport_edges(regions, channel_type="ecological_stress_gradient")
        if diffusion_template == "terrestrial_surface":
            return self._build_neighbor_transport_edges(regions, channel_type="surface_runoff")
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
        map_evidence_context: Optional[MapEvidenceContext] = None,
    ) -> int:
        if map_evidence_context is not None:
            return map_evidence_context.target_agent_count
        base = len(prepared_entities)
        layered = max(len(subregions) * 4, len(regions) * 12)
        return min(180, max(84, base + layered))

    def _build_map_evidence_context(
        self,
        prepared_entities: List[PreparedEntityContext],
        regions: List[RegionNode],
        subregions: List[RegionNode],
        diffusion_template: str,
        search_mode: str,
    ) -> MapEvidenceContext:
        del search_mode
        score = defaultdict(float)
        subtype_counts: Dict[str, int] = defaultdict(int)
        source_counts: Dict[str, int] = defaultdict(int)
        refs: Dict[str, List[str]] = defaultdict(list)
        admin_context: Dict[str, Any] = {}
        observed_human_subtypes: set[str] = set()
        warnings: List[str] = []

        def add_ref(bucket: str, ref: str) -> None:
            if ref and ref not in refs[bucket]:
                refs[bucket].append(ref)

        for prepared in prepared_entities:
            attrs = prepared.entity.attributes or {}
            ref = prepared.entity.uuid or prepared.entity.name
            if isinstance(attrs.get("admin_context"), dict):
                admin_context = dict(attrs.get("admin_context") or {})
                add_ref("governance", ref)
                add_ref("admin", ref)

            subtype = str(attrs.get("subtype") or "").strip().lower()
            source_kind = str(attrs.get("source_kind") or "").strip().lower()
            proxy_role = str(attrs.get("proxy_role") or "").strip().lower()
            if source_kind:
                source_counts[source_kind] += 1
            if subtype:
                subtype_counts[subtype] += 1

            weight = self._map_feature_weight_for_evidence(prepared)
            if subtype in HUMAN_ACTIVITY_SUBTYPES:
                score["human_activity"] += weight
                observed_human_subtypes.add(subtype)
                add_ref("human_activity", ref)
            if subtype in INDUSTRY_SUBTYPES:
                score["industry"] += weight
                add_ref("industry", ref)
            if subtype in TRANSPORT_SUBTYPES:
                score["transport"] += weight
                add_ref("transport", ref)
                if subtype in {"pier", "marina", "ferry_terminal"}:
                    add_ref("coastal_work", ref)
            if subtype in WATER_SUBTYPES:
                score["water"] += weight
                add_ref("water", ref)
            if subtype in ECOLOGY_SUBTYPES:
                score["ecology"] += weight
                add_ref("ecology", ref)
            if subtype in AGRICULTURE_SUBTYPES:
                score["agriculture"] += weight
                add_ref("agriculture", ref)
            if subtype in OPEN_SUBTYPES:
                score["open"] += weight
                add_ref("open", ref)
            if subtype == "weather_baseline":
                add_ref("weather", ref)
                add_ref("governance", ref)

            # Inferred proxy nodes should not create human activity by themselves.
            if proxy_role in {"residents", "operators", "visitors"} and observed_human_subtypes:
                score["human_activity"] += weight * 0.45
                add_ref("human_activity", ref)
            elif proxy_role in {"regulators", "maintainers"}:
                add_ref("governance", ref)
            elif proxy_role == "vulnerable_groups" and observed_human_subtypes:
                add_ref("human_activity", ref)

        for region in regions:
            if region.region_id:
                add_ref(region.land_use_class or region.region_type or "region", f"region::{region.region_id}")
            for tag in region.tags or []:
                normalized = str(tag).lower()
                if normalized in {"water", "ecology", "transport", "industrial", "urban", "open"}:
                    add_ref(normalized, f"region::{region.region_id}")

        evidence_level = self._map_evidence_level(source_counts)
        environment_archetype = self._infer_map_environment_archetype(
            human_activity_score=score["human_activity"],
            industry_score=score["industry"],
            transport_score=score["transport"],
            ecology_score=score["ecology"],
            water_score=score["water"],
            agriculture_score=score["agriculture"],
            open_score=score["open"],
            subtype_counts=subtype_counts,
            diffusion_template=diffusion_template,
        )
        target_range = self._map_target_count_range(environment_archetype)
        target_agent_count = self._resolve_map_target_agent_count(
            target_range=target_range,
            environment_archetype=environment_archetype,
            evidence_level=evidence_level,
            prepared_entities=prepared_entities,
            regions=regions,
            subregions=subregions,
            source_counts=source_counts,
        )
        allowed_roles, forbidden_roles = self._map_role_policy(
            environment_archetype=environment_archetype,
            human_activity_score=score["human_activity"],
            industry_score=score["industry"],
            transport_score=score["transport"],
            ecology_score=score["ecology"],
            water_score=score["water"],
            agriculture_score=score["agriculture"],
        )
        if environment_archetype == "ocean_sparse":
            warnings.append("AOI lacks direct human-activity evidence; social agents are gated off.")
        if evidence_level == "low":
            warnings.append("Map evidence is sparse; generated agents should be treated as low-confidence simulation proxies.")

        dominant_subtypes = [
            key
            for key, _count in sorted(subtype_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        ]
        return MapEvidenceContext(
            human_activity_score=score["human_activity"],
            industry_score=score["industry"],
            transport_score=score["transport"],
            ecology_score=score["ecology"],
            water_score=score["water"],
            agriculture_score=score["agriculture"],
            open_score=score["open"],
            evidence_level=evidence_level,
            environment_archetype=environment_archetype,
            target_count_range=target_range,
            target_agent_count=target_agent_count,
            allowed_roles=allowed_roles,
            forbidden_roles=forbidden_roles,
            evidence_refs_by_role={key: list(dict.fromkeys(value)) for key, value in refs.items()},
            feature_subtype_counts=dict(subtype_counts),
            source_kind_counts=dict(source_counts),
            dominant_subtypes=dominant_subtypes,
            admin_context=admin_context,
            warnings=warnings,
        )

    def _map_feature_weight_for_evidence(self, prepared: PreparedEntityContext) -> float:
        attrs = prepared.entity.attributes or {}
        source_kind = str(attrs.get("source_kind") or "").lower()
        source_multiplier = {"observed": 1.0, "detected": 0.7, "inferred": 0.35}.get(source_kind, 0.45)
        importance = self._coerce_float(attrs.get("importance")) or 4.0
        tags = attrs.get("tags") if isinstance(attrs.get("tags"), dict) else {}
        share = self._coerce_float((tags or {}).get("pixel_share_pct")) or 0.0
        confidence = self._coerce_float(attrs.get("confidence")) or 0.6
        return round((importance * 0.7 + share * 0.08 + confidence * 2.0) * source_multiplier, 3)

    def _map_evidence_level(self, source_counts: Dict[str, int]) -> str:
        observed = source_counts.get("observed", 0)
        detected = source_counts.get("detected", 0)
        inferred = source_counts.get("inferred", 0)
        if observed >= 4 or (observed >= 2 and detected >= 3):
            return "high"
        if observed + detected >= 4 or observed + detected + inferred >= 6:
            return "medium"
        return "low"

    def _infer_map_environment_archetype(
        self,
        *,
        human_activity_score: float,
        industry_score: float,
        transport_score: float,
        ecology_score: float,
        water_score: float,
        agriculture_score: float,
        open_score: float,
        subtype_counts: Dict[str, int],
        diffusion_template: str,
    ) -> str:
        coastal_tokens = {"coastline", "beach", "pier", "marina", "breakwater", "groyne"}
        has_coastal = bool(coastal_tokens & set(subtype_counts))
        if water_score >= 4 and human_activity_score < 2 and industry_score < 2 and transport_score < 2:
            return "ocean_sparse" if not has_coastal else "nearshore_natural"
        if industry_score >= max(human_activity_score, transport_score, ecology_score, agriculture_score, 3):
            return "industrial"
        if transport_score >= 3 and water_score >= 2:
            return "coastal_port"
        if transport_score >= max(human_activity_score, industry_score, ecology_score, 3):
            return "transport_corridor"
        if human_activity_score >= max(industry_score, transport_score, ecology_score, agriculture_score, 4):
            return "urban"
        if agriculture_score >= max(human_activity_score, industry_score, transport_score, 3):
            return "agricultural"
        if ecology_score >= max(human_activity_score, industry_score, transport_score, agriculture_score, 3):
            return "wetland_forest" if water_score >= 2 or normalize_transport_family(diffusion_template) in {"marine_current", "inland_water_network", "surface_flood_flow", "coastal_inundation"} else "ecology_sparse"
        if open_score >= 3 and human_activity_score < 3:
            return "natural_sparse"
        return "mixed_sparse" if human_activity_score < 3 and industry_score < 3 and transport_score < 3 else "mixed"

    def _map_target_count_range(self, environment_archetype: str) -> Tuple[int, int]:
        if environment_archetype in {"ocean_sparse", "nearshore_natural"}:
            return (8, 20)
        if environment_archetype in {"natural_sparse", "ecology_sparse", "mixed_sparse"}:
            return (12, 35)
        if environment_archetype in {"agricultural", "wetland_forest"}:
            return (25, 60)
        if environment_archetype in {"urban", "coastal_port", "industrial", "transport_corridor"}:
            return (50, 120)
        return (30, 80)

    def _resolve_map_target_agent_count(
        self,
        *,
        target_range: Tuple[int, int],
        environment_archetype: str,
        evidence_level: str,
        prepared_entities: List[PreparedEntityContext],
        regions: List[RegionNode],
        subregions: List[RegionNode],
        source_counts: Dict[str, int],
    ) -> int:
        lower, upper = target_range
        evidence_count = source_counts.get("observed", 0) + source_counts.get("detected", 0)
        base = len(subregions) * 4 + len(regions) * 2 + evidence_count
        if environment_archetype in {"urban", "coastal_port", "industrial", "transport_corridor"}:
            base = len(subregions) * 6 + evidence_count * 3 + source_counts.get("inferred", 0)
        elif environment_archetype in {"ocean_sparse", "nearshore_natural"}:
            base = len(subregions) * 4 + max(2, evidence_count // 3)
        if evidence_level == "low":
            base = min(base, lower + 4)
        if not prepared_entities:
            base = lower
        return max(lower, min(upper, int(base)))

    def _map_role_policy(
        self,
        *,
        environment_archetype: str,
        human_activity_score: float,
        industry_score: float,
        transport_score: float,
        ecology_score: float,
        water_score: float,
        agriculture_score: float,
    ) -> Tuple[List[str], List[str]]:
        allowed = {"ecology", "carrier", "remote_monitor", "governance"}
        if human_activity_score >= 2.0:
            allowed.update({"resident", "shop_owner", "community_committee", "white_collar", "market_association", "visitor"})
        if industry_score >= 2.0:
            allowed.update({"worker", "plant_operator", "safety_inspector", "logistics_operator"})
        if transport_score >= 2.0:
            allowed.update({"transport_operator", "emergency_office", "worker"})
        if ecology_score >= 2.0 or water_score >= 2.0:
            allowed.update({"conservation_station", "scientist", "field_observer"})
        if agriculture_score >= 2.0:
            allowed.update({"field_observer", "producer", "maintenance_operator"})

        forbidden = set()
        if environment_archetype == "ocean_sparse":
            forbidden.update({"resident", "shop_owner", "community_committee", "white_collar", "worker", "plant_operator", "visitor", "field_observer", "conservation_station"})
        if human_activity_score < 2.0:
            forbidden.update({"resident", "shop_owner", "community_committee", "white_collar", "market_association", "visitor"})
        if industry_score < 2.0:
            forbidden.update({"plant_operator", "safety_inspector"})
        if transport_score < 2.0:
            forbidden.update({"transport_operator"})
        return sorted(allowed - forbidden), sorted(forbidden)

    def _generate_map_seed_agent_profiles(
        self,
        *,
        prepared_entities: List[PreparedEntityContext],
        regions: List[RegionNode],
        subregions: List[RegionNode],
        scenario_mode: str,
        diffusion_template: str,
        simulation_requirement: str,
        evidence_context: MapEvidenceContext,
        target_count: int,
        injected_variables: List[InjectedVariable],
        use_llm: bool,
        profile_created_callback: Optional[Callable[[EnvAgentProfile], None]] = None,
    ) -> Tuple[List[EnvAgentProfile], List[EnvAgentProfile], Dict[str, Any]]:
        del prepared_entities
        candidates = self._plan_map_agent_candidates(
            regions=regions,
            subregions=subregions,
            diffusion_template=diffusion_template,
            evidence_context=evidence_context,
        )
        if use_llm and self.llm_client:
            candidates.extend(
                self._plan_map_agents_with_llm(
                    regions=regions,
                    subregions=subregions,
                    simulation_requirement=simulation_requirement,
                    evidence_context=evidence_context,
                    injected_variables=injected_variables,
                )
            )

        unique_candidates: Dict[str, AgentCandidatePlan] = {}
        for candidate in candidates:
            key = f"{candidate.agent_type}:{candidate.agent_subtype}:{candidate.home_subregion_id}:{candidate.role_name}"
            if key not in unique_candidates:
                unique_candidates[key] = candidate

        accepted: List[AgentCandidatePlan] = []
        rejected: List[Dict[str, Any]] = []
        for candidate in unique_candidates.values():
            ok, reason = self._review_map_agent_candidate(candidate, evidence_context, subregions)
            if ok:
                accepted.append(candidate)
            else:
                rejected.append({"candidate": candidate.to_dict(), "reason": reason})

        if use_llm and self.llm_client and accepted:
            rejected_ids = self._critique_map_agent_candidates_with_llm(
                evidence_context=evidence_context,
                candidates=accepted,
            )
            if rejected_ids:
                kept = []
                for candidate in accepted:
                    if candidate.candidate_id in rejected_ids:
                        rejected.append({"candidate": candidate.to_dict(), "reason": "LLM critic rejected as weakly grounded"})
                    else:
                        kept.append(candidate)
                accepted = kept

        if len(accepted) < evidence_context.target_count_range[0]:
            supplements = self._supplement_map_agent_candidates(
                accepted=accepted,
                regions=regions,
                subregions=subregions,
                diffusion_template=diffusion_template,
                evidence_context=evidence_context,
                needed=max(
                    evidence_context.target_count_range[0] - len(accepted) + 8,
                    (evidence_context.target_count_range[0] - len(accepted)) * 2,
                ),
            )
            for candidate in supplements:
                ok, reason = self._review_map_agent_candidate(candidate, evidence_context, subregions)
                if ok:
                    accepted.append(candidate)
                else:
                    rejected.append({"candidate": candidate.to_dict(), "reason": reason})

        accepted = accepted[:target_count]
        region_lookup = {region.region_id: region for region in regions}
        subregion_lookup = {subregion.region_id: subregion for subregion in subregions}
        profiles: List[EnvAgentProfile] = []
        for index, candidate in enumerate(accepted):
            profile = self._build_profile_from_candidate(
                index=index,
                candidate=candidate,
                regions=region_lookup,
                subregions=subregion_lookup,
                scenario_mode=scenario_mode,
            )
            profiles.append(profile)
            if profile_created_callback:
                profile_created_callback(profile)

        role_distribution: Dict[str, int] = defaultdict(int)
        for profile in profiles:
            role_distribution[profile.agent_type] += 1

        summary = {
            "map_evidence_context": evidence_context.to_dict(),
            "accepted_candidates_count": len(accepted),
            "rejected_candidates_count": len(rejected),
            "rejected_candidates": rejected[:80],
            "role_distribution": dict(role_distribution),
            "target_count_range": list(evidence_context.target_count_range),
            "target_agent_count": target_count,
            "actual_agent_count": len(profiles),
            "low_confidence_warnings": list(evidence_context.warnings),
        }
        return profiles, profiles, summary

    def _plan_map_agent_candidates(
        self,
        *,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        diffusion_template: str,
        evidence_context: MapEvidenceContext,
    ) -> List[AgentCandidatePlan]:
        region_lookup = {region.region_id: region for region in regions}
        candidates: List[AgentCandidatePlan] = []
        for subregion in subregions:
            parent_region = region_lookup.get(subregion.parent_region_id or "", regions[0])
            for blueprint in self._map_seed_agent_blueprints(subregion, parent_region, diffusion_template, evidence_context):
                evidence_refs = self._candidate_evidence_refs(blueprint, subregion, evidence_context)
                candidate_id = f"map_{len(candidates)}_{subregion.region_id}_{blueprint['agent_subtype']}"
                candidates.append(
                    AgentCandidatePlan(
                        candidate_id=candidate_id,
                        role_name=blueprint["name"],
                        node_family=blueprint["node_family"],
                        agent_type=blueprint["agent_type"],
                        agent_subtype=blueprint["agent_subtype"],
                        role_type=blueprint["role_type"],
                        home_region_id=parent_region.region_id,
                        home_subregion_id=subregion.region_id,
                        evidence_refs=evidence_refs,
                        confidence=self._candidate_confidence(blueprint, evidence_refs, evidence_context),
                        why_this_agent=blueprint.get("why") or f"由 {subregion.name} 的 {subregion.land_use_class or 'mixed'} 地图证据推导。",
                        action_space_hint=list(blueprint.get("action_space_hint") or []),
                        generation_mode="map_rule",
                    )
                )
        return candidates

    def _map_seed_agent_blueprints(
        self,
        subregion: RegionNode,
        region: RegionNode,
        diffusion_template: str,
        evidence_context: MapEvidenceContext,
    ) -> List[Dict[str, Any]]:
        diffusion_template = normalize_transport_family(diffusion_template)
        if evidence_context.environment_archetype == "ocean_sparse":
            carrier_subtype = "marine_current" if diffusion_template in {"marine", "marine_current", "coastal_inundation"} else (diffusion_template or "water_flow")
            return [
                {"name": "水体载体", "node_family": "EnvironmentalCarrier", "agent_type": "carrier", "agent_subtype": carrier_subtype, "role_type": "CarrierNode", "action_space_hint": ["transport_pressure", "retain_pollutant", "dilute"]},
                {"name": "海洋生态受体", "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "habitat_species", "role_type": "HabitatSpecies", "action_space_hint": ["migrate", "stress_signal"]},
                {"name": "远程海况监测主体", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "environment_bureau", "role_type": "EnvironmentBureau", "action_space_hint": ["monitor", "issue_alert"]},
                {"name": "污染扩散载体", "node_family": "EnvironmentalCarrier", "agent_type": "carrier", "agent_subtype": "surface_runoff" if diffusion_template not in {"marine", "marine_current", "coastal_inundation"} else "coastal_current", "role_type": "CarrierNode", "action_space_hint": ["transport_pressure", "dilute"]},
            ]

        blueprints = [dict(item) for item in self._synthetic_agent_blueprints(subregion, region, diffusion_template)]
        if subregion.land_use_class in {"water", "ecology"}:
            blueprints.append(
                {"name": "远程监测主体", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "environment_bureau", "role_type": "EnvironmentBureau", "action_space_hint": ["monitor", "publish_assessment"]}
            )
        if evidence_context.agriculture_score >= 2 and subregion.land_use_class in {"open", "ecology", "water"}:
            blueprints.append(
                {"name": "农业生产者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "field_observer", "role_type": "Farmer", "action_space_hint": ["report_hazard", "adapt"]}
            )
        if evidence_context.transport_score >= 2 and subregion.land_use_class not in {"transport"}:
            blueprints.append(
                {"name": "交通运维员", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "worker", "role_type": "TransportWorker", "action_space_hint": ["report_hazard", "reroute"]}
            )
        return blueprints

    def _candidate_evidence_refs(
        self,
        blueprint: Dict[str, Any],
        subregion: RegionNode,
        evidence_context: MapEvidenceContext,
    ) -> List[str]:
        subtype = blueprint.get("agent_subtype")
        agent_type = blueprint.get("agent_type")
        buckets: List[str] = []
        if agent_type in {"ecology", "carrier"}:
            buckets.extend([subregion.land_use_class, "water", "ecology", "open", "weather"])
        elif subtype in {"resident", "shop_owner", "community_committee", "white_collar", "market_association"}:
            buckets.extend(["human_activity", "urban", "transport"])
        elif subtype in {"worker", "plant_operator", "safety_inspector"}:
            buckets.extend(["industry", "transport", "agriculture", "coastal_work"])
        elif subtype in {"field_observer"}:
            buckets.extend(["agriculture", "ecology", "water", "coastal_work", "human_activity"])
        elif subtype in {"conservation_station", "scientist"}:
            buckets.extend(["ecology", "water", "governance"])
        elif agent_type == "governance":
            buckets.extend(["governance", "admin", "weather", "water", "ecology", "industry", "transport"])
        else:
            buckets.extend([subregion.land_use_class, "human_activity", "governance"])

        refs: List[str] = []
        for bucket in buckets:
            refs.extend(evidence_context.evidence_refs_by_role.get(str(bucket or ""), []))
        if subregion.region_id:
            refs.append(f"subregion::{subregion.region_id}")
        return list(dict.fromkeys(refs))[:8]

    def _candidate_confidence(
        self,
        blueprint: Dict[str, Any],
        evidence_refs: List[str],
        evidence_context: MapEvidenceContext,
    ) -> float:
        base = {"high": 0.78, "medium": 0.66, "low": 0.52}.get(evidence_context.evidence_level, 0.58)
        if blueprint.get("agent_type") in {"human", "organization"} and not evidence_refs:
            base -= 0.25
        if blueprint.get("agent_type") in {"ecology", "carrier"}:
            base += 0.08
        if blueprint.get("agent_type") == "governance":
            base += 0.04
        return max(0.1, min(0.95, round(base, 3)))

    def _review_map_agent_candidate(
        self,
        candidate: AgentCandidatePlan,
        evidence_context: MapEvidenceContext,
        subregions: List[RegionNode],
    ) -> Tuple[bool, str]:
        subregion_ids = {item.region_id for item in subregions}
        if candidate.home_subregion_id not in subregion_ids:
            return False, "candidate subregion does not exist"
        if candidate.agent_subtype in evidence_context.forbidden_roles:
            return False, f"{candidate.agent_subtype} is forbidden for {evidence_context.environment_archetype}"
        if candidate.confidence < 0.4:
            return False, "candidate confidence below grounding threshold"
        if evidence_context.environment_archetype == "ocean_sparse" and candidate.agent_type in {"human", "organization"}:
            return False, "ocean_sparse context lacks human activity evidence"

        if candidate.agent_type in {"human", "organization"}:
            environmental_org = candidate.agent_subtype in {"conservation_station"} and evidence_context.environment_archetype != "ocean_sparse"
            if not environmental_org and not self._candidate_has_social_evidence(candidate, evidence_context):
                return False, "social or organization agent lacks direct map evidence"
        return True, "accepted"

    def _candidate_has_social_evidence(
        self,
        candidate: AgentCandidatePlan,
        evidence_context: MapEvidenceContext,
    ) -> bool:
        refs = set(candidate.evidence_refs)
        social_refs = set(evidence_context.evidence_refs_by_role.get("human_activity", []))
        industry_refs = set(evidence_context.evidence_refs_by_role.get("industry", []))
        transport_refs = set(evidence_context.evidence_refs_by_role.get("transport", []))
        agriculture_refs = set(evidence_context.evidence_refs_by_role.get("agriculture", []))
        coastal_refs = set(evidence_context.evidence_refs_by_role.get("coastal_work", []))
        if candidate.agent_subtype in {"resident", "shop_owner", "community_committee", "white_collar", "market_association"}:
            return bool(refs & social_refs)
        if candidate.agent_subtype in {"worker", "plant_operator", "safety_inspector"}:
            return bool(refs & (industry_refs | transport_refs | agriculture_refs | coastal_refs))
        if candidate.agent_subtype == "field_observer":
            return bool(refs & (social_refs | agriculture_refs | coastal_refs))
        return bool(refs & (social_refs | industry_refs | transport_refs | agriculture_refs | coastal_refs))

    def _supplement_map_agent_candidates(
        self,
        *,
        accepted: List[AgentCandidatePlan],
        regions: List[RegionNode],
        subregions: List[RegionNode],
        diffusion_template: str,
        evidence_context: MapEvidenceContext,
        needed: int,
    ) -> List[AgentCandidatePlan]:
        del regions
        if needed <= 0 or not subregions:
            return []
        supplements: List[AgentCandidatePlan] = []
        existing_keys = {f"{item.agent_type}:{item.agent_subtype}:{item.home_subregion_id}:{item.role_name}" for item in accepted}
        index = 0
        while len(supplements) < needed and index < needed * 4 + 12:
            subregion = subregions[index % len(subregions)]
            parent_region_id = subregion.parent_region_id or ""
            if evidence_context.environment_archetype == "ocean_sparse":
                blueprints = [
                    {"name": f"海洋状态哨兵{len(supplements) + 1}", "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "habitat_species", "role_type": "HabitatSpecies"},
                    {"name": f"水动力载体{len(supplements) + 1}", "node_family": "EnvironmentalCarrier", "agent_type": "carrier", "agent_subtype": "coastal_current" if normalize_transport_family(diffusion_template) in {"marine", "marine_current", "coastal_inundation"} else "water_flow", "role_type": "CarrierNode"},
                    {"name": f"远程监测节点{len(supplements) + 1}", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "environment_bureau", "role_type": "EnvironmentBureau"},
                ]
            else:
                blueprints = self._map_seed_agent_blueprints(subregion, RegionNode(region_id=parent_region_id, name=parent_region_id), diffusion_template, evidence_context)
            for blueprint in blueprints:
                key = f"{blueprint['agent_type']}:{blueprint['agent_subtype']}:{subregion.region_id}:{blueprint['name']}"
                if key in existing_keys:
                    blueprint = {
                        **blueprint,
                        "name": f"{blueprint['name']}扩展{len(supplements) + 1}",
                    }
                    key = f"{blueprint['agent_type']}:{blueprint['agent_subtype']}:{subregion.region_id}:{blueprint['name']}"
                    if key in existing_keys:
                        continue
                refs = self._candidate_evidence_refs(blueprint, subregion, evidence_context)
                supplements.append(
                    AgentCandidatePlan(
                        candidate_id=f"map_supplement_{len(supplements)}_{subregion.region_id}_{blueprint['agent_subtype']}",
                        role_name=blueprint["name"],
                        node_family=blueprint["node_family"],
                        agent_type=blueprint["agent_type"],
                        agent_subtype=blueprint["agent_subtype"],
                        role_type=blueprint["role_type"],
                        home_region_id=parent_region_id,
                        home_subregion_id=subregion.region_id,
                        evidence_refs=refs,
                        confidence=self._candidate_confidence(blueprint, refs, evidence_context),
                        why_this_agent=f"用于满足 {evidence_context.environment_archetype} 地图场景的最低环境模拟密度。",
                        action_space_hint=list(blueprint.get("action_space_hint") or []),
                        generation_mode="map_rule_supplement",
                    )
                )
                existing_keys.add(key)
                if len(supplements) >= needed:
                    break
            index += 1
        return supplements

    def _build_profile_from_candidate(
        self,
        *,
        index: int,
        candidate: AgentCandidatePlan,
        regions: Dict[str, RegionNode],
        subregions: Dict[str, RegionNode],
        scenario_mode: str,
    ) -> EnvAgentProfile:
        subregion = subregions.get(candidate.home_subregion_id)
        region = regions.get(candidate.home_region_id)
        if subregion is None:
            subregion = next(iter(subregions.values()))
        if region is None:
            region = regions.get(subregion.parent_region_id or "") or next(iter(regions.values()))
        behavior = self._behavior_bundle(
            node_family=candidate.node_family,
            agent_subtype=candidate.agent_subtype,
            region_name=region.name,
            subregion_name=subregion.name,
            land_use_class=subregion.land_use_class or "mixed",
        )
        if candidate.action_space_hint:
            behavior["action_space"] = list(dict.fromkeys([*candidate.action_space_hint, *behavior["action_space"]]))
        display_name = f"{subregion.name}{candidate.role_name}"
        return EnvAgentProfile(
            agent_id=index,
            username=self._username_from_name(display_name, index),
            name=display_name,
            node_family=candidate.node_family,
            role_type=candidate.role_type,
            bio=behavior["bio"],
            persona=f"{behavior['persona']} 生成依据：{candidate.why_this_agent}",
            profession=candidate.role_name,
            primary_region=region.region_id,
            agent_type=candidate.agent_type,
            agent_subtype=candidate.agent_subtype,
            archetype_key=f"map:{subregion.land_use_class}:{candidate.agent_subtype}",
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
            state_vector=default_state_vector(scenario_mode, candidate.node_family),
            source_entity_uuid=None,
            source_entity_type=candidate.role_type,
            generation_mode=candidate.generation_mode,
            evidence_refs=list(dict.fromkeys(candidate.evidence_refs)),
            evidence_confidence=candidate.confidence,
            review_status="accepted",
            grounding_reason=candidate.why_this_agent,
        )

    def _plan_map_agents_with_llm(
        self,
        *,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        simulation_requirement: str,
        evidence_context: MapEvidenceContext,
        injected_variables: List[InjectedVariable],
    ) -> List[AgentCandidatePlan]:
        if not self.llm_client:
            return []
        prompt = {
            "task": "Create grounded EnvFish agent candidates from map evidence only.",
            "rules": [
                "Return compact JSON only.",
                "Do not invent residents, workers, businesses, tourists, or institutions unless allowed_roles supports them.",
                "Every candidate must include evidence_refs from evidence_refs_by_role or a subregion ref.",
                "Respect forbidden_roles strictly.",
            ],
            "evidence_context": evidence_context.to_dict(),
            "regions": [region.to_dict() for region in regions[:8]],
            "subregions": [subregion.to_dict() for subregion in subregions[:16]],
            "requirement": simulation_requirement[:1200],
            "injected_variables": self._summarize_injected_variables(injected_variables),
            "schema": {
                "candidates": [
                    {
                        "role_name": "short role label",
                        "agent_type": "human|organization|governance|ecology|carrier",
                        "agent_subtype": "resident|field_observer|environment_bureau|habitat_species|water_flow",
                        "role_type": "RoleType",
                        "home_region_id": "region id",
                        "home_subregion_id": "subregion id",
                        "evidence_refs": ["uuid or subregion ref"],
                        "confidence": 0.7,
                        "why_this_agent": "one sentence",
                        "action_space_hint": ["monitor"],
                    }
                ]
            },
        }
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": "You generate fact-constrained map simulation agent plans as JSON."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.15,
                max_tokens=2200,
            )
        except Exception as exc:
            logger.warning(f"Map agent LLM planning failed, using deterministic candidates: {exc}")
            return []
        raw_candidates = result.get("candidates") if isinstance(result, dict) else None
        if not isinstance(raw_candidates, list):
            return []
        region_ids = {region.region_id for region in regions}
        subregion_ids = {subregion.region_id for subregion in subregions}
        candidates: List[AgentCandidatePlan] = []
        for index, item in enumerate(raw_candidates[:24]):
            if not isinstance(item, dict):
                continue
            home_region_id = str(item.get("home_region_id") or "")
            home_subregion_id = str(item.get("home_subregion_id") or "")
            if home_region_id not in region_ids or home_subregion_id not in subregion_ids:
                continue
            agent_type = str(item.get("agent_type") or "ecology")
            agent_subtype = str(item.get("agent_subtype") or "habitat_species")
            node_family = self._node_family_for_agent_type(agent_type)
            confidence = self._coerce_float(item.get("confidence")) or 0.55
            candidates.append(
                AgentCandidatePlan(
                    candidate_id=f"map_llm_{index}_{home_subregion_id}_{agent_subtype}",
                    role_name=str(item.get("role_name") or agent_subtype),
                    node_family=node_family,
                    agent_type=agent_type,
                    agent_subtype=agent_subtype,
                    role_type=str(item.get("role_type") or agent_subtype.title().replace("_", "")),
                    home_region_id=home_region_id,
                    home_subregion_id=home_subregion_id,
                    evidence_refs=[str(ref) for ref in (item.get("evidence_refs") or []) if ref],
                    confidence=max(0.0, min(1.0, confidence)),
                    why_this_agent=str(item.get("why_this_agent") or "LLM planned from constrained map evidence."),
                    action_space_hint=[str(action) for action in (item.get("action_space_hint") or []) if action],
                    generation_mode="map_llm_personalized",
                )
            )
        return candidates

    def _critique_map_agent_candidates_with_llm(
        self,
        *,
        evidence_context: MapEvidenceContext,
        candidates: List[AgentCandidatePlan],
    ) -> set[str]:
        if not self.llm_client:
            return set()
        prompt = {
            "task": "Review whether map-generated agent candidates are grounded.",
            "evidence_context": evidence_context.to_dict(),
            "candidates": [candidate.to_dict() for candidate in candidates[:60]],
            "rules": [
                "Reject agents that are not plausible for the environment_archetype.",
                "Reject social agents without direct human, industry, transport, agriculture, tourism, or administrative evidence.",
                "Be conservative when the archetype is ocean_sparse.",
            ],
            "schema": {"rejected_candidate_ids": ["candidate_id"]},
        }
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": "You are a strict map-grounding critic. Return JSON only."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.0,
                max_tokens=900,
            )
        except Exception as exc:
            logger.warning(f"Map agent LLM critic failed, keeping deterministic review: {exc}")
            return set()
        rejected = result.get("rejected_candidate_ids") if isinstance(result, dict) else []
        return {str(item) for item in rejected or []}

    def _node_family_for_agent_type(self, agent_type: str) -> str:
        return {
            "human": "HumanActor",
            "organization": "OrganizationActor",
            "governance": "GovernmentActor",
            "ecology": "EcologicalReceptor",
            "carrier": "EnvironmentalCarrier",
        }.get(agent_type, "EcologicalReceptor")

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
                if blueprint["distance_band"] == "core":
                    state_vector["spread_pressure"] += 8
                if blueprint["land_use_class"] == "industrial":
                    state_vector["economic_stress"] += 10
                    state_vector["ecosystem_integrity"] -= 8
                if blueprint["land_use_class"] == "ecology":
                    state_vector["ecosystem_integrity"] += 6
                    state_vector["vulnerability_score"] += 6
                    state_vector["livelihood_stability"] -= 4
                if blueprint["land_use_class"] == "water":
                    state_vector["spread_pressure"] += 12
                    state_vector["ecosystem_integrity"] += 4
                    state_vector["service_capacity"] -= 2
                if blueprint["land_use_class"] == "transport":
                    state_vector["service_capacity"] += 8
                    state_vector["economic_stress"] += 6
                if blueprint["land_use_class"] == "open":
                    state_vector["ecosystem_integrity"] += 2
                    state_vector["livelihood_stability"] -= 2
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
        diffusion_template = normalize_transport_family(diffusion_template)
        ecology_focus = {
            "marine": {
                "label": "滨海生态缓冲带",
                "ecology_assets": ["mangrove", "seabird", "shellfish"],
                "carriers": ["coastal_current", "shore_wind"],
            },
            "marine_current": {
                "label": "滨海生态缓冲带",
                "ecology_assets": ["mangrove", "seabird", "shellfish"],
                "carriers": ["coastal_current", "shore_wind"],
            },
            "inland_water": {
                "label": "河岸生态缓冲带",
                "ecology_assets": ["riparian_plants", "freshwater_fish", "wetland_birds"],
                "carriers": ["river_segment", "groundwater_exchange"],
            },
            "inland_water_network": {
                "label": "河岸生态缓冲带",
                "ecology_assets": ["riparian_plants", "freshwater_fish", "wetland_birds"],
                "carriers": ["river_segment", "groundwater_exchange"],
            },
            "air": {
                "label": "下风向生态缓冲带",
                "ecology_assets": ["tree_canopy", "urban_birds", "soil_microbiome"],
                "carriers": ["air_mass", "dust_pathway"],
            },
            "atmospheric_plume": {
                "label": "下风向生态缓冲带",
                "ecology_assets": ["tree_canopy", "urban_birds", "soil_microbiome"],
                "carriers": ["air_mass", "dust_pathway"],
            },
            "ash_plume": {
                "label": "火山灰影响带",
                "ecology_assets": ["tree_canopy", "soil_microbiome", "downstream_fish"],
                "carriers": ["ash_plume", "lahar_runoff"],
            },
            "coastal_inundation": {
                "label": "沿海淹没缓冲带",
                "ecology_assets": ["saltmarsh", "estuarine_fish", "shorebirds"],
                "carriers": ["storm_surge_front", "saline_intrusion"],
            },
            "surface_flood_flow": {
                "label": "洪泛冲积带",
                "ecology_assets": ["wetland_plants", "freshwater_fish", "soil_microbiome"],
                "carriers": ["surface_flood_flow", "sewage_overflow"],
            },
            "ecological_mobility": {
                "label": "扩散走廊带",
                "ecology_assets": ["indicator_species", "edge_species"],
                "carriers": ["habitat_corridor", "human_transport_vector"],
            },
            "bio_ecological_transmission": {
                "label": "宿主-媒介传播带",
                "ecology_assets": ["indicator_species", "wild_hosts"],
                "carriers": ["bio_vector", "host_density"],
            },
            "slow_ecosystem_decline": {
                "label": "慢变量退化带",
                "ecology_assets": ["tree_canopy", "wetland_plants", "indicator_species"],
                "carriers": ["ecological_stress_gradient", "water_shortage"],
            },
            "infrastructure_failure": {
                "label": "设施级联系统带",
                "ecology_assets": ["indicator_species"],
                "carriers": ["infrastructure_corridor", "service_disruption"],
            },
            "impact_blast": {
                "label": "撞击影响带",
                "ecology_assets": ["indicator_species", "soil_microbiome"],
                "carriers": ["impact_wave", "ejecta_fallout"],
            },
            "terrestrial_surface": {
                "label": "地表暴露缓冲带",
                "ecology_assets": ["indicator_species", "soil_microbiome"],
                "carriers": ["surface_runoff", "soil_accumulation"],
            },
            "generic": {
                "label": "生态缓冲带",
                "ecology_assets": ["indicator_species"],
                "carriers": ["environmental_link"],
            },
        }.get(diffusion_template, {})

        tagset = {str(tag).lower() for tag in (region.tags or []) if tag}
        carriers = list(region.carriers or [])
        blueprints: List[Dict[str, Any]] = []

        def add_blueprint(
            *,
            slug: str,
            label: str,
            region_type: str,
            land_use_class: str,
            distance_band: str,
            description: str,
            ecology_assets: List[str],
            industry_tags: List[str],
            region_constraints: List[str],
            exposure_channels: List[str],
            population_capacity: int,
            carriers_override: Optional[List[str]] = None,
        ) -> None:
            if any(item["slug"] == slug for item in blueprints):
                return
            blueprints.append(
                {
                    "slug": slug,
                    "label": label,
                    "region_type": region_type,
                    "land_use_class": land_use_class,
                    "distance_band": distance_band,
                    "description": description,
                    "ecology_assets": ecology_assets,
                    "industry_tags": industry_tags,
                    "region_constraints": region_constraints,
                    "exposure_channels": exposure_channels,
                    "population_capacity": population_capacity,
                    "carriers": carriers_override or carriers,
                }
            )

        is_water = region.land_use_class == "water" or region.region_type == "coastal_zone" or "water" in tagset
        is_transport = region.land_use_class == "transport" or region.region_type == "infrastructure_corridor" or "transport" in tagset
        is_industrial = region.land_use_class == "industrial" or region.region_type == "industrial_zone" or "industrial" in tagset
        is_ecology = region.land_use_class == "ecology" or region.region_type == "ecology_zone" or "ecology" in tagset
        is_urban = region.land_use_class in {"urban", "residential", "commercial"} or region.region_type in {"urban_zone", "residential_zone"} or "urban" in tagset
        is_open = region.land_use_class == "open" or region.region_type == "open_space_zone" or "open" in tagset

        if is_water:
            add_blueprint(
                slug="water_core",
                label="主水域核心带",
                region_type="water_core_zone",
                land_use_class="water",
                distance_band="core",
                description=f"{region.name} 中承担主要水体交换与污染输移的核心水域。",
                ecology_assets=["water_column", "plankton"],
                industry_tags=["hydrology"],
                region_constraints=["扩散快", "边界不稳定"],
                exposure_channels=["water_flow", "shore_contact"],
                population_capacity=6,
                carriers_override=["water_flow", *carriers],
            )
            add_blueprint(
                slug="shore_buffer",
                label=ecology_focus.get("label", "岸线生态缓冲带"),
                region_type="shore_buffer_zone",
                land_use_class="ecology",
                distance_band="transition",
                description=f"{region.name} 与陆地或岸线过渡的生态缓冲带。",
                ecology_assets=ecology_focus.get("ecology_assets", ["indicator_species"]),
                industry_tags=["habitat"],
                region_constraints=["恢复慢", "受扰敏感"],
                exposure_channels=ecology_focus.get("carriers", ["water_flow"]),
                population_capacity=8,
                carriers_override=ecology_focus.get("carriers", carriers),
            )
            if "transport" in tagset or "road_corridor" in tagset or "港" in region.name or "桥" in region.name:
                add_blueprint(
                    slug="bridge_interface",
                    label="桥区扰动带",
                    region_type="transport_interface_zone",
                    land_use_class="transport",
                    distance_band="near",
                    description=f"{region.name} 中受桥梁、航运或交通活动直接扰动的接口带。",
                    ecology_assets=["surface_birds"],
                    industry_tags=["transport", "logistics"],
                    region_constraints=["线性暴露", "管控复杂"],
                    exposure_channels=["traffic_flow", "surface_contact", "water_flow"],
                    population_capacity=10,
                )

        elif is_transport:
            add_blueprint(
                slug="corridor_core",
                label="交通走廊核心段",
                region_type="transport_core_zone",
                land_use_class="transport",
                distance_band="core",
                description=f"{region.name} 中承担主要流量与暴露传导的线性核心段。",
                ecology_assets=["roadside_birds"],
                industry_tags=["transport", "logistics"],
                region_constraints=["中断敏感", "联动范围大"],
                exposure_channels=["traffic_flow", "surface_contact"],
                population_capacity=12,
            )
            add_blueprint(
                slug="service_node",
                label="服务接驳节点",
                region_type="service_node_zone",
                land_use_class="commercial",
                distance_band="transition",
                description=f"{region.name} 周边承接物流、补给和服务转换的节点带。",
                ecology_assets=["urban_birds"],
                industry_tags=["services", "logistics"],
                region_constraints=["舆情敏感", "供给波动"],
                exposure_channels=["service_flow", "traffic_flow"],
                population_capacity=10,
            )
            add_blueprint(
                slug="response_interface",
                label="应急响应接口",
                region_type="civic_zone",
                land_use_class="civic",
                distance_band="near",
                description=f"{region.name} 中最需要调度、封控或分流的治理接口。",
                ecology_assets=["monitoring_plots"],
                industry_tags=["governance", "emergency"],
                region_constraints=["协调复杂", "跨部门联动"],
                exposure_channels=["policy", "public_communication", "traffic_flow"],
                population_capacity=9,
            )
            if "water_flow" in carriers or "water" in tagset:
                add_blueprint(
                    slug="bridgehead_water",
                    label="桥头近水接口",
                    region_type="waterfront_interface_zone",
                    land_use_class="water",
                    distance_band="transition",
                    description=f"{region.name} 与近岸水体相互作用最强的桥头接口带。",
                    ecology_assets=["nearshore_habitat"],
                    industry_tags=["transport", "shoreline"],
                    region_constraints=["跨域耦合", "扰动扩散"],
                    exposure_channels=["traffic_flow", "water_flow"],
                    population_capacity=7,
                )

        elif is_industrial:
            add_blueprint(
                slug="operation_core",
                label="作业核心区",
                region_type="industrial_core_zone",
                land_use_class="industrial",
                distance_band="core",
                description=f"{region.name} 中生产、排放或设备运行最集中的作业核心区。",
                ecology_assets=["soil_microbiome"],
                industry_tags=["manufacturing", "operations"],
                region_constraints=["停摆成本高", "合规压力大"],
                exposure_channels=["waste_stream", "surface_contact"],
                population_capacity=12,
            )
            add_blueprint(
                slug="logistics_edge",
                label="物流接口带",
                region_type="industrial_logistics_zone",
                land_use_class="transport",
                distance_band="near",
                description=f"{region.name} 与仓储、运输和装卸相连的物流接口带。",
                ecology_assets=["roadside_birds"],
                industry_tags=["logistics", "freight"],
                region_constraints=["链路脆弱", "扩散外溢"],
                exposure_channels=["transport", "surface_contact"],
                population_capacity=10,
            )
            add_blueprint(
                slug="compliance_buffer",
                label="合规治理带",
                region_type="civic_zone",
                land_use_class="civic",
                distance_band="transition",
                description=f"{region.name} 中用于监测、执法和应急布设的治理缓冲带。",
                ecology_assets=["monitoring_plots"],
                industry_tags=["governance", "compliance"],
                region_constraints=["协调摩擦", "信息压力"],
                exposure_channels=["policy", "monitoring"],
                population_capacity=8,
            )
            if "water_flow" in carriers or "ecology" in tagset:
                add_blueprint(
                    slug="runoff_buffer",
                    label="径流生态缓冲带",
                    region_type="ecology_zone",
                    land_use_class="ecology",
                    distance_band="far",
                    description=f"{region.name} 中承接工业外溢影响的生态与径流缓冲带。",
                    ecology_assets=["wetland_plants", "indicator_species"],
                    industry_tags=["habitat"],
                    region_constraints=["恢复慢", "阈值脆弱"],
                    exposure_channels=["surface_runoff", "water_flow"],
                    population_capacity=7,
                )

        elif is_ecology:
            add_blueprint(
                slug="eco_core",
                label="生态核心区",
                region_type="ecology_core_zone",
                land_use_class="ecology",
                distance_band="core",
                description=f"{region.name} 中生态受体最集中、恢复价值最高的核心片区。",
                ecology_assets=ecology_focus.get("ecology_assets", ["indicator_species"]),
                industry_tags=["habitat"],
                region_constraints=["阈值脆弱", "恢复缓慢"],
                exposure_channels=ecology_focus.get("carriers", carriers),
                population_capacity=7,
                carriers_override=ecology_focus.get("carriers", carriers),
            )
            add_blueprint(
                slug="observation_edge",
                label="观测巡护带",
                region_type="ecology_monitor_zone",
                land_use_class="civic",
                distance_band="transition",
                description=f"{region.name} 中承担巡护、监测和干预观测的边缘带。",
                ecology_assets=["monitoring_plots"],
                industry_tags=["conservation", "monitoring"],
                region_constraints=["资源有限", "进入受限"],
                exposure_channels=["monitoring", "public_communication"],
                population_capacity=6,
            )
            if "water_flow" in carriers or "water" in tagset:
                add_blueprint(
                    slug="wetland_margin",
                    label="近水生态边缘带",
                    region_type="shore_buffer_zone",
                    land_use_class="water",
                    distance_band="near",
                    description=f"{region.name} 中与水体交换最强的近水生态边缘带。",
                    ecology_assets=["nearshore_habitat", "waders"],
                    industry_tags=["shoreline"],
                    region_constraints=["受扰敏感", "边界多变"],
                    exposure_channels=["water_flow", "habitat_disturbance"],
                    population_capacity=5,
                )

        elif is_urban:
            add_blueprint(
                slug="residential_life",
                label="居住生活片区",
                region_type="residential_zone",
                land_use_class="residential",
                distance_band="near",
                description=f"{region.name} 中最先承受日常暴露与生活压力变化的居住片区。",
                ecology_assets=["street_trees", "pet_animals"],
                industry_tags=["community_services"],
                region_constraints=["人口密集", "信息敏感"],
                exposure_channels=["daily_contact", "service_flow"],
                population_capacity=18,
            )
            add_blueprint(
                slug="service_cluster",
                label="服务商业片区",
                region_type="commercial_zone",
                land_use_class="commercial",
                distance_band="transition",
                description=f"{region.name} 中承担办公、零售、补给与服务流转的片区。",
                ecology_assets=["urban_birds"],
                industry_tags=["retail", "services"],
                region_constraints=["供给波动", "舆情敏感"],
                exposure_channels=["consumer_flow", "service_flow"],
                population_capacity=14,
            )
            add_blueprint(
                slug="civic_node",
                label="治理服务节点",
                region_type="civic_zone",
                land_use_class="civic",
                distance_band="transition",
                description=f"{region.name} 中承担信息发布、医疗与应急协同的治理服务节点。",
                ecology_assets=["monitoring_plots"],
                industry_tags=["governance", "healthcare", "education"],
                region_constraints=["协调摩擦", "响应压力"],
                exposure_channels=["policy", "public_communication"],
                population_capacity=10,
            )
            if "transport" in tagset or "transport_flow" in carriers:
                add_blueprint(
                    slug="mobility_edge",
                    label="交通接触带",
                    region_type="mobility_interface_zone",
                    land_use_class="transport",
                    distance_band="near",
                    description=f"{region.name} 中与交通流、通勤流和物流接口最强的边缘带。",
                    ecology_assets=["roadside_birds"],
                    industry_tags=["transport", "mobility"],
                    region_constraints=["暴露高", "波及快"],
                    exposure_channels=["traffic_flow", "daily_contact"],
                    population_capacity=11,
                )
            if "water_flow" in carriers or "water" in tagset or "ecology" in tagset:
                add_blueprint(
                    slug="urban_eco_edge",
                    label=ecology_focus.get("label", "城市生态边缘带"),
                    region_type="ecology_zone",
                    land_use_class="ecology",
                    distance_band="far",
                    description=f"{region.name} 中与生态斑块或岸线交错的城市生态边缘带。",
                    ecology_assets=ecology_focus.get("ecology_assets", ["indicator_species"]),
                    industry_tags=["habitat", "urban_edge"],
                    region_constraints=["边缘效应强", "恢复慢"],
                    exposure_channels=ecology_focus.get("carriers", carriers),
                    population_capacity=8,
                    carriers_override=ecology_focus.get("carriers", carriers),
                )

        elif is_open:
            add_blueprint(
                slug="open_core",
                label="开放地表核心区",
                region_type="open_core_zone",
                land_use_class="open",
                distance_band="core",
                description=f"{region.name} 中土地覆盖较裸露或低密度的开放地表核心区。",
                ecology_assets=["edge_species"],
                industry_tags=["open_space"],
                region_constraints=["用途混杂", "边缘效应强"],
                exposure_channels=["surface_runoff", "wind_rework"],
                population_capacity=6,
            )
            add_blueprint(
                slug="edge_buffer",
                label="过渡缓冲带",
                region_type="transition_buffer_zone",
                land_use_class="ecology",
                distance_band="transition",
                description=f"{region.name} 中连接开放地表与周边建成/生态单元的过渡缓冲带。",
                ecology_assets=["indicator_species"],
                industry_tags=["edge_transition"],
                region_constraints=["功能不稳定", "边界模糊"],
                exposure_channels=["surface_runoff", "habitat_disturbance"],
                population_capacity=7,
            )
            if "transport" in tagset:
                add_blueprint(
                    slug="roadside_fringe",
                    label="路侧边缘带",
                    region_type="roadside_zone",
                    land_use_class="transport",
                    distance_band="near",
                    description=f"{region.name} 中与道路或交通边界接触最强的路侧边缘带。",
                    ecology_assets=["roadside_birds"],
                    industry_tags=["transport"],
                    region_constraints=["扰动频繁", "碎片化"],
                    exposure_channels=["traffic_flow", "surface_contact"],
                    population_capacity=6,
                )

        if not blueprints:
            add_blueprint(
                slug="general_transition",
                label="综合过渡区",
                region_type="transition_zone",
                land_use_class="urban",
                distance_band="transition",
                description=f"{region.name} 中暂未细分出更具体类型的综合过渡片区。",
                ecology_assets=["indicator_species"],
                industry_tags=["mixed_use"],
                region_constraints=["信息有限"],
                exposure_channels=list(carriers or ["environmental_link"]),
                population_capacity=8,
            )

        return blueprints

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
            "marine": "红树林观察点" if subregion.land_use_class in {"ecology", "water"} else "海鸥群",
            "inland_water": "河岸鱼群" if subregion.land_use_class in {"ecology", "water"} else "湿地鸟群",
            "air": "城市树冠层" if subregion.land_use_class in {"ecology", "open"} else "下风向鸟群",
            "generic": "指示物种群",
        }.get(diffusion_template, "指示物种群")

        blueprints_by_land_use = {
            "urban": [
                {"name": "居民代表", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "resident", "role_type": "Resident"},
                {"name": "社区经营者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "shop_owner", "role_type": "ShopOwner"},
                {"name": "社区委员会", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "community_committee", "role_type": "CommunityCommittee"},
                {"name": "城市鸟群", "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "urban_birds", "role_type": "UrbanBirds"},
            ],
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
            "water": [
                {"name": "近岸观察者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "field_observer", "role_type": "FieldObserver"},
                {"name": "水域巡护站", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "conservation_station", "role_type": "ConservationStation"},
                {"name": ecology_name, "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "habitat_species", "role_type": "HabitatSpecies"},
                {"name": "水体载体", "node_family": "EnvironmentalCarrier", "agent_type": "carrier", "agent_subtype": diffusion_template or "water_flow", "role_type": "CarrierNode"},
            ],
            "transport": [
                {"name": "通道运维员", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "worker", "role_type": "Worker"},
                {"name": "交通运营方", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "plant_operator", "role_type": "PlantOperator"},
                {"name": "应急协调员", "node_family": "GovernmentActor", "agent_type": "governance", "agent_subtype": "emergency_office", "role_type": "EmergencyOffice"},
                {"name": "路侧生态哨兵", "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "urban_birds", "role_type": "UrbanBirds"},
            ],
            "open": [
                {"name": "现场观察者", "node_family": "HumanActor", "agent_type": "human", "agent_subtype": "field_observer", "role_type": "FieldObserver"},
                {"name": "开放空间维护方", "node_family": "OrganizationActor", "agent_type": "organization", "agent_subtype": "community_committee", "role_type": "CommunityCommittee"},
                {"name": ecology_name, "node_family": "EcologicalReceptor", "agent_type": "ecology", "agent_subtype": "urban_ecology", "role_type": "EcologySentinel"},
                {"name": "地表载体", "node_family": "EnvironmentalCarrier", "agent_type": "carrier", "agent_subtype": "surface_runoff", "role_type": "CarrierNode"},
            ],
        }
        return blueprints_by_land_use.get(subregion.land_use_class, blueprints_by_land_use["urban"])

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
        if land_use_class == "transport":
            merged["decision_policy"] = {**merged["decision_policy"], "economic_weight": 0.75, "ecology_weight": 0.2}
            merged["capabilities"] = list(dict.fromkeys([*merged["capabilities"], "routing", "traffic_control"]))
        if land_use_class == "water":
            merged["decision_policy"] = {**merged["decision_policy"], "economic_weight": 0.15, "ecology_weight": 0.9}
            merged["capabilities"] = list(dict.fromkeys([*merged["capabilities"], "hydro_observation"]))
        if land_use_class == "open":
            merged["decision_policy"] = {**merged["decision_policy"], "economic_weight": 0.2, "ecology_weight": 0.75}
        return merged

    def _build_profile(
        self,
        index: int,
        prepared: PreparedEntityContext,
        regions: List[RegionNode],
        subregions: List[RegionNode],
        scenario_mode: str,
        simulation_requirement: str,
        injected_variables: List[InjectedVariable],
        use_llm: bool,
    ) -> EnvAgentProfile:
        primary_region = self._match_region(prepared, regions)
        primary_subregion = self._match_subregion(prepared, primary_region, subregions)
        relevant_variables = self._select_variables_for_profile(prepared, primary_region, primary_subregion, injected_variables)
        state_vector = self._apply_variable_pressure_to_state_vector(
            default_state_vector(scenario_mode, prepared.node_family),
            relevant_variables,
            prepared.node_family,
        )
        base_goals = self._default_goals(prepared.node_family, primary_region.name)
        sensitivities = self._default_sensitivities(prepared.node_family, primary_region.name)
        if relevant_variables:
            base_goals = self._merge_text_items(base_goals, [f"respond to {item.name}" for item in relevant_variables[:2]])
            sensitivities = self._merge_text_items(
                sensitivities,
                [item.description or item.name for item in relevant_variables[:2]],
            )

        llm_payload = None
        if use_llm and self.llm_client:
            llm_payload = self._generate_profile_with_llm(
                prepared=prepared,
                primary_region=primary_region,
                simulation_requirement=simulation_requirement,
                injected_variables=relevant_variables,
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
        lat = self._coerce_float(prepared.entity.attributes.get("lat"))
        lon = self._coerce_float(prepared.entity.attributes.get("lon"))
        if lat is not None and lon is not None:
            geo_candidates = [region for region in regions if region.lat is not None and region.lon is not None]
            if geo_candidates:
                return min(
                    geo_candidates,
                    key=lambda item: self._haversine_m(lat, lon, float(item.lat), float(item.lon)),
                )
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
            preferred_land_use = "water" if any(item.land_use_class == "water" for item in candidates) else "ecology"
        elif prepared.node_family == "GovernmentActor":
            preferred_land_use = "civic"
        elif prepared.node_family == "OrganizationActor":
            preferred_land_use = "transport" if any(token in haystack for token in ("transport", "traffic", "logistics", "bridge", "港", "桥")) else "commercial"
        elif "worker" in haystack or "factory" in haystack or "industrial" in haystack:
            preferred_land_use = "industrial"
        elif any(token in haystack for token in ("transport", "traffic", "bridge", "corridor", "road", "港珠澳")):
            preferred_land_use = "transport"
        elif any(token in haystack for token in ("water", "wetland", "coast", "bay", "shore", "海", "水域", "近岸")):
            preferred_land_use = "water" if any(item.land_use_class == "water" for item in candidates) else "ecology"
        elif any(token in haystack for token in ("grass", "meadow", "open", "bare", "草地", "裸地")):
            preferred_land_use = "open"
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
        injected_variables: List[InjectedVariable],
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
            "injected_variables": self._summarize_injected_variables(injected_variables),
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

    def _summarize_injected_variables(self, injected_variables: List[InjectedVariable]) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        for item in injected_variables[:8]:
            summary.append(
                {
                    "name": item.name,
                    "type": item.type,
                    "description": item.description,
                    "target_regions": item.target_regions[:4],
                    "start_round": item.start_round,
                    "duration_rounds": item.duration_rounds,
                    "intensity_0_100": item.intensity_0_100,
                }
            )
        return summary

    def _select_variables_for_profile(
        self,
        prepared: PreparedEntityContext,
        primary_region: RegionNode,
        primary_subregion: RegionNode,
        injected_variables: List[InjectedVariable],
    ) -> List[InjectedVariable]:
        haystack = " ".join(
            [
                prepared.entity.name,
                prepared.entity_type,
                prepared.summary,
                primary_region.name,
                primary_subregion.name,
            ]
        ).lower()
        matched: List[InjectedVariable] = []
        for item in injected_variables:
            region_match = not item.target_regions or any(
                str(region or "").strip().lower() in {
                    primary_region.region_id.lower(),
                    primary_region.name.lower(),
                    primary_subregion.region_id.lower(),
                    primary_subregion.name.lower(),
                }
                for region in item.target_regions
            )
            text_match = item.name.lower() in haystack or (item.description and item.description.lower() in haystack)
            if region_match or text_match:
                matched.append(item)
        return matched[:3]

    def _apply_variable_pressure_to_state_vector(
        self,
        state_vector: Dict[str, float],
        injected_variables: List[InjectedVariable],
        node_family: str,
    ) -> Dict[str, float]:
        adjusted = dict(state_vector)
        if not injected_variables:
            return adjusted
        pressure = min(18.0, sum(item.intensity_0_100 for item in injected_variables) / max(len(injected_variables), 1) / 6.0)
        adjusted["vulnerability_score"] = adjusted.get("vulnerability_score", 0.0) + pressure
        adjusted["exposure_score"] = adjusted.get("exposure_score", 0.0) + pressure * 0.8
        if any(item.type == "policy" for item in injected_variables):
            adjusted["service_capacity"] = adjusted.get("service_capacity", 0.0) + 4.0
            adjusted["public_trust"] = adjusted.get("public_trust", 0.0) + 2.0
        if node_family in {"EcologicalReceptor", "EnvironmentalCarrier"} and any(item.type == "disaster" for item in injected_variables):
            adjusted["ecosystem_integrity"] = adjusted.get("ecosystem_integrity", 0.0) - pressure * 0.7
            adjusted["spread_pressure"] = adjusted.get("spread_pressure", 0.0) + pressure
        return adjusted

    def _merge_text_items(self, existing: List[str], additions: List[str]) -> List[str]:
        merged = [str(item) for item in existing if item]
        for item in additions:
            text = str(item or "").strip()
            if text and text not in merged:
                merged.append(text)
        return merged[:6]

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
