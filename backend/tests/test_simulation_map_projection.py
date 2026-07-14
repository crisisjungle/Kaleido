import json
import tempfile
import unittest
from pathlib import Path

from app.services.simulation_map_projection import SimulationMapProjectionBuilder
from app.services.simulation_realtime_graph import SimulationRealtimeGraphBuilder


class SimulationMapProjectionTestCase(unittest.TestCase):
    def test_missing_legacy_quality_is_materialized_as_degraded(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = builder._build_context(
            map_layers_payload={
                "center": {"lat": 22.55, "lon": 113.85},
                "feature_points": [
                    {
                        "lat": 22.56,
                        "lon": 113.86,
                        "name": "旧参考点",
                        "source_kind": "reference",
                        "source_provider": "local_geographic_gazetteer",
                    }
                ],
            }
        )

        self.assertFalse(context["data_quality"]["formal_ready"])
        self.assertEqual(context["data_quality"]["status"], "unknown")
        self.assertEqual(context["formal_anchor_points"], [])

    def test_legacy_map_seed_coordinates_without_quality_are_not_labeled_real(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = {
            "center": {"lat": 22.55, "lon": 113.85},
            "radius_m": 50_000,
            "data_quality": {"status": "unknown", "formal_ready": False},
            "anchor_points": [],
            "formal_anchor_points": [],
            "water_geometries": [],
            "water_zones": [],
        }
        nodes = [
            {
                "uuid": "region::legacy_reference_cluster",
                "name": "旧参考点聚类区域",
                "labels": ["Entity", "Region"],
                "attributes": {
                    "region_id": "legacy_reference_cluster",
                    "region_type": "urban_zone",
                    "lat": 22.6,
                    "lon": 113.9,
                },
            }
        ]

        projected = builder._project_nodes(nodes, context)

        self.assertFalse(projected[0]["is_geographic"])
        self.assertEqual(projected[0]["attributes"]["placement"], "synthetic")

    def test_analysis_area_polygon_is_not_converted_to_agent_anchor(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = builder._build_context(
            map_layers_payload={
                "center": {"lat": 22.55, "lon": 113.85},
                "radius_m": 50_000,
                "data_quality": {"status": "partial", "formal_ready": False},
                "layers": [
                    {
                        "id": "analysis-area",
                        "type": "geojson",
                        "data": {
                            "type": "FeatureCollection",
                            "features": [
                                {
                                    "type": "Feature",
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [[[113.7, 22.4], [114.0, 22.4], [114.0, 22.7], [113.7, 22.4]]],
                                    },
                                    "properties": {"name": "分析范围"},
                                }
                            ],
                        },
                    }
                ],
            }
        )

        self.assertEqual(context["anchor_points"], [])
        self.assertFalse(context["data_quality"]["formal_ready"])

    def test_realtime_graph_preserves_region_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            sim_dir = Path(tmp)
            (sim_dir / "region_graph_snapshot.json").write_text(
                json.dumps(
                    [
                        {
                            "region_id": "urban_core",
                            "name": "城市建成片区",
                            "region_type": "urban_zone",
                            "lat": 22.7485,
                            "lon": 113.97629,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            graph = SimulationRealtimeGraphBuilder(str(sim_dir)).build()
            region_node = next(node for node in graph["nodes"] if node["uuid"] == "region::urban_core")

            self.assertEqual(region_node["attributes"]["lat"], 22.7485)
            self.assertEqual(region_node["attributes"]["lon"], 113.97629)

    def test_human_agent_does_not_use_far_dry_anchor_outside_home_region(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = {
            "center": {"lat": 22.467, "lon": 113.7483},
            "radius_m": 20500,
            "data_quality": {"status": "complete", "formal_ready": True},
            "anchor_points": [
                {
                    "lat": 22.37,
                    "lon": 113.76,
                    "name": "伶仃洋水域",
                    "category": "ecology",
                    "subtype": "water",
                    "source_kind": "observed",
                    "source_provider": "osm_overpass",
                },
                {
                    "lat": 22.748,
                    "lon": 113.936,
                    "name": "光明区",
                    "category": "region",
                    "subtype": "admin_district",
                    "source_kind": "observed",
                    "source_provider": "osm_overpass",
                },
            ],
            "water_geometries": [],
            "water_zones": [{"lat": 22.37, "lon": 113.76, "radius_m": 220.0}],
        }
        nodes = [
            {
                "uuid": "region::coastal",
                "name": "近岸水域",
                "labels": ["Entity", "Region"],
                "attributes": {"region_id": "coastal", "region_type": "coastal_zone"},
            },
            {
                "uuid": "agent::1",
                "name": "居民群体",
                "labels": ["Entity", "HumanActor"],
                "attributes": {"agent_id": 1, "home_region_id": "coastal", "agent_type": "human", "role_type": "residents"},
            },
        ]

        projected = builder._project_nodes(nodes, context)
        human = next(node for node in projected if node["uuid"] == "agent::1")

        distance_from_home_m = builder._haversine_m(
            human["attributes"]["lat"],
            human["attributes"]["lon"],
            22.37,
            113.76,
        )
        self.assertLess(distance_from_home_m, 3000)
        self.assertEqual(human["attributes"]["placement"], "synthetic")
        self.assertFalse(human["is_geographic"])

    def test_agent_uses_compatible_real_anchor_inside_home_subregion(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = {
            "center": {"lat": 22.55, "lon": 113.9},
            "radius_m": 36000,
            "data_quality": {"status": "complete", "formal_ready": True},
            "anchor_points": [
                {
                    "lat": 22.551,
                    "lon": 113.901,
                    "name": "南山社区服务中心",
                    "category": "social",
                    "subtype": "community",
                    "source_kind": "observed",
                    "source_provider": "osm_overpass",
                },
                {
                    "lat": 22.75,
                    "lon": 113.95,
                    "name": "远端城区",
                    "category": "region",
                    "subtype": "admin_district",
                    "source_kind": "observed",
                    "source_provider": "osm_overpass",
                },
            ],
            "water_geometries": [],
            "water_zones": [],
        }
        nodes = [
            {
                "uuid": "region::nanshan",
                "name": "南山区",
                "labels": ["Entity", "Region"],
                "attributes": {"region_id": "nanshan", "region_type": "urban_zone", "lat": 22.55, "lon": 113.9},
            },
            {
                "uuid": "subregion::nanshan_core",
                "name": "南山区·核心社区",
                "labels": ["Entity", "Region", "Subregion"],
                "attributes": {
                    "region_id": "nanshan_core",
                    "parent_region_id": "nanshan",
                    "region_type": "urban_zone",
                    "lat": 22.55,
                    "lon": 113.9,
                },
            },
            {
                "uuid": "agent::resident",
                "name": "社区居民代表",
                "labels": ["Entity", "HumanActor"],
                "attributes": {
                    "agent_id": "resident",
                    "home_region_id": "nanshan",
                    "home_subregion_id": "nanshan_core",
                    "agent_type": "human",
                    "role_type": "resident",
                },
            },
        ]

        projected = builder._project_nodes(nodes, context)
        agent = next(node for node in projected if node["uuid"] == "agent::resident")

        self.assertAlmostEqual(agent["attributes"]["lat"], 22.551, places=2)
        self.assertAlmostEqual(agent["attributes"]["lon"], 113.901, places=2)
        self.assertEqual(agent["attributes"]["placement"], "geographic")
        self.assertTrue(agent["is_geographic"])

    def test_reference_or_unknown_provider_cannot_become_real_anchor(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = {
            "center": {"lat": 22.55, "lon": 113.9},
            "radius_m": 36_000,
            "data_quality": {"status": "partial", "formal_ready": True},
            "anchor_points": [
                {
                    "lat": 22.551,
                    "lon": 113.901,
                    "name": "本地参考居民区",
                    "category": "facility",
                    "subtype": "residential",
                    "source_kind": "reference",
                    "source_provider": "local_geographic_gazetteer",
                },
                {
                    "lat": 22.552,
                    "lon": 113.902,
                    "name": "来源未知的居民区",
                    "category": "facility",
                    "subtype": "residential",
                    "source_kind": "observed",
                    "source_provider": "unknown_provider",
                },
            ],
            "water_geometries": [],
            "water_zones": [],
        }

        candidates = builder._select_anchor_candidates(
            context=context,
            desired_tags=["built"],
            require_water=False,
        )

        self.assertEqual(candidates, [])

    def test_graph_layout_xy_is_not_treated_as_geographic_position(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = {
            "center": {"lat": 22.52876, "lon": 113.89767},
            "radius_m": 47000,
            "anchor_points": [
                {
                    "lat": 22.52876,
                    "lon": 113.89767,
                    "name": "深圳西部-珠江口东岸区域",
                    "category": "region",
                    "subtype": "admin_area",
                    "source_kind": "observed",
                }
            ],
            "water_geometries": [],
            "water_zones": [],
        }
        nodes = [
            {
                "uuid": "region::layout_only",
                "name": "布局坐标测试区域",
                "labels": ["Entity", "Region"],
                "attributes": {"x": 12.5, "y": 44.8, "region_id": "layout_only"},
            }
        ]

        projected = builder._project_nodes(nodes, context)
        node = projected[0]

        self.assertNotEqual(node["attributes"]["lat"], 44.8)
        self.assertNotEqual(node["attributes"]["lon"], 12.5)
        self.assertAlmostEqual(node["attributes"]["lat"], 22.52876, places=1)
        self.assertAlmostEqual(node["attributes"]["lon"], 113.89767, places=1)

    def test_projection_center_uses_node_coordinates_without_map_seed(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="golden_case",
        )
        graph = {
            "nodes": [
                {
                    "uuid": "region::wuhan_core",
                    "name": "武汉核心城区",
                    "labels": ["Entity", "Region"],
                    "attributes": {"region_id": "wuhan_core", "lat": 30.6, "lon": 114.3},
                },
                {
                    "uuid": "region::wuhan_east",
                    "name": "武汉东部片区",
                    "labels": ["Entity", "Region"],
                    "attributes": {"region_id": "wuhan_east", "lat": 30.7, "lon": 114.5},
                },
            ],
            "edges": [],
        }

        projection = builder.build(graph)

        self.assertEqual(projection["meta"]["node_count"], 2)
        self.assertNotEqual(projection["center"], {"lat": 20.0, "lon": 0.0})
        self.assertAlmostEqual(projection["center"]["lat"], 30.65, places=2)
        self.assertAlmostEqual(projection["center"]["lon"], 114.4, places=2)


if __name__ == "__main__":
    unittest.main()
