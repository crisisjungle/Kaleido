import json
import tempfile
import unittest
from pathlib import Path

from app.services.simulation_map_projection import SimulationMapProjectionBuilder
from app.services.simulation_realtime_graph import SimulationRealtimeGraphBuilder


class SimulationMapProjectionTestCase(unittest.TestCase):
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

    def test_human_agent_in_coastal_region_uses_dry_anchor(self):
        builder = SimulationMapProjectionBuilder(
            sim_dir="",
            simulation_id="sim_test",
            map_seed_id=None,
            source_mode="map_seed",
        )
        context = {
            "center": {"lat": 22.467, "lon": 113.7483},
            "radius_m": 20500,
            "anchor_points": [
                {
                    "lat": 22.37,
                    "lon": 113.76,
                    "name": "伶仃洋水域",
                    "category": "ecology",
                    "subtype": "water",
                    "source_kind": "observed",
                },
                {
                    "lat": 22.748,
                    "lon": 113.936,
                    "name": "光明区",
                    "category": "region",
                    "subtype": "admin_district",
                    "source_kind": "observed",
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

        self.assertAlmostEqual(human["attributes"]["lat"], 22.748, places=2)
        self.assertAlmostEqual(human["attributes"]["lon"], 113.936, places=2)

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
