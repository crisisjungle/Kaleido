import os
import shutil
import tempfile
import unittest

from app import create_app
from app.models.project import ProjectManager, ProjectStatus
from app.models.task import TaskManager, TaskStatus
from app.services.map_seed_manager import MapSeedManager
from app.services.report_agent import ReportManager
from app.services.simulation_manager import SimulationManager, SimulationStatus
from app.services.startup_recovery import recover_interrupted_tasks
from app.utils.atomic_file import read_json_file, write_json_file


class StabilityFoundationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="kaleido_stability_")

        self._orig_projects_dir = ProjectManager.PROJECTS_DIR
        self._orig_tasks_dir = TaskManager.TASKS_DIR
        self._orig_sim_dir = SimulationManager.SIMULATION_DATA_DIR
        self._orig_seed_dir = MapSeedManager.MAP_SEEDS_DIR
        self._orig_reports_dir = ReportManager.REPORTS_DIR

        ProjectManager.PROJECTS_DIR = os.path.join(self.temp_dir, "projects")
        TaskManager.TASKS_DIR = os.path.join(self.temp_dir, "tasks")
        SimulationManager.SIMULATION_DATA_DIR = os.path.join(self.temp_dir, "simulations")
        MapSeedManager.MAP_SEEDS_DIR = os.path.join(self.temp_dir, "map_seeds")
        ReportManager.REPORTS_DIR = os.path.join(self.temp_dir, "reports")

    def tearDown(self):
        ProjectManager.PROJECTS_DIR = self._orig_projects_dir
        TaskManager.TASKS_DIR = self._orig_tasks_dir
        SimulationManager.SIMULATION_DATA_DIR = self._orig_sim_dir
        MapSeedManager.MAP_SEEDS_DIR = self._orig_seed_dir
        ReportManager.REPORTS_DIR = self._orig_reports_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_atomic_json_read_write_and_default(self):
        path = os.path.join(self.temp_dir, "state", "payload.json")
        write_json_file(path, {"ok": True, "items": [1, 2]})

        self.assertEqual(read_json_file(path), {"ok": True, "items": [1, 2]})
        self.assertEqual(read_json_file(os.path.join(self.temp_dir, "missing.json"), default={}), {})

        broken_path = os.path.join(self.temp_dir, "broken.json")
        with open(broken_path, "w", encoding="utf-8") as handle:
            handle.write("{")
        self.assertEqual(read_json_file(broken_path, default=[]), [])

    def test_task_manager_lifecycle_methods(self):
        manager = TaskManager()
        task_id = manager.create_task("稳定性测试", task_type="stability")

        manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=40)
        manager.complete_task(task_id, {"done": True})
        completed = manager.get_task(task_id)
        self.assertEqual(completed.status, TaskStatus.COMPLETED)
        self.assertEqual(completed.progress, 100)
        self.assertEqual(completed.result, {"done": True})

        failed_id = manager.create_task("失败测试")
        manager.fail_task(failed_id, "boom")
        self.assertEqual(manager.get_task(failed_id).status, TaskStatus.FAILED)

        cancelled_id = manager.create_task("取消测试")
        manager.cancel_task(cancelled_id, "stop")
        self.assertEqual(manager.get_task(cancelled_id).status, TaskStatus.CANCELLED)

    def test_startup_recovery_marks_interrupted_project_and_simulation(self):
        task_manager = TaskManager()
        graph_task_id = task_manager.create_task("图谱构建", task_type="graph_build")
        task_manager.update_task(graph_task_id, status=TaskStatus.PROCESSING)

        project = ProjectManager.create_project("恢复测试项目")
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = graph_task_id
        ProjectManager.save_project(project)

        simulation = SimulationManager().create_simulation(
            project_id=project.project_id,
            graph_id="graph_for_recovery",
        )
        simulation.status = SimulationStatus.PREPARING
        SimulationManager()._save_simulation_state(simulation)
        sim_task_id = task_manager.create_task(
            "模拟准备",
            task_type="simulation_prepare",
            metadata={"simulation_id": simulation.simulation_id},
        )
        task_manager.update_task(sim_task_id, status=TaskStatus.PROCESSING)

        recovered = recover_interrupted_tasks(reason="restart")

        self.assertEqual(len(recovered), 2)
        self.assertEqual(task_manager.get_task(graph_task_id).status, TaskStatus.FAILED)
        self.assertEqual(ProjectManager.get_project(project.project_id).status, ProjectStatus.FAILED)
        self.assertEqual(SimulationManager().get_simulation(simulation.simulation_id).status, SimulationStatus.STOPPED)

    def test_health_and_task_status_endpoint(self):
        app = create_app()
        client = app.test_client()

        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["status"], "ok")

        task_id = TaskManager().create_task("接口任务")
        response = client.get(f"/api/graph/task/{task_id}")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["task_id"], task_id)

    def test_simulation_state_create_and_read_without_external_services(self):
        state = SimulationManager().create_simulation(
            project_id="proj_local",
            graph_id="graph_local",
            diffusion_template="marine",
            configured_total_rounds=8,
        )

        loaded = SimulationManager().get_simulation(state.simulation_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.project_id, "proj_local")
        self.assertEqual(loaded.graph_id, "graph_local")
        self.assertEqual(loaded.status, SimulationStatus.CREATED)


if __name__ == "__main__":
    unittest.main()
