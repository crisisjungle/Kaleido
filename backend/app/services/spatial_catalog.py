"""Stable spatial-catalog boundary with an embedded SQLite implementation.

The formal production catalog is expected to live in a controlled spatial
database (for example PostGIS).  This module deliberately keeps the boundary
small so local development, deterministic fixtures, and recovery paths do not
depend on a public POI API.  ``SQLiteSpatialCatalog`` is the embedded adapter;
``SpatialCatalogPort`` is the replaceable application boundary.

The implementation uses only the Python standard library.  SQLite RTree is
used when the interpreter was compiled with that extension and otherwise the
same overlap query falls back to indexed scalar columns.  GeoJSON geometries
and source metadata are stored losslessly as canonical JSON.  All catalog
queries are deterministic and return features ordered by their stable ID.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Protocol, Sequence, Tuple, runtime_checkable


SPATIAL_CATALOG_CONTRACT_VERSION = "spatial_catalog.v1"
_EVIDENCE_GRADES = {"A", "B", "C", "D", "S"}
_DEFAULT_COORDINATE_SYSTEM = "WGS84"

BBox = Tuple[float, float, float, float]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _required_text(value: Any, label: str) -> str:
    text = _clean_text(value)
    if not text:
        raise ValueError(f"{label}不能为空")
    return text


def _canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("空间目录字段必须能够序列化为 JSON") from exc


def _json_copy(value: Any, *, expected_mapping: bool = False) -> Any:
    copied = json.loads(_canonical_json(value))
    if expected_mapping and not isinstance(copied, dict):
        raise ValueError("空间目录映射字段必须使用对象格式")
    return copied


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _unique_sorted_strings(values: Iterable[Any]) -> Tuple[str, ...]:
    normalized = {_clean_text(value) for value in values}
    normalized.discard("")
    return tuple(sorted(normalized))


def _string_sequence(value: Any) -> Tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return _unique_sorted_strings([value])
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return _unique_sorted_strings(value)
    raise ValueError("facility_class_keys 必须使用字符串或字符串数组")


def _finite_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数值") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label}必须是有限数值")
    return number


def _normalize_bbox(value: Sequence[Any]) -> BBox:
    if isinstance(value, (str, bytes, bytearray)) or len(value) != 4:
        raise ValueError("bbox 必须按 min_lon、min_lat、max_lon、max_lat 提供四个数值")
    min_lon, min_lat, max_lon, max_lat = (
        _finite_number(item, "bbox 坐标") for item in value
    )
    if min_lon > max_lon or min_lat > max_lat:
        raise ValueError("bbox 最小坐标不能大于最大坐标")
    if min_lon < -180 or max_lon > 180 or min_lat < -90 or max_lat > 90:
        raise ValueError("空间目录 bbox 必须使用有效的经纬度范围")
    return (min_lon, min_lat, max_lon, max_lat)


def _coordinate_pairs(value: Any) -> Iterable[Tuple[float, float]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return
    if len(value) >= 2 and all(
        isinstance(item, (int, float)) and not isinstance(item, bool) for item in value[:2]
    ):
        x = _finite_number(value[0], "GeoJSON 经度")
        y = _finite_number(value[1], "GeoJSON 纬度")
        yield (x, y)
        return
    for nested in value:
        yield from _coordinate_pairs(nested)


def geometry_bbox(geometry: Mapping[str, Any]) -> BBox:
    """Return a WGS84 bounding box for a non-empty GeoJSON geometry."""

    normalized = _json_copy(geometry, expected_mapping=True)
    geometry_type = _clean_text(normalized.get("type"))
    if not geometry_type:
        raise ValueError("GeoJSON geometry 缺少 type")

    pairs: List[Tuple[float, float]] = []
    if geometry_type == "GeometryCollection":
        geometries = normalized.get("geometries")
        if not isinstance(geometries, list):
            raise ValueError("GeometryCollection.geometries 必须使用数组格式")
        for nested in geometries:
            if not isinstance(nested, Mapping):
                raise ValueError("GeometryCollection 只能包含 GeoJSON geometry")
            nested_bbox = geometry_bbox(nested)
            pairs.extend(
                [
                    (nested_bbox[0], nested_bbox[1]),
                    (nested_bbox[2], nested_bbox[3]),
                ]
            )
    else:
        if "coordinates" not in normalized:
            raise ValueError("GeoJSON geometry 缺少 coordinates")
        pairs.extend(_coordinate_pairs(normalized.get("coordinates")))

    if not pairs:
        raise ValueError("GeoJSON geometry 不能是空几何")
    bbox = _normalize_bbox(
        (
            min(item[0] for item in pairs),
            min(item[1] for item in pairs),
            max(item[0] for item in pairs),
            max(item[1] for item in pairs),
        )
    )
    return bbox


@dataclass(frozen=True)
class SpatialCatalogFeature:
    """One traceable R0-R3 spatial feature stored in the catalog."""

    feature_id: str
    display_name: str
    facility_class_keys: Tuple[str, ...]
    geometry: Dict[str, Any]
    bbox: BBox
    source_key: str
    provider: str
    source_record_id: str
    evidence_grade: str
    dataset_version: str
    coordinate_system: str = _DEFAULT_COORDINATE_SYSTEM
    tags: Dict[str, Any] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_id", _required_text(self.feature_id, "feature_id"))
        object.__setattr__(self, "display_name", _required_text(self.display_name, "display_name"))
        object.__setattr__(self, "facility_class_keys", _string_sequence(self.facility_class_keys))
        normalized_geometry = _json_copy(self.geometry, expected_mapping=True)
        derived_bbox = geometry_bbox(normalized_geometry)
        normalized_bbox = _normalize_bbox(self.bbox)
        if any(abs(left - right) > 1e-9 for left, right in zip(derived_bbox, normalized_bbox)):
            raise ValueError("feature bbox 必须与 GeoJSON geometry 一致")
        object.__setattr__(self, "geometry", normalized_geometry)
        object.__setattr__(self, "bbox", normalized_bbox)
        object.__setattr__(self, "source_key", _required_text(self.source_key, "source_key"))
        object.__setattr__(self, "provider", _required_text(self.provider, "provider"))
        object.__setattr__(
            self,
            "source_record_id",
            _required_text(self.source_record_id, "source_record_id"),
        )
        evidence_grade = _required_text(self.evidence_grade, "evidence_grade").upper()
        if evidence_grade not in _EVIDENCE_GRADES:
            raise ValueError("evidence_grade 只能是 A、B、C、D 或 S")
        object.__setattr__(self, "evidence_grade", evidence_grade)
        object.__setattr__(
            self,
            "dataset_version",
            _required_text(self.dataset_version, "dataset_version"),
        )
        object.__setattr__(
            self,
            "coordinate_system",
            _required_text(self.coordinate_system, "coordinate_system"),
        )
        object.__setattr__(self, "tags", _json_copy(self.tags, expected_mapping=True))
        object.__setattr__(
            self,
            "properties",
            _json_copy(self.properties, expected_mapping=True),
        )

        hash_payload = self._hash_payload()
        calculated_hash = _stable_hash(hash_payload)
        supplied_hash = _clean_text(self.content_hash)
        if supplied_hash and supplied_hash != calculated_hash:
            raise ValueError("content_hash 与空间要素内容不一致")
        object.__setattr__(self, "content_hash", calculated_hash)

    @property
    def coordinates(self) -> Any:
        """Return a detached copy of the original GeoJSON coordinates."""

        return _json_copy(self.geometry.get("coordinates"))

    def _hash_payload(self) -> Dict[str, Any]:
        return {
            "contract_version": SPATIAL_CATALOG_CONTRACT_VERSION,
            "feature_id": self.feature_id,
            "display_name": self.display_name,
            "facility_class_keys": list(self.facility_class_keys),
            "geometry": self.geometry,
            "bbox": list(self.bbox),
            "source_key": self.source_key,
            "provider": self.provider,
            "source_record_id": self.source_record_id,
            "evidence_grade": self.evidence_grade,
            "dataset_version": self.dataset_version,
            "coordinate_system": self.coordinate_system,
            "tags": self.tags,
            "properties": self.properties,
        }

    def to_dict(self) -> Dict[str, Any]:
        payload = self._hash_payload()
        payload.pop("contract_version", None)
        payload["content_hash"] = self.content_hash
        return payload

    def to_geojson_feature(self) -> Dict[str, Any]:
        properties = dict(self.properties)
        properties.update(
            {
                "feature_id": self.feature_id,
                "display_name": self.display_name,
                "facility_class_keys": list(self.facility_class_keys),
                "source_key": self.source_key,
                "provider": self.provider,
                "source_record_id": self.source_record_id,
                "evidence_grade": self.evidence_grade,
                "dataset_version": self.dataset_version,
                "coordinate_system": self.coordinate_system,
                "tags": dict(self.tags),
                "content_hash": self.content_hash,
            }
        )
        return {
            "type": "Feature",
            "id": self.feature_id,
            "bbox": list(self.bbox),
            "geometry": _json_copy(self.geometry, expected_mapping=True),
            "properties": properties,
        }


@runtime_checkable
class SpatialCatalogPort(Protocol):
    """Storage boundary shared by the embedded and future PostGIS adapters."""

    def upsert(self, feature: SpatialCatalogFeature) -> SpatialCatalogFeature:
        """Insert or deterministically replace a feature by ``feature_id``."""

    def upsert_many(self, features: Iterable[SpatialCatalogFeature]) -> int:
        """Insert or replace multiple features and return the processed count."""

    def query_bbox(
        self,
        bbox: Sequence[float],
        *,
        facility_class_keys: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> List[SpatialCatalogFeature]:
        """Return overlapping features, optionally matching any facility class."""

    def import_geojson(
        self,
        feature_collection: Mapping[str, Any],
        *,
        source_key: str,
        provider: str,
        evidence_grade: str,
        dataset_version: str,
        coordinate_system: str = _DEFAULT_COORDINATE_SYSTEM,
    ) -> List[SpatialCatalogFeature]:
        """Import a GeoJSON FeatureCollection and return the stored features."""


class SQLiteSpatialCatalog:
    """Embedded deterministic implementation of :class:`SpatialCatalogPort`."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        database_text = str(database)
        if database_text != ":memory:":
            Path(database_text).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_text, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._closed = False
        self._has_rtree = False
        self._initialize()

    @property
    def uses_rtree(self) -> bool:
        return self._has_rtree

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS spatial_catalog_features (
                    feature_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    facility_class_keys_json TEXT NOT NULL,
                    geometry_json TEXT NOT NULL,
                    min_lon REAL NOT NULL,
                    min_lat REAL NOT NULL,
                    max_lon REAL NOT NULL,
                    max_lat REAL NOT NULL,
                    source_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    evidence_grade TEXT NOT NULL,
                    dataset_version TEXT NOT NULL,
                    coordinate_system TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_spatial_catalog_scalar_bbox
                ON spatial_catalog_features(min_lon, max_lon, min_lat, max_lat)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_spatial_catalog_source_record
                ON spatial_catalog_features(provider, source_key, source_record_id, dataset_version)
                """
            )
            try:
                self._connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS spatial_catalog_rtree
                    USING rtree(feature_rowid, min_lon, max_lon, min_lat, max_lat)
                    """
                )
            except sqlite3.OperationalError:
                self._has_rtree = False
            else:
                self._has_rtree = True
                self._rebuild_rtree_locked()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("空间目录已经关闭")

    def _rebuild_rtree_locked(self) -> None:
        if not self._has_rtree:
            return
        self._connection.execute("DELETE FROM spatial_catalog_rtree")
        self._connection.execute(
            """
            INSERT INTO spatial_catalog_rtree(feature_rowid, min_lon, max_lon, min_lat, max_lat)
            SELECT rowid, min_lon, max_lon, min_lat, max_lat
            FROM spatial_catalog_features
            """
        )

    def _upsert_locked(self, feature: SpatialCatalogFeature) -> None:
        self._connection.execute(
            """
            INSERT INTO spatial_catalog_features (
                feature_id, display_name, facility_class_keys_json, geometry_json,
                min_lon, min_lat, max_lon, max_lat, source_key, provider,
                source_record_id, evidence_grade, dataset_version, coordinate_system,
                tags_json, properties_json, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(feature_id) DO UPDATE SET
                display_name = excluded.display_name,
                facility_class_keys_json = excluded.facility_class_keys_json,
                geometry_json = excluded.geometry_json,
                min_lon = excluded.min_lon,
                min_lat = excluded.min_lat,
                max_lon = excluded.max_lon,
                max_lat = excluded.max_lat,
                source_key = excluded.source_key,
                provider = excluded.provider,
                source_record_id = excluded.source_record_id,
                evidence_grade = excluded.evidence_grade,
                dataset_version = excluded.dataset_version,
                coordinate_system = excluded.coordinate_system,
                tags_json = excluded.tags_json,
                properties_json = excluded.properties_json,
                content_hash = excluded.content_hash
            """,
            (
                feature.feature_id,
                feature.display_name,
                _canonical_json(list(feature.facility_class_keys)),
                _canonical_json(feature.geometry),
                feature.bbox[0],
                feature.bbox[1],
                feature.bbox[2],
                feature.bbox[3],
                feature.source_key,
                feature.provider,
                feature.source_record_id,
                feature.evidence_grade,
                feature.dataset_version,
                feature.coordinate_system,
                _canonical_json(feature.tags),
                _canonical_json(feature.properties),
                feature.content_hash,
            ),
        )
        if self._has_rtree:
            row = self._connection.execute(
                "SELECT rowid FROM spatial_catalog_features WHERE feature_id = ?",
                (feature.feature_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("空间目录写入后无法定位要素")
            self._connection.execute(
                """
                INSERT OR REPLACE INTO spatial_catalog_rtree(
                    feature_rowid, min_lon, max_lon, min_lat, max_lat
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(row["rowid"]),
                    feature.bbox[0],
                    feature.bbox[2],
                    feature.bbox[1],
                    feature.bbox[3],
                ),
            )

    def upsert(self, feature: SpatialCatalogFeature) -> SpatialCatalogFeature:
        if not isinstance(feature, SpatialCatalogFeature):
            raise TypeError("upsert 只接受 SpatialCatalogFeature")
        with self._lock:
            self._ensure_open()
            with self._connection:
                self._upsert_locked(feature)
        return feature

    def upsert_many(self, features: Iterable[SpatialCatalogFeature]) -> int:
        by_feature_id: Dict[str, SpatialCatalogFeature] = {}
        for item in features:
            if not isinstance(item, SpatialCatalogFeature):
                raise TypeError("upsert_many 只接受 SpatialCatalogFeature")
            existing = by_feature_id.get(item.feature_id)
            if existing is not None and existing.content_hash != item.content_hash:
                raise ValueError(f"同一批次包含冲突的 feature_id：{item.feature_id}")
            by_feature_id[item.feature_id] = item
        # The caller's iteration order must not affect the final write order.
        normalized = sorted(by_feature_id.values(), key=lambda item: item.feature_id)
        with self._lock:
            self._ensure_open()
            with self._connection:
                for feature in normalized:
                    self._upsert_locked(feature)
        return len(normalized)

    def query_bbox(
        self,
        bbox: Sequence[float],
        *,
        facility_class_keys: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> List[SpatialCatalogFeature]:
        normalized_bbox = _normalize_bbox(bbox)
        requested_classes = set(_string_sequence(facility_class_keys or ()))
        if limit is not None:
            if isinstance(limit, bool):
                raise ValueError("limit 必须是正整数")
            try:
                parsed_limit = int(limit)
            except (TypeError, ValueError) as exc:
                raise ValueError("limit 必须是正整数") from exc
            if parsed_limit <= 0:
                raise ValueError("limit 必须是正整数")
        else:
            parsed_limit = None

        with self._lock:
            self._ensure_open()
            if self._has_rtree:
                rows = self._connection.execute(
                    """
                    SELECT feature.*
                    FROM spatial_catalog_rtree AS spatial
                    JOIN spatial_catalog_features AS feature
                      ON feature.rowid = spatial.feature_rowid
                    WHERE spatial.max_lon >= ? AND spatial.min_lon <= ?
                      AND spatial.max_lat >= ? AND spatial.min_lat <= ?
                    ORDER BY feature.feature_id ASC
                    """,
                    (
                        normalized_bbox[0],
                        normalized_bbox[2],
                        normalized_bbox[1],
                        normalized_bbox[3],
                    ),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT *
                    FROM spatial_catalog_features
                    WHERE max_lon >= ? AND min_lon <= ?
                      AND max_lat >= ? AND min_lat <= ?
                    ORDER BY feature_id ASC
                    """,
                    (
                        normalized_bbox[0],
                        normalized_bbox[2],
                        normalized_bbox[1],
                        normalized_bbox[3],
                    ),
                ).fetchall()

        results: List[SpatialCatalogFeature] = []
        for row in rows:
            feature = self._row_to_feature(row)
            # SQLite RTree uses outward-rounded 32-bit bounds.  Recheck the
            # stored double-precision bbox to remove harmless false positives.
            if not (
                feature.bbox[2] >= normalized_bbox[0]
                and feature.bbox[0] <= normalized_bbox[2]
                and feature.bbox[3] >= normalized_bbox[1]
                and feature.bbox[1] <= normalized_bbox[3]
            ):
                continue
            if requested_classes and not requested_classes.intersection(feature.facility_class_keys):
                continue
            results.append(feature)
            if parsed_limit is not None and len(results) >= parsed_limit:
                break
        return results

    def import_geojson(
        self,
        feature_collection: Mapping[str, Any],
        *,
        source_key: str,
        provider: str,
        evidence_grade: str,
        dataset_version: str,
        coordinate_system: str = _DEFAULT_COORDINATE_SYSTEM,
    ) -> List[SpatialCatalogFeature]:
        if not isinstance(feature_collection, Mapping):
            raise ValueError("GeoJSON 导入内容必须是 FeatureCollection 对象")
        payload = _json_copy(feature_collection, expected_mapping=True)
        if payload.get("type") != "FeatureCollection":
            raise ValueError("GeoJSON 导入内容必须是 FeatureCollection")
        raw_features = payload.get("features")
        if not isinstance(raw_features, list):
            raise ValueError("FeatureCollection.features 必须使用数组格式")

        defaults = {
            "source_key": _required_text(source_key, "source_key"),
            "provider": _required_text(provider, "provider"),
            "evidence_grade": _required_text(evidence_grade, "evidence_grade").upper(),
            "dataset_version": _required_text(dataset_version, "dataset_version"),
            "coordinate_system": _required_text(coordinate_system, "coordinate_system"),
        }
        if defaults["evidence_grade"] not in _EVIDENCE_GRADES:
            raise ValueError("evidence_grade 只能是 A、B、C、D 或 S")

        converted: List[SpatialCatalogFeature] = []
        for index, raw_feature in enumerate(raw_features):
            if not isinstance(raw_feature, Mapping) or raw_feature.get("type") != "Feature":
                raise ValueError(f"features[{index}] 必须是 GeoJSON Feature")
            geometry = raw_feature.get("geometry")
            if not isinstance(geometry, Mapping):
                raise ValueError(f"features[{index}].geometry 必须是非空 GeoJSON geometry")
            properties = raw_feature.get("properties") or {}
            if not isinstance(properties, Mapping):
                raise ValueError(f"features[{index}].properties 必须使用对象格式")
            properties_copy = _json_copy(properties, expected_mapping=True)
            nested_source = properties_copy.get("source") or {}
            if not isinstance(nested_source, Mapping):
                nested_source = {}

            item_source_key = _clean_text(properties_copy.get("source_key")) or _clean_text(
                nested_source.get("source_key")
            ) or defaults["source_key"]
            item_provider = _clean_text(properties_copy.get("provider")) or _clean_text(
                nested_source.get("provider")
            ) or defaults["provider"]
            item_dataset_version = _clean_text(properties_copy.get("dataset_version")) or _clean_text(
                nested_source.get("dataset_version")
            ) or defaults["dataset_version"]
            item_evidence_grade = _clean_text(properties_copy.get("evidence_grade")) or _clean_text(
                nested_source.get("evidence_grade")
            ) or defaults["evidence_grade"]
            item_coordinate_system = _clean_text(properties_copy.get("coordinate_system")) or _clean_text(
                nested_source.get("coordinate_system")
            ) or defaults["coordinate_system"]
            source_record_id = _clean_text(properties_copy.get("source_record_id")) or _clean_text(
                nested_source.get("source_record_id")
            ) or _clean_text(raw_feature.get("id"))
            display_name = (
                _clean_text(properties_copy.get("display_name"))
                or _clean_text(properties_copy.get("name"))
                or _clean_text(properties_copy.get("label_zh"))
                or _clean_text(properties_copy.get("label"))
            )
            class_keys = _string_sequence(
                properties_copy.get("facility_class_keys")
                or properties_copy.get("facility_class_key")
                or []
            )
            tags = properties_copy.get("tags") or {}
            if not isinstance(tags, Mapping):
                raise ValueError(f"features[{index}].properties.tags 必须使用对象格式")

            identity_payload = {
                "source_key": item_source_key,
                "provider": item_provider,
                "source_record_id": source_record_id,
                "display_name": display_name,
                "facility_class_keys": list(class_keys),
                "geometry": geometry,
            }
            if not source_record_id:
                source_record_id = f"derived_{_stable_hash(identity_payload)[:24]}"
            feature_id = (
                _clean_text(properties_copy.get("feature_id"))
                or _clean_text(raw_feature.get("id"))
                or f"spatial_{_stable_hash({**identity_payload, 'source_record_id': source_record_id})[:24]}"
            )
            if not display_name:
                display_name = feature_id
            normalized_geometry = _json_copy(geometry, expected_mapping=True)
            converted.append(
                SpatialCatalogFeature(
                    feature_id=feature_id,
                    display_name=display_name,
                    facility_class_keys=class_keys,
                    geometry=normalized_geometry,
                    bbox=geometry_bbox(normalized_geometry),
                    source_key=item_source_key,
                    provider=item_provider,
                    source_record_id=source_record_id,
                    evidence_grade=item_evidence_grade,
                    dataset_version=item_dataset_version,
                    coordinate_system=item_coordinate_system,
                    tags=dict(tags),
                    properties=properties_copy,
                )
            )

        self.upsert_many(converted)
        return sorted(converted, key=lambda item: item.feature_id)

    @staticmethod
    def _row_to_feature(row: sqlite3.Row) -> SpatialCatalogFeature:
        return SpatialCatalogFeature(
            feature_id=str(row["feature_id"]),
            display_name=str(row["display_name"]),
            facility_class_keys=tuple(json.loads(row["facility_class_keys_json"])),
            geometry=json.loads(row["geometry_json"]),
            bbox=(
                float(row["min_lon"]),
                float(row["min_lat"]),
                float(row["max_lon"]),
                float(row["max_lat"]),
            ),
            source_key=str(row["source_key"]),
            provider=str(row["provider"]),
            source_record_id=str(row["source_record_id"]),
            evidence_grade=str(row["evidence_grade"]),
            dataset_version=str(row["dataset_version"]),
            coordinate_system=str(row["coordinate_system"]),
            tags=json.loads(row["tags_json"]),
            properties=json.loads(row["properties_json"]),
            content_hash=str(row["content_hash"]),
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._connection.close()
            self._closed = True

    def __enter__(self) -> "SQLiteSpatialCatalog":
        self._ensure_open()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        self.close()


__all__ = [
    "BBox",
    "SPATIAL_CATALOG_CONTRACT_VERSION",
    "SQLiteSpatialCatalog",
    "SpatialCatalogFeature",
    "SpatialCatalogPort",
    "geometry_bbox",
]
