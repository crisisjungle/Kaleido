import os
import shutil
import tempfile
from copy import deepcopy
from unittest.mock import patch

import pytest

from app import create_app
from app.api import simulation as simulation_api
from app.config import Config
from app.models.project import ProjectManager
from app.models.task import TaskManager, TaskStatus
from app.services.effort_contract import build_effort_snapshot
from app.services.simulation_manager import SimulationManager
from app.services.semantic_input import SemanticArtifactStore
from app.services.task_executor import TaskExecutor
from app.services.zep_entity_reader import ZepEntityReader


@pytest.fixture()
def step2_contract_workspace():
    root = tempfile.mkdtemp(prefix="kaleido_step2_contract_")
    originals = (
        ProjectManager.PROJECTS_DIR,
        SimulationManager.SIMULATION_DATA_DIR,
        TaskManager.TASKS_DIR,
        SemanticArtifactStore.ROOT,
        Config.LLM_API_KEY,
    )
    ProjectManager.PROJECTS_DIR = os.path.join(root, "projects")
    SimulationManager.SIMULATION_DATA_DIR = os.path.join(root, "simulations")
    TaskManager.TASKS_DIR = os.path.join(root, "tasks")
    SemanticArtifactStore.ROOT = os.path.join(root, "semantic_inputs")
    Config.LLM_API_KEY = ""

    snapshot = build_effort_snapshot("high", effort_snapshot_id="effort_step2contract")
    project = ProjectManager.create_project(name="沿海复合灾害", effort_snapshot=snapshot)
    project.simulation_requirement = "分析台风导致沿海核电站事故及其社会生态影响。"
    ProjectManager.save_project(project)
    ProjectManager.save_extracted_text(project.project_id, "沿海核电站、居民区、医院与渔业社区。")
    state = SimulationManager().create_simulation(
        project_id=project.project_id,
        graph_id="graph_step2_contract",
        effort_snapshot=snapshot,
    )

    yield create_app().test_client(), state, snapshot

    (
        ProjectManager.PROJECTS_DIR,
        SimulationManager.SIMULATION_DATA_DIR,
        TaskManager.TASKS_DIR,
        SemanticArtifactStore.ROOT,
        Config.LLM_API_KEY,
    ) = originals
    shutil.rmtree(root, ignore_errors=True)


def _new_payload(state, snapshot):
    return {
        "simulation_id": state.simulation_id,
        "effort_snapshot_id": snapshot["effort_snapshot_id"],
        "event_inputs": [
            {
                "input_id": "event_1",
                "name": "台风引发沿海核事故",
                "description": "台风导致核电站进水、断电和冷却失效，随后放射性物质通过海洋和大气传播。",
                "order": 1,
            }
        ],
        "policy_inputs": [
            {"input_id": "policy_1", "name": "居民疏散", "intent": "组织沿海居民分区疏散"},
            {"input_id": "policy_2", "name": "渔业限制与补偿", "intent": "暂停捕捞并补偿渔民"},
        ],
        "advanced_overrides": {"step_unit": "hour", "step_value": 6, "total_rounds": 20},
    }


def test_new_prepare_contract_fixes_architecture_and_drops_manual_agent_count(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    # These stale legacy knobs must not control a new-contract request.
    payload.update({"search_mode": "fast", "target_agent_count": 999, "hazard_template_id": "air_release"})

    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        response = client.post("/api/simulation/prepare", json=payload)

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    result = body["data"]
    assert result["simulation_architecture"] == "llm_mechanism_v1"
    assert result["search_mode"] == "deep_search"
    assert result["hazard_template_id"] == "generic"
    assert "target_agent_count" not in result
    assert result["agent_plan_source"] == "agent_v2"
    assert result["scenario_planning_input"]["role_demands"]
    foundation = result["scenario_planning_input"]["foundation_ref"]
    assert foundation["contract_version"] == "foundation.step1.v3"
    assert foundation["content_hash"] != snapshot["content_hash"]
    assert result["time_plan"]["step_unit"] == "hour"
    assert result["time_plan"]["step_size"] == 6
    assert result["effort_snapshot"]["effort_snapshot_id"] == snapshot["effort_snapshot_id"]

    sim_dir = os.path.join(SimulationManager.SIMULATION_DATA_DIR, state.simulation_id)
    assert os.path.exists(os.path.join(sim_dir, "agent_planning_request.json"))


def test_prepare_accepts_event_and_policy_projected_from_same_source_input(
    step2_contract_workspace,
):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    payload["event_inputs"] = [
        {
            "input_id": "compound_scene_1",
            "name": "8号风球袭港",
            "description": "香港八号烈风或暴风信号生效。",
            "atomic_keys": ["typhoon", "strong_wind"],
        }
    ]
    payload["policy_inputs"] = [
        {
            "input_id": "compound_scene_1",
            "name": "停工停学",
            "intent": "学校停课，公司停工。",
            "action_primitives": ["school_closure", "workplace_shutdown"],
        }
    ]

    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        response = client.post("/api/simulation/prepare", json=payload)

    assert response.status_code == 200
    result = response.get_json()["data"]["scenario_planning_input"]
    assert result["normalized_user_events"][0]["input_id"] == "compound_scene_1"
    assert result["normalized_user_policies"][0]["input_id"] == "compound_scene_1"


def test_prepare_status_prioritizes_explicit_regeneration_task_over_old_ready_artifacts(
    step2_contract_workspace,
):
    client, state, _snapshot = step2_contract_workspace
    task_manager = TaskManager()
    task_id = task_manager.create_task(
        "重新生成场景",
        metadata={"simulation_id": state.simulation_id},
        task_type="simulation_prepare",
    )
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=62,
        message="正在生成代理体与关系",
    )

    with patch.object(
        simulation_api,
        "_check_simulation_prepared",
        return_value=(True, {"status": "ready", "config_generated": True}),
    ):
        response = client.post(
            "/api/simulation/prepare/status",
            json={"task_id": task_id, "simulation_id": state.simulation_id},
        )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"] == task_id
    assert data["status"] == "processing"
    assert data["progress"] == 62
    assert data["already_prepared"] is False


def test_new_prepare_rejects_conflicting_or_missing_effort_reference(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    payload["effort_snapshot_id"] = "effort_othercontract"
    response = client.post("/api/simulation/prepare", json=payload)
    assert response.status_code == 409
    assert response.get_json()["code"] == "effort_snapshot_conflict"

    payload.pop("effort_snapshot_id")
    response = client.post("/api/simulation/prepare", json=payload)
    assert response.status_code == 409
    assert "缺少已锁定" in response.get_json()["error"]


def test_prepare_rejects_project_and_simulation_effort_drift(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    project = ProjectManager.get_project(state.project_id)
    project.effort_snapshot = build_effort_snapshot(
        "high",
        effort_snapshot_id="effort_projectdrift",
    )
    ProjectManager.save_project(project)

    response = client.post("/api/simulation/prepare", json=_new_payload(state, snapshot))

    assert response.status_code == 409
    assert "项目" in response.get_json()["error"]


def test_legacy_prepare_payload_remains_readable(step2_contract_workspace):
    client, state, _snapshot = step2_contract_workspace
    payload = {
        "simulation_id": state.simulation_id,
        "injected_variables": [
            {"variable_id": "legacy_1", "type": "disaster", "name": "历史洪水变量"}
        ],
        "search_mode": "fast",
        "target_agent_count": 24,
    }
    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        response = client.post("/api/simulation/prepare", json=payload)

    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["search_mode"] == "deep_search"
    assert result["simulation_architecture"] == "llm_mechanism_v1"
    assert result["target_agent_count"] == 24
    assert result["injected_variables_count"] == 1
    assert result["agent_plan_source"] == "agent_v2"
    assert result["scenario_planning_input"]["normalized_user_events"][0]["name"] == "历史洪水变量"


@pytest.mark.parametrize(
    "field,value,error_text",
    [
        ("event_inputs", "不是数组", "灾害事件必须使用数组格式"),
        ("policy_inputs", {"name": "疏散"}, "政策措施必须使用数组格式"),
    ],
)
def test_new_prepare_rejects_invalid_input_shapes(step2_contract_workspace, field, value, error_text):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    payload[field] = value

    response = client.post("/api/simulation/prepare", json=payload)

    assert response.status_code == 400
    assert error_text in response.get_json()["error"]


def test_new_prepare_does_not_require_legacy_simulation_requirement(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    project = ProjectManager.get_project(state.project_id)
    project.simulation_requirement = ""
    ProjectManager.save_project(project)

    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        response = client.post("/api/simulation/prepare", json=_new_payload(state, snapshot))

    assert response.status_code == 200
    assert response.get_json()["data"]["scenario_planning_input"]["normalized_user_events"]


def test_prepare_reuses_active_task_for_identical_scenario_input(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)

    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        first = client.post("/api/simulation/prepare", json=payload)
        first_task_id = first.get_json()["data"]["task_id"]
        TaskManager().update_task(
            first_task_id,
            status=TaskStatus.PROCESSING,
            progress=73,
            message="正在生成 Agent 与关系",
        )
        second = client.post("/api/simulation/prepare", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    first_data = first.get_json()["data"]
    second_data = second.get_json()["data"]
    assert second_data["task_id"] == first_data["task_id"]
    assert second_data["status"] == "preparing"
    assert second_data["task_status"] == "processing"
    assert second_data["progress"] == 73
    assert second_data["reused_task"] is True
    assert second_data["scenario_planning_input"]["content_hash"] == first_data["scenario_planning_input"]["content_hash"]

    tasks = TaskManager().list_tasks()
    assert len(tasks) == 1
    persisted = SimulationManager().get_simulation(state.simulation_id)
    assert persisted.prepare_task_id == first_data["task_id"]
    assert persisted.planning_content_hash == first_data["scenario_planning_input"]["content_hash"]


def test_prepare_rejects_changed_input_while_task_is_active(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    original = _new_payload(state, snapshot)
    changed = deepcopy(original)
    changed["event_inputs"][0]["description"] = "台风登陆后仅发生局地内涝。"

    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        first = client.post("/api/simulation/prepare", json=original)
        conflict = client.post("/api/simulation/prepare", json=changed)

    assert first.status_code == 200
    assert conflict.status_code == 409
    body = conflict.get_json()
    assert body["code"] == "scenario_input_changed"
    assert body["data"]["task_id"] == first.get_json()["data"]["task_id"]
    assert "另一组输入" in body["error"]
    assert len(TaskManager().list_tasks()) == 1
