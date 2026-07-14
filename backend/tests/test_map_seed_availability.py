import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from app.models.task import TaskManager, TaskStatus
from app.services.map_seed_manager import MapSeedManager


class MapSeedAvailabilityContractTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kaleido_map_availability_")
        self.original_seed_dir = MapSeedManager.MAP_SEEDS_DIR
        self.original_cache_dir = MapSeedManager.SOURCE_CACHE_DIR
        self.original_task_dir = TaskManager.TASKS_DIR
        MapSeedManager.MAP_SEEDS_DIR = os.path.join(self.temp_dir, "map_seeds")
        MapSeedManager.SOURCE_CACHE_DIR = os.path.join(self.temp_dir, "map_cache")
        TaskManager.TASKS_DIR = os.path.join(self.temp_dir, "tasks")

    def tearDown(self):
        MapSeedManager.MAP_SEEDS_DIR = self.original_seed_dir
        MapSeedManager.SOURCE_CACHE_DIR = self.original_cache_dir
        TaskManager.TASKS_DIR = self.original_task_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _build_unavailable_seed(self):
        manager = MapSeedManager()
        manager._llm_client = None
        seed = manager.create_seed(
            lat=25.107477,
            lon=121.552734,
            radius_m=37_500,
            requested_location="臺北市士林區",
        )
        overpass_status = {
            "status": "failed",
            "provider": "osm_overpass",
            "error": "The read operation timed out",
            "attempts": [
                {
                    "batch": "administrative",
                    "endpoint": "https://overpass.example/api/interpreter",
                    "status": "failed",
                    "error": "The read operation timed out",
                }
            ],
            "batches": [
                {
                    "batch": "administrative",
                    "status": "failed",
                    "error": "The read operation timed out",
                }
            ],
        }
        worldcover_status = {
            "status": "failed",
            "provider": "worldcover_wms",
            "analysis_grade": "contextual_only",
            "error": "Remote end closed connection without response",
        }

        with patch.object(manager, "_reverse_geocode", return_value={"city": "臺北市", "district": "士林區"}), patch.object(
            manager,
            "_build_area_of_interest",
            return_value={
                "center": {"lat": 25.107477, "lon": 121.552734},
                "radius_m": 37_500,
                "label": "臺北市士林區周边",
            },
        ), patch.object(
            manager,
            "_collect_spatial_features",
            return_value=([], overpass_status),
        ), patch.object(
            manager,
            "_collect_worldcover_features",
            return_value=([], worldcover_status, []),
        ), patch.object(manager, "_local_curated_features", return_value=[]), patch.object(
            manager,
            "_build_environment_baseline",
            return_value={},
        ), patch.object(manager, "_merge_context_features", return_value=[]), patch.object(
            manager,
            "_filter_features_to_aoi",
            return_value=[],
        ), patch.object(
            manager,
            "_classify_scene",
            return_value={"primary_scene": "mixed"},
        ), patch.object(
            manager,
            "_build_graph",
            return_value={"graph_data": {"nodes": [], "edges": []}, "stats": {}},
        ), patch.object(manager, "_build_report", return_value="仅用于失败诊断。"), patch.object(
            manager,
            "_build_layers_payload",
            return_value={"layers": []},
        ), patch.object(
            manager,
            "_build_summary",
            return_value={"title": "士林区空间分析", "summary": "正式地理数据不可用"},
        ):
            result = manager.build_seed(seed["seed_id"])
        return manager, result

    def test_build_without_formal_observations_is_unavailable_not_ready(self):
        manager, result = self._build_unavailable_seed()

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["data_quality"]["formal_ready"])
        self.assertFalse(result["availability"]["available"])
        self.assertTrue(result["availability"]["retryable"])
        self.assertEqual(result["availability"]["reason_code"], "timeout")
        self.assertEqual(
            result["availability"]["provider_failures"][0]["batches"][0]["batch"],
            "administrative",
        )
        self.assertFalse(manager.is_formal_seed_ready(result))

    def test_unavailable_artifacts_are_diagnostic_only_and_cannot_create_project(self):
        manager, result = self._build_unavailable_seed()
        seed_id = result["seed_id"]

        self.assertIsNone(manager.get_graph_snapshot(seed_id))
        self.assertIsNone(manager.get_layers(seed_id))
        self.assertEqual(manager.get_report_text(seed_id), "")
        self.assertIsNotNone(manager.get_graph_snapshot(seed_id, allow_unavailable=True))
        self.assertIsNotNone(manager.get_layers(seed_id, allow_unavailable=True))
        self.assertEqual(manager.get_report_text(seed_id, allow_unavailable=True), "仅用于失败诊断。")
        with self.assertRaisesRegex(ValueError, "没有可用于正式分析"):
            manager.create_project_from_seed(seed_id)

    def test_status_api_normalizes_legacy_ready_without_formal_data_to_unavailable(self):
        seed = MapSeedManager.create_seed(lat=25.1, lon=121.5, radius_m=37_500)
        MapSeedManager.update_seed(
            seed["seed_id"],
            status="ready",
            data_quality={
                "status": "unavailable",
                "formal_ready": False,
                "retryable": True,
                "reason_code": "timeout",
                "provider_failures": [],
                "providers": {
                    "overpass": {
                        "status": "failed",
                        "provider": "osm_overpass",
                        "error": "The read operation timed out",
                    },
                    "worldcover": {
                        "status": "failed",
                        "provider": "worldcover_wms",
                        "error": "Remote end closed connection without response",
                    },
                },
            },
        )
        client = create_app().test_client()

        response = client.post("/api/map/seed/status", json={"seed_id": seed["seed_id"]})
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["status"], "unavailable")
        self.assertFalse(payload["data"]["available"])
        self.assertTrue(payload["data"]["retryable"])
        self.assertEqual(payload["data"]["reason_code"], "timeout")
        self.assertEqual(
            {item["provider"] for item in payload["data"]["availability"]["provider_failures"]},
            {"osm_overpass", "worldcover_wms"},
        )

        conversion = client.post(f"/api/map/seed/{seed['seed_id']}/to-simulation")
        conversion_payload = conversion.get_json()
        self.assertEqual(conversion.status_code, 409)
        self.assertFalse(conversion_payload["success"])
        self.assertEqual(conversion_payload["code"], "formal_spatial_data_unavailable")

    def test_async_task_is_failed_when_seed_result_is_unavailable(self):
        unavailable_result = {
            "seed_id": "placeholder",
            "status": "unavailable",
            "summary": "正式地理数据不可用",
            "data_quality": {
                "status": "unavailable",
                "formal_ready": False,
                "availability": {
                    "status": "unavailable",
                    "available": False,
                    "retryable": True,
                    "reason_code": "timeout",
                    "message": "正式地理数据暂时不可用，可以重新获取。",
                    "provider_failures": [],
                },
            },
            "selection_summary": {},
        }

        def run_inline(_executor, *, task_id, target, **_kwargs):
            del task_id
            target()
            return None

        def fake_build(_manager, seed_id, *, progress_callback=None):
            del progress_callback
            return {**unavailable_result, "seed_id": seed_id}

        client = create_app().test_client()
        with patch("app.api.map_seed.TaskExecutor.start", new=run_inline), patch.object(
            MapSeedManager,
            "build_seed",
            new=fake_build,
        ):
            response = client.post(
                "/api/map/seed",
                json={"lat": 25.1, "lon": 121.5, "radius_m": 37_500},
            )

        payload = response.get_json()
        task = TaskManager().get_task(payload["data"]["task_id"])
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(task.progress, 100)
        self.assertEqual(task.result["status"], "unavailable")
        self.assertTrue(task.result["availability"]["retryable"])


if __name__ == "__main__":
    unittest.main()
