#!/usr/bin/env python3
"""Validate and import a controlled GeoJSON dataset into the spatial catalog.

The command is deliberately offline.  It validates the complete
FeatureCollection in an in-memory catalog before opening the target database,
so a malformed feature cannot leave a partially imported dataset behind.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.config import Config  # noqa: E402
from app.services.spatial_catalog import (  # noqa: E402
    SPATIAL_CATALOG_CONTRACT_VERSION,
    SQLiteSpatialCatalog,
    SpatialCatalogFeature,
)


IMPORT_SUMMARY_CONTRACT_VERSION = "spatial_catalog_import.v1"
_EVIDENCE_GRADES = ("A", "B", "C", "D", "S")


def _default_catalog_path() -> Path:
    configured = str(getattr(Config, "SPATIAL_CATALOG_PATH", "") or "").strip()
    if configured:
        return Path(configured).expanduser()
    upload_folder = Path(str(getattr(Config, "UPLOAD_FOLDER", BACKEND_DIR)))
    return upload_folder / "spatial_catalog.sqlite3"


def _evidence_grade(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in _EVIDENCE_GRADES:
        raise argparse.ArgumentTypeError("must be one of A, B, C, D, or S")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and import a controlled GeoJSON FeatureCollection.",
    )
    parser.add_argument("input", type=Path, help="UTF-8 GeoJSON FeatureCollection path")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=_default_catalog_path(),
        help="SQLite catalog path (defaults to the configured spatial catalog)",
    )
    parser.add_argument("--source-key", required=True, help="Stable source dataset key")
    parser.add_argument("--provider", required=True, help="Source provider identifier")
    parser.add_argument(
        "--evidence-grade",
        required=True,
        type=_evidence_grade,
        help="Default evidence grade: A, B, C, D, or S",
    )
    parser.add_argument("--dataset-version", required=True, help="Immutable source release/version")
    parser.add_argument(
        "--coordinate-system",
        required=True,
        help="Coordinate system recorded with imported features, for example WGS84",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the summary without opening or changing the catalog",
    )
    return parser


def load_feature_collection(path: Path) -> Mapping[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"input file does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"input path is not a file: {resolved}")
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except UnicodeDecodeError as exc:
        raise ValueError("input must be UTF-8 encoded") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"input is not valid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ValueError("input must be a GeoJSON FeatureCollection object")
    return payload


def validate_features(
    feature_collection: Mapping[str, Any],
    *,
    source_key: str,
    provider: str,
    evidence_grade: str,
    dataset_version: str,
    coordinate_system: str,
) -> list[SpatialCatalogFeature]:
    # Import into memory first.  The real catalog is not opened until every
    # feature has passed geometry, provenance, metadata and hash validation.
    with SQLiteSpatialCatalog() as validation_catalog:
        return validation_catalog.import_geojson(
            feature_collection,
            source_key=source_key,
            provider=provider,
            evidence_grade=evidence_grade,
            dataset_version=dataset_version,
            coordinate_system=coordinate_system,
        )


def _count(values: Sequence[str]) -> Dict[str, int]:
    return dict(sorted(Counter(values).items()))


def build_summary(
    features: Sequence[SpatialCatalogFeature],
    *,
    input_path: Path,
    catalog_path: Path,
    dry_run: bool,
) -> Dict[str, Any]:
    ordered = sorted(features, key=lambda item: item.feature_id)
    canonical_features = json.dumps(
        [item.to_dict() for item in ordered],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    class_counts = Counter(
        class_key
        for feature in ordered
        for class_key in feature.facility_class_keys
    )
    if ordered:
        bbox = [
            min(item.bbox[0] for item in ordered),
            min(item.bbox[1] for item in ordered),
            max(item.bbox[2] for item in ordered),
            max(item.bbox[3] for item in ordered),
        ]
    else:
        bbox = None
    return {
        "bbox": bbox,
        "catalog_contract_version": SPATIAL_CATALOG_CONTRACT_VERSION,
        "catalog_path": str(catalog_path.expanduser().resolve()),
        "content_hash": hashlib.sha256(canonical_features).hexdigest(),
        "coordinate_system_counts": _count([item.coordinate_system for item in ordered]),
        "dataset_version_counts": _count([item.dataset_version for item in ordered]),
        "evidence_grade_counts": _count([item.evidence_grade for item in ordered]),
        "facility_class_counts": dict(sorted(class_counts.items())),
        "feature_count": len(ordered),
        "first_feature_id": ordered[0].feature_id if ordered else None,
        "input_path": str(input_path.expanduser().resolve()),
        "last_feature_id": ordered[-1].feature_id if ordered else None,
        "mode": "validate_only" if dry_run else "upsert",
        "provider_counts": _count([item.provider for item in ordered]),
        "source_key_counts": _count([item.source_key for item in ordered]),
        "summary_contract_version": IMPORT_SUMMARY_CONTRACT_VERSION,
    }


def run_import(args: argparse.Namespace) -> Dict[str, Any]:
    feature_collection = load_feature_collection(args.input)
    features = validate_features(
        feature_collection,
        source_key=args.source_key,
        provider=args.provider,
        evidence_grade=args.evidence_grade,
        dataset_version=args.dataset_version,
        coordinate_system=args.coordinate_system,
    )
    if not args.dry_run:
        with SQLiteSpatialCatalog(args.catalog.expanduser()) as catalog:
            catalog.upsert_many(features)
    return build_summary(
        features,
        input_path=args.input,
        catalog_path=args.catalog,
        dry_run=args.dry_run,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = run_import(args)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        error = {
            "error": str(exc),
            "status": "error",
            "summary_contract_version": IMPORT_SUMMARY_CONTRACT_VERSION,
        }
        print(json.dumps(error, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
