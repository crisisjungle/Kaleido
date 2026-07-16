import json
from pathlib import Path

from flask import Flask

from app.api import golden_cases_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.golden_case_service import GoldenCaseService
from app.services.report_agent import ReportManager
from app.services.report_analysis import ReportAnalysisService
from app.services.simulation_manager import SimulationManager
from app.services.wuhan_showcase_builder import (
    WUHAN_V2_ARTIFACT_CONTRACT_VERSION,
    WUHAN_V2_CASE_ID,
    WuhanShowcaseBuilder,
)


def configure_isolated_storage(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(Config, "GOLDEN_RUNS_FOLDER", str(upload_root / "golden_runs"))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations"))
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(upload_root / "reports"))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_wuhan_v2_source_package_has_locked_editorial_scope():
    builder = WuhanShowcaseBuilder()

    assert builder.case_manifest["case_id"] == WUHAN_V2_CASE_ID
    assert builder.case_manifest["total_rounds"] == 36
    assert builder.case_manifest["playback_duration_ms"] == 203000
    assert len(builder.case_manifest["chapters"]) == 6
    assert len(builder.case_manifest["storylines"]) == 6
    assert len(builder.anchor_collection["features"]) == 36
    assert len(builder.story_events) == 36
    assert len(builder.source_manifest["sources"]) == 8
    assert len(builder.roster_spec["archetypes"]) >= 24
    assert len(builder.roster_spec["agents"]) == 240
    assert len({item["anchor_id"] for item in builder.roster_spec["agents"]}) == 36
    assert sum(item["count"] for item in builder.roster_spec["system_allocations"]) == 240
    assert sum(item["core_count"] for item in builder.roster_spec["system_allocations"]) == 72
    assert all(len(item["storyline_ids"]) >= 3 and len(item["actions"]) >= 4 for item in builder.story_events)
    assert "不表达为疫情起源" in builder.source_manifest["boundary_note"]


def test_wuhan_v2_compiler_emits_dense_four_step_contract(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_V2_CASE_ID)
    config = load_json(manifest["simulation"]["config"])
    animation = load_json(manifest["animation"]["file"])
    foundation = load_json(manifest["artifacts"]["foundation"])
    scenario = load_json(manifest["artifacts"]["scenario"])
    runtime = load_json(manifest["artifacts"]["runtime"])
    analysis = load_json(manifest["artifacts"]["analysis"])
    simulation_dir = Path(manifest["simulation"]["dir"])
    agent_plan = load_json(simulation_dir / "agent_plan.json")
    placement_plan = load_json(simulation_dir / "agent_placement_plan.json")
    resolution_plan = load_json(simulation_dir / "resolution_plan.json")
    policy_execution_plan = load_json(simulation_dir / "policy_execution_plan.json")
    facility_query_plan = load_json(manifest["artifacts"]["facility_query_plan"])
    spatial_snapshot = load_json(manifest["artifacts"]["spatial_refinement_snapshot"])
    agent_request = load_json(manifest["simulation"]["agent_planning_request"])

    assert manifest["artifact_contract_version"] == WUHAN_V2_ARTIFACT_CONTRACT_VERSION
    assert manifest["generation_mode"] == "curated_target_state"
    assert manifest["artifact_mode"] == "frozen"
    assert foundation["contract_version"] == "background-foundation.v2"
    assert scenario["contract_version"] == "scenario-definition.v2"
    assert runtime["contract_version"] == "runtime-ledger.v2"
    assert analysis["contract_version"] == "analysis-bundle.v2"
    assert len(config["region_graph"]) == 12
    assert len(config["subregion_graph"]) == 36
    assert len(config["agent_configs"]) == 240
    assert len(config["agent_relationship_graph"]) == 1800
    assert len(config["risk_definitions"]) == 5
    assert len(animation["layout"]["nodes"]) == 288
    assert 2000 <= len(animation["layout"]["edges"]) <= 2400
    assert len({item["id"] for item in animation["layout"]["edges"]}) == len(animation["layout"]["edges"])
    assert [frame["round"] for frame in animation["frames"]] == list(range(37))
    assert animation["frames"][-1]["timestamp"] == "2020-04-08T00:00:00+08:00"
    assert animation["timeline"]["playback_duration_ms"] == 203000
    assert animation["timeline"]["clock"]["duration_ms"] == 203000
    assert animation["timeline"]["clock"]["committed_end_ms"] == 203000
    assert animation["timeline"]["head"]["global_end_ms"] == 203000
    assert animation["timeline"]["rounds"][-1]["end_ms"] == 203000
    assert animation["timeline"]["events"][-1]["timing"]["global_end_ms"] == 203000
    assert sum(frame["playback_duration_ms"] for frame in animation["frames"]) == 203000
    assert len(animation["timeline"]["events"]) >= 696
    for round_num in range(1, 37):
        primary = [
            item for item in animation["timeline"]["events"]
            if item.get("round") == round_num and item.get("display_priority") == "primary"
        ]
        assert 4 <= len(primary) <= 6
        assert all(item.get("display", {}).get("title_zh") for item in primary)
    assert len(analysis["turning_points"]) == 6
    assert len(analysis["risk_outcomes"]) == 5
    assert len(analysis["intervention_observations"]) == 6
    assert analysis["impact_scope"]["dynamic_relation_count"] == 168
    assert analysis["impact_scope"]["dynamic_relation_event_count"] == 216
    assert analysis["impact_scope"]["dynamic_relation_count"] == len({
        item["edge_id"] for item in runtime["relationship_event_ledger"]
    })
    assert analysis["impact_scope"]["dynamic_relation_event_count"] == len(
        runtime["relationship_event_ledger"]
    )
    assert len(analysis["evidence_index"]) == 175
    assert sum(
        item.get("provenance") == "observed/public_source"
        for item in analysis["evidence_index"]
    ) == 8
    assert sum(
        item.get("provenance") == "curated_projection"
        for item in analysis["evidence_index"]
    ) == 167
    assert analysis["counterfactual_branches"] == []
    for artifact in (agent_plan, placement_plan, resolution_plan, policy_execution_plan):
        assert artifact["generation_mode"] == "curated_target_state"
        assert artifact["artifact_mode"] == "frozen"
    assert facility_query_plan["contract_version"] == "facility_query_plan.v1"
    assert spatial_snapshot["contract_version"] == "spatial_refinement_snapshot.v1"
    assert agent_request["facility_query_plan_ref"]["plan_id"] == facility_query_plan["plan_id"]
    assert (
        agent_request["spatial_refinement_snapshot_ref"]["snapshot_id"]
        == spatial_snapshot["snapshot_id"]
    )
    assert agent_request["spatial_evidence_summary"]["required_r3_count"] == 24
    assert agent_request["spatial_evidence_summary"]["covered_r3_count"] == 0
    assert spatial_snapshot["selected_r3_features"] == []
    assert spatial_snapshot["r4_model_units"] == []
    assert {item["evidence_grade"] for item in spatial_snapshot["source_versions"]} == {"D", "S"}
    assert all(
        item.get("status") != "covered"
        for item in spatial_snapshot["request_coverage"]
        if item.get("resolution_level") == "R3"
    )
    assert {item["evidence_grade"] for item in foundation["spatial_anchors"]} == {"D", "S"}
    assert scenario["facility_query_plan_ref"]["plan_id"] == facility_query_plan["plan_id"]
    assert scenario["spatial_evidence_summary"] == agent_request["spatial_evidence_summary"]


def test_wuhan_v2_references_are_resolvable(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_V2_CASE_ID)
    config = load_json(manifest["simulation"]["config"])
    runtime = load_json(manifest["artifacts"]["runtime"])
    analysis = load_json(manifest["artifacts"]["analysis"])
    policy_execution_plan = load_json(Path(manifest["simulation"]["dir"]) / "policy_execution_plan.json")

    agent_ids = {item["agent_id"] for item in config["agent_configs"]}
    anchor_ids = {item["anchor_id"] for item in config["subregion_graph"]}
    relation_ids = {item["edge_id"] for item in config["agent_relationship_graph"]}
    assert len(relation_ids) == len(config["agent_relationship_graph"])
    assert all(item["home_subregion_id"] in anchor_ids for item in config["agent_configs"])
    assert all(item.get("agent_ids") for item in config["subregion_graph"])
    assert all(item["storyline_ids"] for item in config["agent_configs"])
    assert all(
        item["source_agent_id"] in agent_ids and item["target_agent_id"] in agent_ids
        for item in config["agent_relationship_graph"]
    )
    assert all(
        item["source_agent_id"] in agent_ids and item["target_agent_id"] in agent_ids
        for item in runtime["relationship_event_ledger"]
    )
    lifecycle_by_edge = {}
    for item in runtime["relationship_event_ledger"]:
        lifecycle_by_edge.setdefault(item["edge_id"], []).append(item)
    full_lifecycles = [
        items for items in lifecycle_by_edge.values()
        if {item["lifecycle_action"] for item in items}
        == {"created", "activated", "strengthened", "weakened", "resolved"}
    ]
    assert len(runtime["relationship_event_ledger"]) == 216
    assert len(full_lifecycles) == 12
    assert all([item["round"] for item in items] == sorted(item["round"] for item in items) for items in full_lifecycles)
    assert all(len(item.get("visible_highlights") or []) >= 4 for item in runtime["round_snapshots"])

    risk_event_by_id = {item["id"]: item for item in runtime["risk_events"]}
    evidence_ids = {item["evidence_id"] for item in analysis["evidence_index"]}
    for outcome in analysis["risk_outcomes"]:
        assert outcome["evidence_refs"]
        assert all(ref in evidence_ids for ref in outcome["evidence_refs"])
        assert all(risk_event_by_id[ref]["risk_id"] == outcome["risk_id"] for ref in outcome["evidence_refs"])

    agent_by_id = {item["agent_id"]: item for item in config["agent_configs"]}
    expected_policy_systems = {
        "monitoring_reporting": {"detection", "governance"},
        "testing_tracing": {"detection", "community", "healthcare"},
        "transport_control": {"mobility", "governance"},
        "capacity_expansion": {"healthcare", "supply"},
        "supply_community": {"community", "supply"},
        "phased_recovery": {"mobility", "governance", "detection"},
    }
    for binding in policy_execution_plan["policy_bindings"]:
        executor_systems = {
            agent_by_id[agent_id]["system_id"] for agent_id in binding["executor_agent_ids"]
        }
        assert executor_systems == expected_policy_systems[binding["policy_id"]]


def test_wuhan_v2_build_is_deterministic_three_times(tmp_path):
    definition = GoldenCaseService.get_case(WUHAN_V2_CASE_ID)
    signatures = []
    for index in range(3):
        manifest = WuhanShowcaseBuilder().compile(definition, str(tmp_path / f"build-{index}"))
        animation = load_json(manifest["animation"]["file"])
        signatures.append({
            "hashes": manifest["artifact_hashes"],
            "nodes": [(item["id"], item["lat"], item["lon"]) for item in animation["layout"]["nodes"]],
            "frames": [item["round"] for item in animation["frames"]],
            "timeline": [item["id"] for item in animation["timeline"]["events"]],
        })
    assert signatures[0] == signatures[1] == signatures[2]


def test_wuhan_v2_restore_starts_at_step1_and_preserves_legacy_routes(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)
    restored = GoldenCaseService.restore_case(WUHAN_V2_CASE_ID, reuse=False)

    assert restored["demo_mode"] == "curated_showcase"
    assert restored["default_step"] == 1
    assert restored["step_routes"]["foundation"]["name"] == "SceneComposer"
    assert restored["step_routes"]["scenario"]["name"] == "Simulation"
    assert restored["step_routes"]["runtime"]["name"] == "SimulationRun"
    assert restored["step_routes"]["analysis"]["name"] == "Analysis"
    assert restored["step_routes"]["foundation"]["query"]["search_mode"] == "ultra"
    assert restored["step_routes"]["foundation"]["query"]["simulation_id"] == restored["simulation_id"]
    assert restored["step_routes"]["foundation"]["query"]["step"] == "1"
    assert restored["step_routes"]["foundation"]["query"]["golden_case_id"] == WUHAN_V2_CASE_ID
    assert restored["step_routes"]["foundation"]["query"]["demo_mode"] == "curated_showcase"
    assert restored["route"] == restored["step_routes"]["scenario"]
    assert restored["playback_route"] == restored["step_routes"]["runtime"]
    assert restored["capabilities"] == {
        "editable": False,
        "live_intervention": False,
        "chapter_navigation": True,
        "copy_as_new": True,
    }
    project = ProjectManager.get_project(restored["project_id"])
    simulation = SimulationManager().get_simulation(restored["simulation_id"])
    assert project.scene_id == f"foundation::{WUHAN_V2_CASE_ID}"
    assert project.semantic_artifact_ref["artifact_name"] == "foundation"
    assert simulation.resolved_foundation_ref["artifact_name"] == "foundation"
    assert simulation.agent_plan_source == "curated_target_state"
    assert simulation.risk_objects_count == 5


def test_wuhan_v2_artifact_api_and_report_analysis_use_frozen_bundle(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)
    restored = GoldenCaseService.restore_case(WUHAN_V2_CASE_ID, reuse=False)
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.register_blueprint(golden_cases_bp, url_prefix="/api/golden-cases")

    response = app.test_client().get(f"/api/golden-cases/{WUHAN_V2_CASE_ID}/artifacts/foundation")
    assert response.status_code == 200
    public_foundation = response.get_json()["data"]
    assert public_foundation["contract_version"] == "background-foundation.v2"
    assert public_foundation["area_of_interest"]["location"] == "武汉市"
    assert len(public_foundation["area_of_interest"]["regions"]) == 12
    assert len(public_foundation["spatial_anchors"]) == 36
    assert len(public_foundation["city_systems"]) == 6
    assert len(public_foundation["source_refs"]) == 8
    assert len(public_foundation["research_questions"]) == 3
    assert len(public_foundation["analysis_boundaries"]) == 4
    assert len(public_foundation["open_data_gaps"]) == 2
    assert "武汉疫情城市系统复盘" in public_foundation["report_markdown"]
    assert "108天" in public_foundation["report_markdown"]
    assert "事实与推演边界" in public_foundation["report_markdown"]

    restore_response = app.test_client().post(
        f"/api/golden-cases/{WUHAN_V2_CASE_ID}/restore?fresh=1",
        json={"reuse": False},
    )
    assert restore_response.status_code == 200
    public_restore = restore_response.get_json()["data"]
    assert {
        key: value["name"] for key, value in public_restore["step_routes"].items()
    } == {
        "foundation": "SceneComposer",
        "scenario": "Simulation",
        "runtime": "SimulationRun",
        "analysis": "Analysis",
    }
    assert all(
        value["artifact_name"] == key
        for key, value in public_restore["artifact_refs"].items()
    )

    scenario_response = app.test_client().get(
        f"/api/golden-cases/{WUHAN_V2_CASE_ID}/artifacts/scenario"
    )
    analysis_response = app.test_client().get(
        f"/api/golden-cases/{WUHAN_V2_CASE_ID}/artifacts/analysis"
    )
    public_scenario = scenario_response.get_json()["data"]
    public_analysis = analysis_response.get_json()["data"]
    assert public_scenario["agent_plan_ref"]["artifact_name"] == "agent_plan"
    assert public_analysis["report_artifact_ref"]["artifact_name"] == "full_report"
    assert public_analysis["turning_points"][0]["evidence_ref"] == "round::3"
    assert public_analysis["turning_points"][0]["provenance"] == "curated_projection"

    service = ReportAnalysisService(restored["report_id"])
    bundle_tab = service.get_tab_data("analysis-bundle")
    intervention_tab = service.get_tab_data("intervention")
    risk_tab = service.get_tab_data("risk-outcomes")
    assert bundle_tab["analysis_bundle"]["generation_mode"] == "curated_target_state"
    assert len(bundle_tab["analysis_bundle"]["evidence_index"]) == 175
    assert intervention_tab["summary"]["policy_event_count"] == 6
    assert intervention_tab["summary"]["intervention_count"] == 0
    assert "不宣称" in intervention_tab["causality_boundary"]
    assert len(risk_tab["risk_outcomes"]) == 5
