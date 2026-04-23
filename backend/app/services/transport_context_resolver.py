"""
Directional transport context resolution for EnvFish.

This service keeps external lookups optional. When directional data is missing
or an API is unavailable, callers receive an explicit fallback payload and may
continue with topology-only heuristics.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..utils.logger import get_logger
from .envfish_models import DIFFUSION_PROVIDER_DEFAULTS, RegionNode, normalize_transport_family

logger = get_logger("envfish.transport_context")


def _safe_get_json(url: str, timeout: float = 8.0) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        logger.debug(f"Transport context request failed: {url} - {exc}")
        return None


def _parse_reference_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _normalize_angle(value: float) -> float:
    return round(value % 360.0, 2)


def _vector_average(samples: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    weighted_x = 0.0
    weighted_y = 0.0
    total_weight = 0.0
    for direction_deg, weight in samples:
        if weight <= 0:
            continue
        radians = math.radians(direction_deg)
        weighted_x += math.cos(radians) * weight
        weighted_y += math.sin(radians) * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    angle = math.degrees(math.atan2(weighted_y, weighted_x))
    speed = total_weight / max(len(samples), 1)
    return _normalize_angle(angle), round(speed, 2)


class TransportContextResolver:
    def resolve(
        self,
        regions: Iterable[RegionNode],
        diffusion_template: str,
        reference_time: Optional[str] = None,
        preferred_provider: str = "auto",
    ) -> Dict[str, Any]:
        region_list = list(regions)
        diffusion_template = normalize_transport_family(diffusion_template)
        provider = self._resolve_provider(diffusion_template, preferred_provider)
        centroid = self._centroid(region_list)
        reference_dt = _parse_reference_time(reference_time)
        payload: Dict[str, Any] = {
            "template": diffusion_template,
            "provider": provider,
            "reference_time": reference_time or "",
            "status": "fallback",
            "note": "",
            "centroid": {"lat": centroid[0], "lon": centroid[1]} if centroid else None,
        }

        if provider in {"topology", "heuristic"} and diffusion_template in {"air", "marine", "atmospheric_plume", "marine_current", "coastal_inundation", "ash_plume"}:
            payload["note"] = f"{provider} provider selected; using topology-first directional inference."
            return payload

        if diffusion_template in {"inland_water", "inland_water_network", "surface_flood_flow"}:
            payload["status"] = "ok"
            payload["note"] = "Inland-water routing is topology-first; no external flow lookup was required."
            return payload

        if centroid is None:
            payload["note"] = "Regions do not have coordinates; using topology-only transport inference."
            return payload

        if diffusion_template in {"air", "atmospheric_plume", "ash_plume"}:
            return self._resolve_air_context(payload, centroid, reference_dt)
        if diffusion_template in {"marine", "marine_current", "coastal_inundation"}:
            return self._resolve_marine_context(payload, centroid, reference_dt)

        payload["note"] = "Generic template falls back to topology-only routing."
        return payload

    def _resolve_provider(self, diffusion_template: str, preferred_provider: str) -> str:
        normalized = str(preferred_provider or "auto").strip().lower()
        if normalized not in {"auto", "open_meteo", "topology", "heuristic"}:
            normalized = "auto"
        if normalized == "auto":
            return DIFFUSION_PROVIDER_DEFAULTS.get(diffusion_template, "heuristic")
        return normalized

    def _centroid(self, regions: List[RegionNode]) -> Optional[Tuple[float, float]]:
        coords = [(float(region.lat), float(region.lon)) for region in regions if region.lat is not None and region.lon is not None]
        if not coords:
            return None
        lat = round(sum(item[0] for item in coords) / len(coords), 6)
        lon = round(sum(item[1] for item in coords) / len(coords), 6)
        return lat, lon

    def _resolve_air_context(
        self,
        payload: Dict[str, Any],
        centroid: Tuple[float, float],
        reference_dt: Optional[datetime],
    ) -> Dict[str, Any]:
        lat, lon = centroid
        now_utc = datetime.now(timezone.utc)
        if reference_dt and reference_dt.date() < now_utc.date():
            query = urllib.parse.urlencode(
                {
                    "latitude": f"{lat:.6f}",
                    "longitude": f"{lon:.6f}",
                    "start_date": reference_dt.date().isoformat(),
                    "end_date": reference_dt.date().isoformat(),
                    "hourly": "wind_speed_10m,wind_direction_10m",
                    "timezone": "UTC",
                }
            )
            url = f"https://archive-api.open-meteo.com/v1/archive?{query}"
            response = _safe_get_json(url)
            hourly = response.get("hourly") if response else {}
            speeds = list(hourly.get("wind_speed_10m") or [])
            directions = list(hourly.get("wind_direction_10m") or [])
            if speeds and directions:
                averaged = _vector_average(
                    [(_normalize_angle(float(direction) + 180.0), float(speed)) for direction, speed in zip(directions, speeds)]
                )
                if averaged:
                    payload.update(
                        {
                            "status": "ok",
                            "provider": "open_meteo_archive",
                            "flow_direction_deg": averaged[0],
                            "wind_speed": averaged[1],
                            "note": "Historical atmospheric flow estimated from archived Open-Meteo wind fields.",
                        }
                    )
                    return payload
            payload["note"] = "Historical atmospheric lookup failed; using topology-only atmospheric routing."
            return payload
        query = urllib.parse.urlencode(
            {
                "latitude": f"{lat:.6f}",
                "longitude": f"{lon:.6f}",
                "current": "wind_speed_10m,wind_direction_10m",
                "timezone": "UTC",
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{query}"
        response = _safe_get_json(url)
        current = response.get("current") if response else {}
        direction = current.get("wind_direction_10m")
        speed = current.get("wind_speed_10m")
        if direction is None or speed is None:
            payload["note"] = "Open-Meteo wind lookup failed; using topology-only atmospheric routing."
            return payload
        payload.update(
            {
                "status": "ok",
                "provider": "open_meteo",
                "flow_direction_deg": _normalize_angle(float(direction) + 180.0),
                "wind_speed": round(float(speed), 2),
                "note": "Atmospheric flow estimated from Open-Meteo wind direction and speed.",
            }
        )
        return payload

    def _resolve_marine_context(
        self,
        payload: Dict[str, Any],
        centroid: Tuple[float, float],
        reference_dt: Optional[datetime],
    ) -> Dict[str, Any]:
        lat, lon = centroid
        now_utc = datetime.now(timezone.utc)
        if reference_dt and reference_dt.date() < now_utc.date():
            payload["note"] = (
                "Historical marine current lookup is not configured in this environment; using geometry-aware coastal heuristics."
            )
            return payload

        query = urllib.parse.urlencode(
            {
                "latitude": f"{lat:.6f}",
                "longitude": f"{lon:.6f}",
                "current": "ocean_current_velocity,ocean_current_direction",
                "timezone": "UTC",
            }
        )
        url = f"https://marine-api.open-meteo.com/v1/marine?{query}"
        response = _safe_get_json(url)
        current = response.get("current") if response else {}
        direction = current.get("ocean_current_direction")
        speed = current.get("ocean_current_velocity")
        if direction is None or speed is None:
            payload["note"] = "Open-Meteo marine lookup failed; using geometry-aware coastal heuristics."
            return payload

        payload.update(
            {
                "status": "ok",
                "provider": "open_meteo",
                "flow_direction_deg": _normalize_angle(float(direction)),
                "current_velocity": round(float(speed), 2),
                "note": "Marine flow estimated from Open-Meteo ocean current direction and velocity.",
            }
        )
        return payload
