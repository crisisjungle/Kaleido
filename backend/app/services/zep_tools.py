"""
Zep检索工具服务
封装图谱搜索、节点读取、边查询等工具，供Report Agent使用

核心检索工具（优化后）：
1. InsightForge（深度洞察检索）- 最强大的混合检索，自动生成子问题并多维度检索
2. PanoramaSearch（广度搜索）- 获取全貌，包括过期内容
3. QuickSearch（简单搜索）- 快速检索
"""

import csv
import json
import os
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .risk_projection import build_legacy_risk_summary, project_legacy_risk_objects

logger = get_logger('envfish.zep_tools')


@dataclass
class SearchResult:
    """搜索结果"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式，供LLM理解"""
        text_parts = [f"搜索查询: {self.query}", f"找到 {self.total_count} 条相关信息"]
        
        if self.facts:
            text_parts.append("\n### 相关事实:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """节点信息"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """转换为文本格式"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), "未知类型")
        return f"实体: {self.name} (类型: {entity_type})\n摘要: {self.summary}"


@dataclass
class EdgeInfo:
    """边信息"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # 时间信息
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """转换为文本格式"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"关系: {source} --[{self.name}]--> {target}\n事实: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or "未知"
            invalid_at = self.invalid_at or "至今"
            base_text += f"\n时效: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (已过期: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """是否已失效"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    深度洞察检索结果 (InsightForge)
    包含多个子问题的检索结果，以及综合分析
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # 各维度检索结果
    semantic_facts: List[str] = field(default_factory=list)  # 语义搜索结果
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # 实体洞察
    relationship_chains: List[str] = field(default_factory=list)  # 关系链
    
    # 统计信息
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """转换为详细的文本格式，供LLM理解"""
        text_parts = [
            f"## 未来预测深度分析",
            f"分析问题: {self.query}",
            f"预测场景: {self.simulation_requirement}",
            f"\n### 预测数据统计",
            f"- 相关预测事实: {self.total_facts}条",
            f"- 涉及实体: {self.total_entities}个",
            f"- 关系链: {self.total_relationships}条"
        ]
        
        # 子问题
        if self.sub_queries:
            text_parts.append(f"\n### 分析的子问题")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        # 语义搜索结果
        if self.semantic_facts:
            text_parts.append(f"\n### 【关键事实】(请在报告中引用这些原文)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 实体洞察
        if self.entity_insights:
            text_parts.append(f"\n### 【核心实体】")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', '未知')}** ({entity.get('type', '实体')})")
                if entity.get('summary'):
                    text_parts.append(f"  摘要: \"{entity.get('summary')}\"")
                if entity.get('related_facts'):
                    text_parts.append(f"  相关事实: {len(entity.get('related_facts', []))}条")
        
        # 关系链
        if self.relationship_chains:
            text_parts.append(f"\n### 【关系链】")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    广度搜索结果 (Panorama)
    包含所有相关信息，包括过期内容
    """
    query: str
    
    # 全部节点
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # 全部边（包括过期的）
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # 当前有效的事实
    active_facts: List[str] = field(default_factory=list)
    # 已过期/失效的事实（历史记录）
    historical_facts: List[str] = field(default_factory=list)
    
    # 统计
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式（完整版本，不截断）"""
        text_parts = [
            f"## 广度搜索结果（未来全景视图）",
            f"查询: {self.query}",
            f"\n### 统计信息",
            f"- 总节点数: {self.total_nodes}",
            f"- 总边数: {self.total_edges}",
            f"- 当前有效事实: {self.active_count}条",
            f"- 历史/过期事实: {self.historical_count}条"
        ]
        
        # 当前有效的事实（完整输出，不截断）
        if self.active_facts:
            text_parts.append(f"\n### 【当前有效事实】(模拟结果原文)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 历史/过期事实（完整输出，不截断）
        if self.historical_facts:
            text_parts.append(f"\n### 【历史/过期事实】(演变过程记录)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # 关键实体（完整输出，不截断）
        if self.all_nodes:
            text_parts.append(f"\n### 【涉及实体】")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "实体")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


def _safe_read_json(path: str, default: Optional[Any] = None) -> Any:
    """安全读取 JSON 文件，失败则返回默认值。"""
    if not path or not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"读取 JSON 失败: {path}, error={e}")
        return default


def _safe_read_jsonl(path: str) -> List[Dict[str, Any]]:
    """安全读取 JSONL 文件。"""
    if not path or not os.path.exists(path):
        return []

    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if isinstance(data, dict):
                        rows.append(data)
                    else:
                        rows.append({"value": data})
                except json.JSONDecodeError:
                    rows.append({"raw": line})
    except Exception as e:
        logger.debug(f"读取 JSONL 失败: {path}, error={e}")
    return rows


def _safe_read_csv(path: str) -> List[Dict[str, Any]]:
    """安全读取 CSV 文件。"""
    if not path or not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(row) for row in reader]
    except Exception as e:
        logger.debug(f"读取 CSV 失败: {path}, error={e}")
        return []


def _find_first_existing(root_dir: str, candidate_names: List[str]) -> Optional[str]:
    """在目录树中查找第一个匹配的文件。"""
    if not os.path.exists(root_dir):
        return None

    for candidate in candidate_names:
        direct = os.path.join(root_dir, candidate)
        if os.path.exists(direct):
            return direct

    for base, _, files in os.walk(root_dir):
        for candidate in candidate_names:
            if candidate in files:
                return os.path.join(base, candidate)

    return None


def _normalize_name(value: Any, fallback: str = "") -> str:
    """将任意值转成可展示的名称。"""
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _clamp_score(value: Any) -> float:
    """将分数限制在 0-100 之间。"""
    try:
        return max(0.0, min(100.0, float(value)))
    except Exception:
        return 0.0


def _format_multi_value(value: Any) -> str:
    """把单值或列表值格式化成可读文本。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = [_normalize_name(item, "") for item in value]
        parts = [part for part in parts if part]
        return "、".join(parts)
    if isinstance(value, dict):
        parts = [_normalize_name(v, "") for v in value.values()]
        parts = [part for part in parts if part]
        return "、".join(parts)
    return _normalize_name(value, "")


@dataclass
class EnvFishArtifactBundle:
    """EnvFish 模拟工件集合。"""

    simulation_id: str
    simulation_dir: str
    available: bool = False
    engine_mode: str = "unknown"
    scenario_mode: str = ""
    diffusion_template: str = ""
    simulation_config: Dict[str, Any] = field(default_factory=dict)
    env_status: Dict[str, Any] = field(default_factory=dict)
    grounding_summary: Dict[str, Any] = field(default_factory=dict)
    region_graph: Any = field(default_factory=dict)
    subregion_graph: Any = field(default_factory=dict)
    risk_definitions: List[Dict[str, Any]] = field(default_factory=list)
    latest_risk_runtime_state: Dict[str, Any] = field(default_factory=dict)
    risk_runtime_state: List[Dict[str, Any]] = field(default_factory=list)
    risk_events: List[Dict[str, Any]] = field(default_factory=list)
    risk_objects: List[Dict[str, Any]] = field(default_factory=list)
    risk_object_summary: Dict[str, Any] = field(default_factory=dict)
    regional_state_matrix: Any = field(default_factory=dict)
    latest_round_snapshot: Dict[str, Any] = field(default_factory=dict)
    spread_events: List[Dict[str, Any]] = field(default_factory=list)
    intervention_log: List[Dict[str, Any]] = field(default_factory=list)
    feedback_loops: List[Dict[str, Any]] = field(default_factory=list)
    interviews: List[Dict[str, Any]] = field(default_factory=list)
    legacy_actions: List[Dict[str, Any]] = field(default_factory=list)
    raw_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "simulation_dir": self.simulation_dir,
            "available": self.available,
            "engine_mode": self.engine_mode,
            "scenario_mode": self.scenario_mode,
            "diffusion_template": self.diffusion_template,
            "simulation_config": self.simulation_config,
            "env_status": self.env_status,
            "grounding_summary": self.grounding_summary,
            "region_graph": self.region_graph,
            "subregion_graph": self.subregion_graph,
            "risk_definitions": self.risk_definitions,
            "latest_risk_runtime_state": self.latest_risk_runtime_state,
            "risk_runtime_state": self.risk_runtime_state,
            "risk_events": self.risk_events,
            "risk_objects": self.risk_objects,
            "risk_object_summary": self.risk_object_summary,
            "regional_state_matrix": self.regional_state_matrix,
            "latest_round_snapshot": self.latest_round_snapshot,
            "spread_events": self.spread_events,
            "intervention_log": self.intervention_log,
            "feedback_loops": self.feedback_loops,
            "interviews": self.interviews,
            "legacy_actions": self.legacy_actions,
            "raw_files": self.raw_files,
        }

    def _config_value(self, *keys: str) -> str:
        for key in keys:
            value = self.simulation_config.get(key)
            if value not in (None, "", [], {}):
                return _normalize_name(value)
        return ""

    def _as_list(self, value: Any) -> List[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, dict):
            return list(value.values())
        return [value]

    def _get_latest_snapshot(self) -> Dict[str, Any]:
        snapshot = self.latest_round_snapshot
        if isinstance(snapshot, dict) and snapshot:
            return snapshot

        source = self.regional_state_matrix
        if isinstance(source, list):
            for item in reversed(source):
                if isinstance(item, dict) and any(
                    key in item for key in ("regions", "top_regions", "diffusion", "feedback", "vulnerability_ranking")
                ):
                    return item

        if isinstance(source, dict) and any(
            key in source for key in ("regions", "top_regions", "diffusion", "feedback", "vulnerability_ranking")
        ):
            return source

        return {}

    def _preferred_risk_definitions(self) -> List[Dict[str, Any]]:
        if isinstance(self.risk_definitions, list) and self.risk_definitions:
            return [item for item in self.risk_definitions if isinstance(item, dict)]
        config_defs = self.simulation_config.get("risk_definitions") if isinstance(self.simulation_config, dict) else []
        if isinstance(config_defs, list):
            return [item for item in config_defs if isinstance(item, dict)]
        return []

    def _preferred_runtime_state(self) -> Dict[str, Any]:
        if isinstance(self.latest_risk_runtime_state, dict) and self.latest_risk_runtime_state:
            return self.latest_risk_runtime_state
        config_runtime = self.simulation_config.get("latest_risk_runtime_state") if isinstance(self.simulation_config, dict) else {}
        if isinstance(config_runtime, dict):
            return config_runtime
        return {}

    def _preferred_risk_events(self) -> List[Dict[str, Any]]:
        if isinstance(self.risk_events, list) and self.risk_events:
            return [item for item in self.risk_events if isinstance(item, dict)]
        config_events = self.simulation_config.get("risk_events") if isinstance(self.simulation_config, dict) else []
        if isinstance(config_events, list):
            return [item for item in config_events if isinstance(item, dict)]
        return []

    def _preferred_risk_objects(self) -> List[Dict[str, Any]]:
        definitions = self._preferred_risk_definitions()
        if definitions:
            projected = project_legacy_risk_objects(definitions, self._preferred_runtime_state())
            if projected:
                return projected
        if isinstance(self.risk_objects, list):
            return [item for item in self.risk_objects if isinstance(item, dict)]
        config_risks = self.simulation_config.get("risk_objects") if isinstance(self.simulation_config, dict) else []
        if isinstance(config_risks, list):
            return [item for item in config_risks if isinstance(item, dict)]
        return []

    def _preferred_risk_summary(self) -> Dict[str, Any]:
        runtime_state = self._preferred_runtime_state()
        summary = build_legacy_risk_summary(
            self._preferred_risk_objects(),
            primary_risk_object_id=str(self.risk_object_summary.get("primary_risk_object_id") or ""),
            generation_notes=list(self.risk_object_summary.get("generation_notes") or []),
            primary_active_risk_id=str(runtime_state.get("primary_active_risk_id") or ""),
            pinned_risk_ids=list(runtime_state.get("pinned_risk_ids") or []),
        )
        summary["risk_definition_count"] = len(self._preferred_risk_definitions())
        summary["risk_runtime_state_count"] = len(self.risk_runtime_state or [])
        summary["risk_event_count"] = len(self._preferred_risk_events())
        summary["risk_object_count"] = summary.get("risk_objects_count", 0)
        return summary

    def _latest_risk_runtime_state_label(self) -> str:
        runtime_state = self._preferred_runtime_state()
        if not runtime_state:
            return ""
        primary = runtime_state.get("primary_active_risk") or {}
        if isinstance(primary, dict):
            return _normalize_name(primary.get("title") or primary.get("risk_id"), "")
        primary_id = runtime_state.get("primary_active_risk_id")
        if primary_id:
            return _normalize_name(primary_id, "")
        return ""

    def _extract_region_state_records(self) -> List[Dict[str, Any]]:
        source = self.regional_state_matrix or self._get_latest_snapshot()
        records: List[Dict[str, Any]] = []

        if isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    if "round" in item and isinstance(item.get("regions"), list):
                        round_id = item.get("round")
                        for region_entry in item.get("regions", []):
                            if isinstance(region_entry, dict):
                                row = dict(region_entry)
                                row.setdefault("round", round_id)
                                records.append(row)
                    else:
                        records.append(dict(item))
                else:
                    records.append({"value": item})
            return records

        if not isinstance(source, dict):
            return records

        if isinstance(source.get("regions"), list):
            region_list = source.get("regions", [])
            for region_entry in region_list:
                if isinstance(region_entry, dict):
                    records.append(dict(region_entry))
                else:
                    records.append({"region": region_entry})
            return records

        for key in ("state_history", "rounds", "snapshots", "timeline"):
            if isinstance(source.get(key), list):
                for item in source.get(key, []):
                    if isinstance(item, dict):
                        if isinstance(item.get("regions"), list):
                            round_id = item.get("round")
                            for region_entry in item.get("regions", []):
                                if isinstance(region_entry, dict):
                                    row = dict(region_entry)
                                    row.setdefault("round", round_id)
                                    records.append(row)
                        else:
                            records.append(dict(item))
                    else:
                        records.append({"value": item})
                if records:
                    return records

        if source and all(not isinstance(v, (list, dict)) for v in source.values()):
            for region_name, state in source.items():
                row = {"region": region_name}
                if isinstance(state, dict):
                    row.update(state)
                else:
                    row["value"] = state
                records.append(row)
            return records

        for key, value in source.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("region", key)
                records.append(row)
            else:
                records.append({"region": key, "value": value})
        return records

    def _extract_event_records(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        for event in events or []:
            if isinstance(event, dict):
                records.append(dict(event))
            else:
                records.append({"value": event})
        return records

    def _extract_actor_profiles(self) -> List[Dict[str, Any]]:
        profiles: List[Dict[str, Any]] = []
        seen: set = set()

        def append_profile(name: str, role: str, bio: str, persona: str = "", topic: str = ""):
            key = (name, role, bio)
            if key in seen:
                return
            seen.add(key)
            profiles.append({
                "realname": name,
                "username": name,
                "profession": role,
                "bio": bio,
                "persona": persona or bio,
                "interested_topics": [topic] if topic else []
            })

        config_profiles = self.simulation_config.get("agent_profiles") or self.simulation_config.get("profiles")
        if isinstance(config_profiles, list):
            for item in config_profiles:
                if not isinstance(item, dict):
                    continue
                append_profile(
                    name=_normalize_name(item.get("realname") or item.get("name") or item.get("username"), "EnvFish角色"),
                    role=_normalize_name(item.get("profession") or item.get("role") or item.get("type"), "环境角色"),
                    bio=_normalize_name(item.get("bio") or item.get("persona") or item.get("description"), "EnvFish模拟角色"),
                    persona=_normalize_name(item.get("persona") or item.get("bio"), ""),
                    topic=_normalize_name(item.get("topic") or item.get("interest"), "")
                )

        graph_entities: List[Any] = []
        if isinstance(self.region_graph, dict):
            graph_entities = self.region_graph.get("entities") or self.region_graph.get("nodes") or []
        elif isinstance(self.region_graph, list):
            graph_entities = self.region_graph
        if isinstance(graph_entities, list):
            for item in graph_entities:
                if not isinstance(item, dict):
                    continue
                labels = [str(label) for label in self._as_list(item.get("labels") or item.get("types"))]
                role = _normalize_name(item.get("type") or item.get("category") or (labels[0] if labels else ""), "环境角色")
                if role.lower() in {"region", "environment", "environmentalcarrier"}:
                    continue
                name = _normalize_name(item.get("name") or item.get("title") or item.get("id"), role)
                bio = _normalize_name(item.get("summary") or item.get("description") or item.get("persona"), role)
                append_profile(
                    name=name,
                    role=role,
                    bio=bio,
                    persona=_normalize_name(item.get("persona") or bio, ""),
                    topic=_normalize_name(item.get("topic") or item.get("focus"), "")
                )

        if not profiles:
            for item in self._extract_region_state_records():
                role = _normalize_name(item.get("role") or item.get("type") or item.get("category"), "")
                region = _normalize_name(item.get("region") or item.get("name"), "")
                if not region:
                    continue
                if role.lower() in {"region", "environment", "carrier"}:
                    continue
                append_profile(
                    name=region,
                    role=role or "环境相关角色",
                    bio=_normalize_name(item.get("summary") or item.get("note") or item.get("description"), "EnvFish受访对象")
                )

        return profiles

    def _score_summary(self) -> Dict[str, Any]:
        region_records = self._extract_region_state_records()
        if not region_records:
            return {
                "top_regions": [],
                "top_vulnerable": [],
                "average_scores": {},
                "region_count": 0,
                "round_count": 0
            }

        metric_keys = [
            "exposure_score",
            "spread_pressure",
            "ecosystem_integrity",
            "livelihood_stability",
            "public_trust",
            "panic_level",
            "service_capacity",
            "response_capacity",
            "economic_stress",
            "vulnerability_score",
        ]
        region_scores: Dict[str, Dict[str, List[float]]] = {}
        round_ids = set()

        for record in region_records:
            region_name = _normalize_name(
                record.get("region") or record.get("region_name") or record.get("name") or record.get("location"),
                "未知区域"
            )
            round_value = record.get("round") or record.get("round_index") or record.get("step")
            if round_value is not None:
                round_ids.add(str(round_value))
            region_scores.setdefault(region_name, {})
            for key in metric_keys:
                value = record.get(key)
                if isinstance(value, (int, float)):
                    region_scores[region_name].setdefault(key, []).append(float(value))

        region_rankings: List[Dict[str, Any]] = []
        for region_name, metrics in region_scores.items():
            latest = {}
            averages = {}
            for key, values in metrics.items():
                if values:
                    latest[key] = round(values[-1], 2)
                    averages[key] = round(sum(values) / len(values), 2)
            vulnerability = latest.get("vulnerability_score")
            if vulnerability is None:
                vulnerability = max(
                    latest.get("exposure_score", 0.0),
                    latest.get("spread_pressure", 0.0),
                    latest.get("economic_stress", 0.0),
                    latest.get("panic_level", 0.0),
                ) - min(
                    latest.get("ecosystem_integrity", 100.0),
                    latest.get("livelihood_stability", 100.0),
                    latest.get("public_trust", 100.0),
                ) / 3.0
            vulnerability = _clamp_score(vulnerability)
            region_rankings.append({
                "region": region_name,
                "latest": latest,
                "average": averages,
                "vulnerability_score": round(float(vulnerability), 2),
                "exposure_score": round(_clamp_score(latest.get("exposure_score", 0.0)), 2),
                "spread_pressure": round(_clamp_score(latest.get("spread_pressure", 0.0)), 2),
                "panic_level": round(_clamp_score(latest.get("panic_level", 0.0)), 2),
                "public_trust": round(_clamp_score(latest.get("public_trust", 0.0)), 2),
            })

        region_rankings.sort(key=lambda item: (item["vulnerability_score"], item["spread_pressure"], item["exposure_score"]), reverse=True)

        avg_scores: Dict[str, float] = {}
        for key in metric_keys:
            values: List[float] = []
            for item in region_rankings:
                if key in item["average"]:
                    values.append(item["average"][key])
            if values:
                avg_scores[key] = round(sum(values) / len(values), 2)

        top_regions = []
        for item in region_rankings[:10]:
            top_regions.append({
                "region": item["region"],
                "vulnerability_score": item["vulnerability_score"],
                "exposure_score": item["exposure_score"],
                "spread_pressure": item["spread_pressure"],
                "panic_level": item["panic_level"],
                "public_trust": item["public_trust"],
            })

        return {
            "top_regions": top_regions,
            "top_vulnerable": region_rankings[:10],
            "average_scores": avg_scores,
            "region_count": len(region_rankings),
            "round_count": len(round_ids),
        }

    def _event_summary(self) -> Dict[str, Any]:
        spread_events = self._extract_event_records(self.spread_events)
        intervention_events = self._extract_event_records(self.intervention_log)
        feedback_events = self._extract_event_records(self.feedback_loops)
        latest_snapshot = self._get_latest_snapshot()

        diffusion = latest_snapshot.get("diffusion") if isinstance(latest_snapshot.get("diffusion"), dict) else {}
        if not spread_events and diffusion:
            region_ranking = diffusion.get("region_ranking") or []
            likely_next = diffusion.get("likely_next_impacted_regions") or []
            for item in region_ranking:
                if not isinstance(item, dict):
                    continue
                spread_events.append({
                    "region_name": item.get("name") or item.get("region_name") or item.get("region") or item.get("region_id"),
                    "intensity": item.get("transfer_intensity")
                    or item.get("intensity")
                    or item.get("exposure_score")
                    or item.get("spread_pressure")
                    or item.get("severity")
                    or item.get("score")
                    or 0,
                    "severity_band": item.get("severity_band"),
                })
            if not spread_events:
                for region_name in likely_next:
                    spread_events.append({
                        "region_name": region_name,
                        "intensity": 0,
                    })

        feedback = latest_snapshot.get("feedback") if isinstance(latest_snapshot.get("feedback"), dict) else {}
        if not feedback_events and feedback:
            propagation = feedback.get("feedback_propagation") or []
            for item in propagation:
                if isinstance(item, dict):
                    feedback_events.append(dict(item))

        spread_rank: Dict[str, float] = {}
        for event in spread_events:
            for key in ("target_region", "region", "region_name", "target", "location"):
                name = _format_multi_value(event.get(key))
                if name:
                    intensity = event.get("transfer_intensity") or event.get("intensity") or event.get("severity") or 0
                    if isinstance(intensity, (int, float)):
                        spread_rank[name] = max(spread_rank.get(name, 0.0), float(intensity))
                    else:
                        spread_rank.setdefault(name, 0.0)

        ranked_spread = [
            {"region": region, "max_intensity": round(score, 2)}
            for region, score in sorted(spread_rank.items(), key=lambda item: item[1], reverse=True)
        ]

        intervention_types: Dict[str, int] = {}
        for event in intervention_events:
            mode = _format_multi_value(
                event.get("policy_mode") or event.get("mode") or event.get("type") or event.get("action"),
            )
            if not mode:
                mode = "unknown"
            intervention_types[mode] = intervention_types.get(mode, 0) + 1

        feedback_chains: List[str] = []
        for event in feedback_events[:20]:
            chain = _normalize_name(
                event.get("loop") or event.get("chain") or event.get("path") or event.get("summary") or event.get("description"),
                ""
            )
            if chain:
                region_name = _normalize_name(
                    event.get("region_name") or event.get("region") or event.get("region_id"),
                    "",
                )
                if region_name:
                    chain = f"{region_name}: {chain}"
                feedback_chains.append(chain)

        return {
            "spread_events": spread_events,
            "intervention_events": intervention_events,
            "feedback_events": feedback_events,
            "ranked_spread": ranked_spread,
            "intervention_types": intervention_types,
            "feedback_chains": feedback_chains,
        }

    def to_text(self, limit: int = 8) -> str:
        """返回 EnvFish 工件的长文本摘要。"""
        lines = [
            "## EnvFish 工件总览",
            f"- 模拟ID: {self.simulation_id}",
            f"- 工件状态: {'可用' if self.available else '未检测到完整 EnvFish 工件'}",
            f"- 引擎模式: {self.engine_mode or 'unknown'}",
            f"- 场景模式: {self.scenario_mode or 'unknown'}",
            f"- 扩散模板: {self.diffusion_template or 'unknown'}",
            f"- 工件文件数: {len(self.raw_files)}",
        ]

        if self.env_status:
            lines.append(f"- 当前运行状态: {_normalize_name(self.env_status.get('status') or self.env_status.get('state'), 'unknown')}")
            if self.env_status.get("current_round") is not None:
                lines.append(f"- 当前轮次: {self.env_status.get('current_round')}")

        if self.simulation_config:
            injected_variables = self.simulation_config.get("injected_variables") or []
            if injected_variables:
                lines.append(f"- 注入变量数: {len(injected_variables)}")
            risk_summary = self._preferred_risk_summary()
            if risk_summary.get("risk_definition_count"):
                lines.append(f"- 风险定义数: {risk_summary['risk_definition_count']}")
            if risk_summary.get("risk_objects_count"):
                lines.append(f"- 风险对象数: {risk_summary['risk_objects_count']}")
            primary_active_risk_id = risk_summary.get("primary_active_risk_id") or ""
            if primary_active_risk_id:
                lines.append(f"- 主活跃风险: {primary_active_risk_id}")
            elif risk_summary.get("primary_risk_object_id"):
                lines.append(f"- 主风险对象: {risk_summary['primary_risk_object_id']}")
            if risk_summary.get("risk_event_count"):
                lines.append(f"- 风险事件数: {risk_summary['risk_event_count']}")
            grounding = self.simulation_config.get("data_grounding_summary") or {}
            if grounding:
                lines.append(f"- 数据基线来源: {', '.join([k for k, v in grounding.items() if v]) or '未提供'}")

        score_summary = self._score_summary()
        event_summary = self._event_summary()

        lines.extend([
            "",
            "### 区域脆弱性概览",
        ])

        if score_summary["top_regions"]:
            for i, item in enumerate(score_summary["top_regions"][:limit], 1):
                lines.append(
                    f"{i}. {item['region']} | 脆弱性 {item['vulnerability_score']} | "
                    f"暴露 {item['exposure_score']} | 扩散压力 {item['spread_pressure']} | "
                    f"恐慌 {item['panic_level']} | 信任 {item['public_trust']}"
                )
        else:
            lines.append("（暂无可解析的区域状态记录）")

        lines.extend([
            "",
            "### 扩散与反馈概览",
        ])
        if event_summary["ranked_spread"]:
            for i, item in enumerate(event_summary["ranked_spread"][:limit], 1):
                lines.append(f"{i}. {item['region']} | 最大扩散强度 {item['max_intensity']}")
        else:
            lines.append("（暂无可解析的扩散事件）")

        if event_summary["feedback_chains"]:
            lines.extend(["", "### 关键反馈链"])
            for i, chain in enumerate(event_summary["feedback_chains"][:limit], 1):
                lines.append(f"{i}. {chain}")

        preferred_risk_objects = self._preferred_risk_objects()
        if preferred_risk_objects:
            lines.extend(["", "### 风险对象概览"])
            for i, item in enumerate(preferred_risk_objects[:limit], 1):
                title = _normalize_name(item.get("title"), f"风险对象 {i}")
                status = _normalize_name(item.get("status"), "unknown")
                severity = item.get("severity_score")
                why_now = _normalize_name(item.get("why_now"), "")
                line = f"{i}. {title} | 状态 {status}"
                if isinstance(severity, (int, float)):
                    line += f" | 严重度 {round(float(severity), 2)}"
                if why_now:
                    line += f" | why_now: {why_now}"
                lines.append(line)

        if event_summary["intervention_types"]:
            lines.extend(["", "### 干预类型分布"])
            for mode, count in sorted(event_summary["intervention_types"].items(), key=lambda item: item[1], reverse=True):
                lines.append(f"- {mode}: {count}")

        return "\n".join(lines)

    def to_fact_bullets(self, limit: int = 12) -> List[str]:
        """返回适合注入提示词的事实 bullet 列表。"""
        bullets = [
            f"场景模式: {self.scenario_mode or 'unknown'}",
            f"扩散模板: {self.diffusion_template or 'unknown'}",
            f"引擎模式: {self.engine_mode or 'unknown'}",
        ]
        preferred_risk_objects = self._preferred_risk_objects()
        if preferred_risk_objects:
            primary = self._preferred_risk_summary().get("primary_risk_object") or preferred_risk_objects[0]
            title = _normalize_name(primary.get("title"), "主风险对象")
            severity = primary.get("severity_score")
            bullets.append(
                f"主风险对象: {title}"
                + (f"，严重度 {round(float(severity), 2)}" if isinstance(severity, (int, float)) else "")
            )
            why_now = _normalize_name(primary.get("why_now"), "")
            if why_now:
                bullets.append(f"why_now: {why_now}")

        score_summary = self._score_summary()
        for item in score_summary["top_regions"][:limit]:
            bullets.append(
                f"区域 {item['region']} 的脆弱性为 {item['vulnerability_score']}，"
                f"暴露 {item['exposure_score']}，扩散压力 {item['spread_pressure']}，"
                f"恐慌 {item['panic_level']}，信任 {item['public_trust']}"
            )

        event_summary = self._event_summary()
        for item in event_summary["ranked_spread"][:limit]:
            bullets.append(f"扩散热点: {item['region']} 的最大扩散强度为 {item['max_intensity']}")
        for chain in event_summary["feedback_chains"][:limit]:
            bullets.append(f"反馈链: {chain}")

        if self.grounding_summary:
            sources = [name for name, value in self.grounding_summary.items() if value]
            if sources:
                bullets.append(f"数据基线来源: {', '.join(sources)}")

        if self.env_status:
            bullets.append(f"当前状态: {_normalize_name(self.env_status.get('status') or self.env_status.get('state'), 'unknown')}")

        return bullets[:limit] if limit and limit > 0 else bullets

    def regional_spread_text(self, limit: int = 8) -> str:
        """返回区域扩散摘要。"""
        score_summary = self._score_summary()
        event_summary = self._event_summary()
        lines = [
            "## 区域扩散预测",
            f"- 区域数量: {score_summary['region_count']}",
            f"- 推演轮次: {score_summary['round_count']}",
            "",
            "### 预测的高风险区域",
        ]

        if score_summary["top_regions"]:
            for i, item in enumerate(score_summary["top_regions"][:limit], 1):
                lines.append(
                    f"{i}. {item['region']}：脆弱性 {item['vulnerability_score']}，"
                    f"暴露 {item['exposure_score']}，扩散压力 {item['spread_pressure']}，"
                    f"恐慌 {item['panic_level']}，信任 {item['public_trust']}"
                )
        else:
            lines.append("（无法解析区域状态，改为输出事件级扩散信号）")

        if event_summary["ranked_spread"]:
            lines.extend(["", "### 观察到的扩散热点"])
            for i, item in enumerate(event_summary["ranked_spread"][:limit], 1):
                lines.append(f"{i}. {item['region']}：最大扩散强度 {item['max_intensity']}")

        return "\n".join(lines)

    def vulnerability_text(self, limit: int = 8) -> str:
        """返回脆弱区域与角色摘要。"""
        score_summary = self._score_summary()
        lines = [
            "## 脆弱性排序",
            f"- 区域数量: {score_summary['region_count']}",
        ]

        if score_summary["top_vulnerable"]:
            for i, item in enumerate(score_summary["top_vulnerable"][:limit], 1):
                latest = item.get("latest", {})
                lines.append(
                    f"{i}. {item['region']}：脆弱性 {item['vulnerability_score']}，"
                    f"暴露 {latest.get('exposure_score', 0)}，生态完整性 {latest.get('ecosystem_integrity', 0)}，"
                    f"生计稳定性 {latest.get('livelihood_stability', 0)}，治理能力 {latest.get('response_capacity', 0)}"
                )
        else:
            lines.append("（暂无可解析的区域状态记录）")

        if self.intervention_log:
            lines.extend(["", "### 相关干预"])
            for i, item in enumerate(self.intervention_log[:limit], 1):
                target = _format_multi_value(item.get("target_regions") or item.get("target_region") or item.get("target"))
                if not target:
                    target = "未知区域"
                mode = _normalize_name(item.get("policy_mode") or item.get("mode") or item.get("type"), "unknown")
                intensity = item.get("intensity_0_100") or item.get("intensity") or item.get("severity")
                lines.append(f"{i}. {mode} -> {target}，强度 {intensity if intensity is not None else 'unknown'}")

        return "\n".join(lines)

    def intervention_text(self, limit: int = 8) -> str:
        """返回干预比较摘要。"""
        event_summary = self._event_summary()
        lines = [
            "## 干预比较",
        ]

        if not self.intervention_log:
            lines.append("暂无可用的干预记录，无法做差异比较。")
            return "\n".join(lines)

        lines.append("### 已观察到的干预类型")
        for mode, count in sorted(event_summary["intervention_types"].items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {mode}: {count}")

        lines.append("")
        lines.append("### 干预事件样本")
        for i, item in enumerate(self.intervention_log[:limit], 1):
            target = _format_multi_value(item.get("target_regions") or item.get("target_region") or item.get("target"))
            if not target:
                target = "未知区域"
            mode = _normalize_name(item.get("policy_mode") or item.get("mode") or item.get("type") or item.get("action"), "unknown")
            outcome = _normalize_name(item.get("outcome") or item.get("result") or item.get("impact"), "")
            secondary = _normalize_name(item.get("secondary_risk") or item.get("secondary_effect"), "")
            line = f"{i}. {mode} -> {target}"
            if outcome:
                line += f"，结果 {outcome}"
            if secondary:
                line += f"，次生效应 {secondary}"
            lines.append(line)

        return "\n".join(lines)

    def feedback_text(self, limit: int = 8) -> str:
        """返回人类-自然反馈链摘要。"""
        event_summary = self._event_summary()
        lines = [
            "## 人类-自然反馈回路",
        ]

        if event_summary["feedback_chains"]:
            for i, chain in enumerate(event_summary["feedback_chains"][:limit], 1):
                lines.append(f"{i}. {chain}")
        else:
            lines.append("暂无独立的反馈链记录，改用扩散与干预事件推断。")
            for i, item in enumerate(event_summary["ranked_spread"][:limit], 1):
                lines.append(f"{i}. 扩散热点 {item['region']} 的最大强度 {item['max_intensity']}")

        return "\n".join(lines)


@dataclass
class AgentInterview:
    """单个Agent的采访结果"""
    agent_name: str
    agent_role: str  # 角色类型（如：学生、教师、媒体等）
    agent_bio: str  # 简介
    question: str  # 采访问题
    response: str  # 采访回答
    key_quotes: List[str] = field(default_factory=list)  # 关键引言
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        # 显示完整的agent_bio，不截断
        text += f"_简介: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**关键引言:**\n"
            for quote in self.key_quotes:
                # 清理各种引号
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                # 去掉开头的标点
                while clean_quote and clean_quote[0] in '，,；;：:、。！？\n\r\t ':
                    clean_quote = clean_quote[1:]
                # 过滤包含问题编号的垃圾内容（问题1-9）
                skip = False
                for d in '123456789':
                    if f'\u95ee\u9898{d}' in clean_quote:
                        skip = True
                        break
                if skip:
                    continue
                # 截断过长内容（按句号截断，而非硬截断）
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """
    采访结果 (Interview)
    包含多个模拟Agent的采访回答
    """
    interview_topic: str  # 采访主题
    interview_questions: List[str]  # 采访问题列表
    
    # 采访选择的Agent
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # 各Agent的采访回答
    interviews: List[AgentInterview] = field(default_factory=list)
    
    # 选择Agent的理由
    selection_reasoning: str = ""
    # 整合后的采访摘要
    summary: str = ""
    
    # 统计
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """转换为详细的文本格式，供LLM理解和报告引用"""
        text_parts = [
            "## 深度采访报告",
            f"**采访主题:** {self.interview_topic}",
            f"**采访人数:** {self.interviewed_count} / {self.total_agents} 位模拟Agent",
            "\n### 采访对象选择理由",
            self.selection_reasoning or "（自动选择）",
            "\n---",
            "\n### 采访实录",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### 采访 #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append("（无采访记录）\n\n---")

        text_parts.append("\n### 采访摘要与核心观点")
        text_parts.append(self.summary or "（无摘要）")

        return "\n".join(text_parts)


class ZepToolsService:
    """
    Zep检索工具服务
    
    【核心检索工具 - 优化后】
    1. insight_forge - 深度洞察检索（最强大，自动生成子问题，多维度检索）
    2. panorama_search - 广度搜索（获取全貌，包括过期内容）
    3. quick_search - 简单搜索（快速检索）
    4. interview_agents - 深度采访（采访模拟Agent，获取多视角观点）
    
    【基础工具】
    - search_graph - 图谱语义搜索
    - get_all_nodes - 获取图谱所有节点
    - get_all_edges - 获取图谱所有边（含时间信息）
    - get_node_detail - 获取节点详细信息
    - get_node_edges - 获取节点相关的边
    - get_entities_by_type - 按类型获取实体
    - get_entity_summary - 获取实体的关系摘要
    """
    
    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")
        
        self.client = Zep(api_key=self.api_key)
        # LLM客户端用于InsightForge生成子问题
        self._llm_client = llm_client
        logger.info("ZepToolsService 初始化完成")

    def _get_simulation_dir(self, simulation_id: str) -> str:
        """获取模拟目录路径。"""
        return os.path.join(Config.UPLOAD_FOLDER, "simulations", simulation_id)

    def _load_envfish_artifacts(self, simulation_id: str) -> EnvFishArtifactBundle:
        """加载 EnvFish 模拟工件，失败时返回空 bundle。"""
        sim_dir = self._get_simulation_dir(simulation_id)
        bundle = EnvFishArtifactBundle(
            simulation_id=simulation_id,
            simulation_dir=sim_dir,
        )

        if not os.path.exists(sim_dir):
            return bundle

        config_path = _find_first_existing(
            sim_dir,
            [
                "simulation_config.json",
                "envfish_config.json",
                "config.json",
            ],
        )
        status_path = _find_first_existing(
            sim_dir,
            [
                "env_status.json",
                "status.json",
            ],
        )
        summary_path = _find_first_existing(
            sim_dir,
            [
                "env_summary.json",
                "envfish_summary.json",
                "grounding_summary.json",
            ],
        )
        region_graph_path = _find_first_existing(
            sim_dir,
            [
                "region_graph.json",
                "region_graph_snapshot.json",
                "env_graph.json",
            ],
        )
        subregion_graph_path = _find_first_existing(
            sim_dir,
            [
                "subregion_graph.json",
                "subregion_graph_snapshot.json",
            ],
        )
        risk_objects_path = _find_first_existing(
            sim_dir,
            [
                "risk_objects.json",
            ],
        )
        risk_object_summary_path = _find_first_existing(
            sim_dir,
            [
                "risk_object_summary.json",
            ],
        )
        risk_definitions_path = _find_first_existing(
            sim_dir,
            [
                "risk_definitions.json",
            ],
        )
        latest_risk_runtime_state_path = _find_first_existing(
            sim_dir,
            [
                "latest_risk_runtime_state.json",
            ],
        )
        risk_runtime_state_jsonl = _find_first_existing(
            sim_dir,
            [
                "risk_runtime_state.jsonl",
            ],
        )
        risk_events_jsonl = _find_first_existing(
            sim_dir,
            [
                "risk_events.jsonl",
            ],
        )
        regional_state_path = _find_first_existing(
            sim_dir,
            [
                "regional_state_matrix.json",
                "regional_states.json",
                "round_state_matrix.json",
                "state_matrix.json",
                "state_history.json",
            ],
        )
        regional_state_jsonl = _find_first_existing(
            sim_dir,
            [
                "regional_state_matrix.jsonl",
                "regional_states.jsonl",
                "round_state_matrix.jsonl",
                "state_history.jsonl",
            ],
        )
        latest_round_snapshot_path = _find_first_existing(
            sim_dir,
            [
                "latest_round_snapshot.json",
                "round_snapshot_latest.json",
            ],
        )
        spread_events_jsonl = _find_first_existing(
            sim_dir,
            [
                "spread_events.jsonl",
                "diffusion_events.jsonl",
                "spread_ledger.jsonl",
            ],
        )
        spread_events_json = _find_first_existing(
            sim_dir,
            [
                "spread_events.json",
                "diffusion_events.json",
            ],
        )
        intervention_jsonl = _find_first_existing(
            sim_dir,
            [
                "intervention_log.jsonl",
                "interventions.jsonl",
                "policy_log.jsonl",
            ],
        )
        intervention_json = _find_first_existing(
            sim_dir,
            [
                "intervention_log.json",
                "interventions.json",
                "policy_log.json",
            ],
        )
        feedback_jsonl = _find_first_existing(
            sim_dir,
            [
                "feedback_loops.jsonl",
                "feedback_chain.jsonl",
                "feedback_events.jsonl",
            ],
        )
        feedback_json = _find_first_existing(
            sim_dir,
            [
                "feedback_loops.json",
                "feedback_chain.json",
                "feedback_events.json",
            ],
        )
        interviews_jsonl = _find_first_existing(
            sim_dir,
            [
                "interviews.jsonl",
                "envfish_interviews.jsonl",
            ],
        )
        interviews_json = _find_first_existing(
            sim_dir,
            [
                "interviews.json",
                "envfish_interviews.json",
            ],
        )

        bundle.simulation_config = _safe_read_json(config_path, {}) or {}
        bundle.env_status = _safe_read_json(status_path, {}) or {}
        bundle.grounding_summary = _safe_read_json(summary_path, {}) or {}
        bundle.region_graph = _safe_read_json(region_graph_path, {}) or {}
        bundle.subregion_graph = _safe_read_json(subregion_graph_path, {}) or {}
        bundle.risk_definitions = _safe_read_json(risk_definitions_path, []) or []
        bundle.latest_risk_runtime_state = _safe_read_json(latest_risk_runtime_state_path, {}) or {}
        bundle.risk_runtime_state = _safe_read_jsonl(risk_runtime_state_jsonl)
        bundle.risk_events = _safe_read_jsonl(risk_events_jsonl)
        risk_objects_data = _safe_read_json(risk_objects_path, []) or []
        bundle.risk_objects = risk_objects_data if isinstance(risk_objects_data, list) else []
        bundle.risk_object_summary = _safe_read_json(risk_object_summary_path, {}) or {}
        if bundle.risk_definitions:
            projected_risk_objects = project_legacy_risk_objects(bundle.risk_definitions, bundle.latest_risk_runtime_state)
            if projected_risk_objects:
                bundle.risk_objects = projected_risk_objects
                bundle.risk_object_summary = build_legacy_risk_summary(
                    projected_risk_objects,
                    primary_risk_object_id=str(bundle.risk_object_summary.get("primary_risk_object_id") or ""),
                    generation_notes=list(bundle.risk_object_summary.get("generation_notes") or []),
                    primary_active_risk_id=str(bundle.latest_risk_runtime_state.get("primary_active_risk_id") or ""),
                    pinned_risk_ids=list(bundle.latest_risk_runtime_state.get("pinned_risk_ids") or []),
                )
        bundle.latest_round_snapshot = _safe_read_json(latest_round_snapshot_path, {}) or {}
        bundle.regional_state_matrix = _safe_read_json(regional_state_path, {}) or _safe_read_jsonl(regional_state_jsonl)
        if not bundle.regional_state_matrix and bundle.latest_round_snapshot:
            bundle.regional_state_matrix = bundle.latest_round_snapshot
        bundle.spread_events = _safe_read_jsonl(spread_events_jsonl)
        if not bundle.spread_events:
            spread_json = _safe_read_json(spread_events_json, [])
            if isinstance(spread_json, list):
                bundle.spread_events = [item for item in spread_json if isinstance(item, dict)]
            elif isinstance(spread_json, dict):
                bundle.spread_events = [spread_json]
        bundle.intervention_log = _safe_read_jsonl(intervention_jsonl)
        if not bundle.intervention_log:
            intervention_json_data = _safe_read_json(intervention_json, [])
            if isinstance(intervention_json_data, list):
                bundle.intervention_log = [item for item in intervention_json_data if isinstance(item, dict)]
            elif isinstance(intervention_json_data, dict):
                bundle.intervention_log = [intervention_json_data]
        bundle.feedback_loops = _safe_read_jsonl(feedback_jsonl)
        if not bundle.feedback_loops:
            feedback_json_data = _safe_read_json(feedback_json, [])
            if isinstance(feedback_json_data, list):
                bundle.feedback_loops = [item for item in feedback_json_data if isinstance(item, dict)]
            elif isinstance(feedback_json_data, dict):
                bundle.feedback_loops = [feedback_json_data]
        bundle.interviews = _safe_read_jsonl(interviews_jsonl)
        if not bundle.interviews:
            interviews_json_data = _safe_read_json(interviews_json, [])
            if isinstance(interviews_json_data, list):
                bundle.interviews = [item for item in interviews_json_data if isinstance(item, dict)]
            elif isinstance(interviews_json_data, dict):
                bundle.interviews = [interviews_json_data]

        twitter_actions = _find_first_existing(sim_dir, ["twitter/actions.jsonl"])
        reddit_actions = _find_first_existing(sim_dir, ["reddit/actions.jsonl"])
        root_actions = _find_first_existing(sim_dir, ["actions.jsonl"])
        bundle.legacy_actions = (
            _safe_read_jsonl(twitter_actions)
            + _safe_read_jsonl(reddit_actions)
            + _safe_read_jsonl(root_actions)
        )

        config_mode = _normalize_name(
            bundle.simulation_config.get("engine_mode")
            or bundle.simulation_config.get("engine")
            or bundle.simulation_config.get("mode"),
            "",
        ).lower()
        if not config_mode and any(
            key in bundle.simulation_config
            for key in ("scenario_mode", "diffusion_template", "state_vector_schema", "injected_variables")
        ):
            config_mode = "envfish"

        artifact_signals = any([
            bool(bundle.grounding_summary),
            bool(bundle.region_graph),
            bool(bundle.subregion_graph),
            bool(bundle.risk_definitions),
            bool(bundle.latest_risk_runtime_state),
            bool(bundle.risk_runtime_state),
            bool(bundle.risk_events),
            bool(bundle.risk_objects),
            bool(bundle.regional_state_matrix),
            bool(bundle.latest_round_snapshot),
            bool(bundle.spread_events),
            bool(bundle.intervention_log),
            bool(bundle.feedback_loops),
        ])

        bundle.engine_mode = config_mode or ("envfish" if artifact_signals else "legacy")
        bundle.scenario_mode = _normalize_name(
            bundle.simulation_config.get("scenario_mode")
            or bundle.simulation_config.get("scenario")
            or bundle.env_status.get("scenario_mode"),
            "",
        )
        bundle.diffusion_template = _normalize_name(
            bundle.simulation_config.get("diffusion_template")
            or bundle.simulation_config.get("template")
            or bundle.env_status.get("diffusion_template"),
            "",
        )
        bundle.available = bundle.engine_mode == "envfish" or artifact_signals

        raw_files = []
        for candidate in [
            config_path,
            status_path,
            summary_path,
            region_graph_path,
            subregion_graph_path,
            risk_objects_path,
            risk_object_summary_path,
            risk_definitions_path,
            latest_risk_runtime_state_path,
            risk_runtime_state_jsonl,
            risk_events_jsonl,
            regional_state_path,
            regional_state_jsonl,
            latest_round_snapshot_path,
            spread_events_jsonl,
            spread_events_json,
            intervention_jsonl,
            intervention_json,
            feedback_jsonl,
            feedback_json,
            interviews_jsonl,
            interviews_json,
            twitter_actions,
            reddit_actions,
            root_actions,
        ]:
            if candidate and os.path.exists(candidate):
                raw_files.append(os.path.relpath(candidate, sim_dir))
        bundle.raw_files = raw_files

        if bundle.available and not bundle.scenario_mode:
            bundle.scenario_mode = _normalize_name(bundle.simulation_config.get("scenario_mode"), "envfish")
        if bundle.available and not bundle.diffusion_template:
            bundle.diffusion_template = _normalize_name(bundle.simulation_config.get("diffusion_template"), "generic")

        return bundle

    def get_envfish_summary(self, simulation_id: str, limit: int = 8) -> str:
        """获取 EnvFish 工件总览文本。"""
        bundle = self._load_envfish_artifacts(simulation_id)
        if not bundle.available:
            return "未检测到 EnvFish 工件，当前模拟仍按传统图谱/舆情模式处理。"
        return bundle.to_text(limit=limit)

    def get_envfish_regional_spread_summary(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_envfish_artifacts(simulation_id)
        if not bundle.available:
            return "未检测到 EnvFish 工件，无法生成区域扩散摘要。"
        return bundle.regional_spread_text(limit=limit)

    def get_envfish_vulnerability_ranking(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_envfish_artifacts(simulation_id)
        if not bundle.available:
            return "未检测到 EnvFish 工件，无法生成脆弱性排序。"
        return bundle.vulnerability_text(limit=limit)

    def get_envfish_intervention_comparison(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_envfish_artifacts(simulation_id)
        if not bundle.available:
            return "未检测到 EnvFish 工件，无法生成干预比较。"
        return bundle.intervention_text(limit=limit)

    def get_envfish_feedback_summary(self, simulation_id: str, limit: int = 8) -> str:
        bundle = self._load_envfish_artifacts(simulation_id)
        if not bundle.available:
            return "未检测到 EnvFish 工件，无法生成反馈回路摘要。"
        return bundle.feedback_text(limit=limit)

    def get_envfish_actor_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """从 EnvFish 工件中提取可采访对象。"""
        bundle = self._load_envfish_artifacts(simulation_id)
        if not bundle.available:
            return []
        return bundle._extract_actor_profiles()

    def _run_envfish_interview(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """基于 EnvFish 工件生成虚拟采访。"""
        bundle = self._load_envfish_artifacts(simulation_id)
        profiles = self.get_envfish_actor_profiles(simulation_id)
        if not profiles:
            profiles = self._load_agent_profiles(simulation_id)

        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )

        if not profiles:
            result.summary = "未找到可采访的EnvFish角色画像"
            return result

        result.total_agents = len(profiles)

        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning

        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )

        combined_prompt = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(result.interview_questions)])
        env_context_text = bundle.to_text(limit=8)
        import re

        for agent in selected_agents:
            agent_name = agent.get("realname", agent.get("username", "EnvFish角色"))
            agent_role = agent.get("profession", "环境角色")
            agent_bio = agent.get("bio", "") or agent.get("persona", "")

            system_prompt = (
                "你正在接受一次生态社会影响推演采访。"
                "你必须以第一人称自然语言回答问题，只能依据给定的人设、环境工件摘要和模拟背景。"
                "不要提及你是AI、模型或系统。"
                "回答时要体现你对污染扩散、生态反馈、社会压力和政策干预的真实反应。"
                "不要输出JSON或工具调用格式。"
            )
            user_prompt = f"""角色资料：
{json.dumps(agent, ensure_ascii=False, indent=2)}

EnvFish 工件摘要：
{env_context_text}

模拟背景：
{simulation_requirement if simulation_requirement else "（未提供）"}

采访主题：
{interview_requirement}

采访问题：
{combined_prompt}

请按问题编号逐一回答，每个问题至少 2-3 句话。"""

            try:
                response = self.llm.chat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.45,
                    max_tokens=1200
                )
            except Exception as e:
                logger.warning(f"EnvFish 虚拟采访失败: {e}")
                response = f"我认为当前局势正在改变区域生态和社会心理的平衡。{str(e)[:120]}"

            response = self._clean_tool_call_response(response or "")
            if not response:
                response = "（未能生成有效回答）"

            clean_text = re.sub(r'#{1,6}\s+', '', response)
            clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
            clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
            clean_text = re.sub(r'问题\d+[：:]\s*', '', clean_text)
            clean_text = re.sub(r'【[^】]+】', '', clean_text)
            sentences = re.split(r'[。！？]', clean_text)
            meaningful = [
                s.strip() for s in sentences
                if 20 <= len(s.strip()) <= 150
                and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                and not s.strip().startswith(('{', '问题'))
            ]
            meaningful.sort(key=len, reverse=True)
            key_quotes = [s + "。" for s in meaningful[:3]]

            interview = AgentInterview(
                agent_name=agent_name,
                agent_role=agent_role,
                agent_bio=agent_bio[:1000],
                question=combined_prompt,
                response=response,
                key_quotes=key_quotes[:5]
            )
            result.interviews.append(interview)

        result.interviewed_count = len(result.interviews)
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        return result
    
    @property
    def llm(self) -> LLMClient:
        """延迟初始化LLM客户端"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """带重试机制的API调用"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} 第 {attempt + 1} 次尝试失败: {str(e)[:100]}, "
                        f"{delay:.1f}秒后重试..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name} 在 {max_retries} 次尝试后仍失败: {str(e)}")
        
        raise last_exception
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        图谱语义搜索
        
        使用混合搜索（语义+BM25）在图谱中搜索相关信息。
        如果Zep Cloud的search API不可用，则降级为本地关键词匹配。
        
        Args:
            graph_id: 图谱ID (Standalone Graph)
            query: 搜索查询
            limit: 返回结果数量
            scope: 搜索范围，"edges" 或 "nodes"
            
        Returns:
            SearchResult: 搜索结果
        """
        logger.info(f"图谱搜索: graph_id={graph_id}, query={query[:50]}...")
        
        # 尝试使用Zep Cloud Search API
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=query,
                    limit=limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=f"图谱搜索(graph={graph_id})"
            )
            
            facts = []
            edges = []
            nodes = []
            
            # 解析边搜索结果
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })
            
            # 解析节点搜索结果
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # 节点摘要也算作事实
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"搜索完成: 找到 {len(facts)} 条相关事实")
            
            return SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )
            
        except Exception as e:
            logger.warning(f"Zep Search API失败，降级为本地搜索: {str(e)}")
            # 降级：使用本地关键词匹配搜索
            return self._local_search(graph_id, query, limit, scope)
    
    def _local_search(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        本地关键词匹配搜索（作为Zep Search API的降级方案）
        
        获取所有边/节点，然后在本地进行关键词匹配
        
        Args:
            graph_id: 图谱ID
            query: 搜索查询
            limit: 返回结果数量
            scope: 搜索范围
            
        Returns:
            SearchResult: 搜索结果
        """
        logger.info(f"使用本地搜索: query={query[:30]}...")
        
        facts = []
        edges_result = []
        nodes_result = []
        
        # 提取查询关键词（简单分词）
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            """计算文本与查询的匹配分数"""
            if not text:
                return 0
            text_lower = text.lower()
            # 完全匹配查询
            if query_lower in text_lower:
                return 100
            # 关键词匹配
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            if scope in ["edges", "both"]:
                # 获取所有边并匹配
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                # 按分数排序
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # 获取所有节点并匹配
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"本地搜索完成: 找到 {len(facts)} 条相关事实")
            
        except Exception as e:
            logger.error(f"本地搜索失败: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        获取图谱的所有节点（分页获取）

        Args:
            graph_id: 图谱ID

        Returns:
            节点列表
        """
        logger.info(f"获取图谱 {graph_id} 的所有节点...")

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', None) or ""
            result.append(NodeInfo(
                uuid=str(node_uuid) if node_uuid else "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))

        logger.info(f"获取到 {len(result)} 个节点")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        获取图谱的所有边（分页获取，包含时间信息）

        Args:
            graph_id: 图谱ID
            include_temporal: 是否包含时间信息（默认True）

        Returns:
            边列表（包含created_at, valid_at, invalid_at, expired_at）
        """
        logger.info(f"获取图谱 {graph_id} 的所有边...")

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )

            # 添加时间信息
            if include_temporal:
                edge_info.created_at = getattr(edge, 'created_at', None)
                edge_info.valid_at = getattr(edge, 'valid_at', None)
                edge_info.invalid_at = getattr(edge, 'invalid_at', None)
                edge_info.expired_at = getattr(edge, 'expired_at', None)

            result.append(edge_info)

        logger.info(f"获取到 {len(result)} 条边")
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        获取单个节点的详细信息
        
        Args:
            node_uuid: 节点UUID
            
        Returns:
            节点信息或None
        """
        logger.info(f"获取节点详情: {node_uuid[:8]}...")
        
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"获取节点详情(uuid={node_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"获取节点详情失败: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        获取节点相关的所有边
        
        通过获取图谱所有边，然后过滤出与指定节点相关的边
        
        Args:
            graph_id: 图谱ID
            node_uuid: 节点UUID
            
        Returns:
            边列表
        """
        logger.info(f"获取节点 {node_uuid[:8]}... 的相关边")
        
        try:
            # 获取图谱所有边，然后过滤
            all_edges = self.get_all_edges(graph_id)
            
            result = []
            for edge in all_edges:
                # 检查边是否与指定节点相关（作为源或目标）
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
            
            logger.info(f"找到 {len(result)} 条与节点相关的边")
            return result
            
        except Exception as e:
            logger.warning(f"获取节点边失败: {str(e)}")
            return []
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str
    ) -> List[NodeInfo]:
        """
        按类型获取实体
        
        Args:
            graph_id: 图谱ID
            entity_type: 实体类型（如 Student, PublicFigure 等）
            
        Returns:
            符合类型的实体列表
        """
        logger.info(f"获取类型为 {entity_type} 的实体...")
        
        all_nodes = self.get_all_nodes(graph_id)
        
        filtered = []
        for node in all_nodes:
            # 检查labels是否包含指定类型
            if entity_type in node.labels:
                filtered.append(node)
        
        logger.info(f"找到 {len(filtered)} 个 {entity_type} 类型的实体")
        return filtered
    
    def get_entity_summary(
        self, 
        graph_id: str, 
        entity_name: str
    ) -> Dict[str, Any]:
        """
        获取指定实体的关系摘要
        
        搜索与该实体相关的所有信息，并生成摘要
        
        Args:
            graph_id: 图谱ID
            entity_name: 实体名称
            
        Returns:
            实体摘要信息
        """
        logger.info(f"获取实体 {entity_name} 的关系摘要...")
        
        # 先搜索该实体相关的信息
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # 尝试在所有节点中找到该实体
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            # 传入graph_id参数
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        获取图谱的统计信息
        
        Args:
            graph_id: 图谱ID
            
        Returns:
            统计信息
        """
        logger.info(f"获取图谱 {graph_id} 的统计信息...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        # 统计实体类型分布
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        # 统计关系类型分布
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(
        self, 
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30,
        simulation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取模拟相关的上下文信息
        
        综合搜索与模拟需求相关的所有信息
        
        Args:
            graph_id: 图谱ID
            simulation_requirement: 模拟需求描述
            limit: 每类信息的数量限制
            
        Returns:
            模拟上下文信息
        """
        logger.info(f"获取模拟上下文: {simulation_requirement[:50]}...")

        envfish_bundle = self._load_envfish_artifacts(simulation_id) if simulation_id else EnvFishArtifactBundle(
            simulation_id="",
            simulation_dir="",
        )
        
        # 搜索与模拟需求相关的信息
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        # 获取图谱统计
        stats = self.get_graph_statistics(graph_id)
        
        # 获取所有实体节点
        all_nodes = self.get_all_nodes(graph_id)
        
        # 筛选有实际类型的实体（非纯Entity节点）
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })

        related_facts = list(search_result.facts)
        if envfish_bundle.available:
            env_fact_bullets = envfish_bundle.to_fact_bullets(limit=limit)
            for fact in env_fact_bullets:
                if fact not in related_facts:
                    related_facts.insert(0, fact)
            # 将工件摘要放入 related_facts 头部，便于报告规划和章节生成
            env_summary = envfish_bundle.to_text(limit=min(limit, 8))
            if env_summary not in related_facts:
                related_facts.insert(0, env_summary)

        context = {
            "simulation_requirement": simulation_requirement,
            "related_facts": related_facts,
            "graph_statistics": stats,
            "entities": entities[:limit],  # 限制数量
            "total_entities": len(entities),
            "simulation_kind": "envfish" if envfish_bundle.available else "legacy",
            "envfish_available": envfish_bundle.available,
            "simulation_id": simulation_id,
        }

        if envfish_bundle.available:
            context.update({
                "envfish": envfish_bundle.to_dict(),
                "envfish_summary": envfish_bundle.to_text(limit=min(limit, 8)),
                "envfish_fact_bullets": envfish_bundle.to_fact_bullets(limit=limit),
                "grounding_summary": envfish_bundle.grounding_summary,
            })

        return context
    
    # ========== 核心检索工具（优化后） ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        【InsightForge - 深度洞察检索】
        
        最强大的混合检索函数，自动分解问题并多维度检索：
        1. 使用LLM将问题分解为多个子问题
        2. 对每个子问题进行语义搜索
        3. 提取相关实体并获取其详细信息
        4. 追踪关系链
        5. 整合所有结果，生成深度洞察
        
        Args:
            graph_id: 图谱ID
            query: 用户问题
            simulation_requirement: 模拟需求描述
            report_context: 报告上下文（可选，用于更精准的子问题生成）
            max_sub_queries: 最大子问题数量
            
        Returns:
            InsightForgeResult: 深度洞察检索结果
        """
        logger.info(f"InsightForge 深度洞察检索: {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: 使用LLM生成子问题
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"生成 {len(sub_queries)} 个子问题")
        
        # Step 2: 对每个子问题进行语义搜索
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )
            
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            
            all_edges.extend(search_result.edges)
        
        # 对原始问题也进行搜索
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Step 3: 从边中提取相关实体UUID，只获取这些实体的信息（不获取全部节点）
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)
        
        # 获取所有相关实体的详情（不限制数量，完整输出）
        entity_insights = []
        node_map = {}  # 用于后续关系链构建
        
        for uuid in list(entity_uuids):  # 处理所有实体，不截断
            if not uuid:
                continue
            try:
                # 单独获取每个相关节点的信息
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "实体")
                    
                    # 获取该实体相关的所有事实（不截断）
                    related_facts = [
                        f for f in all_facts 
                        if node.name.lower() in f.lower()
                    ]
                    
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts  # 完整输出，不截断
                    })
            except Exception as e:
                logger.debug(f"获取节点 {uuid} 失败: {e}")
                continue
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: 构建所有关系链（不限制数量）
        relationship_chains = []
        for edge_data in all_edges:  # 处理所有边，不截断
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForge完成: {result.total_facts}条事实, {result.total_entities}个实体, {result.total_relationships}条关系")
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        使用LLM生成子问题
        
        将复杂问题分解为多个可以独立检索的子问题
        """
        system_prompt = """你是一个专业的问题分析专家。你的任务是将一个复杂问题分解为多个可以在模拟世界中独立观察的子问题。

要求：
1. 每个子问题应该足够具体，可以在模拟世界中找到相关的Agent行为或事件
2. 子问题应该覆盖原问题的不同维度（如：谁、什么、为什么、怎么样、何时、何地）
3. 子问题应该与模拟场景相关
4. 返回JSON格式：{"sub_queries": ["子问题1", "子问题2", ...]}"""

        user_prompt = f"""模拟需求背景：
{simulation_requirement}

{f"报告上下文：{report_context[:500]}" if report_context else ""}

请将以下问题分解为{max_queries}个子问题：
{query}

返回JSON格式的子问题列表。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # 确保是字符串列表
            return [str(sq) for sq in sub_queries[:max_queries]]
            
        except Exception as e:
            logger.warning(f"生成子问题失败: {str(e)}，使用默认子问题")
            # 降级：返回基于原问题的变体
            return [
                query,
                f"{query} 的主要参与者",
                f"{query} 的原因和影响",
                f"{query} 的发展过程"
            ][:max_queries]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        【PanoramaSearch - 广度搜索】
        
        获取全貌视图，包括所有相关内容和历史/过期信息：
        1. 获取所有相关节点
        2. 获取所有边（包括已过期/失效的）
        3. 分类整理当前有效和历史信息
        
        这个工具适用于需要了解事件全貌、追踪演变过程的场景。
        
        Args:
            graph_id: 图谱ID
            query: 搜索查询（用于相关性排序）
            include_expired: 是否包含过期内容（默认True）
            limit: 返回结果数量限制
            
        Returns:
            PanoramaResult: 广度搜索结果
        """
        logger.info(f"PanoramaSearch 广度搜索: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        # 获取所有节点
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        # 获取所有边（包含时间信息）
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        # 分类事实
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            # 为事实添加实体名称
            source_name = node_map.get(edge.source_node_uuid, NodeInfo('', '', [], '', {})).name or edge.source_node_uuid[:8]
            target_name = node_map.get(edge.target_node_uuid, NodeInfo('', '', [], '', {})).name or edge.target_node_uuid[:8]
            
            # 判断是否过期/失效
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                # 历史/过期事实，添加时间标记
                valid_at = edge.valid_at or "未知"
                invalid_at = edge.invalid_at or edge.expired_at or "未知"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                # 当前有效事实
                active_facts.append(edge.fact)
        
        # 基于查询进行相关性排序
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        # 排序并限制数量
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearch完成: {result.active_count}条有效, {result.historical_count}条历史")
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        【QuickSearch - 简单搜索】
        
        快速、轻量级的检索工具：
        1. 直接调用Zep语义搜索
        2. 返回最相关的结果
        3. 适用于简单、直接的检索需求
        
        Args:
            graph_id: 图谱ID
            query: 搜索查询
            limit: 返回结果数量
            
        Returns:
            SearchResult: 搜索结果
        """
        logger.info(f"QuickSearch 简单搜索: {query[:50]}...")
        
        # 直接调用现有的search_graph方法
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(f"QuickSearch完成: {result.total_count}条结果")
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        【InterviewAgents - 深度采访】
        
        调用真实的OASIS采访API，采访模拟中正在运行的Agent：
        1. 自动读取人设文件，了解所有模拟Agent
        2. 使用LLM分析采访需求，智能选择最相关的Agent
        3. 使用LLM生成采访问题
        4. 调用 /api/simulation/interview/batch 接口进行真实采访（双平台同时采访）
        5. 整合所有采访结果，生成采访报告
        
        【重要】此功能需要模拟环境处于运行状态（OASIS环境未关闭）
        
        【使用场景】
        - 需要从不同角色视角了解事件看法
        - 需要收集多方意见和观点
        - 需要获取模拟Agent的真实回答（非LLM模拟）
        
        Args:
            simulation_id: 模拟ID（用于定位人设文件和调用采访API）
            interview_requirement: 采访需求描述（非结构化，如"了解学生对事件的看法"）
            simulation_requirement: 模拟需求背景（可选）
            max_agents: 最多采访的Agent数量
            custom_questions: 自定义采访问题（可选，若不提供则自动生成）
            
        Returns:
            InterviewResult: 采访结果
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents 深度采访（真实API）: {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )

        envfish_bundle = self._load_envfish_artifacts(simulation_id)
        if envfish_bundle.available:
            logger.info("检测到 EnvFish 工件，使用文件驱动的虚拟采访模式")
            return self._run_envfish_interview(
                simulation_id=simulation_id,
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                max_agents=max_agents,
                custom_questions=custom_questions
            )
        
        # Step 1: 读取人设文件
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"未找到模拟 {simulation_id} 的人设文件")
            result.summary = "未找到可采访的Agent人设文件"
            return result
        
        result.total_agents = len(profiles)
        logger.info(f"加载到 {len(profiles)} 个Agent人设")
        
        # Step 2: 使用LLM选择要采访的Agent（返回agent_id列表）
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"选择了 {len(selected_agents)} 个Agent进行采访: {selected_indices}")
        
        # Step 3: 生成采访问题（如果没有提供）
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"生成了 {len(result.interview_questions)} 个采访问题")
        
        # 将问题合并为一个采访prompt
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        # 添加优化前缀，约束Agent回复格式
        INTERVIEW_PROMPT_PREFIX = (
            "你正在接受一次采访。请结合你的人设、所有的过往记忆与行动，"
            "以纯文本方式直接回答以下问题。\n"
            "回复要求：\n"
            "1. 直接用自然语言回答，不要调用任何工具\n"
            "2. 不要返回JSON格式或工具调用格式\n"
            "3. 不要使用Markdown标题（如#、##、###）\n"
            "4. 按问题编号逐一回答，每个回答以「问题X：」开头（X为问题编号）\n"
            "5. 每个问题的回答之间用空行分隔\n"
            "6. 回答要有实质内容，每个问题至少回答2-3句话\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: 调用真实的采访API（不指定platform，默认双平台同时采访）
        try:
            # 构建批量采访列表（不指定platform，双平台采访）
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # 使用优化后的prompt
                    # 不指定platform，API会在twitter和reddit两个平台都采访
                })
            
            logger.info(f"调用批量采访API（双平台）: {len(interviews_request)} 个Agent")
            
            # 调用 SimulationRunner 的批量采访方法（不传platform，双平台采访）
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # 不指定platform，双平台采访
                timeout=180.0   # 双平台需要更长超时
            )
            
            logger.info(f"采访API返回: {api_result.get('interviews_count', 0)} 个结果, success={api_result.get('success')}")
            
            # 检查API调用是否成功
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "未知错误")
                logger.warning(f"采访API返回失败: {error_msg}")
                result.summary = f"采访API调用失败：{error_msg}。请检查OASIS模拟环境状态。"
                return result
            
            # Step 5: 解析API返回结果，构建AgentInterview对象
            # 双平台模式返回格式: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "未知")
                agent_bio = agent.get("bio", "")
                
                # 获取该Agent在两个平台的采访结果
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # 清理可能的工具调用 JSON 包裹
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                # 始终输出双平台标记
                twitter_text = twitter_response if twitter_response else "（该平台未获得回复）"
                reddit_text = reddit_response if reddit_response else "（该平台未获得回复）"
                response_text = f"【Twitter平台回答】\n{twitter_text}\n\n【Reddit平台回答】\n{reddit_text}"

                # 提取关键引言（从两个平台的回答中）
                import re
                combined_responses = f"{twitter_response} {reddit_response}"

                # 清理响应文本：去掉标记、编号、Markdown 等干扰
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'问题\d+[：:]\s*', '', clean_text)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)

                # 策略1（主）: 提取完整的有实质内容的句子
                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not s.strip().startswith(('{', '问题'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]

                # 策略2（补充）: 正确配对的中文引号「」内长文本
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # 扩大bio长度限制
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            # 模拟环境未运行
            logger.warning(f"采访API调用失败（环境未运行？）: {e}")
            result.summary = f"采访失败：{str(e)}。模拟环境可能已关闭，请确保OASIS环境正在运行。"
            return result
        except Exception as e:
            logger.error(f"采访API调用异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"采访过程发生错误：{str(e)}"
            return result
        
        # Step 6: 生成采访摘要
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgents完成: 采访了 {result.interviewed_count} 个Agent（双平台）")
        return result
    
    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """清理 Agent 回复中的 JSON 工具调用包裹，提取实际内容"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """加载模拟的Agent人设文件"""
        import os
        import csv
        
        # 构建人设文件路径
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        # 优先尝试读取Reddit JSON格式
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"从 reddit_profiles.json 加载了 {len(profiles)} 个人设")
                return profiles
            except Exception as e:
                logger.warning(f"读取 reddit_profiles.json 失败: {e}")
        
        # 尝试读取Twitter CSV格式
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # CSV格式转换为统一格式
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "未知"
                        })
                logger.info(f"从 twitter_profiles.csv 加载了 {len(profiles)} 个人设")
                return profiles
            except Exception as e:
                logger.warning(f"读取 twitter_profiles.csv 失败: {e}")
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        使用LLM选择要采访的Agent
        
        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: 选中Agent的完整信息列表
                - selected_indices: 选中Agent的索引列表（用于API调用）
                - reasoning: 选择理由
        """
        
        # 构建Agent摘要列表
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "未知"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)
        
        system_prompt = """你是一个专业的采访策划专家。你的任务是根据采访需求，从模拟Agent列表中选择最适合采访的对象。

选择标准：
1. Agent的身份/职业与采访主题相关
2. Agent可能持有独特或有价值的观点
3. 选择多样化的视角（如：支持方、反对方、中立方、专业人士等）
4. 优先选择与事件直接相关的角色

返回JSON格式：
{
    "selected_indices": [选中Agent的索引列表],
    "reasoning": "选择理由说明"
}"""

        user_prompt = f"""采访需求：
{interview_requirement}

模拟背景：
{simulation_requirement if simulation_requirement else "未提供"}

可选择的Agent列表（共{len(agent_summaries)}个）：
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

请选择最多{max_agents}个最适合采访的Agent，并说明选择理由。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "基于相关性自动选择")
            
            # 获取选中的Agent完整信息
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(f"LLM选择Agent失败，使用默认选择: {e}")
            # 降级：选择前N个
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "使用默认选择策略"
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """使用LLM生成采访问题"""
        
        agent_roles = [a.get("profession", "未知") for a in selected_agents]
        
        system_prompt = """你是一个专业的记者/采访者。根据采访需求，生成3-5个深度采访问题。

问题要求：
1. 开放性问题，鼓励详细回答
2. 针对不同角色可能有不同答案
3. 涵盖事实、观点、感受等多个维度
4. 语言自然，像真实采访一样
5. 每个问题控制在50字以内，简洁明了
6. 直接提问，不要包含背景说明或前缀

返回JSON格式：{"questions": ["问题1", "问题2", ...]}"""

        user_prompt = f"""采访需求：{interview_requirement}

模拟背景：{simulation_requirement if simulation_requirement else "未提供"}

采访对象角色：{', '.join(agent_roles)}

请生成3-5个采访问题。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [f"关于{interview_requirement}，您有什么看法？"])
            
        except Exception as e:
            logger.warning(f"生成采访问题失败: {e}")
            return [
                f"关于{interview_requirement}，您的观点是什么？",
                "这件事对您或您所代表的群体有什么影响？",
                "您认为应该如何解决或改进这个问题？"
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """生成采访摘要"""
        
        if not interviews:
            return "未完成任何采访"
        
        # 收集所有采访内容
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"【{interview.agent_name}（{interview.agent_role}）】\n{interview.response[:500]}")
        
        system_prompt = """你是一个专业的新闻编辑。请根据多位受访者的回答，生成一份采访摘要。

摘要要求：
1. 提炼各方主要观点
2. 指出观点的共识和分歧
3. 突出有价值的引言
4. 客观中立，不偏袒任何一方
5. 控制在1000字内

格式约束（必须遵守）：
- 使用纯文本段落，用空行分隔不同部分
- 不要使用Markdown标题（如#、##、###）
- 不要使用分割线（如---、***）
- 引用受访者原话时使用中文引号「」
- 可以使用**加粗**标记关键词，但不要使用其他Markdown语法"""

        user_prompt = f"""采访主题：{interview_requirement}

采访内容：
{"".join(interview_texts)}

请生成采访摘要。"""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
            
        except Exception as e:
            logger.warning(f"生成采访摘要失败: {e}")
            # 降级：简单拼接
            return f"共采访了{len(interviews)}位受访者，包括：" + "、".join([i.agent_name for i in interviews])
