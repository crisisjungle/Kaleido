import json

from app import create_app
from app.services.risk_artifact_store import load_risk_artifacts, write_risk_artifacts
from app.services.simulation_manager import SimulationManager


def _definition():
    return {
        "risk_contract_version": 2,
        "risk_id": "risk_v2_test",
        "title": "滨海区居民暴露风险",
        "summary": "风暴潮通过海水倒灌影响滨海区居民。",
        "primary_family": "health_safety",
        "evidence_strength_score": 82,
        "confidence_score": 0.82,
        "severity_score": 75,
        "impact_score": 75,
        "risk_statement": {
            "trigger_name": "风暴潮",
            "receptor_name": "滨海区居民",
            "source_node_ids": ["source"],
            "receptor_node_ids": ["resident"],
            "consequence": "居民安全暴露上升。",
        },
        "mechanism_node_ids": ["source", "process", "resident"],
        "mechanism_edge_ids": ["edge_1", "edge_2"],
        "monitoring_metrics": [
            {"key": "exposure_score", "label": "人群暴露", "polarity": "higher_is_worse", "weight": 1.0}
        ],
    }


def test_missing_contract_version_reads_as_v1(tmp_path):
    (tmp_path / "risk_definitions.json").write_text(
        json.dumps([{"risk_id": "legacy", "title": "历史风险"}], ensure_ascii=False),
        encoding="utf-8",
    )
    bundle = load_risk_artifacts(str(tmp_path))
    assert bundle["risk_contract_version"] == 1
    assert bundle["risk_definitions"][0]["risk_id"] == "legacy"


def test_v2_manifest_candidate_ledger_and_zero_objects_are_persisted(tmp_path):
    initial_runtime = {
        "round": 0,
        "primary_active_risk_id": "risk_v2_test",
        "risk_states": [{"risk_id": "risk_v2_test", "status": "watch"}],
    }
    bundle = write_risk_artifacts(
        sim_dir=str(tmp_path),
        risk_definitions=[_definition()],
        latest_runtime_bundle=initial_runtime,
        primary_risk_id="risk_v2_test",
        risk_contract_version=2,
        generation_audit={"candidate_count": 3, "rejected_count": 2, "generation_mode": "mechanism_graph_deterministic"},
        candidate_ledger=[{"status": "accepted", "risk_id": "risk_v2_test"}],
        rewrite_runtime_history=[initial_runtime],
    )
    assert bundle["risk_contract_version"] == 2
    assert bundle["risk_candidate_ledger"][0]["risk_id"] == "risk_v2_test"
    assert bundle["risk_objects"][0]["evidence_strength_score"] == 82
    assert bundle["risk_objects_summary"]["active_count"] == 1

    zero_dir = tmp_path / "zero"
    zero = write_risk_artifacts(
        sim_dir=str(zero_dir),
        risk_definitions=[],
        latest_runtime_bundle={"round": 0, "primary_active_risk_id": "", "risk_states": []},
        primary_risk_id="",
        risk_contract_version=2,
        generation_audit={"candidate_count": 0, "active_count": 0, "zero_reason": "证据不足"},
        rewrite_runtime_history=[{"round": 0, "primary_active_risk_id": "", "risk_states": []}],
    )
    assert zero["risk_contract_version"] == 2
    assert zero["risk_definitions"] == []
    assert zero["risk_objects"] == []
    assert zero["risk_objects_summary"]["active_count"] == 0
    assert zero["risk_objects_summary"]["zero_reason"] == "证据不足"


def test_v2_pin_and_reframe_endpoints_are_read_only(monkeypatch, tmp_path):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations"))
    manager = SimulationManager()
    state = manager.create_simulation(project_id="project_v2", graph_id="graph_v2")
    sim_dir = manager._get_simulation_dir(state.simulation_id)
    runtime = {
        "round": 0,
        "primary_active_risk_id": "risk_v2_test",
        "pinned_risk_ids": [],
        "risk_states": [{"risk_id": "risk_v2_test", "status": "watch"}],
    }
    write_risk_artifacts(
        sim_dir=sim_dir,
        risk_definitions=[_definition()],
        latest_runtime_bundle=runtime,
        primary_risk_id="risk_v2_test",
        risk_contract_version=2,
        generation_audit={"generation_mode": "mechanism_graph_deterministic"},
        rewrite_runtime_history=[runtime],
    )

    client = create_app().test_client()
    pin = client.post(f"/api/simulation/{state.simulation_id}/risk/pin", json={"pinned_risk_ids": ["risk_v2_test"]})
    reframe = client.post(f"/api/simulation/{state.simulation_id}/risk/reframe", json={})

    assert pin.status_code == 409
    assert pin.get_json()["code"] == "risk_definitions_read_only"
    assert reframe.status_code == 409
    assert reframe.get_json()["code"] == "risk_definitions_read_only"
