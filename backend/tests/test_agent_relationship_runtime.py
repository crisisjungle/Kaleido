from app.services.agent_relationship_runtime import (
    apply_relationship_event,
    build_interaction_event,
    build_lifecycle_event,
    initialize_relationship_states,
    upsert_relationship_state,
)


def _edge(**overrides):
    edge = {
        "relationship_contract_id": "relationship_contract_test",
        "source_agent_id": 1,
        "target_agent_id": 2,
        "relation_type": "emergency_coordination",
        "initial_trust": 0.55,
        "initial_dependency": 0.35,
        "initial_coordination": 0.45,
        "confidence": 0.7,
        "mechanism_edge_ids": ["mechanism_release_response"],
        "evidence": ["role_demand:response"],
    }
    edge.update(overrides)
    return edge


def test_initial_relationship_state_comes_from_contract():
    states = initialize_relationship_states([_edge()])

    assert len(states) == 1
    state = states[0]
    assert state["relationship_contract_id"] == "relationship_contract_test"
    assert state["trust"] == 0.55
    assert state["dependency"] == 0.35
    assert state["coordination"] == 0.45
    assert state["mechanism_edge_ids"] == ["mechanism_release_response"]


def test_successful_cooperation_event_is_the_only_input_that_changes_state():
    state = initialize_relationship_states([_edge()])[0]
    event = build_interaction_event(
        round_number=3,
        edge=_edge(),
        action_key="coordinate_response",
        action_label_zh="协调响应",
        source_action_ref={"artifact_id": "action_3_1", "contract_version": "agent-action.v2"},
        state_mutation_refs=[],
        success_status="success",
        scenario_version_ref={"artifact_id": "scenario_v1"},
    )
    next_state = apply_relationship_event(state, event)

    assert event["event_type"] == "cooperation"
    assert event["path_edge_ids"] == ["relationship_contract_test"]
    assert event["related_edge_ids"] == ["mechanism_release_response"]
    assert next_state["trust"] > state["trust"]
    assert next_state["coordination"] > state["coordination"]
    assert next_state["last_event_ref"]["artifact_id"] == event["relationship_event_id"]
    assert next_state["last_updated_round"] == 3


def test_relationship_event_preserves_only_explicit_causal_context():
    event = build_interaction_event(
        round_number=3,
        edge=_edge(),
        action_key="coordinate_response",
        action_label_zh="协调响应",
        source_action_ref={"artifact_id": "action_3_1", "contract_version": "agent-action.v2"},
        state_mutation_refs=[],
        success_status="success",
        scenario_version_ref={"artifact_id": "scenario_v1"},
        causal_context={
            "root_event_id": "interaction_root",
            "parent_event_ids": ["interaction_root"],
            "hop": 1,
        },
    )

    assert event["root_event_id"] == "interaction_root"
    assert event["parent_event_ids"] == ["interaction_root"]
    assert event["hop"] == 1

    standalone = build_lifecycle_event(
        round_number=4,
        edge=_edge(),
        lifecycle_event_type="updated",
        scenario_version_ref={"artifact_id": "scenario_v1"},
    )
    assert standalone["root_event_id"] == standalone["relationship_event_id"]
    assert standalone["parent_event_ids"] == []
    assert standalone["hop"] == 0
    assert standalone["path_edge_ids"] == ["relationship_contract_test"]
    assert standalone["related_edge_ids"] == ["mechanism_release_response"]


def test_relationship_interruption_is_recorded_as_lifecycle_event():
    state = initialize_relationship_states([_edge()])[0]
    event = build_lifecycle_event(
        round_number=5,
        edge=_edge(),
        lifecycle_event_type="expired",
        scenario_version_ref={"artifact_id": "scenario_v1"},
    )
    next_state = apply_relationship_event(state, event)

    assert event["event_type"] == "relationship_interrupted"
    assert next_state["status"] == "dormant"
    assert next_state["tension"] > state["tension"]


def test_dynamic_edge_gets_a_minimal_state_without_fabricating_extra_edges():
    dynamic = _edge(
        relationship_contract_id="",
        edge_id="dynamic_1_2_response_bridge",
        relation_type="response_bridge",
    )
    states, state = upsert_relationship_state([], dynamic)

    assert len(states) == 1
    assert state["relationship_contract_id"] == "dynamic_1_2_response_bridge"
