from app.services.agent_planning_port import plan_scenario_agents
from app.services.scenario_planner import AgentPlanningPort, ScenarioPlanner


def _scenario():
    return ScenarioPlanner().build(
        foundation={"artifact_id": "foundation_test", "region_ids": ["region_a"]},
        effort_snapshot_ref={
            "effort_snapshot_id": "effort_porttest123",
            "effort_level": "high",
            "profile_version": "effort-profile-v1",
            "content_hash": "hash",
        },
        user_events=[
            {
                "input_id": "event_typhoon",
                "name": "台风登陆",
                "description": "台风登陆并引发沿海设施进水",
                "order": 1,
                "target_region_ids": ["region_a"],
            }
        ],
        user_policies=[],
    )


def test_default_agent_planning_port_submits_to_agent_v2():
    result = plan_scenario_agents(_scenario())
    assert result["agent_plan_source"] == "agent_v2"
    assert result["agent_plan_contract_version"] == "agent-plan.v2"
    assert result["planning_mode"] == "role_demand_evidence_placement"
    assert result["status"] == "角色需求已提交，等待空间证据匹配"
    assert result["scenario_planning_ref"]["planning_input_id"]


def test_agent_planning_port_is_replaceable():
    class FakePort:
        def plan(self, scenario):
            assert scenario.planning_input_id
            return {"agent_plan_source": "agent_v2_test", "role_demands": []}

    assert isinstance(FakePort(), AgentPlanningPort)
    result = plan_scenario_agents(_scenario(), port=FakePort())
    assert result["agent_plan_source"] == "agent_v2_test"
