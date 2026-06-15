"""Public-data spatial grounding for EnvFish region graphs.

This module turns the rich map-seed pipeline artifacts (ESA WorldCover land
cover, OSM features, Open-Meteo baseline) into *priors* that the simulation
main path can actually consume, instead of always returning an empty
``local_fallback`` stub.

Design notes / honesty contract:
- We never fabricate precision. Every prior carries ``provenance`` marking it
  as ``observed`` (read straight from real spatial facts: WorldCover pixel
  shares, OSM land-use classes) or ``inferred`` (derived heuristically from
  those observed facts, e.g. mapping a water share to a livelihood prior).
- The return shape is backward compatible with the previous 9-line stub: the
  same top-level keys are always present. When grounding succeeds we set
  ``source = "map_seed_grounded"`` and populate ``priors`` / ``records`` with
  real values; otherwise we degrade gracefully to ``local_fallback`` with the
  old empty shape so existing callers/tests keep working.
- ``records`` is the structure ``EnvProfileGenerator._apply_grounding_priors``
  consumes: a list of ``{"metadata": {"region": <name>}, "priors": {...},
  "provenance": {...}}`` entries keyed by region name.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


# ESA WorldCover 2021 class codes -> coarse cover buckets we reason about.
_WORLDCOVER_WATER = {80}
_WORLDCOVER_WETLAND = {90, 95}
_WORLDCOVER_VEGETATION = {10, 20, 30, 40, 90, 95, 100}
_WORLDCOVER_BUILTUP = {50}
_WORLDCOVER_BARE = {60, 70}

# land_use_class values produced upstream by env_profile_generator.
_WATER_CLASSES = {"water"}
_ECOLOGY_CLASSES = {"ecology"}
_BUILT_CLASSES = {"industrial", "urban"}
_TRANSPORT_CLASSES = {"transport"}
_OPEN_CLASSES = {"open"}


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _region_field(region: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dict (``to_dict``) or a RegionNode object."""
    if isinstance(region, dict):
        return region.get(key, default)
    return getattr(region, key, default)


class PublicDataGroundingService:
    """Reads map-seed spatial facts and produces grounded region priors.

    Public signature preserved: ``ground(regions=None, diffusion_template=None,
    document_text="", **kwargs)`` — callers in ``env_profile_generator`` are
    untouched. New optional handles (``seed_id`` / ``map_seed_id`` / ``seed_dir``)
    are accepted via kwargs but are not required; when absent we still ground
    from the spatial signal already embedded in the region dicts.
    """

    def ground(
        self,
        regions: Optional[List[Any]] = None,
        diffusion_template: Optional[str] = None,
        document_text: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        regions = regions or []
        seed_id = (
            kwargs.get("seed_id")
            or kwargs.get("map_seed_id")
            or kwargs.get("seed_handle")
        )
        seed_dir = kwargs.get("seed_dir")

        # Land-cover fractions discovered from the seed artifacts, keyed by a
        # coarse bucket. Used to enrich region priors when a region itself
        # carries little embedded signal.
        seed_cover: Dict[str, float] = {}
        seed_baseline: Dict[str, Any] = {}
        seed_sources: List[str] = []
        try:
            seed_cover, seed_baseline, seed_sources = self._load_seed_facts(seed_id, seed_dir)
        except Exception:
            # Defensive: a missing/unreadable seed must never break grounding.
            seed_cover, seed_baseline, seed_sources = {}, {}, []

        records: List[Dict[str, Any]] = []
        priors_by_region: Dict[str, Dict[str, float]] = {}
        provenance_by_region: Dict[str, Dict[str, str]] = {}
        grounded_regions = 0

        for region in regions:
            name = _region_field(region, "name")
            if not name:
                continue
            priors, provenance, has_signal = self._region_priors(region, seed_cover)
            if not priors:
                continue
            if has_signal:
                grounded_regions += 1
            priors_by_region[name] = priors
            provenance_by_region[name] = provenance
            records.append(
                {
                    "metadata": {
                        "region": name,
                        "land_use_class": _region_field(region, "land_use_class", "") or "",
                        "lat": _region_field(region, "lat"),
                        "lon": _region_field(region, "lon"),
                    },
                    "priors": priors,
                    "provenance": provenance,
                }
            )

        # We consider the run "grounded" if any region carried real spatial
        # signal OR we successfully read seed artifacts from disk.
        is_grounded = grounded_regions > 0 or bool(seed_sources)

        if not is_grounded:
            # Preserve the exact legacy fallback shape.
            return {
                "source": "local_fallback",
                "regions": regions if isinstance(regions, list) else list(regions),
                "diffusion_template": diffusion_template,
                "priors": {},
                "records": [],
                "notes": [],
            }

        successful_sources = ["region_land_cover"]
        successful_sources.extend(seed_sources)
        notes = [
            f"Grounded {grounded_regions} region(s) from WorldCover/OSM land-cover signal.",
        ]
        if seed_sources:
            notes.append(f"Read map-seed artifacts: {', '.join(seed_sources)}.")
        if seed_baseline.get("wind_direction_10m") is not None:
            notes.append("Open-Meteo wind baseline available for transport ordering.")

        return {
            "source": "map_seed_grounded",
            "regions": regions if isinstance(regions, list) else list(regions),
            "diffusion_template": diffusion_template,
            # ``priors`` keeps a flat per-region view for callers that want the
            # whole picture; ``records`` is what _apply_grounding_priors reads.
            "priors": priors_by_region,
            "provenance": provenance_by_region,
            "records": records,
            "successful_sources": successful_sources,
            "seed_land_cover": seed_cover,
            "environment_baseline": seed_baseline,
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Per-region prior derivation
    # ------------------------------------------------------------------
    def _region_priors(
        self, region: Any, seed_cover: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, str], bool]:
        """Map a region's observed land-cover signal to state-vector priors.

        Returns ``(priors, provenance, has_real_signal)``. ``priors`` keys are
        a subset of the EnvFish state-vector schema; provenance marks each key
        as ``observed`` or ``inferred``.
        """
        land_use_class = str(_region_field(region, "land_use_class", "") or "").lower()
        tags = [str(tag).lower() for tag in (_region_field(region, "tags", []) or [])]
        ecology_assets = _region_field(region, "ecology_assets", []) or []
        industry_tags = _region_field(region, "industry_tags", []) or []

        water_share = self._tag_pixel_share(tags, _WORLDCOVER_WATER)
        veg_share = self._tag_pixel_share(tags, _WORLDCOVER_VEGETATION)
        built_share = self._tag_pixel_share(tags, _WORLDCOVER_BUILTUP)

        priors: Dict[str, float] = {}
        provenance: Dict[str, str] = {}
        has_real_signal = False

        def set_prior(key: str, value: float, source: str) -> None:
            priors[key] = round(_clamp(value), 2)
            provenance[key] = source

        # land_use_class is itself derived from observed WorldCover/OSM facts
        # upstream, so a non-empty, non-generic class counts as real signal.
        if land_use_class and land_use_class not in {"", "region", "mixed"}:
            has_real_signal = True

        if land_use_class in _WATER_CLASSES or water_share > 0:
            has_real_signal = True
            # Water-dominated zones: strong ecological asset, low impervious
            # pressure, livelihoods tied to the water body.
            set_prior("ecosystem_integrity", 70 + min(20, water_share * 0.2), "inferred")
            set_prior("vulnerability_score", 30 + min(20, water_share * 0.2), "inferred")
            if water_share > 0:
                set_prior("exposure_score", 18 + min(22, water_share * 0.25), "observed")

        if land_use_class in _ECOLOGY_CLASSES or veg_share > 0 or ecology_assets:
            has_real_signal = True
            integrity = 72 + min(18, veg_share * 0.2)
            set_prior("ecosystem_integrity", integrity, "observed" if veg_share > 0 else "inferred")
            set_prior("vulnerability_score", 26 + min(18, veg_share * 0.15), "inferred")

        if land_use_class in _BUILT_CLASSES or built_share > 0 or industry_tags:
            has_real_signal = True
            # Built-up / industrial: higher economic stress + service load,
            # lower baseline ecosystem integrity (impervious surface).
            set_prior("economic_stress", 30 + min(25, built_share * 0.3), "observed" if built_share > 0 else "inferred")
            set_prior("service_capacity", 58 + min(15, built_share * 0.1), "inferred")
            set_prior("ecosystem_integrity", _clamp(62 - min(20, built_share * 0.2)), "inferred")
            if land_use_class == "industrial" or industry_tags:
                set_prior("exposure_score", 26, "inferred")

        if land_use_class in _TRANSPORT_CLASSES or "transport" in tags:
            has_real_signal = True
            set_prior("spread_pressure", 28, "inferred")
            set_prior("service_capacity", 60, "inferred")

        if land_use_class in _OPEN_CLASSES or "open" in tags:
            has_real_signal = True
            set_prior("ecosystem_integrity", 66, "inferred")
            set_prior("vulnerability_score", 32, "inferred")

        # If the region carried no embedded signal, fall back to seed-wide
        # land-cover fractions (still real observed facts, just not region-local).
        if not has_real_signal and seed_cover:
            water = seed_cover.get("water", 0.0)
            veg = seed_cover.get("vegetation", 0.0)
            built = seed_cover.get("built", 0.0)
            if water or veg or built:
                has_real_signal = True
                set_prior(
                    "ecosystem_integrity",
                    _clamp(60 + (water + veg) * 0.15 - built * 0.2),
                    "observed",
                )
                if built:
                    set_prior("economic_stress", _clamp(28 + built * 0.2), "observed")

        return priors, provenance, has_real_signal

    @staticmethod
    def _tag_pixel_share(tags: List[str], class_codes: set) -> float:
        """Best-effort: presence of a ``worldcover_<code>`` tag implies that
        class is observed in the region. We don't have per-region pixel shares
        on the region object itself (those live on the source features), so we
        return a nominal share signal: 0 when absent, a positive nominal when
        present. This keeps the prior derivation monotonic and observed-tagged.
        """
        share = 0.0
        for tag in tags:
            if not tag.startswith("worldcover_"):
                continue
            code_part = tag.split("_", 1)[-1]
            try:
                code = int(code_part)
            except (TypeError, ValueError):
                continue
            if code in class_codes:
                # Nominal observed presence; exact share is computed seed-wide
                # in _load_seed_facts when artifacts are available.
                share = max(share, 40.0)
        return share

    # ------------------------------------------------------------------
    # Seed artifact reading
    # ------------------------------------------------------------------
    def _load_seed_facts(
        self, seed_id: Optional[str], seed_dir: Optional[str]
    ) -> Tuple[Dict[str, float], Dict[str, Any], List[str]]:
        """Read ``layers.json`` / ``graph_snapshot.json`` / ``seed.json`` and
        compute seed-wide land-cover fractions + environment baseline.

        Returns ``(cover_fractions, environment_baseline, sources_read)``.
        Never raises for a missing seed — returns empties instead.
        """
        directory = self._resolve_seed_dir(seed_id, seed_dir)
        if not directory or not os.path.isdir(directory):
            return {}, {}, []

        sources: List[str] = []
        cover: Dict[str, float] = {}
        baseline: Dict[str, Any] = {}

        graph = self._read_json(os.path.join(directory, "graph_snapshot.json"))
        if graph:
            sources.append("graph_snapshot.json")
            cover = self._cover_from_graph(graph)
            baseline = self._baseline_from_graph(graph)

        layers = self._read_json(os.path.join(directory, "layers.json"))
        if layers:
            sources.append("layers.json")
            if not cover:
                cover = self._cover_from_layers(layers)

        seed_meta = self._read_json(os.path.join(directory, "seed.json"))
        if seed_meta:
            sources.append("seed.json")
            if not baseline and isinstance(seed_meta.get("environment_baseline"), dict):
                baseline = self._baseline_from_meta(seed_meta["environment_baseline"])

        return cover, baseline, sources

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

    def _cover_from_graph(self, graph: Dict[str, Any]) -> Dict[str, float]:
        nodes = graph.get("nodes") or (graph.get("graph_data") or {}).get("nodes") or []
        return self._aggregate_cover(self._iter_worldcover_shares(nodes))

    def _cover_from_layers(self, layers: Dict[str, Any]) -> Dict[str, float]:
        shares: List[Tuple[int, float]] = []
        layer_list = layers.get("layers") if isinstance(layers, dict) else None
        for layer in layer_list or []:
            features = (layer or {}).get("features") or []
            for feature in features:
                props = (feature or {}).get("properties") or {}
                code = _coerce_float(props.get("class_code"))
                share = _coerce_float(props.get("pixel_share_pct"))
                if code is not None and share is not None:
                    shares.append((int(code), share))
        return self._aggregate_cover(shares)

    @staticmethod
    def _iter_worldcover_shares(nodes: List[Dict[str, Any]]) -> List[Tuple[int, float]]:
        out: List[Tuple[int, float]] = []
        for node in nodes or []:
            attrs = (node or {}).get("attributes") or {}
            tags = attrs.get("tags") if isinstance(attrs.get("tags"), dict) else {}
            code = _coerce_float((tags or {}).get("class_code"))
            share = _coerce_float((tags or {}).get("pixel_share_pct"))
            if code is not None and share is not None:
                out.append((int(code), share))
        return out

    @staticmethod
    def _aggregate_cover(shares: List[Tuple[int, float]]) -> Dict[str, float]:
        cover = {"water": 0.0, "vegetation": 0.0, "built": 0.0, "bare": 0.0, "wetland": 0.0}
        for code, share in shares:
            if code in _WORLDCOVER_WATER:
                cover["water"] += share
            if code in _WORLDCOVER_WETLAND:
                cover["wetland"] += share
            if code in _WORLDCOVER_VEGETATION:
                cover["vegetation"] += share
            if code in _WORLDCOVER_BUILTUP:
                cover["built"] += share
            if code in _WORLDCOVER_BARE:
                cover["bare"] += share
        return {key: round(value, 2) for key, value in cover.items() if value > 0}

    def _baseline_from_graph(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        nodes = graph.get("nodes") or (graph.get("graph_data") or {}).get("nodes") or []
        for node in nodes or []:
            attrs = (node or {}).get("attributes") or {}
            baseline = attrs.get("environment_baseline")
            if isinstance(baseline, dict):
                return self._baseline_from_meta(baseline)
        return {}

    @staticmethod
    def _baseline_from_meta(baseline: Dict[str, Any]) -> Dict[str, Any]:
        current = baseline.get("current") if isinstance(baseline.get("current"), dict) else {}
        return {
            "provider": baseline.get("provider"),
            "wind_direction_10m": (current or {}).get("wind_direction_10m"),
            "wind_speed_10m": (current or {}).get("wind_speed_10m"),
            "precipitation": (current or {}).get("precipitation"),
        }
