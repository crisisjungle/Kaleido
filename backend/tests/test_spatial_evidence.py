"""Focused tests for mechanism-aware R3/R4 spatial evidence planning."""

import json

import pytest

from app.services.scenario_planner import ScenarioPlanner
from app.services.spatial_evidence import (
    FacilityQueryPlan,
    R4ModelUnit,
    SpatialEvidenceRequest,
    SpatialRefinementSnapshot,
    build_spatial_refinement_snapshot,
    compile_facility_query_plan,
    normalize_spatial_catalog_candidate,
)


def _scenario():
    return ScenarioPlanner().build(
        foundation={
            "artifact_id": "foundation_daya_bay",
            "contract_version": "foundation.v1",
            "content_hash": "foundation-hash",
            "region_ids": ["region_daya_bay", "region_shenzhen_east"],
            "location": "大亚湾核电站与深圳东部沿海",
        },
        effort_snapshot_ref={
            "effort_snapshot_id": "effort_high_locked",
            "effort_level": "high",
            "profile_version": "effort.v1",
            "content_hash": "effort-hash",
        },
        user_events=[
            {
                "input_id": "event_typhoon_release",
                "name": "台风引发沿海核事故",
                "description": (
                    "台风导致沿海核电站进水、外部电源和冷却失效，随后发生放射性释放，"
                    "并通过海洋和大气传播，造成人群暴露、医疗压力与交通压力"
                ),
                "order": 1,
                "target_region_ids": ["region_daya_bay"],
                "target_entity_ids": ["facility_daya_bay_nuclear"],
            }
        ],
        user_policies=[
            {
                "input_id": "policy_monitoring",
                "name": "辐射监测与疏散",
                "intent": "加强环境监测并组织受影响居民疏散",
            },
            {
                "input_id": "policy_fisheries",
                "name": "渔业限制与补偿",
                "intent": "暂停近海捕捞并补偿受影响渔民",
            },
        ],
    )


def _assert_contract_has_no_agent_placement_fields(value):
    forbidden = {"agent_id", "agent_ids", "target_agent_count", "agent_count"}
    if isinstance(value, dict):
        assert not forbidden.intersection(value)
        for nested in value.values():
            _assert_contract_has_no_agent_placement_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_contract_has_no_agent_placement_fields(nested)


def test_compiler_prioritizes_explicit_and_critical_r3_evidence_before_r4_models():
    plan = compile_facility_query_plan(_scenario())
    requests = plan.requests

    assert requests
    assert requests[0].request_kind == "explicit_target_facility"
    assert requests[0].resolution_level == "R3"
    assert requests[0].priority == 100
    assert requests[0].target_entity_ids == ["facility_daya_bay_nuclear"]
    assert "nuclear_power_facility" in requests[0].facility_class_keys

    demand_requests = {
        demand_id: request
        for request in requests
        for demand_id in request.caused_by_role_demand_ids
        if request.resolution_level == "R3"
    }
    demands = {item["demand_key"]: item for item in _scenario().role_demands}
    critical_operator = demand_requests[demands["critical_facility_operator"]["demand_id"]]
    monitoring = demand_requests[demands["environmental_monitoring"]["demand_id"]]
    medical = demand_requests[demands["emergency_medical_response"]["demand_id"]]

    assert critical_operator.minimum_evidence_grade == "B"
    assert "nuclear_power_facility" in critical_operator.facility_class_keys
    assert "radiation_monitoring_station" in monitoring.facility_class_keys
    assert "emergency_hospital" in medical.facility_class_keys
    assert plan.required_r3_request_ids
    assert plan.required_r4_request_ids
    assert all(request.resolution_level == "R3" for request in requests[: requests.index(next(
        item for item in requests if item.resolution_level == "R4"
    ))])


def test_r4_requests_are_parent_bounded_and_explicit_about_permitted_source_kinds():
    plan = compile_facility_query_plan(_scenario())
    r4_requests = [item for item in plan.requests if item.resolution_level == "R4"]

    assert r4_requests
    assert any("intensive_care_unit" in item.r4_unit_type_keys for item in r4_requests)
    assert any("cooling_system_unit" in item.r4_unit_type_keys for item in r4_requests)
    assert any("vulnerable_population_segment" in item.r4_unit_type_keys for item in r4_requests)
    for request in r4_requests:
        assert request.parent_r3_request_ids
        assert set(request.allowed_source_kinds) == {
            "authoritative",
            "user_supplied",
            "synthetic_model",
        }
        assert set(request.parent_r3_request_ids).issubset(plan.required_r3_request_ids)


def test_plan_is_deterministic_serializable_and_contains_no_agent_placement_contract():
    first = compile_facility_query_plan(_scenario())
    second = compile_facility_query_plan(_scenario())
    serialized = first.to_dict()
    restored = FacilityQueryPlan.from_dict(json.loads(json.dumps(serialized, ensure_ascii=False)))

    assert first.plan_id == second.plan_id
    assert first.content_hash == second.content_hash
    assert restored.to_dict() == serialized
    assert restored.scenario_planning_ref["planning_input_id"] == _scenario().planning_input_id
    assert restored.effort_snapshot_ref["effort_snapshot_id"] == "effort_high_locked"
    _assert_contract_has_no_agent_placement_fields(serialized)


def test_standalone_graph_and_role_demand_compile_without_importing_planner_contract_type():
    scenario = _scenario()
    plan = compile_facility_query_plan(
        event_mechanism_graph=scenario.event_mechanism_graph,
        role_demands=scenario.role_demands,
        foundation_ref=scenario.foundation_ref,
        effort_snapshot_ref=scenario.effort_snapshot_ref,
        scenario_planning_ref={
            "planning_input_id": scenario.planning_input_id,
            "contract_version": scenario.contract_version,
            "content_hash": scenario.content_hash,
        },
    )

    assert plan.event_mechanism_graph_ref["graph_id"] == scenario.event_mechanism_graph["graph_id"]
    assert set(plan.role_demand_refs) == {item["demand_id"] for item in scenario.role_demands}


def test_r4_model_unit_requires_parent_and_truthful_source_kind():
    with pytest.raises(ValueError, match="必须绑定父级"):
        R4ModelUnit(
            unit_id="r4_no_parent",
            parent_r3_feature_id="",
            label_zh="急诊容量",
            unit_type_key="emergency_department",
            source_kind="synthetic_model",
        )
    with pytest.raises(ValueError, match="必须明确标记"):
        R4ModelUnit(
            unit_id="r4_bad_source",
            parent_r3_feature_id="hospital_1",
            label_zh="急诊容量",
            unit_type_key="emergency_department",
            source_kind="inferred",  # type: ignore[arg-type]
        )

    unit = R4ModelUnit(
        unit_id="r4_hospital_icu",
        parent_r3_feature_id="hospital_1",
        label_zh="重症监护容量模型",
        unit_type_key="intensive_care_unit",
        source_kind="synthetic_model",
        capability_keys=["critical_care"],
        assumptions=["根据同等级医院容量区间建立，不表示实时床位数据。"],
        confidence=0.52,
    )
    restored = R4ModelUnit.from_dict(unit.to_dict())

    assert restored.source_kind == "synthetic_model"
    assert restored.parent_r3_feature_id == "hospital_1"


def test_spatial_refinement_snapshot_round_trip_keeps_r4_provenance():
    plan = compile_facility_query_plan(_scenario())
    unit = R4ModelUnit(
        unit_id="r4_icu_1",
        parent_r3_feature_id="hospital_1",
        label_zh="医院重症监护单元",
        unit_type_key="intensive_care_unit",
        source_kind="user_supplied",
        evidence_refs=[{"artifact_id": "hospital_capacity_upload"}],
        confidence=0.94,
    )
    snapshot = SpatialRefinementSnapshot(
        snapshot_id="spatial_refinement_demo",
        facility_query_plan_ref={"plan_id": plan.plan_id, "content_hash": plan.content_hash},
        selected_r3_features=[{"feature_id": "hospital_1", "label_zh": "区域应急医院"}],
        r4_model_units=[unit],
        request_coverage=[{"request_id": plan.required_r3_request_ids[0], "status": "covered"}],
        source_versions=[{"source_key": "user_upload", "version": "upload-1"}],
    )
    restored = SpatialRefinementSnapshot.from_dict(snapshot.to_dict())

    assert restored.to_dict() == snapshot.to_dict()
    assert restored.r4_model_units[0].source_kind == "user_supplied"


def test_r4_request_rejects_unbounded_or_ambiguous_source_contract():
    with pytest.raises(ValueError, match="必须明确限定"):
        SpatialEvidenceRequest(
            request_id="r4_invalid",
            label_zh="未绑定的内部单元",
            request_kind="internal_unit_model",
            resolution_level="R4",
            priority=80,
            importance="high",
            parent_r3_request_ids=["r3_parent"],
            allowed_source_kinds=["inferred"],
        )


def test_current_catalog_coverage_does_not_treat_weak_candidate_as_grounded():
    plan = compile_facility_query_plan(_scenario())
    snapshot = build_spatial_refinement_snapshot(
        plan,
        target_catalog=[
            {
                "id": "facility_daya_bay_nuclear",
                "name": "大亚湾核电基地",
                "kind": "entity",
                "subtype": "power_plant",
                "source_kind": "observed",
                "provider": "osm_overpass",
                "tags": {"plant:source": "nuclear"},
            },
            {
                "id": "hospital_public",
                "name": "区域医院",
                "kind": "entity",
                "subtype": "hospital",
                "source_kind": "observed",
                "provider": "osm_overpass",
            },
        ],
    )

    explicit_request = next(
        item for item in plan.requests if item.request_kind == "explicit_target_facility"
    )
    explicit_coverage = next(
        item for item in snapshot.request_coverage if item["request_id"] == explicit_request.request_id
    )
    assert explicit_request.minimum_evidence_grade == "B"
    assert explicit_coverage["status"] == "insufficient_evidence"
    assert explicit_coverage["candidate_feature_ids"] == ["facility_daya_bay_nuclear"]
    assert any(
        item["request_id"] == explicit_request.request_id and item["blocking"] is True
        for item in snapshot.evidence_gaps
    )


def test_authoritative_r3_evidence_covers_parent_but_r4_stays_explicitly_unresolved():
    plan = compile_facility_query_plan(_scenario())
    snapshot = build_spatial_refinement_snapshot(
        plan,
        target_catalog=[
            {
                "id": "facility_daya_bay_nuclear",
                "name": "大亚湾核电基地",
                "kind": "entity",
                "subtype": "power_plant",
                "source_kind": "authoritative",
                "provider": "official_energy_directory",
                "tags": {"plant:source": "nuclear"},
            }
        ],
        source_versions=[{"source_key": "official_energy_directory", "version": "2026-07"}],
    )

    explicit_request = next(
        item for item in plan.requests if item.request_kind == "explicit_target_facility"
    )
    explicit_coverage = next(
        item for item in snapshot.request_coverage if item["request_id"] == explicit_request.request_id
    )
    assert explicit_coverage["status"] == "covered"
    assert explicit_coverage["matched_feature_ids"] == ["facility_daya_bay_nuclear"]
    assert snapshot.selected_r3_features[0]["evidence_grade"] == "A"
    assert any(
        item["resolution_level"] == "R4" and item["status"] in {"model_input_required", "parent_r3_missing"}
        for item in snapshot.request_coverage
    )
    assert snapshot.r4_model_units == []


def test_catalog_candidate_normalization_keeps_single_class_and_maps_shelters():
    explicit = normalize_spatial_catalog_candidate(
        {
            "id": "facility_monitoring",
            "facility_class_keys": "radiation_monitoring_station",
            "source_kind": "observed",
            "provider": "osm_overpass",
        }
    )
    shelter = normalize_spatial_catalog_candidate(
        {
            "id": "facility_shelter",
            "subtype": "shelter",
            "source_kind": "authoritative",
        }
    )

    assert explicit["facility_class_keys"] == ["radiation_monitoring_station"]
    assert explicit["evidence_grade"] == "C"
    assert "evacuation_shelter" in shelter["facility_class_keys"]
    assert shelter["evidence_grade"] == "A"
