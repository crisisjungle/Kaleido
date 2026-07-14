import json

from app import create_app
from app.api import simulation as simulation_api
from app.services import simulation_runner as simulation_runner_module
from app.services.simulation_manager import SimulationManager, SimulationStatus
from app.services.simulation_runner import RunnerStatus, SimulationRunState


def test_force_start_cleans_previous_run_when_prepared_state_is_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations"))
    manager = SimulationManager()
    state = manager.create_simulation(project_id="project_force", graph_id="graph_force")
    state.status = SimulationStatus.READY
    manager._save_simulation_state(state)

    calls = {"stop_existing": 0, "cleanup": 0, "start": 0}

    def stop_existing(cls, simulation_id, timeout=5):
        calls["stop_existing"] += 1
        assert simulation_id == state.simulation_id
        return {"stopped": False, "mode": "not_running"}

    def cleanup(cls, simulation_id):
        calls["cleanup"] += 1
        assert simulation_id == state.simulation_id
        return {"success": True, "cleaned_files": ["run_state.json"]}

    def start(cls, simulation_id, **kwargs):
        calls["start"] += 1
        return SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.RUNNING,
            total_rounds=12,
        )

    monkeypatch.setattr(simulation_api.SimulationRunner, "cleanup_simulation_logs", classmethod(cleanup))
    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "stop_existing_environment",
        classmethod(stop_existing),
    )
    monkeypatch.setattr(simulation_api.SimulationRunner, "start_simulation", classmethod(start))

    response = create_app().test_client().post(
        "/api/simulation/start",
        json={"simulation_id": state.simulation_id, "force": True, "max_rounds": 12},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["force_restarted"] is True
    assert calls == {"stop_existing": 1, "cleanup": 1, "start": 1}


def test_force_cleanup_removes_all_runtime_ledgers_but_keeps_prepared_risk_contract(
    monkeypatch,
    tmp_path,
):
    simulation_id = "sim_cleanup"
    sim_dir = tmp_path / simulation_id
    sim_dir.mkdir(parents=True)
    runtime_files = [
        "run_state.json",
        "agent_interaction_ledger.jsonl",
        "dynamic_edge_ledger.jsonl",
        "relationship_event_ledger.jsonl",
        "round_reasoning_ledger.jsonl",
        "agent_emergence_ledger.jsonl",
        "agent_lineage_ledger.jsonl",
        "agent_candidate_ledger.jsonl",
        "agent_action_decision_ledger.jsonl",
        "injection_receipts.json",
    ]
    for filename in runtime_files:
        (sim_dir / filename).write_text("old runtime data\n", encoding="utf-8")
    (sim_dir / "risk_definitions.json").write_text("[]\n", encoding="utf-8")
    (sim_dir / "risk_candidate_ledger.jsonl").write_text("initial contract\n", encoding="utf-8")

    monkeypatch.setattr(simulation_api.SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    result = simulation_api.SimulationRunner.cleanup_simulation_logs(simulation_id)

    assert result["success"] is True
    assert all(not (sim_dir / filename).exists() for filename in runtime_files)
    assert (sim_dir / "risk_definitions.json").exists()
    assert (sim_dir / "risk_candidate_ledger.jsonl").exists()


def test_server_cleanup_preserves_a_completed_run(monkeypatch, tmp_path):
    simulation_id = "sim_completed_cleanup"
    sim_dir = tmp_path / simulation_id
    sim_dir.mkdir(parents=True)
    (sim_dir / "twitter").mkdir()
    (sim_dir / "reddit").mkdir()
    (sim_dir / "twitter" / "actions.jsonl").write_text("", encoding="utf-8")
    (sim_dir / "reddit" / "actions.jsonl").write_text("", encoding="utf-8")
    (sim_dir / "state.json").write_text(
        json.dumps(
            {
                "status": "running",
                "current_round": 0,
                "twitter_status": "running",
                "reddit_status": "running",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    state = SimulationRunState(
        simulation_id=simulation_id,
        runner_status=RunnerStatus.COMPLETED,
        current_round=12,
        total_rounds=12,
        twitter_completed=True,
        reddit_completed=True,
        completed_at="2026-07-13T12:56:35",
    )

    class LingeringProcess:
        pid = 4321

        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(simulation_api.SimulationRunner, "RUN_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(simulation_api.SimulationRunner, "_cleanup_done", False)
    monkeypatch.setattr(simulation_api.SimulationRunner, "_processes", {simulation_id: LingeringProcess()})
    monkeypatch.setattr(simulation_api.SimulationRunner, "_run_states", {simulation_id: state})
    monkeypatch.setattr(simulation_api.SimulationRunner, "_action_queues", {})
    monkeypatch.setattr(simulation_api.SimulationRunner, "_graph_memory_enabled", {})
    monkeypatch.setattr(simulation_api.SimulationRunner, "_stdout_files", {})
    monkeypatch.setattr(simulation_api.SimulationRunner, "_stderr_files", {})
    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "_terminate_process",
        classmethod(lambda cls, process, sim_id, timeout=10: None),
    )
    monkeypatch.setattr(
        simulation_runner_module.ZepGraphMemoryManager,
        "stop_all",
        classmethod(lambda cls: None),
    )

    simulation_api.SimulationRunner.cleanup_all_simulations()

    persisted_run = json.loads((sim_dir / "run_state.json").read_text(encoding="utf-8"))
    persisted_simulation = json.loads((sim_dir / "state.json").read_text(encoding="utf-8"))
    assert persisted_run["runner_status"] == "completed"
    assert persisted_run["completed_at"] == "2026-07-13T12:56:35"
    assert persisted_run["error"] is None
    assert persisted_simulation["status"] == "completed"
    assert persisted_simulation["current_round"] == 12
    assert persisted_simulation["twitter_status"] == "completed"
    assert persisted_simulation["reddit_status"] == "completed"
