from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.map_seed_manager import MapSeedManager
from app.services.scenario_foundation_resolver import (
    FoundationResolutionError,
    ScenarioFoundationResolver,
)


def _foundation():
    return {
        "artifact_id": "mapseed_base",
        "contract_version": "foundation.step1.v4",
        "project_id": "project_1",
        "graph_id": "graph_1",
        "map_seed_id": "mapseed_base",
        "location": "深圳湾",
        "content_hash": "foundation_hash",
        "region_ids": ["region_nanshan"],
        "target_catalog": [
            {"id": "region_nanshan", "name": "南山区", "kind": "region", "aliases": ["南山"]},
            {"id": "entity_hospital", "name": "深圳市第三人民医院", "kind": "entity"},
        ],
        "evidence_sources": [{"source": "osm", "status": "ready"}],
    }


class FakeMapSeedManager:
    def __init__(self, *, built_seed=None, geocodes=None):
        self.built_seed = built_seed or {"status": "ready", "data_quality": {"formal_ready": True}}
        self.geocodes = geocodes or []
        self.build_calls = []

    def build_seed(self, seed_id):
        self.build_calls.append(seed_id)
        return deepcopy(self.built_seed)

    def geocode_location(self, query, *, limit=3, radius_m=3000):
        return deepcopy(self.geocodes)


def test_reuses_existing_foundation_and_resolves_known_target_name():
    result = ScenarioFoundationResolver(FakeMapSeedManager()).resolve(
        base_foundation=_foundation(),
        event_inputs=[{"name": "强降雨", "target_labels": ["南山"]}],
        policy_inputs=[{"name": "医疗调度", "target_labels": ["深圳市第三人民医院"]}],
        simulation_id="sim_1",
        effort_snapshot={"effort_level": "high"},
        foundation_builder=lambda _seed_id: pytest.fail("不应重建底座"),
    )

    assert result.artifact["resolution_status"] == "reused"
    assert result.event_inputs[0]["target_region_ids"] == ["region_nanshan"]
    assert result.policy_inputs[0]["target_entity_ids"] == ["entity_hospital"]


def test_unicode_numeric_suffixes_remain_distinct_and_explicit_id_disambiguates():
    foundation = _foundation()
    foundation["target_catalog"].extend([
        {"id": "station_1", "name": "深圳湾公园地铁站 ①", "kind": "entity"},
        {"id": "station_2", "name": "深圳湾公园地铁站 ②", "kind": "entity"},
        {"id": "station_main", "name": "深圳湾公园地铁站", "kind": "entity"},
    ])

    result = ScenarioFoundationResolver(FakeMapSeedManager()).resolve(
        base_foundation=foundation,
        event_inputs=[{
            "name": "风暴潮影响轨道交通",
            "target_entity_ids": ["station_main"],
            "target_labels": ["深圳湾公园地铁站"],
        }],
        policy_inputs=[],
        simulation_id="sim_1",
        effort_snapshot={"effort_level": "high"},
        foundation_builder=lambda _seed_id: pytest.fail("不应重建底座"),
    )

    assert result.artifact["resolution_status"] == "reused"
    assert result.event_inputs[0]["target_entity_ids"] == ["station_main"]


def test_unknown_explicit_identifier_is_rejected_without_fabrication():
    with pytest.raises(FoundationResolutionError) as error:
        ScenarioFoundationResolver(FakeMapSeedManager()).resolve(
            base_foundation=_foundation(),
            event_inputs=[{"name": "强降雨", "target_entity_ids": ["missing_entity"]}],
            policy_inputs=[],
            simulation_id="sim_1",
            effort_snapshot={"effort_level": "high"},
            foundation_builder=lambda _seed_id: {},
        )

    assert error.value.code == "foundation_target_not_found"
    assert error.value.artifact["unresolved_targets"] == ["missing_entity"]


def test_missing_named_target_creates_simulation_scoped_revision(monkeypatch):
    base_seed = {
        "seed_id": "mapseed_base",
        "title": "深圳湾",
        "input": {"lat": 22.5, "lon": 113.95, "radius_m": 5000, "requested_location": "深圳湾"},
    }
    created = {}
    updates = []
    monkeypatch.setattr(MapSeedManager, "get_seed", lambda seed_id: deepcopy(base_seed))
    monkeypatch.setattr(
        MapSeedManager,
        "create_seed",
        lambda **kwargs: created.update(kwargs) or {"seed_id": "mapseed_revision"},
    )
    monkeypatch.setattr(
        MapSeedManager,
        "update_seed",
        lambda seed_id, **changes: updates.append((seed_id, changes)) or {"seed_id": seed_id, **changes},
    )
    monkeypatch.setattr(MapSeedManager, "is_formal_seed_ready", lambda seed: True)

    resolved = _foundation()
    resolved.update({
        "artifact_id": "mapseed_revision",
        "map_seed_id": "mapseed_revision",
        "content_hash": "revision_hash",
        "target_catalog": [
            *_foundation()["target_catalog"],
            {"id": "entity_pump", "name": "福田泵站", "kind": "entity"},
        ],
    })
    manager = FakeMapSeedManager()
    result = ScenarioFoundationResolver(manager).resolve(
        base_foundation=_foundation(),
        event_inputs=[{"name": "城市内涝", "target_labels": ["福田泵站"]}],
        policy_inputs=[],
        simulation_id="sim_1",
        effort_snapshot={"effort_level": "high"},
        foundation_builder=lambda seed_id: deepcopy(resolved),
    )

    assert manager.build_calls == ["mapseed_revision"]
    assert created["known_entities"] == "福田泵站"
    assert updates[0][1]["foundation_scope"] == "simulation"
    assert result.artifact["resolution_status"] == "enriched"
    assert result.artifact["added_entity_ids"] == ["entity_pump"]
    assert result.event_inputs[0]["target_entity_ids"] == ["entity_pump"]


def test_ambiguous_new_location_stops_before_map_generation(monkeypatch):
    base_seed = {
        "seed_id": "mapseed_base",
        "input": {"lat": 22.5, "lon": 113.95, "radius_m": 5000},
    }
    monkeypatch.setattr(MapSeedManager, "get_seed", lambda seed_id: deepcopy(base_seed))
    manager = FakeMapSeedManager(geocodes=[
        {"lat": 30.1, "lon": 114.1},
        {"lat": 31.1, "lon": 115.1},
    ])

    with pytest.raises(FoundationResolutionError) as error:
        ScenarioFoundationResolver(manager).resolve(
            base_foundation=_foundation(),
            event_inputs=[{"name": "化学泄漏"}],
            policy_inputs=[],
            scenario_location="新城",
            simulation_id="sim_1",
            effort_snapshot={"effort_level": "high"},
            foundation_builder=lambda _seed_id: {},
        )

    assert error.value.code == "foundation_location_ambiguous"
    assert error.value.artifact["resolution_status"] == "blocked"
