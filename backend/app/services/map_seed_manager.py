"""
Map-first seed generation and persistence.

This service builds a spatially anchored seed graph from a map point using
best-effort public data sources. It deliberately distinguishes observed,
detected, and inferred graph items so downstream simulation logic can preserve
uncertainty instead of flattening everything into "facts".
"""

from __future__ import annotations

import io
import json
import math
import os
import threading
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PIL import Image

from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("envfish.map_seed")
PIL_NEAREST = getattr(getattr(Image, "Resampling", Image), "NEAREST")


WORLD_COVER_CLASSES: Dict[int, Dict[str, Any]] = {
    10: {"name": "Tree cover", "name_zh": "树木覆盖", "color": (0, 100, 0), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 8},
    20: {"name": "Shrubland", "name_zh": "灌丛", "color": (255, 187, 34), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 6},
    30: {"name": "Grassland", "name_zh": "草地", "color": (255, 255, 76), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 6},
    40: {"name": "Cropland", "name_zh": "农田", "color": (240, 150, 255), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 6},
    50: {"name": "Built-up", "name_zh": "建成区", "color": (250, 0, 0), "category": "facility", "node_family": "Infrastructure", "importance": 7},
    60: {"name": "Bare / sparse vegetation", "name_zh": "裸地/稀疏植被", "color": (180, 180, 180), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 5},
    70: {"name": "Snow and ice", "name_zh": "雪冰", "color": (240, 240, 240), "category": "ecology", "node_family": "EnvironmentalCarrier", "importance": 4},
    80: {"name": "Permanent water bodies", "name_zh": "永久水体", "color": (0, 100, 200), "category": "ecology", "node_family": "EnvironmentalCarrier", "importance": 9},
    90: {"name": "Herbaceous wetland", "name_zh": "草本湿地", "color": (0, 150, 160), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 9},
    95: {"name": "Mangroves", "name_zh": "红树林", "color": (0, 207, 117), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 10},
    100: {"name": "Moss and lichen", "name_zh": "苔藓/地衣", "color": (250, 230, 160), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 5},
}


def _utcnow_iso() -> str:
    return datetime.now().isoformat()


def _safe_http_json(
    url: str,
    *,
    method: str = "GET",
    data: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 20.0,
) -> Any:
    request_headers = {
        "User-Agent": "Kaleido/0.1 map-seed (+https://github.com/crisisjungle/Kaleido)",
        "Accept": "application/json",
    }
    if headers:
        request_headers.update(headers)

    payload = data.encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=payload, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(1e-12, 1 - a)))


def _radius_to_bbox(lat: float, lon: float, radius_m: float) -> Dict[str, float]:
    lat_delta = radius_m / 111320.0
    lon_denominator = max(math.cos(math.radians(lat)) * 111320.0, 1e-6)
    lon_delta = radius_m / lon_denominator
    return {
        "min_lat": round(lat - lat_delta, 6),
        "max_lat": round(lat + lat_delta, 6),
        "min_lon": round(lon - lon_delta, 6),
        "max_lon": round(lon + lon_delta, 6),
    }


def _lonlat_to_mercator(lon: float, lat: float) -> Tuple[float, float]:
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * 20037508.34 / 180.0
    return x, y


def _mercator_to_lonlat(x: float, y: float) -> Tuple[float, float]:
    lon = x / 20037508.34 * 180.0
    lat = y / 20037508.34 * 180.0
    lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
    return lon, lat


def _circle_polygon(lat: float, lon: float, radius_m: float, steps: int = 24) -> List[List[float]]:
    points: List[List[float]] = []
    for index in range(steps):
        angle = 2 * math.pi * index / steps
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        lat_offset = dy / 111320.0
        lon_offset = dx / max(math.cos(math.radians(lat)) * 111320.0, 1e-6)
        points.append([round(lon + lon_offset, 6), round(lat + lat_offset, 6)])
    if points:
        points.append(points[0])
    return points


def _slugify(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    parts = [part for part in text.split("_") if part]
    return "_".join(parts) or "item"


class MapSeedManager:
    MAP_SEEDS_DIR = os.path.join(Config.UPLOAD_FOLDER, "map_seeds")
    GRAPH_FILENAME = "graph_snapshot.json"
    LAYERS_FILENAME = "layers.json"
    META_FILENAME = "seed.json"
    REPORT_FILENAME = "map_seed_report.md"

    PROXY_CATEGORY_ORDER = [
        "residents",
        "operators",
        "visitors",
        "regulators",
        "maintainers",
        "vulnerable_groups",
    ]

    def __init__(self):
        os.makedirs(self.MAP_SEEDS_DIR, exist_ok=True)
        self._llm_client: Optional[LLMClient] = None
        if Config.LLM_API_KEY:
            try:
                self._llm_client = LLMClient()
            except Exception as exc:
                logger.warning(f"MapSeed LLM init failed, using rule-based inference only: {exc}")

    def geocode_location(self, query: str, *, limit: int = 5, radius_m: int = 3000) -> List[Dict[str, Any]]:
        text = str(query or "").strip()
        if not text:
            return []
        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode(
                {
                    "format": "jsonv2",
                    "q": text,
                    "limit": max(1, min(int(limit or 5), 8)),
                    "addressdetails": 1,
                }
            )
        )
        try:
            payload = _safe_http_json(url, timeout=15.0)
        except Exception as exc:
            logger.warning(f"Forward geocode failed for '{text}': {exc}")
            return []

        candidates: List[Dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else []:
            try:
                lat = round(float(item.get("lat")), 6)
                lon = round(float(item.get("lon")), 6)
            except Exception:
                continue
            admin_context = self._normalize_admin_context(
                address=item.get("address") or {},
                display_name=str(item.get("display_name") or text),
                lat=lat,
                lon=lon,
            )
            candidates.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "display_name": admin_context.get("display_name") or text,
                    "area_label": self.describe_area_label(lat=lat, lon=lon, radius_m=radius_m, admin_context=admin_context),
                    "admin_context": admin_context,
                }
            )
        return candidates

    def resolve_area_context(self, lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
        admin_context = self._reverse_geocode(lat, lon)
        return {
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
            "radius_m": max(500, int(radius_m or 3000)),
            "admin_context": admin_context,
            "area_label": self.describe_area_label(
                lat=float(lat),
                lon=float(lon),
                radius_m=max(500, int(radius_m or 3000)),
                admin_context=admin_context,
            ),
        }

    def describe_area_label(self, lat: float, lon: float, radius_m: int, admin_context: Optional[Dict[str, Any]] = None) -> str:
        context = dict(admin_context or self._reverse_geocode(lat, lon) or {})
        city = str(context.get("city") or "").strip()
        district = str(context.get("district") or "").strip()
        road = str(context.get("road") or "").strip()
        locality = self._select_locality_name(context, radius_m)
        display_name = str(context.get("display_name") or "").strip()
        radius_m = max(500, int(radius_m or 3000))
        base_label = self._join_place_tokens(city, district, locality)
        if base_label:
            if locality and road and locality == road:
                return f"{base_label}周边" if radius_m <= 1800 else base_label
            if locality and radius_m <= 1800:
                return f"{base_label}周边"
            if radius_m >= 15000 and not locality:
                return f"{base_label}重点区域"
            if radius_m >= 6000 and not locality and district:
                return f"{base_label}片区"
            return base_label

        if city:
            return f"{city}周边区域"

        primary = self._display_name_to_place(display_name)
        if primary:
            return primary
        return "选定区域"

    @classmethod
    def _seed_dir(cls, seed_id: str) -> str:
        return os.path.join(cls.MAP_SEEDS_DIR, seed_id)

    @classmethod
    def _seed_file(cls, seed_id: str, name: str) -> str:
        return os.path.join(cls._seed_dir(seed_id), name)

    @classmethod
    def create_seed(
        cls,
        *,
        lat: float,
        lon: float,
        radius_m: int,
        simulation_requirement: str = "",
        title: str = "",
    ) -> Dict[str, Any]:
        seed_id = f"mapseed_{uuid.uuid4().hex[:12]}"
        seed_dir = cls._seed_dir(seed_id)
        os.makedirs(seed_dir, exist_ok=True)
        payload = {
            "seed_id": seed_id,
            "status": "pending",
            "created_at": _utcnow_iso(),
            "updated_at": _utcnow_iso(),
            "title": title or f"Map Seed {seed_id[-6:]}",
            "input": {
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "radius_m": max(500, int(radius_m)),
                "simulation_requirement": simulation_requirement.strip(),
            },
            "summary": "",
            "scene_classification": {},
            "environment_baseline": {},
            "remote_sensing_summary": {},
            "project_id": None,
            "simulation_id": None,
            "error": None,
        }
        cls._write_json(cls._seed_file(seed_id, cls.META_FILENAME), payload)
        return payload

    @classmethod
    def get_seed(cls, seed_id: str) -> Optional[Dict[str, Any]]:
        path = cls._seed_file(seed_id, cls.META_FILENAME)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def get_graph_snapshot(cls, seed_id: str) -> Optional[Dict[str, Any]]:
        path = cls._seed_file(seed_id, cls.GRAPH_FILENAME)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def get_layers(cls, seed_id: str) -> Optional[Dict[str, Any]]:
        path = cls._seed_file(seed_id, cls.LAYERS_FILENAME)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def get_report_text(cls, seed_id: str) -> str:
        path = cls._seed_file(seed_id, cls.REPORT_FILENAME)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    @classmethod
    def update_seed(cls, seed_id: str, **changes: Any) -> Dict[str, Any]:
        payload = cls.get_seed(seed_id)
        if not payload:
            raise ValueError(f"Map seed not found: {seed_id}")
        payload.update(changes)
        payload["updated_at"] = _utcnow_iso()
        cls._write_json(cls._seed_file(seed_id, cls.META_FILENAME), payload)
        return payload

    @classmethod
    def _write_json(cls, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    @classmethod
    def _write_text(cls, path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def build_seed(
        self,
        seed_id: str,
        *,
        progress_callback=None,
    ) -> Dict[str, Any]:
        seed = self.get_seed(seed_id)
        if not seed:
            raise ValueError(f"Map seed not found: {seed_id}")

        lat = float(seed["input"]["lat"])
        lon = float(seed["input"]["lon"])
        radius_m = int(seed["input"]["radius_m"])
        simulation_requirement = seed["input"].get("simulation_requirement", "")

        self.update_seed(seed_id, status="processing", error=None)
        if progress_callback:
            progress_callback("locating", 5, "解析地点与分析范围")

        admin_context = self._reverse_geocode(lat, lon)
        aoi = self._build_area_of_interest(lat, lon, radius_m, admin_context)

        if progress_callback:
            progress_callback("collecting", 20, "采集周边空间要素和环境基线")

        features = self._collect_spatial_features(lat, lon, radius_m)
        remote_sensing_features, remote_sensing_summary, remote_sensing_layers = self._collect_worldcover_features(
            lat=lat,
            lon=lon,
            radius_m=radius_m,
        )
        environment_baseline = self._build_environment_baseline(lat, lon, admin_context)
        features = self._merge_context_features(
            features=features + remote_sensing_features,
            lat=lat,
            lon=lon,
            admin_context=admin_context,
            environment_baseline=environment_baseline,
        )

        if progress_callback:
            progress_callback("classifying", 40, "判定场景类型并构建空间事实层")

        scene_classification = self._classify_scene(features, admin_context)

        if progress_callback:
            progress_callback("graphing", 60, "构建地图图谱节点与关系")

        graph = self._build_graph(
            seed=seed,
            aoi=aoi,
            admin_context=admin_context,
            features=features,
            environment_baseline=environment_baseline,
            scene_classification=scene_classification,
        )

        if progress_callback:
            progress_callback("reporting", 85, "生成地图基线报告")

        report_text = self._build_report(
            seed=seed,
            aoi=aoi,
            admin_context=admin_context,
            features=features,
            environment_baseline=environment_baseline,
            scene_classification=scene_classification,
            graph=graph,
        )

        layers = self._build_layers_payload(aoi, features, graph, remote_sensing_layers=remote_sensing_layers)
        self._write_json(self._seed_file(seed_id, self.GRAPH_FILENAME), graph)
        self._write_json(self._seed_file(seed_id, self.LAYERS_FILENAME), layers)
        self._write_text(self._seed_file(seed_id, self.REPORT_FILENAME), report_text)

        summary = self._build_summary(admin_context, scene_classification, graph)
        payload = self.update_seed(
            seed_id,
            status="ready",
            title=summary["title"],
            summary=summary["summary"],
            admin_context=admin_context,
            area_of_interest=aoi,
            scene_classification=scene_classification,
            environment_baseline=environment_baseline,
            remote_sensing_summary=remote_sensing_summary,
            graph_stats=graph.get("stats", {}),
        )
        if progress_callback:
            progress_callback("completed", 100, "地图种子图谱已生成")
        return payload

    def build_seed_async(
        self,
        seed_id: str,
        *,
        progress_callback=None,
        error_callback=None,
    ) -> threading.Thread:
        def runner():
            try:
                self.build_seed(seed_id, progress_callback=progress_callback)
            except Exception as exc:
                logger.exception(f"Map seed build failed: {seed_id}")
                self.update_seed(seed_id, status="failed", error=str(exc))
                if error_callback:
                    error_callback(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        return thread

    def create_project_from_seed(self, seed_id: str) -> Dict[str, Any]:
        seed = self.get_seed(seed_id)
        graph = self.get_graph_snapshot(seed_id)
        report_text = self.get_report_text(seed_id)
        if not seed or not graph:
            raise ValueError(f"Map seed not ready: {seed_id}")

        existing_project_id = seed.get("project_id")
        if existing_project_id:
            project = ProjectManager.get_project(existing_project_id)
            if project:
                return {
                    "project_id": project.project_id,
                    "project_name": project.name,
                }

        title = seed.get("title") or f"Map Seed {seed_id[-6:]}"
        project = ProjectManager.create_project(name=title)
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.simulation_requirement = seed.get("input", {}).get("simulation_requirement") or (
            seed.get("summary") or "基于地图空间事实层建立生态推演场景。"
        )
        project.analysis_summary = seed.get("summary") or ""
        project.ontology = self._default_map_ontology()
        project.files = []
        ProjectManager.save_extracted_text(project.project_id, report_text)

        file_dir = ProjectManager._get_project_files_dir(project.project_id)
        report_filename = "map_seed_report.md"
        report_path = os.path.join(file_dir, report_filename)
        os.makedirs(file_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report_text)
        project.files.append({"filename": report_filename, "size": os.path.getsize(report_path)})
        project.total_text_length = len(report_text)

        graph_snapshot_path = os.path.join(ProjectManager._get_project_dir(project.project_id), "map_graph_snapshot.json")
        self._write_json(graph_snapshot_path, graph)
        project.graph_id = None
        ProjectManager.save_project(project)
        self.update_seed(seed_id, project_id=project.project_id)
        return {
            "project_id": project.project_id,
            "project_name": project.name,
        }

    def _build_area_of_interest(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        admin_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        bbox = _radius_to_bbox(lat, lon, radius_m)
        return {
            "center": {"lat": round(lat, 6), "lon": round(lon, 6)},
            "radius_m": radius_m,
            "bbox": bbox,
            "polygon": {
                "type": "Polygon",
                "coordinates": [_circle_polygon(lat, lon, radius_m)],
            },
            "label": self.describe_area_label(lat=lat, lon=lon, radius_m=radius_m, admin_context=admin_context),
        }

    def _reverse_geocode(self, lat: float, lon: float) -> Dict[str, Any]:
        url = (
            "https://nominatim.openstreetmap.org/reverse?"
            + urllib.parse.urlencode(
                {
                    "format": "jsonv2",
                    "lat": f"{lat:.6f}",
                    "lon": f"{lon:.6f}",
                    "zoom": 16,
                    "addressdetails": 1,
                }
            )
        )
        try:
            payload = _safe_http_json(url, timeout=15.0)
        except Exception as exc:
            logger.warning(f"Reverse geocode failed, using coordinate fallback: {exc}")
            payload = {}

        return self._normalize_admin_context(
            address=payload.get("address") or {},
            display_name=str(payload.get("display_name") or f"{lat:.4f}, {lon:.4f}"),
            lat=lat,
            lon=lon,
        )

    def _normalize_admin_context(
        self,
        *,
        address: Dict[str, Any],
        display_name: str,
        lat: float,
        lon: float,
    ) -> Dict[str, Any]:
        city = (
            address.get("city")
            or address.get("municipality")
            or address.get("town")
            or address.get("county")
            or ""
        )
        district = (
            address.get("city_district")
            or address.get("district")
            or address.get("suburb")
            or address.get("borough")
            or address.get("county")
            or ""
        )
        return {
            "display_name": display_name or f"{lat:.4f}, {lon:.4f}",
            "country": address.get("country", ""),
            "state": address.get("state", address.get("province", "")),
            "city": city,
            "district": district,
            "town": address.get("town", ""),
            "suburb": address.get("suburb", ""),
            "neighbourhood": address.get("neighbourhood", ""),
            "quarter": address.get("quarter", ""),
            "borough": address.get("borough", ""),
            "village": address.get("village", ""),
            "hamlet": address.get("hamlet", ""),
            "poi": (
                address.get("attraction")
                or address.get("building")
                or address.get("amenity")
                or address.get("leisure")
                or address.get("tourism")
                or address.get("shop")
                or ""
            ),
            "road": address.get("road", ""),
            "address": address,
            "lat": lat,
            "lon": lon,
        }

    def _select_locality_name(self, context: Dict[str, Any], radius_m: int) -> str:
        fine_grained = [
            context.get("poi"),
            context.get("road"),
            context.get("neighbourhood"),
            context.get("quarter"),
            context.get("suburb"),
            context.get("town"),
            context.get("village"),
            context.get("hamlet"),
        ]
        medium_grained = [
            context.get("suburb"),
            context.get("neighbourhood"),
            context.get("quarter"),
            context.get("town"),
            context.get("district"),
            context.get("village"),
        ]
        coarse_grained = [
            context.get("district"),
            context.get("suburb"),
            context.get("town"),
        ]
        candidates = fine_grained if radius_m <= 1800 else medium_grained if radius_m <= 8000 else coarse_grained
        for item in candidates:
            text = str(item or "").strip()
            if text:
                return text
        return ""

    def _join_place_tokens(self, *parts: Any) -> str:
        tokens: List[str] = []
        for part in parts:
            text = str(part or "").strip()
            if not text:
                continue
            if self._looks_like_coordinate_text(text):
                continue
            if any(text == existing or text in existing or existing in text for existing in tokens):
                if any(existing in text and existing != text for existing in tokens):
                    tokens = [existing for existing in tokens if existing not in text]
                    tokens.append(text)
                continue
            tokens.append(text)
        return "".join(tokens)

    def _display_name_to_place(self, display_name: str) -> str:
        if not display_name or self._looks_like_coordinate_text(display_name):
            return ""
        tokens: List[str] = []
        for raw in display_name.split(","):
            text = raw.strip()
            if not text or self._looks_like_coordinate_text(text):
                continue
            tokens.append(text)
            if len(tokens) >= 3:
                break
        if not tokens:
            return ""
        return "".join(tokens[:2]) if len(tokens) >= 2 else tokens[0]

    @staticmethod
    def _looks_like_coordinate_text(text: str) -> bool:
        value = str(text or "").strip()
        if not value:
            return True
        compact = value.replace(" ", "")
        if compact.count(",") == 1:
            left, right = compact.split(",", 1)
            if left.replace(".", "", 1).replace("-", "", 1).isdigit() and right.replace(".", "", 1).replace("-", "", 1).isdigit():
                return True
        return False

    def _collect_spatial_features(self, lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
        query = f"""
[out:json][timeout:25];
(
  nwr(around:{radius_m},{lat},{lon})[natural];
  nwr(around:{radius_m},{lat},{lon})[waterway];
  nwr(around:{radius_m},{lat},{lon})[landuse~"industrial|residential|commercial|retail|farmland|forest|reservoir|meadow|basin|farmyard"];
  nwr(around:{radius_m},{lat},{lon})[amenity~"wastewater_plant|hospital|school|university|marketplace|parking|bus_station|ferry_terminal|police|fire_station|townhall"];
  nwr(around:{radius_m},{lat},{lon})[man_made~"pier|breakwater|groyne"];
  nwr(around:{radius_m},{lat},{lon})[leisure];
  nwr(around:{radius_m},{lat},{lon})[tourism];
  nwr(around:{radius_m},{lat},{lon})[power="plant"];
  nwr(around:{radius_m},{lat},{lon})[building~"industrial|warehouse|commercial|retail"];
  nwr(around:{radius_m},{lat},{lon})[highway~"motorway|trunk|primary|secondary|tertiary|residential|pedestrian|service"];
  nwr(around:{radius_m},{lat},{lon})[public_transport];
  nwr(around:{radius_m},{lat},{lon})[railway~"station|halt|subway_entrance|tram_stop"];
  nwr(around:{radius_m},{lat},{lon})[shop~"mall|supermarket|convenience"];
  nwr(around:{radius_m},{lat},{lon})[office];
  nwr(around:{radius_m},{lat},{lon})[boundary="protected_area"];
);
out center tags;
"""
        payload = None
        last_error = None
        for endpoint in [
            "https://overpass-api.de/api/interpreter",
            "https://lz4.overpass-api.de/api/interpreter",
        ]:
            try:
                payload = _safe_http_json(
                    endpoint,
                    method="POST",
                    data=query,
                    headers={"Content-Type": "text/plain;charset=utf-8"},
                    timeout=30.0,
                )
                break
            except Exception as exc:
                last_error = exc
                logger.warning(f"Overpass fetch failed via {endpoint}: {exc}")
        if payload is None:
            if last_error:
                logger.warning(f"All Overpass endpoints failed, continuing with fallback features: {last_error}")
            return []

        elements = payload.get("elements") or []
        features: List[Dict[str, Any]] = []
        seen_ids = set()
        for element in elements:
            element_id = f"{element.get('type', 'item')}_{element.get('id')}"
            if element_id in seen_ids:
                continue
            seen_ids.add(element_id)
            tags = element.get("tags") or {}
            lat_value = element.get("lat")
            lon_value = element.get("lon")
            if lat_value is None or lon_value is None:
                center = element.get("center") or {}
                lat_value = center.get("lat")
                lon_value = center.get("lon")
            if lat_value is None or lon_value is None:
                continue

            classification = self._classify_feature(tags)
            if not classification:
                continue

            distance_m = round(_haversine_m(lat, lon, float(lat_value), float(lon_value)), 1)
            features.append(
                {
                    "feature_id": element_id,
                    "name": tags.get("name") or classification["default_name"],
                    "category": classification["category"],
                    "subtype": classification["subtype"],
                    "node_family": classification["node_family"],
                    "source_kind": "observed",
                    "lat": round(float(lat_value), 6),
                    "lon": round(float(lon_value), 6),
                    "distance_m": distance_m,
                    "importance": classification["importance"],
                    "summary": classification["summary"],
                    "tags": tags,
                    "confidence": classification["confidence"],
                }
            )

        features.sort(key=lambda item: (-item["importance"], item["distance_m"], item["name"]))

        selected: List[Dict[str, Any]] = []
        subtype_counts: Dict[str, int] = {}
        for feature in features:
            subtype = feature["subtype"]
            if subtype_counts.get(subtype, 0) >= 4:
                continue
            selected.append(feature)
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
            if len(selected) >= 28:
                break
        return selected

    def _collect_worldcover_features(
        self,
        *,
        lat: float,
        lon: float,
        radius_m: int,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
        bbox = _radius_to_bbox(lat, lon, radius_m)
        minx, miny = _lonlat_to_mercator(bbox["min_lon"], bbox["min_lat"])
        maxx, maxy = _lonlat_to_mercator(bbox["max_lon"], bbox["max_lat"])
        params = {
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetMap",
            "layers": "WORLDCOVER_2021_MAP",
            "srs": "EPSG:3857",
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "width": "256",
            "height": "256",
            "styles": "worldcover.txt",
            "format": "image/png",
            "transparent": "true",
            "time": "2021-12-31",
        }
        url = "https://services.terrascope.be/wms/v2?" + urllib.parse.urlencode(params)

        try:
            with urllib.request.urlopen(url, timeout=30.0) as response:
                image = Image.open(io.BytesIO(response.read())).convert("RGBA")
        except Exception as exc:
            logger.warning(f"WorldCover GetMap failed: {exc}")
            return [], {
                "status": "failed",
                "provider": "esa_worldcover",
                "product": "WorldCover 2021 v200",
                "error": str(exc),
                "note": "未能获取 WorldCover 遥感层，已退回 OSM 和上下文特征。",
            }, []

        sampled = image.resize((128, 128), resample=PIL_NEAREST)
        width, height = sampled.size
        grid: List[List[int]] = []
        class_pixel_counts: Dict[int, int] = {}

        for row in range(height):
            row_codes: List[int] = []
            for col in range(width):
                rgba = sampled.getpixel((col, row))
                code = self._match_worldcover_class(rgba[:3], alpha=rgba[3])
                row_codes.append(code)
                if code:
                    class_pixel_counts[code] = class_pixel_counts.get(code, 0) + 1
            grid.append(row_codes)

        visited = [[False for _ in range(width)] for _ in range(height)]
        min_component_pixels = max(10, int(width * height * 0.0015))
        components_by_code: Dict[int, List[Dict[str, Any]]] = {}

        for row in range(height):
            for col in range(width):
                code = grid[row][col]
                if code == 0 or visited[row][col]:
                    continue
                queue = [(row, col)]
                visited[row][col] = True
                pixels = []
                min_row = max_row = row
                min_col = max_col = col
                sum_row = 0
                sum_col = 0

                while queue:
                    current_row, current_col = queue.pop()
                    pixels.append((current_row, current_col))
                    sum_row += current_row
                    sum_col += current_col
                    min_row = min(min_row, current_row)
                    max_row = max(max_row, current_row)
                    min_col = min(min_col, current_col)
                    max_col = max(max_col, current_col)

                    for next_row, next_col in [
                        (current_row - 1, current_col),
                        (current_row + 1, current_col),
                        (current_row, current_col - 1),
                        (current_row, current_col + 1),
                    ]:
                        if next_row < 0 or next_row >= height or next_col < 0 or next_col >= width:
                            continue
                        if visited[next_row][next_col] or grid[next_row][next_col] != code:
                            continue
                        visited[next_row][next_col] = True
                        queue.append((next_row, next_col))

                if len(pixels) < min_component_pixels:
                    continue

                components_by_code.setdefault(code, []).append(
                    {
                        "pixel_count": len(pixels),
                        "min_row": min_row,
                        "max_row": max_row,
                        "min_col": min_col,
                        "max_col": max_col,
                        "centroid_row": sum_row / len(pixels),
                        "centroid_col": sum_col / len(pixels),
                    }
                )

        detected_features: List[Dict[str, Any]] = []
        remote_layers: List[Dict[str, Any]] = []
        total_detected_pixels = sum(class_pixel_counts.values()) or 1

        for code, components in components_by_code.items():
            class_meta = WORLD_COVER_CLASSES.get(code)
            if not class_meta:
                continue
            components.sort(key=lambda item: item["pixel_count"], reverse=True)
            layer_features = []

            for index, component in enumerate(components[:2], start=1):
                centroid_lon, centroid_lat = self._pixel_to_lonlat(
                    component["centroid_col"],
                    component["centroid_row"],
                    width=width,
                    height=height,
                    minx=minx,
                    miny=miny,
                    maxx=maxx,
                    maxy=maxy,
                )
                geometry = self._component_bbox_geometry(
                    component=component,
                    width=width,
                    height=height,
                    minx=minx,
                    miny=miny,
                    maxx=maxx,
                    maxy=maxy,
                )
                share = round(component["pixel_count"] / total_detected_pixels * 100, 2)
                feature_id = f"worldcover_{code}_{index}"
                summary = (
                    f"基于 ESA WorldCover 2021 10m 土地覆盖图识别出的{class_meta['name_zh']}斑块，"
                    f"约占分析范围像元的 {share}% 。"
                )
                detected_features.append(
                    {
                        "feature_id": feature_id,
                        "name": f"{class_meta['name_zh']}斑块 {index}",
                        "category": class_meta["category"],
                        "subtype": f"worldcover_{code}",
                        "node_family": class_meta["node_family"],
                        "source_kind": "detected",
                        "lat": round(centroid_lat, 6),
                        "lon": round(centroid_lon, 6),
                        "distance_m": round(_haversine_m(lat, lon, centroid_lat, centroid_lon), 1),
                        "importance": class_meta["importance"],
                        "summary": summary,
                        "geometry": geometry,
                        "tags": {
                            "provider": "esa_worldcover",
                            "product": "WorldCover 2021 v200",
                            "class_code": code,
                            "class_name": class_meta["name"],
                            "class_name_zh": class_meta["name_zh"],
                            "pixel_share_pct": share,
                        },
                        "confidence": 0.78,
                    }
                )
                layer_features.append(
                    {
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": {
                            "name": f"{class_meta['name_zh']}斑块 {index}",
                            "color": self._rgb_to_hex(class_meta["color"]),
                            "pixel_share_pct": share,
                            "class_code": code,
                            "class_name": class_meta["name_zh"],
                        },
                    }
                )

            if layer_features:
                remote_layers.append(
                    {
                        "id": f"worldcover_{code}",
                        "name": f"遥感 {class_meta['name_zh']}",
                        "type": "geojson",
                        "color": self._rgb_to_hex(class_meta["color"]),
                        "visible": True,
                        "note": "ESA WorldCover 2021 v200 遥感识别结果",
                        "data": {
                            "type": "FeatureCollection",
                            "features": layer_features,
                        },
                    }
                )

        detected_classes = [
            {
                "code": code,
                "name": WORLD_COVER_CLASSES[code]["name"],
                "name_zh": WORLD_COVER_CLASSES[code]["name_zh"],
                "pixel_share_pct": round(class_pixel_counts[code] / total_detected_pixels * 100, 2),
            }
            for code in sorted(class_pixel_counts)
            if code in WORLD_COVER_CLASSES
        ]
        remote_summary = {
            "status": "completed" if detected_features else "empty",
            "provider": "esa_worldcover",
            "product": "WorldCover 2021 v200",
            "mode": "wms_classified_png_sampling",
            "detected_features_count": len(detected_features),
            "detected_classes": detected_classes,
            "note": "基于 ESA WorldCover 2021 年度土地覆盖图识别，属于卫星派生地表分类，不是实时影像解译。",
        }
        return detected_features, remote_summary, remote_layers

    def _match_worldcover_class(self, rgb: Tuple[int, int, int], *, alpha: int) -> int:
        if alpha == 0:
            return 0
        best_code = 0
        best_distance = float("inf")
        for code, meta in WORLD_COVER_CLASSES.items():
            distance = sum((rgb[index] - meta["color"][index]) ** 2 for index in range(3))
            if distance < best_distance:
                best_distance = distance
                best_code = code
        return best_code if best_distance <= 6400 else 0

    def _pixel_to_lonlat(
        self,
        col: float,
        row: float,
        *,
        width: int,
        height: int,
        minx: float,
        miny: float,
        maxx: float,
        maxy: float,
    ) -> Tuple[float, float]:
        mercator_x = minx + ((col + 0.5) / width) * (maxx - minx)
        mercator_y = maxy - ((row + 0.5) / height) * (maxy - miny)
        return _mercator_to_lonlat(mercator_x, mercator_y)

    def _component_bbox_geometry(
        self,
        *,
        component: Dict[str, Any],
        width: int,
        height: int,
        minx: float,
        miny: float,
        maxx: float,
        maxy: float,
    ) -> Dict[str, Any]:
        left_x = minx + (component["min_col"] / width) * (maxx - minx)
        right_x = minx + ((component["max_col"] + 1) / width) * (maxx - minx)
        top_y = maxy - (component["min_row"] / height) * (maxy - miny)
        bottom_y = maxy - ((component["max_row"] + 1) / height) * (maxy - miny)

        min_lon, max_lat = _mercator_to_lonlat(left_x, top_y)
        max_lon, min_lat = _mercator_to_lonlat(right_x, bottom_y)
        coordinates = [
            [round(min_lon, 6), round(min_lat, 6)],
            [round(max_lon, 6), round(min_lat, 6)],
            [round(max_lon, 6), round(max_lat, 6)],
            [round(min_lon, 6), round(max_lat, 6)],
            [round(min_lon, 6), round(min_lat, 6)],
        ]
        return {"type": "Polygon", "coordinates": [coordinates]}

    def _rgb_to_hex(self, rgb: Tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _merge_context_features(
        self,
        *,
        features: List[Dict[str, Any]],
        lat: float,
        lon: float,
        admin_context: Dict[str, Any],
        environment_baseline: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        merged = list(features)
        existing_ids = {item["feature_id"] for item in merged}
        existing_subtypes = {item["subtype"] for item in merged}
        current = environment_baseline.get("current") or {}

        def add_feature(feature: Dict[str, Any]) -> None:
            if feature["feature_id"] in existing_ids:
                return
            merged.append(feature)
            existing_ids.add(feature["feature_id"])
            existing_subtypes.add(feature["subtype"])

        if any(current.get(key) is not None for key in ["temperature_2m", "wind_speed_10m", "precipitation"]) and "weather_baseline" not in existing_subtypes:
            summary_bits = []
            if current.get("temperature_2m") is not None:
                summary_bits.append(f"气温 {current['temperature_2m']}°C")
            if current.get("precipitation") is not None:
                summary_bits.append(f"降水 {current['precipitation']} mm")
            if current.get("wind_speed_10m") is not None:
                summary_bits.append(f"风速 {current['wind_speed_10m']} m/s")
            add_feature(
                {
                    "feature_id": "context_weather_baseline",
                    "name": "局地天气基线",
                    "category": "ecology",
                    "subtype": "weather_baseline",
                    "node_family": "EnvironmentalCarrier",
                    "source_kind": "observed",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "distance_m": 0.0,
                    "importance": 6,
                    "summary": "来自 Open-Meteo 的局地天气基线。" + (" " + "，".join(summary_bits) if summary_bits else ""),
                    "tags": {"provider": "open-meteo"},
                    "confidence": 0.83,
                }
            )

        if admin_context.get("road") and not (existing_subtypes & {"road_corridor", "transit_stop", "rail_station"}):
            add_feature(
                {
                    "feature_id": "context_primary_road",
                    "name": admin_context["road"],
                    "category": "facility",
                    "subtype": "road_corridor",
                    "node_family": "Infrastructure",
                    "source_kind": "observed",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "distance_m": 0.0,
                    "importance": 6,
                    "summary": "来自逆地理编码的主要道路上下文，可作为人类活动与交通暴露的空间锚点。",
                    "tags": {"provider": "reverse_geocode", "road": admin_context["road"]},
                    "confidence": 0.78,
                }
            )

        merged.sort(key=lambda item: (-item["importance"], item["distance_m"], item["name"]))
        return merged

    def _classify_feature(self, tags: Dict[str, str]) -> Optional[Dict[str, Any]]:
        natural = tags.get("natural", "")
        waterway = tags.get("waterway", "")
        landuse = tags.get("landuse", "")
        amenity = tags.get("amenity", "")
        leisure = tags.get("leisure", "")
        tourism = tags.get("tourism", "")
        man_made = tags.get("man_made", "")
        power = tags.get("power", "")
        building = tags.get("building", "")
        boundary = tags.get("boundary", "")
        highway = tags.get("highway", "")
        public_transport = tags.get("public_transport", "")
        railway = tags.get("railway", "")
        shop = tags.get("shop", "")
        office = tags.get("office", "")

        if natural in {"water", "wetland", "wood", "beach", "grassland", "scrub", "heath", "sand"}:
            subtype = natural
            node_family = "EnvironmentalCarrier" if subtype in {"water"} else "EcologicalReceptor"
            summary = f"OSM 标记为 natural={natural}。"
            return {
                "category": "ecology",
                "subtype": subtype,
                "node_family": node_family,
                "importance": 7,
                "confidence": 0.86,
                "summary": summary,
                "default_name": f"{subtype} patch",
            }
        if natural == "coastline" or man_made in {"breakwater", "groyne"}:
            return {
                "category": "ecology",
                "subtype": natural or man_made,
                "node_family": "EnvironmentalCarrier",
                "importance": 8,
                "confidence": 0.84,
                "summary": "近岸边界或海岸防护要素。",
                "default_name": "Coastal edge",
            }
        if waterway:
            return {
                "category": "ecology",
                "subtype": waterway,
                "node_family": "EnvironmentalCarrier",
                "importance": 8,
                "confidence": 0.88,
                "summary": f"OSM 水系要素 waterway={waterway}。",
                "default_name": f"{waterway} segment",
            }
        if landuse in {"industrial", "commercial", "residential", "retail", "farmland", "forest", "reservoir", "meadow", "basin", "farmyard"}:
            if landuse in {"industrial", "commercial", "residential", "retail", "farmyard"}:
                category = "facility"
                node_family = "Infrastructure"
            elif landuse in {"reservoir", "basin"}:
                category = "ecology"
                node_family = "EnvironmentalCarrier"
            else:
                category = "ecology"
                node_family = "EcologicalReceptor"
            return {
                "category": category,
                "subtype": landuse,
                "node_family": node_family,
                "importance": 6,
                "confidence": 0.8,
                "summary": f"OSM 用地分类 landuse={landuse}。",
                "default_name": f"{landuse} area",
            }
        if amenity in {"wastewater_plant", "hospital", "school", "university", "marketplace", "parking", "bus_station", "ferry_terminal", "police", "fire_station", "townhall"}:
            return {
                "category": "facility",
                "subtype": amenity,
                "node_family": "Infrastructure",
                "importance": 7,
                "confidence": 0.83,
                "summary": f"公共设施 amenity={amenity}。",
                "default_name": amenity.replace("_", " "),
            }
        if leisure in {"park", "nature_reserve", "marina", "garden", "playground"}:
            category = "ecology" if leisure in {"park", "nature_reserve", "garden"} else "facility"
            node_family = "EcologicalReceptor" if category == "ecology" else "Infrastructure"
            return {
                "category": category,
                "subtype": leisure,
                "node_family": node_family,
                "importance": 7,
                "confidence": 0.8,
                "summary": f"OSM leisure={leisure}。",
                "default_name": leisure.replace("_", " "),
            }
        if tourism:
            return {
                "category": "facility",
                "subtype": tourism,
                "node_family": "Infrastructure",
                "importance": 5,
                "confidence": 0.74,
                "summary": f"旅游相关要素 tourism={tourism}。",
                "default_name": tourism.replace("_", " "),
            }
        if man_made == "pier":
            return {
                "category": "facility",
                "subtype": "pier",
                "node_family": "Infrastructure",
                "importance": 8,
                "confidence": 0.86,
                "summary": "码头或栈桥设施。",
                "default_name": "Pier",
            }
        if power == "plant" or building in {"industrial", "warehouse"}:
            subtype = "power_plant" if power == "plant" else building
            return {
                "category": "facility",
                "subtype": subtype,
                "node_family": "Infrastructure",
                "importance": 7,
                "confidence": 0.78,
                "summary": "工业或能源相关设施。",
                "default_name": subtype.replace("_", " "),
            }
        if building in {"commercial", "retail"}:
            return {
                "category": "facility",
                "subtype": "commercial_hub",
                "node_family": "Infrastructure",
                "importance": 5,
                "confidence": 0.72,
                "summary": f"建筑类型 building={building}，可视为商业活动载体。",
                "default_name": f"{building} building",
            }
        if public_transport in {"station", "stop_position", "platform"} or railway in {"station", "halt", "subway_entrance", "tram_stop"}:
            subtype = "rail_station" if railway in {"station", "halt", "subway_entrance", "tram_stop"} else "transit_stop"
            return {
                "category": "facility",
                "subtype": subtype,
                "node_family": "Infrastructure",
                "importance": 6,
                "confidence": 0.79,
                "summary": "公共交通节点，可作为人类活动和移动性的空间锚点。",
                "default_name": "Transit node",
            }
        if highway in {"motorway", "trunk", "primary", "secondary", "tertiary", "residential", "pedestrian", "service"}:
            return {
                "category": "facility",
                "subtype": "road_corridor",
                "node_family": "Infrastructure",
                "importance": 5,
                "confidence": 0.76,
                "summary": f"交通廊道 highway={highway}。",
                "default_name": f"{highway} corridor",
            }
        if shop in {"mall", "supermarket", "convenience"} or office:
            subtype = "commercial_hub" if shop else "office_cluster"
            return {
                "category": "facility",
                "subtype": subtype,
                "node_family": "Infrastructure",
                "importance": 5,
                "confidence": 0.74,
                "summary": "商业或办公活动节点。",
                "default_name": (shop or office).replace("_", " "),
            }
        if boundary == "protected_area":
            return {
                "category": "ecology",
                "subtype": "protected_area",
                "node_family": "Region",
                "importance": 9,
                "confidence": 0.9,
                "summary": "保护地边界相关区域。",
                "default_name": "Protected area",
            }
        return None

    def _build_environment_baseline(self, lat: float, lon: float, admin_context: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "latitude": f"{lat:.6f}",
            "longitude": f"{lon:.6f}",
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m",
                "wind_direction_10m",
                "weather_code",
            ],
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
            ],
            "forecast_days": 3,
            "timezone": "auto",
        }
        query = urllib.parse.urlencode(
            {
                "latitude": params["latitude"],
                "longitude": params["longitude"],
                "current": ",".join(params["current"]),
                "daily": ",".join(params["daily"]),
                "forecast_days": params["forecast_days"],
                "timezone": params["timezone"],
            }
        )
        try:
            payload = _safe_http_json(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=20.0)
        except Exception as exc:
            logger.warning(f"Open-Meteo fetch failed: {exc}")
            payload = {}

        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        return {
            "provider": "open-meteo",
            "location": admin_context.get("display_name") or f"{lat:.4f}, {lon:.4f}",
            "current": {
                "temperature_2m": current.get("temperature_2m"),
                "relative_humidity_2m": current.get("relative_humidity_2m"),
                "precipitation": current.get("precipitation"),
                "wind_speed_10m": current.get("wind_speed_10m"),
                "wind_direction_10m": current.get("wind_direction_10m"),
                "weather_code": current.get("weather_code"),
            },
            "daily": {
                "temperature_2m_max": (daily.get("temperature_2m_max") or [None])[0],
                "temperature_2m_min": (daily.get("temperature_2m_min") or [None])[0],
                "precipitation_sum": (daily.get("precipitation_sum") or [None])[0],
                "wind_speed_10m_max": (daily.get("wind_speed_10m_max") or [None])[0],
            },
        }

    def _classify_scene(self, features: List[Dict[str, Any]], admin_context: Dict[str, Any]) -> Dict[str, Any]:
        scores = {
            "coastal": 0,
            "inland_water": 0,
            "wetland": 0,
            "urban_edge": 0,
            "agricultural": 0,
            "mixed": 1,
        }
        for feature in features:
            subtype = feature["subtype"]
            if subtype in {"beach", "coastline", "pier", "marina", "breakwater", "groyne"}:
                scores["coastal"] += 3
            if subtype in {"river", "stream", "canal", "ditch", "water", "reservoir", "basin", "worldcover_80"}:
                scores["inland_water"] += 2
            if subtype in {"wetland", "worldcover_90", "worldcover_95"}:
                scores["wetland"] += 4
            if subtype in {"industrial", "commercial", "residential", "hospital", "school", "university", "worldcover_50"}:
                scores["urban_edge"] += 2
            if subtype in {"farmland", "farmyard", "meadow", "worldcover_40"}:
                scores["agricultural"] += 3

        title = max(scores.items(), key=lambda item: item[1])[0]
        return {
            "primary_scene": title,
            "scores": scores,
            "reasoning": (
                f"Based on nearby OSM features around {admin_context.get('display_name', 'selected area')}, "
                f"the strongest spatial signature is {title}."
            ),
        }

    def _build_graph(
        self,
        *,
        seed: Dict[str, Any],
        aoi: Dict[str, Any],
        admin_context: Dict[str, Any],
        features: List[Dict[str, Any]],
        environment_baseline: Dict[str, Any],
        scene_classification: Dict[str, Any],
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        center = aoi["center"]
        region_id = f"region_{_slugify(admin_context.get('city') or admin_context.get('display_name') or seed['seed_id'])}"
        region_node = self._make_graph_node(
            node_id=region_id,
            name=admin_context.get("city") or admin_context.get("display_name") or "Selected region",
            label="Region",
            summary=(
                f"中心点 ({center['lat']}, {center['lon']}) 周边 {aoi['radius_m']} 米分析范围，"
                f"场景类型倾向为 {scene_classification['primary_scene']}。"
            ),
            lat=center["lat"],
            lon=center["lon"],
            source_kind="observed",
            confidence=0.95,
            attributes={
                "category": "region",
                "scene_type": scene_classification["primary_scene"],
                "radius_m": aoi["radius_m"],
                "admin_context": admin_context,
                "environment_baseline": environment_baseline,
            },
        )
        nodes.append(region_node)

        feature_nodes: List[Dict[str, Any]] = []
        for feature in features[:18]:
            label = feature["node_family"]
            feature_node = self._make_graph_node(
                node_id=f"feature_{feature['feature_id']}",
                name=feature["name"],
                label=label,
                summary=f"{feature['summary']} 距中心点约 {feature['distance_m']} 米。",
                lat=feature["lat"],
                lon=feature["lon"],
                source_kind=feature["source_kind"],
                confidence=feature["confidence"],
                attributes={
                    "category": feature["category"],
                    "subtype": feature["subtype"],
                    "distance_m": feature["distance_m"],
                    "importance": feature["importance"],
                    "tags": feature["tags"],
                    "evidence_summary": feature["summary"],
                },
            )
            feature_nodes.append(feature_node)
            nodes.append(feature_node)
            edges.append(
                self._make_graph_edge(
                    edge_id=f"edge_{region_id}_{feature_node['uuid']}",
                    source=region_id,
                    target=feature_node["uuid"],
                    relation="located_in",
                    fact=f"{feature_node['name']} 位于选定分析区域内。",
                )
            )

        proxy_nodes, proxy_edges = self._build_human_proxy_nodes(
            seed=seed,
            admin_context=admin_context,
            scene_classification=scene_classification,
            feature_nodes=feature_nodes,
            center=center,
        )
        nodes.extend(proxy_nodes)
        edges.extend(proxy_edges)

        feature_node_map = {node["uuid"]: node for node in feature_nodes}
        ecology_nodes = [
            node
            for node in feature_nodes
            if node["attributes"].get("category") == "ecology"
            and node["attributes"].get("subtype") != "weather_baseline"
        ]
        facility_nodes = [node for node in feature_nodes if node["attributes"].get("category") == "facility"]

        for node in facility_nodes:
            nearby_ecology = self._nearest_nodes(node, ecology_nodes, max_distance_m=850, limit=2)
            for ecology in nearby_ecology:
                edges.append(
                    self._make_graph_edge(
                        edge_id=f"edge_affect_{node['uuid']}_{ecology['uuid']}",
                        source=node["uuid"],
                        target=ecology["uuid"],
                        relation="affects",
                        fact=f"{node['name']} 与 {ecology['name']} 空间上接近，可能形成环境影响链。",
                        confidence=0.66,
                    )
                )

        llm_edges = self._llm_refine_graph(
            seed=seed,
            admin_context=admin_context,
            scene_classification=scene_classification,
            feature_nodes=feature_nodes,
            proxy_nodes=proxy_nodes,
        )
        if llm_edges:
            edges.extend(llm_edges)

        graph_data = self._to_graph_panel_data(nodes, edges)
        return {
            "seed_id": seed["seed_id"],
            "generated_at": _utcnow_iso(),
            "nodes": nodes,
            "edges": edges,
            "graph_data": graph_data,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "observed_nodes": len([node for node in nodes if node["attributes"]["source_kind"] == "observed"]),
                "detected_nodes": len([node for node in nodes if node["attributes"]["source_kind"] == "detected"]),
                "inferred_nodes": len([node for node in nodes if node["attributes"]["source_kind"] == "inferred"]),
            },
        }

    def _build_human_proxy_nodes(
        self,
        *,
        seed: Dict[str, Any],
        admin_context: Dict[str, Any],
        scene_classification: Dict[str, Any],
        feature_nodes: List[Dict[str, Any]],
        center: Dict[str, float],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        observed_subtypes = {node["attributes"].get("subtype") for node in feature_nodes}
        proxies: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        def nearest_anchor(candidates: Iterable[Dict[str, Any]]) -> Tuple[float, float, Optional[str]]:
            nearest = None
            best_distance = float("inf")
            for candidate in candidates:
                lat_value = candidate["attributes"].get("lat")
                lon_value = candidate["attributes"].get("lon")
                if lat_value is None or lon_value is None:
                    continue
                distance = _haversine_m(center["lat"], center["lon"], lat_value, lon_value)
                if distance < best_distance:
                    best_distance = distance
                    nearest = candidate
            if nearest:
                return float(nearest["attributes"]["lat"]), float(nearest["attributes"]["lon"]), nearest["uuid"]
            return center["lat"], center["lon"], None

        proxy_specs = []
        if observed_subtypes & {"residential", "commercial", "commercial_hub", "office_cluster", "hospital", "school", "university", "road_corridor", "transit_stop", "rail_station", "worldcover_50"}:
            proxy_specs.append(
                {
                    "key": "residents",
                    "name": f"{admin_context.get('district') or admin_context.get('city') or '周边'}居民群体",
                    "label": "HumanActor",
                    "summary": "围绕居住、通勤与日常公共服务活动形成的居民代理群体。",
                    "anchors": [node for node in feature_nodes if node["attributes"].get("subtype") in {"residential", "commercial", "commercial_hub", "office_cluster", "hospital", "school", "university", "road_corridor", "transit_stop", "rail_station", "worldcover_50"}],
                    "targets": {"depends_on": {"residential", "commercial_hub", "road_corridor", "transit_stop", "water", "park", "worldcover_50"}, "affected_by": {"industrial", "wastewater_plant", "reservoir"}},
                }
            )
        if observed_subtypes & {"industrial", "farmyard", "farmland", "pier", "marina", "power_plant", "warehouse", "commercial_hub", "office_cluster", "road_corridor", "transit_stop", "rail_station", "worldcover_50"}:
            proxy_specs.append(
                {
                    "key": "operators",
                    "name": "生产者/经营者群体",
                    "label": "OrganizationActor",
                    "summary": "围绕生产、运输、经营和基础设施运维活动形成的代理主体。",
                    "anchors": [node for node in feature_nodes if node["attributes"].get("subtype") in {"industrial", "farmyard", "farmland", "pier", "marina", "power_plant", "warehouse", "commercial_hub", "office_cluster", "road_corridor", "transit_stop", "rail_station", "worldcover_50"}],
                    "targets": {"uses": {"industrial", "farmland", "pier", "marina", "power_plant", "commercial_hub", "road_corridor", "transit_stop"}, "affects": {"water", "wetland", "reservoir"}},
                }
            )
        if observed_subtypes & {"beach", "park", "garden", "tourism", "marina", "commercial_hub", "transit_stop", "rail_station", "worldcover_50"}:
            proxy_specs.append(
                {
                    "key": "visitors",
                    "name": "游客/访客群体",
                    "label": "HumanActor",
                    "summary": "围绕滨水休闲、旅游与短时访问活动形成的代理群体。",
                    "anchors": [node for node in feature_nodes if node["attributes"].get("subtype") in {"beach", "park", "garden", "marina", "commercial_hub", "transit_stop", "rail_station", "worldcover_50"} or node["attributes"].get("category") == "facility"],
                    "targets": {"uses": {"beach", "park", "garden", "marina", "commercial_hub"}, "depends_on": {"commercial", "commercial_hub", "pier", "transit_stop", "rail_station"}},
                }
            )

        proxy_specs.append(
            {
                "key": "regulators",
                "name": f"{admin_context.get('city') or admin_context.get('state') or '区域'}监管主体",
                "label": "GovernmentActor",
                "summary": "对生态保护、设施运维、风险处置与信息发布负有职责的代理监管主体。",
                "anchors": feature_nodes,
                "targets": {"regulates": {"industrial", "wastewater_plant", "protected_area", "reservoir", "pier", "road_corridor", "transit_stop", "rail_station"}},
            }
        )
        if observed_subtypes & {"park", "nature_reserve", "garden", "wastewater_plant", "reservoir", "wetland", "road_corridor", "transit_stop", "worldcover_90", "worldcover_95"}:
            proxy_specs.append(
                {
                    "key": "maintainers",
                    "name": "治理/维护主体",
                    "label": "OrganizationActor",
                    "summary": "承担生态修复、设施维护、巡护或运营维护的代理主体。",
                    "anchors": [node for node in feature_nodes if node["attributes"].get("subtype") in {"park", "nature_reserve", "garden", "wastewater_plant", "reservoir", "wetland", "road_corridor", "transit_stop", "worldcover_90", "worldcover_95"}],
                    "targets": {"maintains": {"park", "nature_reserve", "garden", "wastewater_plant", "reservoir", "wetland", "road_corridor", "transit_stop", "worldcover_90", "worldcover_95"}},
                }
            )

        if observed_subtypes & {"water", "wetland", "industrial", "wastewater_plant", "reservoir", "coastline", "road_corridor", "transit_stop", "weather_baseline", "worldcover_80", "worldcover_90", "worldcover_95"}:
            proxy_specs.append(
                {
                    "key": "vulnerable_groups",
                    "name": "脆弱群体",
                    "label": "HumanActor",
                    "summary": "在暴露、通达性或生计依赖上更容易受到环境变化影响的代理群体。",
                    "anchors": feature_nodes,
                    "targets": {"exposed_to": {"water", "wetland", "industrial", "wastewater_plant", "coastline", "road_corridor", "weather_baseline", "worldcover_80", "worldcover_90", "worldcover_95"}},
                }
            )

        feature_lookup = {node["attributes"].get("subtype"): [] for node in feature_nodes}
        for node in feature_nodes:
            feature_lookup.setdefault(node["attributes"].get("subtype"), []).append(node)

        for spec in proxy_specs:
            lat_value, lon_value, anchor_id = nearest_anchor(spec["anchors"])
            proxy_node = self._make_graph_node(
                node_id=f"proxy_{_slugify(spec['key'])}",
                name=spec["name"],
                label=spec["label"],
                summary=spec["summary"],
                lat=lat_value,
                lon=lon_value,
                source_kind="inferred",
                confidence=0.64 if spec["key"] != "regulators" else 0.72,
                attributes={
                    "category": "human_proxy",
                    "proxy_role": spec["key"],
                    "scene_type": scene_classification["primary_scene"],
                    "anchor_node_id": anchor_id,
                    "inference_reason": spec["summary"],
                },
            )
            proxies.append(proxy_node)
            if anchor_id:
                edges.append(
                    self._make_graph_edge(
                        edge_id=f"edge_anchor_{proxy_node['uuid']}_{anchor_id}",
                        source=proxy_node["uuid"],
                        target=anchor_id,
                        relation="anchored_to",
                        fact=f"{proxy_node['name']} 锚定到附近空间要素以便地图定位。",
                        confidence=0.7,
                    )
                )

            for relation, subtype_targets in spec["targets"].items():
                matched_targets = [node for node in feature_nodes if node["attributes"].get("subtype") in subtype_targets]
                for target in self._nearest_nodes(proxy_node, matched_targets, max_distance_m=1200, limit=2):
                    edges.append(
                        self._make_graph_edge(
                            edge_id=f"edge_{relation}_{proxy_node['uuid']}_{target['uuid']}",
                            source=proxy_node["uuid"],
                            target=target["uuid"],
                            relation=relation,
                            fact=f"{proxy_node['name']} 与 {target['name']} 之间形成 {relation} 关系。",
                            confidence=0.63,
                        )
                    )

        return proxies, edges

    def _nearest_nodes(
        self,
        source_node: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        *,
        max_distance_m: float,
        limit: int,
    ) -> List[Dict[str, Any]]:
        source_lat = source_node["attributes"].get("lat")
        source_lon = source_node["attributes"].get("lon")
        if source_lat is None or source_lon is None:
            return []
        ranked = []
        for candidate in candidates:
            candidate_lat = candidate["attributes"].get("lat")
            candidate_lon = candidate["attributes"].get("lon")
            if candidate_lat is None or candidate_lon is None:
                continue
            distance = _haversine_m(float(source_lat), float(source_lon), float(candidate_lat), float(candidate_lon))
            if distance <= max_distance_m:
                ranked.append((distance, candidate))
        ranked.sort(key=lambda item: item[0])
        return [item[1] for item in ranked[:limit]]

    def _llm_refine_graph(
        self,
        *,
        seed: Dict[str, Any],
        admin_context: Dict[str, Any],
        scene_classification: Dict[str, Any],
        feature_nodes: List[Dict[str, Any]],
        proxy_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not self._llm_client:
            return []

        feature_summary = [
            {
                "id": node["uuid"],
                "name": node["name"],
                "label": [item for item in node["labels"] if item not in {"Entity", "Node"}][0],
                "subtype": node["attributes"].get("subtype"),
                "distance_m": node["attributes"].get("distance_m"),
            }
            for node in feature_nodes[:10]
        ]
        proxy_summary = [
            {
                "id": node["uuid"],
                "name": node["name"],
                "label": [item for item in node["labels"] if item not in {"Entity", "Node"}][0],
                "proxy_role": node["attributes"].get("proxy_role"),
            }
            for node in proxy_nodes
        ]
        prompt = {
            "task": "Add at most 6 plausible semantic relations between proxy actors and nearby observed spatial nodes.",
            "area": admin_context.get("display_name"),
            "scene_type": scene_classification.get("primary_scene"),
            "simulation_requirement": seed.get("input", {}).get("simulation_requirement", ""),
            "observed_nodes": feature_summary,
            "proxy_nodes": proxy_summary,
            "rules": [
                "Only use node ids from the provided lists.",
                "Only return relations if a clear, explainable connection exists.",
                "Prefer depends_on, uses, regulates, affects, exposed_to, monitors.",
                "Do not invent new nodes.",
            ],
            "output_schema": {
                "edges": [
                    {
                        "source": "proxy_node_id",
                        "target": "observed_node_id",
                        "relation": "depends_on",
                        "fact": "short explanation",
                        "confidence": 0.6,
                    }
                ]
            },
        }
        try:
            response = self._llm_client.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "You return compact JSON with only explainable graph edges.",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=1200,
            )
        except Exception as exc:
            logger.warning(f"Map graph LLM refinement failed: {exc}")
            return []

        observed_ids = {node["uuid"] for node in feature_nodes}
        proxy_ids = {node["uuid"] for node in proxy_nodes}
        edges = []
        for index, item in enumerate(response.get("edges") or []):
            source = item.get("source")
            target = item.get("target")
            if source not in proxy_ids or target not in observed_ids:
                continue
            relation = str(item.get("relation") or "").strip() or "depends_on"
            edges.append(
                self._make_graph_edge(
                    edge_id=f"edge_llm_{index}_{source}_{target}",
                    source=source,
                    target=target,
                    relation=relation,
                    fact=str(item.get("fact") or "LLM 依据空间事实补充的代理关系。"),
                    confidence=max(0.45, min(0.75, float(item.get("confidence") or 0.58))),
                )
            )
        return edges[:6]

    def _build_report(
        self,
        *,
        seed: Dict[str, Any],
        aoi: Dict[str, Any],
        admin_context: Dict[str, Any],
        features: List[Dict[str, Any]],
        environment_baseline: Dict[str, Any],
        scene_classification: Dict[str, Any],
        graph: Dict[str, Any],
    ) -> str:
        center = aoi["center"]
        top_features = features[:8]
        feature_lines = [
            f"- {item['name']} ({item['subtype']}, {item['distance_m']}m, {item['source_kind']})"
            for item in top_features
        ]
        proxy_lines = [
            f"- {node['name']} ({node['attributes'].get('proxy_role')}, {node['attributes'].get('source_kind')})"
            for node in graph["nodes"]
            if node["attributes"].get("category") == "human_proxy"
        ]
        weather = environment_baseline.get("current") or {}
        title = seed.get("title") or "Map Seed Report"
        requirement = seed.get("input", {}).get("simulation_requirement") or "未提供额外模拟需求。"
        return "\n".join(
            [
                f"# {title}",
                "",
                "## 1. 选点概览",
                f"- 中心点: {center['lat']}, {center['lon']}",
                f"- 分析半径: {aoi['radius_m']} 米",
                f"- 行政与地点描述: {admin_context.get('display_name')}",
                f"- 场景类型判定: {scene_classification.get('primary_scene')}",
                "",
                "## 2. 环境基线",
                f"- 当前温度: {weather.get('temperature_2m', 'n/a')}",
                f"- 当前湿度: {weather.get('relative_humidity_2m', 'n/a')}",
                f"- 当前降水: {weather.get('precipitation', 'n/a')}",
                f"- 当前风速: {weather.get('wind_speed_10m', 'n/a')}",
                "",
                "## 3. 观测到的关键空间节点",
                *(feature_lines or ["- 当前公开空间数据未返回足够要素。"]),
                "",
                "## 4. 推断的人类代理节点",
                *(proxy_lines or ["- 当前基于空间事实未推断出代理主体。"]),
                "",
                "## 5. 推演需求",
                requirement,
                "",
                "## 6. 说明",
                "- observed 节点来自公开空间要素。",
                "- detected 节点来自 ESA WorldCover 2021 卫星派生土地覆盖识别。",
                "- inferred 节点来自规则与 LLM 约束推断，不代表真实具名主体。",
                "- 当前遥感层是年度土地覆盖产品，不是实时卫星图像解译。",
            ]
        )

    def _build_summary(
        self,
        admin_context: Dict[str, Any],
        scene_classification: Dict[str, Any],
        graph: Dict[str, Any],
    ) -> Dict[str, str]:
        place = admin_context.get("city") or admin_context.get("display_name") or "选定区域"
        scene = scene_classification.get("primary_scene") or "mixed"
        stats = graph.get("stats") or {}
        title = f"{place} · {scene} map seed"
        summary = (
            f"基于公开空间数据与卫星派生土地覆盖为 {place} 生成 {scene} 场景地图图谱，"
            f"共 {stats.get('node_count', 0)} 个节点、{stats.get('edge_count', 0)} 条边。"
        )
        return {"title": title, "summary": summary}

    def _build_layers_payload(
        self,
        aoi: Dict[str, Any],
        features: List[Dict[str, Any]],
        graph: Dict[str, Any],
        *,
        remote_sensing_layers: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        detected_points = [
            {
                "lat": item["lat"],
                "lon": item["lon"],
                "label": item["name"],
                "radius": 6,
            }
            for item in features
            if item["source_kind"] == "detected"
        ]
        observed_points = [
            {
                "lat": item["lat"],
                "lon": item["lon"],
                "label": item["name"],
                "radius": 5,
            }
            for item in features
            if item["source_kind"] == "observed"
        ]
        inferred_points = [
            {
                "lat": node["attributes"].get("lat"),
                "lon": node["attributes"].get("lon"),
                "label": node["name"],
                "radius": 6,
            }
            for node in graph["nodes"]
            if node["attributes"].get("source_kind") == "inferred"
            and node["attributes"].get("lat") is not None
            and node["attributes"].get("lon") is not None
        ]
        layers = [
            {
                "id": "analysis-area",
                "name": "分析范围",
                "type": "geojson",
                "color": "#0f766e",
                "visible": True,
                "note": "当前地图选点分析半径",
                "data": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": aoi["polygon"],
                            "properties": {"name": "分析范围"},
                        }
                    ],
                },
            }
        ]
        layers.extend(remote_sensing_layers or [])
        if observed_points:
            layers.append(
                {
                    "id": "observed-features",
                    "name": "公开空间要素",
                    "type": "points",
                    "color": "#1f5d45",
                    "visible": True,
                    "note": "来自 OSM / 逆地理编码 / 环境基线的观测节点",
                    "data": observed_points,
                }
            )
        if detected_points:
            layers.append(
                {
                    "id": "detected-features",
                    "name": "遥感识别节点",
                    "type": "points",
                    "color": "#0f766e",
                    "visible": True,
                    "note": "来自 ESA WorldCover 的卫星派生地表覆盖节点",
                    "data": detected_points,
                }
            )
        if inferred_points:
            layers.append(
                {
                    "id": "inferred-proxies",
                    "name": "代理人类节点",
                    "type": "points",
                    "color": "#d97706",
                    "visible": True,
                    "note": "规则与 LLM 推断的人类代理节点",
                    "data": inferred_points,
                }
            )
        return {
            "center": aoi["center"],
            "radius_m": aoi["radius_m"],
            "analysis_polygon": aoi["polygon"],
            "layers": layers,
            "feature_points": [
                {
                    "id": item["feature_id"],
                    "name": item["name"],
                    "lat": item["lat"],
                    "lon": item["lon"],
                    "category": item["category"],
                    "subtype": item["subtype"],
                    "source_kind": item["source_kind"],
                }
                for item in features
            ],
            "graph_nodes": [
                {
                    "id": node["uuid"],
                    "name": node["name"],
                    "lat": node["attributes"].get("lat"),
                    "lon": node["attributes"].get("lon"),
                    "label": [item for item in node["labels"] if item not in {"Entity", "Node"}][0],
                    "category": node["attributes"].get("category"),
                    "source_kind": node["attributes"].get("source_kind"),
                    "confidence": node["attributes"].get("confidence"),
                }
                for node in graph["nodes"]
            ],
        }

    def _make_graph_node(
        self,
        *,
        node_id: str,
        name: str,
        label: str,
        summary: str,
        lat: float,
        lon: float,
        source_kind: str,
        confidence: float,
        attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload_attributes = dict(attributes)
        payload_attributes.update(
            {
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "source_kind": source_kind,
                "confidence": round(float(confidence), 3),
            }
        )
        return {
            "uuid": node_id,
            "name": name,
            "labels": ["Entity", label],
            "summary": summary,
            "attributes": payload_attributes,
            "created_at": _utcnow_iso(),
        }

    def _make_graph_edge(
        self,
        *,
        edge_id: str,
        source: str,
        target: str,
        relation: str,
        fact: str,
        confidence: float = 0.72,
    ) -> Dict[str, Any]:
        return {
            "uuid": edge_id,
            "name": relation,
            "fact": fact,
            "fact_type": relation,
            "source_node_uuid": source,
            "target_node_uuid": target,
            "attributes": {
                "relation_origin": "rule_based_relation",
                "confidence": round(float(confidence), 3),
            },
            "created_at": _utcnow_iso(),
            "valid_at": None,
            "episodes": [],
        }

    def _to_graph_panel_data(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
        node_lookup = {node["uuid"]: node for node in nodes}
        output_edges = []
        for edge in edges:
            source_node = node_lookup.get(edge["source_node_uuid"])
            target_node = node_lookup.get(edge["target_node_uuid"])
            output_edge = dict(edge)
            output_edge["source_node_name"] = source_node["name"] if source_node else ""
            output_edge["target_node_name"] = target_node["name"] if target_node else ""
            output_edges.append(output_edge)
        return {
            "graph_id": "",
            "nodes": nodes,
            "edges": output_edges,
            "node_count": len(nodes),
            "edge_count": len(output_edges),
        }

    def _default_map_ontology(self) -> Dict[str, Any]:
        return {
            "entity_types": [
                {
                    "name": "Region",
                    "description": "A geographic analysis region or bounded area.",
                    "attributes": [
                        {"name": "location", "description": "Region description"},
                        {"name": "scene_type", "description": "Auto-classified scene type"},
                    ],
                },
                {
                    "name": "EcologicalReceptor",
                    "description": "A habitat or ecological receptor inferred from map-first analysis.",
                    "attributes": [
                        {"name": "location", "description": "Primary ecological location"},
                        {"name": "source_kind", "description": "observed/detected/inferred"},
                    ],
                },
                {
                    "name": "EnvironmentalCarrier",
                    "description": "A water, air, shoreline, or transport carrier relevant to spread.",
                    "attributes": [
                        {"name": "location", "description": "Primary environmental location"},
                        {"name": "source_kind", "description": "observed/detected/inferred"},
                    ],
                },
                {
                    "name": "Infrastructure",
                    "description": "A facility or built asset in the local environment.",
                    "attributes": [
                        {"name": "location", "description": "Facility location"},
                        {"name": "source_kind", "description": "observed/detected/inferred"},
                    ],
                },
                {
                    "name": "HumanActor",
                    "description": "A spatially anchored human proxy group.",
                    "attributes": [
                        {"name": "location", "description": "Anchor location"},
                        {"name": "source_kind", "description": "observed/detected/inferred"},
                    ],
                },
                {
                    "name": "GovernmentActor",
                    "description": "A governing or regulatory actor inferred from map context.",
                    "attributes": [
                        {"name": "jurisdiction", "description": "Administrative scope"},
                        {"name": "source_kind", "description": "observed/detected/inferred"},
                    ],
                },
                {
                    "name": "OrganizationActor",
                    "description": "A maintenance or operator proxy inferred from facilities.",
                    "attributes": [
                        {"name": "service_scope", "description": "Service scope"},
                        {"name": "source_kind", "description": "observed/detected/inferred"},
                    ],
                },
            ],
            "edge_types": [
                {
                    "name": "located_in",
                    "description": "The source lies within the target region.",
                    "source_targets": [
                        {"source": "EcologicalReceptor", "target": "Region"},
                        {"source": "EnvironmentalCarrier", "target": "Region"},
                        {"source": "Infrastructure", "target": "Region"},
                        {"source": "HumanActor", "target": "Region"},
                        {"source": "OrganizationActor", "target": "Region"},
                        {"source": "GovernmentActor", "target": "Region"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "depends_on",
                    "description": "The source depends on the target.",
                    "source_targets": [
                        {"source": "HumanActor", "target": "Infrastructure"},
                        {"source": "HumanActor", "target": "EnvironmentalCarrier"},
                        {"source": "OrganizationActor", "target": "Infrastructure"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "affects",
                    "description": "The source can affect the target.",
                    "source_targets": [
                        {"source": "Infrastructure", "target": "EcologicalReceptor"},
                        {"source": "Infrastructure", "target": "EnvironmentalCarrier"},
                        {"source": "EnvironmentalCarrier", "target": "EcologicalReceptor"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "regulates",
                    "description": "The source regulates or governs the target.",
                    "source_targets": [
                        {"source": "GovernmentActor", "target": "Infrastructure"},
                        {"source": "GovernmentActor", "target": "EcologicalReceptor"},
                        {"source": "GovernmentActor", "target": "HumanActor"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "uses",
                    "description": "The source uses the target.",
                    "source_targets": [
                        {"source": "HumanActor", "target": "Infrastructure"},
                        {"source": "OrganizationActor", "target": "Infrastructure"},
                    ],
                    "attributes": [],
                },
            ],
        }
