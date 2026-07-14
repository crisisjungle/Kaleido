"""Focused tests for the Step 2 scenario planning boundary.

All tests are deterministic and network-free.  They cover the planning artifact
owned by Step 2 and deliberately stop before actual Agent generation.
"""

import pytest

from app.services.scenario_planner import (
    LEGACY_AGENT_PLAN_SOURCE,
    LEGACY_SEARCH_MODE,
    LegacyAgentPlanningAdapter,
    ScenarioPlanner,
)


def _effort():
    return {
        "effort_snapshot_id": "effort_demo_high",
        "effort_level": "high",
        "profile_version": "effort.v1",
        "content_hash": "effort-hash",
        "stage_budgets": {"mechanism_candidate_limit": 18, "profile_detail_level": 3},
    }


def _foundation():
    return {
        "artifact_id": "foundation_coast",
        "contract_version": "foundation.v1",
        "content_hash": "foundation-hash",
        "region_ids": ["region_coastal"],
        "location": "沿海核电站周边区域",
    }


def _compound_event():
    return {
        "input_id": "event_user_1",
        "name": "台风引发沿海核事故",
        "description": (
            "台风登陆导致沿海核电站进水、外部电源和冷却失效，"
            "随后发生放射性释放，并通过海洋和大气传播"
        ),
        "order": 1,
        "target_entity_ids": ["nuclear_plant_1"],
    }


def _policies():
    return [
        {"input_id": "policy_1", "name": "居民疏散", "intent": "组织沿海居民分区疏散"},
        {"input_id": "policy_2", "name": "环境监测", "intent": "提高海洋和大气辐射监测频率"},
        {"input_id": "policy_3", "name": "渔业限制与补偿", "intent": "暂停近海捕捞并补偿受影响渔民"},
    ]


def _build_compound():
    return ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[_compound_event()],
        user_policies=_policies(),
    )


def test_normalizes_single_event_and_uses_locked_effort_reference():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[{"name": "极端暴雨", "description": "极端暴雨冲击城区排水系统", "order": 2}],
        user_policies=[],
    )

    event = result.normalized_user_events[0]
    assert event["name"] == "极端暴雨"
    assert event["description"] == "极端暴雨冲击城区排水系统"
    assert event["input_id"].startswith("event_input_")
    assert result.effort_snapshot_ref["effort_snapshot_id"] == "effort_demo_high"
    assert result.effort_snapshot_ref["stage_budgets"]["mechanism_candidate_limit"] == 18
    assert result.simulation_architecture == "llm_mechanism_v1"
    assert result.contract_version == "scenario_planning.v2"
    assert result.compatibility["search_mode"] == "deep_search"


def test_hong_kong_wind_signal_builds_distinct_physical_risk_paths():
    result = ScenarioPlanner().build(
        foundation={
            **_foundation(),
            "location": "深圳市南山区与香港后海湾周边",
        },
        effort_snapshot_ref=_effort(),
        user_events=[{
            "input_id": "wind_signal_8",
            "name": "8号风球袭港",
            "description": "8号风球袭港",
        }],
        user_policies=[{
            "input_id": "policy_school",
            "name": "停工停学",
            "intent": "停工停学",
        }],
    )

    graph = result.event_mechanism_graph
    keys = {item["atomic_key"] for item in graph["nodes"]}
    pairs = {
        (item["source_atomic_key"], item["target_atomic_key"], item["primitive_key"])
        for item in graph["edges"]
    }
    assert "generic_event" not in keys
    assert {"typhoon", "strong_wind", "storm_surge", "traffic_pressure", "ecological_impact"}.issubset(keys)
    assert {
        ("typhoon", "strong_wind", "typhoon_wind_field"),
        ("strong_wind", "traffic_pressure", "wind_mobility_disruption"),
        ("typhoon", "storm_surge", "coastal_inundation"),
        ("storm_surge", "ecological_impact", "storm_surge_wetland_disturbance"),
    }.issubset(pairs)
    assert not any(item["source_event_id"] == item["target_event_id"] for item in graph["edges"])
    assert any("受控气象机制" in item for item in result.assumptions)


def test_compound_typhoon_nuclear_event_becomes_branching_mechanism_graph():
    result = _build_compound()
    graph = result.event_mechanism_graph
    nodes = {item["atomic_key"]: item for item in graph["nodes"]}

    required_keys = {
        "typhoon",
        "facility_ingress",
        "power_loss",
        "cooling_failure",
        "radioactive_release",
        "marine_spread",
        "air_spread",
    }
    assert required_keys.issubset(nodes)
    assert nodes["radioactive_release"]["label_zh"] == "放射性物质释放"
    assert nodes["marine_spread"]["label_zh"] == "污染物海洋传播"
    assert nodes["air_spread"]["label_zh"] == "污染物大气传播"
    assert graph["branching_event_ids"]

    pairs = {
        (item["source_atomic_key"], item["target_atomic_key"], item["primitive_key"])
        for item in graph["edges"]
    }
    assert ("facility_ingress", "power_loss", "water_intrusion_power_failure") in pairs
    assert ("cooling_failure", "radioactive_release", "thermal_control_failure_release") in pairs
    assert ("radioactive_release", "marine_spread", "marine_dispersion") in pairs
    assert ("radioactive_release", "air_spread", "atmospheric_dispersion") in pairs


def test_ordered_event_inputs_connect_with_known_cross_input_mechanism():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[
            {
                "input_id": "event_typhoon",
                "name": "台风登陆",
                "description": "台风登陆沿海区域",
                "order": 1,
                "target_region_ids": ["region_coast"],
            },
            {
                "input_id": "event_ingress",
                "name": "核电站进水",
                "description": "沿海核电站关键设备进水",
                "order": 2,
                "target_region_ids": ["region_plant"],
            },
        ],
        user_policies=[],
    )
    cross_edges = [
        edge
        for edge in result.event_mechanism_graph["edges"]
        if edge["source_atomic_key"] == "typhoon" and edge["target_atomic_key"] == "facility_ingress"
    ]

    assert len(cross_edges) == 1
    assert cross_edges[0]["primitive_key"] == "extreme_weather_facility_impact"
    assert cross_edges[0]["origin"] == "system_inferred"
    windows = {item["event_id"]: item for item in result.temporal_plan["event_windows"]}
    assert windows[cross_edges[0]["target_event_id"]]["start_round"] > windows[cross_edges[0]["source_event_id"]]["start_round"]


def test_unknown_cross_input_cause_uses_low_confidence_user_order_edge():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[
            {"input_id": "event_rain", "name": "强降雨", "description": "城区出现强降雨", "order": 1},
            {"input_id": "event_ecology", "name": "生态影响", "description": "湿地生态受到影响", "order": 2},
        ],
        user_policies=[],
    )
    order_edges = [
        edge for edge in result.event_mechanism_graph["edges"] if edge["origin"] == "user_order"
    ]

    assert len(order_edges) == 1
    assert order_edges[0]["primitive_key"] == "user_order_transition"
    assert order_edges[0]["confidence"] < 0.5
    assert "因果关系待审阅" in order_edges[0]["epistemic_status"]
    assert any("仅确认先后关系" in assumption for assumption in result.assumptions)


def test_short_typhoon_nuclear_leak_infers_missing_bridge_events_and_assumption():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[{"name": "复合灾害", "description": "台风导致海边核电站泄漏", "order": 1}],
        user_policies=[],
    )
    nodes = {item["atomic_key"]: item for item in result.event_mechanism_graph["nodes"]}
    assert {"facility_ingress", "power_loss", "cooling_failure"}.issubset(nodes)
    assert nodes["facility_ingress"]["origin"] == "system_inferred"
    assert nodes["facility_ingress"]["epistemic_status"] == "待审阅的系统推断"
    assert any("补全机制链" in item for item in result.assumptions)


def test_initial_mechanism_library_covers_secondary_spread_and_system_pressure():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[
            {
                "input_id": "event_extended_chain",
                "name": "地震与污染扩散复合影响",
                "description": (
                    "地震引发滑坡、地基液化和次生火灾，化学品泄漏后通过河流传播与地表径流扩散，"
                    "继而造成人群暴露、医疗压力、交通压力、供应压力和治理压力"
                ),
                "order": 1,
                "target_region_ids": ["region_coastal"],
            }
        ],
        user_policies=[],
    )
    keys = {item["atomic_key"] for item in result.event_mechanism_graph["nodes"]}
    edge_keys = {item["primitive_key"] for item in result.event_mechanism_graph["edges"]}
    demand_keys = {item["demand_key"] for item in result.role_demands}

    assert {
        "earthquake", "landslide", "liquefaction", "secondary_fire", "river_spread",
        "surface_spread", "medical_pressure", "traffic_pressure", "supply_pressure", "governance_pressure",
    }.issubset(keys)
    assert "seismic_slope_failure" in edge_keys
    assert "river_network_dispersion" in edge_keys
    assert "mobility_supply_disruption" in edge_keys
    assert {
        "geological_emergency_monitoring", "healthcare_capacity_coordination",
        "transport_continuity", "critical_supply_coordination", "cross_agency_governance",
    }.issubset(demand_keys)


def test_marine_release_branches_to_real_receptors_instead_of_chaining_impacts():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[
            {
                "input_id": "daya_release",
                "name": "大亚湾放射性物质释放",
                "description": (
                    "放射性物质进入近岸水体并通过海洋传播，可能造成人群暴露、深圳湾生态影响、"
                    "珠江口海产品污染、机场港口交通中断和跨部门治理压力"
                ),
                "target_region_ids": ["region_estuary"],
            }
        ],
        user_policies=[],
    )
    graph = result.event_mechanism_graph
    nodes = {item["atomic_key"]: item for item in graph["nodes"]}
    pairs = {
        (item["source_atomic_key"], item["target_atomic_key"], item["primitive_key"])
        for item in graph["edges"]
    }

    assert {
        "radioactive_release",
        "marine_spread",
        "human_exposure",
        "ecological_impact",
        "resource_contamination",
        "traffic_pressure",
        "governance_pressure",
    }.issubset(nodes)
    assert {
        ("marine_spread", "human_exposure", "marine_contact_exposure"),
        ("marine_spread", "ecological_impact", "marine_ecosystem_exposure"),
        ("marine_spread", "resource_contamination", "marine_food_chain_contamination"),
        ("marine_spread", "traffic_pressure", "marine_incident_mobility_control"),
        ("marine_spread", "governance_pressure", "marine_incident_governance_coordination"),
    }.issubset(pairs)
    assert not any(source == "human_exposure" and target == "ecological_impact" for source, target, _ in pairs)
    assert not any(source == "ecological_impact" and target == "traffic_pressure" for source, target, _ in pairs)
    assert nodes["marine_spread"]["event_id"] in graph["branching_event_ids"]
    assert "深圳湾生态影响" in nodes["ecological_impact"]["description_zh"]
    assert "海产品污染" not in nodes["ecological_impact"]["description_zh"]
    assert "珠江口海产品污染" in nodes["resource_contamination"]["description_zh"]
    assert "深圳湾" not in nodes["resource_contamination"]["description_zh"]
    assert "机场港口交通中断" in nodes["traffic_pressure"]["description_zh"]
    assert "跨部门治理压力" not in nodes["traffic_pressure"]["description_zh"]
    assert nodes["human_exposure"]["label_zh"] == "受影响人群"
    assert nodes["ecological_impact"]["label_zh"] == "敏感生态系统"
    assert nodes["resource_contamination"]["label_zh"] == "渔业水域与食品供应链"
    assert nodes["traffic_pressure"]["label_zh"] == "交通与疏散系统"
    assert nodes["governance_pressure"]["label_zh"] == "应急治理与跨部门协同体系"


def test_unknown_intra_event_impacts_branch_from_upstream_and_stay_low_confidence():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[
            {
                "input_id": "unknown_branch",
                "name": "地震复合影响",
                "description": "地震后出现人群暴露和生态影响",
            }
        ],
        user_policies=[],
    )
    fallback_edges = [
        item
        for item in result.event_mechanism_graph["edges"]
        if item["origin"] == "structural_fallback"
    ]

    assert len(fallback_edges) == 2
    assert {item["source_atomic_key"] for item in fallback_edges} == {"earthquake"}
    assert {item["target_atomic_key"] for item in fallback_edges} == {
        "human_exposure",
        "ecological_impact",
    }
    assert all(item["confidence"] < 0.5 for item in fallback_edges)
    assert all("具体因果机制待审阅" in item["epistemic_status"] for item in fallback_edges)


def test_input_contract_rejects_duplicate_ids_and_string_target_lists():
    planner = ScenarioPlanner()
    with pytest.raises(ValueError, match="输入标识重复"):
        planner.normalize_user_events([
            {"input_id": "duplicate", "name": "台风", "description": "台风", "order": 1},
            {"input_id": "duplicate", "name": "暴雨", "description": "暴雨", "order": 2},
        ])
    with pytest.raises(ValueError, match="目标区域必须使用数组格式"):
        planner.normalize_user_policies([
            {"input_id": "policy_bad", "name": "疏散", "intent": "组织疏散", "target_region_ids": "region_a"}
        ])


def test_temporal_plan_respects_causal_order_and_advanced_overrides():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[_compound_event()],
        user_policies=[],
        advanced_overrides={"step_unit": "hour", "step_value": 6, "total_rounds": 20},
    )
    temporal = result.temporal_plan
    windows = {item["event_id"]: item for item in temporal["event_windows"]}
    nodes = {item["atomic_key"]: item for item in result.event_mechanism_graph["nodes"]}

    assert temporal["step_unit"] == "hour"
    assert temporal["step_unit_label_zh"] == "小时"
    assert temporal["step_value"] == 6
    assert temporal["total_rounds"] == 20
    assert windows[nodes["typhoon"]["event_id"]]["start_round"] == 0
    assert windows[nodes["radioactive_release"]["event_id"]]["start_round"] > 0
    assert windows[nodes["marine_spread"]["event_id"]]["start_round"] > windows[nodes["radioactive_release"]["event_id"]]["start_round"]
    assert nodes["marine_spread"]["physical_time_window"]["step_unit"] == "hour"


def test_event_input_override_controls_window_and_intensity_without_atomic_key():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[_compound_event()],
        user_policies=[],
        advanced_overrides={
            "step_unit": "quarter",
            "step_value": 1,
            "total_rounds": 12,
            "event_overrides": {
                "event_user_1": {
                    "start_round": 2,
                    "duration_rounds": 5,
                    "intensity": 91,
                }
            },
        },
    )
    nodes = result.event_mechanism_graph["nodes"]
    windows = result.temporal_plan["event_windows"]

    assert result.temporal_plan["step_unit_label_zh"] == "季度"
    assert all(node["intensity"]["score"] == 91 for node in nodes)
    assert all(node["intensity"]["source_zh"] == "用户高级设置" for node in nodes)
    assert all(window["start_round"] == 2 for window in windows)
    assert all(window["duration_rounds"] == 5 for window in windows)


def test_policy_plan_exposes_effects_capabilities_and_no_executor_agent():
    result = _build_compound()
    policy_by_name = {item["label_zh"]: item for item in result.policy_plan}

    evacuation = policy_by_name["居民疏散"]
    assert "population_relocation" in evacuation["effect_primitives"]
    assert "evacuation_coordination" in evacuation["executor_capability_keys"]
    assert evacuation["expected_effects"]
    assert evacuation["side_effects"]

    fisheries = policy_by_name["渔业限制与补偿"]
    assert "activity_restriction" in fisheries["effect_primitives"]
    assert "economic_compensation" in fisheries["effect_primitives"]
    assert "fisheries_management" in fisheries["executor_capability_keys"]
    assert "compensation_administration" in fisheries["executor_capability_keys"]

    for policy in result.policy_plan:
        assert "executor_agent_id" not in policy
        assert "executor_agent_ids" not in policy


def test_role_demands_cover_vertical_case_without_agent_ids_or_counts():
    result = _build_compound()
    by_key = {item["demand_key"]: item for item in result.role_demands}

    expected = {
        "critical_facility_operator",
        "nuclear_safety_regulator",
        "environmental_monitoring",
        "emergency_medical_response",
        "public_emergency_command",
        "affected_population",
        "fisheries_stakeholders",
    }
    assert expected.issubset(by_key)
    assert by_key["critical_facility_operator"]["required_resolution"] == "specific_facility"
    assert "nuclear_safety_regulation" in by_key["nuclear_safety_regulator"]["required_capability_keys"]
    assert "radiation_monitoring" in by_key["environmental_monitoring"]["required_capability_keys"]
    assert "radiation_injury_treatment" in by_key["emergency_medical_response"]["required_capability_keys"]

    for demand in result.role_demands:
        assert "agent_id" not in demand
        assert "agent_ids" not in demand
        assert "target_agent_count" not in demand
        assert "agent_count" not in demand


def test_role_demands_keep_all_same_key_causes_but_do_not_leak_unrelated_regions():
    result = ScenarioPlanner().build(
        foundation={"artifact_id": "foundation_multi", "region_ids": ["foundation_fallback"]},
        effort_snapshot_ref=_effort(),
        user_events=[
            {
                "input_id": "weather_b",
                "name": "台风登陆",
                "description": "台风登陆天气区",
                "order": 1,
                "target_region_ids": ["region_weather"],
            },
            {
                "input_id": "release_a",
                "name": "核事故 A",
                "description": "核电站进水、断电和冷却失效后发生放射性释放",
                "order": 2,
                "target_region_ids": ["region_nuclear_a"],
            },
            {
                "input_id": "release_b",
                "name": "核事故 B",
                "description": "另一设施发生放射性释放",
                "order": 3,
                "target_region_ids": ["region_nuclear_b"],
            },
        ],
        user_policies=[],
    )
    demands = {item["demand_key"]: item for item in result.role_demands}
    regulator = demands["nuclear_safety_regulator"]
    release_event_ids = {
        node["event_id"]
        for node in result.event_mechanism_graph["nodes"]
        if node["atomic_key"] == "radioactive_release"
    }

    assert release_event_ids.issubset(set(regulator["caused_by_event_ids"]))
    assert set(regulator["jurisdiction_region_ids"]) == {"region_nuclear_a", "region_nuclear_b"}
    assert "region_weather" not in regulator["jurisdiction_region_ids"]
    assert "foundation_fallback" not in regulator["jurisdiction_region_ids"]


def test_unknown_policy_fallback_has_lower_confidence_than_known_policy_rule():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        user_events=[{"name": "洪水", "description": "洪水影响沿岸地区"}],
        user_policies=[
            {"input_id": "known", "name": "加强监测", "intent": "增加环境采样和预警"},
            {"input_id": "unknown", "name": "建立联络机制", "intent": "根据现场情况调整工作安排"},
        ],
    )
    policies = {item["source_input_id"]: item for item in result.policy_plan}

    assert policies["known"]["confidence"] == 0.76
    assert policies["unknown"]["confidence"] == 0.48
    assert policies["unknown"]["confidence"] < policies["known"]["confidence"]
    assert "低置信度" in policies["unknown"]["epistemic_status"]


def test_legacy_injected_variables_project_without_rewriting_source_shape():
    legacy = [
        {
            "variable_id": "legacy_d1",
            "type": "disaster",
            "name": "台风暴雨",
            "description": "台风带来暴雨和沿海淹没",
            "target_regions": ["region_a"],
            "start_round": 3,
        },
        {
            "variable_id": "legacy_p1",
            "type": "policy",
            "name": "应急监测",
            "description": "提高环境监测和预警频率",
            "target_regions": ["region_a"],
        },
    ]
    result = ScenarioPlanner().build_from_legacy(
        foundation=_foundation(),
        effort_snapshot_ref=_effort(),
        injected_variables=legacy,
    )

    assert result.normalized_user_events[0]["input_id"] == "legacy_d1"
    assert result.normalized_user_events[0]["target_region_ids"] == ["region_a"]
    assert result.normalized_user_policies[0]["input_id"] == "legacy_p1"
    # The source was consumed as compatibility input, not mutated into the new shape.
    assert "input_id" not in legacy[0]
    assert legacy[0]["start_round"] == 3


def test_prepare_payload_prefers_explicit_new_inputs_over_stale_legacy_variables():
    payload = {
        "effort_snapshot_id": "effort_payload_high",
        "event_inputs": [],
        "policy_inputs": [{"name": "监测措施", "intent": "加强环境监测"}],
        "injected_variables": [
            {"variable_id": "stale_legacy", "type": "disaster", "name": "不应恢复的历史灾害"}
        ],
    }
    result = ScenarioPlanner().build_from_payload(_foundation(), payload)

    assert result.normalized_user_events == []
    assert [item["name"] for item in result.normalized_user_policies] == ["监测措施"]
    assert result.effort_snapshot_ref["effort_snapshot_id"] == "effort_payload_high"


def test_planning_ids_and_content_hash_are_stable_for_same_semantic_input():
    first = _build_compound()
    second = _build_compound()

    assert first.planning_input_id == second.planning_input_id
    assert first.event_mechanism_graph["graph_id"] == second.event_mechanism_graph["graph_id"]
    assert first.content_hash == second.content_hash
    assert len(first.content_hash) == 64


def test_missing_effort_uses_explicit_fixture_assumption_instead_of_hidden_default():
    result = ScenarioPlanner().build(
        foundation=_foundation(),
        effort_snapshot_ref=None,
        user_events=[{"name": "洪水", "description": "洪水影响沿岸地区"}],
        user_policies=[],
    )

    assert result.effort_snapshot_ref["source"] == "contract_fixture"
    assert result.effort_snapshot_ref["effort_level"] == "high"
    assert any("分析投入" in item and "深入" in item for item in result.assumptions)


def test_legacy_agent_adapter_is_explicit_deep_search_transport_only():
    result = _build_compound()
    adapted = LegacyAgentPlanningAdapter().plan(result)

    assert adapted["agent_plan_source"] == LEGACY_AGENT_PLAN_SOURCE
    assert adapted["effort_profile"]["stage_budgets"]["profile_detail_level"] == 3
    assert adapted["search_mode"] == LEGACY_SEARCH_MODE
    assert adapted["simulation_architecture"] == "llm_mechanism_v1"
    assert adapted["status"] == "等待旧版代理体生成器处理"
    assert adapted["role_demands"] == result.role_demands
    assert adapted["scenario_planning_ref"]["content_hash"] == result.content_hash
    assert {item["type"] for item in adapted["injected_variables"]} == {"disaster", "policy"}
    assert any("全部传播分支" in item for item in adapted["projection_warnings"])
    assert "target_agent_count" not in adapted
