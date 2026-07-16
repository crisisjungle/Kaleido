"""
Golden case registry, scaffold builder, and frozen artifact restore.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..utils.logger import get_logger
from .effort_contract import build_effort_snapshot
from .envfish_models import normalize_time_plan
from .report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
from .scenario_planner import (
    LEGACY_AGENT_PLAN_SOURCE,
    SIMULATION_ARCHITECTURE,
    LegacyAgentPlanningAdapter,
    ScenarioPlanner,
)
from .simulation_manager import SimulationManager, SimulationStatus
from .spatial_evidence import (
    build_spatial_refinement_snapshot,
    compile_facility_query_plan,
)
from .wuhan_showcase_builder import (
    WUHAN_V2_ARTIFACT_CONTRACT_VERSION,
    WUHAN_V2_CASE_ID,
    WUHAN_V2_SPATIAL_FIXTURE_ID,
    WUHAN_V2_SPATIAL_GROUNDING,
    WuhanShowcaseBuilder,
)

logger = get_logger("envfish.golden_case")

WUHAN_CASE_ID = "wuhan_covid_v1"
WUHAN_REFERENCE_TIME = "2019-12-22T00:00:00+08:00"
WUHAN_TOTAL_ROUNDS = 36
WUHAN_MINUTES_PER_ROUND = 4320
WUHAN_SPATIAL_FIXTURE_ID = "golden_spatial_fixture::wuhan_covid_v1"
WUHAN_SPATIAL_GROUNDING = "curated_deterministic_fixture"
WUHAN_ARTIFACT_CONTRACT_VERSION = (
    "2026-07-15.semantic-input.v1-scenario-planning.v2-animation-timeline.v3-"
    "global-story-clock.v1-split-edge-refs.v1-environment-diffusion.v1-"
    "facility-query-plan.v1-spatial-refinement-snapshot.v1"
)
WUHAN_EFFORT_SNAPSHOT_ID = "effort_wuhan_covid_v1_high"


@dataclass(frozen=True)
class GoldenCaseDefinition:
    case_id: str
    title: str
    summary: str
    profile: str
    scenario_mode: str
    hazard_template_id: str
    diffusion_template: str
    search_mode: str
    reference_time: str
    step_unit: str
    step_size: int
    total_rounds: int
    target_node_count: int
    target_agent_count: int
    report_title: str


WUHAN_CASE = GoldenCaseDefinition(
    case_id=WUHAN_CASE_ID,
    title="武汉疫情推演演示",
    summary="固定武汉疫情背景的黄金演示案例，用于冻结回放、动画和后续流程调试。",
    profile=WUHAN_CASE_ID,
    scenario_mode="crisis_mode",
    hazard_template_id="pest_disease_ecology",
    diffusion_template="bio_ecological_transmission",
    search_mode="deep_search",
    reference_time=WUHAN_REFERENCE_TIME,
    step_unit="day",
    step_size=3,
    total_rounds=WUHAN_TOTAL_ROUNDS,
    target_node_count=200,
    target_agent_count=240,
    report_title="武汉疫情黄金案例推演报告",
)

WUHAN_V2_CASE = GoldenCaseDefinition(
    case_id=WUHAN_V2_CASE_ID,
    title="武汉疫情城市系统复盘",
    summary="策划型 Ultra 目标态黄金案例，完整展示武汉疫情期间六个城市系统的协同演化。",
    profile=WUHAN_V2_CASE_ID,
    scenario_mode="crisis_mode",
    hazard_template_id="pest_disease_ecology",
    diffusion_template="bio_ecological_transmission",
    search_mode="ultra",
    reference_time=WUHAN_REFERENCE_TIME,
    step_unit="day",
    step_size=3,
    total_rounds=WUHAN_TOTAL_ROUNDS,
    target_node_count=288,
    target_agent_count=240,
    report_title="武汉疫情城市系统复盘报告",
)


class GoldenCaseService:
    CASES: Dict[str, GoldenCaseDefinition] = {
        WUHAN_CASE.case_id: WUHAN_CASE,
        WUHAN_V2_CASE.case_id: WUHAN_V2_CASE,
    }

    @classmethod
    def list_cases(cls) -> List[Dict[str, Any]]:
        items = []
        for definition in cls.CASES.values():
            manifest = cls.load_manifest(definition.case_id)
            items.append(
                {
                    "case_id": definition.case_id,
                    "title": definition.title,
                    "summary": definition.summary,
                    "profile": definition.profile,
                    "scenario_mode": definition.scenario_mode,
                    "hazard_template_id": definition.hazard_template_id,
                    "diffusion_template": definition.diffusion_template,
                    "search_mode": definition.search_mode,
                    "reference_time": definition.reference_time,
                    "step_unit": definition.step_unit,
                    "step_size": definition.step_size,
                    "total_rounds": definition.total_rounds,
                    "target_node_count": definition.target_node_count,
                    "target_agent_count": definition.target_agent_count,
                    "artifact_ready": bool(manifest),
                }
            )
        return items

    @classmethod
    def get_case(cls, case_id: str) -> GoldenCaseDefinition:
        definition = cls.CASES.get(case_id)
        if not definition:
            raise ValueError(f"Golden case not found: {case_id}")
        return definition

    @classmethod
    def case_root(cls, case_id: str) -> str:
        return os.path.join(Config.GOLDEN_RUNS_FOLDER, case_id)

    @classmethod
    def load_manifest(cls, case_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(cls.case_root(case_id), "manifest.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        normalized = cls._normalize_manifest_paths(case_id, manifest)
        if normalized != manifest:
            cls._write_json(path, normalized)
        return normalized

    @classmethod
    def _normalize_manifest_paths(cls, case_id: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
        root = cls.case_root(case_id)
        normalized = dict(manifest or {})
        scene_dir = os.path.join(root, "scene")
        simulation_dir = os.path.join(root, "simulation")
        report_dir = os.path.join(root, "report")
        animation_dir = os.path.join(root, "animation")
        artifact_paths = dict((manifest or {}).get("artifacts") or {})

        normalized["scene"] = {
            **dict((manifest or {}).get("scene") or {}),
            "dir": scene_dir,
            "scene_seed": os.path.join(scene_dir, "scene_seed.json"),
        }
        normalized["simulation"] = {
            **dict((manifest or {}).get("simulation") or {}),
            "dir": simulation_dir,
            "config": os.path.join(simulation_dir, "simulation_config.json"),
            "latest_snapshot": os.path.join(simulation_dir, "latest_round_snapshot.json"),
            "scenario_planning_input": os.path.join(simulation_dir, "scenario_planning_input.json"),
            "mechanism_graph": os.path.join(simulation_dir, "mechanism_graph.json"),
            "temporal_plan": os.path.join(simulation_dir, "temporal_plan.json"),
            "policy_plan": os.path.join(simulation_dir, "policy_plan.json"),
            "role_demands": os.path.join(simulation_dir, "role_demands.json"),
            "agent_planning_request": os.path.join(simulation_dir, "agent_planning_request.json"),
            "facility_query_plan": os.path.join(simulation_dir, "facility_query_plan.json"),
            "spatial_refinement_snapshot": os.path.join(
                simulation_dir, "spatial_refinement_snapshot.json"
            ),
            "spread_event_ledger": os.path.join(simulation_dir, "spread_event_ledger.jsonl"),
        }
        normalized["report"] = {
            **dict((manifest or {}).get("report") or {}),
            "dir": report_dir,
            "markdown": os.path.join(report_dir, "full_report.md"),
            "outline": os.path.join(report_dir, "outline.json"),
        }
        normalized["animation"] = {
            **dict((manifest or {}).get("animation") or {}),
            "dir": animation_dir,
            "file": os.path.join(animation_dir, "animation.json"),
        }
        if artifact_paths or case_id == WUHAN_V2_CASE_ID:
            simulation_dir = normalized["simulation"]["dir"]
            normalized["artifacts"] = {
                "foundation": os.path.join(simulation_dir, "background_foundation.json"),
                "scenario": os.path.join(simulation_dir, "scenario_definition.json"),
                "runtime": os.path.join(simulation_dir, "runtime_ledger.json"),
                "analysis": os.path.join(simulation_dir, "analysis_bundle.json"),
                "config": os.path.join(simulation_dir, "simulation_config.json"),
                "animation": os.path.join(normalized["animation"]["dir"], "animation.json"),
                "agent_plan": os.path.join(simulation_dir, "agent_plan.json"),
                "placement_plan": os.path.join(simulation_dir, "agent_placement_plan.json"),
                "resolution_plan": os.path.join(simulation_dir, "resolution_plan.json"),
                "policy_execution_plan": os.path.join(simulation_dir, "policy_execution_plan.json"),
                "facility_query_plan": os.path.join(simulation_dir, "facility_query_plan.json"),
                "spatial_refinement_snapshot": os.path.join(
                    simulation_dir, "spatial_refinement_snapshot.json"
                ),
            }
        return normalized

    @classmethod
    def _artifact_contract_version(cls, definition: GoldenCaseDefinition) -> str:
        if definition.case_id == WUHAN_CASE_ID:
            return WUHAN_ARTIFACT_CONTRACT_VERSION
        if definition.case_id == WUHAN_V2_CASE_ID:
            return WUHAN_V2_ARTIFACT_CONTRACT_VERSION
        return "unversioned"

    @classmethod
    def _manifest_contract_is_current(cls, definition: GoldenCaseDefinition, manifest: Dict[str, Any]) -> bool:
        expected = cls._artifact_contract_version(definition)
        return str((manifest or {}).get("artifact_contract_version") or "") == expected

    @classmethod
    def _manifest_is_healthy(cls, manifest: Dict[str, Any]) -> bool:
        required_paths = [
            ((manifest or {}).get("scene") or {}).get("scene_seed"),
            ((manifest or {}).get("simulation") or {}).get("config"),
            ((manifest or {}).get("simulation") or {}).get("latest_snapshot"),
            ((manifest or {}).get("simulation") or {}).get("scenario_planning_input"),
            ((manifest or {}).get("simulation") or {}).get("mechanism_graph"),
            ((manifest or {}).get("simulation") or {}).get("temporal_plan"),
            ((manifest or {}).get("simulation") or {}).get("policy_plan"),
            ((manifest or {}).get("simulation") or {}).get("role_demands"),
            ((manifest or {}).get("simulation") or {}).get("agent_planning_request"),
            ((manifest or {}).get("simulation") or {}).get("facility_query_plan"),
            ((manifest or {}).get("simulation") or {}).get("spatial_refinement_snapshot"),
            ((manifest or {}).get("simulation") or {}).get("spread_event_ledger"),
            ((manifest or {}).get("report") or {}).get("markdown"),
            ((manifest or {}).get("report") or {}).get("outline"),
            ((manifest or {}).get("animation") or {}).get("file"),
        ]
        required_artifacts = [
            ((manifest or {}).get("artifacts") or {}).get(name)
            for name in ((manifest or {}).get("required_artifacts") or [])
        ]
        return all(path and os.path.exists(path) for path in [*required_paths, *required_artifacts])

    @classmethod
    def ensure_scaffold(cls, case_id: str, *, force: bool = False) -> Dict[str, Any]:
        definition = cls.get_case(case_id)
        root = cls.case_root(case_id)
        manifest_path = os.path.join(root, "manifest.json")
        if not force and os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            normalized = cls._normalize_manifest_paths(case_id, manifest)
            if cls._manifest_is_healthy(normalized) and cls._manifest_contract_is_current(definition, normalized):
                if normalized != manifest:
                    cls._write_json(manifest_path, normalized)
                return normalized

        if case_id == WUHAN_V2_CASE_ID:
            os.makedirs(root, exist_ok=True)
            return cls._normalize_manifest_paths(
                case_id,
                WuhanShowcaseBuilder().compile(definition, root),
            )

        os.makedirs(root, exist_ok=True)
        scene_dir = os.path.join(root, "scene")
        simulation_dir = os.path.join(root, "simulation")
        report_dir = os.path.join(root, "report")
        animation_dir = os.path.join(root, "animation")
        for directory in (scene_dir, simulation_dir, report_dir, animation_dir):
            os.makedirs(directory, exist_ok=True)

        region_graph = cls._build_regions()
        subregion_graph = cls._build_subregions(region_graph)
        profiles = cls._build_profiles(region_graph, subregion_graph)
        relationships = cls._build_relationships(profiles, region_graph, subregion_graph)
        transport_edges = cls._build_transport_edges(region_graph)
        risk_bundle = cls._build_risk_bundle(region_graph)
        round_snapshots = cls._build_round_snapshots(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
            profiles=profiles,
            relationships=relationships,
        )
        latest_snapshot = round_snapshots[-1] if round_snapshots else {}
        interaction_rows = cls._build_interactions(profiles, subregion_graph)
        dynamic_edges = cls._build_dynamic_edges(relationships)
        report_outline = cls._build_report_outline()
        report_markdown = cls._build_report_markdown(report_outline)
        step2_artifacts = cls._build_step2_planning_artifacts(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
        )
        spread_events = cls._build_spread_events(
            definition=definition,
            transport_edges=transport_edges,
            injected_variables=step2_artifacts["agent_planning_request"]["injected_variables"],
        )

        simulation_config = cls._build_simulation_config(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
            profiles=profiles,
            relationships=relationships,
            transport_edges=transport_edges,
            risk_bundle=risk_bundle,
            step2_artifacts=step2_artifacts,
        )
        run_state = cls._build_run_state(definition, round_snapshots)
        state_payload = cls._build_state_payload(
            definition,
            simulation_config,
            profiles,
            region_graph,
            risk_bundle,
            step2_artifacts,
        )
        animation_payload = cls._build_animation_payload(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
            profiles=profiles,
            relationships=relationships,
            round_snapshots=round_snapshots,
            interaction_rows=interaction_rows,
            dynamic_edges=dynamic_edges,
            risk_events=risk_bundle["risk_events"],
            transport_edges=transport_edges,
            spread_events=spread_events,
        )

        cls._write_json(
            os.path.join(scene_dir, "scene_seed.json"),
            cls._build_scene_seed(definition, step2_artifacts["effort_snapshot"]),
        )
        cls._write_text(os.path.join(scene_dir, "scene_report.md"), cls._build_scene_report())

        cls._write_json(os.path.join(simulation_dir, "state.json"), state_payload)
        cls._write_json(os.path.join(simulation_dir, "run_state.json"), run_state)
        cls._write_json(os.path.join(simulation_dir, "simulation_config.json"), simulation_config)
        cls._write_json(
            os.path.join(simulation_dir, "scenario_planning_input.json"),
            step2_artifacts["scenario_planning_input"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "mechanism_graph.json"),
            step2_artifacts["event_mechanism_graph"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "temporal_plan.json"),
            step2_artifacts["temporal_plan"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "policy_plan.json"),
            step2_artifacts["policy_plan"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "role_demands.json"),
            step2_artifacts["role_demands"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "agent_planning_request.json"),
            step2_artifacts["agent_planning_request"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "facility_query_plan.json"),
            step2_artifacts["facility_query_plan"],
        )
        cls._write_json(
            os.path.join(simulation_dir, "spatial_refinement_snapshot.json"),
            step2_artifacts["spatial_refinement_snapshot"],
        )
        cls._write_json(os.path.join(simulation_dir, "region_graph_snapshot.json"), region_graph)
        cls._write_json(os.path.join(simulation_dir, "subregion_graph_snapshot.json"), subregion_graph)
        cls._write_json(os.path.join(simulation_dir, "profiles_full.json"), profiles)
        cls._write_json(os.path.join(simulation_dir, "reddit_profiles.json"), cls._build_reddit_profiles(profiles))
        cls._write_csv(os.path.join(simulation_dir, "twitter_profiles.csv"), cls._build_twitter_profiles(profiles))
        cls._write_json(os.path.join(simulation_dir, "agent_relationship_graph.json"), relationships)
        cls._write_json(os.path.join(simulation_dir, "transport_edges.json"), transport_edges)
        cls._write_json(os.path.join(simulation_dir, "transport_edges_snapshot.json"), transport_edges)
        cls._write_json(os.path.join(simulation_dir, "grounding_summary.json"), cls._build_grounding_summary(region_graph))
        cls._write_json(os.path.join(simulation_dir, "diffusion_context.json"), cls._build_diffusion_context(definition))
        cls._write_json(os.path.join(simulation_dir, "region_agent_index.json"), cls._build_region_agent_index(region_graph, subregion_graph, profiles))
        cls._write_json(os.path.join(simulation_dir, "agent_generation_summary.json"), cls._build_agent_generation_summary(profiles))
        cls._write_json(
            os.path.join(simulation_dir, "injected_variables.json"),
            step2_artifacts["agent_planning_request"]["injected_variables"],
        )
        cls._write_json(os.path.join(simulation_dir, "latest_round_snapshot.json"), latest_snapshot)
        cls._write_json(os.path.join(simulation_dir, "risk_definitions.json"), risk_bundle["risk_definitions"])
        cls._write_json(os.path.join(simulation_dir, "risk_objects.json"), risk_bundle["risk_objects"])
        cls._write_json(os.path.join(simulation_dir, "risk_object_summary.json"), risk_bundle["risk_objects_summary"])
        cls._write_json(os.path.join(simulation_dir, "latest_risk_runtime_state.json"), risk_bundle["latest_risk_runtime_state"])
        cls._write_json(os.path.join(simulation_dir, "env_status.json"), {"status": "replay_only", "twitter_available": False, "reddit_available": False})
        cls._write_jsonl(os.path.join(simulation_dir, "round_state_matrix.jsonl"), round_snapshots)
        cls._write_jsonl(os.path.join(simulation_dir, "risk_runtime_state.jsonl"), risk_bundle["risk_runtime_history"])
        cls._write_jsonl(os.path.join(simulation_dir, "risk_events.jsonl"), risk_bundle["risk_events"])
        cls._write_jsonl(os.path.join(simulation_dir, "spread_event_ledger.jsonl"), spread_events)
        cls._write_jsonl(os.path.join(simulation_dir, "agent_interaction_ledger.jsonl"), interaction_rows)
        cls._write_jsonl(os.path.join(simulation_dir, "dynamic_edge_ledger.jsonl"), dynamic_edges)
        cls._write_jsonl(os.path.join(simulation_dir, "intervention_log.jsonl"), [])
        cls._write_text(os.path.join(simulation_dir, "simulation.log"), "武汉黄金案例冻结回放脚手架已加载。\n")

        cls._write_json(os.path.join(report_dir, "outline.json"), report_outline)
        cls._write_text(os.path.join(report_dir, "full_report.md"), report_markdown)
        cls._write_json(
            os.path.join(report_dir, "progress.json"),
            {
                "status": "completed",
                "progress": 100,
                "message": "冻结回放报告已就绪。",
                "completed_sections": [section["title"] for section in report_outline["sections"]],
                "updated_at": datetime.now().isoformat(),
            },
        )
        cls._write_json(os.path.join(report_dir, "meta.json"), cls._build_report_meta(definition))
        cls._write_jsonl(os.path.join(report_dir, "agent_log.jsonl"), cls._build_report_agent_log())
        cls._write_text(os.path.join(report_dir, "console_log.txt"), "已从黄金案例产物加载冻结回放报告。\n")

        cls._write_json(os.path.join(animation_dir, "animation.json"), animation_payload)
        cls._write_json(os.path.join(simulation_dir, "animation.json"), animation_payload)

        manifest = {
            "case_id": definition.case_id,
            "title": definition.title,
            "summary": definition.summary,
            "profile": definition.profile,
            "scenario_mode": definition.scenario_mode,
            "hazard_template_id": definition.hazard_template_id,
            "diffusion_template": definition.diffusion_template,
            "search_mode": definition.search_mode,
            "reference_time": definition.reference_time,
            "step_unit": definition.step_unit,
            "step_size": definition.step_size,
            "total_rounds": definition.total_rounds,
            "target_node_count": definition.target_node_count,
            "target_agent_count": definition.target_agent_count,
            "artifact_contract_version": cls._artifact_contract_version(definition),
            "artifact_contract_note": (
                "用于确定性演示数据的冻结产物版本；正式推演数据合同变化时必须升级，"
                "仅共享界面或样式变化无需升级。"
            ),
            "scene": {
                "dir": scene_dir,
                "scene_seed": os.path.join(scene_dir, "scene_seed.json"),
            },
            "simulation": {
                "dir": simulation_dir,
                "config": os.path.join(simulation_dir, "simulation_config.json"),
                "latest_snapshot": os.path.join(simulation_dir, "latest_round_snapshot.json"),
                "scenario_planning_input": os.path.join(simulation_dir, "scenario_planning_input.json"),
                "mechanism_graph": os.path.join(simulation_dir, "mechanism_graph.json"),
                "temporal_plan": os.path.join(simulation_dir, "temporal_plan.json"),
                "policy_plan": os.path.join(simulation_dir, "policy_plan.json"),
                "role_demands": os.path.join(simulation_dir, "role_demands.json"),
                "agent_planning_request": os.path.join(simulation_dir, "agent_planning_request.json"),
                "facility_query_plan": os.path.join(simulation_dir, "facility_query_plan.json"),
                "spatial_refinement_snapshot": os.path.join(
                    simulation_dir, "spatial_refinement_snapshot.json"
                ),
                "spread_event_ledger": os.path.join(simulation_dir, "spread_event_ledger.jsonl"),
            },
            "report": {
                "dir": report_dir,
                "markdown": os.path.join(report_dir, "full_report.md"),
                "outline": os.path.join(report_dir, "outline.json"),
            },
            "animation": {
                "dir": animation_dir,
                "file": os.path.join(animation_dir, "animation.json"),
            },
            "generated_at": datetime.now().isoformat(),
        }
        cls._write_json(manifest_path, manifest)
        return manifest

    @classmethod
    def read_artifact(cls, case_id: str, artifact_name: str) -> Dict[str, Any]:
        """Read a named, public workflow projection from a frozen case."""
        cls.get_case(case_id)
        manifest = cls.ensure_scaffold(case_id)
        allowed = {"foundation", "scenario", "runtime", "analysis"}
        normalized_name = str(artifact_name or "").strip().lower()
        if normalized_name not in allowed:
            raise ValueError(f"Golden case artifact not found: {artifact_name}")
        path = str(((manifest or {}).get("artifacts") or {}).get(normalized_name) or "")
        if not path or not os.path.exists(path):
            raise ValueError(f"Golden case artifact not found: {artifact_name}")
        payload = cls._read_json(path, {})
        if not isinstance(payload, dict):
            raise ValueError(f"Golden case artifact is invalid: {artifact_name}")
        return payload

    @classmethod
    def restore_case(cls, case_id: str, *, reuse: bool = True) -> Dict[str, Any]:
        definition = cls.get_case(case_id)
        manifest = cls.ensure_scaffold(case_id)
        reusable = cls._find_reusable_restore(case_id, manifest)
        if reuse and reusable:
            return cls._build_restore_payload(
                definition=definition,
                case_id=case_id,
                project_id=reusable["project_id"],
                simulation_id=reusable["simulation_id"],
                report_id=reusable["report_id"],
                reused=True,
            )

        frozen_config = cls._read_json(manifest["simulation"]["config"], {})
        effort_snapshot = dict(frozen_config.get("effort_snapshot") or {})
        scenario_planning_input = dict(frozen_config.get("scenario_planning_input") or {})
        project = ProjectManager.create_project(
            name=definition.title,
            effort_snapshot=effort_snapshot,
        )
        project.status = ProjectStatus.GRAPH_COMPLETED
        project.graph_id = f"golden_graph::{case_id}"
        is_curated_showcase = case_id == WUHAN_V2_CASE_ID
        foundation_ref = {
            "foundation_id": f"foundation::{case_id}",
            "artifact_name": "foundation",
            "contract_version": "background-foundation.v2",
            "golden_case_id": case_id,
        }
        project.scene_id = foundation_ref["foundation_id"] if is_curated_showcase else project.scene_id
        project.semantic_artifact_ref = dict(foundation_ref) if is_curated_showcase else project.semantic_artifact_ref
        project.simulation_requirement = (
            "复盘武汉疫情期间发现监测、医疗救治、交通流动、社区治理、物资供应和公共信息六个城市系统的协同演化。"
            if is_curated_showcase
            else cls._simulation_requirement()
        )
        ProjectManager.save_project(project)
        ProjectManager.save_extracted_text(
            project.project_id,
            (
                "武汉疫情城市系统复盘：公开历史节点构成时间骨架，主体行动、关系与连续状态为策划推演。"
                if is_curated_showcase
                else cls._background_text()
            ),
        )

        manager = SimulationManager()
        time_plan = dict(frozen_config.get("time_plan") or {})
        simulation_state = manager.create_simulation(
            project_id=project.project_id,
            graph_id=project.graph_id or "",
            engine_mode="envfish",
            simulation_architecture=SIMULATION_ARCHITECTURE,
            scenario_mode=definition.scenario_mode,
            diffusion_template=definition.diffusion_template,
            hazard_template_id=definition.hazard_template_id,
            search_mode=definition.search_mode,
            temporal_preset="slow",
            configured_total_rounds=definition.total_rounds,
            configured_minutes_per_round=WUHAN_MINUTES_PER_ROUND,
            time_plan_mode="manual",
            time_plan=time_plan,
            reference_time=definition.reference_time,
            diffusion_provider="heuristic",
            source_mode="golden_case",
            effort_snapshot=effort_snapshot,
            semantic_artifact_ref=foundation_ref if is_curated_showcase else None,
            artifact_mode="frozen",
            artifact_root=manifest["simulation"]["dir"],
            golden_case_id=case_id,
            golden_case_profile=definition.profile,
            is_replay_only=True,
        )
        simulation_state.status = SimulationStatus.COMPLETED
        simulation_state.config_generated = True
        simulation_state.entities_count = definition.target_node_count
        simulation_state.profiles_count = definition.target_agent_count
        simulation_state.region_count = 12
        simulation_state.risk_objects_count = 5 if is_curated_showcase else 3
        simulation_state.active_variables_count = len(
            (frozen_config.get("agent_planning_request") or {}).get("injected_variables") or []
        )
        simulation_state.hazard_template_mode = "curated_projection" if is_curated_showcase else "compatibility_projection"
        simulation_state.planning_input_id = str(
            scenario_planning_input.get("planning_input_id") or ""
        )
        simulation_state.planning_content_hash = str(
            scenario_planning_input.get("content_hash") or ""
        )
        simulation_state.agent_plan_source = "curated_target_state" if is_curated_showcase else LEGACY_AGENT_PLAN_SOURCE
        if is_curated_showcase:
            simulation_state.resolved_foundation_ref = dict(foundation_ref)
            simulation_state.scenario_input_authority = "curated_target_state"
        manager._save_simulation_state(simulation_state)

        outline_payload = cls._read_json(manifest["report"]["outline"], {})
        outline = ReportOutline(
            title=outline_payload.get("title") or definition.report_title,
            summary=outline_payload.get("summary") or definition.summary,
            sections=[ReportSection(title=item.get("title") or "", content=item.get("content") or "") for item in outline_payload.get("sections") or []],
        )
        report = Report(
            report_id=f"report_{datetime.now().strftime('%Y%m%d%H%M%S%f')[-12:]}",
            simulation_id=simulation_state.simulation_id,
            graph_id=project.graph_id or "",
            simulation_requirement=project.simulation_requirement or "",
            status=ReportStatus.COMPLETED,
            outline=outline,
            created_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
            artifact_mode="frozen",
            artifact_root=manifest["report"]["dir"],
            golden_case_id=case_id,
            is_replay_only=True,
        )
        ReportManager.save_report(report)

        return cls._build_restore_payload(
            definition=definition,
            case_id=case_id,
            project_id=project.project_id,
            simulation_id=simulation_state.simulation_id,
            report_id=report.report_id,
            reused=False,
        )

    @classmethod
    def _build_restore_payload(
        cls,
        *,
        definition: GoldenCaseDefinition,
        case_id: str,
        project_id: str,
        simulation_id: str,
        report_id: str,
        reused: bool,
    ) -> Dict[str, Any]:
        if case_id == WUHAN_V2_CASE_ID:
            base_query = {
                "scenario_mode": definition.scenario_mode,
                "hazard_template_id": definition.hazard_template_id,
                "diffusion_template": definition.diffusion_template,
                "search_mode": definition.search_mode,
                "reference_time": definition.reference_time,
                "maxRounds": definition.total_rounds,
                "golden_case_id": case_id,
                "project_id": project_id,
                "simulation_id": simulation_id,
                "replay": "1",
                "readonly": "1",
                "report_id": report_id,
                "demo_mode": "curated_showcase",
                "version": "v2",
            }
            step_routes = {
                "foundation": {
                    "name": "SceneComposer",
                    "params": {},
                    "query": {**base_query, "step": "1", "restore": "1"},
                },
                "scenario": {
                    "name": "Simulation",
                    "params": {"simulationId": simulation_id},
                    "query": {**base_query, "step": "2"},
                },
                "runtime": {
                    "name": "SimulationRun",
                    "params": {"simulationId": simulation_id},
                    "query": {**base_query, "step": "3"},
                },
                "analysis": {
                    "name": "Analysis",
                    "params": {"reportId": report_id},
                    "query": {**base_query, "step": "4"},
                },
            }
            artifact_refs = {
                name: {
                    "case_id": case_id,
                    "artifact_name": name,
                    "url": f"/api/golden-cases/{case_id}/artifacts/{name}",
                }
                for name in ("foundation", "scenario", "runtime", "analysis")
            }
            return {
                "case_id": case_id,
                "project_id": project_id,
                "foundation_id": f"foundation::{case_id}",
                "scene_id": f"foundation::{case_id}",
                "simulation_id": simulation_id,
                "report_id": report_id,
                "reused": reused,
                "demo_mode": "curated_showcase",
                "default_step": 1,
                "next_step": "background_foundation",
                "capabilities": {
                    "editable": False,
                    "live_intervention": False,
                    "chapter_navigation": True,
                    "copy_as_new": True,
                },
                "artifact_refs": artifact_refs,
                "step_routes": step_routes,
                # Compatibility fields remain Step 2 and Step 3 for V1-era clients.
                "route": step_routes["scenario"],
                "playback_route": step_routes["runtime"],
            }
        return {
            "case_id": case_id,
            "project_id": project_id,
            "simulation_id": simulation_id,
            "report_id": report_id,
            "reused": reused,
            "demo_mode": "frozen_replay",
            "next_step": "scenario_design",
            "route": {
                "name": "Simulation",
                "params": {"simulationId": simulation_id},
                "query": {
                    "scenario_mode": definition.scenario_mode,
                    "hazard_template_id": definition.hazard_template_id,
                    "diffusion_template": definition.diffusion_template,
                    "search_mode": definition.search_mode,
                    "reference_time": definition.reference_time,
                    "maxRounds": definition.total_rounds,
                    "golden_case_id": case_id,
                    "replay": "1",
                    "report_id": report_id,
                    "demo_mode": "frozen_replay",
                },
            },
            "playback_route": {
                "name": "SimulationRun",
                "params": {"simulationId": simulation_id},
                "query": {
                    "scenario_mode": definition.scenario_mode,
                    "hazard_template_id": definition.hazard_template_id,
                    "diffusion_template": definition.diffusion_template,
                    "search_mode": definition.search_mode,
                    "reference_time": definition.reference_time,
                    "maxRounds": definition.total_rounds,
                    "golden_case_id": case_id,
                    "replay": "1",
                    "report_id": report_id,
                    "demo_mode": "frozen_replay",
                },
            },
        }

    @classmethod
    def _find_reusable_restore(cls, case_id: str, manifest: Dict[str, Any]) -> Optional[Dict[str, str]]:
        if not cls._manifest_is_healthy(manifest):
            return None

        frozen_config = cls._read_json(((manifest or {}).get("simulation") or {}).get("config") or "", {})
        expected_effort = dict(frozen_config.get("effort_snapshot") or {})
        expected_planning = dict(frozen_config.get("scenario_planning_input") or {})
        expected_snapshot_id = str(expected_effort.get("effort_snapshot_id") or "")
        expected_effort_hash = str(expected_effort.get("content_hash") or "")
        expected_planning_id = str(expected_planning.get("planning_input_id") or "")
        expected_planning_hash = str(expected_planning.get("content_hash") or "")
        manager = SimulationManager()
        for state in manager.list_simulations():
            if not state.is_replay_only or state.golden_case_id != case_id:
                continue
            if str(state.artifact_mode or "") != "frozen":
                continue
            if not os.path.exists(str(state.artifact_root or "")):
                continue
            project = ProjectManager.get_project(state.project_id)
            if not project:
                continue
            if state.simulation_architecture != SIMULATION_ARCHITECTURE:
                continue
            expected_agent_plan_source = "curated_target_state" if case_id == WUHAN_V2_CASE_ID else LEGACY_AGENT_PLAN_SOURCE
            if state.agent_plan_source != expected_agent_plan_source:
                continue
            if state.planning_input_id != expected_planning_id or state.planning_content_hash != expected_planning_hash:
                continue
            state_effort = dict(state.effort_snapshot or {})
            project_effort = dict(project.effort_snapshot or {})
            if (
                str(state_effort.get("effort_snapshot_id") or "") != expected_snapshot_id
                or str(state_effort.get("content_hash") or "") != expected_effort_hash
                or str(project_effort.get("effort_snapshot_id") or "") != expected_snapshot_id
                or str(project_effort.get("content_hash") or "") != expected_effort_hash
            ):
                continue
            report = ReportManager.get_report_by_simulation(state.simulation_id)
            if not report or report.golden_case_id != case_id or not report.is_replay_only:
                continue

            state.status = SimulationStatus.COMPLETED
            state.current_round = int(state.configured_total_rounds or WUHAN_TOTAL_ROUNDS)
            manager._save_simulation_state(state)
            return {
                "project_id": state.project_id,
                "simulation_id": state.simulation_id,
                "report_id": report.report_id,
            }
        return None

    @classmethod
    def _build_regions(cls) -> List[Dict[str, Any]]:
        base = [
            ("jianghan_market_corridor", "江汉市场走廊", 30.6035, 114.2705),
            ("jiangan_medical_belt", "江岸医疗带", 30.6358, 114.3097),
            ("qiaokou_supply_link", "硚口供应联络带", 30.5856, 114.2444),
            ("hanyang_river_port", "汉阳沿江物流口", 30.5547, 114.2179),
            ("wuchang_civic_core", "武昌治理核心", 30.5467, 114.3162),
            ("hongshan_university_cluster", "洪山高校群", 30.5151, 114.3663),
            ("qingshan_industrial_ring", "青山工业环", 30.6432, 114.3976),
            ("donghu_public_health", "东湖公共卫生圈", 30.5657, 114.4188),
            ("rail_hub_corridor", "铁路枢纽走廊", 30.6188, 114.3321),
            ("airport_gateway", "空港门户区", 30.7838, 114.2081),
            ("community_care_ring", "社区照护环", 30.5798, 114.2874),
            ("yangtze_bridge_axis", "长江桥梁轴", 30.5554, 114.2871),
        ]
        regions: List[Dict[str, Any]] = []
        for index, (region_id, name, lat, lon) in enumerate(base):
            neighbors = []
            if index > 0:
                neighbors.append(base[index - 1][0])
            if index < len(base) - 1:
                neighbors.append(base[index + 1][0])
            if index in {0, 4, 8} and index + 4 < len(base):
                neighbors.append(base[index + 4][0])
            regions.append(
                {
                    "region_id": region_id,
                    "name": name,
                    "region_type": "urban_core" if index < 8 else "support_belt",
                    "description": f"{name}，围绕医疗、交通、社区与市场活动形成高频接触网络。",
                    "tags": ["urban", "transport", "governance"] if index != 9 else ["transport", "gateway", "open"],
                    "neighbors": neighbors,
                    "layer": "macro",
                    "lat": lat,
                    "lon": lon,
                    "state_vector": {
                        "exposure_score": 22 + index,
                        "spread_pressure": 18 + index,
                        "panic_level": 10 + index // 2,
                        "public_trust": 68 - index,
                        "service_capacity": 76 - index,
                        "response_capacity": 74 - index,
                        "economic_stress": 16 + index,
                        "livelihood_stability": 72 - index,
                        "ecosystem_integrity": 61 - index // 2,
                        "vulnerability_score": 24 + index,
                    },
                }
            )
        return regions

    @classmethod
    def _build_subregions(cls, regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        templates = [
            ("market", "市场接触带", "commercial", "near"),
            ("medical", "医疗承压带", "civic", "mid"),
            ("community", "社区传播带", "residential", "far"),
        ]
        for region in regions:
            for idx, (suffix, label, land_use, distance_band) in enumerate(templates, start=1):
                lat, lon = cls._natural_subregion_position(
                    region=region,
                    suffix=suffix,
                    template_index=idx - 1,
                    distance_band=distance_band,
                )
                rows.append(
                    {
                        "region_id": f"{region['region_id']}::{suffix}",
                        "parent_region_id": region["region_id"],
                        "name": f"{region['name']}·{label}",
                        "region_type": label,
                        "land_use_class": land_use,
                        "distance_band": distance_band,
                        "description": f"{region['name']}中的{label}，承接病例发现、就医、物流或社区接触链条。",
                        "layer": "subregion",
                        "tags": [land_use, distance_band, suffix],
                        "lat": lat,
                        "lon": lon,
                        "agent_ids": [],
                    }
                )
        return rows

    @classmethod
    def _build_profiles(cls, regions: List[Dict[str, Any]], subregions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        profiles: List[Dict[str, Any]] = []
        role_templates = [
            ("疾控值守员", "governance", "governmentactor", "疾控协同"),
            ("社区网格员", "human", "humanactor", "社区排查"),
            ("急诊护士", "human", "humanactor", "医疗承压"),
            ("检验技师", "human", "humanactor", "检测链路"),
            ("市场经营者", "human", "humanactor", "市场接触"),
            ("物流调度员", "organization", "organizationactor", "物流调度"),
            ("交通值守员", "organization", "organizationactor", "交通筛查"),
            ("媒体编辑", "organization", "organizationactor", "信息传播"),
            ("医院联络官", "governance", "governmentactor", "医疗统筹"),
            ("社区志愿者", "human", "humanactor", "居民服务"),
            ("药店店长", "organization", "organizationactor", "药品供应"),
            ("物业经理", "organization", "organizationactor", "楼栋治理"),
            ("大学辅导员", "human", "humanactor", "高校管理"),
            ("班车司机", "human", "humanactor", "跨区移动"),
            ("仓储主管", "organization", "organizationactor", "供应链承压"),
            ("热线接线员", "governance", "governmentactor", "舆情响应"),
            ("流调专员", "governance", "governmentactor", "接触链追踪"),
            ("街道办联络员", "governance", "governmentactor", "基层治理"),
            ("实验室管理员", "organization", "organizationactor", "实验资源"),
            ("社区居民代表", "human", "humanactor", "居民感知"),
        ]
        subregions_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for item in subregions:
            subregions_by_parent.setdefault(item["parent_region_id"], []).append(item)
        agent_id = 1
        for region in regions:
            region_subregions = subregions_by_parent.get(region["region_id"], [])
            for index, (role, family, agent_type, motif) in enumerate(role_templates):
                subregion = region_subregions[index % len(region_subregions)]
                lat, lon = cls._natural_agent_position(
                    region=region,
                    subregion=subregion,
                    agent_id=agent_id,
                    role=role,
                    family=family,
                    role_index=index,
                )
                profile = {
                    "agent_id": agent_id,
                    "name": f"{region['name']}-{role}-{(index % 4) + 1:02d}",
                    "username": f"wh_{region['region_id']}_{agent_id}",
                    "bio": f"{region['name']}中的{role}，围绕{motif}与周边机构互动。",
                    "persona": f"围绕{motif}维持区域运转并感知疫情扩散。",
                    "agent_type": agent_type,
                    "agent_subtype": role,
                    "role_type": role,
                    "node_family": family,
                    "home_region_id": region["region_id"],
                    "home_subregion_id": subregion["region_id"],
                    "primary_region": region["region_id"],
                    "lat": lat,
                    "lon": lon,
                    "is_synthesized": True,
                    "source_entity_uuid": f"golden::{agent_id}",
                    "goals": [motif, "控制风险", "维持服务"],
                    "motivation_stack": [motif, "信息同步", "资源协调"],
                    "action_space": ["monitor", "coordinate", "signal", "respond"],
                    "action_space_hint": ["monitor", "coordinate", "signal", "respond"],
                    "state_vector": {
                        "exposure_score": min(95, 20 + (agent_id % 14) * 3),
                        "spread_pressure": min(95, 18 + (agent_id % 11) * 4),
                        "panic_level": 10 + (agent_id % 7) * 4,
                        "public_trust": max(15, 78 - (agent_id % 12) * 3),
                        "service_capacity": max(22, 84 - (agent_id % 10) * 4),
                        "response_capacity": max(22, 80 - (agent_id % 9) * 4),
                        "economic_stress": 8 + (agent_id % 13) * 4,
                        "livelihood_stability": max(16, 80 - (agent_id % 10) * 4),
                        "ecosystem_integrity": max(20, 65 - (agent_id % 8) * 3),
                        "vulnerability_score": min(96, 16 + (agent_id % 15) * 5),
                    },
                    "influenced_regions": [region["region_id"], *(region["neighbors"][:2])],
                }
                profiles.append(profile)
                subregion["agent_ids"].append(agent_id)
                agent_id += 1
        return profiles

    @classmethod
    def _build_relationships(
        cls,
        profiles: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        subregions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_region: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            by_region.setdefault(profile["home_region_id"], []).append(profile)
        subregion_agents: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            subregion_agents.setdefault(profile["home_subregion_id"], []).append(profile)

        rows: List[Dict[str, Any]] = []
        seen = set()

        def add_edge(source: Dict[str, Any], target: Dict[str, Any], relation_type: str, channel: str, strength: float) -> None:
            key = (source["agent_id"], target["agent_id"], relation_type)
            if source["agent_id"] == target["agent_id"] or key in seen:
                return
            seen.add(key)
            rows.append(
                {
                    "edge_id": f"rel::{source['agent_id']}::{target['agent_id']}::{relation_type}",
                    "source_agent_id": source["agent_id"],
                    "target_agent_id": target["agent_id"],
                    "source_region_id": source["home_region_id"],
                    "target_region_id": target["home_region_id"],
                    "relation_type": relation_type,
                    "interaction_channel": channel,
                    "strength": round(strength, 2),
                    "confidence": 0.81,
                    "rationale": f"{source['name']} 与 {target['name']} 围绕 {channel} 形成稳定协作。",
                }
            )

        for region in regions:
            members = by_region.get(region["region_id"], [])
            governance = [item for item in members if item["node_family"] == "governance"]
            medical = [item for item in members if any(token in item["agent_subtype"] for token in ("护士", "检验", "流调", "实验"))]
            community = [item for item in members if any(token in item["agent_subtype"] for token in ("社区", "物业", "居民", "志愿"))]
            logistics = [item for item in members if any(token in item["agent_subtype"] for token in ("物流", "交通", "司机", "仓储"))]
            media = [item for item in members if "媒体" in item["agent_subtype"] or "热线" in item["agent_subtype"]]

            for source in governance:
                for target in medical[:5] + community[:5] + logistics[:4] + media[:2]:
                    add_edge(source, target, "regulates", "governance_hierarchy", 0.72)
            for source in medical:
                for target in community[:3] + logistics[:2]:
                    add_edge(source, target, "supports", "health_response", 0.64)
            for source in logistics:
                for target in medical[:2] + community[:2]:
                    add_edge(source, target, "uses", "supply_chain", 0.58)
            for source in media:
                for target in governance[:2] + community[:3]:
                    add_edge(source, target, "affects", "media_reach", 0.54)

        for subregion_id, members in subregion_agents.items():
            for idx, source in enumerate(members):
                for offset in (1, 2):
                    target = members[(idx + offset) % len(members)]
                    add_edge(source, target, "collaborates_with", "local_contact", 0.49)

        return rows

    @classmethod
    def _build_transport_edges(cls, regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, region in enumerate(regions):
            for neighbor in region["neighbors"]:
                rows.append(
                    {
                        "edge_id": f"transport::{region['region_id']}::{neighbor}",
                        "source_region_id": region["region_id"],
                        "target_region_id": neighbor,
                        "channel_type": "mobility_corridor",
                        "directionality": "directed",
                        "attenuation_rate": 0.18,
                        "travel_time_rounds": 1 if index < 8 else 2,
                        "retention_factor": 0.42,
                        "strength": 0.76,
                        "confidence": 0.8,
                        "rationale": f"{region['name']} 与相邻区域存在稳定人员与物资流动。",
                    }
                )
        return rows

    @classmethod
    def _build_spread_events(
        cls,
        *,
        definition: GoldenCaseDefinition,
        transport_edges: List[Dict[str, Any]],
        injected_variables: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Project one honest deterministic diffusion tree for the frozen fixture.

        The fixture has one explicit outbreak variable rooted in the Jianghan
        market corridor.  We follow only configured directed transport edges and
        their ``travel_time_rounds``.  The first-arrival tree is deterministic;
        proximity, matching rounds, and Agent activity are deliberately excluded
        as causal evidence.
        """

        outbreak_variables = sorted(
            (
                item
                for item in injected_variables
                if str(item.get("type") or "") == "disaster"
                and "jianghan_market_corridor" in list(item.get("target_regions") or [])
            ),
            key=lambda item: str(item.get("variable_id") or ""),
        )
        if not outbreak_variables:
            raise ValueError("武汉冻结样例缺少江汉市场爆发变量，无法构建环境扩散链。")

        variable = outbreak_variables[0]
        source_variable_id = str(variable.get("variable_id") or "").strip()
        origin_region_id = "jianghan_market_corridor"
        start_round = max(0, int(variable.get("start_round") or 0))
        initial_intensity = round(float(variable.get("intensity_0_100") or 0), 4)
        root_event_id = f"golden_spread::{source_variable_id}::root::{origin_region_id}"

        outgoing: Dict[str, List[Dict[str, Any]]] = {}
        for edge in transport_edges:
            source_region_id = str(edge.get("source_region_id") or "").strip()
            target_region_id = str(edge.get("target_region_id") or "").strip()
            if not source_region_id or not target_region_id:
                continue
            outgoing.setdefault(source_region_id, []).append(edge)
        for rows in outgoing.values():
            rows.sort(key=lambda item: str(item.get("edge_id") or ""))

        paths: Dict[str, Dict[str, Any]] = {
            origin_region_id: {
                "key": (start_round, 0, "", ""),
                "arrival_round": start_round,
                "hop": 0,
                "parent_region_id": "",
                "edge": None,
                "intensity": initial_intensity,
            }
        }
        frontier: List[tuple] = [(start_round, 0, "", "", origin_region_id)]
        while frontier:
            arrival_round, hop, via_edge_id, parent_region_id, region_id = heapq.heappop(frontier)
            current = paths.get(region_id) or {}
            if current.get("key") != (arrival_round, hop, via_edge_id, parent_region_id):
                continue
            for edge in outgoing.get(region_id, []):
                edge_id = str(edge.get("edge_id") or "").strip()
                target_region_id = str(edge.get("target_region_id") or "").strip()
                travel_time = max(1, int(edge.get("travel_time_rounds") or 1))
                candidate_key = (arrival_round + travel_time, hop + 1, edge_id, region_id)
                existing = paths.get(target_region_id)
                if existing and tuple(existing["key"]) <= candidate_key:
                    continue
                attenuation = min(1.0, max(0.0, float(edge.get("attenuation_rate") or 0)))
                strength = min(1.0, max(0.0, float(edge.get("strength") or 1)))
                intensity = round(max(1.0, float(current["intensity"]) * (1.0 - attenuation) * strength), 4)
                paths[target_region_id] = {
                    "key": candidate_key,
                    "arrival_round": candidate_key[0],
                    "hop": candidate_key[1],
                    "parent_region_id": region_id,
                    "edge": edge,
                    "intensity": intensity,
                }
                heapq.heappush(frontier, (*candidate_key, target_region_id))

        event_id_by_region = {
            region_id: (
                root_event_id
                if int(path["hop"]) == 0
                else f"golden_spread::{source_variable_id}::hop-{int(path['hop'])}::{region_id}"
            )
            for region_id, path in paths.items()
        }
        reference_time = datetime.fromisoformat(definition.reference_time)
        events: List[Dict[str, Any]] = []
        for region_id, path in sorted(
            paths.items(),
            key=lambda pair: (
                int(pair[1]["arrival_round"]),
                int(pair[1]["hop"]),
                pair[0],
            ),
        ):
            round_num = int(path["arrival_round"])
            hop = int(path["hop"])
            parent_region_id = str(path.get("parent_region_id") or "")
            edge = dict(path.get("edge") or {})
            edge_id = str(edge.get("edge_id") or "")
            event_id = event_id_by_region[region_id]
            parent_event_ids = [event_id_by_region[parent_region_id]] if parent_region_id else []
            is_root = hop == 0
            events.append(
                {
                    "round": round_num,
                    "timestamp": (
                        reference_time + timedelta(days=definition.step_size * round_num)
                    ).isoformat(),
                    "event_id": event_id,
                    "root_event_id": root_event_id,
                    "parent_event_ids": parent_event_ids,
                    "hop": hop,
                    "source_variable_id": source_variable_id,
                    "causal_source_type": "golden_fixture_projection",
                    "grounding_mode": "curated_deterministic_fixture",
                    "projection_rule": "directed_transport_first_arrival_tree",
                    "observed": False,
                    "source_region": origin_region_id if is_root else parent_region_id,
                    "target_region": region_id,
                    "transfer_intensity": round(float(path["intensity"]), 4),
                    "delay_rounds": 0 if is_root else max(1, int(edge.get("travel_time_rounds") or 1)),
                    "persistence": max(1, int(variable.get("duration_rounds") or 1)),
                    "confidence": 1.0 if is_root else round(float(edge.get("confidence") or 0), 4),
                    "channel_type": "fixture_injection" if is_root else str(edge.get("channel_type") or ""),
                    "transport_edge_id": edge_id or None,
                    "edge_id": edge_id or None,
                    "path_edge_ids": [edge_id] if edge_id else [],
                    "related_edge_ids": [],
                    "rationale": (
                        "冻结样例投影：爆发变量明确注入江汉市场走廊；该事件不是现实观测记录。"
                        if is_root
                        else (
                            "冻结样例投影：仅依据已配置的有向交通边及其传播时延，"
                            f"由 {parent_region_id} 到达 {region_id}；该事件不是现实观测记录。"
                        )
                    ),
                }
            )
        return events

    @classmethod
    def _build_round_snapshots(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        snapshots: List[Dict[str, Any]] = []
        for round_num in range(1, definition.total_rounds + 1):
            intensity = cls._wave(round_num, definition.total_rounds)
            regions = []
            for idx, region in enumerate(region_graph):
                base = region["state_vector"]
                escalation = intensity * (1 + idx * 0.03)
                regions.append(
                    {
                        "region_id": region["region_id"],
                        "name": region["name"],
                        "region_type": region["region_type"],
                        "tagline": "病例发现 / 资源调度 / 风险外溢",
                        "exposure_score": cls._clamp(base["exposure_score"] + escalation * 36),
                        "spread_pressure": cls._clamp(base["spread_pressure"] + escalation * 42),
                        "panic_level": cls._clamp(base["panic_level"] + escalation * 44),
                        "public_trust": cls._clamp(base["public_trust"] - escalation * 28),
                        "service_capacity": cls._clamp(base["service_capacity"] - escalation * 26),
                        "response_capacity": cls._clamp(base["response_capacity"] - escalation * 18),
                        "economic_stress": cls._clamp(base["economic_stress"] + escalation * 32),
                        "livelihood_stability": cls._clamp(base["livelihood_stability"] - escalation * 24),
                        "ecosystem_integrity": cls._clamp(base["ecosystem_integrity"] - escalation * 10),
                        "vulnerability_score": cls._clamp(base["vulnerability_score"] + escalation * 38),
                        "severity_band": "high" if escalation > 0.72 else "medium",
                        "uncertainty_band": {"confidence": round(max(0.52, 0.88 - intensity * 0.2), 2)},
                    }
                )

            subregions = []
            for idx, item in enumerate(subregion_graph):
                escalation = intensity * (1 + (idx % 3) * 0.06)
                subregions.append(
                    {
                        "region_id": item["region_id"],
                        "parent_region_id": item["parent_region_id"],
                        "name": item["name"],
                        "region_type": item["region_type"],
                        "land_use_class": item["land_use_class"],
                        "distance_band": item["distance_band"],
                        "agent_ids": item["agent_ids"],
                        "exposure_score": cls._clamp(18 + escalation * 48 + (idx % 5) * 4),
                        "spread_pressure": cls._clamp(16 + escalation * 52 + (idx % 4) * 5),
                        "panic_level": cls._clamp(12 + escalation * 44 + (idx % 3) * 6),
                        "public_trust": cls._clamp(70 - escalation * 30 - (idx % 4) * 2),
                        "service_capacity": cls._clamp(76 - escalation * 28 - (idx % 3) * 3),
                        "response_capacity": cls._clamp(74 - escalation * 22 - (idx % 2) * 3),
                        "economic_stress": cls._clamp(14 + escalation * 36 + (idx % 4) * 4),
                        "livelihood_stability": cls._clamp(74 - escalation * 26 - (idx % 3) * 2),
                        "ecosystem_integrity": cls._clamp(65 - escalation * 12),
                        "vulnerability_score": cls._clamp(22 + escalation * 46 + (idx % 5) * 3),
                    }
                )

            agents = []
            activation_band = min(len(profiles), 48 + round_num * 4)
            for profile in profiles[:activation_band]:
                base = profile["state_vector"]
                role_bonus = 1.15 if profile["node_family"] == "governance" else 1.0
                agents.append(
                    {
                        "agent_id": profile["agent_id"],
                        "name": profile["name"],
                        "agent_type": profile["agent_type"],
                        "agent_subtype": profile["agent_subtype"],
                        "primary_region": profile["primary_region"],
                        "home_subregion_id": profile["home_subregion_id"],
                        "state_vector": {
                            "exposure_score": cls._clamp(base["exposure_score"] + intensity * 26),
                            "spread_pressure": cls._clamp(base["spread_pressure"] + intensity * 30),
                            "panic_level": cls._clamp(base["panic_level"] + intensity * 22),
                            "public_trust": cls._clamp(base["public_trust"] - intensity * 20 * role_bonus),
                            "service_capacity": cls._clamp(base["service_capacity"] - intensity * 16),
                            "response_capacity": cls._clamp(base["response_capacity"] - intensity * 12 + (4 if profile["node_family"] == "governance" else 0)),
                            "economic_stress": cls._clamp(base["economic_stress"] + intensity * 24),
                            "livelihood_stability": cls._clamp(base["livelihood_stability"] - intensity * 18),
                            "ecosystem_integrity": cls._clamp(base["ecosystem_integrity"] - intensity * 8),
                            "vulnerability_score": cls._clamp(base["vulnerability_score"] + intensity * 28),
                        },
                    }
                )

            interactions = cls._build_round_interactions(round_num, relationships, profiles)
            snapshots.append(
                {
                    "round": round_num,
                    "timestamp": (datetime.fromisoformat(definition.reference_time) + timedelta(days=3 * round_num)).isoformat(),
                    "regions": regions,
                    "subregions": subregions,
                    "agents": agents,
                    "interactions": {
                        "agent_interactions": interactions,
                        "agent_environment_effects": interactions[:6],
                    },
                    "agent_summary": {
                        "active_agents": len(agents),
                        "environment_effect_count": len(interactions[:6]),
                    },
                    "feedback": {
                        "feedback_propagation": [
                            {"loop": "环境 → 生态 → 生计 → 恐慌/媒体 → 政策"},
                            {"loop": "市场接触 → 医疗承压 → 社区感知 → 治理加码"},
                        ]
                    },
                    "search_mode": definition.search_mode,
                    "scenario_mode": definition.scenario_mode,
                }
            )
        return snapshots

    @classmethod
    def _build_round_interactions(cls, round_num: int, relationships: List[Dict[str, Any]], profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        sample = relationships[(round_num - 1) * 8: (round_num - 1) * 8 + 10] or relationships[:10]
        profile_by_id = {int(item["agent_id"]): item for item in profiles}
        for idx, rel in enumerate(sample):
            source = profile_by_id.get(int(rel["source_agent_id"]))
            target = profile_by_id.get(int(rel["target_agent_id"]))
            if not source or not target:
                continue
            rows.append(
                {
                    "id": f"interaction::{round_num}::{idx}",
                    "round": round_num,
                    "channel": rel["interaction_channel"],
                    "interaction_channel": rel["interaction_channel"],
                    "source_agent_id": source["agent_id"],
                    "source_agent_name": source["name"],
                    "target_agent_id": target["agent_id"],
                    "target_agent_name": target["name"],
                    "source_region_name": source["home_region_id"],
                    "target_region_name": target["home_region_id"],
                    "action_type": "COORDINATE",
                    "summary": f"{source['name']} 与 {target['name']} 围绕 {rel['interaction_channel']} 协调资源与信息。",
                    "rationale": rel["rationale"],
                    "delta": {"public_trust": -0.4 + idx * 0.05},
                }
            )
        return rows

    @classmethod
    def _build_interactions(cls, profiles: List[Dict[str, Any]], subregions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        profile_by_subregion: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            profile_by_subregion.setdefault(profile["home_subregion_id"], []).append(profile)
        for round_num in range(1, WUHAN_TOTAL_ROUNDS + 1):
            for idx, subregion in enumerate(subregions[:12]):
                members = profile_by_subregion.get(subregion["region_id"], [])
                if len(members) < 2:
                    continue
                source = members[(round_num + idx) % len(members)]
                target = members[(round_num + idx + 1) % len(members)]
                rows.append(
                    {
                        "id": f"interaction-ledger::{round_num}::{idx}",
                        "round": round_num,
                        "channel": "local_contact",
                        "source_agent_id": source["agent_id"],
                        "source_agent_name": source["name"],
                        "target_agent_id": target["agent_id"],
                        "target_agent_name": target["name"],
                        "source_region_name": source["home_region_id"],
                        "target_region_name": target["home_region_id"],
                        "action_type": "COORDINATE",
                        "summary": f"{source['name']} 在 {subregion['name']} 与 {target['name']} 交换新的接触线索。",
                        "rationale": "用于动画回放的冻结互动账本。",
                        "delta": {"vulnerability_score": round(0.2 + idx * 0.03, 2)},
                    }
                )
        return rows

    @classmethod
    def _build_dynamic_edges(cls, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        sample = relationships[: WUHAN_TOTAL_ROUNDS * 6]
        for idx, rel in enumerate(sample):
            round_num = idx // 6 + 1
            rows.append(
                {
                    "edge_id": f"dynamic::{rel['source_agent_id']}::{rel['target_agent_id']}::{round_num}",
                    "source_agent_id": rel["source_agent_id"],
                    "target_agent_id": rel["target_agent_id"],
                    "edge_type": "cross_region_bridge",
                    "interaction_channel": rel["interaction_channel"],
                    "layer": "social_bridge",
                    "origin": "golden_case_scaffold",
                    "scope": "citywide",
                    "strength": round(0.45 + (idx % 5) * 0.07, 2),
                    "confidence": 0.76,
                    "status": "active" if round_num >= WUHAN_TOTAL_ROUNDS - 1 else "created",
                    "created_round": round_num,
                    "last_activated_round": min(WUHAN_TOTAL_ROUNDS, round_num + 2),
                    "rationale": rel["rationale"],
                }
            )
        return rows

    @classmethod
    def _build_risk_bundle(cls, regions: List[Dict[str, Any]]) -> Dict[str, Any]:
        risk_definitions = [
            {
                "risk_id": "cluster_spread_pressure",
                "title": "聚集传播压力",
                "description": "市场、医院和社区接触链的叠加使传播压力快速抬升。",
            },
            {
                "risk_id": "service_capacity_overload",
                "title": "医疗服务超载",
                "description": "急诊、检验与住院能力在高峰期接近阈值。",
            },
            {
                "risk_id": "public_trust_volatility",
                "title": "公众信任波动",
                "description": "信息不对称与谣言传播削弱治理协同效率。",
            },
        ]
        risk_objects = [
            {
                "risk_object_id": "risk_object_cluster_spread",
                "title": "市场-医院-社区接触链",
                "summary": "病例发现与就医迁移共同推高城区传播压力。",
                "why_now": "接触链密集节点开始跨区外溢，形成新的放大器。",
                "severity_score": 86,
                "actionability_score": 72,
                "confidence_score": 0.83,
                "mode": "incident",
                "chain_steps": ["病例发现", "就医迁移", "社区扩散", "治理加码"],
                "root_pressures": ["高频接触", "检测滞后", "跨区流动"],
                "source_entity_uuids": ["agent::1", "agent::3", "agent::41"],
                "primary_regions": [regions[0]["name"], regions[1]["name"], regions[4]["name"]],
                "region_scope": [regions[0]["name"], regions[4]["name"], regions[8]["name"]],
                "affected_clusters": [
                    {"cluster_id": "cluster_1", "name": "医疗前线群簇", "cluster_type": "medical", "vulnerability_score": 88, "mismatch_risk": 74, "dependency_profile": ["检验", "分诊", "床位"]},
                    {"cluster_id": "cluster_2", "name": "社区照护群簇", "cluster_type": "community", "vulnerability_score": 76, "mismatch_risk": 68, "dependency_profile": ["排查", "药品", "楼栋治理"]},
                ],
                "turning_points": ["病例发现从市场接触带转向社区传播带", "医疗承压带开始出现延迟反馈"],
                "scenario_branches": [
                    {"branch_id": "branch_1", "name": "快速检测扩容", "branch_type": "intervention", "description": "通过扩容检测与分诊降低次生扩散。"},
                    {"branch_id": "branch_2", "name": "交通筛查滞后", "branch_type": "counterfactual", "description": "交通节点筛查滞后会放大跨区桥接。"},
                ],
                "evidence": [{"title": "高频接触", "summary": "市场与医院之间存在高频接触迁移。", "entity_refs": ["agent::1", "agent::3"]}],
            },
            {
                "risk_object_id": "risk_object_capacity",
                "title": "医疗容量摩擦",
                "summary": "检验、转运、床位与社区转介之间出现时滞。",
                "why_now": "多条病例链同时汇入医疗带，容量被持续挤压。",
                "severity_score": 78,
                "actionability_score": 69,
                "confidence_score": 0.79,
                "mode": "watch",
                "chain_steps": ["检验积压", "转运延迟", "服务摩擦"],
                "root_pressures": ["高峰积压", "协同失配"],
                "source_entity_uuids": ["agent::4", "agent::9"],
                "primary_regions": [regions[1]["name"], regions[7]["name"]],
                "region_scope": [regions[1]["name"], regions[8]["name"]],
                "affected_clusters": [],
                "turning_points": ["检验周转时间超过阈值"],
                "scenario_branches": [],
                "evidence": [{"title": "容量摩擦", "summary": "多节点服务能力开始下降。", "entity_refs": ["agent::4"]}],
            },
            {
                "risk_object_id": "risk_object_trust",
                "title": "信息与信任波动",
                "summary": "公共沟通和社区感知在高压下出现波动。",
                "why_now": "延迟和不确定信息开始通过媒体与社区双向放大。",
                "severity_score": 71,
                "actionability_score": 75,
                "confidence_score": 0.74,
                "mode": "watch",
                "chain_steps": ["信息不对称", "谣言扩散", "信任回落"],
                "root_pressures": ["信息延迟", "高压反馈"],
                "source_entity_uuids": ["agent::8", "agent::16"],
                "primary_regions": [regions[4]["name"], regions[10]["name"]],
                "region_scope": [regions[4]["name"], regions[10]["name"]],
                "affected_clusters": [],
                "turning_points": ["社区热线需求激增"],
                "scenario_branches": [],
                "evidence": [{"title": "信任波动", "summary": "媒体与社区感知出现偏差。", "entity_refs": ["agent::8"]}],
            },
        ]
        risk_runtime_history = []
        risk_events = []
        for round_num in range(1, WUHAN_TOTAL_ROUNDS + 1):
            severity = min(96, 42 + round_num * 1.4)
            risk_runtime_history.append(
                {
                    "round": round_num,
                    "primary_active_risk_id": "cluster_spread_pressure",
                    "risk_states": [
                        {"risk_id": "cluster_spread_pressure", "severity_score": severity, "trend": "rising", "active_step_ids": ["病例发现", "社区扩散"]},
                        {"risk_id": "service_capacity_overload", "severity_score": max(30, severity - 8), "trend": "rising", "active_step_ids": ["检验积压"]},
                        {"risk_id": "public_trust_volatility", "severity_score": max(25, severity - 12), "trend": "rising" if round_num > 8 else "stable", "active_step_ids": ["信息不对称"] if round_num > 8 else []},
                    ],
                    "pinned_risk_ids": ["cluster_spread_pressure"],
                }
            )
            risk_events.append(
                {
                    "id": f"risk-event::{round_num}",
                    "round": round_num,
                    "event_type": "risk_escalation",
                    "title": "聚集传播压力上升",
                    "summary": f"第 {round_num} 轮，核心接触链继续上升并向跨区桥接蔓延。",
                    "severity_score": severity,
                    "region_scope": [regions[round_num % len(regions)]["name"]],
                }
            )
        latest_runtime_state = risk_runtime_history[-1]
        return {
            "risk_definitions": risk_definitions,
            "risk_objects": risk_objects,
            "risk_objects_summary": {
                "primary_risk_object_id": "risk_object_cluster_spread",
                "primary_active_risk_id": "cluster_spread_pressure",
                "primary_risk_object": risk_objects[0],
                "risk_definitions_count": len(risk_definitions),
                "risk_event_count": len(risk_events),
            },
            "latest_risk_runtime_state": latest_runtime_state,
            "risk_runtime_history": risk_runtime_history,
            "risk_events": risk_events,
        }

    @classmethod
    def _build_animation_payload(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        round_snapshots: List[Dict[str, Any]],
        interaction_rows: List[Dict[str, Any]],
        dynamic_edges: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
        transport_edges: List[Dict[str, Any]],
        spread_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        is_wuhan_v2 = definition.case_id == WUHAN_V2_CASE_ID
        spatial_grounding = WUHAN_V2_SPATIAL_GROUNDING if is_wuhan_v2 else WUHAN_SPATIAL_GROUNDING
        spatial_fixture_id = WUHAN_V2_SPATIAL_FIXTURE_ID if is_wuhan_v2 else WUHAN_SPATIAL_FIXTURE_ID

        def fixture_spatial_attributes(attributes: Dict[str, Any]) -> Dict[str, Any]:
            return {
                **attributes,
                "is_geographic": True,
                "placement": "curated_fixture",
                "geographic_grounding": spatial_grounding,
                "coordinate_grounding": spatial_grounding,
                "coordinates_observed": False,
                "spatial_fixture_id": spatial_fixture_id,
            }

        layout_nodes = []
        for region in region_graph:
            layout_nodes.append(
                {
                    "id": f"region::{region['region_id']}",
                    "name": region["name"],
                    "labels": ["Entity", "Region"],
                    "kind": "region",
                    "is_geographic": True,
                    "geographic_grounding": spatial_grounding,
                    "lat": region["lat"],
                    "lon": region["lon"],
                    "attributes": fixture_spatial_attributes(
                        {"region_id": region["region_id"], "region_type": region["region_type"]}
                    ),
                }
            )
        for subregion in subregion_graph:
            layout_nodes.append(
                {
                    "id": f"subregion::{subregion['region_id']}",
                    "name": subregion["name"],
                    "labels": ["Entity", "Region", "Subregion"],
                    "kind": "subregion",
                    "is_geographic": True,
                    "geographic_grounding": spatial_grounding,
                    "lat": subregion["lat"],
                    "lon": subregion["lon"],
                    "attributes": fixture_spatial_attributes(
                        {
                            "region_id": subregion["region_id"],
                            "parent_region_id": subregion["parent_region_id"],
                            "land_use_class": subregion["land_use_class"],
                        }
                    ),
                }
            )
        for profile in profiles:
            layout_nodes.append(
                {
                    "id": f"agent::{profile['agent_id']}",
                    "name": profile["name"],
                    "labels": ["Entity", profile["agent_type"]],
                    "kind": "agent",
                    "is_geographic": True,
                    "geographic_grounding": spatial_grounding,
                    "lat": profile.get("lat") or 30.59,
                    "lon": profile.get("lon") or 114.30,
                    "attributes": fixture_spatial_attributes(
                        {
                            "agent_id": profile["agent_id"],
                            "primary_region": profile["primary_region"],
                            "home_subregion_id": profile.get("home_subregion_id"),
                            "node_family": profile.get("node_family"),
                            "agent_subtype": profile.get("agent_subtype"),
                        }
                    ),
                }
            )

        layout_edges = []
        for region in region_graph:
            for neighbor in region["neighbors"]:
                layout_edges.append(
                    {
                        "id": f"region_neighbor::{region['region_id']}::{neighbor}",
                        "source": f"region::{region['region_id']}",
                        "target": f"region::{neighbor}",
                        "name": "neighbor_of",
                        "fact_type": "region_neighbor",
                    }
                )
        for edge in transport_edges:
            layout_edges.append(
                {
                    "id": edge["edge_id"],
                    "source": f"region::{edge['source_region_id']}",
                    "target": f"region::{edge['target_region_id']}",
                    "name": "有向交通传播通道",
                    "fact_type": "transport_edge",
                    "attributes": {
                        "channel_type": edge.get("channel_type"),
                        "directionality": edge.get("directionality"),
                        "travel_time_rounds": edge.get("travel_time_rounds"),
                        "attenuation_rate": edge.get("attenuation_rate"),
                        "strength": edge.get("strength"),
                        "confidence": edge.get("confidence"),
                        "is_route_edge": True,
                        "route_grounding": spatial_grounding,
                        "geographic_grounding": spatial_grounding,
                        "route_observed": False,
                        "route_geometry_kind": "fixture_endpoint_projection",
                        "spatial_fixture_id": spatial_fixture_id,
                    },
                }
            )
        for rel in relationships:
            layout_edges.append(
                {
                    "id": rel["edge_id"],
                    "source": f"agent::{rel['source_agent_id']}",
                    "target": f"agent::{rel['target_agent_id']}",
                    "name": rel.get("relation_label") or rel["relation_type"],
                    "fact_type": rel["relation_type"],
                    "attributes": {
                        "relation_label": rel.get("relation_label") or "主体关系",
                        "layer": rel.get("layer") or "城市上下文关系",
                        "provenance": rel.get("provenance") or "curated_projection",
                    },
                }
            )
        dynamic_layout_by_id: Dict[str, Dict[str, Any]] = {}
        dynamic_layout_order: List[str] = []
        for item in dynamic_edges:
            edge_id = str(item.get("edge_id") or "").strip()
            if not edge_id:
                continue
            if edge_id not in dynamic_layout_by_id:
                dynamic_layout_order.append(edge_id)
            dynamic_layout_by_id[edge_id] = item
        for edge_id in dynamic_layout_order:
            item = dynamic_layout_by_id[edge_id]
            layout_edges.append(
                {
                    "id": edge_id,
                    "source": f"agent::{item['source_agent_id']}",
                    "target": f"agent::{item['target_agent_id']}",
                    "name": item.get("relation_label") or item["edge_type"],
                    "fact_type": "dynamic_edge",
                    "attributes": {
                        "relation_label": item.get("relation_label") or "运行关系",
                        "lifecycle_label": item.get("lifecycle_label") or "激活",
                        "layer": item.get("layer") or "机制运行关系",
                        "provenance": item.get("provenance") or "curated_projection",
                    },
                }
            )

        frames = [
            {
                "round": 0,
                "timestamp": definition.reference_time,
                "narrative": {
                    "title": "基线建图",
                    "summary": "先展示武汉基础区块、交通骨架、关键机构与社区节点。",
                    "interaction_summary": "",
                    "risk_summary": "",
                },
                "metrics": {
                    "region_count": len(region_graph),
                    "agent_count": 0,
                    "interaction_count": 0,
                    "risk_event_count": 0,
                    "avg_vulnerability_score": 24,
                },
                "focus_ids": {"node_ids": [item["id"] for item in layout_nodes[:18]], "edge_ids": [item["id"] for item in layout_edges[:12]]},
                "node_states": [
                    {
                        "id": item["id"],
                        "status": "new" if idx < len(region_graph) + len(subregion_graph) else "hidden",
                        "first_seen_round": 0,
                        "last_active_round": 0,
                        "delay_ms": 80 * idx,
                    }
                    for idx, item in enumerate(layout_nodes)
                ],
                "edge_states": [
                    {
                        "id": item["id"],
                        "status": "new" if idx < 18 else "hidden",
                        "first_seen_round": 0 if idx < 18 else 1,
                        "last_active_round": 0,
                        "delay_ms": 45 * idx,
                    }
                    for idx, item in enumerate(layout_edges)
                ],
                "map_layers": {"center": {"lat": 30.5928, "lon": 114.3055}, "base_layer_count": 0},
                "risk_events": [],
            }
        ]

        interactions_by_round: Dict[int, List[Dict[str, Any]]] = {}
        for item in interaction_rows:
            interactions_by_round.setdefault(int(item["round"]), []).append(item)
        risk_by_round: Dict[int, List[Dict[str, Any]]] = {}
        for item in risk_events:
            risk_by_round.setdefault(int(item["round"]), []).append(item)
        dynamic_by_round: Dict[int, List[Dict[str, Any]]] = {}
        for item in dynamic_edges:
            dynamic_by_round.setdefault(int(item.get("round") or item["created_round"]), []).append(item)

        for snapshot in round_snapshots:
            round_num = int(snapshot["round"])
            active_agent_ids = {item["agent_id"] for item in snapshot["agents"][:24]}
            active_dynamic_ids = {item["edge_id"] for item in dynamic_by_round.get(round_num, [])}
            top_region = max(snapshot["regions"], key=lambda item: item.get("vulnerability_score", 0))
            frames.append(
                {
                    "round": round_num,
                    "timestamp": snapshot["timestamp"],
                    "narrative": {
                        "title": snapshot.get("headline") or f"第 {round_num} 轮态势",
                        "summary": (
                            "；".join((snapshot.get("visible_highlights") or [])[:2])
                            if snapshot.get("visible_highlights")
                            else f"{top_region['name']} 成为当轮关键变化区域，脆弱性为 {top_region['vulnerability_score']:.0f}。"
                        ),
                        "interaction_summary": interactions_by_round.get(round_num, [{}])[0].get("summary", ""),
                        "risk_summary": risk_by_round.get(round_num, [{}])[0].get("summary", ""),
                    },
                    "metrics": {
                        "region_count": len(snapshot["regions"]),
                        "agent_count": len(snapshot["agents"]),
                        "interaction_count": len(interactions_by_round.get(round_num, [])),
                        "risk_event_count": len(risk_by_round.get(round_num, [])),
                        "avg_vulnerability_score": round(sum(item["vulnerability_score"] for item in snapshot["regions"]) / len(snapshot["regions"]), 2),
                    },
                    "focus_ids": {
                        "node_ids": [f"agent::{item}" for item in sorted(active_agent_ids)[:18]],
                        "edge_ids": list(active_dynamic_ids)[:18],
                    },
                    "node_states": [
                        {
                            "id": item["id"],
                            "status": (
                                "active"
                                if item["id"].startswith("agent::") and int(item["attributes"].get("agent_id") or 0) in active_agent_ids
                                else "steady"
                            ),
                            "first_seen_round": 0,
                            "last_active_round": round_num if item["id"].startswith("agent::") and int(item["attributes"].get("agent_id") or 0) in active_agent_ids else max(0, round_num - 1),
                            "delay_ms": 80 * (idx % 8) if item["id"].startswith("agent::") else 40 * idx,
                        }
                        for idx, item in enumerate(layout_nodes)
                    ],
                    "edge_states": [
                        {
                            "id": item["id"],
                            "status": (
                                "active"
                                if item["id"] in active_dynamic_ids
                                else "new"
                                if item["fact_type"] == "dynamic_edge" and item["id"] in {edge["edge_id"] for edge in dynamic_by_round.get(round_num, [])}
                                else "steady"
                                if item["fact_type"] != "dynamic_edge" or round_num > 0
                                else "hidden"
                            ),
                            "first_seen_round": 0 if item["fact_type"] != "dynamic_edge" else max(1, next((edge["created_round"] for edge in dynamic_edges if edge["edge_id"] == item["id"]), 1)),
                            "last_active_round": round_num if item["id"] in active_dynamic_ids else max(0, round_num - 1),
                            "delay_ms": 45 * (idx % 12),
                        }
                        for idx, item in enumerate(layout_edges)
                    ],
                    "map_layers": {"center": {"lat": 30.5928, "lon": 114.3055}, "base_layer_count": 0},
                    "risk_events": risk_by_round.get(round_num, []),
                }
            )

        payload = {
            "meta": {
                "simulation_id": f"golden::{definition.case_id}",
                "golden_case_id": definition.case_id,
                "artifact_mode": "frozen",
                "artifact_contract_version": cls._artifact_contract_version(definition),
                "reference_time": definition.reference_time,
                "minutes_per_round": WUHAN_MINUTES_PER_ROUND,
                "total_rounds": definition.total_rounds,
                "default_speed_ms": 1400,
                "speed_options_ms": [800, 1400, 2200],
            },
            "layout": {
                "simulation_id": f"golden::{definition.case_id}",
                "source_mode": "golden_case",
                "map_seed_id": None,
                "geographic_grounding": spatial_grounding,
                "data_quality": {
                    "status": "curated_fixture",
                    "formal_ready": False,
                    "fixture_ready": True,
                    "observed": False,
                    "spatial_fixture_id": spatial_fixture_id,
                },
                "selection_summary": {
                    "source": "golden_fixture",
                    "spatial_fixture_id": spatial_fixture_id,
                },
                "meta": {
                    "geographic_grounding": spatial_grounding,
                    "spatial_fixture_id": spatial_fixture_id,
                    "coordinates_observed": False,
                    "geographic_node_count": len(layout_nodes),
                    "synthetic_node_count": 0,
                    "fixture_route_edge_count": len(transport_edges),
                },
                "center": {"lat": 30.5928, "lon": 114.3055},
                "zoom_hint": 10,
                "radius_m": 45000,
                "analysis_polygon": None,
                "base_layers": [],
                "nodes": layout_nodes,
                "edges": layout_edges,
            },
            "frames": frames,
        }
        # Freeze the same production Timeline V2 projection served to normal
        # simulations into the artifact itself.  The projector is instantiated
        # without SimulationManager because every source ledger is already in
        # memory and this path must remain deterministic and network-free.
        from .simulation_animation_service import SimulationAnimationService

        projector = SimulationAnimationService.__new__(SimulationAnimationService)
        projector.simulation_id = f"golden::{definition.case_id}"
        timeline = projector._build_timeline(
            spread_events=spread_events,
            dynamic_edge_events=dynamic_edges,
            agent_interactions=interaction_rows,
            relationship_events=[],
            risk_events=risk_events,
            frames=frames,
            layout_nodes=layout_nodes,
            layout_edges=layout_edges,
            completed_rounds={int(item.get("round") or 0) for item in round_snapshots},
            allow_legacy_fallback=True,
        )
        spread_by_timeline_id = {
            projector._stable_timeline_event_id("spread_applied", record, index): record
            for index, record in enumerate(spread_events)
        }
        timeline["source_mode"] = "curated_fixture_ledgers"
        timeline["observed_event_count"] = 0
        timeline["curated_event_count"] = len(timeline.get("events") or [])
        timeline["grounding"] = {
            **dict(timeline.get("grounding") or {}),
            "mode": "curated_deterministic_fixture",
            "projection": "golden_fixture_projection",
            "observed": False,
            "fallback_used": False,
        }
        for event in timeline.get("events") or []:
            event["grounding"] = {
                **dict(event.get("grounding") or {}),
                "mode": "curated_deterministic_fixture",
                "projection": "golden_fixture_projection",
                "observed": False,
                "fallback": False,
            }
            spread_record = spread_by_timeline_id.get(str(event.get("id") or ""))
            if spread_record:
                event["cause"] = {
                    "type": "golden_fixture_projection",
                    "source_variable_id": spread_record.get("source_variable_id"),
                    "transport_edge_id": spread_record.get("transport_edge_id"),
                    "projection_rule": spread_record.get("projection_rule"),
                }
        payload["timeline"] = timeline
        return projector._normalize_animation_payload(payload)

    @staticmethod
    def _build_spatial_evidence_summary(
        facility_query_plan: Dict[str, Any],
        spatial_refinement_snapshot: Dict[str, Any],
    ) -> Dict[str, int]:
        return {
            "request_count": len(facility_query_plan.get("requests") or []),
            "required_r3_count": len(
                facility_query_plan.get("required_r3_request_ids") or []
            ),
            "required_r4_count": len(
                facility_query_plan.get("required_r4_request_ids") or []
            ),
            "covered_r3_count": sum(
                1
                for item in spatial_refinement_snapshot.get("request_coverage") or []
                if item.get("resolution_level") == "R3"
                and item.get("status") == "covered"
            ),
            "blocking_gap_count": sum(
                1
                for item in spatial_refinement_snapshot.get("evidence_gaps") or []
                if item.get("blocking") is True
            ),
        }

    @staticmethod
    def _build_v1_spatial_catalog(
        subregion_graph: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Project replay geometry as synthetic candidates, never verified R3.

        V1 subregions were generated to make the frozen replay readable.  They
        may help demonstrate which requirements a refinement worker would try
        to resolve, but they are not observed facilities and therefore carry
        evidence grade ``S`` below every R3 acceptance threshold.
        """

        classes_by_suffix = {
            "market": ["seafood_market"],
            "medical": ["hospital", "emergency_hospital", "emergency_medical_center"],
            "community": ["residential_community"],
        }
        catalog: List[Dict[str, Any]] = []
        for item in subregion_graph:
            feature_id = str(item.get("region_id") or "")
            suffix = feature_id.rsplit("::", 1)[-1]
            catalog.append(
                {
                    "id": feature_id,
                    "name": item.get("name") or "",
                    "kind": "entity",
                    "subtype": suffix,
                    "facility_class_keys": list(classes_by_suffix.get(suffix, [])),
                    "target_region_ids": [str(item.get("parent_region_id") or "")],
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                    "source_kind": "synthetic_model",
                    "provider": "golden_fixture",
                    "evidence_grade": "S",
                    "provenance": "curated_deterministic_fixture",
                    "spatial_fixture_id": WUHAN_SPATIAL_FIXTURE_ID,
                }
            )
        return catalog

    @classmethod
    def _build_step2_planning_artifacts(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the frozen Step 2 contract through the production planner.

        This fixture is intentionally deterministic: it uses a stable snapshot
        identifier and lock time, fixed user inputs, and the network-free
        ScenarioPlanner.  The legacy adapter is only the Agent hand-off; its
        compatibility template never replaces the authoritative mechanism graph.
        """

        effort_snapshot = build_effort_snapshot(
            "high",
            effort_snapshot_id=WUHAN_EFFORT_SNAPSHOT_ID,
            locked_at=definition.reference_time,
        )
        region_ids = [str(item.get("region_id") or "") for item in region_graph]
        foundation_payload = {
            "artifact_id": f"scene::{definition.case_id}",
            "contract_version": "scene-foundation.golden.v1",
            "content_hash": hashlib.sha256(cls._background_text().encode("utf-8")).hexdigest(),
            "project_id": f"golden_project::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "location": "武汉市核心城区",
            "region_ids": region_ids,
            "regions": [
                {"region_id": item.get("region_id"), "name": item.get("name")}
                for item in region_graph
            ],
        }
        event_inputs = [
            {
                "input_id": "wuhan_event_outbreak",
                "name": "新型传染病在市场接触带出现",
                "description": "江汉市场接触带出现早期病例，并经人员接触和跨区流动形成传播风险。",
                "order": 1,
                "target_region_ids": ["jianghan_market_corridor"],
                "target_entity_ids": ["jianghan_market_corridor::market"],
            },
            {
                "input_id": "wuhan_event_health_pressure",
                "name": "感染人群暴露与医疗系统承压",
                "description": "居民暴露范围扩大，病例筛查、转运和救治需求集中增加，医院承压。",
                "order": 2,
                "target_region_ids": ["jiangan_medical_belt", "donghu_public_health"],
                "target_entity_ids": [
                    "jiangan_medical_belt::medical",
                    "donghu_public_health::medical",
                ],
            },
            {
                "input_id": "wuhan_event_system_pressure",
                "name": "交通、供应与治理协同承压",
                "description": "跨区流动带来交通压力，防护和生活物资短缺形成供应压力，并增加跨部门协调压力。",
                "order": 3,
                "target_region_ids": [
                    "rail_hub_corridor",
                    "airport_gateway",
                    "qiaokou_supply_link",
                    "wuchang_civic_core",
                ],
                "target_entity_ids": [],
            },
        ]
        policy_inputs = [
            {
                "input_id": "wuhan_policy_surveillance",
                "name": "病例监测、检测与接触追踪",
                "intent": "加强病例监测、核酸检测、接触追踪和风险信息通报。",
                "target_region_ids": ["jianghan_market_corridor", "donghu_public_health"],
                "target_entity_ids": [],
            },
            {
                "input_id": "wuhan_policy_restriction",
                "name": "重点场所与跨区流动限制",
                "intent": "对重点场所实施活动限制，并对高风险跨区流动进行分阶段管控。",
                "target_region_ids": ["jianghan_market_corridor", "rail_hub_corridor", "airport_gateway"],
                "target_entity_ids": [],
            },
            {
                "input_id": "wuhan_policy_support",
                "name": "医疗物资调拨与困难群体救助",
                "intent": "跨区调拨医疗和生活物资，并向受影响的困难群体提供救助与补偿。",
                "target_region_ids": ["jiangan_medical_belt", "qiaokou_supply_link", "community_care_ring"],
                "target_entity_ids": [],
            },
        ]
        planning = ScenarioPlanner().build(
            foundation=foundation_payload,
            effort_snapshot_ref=effort_snapshot,
            user_events=event_inputs,
            user_policies=policy_inputs,
            advanced_overrides={
                "step_unit": definition.step_unit,
                "step_value": definition.step_size,
                "total_rounds": definition.total_rounds,
            },
        )
        planning_payload = planning.to_dict()
        agent_planning_request = LegacyAgentPlanningAdapter().plan(planning)
        compiled_facility_plan = compile_facility_query_plan(planning)
        facility_query_plan = compiled_facility_plan.to_dict()
        spatial_refinement_snapshot = build_spatial_refinement_snapshot(
            compiled_facility_plan,
            target_catalog=cls._build_v1_spatial_catalog(subregion_graph),
            provider_attempts=[
                {
                    "provider": "golden_fixture",
                    "status": "fixture_candidates_only",
                    "observed": False,
                    "note_zh": "冻结回放坐标仅用于演示，不构成真实 R3 设施证据。",
                }
            ],
            source_versions=[
                {
                    "source_key": WUHAN_SPATIAL_FIXTURE_ID,
                    "version": "wuhan-covid-v1.synthetic-spatial.v1",
                    "evidence_grade": "S",
                }
            ],
        ).to_dict()
        spatial_evidence_summary = cls._build_spatial_evidence_summary(
            facility_query_plan,
            spatial_refinement_snapshot,
        )
        agent_planning_request["facility_query_plan_ref"] = {
            key: facility_query_plan.get(key)
            for key in ("contract_version", "plan_id", "content_hash")
        }
        agent_planning_request["spatial_refinement_snapshot_ref"] = {
            key: spatial_refinement_snapshot.get(key)
            for key in ("contract_version", "snapshot_id", "content_hash")
        }
        agent_planning_request["spatial_evidence_summary"] = spatial_evidence_summary
        graph = dict(planning_payload.get("event_mechanism_graph") or {})
        event_names = [
            str(item.get("name") or "")
            for item in (planning_payload.get("normalized_user_events") or [])
            if str(item.get("name") or "")
        ]
        scenario_model = {
            "architecture": SIMULATION_ARCHITECTURE,
            "source": "scenario_planner",
            "planning_input_id": planning_payload.get("planning_input_id") or "",
            "planning_content_hash": planning_payload.get("content_hash") or "",
            "event_mechanism_graph_id": graph.get("graph_id") or "",
            "scenario_title": " → ".join(event_names),
            "scenario_summary": "武汉疫情场景由用户事件、系统机制推导和政策作用计划共同定义。",
            "core_processes": [
                str(item.get("label_zh") or "")
                for item in (graph.get("nodes") or [])
                if str(item.get("label_zh") or "")
            ],
            "assumptions": list(planning_payload.get("assumptions") or []),
            "temporal_plan": dict(planning_payload.get("temporal_plan") or {}),
        }
        return {
            "effort_snapshot": effort_snapshot,
            "scenario_planning_input": planning_payload,
            "event_mechanism_graph": graph,
            "temporal_plan": dict(planning_payload.get("temporal_plan") or {}),
            "policy_plan": list(planning_payload.get("policy_plan") or []),
            "role_demands": list(planning_payload.get("role_demands") or []),
            "assumptions": list(planning_payload.get("assumptions") or []),
            "agent_planning_request": agent_planning_request,
            "facility_query_plan": facility_query_plan,
            "spatial_refinement_snapshot": spatial_refinement_snapshot,
            "spatial_evidence_summary": spatial_evidence_summary,
            "scenario_model": scenario_model,
            "simulation_audit": {
                "mechanism_graph_source": "scenario_planner",
                "planning_input_id": planning_payload.get("planning_input_id") or "",
                "planning_content_hash": planning_payload.get("content_hash") or "",
                "legacy_mechanism_planner_used": False,
                "说明": "冻结案例与正式流程共同使用 Step 2 事件机制图，未调用网络或模型。",
            },
        }

    @classmethod
    def _build_simulation_config(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        transport_edges: List[Dict[str, Any]],
        risk_bundle: Dict[str, Any],
        step2_artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        planning = step2_artifacts["scenario_planning_input"]
        agent_request = step2_artifacts["agent_planning_request"]
        return {
            "simulation_id": f"golden::{definition.case_id}",
            "project_id": f"golden_project::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "engine_mode": "envfish",
            "simulation_architecture": SIMULATION_ARCHITECTURE,
            "scenario_mode": definition.scenario_mode,
            "diffusion_template": definition.diffusion_template,
            "hazard_template_id": definition.hazard_template_id,
            "hazard_template_mode": "compatibility_projection",
            "search_mode": definition.search_mode,
            "simulation_requirement": (
                f"{cls._simulation_requirement()}。{agent_request.get('simulation_requirement') or ''}"
            ).rstrip("。") + "。",
            "reference_time": definition.reference_time,
            "time_plan_mode": "manual",
            "time_plan": normalize_time_plan(
                {
                    "step_unit": definition.step_unit,
                    "step_size": definition.step_size,
                    "total_rounds": definition.total_rounds,
                    "reference_time": definition.reference_time,
                    "source": "golden_case_scaffold",
                },
                total_rounds=definition.total_rounds,
                minutes_per_round=WUHAN_MINUTES_PER_ROUND,
                preset="slow",
                reference_time=definition.reference_time,
                source="golden_case_scaffold",
            ),
            "time_config": {
                "total_rounds": definition.total_rounds,
                "minutes_per_round": WUHAN_MINUTES_PER_ROUND,
                "total_simulation_hours": definition.total_rounds * WUHAN_MINUTES_PER_ROUND / 60,
            },
            "region_graph": region_graph,
            "subregion_graph": subregion_graph,
            "transport_edges": transport_edges,
            "actor_profiles": profiles,
            "agent_configs": [
                {
                    "agent_id": item["agent_id"],
                    "name": item["name"],
                    "agent_type": item["agent_type"],
                    "agent_subtype": item["agent_subtype"],
                    "primary_region": item["primary_region"],
                    "home_subregion_id": item["home_subregion_id"],
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
                }
                for item in profiles
            ],
            "agent_relationship_graph": relationships,
            "region_agent_index": cls._build_region_agent_index(region_graph, subregion_graph, profiles),
            "agent_generation_summary": cls._build_agent_generation_summary(profiles),
            "effort_snapshot": step2_artifacts["effort_snapshot"],
            "scenario_planning_input": planning,
            "event_mechanism_graph": step2_artifacts["event_mechanism_graph"],
            "mechanism_graph": step2_artifacts["event_mechanism_graph"],
            "temporal_plan": step2_artifacts["temporal_plan"],
            "policy_plan": step2_artifacts["policy_plan"],
            "role_demands": step2_artifacts["role_demands"],
            "assumptions": step2_artifacts["assumptions"],
            "scenario_model": step2_artifacts["scenario_model"],
            "simulation_audit": step2_artifacts["simulation_audit"],
            "agent_plan_source": LEGACY_AGENT_PLAN_SOURCE,
            "agent_planning_request": agent_request,
            "interaction_policies": {
                "activation_mode": "stress_weighted_round_robin",
                "max_actions_per_round": 72,
                "link_follow_probability": 0.84,
                "ecology_feedback_enabled": True,
                "cross_region_candidates_per_agent": 10,
                "max_new_dynamic_edges_per_agent": 4,
                "dynamic_edge_ttl_rounds": 4,
                "dynamic_edge_decay_per_round": 0.10,
                "allowed_cross_region_hops": 3,
                "llm_relation_search_budget": 24,
                "edge_promotion_enabled": True,
            },
            "runtime_limits": {
                "max_agents": len(profiles),
                "max_active_agents_per_round": 72,
                "max_relationship_hops": 4,
                "llm_batch_size": 24,
                "cross_region_candidates_per_agent": 10,
                "max_new_dynamic_edges_per_agent": 4,
            },
            "risk_definitions": risk_bundle["risk_definitions"],
            "latest_risk_runtime_state": risk_bundle["latest_risk_runtime_state"],
            "risk_objects": risk_bundle["risk_objects"],
            "primary_risk_object_id": risk_bundle["risk_objects_summary"]["primary_risk_object_id"],
            "primary_active_risk_id": risk_bundle["risk_objects_summary"]["primary_active_risk_id"],
            "data_grounding_summary": cls._build_grounding_summary(region_graph),
            "diffusion_context": cls._build_diffusion_context(definition),
            "golden_case_profile": definition.profile,
            "artifact_contract_version": cls._artifact_contract_version(definition),
            "report_focus": ["风险对象摘要", "区域脆弱性演化", "代理体关系级联"],
        }

    @classmethod
    def _build_region_agent_index(
        cls,
        regions: List[Dict[str, Any]],
        subregions: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {"regions": {}, "subregions": {}}
        for region in regions:
            result["regions"][region["region_id"]] = [item["agent_id"] for item in profiles if item["home_region_id"] == region["region_id"]]
        for subregion in subregions:
            result["subregions"][subregion["region_id"]] = [item["agent_id"] for item in profiles if item["home_subregion_id"] == subregion["region_id"]]
        return result

    @classmethod
    def _build_agent_generation_summary(cls, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_family: Dict[str, int] = {}
        for item in profiles:
            by_family[item["node_family"]] = by_family.get(item["node_family"], 0) + 1
        return {
            "target_agent_count": len(profiles),
            "generated_agent_count": len(profiles),
            "by_family": by_family,
            "generation_mode": "golden_case_scaffold",
            "agent_plan_source": LEGACY_AGENT_PLAN_SOURCE,
        }

    @classmethod
    def _natural_subregion_position(
        cls,
        *,
        region: Dict[str, Any],
        suffix: str,
        template_index: int,
        distance_band: str,
    ) -> tuple[float, float]:
        band_radius_m = {
            "near": 780.0,
            "mid": 1280.0,
            "far": 1850.0,
        }.get(distance_band, 1100.0)
        region_key = str(region.get("region_id") or region.get("name") or "")
        base_turn = cls._stable_unit(f"subregion-turn::{region_key}")
        local_turn = cls._stable_unit(f"subregion-local::{region_key}::{suffix}")
        angle = (base_turn * 2 * math.pi) + (template_index * 1.92) + ((local_turn - 0.5) * 0.72)
        radius = band_radius_m * (0.76 + cls._stable_unit(f"subregion-radius::{region_key}::{suffix}") * 0.52)
        return cls._offset_lat_lon(
            float(region["lat"]),
            float(region["lon"]),
            radius_m=radius,
            angle_rad=angle,
        )

    @classmethod
    def _natural_agent_position(
        cls,
        *,
        region: Dict[str, Any],
        subregion: Dict[str, Any],
        agent_id: int,
        role: str,
        family: str,
        role_index: int,
    ) -> tuple[float, float]:
        role_text = f"{role} {family}"
        if any(token in role_text for token in ["司机", "物流", "交通", "仓储"]):
            base_radius = 620.0
        elif any(token in role_text for token in ["疾控", "街道", "热线", "联络"]):
            base_radius = 460.0
        elif any(token in role_text for token in ["护士", "检验", "实验", "医院"]):
            base_radius = 360.0
        elif any(token in role_text for token in ["居民", "社区", "物业", "志愿"]):
            base_radius = 520.0
        else:
            base_radius = 440.0

        key = f"agent-layout::{region.get('region_id')}::{subregion.get('region_id')}::{agent_id}::{role}"
        turn = cls._stable_unit(f"{key}::turn")
        spread = cls._stable_unit(f"{key}::spread")
        lane = role_index % 5
        angle = (turn * 2 * math.pi) + lane * 0.41
        radius = base_radius * (0.35 + spread * 1.45)
        lat, lon = cls._offset_lat_lon(
            float(subregion["lat"]),
            float(subregion["lon"]),
            radius_m=radius,
            angle_rad=angle,
        )

        if any(token in role_text for token in ["司机", "物流", "交通", "媒体", "热线"]):
            blend = 0.18 + cls._stable_unit(f"{key}::blend") * 0.12
            lat = round(lat * (1 - blend) + float(region["lat"]) * blend, 6)
            lon = round(lon * (1 - blend) + float(region["lon"]) * blend, 6)

        return lat, lon

    @classmethod
    def _offset_lat_lon(cls, lat: float, lon: float, *, radius_m: float, angle_rad: float) -> tuple[float, float]:
        dx = radius_m * math.cos(angle_rad)
        dy = radius_m * math.sin(angle_rad)
        lat_offset = dy / 111320.0
        lon_offset = dx / max(math.cos(math.radians(lat)) * 111320.0, 1e-6)
        return round(lat + lat_offset, 6), round(lon + lon_offset, 6)

    @classmethod
    def _stable_unit(cls, key: str) -> float:
        digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
        return int(digest[:12], 16) / float(16**12 - 1)

    @classmethod
    def _build_diffusion_context(cls, definition: GoldenCaseDefinition) -> Dict[str, Any]:
        return {
            "provider": "heuristic",
            "template": definition.diffusion_template,
            "notes": "武汉疫情冻结案例使用确定性扩散上下文。",
        }

    @classmethod
    def _build_grounding_summary(cls, regions: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "records": [
                {
                    "metadata": {"region": region["name"]},
                    "priors": {"vulnerability_score": region["state_vector"]["vulnerability_score"]},
                }
                for region in regions[:6]
            ],
            "note": "黄金案例脚手架使用人工整理的武汉区域先验。",
        }

    @classmethod
    def _build_scene_seed(
        cls,
        definition: GoldenCaseDefinition,
        effort_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "scene_id": f"scene::{definition.case_id}",
            "title": definition.title,
            "report_markdown": cls._build_scene_report(),
            "recommended_simulation_requirement": cls._simulation_requirement(),
            "location": "武汉市核心城区",
            "time_scope": "2019-12-22 至 2020-04-08",
            "effort_snapshot": dict(effort_snapshot or {}),
        }

    @classmethod
    def _build_scene_report(cls) -> str:
        return "\n".join(
            [
                "# 武汉疫情背景素材",
                "",
                "本案例固定围绕武汉核心城区在疫情爆发窗口中的空间结构、医疗承压、市场接触链、社区治理与跨区流动展开。",
                "",
                "## 关键锚点",
                "- 市场接触带",
                "- 医疗承压带",
                "- 社区传播带",
                "- 铁路枢纽与机场门户",
                "",
                "## 目标",
                "作为冻结黄金案例，用于动画、关系网回放和后续流程调试。",
            ]
        )

    @classmethod
    def _build_report_outline(cls) -> Dict[str, Any]:
        return {
            "title": WUHAN_CASE.report_title,
            "summary": "围绕武汉疫情黄金案例，复盘地图结构、关系网增长与风险对象演化。",
            "sections": [
                {"title": "案例概览", "content": "回顾武汉案例的空间结构、时间窗口和关键参与群体。"},
                {"title": "区域与子区域演化", "content": "展示宏观区域与子区域在 36 轮中的承压变化。"},
                {"title": "代理体关系增长", "content": "分析治理、医疗、社区和物流网络如何逐步扩张连接。"},
                {"title": "风险对象与干预窗口", "content": "总结主要风险对象、转折点和可干预节点。"},
            ],
        }

    @classmethod
    def _build_report_markdown(cls, outline: Dict[str, Any]) -> str:
        lines = [
            f"# {outline['title']}",
            "",
            f"> {outline['summary']}",
            "",
            "---",
            "",
        ]
        for section in outline["sections"]:
            lines.extend([f"## {section['title']}", "", section["content"], ""])
        lines.extend(
            [
                "## 结论",
                "",
                "武汉黄金案例的价值不在于一次性跑出结论，而在于把空间锚点、关系网络、风险对象和报告入口冻结为可反复回放的演示底座。",
                "",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def _build_report_meta(cls, definition: GoldenCaseDefinition) -> Dict[str, Any]:
        return {
            "report_id": f"golden::{definition.case_id}",
            "simulation_id": f"golden::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "simulation_requirement": cls._simulation_requirement(),
            "status": "completed",
            "outline": cls._build_report_outline(),
            "markdown_content": "",
            "created_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "artifact_mode": "frozen",
            "artifact_root": os.path.join(cls.case_root(definition.case_id), "report"),
            "golden_case_id": definition.case_id,
            "is_replay_only": True,
        }

    @classmethod
    def _build_report_agent_log(cls) -> List[Dict[str, Any]]:
        return [
            {"timestamp": datetime.now().isoformat(), "stage": "load", "message": "已加载武汉冻结报告。"},
            {"timestamp": datetime.now().isoformat(), "stage": "analysis", "message": "已准备适合回放的摘要与大纲。"},
        ]

    @classmethod
    def _build_state_payload(
        cls,
        definition: GoldenCaseDefinition,
        simulation_config: Dict[str, Any],
        profiles: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        risk_bundle: Dict[str, Any],
        step2_artifacts: Dict[str, Any],
    ) -> Dict[str, Any]:
        planning = step2_artifacts["scenario_planning_input"]
        injected_variables = step2_artifacts["agent_planning_request"]["injected_variables"]
        return {
            "simulation_id": f"golden::{definition.case_id}",
            "project_id": f"golden_project::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "engine_mode": "envfish",
            "simulation_architecture": SIMULATION_ARCHITECTURE,
            "scenario_mode": definition.scenario_mode,
            "diffusion_template": definition.diffusion_template,
            "hazard_template_id": definition.hazard_template_id,
            "hazard_template_mode": "compatibility_projection",
            "transport_profile": {"primary_family": definition.diffusion_template},
            "search_mode": definition.search_mode,
            "temporal_preset": "slow",
            "configured_total_rounds": definition.total_rounds,
            "configured_minutes_per_round": WUHAN_MINUTES_PER_ROUND,
            "time_plan_mode": "manual",
            "time_plan": simulation_config["time_plan"],
            "reference_time": definition.reference_time,
            "diffusion_provider": "heuristic",
            "status": "completed",
            "entities_count": definition.target_node_count,
            "profiles_count": len(profiles),
            "region_count": len(regions),
            "active_variables_count": len(injected_variables),
            "risk_objects_count": len(risk_bundle["risk_objects"]),
            "entity_types": ["Region", "Subregion", "HumanActor", "GovernmentActor", "OrganizationActor"],
            "config_generated": True,
            "config_reasoning": "武汉疫情冻结案例已通过 Step 2 场景规划合同装配。",
            "primary_risk_object_id": risk_bundle["risk_objects_summary"]["primary_risk_object_id"],
            "source_mode": "golden_case",
            "map_seed_id": None,
            "effort_snapshot": step2_artifacts["effort_snapshot"],
            "planning_input_id": planning.get("planning_input_id") or "",
            "planning_content_hash": planning.get("content_hash") or "",
            "agent_plan_source": LEGACY_AGENT_PLAN_SOURCE,
            "scenario_planning_input": planning,
            "event_mechanism_graph": step2_artifacts["event_mechanism_graph"],
            "temporal_plan": step2_artifacts["temporal_plan"],
            "policy_plan": step2_artifacts["policy_plan"],
            "role_demands": step2_artifacts["role_demands"],
            "assumptions": step2_artifacts["assumptions"],
            "artifact_mode": "frozen",
            "artifact_root": os.path.join(cls.case_root(definition.case_id), "simulation"),
            "golden_case_id": definition.case_id,
            "golden_case_profile": definition.profile,
            "artifact_contract_version": cls._artifact_contract_version(definition),
            "is_replay_only": True,
            "current_round": definition.total_rounds,
            "twitter_status": "not_started",
            "reddit_status": "not_started",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": None,
        }

    @classmethod
    def _build_run_state(cls, definition: GoldenCaseDefinition, round_snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_hours = definition.total_rounds * WUHAN_MINUTES_PER_ROUND / 60
        return {
            "simulation_id": f"golden::{definition.case_id}",
            "runner_status": "completed",
            "current_round": definition.total_rounds,
            "total_rounds": definition.total_rounds,
            "simulated_hours": total_hours,
            "total_simulation_hours": total_hours,
            "twitter_current_round": 0,
            "reddit_current_round": 0,
            "twitter_simulated_hours": 0,
            "reddit_simulated_hours": 0,
            "twitter_running": False,
            "reddit_running": False,
            "twitter_completed": False,
            "reddit_completed": False,
            "twitter_actions_count": 0,
            "reddit_actions_count": 0,
            "rounds": [{"round_num": item["round"], "start_time": item["timestamp"], "end_time": item["timestamp"], "simulated_hour": item["round"] * 72, "twitter_actions": 0, "reddit_actions": 0, "active_agents": [agent["agent_id"] for agent in item["agents"][:16]], "actions": []} for item in round_snapshots],
            "recent_actions": [],
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "error": None,
            "process_pid": None,
        }

    @classmethod
    def _build_reddit_profiles(cls, profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id": item["agent_id"], "name": item["name"], "bio": item["bio"]} for item in profiles]

    @classmethod
    def _build_twitter_profiles(cls, profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id": item["agent_id"], "name": item["name"], "bio": item["bio"]} for item in profiles]

    @classmethod
    def _simulation_requirement(cls) -> str:
        return (
            "以武汉疫情爆发早期为背景，围绕市场接触链、医疗承压、社区传播和跨区流动进行高保真推演，"
            "观察关系网如何逐步增长并形成风险对象。"
        )

    @classmethod
    def _background_text(cls) -> str:
        return (
            "武汉疫情黄金案例背景：固定覆盖 2019-12-22 至 2020-04-08，"
            "突出市场接触、医疗承压、社区传播、交通枢纽和治理协调等要素。"
        )

    @classmethod
    def _wave(cls, round_num: int, total_rounds: int) -> float:
        midpoint = total_rounds * 0.45
        steepness = 0.22
        return 1.0 / (1.0 + math.exp(-(round_num - midpoint) * steepness))

    @classmethod
    def _clamp(cls, value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)

    @classmethod
    def _read_json(cls, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def _write_json(cls, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    @classmethod
    def _write_text(cls, path: str, payload: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)

    @classmethod
    def _write_jsonl(cls, path: str, rows: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @classmethod
    def _write_csv(cls, path: str, rows: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["agent_id", "name", "bio"])
            writer.writeheader()
            writer.writerows(rows)
