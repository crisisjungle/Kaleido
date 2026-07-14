from app.services.policy_runtime import execute_policy_binding


def _actor(agent_id=1):
    return {
        "agent_id": agent_id,
        "lifecycle_status": "active",
        "primary_region": "region_a",
        "coverage_region_ids": ["region_a"],
        "capability_keys": ["compensation_administration", "fiscal_resource_allocation"],
        "permission_keys": ["administer_compensation"],
        "resource_budget": {"fiscal": 4, "coordination": 2},
    }


def _binding(**overrides):
    value = {
        "policy_id": "policy_compensation",
        "label_zh": "生计补偿",
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
        "state_effect_template": {"economic_stress": -0.6, "public_trust": 0.4},
        "start_round": 2,
        "duration_rounds": 2,
    }
    value.update(overrides)
    return value


def test_due_bound_policy_executes_and_settles_relative_resources():
    actor = _actor()
    event = execute_policy_binding(
        binding=_binding(),
        actor_lookup={1: actor},
        round_number=2,
        available_target_region_ids=["region_a"],
        scenario_version_ref={"artifact_id": "scenario_1"},
    )

    assert event["execution_status"] == "executed"
    assert event["state_effect_delta"]["economic_stress"] == -0.3
    assert actor["resource_budget"]["fiscal"] == 3
    assert event["resource_settlements"][0]["consumed"]["coordination"] == 0.5


def test_unbound_or_out_of_jurisdiction_policy_cannot_change_state():
    actor = _actor()
    event = execute_policy_binding(
        binding=_binding(target_region_ids=["region_b"]),
        actor_lookup={1: actor},
        round_number=2,
        available_target_region_ids=["region_a", "region_b"],
        scenario_version_ref={},
    )

    assert event["execution_status"] == "blocked"
    assert event["state_effect_delta"] == {}
    assert event["outside_jurisdiction_region_ids"] == ["region_b"]
    assert actor["resource_budget"]["fiscal"] == 4


def test_policy_outside_active_window_emits_no_execution_event():
    assert execute_policy_binding(
        binding=_binding(),
        actor_lookup={1: _actor()},
        round_number=1,
        available_target_region_ids=["region_a"],
        scenario_version_ref={},
    ) is None
