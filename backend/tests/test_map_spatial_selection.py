"""Contract tests for map-seed spatial selection.

These tests intentionally exercise the selection policy through a small pure
module.  Network collection belongs to ``MapSeedManager``; deciding which of
the collected/fallback candidates represent the user's AOI belongs here so the
policy remains deterministic and independently testable.
"""

import io
import math
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

from PIL import Image

from app.config import Config
from app.services.effort_contract import build_effort_snapshot
from app.services.map_spatial_selection import (
    SelectionContext,
    is_valid_proxy_anchor,
    select_spatial_features,
    spatial_policy_from_effort,
    summarize_source_status,
)
from app.services.map_seed_manager import MapSeedManager


CENTER_LAT = 22.55
CENTER_LON = 113.85


def make_feature(
    feature_id,
    name,
    *,
    lat,
    lon,
    category="ecology",
    subtype="wetland",
    spatial_level="site",
    importance=8,
    source_kind="observed",
    provider="overpass",
    tags=None,
):
    merged_tags = {
        "provider": provider,
        "spatial_level": spatial_level,
    }
    merged_tags.update(tags or {})
    return {
        "feature_id": feature_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "distance_m": round(_haversine_m(CENTER_LAT, CENTER_LON, lat, lon), 1),
        "category": category,
        "subtype": subtype,
        "spatial_level": spatial_level,
        "node_family": "EcologicalReceptor",
        "importance": importance,
        "source_kind": source_kind,
        "confidence": 0.8,
        "summary": name,
        "tags": merged_tags,
    }


def _haversine_m(lat1, lon1, lat2, lon2):
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _quadrant(feature):
    north_south = "N" if feature["lat"] >= CENTER_LAT else "S"
    east_west = "E" if feature["lon"] >= CENTER_LON else "W"
    return north_south + east_west


class MapSpatialSelectionContractTestCase(unittest.TestCase):
    def test_effort_policy_controls_candidate_anchors_and_selective_detail(self):
        candidates = [
            make_feature(
                "city",
                "测试市",
                lat=CENTER_LAT,
                lon=CENTER_LON,
                category="region",
                subtype="admin_city",
                spatial_level="city",
            ),
            make_feature(
                "district",
                "测试区",
                lat=CENTER_LAT + 0.01,
                lon=CENTER_LON,
                category="region",
                subtype="admin_district",
                spatial_level="district",
            ),
            make_feature(
                "street",
                "测试街道",
                lat=CENTER_LAT + 0.02,
                lon=CENTER_LON,
                category="region",
                subtype="subdistrict",
                spatial_level="street",
            ),
        ]
        for index in range(3):
            candidates.append(
                make_feature(
                    f"hospital_{index}",
                    f"应急医院 {index}",
                    lat=CENTER_LAT + 0.025 + index * 0.002,
                    lon=CENTER_LON,
                    category="facility",
                    subtype="hospital",
                    spatial_level="site",
                )
            )
        candidates.append(
            make_feature(
                "hospital_icu",
                "应急医院 ICU",
                lat=CENTER_LAT + 0.03,
                lon=CENTER_LON,
                category="facility",
                subtype="hospital",
                spatial_level="internal_unit",
            )
        )
        context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=50_000,
            simulation_requirement="评估台风期间应急医疗承压",
        )

        light = select_spatial_features(
            candidates,
            context=context,
            limit=100,
            effort_policy=spatial_policy_from_effort(build_effort_snapshot("light")),
        )
        high = select_spatial_features(
            candidates,
            context=context,
            limit=100,
            effort_policy=spatial_policy_from_effort(build_effort_snapshot("high")),
        )
        extra_high = select_spatial_features(
            candidates,
            context=context,
            limit=100,
            effort_policy=spatial_policy_from_effort(build_effort_snapshot("extra_high")),
        )

        light_ids = {item["feature_id"] for item in light.selected_features}
        high_ids = {item["feature_id"] for item in high.selected_features}
        extra_high_ids = {item["feature_id"] for item in extra_high.selected_features}
        self.assertNotIn("street", light_ids)
        self.assertEqual(len(light_ids & {"hospital_0", "hospital_1", "hospital_2"}), 2)
        self.assertIn("street", high_ids)
        self.assertTrue({"hospital_0", "hospital_1", "hospital_2"}.issubset(high_ids))
        self.assertNotIn("hospital_icu", high_ids)
        self.assertIn("hospital_icu", extra_high_ids)
        self.assertEqual(light.diagnostics["targeted_refinement_count"], 2)

    def test_effort_candidate_pool_and_anchor_caps_are_hard_boundaries(self):
        candidates = [
            make_feature(
                f"district_{index}",
                f"片区 {index}",
                lat=CENTER_LAT + (index % 10) * 0.001,
                lon=CENTER_LON + (index // 10) * 0.001,
                category="region",
                subtype="admin_district",
                spatial_level="district",
            )
            for index in range(100)
        ]
        result = select_spatial_features(
            candidates,
            context=SelectionContext(
                center_lat=CENTER_LAT,
                center_lon=CENTER_LON,
                radius_m=50_000,
            ),
            limit=100,
            effort_policy=spatial_policy_from_effort(build_effort_snapshot("light")),
        )

        self.assertEqual(result.diagnostics["collected_candidate_count"], 100)
        self.assertEqual(result.diagnostics["candidate_count"], 36)
        self.assertEqual(len(result.selected_features), 12)

    def test_map_seed_manager_reads_exact_limits_from_effort_snapshot(self):
        manager = MapSeedManager()
        limits = manager._profile_limits(
            {
                "input": {},
                "effort_snapshot": build_effort_snapshot("extra_high"),
            }
        )

        self.assertEqual(limits["spatial_feature_limit"], 80)
        self.assertEqual(limits["candidate_pool_limit"], 240)
        self.assertEqual(limits["spatial_effort_policy"].base_spatial_level, 3)
        self.assertEqual(limits["spatial_effort_policy"].hotspot_spatial_level, 4)

    def test_overpass_runtime_remark_is_failure_not_empty_success(self):
        manager = MapSeedManager()
        manager._llm_client = None
        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            with patch.object(Config, "OVERPASS_ENDPOINTS", ["https://example.invalid/interpreter"]), patch(
                "app.services.map_seed_manager._safe_http_json",
                return_value={"elements": [], "remark": "runtime error: Query timed out"},
            ):
                features, status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    3_000,
                )

        self.assertEqual(features, [])
        self.assertEqual(status["status"], "failed")
        self.assertIn("Query timed out", status["error"])

    def test_cached_overpass_fallback_recomputes_distance_for_current_center(self):
        manager = MapSeedManager()
        manager._llm_client = None
        cached_feature = make_feature(
            "cached_wetland",
            "缓存湿地",
            lat=CENTER_LAT + 0.01,
            lon=CENTER_LON,
        )
        cached_feature["distance_m"] = 99_999
        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            cache_key = manager._source_cache_key(
                "overpass",
                lat=CENTER_LAT,
                lon=CENTER_LON,
                radius_m=3_000,
                profile="site_street:v5-batched-facilities",
            )
            manager._write_source_cache(
                "overpass",
                cache_key,
                features=[cached_feature],
                status={"status": "completed", "provider": "osm_overpass"},
            )
            with patch.object(Config, "OVERPASS_ENDPOINTS", ["https://example.invalid/interpreter"]), patch(
                "app.services.map_seed_manager._safe_http_json",
                side_effect=TimeoutError("live timeout"),
            ):
                features, status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    3_000,
                )

        # A legacy cache without per-batch completeness may still provide
        # evidence, but it must not short-circuit retries or masquerade as a
        # complete cache hit.
        self.assertEqual(status["status"], "partial")
        self.assertFalse(status["batch_coverage"]["complete"])
        self.assertEqual(
            status["batch_coverage"]["missing_batches"],
            [
                "administrative",
                "water_ecology",
                "settlement_landuse",
                "public_facilities",
                "critical_infrastructure",
                "service_hubs",
                "transport",
            ],
        )
        self.assertLess(features[0]["distance_m"], 2_000)
        self.assertNotEqual(features[0]["distance_m"], 99_999)

    def test_partial_overpass_cache_retries_only_missing_batches(self):
        manager = MapSeedManager()
        manager._llm_client = None
        cached_admin = make_feature(
            "relation_101",
            "缓存行政区",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            category="region",
            subtype="admin_district",
            spatial_level="district",
        )
        cached_admin["tags"]["overpass_batch"] = "administrative"
        cached_batches = [
            {"batch": "administrative", "status": "completed", "raw_element_count": 1},
            {"batch": "water_ecology", "status": "completed", "raw_element_count": 0},
            {"batch": "settlement_landuse", "status": "completed", "raw_element_count": 0},
            {"batch": "public_facilities", "status": "failed", "error": "timeout"},
            {"batch": "critical_infrastructure", "status": "completed", "raw_element_count": 0},
            {"batch": "service_hubs", "status": "completed", "raw_element_count": 0},
            {"batch": "transport", "status": "completed", "raw_element_count": 0},
        ]
        calls = []

        def fake_overpass(_url, **kwargs):
            query = str(kwargs.get("data") or "")
            calls.append(query)
            return {
                "elements": [
                    {
                        "type": "node",
                        "id": 202,
                        "lat": CENTER_LAT + 0.005,
                        "lon": CENTER_LON,
                        "tags": {"name": "补查医院", "amenity": "hospital"},
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            cache_key = manager._source_cache_key(
                "overpass",
                lat=CENTER_LAT,
                lon=CENTER_LON,
                radius_m=3_000,
                profile="site_street:v5-batched-facilities",
            )
            manager._write_source_cache(
                "overpass",
                cache_key,
                features=[cached_admin],
                status={
                    "status": "partial",
                    "provider": "osm_overpass",
                    "batches": cached_batches,
                },
            )
            with patch.object(Config, "OVERPASS_ENDPOINTS", ["https://example.test/interpreter"]), patch(
                "app.services.map_seed_manager._safe_http_json",
                side_effect=fake_overpass,
            ):
                features, status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    3_000,
                )

        self.assertEqual(len(calls), 1)
        self.assertIn('amenity~"hospital|clinic|doctors', calls[0])
        self.assertEqual(status["status"], "completed")
        self.assertTrue(status["batch_coverage"]["complete"])
        self.assertEqual(status["batch_coverage"]["missing_batches"], [])
        self.assertEqual(status["category_coverage"]["coverage_ratio"], 1.0)
        self.assertEqual({item["name"] for item in features}, {"缓存行政区", "补查医院"})
        hospital = next(item for item in features if item["name"] == "补查医院")
        self.assertEqual(hospital["tags"]["overpass_batch"], "public_facilities")

    def test_public_facility_batch_keeps_clinic_and_shelter_as_separate_r3_candidates(self):
        manager = MapSeedManager()
        manager._llm_client = None

        def fake_overpass(_url, **kwargs):
            query = str(kwargs.get("data") or "")
            if 'amenity~"hospital|clinic|doctors' not in query:
                return {"elements": []}
            return {
                "elements": [
                    {
                        "type": "node",
                        "id": 301,
                        "lat": CENTER_LAT + 0.002,
                        "lon": CENTER_LON,
                        "tags": {"name": "社区诊所", "amenity": "clinic"},
                    },
                    {
                        "type": "node",
                        "id": 302,
                        "lat": CENTER_LAT - 0.002,
                        "lon": CENTER_LON,
                        "tags": {"name": "滨海避难场所", "amenity": "shelter"},
                    },
                ]
            }

        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            with patch.object(Config, "OVERPASS_ENDPOINTS", ["https://example.test/interpreter"]), patch(
                "app.services.map_seed_manager._safe_http_json",
                side_effect=fake_overpass,
            ):
                features, status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    3_000,
                )

        by_subtype = {item["subtype"]: item for item in features}
        self.assertIn("clinic", by_subtype)
        self.assertIn("shelter", by_subtype)
        self.assertEqual(by_subtype["clinic"]["tags"]["overpass_batch"], "public_facilities")
        self.assertTrue(status["batch_coverage"]["complete"])

    def test_complete_empty_overpass_result_uses_short_negative_cache(self):
        manager = MapSeedManager()
        manager._llm_client = None
        call_count = 0

        def empty_overpass(_url, **_kwargs):
            nonlocal call_count
            call_count += 1
            return {"elements": []}

        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            with patch.object(Config, "OVERPASS_ENDPOINTS", ["https://example.test/interpreter"]), patch.object(
                Config,
                "MAP_SOURCE_NEGATIVE_CACHE_TTL_SECONDS",
                900,
            ), patch(
                "app.services.map_seed_manager._safe_http_json",
                side_effect=empty_overpass,
            ):
                first_features, first_status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    3_000,
                )
                first_call_count = call_count
                second_features, second_status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    3_000,
                )

        self.assertEqual(first_features, [])
        self.assertEqual(first_status["status"], "empty")
        self.assertTrue(first_status["batch_coverage"]["complete"])
        self.assertGreater(first_call_count, 0)
        self.assertEqual(call_count, first_call_count)
        self.assertEqual(second_features, [])
        self.assertEqual(second_status["status"], "cached")
        self.assertEqual(second_status["cache_source_status"], "empty")

    def test_worldcover_uses_current_official_wms_contract_as_context_only(self):
        manager = MapSeedManager()
        manager._llm_client = None
        image_bytes = io.BytesIO()
        Image.new("RGB", (32, 32), (0, 100, 0)).save(image_bytes, format="PNG")
        captured_urls = []

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(request, timeout):
            self.assertGreaterEqual(timeout, 3)
            captured_urls.append(request.full_url)
            return FakeResponse(image_bytes.getvalue())

        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            with patch.object(Config, "WORLDCOVER_WMS_URL", "https://titiler.terrascope.be/wms"), patch.object(
                Config, "WORLDCOVER_WMS_VERSION", "1.3.0"
            ), patch.object(
                Config, "WORLDCOVER_WMS_LAYER", "esa-worldcover-map-10m-2021-v2_map"
            ), patch.object(
                Config, "WORLDCOVER_WMS_TIME", "2021-01-01"
            ), patch(
                "app.services.map_seed_manager.urllib.request.urlopen",
                side_effect=fake_urlopen,
            ):
                features, status, _layers = manager._collect_worldcover_features(
                    lat=CENTER_LAT,
                    lon=CENTER_LON,
                    radius_m=3_000,
                    components_per_class=1,
                )

        query = urllib.parse.parse_qs(urllib.parse.urlparse(captured_urls[0]).query)
        self.assertEqual(query["version"], ["1.3.0"])
        self.assertEqual(query["layers"], ["esa-worldcover-map-10m-2021-v2_map"])
        self.assertEqual(query["time"], ["2021-01-01"])
        self.assertEqual(query["crs"], ["EPSG:3857"])
        self.assertNotIn("srs", query)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["analysis_grade"], "contextual_only")
        self.assertTrue(features)
        self.assertTrue(all(item["source_kind"] == "reference" for item in features))

    def test_scene_type_is_not_guessed_from_admin_or_wms_context(self):
        manager = MapSeedManager()
        manager._llm_client = None
        admin_boundary = make_feature(
            "taipei_admin",
            "臺北市",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            category="region",
            subtype="admin_city",
            spatial_level="city",
            provider="osm_overpass",
        )
        wms_built_context = make_feature(
            "wms_built",
            "建成区背景",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            category="facility",
            subtype="worldcover_50",
            source_kind="reference",
            provider="worldcover_wms",
        )

        result = manager._classify_scene(
            [admin_boundary, wms_built_context],
            {"display_name": "臺北市士林區"},
        )

        self.assertFalse(result["classification_ready"])
        self.assertEqual(result["primary_scene"], "unknown")
        self.assertIn("不判断区域类型", result["reasoning"])

    def test_scene_type_uses_formal_environment_features(self):
        manager = MapSeedManager()
        manager._llm_client = None
        residential = make_feature(
            "osm_residential",
            "士林居住片区",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            category="facility",
            subtype="residential",
            provider="osm_overpass",
        )

        result = manager._classify_scene(
            [residential],
            {"display_name": "臺北市士林區"},
        )

        self.assertTrue(result["classification_ready"])
        self.assertEqual(result["primary_scene"], "urban_edge")
        self.assertEqual(result["evidence_feature_count"], 1)

    def test_explicit_place_and_focus_terms_override_distance_bias(self):
        candidates = [
            make_feature(
                "near_guangzhou_park",
                "南沙中心公园",
                lat=22.551,
                lon=113.851,
                subtype="park",
                importance=10,
            ),
            make_feature(
                "near_guangzhou_road",
                "龙穴大道",
                lat=22.552,
                lon=113.852,
                category="facility",
                subtype="road_corridor",
                importance=10,
            ),
            make_feature(
                "focus_shenzhen_bay",
                "深圳湾湿地",
                lat=22.49,
                lon=113.99,
                subtype="wetland",
                importance=7,
            ),
            make_feature(
                "focus_futian_hospital",
                "深圳福田区应急医院",
                lat=22.53,
                lon=114.05,
                category="facility",
                subtype="hospital",
                importance=7,
            ),
        ]
        context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=50_000,
            title="深圳湾湿地台风影响",
            simulation_requirement="重点分析深圳湾湿地及深圳福田区的脆弱群体与应急医疗",
            admin_context={"city": "广州市", "district": "南沙区"},
        )

        result = select_spatial_features(candidates, context=context, limit=2)
        selected_ids = [item["feature_id"] for item in result.selected_features]

        self.assertEqual(selected_ids[0], "focus_shenzhen_bay")
        self.assertEqual(set(selected_ids), {"focus_shenzhen_bay", "focus_futian_hospital"})
        self.assertTrue(any("深圳湾" in term for term in result.focus_terms))
        self.assertTrue(result.diagnostics.get("explicit_focus"))

    def test_city_short_name_and_focus_clause_distinguish_shenzhen_from_scope_guangzhou(self):
        candidates = [
            make_feature(
                "guangzhou_city",
                "广州市",
                lat=CENTER_LAT,
                lon=CENTER_LON,
                category="region",
                subtype="admin_city",
                spatial_level="city",
                importance=10,
            ),
            make_feature(
                "shenzhen_city",
                "深圳市",
                lat=CENTER_LAT - 0.08,
                lon=CENTER_LON + 0.18,
                category="region",
                subtype="admin_city",
                spatial_level="city",
                importance=7,
            ),
        ]
        context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=50_000,
            focus_text="我其实就想深圳，但是范围确实覆盖到了广州市",
        )

        result = select_spatial_features(candidates, context=context, limit=1)

        self.assertEqual(result.selected_features[0]["feature_id"], "shenzhen_city")
        self.assertTrue(result.diagnostics["explicit_focus"])
        self.assertIn("深圳", result.focus_terms)

    def test_city_focus_does_not_directly_name_every_poi_in_that_city(self):
        candidates = [
            make_feature(
                "shenzhen_city",
                "深圳市",
                lat=CENTER_LAT - 0.08,
                lon=CENTER_LON + 0.18,
                category="region",
                subtype="admin_city",
                spatial_level="city",
            ),
            make_feature(
                "guangzhou_city",
                "广州市",
                lat=CENTER_LAT,
                lon=CENTER_LON,
                category="region",
                subtype="admin_city",
                spatial_level="city",
            ),
        ]
        for index in range(35):
            candidates.append(
                make_feature(
                    f"shenzhen_poi_{index}",
                    f"深圳设施 {index}",
                    lat=CENTER_LAT - 0.04 + index * 0.001,
                    lon=CENTER_LON + 0.08,
                    category="facility",
                    subtype="hospital" if index % 2 else "school",
                    spatial_level="site",
                    tags={"addr:city": "深圳市"},
                )
            )
        result = select_spatial_features(
            candidates,
            context=SelectionContext(
                center_lat=CENTER_LAT,
                center_lon=CENTER_LON,
                radius_m=50_000,
                focus_text="我其实就想深圳，但是范围确实覆盖到了广州市",
            ),
            limit=28,
        )

        self.assertEqual(result.selected_features[0]["feature_id"], "shenzhen_city")
        self.assertFalse(any(item["spatial_level"] == "site" for item in result.selected_features))

    def test_missing_focused_city_boundary_uses_bounded_poi_representatives_not_excluded_city(self):
        candidates = [
            make_feature(
                "guangzhou_city",
                "广州市",
                lat=CENTER_LAT,
                lon=CENTER_LON,
                category="region",
                subtype="admin_city",
                spatial_level="city",
            )
        ]
        for index, subtype in enumerate(["hospital", "school", "hospital", "school", "rail_station", "park", "marketplace"]):
            candidates.append(
                make_feature(
                    f"shenzhen_poi_{index}",
                    f"焦点设施 {index}",
                    lat=CENTER_LAT - 0.06 + index * 0.012,
                    lon=CENTER_LON + 0.10,
                    category="ecology" if subtype == "park" else "facility",
                    subtype=subtype,
                    spatial_level="site",
                    tags={"addr:city": "深圳市"},
                )
            )
        result = select_spatial_features(
            candidates,
            context=SelectionContext(
                center_lat=CENTER_LAT,
                center_lon=CENTER_LON,
                radius_m=50_000,
                focus_text="我其实就想深圳，但是范围确实覆盖到了广州市",
            ),
            limit=28,
        )

        selected_ids = {item["feature_id"] for item in result.selected_features}
        self.assertNotIn("guangzhou_city", selected_ids)
        self.assertLessEqual(len(result.selected_features), 6)
        self.assertEqual(result.diagnostics["focus_resolution"], "representative_fallback")
        self.assertGreaterEqual(len({item["category"] for item in result.selected_features}), 2)

    def test_no_explicit_focus_balances_spatial_sectors_and_categories(self):
        candidates = []
        quadrant_offsets = {
            "NE": (0.055, 0.055),
            "NW": (0.055, -0.055),
            "SE": (-0.055, 0.055),
            "SW": (-0.055, -0.055),
        }
        category_specs = [
            ("ecology", "wetland"),
            ("facility", "hospital"),
            ("region", "admin_district"),
        ]
        for quadrant, (lat_delta, lon_delta) in quadrant_offsets.items():
            for category, subtype in category_specs:
                candidates.append(
                    make_feature(
                        f"{quadrant.lower()}_{category}",
                        f"{quadrant} {category}",
                        lat=CENTER_LAT + lat_delta,
                        lon=CENTER_LON + lon_delta,
                        category=category,
                        subtype=subtype,
                        spatial_level="district" if category == "region" else "site",
                    )
                )
        context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=15_000,
            title="",
            simulation_requirement="评估选定区域的综合环境风险",
            admin_context={},
        )

        result = select_spatial_features(candidates, context=context, limit=8)
        selected = result.selected_features

        self.assertEqual(len(selected), 8)
        self.assertGreaterEqual(len({_quadrant(item) for item in selected}), 4)
        self.assertGreaterEqual(len({item["category"] for item in selected}), 3)
        self.assertFalse(result.diagnostics.get("explicit_focus"))

    def test_aoi_location_alone_scopes_but_does_not_become_focus(self):
        candidates = [
            make_feature(
                "district_nansha",
                "南沙区",
                lat=22.56,
                lon=113.86,
                category="region",
                subtype="admin_district",
                spatial_level="district",
            ),
            make_feature(
                "district_baoan",
                "宝安区",
                lat=22.60,
                lon=113.80,
                category="region",
                subtype="admin_district",
                spatial_level="district",
            ),
        ]
        context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=50_000,
            requested_location="南沙区",
            title="南沙区",
            simulation_requirement="南沙区",
            admin_context={"display_name": "南沙区", "district": "南沙区"},
        )

        result = select_spatial_features(candidates, context=context, limit=2)

        self.assertFalse(result.diagnostics.get("explicit_focus"))

    def test_large_aoi_uses_macro_granularity_unless_user_names_a_site(self):
        candidates = [
            make_feature(
                "city_shenzhen",
                "深圳市",
                lat=22.54,
                lon=114.06,
                category="region",
                subtype="admin_city",
                spatial_level="city",
            ),
            make_feature(
                "district_nansha",
                "南沙区",
                lat=22.68,
                lon=113.54,
                category="region",
                subtype="admin_district",
                spatial_level="district",
            ),
            make_feature(
                "region_estuary",
                "珠江口生态廊道",
                lat=22.40,
                lon=113.78,
                category="ecology",
                subtype="coastline",
                spatial_level="region",
            ),
            make_feature(
                "street_phoenix",
                "凤凰街道",
                lat=22.745,
                lon=113.976,
                category="region",
                subtype="subdistrict",
                spatial_level="street",
                importance=10,
            ),
            make_feature(
                "site_school",
                "凤凰实验学校",
                lat=22.744,
                lon=113.974,
                category="facility",
                subtype="school",
                spatial_level="site",
                importance=10,
            ),
        ]
        broad_context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=50_000,
            title="",
            simulation_requirement="评估珠江口区域综合风险",
            admin_context={},
        )

        broad = select_spatial_features(candidates, context=broad_context, limit=3)

        self.assertIn(broad.granularity, {"district", "city_region"})
        self.assertNotIn("site_school", {item["feature_id"] for item in broad.selected_features})

        focused_context = SelectionContext(
            center_lat=CENTER_LAT,
            center_lon=CENTER_LON,
            radius_m=50_000,
            title="凤凰实验学校暴雨场景",
            simulation_requirement="重点分析凤凰实验学校",
            admin_context={},
        )
        focused = select_spatial_features(candidates, context=focused_context, limit=3)

        self.assertEqual(focused.selected_features[0]["feature_id"], "site_school")

    def test_failed_public_sources_report_partial_and_gazetteer_is_fallback(self):
        local_only = [
            make_feature(
                "local_shenzhen_bay",
                "深圳湾",
                lat=22.49,
                lon=113.99,
                source_kind="observed",
                provider="local_geographic_gazetteer",
            )
        ]

        summary = summarize_source_status(
            overpass_status={"status": "failed", "error": "timeout"},
            worldcover_status={"status": "failed", "error": "upstream unavailable"},
            features=local_only,
        )

        self.assertEqual(summary["status"], "unavailable")
        self.assertFalse(summary["public_observation_available"])
        self.assertEqual(summary["public_observation_feature_count"], 0)
        self.assertEqual(summary["fallback_feature_count"], 1)
        self.assertIn("local_geographic_gazetteer", summary["fallback_providers"])
        self.assertTrue(summary["warning"])
        self.assertFalse(summary["formal_ready"])
        self.assertFalse(summary["availability"]["available"])
        self.assertTrue(summary["availability"]["retryable"])
        self.assertEqual(summary["availability"]["reason_code"], "timeout")
        self.assertEqual(
            {item["provider"] for item in summary["provider_failures"]},
            {"osm_overpass", "worldcover_wms"},
        )

    def test_overpass_uses_bounded_thematic_batches_with_per_batch_diagnostics(self):
        manager = MapSeedManager()
        manager._llm_client = None
        calls = []

        def fake_overpass(_url, **kwargs):
            query = str(kwargs.get("data") or "")
            calls.append(query)
            if '[boundary="administrative"]' in query:
                return {
                    "elements": [
                        {
                            "type": "relation",
                            "id": 1,
                            "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
                            "tags": {
                                "name": "测试行政区",
                                "boundary": "administrative",
                                "admin_level": "8",
                            },
                        }
                    ]
                }
            return {"elements": []}

        with tempfile.TemporaryDirectory() as cache_dir:
            manager.SOURCE_CACHE_DIR = cache_dir
            with patch.object(Config, "OVERPASS_ENDPOINTS", ["https://example.test/interpreter"]), patch.object(
                Config,
                "OVERPASS_MAXSIZE_BYTES",
                64 * 1024 * 1024,
            ), patch(
                "app.services.map_seed_manager._safe_http_json",
                side_effect=fake_overpass,
            ):
                features, status = manager._collect_spatial_features(
                    CENTER_LAT,
                    CENTER_LON,
                    37_500,
                )

        self.assertEqual(len(calls), 2)
        self.assertTrue(all("[maxsize:67108864]" in query for query in calls))
        self.assertTrue(all(query.count("out center tags") == 1 for query in calls))
        self.assertEqual(status["query_strategy"], "thematic_batches")
        self.assertEqual(status["successful_batch_count"], 2)
        self.assertEqual(status["failed_batch_count"], 0)
        self.assertTrue(status["batch_coverage"]["complete"])
        self.assertEqual(status["category_coverage"]["coverage_ratio"], 1.0)
        self.assertEqual({item["batch"] for item in status["batches"]}, {
            "administrative",
            "regional_boundaries",
        })
        self.assertEqual(features[0]["name"], "测试行政区")

    def test_public_skeleton_is_not_formal_when_required_categories_are_missing(self):
        public_admin = make_feature(
            "public_admin",
            "公开行政区",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            category="region",
            subtype="admin_district",
            spatial_level="district",
            provider="osm_overpass",
        )
        summary = summarize_source_status(
            overpass_status={
                "status": "partial",
                "provider": "osm_overpass",
                "error": "public facilities timeout",
                "category_coverage": {
                    "required_categories": [
                        "administrative",
                        "water_ecology",
                        "settlement_landuse",
                        "public_facilities",
                        "critical_infrastructure",
                        "service_hubs",
                        "transport",
                    ],
                    "covered_categories": ["administrative"],
                    "missing_categories": [
                        "water_ecology",
                        "settlement_landuse",
                        "public_facilities",
                        "critical_infrastructure",
                        "service_hubs",
                        "transport",
                    ],
                    "complete": False,
                },
            },
            worldcover_status={"status": "failed"},
            features=[public_admin],
        )

        self.assertTrue(summary["skeleton_ready"])
        self.assertFalse(summary["formal_ready"])
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(
            summary["availability"]["reason_code"],
            "required_spatial_categories_incomplete",
        )
        self.assertEqual(
            summary["required_category_coverage"]["missing_categories"],
            [
                "water_ecology",
                "settlement_landuse",
                "public_facilities",
                "critical_infrastructure",
                "service_hubs",
                "transport",
            ],
        )
        self.assertEqual(summary["readiness"]["skeleton_ready"], True)

    def test_filtered_out_public_site_cannot_make_selected_reference_skeleton_formal(self):
        candidates = [
            make_feature(
                "public_site",
                "未点名的小型学校",
                lat=CENTER_LAT + 0.01,
                lon=CENTER_LON,
                category="facility",
                subtype="school",
                spatial_level="site",
                provider="osm_overpass",
            ),
            make_feature(
                "reference_region",
                "珠江口参考区域",
                lat=CENTER_LAT - 0.05,
                lon=CENTER_LON,
                category="region",
                subtype="coastline",
                spatial_level="region",
                source_kind="reference",
                provider="local_geographic_gazetteer",
            ),
        ]
        result = select_spatial_features(
            candidates,
            context=SelectionContext(
                center_lat=CENTER_LAT,
                center_lon=CENTER_LON,
                radius_m=50_000,
                simulation_requirement="评估选定区域综合风险",
            ),
            limit=4,
        )
        summary = summarize_source_status(
            overpass_status={"status": "completed", "feature_count": 1},
            worldcover_status={"status": "failed"},
            features=result.selected_features,
        )

        self.assertEqual([item["feature_id"] for item in result.selected_features], ["reference_region"])
        self.assertFalse(summary["formal_ready"])
        self.assertTrue(summary["warning"])

    def test_reference_source_never_becomes_formal_even_with_public_provider_label(self):
        mislabeled_reference = make_feature(
            "reference_osm",
            "历史参考点",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            source_kind="reference",
            provider="osm_overpass",
        )
        summary = summarize_source_status(
            overpass_status={"status": "completed"},
            worldcover_status={"status": "failed"},
            features=[mislabeled_reference],
        )

        self.assertFalse(summary["formal_ready"])
        self.assertEqual(summary["fallback_feature_count"], 1)

    def test_vulnerable_group_cannot_anchor_to_weather_without_population_evidence(self):
        weather = make_feature(
            "context_weather_baseline",
            "局地天气基线",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            subtype="weather_baseline",
            provider="open-meteo",
        )
        residential = make_feature(
            "residential_neighbourhood",
            "南沙居民社区",
            lat=CENTER_LAT + 0.01,
            lon=CENTER_LON + 0.01,
            category="facility",
            subtype="residential",
            provider="overpass",
            tags={"population_evidence": True},
        )

        self.assertFalse(is_valid_proxy_anchor("vulnerable_groups", weather))
        self.assertTrue(is_valid_proxy_anchor("vulnerable_groups", residential))

    def test_weather_only_proxy_has_no_fake_center_coordinate(self):
        manager = MapSeedManager()
        manager._llm_client = None
        weather_node = manager._make_graph_node(
            node_id="feature_weather",
            name="局地天气基线",
            label="EnvironmentalCarrier",
            summary="weather",
            lat=CENTER_LAT,
            lon=CENTER_LON,
            source_kind="observed",
            confidence=0.8,
            attributes={
                "category": "ecology",
                "subtype": "weather_baseline",
                "tags": {"provider": "open-meteo"},
            },
        )

        proxies, _edges = manager._build_human_proxy_nodes(
            seed={"seed_id": "test"},
            admin_context={"city": "测试市"},
            scene_classification={"primary_scene": "mixed"},
            feature_nodes=[weather_node],
            center={"lat": CENTER_LAT, "lon": CENTER_LON},
        )
        vulnerable = next(
            node for node in proxies if node["attributes"].get("proxy_role") == "vulnerable_groups"
        )

        self.assertIsNone(vulnerable["attributes"].get("lat"))
        self.assertIsNone(vulnerable["attributes"].get("lon"))
        self.assertEqual(vulnerable["attributes"].get("spatial_precision"), "area_only")
        regulator = next(
            node for node in proxies if node["attributes"].get("proxy_role") == "regulators"
        )
        self.assertIsNone(regulator["attributes"].get("lat"))
        self.assertIsNone(regulator["attributes"].get("lon"))


if __name__ == "__main__":
    unittest.main()
