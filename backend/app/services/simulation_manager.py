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

from ..config import Config
from ..utils.logger import get_logger
from ..utils.atomic_file import read_json_file, write_text_file
from ..models.task import TaskCancelledError
from .env_profile_generator import EnvProfileGenerator
from .effort_contract import (
    build_effort_snapshot,
    effort_operation_limit,
    normalize_effort_snapshot,
)
from .env_simulation_config_generator import (
    EnvSimulationConfigGenerator,
    build_mechanism_transport_profile,
    build_scenario_planner_display_projection,
    build_scenario_temporal_runtime_projection,
    normalize_search_mode,
)
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
from .mechanism_simulation_service import (
    LEGACY_SIMULATION_ARCHITECTURE,
    MechanismSimulationPlanner,
    is_llm_mechanism_architecture,
    normalize_simulation_architecture,
)
from .risk_artifact_store import write_risk_artifacts
from .risk_definition_builder import RiskDefinitionBuilder
from .risk_runtime_tracker import RiskRuntimeTracker
from .scenario_planning.agent_planner import AgentPlannerV2
from .workflow_artifacts import project_scenario_definition
from .zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader

logger = get_logger("envfish.simulation")


def _scenario_model_from_planning_input(
    scenario_planning_input: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Project the Step 2 planning artifact into the runtime scenario header.

    The EventMechanismGraph remains the authoritative mechanism payload.  This
    compact model only supplies the title/summary metadata expected by the
    existing runtime and report surfaces; it must never synthesize another
    mechanism graph.
    """

    planning = dict(scenario_planning_input or {})
    graph = dict(planning.get("event_mechanism_graph") or {})
    events = [
        dict(item)
        for item in (planning.get("normalized_user_events") or [])
        if isinstance(item, dict)
    ]
    titles = [str(item.get("name") or "").strip() for item in events]
    titles = [item for item in titles if item]
    descriptions = [str(item.get("description") or "").strip() for item in events]
    descriptions = [item for item in descriptions if item]
    core_processes = [
        str(item.get("label_zh") or "").strip()
        for item in (graph.get("nodes") or [])
        if isinstance(item, dict) and str(item.get("label_zh") or "").strip()
    ]
    model = {
        "architecture": str(planning.get("simulation_architecture") or "llm_mechanism_v1"),
        "source": "scenario_planner",
        "planning_input_id": str(planning.get("planning_input_id") or ""),
        "planning_content_hash": str(planning.get("content_hash") or ""),
        "event_mechanism_graph_id": str(graph.get("graph_id") or ""),
        "scenario_title": " → ".join(titles[:4]) or "Step 2 场景规划",
        "scenario_summary": "；".join(descriptions[:4]) or "场景由 Step 2 事件机制图定义。",
        "core_processes": list(dict.fromkeys(core_processes))[:16],
        "assumptions": list(planning.get("assumptions") or []),
        "temporal_plan": dict(planning.get("temporal_plan") or {}),
    }
    return dict(
        build_scenario_planner_display_projection(
            planning,
            scenario_model=model,
        )["scenario_model"]
    )


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
    simulation_architecture: str = LEGACY_SIMULATION_ARCHITECTURE
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
    temporal_plan: Dict[str, Any] = field(default_factory=dict)
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
    base_map_seed_id: Optional[str] = None
    effort_snapshot: Dict[str, Any] = field(default_factory=dict)
    semantic_artifact_ref: Dict[str, Any] = field(default_factory=dict)
    step1_suggestion_ref: Dict[str, Any] = field(default_factory=dict)
    resolved_foundation_ref: Dict[str, Any] = field(default_factory=dict)
    scenario_input_authority: str = ""
    planning_input_id: str = ""
    planning_content_hash: str = ""
    agent_plan_source: str = ""
    prepare_task_id: str = ""
    artifact_mode: str = "live"
    artifact_root: str = ""
    golden_case_id: str = ""
    golden_case_profile: str = ""
    is_replay_only: bool = False
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
            "simulation_architecture": self.simulation_architecture,
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
            "temporal_plan": self.temporal_plan,
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
            "base_map_seed_id": self.base_map_seed_id,
            "effort_snapshot": self.effort_snapshot,
            "semantic_artifact_ref": self.semantic_artifact_ref,
            "step1_suggestion_ref": self.step1_suggestion_ref,
            "resolved_foundation_ref": self.resolved_foundation_ref,
            "scenario_input_authority": self.scenario_input_authority,
            "planning_input_id": self.planning_input_id,
            "planning_content_hash": self.planning_content_hash,
            "agent_plan_source": self.agent_plan_source,
            "prepare_task_id": self.prepare_task_id,
            "artifact_mode": self.artifact_mode,
            "artifact_root": self.artifact_root,
            "golden_case_id": self.golden_case_id,
            "golden_case_profile": self.golden_case_profile,
            "is_replay_only": self.is_replay_only,
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
            "simulation_architecture": self.simulation_architecture,
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
            "temporal_plan": self.temporal_plan,
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
            "base_map_seed_id": self.base_map_seed_id,
            "effort_snapshot": self.effort_snapshot,
            "step1_suggestion_ref": self.step1_suggestion_ref,
            "resolved_foundation_ref": self.resolved_foundation_ref,
            "scenario_input_authority": self.scenario_input_authority,
            "planning_input_id": self.planning_input_id,
            "planning_content_hash": self.planning_content_hash,
            "agent_plan_source": self.agent_plan_source,
            "prepare_task_id": self.prepare_task_id,
            "artifact_mode": self.artifact_mode,
            "artifact_root": self.artifact_root,
            "golden_case_id": self.golden_case_id,
            "golden_case_profile": self.golden_case_profile,
            "is_replay_only": self.is_replay_only,
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

    def resolve_artifact_dir(
        self,
        simulation: Optional[SimulationState | str],
        *,
        create_if_missing: bool = False,
    ) -> Optional[str]:
        if isinstance(simulation, SimulationState):
            state = simulation
        elif simulation:
            state = self._load_simulation_state(str(simulation))
        else:
            state = None

        if state and str(state.artifact_mode or "live") == "frozen":
            artifact_root = str(state.artifact_root or "").strip()
            if artifact_root and os.path.exists(artifact_root):
                return artifact_root
            return artifact_root or None

        if not simulation:
            return None
        sim_id = state.simulation_id if state else str(simulation)
        if create_if_missing:
            return self._get_simulation_dir(sim_id)
        sim_dir = os.path.join(self.SIMULATION_DATA_DIR, sim_id)
        return sim_dir if os.path.exists(sim_dir) else None

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

        data = read_json_file(state_file, default=None)
        if not data:
            return None

        state = SimulationState(
            simulation_id=simulation_id,
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id", ""),
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
            engine_mode=data.get("engine_mode", ENVFISH_ENGINE_MODE),
            simulation_architecture=normalize_simulation_architecture(
                data.get("simulation_architecture", LEGACY_SIMULATION_ARCHITECTURE)
            ),
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
            temporal_plan=data.get("temporal_plan", {}),
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
            base_map_seed_id=data.get("base_map_seed_id") or data.get("map_seed_id"),
            effort_snapshot=normalize_effort_snapshot(
                data.get("effort_snapshot")
                or build_effort_snapshot(
                    "high",
                    effort_snapshot_id=f"effort_legacy_{simulation_id}",
                    locked_at=data.get("created_at") or datetime.now().isoformat(),
                )
            ),
            semantic_artifact_ref=dict(data.get("semantic_artifact_ref") or {}),
            step1_suggestion_ref=dict(data.get("step1_suggestion_ref") or {}),
            resolved_foundation_ref=dict(data.get("resolved_foundation_ref") or {}),
            scenario_input_authority=str(data.get("scenario_input_authority") or ""),
            planning_input_id=data.get("planning_input_id", ""),
            planning_content_hash=data.get("planning_content_hash", ""),
            agent_plan_source=data.get("agent_plan_source", ""),
            prepare_task_id=data.get("prepare_task_id", ""),
            artifact_mode=data.get("artifact_mode", "live"),
            artifact_root=data.get("artifact_root", ""),
            golden_case_id=data.get("golden_case_id", ""),
            golden_case_profile=data.get("golden_case_profile", ""),
            is_replay_only=bool(data.get("is_replay_only", False)),
            current_round=data.get("current_round", 0),
            twitter_status=data.get("twitter_status", "not_started"),
            reddit_status=data.get("reddit_status", "not_started"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )
        self._simulations[simulation_id] = state
        if not data.get("effort_snapshot"):
            self._save_simulation_state(state)
        return state

    def create_simulation(
        self,
        project_id: str,
        graph_id: str,
        enable_twitter: bool = True,
        enable_reddit: bool = True,
        engine_mode: str = ENVFISH_ENGINE_MODE,
        simulation_architecture: str = LEGACY_SIMULATION_ARCHITECTURE,
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
        effort_snapshot: Optional[Dict[str, Any]] = None,
        semantic_artifact_ref: Optional[Dict[str, Any]] = None,
        artifact_mode: str = "live",
        artifact_root: str = "",
        golden_case_id: str = "",
        golden_case_profile: str = "",
        is_replay_only: bool = False,
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
            simulation_architecture=normalize_simulation_architecture(simulation_architecture),
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
            base_map_seed_id=map_seed_id,
            effort_snapshot=normalize_effort_snapshot(effort_snapshot),
            semantic_artifact_ref=dict(semantic_artifact_ref or {}),
            step1_suggestion_ref=dict(semantic_artifact_ref or {}),
            artifact_mode=str(artifact_mode or "live"),
            artifact_root=str(artifact_root or ""),
            golden_case_id=str(golden_case_id or ""),
            golden_case_profile=str(golden_case_profile or ""),
            is_replay_only=bool(is_replay_only),
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
        target_agent_count: Optional[int] = None,
        search_profile_overrides: Optional[Dict[str, Any]] = None,
        simulation_architecture: str = LEGACY_SIMULATION_ARCHITECTURE,
        scenario_planning_input: Optional[Dict[str, Any]] = None,
        agent_plan_source: str = "",
    ) -> SimulationState:
        state = self._load_simulation_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")

        has_scenario_plan = bool(scenario_planning_input)
        authoritative_temporal_plan = dict(
            (scenario_planning_input or {}).get("temporal_plan") or {}
        )
        authoritative_mechanism_graph = dict(
            (scenario_planning_input or {}).get("event_mechanism_graph") or {}
        )
        authoritative_transport_profile: Dict[str, Any] = {}
        authoritative_time_config: Dict[str, Any] = {}
        if has_scenario_plan:
            if not authoritative_temporal_plan:
                raise ValueError("Step 2 场景规划缺少时间计划")
            normalized_family = "generic"
            normalized_time_plan, authoritative_temporal_profile, authoritative_time_config = (
                build_scenario_temporal_runtime_projection(
                    authoritative_temporal_plan,
                    reference_time=reference_time or state.reference_time,
                )
            )
            authoritative_transport_profile = build_mechanism_transport_profile(
                authoritative_mechanism_graph
            )
        else:
            normalized_family = normalize_transport_family(diffusion_template or state.diffusion_template)
            normalized_time_plan = normalize_time_plan(
                time_plan,
                total_rounds=(temporal_profile or {}).get("total_rounds") or state.configured_total_rounds,
                minutes_per_round=(temporal_profile or {}).get("minutes_per_round") or state.configured_minutes_per_round,
                preset=(temporal_profile or {}).get("preset") or state.temporal_preset,
                reference_time=reference_time or state.reference_time,
                source=time_plan_mode or state.time_plan_mode or "auto",
            )
            authoritative_temporal_profile = {}
        state.status = SimulationStatus.PREPARING
        state.scenario_mode = scenario_mode or state.scenario_mode
        state.simulation_architecture = normalize_simulation_architecture(
            simulation_architecture or state.simulation_architecture
        )
        state.diffusion_template = normalized_family
        state.hazard_template_id = hazard_template_id or state.hazard_template_id or default_hazard_template_for_family(normalized_family)
        state.hazard_template_mode = (
            "compatibility_projection"
            if has_scenario_plan
            else (hazard_template_mode or state.hazard_template_mode or "auto")
        )
        if has_scenario_plan:
            state.hazard_template_reasoning = (
                "兼容字段，仅供旧运行时识别；复合事件及传播路径以 Step 2 事件机制图为准。"
            )
            state.transport_profile = dict(authoritative_transport_profile)
        state.search_mode = normalize_search_mode(search_mode or state.search_mode)
        state.temporal_preset = str(normalized_time_plan.get("preset") or state.temporal_preset or "standard")
        state.configured_total_rounds = max(
            1 if has_scenario_plan else 4,
            int(normalized_time_plan.get("total_rounds") or state.configured_total_rounds or 12),
        )
        state.configured_minutes_per_round = max(10, int(normalized_time_plan.get("minutes_per_round") or state.configured_minutes_per_round or 60))
        state.time_plan_mode = (
            "scenario_planner"
            if has_scenario_plan
            else (time_plan_mode or state.time_plan_mode or "auto")
        )
        state.time_plan = normalized_time_plan
        state.temporal_plan = dict(authoritative_temporal_plan) if has_scenario_plan else {}
        state.reference_time = str(reference_time or state.reference_time or "")
        state.diffusion_provider = str(diffusion_provider or state.diffusion_provider or "auto")
        state.error = None
        self._save_simulation_state(state)

        try:
            sim_dir = self._get_simulation_dir(simulation_id)
            variables = [InjectedVariable.from_dict(item, default_index=index + 1) for index, item in enumerate(injected_variables or [])]
            state.active_variables_count = len(variables)
            dump_json(os.path.join(sim_dir, "injected_variables.json"), [variable.to_dict() for variable in variables])
            scenario_plan_path = os.path.join(sim_dir, "scenario_planning_input.json")
            if scenario_planning_input:
                dump_json(scenario_plan_path, scenario_planning_input)
            elif os.path.exists(scenario_plan_path):
                os.remove(scenario_plan_path)
            if progress_callback:
                progress_callback("reading", 5, "正在连接图谱")

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
                raise ValueError("图谱中没有可用于场景生成的实体")

            if progress_callback:
                progress_callback("reading", 100, f"已读取 {filtered.filtered_count} 个可用实体")

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

            # Thread the on-disk map-seed handle so the profile generator can
            # activate the disk-grounding path (PublicDataGroundingService.ground
            # / TransportContextResolver.resolve read the seed's WorldCover/OSM/
            # Open-Meteo artifacts and flip the grounding source to
            # ``map_seed_grounded``). Only set for real map-seed runs; otherwise
            # it stays None and generation behavior is unchanged.
            profile_map_seed_id = (
                state.map_seed_id if state.source_mode == "map_seed" else None
            )
            planned_agent_limit = int(
                effort_operation_limit(
                    state.effort_snapshot,
                    "step2",
                    "planned_agent_limit",
                )
            )
            relationship_candidates_per_agent = int(
                effort_operation_limit(
                    state.effort_snapshot,
                    "step2",
                    "relationship_candidates_per_agent",
                )
            )

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
                target_agent_count=target_agent_count,
                max_agent_count=planned_agent_limit,
                relationship_candidates_per_agent=relationship_candidates_per_agent,
                map_seed_id=profile_map_seed_id,
            )

            result.generation_summary = {
                **(result.generation_summary or {}),
                "effort_limits": {
                    "planned_agent_limit": planned_agent_limit,
                    "relationship_candidates_per_agent": relationship_candidates_per_agent,
                },
            }

            if agent_plan_source:
                result.generation_summary = {
                    **(result.generation_summary or {}),
                    "agent_plan_source": agent_plan_source,
                }

            state.profiles_count = len(result.profiles)
            state.region_count = len(result.regions)

            mechanism_artifacts = None
            has_scenario_plan = bool(scenario_planning_input)
            authoritative_mechanism_graph: Dict[str, Any] = {}
            authoritative_scenario_model: Dict[str, Any] = {}
            authoritative_agent_blueprints: List[Dict[str, Any]] = []
            authoritative_validated_relation_graph: Dict[str, Any] = {}
            authoritative_scenario_state_schema: Dict[str, Any] = {}
            authoritative_simulation_audit: Dict[str, Any] = {}
            agent_plan_artifact: Dict[str, Any] = {}
            agent_placement_plan: Dict[str, Any] = {}
            resolution_plan: Dict[str, Any] = {}
            policy_execution_plan: Dict[str, Any] = {}
            spatial_anchor_candidates: List[Dict[str, Any]] = []
            normalized_role_demands: List[Dict[str, Any]] = list(
                (scenario_planning_input or {}).get("role_demands") or []
            )
            agent_archetypes_v2: List[Dict[str, Any]] = []

            if has_scenario_plan:
                # Step 2's EventMechanismGraph is the sole scenario fact source.
                # The older mechanism planner used to run afterwards and replace
                # this graph with a second LLM-generated interpretation.  That
                # made config, risks and runtime disagree with the reviewed
                # Step 2 artifact, so a supplied plan now bypasses it entirely.
                authoritative_mechanism_graph = dict(
                    (scenario_planning_input or {}).get("event_mechanism_graph") or {}
                )
                authoritative_scenario_model = _scenario_model_from_planning_input(
                    scenario_planning_input
                )
                authoritative_simulation_audit = {
                    "mechanism_graph_source": "scenario_planner",
                    "temporal_plan_source": "scenario_planner",
                    "transport_plan_source": "event_mechanism_graph",
                    "hazard_template_role": "legacy_projection",
                    "propagation_media": list(
                        authoritative_transport_profile.get("propagation_media") or []
                    ),
                    "planning_input_id": str(
                        (scenario_planning_input or {}).get("planning_input_id") or ""
                    ),
                    "planning_content_hash": str(
                        (scenario_planning_input or {}).get("content_hash") or ""
                    ),
                    "legacy_mechanism_planner_used": False,
                    "说明": "配置、风险定义与运行时共同使用 Step 2 已审阅的事件机制图。",
                }
                dump_json(
                    os.path.join(sim_dir, "mechanism_graph.json"),
                    authoritative_mechanism_graph,
                )
                dump_json(
                    os.path.join(sim_dir, "temporal_plan.json"),
                    authoritative_temporal_plan,
                )
                dump_json(
                    os.path.join(sim_dir, "scenario_model.json"),
                    authoritative_scenario_model,
                )
                dump_json(
                    os.path.join(sim_dir, "simulation_audit.json"),
                    authoritative_simulation_audit,
                )
                result.generation_summary = {
                    **(result.generation_summary or {}),
                    "simulation_architecture": state.simulation_architecture,
                    "mechanism_graph_source": "scenario_planner",
                    "mechanism_node_count": len(
                        authoritative_mechanism_graph.get("nodes") or []
                    ),
                    "mechanism_edge_count": len(
                        authoritative_mechanism_graph.get("edges") or []
                    ),
                }

                if progress_callback:
                    progress_callback(
                        "generating_profiles",
                        92,
                        "正在匹配角色需求、空间锚点与代理体档案",
                    )
                agent_planning = AgentPlannerV2().plan(
                    candidate_profiles=result.profiles,
                    entities=filtered.entities,
                    regions=result.regions,
                    subregions=result.subregions,
                    role_demands=(scenario_planning_input or {}).get("role_demands") or [],
                    mechanism_graph=authoritative_mechanism_graph,
                    policy_plan=(scenario_planning_input or {}).get("policy_plan") or [],
                    effort_snapshot=state.effort_snapshot,
                    planning_input_ref=scenario_planning_input or {},
                )
                result.profiles = list(agent_planning.profiles)
                result.agent_relationships = list(agent_planning.relationships)
                result.region_agent_index = generator.rebuild_region_agent_index(
                    regions=result.regions,
                    subregions=result.subregions,
                    profiles=result.profiles,
                )
                result.generation_summary = {
                    **(result.generation_summary or {}),
                    **agent_planning.generation_summary,
                }
                authoritative_agent_blueprints = list(agent_planning.agent_archetypes)
                authoritative_validated_relation_graph = dict(
                    agent_planning.validated_relation_graph
                )
                agent_plan_artifact = dict(agent_planning.agent_plan)
                agent_placement_plan = dict(agent_planning.placement_plan)
                resolution_plan = dict(agent_planning.resolution_plan)
                policy_execution_plan = dict(agent_planning.policy_execution_plan)
                spatial_anchor_candidates = list(
                    agent_planning.spatial_anchor_candidates
                )
                normalized_role_demands = list(agent_planning.role_demands)
                agent_archetypes_v2 = list(agent_planning.agent_archetypes)
                agent_plan_source = "agent_v2"
                state.agent_plan_source = agent_plan_source
                state.profiles_count = len(result.profiles)
                authoritative_simulation_audit.update({
                    "agent_plan_source": agent_plan_source,
                    "agent_plan_id": str(agent_plan_artifact.get("agent_plan_id") or ""),
                    "agent_plan_contract_version": str(
                        agent_plan_artifact.get("contract_version") or ""
                    ),
                    "target_agent_count_used": False,
                    "policy_execution_summary": dict(
                        policy_execution_plan.get("summary") or {}
                    ),
                })
                dump_json(os.path.join(sim_dir, "agent_plan.json"), agent_plan_artifact)
                dump_json(
                    os.path.join(sim_dir, "agent_placement_plan.json"),
                    agent_placement_plan,
                )
                dump_json(os.path.join(sim_dir, "resolution_plan.json"), resolution_plan)
                dump_json(
                    os.path.join(sim_dir, "policy_execution_plan.json"),
                    policy_execution_plan,
                )
                dump_json(
                    os.path.join(sim_dir, "spatial_anchor_candidates.json"),
                    spatial_anchor_candidates,
                )
                dump_json(
                    os.path.join(sim_dir, "agent_archetypes_v2.json"),
                    agent_archetypes_v2,
                )
                dump_json(
                    os.path.join(sim_dir, "simulation_audit.json"),
                    authoritative_simulation_audit,
                )
            elif is_llm_mechanism_architecture(state.simulation_architecture):
                if progress_callback:
                    progress_callback("generating_config", 4, "正在识别场景机制...", current=1, total=4)
                mechanism_artifacts = MechanismSimulationPlanner().build_prepare_artifacts(
                    sim_dir=sim_dir,
                    simulation_id=simulation_id,
                    graph_id=state.graph_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    entities=filtered.entities,
                    regions=result.regions,
                    subregions=result.subregions,
                    profiles=result.profiles,
                    existing_relationships=result.agent_relationships,
                    scenario_mode=state.scenario_mode,
                    diffusion_template=state.diffusion_template,
                    hazard_template_id=state.hazard_template_id,
                    time_plan=state.time_plan,
                )
                result.agent_relationships = mechanism_artifacts.relation_edges
                result.generation_summary = {
                    **(result.generation_summary or {}),
                    "simulation_architecture": state.simulation_architecture,
                    "mechanism_node_count": len(mechanism_artifacts.mechanism_graph.get("nodes") or []),
                    "mechanism_edge_count": len(mechanism_artifacts.mechanism_graph.get("edges") or []),
                    "validated_relation_count": len(mechanism_artifacts.relation_edges),
                    "mechanism_fallback_used": bool(mechanism_artifacts.simulation_audit.get("fallback_used")),
                    "mechanism_quality_flags": list(mechanism_artifacts.simulation_audit.get("quality_flags") or []),
                }
                authoritative_mechanism_graph = dict(mechanism_artifacts.mechanism_graph or {})
                authoritative_scenario_model = dict(mechanism_artifacts.scenario_model or {})
                authoritative_agent_blueprints = list(mechanism_artifacts.agent_blueprints or [])
                authoritative_validated_relation_graph = dict(
                    mechanism_artifacts.validated_relation_graph or {}
                )
                authoritative_scenario_state_schema = dict(
                    mechanism_artifacts.scenario_state_schema or {}
                )
                authoritative_simulation_audit = dict(mechanism_artifacts.simulation_audit or {})

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
                risk_contract_version=Config.RISK_OBJECT_CONTRACT_VERSION,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                entities=filtered.entities,
                regions=result.regions,
                subregions=result.subregions,
                profiles=result.profiles,
                agent_relationships=result.agent_relationships,
                transport_edges=result.transport_edges,
                injected_variables=variables,
                scenario_mode=state.scenario_mode,
                diffusion_template=state.diffusion_template,
                hazard_template_id=state.hazard_template_id,
                temporal_profile={
                    "preset": state.temporal_preset,
                    "total_rounds": state.configured_total_rounds,
                    "minutes_per_round": state.configured_minutes_per_round,
                },
                mechanism_graph=authoritative_mechanism_graph,
                validated_relation_graph=authoritative_validated_relation_graph,
                scenario_state_schema=authoritative_scenario_state_schema,
                data_grounding_summary=result.grounding_summary,
                agent_plan=agent_plan_artifact,
                role_demands=normalized_role_demands,
                candidate_scan_limit=int(
                    effort_operation_limit(
                        state.effort_snapshot,
                        "step2",
                        "risk_candidate_scan_limit",
                    )
                ),
                max_active_risks=8,
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
                risk_contract_version=risk_result.risk_contract_version,
                generation_audit=risk_result.generation_audit,
                candidate_ledger=risk_result.candidate_ledger,
            )
            state.risk_objects_count = len(risk_artifacts["risk_objects"])
            state.primary_risk_object_id = (
                risk_artifacts["risk_objects_summary"].get("primary_risk_object_id")
                or risk_result.primary_risk_id
            )

            if progress_callback:
                progress_callback("generating_config", 10, "正在生成推演配置...", current=1, total=3)

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
                search_profile_overrides=search_profile_overrides,
                data_grounding_summary=result.grounding_summary,
                risk_definitions=risk_artifacts["risk_definitions"],
                risk_contract_version=risk_result.risk_contract_version,
                risk_generation_audit=risk_result.generation_audit,
                latest_risk_runtime_state=risk_artifacts["latest_risk_runtime_state"],
                risk_objects=risk_artifacts["risk_objects"],
                primary_risk_object_id=state.primary_risk_object_id,
                primary_active_risk_id=risk_artifacts["latest_risk_runtime_state"].get("primary_active_risk_id", ""),
                simulation_architecture=state.simulation_architecture,
                scenario_model=authoritative_scenario_model,
                mechanism_graph=authoritative_mechanism_graph,
                agent_blueprints=authoritative_agent_blueprints,
                validated_relation_graph=authoritative_validated_relation_graph,
                simulation_audit=authoritative_simulation_audit,
                scenario_state_schema=authoritative_scenario_state_schema,
                scenario_planning_input=scenario_planning_input,
            )
            # Keep the final persisted config pinned to the reviewed planning
            # artifact even if a legacy config generator applies defaults.
            config.scenario_model = dict(authoritative_scenario_model)
            config.mechanism_graph = dict(authoritative_mechanism_graph)
            config.agent_blueprints = list(authoritative_agent_blueprints)
            config.validated_relation_graph = dict(authoritative_validated_relation_graph)
            config.simulation_audit = dict(authoritative_simulation_audit)
            config.scenario_state_schema = dict(authoritative_scenario_state_schema)
            config.effort_snapshot = dict(state.effort_snapshot or {})
            config.scenario_planning_input = dict(scenario_planning_input or {})
            config.event_inputs = list((scenario_planning_input or {}).get("normalized_user_events") or [])
            config.policy_inputs = list((scenario_planning_input or {}).get("normalized_user_policies") or [])
            config.resolved_foundation_ref = dict(
                (scenario_planning_input or {}).get("resolved_foundation_ref")
                or (scenario_planning_input or {}).get("foundation_ref")
                or {}
            )
            config.step1_suggestion_ref = dict(
                (scenario_planning_input or {}).get("step1_suggestion_ref") or {}
            )
            config.scenario_input_authority = str(
                (scenario_planning_input or {}).get("input_authority") or ""
            )
            config.agent_plan_source = str(agent_plan_source or "")
            config.agent_plan_contract_version = str(
                agent_plan_artifact.get("contract_version") or ""
            )
            config.agent_plan = dict(agent_plan_artifact)
            config.agent_placement_plan = dict(agent_placement_plan)
            config.resolution_plan = dict(resolution_plan)
            config.spatial_anchor_candidates = list(spatial_anchor_candidates)
            config.role_demands = list(normalized_role_demands)
            if agent_archetypes_v2:
                config.agent_archetypes = list(agent_archetypes_v2)
            config.policy_plan = list((scenario_planning_input or {}).get("policy_plan") or [])
            config.policy_execution_plan = dict(policy_execution_plan)
            if has_scenario_plan:
                config.temporal_plan = dict(authoritative_temporal_plan)
                config.time_plan = dict(normalized_time_plan)
                config.temporal_profile = dict(authoritative_temporal_profile)
                config.time_config = dict(authoritative_time_config)
                config.time_plan_mode = "scenario_planner"
                config.transport_profile = dict(authoritative_transport_profile)
                config.diffusion_template = "generic"
                config.hazard_template_mode = "compatibility_projection"
                config.hazard_template_reasoning = state.hazard_template_reasoning
                config.hazard_template_recommendation = {
                    "hazard_template_id": config.hazard_template_id,
                    "authoritative": False,
                    "projection_only": True,
                    "mechanism_graph_id": str(
                        authoritative_mechanism_graph.get("graph_id") or ""
                    ),
                    "propagation_media": list(
                        authoritative_transport_profile.get("propagation_media") or []
                    ),
                    "reasoning_summary": state.hazard_template_reasoning,
                }
                config.round_policies = {
                    **dict(config.round_policies or {}),
                    "diffusion_decay": authoritative_transport_profile.get("default_decay", 0.88),
                    "default_lag_rounds": authoritative_transport_profile.get("default_lag_rounds", 1),
                    "default_persistence": authoritative_transport_profile.get("default_persistence", 55),
                    "max_neighbor_spread": authoritative_transport_profile.get("max_neighbor_spread", 2),
                }

            config.scenario_definition = project_scenario_definition(
                scenario_planning_input,
                config.to_dict(),
            )
            dump_json(
                os.path.join(sim_dir, "scenario_definition.json"),
                config.scenario_definition,
            )
            dump_json(
                os.path.join(sim_dir, "background_foundation.json"),
                config.scenario_definition.get("foundation_ref") or {},
            )

            if progress_callback:
                progress_callback("generating_config", 70, "正在保存推演配置", current=2, total=3)

            write_text_file(os.path.join(sim_dir, "simulation_config.json"), config.to_json())

            state.config_generated = True
            state.config_reasoning = config.generation_reasoning
            state.simulation_architecture = config.simulation_architecture or state.simulation_architecture
            state.hazard_template_id = config.hazard_template_id or state.hazard_template_id
            state.hazard_template_mode = config.hazard_template_mode or state.hazard_template_mode
            state.hazard_template_reasoning = config.hazard_template_reasoning or state.hazard_template_reasoning
            state.transport_profile = dict(config.transport_profile or {})
            state.temporal_preset = config.temporal_profile.get("preset", state.temporal_preset)
            state.configured_total_rounds = int(config.temporal_profile.get("total_rounds", state.configured_total_rounds))
            state.configured_minutes_per_round = int(config.temporal_profile.get("minutes_per_round", state.configured_minutes_per_round))
            state.time_plan_mode = config.time_plan_mode or state.time_plan_mode
            state.time_plan = dict(config.time_plan or state.time_plan)
            state.temporal_plan = dict(config.temporal_plan or state.temporal_plan)
            state.diffusion_template = config.diffusion_template or state.diffusion_template
            state.planning_input_id = str((scenario_planning_input or {}).get("planning_input_id") or "")
            state.planning_content_hash = str((scenario_planning_input or {}).get("content_hash") or "")
            state.resolved_foundation_ref = dict(config.resolved_foundation_ref or {})
            state.step1_suggestion_ref = dict(config.step1_suggestion_ref or {})
            state.scenario_input_authority = str(config.scenario_input_authority or "")
            state.agent_plan_source = str(agent_plan_source or "")
            state.status = SimulationStatus.READY
            state.error = None

            if progress_callback:
                progress_callback("generating_config", 100, "推演配置已生成", current=3, total=3)

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
            raise ValueError(f"地图种子缺少图谱快照: {map_seed_id}")

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
            raise ValueError(f"模拟不存在: {simulation_id}")

        sim_dir = self.resolve_artifact_dir(state, create_if_missing=False)
        if not sim_dir:
            return []
        if platform == "envfish":
            json_path = os.path.join(sim_dir, "profiles_full.json")
            if not os.path.exists(json_path):
                return []
            return read_json_file(json_path, default=[])
        if platform == "twitter":
            csv_path = os.path.join(sim_dir, "twitter_profiles.csv")
            if not os.path.exists(csv_path):
                return []
            with open(csv_path, "r", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))

        json_path = os.path.join(sim_dir, "reddit_profiles.json")
        if not os.path.exists(json_path):
            return []
        return read_json_file(json_path, default=[])

    def get_simulation_config(self, simulation_id: str) -> Optional[Dict[str, Any]]:
        state = self._load_simulation_state(simulation_id)
        sim_dir = self.resolve_artifact_dir(state or simulation_id, create_if_missing=False)
        if not sim_dir:
            return None
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            return None
        config = read_json_file(config_path, default=None)
        if isinstance(config, dict) and not config.get("scenario_definition"):
            planning_input = config.get("scenario_planning_input")
            if isinstance(planning_input, dict) and planning_input:
                config["scenario_definition"] = project_scenario_definition(planning_input, config)
        return config

    def get_run_instructions(self, simulation_id: str) -> Dict[str, str]:
        state = self._load_simulation_state(simulation_id)
        if state and state.is_replay_only:
            sim_dir = self.resolve_artifact_dir(state, create_if_missing=False) or ""
            return {
                "simulation_dir": sim_dir,
                "scripts_dir": "",
                "config_file": os.path.join(sim_dir, "simulation_config.json") if sim_dir else "",
                "commands": {},
                "instructions": "This simulation is replay-only and reads from frozen artifacts. No runner command is required.",
            }

        sim_dir = self.resolve_artifact_dir(state or simulation_id, create_if_missing=True) or self._get_simulation_dir(simulation_id)
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
