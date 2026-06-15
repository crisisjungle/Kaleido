import json
from pathlib import Path

from app.config import Config
from app.models.project import ProjectManager
from app.services.golden_case_service import GoldenCaseService, WUHAN_ARTIFACT_CONTRACT_VERSION, WUHAN_CASE_ID
from app.services.report_agent import ReportManager
from app.services.simulation_manager import SimulationManager


def configure_isolated_storage(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(Config, "GOLDEN_RUNS_FOLDER", str(upload_root / "golden_runs"))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations"))
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(upload_root / "reports"))


def test_wuhan_restore_reuses_frozen_handles_by_default(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    first = GoldenCaseService.restore_case(WUHAN_CASE_ID)
    second = GoldenCaseService.restore_case(WUHAN_CASE_ID)

    assert first["demo_mode"] == "frozen_replay"
    assert first["reused"] is False
    assert second["reused"] is True
    assert second["project_id"] == first["project_id"]
    assert second["simulation_id"] == first["simulation_id"]
    assert second["report_id"] == first["report_id"]
    assert second["route"]["name"] == "Simulation"
    assert second["playback_route"]["name"] == "SimulationRun"
    assert second["route"]["query"]["replay"] == "1"


def test_wuhan_restore_can_create_fresh_handle(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    first = GoldenCaseService.restore_case(WUHAN_CASE_ID)
    fresh = GoldenCaseService.restore_case(WUHAN_CASE_ID, reuse=False)

    assert fresh["reused"] is False
    assert fresh["project_id"] != first["project_id"]
    assert fresh["simulation_id"] != first["simulation_id"]
    assert fresh["report_id"] != first["report_id"]


def test_wuhan_scaffold_refreshes_stale_artifact_contract(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    manifest_path = Path(GoldenCaseService.case_root(WUHAN_CASE_ID)) / "manifest.json"
    assert manifest["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION

    stale = dict(manifest)
    stale["artifact_contract_version"] = "old-contract"
    manifest_path.write_text(json.dumps(stale, ensure_ascii=False, indent=2), encoding="utf-8")

    refreshed = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)

    assert refreshed["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["artifact_contract_version"] == WUHAN_ARTIFACT_CONTRACT_VERSION


def test_wuhan_fixture_uses_non_template_map_layout(monkeypatch, tmp_path):
    configure_isolated_storage(monkeypatch, tmp_path)

    GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    root = Path(GoldenCaseService.case_root(WUHAN_CASE_ID))
    regions = json.loads((root / "simulation" / "region_graph_snapshot.json").read_text(encoding="utf-8"))
    subregions = json.loads((root / "simulation" / "subregion_graph_snapshot.json").read_text(encoding="utf-8"))
    profiles = json.loads((root / "simulation" / "profiles_full.json").read_text(encoding="utf-8"))

    regions_by_id = {item["region_id"]: item for item in regions}
    offset_signatures = []
    for item in subregions[:12]:
        parent = regions_by_id[item["parent_region_id"]]
        offset_signatures.append(
            (
                round(item["lat"] - parent["lat"], 4),
                round(item["lon"] - parent["lon"], 4),
            )
        )

    assert len(set(offset_signatures)) > 8
    assert all(profile.get("lat") and profile.get("lon") for profile in profiles[:30])
