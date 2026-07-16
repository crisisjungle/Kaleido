"""Deterministic compiler for the curated Wuhan COVID target-state showcase.

The compiler intentionally has no network, LLM, Zep, planner, or runtime
dependencies.  Versioned editorial sources are expanded into the same frozen
artifact shapes consumed by the formal Step 1-4 product flow.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .effort_contract import build_effort_snapshot
from .envfish_models import normalize_time_plan
from .scenario_planner import SIMULATION_ARCHITECTURE
from .spatial_evidence import (
    build_spatial_refinement_snapshot,
    compile_facility_query_plan,
)
from .workflow_artifacts import (
    project_analysis_bundle,
    project_background_foundation,
    project_runtime_ledger,
    project_scenario_definition,
)


WUHAN_V2_CASE_ID = "wuhan_covid_v2"
WUHAN_V2_ARTIFACT_CONTRACT_VERSION = (
    "2026-07-15.wuhan-curated-target-state.v2-background-foundation.v2-"
    "scenario-definition.v2-runtime-ledger.v2-analysis-bundle.v2-animation-timeline.v3-"
    "facility-query-plan.v1-spatial-refinement-snapshot.v1-dynamic-relationship-metrics.v1"
)
WUHAN_V2_SPATIAL_FIXTURE_ID = "golden_spatial_fixture::wuhan_covid_v2"
WUHAN_V2_SPATIAL_GROUNDING = "curated_public_anchor_projection"
WUHAN_V2_EFFORT_SNAPSHOT_ID = "effort_wuhan_covid_v2_ultra"
WUHAN_V2_COMPILED_AT = "2026-07-14T00:00:00+08:00"


class WuhanShowcaseBuilder:
    """Compile the tracked Wuhan V2 editorial package into frozen artifacts."""

    RELATION_TYPES = (
        ("reports_to", "上报给", "机制运行关系"),
        ("tests_for", "为其提供检测", "机制运行关系"),
        ("refers_patient_to", "转诊至", "机制运行关系"),
        ("coordinates_with", "协同处置", "机制运行关系"),
        ("supplies", "调拨物资至", "机制运行关系"),
        ("transports", "闭环转运至", "机制运行关系"),
        ("informs", "共享信息给", "城市上下文关系"),
        ("supports", "提供支持给", "城市上下文关系"),
        ("serves", "服务于", "城市上下文关系"),
        ("observes", "持续观察", "城市上下文关系"),
    )
    ACTION_TYPES = (
        ("DISCOVER", "发现"),
        ("REPORT", "上报"),
        ("SAMPLE", "采样"),
        ("TEST", "检测"),
        ("TRIAGE", "分诊"),
        ("TRANSFER", "转运"),
        ("ISOLATE", "隔离"),
        ("EXPAND", "扩容"),
        ("ALLOCATE", "调拨"),
        ("DELIVER", "配送"),
        ("COMMUNICATE", "沟通"),
        ("RECOVER", "恢复"),
    )
    LIFECYCLE_ACTIONS = (
        ("created", "创建"),
        ("activated", "激活"),
        ("strengthened", "增强"),
        ("weakened", "减弱"),
        ("resolved", "结束"),
        ("activated", "激活"),
    )

    def __init__(self, *, source_root: str | None = None) -> None:
        self.source_root = source_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "golden_cases", WUHAN_V2_CASE_ID)
        )
        self.case_manifest = self._read_json("case_manifest.json")
        self.source_manifest = self._read_json("source_manifest.json")
        self.anchor_collection = self._read_json("spatial_anchors.geojson")
        self.roster_spec = self._read_json("agent_roster.json")
        self.analysis_spec = self._read_json("analysis_spec.json")
        self.story_events = self._read_jsonl("story_events.jsonl")

    def compile(self, definition: Any, root: str) -> Dict[str, Any]:
        from .golden_case_service import GoldenCaseService

        self._validate_sources()
        scene_dir = os.path.join(root, "scene")
        simulation_dir = os.path.join(root, "simulation")
        report_dir = os.path.join(root, "report")
        animation_dir = os.path.join(root, "animation")
        artifact_dir = os.path.join(root, "artifacts")
        for directory in (scene_dir, simulation_dir, report_dir, animation_dir, artifact_dir):
            os.makedirs(directory, exist_ok=True)

        effort_snapshot = build_effort_snapshot(
            "ultra",
            effort_snapshot_id=WUHAN_V2_EFFORT_SNAPSHOT_ID,
            source="curated_fixture",
            selected_at=WUHAN_V2_COMPILED_AT,
            locked_at=WUHAN_V2_COMPILED_AT,
        )
        regions = self._build_regions()
        anchors = self._build_anchors()
        profiles = self._build_profiles(anchors)
        self._attach_anchor_agents(anchors, profiles)
        relationships = self._build_relationships(profiles)
        transport_edges = self._build_transport_edges(regions)
        risk_bundle = self._build_risk_bundle(regions)
        planning_artifacts = self._build_planning_artifacts(
            effort_snapshot=effort_snapshot,
            regions=regions,
            anchors=anchors,
            profiles=profiles,
            relationships=relationships,
            risk_bundle=risk_bundle,
        )
        round_snapshots = self._build_round_snapshots(regions, anchors, profiles)
        interactions = self._build_interactions(profiles, anchors)
        dynamic_edges = self._build_dynamic_edges(profiles)
        spread_events = self._build_spread_events(regions)
        relationship_states = self._build_relationship_states(dynamic_edges)
        policy_events = self._build_policy_events()
        state_mutations = self._build_state_mutations(round_snapshots)

        simulation_config = self._build_simulation_config(
            definition=definition,
            effort_snapshot=effort_snapshot,
            regions=regions,
            anchors=anchors,
            profiles=profiles,
            relationships=relationships,
            transport_edges=transport_edges,
            risk_bundle=risk_bundle,
            planning_artifacts=planning_artifacts,
        )
        agent_plan = self._build_agent_plan(profiles)
        placement_plan = self._build_placement_plan(profiles, anchors)
        resolution_plan = self._build_resolution_plan(profiles)
        policy_execution_plan = self._build_policy_execution_plan(profiles)
        simulation_config["agent_plan"] = agent_plan
        simulation_config["agent_placement_plan"] = placement_plan
        simulation_config["resolution_plan"] = resolution_plan
        simulation_config["policy_execution_plan"] = policy_execution_plan
        foundation = self._build_foundation(effort_snapshot, anchors)
        scenario_definition = project_scenario_definition(
            planning_artifacts["scenario_planning_input"], simulation_config
        )
        scenario_definition.update({
            "generation_mode": "curated_target_state",
            "artifact_mode": "frozen",
            "storylines": list(self.case_manifest["storylines"]),
            "chapters": list(self.case_manifest["chapters"]),
            "spatial_anchors": anchors,
            "agent_catalog_summary": self._agent_catalog_summary(profiles),
            "agent_plan_ref": {"artifact_name": "agent_plan", "contract_version": "agent-plan.v2"},
            "placement_plan_ref": {"artifact_name": "placement_plan", "contract_version": "agent-placement-plan.v2"},
            "resolution_plan_ref": {"artifact_name": "resolution_plan", "contract_version": "resolution-plan.v2"},
            "policy_execution_plan_ref": {"artifact_name": "policy_execution_plan", "contract_version": "policy-execution-plan.v2"},
            "facility_query_plan_ref": dict(
                planning_artifacts["agent_planning_request"]["facility_query_plan_ref"]
            ),
            "spatial_refinement_snapshot_ref": dict(
                planning_artifacts["agent_planning_request"]["spatial_refinement_snapshot_ref"]
            ),
            "spatial_evidence_summary": dict(planning_artifacts["spatial_evidence_summary"]),
        })
        simulation_config["background_foundation"] = foundation
        simulation_config["scenario_definition"] = scenario_definition

        runtime_ledger = project_runtime_ledger({
            "round_snapshots": round_snapshots,
            "spread_events": spread_events,
            "agent_action_decisions": interactions,
            "state_mutations": state_mutations,
            "policy_execution_events": policy_events,
            "relationship_events": dynamic_edges,
            "relationship_states": relationship_states,
            "agent_emergence_events": self._build_agent_emergence(profiles),
            "agent_lineage": self._build_agent_lineage(profiles),
            "latest_risk_runtime_state": risk_bundle["latest_risk_runtime_state"],
            "risk_events": risk_bundle["risk_events"],
            "interventions": policy_events,
        })
        runtime_ledger.update({
            "generation_mode": "curated_target_state",
            "artifact_mode": "frozen",
            "story_chapters": list(self.case_manifest["chapters"]),
            "storylines": list(self.case_manifest["storylines"]),
        })
        analysis_bundle = self._build_analysis_bundle(
            round_snapshots=round_snapshots,
            risk_bundle=risk_bundle,
            policy_events=policy_events,
            dynamic_edges=dynamic_edges,
        )
        report_outline = self._build_report_outline()
        report_markdown = self._build_report_markdown(analysis_bundle)

        # Reuse the production animation/timeline projector, but feed it only
        # deterministic in-memory ledgers compiled above.
        animation = GoldenCaseService._build_animation_payload(
            definition=definition,
            region_graph=regions,
            subregion_graph=anchors,
            profiles=profiles,
            relationships=relationships,
            round_snapshots=round_snapshots,
            interaction_rows=interactions,
            dynamic_edges=dynamic_edges,
            risk_events=risk_bundle["risk_events"],
            transport_edges=transport_edges,
            spread_events=spread_events,
        )
        animation["meta"].update({
            "generation_mode": "curated_target_state",
            "artifact_mode": "frozen",
            "playback_duration_ms": int(self.case_manifest["playback_duration_ms"]),
            "default_step": 1,
        })
        animation["story_chapters"] = list(self.case_manifest["chapters"])
        animation["storylines"] = list(self.case_manifest["storylines"])
        animation["policy_interventions"] = [dict(item) for item in self.analysis_spec["policies"]]
        animation["timeline"]["story_chapters"] = list(self.case_manifest["chapters"])
        animation["timeline"]["playback_duration_ms"] = int(self.case_manifest["playback_duration_ms"])
        self._annotate_timeline(animation["timeline"])
        snapshots_by_round = {int(item["round"]): item for item in round_snapshots}
        for frame in animation.get("frames") or []:
            snapshot = snapshots_by_round.get(int(frame.get("round") or 0))
            if not snapshot:
                continue
            frame["chapter_id"] = snapshot["chapter_id"]
            frame["chapter_name"] = snapshot["chapter_name"]
            frame["storyline_ids"] = list(snapshot["storyline_ids"])
            frame["visible_events"] = [
                {
                    "id": f"round-highlight::{snapshot['round']:02d}::{index + 1:02d}",
                    "title": action,
                    "storyline_ids": list(snapshot["storyline_ids"]),
                    "provenance": "curated_projection",
                }
                for index, action in enumerate(snapshot["visible_highlights"][:6])
            ]
            frame["historical_nodes"] = list(snapshot.get("historical_nodes") or [])
            frame["policy_ids"] = list(snapshot.get("policy_ids") or [])
        self._retime_animation(animation, int(self.case_manifest["playback_duration_ms"]))

        self._write_json(os.path.join(scene_dir, "scene_seed.json"), self._build_scene_seed(effort_snapshot))
        self._write_text(os.path.join(scene_dir, "scene_report.md"), foundation["report_markdown"])
        self._write_json(os.path.join(simulation_dir, "state.json"), self._build_state(definition, simulation_config, risk_bundle))
        self._write_json(os.path.join(simulation_dir, "run_state.json"), self._build_run_state(definition, round_snapshots))
        self._write_json(os.path.join(simulation_dir, "simulation_config.json"), simulation_config)
        self._write_json(os.path.join(simulation_dir, "scenario_planning_input.json"), planning_artifacts["scenario_planning_input"])
        self._write_json(os.path.join(simulation_dir, "mechanism_graph.json"), planning_artifacts["event_mechanism_graph"])
        self._write_json(os.path.join(simulation_dir, "temporal_plan.json"), planning_artifacts["temporal_plan"])
        self._write_json(os.path.join(simulation_dir, "policy_plan.json"), planning_artifacts["policy_plan"])
        self._write_json(os.path.join(simulation_dir, "role_demands.json"), planning_artifacts["role_demands"])
        self._write_json(os.path.join(simulation_dir, "agent_planning_request.json"), planning_artifacts["agent_planning_request"])
        self._write_json(os.path.join(simulation_dir, "facility_query_plan.json"), planning_artifacts["facility_query_plan"])
        self._write_json(os.path.join(simulation_dir, "spatial_refinement_snapshot.json"), planning_artifacts["spatial_refinement_snapshot"])
        self._write_json(os.path.join(simulation_dir, "region_graph_snapshot.json"), regions)
        self._write_json(os.path.join(simulation_dir, "subregion_graph_snapshot.json"), anchors)
        self._write_json(os.path.join(simulation_dir, "profiles_full.json"), profiles)
        self._write_json(os.path.join(simulation_dir, "reddit_profiles.json"), self._compact_profiles(profiles))
        self._write_json(os.path.join(simulation_dir, "agent_relationship_graph.json"), relationships)
        self._write_json(os.path.join(simulation_dir, "transport_edges.json"), transport_edges)
        self._write_json(os.path.join(simulation_dir, "transport_edges_snapshot.json"), transport_edges)
        self._write_json(os.path.join(simulation_dir, "latest_round_snapshot.json"), round_snapshots[-1])
        self._write_json(os.path.join(simulation_dir, "risk_definitions.json"), risk_bundle["risk_definitions"])
        self._write_json(os.path.join(simulation_dir, "risk_objects.json"), risk_bundle["risk_objects"])
        self._write_json(os.path.join(simulation_dir, "risk_object_summary.json"), risk_bundle["risk_objects_summary"])
        self._write_json(os.path.join(simulation_dir, "latest_risk_runtime_state.json"), risk_bundle["latest_risk_runtime_state"])
        self._write_json(os.path.join(simulation_dir, "background_foundation.json"), foundation)
        self._write_json(os.path.join(simulation_dir, "scenario_definition.json"), scenario_definition)
        self._write_json(os.path.join(simulation_dir, "runtime_ledger.json"), runtime_ledger)
        self._write_json(os.path.join(simulation_dir, "analysis_bundle.json"), analysis_bundle)
        self._write_json(os.path.join(simulation_dir, "agent_plan.json"), agent_plan)
        self._write_json(os.path.join(simulation_dir, "agent_placement_plan.json"), placement_plan)
        self._write_json(os.path.join(simulation_dir, "resolution_plan.json"), resolution_plan)
        self._write_json(os.path.join(simulation_dir, "policy_execution_plan.json"), policy_execution_plan)
        self._write_json(os.path.join(simulation_dir, "spatial_anchor_candidates.json"), anchors)
        self._write_json(os.path.join(simulation_dir, "agent_archetypes_v2.json"), self.roster_spec)
        self._write_json(os.path.join(simulation_dir, "env_status.json"), {"status": "replay_only", "runtime_invoked": False})
        self._write_json(os.path.join(simulation_dir, "animation.json"), animation)
        self._write_jsonl(os.path.join(simulation_dir, "round_state_matrix.jsonl"), round_snapshots)
        self._write_jsonl(os.path.join(simulation_dir, "risk_runtime_state.jsonl"), risk_bundle["risk_runtime_history"])
        self._write_jsonl(os.path.join(simulation_dir, "risk_events.jsonl"), risk_bundle["risk_events"])
        self._write_jsonl(os.path.join(simulation_dir, "spread_event_ledger.jsonl"), spread_events)
        self._write_jsonl(os.path.join(simulation_dir, "agent_interaction_ledger.jsonl"), interactions)
        self._write_jsonl(os.path.join(simulation_dir, "dynamic_edge_ledger.jsonl"), dynamic_edges)
        self._write_jsonl(os.path.join(simulation_dir, "relationship_state_ledger.jsonl"), relationship_states)
        self._write_jsonl(os.path.join(simulation_dir, "policy_execution_ledger.jsonl"), policy_events)
        self._write_jsonl(os.path.join(simulation_dir, "state_mutation_ledger.jsonl"), state_mutations)
        self._write_jsonl(os.path.join(simulation_dir, "intervention_log.jsonl"), policy_events)
        self._write_text(os.path.join(simulation_dir, "simulation.log"), "武汉策划型目标态案例已从版本化源数据确定性编译。\n")

        self._write_json(os.path.join(report_dir, "outline.json"), report_outline)
        self._write_text(os.path.join(report_dir, "full_report.md"), report_markdown)
        self._write_json(os.path.join(report_dir, "analysis_bundle.json"), analysis_bundle)
        self._write_json(os.path.join(report_dir, "progress.json"), {
            "status": "completed", "progress": 100,
            "completed_sections": list(self.analysis_spec["report_sections"]),
            "updated_at": WUHAN_V2_COMPILED_AT,
        })
        self._write_json(os.path.join(report_dir, "meta.json"), self._build_report_meta(definition, report_outline))
        self._write_jsonl(os.path.join(report_dir, "agent_log.jsonl"), [])
        self._write_text(os.path.join(report_dir, "console_log.txt"), "")
        self._write_json(os.path.join(animation_dir, "animation.json"), animation)

        artifacts = {
            "foundation": os.path.join(simulation_dir, "background_foundation.json"),
            "scenario": os.path.join(simulation_dir, "scenario_definition.json"),
            "runtime": os.path.join(simulation_dir, "runtime_ledger.json"),
            "analysis": os.path.join(simulation_dir, "analysis_bundle.json"),
            "config": os.path.join(simulation_dir, "simulation_config.json"),
            "animation": os.path.join(animation_dir, "animation.json"),
            "agent_plan": os.path.join(simulation_dir, "agent_plan.json"),
            "placement_plan": os.path.join(simulation_dir, "agent_placement_plan.json"),
            "resolution_plan": os.path.join(simulation_dir, "resolution_plan.json"),
            "policy_execution_plan": os.path.join(simulation_dir, "policy_execution_plan.json"),
            "facility_query_plan": os.path.join(simulation_dir, "facility_query_plan.json"),
            "spatial_refinement_snapshot": os.path.join(simulation_dir, "spatial_refinement_snapshot.json"),
        }
        artifact_hashes = {name: self._file_hash(path) for name, path in artifacts.items()}
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
            "generation_mode": "curated_target_state",
            "artifact_mode": "frozen",
            "demo_mode": "curated_showcase",
            "default_step": 1,
            "capabilities": dict(self.case_manifest["capabilities"]),
            "artifact_contract_version": WUHAN_V2_ARTIFACT_CONTRACT_VERSION,
            "source_package": self.source_root,
            "source_hash": self._source_hash(),
            "artifact_hashes": artifact_hashes,
            "required_artifacts": sorted(artifacts),
            "scene": {"dir": scene_dir, "scene_seed": os.path.join(scene_dir, "scene_seed.json")},
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
                "spatial_refinement_snapshot": os.path.join(simulation_dir, "spatial_refinement_snapshot.json"),
                "spread_event_ledger": os.path.join(simulation_dir, "spread_event_ledger.jsonl"),
            },
            "report": {"dir": report_dir, "markdown": os.path.join(report_dir, "full_report.md"), "outline": os.path.join(report_dir, "outline.json")},
            "animation": {"dir": animation_dir, "file": os.path.join(animation_dir, "animation.json")},
            "artifacts": artifacts,
            "compiled_at": WUHAN_V2_COMPILED_AT,
        }
        self._write_json(os.path.join(root, "manifest.json"), manifest)
        return manifest

    def _validate_sources(self) -> None:
        assert self.case_manifest.get("case_id") == WUHAN_V2_CASE_ID
        assert len(self.story_events) == 36
        assert [int(item["round"]) for item in self.story_events] == list(range(1, 37))
        assert len(self.anchor_collection.get("features") or []) == 36
        assert sum(int(item["count"]) for item in self.roster_spec["system_allocations"]) == 240
        assert sum(int(item["core_count"]) for item in self.roster_spec["system_allocations"]) == 72
        assert len(self.roster_spec["archetypes"]) >= 24
        roster_entries = list(self.roster_spec.get("agents") or [])
        assert len(roster_entries) == 240
        assert sum(item.get("representation_level") == "functional" for item in roster_entries) == 72
        assert len({item["roster_id"] for item in roster_entries}) == 240
        anchor_ids = {item["id"] for item in self.anchor_collection["features"]}
        archetype_ids = {item["id"] for item in self.roster_spec["archetypes"]}
        assert {item["anchor_id"] for item in roster_entries} == anchor_ids
        assert all(item["archetype_id"] in archetype_ids for item in roster_entries)
        source_ids = {item["id"] for item in self.source_manifest["sources"]}
        for feature in self.anchor_collection["features"]:
            properties = feature["properties"]
            if properties.get("provenance") == "observed/public_source":
                assert properties.get("source_refs")
            for source_ref in properties.get("source_refs") or []:
                assert source_ref in source_ids
        for item in self.story_events:
            assert len(item.get("storyline_ids") or []) >= 3
            assert len(item.get("actions") or []) >= 4
            for node in item.get("historical_nodes") or []:
                assert node.get("id")
                assert node.get("provenance") == "observed/public_source"
                assert node.get("source_refs")
                assert all(ref in source_ids for ref in node["source_refs"])

    def _build_regions(self) -> List[Dict[str, Any]]:
        items = list(self.case_manifest["macro_scenarios"])
        regions: List[Dict[str, Any]] = []
        for index, item in enumerate(items):
            center = item["center"]
            business_state = self._global_state(0)
            state_vector = {**self._legacy_from_business_state(business_state), **business_state}
            regions.append({
                "region_id": item["id"],
                "name": item["name"],
                "region_type": "城市系统场景",
                "lat": float(center[1]),
                "lon": float(center[0]),
                "system_ids": list(item["system_ids"]),
                "neighbors": [items[(index - 1) % 12]["id"], items[(index + 1) % 12]["id"]],
                "provenance": "curated_projection",
                "state_vector": state_vector,
                "business_state": business_state,
            })
        return regions

    def _build_anchors(self) -> List[Dict[str, Any]]:
        anchors: List[Dict[str, Any]] = []
        for feature in self.anchor_collection["features"]:
            props = dict(feature["properties"])
            coordinates = feature["geometry"]["coordinates"]
            business_state = self._global_state(0)
            state_vector = {**self._legacy_from_business_state(business_state), **business_state}
            anchors.append({
                "region_id": feature["id"],
                "anchor_id": feature["id"],
                "parent_region_id": props["macro_id"],
                "name": props["name"],
                "region_type": "空间锚点",
                "anchor_type": props["anchor_type"],
                "land_use_class": props["anchor_type"],
                "distance_band": "城市级",
                "lat": float(coordinates[1]),
                "lon": float(coordinates[0]),
                "provenance": props["provenance"],
                "source_refs": list(props.get("source_refs") or []),
                "boundary_note": props.get("boundary_note") or "",
                "agent_ids": [],
                "state_vector": state_vector,
                "business_state": business_state,
            })
        return anchors

    def _build_profiles(self, anchors: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        archetype_by_id = {item["id"]: item for item in self.roster_spec["archetypes"]}
        allocation_by_system = {
            item["system_id"]: item for item in self.roster_spec["system_allocations"]
        }
        anchor_by_id = {item["anchor_id"]: item for item in anchors}
        roster_entries = list(self.roster_spec.get("agents") or [])
        profiles: List[Dict[str, Any]] = []
        storyline_name_by_id = {
            item["id"]: item["name"]
            for item in self.case_manifest["storylines"]
        }
        type_by_system = {
            "detection": "OrganizationActor", "healthcare": "OrganizationActor",
            "community": "HumanActor", "mobility": "OrganizationActor",
            "supply": "OrganizationActor", "governance": "GovernmentActor",
        }
        for next_id, roster_entry in enumerate(roster_entries, start=1):
            system_id = roster_entry["system_id"]
            allocation = allocation_by_system[system_id]
            archetype = archetype_by_id[roster_entry["archetype_id"]]
            anchor = anchor_by_id[roster_entry["anchor_id"]]
            offset = int(roster_entry["display_sequence"]) - 1
            representation = roster_entry["representation_level"]
            stable_uid = f"{WUHAN_V2_CASE_ID}::{anchor['anchor_id']}::{archetype['id']}::{offset + 1:02d}"
            jitter_lat = self._stable_jitter(stable_uid + ":lat", 0.0045)
            jitter_lon = self._stable_jitter(stable_uid + ":lon", 0.0060)
            profiles.append({
                    "agent_id": next_id,
                    "agent_uid": stable_uid,
                    "name": f"{anchor['name']}·{archetype['name']}-{offset + 1:02d}",
                    "display_name": f"{anchor['name']}·{archetype['name']}-{offset + 1:02d}",
                    "bio": f"承担{allocation['name']}系统中的{'核心叙事' if representation == 'functional' else '背景协作'}职责，参与{'、'.join(storyline_name_by_id[item] for item in archetype['storyline_ids'])}故事线。",
                    "agent_type": type_by_system[system_id],
                    "agent_subtype": archetype["name"],
                    "archetype_id": archetype["id"],
                    "archetype_name": archetype["name"],
                    "node_family": system_id,
                    "system_id": system_id,
                    "system_name": allocation["name"],
                    "representation_level": representation,
                    "representation_label_zh": "核心职能主体" if representation == "functional" else "聚合背景主体",
                    "is_aggregate": representation == "aggregate",
                    "provenance": "curated_projection",
                    "primary_region": anchor["parent_region_id"],
                    "home_region_id": anchor["parent_region_id"],
                    "home_subregion_id": anchor["anchor_id"],
                    "spatial_anchor_refs": [anchor["anchor_id"]],
                    "storyline_ids": list(archetype["storyline_ids"]),
                    "capabilities": list(archetype["capabilities"]),
                    "capability_keys": list(archetype["capabilities"]),
                    "resources": self._resources_for_system(system_id),
                    "resource_budget": {
                        name: 60 + ((offset + resource_index * 7) % 36)
                        for resource_index, name in enumerate(self._resources_for_system(system_id))
                    },
                    "goals": [f"维持{allocation['name']}系统连续运行", f"推动{archetype['name']}职责与城市协同衔接"],
                    "permissions": ["读取所属锚点态势", "提交职责范围内行动", "参与跨系统协同"],
                    "permission_keys": ["读取所属锚点态势", "提交职责范围内行动", "参与跨系统协同"],
                    "action_space_zh": ["观察", "协同", "反馈", "执行职责行动"],
                    "profile_confidence": 0.86 if representation == "functional" else 0.74,
                    "role_demand_refs": [f"role-demand::{archetype['id']}"],
                    "evidence_refs": list(anchor.get("source_refs") or []),
                    "authority_evidence_refs": [anchor["anchor_id"]],
                    "created_round": 0 if representation == "functional" else (offset % 12),
                    "generation_reason": f"根据{anchor['name']}的空间职责与{archetype['name']}能力需求策划配置。",
                    "lifecycle": {"activation_round": 0 if representation == "functional" else (offset % 12), "end_round": 36, "status": "active"},
                    "lat": round(float(anchor["lat"]) + jitter_lat, 6),
                    "lon": round(float(anchor["lon"]) + jitter_lon, 6),
                "state_vector": self._agent_state_vector(system_id, next_id),
            })
        return profiles

    @staticmethod
    def _attach_anchor_agents(anchors: List[Dict[str, Any]], profiles: Sequence[Mapping[str, Any]]) -> None:
        by_anchor = {item["anchor_id"]: item for item in anchors}
        for profile in profiles:
            by_anchor[profile["home_subregion_id"]]["agent_ids"].append(profile["agent_id"])

    def _build_relationships(self, profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        relationships: List[Dict[str, Any]] = []
        total = len(profiles)
        for index in range(1800):
            source = profiles[index % total]
            target_index = (index * 37 + index // total + 17) % total
            if target_index == index % total:
                target_index = (target_index + 1) % total
            target = profiles[target_index]
            relation_key, relation_label, layer = self.RELATION_TYPES[index % len(self.RELATION_TYPES)]
            relationships.append({
                "edge_id": f"relation::{index + 1:04d}",
                "source_agent_id": source["agent_id"],
                "target_agent_id": target["agent_id"],
                "relation_type": relation_key,
                "relation_label": relation_label,
                "interaction_channel": relation_label,
                "layer": layer,
                "strength": round(0.24 + (index % 11) * 0.055, 3),
                "confidence": round(0.66 + (index % 7) * 0.035, 3),
                "provenance": "curated_projection",
                "rationale": f"{source['archetype_name']}通过{relation_label}连接{target['archetype_name']}，形成城市系统的{'重点机制' if layer == '机制运行关系' else '稳定背景'}。",
                "storyline_ids": sorted(set(source["storyline_ids"]) | set(target["storyline_ids"])),
            })
        return relationships

    def _build_transport_edges(self, regions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        channels = ("铁路客流", "航空门户", "医疗转运", "物资配送")
        for index, region in enumerate(regions):
            for offset in (1, 3):
                target = regions[(index + offset) % len(regions)]
                edges.append({
                    "edge_id": f"transport::{region['region_id']}::{target['region_id']}",
                    "source_region_id": region["region_id"],
                    "target_region_id": target["region_id"],
                    "channel_type": channels[(index + offset) % len(channels)],
                    "directionality": "directed",
                    "travel_time_rounds": 1 if offset == 1 else 2,
                    "attenuation_rate": 0.18 if offset == 1 else 0.32,
                    "strength": round(0.48 + (index % 5) * 0.07, 2),
                    "confidence": 0.78,
                    "provenance": "curated_projection",
                })
        return edges

    def _build_curated_role_demands(
        self,
        *,
        regions: Sequence[Mapping[str, Any]],
        graph_edges: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Express V2 roster needs through the production RoleDemand shape."""

        demand_key_by_system = {
            "detection": "public_health_detection",
            "healthcare": "healthcare_capacity_coordination",
            "community": "affected_population",
            "mobility": "transport_continuity",
            "supply": "critical_supply_coordination",
            "governance": "cross_agency_governance",
        }
        resolution_by_system = {
            "detection": "organization",
            "healthcare": "specific_facility",
            "community": "population_group",
            "mobility": "organization",
            "supply": "organization",
            "governance": "organization",
        }
        mechanism_ids_by_event: Dict[str, List[str]] = {}
        for edge in graph_edges:
            mechanism_id = str(edge.get("mechanism_id") or edge.get("edge_id") or "")
            for event_id in (
                str(edge.get("source_event_id") or ""),
                str(edge.get("target_event_id") or ""),
            ):
                if mechanism_id and event_id:
                    mechanism_ids_by_event.setdefault(event_id, []).append(mechanism_id)

        demands: List[Dict[str, Any]] = []
        for archetype in self.roster_spec["archetypes"]:
            system_id = str(archetype["system_id"])
            event_ids = [
                f"mechanism::{storyline_id}"
                for storyline_id in archetype["storyline_ids"]
            ]
            region_ids = [
                str(region["region_id"])
                for region in regions
                if system_id in (region.get("system_ids") or [])
            ]
            capabilities = list(archetype["capabilities"])
            if system_id == "detection":
                # The generic compiler recognizes these internal capability
                # keys without changing the Chinese roster presentation.
                capabilities.extend(["monitoring", "laboratory"])
            demands.append({
                "demand_id": f"role-demand::{archetype['id']}",
                "demand_key": demand_key_by_system[system_id],
                "label_zh": archetype["name"],
                "name": archetype["name"],
                "capabilities": list(archetype["capabilities"]),
                "required_capability_keys": capabilities,
                "storyline_ids": list(archetype["storyline_ids"]),
                "caused_by_event_ids": event_ids,
                "caused_by_mechanism_ids": sorted({
                    mechanism_id
                    for event_id in event_ids
                    for mechanism_id in mechanism_ids_by_event.get(event_id, [])
                }),
                "jurisdiction_region_ids": region_ids,
                "required_resolution": resolution_by_system[system_id],
                "importance": "critical" if system_id == "healthcare" else "high",
                "rationale_zh": f"{archetype['name']}用于承接{system_id}城市系统的策划能力需求。",
            })
        return demands

    @staticmethod
    def _build_curated_spatial_catalog(
        anchors: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Mark public anchors D and designed networks S; neither is formal R3."""

        def facility_classes(anchor: Mapping[str, Any]) -> List[str]:
            text = f"{anchor.get('name') or ''} {anchor.get('anchor_type') or ''}"
            classes: List[str] = []
            rules = (
                (("医院", "医疗", "门诊", "方舱", "救治", "床位"), ("hospital", "emergency_hospital", "emergency_medical_center")),
                (("疾控", "检测", "检验", "采样", "筛查"), ("monitoring_institution", "analytical_laboratory")),
                (("铁路", "航空", "机场", "交通", "转运"), ("public_transport_hub", "road_network_node")),
                (("社区", "照护", "重点人群"), ("residential_community",)),
                (("仓储", "供应", "保供", "药品", "分拨"), ("emergency_warehouse", "logistics_hub")),
                (("指挥", "信息", "热线", "治理"), ("local_government_command_center", "emergency_management_authority", "responsible_public_authority")),
                (("市场",), ("seafood_market",)),
            )
            for tokens, class_keys in rules:
                if any(token in text for token in tokens):
                    classes.extend(class_keys)
            return list(dict.fromkeys(classes))

        catalog: List[Dict[str, Any]] = []
        for anchor in anchors:
            provenance = str(anchor.get("provenance") or "")
            public_anchor = provenance == "observed/public_source"
            catalog.append({
                **dict(anchor),
                "id": anchor.get("anchor_id") or anchor.get("region_id"),
                "name": anchor.get("name") or "",
                "kind": "entity",
                "subtype": "curated_public_anchor" if public_anchor else "curated_function_network",
                "facility_class_keys": facility_classes(anchor),
                "target_region_ids": [str(anchor.get("parent_region_id") or "")],
                "lat": anchor.get("lat"),
                "lon": anchor.get("lon"),
                "source_kind": "curated_public_anchor" if public_anchor else "synthetic_model",
                "provider": "wuhan_curated_fixture",
                "evidence_grade": "D" if public_anchor else "S",
                "provenance": provenance or "curated_projection",
                "evidence_refs": list(anchor.get("source_refs") or []),
                "spatial_fixture_id": WUHAN_V2_SPATIAL_FIXTURE_ID,
            })
        return catalog

    @staticmethod
    def _build_spatial_evidence_summary(
        facility_query_plan: Mapping[str, Any],
        spatial_refinement_snapshot: Mapping[str, Any],
    ) -> Dict[str, int]:
        return {
            "request_count": len(facility_query_plan.get("requests") or []),
            "required_r3_count": len(facility_query_plan.get("required_r3_request_ids") or []),
            "required_r4_count": len(facility_query_plan.get("required_r4_request_ids") or []),
            "covered_r3_count": sum(
                1
                for item in spatial_refinement_snapshot.get("request_coverage") or []
                if item.get("resolution_level") == "R3" and item.get("status") == "covered"
            ),
            "blocking_gap_count": sum(
                1
                for item in spatial_refinement_snapshot.get("evidence_gaps") or []
                if item.get("blocking") is True
            ),
        }

    def _build_planning_artifacts(
        self, *, effort_snapshot: Mapping[str, Any], regions: Sequence[Mapping[str, Any]],
        anchors: Sequence[Mapping[str, Any]], profiles: Sequence[Mapping[str, Any]],
        relationships: Sequence[Mapping[str, Any]], risk_bundle: Mapping[str, Any],
    ) -> Dict[str, Any]:
        event_nodes = []
        for index, storyline in enumerate(self.case_manifest["storylines"]):
            target_regions = [
                region["region_id"]
                for region in regions
                if storyline["id"] in region["system_ids"]
            ]
            event_nodes.append({
                "event_id": f"mechanism::{storyline['id']}",
                "node_id": f"mechanism::{storyline['id']}",
                "label_zh": storyline["name"],
                "description_zh": f"贯穿36轮的{storyline['name']}机制链。",
                "atomic_key": storyline["id"],
                "event_kind": "curated_city_system_process",
                "hazard_family": "public_health",
                "origin": "curated_target_state",
                "target_region_ids": target_regions,
                "target_entity_ids": [],
                "order": index + 1,
            })
        event_nodes.extend([
            {"event_id":"mechanism::risk_feedback","node_id":"mechanism::risk_feedback","label_zh":"风险反馈","description_zh":"风险状态回流到主体行动与资源优先级。","atomic_key":"risk_feedback","event_kind":"curated_city_system_process","hazard_family":"public_health","origin":"curated_target_state","target_region_ids":[item["region_id"] for item in regions],"target_entity_ids":[],"order":7},
            {"event_id":"mechanism::policy_coordination","node_id":"mechanism::policy_coordination","label_zh":"政策协同","description_zh":"政策介入通过执行主体影响运行关系。","atomic_key":"policy_coordination","event_kind":"curated_city_system_process","hazard_family":"governance","origin":"curated_target_state","target_region_ids":[item["region_id"] for item in regions],"target_entity_ids":[],"order":8},
        ])
        node_labels = {
            item["event_id"].split("::", 1)[1]: item["label_zh"]
            for item in event_nodes
        }
        graph_edges = []
        links = [
            ("detection","healthcare","病例识别推动分诊与收治"), ("healthcare","supply","医疗负荷形成物资需求"),
            ("mobility","detection","跨区流动扩大追踪范围"), ("community","detection","社区排查补充发现线索"),
            ("supply","community","供应连续性支撑社区照护"), ("governance","community","信息与指挥转化为基层行动"),
            ("governance","mobility","指挥网络调整交通运行"), ("healthcare","community","分级收治连接社区支持"),
            ("detection","risk_feedback","检测可见度更新风险判断"), ("healthcare","risk_feedback","容量负荷更新风险判断"),
            ("mobility","risk_feedback","流动强度更新风险判断"), ("risk_feedback","policy_coordination","风险反馈调整政策优先级"),
            ("policy_coordination","detection","政策支持监测追踪"), ("policy_coordination","healthcare","政策支持医疗扩容"),
            ("policy_coordination","community","政策支持社区治理"), ("policy_coordination","supply","政策支持供应保障"),
            ("policy_coordination","mobility","政策调整流动网络"), ("community","governance","诉求反馈修正公共信息"),
        ]
        for index, (source, target, label) in enumerate(links):
            graph_edges.append({
                "edge_id": f"mechanism-edge::{index + 1:02d}",
                "mechanism_id": f"mechanism-edge::{index + 1:02d}",
                "source_event_id": f"mechanism::{source}",
                "target_event_id": f"mechanism::{target}",
                "source_label": node_labels[source],
                "target_label": node_labels[target],
                "relation_label_zh": label,
                "mechanism_zh": label,
            })
        temporal_plan = {
            "contract_version": "temporal-plan.v2",
            "step_unit": "day", "step_size": 3, "total_rounds": 36,
            "reference_time": self.case_manifest["reference_time"],
            "event_windows": [
                {"event_id": f"mechanism::{item['id']}", "start_round": 1, "duration_rounds": 36}
                for item in self.case_manifest["storylines"]
            ],
            "chapters": list(self.case_manifest["chapters"]),
        }
        policies = [dict(item, input_id=item["id"], intent=item["intent"]) for item in self.analysis_spec["policies"]]
        normalized_events = [
            {
                "input_id": f"storyline::{item['id']}", "name": item["name"],
                "description": f"沿36轮持续推进的{item['name']}故事线。",
                "target_region_ids": [region["region_id"] for region in regions if item["id"] in region["system_ids"]],
                "target_entity_ids": [], "order": index + 1,
            }
            for index, item in enumerate(self.case_manifest["storylines"])
        ]
        role_demands = self._build_curated_role_demands(
            regions=regions,
            graph_edges=graph_edges,
        )
        planning_core = {
            "contract_version": "scenario-planning.v2",
            "planning_input_id": "scenario-plan::wuhan_covid_v2",
            "foundation_ref": {"foundation_id":"foundation::wuhan_covid_v2","artifact_id":"foundation::wuhan_covid_v2","location":"武汉市","region_ids":[r["region_id"] for r in regions]},
            "effort_snapshot_ref": dict(effort_snapshot),
            "normalized_user_events": normalized_events,
            "event_mechanism_graph": {"graph_id":"mechanism-graph::wuhan_covid_v2","nodes":event_nodes,"edges":graph_edges},
            "temporal_plan": temporal_plan,
            "policy_plan": policies,
            "role_demands": role_demands,
            "assumptions": list(self.analysis_spec["uncertainty_boundaries"]),
            "generation_mode": "curated_target_state",
        }
        planning_core["content_hash"] = self._hash_payload(planning_core)
        compiled_facility_plan = compile_facility_query_plan(planning_core)
        facility_query_plan = compiled_facility_plan.to_dict()
        spatial_refinement_snapshot = build_spatial_refinement_snapshot(
            compiled_facility_plan,
            target_catalog=self._build_curated_spatial_catalog(anchors),
            provider_attempts=[
                {
                    "provider": "wuhan_curated_fixture",
                    "status": "fixture_candidates_only",
                    "observed": False,
                    "note_zh": "公开地点锚点与策划网络仅作为候选，不冒充生产 R3 设施核验。",
                }
            ],
            source_versions=[
                {
                    "source_key": WUHAN_V2_SPATIAL_FIXTURE_ID,
                    "version": "wuhan-covid-v2.curated-networks.v1",
                    "evidence_grade": "S",
                },
                *[
                    {
                        "source_key": item["id"],
                        "version": "wuhan-covid-v2.source-manifest.v1",
                        "evidence_grade": "D",
                    }
                    for item in self.source_manifest["sources"]
                ],
            ],
        ).to_dict()
        spatial_evidence_summary = self._build_spatial_evidence_summary(
            facility_query_plan,
            spatial_refinement_snapshot,
        )
        agent_request = {
            "contract_version":"agent-planning-request.v2",
            "source":"curated_target_state",
            "simulation_requirement":"复盘六个城市系统在36轮中的行动、关系、风险和资源状态变化。",
            "target_agent_count":240,
            "injected_variables":[dict(item) for item in self.case_manifest["state_dimensions"]],
            "role_demands":planning_core["role_demands"],
            "facility_query_plan_ref":{
                key: facility_query_plan.get(key)
                for key in ("contract_version", "plan_id", "content_hash")
            },
            "spatial_refinement_snapshot_ref":{
                key: spatial_refinement_snapshot.get(key)
                for key in ("contract_version", "snapshot_id", "content_hash")
            },
            "spatial_evidence_summary":spatial_evidence_summary,
        }
        return {
            "effort_snapshot":dict(effort_snapshot),
            "scenario_planning_input":planning_core,
            "event_mechanism_graph":planning_core["event_mechanism_graph"],
            "temporal_plan":temporal_plan,
            "policy_plan":policies,
            "role_demands":planning_core["role_demands"],
            "assumptions":planning_core["assumptions"],
            "agent_planning_request":agent_request,
            "facility_query_plan":facility_query_plan,
            "spatial_refinement_snapshot":spatial_refinement_snapshot,
            "spatial_evidence_summary":spatial_evidence_summary,
        }

    def _build_simulation_config(
        self, *, definition: Any, effort_snapshot: Mapping[str, Any], regions: Sequence[Mapping[str, Any]],
        anchors: Sequence[Mapping[str, Any]], profiles: Sequence[Mapping[str, Any]],
        relationships: Sequence[Mapping[str, Any]], transport_edges: Sequence[Mapping[str, Any]],
        risk_bundle: Mapping[str, Any], planning_artifacts: Mapping[str, Any],
    ) -> Dict[str, Any]:
        time_plan = normalize_time_plan(
            {"step_unit":"day","step_size":3,"total_rounds":36,"reference_time":definition.reference_time,"source":"curated_target_state"},
            total_rounds=36, minutes_per_round=4320, preset="slow",
            reference_time=definition.reference_time, source="curated_target_state",
        )
        return {
            "simulation_id":f"golden::{definition.case_id}", "project_id":f"golden_project::{definition.case_id}",
            "graph_id":f"golden_graph::{definition.case_id}", "engine_mode":"envfish",
            "simulation_architecture":SIMULATION_ARCHITECTURE, "scenario_mode":definition.scenario_mode,
            "diffusion_template":definition.diffusion_template, "hazard_template_id":definition.hazard_template_id,
            "hazard_template_mode":"curated_projection", "search_mode":"ultra",
            "simulation_requirement":"复盘武汉疫情期间六个城市系统的行动、关系、风险和资源状态变化。",
            "reference_time":definition.reference_time, "time_plan_mode":"manual", "time_plan":time_plan,
            "temporal_plan":planning_artifacts["temporal_plan"], "effort_snapshot":dict(effort_snapshot),
            "generation_mode":"curated_target_state", "artifact_mode":"frozen", "agent_plan_source":"curated_target_state",
            "scenario_planning_input":planning_artifacts["scenario_planning_input"],
            "event_mechanism_graph":planning_artifacts["event_mechanism_graph"],
            "policy_plan":planning_artifacts["policy_plan"], "role_demands":planning_artifacts["role_demands"],
            "assumptions":planning_artifacts["assumptions"], "agent_planning_request":planning_artifacts["agent_planning_request"],
            "scenario_state_schema":{"contract_version":"scenario-state-schema.v2","dimensions":list(self.case_manifest["state_dimensions"])},
            "region_graph":[dict(item) for item in regions], "subregion_graph":[dict(item) for item in anchors],
            "agent_configs":[dict(item) for item in profiles], "actor_profiles":[dict(item) for item in profiles],
            "agent_relationship_graph":[dict(item) for item in relationships], "transport_edges":[dict(item) for item in transport_edges],
            "risk_definitions":[dict(item) for item in risk_bundle["risk_definitions"]],
            "risk_objects":[dict(item) for item in risk_bundle["risk_objects"]],
            "capabilities":dict(self.case_manifest["capabilities"]),
            "storylines":list(self.case_manifest["storylines"]), "story_chapters":list(self.case_manifest["chapters"]),
        }

    def _build_round_snapshots(
        self, regions: Sequence[Mapping[str, Any]], anchors: Sequence[Mapping[str, Any]], profiles: Sequence[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        snapshots: List[Dict[str, Any]] = []
        reference = datetime.fromisoformat(self.case_manifest["reference_time"])
        for story in self.story_events:
            round_num = int(story["round"])
            phase = story["state_phase"]
            global_state = self._global_state(round_num)
            region_rows = []
            for index, region in enumerate(regions):
                factor = 0.88 + (index % 5) * 0.04
                state = {key: self._clamp(value * factor if key in {"exposure_pressure","healthcare_load","mobility_intensity"} else 50 + (value - 50) * factor) for key, value in global_state.items()}
                legacy = self._legacy_from_business_state(state)
                region_rows.append({
                    "region_id":region["region_id"], "name":region["name"], "region_type":region["region_type"],
                    "tagline":"行动 / 关系 / 风险 / 资源", **state, **legacy,
                    "business_state":state, "severity_band":"高" if legacy["vulnerability_score"] >= 70 else "中" if legacy["vulnerability_score"] >= 45 else "低",
                    "uncertainty_band":{"confidence":0.78,"provenance":"curated_projection"},
                })
            anchor_rows = []
            for index, anchor in enumerate(anchors):
                local = dict(global_state)
                local["exposure_pressure"] = self._clamp(local["exposure_pressure"] + ((index % 7) - 3) * 1.7)
                local["healthcare_load"] = self._clamp(local["healthcare_load"] + ((index % 5) - 2) * 1.4)
                legacy = self._legacy_from_business_state(local)
                anchor_rows.append({
                    "region_id":anchor["anchor_id"], "parent_region_id":anchor["parent_region_id"], "name":anchor["name"],
                    "region_type":"空间锚点", "land_use_class":anchor["anchor_type"], "distance_band":"城市级",
                    "agent_ids":list(anchor["agent_ids"]), **local, **legacy, "business_state":local,
                })
            agents = []
            for profile in profiles:
                personal = {key:self._clamp(value + self._stable_jitter(f"{profile['agent_uid']}:{round_num}:{key}", 3.8)) for key,value in global_state.items()}
                agents.append({
                    "agent_id":profile["agent_id"], "agent_uid":profile["agent_uid"], "name":profile["name"],
                    "agent_type":profile["agent_type"], "agent_subtype":profile["agent_subtype"],
                    "primary_region":profile["primary_region"], "home_subregion_id":profile["home_subregion_id"],
                    "representation_level":profile["representation_level"], "storyline_ids":profile["storyline_ids"],
                    "business_state":personal, "state_vector":{**self._legacy_from_business_state(personal), **personal},
                })
            snapshots.append({
                "round":round_num, "timestamp":(reference + timedelta(days=3 * round_num)).isoformat(),
                "chapter_id":self._chapter_for_round(round_num)["id"], "chapter_name":self._chapter_for_round(round_num)["name"],
                "headline":story["headline"], "storyline_ids":list(story["storyline_ids"]), "visible_highlights":list(story["actions"][:6]),
                "historical_nodes":list(story.get("historical_nodes") or []), "policy_ids":list(story.get("policy_ids") or []),
                "risk_focus":story["risk_focus"], "state_phase":phase, "business_state":global_state,
                "regions":region_rows, "subregions":anchor_rows, "agents":agents,
                "interactions":{"agent_interactions":[],"agent_environment_effects":[]},
                "agent_summary":{"active_agents":240,"core_agents":72,"background_agents":168},
                "feedback":{"feedback_propagation":[{"loop":"发现 → 检测 → 分诊 → 收治"},{"loop":"社区诉求 → 供应调度 → 公共信息 → 信任反馈"}]},
                "search_mode":"ultra", "scenario_mode":"crisis_mode", "provenance":"curated_projection",
            })
        return snapshots

    def _build_interactions(self, profiles: Sequence[Mapping[str, Any]], anchors: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        by_id = {item["agent_id"]:item for item in profiles}
        anchor_name_by_id = {item["anchor_id"]: item["name"] for item in anchors}
        for story in self.story_events:
            round_num = int(story["round"])
            for index in range(12):
                source = profiles[(round_num * 19 + index * 7) % len(profiles)]
                target = profiles[(round_num * 31 + index * 13 + 41) % len(profiles)]
                if source["agent_id"] == target["agent_id"]:
                    target = by_id[(target["agent_id"] % len(profiles)) + 1]
                action_key, action_label = self.ACTION_TYPES[(round_num + index) % len(self.ACTION_TYPES)]
                action_summary = story["actions"][index % len(story["actions"])]
                rows.append({
                    "id":f"interaction::{round_num:02d}::{index + 1:02d}", "round":round_num,
                    "channel":action_label, "interaction_channel":action_label,
                    "source_agent_id":source["agent_id"], "source_agent_name":source["name"],
                    "target_agent_id":target["agent_id"], "target_agent_name":target["name"],
                    "source_region_name":anchor_name_by_id[source["home_subregion_id"]], "target_region_name":anchor_name_by_id[target["home_subregion_id"]],
                    "action_type":action_key, "action_label":action_label,
                    "summary":f"{source['name']}与{target['name']}协同执行：{action_summary}。",
                    "rationale":f"推进“{story['headline']}”并连接{source['system_name']}与{target['system_name']}。",
                    "storyline_ids":list(story["storyline_ids"]), "provenance":"curated_projection",
                    "delta":{"public_trust":round(-0.3 + index * 0.06,2),"community_support":round(0.2 + (index % 4) * 0.12,2)},
                    "display_priority":"primary" if index < 4 else "background",
                })
        return rows

    def _build_dynamic_edges(self, profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        relation_types = (
            ("reporting_link", "上报链路", "detection", "governance"),
            ("clinical_referral", "临床转诊", "detection", "healthcare"),
            ("supply_route", "物资调拨", "supply", "healthcare"),
            ("community_support", "社区支持", "community", "supply"),
            ("mobility_control", "交通协同", "mobility", "governance"),
            ("public_feedback", "诉求反馈", "community", "governance"),
        )
        profiles_by_system = {
            system_id: [item for item in profiles if item["system_id"] == system_id]
            for system_id in {item["system_id"] for item in profiles}
        }
        lifecycle_actions = (
            ("created", "创建"),
            ("activated", "激活"),
            ("strengthened", "增强"),
            ("weakened", "减弱"),
            ("resolved", "结束"),
        )
        scheduled: Dict[int, List[Dict[str, Any]]] = {round_num: [] for round_num in range(1, 37)}

        # Twelve highlighted mechanism relationships carry a real five-stage
        # lifecycle across separated chapters.  The remaining relations are
        # dense one-round context events, so the graph stays rich without
        # pretending that every background link deserves a full narrative.
        for lifecycle_index in range(12):
            relation_index = lifecycle_index % len(relation_types)
            relation_key, relation_label, source_system, target_system = relation_types[relation_index]
            source_pool = profiles_by_system[source_system]
            target_pool = profiles_by_system[target_system]
            source = source_pool[(lifecycle_index * 3) % len(source_pool)]
            target = target_pool[(lifecycle_index * 5 + 2) % len(target_pool)]
            created_round = lifecycle_index % 6 + 1
            edge_id = f"dynamic::lifecycle::{lifecycle_index + 1:02d}"
            for action_index, (action_key, action_label) in enumerate(lifecycle_actions):
                round_num = created_round + action_index * 7
                scheduled[round_num].append({
                    "edge_id":edge_id,
                    "event_id":f"dynamic-event::{round_num:02d}::{len(scheduled[round_num]) + 1:02d}",
                    "round":round_num,
                    "source_agent_id":source["agent_id"], "target_agent_id":target["agent_id"],
                    "edge_type":relation_key, "relation_label":relation_label,
                    "interaction_channel":relation_label, "layer":"机制运行关系",
                    "origin":"curated_target_state", "scope":"城市系统",
                    "strength":round((0.42, 0.56, 0.72, 0.5, 0.2)[action_index], 2),
                    "confidence":0.82, "status":action_key,
                    "lifecycle_action":action_key, "lifecycle_label":action_label,
                    "created_round":created_round,
                    "last_activated_round":round_num if action_key == "activated" else max(created_round, round_num - 1),
                    "rationale":f"第{round_num}轮{action_label}{relation_label}，连接{source['archetype_name']}与{target['archetype_name']}。",
                    "provenance":"curated_projection",
                })

        context_counter = 0
        for round_num in range(1, 37):
            while len(scheduled[round_num]) < 6:
                slot = len(scheduled[round_num])
                relation_index = (round_num + slot) % len(relation_types)
                relation_key, relation_label, source_system, target_system = relation_types[relation_index]
                source_pool = profiles_by_system[source_system]
                target_pool = profiles_by_system[target_system]
                source = source_pool[(round_num * 3 + slot) % len(source_pool)]
                target = target_pool[(round_num * 5 + slot + 2) % len(target_pool)]
                action_key, action_label = self.LIFECYCLE_ACTIONS[(round_num + slot) % len(self.LIFECYCLE_ACTIONS)]
                context_counter += 1
                scheduled[round_num].append({
                    "edge_id":f"dynamic::context::{context_counter:03d}",
                    "event_id":f"dynamic-event::{round_num:02d}::{len(scheduled[round_num]) + 1:02d}",
                    "round":round_num,
                    "source_agent_id":source["agent_id"], "target_agent_id":target["agent_id"],
                    "edge_type":relation_key, "relation_label":relation_label,
                    "interaction_channel":relation_label, "layer":"机制运行关系",
                    "origin":"curated_target_state", "scope":"城市系统",
                    "strength":round(0.42 + ((round_num + slot) % 8) * 0.06, 2),
                    "confidence":0.78, "status":action_key,
                    "lifecycle_action":action_key, "lifecycle_label":action_label,
                    "created_round":round_num, "last_activated_round":round_num,
                    "rationale":f"第{round_num}轮{action_label}{relation_label}，连接{source['archetype_name']}与{target['archetype_name']}。",
                    "provenance":"curated_projection",
                })

        rows = [item for round_num in range(1, 37) for item in scheduled[round_num]]
        return rows

    def _build_spread_events(self, regions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        rounds = (2,5,8,10,11,13,15,18,21,24,30,36)
        rows = []
        for index, round_num in enumerate(rounds):
            source = regions[index % len(regions)]
            target = regions[(index + 1) % len(regions)]
            rows.append({
                "event_id":f"spread::{round_num:02d}", "round":round_num, "status":"applied",
                "source_region_id":source["region_id"], "target_region_id":target["region_id"],
                "source_variable_id":"exposure_pressure", "transport_edge_id":f"transport::{source['region_id']}::{target['region_id']}",
                "projection_rule":"策划主线中的跨系统状态传递", "title":"城市系统压力跨区传递",
                "summary":f"{source['name']}的压力通过运行网络传递至{target['name']}。",
                "provenance":"curated_projection",
            })
        return rows

    def _build_risk_bundle(self, regions: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        definitions = []
        objects = []
        graph_refs = {
            "hidden_transmission":["mechanism::detection","mechanism::mobility"],
            "healthcare_overload":["mechanism::healthcare","mechanism::supply"],
            "cross_district_mobility":["mechanism::mobility","mechanism::policy_coordination"],
            "supply_continuity":["mechanism::supply","mechanism::community"],
            "information_trust":["mechanism::governance","mechanism::risk_feedback"],
        }
        for index, risk in enumerate(self.analysis_spec["risks"]):
            definitions.append({
                "risk_id":risk["id"], "title":risk["name"], "description":risk["description"],
                "mechanism_node_ids":graph_refs[risk["id"]], "mechanism_edge_ids":[],
                "provenance":"curated_projection",
            })
            objects.append({
                "risk_object_id":f"risk-object::{risk['id']}", "risk_id":risk["id"], "title":risk["name"],
                "summary":risk["description"], "why_now":"该风险在主线账本中持续经历形成、抬升、缓解或转型。",
                "severity_score":round(self._risk_score(risk["id"], 18),2), "actionability_score":72-index*2,
                "confidence_score":0.78, "mode":"lifecycle", "chain_steps":["形成","抬升","响应","缓解","持续监测"],
                "root_pressures":["系统反馈延迟","资源与需求错配"], "source_entity_uuids":[],
                "primary_regions":[regions[index % len(regions)]["name"]], "region_scope":[r["name"] for r in regions[index:index+3]],
                "affected_clusters":[], "turning_points":[item["title"] for item in self.analysis_spec["turning_points"] if item["round"] in {9,11,15,24,36}],
                "scenario_branches":[], "evidence":[{"title":"冻结风险账本","summary":"由36轮状态与行动账本投影。","entity_refs":[]}],
                "provenance":"curated_projection",
            })
        history = []
        events = []
        for story in self.story_events:
            round_num = int(story["round"])
            states = []
            for risk in self.analysis_spec["risks"]:
                score = self._risk_score(risk["id"], round_num)
                states.append({
                    "risk_id":risk["id"], "severity_score":score,
                    "trend":"上升" if round_num <= 15 else "缓解" if round_num >= 22 else "高位波动",
                    "active_step_ids":[story["headline"]],
                })
            history.append({"round":round_num,"primary_active_risk_id":story["risk_focus"],"risk_states":states,"pinned_risk_ids":[story["risk_focus"]]})
            focus = next(item for item in self.analysis_spec["risks"] if item["id"] == story["risk_focus"])
            events.append({
                "id":f"risk-event::{round_num:02d}", "round":round_num, "event_type":"风险状态变化",
                "risk_id":focus["id"], "title":f"{focus['name']}状态更新", "summary":story["headline"],
                "severity_score":self._risk_score(focus["id"], round_num),
                "region_scope":[regions[round_num % len(regions)]["name"]], "provenance":"curated_projection",
            })
        return {
            "risk_definitions":definitions, "risk_objects":objects,
            "risk_objects_summary":{"primary_risk_object_id":"risk-object::hidden_transmission","primary_active_risk_id":history[-1]["primary_active_risk_id"],"primary_risk_object":objects[0],"risk_definitions_count":5,"risk_event_count":36},
            "latest_risk_runtime_state":history[-1], "risk_runtime_history":history, "risk_events":events,
        }

    def _build_foundation(self, effort_snapshot: Mapping[str, Any], anchors: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        raw = {
            "foundation_id":"foundation::wuhan_covid_v2", "contract_version":"foundation.curated.v2", "location":"武汉市",
            "region_ids":[item["id"] for item in self.case_manifest["macro_scenarios"]],
            "regions":list(self.case_manifest["macro_scenarios"]),
            "target_catalog":self._build_curated_spatial_catalog(anchors),
            "baseline_state":{"time_scope":"2019-12-22 至 2020-04-08（108天）","city_systems":[item["name"] for item in self.case_manifest["storylines"]],"state_dimensions":list(self.case_manifest["state_dimensions"])},
            "source_refs":list(self.source_manifest["sources"]),
            "research_questions":["异常临床信号如何变成可见的公共卫生事件？","医疗、交通、社区、供应与信息系统如何在压力下重新连接？","政策介入前后，主线账本中的状态如何变化？"],
            "analysis_boundaries":list(self.analysis_spec["uncertainty_boundaries"]), "open_data_gaps":["不提供逐人历史行动记录","不进行反事实因果验证"],
        }
        foundation = project_background_foundation(raw, effort_snapshot_ref=effort_snapshot)
        foundation.update({
            "generation_mode":"curated_target_state", "artifact_mode":"frozen", "title":self.case_manifest["title"],
            "summary":self.case_manifest["summary"], "time_scope":"2019-12-22 至 2020-04-08", "duration_days":108,
            "city_systems":list(self.case_manifest["storylines"]), "source_boundary":self.source_manifest["boundary_note"],
            "report_markdown":self._build_foundation_markdown(), "capabilities":dict(self.case_manifest["capabilities"]),
        })
        return foundation

    def _build_analysis_bundle(
        self, *, round_snapshots: Sequence[Mapping[str, Any]],
        risk_bundle: Mapping[str, Any], policy_events: Sequence[Mapping[str, Any]],
        dynamic_edges: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        by_round = {int(item["round"]):item for item in round_snapshots}
        findings = [{"finding_id":f"finding::{index+1}","title":text,"summary":text,"evidence_rounds":[3,9,15,24,36]} for index,text in enumerate(self.analysis_spec["conclusions"])]
        turning = [dict(item, evidence_ref=f"round::{item['round']}", provenance="curated_projection") for item in self.analysis_spec["turning_points"]]
        risk_outcomes = []
        for risk in self.analysis_spec["risks"]:
            matching_risk_events = [
                item for item in risk_bundle["risk_events"]
                if item.get("risk_id") == risk["id"]
            ]
            risk_outcomes.append({
                "risk_id":risk["id"], "title":risk["name"], "summary":risk["description"],
                "peak_score":max(self._risk_score(risk["id"], r) for r in range(1,37)),
                "ending_score":self._risk_score(risk["id"],36), "lifecycle":"形成 → 抬升 → 响应 → 缓解/转型",
                "evidence_refs":[item["id"] for item in matching_risk_events],
            })
        observations = []
        for policy in self.analysis_spec["policies"]:
            before_round = max(1, int(policy["round_start"]) - 1)
            after_round = min(36, int(policy["round_start"]) + 3)
            before = by_round[before_round]["business_state"]
            after = by_round[after_round]["business_state"]
            observations.append({
                "intervention_id":policy["id"], "title":policy["name"], "intent":policy["intent"],
                "start_round":policy["round_start"], "end_round":policy["round_end"],
                "before_round":before_round, "after_round":after_round,
                "state_changes":[{"dimension_id":dim["id"],"dimension_name":dim["name"],"before":before[dim["id"]],"after":after[dim["id"]],"delta":round(after[dim["id"]]-before[dim["id"]],2)} for dim in self.case_manifest["state_dimensions"]],
                "observation_boundary":"这是主线账本中的介入前后状态观察，不构成反事实因果证明。",
                "evidence_refs":[f"policy-event::{policy['id']}::{policy['round_start']:02d}",f"round::{before_round}",f"round::{after_round}"],
            })
        evidence = []
        for source in self.source_manifest["sources"]:
            evidence.append({"evidence_id":source["id"],"title":source["title"],"publisher":source["publisher"],"url":source["url"],"provenance":source["provenance"],"claim_scope":source["claim_scope"]})
        evidence.extend([{"evidence_id":f"round::{item['round']}","title":f"第{item['round']}轮冻结账本","summary":item["headline"],"provenance":"curated_projection"} for item in self.story_events])
        evidence.extend([
            {
                "evidence_id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "risk_id": item["risk_id"],
                "round": item["round"],
                "provenance": "curated_projection",
            }
            for item in risk_bundle["risk_events"]
        ])
        evidence.extend([
            {
                "evidence_id": item["id"],
                "title": item["policy_name"],
                "summary": item["summary"],
                "policy_id": item["policy_id"],
                "round": item["round"],
                "provenance": "curated_projection",
            }
            for item in policy_events
        ])
        bundle = project_analysis_bundle(
            executive_findings=findings, turning_points=turning, risk_outcomes=risk_outcomes,
            intervention_observations=observations,
            impact_scope={
                "region_count":12, "subject_count":240, "macro_scenario_count":12,
                "spatial_anchor_count":36, "agent_count":240, "core_agent_count":72,
                "round_count":36, "storyline_count":6,
                "dynamic_relation_count": len({item["edge_id"] for item in dynamic_edges}),
                "dynamic_relation_event_count": len(dynamic_edges),
            },
            evidence_index=evidence, uncertainty_boundaries=list(self.analysis_spec["uncertainty_boundaries"]),
            report_artifact_ref={"artifact_name":"full_report","contract_version":"markdown.v1"},
        )
        bundle.update({"generation_mode":"curated_target_state","artifact_mode":"frozen","title":self.analysis_spec["title"],"executive_summary":self.analysis_spec["executive_summary"],"counterfactual_branches":[]})
        return bundle

    def _build_agent_plan(self, profiles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return {
            "contract_version":"agent-plan.v2", "plan_id":"agent-plan::wuhan_covid_v2", "generation_mode":"curated_target_state",
            "artifact_mode":"frozen",
            "target_agent_count":240, "core_agent_count":72, "background_agent_count":168,
            "agent_profiles":[dict(item) for item in profiles], "archetypes":list(self.roster_spec["archetypes"]),
            "system_allocations":list(self.roster_spec["system_allocations"]), "unresolved_demands":[],
            "generation_audit":{
                "role_demand_count":len(self.roster_spec["archetypes"]),
                "covered_role_demand_count":len(self.roster_spec["archetypes"]),
                "unresolved_role_demand_count":0,
                "created_as_region_aggregate_count":sum(1 for item in profiles if item["representation_level"] == "aggregate"),
                "planner_invoked":False,
                "source":"curated_target_state",
            },
        }

    @staticmethod
    def _build_placement_plan(profiles: Sequence[Mapping[str, Any]], anchors: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return {
            "contract_version":"agent-placement-plan.v2", "plan_id":"placement-plan::wuhan_covid_v2",
            "generation_mode":"curated_target_state", "artifact_mode":"frozen",
            "placements":[{"agent_id":item["agent_id"],"agent_uid":item["agent_uid"],"spatial_anchor_id":item["home_subregion_id"],"lat":item["lat"],"lon":item["lon"],"provenance":"curated_projection"} for item in profiles],
            "spatial_anchors":[dict(item) for item in anchors], "unresolved_agent_ids":[],
        }

    @staticmethod
    def _build_resolution_plan(profiles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return {
            "contract_version":"resolution-plan.v2", "plan_id":"resolution-plan::wuhan_covid_v2",
            "generation_mode":"curated_target_state", "artifact_mode":"frozen",
            "resolutions":[{"agent_id":item["agent_id"],"representation_level":item["representation_level"],"detail_mode":"完整生命周期" if item["representation_level"] == "functional" else "聚合背景"} for item in profiles],
            "core_count":72, "aggregate_count":168,
        }

    def _build_policy_execution_plan(self, profiles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        core = [item for item in profiles if item["representation_level"] == "functional"]
        core_by_system = {
            system_id: [item for item in core if item["system_id"] == system_id]
            for system_id in {item["system_id"] for item in core}
        }
        policy_systems = {
            "monitoring_reporting": ("detection", "governance"),
            "testing_tracing": ("detection", "community", "healthcare"),
            "transport_control": ("mobility", "governance"),
            "capacity_expansion": ("healthcare", "supply"),
            "supply_community": ("community", "supply"),
            "phased_recovery": ("mobility", "governance", "detection"),
        }
        bindings = []
        for index, policy in enumerate(self.analysis_spec["policies"]):
            systems = policy_systems[policy["id"]]
            agents = []
            cycle = 0
            while len(agents) < 4:
                system_id = systems[len(agents) % len(systems)]
                pool = core_by_system[system_id]
                candidate = pool[(index + cycle) % len(pool)]
                if candidate not in agents:
                    agents.append(candidate)
                cycle += 1
            bindings.append({
                "policy_id":policy["id"], "policy_name":policy["name"], "binding_status":"bound",
                "executor_agent_ids":[item["agent_id"] for item in agents],
                "executor_system_ids":list(systems),
                "round_start":policy["round_start"], "round_end":policy["round_end"],
            })
        return {
            "contract_version":"policy-execution-plan.v2", "plan_id":"policy-execution-plan::wuhan_covid_v2",
            "generation_mode":"curated_target_state", "artifact_mode":"frozen", "policy_bindings":bindings,
        }

    def _build_relationship_states(self, dynamic_edges: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [{
            "round":item.get("round") or item["created_round"],
            "edge_id":item["edge_id"], "event_id":item.get("event_id"),
            "status":item["status"], "lifecycle_action":item.get("lifecycle_action"),
            "lifecycle_label":item["lifecycle_label"], "strength":item["strength"],
            "provenance":"curated_projection",
        } for item in dynamic_edges]

    def _build_policy_events(self) -> List[Dict[str, Any]]:
        rows = []
        for policy in self.analysis_spec["policies"]:
            for round_num in range(int(policy["round_start"]), int(policy["round_end"]) + 1):
                rows.append({
                    "id":f"policy-event::{policy['id']}::{round_num:02d}", "round":round_num,
                    "policy_id":policy["id"], "policy_name":policy["name"], "execution_status":"执行中" if round_num < policy["round_end"] else "阶段完成",
                    "summary":f"{policy['name']}在第{round_num}轮进入城市系统运行账本。", "provenance":"curated_projection",
                })
        return rows

    @staticmethod
    def _build_state_mutations(round_snapshots: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        previous: Mapping[str, Any] | None = None
        for snapshot in round_snapshots:
            state = snapshot["business_state"]
            for key, value in state.items():
                rows.append({"id":f"state::{snapshot['round']:02d}::{key}","round":snapshot["round"],"dimension_id":key,"value":value,"delta":round(value - float((previous or state).get(key,value)),2),"provenance":"curated_projection"})
            previous = state
        return rows

    @staticmethod
    def _build_agent_emergence(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id":item["agent_id"],"round":item["lifecycle"]["activation_round"],"status":"进入运行网络","representation_level":item["representation_level"]} for item in profiles]

    @staticmethod
    def _build_agent_lineage(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id":item["agent_id"],"agent_uid":item["agent_uid"],"archetype_id":item["archetype_id"],"spatial_anchor_id":item["home_subregion_id"],"source":"curated_target_state"} for item in profiles]

    def _annotate_timeline(self, timeline: Dict[str, Any]) -> None:
        story_by_round = {int(item["round"]):item for item in self.story_events}
        for event in timeline.get("events") or []:
            round_num = int(event.get("round") or event.get("round_number") or 0)
            story = story_by_round.get(round_num)
            if not story:
                continue
            event["chapter_id"] = self._chapter_for_round(round_num)["id"]
            event["chapter_name"] = self._chapter_for_round(round_num)["name"]
            event["storyline_ids"] = list(story["storyline_ids"])
            event["provenance"] = "curated_projection"
            round_sequence = int(event.get("round_sequence") or 0)
            is_primary = round_sequence < 4
            event["display_priority"] = "primary" if is_primary else "background"
            if is_primary:
                action = story["actions"][round_sequence % len(story["actions"])]
                display = dict(event.get("display") or {})
                display["title_zh"] = action
                display["summary_zh"] = f"{story['headline']}：{action}。"
                event["display"] = display

    @staticmethod
    def _retime_animation(animation: Dict[str, Any], target_duration_ms: int) -> None:
        """Scale every canonical V3 clock coordinate to the locked 203s span."""

        timeline = animation.get("timeline") or {}
        clock = timeline.get("clock") or {}
        source_duration = int(clock.get("committed_end_ms") or clock.get("duration_ms") or 0)
        if source_duration <= 0 or target_duration_ms <= 0:
            return

        def scaled(value: Any) -> int:
            return int(round(float(value or 0) * target_duration_ms / source_duration))

        round_windows: Dict[int, tuple[int, int]] = {}
        rounds = list(timeline.get("rounds") or [])
        for index, item in enumerate(rounds):
            start_ms = scaled(item.get("start_ms"))
            end_ms = target_duration_ms if index == len(rounds) - 1 else scaled(item.get("end_ms"))
            item["start_ms"] = start_ms
            item["end_ms"] = end_ms
            item["duration_ms"] = end_ms - start_ms
            round_windows[int(item.get("round") or 0)] = (start_ms, end_ms)

        events = list(timeline.get("events") or [])
        for index, event in enumerate(events):
            timing = event.get("timing") or {}
            global_start_ms = scaled(timing.get("global_start_ms"))
            global_end_ms = (
                target_duration_ms
                if index == len(events) - 1
                else scaled(timing.get("global_end_ms"))
            )
            round_start_ms = round_windows.get(int(event.get("round") or 0), (0, 0))[0]
            local_start_ms = max(0, global_start_ms - round_start_ms)
            timing.update({
                "global_start_ms": global_start_ms,
                "global_end_ms": global_end_ms,
                "local_start_ms": local_start_ms,
                "start_ms": local_start_ms,
                "duration_ms": max(0, global_end_ms - global_start_ms),
            })
            event["timing"] = timing

        clock["duration_ms"] = target_duration_ms
        clock["committed_end_ms"] = target_duration_ms
        clock["default_round_duration_ms"] = scaled(clock.get("default_round_duration_ms"))
        clock["empty_round_duration_ms"] = scaled(clock.get("empty_round_duration_ms"))
        timeline["clock"] = clock
        timeline["playback_duration_ms"] = target_duration_ms
        if isinstance(timeline.get("head"), dict):
            timeline["head"]["global_end_ms"] = target_duration_ms

        duration_by_round = {
            round_num: end_ms - start_ms
            for round_num, (start_ms, end_ms) in round_windows.items()
        }
        for frame in animation.get("frames") or []:
            frame["playback_duration_ms"] = duration_by_round.get(
                int(frame.get("round") or 0), frame.get("playback_duration_ms")
            )

    def _build_scene_seed(self, effort_snapshot: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "scene_id":"foundation::wuhan_covid_v2", "foundation_id":"foundation::wuhan_covid_v2",
            "title":self.case_manifest["title"], "summary":self.case_manifest["summary"],
            "report_markdown":self._build_foundation_markdown(),
            "recommended_simulation_requirement":"复盘武汉疫情期间六个城市系统的协同演化。",
            "location":"武汉市", "time_scope":"2019-12-22 至 2020-04-08", "effort_snapshot":dict(effort_snapshot),
            "generation_mode":"curated_target_state", "artifact_mode":"frozen",
        }

    def _build_foundation_markdown(self) -> str:
        return "\n".join([
            "# 武汉疫情城市系统复盘", "", self.case_manifest["summary"], "",
            "## 研究范围", "", "- 时间：2019-12-22 至 2020-04-08，共108天", "- 空间：武汉市12个宏观城市系统场景与36个差异化锚点", "- 主体：240个职能化或聚合Agent，不对应真实个人", "",
            "## 六个城市系统", "", *[f"- {item['name']}" for item in self.case_manifest["storylines"]], "",
            "## 事实与推演边界", "", self.source_manifest["boundary_note"], "", "## 公开来源", "", *[f"- {item['publisher']}｜{item['title']}：{'；'.join(item['claim_scope'])}" for item in self.source_manifest["sources"]], "",
        ])

    def _build_report_outline(self) -> Dict[str, Any]:
        return {"title":self.analysis_spec["title"],"summary":self.analysis_spec["executive_summary"],"sections":[{"title":title,"content":"详见冻结主线账本与结构化分析数据。"} for title in self.analysis_spec["report_sections"]]}

    def _build_report_markdown(self, analysis_bundle: Mapping[str, Any]) -> str:
        lines = [f"# {self.analysis_spec['title']}","",f"> {self.analysis_spec['executive_summary']}","","---",""]
        lines.extend(["## 案例边界","",self.source_manifest["boundary_note"],""])
        lines.extend(["## 六条故事线",""] + [f"- **{item['name']}**：贯穿36轮并在章节间交叉推进。" for item in self.case_manifest["storylines"]] + [""])
        lines.extend(["## 关键结论",""] + [f"- {item}" for item in self.analysis_spec["conclusions"]] + [""])
        lines.extend(["## 关键转折",""] + [f"- **R{item['round']} · {item['title']}**：{item['summary']}" for item in self.analysis_spec["turning_points"]] + [""])
        lines.extend(["## 五类风险结果",""] + [f"- **{item['title']}**：峰值 {item['peak_score']}，R36 为 {item['ending_score']}；{item['lifecycle']}。" for item in analysis_bundle["risk_outcomes"]] + [""])
        lines.extend(["## 政策观察",""] + [f"- **{item['title']}（R{item['start_round']}–R{item['end_round']}）**：{item['intent']} {item['observation_boundary']}" for item in analysis_bundle["intervention_observations"]] + [""])
        lines.extend(["## 节点探索", "", "报告中的每个轮次、风险、政策、主体和空间锚点均使用与Step 2/3相同的稳定ID，可回到对应章节与运行节点。", ""])
        lines.extend(["## 证据索引",""] + [f"- [{item['title']}]({item['url']})（{item['publisher']}）" for item in self.source_manifest["sources"]] + [""])
        lines.extend(["## 不确定性边界",""] + [f"- {item}" for item in self.analysis_spec["uncertainty_boundaries"]] + [""])
        return "\n".join(lines)

    def _build_state(self, definition: Any, config: Mapping[str, Any], risk_bundle: Mapping[str, Any]) -> Dict[str, Any]:
        planning = config["scenario_planning_input"]
        return {
            "simulation_id":f"golden::{definition.case_id}","project_id":f"golden_project::{definition.case_id}","graph_id":f"golden_graph::{definition.case_id}",
            "engine_mode":"envfish","simulation_architecture":SIMULATION_ARCHITECTURE,"scenario_mode":definition.scenario_mode,
            "diffusion_template":definition.diffusion_template,"hazard_template_id":definition.hazard_template_id,"hazard_template_mode":"curated_projection",
            "search_mode":"ultra","configured_total_rounds":36,"configured_minutes_per_round":4320,"time_plan_mode":"manual","time_plan":config["time_plan"],
            "reference_time":definition.reference_time,"status":"completed","entities_count":288,"profiles_count":240,"region_count":12,"active_variables_count":8,"risk_objects_count":5,
            "entity_types":["Region","Subregion","HumanActor","GovernmentActor","OrganizationActor"],"config_generated":True,"config_reasoning":"由版本化策划源数据确定性编译。",
            "primary_risk_object_id":risk_bundle["risk_objects_summary"]["primary_risk_object_id"],"source_mode":"golden_case","effort_snapshot":config["effort_snapshot"],
            "resolved_foundation_ref":{"foundation_id":"foundation::wuhan_covid_v2","artifact_name":"foundation"},"scenario_input_authority":"curated_target_state",
            "planning_input_id":planning["planning_input_id"],"planning_content_hash":planning["content_hash"],"agent_plan_source":"curated_target_state",
            "artifact_mode":"frozen","golden_case_id":definition.case_id,"golden_case_profile":definition.profile,"artifact_contract_version":WUHAN_V2_ARTIFACT_CONTRACT_VERSION,
            "is_replay_only":True,"current_round":36,"created_at":WUHAN_V2_COMPILED_AT,"updated_at":WUHAN_V2_COMPILED_AT,"error":None,
        }

    @staticmethod
    def _build_run_state(definition: Any, snapshots: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        return {"simulation_id":f"golden::{definition.case_id}","runner_status":"completed","current_round":36,"total_rounds":36,"simulated_hours":2592,"total_simulation_hours":2592,"twitter_running":False,"reddit_running":False,"rounds":[{"round_num":item["round"],"start_time":item["timestamp"],"end_time":item["timestamp"],"simulated_hour":item["round"]*72,"active_agents":[agent["agent_id"] for agent in item["agents"][:24]],"actions":item["visible_highlights"]} for item in snapshots],"started_at":WUHAN_V2_COMPILED_AT,"updated_at":WUHAN_V2_COMPILED_AT,"completed_at":WUHAN_V2_COMPILED_AT,"error":None}

    @staticmethod
    def _build_report_meta(definition: Any, outline: Mapping[str, Any]) -> Dict[str, Any]:
        return {"report_id":f"golden::{definition.case_id}","simulation_id":f"golden::{definition.case_id}","graph_id":f"golden_graph::{definition.case_id}","simulation_requirement":"复盘六个城市系统的协同演化。","status":"completed","outline":dict(outline),"created_at":WUHAN_V2_COMPILED_AT,"completed_at":WUHAN_V2_COMPILED_AT,"artifact_mode":"frozen","golden_case_id":definition.case_id,"is_replay_only":True}

    @staticmethod
    def _compact_profiles(profiles: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id":item["agent_id"],"name":item["name"],"bio":item["bio"]} for item in profiles]

    @staticmethod
    def _agent_catalog_summary(profiles: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        systems: Dict[str, int] = {}
        archetypes = set()
        for item in profiles:
            systems[item["system_name"]] = systems.get(item["system_name"],0) + 1
            archetypes.add(item["archetype_id"])
        return {"total":len(profiles),"core":sum(1 for item in profiles if item["representation_level"] == "functional"),"aggregate":sum(1 for item in profiles if item["representation_level"] == "aggregate"),"archetype_count":len(archetypes),"system_counts":systems}

    def _global_state(self, round_num: int) -> Dict[str, float]:
        # Piecewise curves preserve the historical mainline shape without
        # claiming epidemiological measurement or causal attribution.
        peak = math.exp(-((round_num - 16) / 8.0) ** 2)
        visibility = 22 + 64 / (1 + math.exp(-(round_num - 8) * 0.32))
        testing = 18 + 70 / (1 + math.exp(-(round_num - 11) * 0.28))
        mobility = 84 - 58 / (1 + math.exp(-(round_num - 11) * 1.25)) + 42 / (1 + math.exp(-(round_num - 32) * 0.55))
        supply = 68 - 28 * math.exp(-((round_num - 15) / 5.8) ** 2) + 18 / (1 + math.exp(-(round_num - 22) * 0.3))
        community = 28 + 61 / (1 + math.exp(-(round_num - 18) * 0.3))
        trust = 66 - 23 * math.exp(-((round_num - 10) / 5.5) ** 2) + 17 / (1 + math.exp(-(round_num - 24) * 0.28))
        return {
            "exposure_pressure":self._clamp(22 + 70 * peak), "detection_visibility":self._clamp(visibility),
            "testing_turnaround":self._clamp(testing), "healthcare_load":self._clamp(26 + 69 * math.exp(-((round_num - 17) / 6.8) ** 2)),
            "mobility_intensity":self._clamp(mobility), "supply_sufficiency":self._clamp(supply),
            "community_support":self._clamp(community), "public_trust":self._clamp(trust),
        }

    def _legacy_state_vector(self, index: int, progress: float) -> Dict[str, float]:
        return {"exposure_score":24+index%5,"spread_pressure":22+index%6,"panic_level":18+index%4,"public_trust":68-index%5,"service_capacity":72-index%4,"response_capacity":66+index%6,"economic_stress":20+index%5,"livelihood_stability":70-index%4,"ecosystem_integrity":62,"vulnerability_score":28+index%7}

    def _agent_state_vector(self, system_id: str, agent_id: int) -> Dict[str, float]:
        base = self._global_state(1)
        adjusted = {key:self._clamp(value + self._stable_jitter(f"{system_id}:{agent_id}:{key}",4.0)) for key,value in base.items()}
        return {**self._legacy_from_business_state(adjusted), **adjusted}

    @staticmethod
    def _legacy_from_business_state(state: Mapping[str, float]) -> Dict[str, float]:
        vulnerability = (float(state["exposure_pressure"]) + float(state["healthcare_load"]) + (100-float(state["supply_sufficiency"])) + (100-float(state["community_support"]))) / 4
        return {
            "exposure_score":round(float(state["exposure_pressure"]),2), "spread_pressure":round((float(state["exposure_pressure"])+float(state["mobility_intensity"]))/2,2),
            "panic_level":round(100-float(state["public_trust"]),2), "public_trust":round(float(state["public_trust"]),2),
            "service_capacity":round(100-float(state["healthcare_load"]),2), "response_capacity":round((float(state["detection_visibility"])+float(state["community_support"]))/2,2),
            "economic_stress":round(100-float(state["supply_sufficiency"]),2), "livelihood_stability":round((float(state["supply_sufficiency"])+float(state["community_support"]))/2,2),
            "ecosystem_integrity":round(float(state["community_support"]),2), "vulnerability_score":round(vulnerability,2),
        }

    def _risk_score(self, risk_id: str, round_num: int) -> float:
        offsets = {"hidden_transmission":-3,"healthcare_overload":2,"cross_district_mobility":-1,"supply_continuity":4,"information_trust":-5}
        centers = {"hidden_transmission":11,"healthcare_overload":17,"cross_district_mobility":10,"supply_continuity":16,"information_trust":12}
        widths = {"hidden_transmission":8.0,"healthcare_overload":7.0,"cross_district_mobility":6.0,"supply_continuity":7.0,"information_trust":8.5}
        value = 24 + 68 * math.exp(-((round_num-centers[risk_id])/widths[risk_id])**2) + offsets[risk_id]
        if risk_id == "cross_district_mobility" and round_num >= 30:
            value += (round_num-29)*2.2
        return self._clamp(value)

    def _chapter_for_round(self, round_num: int) -> Mapping[str, Any]:
        return next(item for item in self.case_manifest["chapters"] if int(item["round_start"]) <= round_num <= int(item["round_end"]))

    @staticmethod
    def _resources_for_system(system_id: str) -> List[str]:
        return {
            "detection":["采样能力","检验批次","病例线索"], "healthcare":["分诊位","床位","防护物资"],
            "community":["网格清单","志愿服务","重点人群通道"], "mobility":["客流态势","转运车辆","通行规则"],
            "supply":["库存","配送线路","采购渠道"], "governance":["指挥席位","热线反馈","信息发布渠道"],
        }[system_id]

    @staticmethod
    def _stable_jitter(seed: str, scale: float) -> float:
        raw = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12], 16) / float(0xFFFFFFFFFFFF)
        return (raw - 0.5) * 2 * scale

    @staticmethod
    def _clamp(value: float) -> float:
        return round(max(0.0,min(100.0,float(value))),2)

    def _source_hash(self) -> str:
        digest = hashlib.sha256()
        for name in sorted(("case_manifest.json","source_manifest.json","spatial_anchors.geojson","agent_roster.json","story_events.jsonl","analysis_spec.json")):
            with open(os.path.join(self.source_root,name),"rb") as handle:
                digest.update(name.encode("utf-8")); digest.update(b"\0"); digest.update(handle.read())
        return digest.hexdigest()

    @staticmethod
    def _hash_payload(payload: Any) -> str:
        canonical = json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _file_hash(path: str) -> str:
        with open(path,"rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    def _read_json(self, name: str) -> Any:
        with open(os.path.join(self.source_root,name),"r",encoding="utf-8") as handle:
            return json.load(handle)

    def _read_jsonl(self, name: str) -> List[Dict[str, Any]]:
        with open(os.path.join(self.source_root,name),"r",encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    @staticmethod
    def _write_json(path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"w",encoding="utf-8") as handle:
            json.dump(payload,handle,ensure_ascii=False,indent=2,sort_keys=True)

    @staticmethod
    def _write_text(path: str, payload: str) -> None:
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"w",encoding="utf-8") as handle:
            handle.write(payload)

    @staticmethod
    def _write_jsonl(path: str, rows: Iterable[Mapping[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path),exist_ok=True)
        with open(path,"w",encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(dict(row),ensure_ascii=False,sort_keys=True)+"\n")


__all__ = [
    "WUHAN_V2_ARTIFACT_CONTRACT_VERSION", "WUHAN_V2_CASE_ID", "WUHAN_V2_EFFORT_SNAPSHOT_ID",
    "WUHAN_V2_SPATIAL_FIXTURE_ID", "WUHAN_V2_SPATIAL_GROUNDING", "WuhanShowcaseBuilder",
]
