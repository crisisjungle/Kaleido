"""Execute deterministic, mechanism-aware R3 catalog refinement.

The facility-query compiler in :mod:`spatial_evidence` decides *what* real
facilities a Step 2 scenario needs.  This module is the narrow execution
boundary that asks a controlled :class:`SpatialCatalogPort` for those R3
facilities and then evaluates the expanded catalog against the existing
evidence contract.

It deliberately does not know about map collection, HTTP providers, Agents or
simulation API state.  It also never creates R4 units: facility-internal facts
must continue to come from authoritative/user data or a separate, explicitly
labelled modelling step.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .spatial_catalog import SpatialCatalogPort
from .spatial_evidence import (
    FacilityQueryPlan,
    SpatialRefinementSnapshot,
    build_spatial_refinement_snapshot,
)


DEFAULT_CATALOG_QUERY_LIMIT = 200
_GRADE_RANK = {"S": 0, "D": 1, "C": 2, "B": 3, "A": 4}


class SpatialRefinementExecutionError(ValueError):
    """Raised when the refiner itself is configured with an invalid contract."""


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return dict(result)
    return {}


def _unique_strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _coerce_bbox(value: Any) -> Optional[Tuple[float, float, float, float]]:
    if isinstance(value, Mapping):
        nested = value.get("bbox") or value.get("bounds")
        if nested is not None and nested is not value:
            parsed = _coerce_bbox(nested)
            if parsed is not None:
                return parsed
        aliases = (
            ("min_lon", "min_lat", "max_lon", "max_lat"),
            ("west", "south", "east", "north"),
            ("left", "bottom", "right", "top"),
        )
        for keys in aliases:
            if all(value.get(key) is not None for key in keys):
                value = [value[key] for key in keys]
                break
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 4:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(value[index]) for index in range(4))
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(item) for item in (min_lon, min_lat, max_lon, max_lat)):
            return None
        if min_lon > max_lon:
            min_lon, max_lon = max_lon, min_lon
        if min_lat > max_lat:
            min_lat, max_lat = max_lat, min_lat
        if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
            return None
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            return None
        return (min_lon, min_lat, max_lon, max_lat)
    return None


def _point_from_feature(feature: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
    geometry = feature.get("geometry")
    if isinstance(geometry, Mapping) and _text(geometry.get("type")).lower() == "point":
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, Sequence) and not isinstance(coordinates, (str, bytes)):
            if len(coordinates) >= 2:
                try:
                    return float(coordinates[0]), float(coordinates[1])
                except (TypeError, ValueError):
                    pass
    try:
        lon = float(feature.get("lon"))
        lat = float(feature.get("lat"))
    except (TypeError, ValueError):
        return None
    if math.isfinite(lon) and math.isfinite(lat):
        return lon, lat
    return None


def _bbox_from_catalog(features: Sequence[Mapping[str, Any]]) -> Optional[Tuple[float, float, float, float]]:
    boxes: List[Tuple[float, float, float, float]] = []
    for feature in features:
        parsed = _coerce_bbox(feature.get("bbox"))
        if parsed is not None:
            boxes.append(parsed)
            continue
        point = _point_from_feature(feature)
        if point is not None:
            boxes.append((point[0], point[1], point[0], point[1]))
    if not boxes:
        return None
    min_lon = min(item[0] for item in boxes)
    min_lat = min(item[1] for item in boxes)
    max_lon = max(item[2] for item in boxes)
    max_lat = max(item[3] for item in boxes)
    # A point-only Step 1 catalog still needs a non-zero local search window.
    if min_lon == max_lon:
        min_lon -= 0.01
        max_lon += 0.01
    if min_lat == max_lat:
        min_lat -= 0.01
        max_lat += 0.01
    return (min_lon, min_lat, max_lon, max_lat)


def _bbox_from_center(scope: Mapping[str, Any]) -> Optional[Tuple[float, float, float, float]]:
    center = scope.get("center")
    lon: Any = scope.get("center_lon", scope.get("lon"))
    lat: Any = scope.get("center_lat", scope.get("lat"))
    if isinstance(center, Mapping):
        lon = center.get("lon", center.get("longitude", lon))
        lat = center.get("lat", center.get("latitude", lat))
    elif isinstance(center, Sequence) and not isinstance(center, (str, bytes)) and len(center) >= 2:
        lon, lat = center[0], center[1]
    try:
        lon_value = float(lon)
        lat_value = float(lat)
        radius_m = max(1.0, float(scope.get("radius_m") or scope.get("radius") or 3000))
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon_value <= 180 and -90 <= lat_value <= 90):
        return None
    lat_delta = radius_m / 111_320.0
    lon_scale = max(0.05, math.cos(math.radians(lat_value)))
    lon_delta = radius_m / (111_320.0 * lon_scale)
    return (
        max(-180.0, lon_value - lon_delta),
        max(-90.0, lat_value - lat_delta),
        min(180.0, lon_value + lon_delta),
        min(90.0, lat_value + lat_delta),
    )


def _spatial_bbox(
    foundation: Mapping[str, Any],
    target_catalog: Sequence[Mapping[str, Any]],
) -> Optional[Tuple[float, float, float, float]]:
    scope = foundation.get("spatial_scope")
    if isinstance(scope, Mapping):
        parsed = _coerce_bbox(scope)
        if parsed is not None:
            return parsed
        parsed = _bbox_from_center(scope)
        if parsed is not None:
            return parsed
    else:
        parsed = _coerce_bbox(scope)
        if parsed is not None:
            return parsed
    for key in ("bbox", "bounds"):
        parsed = _coerce_bbox(foundation.get(key))
        if parsed is not None:
            return parsed
    return _bbox_from_catalog(target_catalog)


def _normalize_feature(raw: Any, *, origin: str) -> Optional[Dict[str, Any]]:
    feature = _mapping(raw)
    feature_id = _text(feature.get("feature_id") or feature.get("id"))
    if not feature_id:
        return None
    feature["feature_id"] = feature_id
    feature.setdefault("id", feature_id)
    label = _text(feature.get("display_name") or feature.get("label_zh") or feature.get("name"))
    if label:
        feature.setdefault("display_name", label)
        feature.setdefault("label_zh", label)
        feature.setdefault("name", label)
    classes = _unique_strings(feature.get("facility_class_keys") or [])
    feature["facility_class_keys"] = sorted(classes)
    grade = _text(feature.get("evidence_grade")).upper()
    if grade in _GRADE_RANK:
        feature["evidence_grade"] = grade
    feature["_refinement_origin"] = origin
    return feature


def _feature_identity(feature: Mapping[str, Any]) -> str:
    # ``feature_id`` is the catalog's canonical identity.  Provider record IDs
    # remain provenance, but using them as the merge key would allow the same
    # canonical feature to appear twice when Step 1 and the controlled catalog
    # carry different amounts of source metadata.
    return f"feature:{_text(feature.get('feature_id') or feature.get('id'))}"


def _feature_rank(feature: Mapping[str, Any], protected_ids: set[str]) -> Tuple[Any, ...]:
    feature_id = _text(feature.get("feature_id") or feature.get("id"))
    grade = _text(feature.get("evidence_grade")).upper()
    completeness = sum(
        1
        for key in (
            "display_name", "geometry", "bbox", "facility_class_keys", "source_key",
            "provider", "source_record_id", "dataset_version", "tags", "properties",
        )
        if feature.get(key) not in (None, "", [], {})
    )
    return (
        1 if feature_id in protected_ids else 0,
        _GRADE_RANK.get(grade, -1),
        completeness,
        1 if feature.get("_refinement_origin") == "foundation" else 0,
        feature_id,
    )


def _merge_feature_group(
    group: Sequence[Mapping[str, Any]],
    *,
    protected_ids: set[str],
) -> Dict[str, Any]:
    ordered = sorted((dict(item) for item in group), key=lambda item: _canonical_json(item))
    primary = max(ordered, key=lambda item: _feature_rank(item, protected_ids))
    merged: Dict[str, Any] = {}
    # Overlay in rank order so the strongest/protected record owns scalar
    # fields while weaker records may still fill missing values.
    for item in sorted(ordered, key=lambda value: _feature_rank(value, protected_ids)):
        for key, value in item.items():
            if value not in (None, "", [], {}):
                merged[key] = value
    canonical_id = _text(primary.get("feature_id") or primary.get("id"))
    merged["feature_id"] = canonical_id
    merged["id"] = canonical_id
    merged["facility_class_keys"] = sorted(_unique_strings(
        class_key
        for item in ordered
        for class_key in (item.get("facility_class_keys") or [])
    ))
    aliases = _unique_strings(
        [
            *(alias for item in ordered for alias in (item.get("aliases") or [])),
            *(
                item.get("feature_id") or item.get("id")
                for item in ordered
                if _text(item.get("feature_id") or item.get("id")) != canonical_id
            ),
        ]
    )
    if aliases:
        merged["aliases"] = sorted(aliases)
    source_records = [
        {
            key: item.get(key)
            for key in ("source_key", "provider", "source_record_id", "dataset_version", "content_hash")
            if item.get(key) not in (None, "")
        }
        for item in ordered
    ]
    source_records = [item for item in source_records if item]
    if source_records:
        merged["source_records"] = sorted(
            { _canonical_json(item): item for item in source_records }.values(),
            key=_canonical_json,
        )
    merged.pop("_refinement_origin", None)
    return merged


def _merge_catalog_features(
    features: Sequence[Any],
    *,
    protected_ids: set[str],
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for raw in features:
        origin = "foundation" if isinstance(raw, Mapping) and raw.get("_refinement_origin") == "foundation" else "catalog"
        normalized = _normalize_feature(raw, origin=origin)
        if normalized is None:
            continue
        groups.setdefault(_feature_identity(normalized), []).append(normalized)
    merged = [
        _merge_feature_group(group, protected_ids=protected_ids)
        for _identity, group in sorted(groups.items())
    ]
    return sorted(merged, key=lambda item: _text(item.get("feature_id")))


def _catalog_key(catalog: SpatialCatalogPort) -> str:
    for attribute in ("catalog_key", "provider_key", "source_key"):
        value = _text(getattr(catalog, attribute, ""))
        if value:
            return value
    return "controlled_spatial_catalog"


def _attempt_id(payload: Mapping[str, Any]) -> str:
    return f"catalog_attempt_{_stable_hash(payload)[:16]}"


def _source_versions(
    foundation: Mapping[str, Any],
    features: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str, str], List[Mapping[str, Any]]] = {}
    for feature in features:
        source_key = _text(feature.get("source_key") or feature.get("provider"))
        provider = _text(feature.get("provider") or source_key)
        version = _text(feature.get("dataset_version") or feature.get("version"))
        coordinate_system = _text(feature.get("coordinate_system")) or "WGS84"
        if not source_key and not provider:
            continue
        groups.setdefault((source_key or provider, provider or source_key, version or "unversioned", coordinate_system), []).append(feature)

    versions: List[Dict[str, Any]] = []
    for key, items in sorted(groups.items()):
        hashes = sorted(
            _text(item.get("content_hash")) or _stable_hash({
                field: item.get(field)
                for field in ("feature_id", "source_record_id", "geometry", "facility_class_keys")
            })
            for item in items
        )
        versions.append({
            "source_key": key[0],
            "provider": key[1],
            "dataset_version": key[2],
            "coordinate_system": key[3],
            "feature_count": len(items),
            "content_hash": _stable_hash(hashes),
        })

    for raw in foundation.get("evidence_sources") or []:
        item = _mapping(raw)
        source_key = _text(item.get("source_key") or item.get("source") or item.get("provider"))
        if not source_key:
            continue
        record = {
            "source_key": source_key,
            "provider": _text(item.get("provider") or source_key),
            "dataset_version": _text(item.get("dataset_version") or item.get("version")) or "unversioned",
        }
        if item.get("content_hash"):
            record["content_hash"] = _text(item.get("content_hash"))
        versions.append(record)

    unique = {_canonical_json(item): item for item in versions}
    return sorted(
        unique.values(),
        key=lambda item: (
            _text(item.get("source_key")),
            _text(item.get("provider")),
            _text(item.get("dataset_version")),
            _canonical_json(item),
        ),
    )


class MechanismAwareSpatialRefiner:
    """Run R3 requests against a controlled spatial catalog.

    Query failures are isolated per request and recorded in the diagnostic
    provider-attempt audit.  The returned evidence snapshot therefore remains
    useful for orchestration even when one catalog request cannot run.
    """

    def __init__(
        self,
        catalog: SpatialCatalogPort,
        *,
        query_limit: int = DEFAULT_CATALOG_QUERY_LIMIT,
    ) -> None:
        if not callable(getattr(catalog, "query_bbox", None)):
            raise SpatialRefinementExecutionError("空间目录必须实现 query_bbox 查询接口")
        try:
            self.query_limit = max(1, int(query_limit))
        except (TypeError, ValueError) as exc:
            raise SpatialRefinementExecutionError("空间目录查询上限必须是正整数") from exc
        self.catalog = catalog

    def refine(
        self,
        plan: FacilityQueryPlan | Mapping[str, Any],
        *,
        foundation: Mapping[str, Any],
    ) -> SpatialRefinementSnapshot:
        compiled_plan = plan if isinstance(plan, FacilityQueryPlan) else FacilityQueryPlan.from_dict(plan)
        foundation_payload = dict(foundation or {})
        base_catalog: List[Dict[str, Any]] = []
        for raw in foundation_payload.get("target_catalog") or []:
            item = _mapping(raw)
            if item:
                item["_refinement_origin"] = "foundation"
                base_catalog.append(item)
        bbox = _spatial_bbox(foundation_payload, base_catalog)
        catalog_key = _catalog_key(self.catalog)
        queried_features: List[Any] = []
        attempts: List[Dict[str, Any]] = []

        r3_requests = [item for item in compiled_plan.requests if item.resolution_level == "R3"]
        for request in r3_requests:
            attempt_seed: Dict[str, Any] = {
                "request_id": request.request_id,
                "provider_key": catalog_key,
                "query_bbox": list(bbox) if bbox is not None else [],
                "facility_class_keys": sorted(_unique_strings(request.facility_class_keys)),
                "query_limit": self.query_limit,
            }
            if bbox is None:
                attempt = {
                    **attempt_seed,
                    "status": "skipped",
                    "reason_code": "spatial_scope_missing",
                    "result_count": 0,
                    "result_feature_ids": [],
                }
            else:
                try:
                    results = list(self.catalog.query_bbox(
                        bbox,
                        facility_class_keys=attempt_seed["facility_class_keys"] or None,
                        limit=self.query_limit,
                    ) or [])
                except Exception as exc:  # Catalog ports isolate their own I/O/provider details.
                    attempt = {
                        **attempt_seed,
                        "status": "failed",
                        "reason_code": "catalog_query_failed",
                        "error_type": type(exc).__name__,
                        "result_count": 0,
                        "result_feature_ids": [],
                    }
                else:
                    normalized_results = [
                        item
                        for result in results
                        if (item := _normalize_feature(result, origin="catalog")) is not None
                    ]
                    normalized_results.sort(key=lambda item: _text(item.get("feature_id")))
                    queried_features.extend(normalized_results)
                    attempt = {
                        **attempt_seed,
                        "status": "completed",
                        "result_count": len(normalized_results),
                        "result_feature_ids": [item["feature_id"] for item in normalized_results],
                    }
            attempt["attempt_id"] = _attempt_id(attempt)
            attempts.append(attempt)

        protected_ids = {
            entity_id
            for request in r3_requests
            for entity_id in request.target_entity_ids
        }
        merged_catalog = _merge_catalog_features(
            [*base_catalog, *queried_features],
            protected_ids=protected_ids,
        )
        source_versions = _source_versions(foundation_payload, merged_catalog)
        snapshot = build_spatial_refinement_snapshot(
            compiled_plan,
            target_catalog=merged_catalog,
            provider_attempts=attempts,
            source_versions=source_versions,
        )
        if snapshot.r4_model_units:
            raise SpatialRefinementExecutionError("空间目录细化服务不得自动生成 R4 模型单元")
        return snapshot


__all__ = [
    "DEFAULT_CATALOG_QUERY_LIMIT",
    "MechanismAwareSpatialRefiner",
    "SpatialRefinementExecutionError",
]
