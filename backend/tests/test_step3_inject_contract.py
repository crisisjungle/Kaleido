"""Runtime intervention contracts at the public Step 3 boundary."""

import json
import os

from app import create_app
from app.api import simulation as simulation_api
from app.config import Config
from app.models.project import ProjectManager
from app.services.semantic_input import SemanticArtifactStore, SemanticInputNormalizer
from app.services.simulation_manager import SimulationManager
from app.services.simulation_ipc import SimulationIPCClient
from scripts.run_envfish_simulation import normalize_runtime_injection_schedule


def test_runtime_schedule_only_defaults_an_omitted_start_round():
    explicit_zero = normalize_runtime_injection_schedule(
        {"start_round": 0},
        current_round=8,
    )
    omitted = normalize_runtime_injection_schedule({}, current_round=8)

    assert explicit_zero["start_round"] == 0
    assert omitted["start_round"] == 9


def test_environment_liveness_uses_status_instead_of_file_presence(tmp_path):
    simulation_dir = tmp_path / "simulation"
    simulation_dir.mkdir()
    status_path = simulation_dir / "env_status.json"
    client = SimulationIPCClient(str(simulation_dir))

    status_path.write_text(json.dumps({"status": "stopped"}), encoding="utf-8")
    assert client.check_env_alive() is False

    status_path.write_text(
        json.dumps({"status": "alive", "process_pid": os.getpid()}),
        encoding="utf-8",
    )
    assert client.check_env_alive() is True


def test_inject_preserves_round_zero_and_replays_one_idempotent_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations"))
    monkeypatch.setattr(SemanticArtifactStore, "ROOT", str(tmp_path / "semantic_inputs"))
    monkeypatch.setattr(Config, "LLM_API_KEY", "")

    project = ProjectManager.create_project(name="香港风暴场景")
    manager = SimulationManager()
    state = manager.create_simulation(project_id=project.project_id, graph_id="graph_hk")
    state.current_round = 8
    manager._save_simulation_state(state)

    monkeypatch.setattr(
        simulation_api,
        "_build_scenario_foundation",
        lambda _project, _state: {
            "location": "香港",
            "region_ids": ["region_wong_tai_sin"],
            "target_catalog": [
                {
                    "id": "region_wong_tai_sin",
                    "name": "黄大仙区",
                    "aliases": ["黄大仙"],
                    "kind": "region",
                }
            ],
        },
    )
    monkeypatch.setattr(
        simulation_api,
        "SemanticInputNormalizer",
        lambda: SemanticInputNormalizer(use_llm=False),
    )
    runner_calls = []

    def inject(cls, simulation_id, variable, timeout=30):
        runner_calls.append((simulation_id, variable, timeout))
        return {
            "success": True,
            "result": {"current_round": 8},
            "timestamp": "2026-07-13T12:00:00",
        }

    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "inject_variable",
        classmethod(inject),
    )

    payload = {
        "simulation_id": state.simulation_id,
        "idempotency_key": "inject_step3_round_zero",
        "type": "policy",
        "name": "加强区域监测",
        "description": "加强黄大仙区监测",
        "target_text": "黄大仙区、黄大仙；不存在的区域",
        "start_round": 0,
        "duration_rounds": 3,
        "intensity": 70,
        "policy_mode": "monitor",
    }
    client = create_app().test_client()
    first = client.post("/api/simulation/inject", json=payload)
    replay = client.post("/api/simulation/inject", json=payload)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert len(runner_calls) == 1
    first_data = first.get_json()["data"]
    replay_data = replay.get_json()["data"]
    assert first_data == replay_data
    assert first_data["normalized_intervention"]["start_round"] == 0
    assert first_data["normalized_intervention"]["target_regions"] == ["region_wong_tai_sin"]
    assert first_data["semantic_revision"] == replay_data["semantic_revision"]

    receipt = simulation_api._read_injection_receipt(
        manager,
        state.simulation_id,
        payload["idempotency_key"],
    )
    assert receipt == first_data
