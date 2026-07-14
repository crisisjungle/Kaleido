import json

from app.services.effort_contract import build_effort_snapshot
from app.services.envfish_models import default_state_vector
from scripts.run_envfish_simulation import EnvFishRuntime


def test_runtime_persists_emergent_agent_and_only_activates_it_next_round(tmp_path):
    config_path = tmp_path / "simulation_config.json"
    config = {
        "simulation_id": "runtime_agent_emergence_test",
        "simulation_requirement": "测试运行期能力缺口",
        "time_config": {"total_rounds": 2, "minutes_per_round": 60},
        "region_graph": [
            {
                "region_id": "region_a",
                "name": "测试区域",
                "region_type": "urban_zone",
                "state_vector": default_state_vector("disaster_mode", "Region"),
            }
        ],
        "subregion_graph": [],
        "transport_edges": [],
        "actor_profiles": [],
        "agent_relationship_graph": [],
        "region_agent_index": {},
        "effort_snapshot": build_effort_snapshot(
            "high", effort_snapshot_id="effort_runtimeintegration"
        ),
        "role_demands": [
            {
                "demand_id": "demand_runtime_nuclear_regulator",
                "demand_key": "nuclear_safety_regulator",
                "label_zh": "核安全监管能力",
                "required_capability_keys": ["nuclear_safety_regulation"],
                "jurisdiction_region_ids": ["region_a"],
                "required_resolution": "organization",
                "importance": "critical",
                "evidence_score": 90,
                "impact_score": 90,
                "evidence_refs": ["runtime:test:nuclear_release"],
            }
        ],
        "interaction_policies": {},
        "runtime_limits": {"max_active_agents_per_round": 4},
        "risk_objects": [],
        "risk_definitions": [],
        "latest_risk_runtime_state": {},
        "injected_variables": [],
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    runtime = EnvFishRuntime(str(config_path), no_wait=True)

    emergence = runtime._detect_runtime_agent_emergence(
        round_num=1,
        active_variables=[],
        interactions={"new_dynamic_edges": []},
        feedback={},
        risk_runtime={},
    )

    assert emergence["created_agent_ids"] == [0]
    assert runtime.actor_profiles[0]["runtime_lifecycle"]["activation_round"] == 2
    assert runtime._agent_interaction_update(1, [], {})["active_agent_ids"] == []
    assert (tmp_path / "profiles_full.json").exists()
    assert (tmp_path / "agent_emergence_state.json").exists()
    persisted_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted_config["agent_emergence_state"]["created_or_split_count"] == 1

    activation_events = runtime._activate_due_runtime_agents(2)
    interactions = runtime._agent_interaction_update(2, [], {})

    assert activation_events[0]["event_type"] == "agent_activated"
    assert interactions["active_agent_ids"] == [0]


def test_agent_v2_runtime_does_not_invent_colocation_relationships(tmp_path):
    config_path = tmp_path / "simulation_config.json"
    actor_profiles = [
        {
            "agent_id": agent_id,
            "username": f"agent_{agent_id}",
            "name": name,
            "agent_type": "organization",
            "agent_subtype": subtype,
            "primary_region": "region_a",
            "home_region_id": "region_a",
            "influenced_regions": ["region_a"],
            "action_space": ["enforce_restriction", "monitor"],
            "capability_keys": ["environmental_monitoring"],
            "permission_keys": [],
            "resource_budget": {"attention": 3.0, "coordination": 2.0, "authority": 80.0},
            "representation_level": "runtime_provisional",
            "state_vector": default_state_vector("disaster_mode", "OrganizationActor"),
            "runtime_lifecycle": {"lifecycle_status": "active"},
        }
        for agent_id, name, subtype in [
            (1, "监测主体", "environmental_monitoring"),
            (2, "医疗主体", "healthcare_provider"),
        ]
    ]
    config = {
        "simulation_id": "agent_v2_no_colocation",
        "simulation_requirement": "验证关系证据门槛",
        "agent_plan_source": "agent_v2",
        "time_config": {"total_rounds": 1, "minutes_per_round": 60},
        "region_graph": [
            {
                "region_id": "region_a",
                "name": "测试区域",
                "region_type": "urban_zone",
                "state_vector": default_state_vector("disaster_mode", "Region"),
            }
        ],
        "subregion_graph": [],
        "transport_edges": [],
        "actor_profiles": actor_profiles,
        "agent_relationship_graph": [],
        "region_agent_index": {"region_a": [1, 2]},
        "effort_snapshot": build_effort_snapshot("high"),
        "role_demands": [],
        "interaction_policies": {},
        "runtime_limits": {"max_active_agents_per_round": 2},
        "risk_objects": [],
        "risk_definitions": [],
        "latest_risk_runtime_state": {},
        "injected_variables": [],
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    runtime = EnvFishRuntime(str(config_path), no_wait=True)

    assert runtime._candidate_relationship_edges(runtime.actor_profiles[0]) == []
    result = runtime._agent_interaction_update(1, [], {})
    assert result["agent_interactions"] == []
    assert runtime.actor_profiles[0]["resource_budget"]["attention"] == 2.0
    decisions = [
        json.loads(line)
        for line in (tmp_path / "agent_action_decision_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert decisions[0]["selected_action_key"] == "monitor"
    assert decisions[0]["candidate_evaluations"][0]["action_key"] == "enforce_restriction"
    assert decisions[0]["candidate_evaluations"][0]["accepted"] is False


def test_agent_v2_interaction_writes_relationship_event_and_updates_state(tmp_path):
    config_path = tmp_path / "simulation_config.json"
    actors = [
        {
            "agent_id": agent_id,
            "username": f"agent_{agent_id}",
            "name": name,
            "agent_type": "organization",
            "agent_subtype": "environmental_monitoring",
            "primary_region": "region_a",
            "home_region_id": "region_a",
            "influenced_regions": ["region_a"],
            "action_space": ["monitor"],
            "capability_keys": ["environmental_monitoring"],
            "permission_keys": [],
            "resource_budget": {"attention": 5.0, "coordination": 2.0},
            "representation_level": "institution",
            "state_vector": default_state_vector("disaster_mode", "OrganizationActor"),
            "runtime_lifecycle": {"lifecycle_status": "active"},
        }
        for agent_id, name in [(1, "监测主体"), (2, "应急主体")]
    ]
    relationship = {
        "relationship_contract_id": "relationship_monitor_report",
        "edge_id": "relationship_monitor_report",
        "source_agent_id": 1,
        "target_agent_id": 2,
        "relation_type": "information_reporting",
        "interaction_channel": "information",
        "initial_trust": 0.5,
        "initial_dependency": 0.3,
        "initial_coordination": 0.4,
        "strength": 0.5,
        "confidence": 0.8,
        "mechanism_edge_ids": ["mechanism_monitor_response"],
        "evidence": ["role_demand:monitoring"],
    }
    config = {
        "simulation_id": "agent_v2_relationship_event",
        "simulation_requirement": "验证关系事件",
        "agent_plan_source": "agent_v2",
        "time_config": {"total_rounds": 1, "minutes_per_round": 60},
        "region_graph": [
            {
                "region_id": "region_a",
                "name": "测试区域",
                "region_type": "urban_zone",
                "state_vector": default_state_vector("disaster_mode", "Region"),
            }
        ],
        "subregion_graph": [],
        "transport_edges": [],
        "actor_profiles": actors,
        "agent_relationship_graph": [relationship],
        "region_agent_index": {"region_a": [1, 2]},
        "effort_snapshot": build_effort_snapshot("high"),
        "role_demands": [],
        "interaction_policies": {},
        "runtime_limits": {"max_active_agents_per_round": 2},
        "risk_objects": [],
        "risk_definitions": [],
        "latest_risk_runtime_state": {},
        "injected_variables": [],
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    runtime = EnvFishRuntime(str(config_path), no_wait=True)

    result = runtime._agent_interaction_update(1, [], {})

    assert len(result["agent_interactions"]) == 1
    interaction = result["agent_interactions"][0]
    relationship_event = result["relationship_events"][0]
    assert interaction["root_event_id"] == interaction["event_id"]
    assert interaction["parent_event_ids"] == []
    assert interaction["hop"] == 0
    assert relationship_event["event_type"] == "information_disclosure"
    assert relationship_event["root_event_id"] == interaction["event_id"]
    assert relationship_event["parent_event_ids"] == [interaction["event_id"]]
    assert relationship_event["hop"] == 1
    state = next(
        item
        for item in result["relationship_states"]
        if item["relationship_contract_id"] == "relationship_monitor_report"
    )
    assert state["trust"] > 0.5
    assert state["last_updated_round"] == 1
    assert runtime._candidate_relationship_edges(runtime.actor_profiles[1]) == []
    assert (tmp_path / "relationship_event_ledger.jsonl").exists()
    assert (tmp_path / "latest_relationship_states.json").exists()

    dynamic_edge = {
        "edge_id": "dynamic::1::2::response_bridge",
        "source_agent_id": 1,
        "target_agent_id": 2,
        "source_region_id": "region_a",
        "target_region_id": "region_a",
        "edge_type": "response_bridge",
        "interaction_channel": "information",
        "layer": "dynamic",
        "status": "active",
        "strength": 0.3,
        "confidence": 0.4,
        "ttl_rounds": 2,
        "reconfirm_count": 1,
    }
    runtime.dynamic_edge_lookup[dynamic_edge["edge_id"]] = dynamic_edge
    runtime._rebuild_dynamic_edge_index()

    second_round = runtime._agent_interaction_update(2, [], {})
    second_interaction = second_round["agent_interactions"][0]
    dynamic_events = [
        json.loads(line)
        for line in (tmp_path / "dynamic_edge_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    activated = dynamic_events[-1]
    lifecycle_events = [
        json.loads(line)
        for line in (tmp_path / "relationship_event_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lifecycle_update = next(
        item
        for item in lifecycle_events
        if item["round_number"] == 2 and item["event_type"] == "relationship_updated"
    )
    assert activated["event_type"] == "activated"
    assert activated["root_event_id"] == second_interaction["event_id"]
    assert activated["parent_event_ids"] == [second_interaction["event_id"]]
    assert activated["hop"] == 1
    assert lifecycle_update["root_event_id"] == second_interaction["event_id"]
    assert lifecycle_update["parent_event_ids"] == [activated["event_id"]]
    assert lifecycle_update["hop"] == 2


def test_agent_v2_bound_policy_executes_through_agent_resources_and_state_ledger(tmp_path):
    config_path = tmp_path / "simulation_config.json"
    region_vector = default_state_vector("disaster_mode", "Region")
    region_vector["economic_stress"] = 60
    actor = {
        "agent_id": 1,
        "name": "地方应急与补偿执行主体",
        "agent_type": "governance",
        "agent_subtype": "emergency_office",
        "primary_region": "region_a",
        "coverage_region_ids": ["region_a"],
        "capability_keys": ["compensation_administration", "fiscal_resource_allocation"],
        "permission_keys": ["administer_compensation"],
        "resource_budget": {"fiscal": 4, "coordination": 2},
        "state_vector": default_state_vector("disaster_mode", "GovernmentActor"),
        "runtime_lifecycle": {"lifecycle_status": "active"},
        "lifecycle_status": "active",
    }
    config = {
        "simulation_id": "agent_v2_policy_execution",
        "agent_plan_source": "agent_v2",
        "time_config": {"total_rounds": 1, "minutes_per_round": 60},
        "region_graph": [
            {
                "region_id": "region_a",
                "name": "测试区域",
                "region_type": "urban_zone",
                "state_vector": region_vector,
            }
        ],
        "subregion_graph": [],
        "transport_edges": [],
        "actor_profiles": [actor],
        "agent_relationship_graph": [],
        "region_agent_index": {"region_a": [1]},
        "effort_snapshot": build_effort_snapshot("high"),
        "role_demands": [],
        "interaction_policies": {},
        "runtime_limits": {"max_active_agents_per_round": 1},
        "risk_objects": [],
        "risk_definitions": [],
        "latest_risk_runtime_state": {},
        "injected_variables": [],
        "policy_execution_plan": {
            "contract_version": "policy-execution-plan.v2",
            "policy_bindings": [
                {
                    "policy_id": "policy_compensation",
                    "label_zh": "受影响群体生计补偿",
                    "binding_status": "bound",
                    "executor_agent_ids": [1],
                    "required_capability_keys": [
                        "compensation_administration",
                        "fiscal_resource_allocation",
                    ],
                    "required_permission_groups": [["administer_compensation"]],
                    "resource_requirements": {"fiscal": 2, "coordination": 1},
                    "target_region_ids": ["region_a"],
                    "target_scope_source": "policy_explicit",
                    "state_effect_template": {"economic_stress": -2, "public_trust": 1},
                    "effect_primitives": ["economic_compensation"],
                    "start_round": 1,
                    "duration_rounds": 2,
                }
            ],
        },
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    runtime = EnvFishRuntime(str(config_path), no_wait=True)

    result = runtime._execute_policy_plan(1)

    assert result["summary"]["executed_count"] == 1
    assert runtime.region_lookup["region_a"]["state_vector"]["economic_stress"] == 59
    assert runtime.actor_lookup[1]["resource_budget"]["fiscal"] == 3
    assert result["state_mutation_records"]
    assert all(
        item["source_type"] == "policy_execution"
        for item in result["state_mutation_records"]
    )
    assert (tmp_path / "policy_execution_ledger.jsonl").exists()
    assert (tmp_path / "latest_policy_execution_state.json").exists()
