"""
Map-first seed generation and persistence.

This service builds a spatially anchored seed graph from a map point using
best-effort public data sources. It deliberately distinguishes observed,
detected, and inferred graph items so downstream simulation logic can preserve
uncertainty instead of flattening everything into "facts".
"""

from __future__ import annotations

import io
import hashlib
import json
import math
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PIL import Image

from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..utils.atomic_file import read_json_file, read_text_file, write_json_file, write_text_file
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .effort_contract import normalize_effort_snapshot
from .map_spatial_selection import (
    PUBLIC_PROVIDERS,
    SelectionContext,
    granularity_for_radius,
    is_valid_proxy_anchor,
    select_spatial_features,
    spatial_policy_from_effort,
    summarize_provider_failures,
    summarize_source_status,
)

logger = get_logger("envfish.map_seed")
PIL_NEAREST = getattr(getattr(Image, "Resampling", Image), "NEAREST")


WORLD_COVER_CLASSES: Dict[int, Dict[str, Any]] = {
    10: {"name": "树木覆盖", "name_zh": "树木覆盖", "name_en": "Tree cover", "color": (0, 100, 0), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 8},
    20: {"name": "灌丛", "name_zh": "灌丛", "name_en": "Shrubland", "color": (255, 187, 34), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 6},
    30: {"name": "草地", "name_zh": "草地", "name_en": "Grassland", "color": (255, 255, 76), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 6},
    40: {"name": "农田", "name_zh": "农田", "name_en": "Cropland", "color": (240, 150, 255), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 6},
    50: {"name": "建成区", "name_zh": "建成区", "name_en": "Built-up", "color": (250, 0, 0), "category": "facility", "node_family": "Infrastructure", "importance": 7},
    60: {"name": "裸地/稀疏植被", "name_zh": "裸地/稀疏植被", "name_en": "Bare / sparse vegetation", "color": (180, 180, 180), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 5},
    70: {"name": "雪冰", "name_zh": "雪冰", "name_en": "Snow and ice", "color": (240, 240, 240), "category": "ecology", "node_family": "EnvironmentalCarrier", "importance": 4},
    80: {"name": "永久水体", "name_zh": "永久水体", "name_en": "Permanent water bodies", "color": (0, 100, 200), "category": "ecology", "node_family": "EnvironmentalCarrier", "importance": 9},
    90: {"name": "草本湿地", "name_zh": "草本湿地", "name_en": "Herbaceous wetland", "color": (0, 150, 160), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 9},
    95: {"name": "红树林", "name_zh": "红树林", "name_en": "Mangroves", "color": (0, 207, 117), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 10},
    100: {"name": "苔藓/地衣", "name_zh": "苔藓/地衣", "name_en": "Moss and lichen", "color": (250, 230, 160), "category": "ecology", "node_family": "EcologicalReceptor", "importance": 5},
}


def _utcnow_iso() -> str:
    return datetime.now().isoformat()


DISPLAY_TOKEN_ZH = {
    "unknown": "未知",
    "mixed": "混合场景",
    "coastal": "滨海岸线",
    "inland_water": "内陆水系",
    "urban_edge": "城市边缘",
    "agricultural": "农业空间",
    "observed": "公开观测",
    "detected": "遥感识别",
    "reference": "参考地名",
    "inferred": "规则推断",
    "ecology": "生态",
    "facility": "设施",
    "region": "区域",
    "human_proxy": "人类代理",
    "explicit_focus_then_spatial_category_balance": "显式焦点优先 + 空间类别平衡",
    "residential": "居住",
    "commercial": "商业",
    "commercial_hub": "商业中心",
    "office_cluster": "办公组团",
    "hospital": "医院",
    "school": "学校",
    "university": "高校",
    "tourism": "旅游",
    "shop": "商户",
    "road_corridor": "道路廊道",
    "transit_stop": "公交站点",
    "rail_station": "轨道站点",
    "pier": "码头",
    "marina": "游艇/小型码头",
    "ferry_terminal": "渡轮码头",
    "industrial": "工业",
    "wastewater_plant": "污水处理设施",
    "power_plant": "电力设施",
    "warehouse": "仓储设施",
    "water": "水体",
    "river": "河流",
    "stream": "溪流",
    "canal": "运河",
    "ditch": "沟渠",
    "reservoir": "水库",
    "basin": "流域",
    "coastline": "岸线",
    "beach": "海滩",
    "forest": "林地",
    "wetland": "湿地",
    "nature_reserve": "自然保护区",
    "protected_area": "保护区",
    "park": "公园",
    "garden": "花园",
    "farmland": "农田",
    "farmyard": "农场院落",
    "meadow": "草地",
    "worldcover_10": "树木覆盖",
    "worldcover_20": "灌丛",
    "worldcover_30": "草地",
    "worldcover_40": "农田",
    "worldcover_50": "建成区",
    "worldcover_60": "裸地/稀疏植被",
    "worldcover_70": "雪冰",
    "worldcover_80": "永久水体",
    "worldcover_90": "草本湿地",
    "worldcover_95": "红树林",
    "worldcover_100": "苔藓/地衣",
}


def _display_token_zh(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未知"
    return DISPLAY_TOKEN_ZH.get(text) or DISPLAY_TOKEN_ZH.get(text.lower()) or text


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
    SOURCE_CACHE_DIR = os.path.join(Config.UPLOAD_FOLDER, "map_source_cache")
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
        os.makedirs(self.SOURCE_CACHE_DIR, exist_ok=True)
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
            payload = []

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
            area_label = self.describe_area_label(lat=lat, lon=lon, radius_m=radius_m, admin_context=admin_context)
            admin_context = dict(admin_context)
            admin_context["area_label"] = area_label
            candidates.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "display_name": admin_context.get("display_name") or text,
                    "area_label": area_label,
                    "admin_context": admin_context,
                }
            )
        if candidates:
            return candidates
        return self._local_forward_geocode_candidates(text, limit=limit, radius_m=radius_m)

    def _local_forward_geocode_candidates(self, query: str, *, limit: int = 5, radius_m: int = 3000) -> List[Dict[str, Any]]:
        text = str(query or "").strip().lower().replace(" ", "")
        if not text:
            return []

        local_index = [
            {
                "aliases": ["深圳", "深圳市", "shenzhen"],
                "lat": 22.544574,
                "lon": 114.054543,
                "display_name": "深圳市, 广东省, 中国",
                "admin_context": {
                    "display_name": "深圳市, 广东省, 中国",
                    "country": "中国",
                    "state": "广东省",
                    "city": "深圳市",
                    "district": "",
                },
            },
            {
                "aliases": ["香港机场", "香港国际机场", "赤鱲角机场", "赤腊角机场", "hongkongairport", "hkg"],
                "lat": 22.31899,
                "lon": 113.91312,
                "display_name": "香港国际机场及赤鱲角周边",
                "admin_context": {
                    "display_name": "香港国际机场及赤鱲角周边",
                    "city": "香港",
                    "district": "香港国际机场",
                    "geographic_context": {
                        "key": "hong_kong_airport",
                        "macro_area": "香港",
                        "local_area": "香港国际机场",
                        "feature_name": "赤鱲角机场岛",
                        "area_label": "香港国际机场周边",
                        "display_name": "香港国际机场及赤鱲角周边",
                        "area_kind": "airport",
                    },
                },
            },
            {
                "aliases": ["大屿山", "lantau"],
                "lat": 22.267,
                "lon": 113.945,
                "display_name": "香港大屿山及东涌、机场周边",
                "admin_context": {
                    "display_name": "香港大屿山及东涌、机场周边",
                    "city": "香港",
                    "district": "大屿山",
                    "geographic_context": {
                        "key": "hong_kong_lantau",
                        "macro_area": "香港",
                        "local_area": "大屿山",
                        "feature_name": "大屿山西部与北部片区",
                        "area_label": "香港大屿山周边",
                        "display_name": "香港大屿山及东涌、机场周边",
                        "area_kind": "district",
                    },
                },
            },
        ]

        matches: List[Dict[str, Any]] = []
        for item in local_index:
            aliases = [str(alias or "").lower().replace(" ", "") for alias in item.get("aliases", [])]
            if not any(alias and (alias in text or text in alias) for alias in aliases):
                continue
            lat = round(float(item["lat"]), 6)
            lon = round(float(item["lon"]), 6)
            admin_context = dict(item.get("admin_context") or {})
            admin_context["lat"] = lat
            admin_context["lon"] = lon
            area_label = self.describe_area_label(lat=lat, lon=lon, radius_m=radius_m, admin_context=admin_context)
            admin_context["area_label"] = area_label
            matches.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "display_name": admin_context.get("display_name") or item.get("display_name") or query,
                    "area_label": area_label,
                    "admin_context": admin_context,
                    "source": "local_fallback",
                }
            )
            if len(matches) >= max(1, int(limit or 5)):
                break
        return matches

    def resolve_area_context(self, lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
        admin_context = self._reverse_geocode(lat, lon)
        radius_m = max(500, int(radius_m or 3000))
        area_label = self.describe_area_label(
            lat=float(lat),
            lon=float(lon),
            radius_m=radius_m,
            admin_context=admin_context,
        )
        admin_context = dict(admin_context)
        admin_context["area_label"] = area_label
        return {
            "lat": round(float(lat), 6),
            "lon": round(float(lon), 6),
            "radius_m": radius_m,
            "admin_context": admin_context,
            "area_label": area_label,
        }

    def describe_area_label(self, lat: float, lon: float, radius_m: int, admin_context: Optional[Dict[str, Any]] = None) -> str:
        context = dict(admin_context or self._reverse_geocode(lat, lon) or {})
        radius_m = max(500, int(radius_m or 3000))
        geographic_context = context.get("geographic_context") if isinstance(context.get("geographic_context"), dict) else {}
        original_geo_key = str(geographic_context.get("key") or "").strip()
        geographic_context = self._select_geographic_context_for_label(context, lat, lon, radius_m)
        if geographic_context:
            selected_geo_key = str(geographic_context.get("key") or "").strip()
            selected_kind = str(geographic_context.get("area_kind") or "").strip()
            context = self._apply_local_geographic_context(
                context,
                geographic_context,
                force=selected_geo_key != original_geo_key or selected_kind in {"airport", "transport", "landmark"},
            )
        city = str(context.get("city") or "").strip()
        district = str(context.get("district") or "").strip()
        road = str(context.get("road") or "").strip()
        locality = self._select_locality_name(context, radius_m)
        display_name = str(context.get("display_name") or "").strip()

        local_area_label = self._radius_aware_local_area_label(context, geographic_context, radius_m)
        if local_area_label:
            return local_area_label

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

    def _radius_aware_local_area_label(
        self,
        context: Dict[str, Any],
        geographic_context: Dict[str, Any],
        radius_m: int,
    ) -> str:
        if not geographic_context:
            return ""

        key = str(geographic_context.get("key") or "").strip()
        city = str(context.get("city") or geographic_context.get("macro_area") or "").strip()
        district = str(context.get("district") or geographic_context.get("local_area") or "").strip()
        feature_name = str(geographic_context.get("feature_name") or "").strip()
        local_area = str(geographic_context.get("local_area") or "").strip()
        default_label = str(geographic_context.get("area_label") or "").strip()

        fine_locality = self._select_locality_name(context, min(radius_m, 1800))
        if radius_m <= 1800:
            label = self._join_place_tokens(city, district, fine_locality or feature_name or local_area)
            return f"{label}周边" if label else default_label

        if radius_m <= 6000:
            label = self._join_place_tokens(city, district or local_area)
            return f"{label}周边" if label else default_label

        if radius_m <= 15000:
            label = self._join_place_tokens(city, district or local_area)
            return f"{label}片区" if label else default_label

        if radius_m <= 30000:
            medium_labels = {
                "shenzhen_baoan": "深圳西部城市片区",
                "shenzhen_nanshan": "深圳湾-前海城市片区",
                "shenzhen_bay": "深圳湾-前海滨海片区",
                "hong_kong_airport": "香港国际机场及大屿山周边",
                "hong_kong_lantau": "香港大屿山片区",
                "shenzhen_guangming": "深圳北部城市与产业片区",
                "shenzhen_longhua": "深圳中北部城市片区",
                "shenzhen_futian": "深圳中心城区片区",
                "shenzhen_luohu": "深圳东部中心城区片区",
                "shenzhen_longgang": "深圳东部城市片区",
                "shenzhen_pingshan": "深圳东部产业与山地生态片区",
                "lingdingyang": "珠江口伶仃洋水域",
                "zhuhai_east_coast": "珠海东岸近岸片区",
                "macao_western_waters": "澳门近岸与横琴片区",
            }
            if key in medium_labels:
                return medium_labels[key]
            label = self._join_place_tokens(city, district or local_area)
            return f"{label}片区" if label else default_label

        if radius_m <= 60000:
            broad_labels = {
                "shenzhen_baoan": "深圳西部-珠江口东岸区域",
                "shenzhen_nanshan": "深圳湾-珠江口东岸区域",
                "shenzhen_bay": "深圳湾-珠江口东岸区域",
                "hong_kong_airport": "香港国际机场-大屿山与珠江口东缘区域",
                "hong_kong_lantau": "香港大屿山与珠江口东缘区域",
                "shenzhen_guangming": "深圳北部-珠江口东岸区域",
                "shenzhen_longhua": "深圳中北部都会区域",
                "shenzhen_futian": "深圳中心城区及周边区域",
                "shenzhen_luohu": "深圳中东部都会区域",
                "shenzhen_longgang": "深圳东部都会区域",
                "shenzhen_pingshan": "深圳东部山地与产业区域",
                "lingdingyang": "珠江口伶仃洋与粤港澳近岸区域",
                "zhuhai_east_coast": "珠海东岸-珠江口西岸区域",
                "macao_western_waters": "澳门近岸-横琴珠海区域",
            }
            if key in broad_labels:
                return broad_labels[key]
            if city:
                return f"{city}及周边区域"
            return default_label

        if key.startswith("shenzhen_") or key in {"shenzhen_bay", "lingdingyang"}:
            return "粤港澳大湾区珠江口区域"
        if key.startswith("hong_kong_"):
            return "香港西部与珠江口东缘区域"
        if key.startswith("zhuhai_") or key.startswith("macao_"):
            return "珠江口西岸与粤港澳近岸区域"
        return default_label

    def _context_place_label(self, admin_context: Dict[str, Any], fallback: str = "选定区域") -> str:
        geographic_context = admin_context.get("geographic_context") if isinstance(admin_context.get("geographic_context"), dict) else {}
        return (
            str(admin_context.get("area_label") or "").strip()
            or str(geographic_context.get("area_label") or "").strip()
            or str(admin_context.get("city") or "").strip()
            or str(admin_context.get("display_name") or "").strip()
            or fallback
        )

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
        requested_location: str = "",
        focus_text: str = "",
        known_entities: str = "",
        analysis_boundaries: str = "",
        focus_mode: str = "auto",
        golden_case_profile: str = "",
        effort_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        seed_id = f"mapseed_{uuid.uuid4().hex[:12]}"
        seed_dir = cls._seed_dir(seed_id)
        os.makedirs(seed_dir, exist_ok=True)
        payload = {
            "seed_id": seed_id,
            "status": "pending",
            "availability": {
                "status": "pending",
                "available": False,
                "retryable": False,
                "reason_code": "analysis_pending",
                "message": "地理数据正在获取。",
                "provider_failures": [],
            },
            "created_at": _utcnow_iso(),
            "updated_at": _utcnow_iso(),
            "title": title or f"Map Seed {seed_id[-6:]}",
            "effort_snapshot": normalize_effort_snapshot(effort_snapshot),
            "input": {
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "radius_m": max(500, int(radius_m)),
                "simulation_requirement": simulation_requirement.strip(),
                "requested_location": str(requested_location or "").strip(),
                "focus_text": str(focus_text or "").strip(),
                "known_entities": str(known_entities or "").strip(),
                "analysis_boundaries": str(analysis_boundaries or "").strip(),
                "focus_mode": str(focus_mode or "auto").strip() or "auto",
                "golden_case_profile": str(golden_case_profile or "").strip(),
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
        return read_json_file(path, default=None)

    @classmethod
    def is_formal_seed_ready(cls, seed: Optional[Dict[str, Any]]) -> bool:
        payload = seed if isinstance(seed, dict) else {}
        quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
        return payload.get("status") == "ready" and quality.get("formal_ready") is True

    @classmethod
    def seed_availability(cls, seed: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = seed if isinstance(seed, dict) else {}
        quality = payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
        recorded = quality.get("availability") if isinstance(quality.get("availability"), dict) else {}
        if not recorded and isinstance(payload.get("availability"), dict):
            recorded = dict(payload.get("availability") or {})
        lifecycle_status = str(payload.get("status") or "unknown")
        if lifecycle_status not in {"pending", "processing"} and str(
            recorded.get("status") or ""
        ) in {"pending", "processing"}:
            recorded = {}
        provider_failures = list(
            recorded.get("provider_failures") or quality.get("provider_failures") or []
        )
        if not provider_failures and isinstance(quality.get("providers"), dict):
            providers = dict(quality.get("providers") or {})
            provider_failures = summarize_provider_failures(
                overpass_status=dict(providers.get("overpass") or {}),
                worldcover_status=dict(providers.get("worldcover") or {}),
            )
        if cls.is_formal_seed_ready(payload):
            return {
                "status": "ready",
                "available": True,
                "retryable": False,
                "reason_code": "formal_spatial_data_ready",
                "message": "已取得可用于正式空间判断的公开地理数据。",
                "provider_failures": provider_failures,
                **recorded,
                "available": True,
                "status": "ready",
            }
        if lifecycle_status in {"pending", "processing"}:
            return {
                "status": lifecycle_status,
                "available": False,
                "retryable": False,
                "reason_code": "analysis_pending",
                "message": "地理数据正在获取。",
                "provider_failures": [],
            }
        blocking_failures = [
            item for item in provider_failures if item.get("required_for_formal_ready")
        ]
        derived_retryable = any(bool(item.get("retryable")) for item in blocking_failures)
        derived_reason = str(
            (blocking_failures[0].get("reason_code") if blocking_failures else "")
            or ""
        )
        return {
            "status": "unavailable",
            "available": False,
            "retryable": bool(
                recorded.get("retryable")
                or quality.get("retryable")
                or derived_retryable
            ),
            "reason_code": str(
                recorded.get("reason_code")
                or quality.get("reason_code")
                or derived_reason
                or ("analysis_failed" if lifecycle_status == "failed" else "formal_spatial_data_unavailable")
            ),
            "message": str(
                recorded.get("message")
                or payload.get("error")
                or "当前没有取得可用于正式空间判断的地理数据。"
            ),
            "provider_failures": provider_failures,
        }

    @classmethod
    def get_graph_snapshot(
        cls,
        seed_id: str,
        *,
        allow_unavailable: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not allow_unavailable and not cls.is_formal_seed_ready(cls.get_seed(seed_id)):
            return None
        path = cls._seed_file(seed_id, cls.GRAPH_FILENAME)
        return read_json_file(path, default=None)

    @classmethod
    def get_layers(
        cls,
        seed_id: str,
        *,
        allow_unavailable: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not allow_unavailable and not cls.is_formal_seed_ready(cls.get_seed(seed_id)):
            return None
        path = cls._seed_file(seed_id, cls.LAYERS_FILENAME)
        return read_json_file(path, default=None)

    @classmethod
    def get_report_text(cls, seed_id: str, *, allow_unavailable: bool = False) -> str:
        if not allow_unavailable and not cls.is_formal_seed_ready(cls.get_seed(seed_id)):
            return ""
        path = cls._seed_file(seed_id, cls.REPORT_FILENAME)
        return read_text_file(path, default="")

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
        write_json_file(path, payload)

    @classmethod
    def _write_text(cls, path: str, text: str) -> None:
        write_text_file(path, text)

    def _profile_limits(self, seed: Dict[str, Any]) -> Dict[str, Any]:
        profile = str((seed.get("input") or {}).get("golden_case_profile") or seed.get("golden_case_profile") or "").strip()
        if profile == "wuhan_covid_v1":
            return {
                "profile": profile,
                "spatial_feature_limit": 120,
                "candidate_pool_limit": 360,
                "spatial_per_subtype_limit": 12,
                "worldcover_components_per_class": 4,
                "graph_feature_limit": 160,
                "llm_semantic_edge_limit": 60,
                "spatial_effort_policy": None,
            }
        effort_snapshot = normalize_effort_snapshot(seed.get("effort_snapshot"))
        spatial_policy = spatial_policy_from_effort(effort_snapshot)
        return {
            "profile": "",
            "effort_level": effort_snapshot["effort_level"],
            "spatial_feature_limit": spatial_policy.planning_anchor_limit,
            "candidate_pool_limit": spatial_policy.candidate_pool_limit,
            "spatial_per_subtype_limit": max(
                2, int(math.ceil(spatial_policy.candidate_pool_limit / 18))
            ),
            "worldcover_components_per_class": max(
                1, min(6, int(math.ceil(spatial_policy.targeted_refinement_slots / 4)))
            ),
            "graph_feature_limit": spatial_policy.planning_anchor_limit,
            "llm_semantic_edge_limit": max(
                3, int(round(math.sqrt(spatial_policy.planning_anchor_limit) * 2))
            ),
            "spatial_effort_policy": spatial_policy,
        }

    def _source_cache_key(self, provider: str, *, lat: float, lon: float, radius_m: int, profile: str) -> str:
        # Nearby requests intentionally share cache entries.  Public spatial
        # sources change slowly relative to one simulation session, while this
        # bucketing prevents a fresh heavy query for every map click.
        payload = "|".join(
            [
                str(provider),
                f"{round(float(lat), 3):.3f}",
                f"{round(float(lon), 3):.3f}",
                str(max(500, int(round(int(radius_m or 0) / 500.0) * 500))),
                str(profile or "default"),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

    def _read_source_cache(self, provider: str, cache_key: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self.SOURCE_CACHE_DIR, f"{provider}_{cache_key}.json")
        try:
            age_seconds = max(0.0, time.time() - os.path.getmtime(path))
        except OSError:
            return None
        if age_seconds > max(300, int(Config.MAP_SOURCE_CACHE_TTL_SECONDS)):
            return None
        payload = read_json_file(path, default=None)
        if not isinstance(payload, dict):
            return None
        if not list(payload.get("features") or []):
            return None
        result = dict(payload)
        status = dict(result.get("status") or {})
        status.update(
            {
                "status": "cached",
                "cache_age_seconds": round(age_seconds, 1),
                "cache_key": cache_key,
            }
        )
        result["status"] = status
        return result

    def _write_source_cache(
        self,
        provider: str,
        cache_key: str,
        *,
        features: List[Dict[str, Any]],
        status: Dict[str, Any],
        layers: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        path = os.path.join(self.SOURCE_CACHE_DIR, f"{provider}_{cache_key}.json")
        try:
            write_json_file(
                path,
                {
                    "provider": provider,
                    "cached_at": _utcnow_iso(),
                    "features": features,
                    "layers": layers or [],
                    "status": status,
                },
            )
        except Exception as exc:
            logger.warning(f"Unable to persist {provider} map cache: {exc}")

    def _merge_feature_lists(self, *feature_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen_ids = set()
        for group in feature_groups:
            for feature in group or []:
                feature_id = str(feature.get("feature_id") or "").strip()
                if not feature_id or feature_id in seen_ids:
                    continue
                merged.append(feature)
                seen_ids.add(feature_id)
        merged.sort(key=lambda item: (-float(item.get("importance") or 0), float(item.get("distance_m") or 0), str(item.get("name") or "")))
        return merged

    def _refresh_cached_feature_distances(
        self,
        features: Iterable[Dict[str, Any]],
        *,
        lat: float,
        lon: float,
    ) -> List[Dict[str, Any]]:
        refreshed: List[Dict[str, Any]] = []
        for feature in features or []:
            item = dict(feature)
            try:
                feature_lat = float(item.get("lat"))
                feature_lon = float(item.get("lon"))
            except (TypeError, ValueError):
                continue
            item["distance_m"] = round(_haversine_m(lat, lon, feature_lat, feature_lon), 1)
            refreshed.append(item)
        return refreshed

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
        profile_limits = self._profile_limits(seed)

        self.update_seed(
            seed_id,
            status="processing",
            error=None,
            availability={
                "status": "processing",
                "available": False,
                "retryable": False,
                "reason_code": "analysis_pending",
                "message": "地理数据正在获取。",
                "provider_failures": [],
            },
        )
        if progress_callback:
            progress_callback("locating", 5, "解析地点与分析范围")

        admin_context = self._reverse_geocode(lat, lon)
        aoi = self._build_area_of_interest(lat, lon, radius_m, admin_context)
        admin_context = dict(admin_context)
        admin_context["area_label"] = aoi.get("label") or self._context_place_label(admin_context)

        if progress_callback:
            progress_callback("collecting", 20, "采集周边空间要素和环境基线")

        overpass_features, overpass_summary = self._collect_spatial_features(
            lat,
            lon,
            radius_m,
            per_subtype_limit=profile_limits["spatial_per_subtype_limit"],
            feature_limit=profile_limits["candidate_pool_limit"],
        )
        remote_sensing_features, remote_sensing_summary, remote_sensing_layers = self._collect_worldcover_features(
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            components_per_class=profile_limits["worldcover_components_per_class"],
        )
        curated_features = self._wuhan_curated_features(lat, lon, radius_m) if profile_limits["profile"] == "wuhan_covid_v1" else []
        curated_features.extend(self._local_curated_features(lat, lon, radius_m))
        environment_baseline = self._build_environment_baseline(lat, lon, admin_context)
        candidate_features = self._merge_context_features(
            features=self._merge_feature_lists(overpass_features, curated_features, remote_sensing_features),
            lat=lat,
            lon=lon,
            admin_context=admin_context,
            environment_baseline=environment_baseline,
        )
        candidate_features = self._filter_features_to_aoi(candidate_features, radius_m)

        selection_context = SelectionContext(
            center_lat=lat,
            center_lon=lon,
            radius_m=radius_m,
            simulation_requirement=simulation_requirement,
            title=str(seed.get("title") or ""),
            requested_location=str(seed["input"].get("requested_location") or ""),
            focus_text=str(seed["input"].get("focus_text") or ""),
            known_entities=str(seed["input"].get("known_entities") or ""),
            analysis_boundaries=str(seed["input"].get("analysis_boundaries") or ""),
            focus_mode=str(seed["input"].get("focus_mode") or "auto"),
            admin_context=admin_context,
        )
        selection_result = select_spatial_features(
            candidate_features,
            context=selection_context,
            limit=profile_limits["spatial_feature_limit"],
            effort_policy=profile_limits["spatial_effort_policy"],
        )
        features = selection_result.selected_features
        source_status = summarize_source_status(
            overpass_status=overpass_summary,
            worldcover_status=remote_sensing_summary,
            # Downstream readiness is a contract on the actual spatial
            # skeleton, not on objects that were collected and then discarded
            # by focus/granularity selection.
            features=features,
        )
        selection_summary = {
            "granularity": selection_result.granularity,
            "focus_terms": selection_result.focus_terms,
            "diagnostics": selection_result.diagnostics,
        }
        data_quality = {
            **source_status,
            "granularity": selection_result.granularity,
            "selection_policy": selection_result.diagnostics.get("selection_policy"),
        }

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
            data_quality=data_quality,
            selection_summary=selection_summary,
            feature_limit=profile_limits["graph_feature_limit"],
            llm_edge_limit=profile_limits["llm_semantic_edge_limit"],
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
            data_quality=data_quality,
            selection_summary=selection_summary,
        )

        layers = self._build_layers_payload(
            aoi,
            features,
            graph,
            remote_sensing_layers=remote_sensing_layers,
            data_quality=data_quality,
            selection_summary=selection_summary,
        )
        self._write_json(self._seed_file(seed_id, self.GRAPH_FILENAME), graph)
        self._write_json(self._seed_file(seed_id, self.LAYERS_FILENAME), layers)
        self._write_text(self._seed_file(seed_id, self.REPORT_FILENAME), report_text)

        summary = self._build_summary(
            admin_context,
            scene_classification,
            graph,
            data_quality=data_quality,
        )
        formal_ready = data_quality.get("formal_ready") is True
        availability = dict(data_quality.get("availability") or {})
        seed_status = "ready" if formal_ready else "unavailable"
        payload = self.update_seed(
            seed_id,
            status=seed_status,
            availability=availability,
            retryable=bool(availability.get("retryable")),
            title=summary["title"],
            summary=summary["summary"],
            admin_context=admin_context,
            area_of_interest=aoi,
            scene_classification=scene_classification,
            environment_baseline=environment_baseline,
            remote_sensing_summary=remote_sensing_summary,
            overpass_summary=overpass_summary,
            data_quality=data_quality,
            selection_summary=selection_summary,
            graph_stats=graph.get("stats", {}),
        )
        if progress_callback:
            progress_callback(
                "completed" if formal_ready else "unavailable",
                100,
                "正式地理数据已生成"
                if formal_ready
                else str(availability.get("message") or "正式地理数据不可用"),
            )
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
        if not self.is_formal_seed_ready(seed):
            raise ValueError(f"地图种子没有可用于正式分析的地理数据: {seed_id}")
        graph = self.get_graph_snapshot(seed_id)
        report_text = self.get_report_text(seed_id)
        if not graph:
            raise ValueError(f"地图种子正式图谱不存在: {seed_id}")

        existing_project_id = seed.get("project_id")
        if existing_project_id:
            project = ProjectManager.get_project(existing_project_id)
            if project:
                return {
                    "project_id": project.project_id,
                    "project_name": project.name,
                    "effort_snapshot": project.effort_snapshot,
                }

        title = seed.get("title") or f"Map Seed {seed_id[-6:]}"
        project = ProjectManager.create_project(
            name=title,
            effort_snapshot=normalize_effort_snapshot(seed.get("effort_snapshot")),
        )
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.map_seed_id = seed_id
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
        write_text_file(report_path, report_text)
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
            "effort_snapshot": project.effort_snapshot,
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

        context = self._normalize_admin_context(
            address=payload.get("address") or {},
            display_name=str(payload.get("display_name") or f"{lat:.4f}, {lon:.4f}"),
            lat=lat,
            lon=lon,
        )
        return self._augment_local_geography(context, lat, lon)

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

    def _augment_local_geography(self, context: Dict[str, Any], lat: float, lon: float) -> Dict[str, Any]:
        local = self._local_geographic_context(lat, lon)
        if not local:
            return context

        return self._apply_local_geographic_context(
            context,
            local,
            force=str(local.get("area_kind") or "").strip() in {"airport", "transport", "landmark"},
        )

    def _apply_local_geographic_context(
        self,
        context: Dict[str, Any],
        local: Dict[str, Any],
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        result = dict(context)
        result["geographic_context"] = local
        macro_area = str(local.get("macro_area") or "").strip()
        local_area = str(local.get("local_area") or "").strip()
        if force and macro_area:
            result["city"] = macro_area
        elif macro_area.endswith("市"):
            result["city"] = macro_area
        elif not str(result.get("city") or "").strip():
            result["city"] = local.get("macro_area", "")

        if force and local_area:
            result["district"] = local_area
        elif macro_area.endswith("市") and local_area:
            result["district"] = local_area
        elif not str(result.get("district") or "").strip():
            result["district"] = local.get("local_area", "")
        if force or not str(result.get("neighbourhood") or "").strip():
            result["neighbourhood"] = local.get("feature_name", "")

        display = str(result.get("display_name") or "").strip()
        local_name = local.get("display_name") or local.get("area_label")
        if not display or self._looks_like_coordinate_text(display):
            result["display_name"] = local_name or display
        elif local_name and local_name not in display:
            result["display_name"] = f"{local_name}，{display}"
        return result

    def _select_geographic_context_for_label(
        self,
        context: Dict[str, Any],
        lat: float,
        lon: float,
        radius_m: int,
    ) -> Dict[str, Any]:
        center_context = context.get("geographic_context") if isinstance(context.get("geographic_context"), dict) else {}
        range_context = self._range_geographic_context(lat, lon, radius_m)
        if not center_context:
            return range_context
        if not range_context or center_context.get("key") == range_context.get("key"):
            return center_context

        center_kind = str(center_context.get("area_kind") or "").strip()
        range_kind = str(range_context.get("area_kind") or "").strip()
        center_is_broad = center_kind in {"water", "regional"}
        range_is_anchor = range_kind in {"airport", "transport", "district", "landmark"}
        if center_is_broad and range_is_anchor:
            return range_context
        return center_context

    def _range_geographic_context(self, lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
        bbox = _radius_to_bbox(lat, lon, max(500, int(radius_m or 3000)))
        range_matches: List[Tuple[int, float, Dict[str, Any]]] = []
        for item in self._local_geographic_candidates():
            min_lat, max_lat, min_lon, max_lon = item["bounds"]
            intersects = not (
                max_lat < bbox["min_lat"]
                or min_lat > bbox["max_lat"]
                or max_lon < bbox["min_lon"]
                or min_lon > bbox["max_lon"]
            )
            if not intersects:
                continue
            kind = str(item.get("area_kind") or "").strip()
            priority = int(item.get("range_priority") or 10)
            if kind in {"water", "regional"}:
                priority += 50
            center_lat = (min_lat + max_lat) / 2
            center_lon = (min_lon + max_lon) / 2
            distance = _haversine_m(lat, lon, center_lat, center_lon)
            range_matches.append((priority, distance, item))
        if not range_matches:
            return {}
        range_matches.sort(key=lambda entry: (entry[0], entry[1]))
        return {key: value for key, value in range_matches[0][2].items() if key != "bounds"}

    def _local_geographic_context(self, lat: float, lon: float) -> Dict[str, Any]:
        for item in self._local_geographic_candidates():
            min_lat, max_lat, min_lon, max_lon = item["bounds"]
            if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                return {key: value for key, value in item.items() if key != "bounds"}
        return {}

    def _local_geographic_candidates(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "shenzhen_guangming",
                "macro_area": "深圳市",
                "local_area": "光明区",
                "feature_name": "光明区城市生态与产业片区",
                "area_label": "深圳市光明区周边",
                "display_name": "深圳市光明区及凤凰城、公明周边",
                "area_kind": "district",
                "bounds": (22.64, 22.86, 113.82, 114.08),
            },
            {
                "key": "shenzhen_longhua",
                "macro_area": "深圳市",
                "local_area": "龙华区",
                "feature_name": "龙华区城市片区",
                "area_label": "深圳市龙华区周边",
                "display_name": "深圳市龙华区及深圳北站周边",
                "area_kind": "district",
                "bounds": (22.58, 22.78, 113.94, 114.13),
            },
            {
                "key": "shenzhen_baoan",
                "macro_area": "深圳市",
                "local_area": "宝安区",
                "feature_name": "宝安区西部城市与滨海片区",
                "area_label": "深圳市宝安区周边",
                "display_name": "深圳市宝安区及机场、茅洲河周边",
                "area_kind": "district",
                "bounds": (22.50, 22.86, 113.75, 114.02),
            },
            {
                "key": "shenzhen_nanshan",
                "macro_area": "深圳市",
                "local_area": "南山区",
                "feature_name": "南山区深圳湾与前海片区",
                "area_label": "深圳市南山区周边",
                "display_name": "深圳市南山区、前海及深圳湾周边",
                "area_kind": "district",
                "bounds": (22.45, 22.62, 113.85, 114.02),
            },
            {
                "key": "shenzhen_futian",
                "macro_area": "深圳市",
                "local_area": "福田区",
                "feature_name": "福田中心城区",
                "area_label": "深圳市福田区周边",
                "display_name": "深圳市福田区中心城区周边",
                "area_kind": "district",
                "bounds": (22.48, 22.62, 114.00, 114.12),
            },
            {
                "key": "shenzhen_luohu",
                "macro_area": "深圳市",
                "local_area": "罗湖区",
                "feature_name": "罗湖口岸与东部中心城区",
                "area_label": "深圳市罗湖区周边",
                "display_name": "深圳市罗湖区及东门、口岸周边",
                "area_kind": "district",
                "bounds": (22.50, 22.62, 114.08, 114.20),
            },
            {
                "key": "shenzhen_longgang",
                "macro_area": "深圳市",
                "local_area": "龙岗区",
                "feature_name": "龙岗区东部城市片区",
                "area_label": "深圳市龙岗区周边",
                "display_name": "深圳市龙岗区及东部城市组团周边",
                "area_kind": "district",
                "bounds": (22.55, 22.85, 114.10, 114.45),
            },
            {
                "key": "shenzhen_pingshan",
                "macro_area": "深圳市",
                "local_area": "坪山区",
                "feature_name": "坪山区产业与山地生态片区",
                "area_label": "深圳市坪山区周边",
                "display_name": "深圳市坪山区及东部山地生态周边",
                "area_kind": "district",
                "bounds": (22.60, 22.82, 114.25, 114.55),
            },
            {
                "key": "hong_kong_airport",
                "macro_area": "香港",
                "local_area": "香港国际机场",
                "feature_name": "赤鱲角机场岛",
                "area_label": "香港国际机场周边",
                "display_name": "香港国际机场及赤鱲角周边",
                "area_kind": "airport",
                "range_priority": 1,
                "bounds": (22.285, 22.335, 113.875, 113.965),
            },
            {
                "key": "hong_kong_lantau",
                "macro_area": "香港",
                "local_area": "大屿山",
                "feature_name": "大屿山西部与北部片区",
                "area_label": "香港大屿山周边",
                "display_name": "香港大屿山及东涌、机场周边",
                "area_kind": "district",
                "range_priority": 4,
                "bounds": (22.18, 22.36, 113.82, 114.05),
            },
            {
                "key": "shenzhen_bay",
                "macro_area": "珠江口",
                "local_area": "深圳湾",
                "feature_name": "深圳湾水域",
                "area_label": "珠江口深圳湾周边",
                "display_name": "珠江口深圳湾及后海湾周边",
                "area_kind": "water",
                "bounds": (22.38, 22.62, 113.86, 114.10),
            },
            {
                "key": "zhuhai_east_coast",
                "macro_area": "珠江口",
                "local_area": "珠海东岸",
                "feature_name": "珠海东部近岸带",
                "area_label": "珠江口珠海东岸周边",
                "display_name": "珠江口珠海东岸及近岸水域",
                "area_kind": "regional",
                "bounds": (21.95, 22.38, 113.45, 113.72),
            },
            {
                "key": "lingdingyang",
                "macro_area": "珠江口",
                "local_area": "伶仃洋",
                "feature_name": "伶仃洋水域",
                "area_label": "珠江口伶仃洋水域",
                "display_name": "珠江口伶仃洋及粤港澳近岸水域",
                "area_kind": "water",
                "bounds": (21.95, 22.72, 113.55, 114.05),
            },
            {
                "key": "macao_western_waters",
                "macro_area": "珠江口",
                "local_area": "澳门近岸",
                "feature_name": "澳门西侧近岸水域",
                "area_label": "珠江口澳门近岸周边",
                "display_name": "珠江口澳门近岸及珠海横琴周边",
                "area_kind": "water",
                "bounds": (21.98, 22.25, 113.45, 113.62),
            },
        ]

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

    def _collect_spatial_features(
        self,
        lat: float,
        lon: float,
        radius_m: int,
        *,
        per_subtype_limit: int = 4,
        feature_limit: int = 28,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        granularity = granularity_for_radius(radius_m)
        regional = granularity == "city_region"
        # Final map nodes must be explainable places.  Unnamed land-use/natural
        # geometry explodes response size and cannot produce a useful place
        # label, so it belongs in a raster/geometry pipeline rather than this
        # point skeleton query.
        named_filter = "[name]"
        road_types = "motorway|trunk|primary" if regional else "motorway|trunk|primary|secondary|tertiary"
        timeout_seconds = max(8, min(int(Config.OVERPASS_QUERY_TIMEOUT_SECONDS), 45))
        # Large AOIs use two low-cardinality boundary queries.  A 37.5 km
        # ``nwr`` union around Taipei previously exceeded the public server's
        # declared 32 MiB working set before it could return a single object.
        # The containing-boundary query is both more relevant to city-level
        # selection and much cheaper than scanning every POI in the circle.
        administrative_query = (
            f"is_in({lat},{lon})->.containing;\n"
            'rel(pivot.containing)[boundary="administrative"]'
            '[admin_level~"4|5|6|7|8|9|10"][name];'
        )
        if regional:
            query_batches = [
                ("administrative", administrative_query),
                (
                    "regional_boundaries",
                    "(\n  "
                    + f'rel(around:{radius_m},{lat},{lon})[boundary="administrative"][admin_level~"4|5|6"][name];\n  '
                    + f'rel(around:{radius_m},{lat},{lon})[boundary="protected_area"][name];\n'
                    + ");",
                ),
            ]
        else:
            thematic_radius = radius_m if radius_m <= 15_000 else 12_000
            infrastructure_radius = radius_m if radius_m <= 15_000 else 8_000
            query_batches = [
                ("administrative", administrative_query),
                (
                    "water_ecology",
                    "(\n  "
                    + f"nwr(around:{thematic_radius},{lat},{lon})[natural]{named_filter};\n  "
                    + f"nwr(around:{thematic_radius},{lat},{lon})[waterway]{named_filter};\n  "
                    + f'nwr(around:{thematic_radius},{lat},{lon})[landuse~"farmland|forest|reservoir|meadow|basin|farmyard"]{named_filter};\n  '
                    + f'nwr(around:{thematic_radius},{lat},{lon})[leisure~"park|nature_reserve|marina|garden|playground"][name];\n'
                    + ");",
                ),
                (
                    "human_infrastructure",
                    "(\n  "
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[landuse~"industrial|residential|commercial|retail"]{named_filter};\n  '
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[amenity~"wastewater_plant|hospital|school|university|marketplace|bus_station|ferry_terminal|police|fire_station|townhall"][name];\n  '
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[man_made~"pier|breakwater|groyne"]{named_filter};\n  '
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[power="plant"][name];\n'
                    + ");",
                ),
                (
                    "transport",
                    "(\n  "
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[highway~"{road_types}"][name];\n  '
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[public_transport~"station|stop_position|platform"][name];\n  '
                    + f'nwr(around:{infrastructure_radius},{lat},{lon})[railway~"station|halt|subway_entrance|tram_stop"][name];\n'
                    + ");",
                ),
            ]
        cache_key = self._source_cache_key(
            "overpass",
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            profile=f"{granularity}:v4-batched-named",
        )
        cached = self._read_source_cache("overpass", cache_key)
        if cached:
            cached_status = dict(cached.get("status") or {})
            cached_status["query_strategy"] = "thematic_batches"
            cached_status["cache_policy"] = "fresh_cache_first"
            return self._refresh_cached_feature_distances(
                cached.get("features") or [],
                lat=lat,
                lon=lon,
            ), cached_status
        maxsize_bytes = max(16 * 1024 * 1024, int(Config.OVERPASS_MAXSIZE_BYTES))
        output_limit = max(120, min(600, int(feature_limit or 28) * 6))
        last_error = None
        attempts: List[Dict[str, Any]] = []
        batch_summaries: List[Dict[str, Any]] = []
        elements: List[Dict[str, Any]] = []
        successful_batches = 0
        failed_batches = 0
        started_at = time.monotonic()
        for batch_name, query_body in query_batches:
            query = (
                f"[out:json][timeout:{timeout_seconds}][maxsize:{maxsize_bytes}];\n"
                + query_body
                + f"\nout center tags qt {output_limit};\n"
            )
            batch_payload = None
            batch_error = None
            batch_attempts: List[Dict[str, Any]] = []
            batch_started = time.monotonic()
            for endpoint in list(Config.OVERPASS_ENDPOINTS or []):
                endpoint_started = time.monotonic()
                try:
                    candidate_payload = _safe_http_json(
                        endpoint,
                        method="POST",
                        data=query,
                        headers={
                            "Content-Type": "text/plain;charset=utf-8",
                            "Accept": "application/json",
                            "User-Agent": "Kaleido/0.1 map-seed (+https://github.com/crisisjungle/Kaleido)",
                        },
                        timeout=max(10.0, float(Config.OVERPASS_HTTP_TIMEOUT_SECONDS)),
                    )
                    if not isinstance(candidate_payload, dict) or not isinstance(candidate_payload.get("elements"), list):
                        raise ValueError("Overpass returned an invalid payload")
                    remark = str(
                        candidate_payload.get("remark")
                        or (candidate_payload.get("osm3s") or {}).get("remark")
                        or ""
                    ).strip()
                    if remark:
                        raise RuntimeError(f"Overpass runtime error: {remark}")
                    batch_payload = candidate_payload
                    attempt = {
                        "batch": batch_name,
                        "endpoint": endpoint,
                        "status": "completed",
                        "elapsed_ms": round((time.monotonic() - endpoint_started) * 1000),
                    }
                    batch_attempts.append(attempt)
                    attempts.append(attempt)
                    break
                except Exception as exc:
                    last_error = exc
                    batch_error = exc
                    attempt = {
                        "batch": batch_name,
                        "endpoint": endpoint,
                        "status": "failed",
                        "error": str(exc),
                        "elapsed_ms": round((time.monotonic() - endpoint_started) * 1000),
                    }
                    batch_attempts.append(attempt)
                    attempts.append(attempt)
                    logger.warning(f"Overpass batch {batch_name} failed via {endpoint}: {exc}")

            if batch_payload is None:
                failed_batches += 1
                batch_summaries.append(
                    {
                        "batch": batch_name,
                        "status": "failed",
                        "error": str(batch_error or "No Overpass endpoint configured"),
                        "attempts": batch_attempts,
                        "elapsed_ms": round((time.monotonic() - batch_started) * 1000),
                    }
                )
                continue

            batch_elements = list(batch_payload.get("elements") or [])
            elements.extend(batch_elements)
            successful_batches += 1
            batch_summaries.append(
                {
                    "batch": batch_name,
                    "status": "completed",
                    "raw_element_count": len(batch_elements),
                    "attempts": batch_attempts,
                    "elapsed_ms": round((time.monotonic() - batch_started) * 1000),
                }
            )

        if successful_batches == 0:
            cached = self._read_source_cache("overpass", cache_key)
            if cached:
                cached_status = dict(cached.get("status") or {})
                cached_status["live_attempts"] = attempts
                cached_status["live_error"] = str(last_error or "")
                cached_status["batches"] = batch_summaries
                return self._refresh_cached_feature_distances(
                    cached.get("features") or [],
                    lat=lat,
                    lon=lon,
                ), cached_status
            if last_error:
                logger.warning(f"All Overpass endpoints failed, continuing with fallback features: {last_error}")
            return [], {
                "status": "failed",
                "provider": "osm_overpass",
                "error": str(last_error or "No Overpass endpoint configured"),
                "attempts": attempts,
                "batches": batch_summaries,
                "batch_count": len(query_batches),
                "failed_batch_count": failed_batches,
                "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                "granularity": granularity,
                "query_profile": "named_macro" if regional else "named_local",
                "query_strategy": "thematic_batches",
                "maxsize_bytes": maxsize_bytes,
            }

        features: List[Dict[str, Any]] = []
        seen_ids = set()
        for element in elements:
            element_id = f"{element.get('type', 'item')}_{element.get('id')}"
            if element_id in seen_ids:
                continue
            seen_ids.add(element_id)
            tags = dict(element.get("tags") or {})
            tags["provider"] = "osm_overpass"
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
                    "spatial_level": classification.get("spatial_level") or "",
                }
            )

        cached_feature_count = 0
        if failed_batches:
            cached = self._read_source_cache("overpass", cache_key)
            if cached:
                cached_features = self._refresh_cached_feature_distances(
                    cached.get("features") or [],
                    lat=lat,
                    lon=lon,
                )
                cached_feature_count = len(cached_features)
                features = self._merge_feature_lists(features, cached_features)

        features.sort(key=lambda item: (-item["importance"], item["distance_m"], item["name"]))

        selected: List[Dict[str, Any]] = []
        subtype_counts: Dict[str, int] = {}
        for feature in features:
            subtype = feature["subtype"]
            if subtype_counts.get(subtype, 0) >= per_subtype_limit:
                continue
            selected.append(feature)
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
            if len(selected) >= feature_limit:
                break
        failed_batch_errors = [
            str(item.get("error") or "")
            for item in batch_summaries
            if item.get("status") == "failed" and str(item.get("error") or "").strip()
        ]
        if selected:
            provider_status = "completed" if failed_batches == 0 else "partial"
        else:
            provider_status = "failed" if failed_batches else "empty"
        status = {
            "status": provider_status,
            "provider": "osm_overpass",
            "feature_count": len(selected),
            "raw_element_count": len(elements),
            "classified_feature_count": len(features),
            "cached_feature_count": cached_feature_count,
            "attempts": attempts,
            "batches": batch_summaries,
            "batch_count": len(query_batches),
            "successful_batch_count": successful_batches,
            "failed_batch_count": failed_batches,
            "error": "; ".join(dict.fromkeys(failed_batch_errors)),
            "elapsed_ms": round((time.monotonic() - started_at) * 1000),
            "granularity": granularity,
            "query_profile": "named_macro" if regional else "named_local",
            "query_strategy": "thematic_batches",
            "maxsize_bytes": maxsize_bytes,
            "cache_key": cache_key,
        }
        if selected:
            self._write_source_cache(
                "overpass",
                cache_key,
                features=selected,
                status=status,
            )
        return selected, status

    def _collect_worldcover_features(
        self,
        *,
        lat: float,
        lon: float,
        radius_m: int,
        components_per_class: int = 2,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
        cache_key = self._source_cache_key(
            "worldcover",
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            profile=(
                "wms-v4-official-contextual-reference:"
                f"{Config.WORLDCOVER_WMS_VERSION}:"
                f"{Config.WORLDCOVER_WMS_LAYER}:"
                f"{Config.WORLDCOVER_WMS_TIME}:"
                f"{components_per_class}"
            ),
        )
        cached = self._read_source_cache("worldcover", cache_key)
        if cached:
            cached_status = dict(cached.get("status") or {})
            cached_status["cache_policy"] = "fresh_cache_first"
            return (
                self._refresh_cached_feature_distances(
                    cached.get("features") or [],
                    lat=lat,
                    lon=lon,
                ),
                cached_status,
                list(cached.get("layers") or []),
            )
        bbox = _radius_to_bbox(lat, lon, radius_m)
        minx, miny = _lonlat_to_mercator(bbox["min_lon"], bbox["min_lat"])
        maxx, maxy = _lonlat_to_mercator(bbox["max_lon"], bbox["max_lat"])
        wms_version = str(Config.WORLDCOVER_WMS_VERSION or "1.3.0").strip()
        wms_layer = str(Config.WORLDCOVER_WMS_LAYER or "esa-worldcover-map-10m-2021-v2_map").strip()
        wms_time = str(Config.WORLDCOVER_WMS_TIME or "2021-01-01").strip()
        params = {
            "service": "WMS",
            "version": wms_version,
            "request": "GetMap",
            "layers": wms_layer,
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "width": "256",
            "height": "256",
            "styles": "",
            "format": "image/png",
            "transparent": "true",
            "time": wms_time,
        }
        params["crs" if wms_version.startswith("1.3") else "srs"] = "EPSG:3857"
        url = str(Config.WORLDCOVER_WMS_URL).rstrip("?") + "?" + urllib.parse.urlencode(params)

        image = None
        last_error = None
        attempts: List[Dict[str, Any]] = []
        attempt_count = max(1, min(int(Config.WORLDCOVER_WMS_ATTEMPTS), 3))
        for attempt in range(attempt_count):
            started_at = time.monotonic()
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Kaleido/0.1 map-seed (+https://github.com/crisisjungle/Kaleido)",
                        "Accept": "image/png",
                    },
                )
                with urllib.request.urlopen(
                    request,
                    timeout=max(3.0, float(Config.WORLDCOVER_WMS_TIMEOUT_SECONDS)),
                ) as response:
                    image = Image.open(io.BytesIO(response.read())).convert("RGBA")
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "status": "completed",
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    }
                )
                break
            except Exception as exc:
                last_error = exc
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "status": "failed",
                        "error": str(exc),
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                    }
                )
                logger.warning(f"WorldCover GetMap failed (attempt {attempt + 1}/{attempt_count}): {exc}")
                if attempt + 1 < attempt_count:
                    time.sleep(0.6)
        if image is None:
            cached = self._read_source_cache("worldcover", cache_key)
            if cached:
                cached_status = dict(cached.get("status") or {})
                cached_status["live_attempts"] = attempts
                cached_status["live_error"] = str(last_error or "")
                return (
                    self._refresh_cached_feature_distances(
                        cached.get("features") or [],
                        lat=lat,
                        lon=lon,
                    ),
                    cached_status,
                    list(cached.get("layers") or []),
                )
            return [], {
                "status": "failed",
                "provider": "worldcover_wms",
                "product": "WorldCover 2021 v200",
                "endpoint": str(Config.WORLDCOVER_WMS_URL),
                "wms_version": wms_version,
                "layer": wms_layer,
                "time": wms_time,
                "error": str(last_error or "WorldCover WMS unavailable"),
                "attempts": attempts,
                "analysis_grade": "contextual_only",
                "note": "WorldCover WMS 未能获取；该 RGB 地图服务本来也只作为背景分类参考，不作为正式分析事实。",
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

            for index, component in enumerate(components[:components_per_class], start=1):
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
                        # The public WMS is an RGB cartographic layer.  Preserve
                        # its polygons as contextual reference, not analysis-
                        # grade detected evidence (official COGs are required
                        # for that stronger claim).
                        "source_kind": "reference",
                        "lat": round(centroid_lat, 6),
                        "lon": round(centroid_lon, 6),
                        "distance_m": round(_haversine_m(lat, lon, centroid_lat, centroid_lon), 1),
                        "importance": class_meta["importance"],
                        "summary": summary,
                        "geometry": geometry,
                        "tags": {
                            "provider": "worldcover_wms",
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
                        "source_provider": "worldcover_wms",
                        "analysis_grade": "contextual_only",
                        "color": self._rgb_to_hex(class_meta["color"]),
                        "visible": True,
                        "note": "ESA WorldCover 2021 v200 WMS 背景分类参考（非分析级栅格）",
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
            "provider": "worldcover_wms",
            "product": "WorldCover 2021 v200",
            "endpoint": str(Config.WORLDCOVER_WMS_URL),
            "wms_version": wms_version,
            "layer": wms_layer,
            "time": wms_time,
            "mode": "wms_classified_png_sampling",
            "analysis_grade": "contextual_only",
            "attempts": attempts,
            "cache_key": cache_key,
            "detected_features_count": len(detected_features),
            "contextual_features_count": len(detected_features),
            "detected_classes": detected_classes,
            "note": "基于 WorldCover WMS RGB 图层的背景分类参考；官方说明 WMS 适合制图、不适合作为分析数据。正式分析应切换到 COG/自托管栅格。",
        }
        if detected_features:
            self._write_source_cache(
                "worldcover",
                cache_key,
                features=detected_features,
                status=remote_summary,
                layers=remote_layers,
            )
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

        admin_candidates = [
            ("city", str(admin_context.get("city") or "").strip()),
            ("district", str(admin_context.get("district") or admin_context.get("suburb") or "").strip()),
        ]
        for level_hint, place_name in admin_candidates:
            if not place_name:
                continue
            if any(
                str(item.get("name") or "").strip() == place_name
                and str((item.get("tags") or {}).get("provider") or "") == "reverse_geocode"
                for item in merged
            ):
                continue
            if place_name.endswith(("街道", "镇", "乡")):
                subtype = "subdistrict"
                spatial_level = "street"
            elif place_name.endswith(("区", "县")):
                subtype = "admin_district"
                spatial_level = "district"
            else:
                subtype = "admin_city" if level_hint == "city" else "admin_district"
                spatial_level = "city" if level_hint == "city" else "district"
            add_feature(
                {
                    "feature_id": f"context_admin_{level_hint}_{_slugify(place_name)}",
                    "name": place_name,
                    "category": "region",
                    "subtype": subtype,
                    "node_family": "Region",
                    "source_kind": "observed",
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "distance_m": 0.0,
                    "importance": 10 if spatial_level in {"city", "district"} else 8,
                    "summary": "来自中心点逆地理编码的行政归属，只用于范围层级与关注区域判断。",
                    "tags": {
                        "provider": "reverse_geocode",
                        "spatial_level": spatial_level,
                        "admin_context": True,
                    },
                    "spatial_level": spatial_level,
                    "confidence": 0.86,
                }
            )

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

    def _filter_features_to_aoi(self, features: List[Dict[str, Any]], radius_m: int) -> List[Dict[str, Any]]:
        radius = max(500.0, float(radius_m or 3000))
        tolerance_m = max(150.0, min(500.0, radius * 0.03))
        limit_m = radius + tolerance_m
        scoped: List[Dict[str, Any]] = []
        for feature in features:
            subtype = str(feature.get("subtype") or "")
            if subtype == "weather_baseline":
                scoped.append(feature)
                continue
            try:
                distance_m = float(feature.get("distance_m"))
            except (TypeError, ValueError):
                continue
            if distance_m <= limit_m:
                scoped.append(feature)
        return scoped

    def _wuhan_curated_features(self, lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
        del radius_m
        anchors = [
            ("wuhan_huanan_market", "华南海鲜批发市场", 30.6185, 114.2573, "facility", "marketplace", "Infrastructure", 10, "疫情早期报告中反复出现的市场接触锚点。"),
            ("wuhan_jinyintan_hospital", "武汉市金银潭医院", 30.6583, 114.2358, "facility", "hospital", "Infrastructure", 10, "传染病收治与救治压力的重要医疗节点。"),
            ("wuhan_tongji_hospital", "华中科技大学同济医院", 30.6132, 114.2860, "facility", "hospital", "Infrastructure", 9, "核心综合医院与跨区就医节点。"),
            ("wuhan_union_hospital", "武汉协和医院", 30.5937, 114.2823, "facility", "hospital", "Infrastructure", 9, "核心综合医院与医疗资源调度节点。"),
            ("wuhan_central_hospital", "武汉市中心医院", 30.5970, 114.2840, "facility", "hospital", "Infrastructure", 9, "早期接诊与医护暴露压力节点。"),
            ("wuhan_zhongnan_hospital", "武汉大学中南医院", 30.5381, 114.3590, "facility", "hospital", "Infrastructure", 8, "武昌片区重点医疗节点。"),
            ("wuhan_renmin_hospital", "武汉大学人民医院", 30.5368, 114.3053, "facility", "hospital", "Infrastructure", 8, "跨江就医网络中的综合医院节点。"),
            ("wuhan_huoshenshan", "火神山医院", 30.5294, 114.0841, "facility", "emergency_hospital", "Infrastructure", 9, "疫情高压期快速建设的专门收治节点。"),
            ("wuhan_leishenshan", "雷神山医院", 30.4409, 114.2660, "facility", "emergency_hospital", "Infrastructure", 9, "疫情高压期快速建设的专门收治节点。"),
            ("wuhan_hankou_station", "汉口火车站", 30.6188, 114.2544, "facility", "rail_station", "Infrastructure", 9, "春运与跨城流动的重要铁路门户。"),
            ("wuhan_wuchang_station", "武昌火车站", 30.5284, 114.3162, "facility", "rail_station", "Infrastructure", 8, "武昌片区铁路流动节点。"),
            ("wuhan_railway_station", "武汉火车站", 30.6096, 114.4211, "facility", "rail_station", "Infrastructure", 8, "高铁枢纽与跨区域连接节点。"),
            ("wuhan_tianhe_airport", "武汉天河国际机场", 30.7838, 114.2081, "facility", "airport", "Infrastructure", 8, "城市空港门户与跨区域流动节点。"),
            ("wuhan_yangtze", "长江武汉段", 30.5530, 114.3000, "ecology", "river", "EnvironmentalCarrier", 8, "城市空间分割、桥梁通勤和物流通道的水系骨架。"),
            ("wuhan_han_river", "汉江入江口", 30.5660, 114.2850, "ecology", "river", "EnvironmentalCarrier", 7, "汉江与长江交汇区，影响跨江通达与片区联系。"),
            ("wuhan_east_lake", "东湖水域", 30.5580, 114.4080, "ecology", "lake", "EnvironmentalCarrier", 7, "大型城市湖泊与公共空间节点。"),
            ("wuhan_shahu", "沙湖水域", 30.5850, 114.3420, "ecology", "lake", "EnvironmentalCarrier", 6, "武昌核心区湖泊与城市开放空间。"),
            ("wuhan_south_lake", "南湖片区", 30.4970, 114.3500, "ecology", "lake", "EnvironmentalCarrier", 6, "高校与居民片区周边水域空间。"),
            ("wuhan_first_bridge", "武汉长江大桥", 30.5533, 114.2871, "facility", "bridge", "Infrastructure", 8, "跨江交通骨架与流动瓶颈节点。"),
            ("wuhan_second_bridge", "武汉长江二桥", 30.6080, 114.3120, "facility", "bridge", "Infrastructure", 7, "汉口与武昌之间的跨江通勤通道。"),
            ("wuhan_erqi_bridge", "二七长江大桥", 30.6400, 114.3370, "facility", "bridge", "Infrastructure", 7, "东北向跨江连接与工业片区通达节点。"),
            ("wuhan_yingwuzhou_bridge", "鹦鹉洲长江大桥", 30.5320, 114.2730, "facility", "bridge", "Infrastructure", 7, "汉阳与武昌之间的跨江连接节点。"),
            ("wuhan_jianghan_district", "江汉区", 30.6035, 114.2705, "region", "admin_district", "Region", 8, "市场、商业与交通节点密集的核心城区。"),
            ("wuhan_jiangan_district", "江岸区", 30.6358, 114.3097, "region", "admin_district", "Region", 7, "医疗、社区和交通走廊叠加片区。"),
            ("wuhan_qiaokou_district", "硚口区", 30.5856, 114.2444, "region", "admin_district", "Region", 7, "供应、医疗和老城区社区联系片区。"),
            ("wuhan_hanyang_district", "汉阳区", 30.5547, 114.2179, "region", "admin_district", "Region", 7, "跨江连接、医院建设与物流通道片区。"),
            ("wuhan_wuchang_district", "武昌区", 30.5467, 114.3162, "region", "admin_district", "Region", 8, "治理核心、高校医院和跨江联系片区。"),
            ("wuhan_hongshan_district", "洪山区", 30.5151, 114.3663, "region", "admin_district", "Region", 7, "高校、社区与医疗服务混合片区。"),
            ("wuhan_baibuting", "百步亭社区", 30.6370, 114.2840, "facility", "residential", "Infrastructure", 7, "大型社区与基层治理响应节点。"),
            ("wuhan_cdc", "武汉市疾控中心", 30.5870, 114.2840, "facility", "public_health", "Infrastructure", 9, "流调、监测和公共卫生信息协同节点。"),
            ("hubei_cdc", "湖北省疾控中心", 30.5200, 114.3480, "facility", "public_health", "Infrastructure", 8, "省级公共卫生协调与风险研判节点。"),
            ("wuhan_logistics_hub", "汉口北物流商贸区", 30.7240, 114.3000, "facility", "warehouse", "Infrastructure", 7, "民生物资、商贸和跨区配送节点。"),
        ]
        features: List[Dict[str, Any]] = []
        for feature_id, name, feature_lat, feature_lon, category, subtype, node_family, importance, summary in anchors:
            features.append(
                {
                    "feature_id": f"curated_{feature_id}",
                    "name": name,
                    "category": category,
                    "subtype": subtype,
                    "node_family": node_family,
                    "source_kind": "observed",
                    "lat": feature_lat,
                    "lon": feature_lon,
                    "distance_m": round(_haversine_m(lat, lon, feature_lat, feature_lon), 1),
                    "importance": importance,
                    "summary": summary,
                    "tags": {"provider": "golden_case_curated", "golden_case_profile": "wuhan_covid_v1"},
                    "confidence": 0.92,
                }
            )
        return features

    def _local_curated_features(self, lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
        local = self._local_geographic_context(lat, lon)
        if not local:
            return []

        anchors = [
            ("sz_guangming_district", "光明区", 22.748, 113.936, "region", "admin_district", "Region", 10, "深圳北部城市与产业片区，连接茅洲河流域、山地生态和高密度建设空间。"),
            ("sz_fenghuang_subdistrict", "凤凰街道", 22.745, 113.976, "region", "subdistrict", "Region", 9, "光明区南部街道，靠近截图选点位置，是城市建设与社区承压分析的近场锚点。"),
            ("sz_gongming_subdistrict", "公明街道", 22.792, 113.902, "region", "subdistrict", "Region", 9, "光明区西北部街道，承接产业、居住与水系廊道交互压力。"),
            ("sz_guangming_science_city", "光明科学城", 22.750, 113.962, "facility", "science_city", "Infrastructure", 9, "光明区核心科创与公共服务集聚区，代表高强度城市活动和应急服务需求。"),
            ("sz_maozhou_river", "茅洲河", 22.785, 113.830, "ecology", "river", "EnvironmentalCarrier", 8, "深圳西北部重要河流廊道，暴雨或台风情景下与地表径流、内涝扩散相关。"),
            ("sz_shiyan_reservoir", "石岩水库", 22.668, 113.943, "ecology", "reservoir", "EnvironmentalCarrier", 8, "宝安与光明交界附近的重要水源与生态空间，对洪涝调蓄和生态稳态有约束意义。"),
            ("sz_yangtaishan", "阳台山森林公园", 22.659, 114.004, "ecology", "forest_park", "EcologicalReceptor", 8, "深圳西部山地生态屏障，影响坡面径流、生态栖息地和城市边缘风险。"),
            ("sz_north_station", "深圳北站", 22.611, 114.030, "facility", "rail_station", "Infrastructure", 7, "深圳北部综合交通枢纽，适合用于分析人流、疏散和跨区联动压力。"),
            ("sz_baoan_airport", "深圳宝安国际机场", 22.637, 113.810, "facility", "airport", "Infrastructure", 7, "区域级交通基础设施，在台风、暴雨和应急物流场景中具有高敏感性。"),
            ("prd_lingdingyang", "伶仃洋水域", 22.37, 113.76, "ecology", "water", "EnvironmentalCarrier", 10, "珠江口核心水域，是风暴潮、洪水下泄和近岸生态压力耦合的关键空间。"),
            ("prd_pearl_river_estuary", "珠江口", 22.33, 113.70, "region", "coastline", "Region", 10, "粤港澳近岸水系与海湾交换的宏观地理锚点。"),
            ("prd_shenzhen_bay", "深圳湾", 22.49, 113.99, "ecology", "wetland", "EnvironmentalCarrier", 9, "珠江口东侧的重要海湾与湿地生态空间。"),
            ("prd_zhuhai_east_coast", "珠海东岸", 22.25, 113.60, "region", "coastline", "Region", 9, "珠江口西侧城市近岸带，连接港口、居住区和滨海生态空间。"),
            ("prd_qianhai", "前海片区", 22.53, 113.89, "facility", "commercial", "Infrastructure", 8, "深圳湾北侧高强度城市开发与服务设施集聚片区。"),
            ("prd_hongkong_wetland_park", "香港湿地公园周边", 22.47, 114.00, "ecology", "protected_area", "EcologicalReceptor", 8, "后海湾湿地生态与候鸟栖息相关的重要生态锚点。"),
            ("prd_hongkong_zhuhai_macao_bridge", "港珠澳大桥通道", 22.28, 113.78, "facility", "road_corridor", "Infrastructure", 8, "跨珠江口的交通廊道，可能影响应急通达、物流和跨区联动。"),
            ("prd_macao_nearshore", "澳门近岸水域", 22.17, 113.55, "ecology", "water", "EnvironmentalCarrier", 7, "珠江口西南侧高密度城市近岸水域。"),
        ]

        local_key = str(local.get("key") or "")
        distance_limit = max(radius_m * 1.2, 8000)
        if local_key.startswith("shenzhen_") and local_key != "shenzhen_bay":
            distance_limit = max(radius_m * 1.35, 30000)

        features: List[Dict[str, Any]] = []
        for feature_id, name, feature_lat, feature_lon, category, subtype, node_family, importance, summary in anchors:
            distance_m = _haversine_m(lat, lon, feature_lat, feature_lon)
            if distance_m > distance_limit:
                continue
            features.append(
                {
                    "feature_id": f"local_{feature_id}",
                    "name": name,
                    "category": category,
                    "subtype": subtype,
                    "node_family": node_family,
                    "source_kind": "reference",
                    "lat": feature_lat,
                    "lon": feature_lon,
                    "distance_m": round(distance_m, 1),
                    "importance": importance,
                    "summary": summary,
                    "tags": {
                        "provider": "local_geographic_gazetteer",
                        "local_context": local.get("key", ""),
                    },
                    "confidence": 0.68,
                }
            )
        return features

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
        if boundary == "administrative":
            try:
                admin_level = int(tags.get("admin_level") or 99)
            except (TypeError, ValueError):
                admin_level = 99
            if admin_level <= 5:
                subtype = "admin_city"
                spatial_level = "city"
            elif admin_level <= 8:
                subtype = "admin_district"
                spatial_level = "district"
            else:
                subtype = "subdistrict"
                spatial_level = "street"
            return {
                "category": "region",
                "subtype": subtype,
                "node_family": "Region",
                "importance": 9 if spatial_level != "street" else 7,
                "confidence": 0.88,
                "summary": f"OSM 行政边界 admin_level={admin_level}。",
                "default_name": "Administrative area",
                "spatial_level": spatial_level,
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
            "mixed": 0,
        }
        evidence_feature_count = 0
        for feature in features:
            tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
            provider = str(tags.get("provider") or feature.get("source_provider") or "").strip().lower()
            source_kind = str(feature.get("source_kind") or "").strip().lower()
            if provider not in PUBLIC_PROVIDERS or source_kind not in {"observed", "detected"}:
                continue
            subtype = str(feature.get("subtype") or "")
            contributed = False
            if subtype in {"beach", "coastline", "pier", "marina", "breakwater", "groyne"}:
                scores["coastal"] += 3
                contributed = True
            if subtype in {"river", "stream", "canal", "ditch", "water", "reservoir", "basin", "worldcover_80"}:
                scores["inland_water"] += 2
                contributed = True
            if subtype in {"wetland", "worldcover_90", "worldcover_95"}:
                scores["wetland"] += 4
                contributed = True
            if subtype in {"industrial", "commercial", "residential", "hospital", "school", "university", "worldcover_50"}:
                scores["urban_edge"] += 2
                contributed = True
            if subtype in {"farmland", "farmyard", "meadow", "worldcover_40"}:
                scores["agricultural"] += 3
                contributed = True
            if contributed:
                evidence_feature_count += 1

        ranked = sorted(
            ((key, value) for key, value in scores.items() if key != "mixed" and value > 0),
            key=lambda item: (-item[1], item[0]),
        )
        place = str(admin_context.get("display_name") or "选定区域")
        if not ranked:
            return {
                "primary_scene": "unknown",
                "classification_ready": False,
                "scores": scores,
                "evidence_feature_count": 0,
                "reasoning": f"已取得 {place} 的范围或行政空间数据，但环境类型证据不足，本轮不判断区域类型。",
            }

        title = ranked[0][0]
        if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.6:
            title = "mixed"
            scores["mixed"] = ranked[0][1] + ranked[1][1]
        scene_label = _display_token_zh(title)
        return {
            "primary_scene": title,
            "classification_ready": True,
            "scores": scores,
            "evidence_feature_count": evidence_feature_count,
            "reasoning": f"根据 {place} 范围内 {evidence_feature_count} 个合格空间要素，主要呈现为{scene_label}。",
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
        data_quality: Optional[Dict[str, Any]] = None,
        selection_summary: Optional[Dict[str, Any]] = None,
        feature_limit: int = 18,
        llm_edge_limit: int = 6,
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        center = aoi["center"]
        place_label = self._context_place_label(admin_context, fallback=seed["seed_id"])
        region_id = f"region_{_slugify(place_label)}"
        region_node = self._make_graph_node(
            node_id=region_id,
            name=place_label or "选定区域",
            label="区域",
            summary=(
                f"中心点 ({center['lat']}, {center['lon']}) 周边 {aoi['radius_m']} 米分析范围，"
                f"场景类型判断为 {_display_token_zh(scene_classification.get('primary_scene'))}。"
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
                "data_quality": dict(data_quality or {}),
                "selection_summary": dict(selection_summary or {}),
            },
        )
        nodes.append(region_node)

        feature_nodes: List[Dict[str, Any]] = []
        for feature in features[:feature_limit]:
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
                    "spatial_level": feature.get("selection_spatial_level")
                    or feature.get("spatial_level")
                    or (feature.get("tags") or {}).get("spatial_level"),
                    "selection_score": feature.get("selection_score"),
                    "selection_focus_score": feature.get("selection_focus_score"),
                    "selection_sector": feature.get("selection_sector"),
                    "selection_reasons": list(feature.get("selection_reasons") or []),
                    "source_provider": (feature.get("tags") or {}).get("provider"),
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
            edge_limit=llm_edge_limit,
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
            "data_quality": dict(data_quality or {}),
            "selection_summary": dict(selection_summary or {}),
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "observed_nodes": len([node for node in nodes if node["attributes"]["source_kind"] == "observed"]),
                "detected_nodes": len([node for node in nodes if node["attributes"]["source_kind"] == "detected"]),
                "reference_nodes": len([node for node in nodes if node["attributes"]["source_kind"] == "reference"]),
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

        def nearest_anchor(
            candidates: Iterable[Dict[str, Any]],
            *,
            allow_center_fallback: bool = True,
        ) -> Tuple[Optional[float], Optional[float], Optional[str]]:
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
            if allow_center_fallback:
                return center["lat"], center["lon"], None
            return None, None, None

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
            valid_anchors = [
                node
                for node in spec["anchors"]
                if is_valid_proxy_anchor(
                    spec["key"],
                    {
                        "category": node["attributes"].get("category"),
                        "subtype": node["attributes"].get("subtype"),
                        "tags": node["attributes"].get("tags") or {},
                    },
                )
            ]
            lat_value, lon_value, anchor_id = nearest_anchor(
                valid_anchors,
                # A proxy may exist conceptually at AOI level, but the circle
                # center is never evidence for its physical location.
                allow_center_fallback=False,
            )
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
                    "spatial_precision": "site_approximate" if anchor_id else "area_only",
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
        edge_limit: int = 6,
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
            for node in feature_nodes[:max(10, min(edge_limit, 30))]
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
            "task": f"Add at most {edge_limit} plausible semantic relations between proxy actors and nearby observed spatial nodes.",
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
                "The fact field must be Simplified Chinese. Keep relation identifiers in English only as machine keys.",
            ],
            "output_schema": {
                "edges": [
                    {
                        "source": "proxy_node_id",
                        "target": "observed_node_id",
                        "relation": "depends_on",
                        "fact": "中文关系说明",
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
                        "content": "You return compact JSON with only explainable graph edges. User-facing fact text must be Simplified Chinese.",
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
        return edges[:edge_limit]

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
        data_quality: Optional[Dict[str, Any]] = None,
        selection_summary: Optional[Dict[str, Any]] = None,
    ) -> str:
        center = aoi["center"]
        top_features = features[:8]
        feature_lines = [
            f"- {item['name']} ({_display_token_zh(item['subtype'])}，{item['distance_m']}m，{_display_token_zh(item['source_kind'])})"
            for item in top_features
        ]
        proxy_lines = [
            f"- {node['name']} ({_display_token_zh(node['attributes'].get('proxy_role'))}，{_display_token_zh(node['attributes'].get('source_kind'))})"
            for node in graph["nodes"]
            if node["attributes"].get("category") == "human_proxy"
        ]
        weather = environment_baseline.get("current") or {}
        title = seed.get("title") or "地图种子报告"
        requirement = seed.get("input", {}).get("simulation_requirement") or "未提供额外模拟需求。"
        quality = dict(data_quality or {})
        selection = dict(selection_summary or {})
        selected_diagnostics = dict(selection.get("diagnostics") or {})
        source_note = quality.get("warning") or "公网空间事实可用；仍需按来源类型区分观测、遥感与推断。"
        return "\n".join(
            [
                f"# {title}",
                "",
                "## 1. 数据质量与选点规则",
                f"- 数据质量: {_display_token_zh(quality.get('status', 'unknown'))}",
                f"- 可用于正式空间判断: {'是' if quality.get('formal_ready') else '否'}",
                f"- 选点粒度: {_display_token_zh(selection.get('granularity') or quality.get('granularity') or 'unknown')}",
                f"- 用户明确焦点: {'是' if selected_diagnostics.get('explicit_focus') else '否'}",
                f"- 选点策略: {_display_token_zh(quality.get('selection_policy') or 'explicit_focus_then_spatial_category_balance')}",
                f"- 提示: {source_note}",
                "",
                "## 2. 选点概览",
                f"- 中心点: {center['lat']}, {center['lon']}",
                f"- 分析半径: {aoi['radius_m']} 米",
                f"- 行政与地点描述: {admin_context.get('display_name')}",
                (
                    f"- 场景类型判定: {_display_token_zh(scene_classification.get('primary_scene'))}"
                    if scene_classification.get("classification_ready") is True
                    else "- 场景类型判定: 证据不足，暂不判断"
                ),
                "",
                "## 3. 环境基线",
                f"- 当前温度: {weather.get('temperature_2m', 'n/a')}",
                f"- 当前湿度: {weather.get('relative_humidity_2m', 'n/a')}",
                f"- 当前降水: {weather.get('precipitation', 'n/a')}",
                f"- 当前风速: {weather.get('wind_speed_10m', 'n/a')}",
                "",
                "## 4. 最终纳入的关键空间节点",
                *(feature_lines or ["- 当前公开空间数据未返回足够要素。"]),
                "",
                "## 5. 推断的人类代理节点",
                *(proxy_lines or ["- 当前基于空间事实未推断出代理主体。"]),
                "",
                "## 6. 推演需求",
                requirement,
                "",
                "## 7. 来源语义",
                "- 公开观测节点来自公开空间要素。",
                "- 遥感识别节点来自遥感派生土地覆盖识别；WMS 结果仅作背景参考，不等于分析级原始栅格。",
                "- 参考地名节点来自内置或静态地名参考，只能用于降级补充。",
                "- 规则推断节点来自规则与 LLM 约束推断，不代表真实具名主体。",
                "- 当前遥感层是年度土地覆盖产品，不是实时卫星图像解译。",
            ]
        )

    def _build_summary(
        self,
        admin_context: Dict[str, Any],
        scene_classification: Dict[str, Any],
        graph: Dict[str, Any],
        *,
        data_quality: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        place = self._context_place_label(admin_context)
        scene = scene_classification.get("primary_scene") or "unknown"
        classification_ready = scene_classification.get("classification_ready") is True
        scene_label = _display_token_zh(scene) if classification_ready else "区域空间"
        stats = graph.get("stats") or {}
        title = f"{place} · {scene_label}地图种子"
        quality = dict(data_quality or {})
        source_phrase = (
            "基于可用公开空间事实"
            if quality.get("formal_ready")
            else "基于部分公开上下文与参考节点（公网空间事实不足）"
        )
        classification_phrase = (
            f"并判定为{scene_label}"
            if classification_ready
            else "；环境类型证据不足，本轮不做类型判断"
        )
        summary = (
            f"{source_phrase}为 {place} 生成空间图谱{classification_phrase}，"
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
        data_quality: Optional[Dict[str, Any]] = None,
        selection_summary: Optional[Dict[str, Any]] = None,
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
        public_observed_points = [
            {
                "lat": item["lat"],
                "lon": item["lon"],
                "label": item["name"],
                "radius": 5,
            }
            for item in features
            if item["source_kind"] == "observed"
            and str((item.get("tags") or {}).get("provider") or "").lower()
            not in {"reverse_geocode", "open-meteo", "open_meteo"}
        ]
        contextual_points = [
            {
                "lat": item["lat"],
                "lon": item["lon"],
                "label": item["name"],
                "radius": 4,
            }
            for item in features
            if str((item.get("tags") or {}).get("provider") or "").lower()
            in {"reverse_geocode", "open-meteo", "open_meteo"}
        ]
        reference_points = [
            {
                "lat": item["lat"],
                "lon": item["lon"],
                "label": item["name"],
                "radius": 4,
            }
            for item in features
            if item["source_kind"] == "reference"
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
        if public_observed_points:
            layers.append(
                {
                    "id": "observed-features",
                    "name": "公开空间要素",
                    "type": "points",
                    "color": "#1f5d45",
                    "visible": True,
                    "note": "来自 OSM 等公开空间数据的观测节点",
                    "data": public_observed_points,
                }
            )
        if contextual_points:
            layers.append(
                {
                    "id": "contextual-features",
                    "name": "范围与环境上下文",
                    "type": "points",
                    "color": "#64748b",
                    "visible": True,
                    "note": "逆地理编码和天气基线只用于范围/环境上下文，不作为地点 Agent 的实地锚点",
                    "data": contextual_points,
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
        if reference_points:
            layers.append(
                {
                    "id": "reference-features",
                    "name": "参考空间节点",
                    "type": "points",
                    "color": "#7c8795",
                    "visible": True,
                    "note": "内置地名或 WMS 背景分类参考，仅作降级辅助，不计作本轮观测",
                    "data": reference_points,
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
            "data_quality": dict(data_quality or {}),
            "selection_summary": dict(selection_summary or {}),
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
                    "source_provider": (item.get("tags") or {}).get("provider"),
                    "spatial_level": item.get("selection_spatial_level")
                    or item.get("spatial_level")
                    or (item.get("tags") or {}).get("spatial_level"),
                    "selection_score": item.get("selection_score"),
                    "selection_reasons": list(item.get("selection_reasons") or []),
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
                    "source_provider": node["attributes"].get("source_provider"),
                    "spatial_precision": node["attributes"].get("spatial_precision"),
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
        lat: Optional[float],
        lon: Optional[float],
        source_kind: str,
        confidence: float,
        attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload_attributes = dict(attributes)
        payload_attributes.update(
            {
                "lat": round(float(lat), 6) if lat is not None else None,
                "lon": round(float(lon), 6) if lon is not None else None,
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
                    "display_name": "区域",
                    "description": "地理分析区域或有边界的场景范围。",
                    "attributes": [
                        {"name": "location", "display_name": "位置", "description": "区域位置说明"},
                        {"name": "scene_type", "display_name": "场景类型", "description": "自动判定的场景类型"},
                    ],
                },
                {
                    "name": "EcologicalReceptor",
                    "display_name": "生态受体",
                    "description": "从地图优先分析中识别出的栖息地或生态受体。",
                    "attributes": [
                        {"name": "location", "display_name": "生态位置", "description": "主要生态位置"},
                        {"name": "source_kind", "display_name": "来源类型", "description": "观测、检测或推断来源"},
                    ],
                },
                {
                    "name": "EnvironmentalCarrier",
                    "display_name": "环境载体",
                    "description": "与扩散相关的水体、空气、岸线或交通载体。",
                    "attributes": [
                        {"name": "location", "display_name": "环境位置", "description": "主要环境位置"},
                        {"name": "source_kind", "display_name": "来源类型", "description": "观测、检测或推断来源"},
                    ],
                },
                {
                    "name": "Infrastructure",
                    "display_name": "基础设施",
                    "description": "本地环境中的设施或建成资产。",
                    "attributes": [
                        {"name": "location", "display_name": "设施位置", "description": "设施所在位置"},
                        {"name": "source_kind", "display_name": "来源类型", "description": "观测、检测或推断来源"},
                    ],
                },
                {
                    "name": "HumanActor",
                    "display_name": "人群主体",
                    "description": "带有空间锚点的人群代理主体。",
                    "attributes": [
                        {"name": "location", "display_name": "锚点位置", "description": "主体的空间锚点"},
                        {"name": "source_kind", "display_name": "来源类型", "description": "观测、检测或推断来源"},
                    ],
                },
                {
                    "name": "GovernmentActor",
                    "display_name": "治理主体",
                    "description": "从地图上下文推断出的治理或监管主体。",
                    "attributes": [
                        {"name": "jurisdiction", "display_name": "管辖范围", "description": "行政或治理覆盖范围"},
                        {"name": "source_kind", "display_name": "来源类型", "description": "观测、检测或推断来源"},
                    ],
                },
                {
                    "name": "OrganizationActor",
                    "display_name": "组织主体",
                    "description": "从设施和服务上下文推断出的维护、运营或协作组织。",
                    "attributes": [
                        {"name": "service_scope", "display_name": "服务范围", "description": "组织服务或维护覆盖范围"},
                        {"name": "source_kind", "display_name": "来源类型", "description": "观测、检测或推断来源"},
                    ],
                },
            ],
            "edge_types": [
                {
                    "name": "located_in",
                    "display_name": "位于",
                    "description": "源节点位于目标区域内。",
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
                    "display_name": "依赖",
                    "description": "源节点依赖目标节点提供支撑。",
                    "source_targets": [
                        {"source": "HumanActor", "target": "Infrastructure"},
                        {"source": "HumanActor", "target": "EnvironmentalCarrier"},
                        {"source": "OrganizationActor", "target": "Infrastructure"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "affects",
                    "display_name": "影响",
                    "description": "源节点可能对目标节点产生影响。",
                    "source_targets": [
                        {"source": "Infrastructure", "target": "EcologicalReceptor"},
                        {"source": "Infrastructure", "target": "EnvironmentalCarrier"},
                        {"source": "EnvironmentalCarrier", "target": "EcologicalReceptor"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "regulates",
                    "display_name": "调控",
                    "description": "源节点对目标节点具有治理、监管或调控作用。",
                    "source_targets": [
                        {"source": "GovernmentActor", "target": "Infrastructure"},
                        {"source": "GovernmentActor", "target": "EcologicalReceptor"},
                        {"source": "GovernmentActor", "target": "HumanActor"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "uses",
                    "display_name": "使用",
                    "description": "源节点使用目标节点提供的设施或服务。",
                    "source_targets": [
                        {"source": "HumanActor", "target": "Infrastructure"},
                        {"source": "OrganizationActor", "target": "Infrastructure"},
                    ],
                    "attributes": [],
                },
            ],
        }
