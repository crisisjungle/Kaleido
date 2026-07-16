"""Focused tests for controlled-catalog R3 spatial refinement execution."""

from __future__ import annotations

from app.services.mechanism_aware_spatial_refiner import MechanismAwareSpatialRefiner
from app.services.spatial_catalog import SQLiteSpatialCatalog, SpatialCatalogFeature
from app.services.spatial_evidence import FacilityQueryPlan, SpatialEvidenceRequest


def _feature(
    feature_id: str,
    name: str,
    classes,
    coordinates,
    *,
    source_key: str,
    provider: str,
    source_record_id: str,
    evidence_grade: str,
    dataset_version: str,
):
    lon, lat = coordinates
    return SpatialCatalogFeature(
        feature_id=feature_id,
        display_name=name,
        facility_class_keys=tuple(classes),
        geometry={"type": "Point", "coordinates": [lon, lat]},
        bbox=(lon, lat, lon, lat),
        source_key=source_key,
        provider=provider,
        source_record_id=source_record_id,
        evidence_grade=evidence_grade,
        dataset_version=dataset_version,
    )


def _plan(*, duplicate_hospital_request: bool = False):
    hospital = SpatialEvidenceRequest(
        request_id="request_hospital",
        label_zh="应急医疗设施",
        request_kind="facility_discovery",
        resolution_level="R3",
        priority=90,
        importance="high",
        target_region_ids=["region_daya_bay"],
        facility_class_keys=["hospital", "emergency_hospital"],
        representation_requirement="facility_required",
        minimum_evidence_grade="C",
        allowed_source_kinds=["controlled_spatial_index"],
    )
    monitoring = SpatialEvidenceRequest(
        request_id="request_monitoring",
        label_zh="辐射监测设施",
        request_kind="institution_discovery",
        resolution_level="R3",
        priority=95,
        importance="critical",
        target_region_ids=["region_daya_bay"],
        facility_class_keys=["radiation_monitoring_station"],
        representation_requirement="facility_required",
        minimum_evidence_grade="B",
        allowed_source_kinds=["authoritative", "controlled_spatial_index"],
    )
    requests = [hospital, monitoring]
    if duplicate_hospital_request:
        requests.append(SpatialEvidenceRequest(
            request_id="request_hospital_capacity",
            label_zh="医疗承载设施",
            request_kind="facility_discovery",
            resolution_level="R3",
            priority=80,
            importance="high",
            target_region_ids=["region_daya_bay"],
            facility_class_keys=["hospital"],
            representation_requirement="facility_required",
            minimum_evidence_grade="C",
            allowed_source_kinds=["controlled_spatial_index"],
        ))
    r4 = SpatialEvidenceRequest(
        request_id="request_hospital_r4",
        label_zh="医院内部承载单元",
        request_kind="internal_unit_model",
        resolution_level="R4",
        priority=75,
        importance="high",
        target_region_ids=["region_daya_bay"],
        facility_class_keys=["hospital"],
        parent_r3_request_ids=[hospital.request_id],
        representation_requirement="subunit_required",
        minimum_evidence_grade="C",
        allowed_source_kinds=["authoritative", "user_supplied", "synthetic_model"],
        r4_unit_type_keys=["emergency_department", "intensive_care_unit"],
    )
    requests.append(r4)
    return FacilityQueryPlan(
        plan_id="facility_query_plan_test",
        scenario_planning_ref={"planning_input_id": "scenario_test", "content_hash": "scenario-hash"},
        event_mechanism_graph_ref={"graph_id": "graph_test"},
        effort_snapshot_ref={"effort_snapshot_id": "effort_high", "effort_level": "high"},
        requests=requests,
        required_r3_request_ids=[
            item.request_id for item in requests if item.resolution_level == "R3"
        ],
        required_r4_request_ids=[r4.request_id],
        role_demand_refs=["demand_medical", "demand_monitoring"],
        content_hash="facility-plan-hash",
    )


class RecordingCatalog:
    catalog_key = "local_test_catalog"

    def __init__(self, delegate):
        self.delegate = delegate
        self.queries = []

    def query_bbox(self, bbox, *, facility_class_keys=None, limit=None):
        self.queries.append({
            "bbox": tuple(bbox),
            "facility_class_keys": tuple(facility_class_keys or ()),
            "limit": limit,
        })
        return self.delegate.query_bbox(
            bbox,
            facility_class_keys=facility_class_keys,
            limit=limit,
        )


def test_refiner_queries_each_r3_request_and_keeps_r4_as_explicit_gap():
    catalog = SQLiteSpatialCatalog()
    catalog.upsert_many([
        _feature(
            "hospital_1",
            "大亚湾区域医院",
            ["hospital", "emergency_hospital"],
            (114.55, 22.72),
            source_key="overture_places",
            provider="overture",
            source_record_id="place_hospital_1",
            evidence_grade="C",
            dataset_version="2026-06",
        ),
        _feature(
            "monitoring_1",
            "大亚湾辐射监测站",
            ["radiation_monitoring_station"],
            (114.58, 22.70),
            source_key="official_environment_directory",
            provider="official_environment_directory",
            source_record_id="station_1",
            evidence_grade="A",
            dataset_version="2026-07",
        ),
    ])
    recording = RecordingCatalog(catalog)

    snapshot = MechanismAwareSpatialRefiner(recording).refine(
        _plan(),
        foundation={
            "spatial_scope": {"bbox": [114.4, 22.6, 114.7, 22.85]},
            "target_catalog": [],
        },
    )

    assert len(recording.queries) == 2
    assert recording.queries[0]["facility_class_keys"] == (
        "emergency_hospital",
        "hospital",
    )
    assert recording.queries[1]["facility_class_keys"] == (
        "radiation_monitoring_station",
    )
    assert {item["feature_id"] for item in snapshot.selected_r3_features} == {
        "hospital_1",
        "monitoring_1",
    }
    assert [item["status"] for item in snapshot.provider_attempts] == [
        "completed",
        "completed",
    ]
    assert {item["source_key"] for item in snapshot.source_versions} == {
        "official_environment_directory",
        "overture_places",
    }
    r4_coverage = next(
        item for item in snapshot.request_coverage if item["request_id"] == "request_hospital_r4"
    )
    assert r4_coverage["status"] == "model_input_required"
    assert snapshot.r4_model_units == []

def test_repeated_r3_hits_are_deduplicated_and_audit_is_deterministic():
    catalog = SQLiteSpatialCatalog()
    catalog.upsert(_feature(
        "hospital_1",
        "大亚湾区域医院",
        ["hospital", "emergency_hospital"],
        (114.55, 22.72),
        source_key="overture_places",
        provider="overture",
        source_record_id="place_hospital_1",
        evidence_grade="C",
        dataset_version="2026-06",
    ))
    plan = _plan(duplicate_hospital_request=True)
    foundation = {
        "spatial_scope": {"west": 114.4, "south": 22.6, "east": 114.7, "north": 22.85},
        "target_catalog": [],
    }

    first = MechanismAwareSpatialRefiner(catalog).refine(plan, foundation=foundation)
    second = MechanismAwareSpatialRefiner(catalog).refine(plan, foundation=foundation)

    assert [item["feature_id"] for item in first.selected_r3_features] == ["hospital_1"]
    source = next(item for item in first.source_versions if item["source_key"] == "overture_places")
    assert source["feature_count"] == 1
    assert first.provider_attempts == second.provider_attempts
    assert first.source_versions == second.source_versions
    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash


def test_existing_foundation_evidence_is_evaluated_when_scope_is_unavailable():
    class MustNotQuery:
        def query_bbox(self, *_args, **_kwargs):
            raise AssertionError("缺少空间范围时不应执行无边界目录扫描")

    snapshot = MechanismAwareSpatialRefiner(MustNotQuery()).refine(
        _plan(),
        foundation={
            "target_catalog": [
                {
                    "id": "hospital_existing",
                    "name": "已确认区域医院",
                    "kind": "entity",
                    "facility_class_keys": ["hospital", "emergency_hospital"],
                    "source_kind": "authoritative",
                    "evidence_grade": "A",
                }
            ],
            "evidence_sources": [
                {
                    "source_key": "official_health_directory",
                    "provider": "official_health_directory",
                    "dataset_version": "2026-07",
                }
            ],
        },
    )

    assert all(item["status"] == "skipped" for item in snapshot.provider_attempts)
    assert all(
        item["reason_code"] == "spatial_scope_missing"
        for item in snapshot.provider_attempts
    )
    hospital_coverage = next(
        item for item in snapshot.request_coverage if item["request_id"] == "request_hospital"
    )
    assert hospital_coverage["status"] == "covered"
    assert hospital_coverage["matched_feature_ids"] == ["hospital_existing"]
    assert snapshot.r4_model_units == []
