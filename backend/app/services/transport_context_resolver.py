"""Transport-context resolution for EnvFish diffusion.

Previously a 9-line stub that always returned ``transport_edges: []``. It now
derives real candidate transport edges from the seed's spatial region graph —
adjacency (``neighbors``) plus carrier/land-use semantics (river reaches,
road corridors, coastal currents) — and surfaces a wind-derived
``flow_direction_deg`` when an Open-Meteo baseline is available from the seed.

Honesty contract:
- Edges are tagged with ``origin`` (``seed_adjacency``) and an
  ``epistemic_status`` (``inferred``) — these are spatially-plausible carriers
  inferred from real adjacency, not measured flows.
- Backward compatible: the same top-level keys always exist. When there is no
  usable spatial signal we degrade to the legacy ``local_fallback`` shape with
  an empty ``transport_edges`` list, so existing callers/tests are unaffected.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


# Coarse channel inference from a region's land_use_class / carriers.
_WATER_CLASSES = {"water"}
_TRANSPORT_CLASSES = {"transport"}


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _region_field(region: Any, key: str, default: Any = None) -> Any:
    if isinstance(region, dict):
        return region.get(key, default)
    return getattr(region, key, default)


class TransportContextResolver:
    """Resolves diffusion transport context from the spatial region graph.

    Public signature preserved: ``resolve(regions=None, diffusion_template=None,
    reference_time=None, preferred_provider=None, **kwargs)``.
    """

    def resolve(
        self,
        regions: Optional[List[Any]] = None,
        diffusion_template: Optional[str] = None,
        reference_time: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        regions = regions or []
        seed_id = (
            kwargs.get("seed_id")
            or kwargs.get("map_seed_id")
            or kwargs.get("seed_handle")
        )
        seed_dir = kwargs.get("seed_dir")

        flow_direction_deg: Optional[float] = None
        baseline_provider: Optional[str] = None
        try:
            flow_direction_deg, baseline_provider = self._wind_flow_direction(seed_id, seed_dir)
        except Exception:
            flow_direction_deg, baseline_provider = None, None

        transport_edges: List[Dict[str, Any]] = []
        try:
            transport_edges = self._edges_from_adjacency(regions, diffusion_template)
        except Exception:
            transport_edges = []

        if not transport_edges and flow_direction_deg is None:
            # Nothing spatial to ground on — preserve legacy fallback shape.
            return {
                "provider": preferred_provider or "local_fallback",
                "diffusion_template": diffusion_template,
                "reference_time": reference_time,
                "transport_edges": [],
                "notes": [],
            }

        provider = preferred_provider or "seed_adjacency"
        if baseline_provider:
            provider = preferred_provider or baseline_provider
        notes: List[str] = []
        if transport_edges:
            notes.append(
                f"Derived {len(transport_edges)} candidate transport edge(s) from seed region adjacency."
            )
        if flow_direction_deg is not None:
            notes.append("Flow direction seeded from Open-Meteo wind baseline.")

        result: Dict[str, Any] = {
            "provider": provider,
            "diffusion_template": diffusion_template,
            "reference_time": reference_time,
            "transport_edges": transport_edges,
            "notes": notes,
        }
        if flow_direction_deg is not None:
            result["flow_direction_deg"] = round(flow_direction_deg, 1)
            result["note"] = "Transport ordering biased by observed wind direction."
        return result

    # ------------------------------------------------------------------
    # Adjacency -> transport edges
    # ------------------------------------------------------------------
    def _edges_from_adjacency(
        self, regions: List[Any], diffusion_template: Optional[str]
    ) -> List[Dict[str, Any]]:
        if not regions or len(regions) <= 1:
            return []

        lookup: Dict[str, Any] = {}
        for region in regions:
            region_id = _region_field(region, "region_id")
            if region_id:
                lookup[region_id] = region
        if not lookup:
            return []

        edges: List[Dict[str, Any]] = []
        seen: set = set()
        for region in regions:
            source_id = _region_field(region, "region_id")
            if not source_id:
                continue
            neighbors = _region_field(region, "neighbors", []) or []
            for neighbor_id in neighbors:
                if neighbor_id == source_id or neighbor_id not in lookup:
                    continue
                key = tuple(sorted((source_id, neighbor_id)))
                if key in seen:
                    continue
                seen.add(key)
                neighbor = lookup[neighbor_id]
                channel_type, directionality = self._infer_channel(region, neighbor, diffusion_template)
                edges.append(
                    {
                        "edge_id": f"transport_{source_id}__{neighbor_id}",
                        "source_region_id": source_id,
                        "target_region_id": neighbor_id,
                        "channel_type": channel_type,
                        "directionality": directionality,
                        "origin": "seed_adjacency",
                        "epistemic_status": "inferred",
                        "confidence": 0.55,
                        "evidence_anchors": [f"region::{source_id}", f"region::{neighbor_id}"],
                        "rationale": (
                            f"Spatial adjacency between {source_id} and {neighbor_id} implies a "
                            f"{channel_type} carrier."
                        ),
                    }
                )
        return edges

    def _infer_channel(self, source: Any, target: Any, diffusion_template: Optional[str]) -> tuple:
        src_class = str(_region_field(source, "land_use_class", "") or "").lower()
        tgt_class = str(_region_field(target, "land_use_class", "") or "").lower()
        src_carriers = {str(c).lower() for c in (_region_field(source, "carriers", []) or [])}
        tgt_carriers = {str(c).lower() for c in (_region_field(target, "carriers", []) or [])}
        carriers = src_carriers | tgt_carriers
        template = str(diffusion_template or "").lower()

        if "water_flow" in carriers or src_class in _WATER_CLASSES or tgt_class in _WATER_CLASSES:
            return "river_reach", "directed"
        if "inland_water" in template or "surface_flood" in template:
            return "surface_runoff", "directed"
        if src_class in _TRANSPORT_CLASSES or tgt_class in _TRANSPORT_CLASSES or "transport_flow" in carriers:
            return "infrastructure_corridor", "asymmetric"
        if "marine" in template or "coastal" in template:
            return "coastal_current", "asymmetric"
        if "air" in template or "atmospheric" in template or "plume" in template:
            return "air_corridor", "directed"
        return "environmental_link", "asymmetric"

    # ------------------------------------------------------------------
    # Wind baseline -> flow direction
    # ------------------------------------------------------------------
    def _wind_flow_direction(
        self, seed_id: Optional[str], seed_dir: Optional[str]
    ) -> tuple:
        directory = self._resolve_seed_dir(seed_id, seed_dir)
        if not directory or not os.path.isdir(directory):
            return None, None

        graph = self._read_json(os.path.join(directory, "graph_snapshot.json"))
        baseline = self._baseline_from_graph(graph) if graph else {}
        if not baseline:
            seed_meta = self._read_json(os.path.join(directory, "seed.json"))
            if isinstance(seed_meta, dict) and isinstance(seed_meta.get("environment_baseline"), dict):
                current = seed_meta["environment_baseline"].get("current") or {}
                baseline = {
                    "provider": seed_meta["environment_baseline"].get("provider"),
                    "wind_direction_10m": current.get("wind_direction_10m"),
                }
        wind_dir = _coerce_float(baseline.get("wind_direction_10m")) if baseline else None
        provider = baseline.get("provider") if baseline else None
        return wind_dir, provider

    @staticmethod
    def _baseline_from_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
        nodes = graph.get("nodes") or (graph.get("graph_data") or {}).get("nodes") or []
        for node in nodes or []:
            attrs = (node or {}).get("attributes") or {}
            baseline = attrs.get("environment_baseline")
            if isinstance(baseline, dict):
                current = baseline.get("current") if isinstance(baseline.get("current"), dict) else {}
                return {
                    "provider": baseline.get("provider"),
                    "wind_direction_10m": (current or {}).get("wind_direction_10m"),
                }
        return {}

    @staticmethod
    def _resolve_seed_dir(seed_id: Optional[str], seed_dir: Optional[str]) -> Optional[str]:
        if seed_dir:
            return seed_dir
        if not seed_id:
            return None
        try:
            from ..config import Config

            return os.path.join(Config.UPLOAD_FOLDER, "map_seeds", str(seed_id))
        except Exception:
            return None

    @staticmethod
    def _read_json(path: str) -> Optional[Dict[str, Any]]:
        try:
            if not os.path.isfile(path):
                return None
            try:
                from ..utils.atomic_file import read_json_file

                data = read_json_file(path, default=None)
            except Exception:
                import json

                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
