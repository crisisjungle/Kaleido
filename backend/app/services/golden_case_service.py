"""
Golden case registry, scaffold builder, and frozen artifact restore.
"""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..utils.logger import get_logger
from .envfish_models import normalize_time_plan
from .report_agent import Report, ReportManager, ReportOutline, ReportSection, ReportStatus
from .simulation_manager import SimulationManager, SimulationStatus

logger = get_logger("envfish.golden_case")

WUHAN_CASE_ID = "wuhan_covid_v1"
WUHAN_REFERENCE_TIME = "2019-12-22T00:00:00+08:00"
WUHAN_TOTAL_ROUNDS = 36
WUHAN_MINUTES_PER_ROUND = 4320


@dataclass(frozen=True)
class GoldenCaseDefinition:
    case_id: str
    title: str
    summary: str
    profile: str
    scenario_mode: str
    hazard_template_id: str
    diffusion_template: str
    search_mode: str
    reference_time: str
    step_unit: str
    step_size: int
    total_rounds: int
    target_node_count: int
    target_agent_count: int
    report_title: str


WUHAN_CASE = GoldenCaseDefinition(
    case_id=WUHAN_CASE_ID,
    title="武汉疫情推演演示",
    summary="固定武汉疫情背景的黄金演示案例，用于冻结回放、动画和后续流程调试。",
    profile=WUHAN_CASE_ID,
    scenario_mode="crisis_mode",
    hazard_template_id="pest_disease_ecology",
    diffusion_template="bio_ecological_transmission",
    search_mode="deep_search",
    reference_time=WUHAN_REFERENCE_TIME,
    step_unit="day",
    step_size=3,
    total_rounds=WUHAN_TOTAL_ROUNDS,
    target_node_count=200,
    target_agent_count=240,
    report_title="武汉疫情黄金案例推演报告",
)


class GoldenCaseService:
    CASES: Dict[str, GoldenCaseDefinition] = {WUHAN_CASE.case_id: WUHAN_CASE}

    @classmethod
    def list_cases(cls) -> List[Dict[str, Any]]:
        items = []
        for definition in cls.CASES.values():
            manifest = cls.load_manifest(definition.case_id)
            items.append(
                {
                    "case_id": definition.case_id,
                    "title": definition.title,
                    "summary": definition.summary,
                    "profile": definition.profile,
                    "scenario_mode": definition.scenario_mode,
                    "hazard_template_id": definition.hazard_template_id,
                    "diffusion_template": definition.diffusion_template,
                    "search_mode": definition.search_mode,
                    "reference_time": definition.reference_time,
                    "step_unit": definition.step_unit,
                    "step_size": definition.step_size,
                    "total_rounds": definition.total_rounds,
                    "target_node_count": definition.target_node_count,
                    "target_agent_count": definition.target_agent_count,
                    "artifact_ready": bool(manifest),
                }
            )
        return items

    @classmethod
    def get_case(cls, case_id: str) -> GoldenCaseDefinition:
        definition = cls.CASES.get(case_id)
        if not definition:
            raise ValueError(f"Golden case not found: {case_id}")
        return definition

    @classmethod
    def case_root(cls, case_id: str) -> str:
        return os.path.join(Config.GOLDEN_RUNS_FOLDER, case_id)

    @classmethod
    def load_manifest(cls, case_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(cls.case_root(case_id), "manifest.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        normalized = cls._normalize_manifest_paths(case_id, manifest)
        if normalized != manifest:
            cls._write_json(path, normalized)
        return normalized

    @classmethod
    def _normalize_manifest_paths(cls, case_id: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
        root = cls.case_root(case_id)
        normalized = dict(manifest or {})
        scene_dir = os.path.join(root, "scene")
        simulation_dir = os.path.join(root, "simulation")
        report_dir = os.path.join(root, "report")
        animation_dir = os.path.join(root, "animation")

        normalized["scene"] = {
            **dict((manifest or {}).get("scene") or {}),
            "dir": scene_dir,
            "scene_seed": os.path.join(scene_dir, "scene_seed.json"),
        }
        normalized["simulation"] = {
            **dict((manifest or {}).get("simulation") or {}),
            "dir": simulation_dir,
            "config": os.path.join(simulation_dir, "simulation_config.json"),
            "latest_snapshot": os.path.join(simulation_dir, "latest_round_snapshot.json"),
        }
        normalized["report"] = {
            **dict((manifest or {}).get("report") or {}),
            "dir": report_dir,
            "markdown": os.path.join(report_dir, "full_report.md"),
            "outline": os.path.join(report_dir, "outline.json"),
        }
        normalized["animation"] = {
            **dict((manifest or {}).get("animation") or {}),
            "dir": animation_dir,
            "file": os.path.join(animation_dir, "animation.json"),
        }
        return normalized

    @classmethod
    def _manifest_is_healthy(cls, manifest: Dict[str, Any]) -> bool:
        required_paths = [
            ((manifest or {}).get("scene") or {}).get("scene_seed"),
            ((manifest or {}).get("simulation") or {}).get("config"),
            ((manifest or {}).get("simulation") or {}).get("latest_snapshot"),
            ((manifest or {}).get("report") or {}).get("markdown"),
            ((manifest or {}).get("report") or {}).get("outline"),
            ((manifest or {}).get("animation") or {}).get("file"),
        ]
        return all(path and os.path.exists(path) for path in required_paths)

    @classmethod
    def ensure_scaffold(cls, case_id: str, *, force: bool = False) -> Dict[str, Any]:
        definition = cls.get_case(case_id)
        root = cls.case_root(case_id)
        manifest_path = os.path.join(root, "manifest.json")
        if not force and os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            normalized = cls._normalize_manifest_paths(case_id, manifest)
            if cls._manifest_is_healthy(normalized):
                if normalized != manifest:
                    cls._write_json(manifest_path, normalized)
                return normalized

        os.makedirs(root, exist_ok=True)
        scene_dir = os.path.join(root, "scene")
        simulation_dir = os.path.join(root, "simulation")
        report_dir = os.path.join(root, "report")
        animation_dir = os.path.join(root, "animation")
        for directory in (scene_dir, simulation_dir, report_dir, animation_dir):
            os.makedirs(directory, exist_ok=True)

        region_graph = cls._build_regions()
        subregion_graph = cls._build_subregions(region_graph)
        profiles = cls._build_profiles(region_graph, subregion_graph)
        relationships = cls._build_relationships(profiles, region_graph, subregion_graph)
        transport_edges = cls._build_transport_edges(region_graph)
        risk_bundle = cls._build_risk_bundle(region_graph)
        round_snapshots = cls._build_round_snapshots(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
            profiles=profiles,
            relationships=relationships,
        )
        latest_snapshot = round_snapshots[-1] if round_snapshots else {}
        interaction_rows = cls._build_interactions(profiles, subregion_graph)
        dynamic_edges = cls._build_dynamic_edges(relationships)
        report_outline = cls._build_report_outline()
        report_markdown = cls._build_report_markdown(report_outline)

        simulation_config = cls._build_simulation_config(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
            profiles=profiles,
            relationships=relationships,
            transport_edges=transport_edges,
            risk_bundle=risk_bundle,
        )
        run_state = cls._build_run_state(definition, round_snapshots)
        state_payload = cls._build_state_payload(definition, simulation_config, profiles, region_graph, risk_bundle)
        animation_payload = cls._build_animation_payload(
            definition=definition,
            region_graph=region_graph,
            subregion_graph=subregion_graph,
            profiles=profiles,
            relationships=relationships,
            round_snapshots=round_snapshots,
            interaction_rows=interaction_rows,
            dynamic_edges=dynamic_edges,
            risk_events=risk_bundle["risk_events"],
        )

        cls._write_json(os.path.join(scene_dir, "scene_seed.json"), cls._build_scene_seed(definition))
        cls._write_text(os.path.join(scene_dir, "scene_report.md"), cls._build_scene_report())

        cls._write_json(os.path.join(simulation_dir, "state.json"), state_payload)
        cls._write_json(os.path.join(simulation_dir, "run_state.json"), run_state)
        cls._write_json(os.path.join(simulation_dir, "simulation_config.json"), simulation_config)
        cls._write_json(os.path.join(simulation_dir, "region_graph_snapshot.json"), region_graph)
        cls._write_json(os.path.join(simulation_dir, "subregion_graph_snapshot.json"), subregion_graph)
        cls._write_json(os.path.join(simulation_dir, "profiles_full.json"), profiles)
        cls._write_json(os.path.join(simulation_dir, "reddit_profiles.json"), cls._build_reddit_profiles(profiles))
        cls._write_csv(os.path.join(simulation_dir, "twitter_profiles.csv"), cls._build_twitter_profiles(profiles))
        cls._write_json(os.path.join(simulation_dir, "agent_relationship_graph.json"), relationships)
        cls._write_json(os.path.join(simulation_dir, "transport_edges.json"), transport_edges)
        cls._write_json(os.path.join(simulation_dir, "transport_edges_snapshot.json"), transport_edges)
        cls._write_json(os.path.join(simulation_dir, "grounding_summary.json"), cls._build_grounding_summary(region_graph))
        cls._write_json(os.path.join(simulation_dir, "diffusion_context.json"), cls._build_diffusion_context(definition))
        cls._write_json(os.path.join(simulation_dir, "region_agent_index.json"), cls._build_region_agent_index(region_graph, subregion_graph, profiles))
        cls._write_json(os.path.join(simulation_dir, "agent_generation_summary.json"), cls._build_agent_generation_summary(profiles))
        cls._write_json(os.path.join(simulation_dir, "injected_variables.json"), [])
        cls._write_json(os.path.join(simulation_dir, "latest_round_snapshot.json"), latest_snapshot)
        cls._write_json(os.path.join(simulation_dir, "risk_definitions.json"), risk_bundle["risk_definitions"])
        cls._write_json(os.path.join(simulation_dir, "risk_objects.json"), risk_bundle["risk_objects"])
        cls._write_json(os.path.join(simulation_dir, "risk_object_summary.json"), risk_bundle["risk_objects_summary"])
        cls._write_json(os.path.join(simulation_dir, "latest_risk_runtime_state.json"), risk_bundle["latest_risk_runtime_state"])
        cls._write_json(os.path.join(simulation_dir, "env_status.json"), {"status": "replay_only", "twitter_available": False, "reddit_available": False})
        cls._write_jsonl(os.path.join(simulation_dir, "round_state_matrix.jsonl"), round_snapshots)
        cls._write_jsonl(os.path.join(simulation_dir, "risk_runtime_state.jsonl"), risk_bundle["risk_runtime_history"])
        cls._write_jsonl(os.path.join(simulation_dir, "risk_events.jsonl"), risk_bundle["risk_events"])
        cls._write_jsonl(os.path.join(simulation_dir, "agent_interaction_ledger.jsonl"), interaction_rows)
        cls._write_jsonl(os.path.join(simulation_dir, "dynamic_edge_ledger.jsonl"), dynamic_edges)
        cls._write_jsonl(os.path.join(simulation_dir, "intervention_log.jsonl"), [])
        cls._write_text(os.path.join(simulation_dir, "simulation.log"), "Replay-only scaffold for Wuhan golden case.\n")

        cls._write_json(os.path.join(report_dir, "outline.json"), report_outline)
        cls._write_text(os.path.join(report_dir, "full_report.md"), report_markdown)
        cls._write_json(
            os.path.join(report_dir, "progress.json"),
            {
                "status": "completed",
                "progress": 100,
                "message": "Frozen replay report is ready.",
                "completed_sections": [section["title"] for section in report_outline["sections"]],
                "updated_at": datetime.now().isoformat(),
            },
        )
        cls._write_json(os.path.join(report_dir, "meta.json"), cls._build_report_meta(definition))
        cls._write_jsonl(os.path.join(report_dir, "agent_log.jsonl"), cls._build_report_agent_log())
        cls._write_text(os.path.join(report_dir, "console_log.txt"), "Replay-only report loaded from golden artifacts.\n")

        cls._write_json(os.path.join(animation_dir, "animation.json"), animation_payload)
        cls._write_json(os.path.join(simulation_dir, "animation.json"), animation_payload)

        manifest = {
            "case_id": definition.case_id,
            "title": definition.title,
            "summary": definition.summary,
            "profile": definition.profile,
            "scenario_mode": definition.scenario_mode,
            "hazard_template_id": definition.hazard_template_id,
            "diffusion_template": definition.diffusion_template,
            "search_mode": definition.search_mode,
            "reference_time": definition.reference_time,
            "step_unit": definition.step_unit,
            "step_size": definition.step_size,
            "total_rounds": definition.total_rounds,
            "target_node_count": definition.target_node_count,
            "target_agent_count": definition.target_agent_count,
            "scene": {
                "dir": scene_dir,
                "scene_seed": os.path.join(scene_dir, "scene_seed.json"),
            },
            "simulation": {
                "dir": simulation_dir,
                "config": os.path.join(simulation_dir, "simulation_config.json"),
                "latest_snapshot": os.path.join(simulation_dir, "latest_round_snapshot.json"),
            },
            "report": {
                "dir": report_dir,
                "markdown": os.path.join(report_dir, "full_report.md"),
                "outline": os.path.join(report_dir, "outline.json"),
            },
            "animation": {
                "dir": animation_dir,
                "file": os.path.join(animation_dir, "animation.json"),
            },
            "generated_at": datetime.now().isoformat(),
        }
        cls._write_json(manifest_path, manifest)
        return manifest

    @classmethod
    def restore_case(cls, case_id: str) -> Dict[str, Any]:
        definition = cls.get_case(case_id)
        manifest = cls.ensure_scaffold(case_id)

        project = ProjectManager.create_project(name=definition.title)
        project.status = ProjectStatus.GRAPH_COMPLETED
        project.graph_id = f"golden_graph::{case_id}"
        project.simulation_requirement = cls._simulation_requirement()
        ProjectManager.save_project(project)
        ProjectManager.save_extracted_text(project.project_id, cls._background_text())

        manager = SimulationManager()
        time_plan = normalize_time_plan(
            {
                "step_unit": definition.step_unit,
                "step_size": definition.step_size,
                "total_rounds": definition.total_rounds,
                "reference_time": definition.reference_time,
                "reasoning_summary": "Frozen Wuhan COVID-19 golden replay timeline.",
                "source": "golden_case_restore",
            },
            total_rounds=definition.total_rounds,
            minutes_per_round=WUHAN_MINUTES_PER_ROUND,
            preset="slow",
            reference_time=definition.reference_time,
            source="golden_case_restore",
        )
        simulation_state = manager.create_simulation(
            project_id=project.project_id,
            graph_id=project.graph_id or "",
            engine_mode="envfish",
            scenario_mode=definition.scenario_mode,
            diffusion_template=definition.diffusion_template,
            hazard_template_id=definition.hazard_template_id,
            search_mode=definition.search_mode,
            temporal_preset="slow",
            configured_total_rounds=definition.total_rounds,
            configured_minutes_per_round=WUHAN_MINUTES_PER_ROUND,
            time_plan_mode="manual",
            time_plan=time_plan,
            reference_time=definition.reference_time,
            diffusion_provider="heuristic",
            source_mode="golden_case",
            artifact_mode="frozen",
            artifact_root=manifest["simulation"]["dir"],
            golden_case_id=case_id,
            golden_case_profile=definition.profile,
            is_replay_only=True,
        )
        simulation_state.status = SimulationStatus.COMPLETED
        simulation_state.config_generated = True
        simulation_state.entities_count = definition.target_node_count
        simulation_state.profiles_count = definition.target_agent_count
        simulation_state.region_count = 12
        simulation_state.risk_objects_count = 3
        manager._save_simulation_state(simulation_state)

        outline_payload = cls._read_json(manifest["report"]["outline"], {})
        outline = ReportOutline(
            title=outline_payload.get("title") or definition.report_title,
            summary=outline_payload.get("summary") or definition.summary,
            sections=[ReportSection(title=item.get("title") or "", content=item.get("content") or "") for item in outline_payload.get("sections") or []],
        )
        report = Report(
            report_id=f"report_{datetime.now().strftime('%Y%m%d%H%M%S%f')[-12:]}",
            simulation_id=simulation_state.simulation_id,
            graph_id=project.graph_id or "",
            simulation_requirement=project.simulation_requirement or "",
            status=ReportStatus.COMPLETED,
            outline=outline,
            created_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat(),
            artifact_mode="frozen",
            artifact_root=manifest["report"]["dir"],
            golden_case_id=case_id,
            is_replay_only=True,
        )
        ReportManager.save_report(report)

        return {
            "case_id": case_id,
            "project_id": project.project_id,
            "simulation_id": simulation_state.simulation_id,
            "report_id": report.report_id,
            "next_step": "simulation_run",
            "route": {
                "name": "SimulationRun",
                "params": {"simulationId": simulation_state.simulation_id},
                "query": {
                    "scenario_mode": definition.scenario_mode,
                    "hazard_template_id": definition.hazard_template_id,
                    "diffusion_template": definition.diffusion_template,
                    "search_mode": definition.search_mode,
                    "reference_time": definition.reference_time,
                    "maxRounds": definition.total_rounds,
                    "golden_case_id": case_id,
                    "replay": "1",
                    "report_id": report.report_id,
                },
            },
        }

    @classmethod
    def _build_regions(cls) -> List[Dict[str, Any]]:
        base = [
            ("jianghan_market_corridor", "江汉市场走廊", 30.6035, 114.2705),
            ("jiangan_medical_belt", "江岸医疗带", 30.6358, 114.3097),
            ("qiaokou_supply_link", "硚口供应联络带", 30.5856, 114.2444),
            ("hanyang_river_port", "汉阳沿江物流口", 30.5547, 114.2179),
            ("wuchang_civic_core", "武昌治理核心", 30.5467, 114.3162),
            ("hongshan_university_cluster", "洪山高校群", 30.5151, 114.3663),
            ("qingshan_industrial_ring", "青山工业环", 30.6432, 114.3976),
            ("donghu_public_health", "东湖公共卫生圈", 30.5657, 114.4188),
            ("rail_hub_corridor", "铁路枢纽走廊", 30.6188, 114.3321),
            ("airport_gateway", "空港门户区", 30.7838, 114.2081),
            ("community_care_ring", "社区照护环", 30.5798, 114.2874),
            ("yangtze_bridge_axis", "长江桥梁轴", 30.5554, 114.2871),
        ]
        regions: List[Dict[str, Any]] = []
        for index, (region_id, name, lat, lon) in enumerate(base):
            neighbors = []
            if index > 0:
                neighbors.append(base[index - 1][0])
            if index < len(base) - 1:
                neighbors.append(base[index + 1][0])
            if index in {0, 4, 8} and index + 4 < len(base):
                neighbors.append(base[index + 4][0])
            regions.append(
                {
                    "region_id": region_id,
                    "name": name,
                    "region_type": "urban_core" if index < 8 else "support_belt",
                    "description": f"{name}，围绕医疗、交通、社区与市场活动形成高频接触网络。",
                    "tags": ["urban", "transport", "governance"] if index != 9 else ["transport", "gateway", "open"],
                    "neighbors": neighbors,
                    "layer": "macro",
                    "lat": lat,
                    "lon": lon,
                    "state_vector": {
                        "exposure_score": 22 + index,
                        "spread_pressure": 18 + index,
                        "panic_level": 10 + index // 2,
                        "public_trust": 68 - index,
                        "service_capacity": 76 - index,
                        "response_capacity": 74 - index,
                        "economic_stress": 16 + index,
                        "livelihood_stability": 72 - index,
                        "ecosystem_integrity": 61 - index // 2,
                        "vulnerability_score": 24 + index,
                    },
                }
            )
        return regions

    @classmethod
    def _build_subregions(cls, regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        templates = [
            ("market", "市场接触带", "commercial", "near", 0.010, 0.012),
            ("medical", "医疗承压带", "civic", "mid", -0.012, 0.008),
            ("community", "社区传播带", "residential", "far", 0.008, -0.015),
        ]
        for region in regions:
            for idx, (suffix, label, land_use, distance_band, lat_delta, lon_delta) in enumerate(templates, start=1):
                rows.append(
                    {
                        "region_id": f"{region['region_id']}::{suffix}",
                        "parent_region_id": region["region_id"],
                        "name": f"{region['name']}·{label}",
                        "region_type": label,
                        "land_use_class": land_use,
                        "distance_band": distance_band,
                        "description": f"{region['name']}中的{label}，承接病例发现、就医、物流或社区接触链条。",
                        "layer": "subregion",
                        "tags": [land_use, distance_band, suffix],
                        "lat": round(region["lat"] + lat_delta, 6),
                        "lon": round(region["lon"] + lon_delta, 6),
                        "agent_ids": [],
                    }
                )
        return rows

    @classmethod
    def _build_profiles(cls, regions: List[Dict[str, Any]], subregions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        profiles: List[Dict[str, Any]] = []
        role_templates = [
            ("疾控值守员", "governance", "governmentactor", "疾控协同"),
            ("社区网格员", "human", "humanactor", "社区排查"),
            ("急诊护士", "human", "humanactor", "医疗承压"),
            ("检验技师", "human", "humanactor", "检测链路"),
            ("市场经营者", "human", "humanactor", "市场接触"),
            ("物流调度员", "organization", "organizationactor", "物流调度"),
            ("交通值守员", "organization", "organizationactor", "交通筛查"),
            ("媒体编辑", "organization", "organizationactor", "信息传播"),
            ("医院联络官", "governance", "governmentactor", "医疗统筹"),
            ("社区志愿者", "human", "humanactor", "居民服务"),
            ("药店店长", "organization", "organizationactor", "药品供应"),
            ("物业经理", "organization", "organizationactor", "楼栋治理"),
            ("大学辅导员", "human", "humanactor", "高校管理"),
            ("班车司机", "human", "humanactor", "跨区移动"),
            ("仓储主管", "organization", "organizationactor", "供应链承压"),
            ("热线接线员", "governance", "governmentactor", "舆情响应"),
            ("流调专员", "governance", "governmentactor", "接触链追踪"),
            ("街道办联络员", "governance", "governmentactor", "基层治理"),
            ("实验室管理员", "organization", "organizationactor", "实验资源"),
            ("社区居民代表", "human", "humanactor", "居民感知"),
        ]
        subregions_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for item in subregions:
            subregions_by_parent.setdefault(item["parent_region_id"], []).append(item)
        agent_id = 1
        for region in regions:
            region_subregions = subregions_by_parent.get(region["region_id"], [])
            for index, (role, family, agent_type, motif) in enumerate(role_templates):
                subregion = region_subregions[index % len(region_subregions)]
                profile = {
                    "agent_id": agent_id,
                    "name": f"{region['name']}-{role}-{(index % 4) + 1:02d}",
                    "username": f"wh_{region['region_id']}_{agent_id}",
                    "bio": f"{region['name']}中的{role}，围绕{motif}与周边机构互动。",
                    "persona": f"围绕{motif}维持区域运转并感知疫情扩散。",
                    "agent_type": agent_type,
                    "agent_subtype": role,
                    "role_type": role,
                    "node_family": family,
                    "home_region_id": region["region_id"],
                    "home_subregion_id": subregion["region_id"],
                    "primary_region": region["region_id"],
                    "is_synthesized": True,
                    "source_entity_uuid": f"golden::{agent_id}",
                    "goals": [motif, "控制风险", "维持服务"],
                    "motivation_stack": [motif, "信息同步", "资源协调"],
                    "action_space": ["monitor", "coordinate", "signal", "respond"],
                    "action_space_hint": ["monitor", "coordinate", "signal", "respond"],
                    "state_vector": {
                        "exposure_score": min(95, 20 + (agent_id % 14) * 3),
                        "spread_pressure": min(95, 18 + (agent_id % 11) * 4),
                        "panic_level": 10 + (agent_id % 7) * 4,
                        "public_trust": max(15, 78 - (agent_id % 12) * 3),
                        "service_capacity": max(22, 84 - (agent_id % 10) * 4),
                        "response_capacity": max(22, 80 - (agent_id % 9) * 4),
                        "economic_stress": 8 + (agent_id % 13) * 4,
                        "livelihood_stability": max(16, 80 - (agent_id % 10) * 4),
                        "ecosystem_integrity": max(20, 65 - (agent_id % 8) * 3),
                        "vulnerability_score": min(96, 16 + (agent_id % 15) * 5),
                    },
                    "influenced_regions": [region["region_id"], *(region["neighbors"][:2])],
                }
                profiles.append(profile)
                subregion["agent_ids"].append(agent_id)
                agent_id += 1
        return profiles

    @classmethod
    def _build_relationships(
        cls,
        profiles: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        subregions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_region: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            by_region.setdefault(profile["home_region_id"], []).append(profile)
        subregion_agents: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            subregion_agents.setdefault(profile["home_subregion_id"], []).append(profile)

        rows: List[Dict[str, Any]] = []
        seen = set()

        def add_edge(source: Dict[str, Any], target: Dict[str, Any], relation_type: str, channel: str, strength: float) -> None:
            key = (source["agent_id"], target["agent_id"], relation_type)
            if source["agent_id"] == target["agent_id"] or key in seen:
                return
            seen.add(key)
            rows.append(
                {
                    "edge_id": f"rel::{source['agent_id']}::{target['agent_id']}::{relation_type}",
                    "source_agent_id": source["agent_id"],
                    "target_agent_id": target["agent_id"],
                    "source_region_id": source["home_region_id"],
                    "target_region_id": target["home_region_id"],
                    "relation_type": relation_type,
                    "interaction_channel": channel,
                    "strength": round(strength, 2),
                    "confidence": 0.81,
                    "rationale": f"{source['name']} 与 {target['name']} 围绕 {channel} 形成稳定协作。",
                }
            )

        for region in regions:
            members = by_region.get(region["region_id"], [])
            governance = [item for item in members if item["node_family"] == "governance"]
            medical = [item for item in members if any(token in item["agent_subtype"] for token in ("护士", "检验", "流调", "实验"))]
            community = [item for item in members if any(token in item["agent_subtype"] for token in ("社区", "物业", "居民", "志愿"))]
            logistics = [item for item in members if any(token in item["agent_subtype"] for token in ("物流", "交通", "司机", "仓储"))]
            media = [item for item in members if "媒体" in item["agent_subtype"] or "热线" in item["agent_subtype"]]

            for source in governance:
                for target in medical[:5] + community[:5] + logistics[:4] + media[:2]:
                    add_edge(source, target, "regulates", "governance_hierarchy", 0.72)
            for source in medical:
                for target in community[:3] + logistics[:2]:
                    add_edge(source, target, "supports", "health_response", 0.64)
            for source in logistics:
                for target in medical[:2] + community[:2]:
                    add_edge(source, target, "uses", "supply_chain", 0.58)
            for source in media:
                for target in governance[:2] + community[:3]:
                    add_edge(source, target, "affects", "media_reach", 0.54)

        for subregion_id, members in subregion_agents.items():
            for idx, source in enumerate(members):
                for offset in (1, 2):
                    target = members[(idx + offset) % len(members)]
                    add_edge(source, target, "collaborates_with", "local_contact", 0.49)

        return rows

    @classmethod
    def _build_transport_edges(cls, regions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index, region in enumerate(regions):
            for neighbor in region["neighbors"]:
                rows.append(
                    {
                        "edge_id": f"transport::{region['region_id']}::{neighbor}",
                        "source_region_id": region["region_id"],
                        "target_region_id": neighbor,
                        "channel_type": "mobility_corridor",
                        "directionality": "directed",
                        "attenuation_rate": 0.18,
                        "travel_time_rounds": 1 if index < 8 else 2,
                        "retention_factor": 0.42,
                        "strength": 0.76,
                        "confidence": 0.8,
                        "rationale": f"{region['name']} 与相邻区域存在稳定人员与物资流动。",
                    }
                )
        return rows

    @classmethod
    def _build_round_snapshots(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        snapshots: List[Dict[str, Any]] = []
        for round_num in range(1, definition.total_rounds + 1):
            intensity = cls._wave(round_num, definition.total_rounds)
            regions = []
            for idx, region in enumerate(region_graph):
                base = region["state_vector"]
                escalation = intensity * (1 + idx * 0.03)
                regions.append(
                    {
                        "region_id": region["region_id"],
                        "name": region["name"],
                        "region_type": region["region_type"],
                        "tagline": "病例发现 / 资源调度 / 风险外溢",
                        "exposure_score": cls._clamp(base["exposure_score"] + escalation * 36),
                        "spread_pressure": cls._clamp(base["spread_pressure"] + escalation * 42),
                        "panic_level": cls._clamp(base["panic_level"] + escalation * 44),
                        "public_trust": cls._clamp(base["public_trust"] - escalation * 28),
                        "service_capacity": cls._clamp(base["service_capacity"] - escalation * 26),
                        "response_capacity": cls._clamp(base["response_capacity"] - escalation * 18),
                        "economic_stress": cls._clamp(base["economic_stress"] + escalation * 32),
                        "livelihood_stability": cls._clamp(base["livelihood_stability"] - escalation * 24),
                        "ecosystem_integrity": cls._clamp(base["ecosystem_integrity"] - escalation * 10),
                        "vulnerability_score": cls._clamp(base["vulnerability_score"] + escalation * 38),
                        "severity_band": "high" if escalation > 0.72 else "medium",
                        "uncertainty_band": {"confidence": round(max(0.52, 0.88 - intensity * 0.2), 2)},
                    }
                )

            subregions = []
            for idx, item in enumerate(subregion_graph):
                escalation = intensity * (1 + (idx % 3) * 0.06)
                subregions.append(
                    {
                        "region_id": item["region_id"],
                        "parent_region_id": item["parent_region_id"],
                        "name": item["name"],
                        "region_type": item["region_type"],
                        "land_use_class": item["land_use_class"],
                        "distance_band": item["distance_band"],
                        "agent_ids": item["agent_ids"],
                        "exposure_score": cls._clamp(18 + escalation * 48 + (idx % 5) * 4),
                        "spread_pressure": cls._clamp(16 + escalation * 52 + (idx % 4) * 5),
                        "panic_level": cls._clamp(12 + escalation * 44 + (idx % 3) * 6),
                        "public_trust": cls._clamp(70 - escalation * 30 - (idx % 4) * 2),
                        "service_capacity": cls._clamp(76 - escalation * 28 - (idx % 3) * 3),
                        "response_capacity": cls._clamp(74 - escalation * 22 - (idx % 2) * 3),
                        "economic_stress": cls._clamp(14 + escalation * 36 + (idx % 4) * 4),
                        "livelihood_stability": cls._clamp(74 - escalation * 26 - (idx % 3) * 2),
                        "ecosystem_integrity": cls._clamp(65 - escalation * 12),
                        "vulnerability_score": cls._clamp(22 + escalation * 46 + (idx % 5) * 3),
                    }
                )

            agents = []
            activation_band = min(len(profiles), 48 + round_num * 4)
            for profile in profiles[:activation_band]:
                base = profile["state_vector"]
                role_bonus = 1.15 if profile["node_family"] == "governance" else 1.0
                agents.append(
                    {
                        "agent_id": profile["agent_id"],
                        "name": profile["name"],
                        "agent_type": profile["agent_type"],
                        "agent_subtype": profile["agent_subtype"],
                        "primary_region": profile["primary_region"],
                        "home_subregion_id": profile["home_subregion_id"],
                        "state_vector": {
                            "exposure_score": cls._clamp(base["exposure_score"] + intensity * 26),
                            "spread_pressure": cls._clamp(base["spread_pressure"] + intensity * 30),
                            "panic_level": cls._clamp(base["panic_level"] + intensity * 22),
                            "public_trust": cls._clamp(base["public_trust"] - intensity * 20 * role_bonus),
                            "service_capacity": cls._clamp(base["service_capacity"] - intensity * 16),
                            "response_capacity": cls._clamp(base["response_capacity"] - intensity * 12 + (4 if profile["node_family"] == "governance" else 0)),
                            "economic_stress": cls._clamp(base["economic_stress"] + intensity * 24),
                            "livelihood_stability": cls._clamp(base["livelihood_stability"] - intensity * 18),
                            "ecosystem_integrity": cls._clamp(base["ecosystem_integrity"] - intensity * 8),
                            "vulnerability_score": cls._clamp(base["vulnerability_score"] + intensity * 28),
                        },
                    }
                )

            interactions = cls._build_round_interactions(round_num, relationships, profiles)
            snapshots.append(
                {
                    "round": round_num,
                    "timestamp": (datetime.fromisoformat(definition.reference_time) + timedelta(days=3 * round_num)).isoformat(),
                    "regions": regions,
                    "subregions": subregions,
                    "agents": agents,
                    "interactions": {
                        "agent_interactions": interactions,
                        "agent_environment_effects": interactions[:6],
                    },
                    "agent_summary": {
                        "active_agents": len(agents),
                        "environment_effect_count": len(interactions[:6]),
                    },
                    "feedback": {
                        "feedback_propagation": [
                            {"loop": "环境 → 生态 → 生计 → 恐慌/媒体 → 政策"},
                            {"loop": "市场接触 → 医疗承压 → 社区感知 → 治理加码"},
                        ]
                    },
                    "search_mode": definition.search_mode,
                    "scenario_mode": definition.scenario_mode,
                }
            )
        return snapshots

    @classmethod
    def _build_round_interactions(cls, round_num: int, relationships: List[Dict[str, Any]], profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        sample = relationships[(round_num - 1) * 8: (round_num - 1) * 8 + 10] or relationships[:10]
        profile_by_id = {int(item["agent_id"]): item for item in profiles}
        for idx, rel in enumerate(sample):
            source = profile_by_id.get(int(rel["source_agent_id"]))
            target = profile_by_id.get(int(rel["target_agent_id"]))
            if not source or not target:
                continue
            rows.append(
                {
                    "id": f"interaction::{round_num}::{idx}",
                    "round": round_num,
                    "channel": rel["interaction_channel"],
                    "interaction_channel": rel["interaction_channel"],
                    "source_agent_id": source["agent_id"],
                    "source_agent_name": source["name"],
                    "target_agent_id": target["agent_id"],
                    "target_agent_name": target["name"],
                    "source_region_name": source["home_region_id"],
                    "target_region_name": target["home_region_id"],
                    "action_type": "COORDINATE",
                    "summary": f"{source['name']} 与 {target['name']} 围绕 {rel['interaction_channel']} 协调资源与信息。",
                    "rationale": rel["rationale"],
                    "delta": {"public_trust": -0.4 + idx * 0.05},
                }
            )
        return rows

    @classmethod
    def _build_interactions(cls, profiles: List[Dict[str, Any]], subregions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        profile_by_subregion: Dict[str, List[Dict[str, Any]]] = {}
        for profile in profiles:
            profile_by_subregion.setdefault(profile["home_subregion_id"], []).append(profile)
        for round_num in range(1, WUHAN_TOTAL_ROUNDS + 1):
            for idx, subregion in enumerate(subregions[:12]):
                members = profile_by_subregion.get(subregion["region_id"], [])
                if len(members) < 2:
                    continue
                source = members[(round_num + idx) % len(members)]
                target = members[(round_num + idx + 1) % len(members)]
                rows.append(
                    {
                        "id": f"interaction-ledger::{round_num}::{idx}",
                        "round": round_num,
                        "channel": "local_contact",
                        "source_agent_id": source["agent_id"],
                        "source_agent_name": source["name"],
                        "target_agent_id": target["agent_id"],
                        "target_agent_name": target["name"],
                        "source_region_name": source["home_region_id"],
                        "target_region_name": target["home_region_id"],
                        "action_type": "COORDINATE",
                        "summary": f"{source['name']} 在 {subregion['name']} 与 {target['name']} 交换新的接触线索。",
                        "rationale": "Frozen replay interaction ledger for animation.",
                        "delta": {"vulnerability_score": round(0.2 + idx * 0.03, 2)},
                    }
                )
        return rows

    @classmethod
    def _build_dynamic_edges(cls, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        sample = relationships[: WUHAN_TOTAL_ROUNDS * 6]
        for idx, rel in enumerate(sample):
            round_num = idx // 6 + 1
            rows.append(
                {
                    "edge_id": f"dynamic::{rel['source_agent_id']}::{rel['target_agent_id']}::{round_num}",
                    "source_agent_id": rel["source_agent_id"],
                    "target_agent_id": rel["target_agent_id"],
                    "edge_type": "cross_region_bridge",
                    "interaction_channel": rel["interaction_channel"],
                    "layer": "social_bridge",
                    "origin": "golden_case_scaffold",
                    "scope": "citywide",
                    "strength": round(0.45 + (idx % 5) * 0.07, 2),
                    "confidence": 0.76,
                    "status": "active" if round_num >= WUHAN_TOTAL_ROUNDS - 1 else "created",
                    "created_round": round_num,
                    "last_activated_round": min(WUHAN_TOTAL_ROUNDS, round_num + 2),
                    "rationale": rel["rationale"],
                }
            )
        return rows

    @classmethod
    def _build_risk_bundle(cls, regions: List[Dict[str, Any]]) -> Dict[str, Any]:
        risk_definitions = [
            {
                "risk_id": "cluster_spread_pressure",
                "title": "聚集传播压力",
                "description": "市场、医院和社区接触链的叠加使传播压力快速抬升。",
            },
            {
                "risk_id": "service_capacity_overload",
                "title": "医疗服务超载",
                "description": "急诊、检验与住院能力在高峰期接近阈值。",
            },
            {
                "risk_id": "public_trust_volatility",
                "title": "公众信任波动",
                "description": "信息不对称与谣言传播削弱治理协同效率。",
            },
        ]
        risk_objects = [
            {
                "risk_object_id": "risk_object_cluster_spread",
                "title": "市场-医院-社区接触链",
                "summary": "病例发现与就医迁移共同推高城区传播压力。",
                "why_now": "接触链密集节点开始跨区外溢，形成新的放大器。",
                "severity_score": 86,
                "actionability_score": 72,
                "confidence_score": 0.83,
                "mode": "incident",
                "chain_steps": ["病例发现", "就医迁移", "社区扩散", "治理加码"],
                "root_pressures": ["高频接触", "检测滞后", "跨区流动"],
                "source_entity_uuids": ["agent::1", "agent::3", "agent::41"],
                "primary_regions": [regions[0]["name"], regions[1]["name"], regions[4]["name"]],
                "region_scope": [regions[0]["name"], regions[4]["name"], regions[8]["name"]],
                "affected_clusters": [
                    {"cluster_id": "cluster_1", "name": "医疗前线群簇", "cluster_type": "medical", "vulnerability_score": 88, "mismatch_risk": 74, "dependency_profile": ["检验", "分诊", "床位"]},
                    {"cluster_id": "cluster_2", "name": "社区照护群簇", "cluster_type": "community", "vulnerability_score": 76, "mismatch_risk": 68, "dependency_profile": ["排查", "药品", "楼栋治理"]},
                ],
                "turning_points": ["病例发现从市场接触带转向社区传播带", "医疗承压带开始出现延迟反馈"],
                "scenario_branches": [
                    {"branch_id": "branch_1", "name": "快速检测扩容", "branch_type": "intervention", "description": "通过扩容检测与分诊降低次生扩散。"},
                    {"branch_id": "branch_2", "name": "交通筛查滞后", "branch_type": "counterfactual", "description": "交通节点筛查滞后会放大跨区桥接。"},
                ],
                "evidence": [{"title": "高频接触", "summary": "市场与医院之间存在高频接触迁移。", "entity_refs": ["agent::1", "agent::3"]}],
            },
            {
                "risk_object_id": "risk_object_capacity",
                "title": "医疗容量摩擦",
                "summary": "检验、转运、床位与社区转介之间出现时滞。",
                "why_now": "多条病例链同时汇入医疗带，容量被持续挤压。",
                "severity_score": 78,
                "actionability_score": 69,
                "confidence_score": 0.79,
                "mode": "watch",
                "chain_steps": ["检验积压", "转运延迟", "服务摩擦"],
                "root_pressures": ["高峰积压", "协同失配"],
                "source_entity_uuids": ["agent::4", "agent::9"],
                "primary_regions": [regions[1]["name"], regions[7]["name"]],
                "region_scope": [regions[1]["name"], regions[8]["name"]],
                "affected_clusters": [],
                "turning_points": ["检验周转时间超过阈值"],
                "scenario_branches": [],
                "evidence": [{"title": "容量摩擦", "summary": "多节点服务能力开始下降。", "entity_refs": ["agent::4"]}],
            },
            {
                "risk_object_id": "risk_object_trust",
                "title": "信息与信任波动",
                "summary": "公共沟通和社区感知在高压下出现波动。",
                "why_now": "延迟和不确定信息开始通过媒体与社区双向放大。",
                "severity_score": 71,
                "actionability_score": 75,
                "confidence_score": 0.74,
                "mode": "watch",
                "chain_steps": ["信息不对称", "谣言扩散", "信任回落"],
                "root_pressures": ["信息延迟", "高压反馈"],
                "source_entity_uuids": ["agent::8", "agent::16"],
                "primary_regions": [regions[4]["name"], regions[10]["name"]],
                "region_scope": [regions[4]["name"], regions[10]["name"]],
                "affected_clusters": [],
                "turning_points": ["社区热线需求激增"],
                "scenario_branches": [],
                "evidence": [{"title": "信任波动", "summary": "媒体与社区感知出现偏差。", "entity_refs": ["agent::8"]}],
            },
        ]
        risk_runtime_history = []
        risk_events = []
        for round_num in range(1, WUHAN_TOTAL_ROUNDS + 1):
            severity = min(96, 42 + round_num * 1.4)
            risk_runtime_history.append(
                {
                    "round": round_num,
                    "primary_active_risk_id": "cluster_spread_pressure",
                    "risk_states": [
                        {"risk_id": "cluster_spread_pressure", "severity_score": severity, "trend": "rising", "active_step_ids": ["病例发现", "社区扩散"]},
                        {"risk_id": "service_capacity_overload", "severity_score": max(30, severity - 8), "trend": "rising", "active_step_ids": ["检验积压"]},
                        {"risk_id": "public_trust_volatility", "severity_score": max(25, severity - 12), "trend": "rising" if round_num > 8 else "stable", "active_step_ids": ["信息不对称"] if round_num > 8 else []},
                    ],
                    "pinned_risk_ids": ["cluster_spread_pressure"],
                }
            )
            risk_events.append(
                {
                    "id": f"risk-event::{round_num}",
                    "round": round_num,
                    "event_type": "risk_escalation",
                    "title": "聚集传播压力上升",
                    "summary": f"第 {round_num} 轮，核心接触链继续上升并向跨区桥接蔓延。",
                    "severity_score": severity,
                    "region_scope": [regions[round_num % len(regions)]["name"]],
                }
            )
        latest_runtime_state = risk_runtime_history[-1]
        return {
            "risk_definitions": risk_definitions,
            "risk_objects": risk_objects,
            "risk_objects_summary": {
                "primary_risk_object_id": "risk_object_cluster_spread",
                "primary_active_risk_id": "cluster_spread_pressure",
                "primary_risk_object": risk_objects[0],
                "risk_definitions_count": len(risk_definitions),
                "risk_event_count": len(risk_events),
            },
            "latest_risk_runtime_state": latest_runtime_state,
            "risk_runtime_history": risk_runtime_history,
            "risk_events": risk_events,
        }

    @classmethod
    def _build_animation_payload(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        round_snapshots: List[Dict[str, Any]],
        interaction_rows: List[Dict[str, Any]],
        dynamic_edges: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        layout_nodes = []
        for region in region_graph:
            layout_nodes.append(
                {
                    "id": f"region::{region['region_id']}",
                    "name": region["name"],
                    "labels": ["Entity", "Region"],
                    "kind": "region",
                    "lat": region["lat"],
                    "lon": region["lon"],
                    "attributes": {"region_id": region["region_id"], "region_type": region["region_type"]},
                }
            )
        for subregion in subregion_graph:
            layout_nodes.append(
                {
                    "id": f"subregion::{subregion['region_id']}",
                    "name": subregion["name"],
                    "labels": ["Entity", "Region", "Subregion"],
                    "kind": "subregion",
                    "lat": subregion["lat"],
                    "lon": subregion["lon"],
                    "attributes": {"region_id": subregion["region_id"], "parent_region_id": subregion["parent_region_id"], "land_use_class": subregion["land_use_class"]},
                }
            )
        for profile in profiles:
            anchor = next((item for item in subregion_graph if item["region_id"] == profile["home_subregion_id"]), None)
            layout_nodes.append(
                {
                    "id": f"agent::{profile['agent_id']}",
                    "name": profile["name"],
                    "labels": ["Entity", profile["agent_type"]],
                    "kind": "agent",
                    "lat": round((anchor or {"lat": 30.59})["lat"] + ((profile["agent_id"] % 5) - 2) * 0.0016, 6),
                    "lon": round((anchor or {"lon": 114.30})["lon"] + ((profile["agent_id"] % 7) - 3) * 0.0013, 6),
                    "attributes": {"agent_id": profile["agent_id"], "primary_region": profile["primary_region"]},
                }
            )

        layout_edges = []
        for region in region_graph:
            for neighbor in region["neighbors"]:
                layout_edges.append(
                    {
                        "id": f"region_neighbor::{region['region_id']}::{neighbor}",
                        "source": f"region::{region['region_id']}",
                        "target": f"region::{neighbor}",
                        "name": "neighbor_of",
                        "fact_type": "region_neighbor",
                    }
                )
        for rel in relationships:
            layout_edges.append(
                {
                    "id": rel["edge_id"],
                    "source": f"agent::{rel['source_agent_id']}",
                    "target": f"agent::{rel['target_agent_id']}",
                    "name": rel["relation_type"],
                    "fact_type": rel["relation_type"],
                }
            )
        for item in dynamic_edges:
            layout_edges.append(
                {
                    "id": item["edge_id"],
                    "source": f"agent::{item['source_agent_id']}",
                    "target": f"agent::{item['target_agent_id']}",
                    "name": item["edge_type"],
                    "fact_type": "dynamic_edge",
                }
            )

        frames = [
            {
                "round": 0,
                "timestamp": definition.reference_time,
                "narrative": {
                    "title": "基线建图",
                    "summary": "先展示武汉基础区块、交通骨架、关键机构与社区节点。",
                    "interaction_summary": "",
                    "risk_summary": "",
                },
                "metrics": {
                    "region_count": len(region_graph),
                    "agent_count": 0,
                    "interaction_count": 0,
                    "risk_event_count": 0,
                    "avg_vulnerability_score": 24,
                },
                "focus_ids": {"node_ids": [item["id"] for item in layout_nodes[:18]], "edge_ids": [item["id"] for item in layout_edges[:12]]},
                "node_states": [
                    {
                        "id": item["id"],
                        "status": "new" if idx < len(region_graph) + len(subregion_graph) else "hidden",
                        "first_seen_round": 0 if idx < len(region_graph) + len(subregion_graph) else max(1, ((idx - len(region_graph) - len(subregion_graph)) // 8) + 1),
                        "last_active_round": 0,
                        "delay_ms": 80 * idx,
                    }
                    for idx, item in enumerate(layout_nodes)
                ],
                "edge_states": [
                    {
                        "id": item["id"],
                        "status": "new" if idx < 18 else "hidden",
                        "first_seen_round": 0 if idx < 18 else 1,
                        "last_active_round": 0,
                        "delay_ms": 45 * idx,
                    }
                    for idx, item in enumerate(layout_edges)
                ],
                "map_layers": {"center": {"lat": 30.5928, "lon": 114.3055}, "base_layer_count": 0},
                "risk_events": [],
            }
        ]

        interactions_by_round: Dict[int, List[Dict[str, Any]]] = {}
        for item in interaction_rows:
            interactions_by_round.setdefault(int(item["round"]), []).append(item)
        risk_by_round: Dict[int, List[Dict[str, Any]]] = {}
        for item in risk_events:
            risk_by_round.setdefault(int(item["round"]), []).append(item)
        dynamic_by_round: Dict[int, List[Dict[str, Any]]] = {}
        for item in dynamic_edges:
            dynamic_by_round.setdefault(int(item["created_round"]), []).append(item)

        for snapshot in round_snapshots:
            round_num = int(snapshot["round"])
            visible_agent_count = min(len(profiles), 48 + round_num * 4)
            active_agent_ids = {item["agent_id"] for item in snapshot["agents"][:24]}
            active_dynamic_ids = {item["edge_id"] for item in dynamic_by_round.get(round_num, [])}
            top_region = max(snapshot["regions"], key=lambda item: item.get("vulnerability_score", 0))
            frames.append(
                {
                    "round": round_num,
                    "timestamp": snapshot["timestamp"],
                    "narrative": {
                        "title": f"第 {round_num} 轮态势",
                        "summary": f"{top_region['name']} 成为当轮关键变化区域，脆弱性上升至 {top_region['vulnerability_score']:.0f}。",
                        "interaction_summary": interactions_by_round.get(round_num, [{}])[0].get("summary", ""),
                        "risk_summary": risk_by_round.get(round_num, [{}])[0].get("summary", ""),
                    },
                    "metrics": {
                        "region_count": len(snapshot["regions"]),
                        "agent_count": len(snapshot["agents"]),
                        "interaction_count": len(interactions_by_round.get(round_num, [])),
                        "risk_event_count": len(risk_by_round.get(round_num, [])),
                        "avg_vulnerability_score": round(sum(item["vulnerability_score"] for item in snapshot["regions"]) / len(snapshot["regions"]), 2),
                    },
                    "focus_ids": {
                        "node_ids": [f"agent::{item}" for item in sorted(active_agent_ids)[:18]],
                        "edge_ids": list(active_dynamic_ids)[:18],
                    },
                    "node_states": [
                        {
                            "id": item["id"],
                            "status": (
                                "active"
                                if item["id"].startswith("agent::") and int(item["attributes"].get("agent_id") or 0) in active_agent_ids
                                else "new"
                                if item["id"].startswith("agent::") and int(item["attributes"].get("agent_id") or 0) <= visible_agent_count and int(item["attributes"].get("agent_id") or 0) > visible_agent_count - 4
                                else "steady"
                                if not item["id"].startswith("agent::") or int(item["attributes"].get("agent_id") or 0) <= visible_agent_count
                                else "hidden"
                            ),
                            "first_seen_round": 0 if not item["id"].startswith("agent::") else max(1, ((int(item["attributes"].get("agent_id") or 1) - 1) // 8) + 1),
                            "last_active_round": round_num if item["id"].startswith("agent::") and int(item["attributes"].get("agent_id") or 0) in active_agent_ids else max(0, round_num - 1),
                            "delay_ms": 80 * (idx % 8) if item["id"].startswith("agent::") else 40 * idx,
                        }
                        for idx, item in enumerate(layout_nodes)
                    ],
                    "edge_states": [
                        {
                            "id": item["id"],
                            "status": (
                                "active"
                                if item["id"] in active_dynamic_ids
                                else "new"
                                if item["fact_type"] == "dynamic_edge" and item["id"] in {edge["edge_id"] for edge in dynamic_by_round.get(round_num, [])}
                                else "steady"
                                if item["fact_type"] != "dynamic_edge" or round_num > 0
                                else "hidden"
                            ),
                            "first_seen_round": 0 if item["fact_type"] != "dynamic_edge" else max(1, next((edge["created_round"] for edge in dynamic_edges if edge["edge_id"] == item["id"]), 1)),
                            "last_active_round": round_num if item["id"] in active_dynamic_ids else max(0, round_num - 1),
                            "delay_ms": 45 * (idx % 12),
                        }
                        for idx, item in enumerate(layout_edges)
                    ],
                    "map_layers": {"center": {"lat": 30.5928, "lon": 114.3055}, "base_layer_count": 0},
                    "risk_events": risk_by_round.get(round_num, []),
                }
            )

        return {
            "meta": {
                "simulation_id": f"golden::{definition.case_id}",
                "golden_case_id": definition.case_id,
                "artifact_mode": "frozen",
                "reference_time": definition.reference_time,
                "minutes_per_round": WUHAN_MINUTES_PER_ROUND,
                "total_rounds": definition.total_rounds,
                "default_speed_ms": 1400,
                "speed_options_ms": [800, 1400, 2200],
            },
            "layout": {
                "center": {"lat": 30.5928, "lon": 114.3055},
                "zoom_hint": 10,
                "radius_m": 45000,
                "analysis_polygon": None,
                "base_layers": [],
                "nodes": layout_nodes,
                "edges": layout_edges,
            },
            "frames": frames,
        }

    @classmethod
    def _build_simulation_config(
        cls,
        *,
        definition: GoldenCaseDefinition,
        region_graph: List[Dict[str, Any]],
        subregion_graph: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        transport_edges: List[Dict[str, Any]],
        risk_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "simulation_id": f"golden::{definition.case_id}",
            "project_id": f"golden_project::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "engine_mode": "envfish",
            "scenario_mode": definition.scenario_mode,
            "diffusion_template": definition.diffusion_template,
            "hazard_template_id": definition.hazard_template_id,
            "hazard_template_mode": "manual",
            "search_mode": definition.search_mode,
            "simulation_requirement": cls._simulation_requirement(),
            "reference_time": definition.reference_time,
            "time_plan_mode": "manual",
            "time_plan": normalize_time_plan(
                {
                    "step_unit": definition.step_unit,
                    "step_size": definition.step_size,
                    "total_rounds": definition.total_rounds,
                    "reference_time": definition.reference_time,
                    "source": "golden_case_scaffold",
                },
                total_rounds=definition.total_rounds,
                minutes_per_round=WUHAN_MINUTES_PER_ROUND,
                preset="slow",
                reference_time=definition.reference_time,
                source="golden_case_scaffold",
            ),
            "time_config": {
                "total_rounds": definition.total_rounds,
                "minutes_per_round": WUHAN_MINUTES_PER_ROUND,
                "total_simulation_hours": definition.total_rounds * WUHAN_MINUTES_PER_ROUND / 60,
            },
            "region_graph": region_graph,
            "subregion_graph": subregion_graph,
            "transport_edges": transport_edges,
            "actor_profiles": profiles,
            "agent_configs": [
                {
                    "agent_id": item["agent_id"],
                    "name": item["name"],
                    "agent_type": item["agent_type"],
                    "agent_subtype": item["agent_subtype"],
                    "primary_region": item["primary_region"],
                    "home_subregion_id": item["home_subregion_id"],
                }
                for item in profiles
            ],
            "agent_relationship_graph": relationships,
            "region_agent_index": cls._build_region_agent_index(region_graph, subregion_graph, profiles),
            "agent_generation_summary": cls._build_agent_generation_summary(profiles),
            "interaction_policies": {
                "activation_mode": "stress_weighted_round_robin",
                "max_actions_per_round": 72,
                "link_follow_probability": 0.84,
                "ecology_feedback_enabled": True,
                "cross_region_candidates_per_agent": 10,
                "max_new_dynamic_edges_per_agent": 4,
                "dynamic_edge_ttl_rounds": 4,
                "dynamic_edge_decay_per_round": 0.10,
                "allowed_cross_region_hops": 3,
                "llm_relation_search_budget": 24,
                "edge_promotion_enabled": True,
            },
            "runtime_limits": {
                "max_agents": len(profiles),
                "max_active_agents_per_round": 72,
                "max_relationship_hops": 4,
                "llm_batch_size": 24,
                "cross_region_candidates_per_agent": 10,
                "max_new_dynamic_edges_per_agent": 4,
            },
            "risk_definitions": risk_bundle["risk_definitions"],
            "latest_risk_runtime_state": risk_bundle["latest_risk_runtime_state"],
            "risk_objects": risk_bundle["risk_objects"],
            "primary_risk_object_id": risk_bundle["risk_objects_summary"]["primary_risk_object_id"],
            "primary_active_risk_id": risk_bundle["risk_objects_summary"]["primary_active_risk_id"],
            "data_grounding_summary": cls._build_grounding_summary(region_graph),
            "diffusion_context": cls._build_diffusion_context(definition),
            "golden_case_profile": definition.profile,
            "report_focus": ["risk object summary", "regional vulnerability progression", "agent relationship cascade"],
        }

    @classmethod
    def _build_region_agent_index(
        cls,
        regions: List[Dict[str, Any]],
        subregions: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {"regions": {}, "subregions": {}}
        for region in regions:
            result["regions"][region["region_id"]] = [item["agent_id"] for item in profiles if item["home_region_id"] == region["region_id"]]
        for subregion in subregions:
            result["subregions"][subregion["region_id"]] = [item["agent_id"] for item in profiles if item["home_subregion_id"] == subregion["region_id"]]
        return result

    @classmethod
    def _build_agent_generation_summary(cls, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_family: Dict[str, int] = {}
        for item in profiles:
            by_family[item["node_family"]] = by_family.get(item["node_family"], 0) + 1
        return {
            "target_agent_count": len(profiles),
            "generated_agent_count": len(profiles),
            "by_family": by_family,
            "generation_mode": "golden_case_scaffold",
        }

    @classmethod
    def _build_diffusion_context(cls, definition: GoldenCaseDefinition) -> Dict[str, Any]:
        return {
            "provider": "heuristic",
            "template": definition.diffusion_template,
            "notes": "Frozen Wuhan COVID-19 scaffold uses deterministic diffusion context.",
        }

    @classmethod
    def _build_grounding_summary(cls, regions: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "records": [
                {
                    "metadata": {"region": region["name"]},
                    "priors": {"vulnerability_score": region["state_vector"]["vulnerability_score"]},
                }
                for region in regions[:6]
            ],
            "note": "Golden scaffold uses curated Wuhan region priors.",
        }

    @classmethod
    def _build_scene_seed(cls, definition: GoldenCaseDefinition) -> Dict[str, Any]:
        return {
            "scene_id": f"scene::{definition.case_id}",
            "title": definition.title,
            "report_markdown": cls._build_scene_report(),
            "recommended_simulation_requirement": cls._simulation_requirement(),
            "location": "武汉市核心城区",
            "time_scope": "2019-12-22 至 2020-04-08",
        }

    @classmethod
    def _build_scene_report(cls) -> str:
        return "\n".join(
            [
                "# 武汉疫情背景素材",
                "",
                "本案例固定围绕武汉核心城区在疫情爆发窗口中的空间结构、医疗承压、市场接触链、社区治理与跨区流动展开。",
                "",
                "## 关键锚点",
                "- 市场接触带",
                "- 医疗承压带",
                "- 社区传播带",
                "- 铁路枢纽与机场门户",
                "",
                "## 目标",
                "作为冻结黄金案例，用于动画、关系网回放和后续流程调试。",
            ]
        )

    @classmethod
    def _build_report_outline(cls) -> Dict[str, Any]:
        return {
            "title": WUHAN_CASE.report_title,
            "summary": "围绕武汉疫情黄金案例，复盘地图结构、关系网增长与风险对象演化。",
            "sections": [
                {"title": "案例概览", "content": "回顾武汉案例的空间结构、时间窗口和关键参与群体。"},
                {"title": "区域与子区域演化", "content": "展示宏观区域与子区域在 36 轮中的承压变化。"},
                {"title": "代理体关系增长", "content": "分析治理、医疗、社区和物流网络如何逐步扩张连接。"},
                {"title": "风险对象与干预窗口", "content": "总结主要风险对象、转折点和可干预节点。"},
            ],
        }

    @classmethod
    def _build_report_markdown(cls, outline: Dict[str, Any]) -> str:
        lines = [
            f"# {outline['title']}",
            "",
            f"> {outline['summary']}",
            "",
            "---",
            "",
        ]
        for section in outline["sections"]:
            lines.extend([f"## {section['title']}", "", section["content"], ""])
        lines.extend(
            [
                "## 结论",
                "",
                "武汉黄金案例的价值不在于一次性跑出结论，而在于把空间锚点、关系网络、风险对象和报告入口冻结为可反复回放的演示底座。",
                "",
            ]
        )
        return "\n".join(lines)

    @classmethod
    def _build_report_meta(cls, definition: GoldenCaseDefinition) -> Dict[str, Any]:
        return {
            "report_id": f"golden::{definition.case_id}",
            "simulation_id": f"golden::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "simulation_requirement": cls._simulation_requirement(),
            "status": "completed",
            "outline": cls._build_report_outline(),
            "markdown_content": "",
            "created_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "artifact_mode": "frozen",
            "artifact_root": os.path.join(cls.case_root(definition.case_id), "report"),
            "golden_case_id": definition.case_id,
            "is_replay_only": True,
        }

    @classmethod
    def _build_report_agent_log(cls) -> List[Dict[str, Any]]:
        return [
            {"timestamp": datetime.now().isoformat(), "stage": "load", "message": "Loaded frozen Wuhan report."},
            {"timestamp": datetime.now().isoformat(), "stage": "analysis", "message": "Prepared replay-friendly summary and outline."},
        ]

    @classmethod
    def _build_state_payload(
        cls,
        definition: GoldenCaseDefinition,
        simulation_config: Dict[str, Any],
        profiles: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        risk_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "simulation_id": f"golden::{definition.case_id}",
            "project_id": f"golden_project::{definition.case_id}",
            "graph_id": f"golden_graph::{definition.case_id}",
            "engine_mode": "envfish",
            "scenario_mode": definition.scenario_mode,
            "diffusion_template": definition.diffusion_template,
            "hazard_template_id": definition.hazard_template_id,
            "hazard_template_mode": "manual",
            "transport_profile": {"primary_family": definition.diffusion_template},
            "search_mode": definition.search_mode,
            "temporal_preset": "slow",
            "configured_total_rounds": definition.total_rounds,
            "configured_minutes_per_round": WUHAN_MINUTES_PER_ROUND,
            "time_plan_mode": "manual",
            "time_plan": simulation_config["time_plan"],
            "reference_time": definition.reference_time,
            "diffusion_provider": "heuristic",
            "status": "completed",
            "entities_count": definition.target_node_count,
            "profiles_count": len(profiles),
            "region_count": len(regions),
            "active_variables_count": 0,
            "risk_objects_count": len(risk_bundle["risk_objects"]),
            "entity_types": ["Region", "Subregion", "HumanActor", "GovernmentActor", "OrganizationActor"],
            "config_generated": True,
            "config_reasoning": "Frozen Wuhan COVID-19 golden scaffold.",
            "primary_risk_object_id": risk_bundle["risk_objects_summary"]["primary_risk_object_id"],
            "source_mode": "golden_case",
            "map_seed_id": None,
            "artifact_mode": "frozen",
            "artifact_root": os.path.join(cls.case_root(definition.case_id), "simulation"),
            "golden_case_id": definition.case_id,
            "golden_case_profile": definition.profile,
            "is_replay_only": True,
            "current_round": definition.total_rounds,
            "twitter_status": "not_started",
            "reddit_status": "not_started",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "error": None,
        }

    @classmethod
    def _build_run_state(cls, definition: GoldenCaseDefinition, round_snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_hours = definition.total_rounds * WUHAN_MINUTES_PER_ROUND / 60
        return {
            "simulation_id": f"golden::{definition.case_id}",
            "runner_status": "completed",
            "current_round": definition.total_rounds,
            "total_rounds": definition.total_rounds,
            "simulated_hours": total_hours,
            "total_simulation_hours": total_hours,
            "twitter_current_round": 0,
            "reddit_current_round": 0,
            "twitter_simulated_hours": 0,
            "reddit_simulated_hours": 0,
            "twitter_running": False,
            "reddit_running": False,
            "twitter_completed": False,
            "reddit_completed": False,
            "twitter_actions_count": 0,
            "reddit_actions_count": 0,
            "rounds": [{"round_num": item["round"], "start_time": item["timestamp"], "end_time": item["timestamp"], "simulated_hour": item["round"] * 72, "twitter_actions": 0, "reddit_actions": 0, "active_agents": [agent["agent_id"] for agent in item["agents"][:16]], "actions": []} for item in round_snapshots],
            "recent_actions": [],
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "error": None,
            "process_pid": None,
        }

    @classmethod
    def _build_reddit_profiles(cls, profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id": item["agent_id"], "name": item["name"], "bio": item["bio"]} for item in profiles]

    @classmethod
    def _build_twitter_profiles(cls, profiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{"agent_id": item["agent_id"], "name": item["name"], "bio": item["bio"]} for item in profiles]

    @classmethod
    def _simulation_requirement(cls) -> str:
        return (
            "以武汉疫情爆发早期为背景，围绕市场接触链、医疗承压、社区传播和跨区流动进行高保真推演，"
            "观察关系网如何逐步增长并形成风险对象。"
        )

    @classmethod
    def _background_text(cls) -> str:
        return (
            "武汉疫情黄金案例背景：固定覆盖 2019-12-22 至 2020-04-08，"
            "突出市场接触、医疗承压、社区传播、交通枢纽和治理协调等要素。"
        )

    @classmethod
    def _wave(cls, round_num: int, total_rounds: int) -> float:
        midpoint = total_rounds * 0.45
        steepness = 0.22
        return 1.0 / (1.0 + math.exp(-(round_num - midpoint) * steepness))

    @classmethod
    def _clamp(cls, value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)

    @classmethod
    def _read_json(cls, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def _write_json(cls, path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    @classmethod
    def _write_text(cls, path: str, payload: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)

    @classmethod
    def _write_jsonl(cls, path: str, rows: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    @classmethod
    def _write_csv(cls, path: str, rows: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["agent_id", "name", "bio"])
            writer.writeheader()
            writer.writerows(rows)
