"""
Optional public-data grounding adapters for EnvFish.

These adapters must never block a simulation. They best-effort fetch rough
baseline hints when enough region metadata is available; otherwise they return
an explicit unavailable status.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..utils.logger import get_logger
from .envfish_models import normalize_transport_family

logger = get_logger("envfish.envfish_grounding")


def _safe_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload)
    except Exception as exc:
        logger.debug(f"Grounding request failed: {url} - {exc}")
        return None


@dataclass
class GroundingRecord:
    source: str
    status: str
    summary: str
    priors: Dict[str, float]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "summary": self.summary,
            "priors": self.priors,
            "metadata": self.metadata,
        }


class PublicDataGroundingService:
    """
    Best-effort public data grounding for region priors.
    """

    def __init__(self):
        self._source_labels = {
            "epa_aqs": "EPA AQS",
            "usgs_wqp": "USGS/WQP",
            "copernicus_marine": "Copernicus Marine",
            "noaa_incident": "NOAA IncidentNews",
        }

    def ground(
        self,
        regions: Iterable[Dict[str, Any]],
        diffusion_template: str,
        document_text: str = "",
    ) -> Dict[str, Any]:
        region_list = list(regions)
        diffusion_template = normalize_transport_family(diffusion_template)
        records: List[GroundingRecord] = []
        aggregate_priors: Dict[str, float] = {}

        for region in region_list:
            if diffusion_template in {"air", "atmospheric_plume", "ash_plume"}:
                record = self._ground_air_region(region)
            elif diffusion_template in {"inland_water", "inland_water_network", "surface_flood_flow"}:
                record = self._ground_inland_water_region(region)
            elif diffusion_template in {"marine", "marine_current", "coastal_inundation"}:
                record = self._ground_marine_region(region, document_text=document_text)
            else:
                record = self._ground_noaa_incident(region, document_text=document_text)

            records.append(record)
            for key, value in (record.priors or {}).items():
                aggregate_priors[key] = round(aggregate_priors.get(key, 0.0) + float(value), 2)

        successful = [record for record in records if record.status == "ok"]
        summary = {
            "status": "ok" if successful else "unavailable",
            "records": [record.to_dict() for record in records],
            "sources_attempted": sorted({record.source for record in records}),
            "successful_sources": sorted({record.source for record in successful}),
            "aggregate_priors": aggregate_priors,
            "note": (
                "Grounding is optional. When public datasets are missing or region metadata is too sparse, "
                "EnvFish falls back to report-only initialization."
            ),
        }
        return summary

    def _ground_air_region(self, region: Dict[str, Any]) -> GroundingRecord:
        lat = region.get("lat")
        lon = region.get("lon")
        if lat is None or lon is None:
            return GroundingRecord(
                source="epa_aqs",
                status="unavailable",
                summary="Region lacks coordinates; skipped EPA AQS lookup.",
                priors={},
                metadata={"region": region.get("name")},
            )

        url = (
            "https://aqs.epa.gov/data/api/annualData/byBox?"
            + urllib.parse.urlencode(
                {
                    "email": "envfish@example.com",
                    "key": "guest",
                    "param": "88101",
                    "bdate": "20240101",
                    "edate": "20241231",
                    "minlat": float(lat) - 0.5,
                    "maxlat": float(lat) + 0.5,
                    "minlon": float(lon) - 0.5,
                    "maxlon": float(lon) + 0.5,
                }
            )
        )
        payload = _safe_get_json(url)
        if not payload or not payload.get("Data"):
            return GroundingRecord(
                source="epa_aqs",
                status="unavailable",
                summary="EPA AQS returned no usable readings for this region.",
                priors={},
                metadata={"region": region.get("name")},
            )

        values = [item.get("arithmetic_mean") for item in payload["Data"] if item.get("arithmetic_mean") is not None]
        if not values:
            return GroundingRecord(
                source="epa_aqs",
                status="unavailable",
                summary="EPA AQS response lacked arithmetic mean values.",
                priors={},
                metadata={"region": region.get("name")},
            )

        mean_value = sum(float(item) for item in values) / len(values)
        prior = min(100.0, max(0.0, mean_value * 2.5))
        return GroundingRecord(
            source="epa_aqs",
            status="ok",
            summary=f"EPA AQS PM2.5 mean roughly maps to exposure prior {prior:.1f}.",
            priors={"exposure_score": round(prior, 2), "spread_pressure": round(prior * 0.75, 2)},
            metadata={"samples": len(values), "region": region.get("name")},
        )

    def _ground_inland_water_region(self, region: Dict[str, Any]) -> GroundingRecord:
        site = region.get("usgs_site") or region.get("site_no")
        if not site:
            return GroundingRecord(
                source="usgs_wqp",
                status="unavailable",
                summary="Region lacks USGS site metadata; skipped inland-water lookup.",
                priors={},
                metadata={"region": region.get("name")},
            )

        url = (
            "https://waterservices.usgs.gov/nwis/iv/?"
            + urllib.parse.urlencode(
                {
                    "format": "json",
                    "sites": site,
                    "parameterCd": "00010,00095",
                    "siteStatus": "all",
                }
            )
        )
        payload = _safe_get_json(url)
        if not payload:
            return GroundingRecord(
                source="usgs_wqp",
                status="unavailable",
                summary="USGS service unavailable or returned invalid data.",
                priors={},
                metadata={"region": region.get("name"), "site": site},
            )

        series = payload.get("value", {}).get("timeSeries", [])
        series_count = len(series)
        prior = min(65.0, 15.0 + series_count * 8.0)
        return GroundingRecord(
            source="usgs_wqp",
            status="ok" if series_count else "unavailable",
            summary=(
                f"USGS returned {series_count} time-series channel(s); used a coarse river prior."
                if series_count
                else "USGS returned no time-series values."
            ),
            priors={"exposure_score": round(prior, 2), "ecosystem_integrity": round(max(0.0, 82.0 - prior), 2)} if series_count else {},
            metadata={"region": region.get("name"), "site": site},
        )

    def _ground_marine_region(self, region: Dict[str, Any], document_text: str = "") -> GroundingRecord:
        lat = region.get("lat")
        lon = region.get("lon")
        if lat is None or lon is None:
            return GroundingRecord(
                source="copernicus_marine",
                status="unavailable",
                summary="Region lacks coordinates; skipped Copernicus Marine lookup.",
                priors={},
                metadata={"region": region.get("name")},
            )

        # Copernicus normally requires a token. For MVP we only record a soft prior when the
        # seed text indicates marine/coastal conditions and coordinates exist.
        text = f"{region.get('description', '')} {document_text}".lower()
        marine_hits = sum(1 for keyword in ("coast", "marine", "bay", "fish", "ocean", "port") if keyword in text)
        prior = min(60.0, 18.0 + marine_hits * 8.0)
        return GroundingRecord(
            source="copernicus_marine",
            status="ok",
            summary="Used coastal keyword density plus coordinates as a soft marine prior.",
            priors={"spread_pressure": round(prior, 2), "ecosystem_integrity": round(max(0.0, 84.0 - prior / 2), 2)},
            metadata={"region": region.get("name"), "keyword_hits": marine_hits},
        )

    def _ground_noaa_incident(self, region: Dict[str, Any], document_text: str = "") -> GroundingRecord:
        query = region.get("name")
        if not query:
            return GroundingRecord(
                source="noaa_incident",
                status="unavailable",
                summary="Region name missing; skipped NOAA incident retrieval.",
                priors={},
                metadata={},
            )

        encoded = urllib.parse.quote(query)
        url = f"https://incidentnews.noaa.gov/raw/index?output=json&name={encoded}"
        payload = _safe_get_json(url)
        if not payload:
            return GroundingRecord(
                source="noaa_incident",
                status="unavailable",
                summary="NOAA incident feed unavailable or not JSON for this region query.",
                priors={},
                metadata={"region": query},
            )

        events = payload if isinstance(payload, list) else payload.get("items", [])
        count = len(events)
        prior = min(55.0, count * 6.0)
        return GroundingRecord(
            source="noaa_incident",
            status="ok" if count else "unavailable",
            summary=f"Found {count} historical incident records for a coarse baseline." if count else "No matching NOAA incidents found.",
            priors={"vulnerability_score": round(30.0 + prior, 2)} if count else {},
            metadata={"region": query, "events": count},
        )
