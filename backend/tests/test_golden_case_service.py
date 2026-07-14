import hashlib
import json
from pathlib import Path

import pytest
from flask import Flask

from app.api import golden_cases_bp
from app.config import Config
from app.models.project import ProjectManager
from app.services.display_localization import find_public_display_leaks, sanitize_public_dto
from app.services.golden_case_service import (
    GoldenCaseService,
    WUHAN_ARTIFACT_CONTRACT_VERSION,
    WUHAN_CASE_ID,
    WUHAN_EFFORT_SNAPSHOT_ID,
    WUHAN_REFERENCE_TIME,
    WUHAN_SPATIAL_FIXTURE_ID,
    WUHAN_SPATIAL_GROUNDING,
)
from app.services.report_agent import ReportManager
from app.services.simulation_manager import SimulationManager
from app.services.simulation_animation_service import (
    ANIMATION_CONTRACT_VERSION,
    TIMELINE_CONTRACT_VERSION,
)
from scripts.build_wuhan_golden_run import validate as validate_wuhan_fixture


def configure_isolated_storage(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(Config, "GOLDEN_RUNS_FOLDER", str(upload_root / "golden_runs"))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations"))
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(upload_root / "reports"))


def test_wuhan_restore_api_preserves_router_machine_names(monkeypatch):
    monkeypatch.setattr(
        GoldenCaseService,
        "restore_case",
        classmethod(lambda cls, case_id, reuse=True: {
            "case_id": case_id,
            "route": {
                "name": "Simulation",
                "params": {"simulationId": "sim_demo_01"},
                "query": {"replay": "1"},
            },
            "playback_route": {
                "name": "SimulationRun",
                "params": {"simulationId": "sim_demo_01"},
                "query": {"replay": "1"},
            },
        }),
    )
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.register_blueprint(golden_cases_bp, url_prefix="/api/golden-cases")

    response = app.test_client().post(
        f"/api/golden-cases/{WUHAN_CASE_ID}/restore",
        json={"reuse": True},
    )
    payload = response.get_json()["data"]

    assert response.status_code == 200
    assert payload["route"]["name"] == "Simulation"
    assert payload["playback_route"]["name"] == "SimulationRun"


def test_wuhan_restore_reuses_frozen_handles_by_default(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    first = GoldenCaseService.restore_case(WUHAN_CASE_ID)
    second = GoldenCaseService.restore_case(WUHAN_CASE_ID)

    assert first["demo_mode"] == "frozen_replay"
    assert first["reused"] is False
    assert second["reused"] is True
    assert second["project_id"] == first["project_id"]
    assert second["simulation_id"] == first["simulation_id"]
    assert second["report_id"] == first["report_id"]
    assert second["route"]["name"] == "Simulation"
    assert second["playback_route"]["name"] == "SimulationRun"
    assert second["route"]["query"]["replay"] == "1"


def test_wuhan_restore_can_create_fresh_handle(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    first = GoldenCaseService.restore_case(WUHAN_CASE_ID)
    fresh = GoldenCaseService.restore_case(WUHAN_CASE_ID, reuse=False)

    assert fresh["reused"] is False
    assert fresh["project_id"] != first["project_id"]
    assert fresh["simulation_id"] != first["simulation_id"]
    assert fresh["report_id"] != first["report_id"]


def test_wuhan_scaffold_refreshes_stale_artifact_contract(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    manifest_path = Path(GoldenCaseService.case_root(WUHAN_CASE_ID)) / "manifest.json"
    assert manifest["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION

    stale = dict(manifest)
    stale["artifact_contract_version"] = "old-contract"
    manifest_path.write_text(json.dumps(stale, ensure_ascii=False, indent=2), encoding="utf-8")

    refreshed = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)

    assert refreshed["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION


def test_wuhan_fixture_uses_non_template_map_layout(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    root = Path(GoldenCaseService.case_root(WUHAN_CASE_ID))
    regions = json.loads((root / "simulation" / "region_graph_snapshot.json").read_text(encoding="utf-8"))
    subregions = json.loads((root / "simulation" / "subregion_graph_snapshot.json").read_text(encoding="utf-8"))
    profiles = json.loads((root / "simulation" / "profiles_full.json").read_text(encoding="utf-8"))

    regions_by_id = {item["region_id"]: item for item in regions}
    offset_signatures = []
    for item in subregions[:12]:
        parent = regions_by_id[item["parent_region_id"]]
        offset_signatures.append(
            (
                round(item["lat"] - parent["lat"], 4),
                round(item["lon"] - parent["lon"], 4),
            )
        )

    assert len(set(offset_signatures)) > 8
    assert all(profile.get("lat") and profile.get("lon") for profile in profiles[:30])


def test_wuhan_fixture_builds_complete_deterministic_step2_contract(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    root = Path(GoldenCaseService.case_root(WUHAN_CASE_ID))
    simulation_root = root / "simulation"
    config = json.loads((simulation_root / "simulation_config.json").read_text(encoding="utf-8"))
    state = json.loads((simulation_root / "state.json").read_text(encoding="utf-8"))
    scene_seed = json.loads((root / "scene" / "scene_seed.json").read_text(encoding="utf-8"))
    planning = json.loads((simulation_root / "scenario_planning_input.json").read_text(encoding="utf-8"))
    mechanism_graph = json.loads((simulation_root / "mechanism_graph.json").read_text(encoding="utf-8"))
    temporal_plan = json.loads((simulation_root / "temporal_plan.json").read_text(encoding="utf-8"))
    policy_plan = json.loads((simulation_root / "policy_plan.json").read_text(encoding="utf-8"))
    role_demands = json.loads((simulation_root / "role_demands.json").read_text(encoding="utf-8"))
    agent_request = json.loads((simulation_root / "agent_planning_request.json").read_text(encoding="utf-8"))

    assert manifest["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION
    assert config["simulation_architecture"] == "llm_mechanism_v1"
    assert planning["contract_version"] == "scenario_planning.v2"
    assert planning["simulation_architecture"] == "llm_mechanism_v1"
    assert len(planning["normalized_user_events"]) == 3
    assert len(planning["normalized_user_policies"]) == 3
    assert len(mechanism_graph["nodes"]) >= 6
    assert len(mechanism_graph["edges"]) >= 5
    assert len(policy_plan) == 3
    assert len(role_demands) >= 5
    assert temporal_plan["step_unit"] == "day"
    assert temporal_plan["step_value"] == 3
    assert temporal_plan["total_rounds"] == 36

    effort_snapshot = config["effort_snapshot"]
    assert effort_snapshot["effort_snapshot_id"] == WUHAN_EFFORT_SNAPSHOT_ID
    assert effort_snapshot["effort_level"] == "high"
    assert effort_snapshot["locked"] is True
    assert effort_snapshot["locked_at"] == WUHAN_REFERENCE_TIME
    assert scene_seed["effort_snapshot"] == effort_snapshot
    assert planning["effort_snapshot_ref"]["effort_snapshot_id"] == effort_snapshot["effort_snapshot_id"]
    assert planning["effort_snapshot_ref"]["effort_level"] == effort_snapshot["effort_level"]
    assert planning["effort_snapshot_ref"]["profile_version"] == effort_snapshot["profile_version"]
    assert planning["effort_snapshot_ref"]["content_hash"] == effort_snapshot["content_hash"]

    assert config["scenario_planning_input"] == planning
    assert config["event_mechanism_graph"] == mechanism_graph
    assert config["mechanism_graph"] == mechanism_graph
    assert config["temporal_plan"] == temporal_plan
    assert config["policy_plan"] == policy_plan
    assert config["role_demands"] == role_demands
    assert config["assumptions"] == planning["assumptions"]
    assert config["agent_plan_source"] == "legacy_adapter"
    assert agent_request["agent_plan_source"] == "legacy_adapter"
    assert agent_request["scenario_planning_ref"]["content_hash"] == planning["content_hash"]
    assert state["planning_input_id"] == planning["planning_input_id"]
    assert state["planning_content_hash"] == planning["content_hash"]
    assert state["effort_snapshot"] == effort_snapshot
    assert state["agent_plan_source"] == "legacy_adapter"
    assert state["event_mechanism_graph"] == mechanism_graph

    assert all(
        any("\u4e00" <= char <= "\u9fff" for char in item["label_zh"])
        for item in mechanism_graph["nodes"]
    )
    assert all(
        any("\u4e00" <= char <= "\u9fff" for char in item["label_zh"])
        for item in policy_plan
    )
    assert all("agent_id" not in demand and "target_agent_count" not in demand for demand in role_demands)

    first_identity = {
        "planning_input_id": planning["planning_input_id"],
        "content_hash": planning["content_hash"],
        "effort_snapshot": effort_snapshot,
    }
    GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID, force=True)
    rebuilt = json.loads((simulation_root / "scenario_planning_input.json").read_text(encoding="utf-8"))
    rebuilt_config = json.loads((simulation_root / "simulation_config.json").read_text(encoding="utf-8"))
    assert {
        "planning_input_id": rebuilt["planning_input_id"],
        "content_hash": rebuilt["content_hash"],
        "effort_snapshot": rebuilt_config["effort_snapshot"],
    } == first_identity


def test_wuhan_animation_fixture_embeds_deterministic_timeline_v2(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    animation_path = Path(manifest["animation"]["file"])
    simulation_animation_path = Path(manifest["simulation"]["dir"]) / "animation.json"
    animation = json.loads(animation_path.read_text(encoding="utf-8"))
    timeline = animation["timeline"]
    events = timeline["events"]
    frames = animation["frames"]
    layout = animation["layout"]

    assert animation == json.loads(simulation_animation_path.read_text(encoding="utf-8"))
    assert animation["meta"]["animation_contract_version"] == ANIMATION_CONTRACT_VERSION
    assert animation["meta"]["timeline_contract_version"] == TIMELINE_CONTRACT_VERSION
    assert animation["meta"]["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION
    assert timeline["contract_version"] == TIMELINE_CONTRACT_VERSION
    assert timeline["edge_reference_contract"] == "split-path-related.v1"
    assert timeline["source_mode"] == "curated_fixture_ledgers"
    assert timeline["observed_event_count"] == 0
    assert timeline["curated_event_count"] == len(events)
    assert timeline["grounding"]["mode"] == "curated_deterministic_fixture"
    assert timeline["grounding"]["projection"] == "golden_fixture_projection"
    assert timeline["grounding"]["observed"] is False
    assert all(event["grounding"]["observed"] is False for event in events)
    assert timeline["fallback_event_count"] == 0
    assert timeline["cursor"] == len(events) >= 600
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert len({event["id"] for event in events}) == len(events)
    assert all(isinstance(frame.get("timeline_event_ids"), list) for frame in frames)
    assert layout["geographic_grounding"] == WUHAN_SPATIAL_GROUNDING
    assert layout["map_seed_id"] is None
    assert layout["data_quality"] == {
        "status": "curated_fixture",
        "formal_ready": False,
        "fixture_ready": True,
        "observed": False,
        "spatial_fixture_id": WUHAN_SPATIAL_FIXTURE_ID,
    }
    assert layout["meta"]["geographic_node_count"] == len(layout["nodes"])
    assert layout["meta"]["synthetic_node_count"] == 0
    for node in layout["nodes"]:
        attrs = node["attributes"]
        assert node["is_geographic"] is True
        assert attrs["is_geographic"] is True
        assert attrs["placement"] == "curated_fixture"
        assert attrs["coordinate_grounding"] == WUHAN_SPATIAL_GROUNDING
        assert attrs["coordinates_observed"] is False
        assert attrs["spatial_fixture_id"] == WUHAN_SPATIAL_FIXTURE_ID
    transport_layout_edges = [
        edge for edge in layout["edges"] if edge["fact_type"] == "transport_edge"
    ]
    assert len(transport_layout_edges) == layout["meta"]["fixture_route_edge_count"]
    assert transport_layout_edges
    for edge in transport_layout_edges:
        attrs = edge["attributes"]
        assert attrs["is_route_edge"] is True
        assert attrs["route_grounding"] == WUHAN_SPATIAL_GROUNDING
        assert attrs["route_observed"] is False
        assert attrs["spatial_fixture_id"] == WUHAN_SPATIAL_FIXTURE_ID

    edge_ids = {edge["id"] for edge in animation["layout"]["edges"]}
    assert {
        edge_id
        for event in events
        for edge_id in event.get("edge_ids") or []
    }.issubset(edge_ids)
    for event in events:
        assert event["edge_reference_contract"] == "split-path-related.v1"
        assert set(event["path_edge_ids"]).isdisjoint(event["related_edge_ids"])
        assert event["edge_ids"] == [
            *event["path_edge_ids"],
            *event["related_edge_ids"],
        ]
    event_ids = {event["id"] for event in events}
    assert {
        parent_id
        for event in events
        for parent_id in event.get("parent_event_ids") or []
    }.issubset(event_ids)
    assert {
        event["root_event_id"]
        for event in events
        if event.get("root_event_id")
    }.issubset(event_ids)
    diffusion_events = [event for event in events if event["phase"] == "environment_diffusion"]
    diffusion_by_id = {event["id"]: event for event in diffusion_events}
    assert diffusion_events
    assert max(event["hop"] for event in diffusion_events) >= 3
    for event in diffusion_events:
        assert event["grounding"]["mode"] == "curated_deterministic_fixture"
        assert event["grounding"]["projection"] == "golden_fixture_projection"
        assert event["grounding"]["observed"] is False
        assert event["cause"]["type"] == "golden_fixture_projection"
        assert event["root_event_id"] in diffusion_by_id
        if event["hop"] == 0:
            assert event["root_event_id"] == event["id"]
            assert event["parent_event_ids"] == []
            assert event["edge_ids"] == []
            assert event["path_edge_ids"] == []
            assert event["related_edge_ids"] == []
        else:
            assert len(event["parent_event_ids"]) == 1
            parent = diffusion_by_id[event["parent_event_ids"][0]]
            assert event["hop"] == parent["hop"] + 1
            assert event["root_event_id"] == parent["root_event_id"]
            assert event["round"] >= parent["round"]
            assert len(event["path_edge_ids"]) == 1
            assert event["related_edge_ids"] == []
    assert find_public_display_leaks(sanitize_public_dto(animation)) == []

    # Every prepared Agent exists from round zero.  The frozen frame contract no
    # longer fabricates reveal order from numeric Agent IDs.
    for frame in frames:
        agent_states = [
            state
            for state in frame.get("node_states") or []
            if str(state.get("id") or "").startswith("agent::")
        ]
        assert all(state.get("first_seen_round") == 0 for state in agent_states)

    first_digest = hashlib.sha256(animation_path.read_bytes()).hexdigest()
    first_copy_digest = hashlib.sha256(simulation_animation_path.read_bytes()).hexdigest()
    spread_path = Path(manifest["simulation"]["spread_event_ledger"])
    first_spread_digest = hashlib.sha256(spread_path.read_bytes()).hexdigest()
    assert first_digest == first_copy_digest
    GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID, force=True)
    assert hashlib.sha256(animation_path.read_bytes()).hexdigest() == first_digest
    assert hashlib.sha256(simulation_animation_path.read_bytes()).hexdigest() == first_copy_digest
    assert hashlib.sha256(spread_path.read_bytes()).hexdigest() == first_spread_digest


def test_wuhan_spread_ledger_is_a_directed_curated_multi_hop_projection(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    simulation_root = Path(manifest["simulation"]["dir"])
    spread_events = [
        json.loads(line)
        for line in Path(manifest["simulation"]["spread_event_ledger"])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    regions = json.loads((simulation_root / "region_graph_snapshot.json").read_text(encoding="utf-8"))
    transport_edges = json.loads((simulation_root / "transport_edges.json").read_text(encoding="utf-8"))
    injected_variables = json.loads((simulation_root / "injected_variables.json").read_text(encoding="utf-8"))

    region_ids = {item["region_id"] for item in regions}
    transport_by_id = {item["edge_id"]: item for item in transport_edges}
    variables_by_id = {item["variable_id"]: item for item in injected_variables}
    spread_by_id = {item["event_id"]: item for item in spread_events}
    roots = [item for item in spread_events if item["hop"] == 0]

    assert len(spread_events) == len(region_ids)
    assert len(spread_by_id) == len(spread_events)
    assert len(roots) == 1
    root = roots[0]
    assert root["source_region"] == root["target_region"] == "jianghan_market_corridor"
    assert root["root_event_id"] == root["event_id"]
    assert root["parent_event_ids"] == []
    assert root["transport_edge_id"] is None
    assert root["path_edge_ids"] == []
    assert root["related_edge_ids"] == []
    assert root["source_variable_id"] in variables_by_id
    assert "jianghan_market_corridor" in variables_by_id[root["source_variable_id"]]["target_regions"]
    assert max(item["hop"] for item in spread_events) >= 3

    for event in spread_events:
        assert event["source_region"] in region_ids
        assert event["target_region"] in region_ids
        assert event["source_variable_id"] in variables_by_id
        assert event["causal_source_type"] == "golden_fixture_projection"
        assert event["grounding_mode"] == "curated_deterministic_fixture"
        assert event["projection_rule"] == "directed_transport_first_arrival_tree"
        assert event["observed"] is False
        assert event["path_edge_ids"] == (
            [event["transport_edge_id"]] if event["transport_edge_id"] else []
        )
        assert event["related_edge_ids"] == []
        assert 0 <= event["round"] <= 36
        if event["hop"] == 0:
            continue
        assert len(event["parent_event_ids"]) == 1
        parent = spread_by_id[event["parent_event_ids"][0]]
        edge = transport_by_id[event["transport_edge_id"]]
        assert event["hop"] == parent["hop"] + 1
        assert event["root_event_id"] == parent["root_event_id"]
        assert event["source_region"] == parent["target_region"]
        assert edge["directionality"] == "directed"
        assert edge["source_region_id"] == event["source_region"]
        assert edge["target_region_id"] == event["target_region"]
        assert event["edge_id"] == edge["edge_id"]
        assert event["delay_rounds"] == edge["travel_time_rounds"]
        assert event["round"] == parent["round"] + edge["travel_time_rounds"]


def test_wuhan_validator_rejects_an_invented_spread_parent(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    spread_path = Path(manifest["simulation"]["spread_event_ledger"])
    rows = [json.loads(line) for line in spread_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    child = next(item for item in rows if item["hop"] > 0)
    child["parent_event_ids"] = ["invented_same_round_parent"]
    spread_path.write_text(
        "".join(f"{json.dumps(item, ensure_ascii=False)}\n" for item in rows),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        validate_wuhan_fixture()


def test_wuhan_restore_carries_locked_effort_and_planning_references(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    restored = GoldenCaseService.restore_case(WUHAN_CASE_ID)
    project = ProjectManager.get_project(restored["project_id"])
    simulation = SimulationManager().get_simulation(restored["simulation_id"])

    assert project is not None
    assert simulation is not None
    assert project.effort_snapshot["effort_snapshot_id"] == WUHAN_EFFORT_SNAPSHOT_ID
    assert simulation.effort_snapshot == project.effort_snapshot
    assert simulation.simulation_architecture == "llm_mechanism_v1"
    assert simulation.planning_input_id.startswith("scenario_plan_")
    assert len(simulation.planning_content_hash) == 64
    assert simulation.agent_plan_source == "legacy_adapter"
    assert simulation.is_replay_only is True


def test_wuhan_restore_does_not_reuse_a_pre_step2_handle(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    first = GoldenCaseService.restore_case(WUHAN_CASE_ID)
    manager = SimulationManager()
    stale = manager.get_simulation(first["simulation_id"])
    assert stale is not None
    stale.planning_input_id = ""
    stale.planning_content_hash = ""
    stale.agent_plan_source = ""
    manager._save_simulation_state(stale)

    refreshed = GoldenCaseService.restore_case(WUHAN_CASE_ID)

    assert refreshed["reused"] is False
    assert refreshed["simulation_id"] != first["simulation_id"]
