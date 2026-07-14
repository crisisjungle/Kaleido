from app.services.agent_emergence_detector import AgentEmergenceDetector
from app.services.effort_contract import build_effort_snapshot


def _demand(
    demand_key="runtime_specialist",
    *,
    evidence=70,
    impact=65,
    importance="high",
    region="region_a",
    capabilities=None,
    **extra,
):
    return {
        "demand_id": f"demand_{demand_key}_{region}",
        "demand_key": demand_key,
        "label_zh": extra.pop("label_zh", "专项应急响应能力"),
        "required_capability_keys": capabilities or [f"{demand_key}_capability"],
        "jurisdiction_region_ids": [region],
        "required_resolution": extra.pop("required_resolution", "organization"),
        "importance": importance,
        "evidence_score": evidence,
        "impact_score": impact,
        "evidence_refs": [f"runtime:test:{demand_key}"],
        **extra,
    }


def _profile(
    agent_id=1,
    *,
    name="现有响应主体",
    subtype="existing_role",
    agent_type="organization",
    region="region_a",
    capability_keys=None,
    lifecycle=None,
    **extra,
):
    return {
        "agent_id": agent_id,
        "username": f"agent_{agent_id}",
        "name": name,
        "node_family": "OrganizationActor",
        "role_type": subtype,
        "agent_type": agent_type,
        "agent_subtype": subtype,
        "primary_region": region,
        "home_region_id": region,
        "influenced_regions": [region],
        "capability_keys": capability_keys or [],
        "capabilities": [],
        "resource_budget": {"attention": 100.0, "coordination": 40.0},
        "state_vector": {},
        "runtime_lifecycle": lifecycle or {"lifecycle_status": "active"},
        **extra,
    }


def test_ordinary_gap_must_persist_for_two_rounds_and_acts_next_round():
    detector = AgentEmergenceDetector()
    snapshot = build_effort_snapshot("high")
    demand = _demand()

    round_one = detector.evaluate(
        current_round=1,
        actor_profiles=[],
        effort_snapshot=snapshot,
        role_demands=[demand],
    )
    assert round_one.created_agent_ids == []
    assert next(iter(round_one.state["candidates"].values()))["consecutive_rounds"] == 1

    round_two = detector.evaluate(
        current_round=2,
        actor_profiles=round_one.actor_profiles,
        effort_snapshot=snapshot,
        role_demands=[demand],
        previous_state=round_one.state,
    )
    assert round_two.created_agent_ids == [0]
    created = round_two.actor_profiles[0]
    assert created["runtime_lifecycle"]["activation_round"] == 3
    assert created["runtime_lifecycle"]["lifecycle_status"] == "pending_activation"
    assert created["decision_policy"]["authority_scope"] == "observation_and_coordination_only"
    assert created["resource_budget"]["authority"] == 0.0
    assert created["lifecycle_status"] == "pending_activation"
    assert created["representation_level"] == "runtime_provisional"
    assert created["role_demand_refs"] == [demand["demand_id"]]
    assert created["permission_keys"] == []
    assert round_two.events[0]["effective_round"] == 3


def test_critical_high_evidence_gap_can_create_immediately():
    result = AgentEmergenceDetector().evaluate(
        current_round=4,
        actor_profiles=[],
        effort_snapshot=build_effort_snapshot("high"),
        role_demands=[
            _demand(
                "nuclear_safety_regulator",
                evidence=90,
                impact=90,
                importance="critical",
                label_zh="核安全监管能力",
            )
        ],
    )

    assert result.created_agent_ids == [0]
    assert result.events[0]["event_type"] == "agent_created"
    assert result.events[0]["round"] == 4
    assert result.events[0]["effective_round"] == 5
    assert result.actor_profiles[0]["archetype_key"] == "industry_regulator"
    assert result.actor_profiles[0]["profile_confidence"] == 0.8


def test_static_prepare_gap_does_not_turn_into_a_runtime_agent_without_new_evidence():
    static_gap = _demand(
        "emergency_medical_response",
        evidence=95,
        impact=95,
        importance="critical",
        label_zh="医疗应急响应能力",
    )
    static_gap["evidence_refs"] = ["event:event_release", "mechanism:medical_exposure"]
    static_gap["source_type"] = "mechanism"

    result = AgentEmergenceDetector().evaluate(
        current_round=4,
        actor_profiles=[],
        effort_snapshot=build_effort_snapshot("ultra"),
        role_demands=[static_gap],
    )

    assert result.created_agent_ids == []
    assert result.state["candidates"] == {}
    assert result.candidate_ledger[0]["status"] == "waiting_runtime_evidence"


def test_dormant_agent_is_reactivated_before_any_new_agent_is_created():
    dormant = _profile(
        capability_keys=["special_response"],
        lifecycle={"lifecycle_status": "dormant"},
    )
    result = AgentEmergenceDetector().evaluate(
        current_round=2,
        actor_profiles=[dormant],
        effort_snapshot=build_effort_snapshot("light"),
        role_demands=[
            _demand(
                capabilities=["special_response"],
                evidence=85,
                impact=85,
                importance="critical",
            )
        ],
    )

    assert result.activated_agent_ids == [1]
    assert result.created_agent_ids == []
    assert result.split_agent_ids == []
    assert result.state["created_or_split_count"] == 0
    assert result.actor_profiles[0]["runtime_lifecycle"]["activation_round"] == 3


def test_aggregate_split_conserves_parent_and_child_resources():
    aggregate = _profile(
        agent_type="human",
        subtype="resident",
        is_aggregate=True,
        aggregation={"is_aggregate": True, "member_count": 5000},
    )
    demand = _demand(
        "affected_population",
        evidence=85,
        impact=85,
        importance="critical",
        required_resolution="population_group",
        capabilities=["evacuation_participation"],
        label_zh="重点疏散居民群体",
        requires_independent_agent=True,
    )

    result = AgentEmergenceDetector().evaluate(
        current_round=3,
        actor_profiles=[aggregate],
        effort_snapshot=build_effort_snapshot("high"),
        role_demands=[demand],
    )

    assert result.split_agent_ids == [2]
    parent, child = result.actor_profiles
    assert parent["resource_budget"]["attention"] + child["resource_budget"]["attention"] == 100.0
    assert parent["resource_budget"]["coordination"] + child["resource_budget"]["coordination"] == 40.0
    assert child["runtime_lifecycle"]["parent_agent_id"] == 1
    assert child["agent_name"] == child["name"]
    assert child["agent_type"] == "human"
    assert "推演第 3 轮" in child["bio"]
    assert "evacuate" in child["action_space"]
    assert result.lineage[0]["resolution_mode"] == "split_aggregate"


def test_mismatched_aggregate_cannot_split_into_unrelated_runtime_role():
    monitoring_aggregate = _profile(
        archetype_key="environmental_monitoring",
        subtype="environment_bureau",
        is_aggregate=True,
        aggregation={"is_aggregate": True, "member_count": 8},
        capability_keys=["environmental_monitoring"],
    )
    demand = _demand(
        "emergency_medical_response",
        evidence=90,
        impact=90,
        importance="critical",
        capabilities=["emergency_medical_response", "patient_transport"],
        label_zh="医疗应急响应能力",
        requires_independent_agent=True,
    )

    result = AgentEmergenceDetector().evaluate(
        current_round=2,
        actor_profiles=[monitoring_aggregate],
        effort_snapshot=build_effort_snapshot("high"),
        role_demands=[demand],
    )

    assert result.split_agent_ids == []
    assert result.created_agent_ids == [2]
    parent, child = result.actor_profiles
    assert parent["resource_budget"]["attention"] == 100.0
    assert child["representation_level"] == "runtime_provisional"
    assert child["archetype_key"] == "healthcare_provider"
    assert child["agent_name"] == child["name"] == "医疗应急响应临时响应主体"
    assert "patient_triage" in child["action_space"]
    assert child["permission_keys"] == []


def test_light_tier_caps_creation_to_one_agent_for_the_whole_run():
    demands = [
        _demand(
            f"critical_gap_{index}",
            region=f"region_{index}",
            evidence=90,
            impact=90,
            importance="critical",
        )
        for index in range(2)
    ]
    first = AgentEmergenceDetector().evaluate(
        current_round=1,
        actor_profiles=[],
        effort_snapshot=build_effort_snapshot("light"),
        role_demands=demands,
    )

    assert len(first.created_agent_ids) == 1
    assert first.state["created_or_split_count"] == 1
    assert any(item["status"] == "capacity_gap" for item in first.candidate_ledger)

    second = AgentEmergenceDetector().evaluate(
        current_round=2,
        actor_profiles=first.actor_profiles,
        effort_snapshot=build_effort_snapshot("light"),
        role_demands=demands,
        previous_state=first.state,
    )
    assert second.created_agent_ids == []


def test_existing_capability_prevents_duplicate_and_relationships_can_raise_a_gap():
    covered = AgentEmergenceDetector().evaluate(
        current_round=1,
        actor_profiles=[
            _profile(
                subtype="environment_bureau",
                capability_keys=["environmental_monitoring"],
            )
        ],
        effort_snapshot=build_effort_snapshot("high"),
        role_demands=[
            _demand(
                "environmental_monitoring",
                capabilities=["environmental_monitoring"],
            )
        ],
    )
    assert covered.created_agent_ids == []
    assert covered.state["candidates"] == {}

    edges = [
        {
            "edge_id": f"dynamic_{index}",
            "source_region_id": "region_a",
            "target_region_id": f"region_{index}",
        }
        for index in range(2)
    ]
    relation_gap = AgentEmergenceDetector().evaluate(
        current_round=1,
        actor_profiles=[],
        effort_snapshot=build_effort_snapshot("high"),
        runtime_signals={"new_dynamic_edges": edges},
    )
    candidate = next(iter(relation_gap.state["candidates"].values()))
    assert candidate["demand_key"] == "cross_region_coordination"
    assert candidate["consecutive_rounds"] == 1


def test_risk_projection_cannot_create_agent_role_demand():
    result = AgentEmergenceDetector().evaluate(
        current_round=1,
        actor_profiles=[],
        effort_snapshot=build_effort_snapshot("high"),
        role_demands=[],
        runtime_signals={
            "risk_runtime": {
                "emergent_role_demands": [
                    {
                        "demand_id": "risk_generated_agent",
                        "demand_key": "public_emergency_command",
                        "required_capability_keys": ["emergency_command"],
                        "evidence_refs": ["risk_runtime:risk_1"],
                        "importance": "critical",
                        "evidence_score": 95,
                        "impact_score": 95,
                    }
                ]
            }
        },
    )

    assert result.created_agent_ids == []
    assert result.state["candidates"] == {}
