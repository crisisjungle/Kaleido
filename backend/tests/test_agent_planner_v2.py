from app.services.effort_contract import build_effort_snapshot
from app.services.envfish_models import EnvAgentProfile, RegionNode, default_state_vector
from app.services.scenario_planning.agent_planner import AgentPlannerV2
from app.services.zep_entity_reader import EntityNode


def _entity(
    entity_id: str,
    name: str,
    *,
    category: str,
    subtype: str,
    source_kind: str = "observed",
    region_id: str = "region_south",
):
    return EntityNode(
        uuid=entity_id,
        name=name,
        labels=["Infrastructure" if category == "facility" else "Region"],
        summary=f"{name}的地图证据",
        attributes={
            "category": category,
            "subtype": subtype,
            "source_kind": source_kind,
            "spatial_level": "R3" if category == "facility" else "R2",
            "spatial_precision": "exact" if category == "facility" else "area_only",
            "region_id": region_id,
        },
    )


def _demand(
    key: str,
    label: str,
    capabilities,
    resolution: str,
    importance: str,
    mechanism_ids,
):
    return {
        "demand_id": f"demand_{key}",
        "demand_key": key,
        "label_zh": label,
        "required_capability_keys": list(capabilities),
        "jurisdiction_region_ids": ["region_south"],
        "required_resolution": resolution,
        "importance": importance,
        "caused_by_event_ids": ["event_release"],
        "caused_by_mechanism_ids": list(mechanism_ids),
        "rationale_zh": f"测试场景需要{label}。",
    }


def _mechanism_graph():
    return {
        "graph_id": "graph_agent_v2_test",
        "nodes": [
            {
                "event_id": "event_release",
                "id": "event_release",
                "atomic_key": "radioactive_release",
                "label_zh": "放射性物质释放",
                "physical_time_window": {"start_round": 0},
            },
            {
                "event_id": "event_spread",
                "id": "event_spread",
                "atomic_key": "marine_spread",
                "label_zh": "海洋传播",
                "physical_time_window": {"start_round": 1},
            },
        ],
        "edges": [
            {
                "mechanism_id": "mechanism_release_spread",
                "id": "mechanism_release_spread",
                "source_event_id": "event_release",
                "target_event_id": "event_spread",
                "source": "event_release",
                "target": "event_spread",
                "propagation_medium": "marine_current",
                "label_zh": "放射性物质经海流传播",
            }
        ],
    }


def _planning_ref():
    return {
        "planning_input_id": "planning_agent_v2_test",
        "contract_version": "scenario_planning.v1",
        "content_hash": "planning_agent_v2_hash",
    }


def _candidate(agent_id: int, name: str, subtype: str, archetype_key: str = ""):
    return EnvAgentProfile(
        agent_id=agent_id,
        username=f"legacy_{agent_id}",
        name=name,
        node_family="HumanActor",
        role_type=subtype,
        bio="旧候选档案",
        persona="旧候选档案",
        profession=name,
        primary_region="region_south",
        agent_type="human",
        agent_subtype=subtype,
        archetype_key=archetype_key,
        home_region_id="region_south",
        evidence_refs=[f"legacy:{agent_id}"],
        evidence_confidence=0.7,
        state_vector=default_state_vector("disaster_mode", "HumanActor"),
    )


def test_agent_plan_uses_role_demands_and_real_facility_anchors():
    demands = [
        _demand(
            "critical_facility_operator",
            "关键设施应急运行能力",
            ["facility_safety_operation", "emergency_shutdown"],
            "specific_facility",
            "critical",
            ["mechanism_release_spread"],
        ),
        _demand(
            "nuclear_safety_regulator",
            "核安全监管能力",
            ["nuclear_safety_regulation", "regulatory_enforcement"],
            "organization",
            "critical",
            ["mechanism_release_spread"],
        ),
        _demand(
            "environmental_monitoring",
            "环境与辐射监测能力",
            ["environmental_monitoring", "radiation_monitoring"],
            "organization",
            "critical",
            ["mechanism_release_spread"],
        ),
        _demand(
            "emergency_medical_response",
            "医疗应急响应能力",
            ["emergency_medical_response", "patient_transport"],
            "specific_facility",
            "high",
            ["mechanism_release_spread"],
        ),
        _demand(
            "healthcare_capacity_coordination",
            "医疗容量协调能力",
            ["hospital_capacity_management", "patient_triage"],
            "specific_facility",
            "high",
            ["mechanism_release_spread"],
        ),
        _demand(
            "affected_population",
            "受影响居民响应能力",
            ["public_risk_response", "evacuation_participation"],
            "population_group",
            "high",
            ["mechanism_release_spread"],
        ),
    ]
    entities = [
        _entity("entity_nuclear", "南侧沿海核电站", category="facility", subtype="nuclear_power_plant"),
        _entity("entity_hospital", "南侧人民医院", category="facility", subtype="hospital"),
        _entity("entity_monitor", "南侧环境监测站", category="facility", subtype="monitoring_station"),
        _entity("entity_government", "南侧行政区域", category="region", subtype="government"),
        _entity("entity_residential", "南侧居民生活区", category="region", subtype="residential"),
    ]
    result = AgentPlannerV2().plan(
        candidate_profiles=[
            _candidate(9, "无关普通候选", "unspecified"),
            _candidate(10, "重复普通候选", "unspecified"),
        ],
        entities=entities,
        regions=[RegionNode(region_id="region_south", name="南侧近岸区域")],
        subregions=[],
        role_demands=demands,
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_agentplanv2"
        ),
        planning_input_ref=_planning_ref(),
    )

    by_archetype = {}
    for profile in result.profiles:
        by_archetype.setdefault(profile.archetype_key, []).append(profile)

    assert result.agent_plan["contract_version"] == "agent-plan.v2"
    assert result.generation_summary["target_agent_count_used"] is False
    assert result.generation_summary["filtered_candidate_count"] >= 1
    assert result.agent_plan["unresolved_demands"] == []
    assert by_archetype["critical_facility_operator"][0].source_entity_uuid == "entity_nuclear"
    assert by_archetype["healthcare_provider"][0].source_entity_uuid == "entity_hospital"
    assert by_archetype["environmental_monitoring"][0].agent_type == "organization"
    assert by_archetype["environmental_monitoring"][0].node_family == "OrganizationActor"
    assert by_archetype["environmental_monitoring"][0].role_type == "environmental_monitoring"
    assert len(by_archetype["healthcare_provider"]) == 1
    assert set(by_archetype["healthcare_provider"][0].role_demand_refs) == {
        "demand_emergency_medical_response",
        "demand_healthcare_capacity_coordination",
    }
    assert all(profile.capability_keys for profile in result.profiles)
    assert all(profile.role_demand_refs for profile in result.profiles)
    assert all(profile.resource_uncertainty for profile in result.profiles)
    assert all("risk_object_ids" not in profile.to_dict() for profile in result.profiles)
    assert all(edge.mechanism_edge_ids for edge in result.relationships)
    assert all(edge.origin == "role_demand_contract" for edge in result.relationships)
    assert result.validated_relation_graph["edges"]


def test_specific_hospital_demand_is_unresolved_without_hospital_evidence():
    result = AgentPlannerV2().plan(
        candidate_profiles=[_candidate(1, "社区综合服务主体", "community_committee")],
        entities=[
            _entity("entity_government", "南侧行政区域", category="region", subtype="government")
        ],
        regions=[RegionNode(region_id="region_south", name="南侧近岸区域")],
        subregions=[],
        role_demands=[
            _demand(
                "emergency_medical_response",
                "医疗应急响应能力",
                ["emergency_medical_response", "patient_transport"],
                "specific_facility",
                "critical",
                ["mechanism_release_spread"],
            )
        ],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_missinghospital"
        ),
        planning_input_ref=_planning_ref(),
    )

    unresolved = [
        item
        for item in result.agent_plan["unresolved_demands"]
        if item["role_key"] == "emergency_medical_response"
    ]
    assert unresolved
    assert unresolved[0]["reason_code"] == "missing_required_spatial_evidence"
    assert all(profile.archetype_key != "healthcare_provider" for profile in result.profiles)


def test_entity_region_references_are_resolved_before_agent_placement():
    demand = _demand(
        "critical_facility_operator",
        "关键设施应急运行能力",
        ["facility_safety_operation", "emergency_shutdown"],
        "specific_facility",
        "critical",
        ["mechanism_release_spread"],
    )
    demand["jurisdiction_region_ids"] = ["entity_nuclear"]
    demand["affected_region_ids"] = ["entity_nuclear"]
    result = AgentPlannerV2().plan(
        candidate_profiles=[],
        entities=[
            _entity(
                "entity_nuclear",
                "南侧沿海核电站",
                category="facility",
                subtype="nuclear_power_plant",
            )
        ],
        regions=[RegionNode(region_id="region_south", name="南侧近岸区域")],
        subregions=[],
        role_demands=[demand],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_regionresolve"
        ),
        planning_input_ref=_planning_ref(),
    )

    assert result.role_demands[0]["jurisdiction_region_ids"] == ["region_south"]
    assert result.role_demands[0]["unresolved_region_refs"] == []
    assert result.placement_plan["placements"][0]["target_region_id"] == "region_south"
    assert result.profiles[0].primary_region == "region_south"
    assert result.profiles[0].home_region_id == "region_south"


def test_source_feature_name_maps_to_unique_formal_region_instead_of_first_region():
    demand = _demand(
        "environmental_monitoring",
        "环境与辐射监测能力",
        ["environmental_monitoring", "radiation_monitoring"],
        "organization",
        "critical",
        ["mechanism_release_spread"],
    )
    demand["jurisdiction_region_ids"] = ["feature_source_shenzhen_bay"]
    result = AgentPlannerV2().plan(
        candidate_profiles=[],
        entities=[
            _entity(
                "feature_source_shenzhen_bay",
                "深圳湾",
                category="facility",
                subtype="monitoring_station",
                region_id="source_feature_region",
            )
        ],
        regions=[
            RegionNode(region_id="region_lingding", name="伶仃洋水域"),
            RegionNode(region_id="region_shenzhen_bay", name="深圳湾湿地"),
        ],
        subregions=[],
        role_demands=[demand],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_unique_region_name"
        ),
        planning_input_ref=_planning_ref(),
    )

    normalized = next(
        item for item in result.role_demands if item["role_key"] == "environmental_monitoring"
    )
    placement = next(
        item for item in result.placement_plan["placements"]
        if item["role_key"] == "environmental_monitoring"
    )
    assert normalized["jurisdiction_region_ids"] == ["region_shenzhen_bay"]
    assert placement["target_region_id"] == "region_shenzhen_bay"
    assert result.generation_summary["resolved_spatial_anchor_count"] == 1


def test_compound_policy_builds_distinct_region_bounded_execution_agents():
    region_ref = "feature_relation_20044132"
    demands = [
        {
            **_demand(
                "education_emergency_execution",
                "教育系统停课与学生安全协调能力",
                [
                    "education_emergency_management",
                    "school_closure_execution",
                    "student_safety_communication",
                ],
                "organization",
                "high",
                ["mechanism_release_spread"],
            ),
            "jurisdiction_region_ids": [region_ref],
        },
        {
            **_demand(
                "workplace_shutdown_execution",
                "工作场所停工与连续性协调能力",
                [
                    "workplace_safety_enforcement",
                    "business_continuity_coordination",
                    "labor_communication",
                ],
                "organization",
                "high",
                ["mechanism_release_spread"],
            ),
            "jurisdiction_region_ids": [region_ref],
        },
    ]
    result = AgentPlannerV2().plan(
        candidate_profiles=[],
        entities=[
            _entity(
                region_ref,
                "香港 Hong Kong",
                category="region",
                subtype="administrative_area",
                region_id="source_feature_region",
            )
        ],
        regions=[
            RegionNode(region_id="黄大仙区", name="黄大仙区"),
            RegionNode(region_id="九龙塘", name="九龙塘"),
        ],
        subregions=[],
        role_demands=demands,
        mechanism_graph=_mechanism_graph(),
        policy_plan=[
            {
                "policy_id": "policy_school_work",
                "label_zh": "停工停学",
                "effect_primitives": ["school_closure", "workplace_shutdown"],
                "semantic_action_primitives": ["school_closure", "workplace_shutdown"],
                "target_region_ids": [region_ref],
                "executor_capability_keys": [
                    "education_emergency_management",
                    "school_closure_execution",
                    "student_safety_communication",
                    "workplace_safety_enforcement",
                    "business_continuity_coordination",
                    "labor_communication",
                ],
            }
        ],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_compound_policy_agents"
        ),
        planning_input_ref={
            **_planning_ref(),
            "foundation_ref": {
                "location": "香港",
                "region_ids": [region_ref],
            },
        },
    )

    profiles = {item.archetype_key: item for item in result.profiles}
    assert set(profiles) >= {"education_authority", "workplace_authority"}
    assert profiles["education_authority"].agent_id != profiles["workplace_authority"].agent_id
    assert profiles["education_authority"].primary_region == "黄大仙区"
    assert profiles["workplace_authority"].primary_region == "黄大仙区"
    assert profiles["education_authority"].is_aggregate is True
    assert profiles["workplace_authority"].is_aggregate is True
    assert result.placement_plan["unresolved_demands"] == []
    assert result.policy_execution_plan["summary"]["bound_count"] == 1


def test_unresolved_entity_scope_is_audited_instead_of_assigned_to_first_region():
    demand = _demand(
        "emergency_medical_response",
        "医疗应急响应能力",
        ["emergency_medical_response", "patient_transport"],
        "specific_facility",
        "critical",
        ["mechanism_release_spread"],
    )
    demand["jurisdiction_region_ids"] = ["entity_unmapped_hospital"]
    result = AgentPlannerV2().plan(
        candidate_profiles=[],
        entities=[
            _entity(
                "entity_unmapped_hospital",
                "跨区域复合医疗节点",
                category="facility",
                subtype="hospital",
                region_id="source_feature_unknown",
            )
        ],
        regions=[
            RegionNode(region_id="region_first", name="第一区域"),
            RegionNode(region_id="region_second", name="第二区域"),
        ],
        subregions=[],
        role_demands=[demand],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_unresolved_region"
        ),
        planning_input_ref=_planning_ref(),
    )

    normalized = next(
        item for item in result.role_demands if item["role_key"] == "emergency_medical_response"
    )
    unresolved = next(
        item for item in result.agent_plan["unresolved_demands"]
        if item["role_key"] == "emergency_medical_response"
    )
    assert normalized["jurisdiction_region_ids"] == []
    assert normalized["unresolved_region_refs"] == ["entity_unmapped_hospital"]
    assert unresolved["reason_code"] == "unresolved_spatial_scope"
    assert all(profile.archetype_key != "healthcare_provider" for profile in result.profiles)
    assert result.generation_summary["unresolved_spatial_anchor_count"] == 1


def test_agent_plan_is_deterministic_and_does_not_pad_to_effort_limit():
    kwargs = dict(
        candidate_profiles=[
            _candidate(index, f"普通候选{index}", "unspecified")
            for index in range(12)
        ],
        entities=[
            _entity("entity_residential", "南侧居民生活区", category="region", subtype="residential")
        ],
        regions=[RegionNode(region_id="region_south", name="南侧近岸区域")],
        subregions=[],
        role_demands=[
            _demand(
                "affected_population",
                "受影响居民响应能力",
                ["public_risk_response", "evacuation_participation"],
                "population_group",
                "high",
                ["mechanism_release_spread"],
            )
        ],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "light", effort_snapshot_id="effort_nopadding"
        ),
        planning_input_ref=_planning_ref(),
    )

    first = AgentPlannerV2().plan(**kwargs)
    second = AgentPlannerV2().plan(**kwargs)

    assert len(first.profiles) < 20
    assert first.agent_plan["content_hash"] == second.agent_plan["content_hash"]
    assert [item.to_dict() for item in first.profiles] == [
        item.to_dict() for item in second.profiles
    ]


def test_ecological_receptor_uses_group_representation_even_with_entity_anchor():
    result = AgentPlannerV2().plan(
        candidate_profiles=[],
        entities=[
            _entity(
                "entity_habitat",
                "南侧滨海湿地物种群",
                category="region",
                subtype="habitat_species",
            )
        ],
        regions=[RegionNode(region_id="region_south", name="南侧近岸区域")],
        subregions=[],
        role_demands=[
            _demand(
                "ecological_receptor",
                "生态受体响应能力",
                ["ecological_response", "habitat_stress_signal"],
                "population_group",
                "high",
                ["mechanism_release_spread"],
            )
        ],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_ecological_representation"
        ),
        planning_input_ref=_planning_ref(),
    )

    receptor = next(
        profile for profile in result.profiles if profile.archetype_key == "ecological_receptor"
    )
    assert receptor.representation_level == "group_representative"
    assert receptor.is_aggregate is True


def test_agent_plan_binds_policy_to_capable_authorized_resourced_agent():
    result = AgentPlannerV2().plan(
        candidate_profiles=[
            _candidate(
                1,
                "南侧应急与补偿执行主体",
                "emergency_office",
                "local_government",
            )
        ],
        entities=[
            _entity(
                "entity_government",
                "南侧应急与补偿执行主体",
                category="region",
                subtype="government",
            )
        ],
        regions=[RegionNode(region_id="region_south", name="南侧近岸区域")],
        subregions=[],
        role_demands=[],
        mechanism_graph=_mechanism_graph(),
        policy_plan=[
            {
                "policy_id": "policy_compensation",
                "label_zh": "受影响群体生计补偿",
                "executor_capability_keys": [
                    "compensation_administration",
                    "fiscal_resource_allocation",
                ],
                "effect_primitives": [
                    "economic_compensation",
                    "livelihood_stabilization",
                ],
                "target_region_ids": ["entity_government"],
                "start_round": 2,
                "duration_rounds": 3,
            }
        ],
        effort_snapshot=build_effort_snapshot(
            "high", effort_snapshot_id="effort_policybinding"
        ),
        planning_input_ref=_planning_ref(),
    )

    binding = result.policy_execution_plan["policy_bindings"][0]
    assert binding["binding_status"] == "bound"
    assert binding["target_region_ids"] == ["region_south"]
    assert binding["unresolved_target_region_refs"] == []
    assert binding["executor_agent_ids"]
    executor = next(
        item for item in result.profiles if item.agent_id in binding["executor_agent_ids"]
    )
    assert executor.agent_type == "governance"
    assert executor.node_family == "GovernmentActor"
    assert executor.role_type == "policy_execution"
    assert "administer_compensation" in executor.permission_keys
    assert executor.resource_budget["fiscal"] > 0
    assert (
        result.agent_plan["policy_execution_plan_ref"]["artifact_id"]
        == result.policy_execution_plan["policy_execution_plan_id"]
    )
