"""
EnvFish simulation manager.

Keeps the original file-backed state layout but prepares EnvFish-specific
profiles, region graphs, and simulation configs.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from ..models.task import TaskCancelledError
from .env_profile_generator import EnvProfileGenerator
from .env_simulation_config_generator import EnvSimulationConfigGenerator, normalize_search_mode
from .envfish_models import (
    ENVFISH_ENGINE_MODE,
    InjectedVariable,
    build_transport_profile,
    default_hazard_template_for_family,
    normalize_time_plan,
    normalize_transport_family,
    dump_json,
    write_profiles_csv,
)
from .map_seed_manager import MapSeedManager
from .risk_artifact_store import write_risk_artifacts
from .risk_definition_builder import RiskDefinitionBuilder
from .risk_runtime_tracker import RiskRuntimeTracker
from .zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader

logger = get_logger("envfish.simulation")


class SimulationStatus(str, Enum):
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


class PlatformType(str, Enum):
    TWITTER = "twitter"
    REDDIT = "reddit"


@dataclass
class SimulationState:
    simulation_id: str
    project_id: str
    graph_id: str
    enable_twitter: bool = True
    enable_reddit: bool = True
    engine_mode: str = ENVFISH_ENGINE_MODE
    scenario_mode: str = "baseline_mode"
    diffusion_template: str = "marine"
    hazard_template_id: str = "generic"
    hazard_template_mode: str = "auto"
    hazard_template_reasoning: str = ""
    transport_profile: Dict[str, Any] = field(default_factory=dict)
    search_mode: str = "fast"
    temporal_preset: str = "standard"
    configured_total_rounds: int = 12
    configured_minutes_per_round: int = 60
    time_plan_mode: str = "auto"
    time_plan: Dict[str, Any] = field(default_factory=dict)
    reference_time: str = ""
    diffusion_provider: str = "auto"
    status: SimulationStatus = SimulationStatus.CREATED
    entities_count: int = 0
    profiles_count: int = 0
    region_count: int = 0
    active_variables_count: int = 0
    risk_objects_count: int = 0
    entity_types: List[str] = field(default_factory=list)
    config_generated: bool = False
    config_reasoning: str = ""
    primary_risk_object_id: str = ""
    source_mode: str = "graph"
    map_seed_id: Optional[str] = None
    current_round: int = 0
    twitter_status: str = "not_started"
    reddit_status: str = "not_started"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "enable_twitter": self.enable_twitter,
            "enable_reddit": self.enable_reddit,
            "engine_mode": self.engine_mode,
            "scenario_mode": self.scenario_mode,
            "diffusion_template": self.diffusion_template,
            "hazard_template_id": self.hazard_template_id,
            "hazard_template_mode": self.hazard_template_mode,
            "hazard_template_reasoning": self.hazard_template_reasoning,
            "transport_profile": self.transport_profile,
            "search_mode": self.search_mode,
            "temporal_preset": self.temporal_preset,
            "configured_total_rounds": self.configured_total_rounds,
            "configured_minutes_per_round": self.configured_minutes_per_round,
            "time_plan_mode": self.time_plan_mode,
            "time_plan": self.time_plan,
            "reference_time": self.reference_time,
            "diffusion_provider": self.diffusion_provider,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "region_count": self.region_count,
            "active_variables_count": self.active_variables_count,
            "risk_objects_count": self.risk_objects_count,
            "entity_types": self.entity_types,
            "config_generated": self.config_generated,
            "config_reasoning": self.config_reasoning,
            "primary_risk_object_id": self.primary_risk_object_id,
            "source_mode": self.source_mode,
            "map_seed_id": self.map_seed_id,
            "current_round": self.current_round,
            "twitter_status": self.twitter_status,
            "reddit_status": self.reddit_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    def to_simple_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "engine_mode": self.engine_mode,
            "scenario_mode": self.scenario_mode,
            "diffusion_template": self.diffusion_template,
            "hazard_template_id": self.hazard_template_id,
            "hazard_template_mode": self.hazard_template_mode,
            "transport_profile": self.transport_profile,
            "search_mode": self.search_mode,
            "temporal_preset": self.temporal_preset,
            "configured_total_rounds": self.configured_total_rounds,
            "configured_minutes_per_round": self.configured_minutes_per_round,
            "time_plan_mode": self.time_plan_mode,
            "time_plan": self.time_plan,
            "reference_time": self.reference_time,
            "diffusion_provider": self.diffusion_provider,
            "status": self.status.value,
            "entities_count": self.entities_count,
            "profiles_count": self.profiles_count,
            "region_count": self.region_count,
            "risk_objects_count": self.risk_objects_count,
            "config_generated": self.config_generated,
            "primary_risk_object_id": self.primary_risk_object_id,
            "source_mode": self.source_mode,
            "map_seed_id": self.map_seed_id,
            "error": self.error,
        }


class SimulationManager:
    SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), "../../uploads/simulations")

    def __init__(self):
        os.makedirs(self.SIMULATION_DATA_DIR, exist_ok=True)
        self._simulations: Dict[str, SimulationState] = {}

    def _get_simulation_dir(self, simulation_id: str) -> str:
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        return sim_dir

    def _save_simulation_state(self, state: SimulationState):
        sim_dir = self._get_simulation_dir(state.simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        state.updated_at = datetime.now().isoformat()
        dump_json(state_file, state.to_dict())
        self._simulations[state.simulation_id] = state

    def _load_simulation_state(self, simulation_id: str) -> Optional[SimulationState]:
        if simulation_id in self._simulations:
            return self._simulations[simulation_id]

        sim_dir = self._get_simulation_dir(simulation_id)
        state_file = os.path.join(sim_dir, "state.json")
        if not os.path.exists(state_file):
            return None

        with open(state_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            engine_mode=data.get("engine_mode", ENVFISH_ENGINE_MODE),
            scenario_mode=data.get("scenario_mode", "baseline_mode"),
            diffusion_template=data.get("diffusion_template", "marine"),
            hazard_template_id=data.get("hazard_template_id", default_hazard_template_for_family(data.get("diffusion_template"))),
            hazard_template_mode=data.get("hazard_template_mode", "auto"),
            hazard_template_reasoning=data.get("hazard_template_reasoning", ""),
            transport_profile=data.get("transport_profile", {}),
            search_mode=normalize_search_mode(data.get("search_mode", "fast")),
            temporal_preset=data.get("temporal_preset", "standard"),
            configured_total_rounds=data.get("configured_total_rounds", 12),
            configured_minutes_per_round=data.get("configured_minutes_per_round", 60),
            time_plan_mode=data.get("time_plan_mode", "auto"),
            time_plan=data.get("time_plan", {}),
            reference_time=data.get("reference_time", ""),
            diffusion_provider=data.get("diffusion_provider", "auto"),
            status=SimulationStatus(data.get("status", "created")),
            entities_count=data.get("entities_count", 0),
            profiles_count=data.get("profiles_count", 0),
            region_count=data.get("region_count", 0),
            active_variables_count=data.get("active_variables_count", 0),
            risk_objects_count=data.get("risk_objects_count", 0),
            entity_types=data.get("entity_types", []),
            config_generated=data.get("config_generated", False),
            config_reasoning=data.get("config_reasoning", ""),
            primary_risk_object_id=data.get("primary_risk_object_id", ""),
            source_mode=data.get("source_mode", "graph"),
            map_seed_id=data.get("map_seed_id"),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        self._simulations[simulation_id] = state
        return state

    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        engine_mode: str = ENVFISH_ENGINE_MODE,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        hazard_template_id: str = "",
        search_mode: str = "fast",
        temporal_preset: str = "standard",
        configured_total_rounds: int = 12,
        configured_minutes_per_round: int = 60,
        time_plan_mode: str = "auto",
        time_plan: Optional[Dict[str, Any]] = None,
        reference_time: str = "",
        diffusion_provider: str = "auto",
        source_mode: str = "graph",
        map_seed_id: Optional[str] = None,
    ) -> SimulationState:
        import uuid

        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        normalized_family = normalize_transport_family(diffusion_template)
        normalized_time_plan = normalize_time_plan(
            time_plan,
            total_rounds=configured_total_rounds,
            minutes_per_round=configured_minutes_per_round,
            preset=temporal_preset,
            reference_time=reference_time,
            source=time_plan_mode or "auto",
        )
        state = SimulationState(
            simulation_id=simulation_id,
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=enable_twitter,
            enable_reddit=enable_reddit,
            engine_mode=engine_mode or ENVFISH_ENGINE_MODE,
            scenario_mode=scenario_mode or "baseline_mode",
            diffusion_template=normalized_family,
            hazard_template_id=hazard_template_id or default_hazard_template_for_family(normalized_family),
            transport_profile=build_transport_profile(normalized_family),
            time_plan_mode=time_plan_mode or "auto",
            time_plan=normalized_time_plan,
            search_mode=normalize_search_mode(search_mode),
            temporal_preset=normalized_time_plan.get("preset", temporal_preset or "standard"),
            configured_total_rounds=max(4, int(normalized_time_plan.get("total_rounds") or configured_total_rounds or 12)),
            configured_minutes_per_round=max(10, int(normalized_time_plan.get("minutes_per_round") or configured_minutes_per_round or 60)),
            reference_time=str(reference_time or ""),
            diffusion_provider=diffusion_provider or "auto",
            source_mode=source_mode or "graph",
            map_seed_id=map_seed_id,
        )
        self._save_simulation_state(state)
        logger.info(f"Created simulation {simulation_id} for project={project_id}, graph={graph_id}")
        return state

    def prepare_simulation(
        self,
        simulation_id: str,
        simulation_requirement: str,
        document_text: str,
        defined_entity_types: Optional[List[str]] = None,
        use_llm_for_profiles: bool = True,
        progress_callback: Optional[callable] = None,
        parallel_profile_count: int = 3,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        hazard_template_id: str = "",
        hazard_template_mode: str = "auto",
        search_mode: str = "fast",
        temporal_profile: Optional[Dict[str, Any]] = None,
        time_plan_mode: str = "auto",
        time_plan: Optional[Dict[str, Any]] = None,
        reference_time: str = "",
        diffusion_provider: str = "auto",
        injected_variables: Optional[List[Dict[str, Any]]] = None,
    ) -> SimulationState:
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation not found: {simulation_id}")

        normalized_family = normalize_transport_family(diffusion_template or state.diffusion_template)
        normalized_time_plan = normalize_time_plan(
            time_plan,
            total_rounds=(temporal_profile or {}).get("total_rounds") or state.configured_total_rounds,
            minutes_per_round=(temporal_profile or {}).get("minutes_per_round") or state.configured_minutes_per_round,
            preset=(temporal_profile or {}).get("preset") or state.temporal_preset,
            reference_time=reference_time or state.reference_time,
            source=time_plan_mode or state.time_plan_mode or "auto",
        )
        state.status = SimulationStatus.PREPARING
        state.scenario_mode = scenario_mode or state.scenario_mode
        state.diffusion_template = normalized_family
        state.hazard_template_id = hazard_template_id or state.hazard_template_id or default_hazard_template_for_family(normalized_family)
        state.hazard_template_mode = hazard_template_mode or state.hazard_template_mode or "auto"
        state.search_mode = normalize_search_mode(search_mode or state.search_mode)
        state.temporal_preset = str(normalized_time_plan.get("preset") or state.temporal_preset or "standard")
        state.configured_total_rounds = max(4, int(normalized_time_plan.get("total_rounds") or state.configured_total_rounds or 12))
        state.configured_minutes_per_round = max(10, int(normalized_time_plan.get("minutes_per_round") or state.configured_minutes_per_round or 60))
        state.time_plan_mode = time_plan_mode or state.time_plan_mode or "auto"
        state.time_plan = normalized_time_plan
        state.reference_time = str(reference_time or state.reference_time or "")
        state.diffusion_provider = str(diffusion_provider or state.diffusion_provider or "auto")
        state.error = None
        self._save_simulation_state(state)

        try:
            sim_dir = self._get_simulation_dir(simulation_id)
            variables = [InjectedVariable.from_dict(item, default_index=index + 1) for index, item in enumerate(injected_variables or [])]
            state.active_variables_count = len(variables)
            dump_json(os.path.join(sim_dir, "injected_variables.json"), [variable.to_dict() for variable in variables])
            if progress_callback:
                progress_callback("reading", 5, "Connecting to graph...")

            if state.source_mode == "map_seed" and state.map_seed_id:
                filtered = self._load_map_seed_entities(state.map_seed_id, defined_entity_types)
            else:
                reader = ZepEntityReader()
                filtered = reader.filter_defined_entities(
                    graph_id=state.graph_id,
                    defined_entity_types=defined_entity_types,
                    enrich_with_edges=True,
                )

            state.entities_count = filtered.filtered_count
            state.entity_types = list(filtered.entity_types)
            self._save_simulation_state(state)

            if filtered.filtered_count == 0:
                raise ValueError("No usable entities found in the graph.")

            if progress_callback:
                progress_callback("reading", 100, f"Loaded {filtered.filtered_count} entities")

            generator = EnvProfileGenerator()
            profiles_full_path = os.path.join(sim_dir, "profiles_full.json")
            incremental_profiles: List[Dict[str, Any]] = []
            dump_json(profiles_full_path, incremental_profiles)

            def profile_progress(current: int, total: int, message: str):
                if progress_callback:
                    percent = int(current / max(total, 1) * 100)
                    progress_callback(
                        "generating_profiles",
                        percent,
                        message,
                        current=current,
                        total=total,
                        item_name=message,
                    )

            def profile_created(profile, generated_count: int, target_count: int, stage: str):
                del generated_count, target_count, stage
                incremental_profiles.append(profile.to_dict())
                dump_json(profiles_full_path, incremental_profiles)
                state.profiles_count = len(incremental_profiles)
                self._save_simulation_state(state)

            result = generator.generate_from_entities(
                entities=filtered.entities,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                scenario_mode=state.scenario_mode,
                diffusion_template=state.diffusion_template,
                search_mode=state.search_mode,
                reference_time=state.reference_time,
                diffusion_provider=state.diffusion_provider,
                injected_variables=variables,
                use_llm=use_llm_for_profiles,
                progress_callback=profile_progress,
                profile_created_callback=profile_created,
                parallel_count=parallel_profile_count,
            )

            state.profiles_count = len(result.profiles)
            state.region_count = len(result.regions)

            dump_json(os.path.join(sim_dir, "region_graph_snapshot.json"), [region.to_dict() for region in result.regions])
            dump_json(os.path.join(sim_dir, "subregion_graph_snapshot.json"), [region.to_dict() for region in result.subregions])
            dump_json(os.path.join(sim_dir, "grounding_summary.json"), result.grounding_summary)
            dump_json(os.path.join(sim_dir, "transport_edges.json"), [edge.to_dict() for edge in result.transport_edges])
            dump_json(os.path.join(sim_dir, "diffusion_context.json"), result.diffusion_context)
            dump_json(profiles_full_path, [profile.to_dict() for profile in result.profiles])
            dump_json(os.path.join(sim_dir, "agent_relationship_graph.json"), [edge.to_dict() for edge in result.agent_relationships])
            dump_json(os.path.join(sim_dir, "region_agent_index.json"), result.region_agent_index)
            dump_json(os.path.join(sim_dir, "agent_generation_summary.json"), result.generation_summary)

            reddit_profiles = [profile.to_reddit_format() for profile in result.profiles]
            twitter_profiles = [profile.to_twitter_format() for profile in result.profiles]
            dump_json(os.path.join(sim_dir, "reddit_profiles.json"), reddit_profiles)
            write_profiles_csv(os.path.join(sim_dir, "twitter_profiles.csv"), twitter_profiles)

            risk_builder = RiskDefinitionBuilder()
            risk_result = risk_builder.build(
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                regions=result.regions,
                profiles=result.profiles,
                injected_variables=variables,
                scenario_mode=state.scenario_mode,
                diffusion_template=state.diffusion_template,
                hazard_template_id=state.hazard_template_id,
            )
            runtime_tracker = RiskRuntimeTracker()
            latest_risk_runtime_state = runtime_tracker.build_initial_bundle(
                risk_definitions=risk_result.risk_definitions,
                primary_risk_id=risk_result.primary_risk_id,
            )
            risk_artifacts = write_risk_artifacts(
                sim_dir=sim_dir,
                risk_definitions=risk_result.risk_definitions,
                latest_runtime_bundle=latest_risk_runtime_state,
                primary_risk_id=risk_result.primary_risk_id,
                generation_notes=risk_result.generation_notes,
                risk_events=[],
                rewrite_runtime_history=[latest_risk_runtime_state],
            )
            state.risk_objects_count = len(risk_artifacts["risk_objects"])
            state.primary_risk_object_id = (
                risk_artifacts["risk_objects_summary"].get("primary_risk_object_id")
                or risk_result.primary_risk_id
            )

            if progress_callback:
                progress_callback("generating_config", 10, "Synthesizing EnvFish config...", current=1, total=3)

            config_generator = EnvSimulationConfigGenerator()
            config = config_generator.generate_config(
                simulation_id=simulation_id,
                project_id=state.project_id,
                graph_id=state.graph_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                regions=result.regions,
                subregions=result.subregions,
                transport_edges=result.transport_edges,
                profiles=result.profiles,
                agent_relationships=result.agent_relationships,
                region_agent_index=result.region_agent_index,
                agent_generation_summary=result.generation_summary,
                scenario_mode=state.scenario_mode,
                diffusion_template=state.diffusion_template,
                hazard_template_id=state.hazard_template_id,
                hazard_template_mode=state.hazard_template_mode,
                search_mode=state.search_mode,
                temporal_profile={
                    "preset": state.temporal_preset,
                    "total_rounds": state.configured_total_rounds,
                    "minutes_per_round": state.configured_minutes_per_round,
                },
                time_plan_mode=state.time_plan_mode,
                time_plan=state.time_plan,
                reference_time=state.reference_time,
                diffusion_context=result.diffusion_context,
                injected_variables=variables,
                data_grounding_summary=result.grounding_summary,
                risk_definitions=risk_artifacts["risk_definitions"],
                latest_risk_runtime_state=risk_artifacts["latest_risk_runtime_state"],
                risk_objects=risk_artifacts["risk_objects"],
                primary_risk_object_id=state.primary_risk_object_id,
                primary_active_risk_id=risk_artifacts["latest_risk_runtime_state"].get("primary_active_risk_id", ""),
            )

            if progress_callback:
                progress_callback("generating_config", 70, "Saving simulation config...", current=2, total=3)

            with open(os.path.join(sim_dir, "simulation_config.json"), "w", encoding="utf-8") as handle:
                handle.write(config.to_json())

            state.config_generated = True
            state.config_reasoning = config.generation_reasoning
            state.hazard_template_id = config.hazard_template_id or state.hazard_template_id
            state.hazard_template_mode = config.hazard_template_mode or state.hazard_template_mode
            state.hazard_template_reasoning = config.hazard_template_reasoning or state.hazard_template_reasoning
            state.transport_profile = dict(config.transport_profile or {})
            state.temporal_preset = config.temporal_profile.get("preset", state.temporal_preset)
            state.configured_total_rounds = int(config.temporal_profile.get("total_rounds", state.configured_total_rounds))
            state.configured_minutes_per_round = int(config.temporal_profile.get("minutes_per_round", state.configured_minutes_per_round))
            state.time_plan_mode = config.time_plan_mode or state.time_plan_mode
            state.time_plan = dict(config.time_plan or state.time_plan)
            state.diffusion_template = config.diffusion_template or state.diffusion_template
            state.status = SimulationStatus.READY
            state.error = None

            if progress_callback:
                progress_callback("generating_config", 100, "EnvFish config ready", current=3, total=3)

            self._save_simulation_state(state)
            logger.info(
                f"Prepared EnvFish simulation {simulation_id}: entities={state.entities_count}, "
                f"profiles={state.profiles_count}, regions={state.region_count}"
            )
            return state

        except TaskCancelledError as exc:
            logger.info(f"Simulation prepare cancelled: {simulation_id}")
            state.status = SimulationStatus.STOPPED
            state.error = str(exc)
            self._save_simulation_state(state)
            raise
        except Exception as exc:
            logger.exception(f"Simulation prepare failed: {simulation_id}")
            state.status = SimulationStatus.FAILED
            state.error = str(exc)
            self._save_simulation_state(state)
            raise

    def _load_map_seed_entities(
        self,
        map_seed_id: str,
        defined_entity_types: Optional[List[str]] = None,
    ) -> FilteredEntities:
        graph_snapshot = MapSeedManager.get_graph_snapshot(map_seed_id)
        if not graph_snapshot:
            raise ValueError(f"Map seed graph snapshot missing: {map_seed_id}")

        graph_data = graph_snapshot.get("graph_data") or graph_snapshot
        nodes = list(graph_data.get("nodes") or [])
        edges = list(graph_data.get("edges") or [])
        node_lookup = {node.get("uuid"): node for node in nodes if node.get("uuid")}
        filtered_entities: List[EntityNode] = []
        entity_types = set()

        for node in nodes:
            labels = list(node.get("labels") or [])
            custom_labels = [label for label in labels if label not in ["Entity", "Node"]]
            if not custom_labels:
                continue
            entity_type = custom_labels[0]
            if defined_entity_types and entity_type not in defined_entity_types:
                continue

            related_edges = []
            related_nodes = []
            for edge in edges:
                source_uuid = edge.get("source_node_uuid")
                target_uuid = edge.get("target_node_uuid")
                if node.get("uuid") not in {source_uuid, target_uuid}:
                    continue
                related_edges.append(
                    {
                        "uuid": edge.get("uuid", ""),
                        "name": edge.get("name", ""),
                        "fact": edge.get("fact", ""),
                        "source_node_uuid": source_uuid,
                        "target_node_uuid": target_uuid,
                        "attributes": edge.get("attributes") or {},
                    }
                )
                other_uuid = target_uuid if source_uuid == node.get("uuid") else source_uuid
                other_node = node_lookup.get(other_uuid)
                if not other_node:
                    continue
                other_labels = [label for label in (other_node.get("labels") or []) if label not in ["Entity", "Node"]]
                related_nodes.append(
                    {
                        "uuid": other_node.get("uuid", ""),
                        "name": other_node.get("name", ""),
                        "entity_type": other_labels[0] if other_labels else "Entity",
                        "summary": other_node.get("summary", ""),
                    }
                )

            filtered_entities.append(
                EntityNode(
                    uuid=node.get("uuid", ""),
                    name=node.get("name", ""),
                    labels=labels,
                    summary=node.get("summary", ""),
                    attributes=node.get("attributes") or {},
                    related_edges=related_edges,
                    related_nodes=related_nodes[:8],
                )
            )
            entity_types.add(entity_type)

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types,
            total_count=len(nodes),
            filtered_count=len(filtered_entities),
        )

    def get_simulation(self, simulation_id: str) -> Optional[SimulationState]:
        return self._load_simulation_state(simulation_id)

    def list_simulations(self, project_id: Optional[str] = None) -> List[SimulationState]:
        simulations: List[SimulationState] = []
        if os.path.exists(self.SIMULATION_DATA_DIR):
            for sim_id in os.listdir(self.SIMULATION_DATA_DIR):
                sim_path = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
                if sim_id.startswith(".") or not os.path.isdir(sim_path):
                    continue
                state = self._load_simulation_state(sim_id)
                if state and (project_id is None or state.project_id == project_id):
                    simulations.append(state)
        simulations.sort(
            key=lambda item: (
                str(item.created_at or ""),
                str(item.updated_at or ""),
                str(item.simulation_id or ""),
            ),
            reverse=True,
        )
        return simulations

    def get_profiles(self, simulation_id: str, platform: str = "reddit") -> List[Dict[str, Any]]:
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"Simulation not found: {simulation_id}")

        sim_dir = self._get_simulation_dir(simulation_id)
        if platform == "envfish":
            json_path = os.path.join(sim_dir, "profiles_full.json")
            if not os.path.exists(json_path):
                return []
            with open(json_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        if platform == "twitter":
            csv_path = os.path.join(sim_dir, "twitter_profiles.csv")
            if not os.path.exists(csv_path):
                return []
            with open(csv_path, "r", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))

        json_path = os.path.join(sim_dir, "reddit_profiles.json")
        if not os.path.exists(json_path):
            return []
        with open(json_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            return None
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        sim_dir = self._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))
        envfish_cmd = f"python {scripts_dir}/run_envfish_simulation.py --config {config_path}"
        return {
            "simulation_dir": sim_dir,
            "scripts_dir": scripts_dir,
            "config_file": config_path,
            "commands": {
                "parallel": envfish_cmd,
                "twitter": envfish_cmd,
                "reddit": envfish_cmd,
            },
            "instructions": (
                f"1. Activate the backend environment.\n"
                f"2. Run EnvFish: {envfish_cmd}"
            ),
        }
