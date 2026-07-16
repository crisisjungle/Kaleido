"""Focused tests for the embedded spatial-catalog adapter boundary."""

from pathlib import Path

import pytest

from app.services.spatial_catalog import (
    SQLiteSpatialCatalog,
    SpatialCatalogFeature,
    SpatialCatalogPort,
    geometry_bbox,
)


def _point_feature(
    feature_id: str,
    name: str,
    coordinates: tuple[float, float],
    facility_class_keys: tuple[str, ...],
    *,
    evidence_grade: str = "C",
    dataset_version: str = "2026-07",
    tags: dict | None = None,
) -> SpatialCatalogFeature:
    geometry = {"type": "Point", "coordinates": list(coordinates)}
    return SpatialCatalogFeature(
        feature_id=feature_id,
        display_name=name,
        facility_class_keys=facility_class_keys,
        geometry=geometry,
        bbox=geometry_bbox(geometry),
        source_key="overture_places",
        provider="overture",
        source_record_id=f"source-{feature_id}",
        evidence_grade=evidence_grade,
        dataset_version=dataset_version,
        coordinate_system="WGS84",
        tags=tags or {},
        properties={"name": name, "language": "zh"},
    )


def test_bbox_query_is_deterministic_and_matches_any_requested_facility_class():
    catalog = SQLiteSpatialCatalog()
    try:
        catalog.upsert_many(
            [
                _point_feature(
                    "facility_shelter",
                    "沿海应急避难场所",
                    (114.20, 22.58),
                    ("emergency_shelter",),
                ),
                _point_feature(
                    "facility_hospital_b",
                    "滨海医院",
                    (114.12, 22.55),
                    ("hospital", "emergency_hospital"),
                ),
                _point_feature(
                    "facility_hospital_a",
                    "区域人民医院",
                    (114.10, 22.50),
                    ("hospital", "emergency_hospital"),
                ),
                _point_feature(
                    "facility_outside",
                    "范围外医院",
                    (115.10, 23.50),
                    ("hospital",),
                ),
            ]
        )

        hospitals = catalog.query_bbox(
            (114.0, 22.4, 114.3, 22.7),
            facility_class_keys=["emergency_hospital"],
        )
        all_local = catalog.query_bbox((114.0, 22.4, 114.3, 22.7))

        assert [item.feature_id for item in hospitals] == [
            "facility_hospital_a",
            "facility_hospital_b",
        ]
        assert [item.feature_id for item in all_local] == [
            "facility_hospital_a",
            "facility_hospital_b",
            "facility_shelter",
        ]
        assert catalog.query_bbox(
            (114.0, 22.4, 114.3, 22.7),
            facility_class_keys=["hospital", "emergency_shelter"],
            limit=2,
        ) == all_local[:2]
    finally:
        catalog.close()


def test_upsert_replaces_same_feature_id_without_creating_duplicates_and_persists(tmp_path: Path):
    database_path = tmp_path / "spatial-catalog.sqlite3"
    initial = _point_feature(
        "facility_monitoring",
        "辐射监测点",
        (114.01, 22.61),
        ("radiation_monitoring_station",),
        evidence_grade="C",
        dataset_version="release-1",
        tags={"status": "candidate"},
    )
    revised = _point_feature(
        "facility_monitoring",
        "大亚湾辐射监测站",
        (114.03, 22.63),
        ("radiation_monitoring_station", "environmental_monitoring_station"),
        evidence_grade="B",
        dataset_version="release-2",
        tags={"status": "cross_verified"},
    )

    with SQLiteSpatialCatalog(database_path) as catalog:
        assert catalog.upsert(initial).content_hash == initial.content_hash
        catalog.upsert(revised)
        stored = catalog.query_bbox((113.9, 22.4, 114.2, 22.8))
        assert len(stored) == 1
        assert stored[0].to_dict() == revised.to_dict()

    with SQLiteSpatialCatalog(database_path) as reopened:
        stored = reopened.query_bbox((113.9, 22.4, 114.2, 22.8))
        assert len(stored) == 1
        assert stored[0].display_name == "大亚湾辐射监测站"
        assert stored[0].dataset_version == "release-2"
        assert stored[0].evidence_grade == "B"
        assert stored[0].tags == {"status": "cross_verified"}


def test_geojson_feature_collection_import_preserves_coordinates_source_and_properties():
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "poi-nuclear-1",
                "geometry": {"type": "Point", "coordinates": [114.54, 22.60, 5.0]},
                "properties": {
                    "display_name": "沿海核电设施",
                    "facility_class_keys": ["nuclear_power_facility", "power_plant"],
                    "source_record_id": "overture-place-nuclear-1",
                    "evidence_grade": "B",
                    "tags": {"operator": "示例运营方", "critical": True},
                    "address": "广东省深圳市东部沿海",
                    "confidence": 0.93,
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [114.42, 22.62]},
                "properties": {
                    "name": "应急医疗中心",
                    "facility_class_key": "emergency_hospital",
                    "tags": {"emergency": "yes"},
                },
            },
        ],
    }

    with SQLiteSpatialCatalog() as catalog:
        first = catalog.import_geojson(
            collection,
            source_key="overture_places",
            provider="overture",
            evidence_grade="C",
            dataset_version="2026-06-17.0",
        )
        second = catalog.import_geojson(
            collection,
            source_key="overture_places",
            provider="overture",
            evidence_grade="C",
            dataset_version="2026-06-17.0",
        )

        assert [item.feature_id for item in first] == [item.feature_id for item in second]
        assert len(catalog.query_bbox((114.0, 22.0, 115.0, 23.0))) == 2

        nuclear = next(item for item in first if item.feature_id == "poi-nuclear-1")
        assert nuclear.coordinates == [114.54, 22.6, 5.0]
        assert nuclear.source_key == "overture_places"
        assert nuclear.provider == "overture"
        assert nuclear.source_record_id == "overture-place-nuclear-1"
        assert nuclear.evidence_grade == "B"
        assert nuclear.dataset_version == "2026-06-17.0"
        assert nuclear.facility_class_keys == ("nuclear_power_facility", "power_plant")
        assert nuclear.tags == {"critical": True, "operator": "示例运营方"}
        assert nuclear.properties["address"] == "广东省深圳市东部沿海"

        derived = next(item for item in first if item.feature_id != "poi-nuclear-1")
        assert derived.feature_id.startswith("spatial_")
        assert derived.source_record_id.startswith("derived_")
        assert derived.display_name == "应急医疗中心"


def test_polygon_bbox_overlap_and_geojson_export_round_trip_metadata():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [113.95, 22.45],
                [114.05, 22.45],
                [114.05, 22.55],
                [113.95, 22.55],
                [113.95, 22.45],
            ]
        ],
    }
    feature = SpatialCatalogFeature(
        feature_id="facility_port_zone",
        display_name="港区应急保障范围",
        facility_class_keys=("port", "logistics_hub"),
        geometry=geometry,
        bbox=(113.95, 22.45, 114.05, 22.55),
        source_key="official_port_directory",
        provider="transport_authority",
        source_record_id="port-zone-01",
        evidence_grade="A",
        dataset_version="2026-Q2",
        tags={"jurisdiction": "municipal"},
        properties={"capacity_band": "regional"},
    )

    with SQLiteSpatialCatalog() as catalog:
        catalog.upsert(feature)
        result = catalog.query_bbox((114.04, 22.54, 114.10, 22.60))
        exported = result[0].to_geojson_feature()

    assert result == [feature]
    assert exported["geometry"] == geometry
    assert exported["properties"]["provider"] == "transport_authority"
    assert exported["properties"]["evidence_grade"] == "A"
    assert exported["properties"]["dataset_version"] == "2026-Q2"
    assert exported["properties"]["tags"] == {"jurisdiction": "municipal"}


def test_catalog_implements_replaceable_port_and_rejects_invalid_spatial_contract():
    catalog = SQLiteSpatialCatalog()
    try:
        assert isinstance(catalog, SpatialCatalogPort)
        with pytest.raises(ValueError, match="经纬度范围"):
            catalog.query_bbox((181.0, 22.0, 182.0, 23.0))
        with pytest.raises(ValueError, match="FeatureCollection"):
            catalog.import_geojson(
                {"type": "Feature", "features": []},
                source_key="fixture",
                provider="fixture",
                evidence_grade="C",
                dataset_version="1",
            )
        with pytest.raises(ValueError, match="必须与 GeoJSON geometry 一致"):
            SpatialCatalogFeature(
                feature_id="invalid_bbox",
                display_name="错误范围",
                facility_class_keys=("hospital",),
                geometry={"type": "Point", "coordinates": [114.0, 22.0]},
                bbox=(113.0, 21.0, 113.0, 21.0),
                source_key="fixture",
                provider="fixture",
                source_record_id="invalid",
                evidence_grade="C",
                dataset_version="1",
            )
    finally:
        catalog.close()
