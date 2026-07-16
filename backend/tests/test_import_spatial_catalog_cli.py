"""Tests for the offline controlled spatial-catalog import command."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.spatial_catalog import SQLiteSpatialCatalog
from scripts.import_spatial_catalog import main


def _write_geojson(path: Path, *, include_invalid: bool = False) -> None:
    features = [
        {
            "type": "Feature",
            "id": "hospital-002",
            "geometry": {"type": "Point", "coordinates": [114.2, 22.6]},
            "properties": {
                "display_name": "滨海应急医院",
                "facility_class_keys": ["hospital", "emergency_hospital"],
                "source_record_id": "official-hospital-002",
            },
        },
        {
            "type": "Feature",
            "id": "shelter-001",
            "geometry": {"type": "Point", "coordinates": [114.1, 22.5]},
            "properties": {
                "display_name": "沿海应急避难场所",
                "facility_class_key": "emergency_shelter",
                "source_record_id": "official-shelter-001",
            },
        },
    ]
    if include_invalid:
        features.append(
            {
                "type": "Feature",
                "id": "invalid-003",
                "geometry": {"type": "Point", "coordinates": [999, 22.5]},
                "properties": {"display_name": "无效坐标"},
            }
        )
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )


def _args(input_path: Path, catalog_path: Path) -> list[str]:
    return [
        str(input_path),
        "--catalog",
        str(catalog_path),
        "--source-key",
        "official_facilities",
        "--provider",
        "municipal_authority",
        "--evidence-grade",
        "A",
        "--dataset-version",
        "2026-Q3",
        "--coordinate-system",
        "WGS84",
    ]


def test_cli_imports_validated_geojson_and_prints_deterministic_summary(
    tmp_path: Path,
    capsys,
):
    input_path = tmp_path / "facilities.geojson"
    catalog_path = tmp_path / "catalog.sqlite3"
    _write_geojson(input_path)

    assert main(_args(input_path, catalog_path)) == 0
    first_stdout = capsys.readouterr().out.strip()
    assert main(_args(input_path, catalog_path)) == 0
    second_stdout = capsys.readouterr().out.strip()

    assert first_stdout == second_stdout
    summary = json.loads(first_stdout)
    assert summary["mode"] == "upsert"
    assert summary["feature_count"] == 2
    assert summary["evidence_grade_counts"] == {"A": 2}
    assert summary["facility_class_counts"] == {
        "emergency_hospital": 1,
        "emergency_shelter": 1,
        "hospital": 1,
    }
    assert len(summary["content_hash"]) == 64

    with SQLiteSpatialCatalog(catalog_path) as catalog:
        features = catalog.query_bbox((114.0, 22.4, 114.3, 22.7))
    assert [item.feature_id for item in features] == ["hospital-002", "shelter-001"]
    assert all(item.provider == "municipal_authority" for item in features)


def test_cli_validates_every_feature_before_creating_target_catalog(
    tmp_path: Path,
    capsys,
):
    input_path = tmp_path / "invalid.geojson"
    catalog_path = tmp_path / "must-not-be-created.sqlite3"
    _write_geojson(input_path, include_invalid=True)

    assert main(_args(input_path, catalog_path)) == 1
    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["status"] == "error"
    assert "经纬度范围" in error["error"]
    assert captured.out == ""
    assert not catalog_path.exists()


def test_cli_dry_run_does_not_create_catalog(tmp_path: Path, capsys):
    input_path = tmp_path / "facilities.geojson"
    catalog_path = tmp_path / "dry-run.sqlite3"
    _write_geojson(input_path)

    assert main([*_args(input_path, catalog_path), "--dry-run"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["mode"] == "validate_only"
    assert summary["feature_count"] == 2
    assert not catalog_path.exists()
