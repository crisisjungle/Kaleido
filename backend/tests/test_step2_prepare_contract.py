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
from app.services.simulation_manager import SimulationManager, SimulationStatus
from app.services.semantic_input import SemanticArtifactStore
from app.services.spatial_evidence import FacilityQueryPlan, SpatialEvidenceRequest
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
        Config.SPATIAL_CATALOG_PATH,
    )
    ProjectManager.PROJECTS_DIR = os.path.join(root, "projects")
    SimulationManager.SIMULATION_DATA_DIR = os.path.join(root, "simulations")
    TaskManager.TASKS_DIR = os.path.join(root, "tasks")
    SemanticArtifactStore.ROOT = os.path.join(root, "semantic_inputs")
    Config.LLM_API_KEY = ""
    Config.SPATIAL_CATALOG_PATH = os.path.join(root, "spatial_catalog.sqlite3")

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
        Config.SPATIAL_CATALOG_PATH,
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


def test_prepare_spatial_refinement_queries_configured_controlled_catalog(
    step2_contract_workspace,
):
    _client, _state, _snapshot = step2_contract_workspace
    request = SpatialEvidenceRequest(
        request_id="request_hospital_controlled",
        label_zh="应急医疗设施",
        request_kind="facility_discovery",
        resolution_level="R3",
        priority=90,
        importance="critical",
        facility_class_keys=["hospital", "emergency_hospital"],
        representation_requirement="facility_required",
        minimum_evidence_grade="B",
        allowed_source_kinds=["authoritative", "controlled_spatial_index"],
    )
    plan = FacilityQueryPlan(
        plan_id="facility_query_plan_controlled_catalog",
        scenario_planning_ref={"planning_input_id": "scenario_controlled"},
        event_mechanism_graph_ref={"graph_id": "graph_controlled"},
        effort_snapshot_ref={"effort_snapshot_id": "effort_controlled"},
        requests=[request],
        required_r3_request_ids=[request.request_id],
        required_r4_request_ids=[],
        role_demand_refs=[],
    )

    spatial_scope = {
        "center_lat": 22.72,
        "center_lon": 114.55,
        "radius_m": 5000,
    }
    refined = simulation_api._refine_spatial_evidence(
        plan,
        foundation={
            "map_seed_id": "mapseed_controlled",
            "spatial_scope": spatial_scope,
            "target_catalog": [
                {
                    "id": "facility_hospital_controlled",
                    "name": "沿海区域应急医院",
                    "kind": "entity",
                    "subtype": "hospital",
                    "source_kind": "authoritative",
                    "source_key": "official_health_directory",
                    "provider": "official_health_directory",
                    "source_record_id": "hospital-001",
                    "dataset_version": "2026-07",
                    "lat": 22.72,
                    "lon": 114.55,
                    "tags": {},
                }
            ],
            "evidence_sources": [],
        },
    )

    assert [item["feature_id"] for item in refined["selected_r3_features"]] == [
        "facility_hospital_controlled"
    ]
    assert refined["request_coverage"][0]["status"] == "covered"
    assert refined["provider_attempts"][0]["status"] == "completed"

    # A later scene in the same area can recover the indexed R3 evidence even
    # when its fresh Step 1 target catalog did not contain that facility.
    recovered = simulation_api._refine_spatial_evidence(
        plan,
        foundation={
            "map_seed_id": "mapseed_later",
            "spatial_scope": spatial_scope,
            "target_catalog": [],
            "evidence_sources": [],
        },
    )
    assert [item["feature_id"] for item in recovered["selected_r3_features"]] == [
        "facility_hospital_controlled"
    ]
    assert recovered["request_coverage"][0]["status"] == "covered"


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
    assert foundation["contract_version"] == "foundation.step1.v4"
    assert foundation["content_hash"] != snapshot["content_hash"]
    assert result["time_plan"]["step_unit"] == "hour"
    assert result["time_plan"]["step_size"] == 6
    assert result["effort_snapshot"]["effort_snapshot_id"] == snapshot["effort_snapshot_id"]

    sim_dir = os.path.join(SimulationManager.SIMULATION_DATA_DIR, state.simulation_id)
    assert os.path.exists(os.path.join(sim_dir, "agent_planning_request.json"))
    assert os.path.exists(os.path.join(sim_dir, "facility_query_plan.json"))
    assert os.path.exists(os.path.join(sim_dir, "spatial_refinement_snapshot.json"))
    assert os.path.exists(os.path.join(sim_dir, "foundation_resolution.json"))
    assert os.path.exists(os.path.join(sim_dir, "scenario_configuration_input.json"))
    assert result["scenario_planning_input"]["input_authority"] == "authoritative"
    assert result["facility_query_plan_ref"]["plan_id"].startswith("facility_query_plan_")
    assert result["spatial_refinement_snapshot_ref"]["snapshot_id"].startswith(
        "spatial_refinement_"
    )
    assert result["spatial_evidence_summary"]["required_r3_count"] > 0


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


def test_new_prepare_requires_complete_arrays_and_one_event(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    payload.pop("policy_inputs")
    response = client.post("/api/simulation/prepare", json=payload)
    assert response.status_code == 400
    assert "完整" in response.get_json()["error"]

    payload = _new_payload(state, snapshot)
    payload["event_inputs"] = []
    payload["policy_inputs"] = []
    response = client.post("/api/simulation/prepare", json=payload)
    assert response.status_code == 400
    assert "至少需要一个" in response.get_json()["error"]


def test_new_prepare_accepts_explicit_empty_policy_array(step2_contract_workspace):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    payload["policy_inputs"] = []

    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        response = client.post("/api/simulation/prepare", json=payload)

    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["policy_inputs"] == []
    assert result["scenario_planning_input"]["normalized_user_policies"] == []


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


def test_ready_configuration_is_read_only_and_identical_retry_is_idempotent(
    step2_contract_workspace,
):
    client, state, snapshot = step2_contract_workspace
    payload = _new_payload(state, snapshot)
    with patch.object(TaskExecutor, "start", return_value=None), patch.object(
        ZepEntityReader,
        "filter_defined_entities",
        side_effect=RuntimeError("测试中跳过外部图谱读取"),
    ):
        first = client.post("/api/simulation/prepare", json=payload)
    assert first.status_code == 200

    manager = SimulationManager()
    persisted = manager.get_simulation(state.simulation_id)
    persisted.status = SimulationStatus.READY
    persisted.config_generated = True
    manager._save_simulation_state(persisted)
    sim_dir = manager._get_simulation_dir(state.simulation_id)
    with open(os.path.join(sim_dir, "simulation_config.json"), "w", encoding="utf-8") as handle:
        handle.write('{"event_inputs": [], "policy_inputs": []}')

    identical = client.post("/api/simulation/prepare", json=payload)
    assert identical.status_code == 200
    assert identical.get_json()["data"]["already_prepared"] is True

    changed = deepcopy(payload)
    changed["event_inputs"][0]["description"] = "改成另一组正式事件。"
    conflict = client.post("/api/simulation/prepare", json=changed)
    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "scenario_configuration_locked"

    forced = deepcopy(payload)
    forced["force_regenerate"] = True
    conflict = client.post("/api/simulation/prepare", json=forced)
    assert conflict.status_code == 409
    assert conflict.get_json()["code"] == "scenario_configuration_locked"
