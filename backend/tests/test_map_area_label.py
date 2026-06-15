import unittest

from app.services.map_seed_manager import MapSeedManager


class MapAreaLabelTestCase(unittest.TestCase):
    def setUp(self):
        self.manager = MapSeedManager()
        self.admin_context = {
            "display_name": "前湾一路，宝安区，深圳市",
            "city": "深圳市",
            "district": "宝安区",
            "road": "前湾一路",
            "neighbourhood": "前海湾",
            "geographic_context": {
                "key": "shenzhen_baoan",
                "macro_area": "深圳市",
                "local_area": "宝安区",
                "feature_name": "宝安区西部城市与滨海片区",
                "area_label": "深圳市宝安区周边",
                "display_name": "深圳市宝安区及机场、茅洲河周边",
            },
        }

    def test_local_area_label_changes_with_radius(self):
        small = self.manager.describe_area_label(
            lat=22.52876,
            lon=113.89767,
            radius_m=1000,
            admin_context=self.admin_context,
        )
        medium = self.manager.describe_area_label(
            lat=22.52876,
            lon=113.89767,
            radius_m=5000,
            admin_context=self.admin_context,
        )
        broad = self.manager.describe_area_label(
            lat=22.52876,
            lon=113.89767,
            radius_m=47000,
            admin_context=self.admin_context,
        )

        self.assertEqual(small, "深圳市宝安区前湾一路周边")
        self.assertEqual(medium, "深圳市宝安区周边")
        self.assertEqual(broad, "深圳西部-珠江口东岸区域")
        self.assertEqual(len({small, medium, broad}), 3)

    def test_center_anchor_wins_over_large_water_range(self):
        airport = self.manager.describe_area_label(
            lat=22.31899,
            lon=113.91312,
            radius_m=17000,
            admin_context={
                "display_name": "22.31899, 113.91312",
                "city": "",
                "district": "",
            },
        )

        self.assertEqual(airport, "香港国际机场及大屿山周边")
        self.assertNotIn("伶仃洋水域", airport)

    def test_range_anchor_can_override_empty_water_center(self):
        water_near_airport = self.manager.describe_area_label(
            lat=22.345,
            lon=113.975,
            radius_m=9000,
            admin_context={
                "display_name": "22.345, 113.975",
                "city": "珠江口",
                "district": "伶仃洋",
                "geographic_context": {
                    "key": "lingdingyang",
                    "macro_area": "珠江口",
                    "local_area": "伶仃洋",
                    "feature_name": "伶仃洋水域",
                    "area_label": "珠江口伶仃洋水域",
                    "display_name": "珠江口伶仃洋及粤港澳近岸水域",
                    "area_kind": "water",
                },
            },
        )

        self.assertTrue(water_near_airport.startswith("香港国际机场"))
        self.assertNotIn("伶仃洋水域", water_near_airport)

    def test_local_forward_geocode_handles_known_airport_alias(self):
        candidates = self.manager._local_forward_geocode_candidates("香港机场", radius_m=17000)

        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["area_label"], "香港国际机场及大屿山周边")
        self.assertEqual(candidates[0]["admin_context"]["geographic_context"]["key"], "hong_kong_airport")

    def test_filter_features_keeps_map_seed_nodes_inside_analysis_radius(self):
        features = [
            {
                "feature_id": "inside_airport",
                "name": "机场岛",
                "subtype": "airport",
                "distance_m": 1200,
            },
            {
                "feature_id": "outside_zhuhai",
                "name": "珠海东岸",
                "subtype": "coastline",
                "distance_m": 36000,
            },
            {
                "feature_id": "weather",
                "name": "局地天气基线",
                "subtype": "weather_baseline",
                "distance_m": 0,
            },
        ]

        scoped = self.manager._filter_features_to_aoi(features, radius_m=17000)
        scoped_ids = {item["feature_id"] for item in scoped}

        self.assertIn("inside_airport", scoped_ids)
        self.assertIn("weather", scoped_ids)
        self.assertNotIn("outside_zhuhai", scoped_ids)


if __name__ == "__main__":
    unittest.main()
