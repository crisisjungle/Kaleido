"""
结果分析服务

为统一的结果分析页面提供结构化聚合数据与节点级解释能力。
"""

from __future__ import annotations

import json
import os
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..models.project import ProjectManager
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .graph_builder import GraphBuilderService
from .report_agent import ReportManager, ReportStatus
from .simulation_manager import SimulationManager
from .simulation_runner import SimulationRunner

logger = get_logger("envfish.report_analysis")


METRIC_LABELS: Dict[str, str] = {
    "exposure_score": "暴露强度",
    "spread_pressure": "扩散压力",
    "ecosystem_integrity": "生态完整性",
    "livelihood_stability": "生计稳定性",
    "public_trust": "公众信任",
    "panic_level": "恐慌水平",
    "service_capacity": "服务能力",
    "response_capacity": "响应能力",
    "economic_stress": "经济压力",
    "vulnerability_score": "脆弱性",
}

ROLE_GROUP_META: Dict[str, Dict[str, Any]] = {
    "governance": {
        "title": "治理者",
        "description": "关注治理响应、公共服务与制度协同的角色集合。",
        "focus_metrics": ["response_capacity", "service_capacity", "public_trust"],
    },
    "livelihood": {
        "title": "生计依赖者",
        "description": "直接受生态波动和经济压力影响的生产经营主体。",
        "focus_metrics": ["livelihood_stability", "economic_stress", "spread_pressure"],
    },
    "resident": {
        "title": "居民/消费者",
        "description": "主要体现日常暴露、风险感知和信任波动的人群。",
        "focus_metrics": ["public_trust", "panic_level", "service_capacity"],
    },
    "ecology": {
        "title": "生态受体/环境节点",
        "description": "体现生态完整性、扩散与环境压力的自然受体。",
        "focus_metrics": ["ecosystem_integrity", "exposure_score", "spread_pressure"],
    },
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _merge_state_vector(item: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(item or {})
    state_vector = item.get("state_vector") if isinstance(item, dict) else None
    if isinstance(state_vector, dict):
        merged.update(state_vector)
    return merged


class ReportAnalysisService:
    """统一结果分析数据服务。"""

    _node_explore_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.report = ReportManager.get_report(report_id)
        if not self.report:
            raise ValueError(f"报告不存在: {report_id}")

        self.simulation_id = self.report.simulation_id
        self.graph_id = self.report.graph_id
        self.simulation_requirement = self.report.simulation_requirement or ""

        manager = SimulationManager()
        self.simulation_state = manager.get_simulation(self.simulation_id)
        self.project = None
        if self.simulation_state:
            self.project = ProjectManager.get_project(self.simulation_state.project_id)

        self.artifacts = SimulationRunner.get_envfish_artifacts(self.simulation_id) or {}
        self.latest_snapshot = self.artifacts.get("latest_snapshot") or {}
        self.round_snapshots = self._dedupe_round_snapshots(self.artifacts.get("round_snapshots") or [])
        self.max_round = self._get_max_round()

    def _simulation_dir(self) -> Optional[str]:
        if not self.simulation_id:
            return None
        sim_dir = os.path.join(SimulationRunner.RUN_STATE_DIR, self.simulation_id)
        if os.path.exists(sim_dir):
            return sim_dir
        return None

    def _read_simulation_json(self, filename: str, default: Any) -> Any:
        sim_dir = self._simulation_dir()
        if not sim_dir:
            return default
        file_path = os.path.join(sim_dir, filename)
        if not os.path.exists(file_path):
            return default
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning(f"读取模拟工件失败: simulation_id={self.simulation_id}, file={filename}, error={exc}")
            return default

    def _dedupe_round_snapshots(self, snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        latest_by_round: Dict[str, Dict[str, Any]] = {}
        ordered_rounds: List[str] = []
        for snap in snapshots:
            if not isinstance(snap, dict):
                continue
            round_value = snap.get("round")
            if round_value is None:
                continue
            key = str(round_value)
            if key not in latest_by_round:
                ordered_rounds.append(key)
            latest_by_round[key] = snap
        result = [latest_by_round[key] for key in ordered_rounds]
        result.sort(key=lambda item: item.get("round", 0))
        return result

    def _get_max_round(self) -> int:
        round_ids = [
            int(item.get("round"))
            for item in self.round_snapshots
            if isinstance(item.get("round"), (int, float, str)) and str(item.get("round")).isdigit()
        ]
        latest_round = self.latest_snapshot.get("round")
        if isinstance(latest_round, (int, float)):
            round_ids.append(int(latest_round))
        return max(round_ids) if round_ids else 0

    def _get_default_round(self) -> int:
        latest_round = self.latest_snapshot.get("round")
        if isinstance(latest_round, (int, float)):
            return int(latest_round)
        return self.max_round

    def _load_agent_catalog(self) -> List[Dict[str, Any]]:
        config_payload = self._read_simulation_json("simulation_config.json", {}) or {}
        config_agents = config_payload.get("agent_configs") or []
        profile_agents = self._read_simulation_json("profiles_full.json", []) or []
        latest_agents = self.latest_snapshot.get("agents") or []

        merged_by_id: Dict[int, Dict[str, Any]] = {}

        def upsert_agent(item: Dict[str, Any]) -> None:
            if not isinstance(item, dict):
                return
            raw_id = item.get("agent_id")
            if not isinstance(raw_id, int) and not str(raw_id or "").isdigit():
                return
            agent_id = int(raw_id)
            existing = merged_by_id.get(agent_id, {})
            merged = dict(existing)
            for key, value in item.items():
                if key not in merged or value not in (None, "", [], {}):
                    merged[key] = value
            merged["agent_id"] = agent_id
            if not merged.get("name"):
                merged["name"] = merged.get("agent_name") or merged.get("username") or f"Agent {agent_id}"
            if not merged.get("agent_name"):
                merged["agent_name"] = merged.get("username") or merged.get("name")
            if not merged.get("username"):
                merged["username"] = merged.get("agent_name") or merged.get("name")
            if not merged.get("primary_region"):
                merged["primary_region"] = merged.get("home_region_id")
            merged_by_id[agent_id] = merged

        for bucket in (config_agents, profile_agents, latest_agents):
            for item in bucket:
                upsert_agent(item)

        result = list(merged_by_id.values())
        result.sort(key=lambda item: int(item.get("agent_id", 0)))
        return result

    def _load_dynamic_edges(self) -> List[Dict[str, Any]]:
        latest_edges = self.latest_snapshot.get("dynamic_edges") or []
        if isinstance(latest_edges, list) and latest_edges:
            return [item for item in latest_edges if isinstance(item, dict)]

        latest_by_id: Dict[str, Dict[str, Any]] = {}
        for item in self.artifacts.get("dynamic_edge_events") or []:
            if not isinstance(item, dict):
                continue
            edge_id = _normalize_text(item.get("edge_id"))
            if not edge_id:
                continue
            latest_by_id[edge_id] = item

        edges = [
            item for item in latest_by_id.values()
            if _normalize_text(item.get("status")) != "expired"
        ]
        edges.sort(
            key=lambda item: (
                _normalize_text(item.get("layer")) != "structural",
                -(_safe_float(item.get("strength")) or 0.0),
                _normalize_text(item.get("edge_id")),
            )
        )
        return edges

    def _build_analysis_graph(self) -> Dict[str, Any]:
        latest_snapshot = self.latest_snapshot if isinstance(self.latest_snapshot, dict) else {}
        latest_regions = latest_snapshot.get("regions") or []
        latest_subregions = latest_snapshot.get("subregions") or []
        base_regions = self.artifacts.get("region_graph") or []
        base_subregions = self.artifacts.get("subregion_graph") or []
        risk_objects = self.artifacts.get("risk_objects") or []
        agent_relationships = self._read_simulation_json("agent_relationship_graph.json", []) or []
        dynamic_edges = self._load_dynamic_edges()
        agents = self._load_agent_catalog()

        base_region_lookup = {
            _normalize_text(item.get("region_id") or item.get("name")): item
            for item in base_regions
            if isinstance(item, dict)
        }
        base_subregion_lookup = {
            _normalize_text(item.get("region_id") or item.get("name")): item
            for item in base_subregions
            if isinstance(item, dict)
        }
        latest_region_lookup = {
            _normalize_text(item.get("region_id") or item.get("name")): item
            for item in latest_regions
            if isinstance(item, dict)
        }
        latest_subregion_lookup = {
            _normalize_text(item.get("region_id") or item.get("name")): item
            for item in latest_subregions
            if isinstance(item, dict)
        }

        nodes_by_uuid: Dict[str, Dict[str, Any]] = {}
        edges_by_uuid: Dict[str, Dict[str, Any]] = {}

        def add_node(node: Dict[str, Any]) -> None:
            node_uuid = _normalize_text(node.get("uuid"))
            if not node_uuid:
                return
            existing = nodes_by_uuid.get(node_uuid)
            if not existing:
                nodes_by_uuid[node_uuid] = node
                return

            merged = dict(existing)
            for key, value in node.items():
                if key == "labels":
                    merged["labels"] = list(dict.fromkeys((existing.get("labels") or []) + (value or [])))
                elif key == "attributes":
                    attributes = dict(existing.get("attributes") or {})
                    attributes.update(value or {})
                    merged["attributes"] = attributes
                elif key not in merged or value not in (None, "", [], {}):
                    merged[key] = value
            nodes_by_uuid[node_uuid] = merged

        def add_edge(edge: Dict[str, Any]) -> None:
            edge_uuid = _normalize_text(edge.get("uuid"))
            source_uuid = _normalize_text(edge.get("source_node_uuid"))
            target_uuid = _normalize_text(edge.get("target_node_uuid"))
            if not edge_uuid or not source_uuid or not target_uuid:
                return
            if edge_uuid in edges_by_uuid:
                return
            edges_by_uuid[edge_uuid] = edge

        def metric_attributes(item: Dict[str, Any]) -> Dict[str, Any]:
            merged = _merge_state_vector(item)
            return {metric: _safe_float(merged.get(metric)) for metric in METRIC_LABELS}

        region_ids = sorted(set(base_region_lookup) | set(latest_region_lookup))
        for region_id in region_ids:
            combined = dict(base_region_lookup.get(region_id) or {})
            combined.update(latest_region_lookup.get(region_id) or {})
            merged = _merge_state_vector(combined)
            region_uuid = f"region::{region_id}"
            add_node({
                "uuid": region_uuid,
                "name": merged.get("name") or merged.get("region_id") or region_id,
                "labels": ["Entity", "Region"],
                "summary": combined.get("description") or f"{merged.get('name') or region_id} 的结果分析区域节点。",
                "attributes": {
                    "scope": "region",
                    "region_id": merged.get("region_id") or region_id,
                    "region_type": merged.get("region_type"),
                    "layer": combined.get("layer"),
                    "neighbors": combined.get("neighbors") or [],
                    **metric_attributes(combined),
                },
                "created_at": combined.get("created_at"),
            })

        subregion_ids = sorted(set(base_subregion_lookup) | set(latest_subregion_lookup))
        for subregion_id in subregion_ids:
            combined = dict(base_subregion_lookup.get(subregion_id) or {})
            combined.update(latest_subregion_lookup.get(subregion_id) or {})
            merged = _merge_state_vector(combined)
            subregion_uuid = f"subregion::{subregion_id}"
            add_node({
                "uuid": subregion_uuid,
                "name": merged.get("name") or merged.get("region_id") or subregion_id,
                "labels": ["Entity", "Subregion"],
                "summary": combined.get("description") or f"{merged.get('name') or subregion_id} 的细分区域节点。",
                "attributes": {
                    "scope": "subregion",
                    "region_id": merged.get("region_id") or subregion_id,
                    "parent_region_id": merged.get("parent_region_id"),
                    "region_type": merged.get("region_type"),
                    "land_use_class": combined.get("land_use_class"),
                    "distance_band": combined.get("distance_band"),
                    **metric_attributes(combined),
                },
                "created_at": combined.get("created_at"),
            })

        for agent in agents:
            agent_id = agent.get("agent_id")
            if not isinstance(agent_id, int):
                continue
            agent_type = _normalize_text(agent.get("agent_type")).lower()
            label_by_type = {
                "governance": "GovernanceAgent",
                "organization": "OrganizationAgent",
                "ecology": "EcologyAgent",
                "carrier": "CarrierAgent",
                "human": "HumanAgent",
            }
            merged = _merge_state_vector(agent)
            add_node({
                "uuid": f"agent::{agent_id}",
                "name": agent.get("name") or agent.get("agent_name") or agent.get("username") or f"Agent {agent_id}",
                "labels": ["Entity", label_by_type.get(agent_type, "Agent")],
                "summary": agent.get("bio") or agent.get("persona") or f"{agent.get('primary_region') or '未知区域'} 的 agent 节点。",
                "attributes": {
                    "scope": "agent",
                    "agent_id": agent_id,
                    "agent_name": agent.get("agent_name") or agent.get("username"),
                    "username": agent.get("username"),
                    "agent_type": agent.get("agent_type"),
                    "agent_subtype": agent.get("agent_subtype"),
                    "role_type": agent.get("role_type"),
                    "profession": agent.get("profession"),
                    "primary_region": agent.get("primary_region"),
                    "home_region_id": agent.get("home_region_id"),
                    "home_subregion_id": agent.get("home_subregion_id"),
                    "source_entity_uuid": agent.get("source_entity_uuid"),
                    "source_entity_type": agent.get("source_entity_type"),
                    **{metric: _safe_float(merged.get(metric)) for metric in METRIC_LABELS},
                },
                "created_at": agent.get("created_at"),
            })

        for risk in risk_objects:
            if not isinstance(risk, dict):
                continue
            risk_id = _normalize_text(risk.get("risk_object_id") or risk.get("title"))
            if not risk_id:
                continue
            add_node({
                "uuid": f"risk::{risk_id}",
                "name": risk.get("title") or risk_id,
                "labels": ["Entity", "RiskObject"],
                "summary": risk.get("summary") or risk.get("why_now") or "风险对象节点。",
                "attributes": {
                    "scope": "risk_object",
                    "risk_object_id": risk.get("risk_object_id"),
                    "risk_type": risk.get("risk_type"),
                    "status": risk.get("status"),
                    "severity_score": _safe_float(risk.get("severity_score")),
                    "confidence_score": _safe_float(risk.get("confidence_score")),
                    "primary_regions": risk.get("primary_regions") or [],
                    "region_scope": risk.get("region_scope") or [],
                },
                "created_at": risk.get("created_at"),
            })

        for region_id in region_ids:
            combined = dict(base_region_lookup.get(region_id) or {})
            combined.update(latest_region_lookup.get(region_id) or {})
            source_uuid = f"region::{region_id}"
            for neighbor in combined.get("neighbors") or []:
                neighbor_id = _normalize_text(neighbor)
                target_uuid = f"region::{neighbor_id}"
                if source_uuid not in nodes_by_uuid or target_uuid not in nodes_by_uuid:
                    continue
                pair = sorted([source_uuid, target_uuid])
                add_edge({
                    "uuid": f"edge::region-neighbor::{pair[0]}::{pair[1]}",
                    "name": "neighbor",
                    "fact": "区域邻接与压力传播通道",
                    "fact_type": "neighbor",
                    "source_node_uuid": source_uuid,
                    "target_node_uuid": target_uuid,
                    "source_node_name": nodes_by_uuid[source_uuid]["name"],
                    "target_node_name": nodes_by_uuid[target_uuid]["name"],
                    "attributes": {"relation_type": "neighbor"},
                    "created_at": None,
                    "valid_at": None,
                    "invalid_at": None,
                    "expired_at": None,
                    "episodes": [],
                })

        for subregion_id in subregion_ids:
            combined = dict(base_subregion_lookup.get(subregion_id) or {})
            combined.update(latest_subregion_lookup.get(subregion_id) or {})
            parent_region_id = _normalize_text(combined.get("parent_region_id"))
            if not parent_region_id:
                continue
            source_uuid = f"region::{parent_region_id}"
            target_uuid = f"subregion::{subregion_id}"
            if source_uuid not in nodes_by_uuid or target_uuid not in nodes_by_uuid:
                continue
            add_edge({
                "uuid": f"edge::contains::{parent_region_id}::{subregion_id}",
                "name": "contains",
                "fact": "宏观区域包含该子区域。",
                "fact_type": "contains",
                "source_node_uuid": source_uuid,
                "target_node_uuid": target_uuid,
                "source_node_name": nodes_by_uuid[source_uuid]["name"],
                "target_node_name": nodes_by_uuid[target_uuid]["name"],
                "attributes": {"relation_type": "contains"},
                "created_at": None,
                "valid_at": None,
                "invalid_at": None,
                "expired_at": None,
                "episodes": [],
            })

        for agent in agents:
            agent_id = agent.get("agent_id")
            if not isinstance(agent_id, int):
                continue
            agent_uuid = f"agent::{agent_id}"
            primary_region = _normalize_text(agent.get("primary_region") or agent.get("home_region_id"))
            home_subregion = _normalize_text(agent.get("home_subregion_id"))

            if primary_region:
                region_uuid = f"region::{primary_region}"
                if region_uuid in nodes_by_uuid:
                    add_edge({
                        "uuid": f"edge::region-agent::{primary_region}::{agent_id}",
                        "name": "hosts_agent",
                        "fact": "该区域承载此 agent 的主要活动。",
                        "fact_type": "hosts_agent",
                        "source_node_uuid": region_uuid,
                        "target_node_uuid": agent_uuid,
                        "source_node_name": nodes_by_uuid[region_uuid]["name"],
                        "target_node_name": nodes_by_uuid[agent_uuid]["name"],
                        "attributes": {"relation_type": "hosts_agent"},
                        "created_at": None,
                        "valid_at": None,
                        "invalid_at": None,
                        "expired_at": None,
                        "episodes": [],
                    })

            if home_subregion:
                subregion_uuid = f"subregion::{home_subregion}"
                if subregion_uuid in nodes_by_uuid:
                    add_edge({
                        "uuid": f"edge::subregion-agent::{home_subregion}::{agent_id}",
                        "name": "anchors_agent",
                        "fact": "该子区域是此 agent 的空间锚点。",
                        "fact_type": "anchors_agent",
                        "source_node_uuid": subregion_uuid,
                        "target_node_uuid": agent_uuid,
                        "source_node_name": nodes_by_uuid[subregion_uuid]["name"],
                        "target_node_name": nodes_by_uuid[agent_uuid]["name"],
                        "attributes": {"relation_type": "anchors_agent"},
                        "created_at": None,
                        "valid_at": None,
                        "invalid_at": None,
                        "expired_at": None,
                        "episodes": [],
                    })

        for edge in agent_relationships:
            if not isinstance(edge, dict):
                continue
            source_agent_id = edge.get("source_agent_id")
            target_agent_id = edge.get("target_agent_id")
            if not isinstance(source_agent_id, int) and not str(source_agent_id or "").isdigit():
                continue
            if not isinstance(target_agent_id, int) and not str(target_agent_id or "").isdigit():
                continue
            source_agent_id = int(source_agent_id)
            target_agent_id = int(target_agent_id)
            source_uuid = f"agent::{source_agent_id}"
            target_uuid = f"agent::{target_agent_id}"
            if source_uuid not in nodes_by_uuid or target_uuid not in nodes_by_uuid:
                continue
            relation_type = edge.get("relation_type") or "related"
            edge_id = edge.get("edge_id") or f"{source_agent_id}-{target_agent_id}-{relation_type}"
            add_edge({
                "uuid": f"edge::agent::{edge_id}",
                "name": relation_type,
                "fact": edge.get("rationale") or "",
                "fact_type": edge.get("interaction_channel") or relation_type,
                "source_node_uuid": source_uuid,
                "target_node_uuid": target_uuid,
                "source_node_name": nodes_by_uuid[source_uuid]["name"],
                "target_node_name": nodes_by_uuid[target_uuid]["name"],
                "attributes": {
                    "relation_type": relation_type,
                    "strength": _safe_float(edge.get("strength")),
                    "interaction_channel": edge.get("interaction_channel"),
                    "source_region_id": edge.get("source_region_id"),
                    "target_region_id": edge.get("target_region_id"),
                    "edge_layer": "structural",
                    "edge_origin": "seed_profile",
                    "is_emergent": False,
                },
                "created_at": None,
                "valid_at": None,
                "invalid_at": None,
                "expired_at": None,
                "episodes": [],
            })

        for edge in dynamic_edges:
            if not isinstance(edge, dict):
                continue
            source_agent_id = edge.get("source_agent_id")
            target_agent_id = edge.get("target_agent_id")
            if not isinstance(source_agent_id, int) and not str(source_agent_id or "").isdigit():
                continue
            if not isinstance(target_agent_id, int) and not str(target_agent_id or "").isdigit():
                continue
            source_agent_id = int(source_agent_id)
            target_agent_id = int(target_agent_id)
            source_uuid = f"agent::{source_agent_id}"
            target_uuid = f"agent::{target_agent_id}"
            if source_uuid not in nodes_by_uuid or target_uuid not in nodes_by_uuid:
                continue
            edge_id = _normalize_text(edge.get("edge_id")) or f"{source_agent_id}-{target_agent_id}-dynamic"
            edge_type = edge.get("edge_type") or "response_bridge"
            layer = _normalize_text(edge.get("layer")) or "dynamic"
            add_edge({
                "uuid": f"edge::dynamic::{edge_id}",
                "name": edge_type,
                "fact": edge.get("rationale") or "仿真运行中生成的跨区关系。",
                "fact_type": edge.get("interaction_channel") or edge_type,
                "source_node_uuid": source_uuid,
                "target_node_uuid": target_uuid,
                "source_node_name": nodes_by_uuid[source_uuid]["name"],
                "target_node_name": nodes_by_uuid[target_uuid]["name"],
                "attributes": {
                    "relation_type": edge_type,
                    "strength": _safe_float(edge.get("strength")),
                    "confidence": _safe_float(edge.get("confidence")),
                    "interaction_channel": edge.get("interaction_channel"),
                    "source_region_id": edge.get("source_region_id"),
                    "target_region_id": edge.get("target_region_id"),
                    "edge_layer": layer,
                    "edge_origin": edge.get("origin"),
                    "edge_status": edge.get("status"),
                    "routing_basis": edge.get("routing_basis") or [],
                    "ttl_rounds": edge.get("ttl_rounds"),
                    "created_round": edge.get("created_round"),
                    "last_activated_round": edge.get("last_activated_round"),
                    "is_emergent": True,
                },
                "created_at": edge.get("created_round"),
                "valid_at": None,
                "invalid_at": None,
                "expired_at": None,
                "episodes": [],
            })

        for risk in risk_objects:
            if not isinstance(risk, dict):
                continue
            risk_id = _normalize_text(risk.get("risk_object_id") or risk.get("title"))
            if not risk_id:
                continue
            risk_uuid = f"risk::{risk_id}"
            for region_name in risk.get("primary_regions") or risk.get("region_scope") or []:
                normalized_region = _normalize_text(region_name)
                region_uuid = f"region::{normalized_region}"
                if risk_uuid not in nodes_by_uuid or region_uuid not in nodes_by_uuid:
                    continue
                add_edge({
                    "uuid": f"edge::risk-region::{risk_id}::{normalized_region}",
                    "name": "focuses_on",
                    "fact": "该风险对象当前重点关注此区域。",
                    "fact_type": "focuses_on",
                    "source_node_uuid": risk_uuid,
                    "target_node_uuid": region_uuid,
                    "source_node_name": nodes_by_uuid[risk_uuid]["name"],
                    "target_node_name": nodes_by_uuid[region_uuid]["name"],
                    "attributes": {"relation_type": "focuses_on"},
                    "created_at": risk.get("created_at"),
                    "valid_at": None,
                    "invalid_at": None,
                    "expired_at": None,
                    "episodes": [],
                })

            actor_ids: List[int] = []
            for cluster in risk.get("affected_clusters") or []:
                if not isinstance(cluster, dict):
                    continue
                for actor_id in cluster.get("actor_ids") or []:
                    if isinstance(actor_id, int):
                        actor_ids.append(actor_id)
                    elif str(actor_id or "").isdigit():
                        actor_ids.append(int(actor_id))
            for actor_id in sorted(set(actor_ids))[:12]:
                agent_uuid = f"agent::{actor_id}"
                if risk_uuid not in nodes_by_uuid or agent_uuid not in nodes_by_uuid:
                    continue
                add_edge({
                    "uuid": f"edge::risk-agent::{risk_id}::{actor_id}",
                    "name": "impacts_actor",
                    "fact": "该风险对象将该 agent 识别为受影响对象。",
                    "fact_type": "impacts_actor",
                    "source_node_uuid": risk_uuid,
                    "target_node_uuid": agent_uuid,
                    "source_node_name": nodes_by_uuid[risk_uuid]["name"],
                    "target_node_name": nodes_by_uuid[agent_uuid]["name"],
                    "attributes": {"relation_type": "impacts_actor"},
                    "created_at": risk.get("created_at"),
                    "valid_at": None,
                    "invalid_at": None,
                    "expired_at": None,
                    "episodes": [],
                })

        nodes = list(nodes_by_uuid.values())
        nodes.sort(key=lambda item: (",".join(item.get("labels") or []), _normalize_text(item.get("name"))))

        edges = [
            edge for edge in edges_by_uuid.values()
            if edge.get("source_node_uuid") in nodes_by_uuid and edge.get("target_node_uuid") in nodes_by_uuid
        ]
        edges.sort(key=lambda item: (_normalize_text(item.get("name")), _normalize_text(item.get("uuid"))))

        return {
            "graph_id": self.graph_id or f"analysis_graph::{self.report_id}",
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def _load_graph_data(self) -> Dict[str, Any]:
        graph_data = self._build_analysis_graph()
        if graph_data.get("nodes") or graph_data.get("edges"):
            return graph_data

        if not self.graph_id or not Config.ZEP_API_KEY:
            if not Config.ZEP_API_KEY:
                logger.warning("ZEP_API_KEY 未配置，结果分析图谱回退为本地工件")
            return graph_data

        try:
            builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
            return builder.get_graph_data(self.graph_id)
        except Exception as exc:
            logger.warning(f"加载原始图谱失败，回退到结果分析工件图: graph_id={self.graph_id}, error={exc}")
            return graph_data

    def get_graph_data(self) -> Dict[str, Any]:
        return self._load_graph_data()

    def _normalize_round_range(self, raw_range: Any) -> Tuple[int, int]:
        default_end = self._get_default_round() or self.max_round or 0
        default_start = 1 if default_end else 0
        if raw_range is None:
            return default_start, default_end

        start = default_start
        end = default_end
        if isinstance(raw_range, list) and raw_range:
            if len(raw_range) >= 1:
                start = int(raw_range[0] or default_start)
            if len(raw_range) >= 2:
                end = int(raw_range[1] or default_end)
        elif isinstance(raw_range, dict):
            start = int(raw_range.get("start") or raw_range.get("from") or default_start)
            end = int(raw_range.get("end") or raw_range.get("to") or default_end)

        if start > end:
            start, end = end, start
        if start < 0:
            start = 0
        if end < 0:
            end = 0
        return start, end

    def _filter_snapshots_by_range(self, round_range: Any) -> List[Dict[str, Any]]:
        start, end = self._normalize_round_range(round_range)
        snapshots = [
            snap for snap in self.round_snapshots
            if isinstance(snap.get("round"), (int, float)) and start <= int(snap.get("round")) <= end
        ]
        if not snapshots and self.latest_snapshot:
            latest_round = self.latest_snapshot.get("round")
            if isinstance(latest_round, (int, float)) and start <= int(latest_round) <= end:
                snapshots = [self.latest_snapshot]
        return snapshots

    def _serialize_state_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            merged = _merge_state_vector(item)
            result.append({
                "region_id": merged.get("region_id"),
                "name": merged.get("name") or merged.get("region_name") or merged.get("region_id"),
                "parent_region_id": merged.get("parent_region_id"),
                "region_type": merged.get("region_type"),
                "severity_band": merged.get("severity_band"),
                "uncertainty_band": merged.get("uncertainty_band"),
                **{metric: _safe_float(merged.get(metric)) for metric in METRIC_LABELS},
            })
        return result

    def _average_confidence(self, snapshot: Dict[str, Any]) -> Optional[float]:
        confidences: List[float] = []
        for item in snapshot.get("regions") or []:
            band = item.get("uncertainty_band") if isinstance(item, dict) else None
            if isinstance(band, dict):
                confidence = _safe_float(band.get("confidence"))
                if confidence is not None:
                    confidences.append(confidence)
        if not confidences:
            return None
        return round(sum(confidences) / len(confidences), 2)

    def _top_region(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        candidates = snapshot.get("top_regions") or snapshot.get("regions") or []
        ranked = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            merged = _merge_state_vector(item)
            ranked.append((merged.get("vulnerability_score") or 0, merged))
        if not ranked:
            return None
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return ranked[0][1]

    def _classify_role_group(self, item: Dict[str, Any]) -> str:
        agent_type = _normalize_text(item.get("agent_type")).lower()
        subtype = _normalize_text(item.get("agent_subtype")).lower()
        name = _normalize_text(item.get("name") or item.get("agent_name")).lower()

        if agent_type == "governance":
            return "governance"
        if agent_type in {"ecology", "carrier"}:
            return "ecology"
        if any(token in subtype or token in name for token in ["shop_owner", "market", "operator", "merchant", "渔", "养殖", "渔业", "港", "批发"]):
            return "livelihood"
        if agent_type == "organization" and any(token in subtype or token in name for token in ["market", "operator", "station", "association", "渔", "养殖"]):
            return "livelihood"
        return "resident"

    def _build_regions_tab(self) -> Dict[str, Any]:
        rounds_payload: List[Dict[str, Any]] = []
        snapshots = self.round_snapshots or ([self.latest_snapshot] if self.latest_snapshot else [])
        for snap in snapshots:
            rounds_payload.append({
                "round": snap.get("round"),
                "timestamp": snap.get("timestamp"),
                "regions": self._serialize_state_items(snap.get("regions") or []),
                "subregions": self._serialize_state_items(snap.get("subregions") or []),
            })

        latest_regions = self._serialize_state_items(self.latest_snapshot.get("regions") or [])
        latest_subregions = self._serialize_state_items(self.latest_snapshot.get("subregions") or [])

        return {
            "tab": "regions",
            "default_metric": "vulnerability_score",
            "metric_options": [{"key": key, "label": label} for key, label in METRIC_LABELS.items()],
            "current_round": self._get_default_round(),
            "max_round": self.max_round,
            "latest_timestamp": self.latest_snapshot.get("timestamp"),
            "regions": latest_regions,
            "subregions": latest_subregions,
            "rounds": rounds_payload,
        }

    def _derive_feedback_fallback(self) -> List[Dict[str, Any]]:
        if len(self.round_snapshots) < 2:
            return []
        current = self.round_snapshots[-1]
        previous = self.round_snapshots[-2]
        previous_by_region = {
            _normalize_text(item.get("region_id") or item.get("name")): _merge_state_vector(item)
            for item in previous.get("regions") or []
            if isinstance(item, dict)
        }
        derived: List[Dict[str, Any]] = []
        for item in current.get("regions") or []:
            if not isinstance(item, dict):
                continue
            merged = _merge_state_vector(item)
            key = _normalize_text(merged.get("region_id") or merged.get("name"))
            prev = previous_by_region.get(key)
            if not prev:
                continue
            panic_delta = (_safe_float(merged.get("panic_level")) or 0) - (_safe_float(prev.get("panic_level")) or 0)
            trust_delta = (_safe_float(merged.get("public_trust")) or 0) - (_safe_float(prev.get("public_trust")) or 0)
            service_delta = (_safe_float(merged.get("service_capacity")) or 0) - (_safe_float(prev.get("service_capacity")) or 0)
            if abs(panic_delta) < 0.5 and abs(trust_delta) < 0.5 and abs(service_delta) < 0.5:
                continue
            summary = f"{merged.get('name') or key} 在相邻轮次中出现情绪/信任/服务能力联动变化。"
            derived.append({
                "id": f"derived-{key}",
                "round": current.get("round"),
                "region_id": merged.get("region_id"),
                "region_name": merged.get("name") or key,
                "loop": summary,
                "delta": {
                    "panic_level": round(panic_delta, 2),
                    "public_trust": round(trust_delta, 2),
                    "service_capacity": round(service_delta, 2),
                },
                "source": "derived_from_round_snapshots",
                "source_type": "多轮推断",
            })
        return derived

    def _build_feedback_tab(self) -> Dict[str, Any]:
        feedback = self.latest_snapshot.get("feedback") if isinstance(self.latest_snapshot.get("feedback"), dict) else {}
        items: List[Dict[str, Any]] = []
        for idx, item in enumerate(feedback.get("feedback_propagation") or []):
            if not isinstance(item, dict):
                continue
            items.append({
                "id": f"feedback-{idx}",
                "round": self._get_default_round(),
                "region_id": item.get("region_id"),
                "region_name": item.get("region_name") or item.get("region_id"),
                "loop": item.get("loop"),
                "delta": item.get("delta") or {},
                "source": "latest_snapshot.feedback.feedback_propagation",
                "source_type": "直接观测",
            })
        if not items:
            items = self._derive_feedback_fallback()

        ecological_impacts = []
        for idx, item in enumerate(feedback.get("ecological_impacts") or []):
            if not isinstance(item, dict):
                continue
            ecological_impacts.append({
                "id": f"eco-{idx}",
                "round": self._get_default_round(),
                "region_id": item.get("region_id"),
                "region_name": item.get("region_name") or item.get("region_id"),
                "note": item.get("note"),
                "delta": item.get("delta") or {},
                "source": "latest_snapshot.feedback.ecological_impacts",
                "source_type": "直接观测",
            })

        return {
            "tab": "feedback",
            "current_round": self._get_default_round(),
            "chain_template": ["生态/环境", "生计/社会", "市场/信任", "治理响应", "生态/环境"],
            "items": items,
            "ecological_impacts": ecological_impacts,
            "turning_points": feedback.get("turning_points") or [],
        }

    def _build_roles_tab(self) -> Dict[str, Any]:
        groups: Dict[str, Dict[str, Any]] = {}
        for key, meta in ROLE_GROUP_META.items():
            groups[key] = {
                "group_id": key,
                **meta,
                "node_count": 0,
                "sample_nodes": [],
                "latest_agents": [],
            }

        agents = self.latest_snapshot.get("agents") or []
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            group_id = self._classify_role_group(agent)
            group = groups[group_id]
            group["node_count"] += 1
            if len(group["sample_nodes"]) < 8:
                group["sample_nodes"].append({
                    "agent_id": agent.get("agent_id"),
                    "name": agent.get("name") or agent.get("agent_name"),
                    "agent_type": agent.get("agent_type"),
                    "agent_subtype": agent.get("agent_subtype"),
                    "primary_region": agent.get("primary_region"),
                })
            merged = _merge_state_vector(agent)
            group["latest_agents"].append(merged)

        payload = []
        for key, meta in groups.items():
            focus_metrics = meta["focus_metrics"]
            metric_avg: Dict[str, float] = {}
            for metric in focus_metrics:
                values = [_safe_float(item.get(metric)) for item in meta["latest_agents"]]
                values = [value for value in values if value is not None]
                if values:
                    metric_avg[metric] = round(sum(values) / len(values), 2)
            region_focus: Dict[str, List[float]] = defaultdict(list)
            primary_metric = focus_metrics[0]
            for item in meta["latest_agents"]:
                region_name = _normalize_text(item.get("primary_region"))
                value = _safe_float(item.get(primary_metric))
                if region_name and value is not None:
                    region_focus[region_name].append(value)
            dominant_regions = [
                {"region_name": region, "score": round(sum(values) / len(values), 2)}
                for region, values in sorted(region_focus.items(), key=lambda pair: sum(pair[1]) / len(pair[1]), reverse=True)[:5]
            ]

            payload.append({
                "group_id": key,
                "title": meta["title"],
                "description": meta["description"],
                "focus_metrics": [{"key": item, "label": METRIC_LABELS[item]} for item in focus_metrics],
                "node_count": meta["node_count"],
                "sample_nodes": meta["sample_nodes"],
                "metric_averages": metric_avg,
                "dominant_regions": dominant_regions,
            })

        return {
            "tab": "roles",
            "current_round": self._get_default_round(),
            "groups": payload,
        }

    def _build_narrative_tab(self) -> Dict[str, Any]:
        narratives: List[Dict[str, Any]] = []
        snapshots = self.round_snapshots or ([self.latest_snapshot] if self.latest_snapshot else [])
        for snap in snapshots:
            top_region = self._top_region(snap)
            top_region_name = _normalize_text((top_region or {}).get("name") or (top_region or {}).get("region_id")) or "未知区域"
            top_region_score = _safe_float((top_region or {}).get("vulnerability_score")) or 0

            feedback = snap.get("feedback") if isinstance(snap.get("feedback"), dict) else {}
            diffusion = snap.get("diffusion") if isinstance(snap.get("diffusion"), dict) else {}
            feedback_loop = ""
            propagation = feedback.get("feedback_propagation") or []
            if propagation and isinstance(propagation[0], dict):
                feedback_loop = _normalize_text(propagation[0].get("loop"))

            diffusion_ranking = diffusion.get("region_ranking") or []
            diffusion_name = ""
            if diffusion_ranking and isinstance(diffusion_ranking[0], dict):
                diffusion_name = _normalize_text(diffusion_ranking[0].get("name") or diffusion_ranking[0].get("region_id"))

            confidence = self._average_confidence(snap)
            uncertainty_text = (
                f"平均置信度 {confidence}，需关注隐含参数与未记录干预。"
                if confidence is not None
                else "当前轮缺少完整 uncertainty_band，结论需结合上下轮对照。"
            )

            headline = f"{top_region_name} 是本轮最关键变化区域，脆弱性达到 {round(top_region_score, 2)}。"
            amplifier = (
                f"主要放大器是反馈链“{feedback_loop}”。"
                if feedback_loop
                else f"主要传播信号来自 {diffusion_name or top_region_name} 的扩散/暴露累积。"
            )
            narratives.append({
                "round": snap.get("round"),
                "timestamp": snap.get("timestamp"),
                "headline": headline,
                "amplifier": amplifier,
                "uncertainty": uncertainty_text,
                "top_region": {
                    "name": top_region_name,
                    "vulnerability_score": round(top_region_score, 2),
                },
            })

        return {
            "tab": "narrative",
            "rounds": narratives,
        }

    def _build_report_tab(self) -> Dict[str, Any]:
        progress = ReportManager.get_progress(self.report_id)
        return {
            "tab": "report",
            "report": self.report.to_dict(),
            "progress": progress,
            "generated_sections": ReportManager.get_generated_sections(self.report_id),
        }

    def get_overview(self) -> Dict[str, Any]:
        analysis_graph = self._load_graph_data()
        dynamic_edges = self._load_dynamic_edges()
        analysis_ready = bool(
            (self.latest_snapshot and isinstance(self.latest_snapshot, dict))
            or self.round_snapshots
            or self.artifacts.get("region_graph")
            or self.artifacts.get("subregion_graph")
            or self.artifacts.get("risk_objects")
        )
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "report_status": self.report.status.value,
            "analysis_ready": analysis_ready,
            "search_mode": self.latest_snapshot.get("search_mode")
            or (self.simulation_state.search_mode if self.simulation_state else "fast"),
            "report_title": self.report.outline.title if self.report.outline else "",
            "report_summary": self.report.outline.summary if self.report.outline else "",
            "default_round": self._get_default_round(),
            "max_round": self.max_round,
            "latest_timestamp": self.latest_snapshot.get("timestamp"),
            "available_tabs": ["regions", "feedback", "roles", "narrative", "node-explore", "report"],
            "node_stats": {
                "region_count": len(self.artifacts.get("region_graph") or []),
                "subregion_count": len(self.artifacts.get("subregion_graph") or []),
                "agent_count": len(self._load_agent_catalog()),
                "risk_object_count": len(self.artifacts.get("risk_objects") or []),
                "dynamic_edge_count": len(dynamic_edges),
                "graph_node_count": analysis_graph.get("node_count", 0),
                "graph_edge_count": analysis_graph.get("edge_count", 0),
            },
        }

    def get_tab_data(self, tab_id: str) -> Dict[str, Any]:
        if tab_id == "regions":
            return self._build_regions_tab()
        if tab_id == "feedback":
            return self._build_feedback_tab()
        if tab_id == "roles":
            return self._build_roles_tab()
        if tab_id == "narrative":
            return self._build_narrative_tab()
        if tab_id == "report":
            return self._build_report_tab()
        raise ValueError(f"不支持的 tab: {tab_id}")

    def _node_by_id(self, graph_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {
            item.get("uuid"): item
            for item in graph_data.get("nodes") or []
            if isinstance(item, dict) and item.get("uuid")
        }

    def _edge_list(self, graph_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [item for item in graph_data.get("edges") or [] if isinstance(item, dict)]

    def _extract_agent_id(self, node: Dict[str, Any]) -> Optional[int]:
        if not isinstance(node, dict):
            return None
        attributes = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        for value in (node.get("agent_id"), attributes.get("agent_id")):
            if isinstance(value, int):
                return value
            if str(value or "").isdigit():
                return int(value)
        node_uuid = _normalize_text(node.get("uuid"))
        if node_uuid.startswith("agent::"):
            suffix = node_uuid.split("agent::", 1)[1]
            if suffix.isdigit():
                return int(suffix)
        return None

    def _match_node_kind(self, node: Dict[str, Any]) -> Tuple[str, bool]:
        node_id = _normalize_text(node.get("uuid"))
        node_name = _normalize_text(node.get("name"))
        node_name_l = node_name.lower()
        labels = [_normalize_text(item).lower() for item in node.get("labels") or []]

        if "subregion" in labels:
            return "subregion", True
        if "region" in labels:
            return "region", True
        if "riskobject" in labels:
            return "risk_object", True

        for item in self.latest_snapshot.get("regions") or []:
            merged = _merge_state_vector(item)
            if node_name == merged.get("name") or node_name == merged.get("region_id"):
                return "region", True

        for item in self.latest_snapshot.get("subregions") or []:
            merged = _merge_state_vector(item)
            if node_name == merged.get("name") or node_name == merged.get("region_id"):
                return "subregion", True

        for item in self.artifacts.get("risk_objects") or []:
            if node_id and node_id in (item.get("source_entity_uuids") or []):
                return "risk_object_related", True
            if node_name == _normalize_text(item.get("title")):
                return "risk_object", True

        matched_agent = self._find_agent_match(node)
        if matched_agent:
            agent_type = _normalize_text(matched_agent.get("agent_type")).lower()
            if agent_type == "governance":
                return "governance_agent", True
            if agent_type in {"ecology", "carrier"}:
                return "ecology_agent", True
            return "social_agent", True

        if any(label in {"organization", "agency", "publicfigure"} for label in labels):
            return "graph_role", False
        if any(token in node_name_l for token in ["风险", "risk", "market", "治理", "生态", "海流"]):
            return "concept", False
        return "general", False

    def _find_agent_match(self, node: Dict[str, Any], snapshot: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        target_agent_id = self._extract_agent_id(node)
        target_name = _normalize_text(node.get("name"))
        candidates = (snapshot or self.latest_snapshot).get("agents") or []
        if target_agent_id is not None:
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                raw_id = item.get("agent_id")
                if isinstance(raw_id, int) and raw_id == target_agent_id:
                    return item
                if str(raw_id or "").isdigit() and int(raw_id) == target_agent_id:
                    return item
        if not target_name:
            return None
        target_name_l = target_name.lower()
        for item in candidates:
            if not isinstance(item, dict):
                continue
            names = [
                _normalize_text(item.get("name")),
                _normalize_text(item.get("agent_name")),
            ]
            if any(target_name == name for name in names if name):
                return item
        for item in candidates:
            if not isinstance(item, dict):
                continue
            names = [
                _normalize_text(item.get("name")).lower(),
                _normalize_text(item.get("agent_name")).lower(),
            ]
            if any(target_name_l == name for name in names if name):
                return item
        for item in candidates:
            if not isinstance(item, dict):
                continue
            names = [
                _normalize_text(item.get("name")).lower(),
                _normalize_text(item.get("agent_name")).lower(),
            ]
            if any(target_name_l in name or name in target_name_l for name in names if name):
                return item
        return None

    def _extract_node_series(self, node: Dict[str, Any], round_range: Any) -> List[Dict[str, Any]]:
        target_name = _normalize_text(node.get("name"))
        target_id = _normalize_text(node.get("uuid"))
        series: List[Dict[str, Any]] = []

        for snapshot in self._filter_snapshots_by_range(round_range):
            round_id = snapshot.get("round")
            timestamp = snapshot.get("timestamp")

            matched = False
            for scope_key in ("regions", "subregions"):
                for item in snapshot.get(scope_key) or []:
                    if not isinstance(item, dict):
                        continue
                    merged = _merge_state_vector(item)
                    if target_name and target_name in {
                        _normalize_text(merged.get("name")),
                        _normalize_text(merged.get("region_id")),
                    }:
                        series.append({
                            "round": round_id,
                            "timestamp": timestamp,
                            "scope": scope_key[:-1],
                            "name": merged.get("name") or merged.get("region_id"),
                            "state": {metric: _safe_float(merged.get(metric)) for metric in METRIC_LABELS},
                        })
                        matched = True
                        break
                if matched:
                    break

            if matched:
                continue

            agent = self._find_agent_match(node, snapshot=snapshot)
            if agent:
                merged = _merge_state_vector(agent)
                series.append({
                    "round": round_id,
                    "timestamp": timestamp,
                    "scope": "agent",
                    "name": merged.get("name") or merged.get("agent_name"),
                    "state": {metric: _safe_float(merged.get(metric)) for metric in METRIC_LABELS},
                    "agent_type": merged.get("agent_type"),
                    "primary_region": merged.get("primary_region"),
                })
                continue

            for item in self.artifacts.get("risk_objects") or []:
                source_uuids = item.get("source_entity_uuids") or []
                if (target_id and target_id in source_uuids) or target_name == _normalize_text(item.get("title")):
                    series.append({
                        "round": round_id,
                        "timestamp": timestamp,
                        "scope": "risk_object",
                        "name": item.get("title"),
                        "state": {
                            "vulnerability_score": _safe_float(item.get("severity_score")),
                            "public_trust": None,
                            "panic_level": None,
                        },
                    })
                    break

        deduped: Dict[Tuple[int, str, str], Dict[str, Any]] = {}
        for item in series:
            round_id = item.get("round") or 0
            key = (int(round_id), _normalize_text(item.get("scope")), _normalize_text(item.get("name")))
            deduped[key] = item
        result = list(deduped.values())
        result.sort(key=lambda item: item.get("round") or 0)
        return result

    def _extract_node_feedback(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        target_agent_id = self._extract_agent_id(node)
        target_name = _normalize_text(node.get("name"))
        target_name_l = target_name.lower()
        feedback = self.latest_snapshot.get("feedback") if isinstance(self.latest_snapshot.get("feedback"), dict) else {}
        interactions = self.latest_snapshot.get("interactions") if isinstance(self.latest_snapshot.get("interactions"), dict) else {}
        events: List[Dict[str, Any]] = []

        for item in feedback.get("feedback_propagation") or []:
            if not isinstance(item, dict):
                continue
            region_name = _normalize_text(item.get("region_name") or item.get("region_id"))
            if target_name and target_name in {region_name, _normalize_text(item.get("region_id"))}:
                events.append({
                    "kind": "feedback_loop",
                    "summary": item.get("loop"),
                    "delta": item.get("delta") or {},
                    "round": self._get_default_round(),
                    "source_type": "直接观测",
                })

        for item in feedback.get("actor_decisions") or []:
            if not isinstance(item, dict):
                continue
            raw_agent_id = item.get("agent_id")
            agent_name = _normalize_text(item.get("name") or item.get("agent_name"))
            matched = False
            if target_agent_id is not None and (isinstance(raw_agent_id, int) or str(raw_agent_id or "").isdigit()):
                matched = int(raw_agent_id) == target_agent_id
            if not matched and target_name_l and agent_name:
                matched = target_name_l in agent_name.lower() or agent_name.lower() in target_name_l
            if matched:
                events.append({
                    "kind": "actor_decision",
                    "summary": item.get("rationale"),
                    "delta": item.get("delta") or {},
                    "round": self._get_default_round(),
                    "source_type": "直接观测",
                })

        for item in interactions.get("agent_environment_effects") or []:
            if not isinstance(item, dict):
                continue
            raw_agent_id = item.get("agent_id")
            agent_name = _normalize_text(item.get("agent_name"))
            region_name = _normalize_text(item.get("region_name"))
            matched = False
            if target_agent_id is not None and (isinstance(raw_agent_id, int) or str(raw_agent_id or "").isdigit()):
                matched = int(raw_agent_id) == target_agent_id
            if not matched and target_name_l:
                matched = (
                    (agent_name and (target_name_l in agent_name.lower() or agent_name.lower() in target_name_l))
                    or target_name == region_name
                )
            if matched:
                events.append({
                    "kind": "environment_effect",
                    "summary": f"{agent_name or target_name} 对 {region_name or '环境'} 产生状态变化。",
                    "delta": item.get("delta") or {},
                    "round": self._get_default_round(),
                    "source_type": "直接观测",
                })

        for turning_point in (feedback.get("turning_points") or []) + (interactions.get("turning_points") or []):
            text = _normalize_text(turning_point)
            if target_name_l and text and target_name_l in text.lower():
                events.append({
                    "kind": "turning_point",
                    "summary": text,
                    "delta": {},
                    "round": self._get_default_round(),
                    "source_type": "多轮推断",
                })

        return events[:12]

    def _extract_related_risk_objects(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        target_agent_id = self._extract_agent_id(node)
        target_name = _normalize_text(node.get("name"))
        target_id = _normalize_text(node.get("uuid"))
        results: List[Dict[str, Any]] = []
        for item in self.artifacts.get("risk_objects") or []:
            if not isinstance(item, dict):
                continue
            source_uuids = item.get("source_entity_uuids") or []
            region_scope = item.get("region_scope") or []
            text_blob = " ".join([
                _normalize_text(item.get("title")),
                _normalize_text(item.get("summary")),
                _normalize_text(item.get("why_now")),
            ]).lower()
            matched = False
            if target_id and target_id in source_uuids:
                matched = True
            elif target_name and target_name in region_scope:
                matched = True
            elif target_name and target_name.lower() in text_blob:
                matched = True
            elif target_agent_id is not None:
                for cluster in item.get("affected_clusters") or []:
                    if not isinstance(cluster, dict):
                        continue
                    actor_ids = cluster.get("actor_ids") or []
                    if any((isinstance(actor_id, int) and actor_id == target_agent_id) or (str(actor_id or "").isdigit() and int(actor_id) == target_agent_id) for actor_id in actor_ids):
                        matched = True
                        break

            if matched:
                results.append({
                    "risk_object_id": item.get("risk_object_id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "severity_score": item.get("severity_score"),
                    "source_type": (
                        "直接观测"
                        if (target_id and target_id in source_uuids) or target_agent_id is not None
                        else "图谱补全"
                    ),
                })
        return results[:6]

    def _build_node_subgraph(self, node_id: str) -> Dict[str, Any]:
        graph_data = self._load_graph_data()
        node_map = self._node_by_id(graph_data)
        edges = self._edge_list(graph_data)
        if node_id not in node_map:
            return {"nodes": [], "edges": [], "direct_neighbor_count": 0, "second_hop_count": 0}

        adjacency: Dict[str, List[str]] = defaultdict(list)
        edge_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            source = edge.get("source_node_uuid")
            target = edge.get("target_node_uuid")
            if not source or not target:
                continue
            adjacency[source].append(target)
            adjacency[target].append(source)
            key = tuple(sorted([source, target]))
            edge_map[key].append(edge)

        visited = {node_id: 0}
        queue: deque[Tuple[str, int]] = deque([(node_id, 0)])
        while queue and len(visited) < 18:
            current, hop = queue.popleft()
            if hop >= 2:
                continue
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited[neighbor] = hop + 1
                    queue.append((neighbor, hop + 1))
                    if len(visited) >= 18:
                        break

        direct_neighbor_count = sum(1 for hop in visited.values() if hop == 1)
        second_hop_count = sum(1 for hop in visited.values() if hop == 2)
        subgraph_nodes = []
        for item_id, hop in visited.items():
            node = node_map.get(item_id)
            if not node:
                continue
            subgraph_nodes.append({
                "uuid": node.get("uuid"),
                "name": node.get("name"),
                "labels": node.get("labels") or [],
                "summary": node.get("summary") or "",
                "hop": hop,
            })

        subgraph_edges: List[Dict[str, Any]] = []
        for key, bucket in edge_map.items():
            if key[0] in visited and key[1] in visited:
                for edge in bucket:
                    subgraph_edges.append({
                        "uuid": edge.get("uuid"),
                        "name": edge.get("name") or edge.get("fact_type") or "RELATED",
                        "fact": edge.get("fact") or "",
                        "source_node_uuid": edge.get("source_node_uuid"),
                        "target_node_uuid": edge.get("target_node_uuid"),
                        "source_node_name": edge.get("source_node_name"),
                        "target_node_name": edge.get("target_node_name"),
                    })
                    if len(subgraph_edges) >= 36:
                        break
            if len(subgraph_edges) >= 36:
                break

        return {
            "nodes": subgraph_nodes,
            "edges": subgraph_edges,
            "direct_neighbor_count": direct_neighbor_count,
            "second_hop_count": second_hop_count,
        }

    def get_node_context(self, node_id: str, round_range: Any = None) -> Dict[str, Any]:
        graph_data = self._load_graph_data()
        node_map = self._node_by_id(graph_data)
        node = node_map.get(node_id)
        if not node:
            raise ValueError(f"节点不存在: {node_id}")

        node_kind, is_core_node = self._match_node_kind(node)
        series = self._extract_node_series(node, round_range=round_range)
        feedback_events = self._extract_node_feedback(node)
        risk_objects = self._extract_related_risk_objects(node)
        subgraph = self._build_node_subgraph(node_id)

        missing_data: List[str] = []
        if not series:
            missing_data.append("缺少与该节点直接匹配的轮次级状态记录")
        if not feedback_events:
            missing_data.append("缺少与该节点直接关联的反馈/交互事件记录")
        if not subgraph.get("edges"):
            missing_data.append("缺少该节点的关系子图数据")

        exploration_mode = "full" if series else "static_relation"
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "node": {
                "uuid": node.get("uuid"),
                "name": node.get("name"),
                "labels": node.get("labels") or [],
                "summary": node.get("summary") or "",
                "attributes": node.get("attributes") or {},
                "created_at": node.get("created_at"),
            },
            "node_kind": node_kind,
            "is_core_node": is_core_node,
            "round_range": list(self._normalize_round_range(round_range)),
            "subgraph": subgraph,
            "time_series": series,
            "related_feedback": feedback_events,
            "related_risk_objects": risk_objects,
            "missing_data": missing_data,
            "supported_modes": {
                "context_ready": True,
                "can_chat": True,
                "can_deep_explore": bool(subgraph.get("nodes")),
                "exploration_mode": exploration_mode,
            },
        }

    def _build_deterministic_sections(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        node = context.get("node") or {}
        series = context.get("time_series") or []
        feedback_events = context.get("related_feedback") or []
        risk_objects = context.get("related_risk_objects") or []
        subgraph = context.get("subgraph") or {}
        node_kind = context.get("node_kind")
        missing_data = context.get("missing_data") or []

        overview_items = [
            {
                "label": "节点定位",
                "content": f"{node.get('name')} 属于 {node_kind}，当前探索模式为 {context.get('supported_modes', {}).get('exploration_mode')}.",
                "source_type": "图谱补全" if node_kind in {"general", "concept", "graph_role"} else "直接观测",
            },
            {
                "label": "关系范围",
                "content": f"一跳邻居 {subgraph.get('direct_neighbor_count', 0)} 个，二跳延展 {subgraph.get('second_hop_count', 0)} 个。",
                "source_type": "图谱补全",
            },
        ]

        timeline_items: List[Dict[str, Any]] = []
        if series:
            first = series[0]
            last = series[-1]
            first_state = first.get("state") or {}
            last_state = last.get("state") or {}
            deltas: List[str] = []
            for metric in ["vulnerability_score", "spread_pressure", "public_trust", "ecosystem_integrity", "livelihood_stability"]:
                start = _safe_float(first_state.get(metric))
                end = _safe_float(last_state.get(metric))
                if start is None or end is None:
                    continue
                delta = round(end - start, 2)
                if abs(delta) >= 0.5:
                    deltas.append(f"{METRIC_LABELS[metric]} {start} -> {end}（变化 {delta:+}）")
            if deltas:
                timeline_items.append({
                    "label": "跨轮次变化",
                    "content": "；".join(deltas[:4]),
                    "source_type": "直接观测",
                })
            timeline_items.append({
                "label": "时间覆盖",
                "content": f"已匹配 {len(series)} 个轮次记录，范围 {series[0].get('round')} - {series[-1].get('round')}。",
                "source_type": "直接观测",
            })
        else:
            timeline_items.append({
                "label": "时间序列缺口",
                "content": "当前没有与该节点直接匹配的轮次级状态记录，后续解释将以关系结构和最新快照为主。",
                "source_type": "多轮推断",
            })

        relation_items: List[Dict[str, Any]] = []
        for edge in (subgraph.get("edges") or [])[:6]:
            source_name = edge.get("source_node_name") or edge.get("source_node_uuid")
            target_name = edge.get("target_node_name") or edge.get("target_node_uuid")
            fact = _normalize_text(edge.get("fact"))
            content = f"{source_name} -> {edge.get('name')} -> {target_name}"
            if fact:
                content += f"；事实: {fact}"
            relation_items.append({
                "label": edge.get("name") or "关系链",
                "content": content,
                "source_type": "图谱补全",
            })
        if not relation_items:
            relation_items.append({
                "label": "关系缺失",
                "content": "当前没有可展示的关系边，无法构建更完整的传播链。",
                "source_type": "图谱补全",
            })

        event_items: List[Dict[str, Any]] = []
        for event in feedback_events[:6]:
            event_items.append({
                "label": event.get("kind") or "事件",
                "content": event.get("summary") or "无描述",
                "source_type": event.get("source_type") or "直接观测",
            })
        for risk in risk_objects[:3]:
            event_items.append({
                "label": "相关风险对象",
                "content": f"{risk.get('title')}，状态 {risk.get('status')}，严重度 {risk.get('severity_score')}",
                "source_type": risk.get("source_type") or "图谱补全",
            })
        if not event_items:
            event_items.append({
                "label": "反馈缺口",
                "content": "当前没有直接匹配到反馈 propagation、actor decisions 或 turning point。",
                "source_type": "多轮推断",
            })

        uncertainty_items = []
        if missing_data:
            for item in missing_data[:4]:
                uncertainty_items.append({
                    "label": "数据缺口",
                    "content": item,
                    "source_type": "多轮推断",
                })
        uncertainty_items.append({
            "label": "证据边界",
            "content": "直接观测优先来自 round snapshots / latest snapshot；关系解释来自图谱子图；缺失记录部分采用保守推断。",
            "source_type": "多轮推断",
        })

        return [
            {"id": "overview", "title": "节点概览", "items": overview_items},
            {"id": "timeline", "title": "跨轮次演化", "items": timeline_items},
            {"id": "relations", "title": "关键关系链", "items": relation_items},
            {"id": "events", "title": "关键反馈/交互事件", "items": event_items},
            {"id": "uncertainty", "title": "不确定性与证据", "items": uncertainty_items},
        ]

    def _generate_llm_sections(self, context: Dict[str, Any], deterministic_sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not Config.LLM_API_KEY:
            return deterministic_sections

        compact_context = {
            "node": context.get("node"),
            "node_kind": context.get("node_kind"),
            "is_core_node": context.get("is_core_node"),
            "round_range": context.get("round_range"),
            "time_series": (context.get("time_series") or [])[-8:],
            "related_feedback": (context.get("related_feedback") or [])[:8],
            "related_risk_objects": (context.get("related_risk_objects") or [])[:4],
            "subgraph": {
                "nodes": (context.get("subgraph") or {}).get("nodes", [])[:10],
                "edges": (context.get("subgraph") or {}).get("edges", [])[:10],
            },
            "missing_data": context.get("missing_data") or [],
            "deterministic_sections": deterministic_sections,
        }

        system_prompt = (
            "你是 EnvFish 结果分析模块中的节点探索助手。"
            "你只能依据提供的上下文输出，不能补造不存在的观测。"
            "请把信息整理成 5 个固定区块，每个区块给出 2-4 条条目。"
            "每条条目必须带 source_type，且只能是 直接观测、多轮推断、图谱补全 三者之一。"
        )
        user_prompt = f"""请输出 JSON 对象，格式如下：
{{
  "sections": [
    {{"id": "overview", "title": "节点概览", "items": [{{"label": "...", "content": "...", "source_type": "直接观测"}}]}},
    {{"id": "timeline", "title": "跨轮次演化", "items": []}},
    {{"id": "relations", "title": "关键关系链", "items": []}},
    {{"id": "events", "title": "关键反馈/交互事件", "items": []}},
    {{"id": "uncertainty", "title": "不确定性与证据", "items": []}}
  ]
}}

上下文：
{compact_context}
"""

        try:
            llm = LLMClient()
            result = llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=2400,
            )
            sections = result.get("sections")
            if isinstance(sections, list) and sections:
                return sections
        except Exception as exc:
            logger.warning(f"LLM 生成节点分析失败，回退到确定性卡片: {exc}")

        return deterministic_sections

    def explore_node(self, node_id: str, round_range: Any = None) -> Dict[str, Any]:
        start, end = self._normalize_round_range(round_range)
        cache_key = f"{self.report_id}:{node_id}:{start}:{end}"
        if cache_key in self._node_explore_cache:
            return self._node_explore_cache[cache_key]

        context = self.get_node_context(node_id=node_id, round_range=round_range)
        deterministic_sections = self._build_deterministic_sections(context)
        sections = self._generate_llm_sections(context, deterministic_sections)

        result = {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "node_id": node_id,
            "node_name": context.get("node", {}).get("name"),
            "analysis_mode": context.get("supported_modes", {}).get("exploration_mode"),
            "sections": sections,
            "missing_data": context.get("missing_data") or [],
            "generated_at": datetime.now().isoformat(),
        }
        self._node_explore_cache[cache_key] = result
        return result

    def chat_on_node(
        self,
        node_id: str,
        message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        round_range: Any = None,
    ) -> Dict[str, Any]:
        context = self.get_node_context(node_id=node_id, round_range=round_range)
        explore_result = self.explore_node(node_id=node_id, round_range=round_range)
        chat_history = chat_history or []

        if not Config.LLM_API_KEY:
            summary = f"{context.get('node', {}).get('name')} 当前可用的直接观测记录有 {len(context.get('time_series') or [])} 条，"
            summary += f"关系边 {len((context.get('subgraph') or {}).get('edges') or [])} 条。"
            if context.get("missing_data"):
                summary += " 数据缺口：" + "；".join(context.get("missing_data")[:3])
            return {
                "response": summary,
                "analysis_mode": context.get("supported_modes", {}).get("exploration_mode"),
                "missing_data": context.get("missing_data") or [],
            }

        sections_text: List[str] = []
        for section in explore_result.get("sections") or []:
            section_title = section.get("title") or section.get("id")
            section_items = []
            for item in section.get("items") or []:
                section_items.append(
                    f"- [{item.get('source_type') or '多轮推断'}] {item.get('label')}: {item.get('content')}"
                )
            sections_text.append(section_title + "\n" + "\n".join(section_items))

        system_prompt = (
            "你是 EnvFish 节点探索对话助手。"
            "你只能围绕当前节点上下文回答，不能退化成全局报告问答。"
            "回答要简洁、明确，并在关键判断前标注 [直接观测] / [多轮推断] / [图谱补全]。"
            "如果上下文没有证据，直接说明缺少哪些数据。"
        )
        sections_summary = "\n\n".join(sections_text)
        messages = [{"role": "system", "content": system_prompt}]
        messages.append({
            "role": "user",
            "content": (
                f"当前节点: {context.get('node', {}).get('name')} ({context.get('node_kind')})\n"
                f"轮次范围: {context.get('round_range')}\n"
                f"缺失数据: {context.get('missing_data')}\n\n"
                f"分析卡摘要:\n{sections_summary}"
            ),
        })
        for item in chat_history[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        llm = LLMClient()
        response = llm.chat(messages=messages, temperature=0.2, max_tokens=1200)
        return {
            "response": response,
            "analysis_mode": context.get("supported_modes", {}).get("exploration_mode"),
            "missing_data": context.get("missing_data") or [],
        }
