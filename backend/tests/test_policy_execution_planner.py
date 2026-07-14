from app.services.scenario_planning.policy_execution_planner import PolicyExecutionPlanner


def _profile(
    agent_id,
    *,
    capabilities,
    permissions,
    resources,
    region="region_a",
):
    return {
        "agent_id": agent_id,
        "name": f"执行主体 {agent_id}",
        "primary_region": region,
        "coverage_region_ids": [region],
        "capability_keys": capabilities,
        "permission_keys": permissions,
        "resource_budget": resources,
        "lifecycle_status": "active",
    }


def test_evacuation_policy_binds_complementary_government_and_transport_agents():
    plan = PolicyExecutionPlanner().build(
        policy_plan=[
            {
                "policy_id": "policy_evacuation",
                "label_zh": "分区疏散",
                "executor_capability_keys": [
                    "emergency_command",
                    "evacuation_coordination",
                    "transport_dispatch",
                ],
                "effect_primitives": ["population_relocation", "exposure_reduction"],
                "target_region_ids": ["region_a"],
                "start_round": 2,
                "duration_rounds": 3,
            }
        ],
        profiles=[
            _profile(
                1,
                capabilities=["emergency_command", "evacuation_coordination"],
                permissions=["order_area_evacuation"],
                resources={"coordination": 5, "response": 5, "authority": 5},
            ),
            _profile(
                2,
                capabilities=["transport_dispatch"],
                permissions=["manage_assigned_transport_network"],
                resources={"transport": 5, "coordination": 2},
            ),
        ],
        planning_input_ref={"planning_input_id": "planning_1"},
    )

    binding = plan["policy_bindings"][0]
    assert binding["binding_status"] == "bound"
    assert binding["executor_agent_ids"] == [1, 2]
    assert binding["missing_capability_keys"] == []
    assert binding["state_effect_template"]["exposure_score"] < 0


def test_unbound_policy_is_preserved_but_cannot_auto_execute():
    plan = PolicyExecutionPlanner().build(
        policy_plan=[
            {
                "policy_id": "policy_compensation",
                "label_zh": "生计补偿",
                "executor_capability_keys": [
                    "compensation_administration",
                    "fiscal_resource_allocation",
                ],
                "effect_primitives": ["economic_compensation", "livelihood_stabilization"],
                "target_region_ids": ["region_a"],
            }
        ],
        profiles=[],
        planning_input_ref={"planning_input_id": "planning_1"},
    )

    binding = plan["policy_bindings"][0]
    assert binding["binding_status"] == "unbound"
    assert binding["executor_agent_ids"] == []
    assert "政策不会自动生效" in binding["binding_reason_zh"]
    assert binding["state_effect_template"]["livelihood_stability"] > 0


def test_compensation_requires_permission_and_relative_fiscal_capacity():
    policy = {
        "policy_id": "policy_compensation",
        "label_zh": "生计补偿",
        "executor_capability_keys": [
            "compensation_administration",
            "fiscal_resource_allocation",
        ],
        "effect_primitives": ["economic_compensation", "livelihood_stabilization"],
        "target_region_ids": ["region_a"],
    }
    missing = PolicyExecutionPlanner().build(
        policy_plan=[policy],
        profiles=[
            _profile(
                1,
                capabilities=policy["executor_capability_keys"],
                permissions=[],
                resources={"fiscal": 0, "coordination": 2},
            )
        ],
        planning_input_ref={},
    )["policy_bindings"][0]
    assert missing["binding_status"] == "partial"

    bound = PolicyExecutionPlanner().build(
        policy_plan=[policy],
        profiles=[
            _profile(
                1,
                capabilities=policy["executor_capability_keys"],
                permissions=["administer_compensation"],
                resources={"fiscal": 5, "coordination": 2},
            )
        ],
        planning_input_ref={},
    )["policy_bindings"][0]
    assert bound["binding_status"] == "bound"
