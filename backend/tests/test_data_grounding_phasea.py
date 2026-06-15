"""Phase-A tests for spatial grounding (M1).

Deterministic, no live LLM / network. Exercises:
- ground() returns source="map_seed_grounded" with non-empty, provenance-tagged
  priors when regions carry real WorldCover/OSM land-cover signal;
- ground() reads on-disk seed artifacts (graph_snapshot.json) for seed-wide
  land cover when a region carries no embedded signal;
- ground() falls back to local_fallback when there is no spatial signal at all;
- TransportContextResolver.resolve() derives transport edges from a synthetic
  region adjacency and degrades to local_fallback when given nothing.
"""

import json
import os

from app.services.data_grounding import PublicDataGroundingService
from app.services.transport_context_resolver import TransportContextResolver


def _water_region():
    return {
        "region_id": "water_basin",
        "name": "Water Basin",
        "land_use_class": "water",
        "tags": ["water", "worldcover_80"],
        "ecology_assets": ["river_channel"],
        "industry_tags": [],
        "neighbors": ["urban_core"],
        "carriers": ["water_flow"],
        "lat": 30.5,
        "lon": 114.3,
    }


def _urban_region():
    return {
        "region_id": "urban_core",
        "name": "Urban Core",
        "land_use_class": "industrial",
        "tags": ["urban", "worldcover_50"],
        "ecology_assets": [],
        "industry_tags": ["port_logistics"],
        "neighbors": ["water_basin"],
        "carriers": ["transport_flow"],
        "lat": 30.6,
        "lon": 114.4,
    }


def test_ground_returns_grounded_with_provenance():
    service = PublicDataGroundingService()
    summary = service.ground(
        regions=[_water_region(), _urban_region()],
        diffusion_template="inland_water_network",
        document_text="",
    )

    assert summary["source"] == "map_seed_grounded"
    assert summary["priors"], "expected non-empty per-region priors"
    records = summary["records"]
    assert len(records) == 2

    water_record = next(r for r in records if r["metadata"]["region"] == "Water Basin")
    assert water_record["priors"], "water region should carry priors"
    # Every prior must declare provenance, and only observed/inferred allowed.
    for key, prov in water_record["provenance"].items():
        assert prov in {"observed", "inferred"}
        assert key in water_record["priors"]
    # Water/ecology zone should report at least one observed prior.
    assert "observed" in set(water_record["provenance"].values())


def test_ground_falls_back_without_signal():
    service = PublicDataGroundingService()
    summary = service.ground(
        regions=[{"region_id": "r1", "name": "Generic", "land_use_class": "", "tags": []}],
        diffusion_template="marine",
        document_text="",
    )
    assert summary["source"] == "local_fallback"
    assert summary["priors"] == {}
    assert summary["records"] == []


def test_ground_reads_seed_artifacts_for_seedwide_cover(tmp_path):
    # Region with no embedded signal, but a seed on disk with WorldCover facts.
    seed_dir = tmp_path / "mapseed_test"
    seed_dir.mkdir()
    graph = {
        "nodes": [
            {
                "uuid": "feature_worldcover_80_0",
                "attributes": {
                    "tags": {"class_code": 80, "pixel_share_pct": 35.0},
                },
            },
            {
                "uuid": "feature_worldcover_50_0",
                "attributes": {
                    "tags": {"class_code": 50, "pixel_share_pct": 22.0},
                },
            },
        ]
    }
    (seed_dir / "graph_snapshot.json").write_text(json.dumps(graph), encoding="utf-8")

    service = PublicDataGroundingService()
    summary = service.ground(
        regions=[{"region_id": "r1", "name": "Generic", "land_use_class": "", "tags": []}],
        diffusion_template="inland_water_network",
        seed_dir=str(seed_dir),
    )
    assert summary["source"] == "map_seed_grounded"
    assert summary["seed_land_cover"].get("water") == 35.0
    assert summary["seed_land_cover"].get("built") == 22.0
    assert "graph_snapshot.json" in summary["successful_sources"]
    # The generic region now picks up seed-wide observed cover priors.
    record = summary["records"][0]
    assert record["priors"]
    assert "observed" in set(record["provenance"].values())


def test_transport_resolver_builds_edges_from_adjacency():
    resolver = TransportContextResolver()
    context = resolver.resolve(
        regions=[_water_region(), _urban_region()],
        diffusion_template="inland_water_network",
    )
    edges = context["transport_edges"]
    assert len(edges) == 1
    edge = edges[0]
    assert {edge["source_region_id"], edge["target_region_id"]} == {"water_basin", "urban_core"}
    assert edge["origin"] == "seed_adjacency"
    assert edge["epistemic_status"] == "inferred"
    # Water carrier present -> river reach channel.
    assert edge["channel_type"] == "river_reach"


def test_transport_resolver_falls_back_without_regions():
    resolver = TransportContextResolver()
    context = resolver.resolve(regions=[], diffusion_template="marine")
    assert context["provider"] == "local_fallback"
    assert context["transport_edges"] == []
