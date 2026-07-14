from app.services.agent_action_contract import (
    AGENT_ACTION_CONTRACT_VERSION,
    consume_action_resources,
    validate_agent_action,
)
from app.services.scenario_planning.agent_archetypes import list_agent_archetypes


def _actor(**overrides):
    actor = {
        "agent_id": 1,
        "action_space": ["enforce_restriction", "monitor"],
        "capability_keys": ["regulatory_enforcement"],
        "permission_keys": [],
        "resource_budget": {"attention": 10.0, "coordination": 5.0, "authority": 80.0},
        "representation_level": "institution",
        "lifecycle_status": "active",
        "runtime_lifecycle": {"lifecycle_status": "active"},
    }
    actor.update(overrides)
    return actor


def test_high_authority_action_requires_explicit_permission():
    result = validate_agent_action(_actor(), "enforce_restriction")

    assert result["contract_version"] == AGENT_ACTION_CONTRACT_VERSION
    assert result["accepted"] is False
    assert "缺少动作所需权限" in result["rejection_reasons_zh"]


def test_accepted_action_consumes_resources_and_updates_uncertainty():
    actor = _actor(permission_keys=["issue_regulatory_order"])
    validation = validate_agent_action(actor, "enforce_restriction")
    settlement = consume_action_resources(actor, validation)

    assert validation["accepted"] is True
    assert settlement["consumed"] == {"attention": 1.0, "coordination": 1.0}
    assert actor["resource_budget"]["attention"] == 9.0
    assert actor["resource_budget"]["coordination"] == 4.0
    assert actor["resource_budget"]["authority"] == 80.0
    assert actor["resource_uncertainty"]["attention"] == [7.2, 10.8]


def test_provisional_agent_cannot_execute_irreversible_action_even_with_permission():
    actor = _actor(
        permission_keys=["issue_regulatory_order"],
        representation_level="runtime_provisional",
    )

    result = validate_agent_action(actor, "enforce_restriction")

    assert result["accepted"] is False
    assert "临时 Agent 不得执行不可逆或高权限动作" in result["rejection_reasons_zh"]


def test_action_outside_profile_action_space_is_rejected():
    result = validate_agent_action(_actor(), "patient_triage")

    assert result["accepted"] is False
    assert "动作不在该 Agent 的行动空间内" in result["rejection_reasons_zh"]


def test_every_archetype_action_has_an_executable_contract():
    failures = []
    for archetype in list_agent_archetypes():
        actor = {
            "action_space": archetype["available_action_keys"],
            "capability_keys": archetype["capabilities"],
            "permission_keys": archetype["permissions"],
            "resource_budget": archetype["default_resources"],
            "representation_level": "institution",
            "lifecycle_status": "active",
        }
        for action_key in archetype["available_action_keys"]:
            validation = validate_agent_action(actor, action_key)
            if not validation["accepted"]:
                failures.append(
                    (
                        archetype["archetype_key"],
                        action_key,
                        validation["rejection_reasons_zh"],
                    )
                )

    assert failures == []
