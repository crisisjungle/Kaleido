from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence


RISK_CONTRACT_VERSION = 2
MAX_ACTIVE_RISKS = 8
MAX_PATH_EDGES = 4
MIN_EVIDENCE_STRENGTH = 40.0

PLACEHOLDER_EVIDENCE = {
    "fallback",
    "fallback_explicit",
    "fallback_explicit_low_confidence",
    "llm_relation_candidate",
    "placeholder",
}
INTERNAL_VARIABLE_TOKENS = {
    "disaster_injection",
    "policy_injection",
}
COLOR_DISPLAY_TOKENS = {
    "blue",
    "brown",
    "orange",
    "green",
    "purple",
    "cyan",
    "red",
    "yellow",
    "gray",
    "grey",
}
INTERNAL_DISPLAY_TOKENS = INTERNAL_VARIABLE_TOKENS | COLOR_DISPLAY_TOKENS

RISK_FAMILIES: Dict[str, Dict[str, Any]] = {
    "ecological_environment": {
        "label": "生态环境",
        "outcome": "生态暴露与功能受损",
        "keywords": ["生态", "生态受体", "生态系统", "湿地", "水体", "森林", "物种", "栖息地", "植被", "生物多样性", "污染", "ecology", "wetland", "habitat"],
        "metrics": [
            ("ecosystem_integrity", "生态完整性", "higher_is_better", 0.6),
            ("exposure_score", "受体暴露", "higher_is_worse", 0.4),
        ],
    },
    "health_safety": {
        "label": "健康与安全",
        "outcome": "健康与安全暴露",
        "keywords": ["健康", "人群", "居民", "游客", "脆弱群体", "患者", "医疗", "医院", "伤亡", "中毒", "暴露", "安全", "health", "resident", "exposure"],
        "metrics": [
            ("exposure_score", "人群暴露", "higher_is_worse", 0.6),
            ("vulnerability_score", "脆弱性", "higher_is_worse", 0.4),
        ],
    },
    "infrastructure_continuity": {
        "label": "基础设施连续性",
        "outcome": "关键设施与服务中断",
        "keywords": ["基础设施", "设施", "机场", "港口", "电力", "电网", "通信", "供水", "科研", "科研设施", "科学城", "中断", "infrastructure", "facility"],
        "metrics": [
            ("service_capacity", "服务能力", "higher_is_better", 0.6),
            ("vulnerability_score", "设施脆弱性", "higher_is_worse", 0.4),
        ],
    },
    "mobility_logistics": {
        "label": "交通与物流",
        "outcome": "交通物流受阻",
        "keywords": ["交通", "疏散", "道路", "桥", "隧道", "物流", "机场", "港口", "航班", "通行", "运输", "transport", "road", "logistics"],
        "metrics": [
            ("service_capacity", "通行服务能力", "higher_is_better", 0.55),
            ("spread_pressure", "网络传播压力", "higher_is_worse", 0.45),
        ],
    },
    "resource_supply": {
        "label": "资源供应",
        "outcome": "资源供应与使用安全受损",
        "keywords": ["水源", "食品", "海产品", "渔业", "捕捞", "能源", "物资", "资源", "供应", "粮食", "resource", "supply", "food"],
        "metrics": [
            ("service_capacity", "资源供应能力", "higher_is_better", 0.55),
            ("exposure_score", "资源暴露", "higher_is_worse", 0.45),
        ],
    },
    "economy_livelihood": {
        "label": "经济与生计",
        "outcome": "经济活动与生计稳定性受损",
        "keywords": ["经济", "市场", "经营", "生计", "渔民", "企业", "就业", "收入", "economy", "market", "livelihood"],
        "metrics": [
            ("economic_stress", "经济压力", "higher_is_worse", 0.55),
            ("livelihood_stability", "生计稳定性", "higher_is_better", 0.45),
        ],
    },
    "governance_response": {
        "label": "治理与响应",
        "outcome": "治理协调与应急响应承压",
        "keywords": ["政府", "治理", "应急", "响应", "协调", "监管", "预警", "封锁", "管控", "governance", "response", "emergency"],
        "metrics": [
            ("response_capacity", "响应能力", "higher_is_better", 0.6),
            ("public_trust", "公众信任", "higher_is_better", 0.4),
        ],
    },
    "information_trust": {
        "label": "信息与信任",
        "outcome": "信息传播与公众信任失衡",
        "keywords": ["信息", "舆情", "恐慌", "谣言", "媒体", "信任", "公众信任", "传播", "information", "panic", "trust"],
        "metrics": [
            ("panic_level", "恐慌水平", "higher_is_worse", 0.55),
            ("public_trust", "公众信任", "higher_is_better", 0.45),
        ],
    },
    "compound_cascade": {
        "label": "复合级联",
        "outcome": "跨系统复合级联影响",
        "keywords": ["级联", "复合", "反馈", "跨区域", "跨系统", "连锁", "cascade", "compound", "systemic"],
        "metrics": [
            ("spread_pressure", "传播压力", "higher_is_worse", 0.35),
            ("vulnerability_score", "系统脆弱性", "higher_is_worse", 0.35),
            ("response_capacity", "响应能力", "higher_is_better", 0.3),
        ],
    },
    "other_emergent": {
        "label": "其他涌现风险",
        "outcome": "场景特异影响",
        "keywords": [],
        "metrics": [
            ("vulnerability_score", "脆弱性", "higher_is_worse", 0.6),
            ("exposure_score", "暴露水平", "higher_is_worse", 0.4),
        ],
    },
}

RECEPTOR_STRONG_TERMS: Dict[str, Sequence[str]] = {
    "ecological_environment": ("生态受体", "生态系统", "湿地", "物种", "栖息地", "植被", "生物多样性"),
    "health_safety": ("人群", "居民", "游客", "脆弱群体", "患者", "医疗", "医院", "健康", "伤亡", "中毒"),
    "infrastructure_continuity": ("基础设施", "科研设施", "科学城", "电网", "供水设施", "通信设施"),
    "mobility_logistics": ("交通", "疏散", "道路", "物流", "机场", "港口", "航班", "通行", "运输"),
    "resource_supply": ("海产品", "渔业", "捕捞", "食品", "水源", "物资供应", "能源供应", "资源供应"),
    "economy_livelihood": ("经济", "市场", "经营", "生计", "渔民", "就业", "收入"),
    "governance_response": ("政府", "治理", "应急响应", "应急指挥", "监管", "跨部门协调", "封锁", "管控"),
    "information_trust": ("信息", "舆情", "恐慌", "谣言", "媒体", "公众信任"),
    "compound_cascade": ("复合级联", "跨系统级联", "反馈回路"),
}

FAMILY_ROLE_DEMAND_TOKENS: Dict[str, Sequence[str]] = {
    "ecological_environment": ("ecological_receptor", "environmental_monitoring", "生态受体", "生态监测"),
    "health_safety": ("affected_population", "emergency_medical_response", "healthcare", "受影响居民", "医疗"),
    "infrastructure_continuity": ("critical_facility_operator", "facility_safety", "关键设施", "设施运行"),
    "mobility_logistics": ("transport_continuity", "evacuation", "交通连续性", "疏散调度"),
    "resource_supply": ("fisheries_stakeholders", "resource_supply", "food_chain", "渔业群体", "资源供应"),
    "economy_livelihood": ("livelihood", "compensation", "生计", "补偿"),
    "governance_response": ("cross_agency_governance", "public_emergency_command", "跨部门治理", "应急指挥"),
    "information_trust": ("public_information", "risk_communication", "公众信息", "风险沟通"),
}

FAMILY_CLASSIFICATION_PRIORITY = {
    "health_safety": 0,
    "ecological_environment": 1,
    "mobility_logistics": 2,
    "resource_supply": 3,
    "infrastructure_continuity": 4,
    "governance_response": 5,
    "information_trust": 6,
    "economy_livelihood": 7,
    "compound_cascade": 8,
}

FAMILY_ENTITY_TYPE_TERMS: Dict[str, Sequence[str]] = {
    "ecological_environment": ("ecological", "ecology", "environmentalcarrier", "habitat", "species", "ecosystem"),
    "health_safety": ("human", "resident", "patient", "medical", "hospital", "health"),
    "infrastructure_continuity": ("infrastructure", "facility", "utility", "plant", "station"),
    "mobility_logistics": ("infrastructure", "transport", "airport", "port", "road", "logistic"),
    "resource_supply": ("environmentalcarrier", "resource", "fish", "food", "water", "supply", "organization"),
    "economy_livelihood": ("human", "organization", "business", "market", "livelihood"),
    "governance_response": ("government", "governance", "organization", "emergency"),
    "information_trust": ("human", "organization", "government", "media", "information"),
}

FAMILY_ENTITY_NAME_TERMS: Dict[str, Sequence[str]] = {
    "ecological_environment": ("生态", "湿地", "水体", "海湾", "栖息地", "物种", "保护区"),
    "health_safety": ("人群", "居民", "游客", "患者", "医院", "医疗", "脆弱群体"),
    "infrastructure_continuity": ("设施", "电网", "供水", "通信", "科研", "科学城"),
    "mobility_logistics": ("交通", "机场", "港口", "道路", "桥梁", "物流", "疏散"),
    "resource_supply": ("水源", "渔业", "海产品", "食品", "能源", "物资", "供应"),
    "economy_livelihood": ("企业", "商户", "市场", "渔民", "就业", "生计"),
    "governance_response": ("政府", "监管", "应急", "治理", "指挥"),
    "information_trust": ("媒体", "信息", "舆情", "公众", "社区"),
}

FAMILY_REGION_TYPE_TERMS: Dict[str, Sequence[str]] = {
    "ecological_environment": ("coastal", "water", "shore", "ecolog", "wetland", "habitat", "forest", "marine", "river"),
    "health_safety": ("residential", "city", "urban", "community", "medical", "hospital", "health"),
    "infrastructure_continuity": ("infrastructure", "facility", "utility", "industrial", "port", "station", "civic"),
    "mobility_logistics": ("transport", "airport", "port", "road", "transit", "logistic"),
    "resource_supply": ("coastal", "water", "agricultur", "fish", "market", "commercial", "supply"),
    "economy_livelihood": ("commercial", "industrial", "market", "business", "city", "urban"),
    "governance_response": ("civic", "city", "administrative", "government", "governance"),
    "information_trust": ("civic", "residential", "city", "urban", "media", "information"),
}

FAMILY_REGION_TEXT_TERMS: Dict[str, Sequence[str]] = {
    "ecological_environment": ("生态", "湿地", "水体", "水域", "海湾", "岸线", "栖息地", "物种", "保护区", "海洋生物"),
    "health_safety": ("居民", "人群", "人口", "居住", "社区", "医疗", "医院", "健康", "暴露", "脆弱群体"),
    "infrastructure_continuity": ("基础设施", "关键设施", "电网", "供水", "通信", "科研设施", "站点", "枢纽"),
    "mobility_logistics": ("交通", "机场", "港口", "道路", "桥梁", "物流", "疏散", "通行", "运输"),
    "resource_supply": ("水源", "渔业", "捕捞", "海产品", "食品", "能源", "物资", "供应"),
    "economy_livelihood": ("商业", "企业", "市场", "渔民", "就业", "收入", "生计", "经营"),
    "governance_response": ("政府", "监管", "应急", "治理", "指挥", "协同", "行政"),
    "information_trust": ("信息", "舆情", "媒体", "公众", "社区", "沟通", "信任"),
}


@dataclass
class RiskCandidateExtractionResult:
    definitions: List[Dict[str, Any]] = field(default_factory=list)
    candidate_ledger: List[Dict[str, Any]] = field(default_factory=list)
    audit: Dict[str, Any] = field(default_factory=dict)


class RiskCandidateExtractor:
    """Derive V2 risk definitions from validated, scenario-local mechanism paths."""

    SOURCE_TYPES = {"source", "pressure", "hazard", "driver", "trigger"}
    TERMINAL_TYPES = {
        "receptor",
        "infrastructure",
        "governance",
        "human",
        "ecological",
        "economy",
        "service",
        "outcome",
    }

    def extract(self, **kwargs: Any) -> RiskCandidateExtractionResult:
        variables = [self._as_dict(item) for item in (kwargs.get("injected_variables") or [])]
        regions = [
            self._as_dict(item)
            for item in [*(kwargs.get("regions") or []), *(kwargs.get("subregions") or [])]
        ]
        entities = [self._as_dict(item) for item in (kwargs.get("entities") or [])]
        profiles = [self._as_dict(item) for item in (kwargs.get("profiles") or [])]
        role_demands = [self._as_dict(item) for item in (kwargs.get("role_demands") or [])]
        mechanism_graph = self._as_dict(kwargs.get("mechanism_graph") or {})
        validated_graph = self._as_dict(kwargs.get("validated_relation_graph") or {})
        scenario_state_schema = self._as_dict(kwargs.get("scenario_state_schema") or {})
        # A graph with an explicit event node but no causal edges is incomplete,
        # not absent. Replacing it with map connectivity would silently turn
        # spatial neighbours into causes and receptors.
        if not mechanism_graph.get("nodes"):
            mechanism_graph = self._build_minimal_graph(
                variables=variables,
                regions=regions,
                profiles=profiles,
                transport_edges=[self._as_dict(item) for item in (kwargs.get("transport_edges") or [])],
                relationships=[self._as_dict(item) for item in (kwargs.get("agent_relationships") or [])],
            )
        document_text = str(kwargs.get("document_text") or "")
        temporal_profile = self._as_dict(kwargs.get("temporal_profile") or {})

        nodes = [self._normalize_node(item, index) for index, item in enumerate(mechanism_graph.get("nodes") or [])]
        node_index = {item["id"]: item for item in nodes if item.get("id")}
        raw_edges = [self._normalize_edge(item, index) for index, item in enumerate(mechanism_graph.get("edges") or [])]
        valid_edges: List[Dict[str, Any]] = []
        ledger: List[Dict[str, Any]] = []
        dangling_count = 0
        invalid_display_count = 0
        for edge in raw_edges:
            if edge["source"] not in node_index or edge["target"] not in node_index:
                dangling_count += 1
                ledger.append(self._rejected_edge(edge, "机制边引用了不存在的节点"))
                continue
            if edge.get("has_forbidden_display_value"):
                invalid_display_count += 1
                ledger.append(self._rejected_edge(edge, "机制边包含占位证据、内部变量名或颜色代码"))
                continue
            if node_index[edge["source"]].get("has_forbidden_display_value") or node_index[edge["target"]].get("has_forbidden_display_value"):
                invalid_display_count += 1
                ledger.append(self._rejected_edge(edge, "机制节点包含内部变量名或颜色代码"))
                continue
            valid_edges.append(edge)

        relation_edges = [self._as_dict(item) for item in (validated_graph.get("edges") or [])]
        epistemic_by_edge = self._epistemic_index(relation_edges)
        actors_by_edge = self._actors_by_mechanism_edge(relation_edges, profiles)
        anchor_names = self._anchor_names(regions, entities)
        corpus = self._join_text(
            document_text,
            kwargs.get("simulation_requirement"),
            *[self._join_text(item.get("name"), item.get("description"), item.get("summary")) for item in regions],
            *[self._join_text(item.get("name"), item.get("summary"), item.get("description")) for item in entities],
        ).lower()

        adjacency: Dict[str, List[Dict[str, Any]]] = {}
        indegree = {node_id: 0 for node_id in node_index}
        for edge in valid_edges:
            adjacency.setdefault(edge["source"], []).append(edge)
            indegree[edge["target"]] = indegree.get(edge["target"], 0) + 1
        source_ids = [
            node_id
            for node_id, node in node_index.items()
            if self._node_type(node) in self.SOURCE_TYPES and indegree.get(node_id, 0) == 0
        ]
        if not source_ids:
            source_ids = [node_id for node_id, count in indegree.items() if count == 0]

        raw_paths = self._enumerate_paths(source_ids, node_index, adjacency)
        feedback_cycles = self._enumerate_feedback_cycles(node_index, adjacency)
        accepted: List[Dict[str, Any]] = []
        for path_edges, is_feedback_cycle in [
            *[(path, False) for path in raw_paths],
            *[(path, True) for path in feedback_cycles],
        ]:
            if self._path_is_agent_relationship_only(path_edges, node_index):
                ledger.append({
                    "status": "rejected",
                    "reason": (
                        "纯主体协同关系闭环不构成风险因果反馈"
                        if is_feedback_cycle
                        else "纯主体关系路径缺少压力源、传播过程和真实受体"
                    ),
                    "mechanism_edge_ids": [item["id"] for item in path_edges],
                })
                continue
            if self._path_is_spatial_connectivity_only(path_edges, node_index):
                ledger.append({
                    "status": "rejected",
                    "reason": "地图空间邻接或运输连通关系不能单独构成风险因果路径",
                    "mechanism_edge_ids": [item["id"] for item in path_edges],
                })
                continue
            if is_feedback_cycle and not self._feedback_cycle_is_cross_region(path_edges, node_index, regions):
                ledger.append({
                    "status": "rejected",
                    "reason": "反馈环未跨越至少两个区域",
                    "mechanism_edge_ids": [item["id"] for item in path_edges],
                })
                continue
            if is_feedback_cycle:
                valid_feedback, feedback_reason = self._feedback_cycle_is_causal(path_edges, node_index)
                if not valid_feedback:
                    ledger.append({
                        "status": "rejected",
                        "reason": feedback_reason,
                        "mechanism_edge_ids": [item["id"] for item in path_edges],
                    })
                    continue
            candidate, rejection = self._build_candidate(
                path_edges=path_edges,
                node_index=node_index,
                epistemic_by_edge=epistemic_by_edge,
                actors_by_edge=actors_by_edge,
                variables=variables,
                regions=regions,
                entities=entities,
                profiles=profiles,
                role_demands=role_demands,
                anchor_names=anchor_names,
                corpus=corpus,
                temporal_profile=temporal_profile,
                scenario_state_schema=scenario_state_schema,
                created_round=int(kwargs.get("created_round") or 0),
                force_family="compound_cascade" if is_feedback_cycle else "",
                is_feedback_cycle=is_feedback_cycle,
            )
            if candidate:
                accepted.append(candidate)
                ledger.append(self._candidate_ledger_item(candidate, "accepted", ""))
            else:
                ledger.append({
                    "status": "rejected",
                    "reason": rejection or "候选未通过校验",
                    "mechanism_edge_ids": [item["id"] for item in path_edges],
                })

        merged = self._merge_candidates(accepted)
        self._disambiguate_titles(merged)
        merged.sort(
            key=lambda item: (
                float(item.get("priority_score") or 0),
                float(item.get("evidence_strength_score") or 0),
                float(item.get("impact_score") or 0),
            ),
            reverse=True,
        )
        requested_active_limit = int(kwargs.get("max_active_risks", MAX_ACTIVE_RISKS))
        active_limit = max(0, min(MAX_ACTIVE_RISKS, requested_active_limit))
        requested_scan_limit = kwargs.get("candidate_scan_limit")
        candidate_scan_limit = (
            240
            if requested_scan_limit is None
            else max(0, min(240, int(requested_scan_limit)))
        )
        scanned_candidates = merged[:candidate_scan_limit]
        definitions = scanned_candidates[:active_limit]
        active_ids = {item["risk_id"] for item in definitions}
        for index, item in enumerate(merged):
            if index < active_limit and index < candidate_scan_limit:
                continue
            if index >= candidate_scan_limit:
                reason = f"超过当前分析强度的风险候选扫描上限 {candidate_scan_limit}"
                status = "budget_deferred"
            else:
                reason = f"通过候选校验，但超过全场最多 {active_limit} 个活跃风险对象的固定上限"
                status = "candidate_only"
            ledger.append(self._candidate_ledger_item(item, status, reason))

        rejected_count = sum(1 for item in ledger if item.get("status") == "rejected")
        audit = {
            "risk_contract_version": RISK_CONTRACT_VERSION,
            "generation_mode": "mechanism_graph_deterministic",
            "candidate_count": len(raw_paths) + len(feedback_cycles),
            "validated_candidate_count": len(merged),
            "candidate_scan_limit": candidate_scan_limit,
            "scanned_candidate_count": len(scanned_candidates),
            "active_risk_limit": active_limit,
            "active_count": len(definitions),
            "rejected_count": rejected_count,
            "dangling_reference_count": dangling_count,
            "invalid_display_reference_count": invalid_display_count,
            "active_risk_ids": [item["risk_id"] for item in definitions],
            "inactive_validated_risk_ids": [item["risk_id"] for item in merged if item["risk_id"] not in active_ids],
            "zero_reason": "" if definitions else self._zero_reason(nodes, valid_edges, raw_paths, ledger),
            "quality_flags": self._quality_flags(dangling_count, invalid_display_count, definitions, [*raw_paths, *feedback_cycles]),
            "graph_source": str(mechanism_graph.get("source") or "scenario_mechanism_graph"),
            "data_source_summary": self._data_source_summary(kwargs.get("data_grounding_summary")),
        }
        return RiskCandidateExtractionResult(definitions=definitions, candidate_ledger=ledger, audit=audit)

    def _enumerate_paths(
        self,
        source_ids: Sequence[str],
        node_index: Dict[str, Dict[str, Any]],
        adjacency: Dict[str, List[Dict[str, Any]]],
    ) -> List[List[Dict[str, Any]]]:
        paths: List[List[Dict[str, Any]]] = []
        seen: set[str] = set()

        def visit(node_id: str, visited: List[str], path: List[Dict[str, Any]]) -> None:
            if len(path) >= MAX_PATH_EDGES:
                return
            for edge in adjacency.get(node_id, []):
                target = edge["target"]
                if target in visited:
                    continue
                next_path = [*path, edge]
                target_node = node_index[target]
                target_type = self._node_type(target_node)
                if target_type in self.TERMINAL_TYPES:
                    signature = "|".join(item["id"] for item in next_path)
                    if signature not in seen:
                        seen.add(signature)
                        paths.append(next_path)
                visit(target, [*visited, target], next_path)

        for source_id in source_ids:
            visit(source_id, [source_id], [])
        return paths[:240]

    def _enumerate_feedback_cycles(
        self,
        node_index: Dict[str, Dict[str, Any]],
        adjacency: Dict[str, List[Dict[str, Any]]],
    ) -> List[List[Dict[str, Any]]]:
        cycles: List[List[Dict[str, Any]]] = []
        seen: set[str] = set()

        def canonical(edge_ids: List[str]) -> str:
            rotations = [edge_ids[index:] + edge_ids[:index] for index in range(len(edge_ids))]
            return min("|".join(items) for items in rotations)

        def visit(start: str, current: str, visited: List[str], path: List[Dict[str, Any]]) -> None:
            if len(path) >= MAX_PATH_EDGES:
                return
            for edge in adjacency.get(current, []):
                target = edge["target"]
                next_path = [*path, edge]
                if target == start:
                    if len(set(visited)) < 3 or len(next_path) < 3:
                        continue
                    signature = canonical([item["id"] for item in next_path])
                    if signature not in seen:
                        seen.add(signature)
                        cycles.append(next_path)
                    continue
                if target in visited:
                    continue
                visit(start, target, [*visited, target], next_path)

        for node_id in sorted(node_index):
            visit(node_id, node_id, [node_id], [])
        return cycles[:120]

    def _path_is_agent_relationship_only(
        self,
        edges: List[Dict[str, Any]],
        node_index: Dict[str, Dict[str, Any]],
    ) -> bool:
        node_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
        nodes = [node_index[node_id] for node_id in node_ids if node_id in node_index]
        return bool(nodes) and all(
            str(node.get("node_origin") or "").strip().lower() == "agent_profile"
            for node in nodes
        ) and all(
            str(edge.get("edge_role") or "").strip().lower() == "agent_relationship"
            for edge in edges
        )

    def _path_is_spatial_connectivity_only(
        self,
        edges: List[Dict[str, Any]],
        node_index: Dict[str, Dict[str, Any]],
    ) -> bool:
        node_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
        nodes = [node_index[node_id] for node_id in node_ids if node_id in node_index]
        return bool(nodes) and (
            all(
                str(node.get("node_origin") or "").strip().lower() == "spatial_region"
                for node in nodes
            )
            or all(
                str(edge.get("edge_role") or "").strip().lower() == "transport_connectivity"
                for edge in edges
            )
        )

    def _feedback_cycle_is_causal(
        self,
        edges: List[Dict[str, Any]],
        node_index: Dict[str, Dict[str, Any]],
    ) -> tuple[bool, str]:
        node_ids = self._unique([
            *[edge["source"] for edge in edges],
            *[edge["target"] for edge in edges],
        ])
        nodes = [node_index[node_id] for node_id in node_ids if node_id in node_index]
        node_types = {self._node_type(node) for node in nodes}
        if not any(node_type in self.SOURCE_TYPES for node_type in node_types):
            return False, "反馈环缺少真实压力源或触发事件"
        if not any(node_type in self.TERMINAL_TYPES for node_type in node_types):
            return False, "反馈环缺少可识别的真实受体或承压系统"

        families = {
            self._family(
                self._join_text(node.get("name"), node.get("description")),
                self._join_text(node.get("name"), node.get("label")),
                self._node_type(node),
            )
            for node in nodes
        }
        families.discard("other_emergent")
        families.discard("compound_cascade")
        if len(families) < 2:
            return False, "反馈环未跨越至少两个可区分的承压系统"

        feedback_text = self._join_text(
            *[
                self._join_text(
                    edge.get("edge_role"),
                    edge.get("relation_kind"),
                    edge.get("relation_label"),
                    edge.get("mechanism"),
                    edge.get("trigger_conditions"),
                )
                for edge in edges
            ]
        ).lower()
        has_feedback_semantics = any(
            token in feedback_text
            for token in ("反馈", "反向", "放大", "强化", "恶化", "feedback", "reinforce", "amplif")
        )
        if not has_feedback_semantics:
            return False, "闭环仅表示连通或往返关系，缺少明确的反馈放大机制"
        return True, ""

    def _feedback_cycle_is_cross_region(
        self,
        edges: List[Dict[str, Any]],
        node_index: Dict[str, Dict[str, Any]],
        regions: List[Dict[str, Any]],
    ) -> bool:
        if any(str(edge.get("scope") or "").lower() in {"cross_region", "cross_scale", "systemic"} for edge in edges):
            return True
        node_text = self._join_text(
            *[
                self._join_text(node_index[node_id].get("name"), node_index[node_id].get("description"))
                for node_id in {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
                if node_id in node_index
            ]
        )
        matched_region_ids = {
            str(item.get("region_id") or item.get("id") or item.get("name") or "")
            for item in regions
            if str(item.get("name") or item.get("region_name") or "").strip()
            and str(item.get("name") or item.get("region_name") or "").strip().lower() in node_text.lower()
        }
        return len({item for item in matched_region_ids if item}) >= 2

    def _build_candidate(
        self,
        *,
        path_edges: List[Dict[str, Any]],
        node_index: Dict[str, Dict[str, Any]],
        epistemic_by_edge: Dict[str, str],
        actors_by_edge: Dict[str, List[Dict[str, Any]]],
        variables: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        role_demands: List[Dict[str, Any]],
        anchor_names: set[str],
        corpus: str,
        temporal_profile: Dict[str, Any],
        scenario_state_schema: Dict[str, Any],
        created_round: int,
        force_family: str = "",
        is_feedback_cycle: bool = False,
    ) -> tuple[Dict[str, Any] | None, str]:
        if not path_edges:
            return None, "候选路径为空"
        path_nodes = [node_index[path_edges[0]["source"]], *[node_index[item["target"]] for item in path_edges]]
        display_path_nodes = path_nodes[:-1] if is_feedback_cycle and path_nodes[-1]["id"] == path_nodes[0]["id"] else path_nodes
        edge_statuses: List[str] = []
        evidence_rows: List[Dict[str, Any]] = []
        edge_scores: List[float] = []
        unresolved_source_citations: List[str] = []
        for edge in path_edges:
            if any(
                self._valid_evidence(item) and not self._evidence_resolves(item, corpus)
                for item in (edge.get("evidence") or [])
            ):
                unresolved_source_citations.append(edge["id"])
            relation_status = epistemic_by_edge.get(edge["id"])
            edge_status = self._infer_edge_status(edge, node_index, anchor_names, corpus)
            status = (
                "observed"
                if edge_status == "observed"
                else "speculative"
                if edge_status == "speculative"
                else self._stronger_epistemic_status(relation_status, edge_status)
            )
            edge_statuses.append(status)
            confidence = self._probability(edge.get("confidence"), 0.6)
            status_weight = {"observed": 100.0, "inferred": 60.0, "speculative": 20.0}.get(status, 20.0)
            edge_scores.append(status_weight * confidence)
            evidence_rows.append(self._evidence_row(edge, node_index, status, confidence, corpus))

        observed_count = edge_statuses.count("observed")
        inferred_count = edge_statuses.count("inferred")
        evidence_strength = round(sum(edge_scores) / max(1, len(edge_scores)), 1)
        if edge_statuses.count("speculative"):
            return None, "初始风险路径包含推测或降级机制边，仅保留在候选审计中"
        if not observed_count and inferred_count < 2:
            return None, "至少需要一条可锚定证据的机制边，或两条非降级推断边"
        if evidence_strength < MIN_EVIDENCE_STRENGTH:
            return None, f"证据充分度 {evidence_strength} 低于阈值 {MIN_EVIDENCE_STRENGTH}"

        path_corpus = self._join_text(
            *[self._join_text(item.get("name"), item.get("description")) for item in path_nodes],
            *[self._join_text(item.get("relation_label"), item.get("mechanism"), item.get("evidence")) for item in path_edges],
        )
        source_node = display_path_nodes[0]
        receptor_node = display_path_nodes[-1]
        # Primary classification follows the receptor identity. Scenario planners may
        # repeat the full multi-domain event description on every node, so including
        # that prose here would make unrelated downstream receptors share one family.
        receptor_corpus = self._join_text(receptor_node.get("name"), receptor_node.get("label"))
        family = force_family if force_family in RISK_FAMILIES else self._family(path_corpus, receptor_corpus, self._node_type(receptor_node))
        scope_corpus = self._join_text(
            *[self._join_text(item.get("name"), item.get("label")) for item in display_path_nodes],
            *[
                self._join_text(
                    item.get("relation_label"),
                    item.get("mechanism"),
                    item.get("evidence"),
                )
                for item in path_edges
            ],
        )
        entity_refs = self._entity_refs_for_candidate(
            path_corpus=path_corpus,
            scope_corpus=scope_corpus,
            path_nodes=display_path_nodes,
            entities=entities,
            family=family,
        )[:10]
        region_refs = self._region_refs_for_candidate(
            path_corpus=path_corpus,
            scope_corpus=scope_corpus,
            path_nodes=display_path_nodes,
            regions=regions,
            entities=entities,
            entity_refs=entity_refs,
            family=family,
        )[:8]
        if not region_refs:
            return None, "候选路径未解析到场景中的真实作用区域"
        actor_refs = self._actor_refs(
            path_edges,
            path_nodes,
            actors_by_edge,
            profiles,
            role_demands,
            family,
            receptor_node,
            region_refs,
            entity_refs,
        )[:12]
        source_variable_id = source_node["id"].split("variable::", 1)[1] if source_node["id"].startswith("variable::") else ""
        path_variables = [
            item
            for item in variables
            if source_variable_id and str(item.get("variable_id") or item.get("id") or "") == source_variable_id
        ]
        variable_refs = [source_variable_id] if source_variable_id else []
        mechanism_edge_ids = [item["id"] for item in path_edges]
        mechanism_node_ids = self._unique([item["id"] for item in display_path_nodes])
        monitoring_metrics = self._monitoring_metrics(family, receptor_node, scenario_state_schema)
        impact_score = self._impact_score(path_variables, receptor_node, region_refs, actor_refs)
        propagation_score = self._propagation_score(path_edges)
        actionability_score = self._actionability_score(monitoring_metrics, region_refs, actor_refs)
        priority_score = round(
            impact_score * 0.35
            + evidence_strength * 0.30
            + propagation_score * 0.20
            + actionability_score * 0.15,
            1,
        )
        source_signature = self._source_signature(
            variable_refs=variable_refs,
            source_node_id=source_node["id"],
            mechanism_edge_ids=mechanism_edge_ids,
            receptor_node_id=receptor_node["id"],
            region_ids=[item["region_id"] for item in region_refs],
            family=family,
        )
        risk_id = f"risk_v2_{source_signature[:16]}"
        mechanism_receptor_name = self._display_name(receptor_node.get("name") or receptor_node["id"])
        receptor_name = self._grounded_receptor_name(
            receptor_node,
            entity_refs,
            actor_refs,
            region_refs,
        )
        display_receptor = {**receptor_node, "name": receptor_name}
        title = self._deterministic_title(display_receptor, family)
        trigger_name = self._trigger_name(path_variables, source_node)
        summary = self._deterministic_summary(trigger_name, display_path_nodes, display_receptor, family)
        region_names = [item["region_name"] for item in region_refs]
        actor_ids = [item["actor_id"] for item in actor_refs]
        chain_steps = [self._display_name(item.get("name") or item["id"]) for item in display_path_nodes]
        if chain_steps:
            chain_steps[-1] = receptor_name
        tags = self._tags(display_path_nodes, path_edges)
        consequence = self._consequence(receptor_node, family, receptor_name=receptor_name)
        if is_feedback_cycle:
            first_system = chain_steps[0]
            title = f"{first_system}与{receptor_name}相互放大风险"
            summary = f"{trigger_name}沿{'、'.join(chain_steps[1:]) or '跨系统机制'}形成反馈回路，使{first_system}与{receptor_name}持续相互放大。"
            consequence = f"{first_system}经反馈路径再次增强{receptor_name}承压，可能造成多个系统同步恶化。"
            tags = self._unique(["复合级联", "跨区域反馈", *tags])[:8]
        time_horizon = self._time_horizon(path_edges, temporal_profile)
        affected_cluster = {
            "cluster_id": f"cluster_{source_signature[:16]}",
            "name": f"{receptor_name}受影响区域与主体",
            "cluster_type": family,
            "primary_regions": region_names[:4],
            "actor_ids": actor_ids,
            "dependency_profile": chain_steps[:-1],
            "early_loss_signals": [item["label"] for item in monitoring_metrics],
            "vulnerability_score": impact_score,
            "mismatch_risk": round(max(0.0, 100.0 - actionability_score), 1),
            "notes": "由已校验机制路径关联的区域与主体归并。",
        }
        return {
            "risk_contract_version": RISK_CONTRACT_VERSION,
            "risk_id": risk_id,
            "legacy_risk_object_id": risk_id,
            "source_signature": source_signature,
            "generation_mode": "mechanism_graph_deterministic",
            "category": "scenario_derived",
            "risk_type": family,
            "primary_family": family,
            "primary_family_label": RISK_FAMILIES[family]["label"],
            "tags": tags,
            "title": title,
            "summary": summary,
            "why_now": f"{trigger_name}已通过当前机制路径作用于{receptor_name}，需要作为独立风险对象持续监测。",
            "status": "tracked",
            "mode": "watch",
            "time_horizon": time_horizon,
            "priority_seed": round(priority_score / 100.0, 3),
            "priority_score": priority_score,
            "impact_score": impact_score,
            "severity_score": impact_score,
            "evidence_strength_score": evidence_strength,
            "confidence_score": round(evidence_strength / 100.0, 3),
            "propagation_score": propagation_score,
            "actionability_score": actionability_score,
            "risk_statement": {
                "trigger_variable_ids": variable_refs,
                "trigger_name": trigger_name,
                "source_node_ids": [source_node["id"]],
                "mechanism_edge_ids": mechanism_edge_ids,
                "receptor_node_ids": [receptor_node["id"]],
                "receptor_name": receptor_name,
                "mechanism_receptor_name": mechanism_receptor_name,
                "consequence": consequence,
                "time_horizon": time_horizon,
                "region_refs": region_refs,
                "entity_refs": entity_refs,
                "actor_refs": actor_refs,
            },
            "mechanism_node_ids": mechanism_node_ids,
            "mechanism_edge_ids": mechanism_edge_ids,
            "edge_ids": mechanism_edge_ids,
            "monitoring_metrics": monitoring_metrics,
            "scope": {"regions": region_refs, "entities": entity_refs, "actors": actor_refs},
            "region_scope": region_names,
            "primary_regions": region_names[:2],
            "source_entity_uuids": [item["entity_uuid"] for item in entity_refs],
            "source_actor_ids": actor_ids,
            "source_actor_names": [item["actor_name"] for item in actor_refs],
            "source_variable_ids": variable_refs,
            "root_pressures": [trigger_name, self._display_name(source_node.get("name") or source_node["id"])],
            "chain_steps": chain_steps,
            "turning_points": [f"{monitoring_metrics[0]['label']}越过升级阈值"] if monitoring_metrics else [],
            "turning_point_candidates": [f"{monitoring_metrics[0]['label']}越过升级阈值"] if monitoring_metrics else [],
            "amplifiers": [self._display_name(item.get("relation_label") or item.get("mechanism") or item["id"]) for item in path_edges if item.get("direction") != "negative"][:6],
            "buffers": [self._display_name(item.get("relation_label") or item.get("mechanism") or item["id"]) for item in path_edges if item.get("direction") == "negative"][:6],
            "evidence": evidence_rows,
            "affected_clusters": [affected_cluster],
            "intervention_templates": self._interventions(risk_id, title, chain_steps, region_names),
            "branch_templates": self._branches(risk_id, title),
            "trigger_rules": {
                "source": "mechanism_path_v2",
                "minimum_evidence_strength": MIN_EVIDENCE_STRENGTH,
                "epistemic_breakdown": {
                    "observed": observed_count,
                    "inferred": inferred_count,
                    "speculative": edge_statuses.count("speculative"),
                },
            },
            "quality_flags": self._unique([
                *(["validated_cross_region_feedback_loop"] if is_feedback_cycle else []),
                *(["unresolved_source_citation_removed"] if unresolved_source_citations else []),
                *(
                    ["region_scope_inferred_from_scene_metadata"]
                    if any(item.get("scope_basis") == "scene_metadata_inference" for item in region_refs)
                    else []
                ),
                *(
                    ["entity_scope_inferred_from_scene_metadata"]
                    if any(item.get("scope_basis") == "scene_metadata_inference" for item in entity_refs)
                    else []
                ),
            ]),
            "created_round": created_round,
        }, ""

    def _merge_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda item: float(item.get("priority_score") or 0), reverse=True):
            statement = candidate.get("risk_statement") or {}
            source_ids = set(statement.get("source_node_ids") or [])
            receptor_ids = set(statement.get("receptor_node_ids") or [])
            edge_ids = set(candidate.get("mechanism_edge_ids") or [])
            duplicate = None
            for existing in merged:
                existing_statement = existing.get("risk_statement") or {}
                if source_ids != set(existing_statement.get("source_node_ids") or []):
                    continue
                if receptor_ids != set(existing_statement.get("receptor_node_ids") or []):
                    continue
                existing_edges = set(existing.get("mechanism_edge_ids") or [])
                overlap = len(edge_ids & existing_edges) / max(1, min(len(edge_ids), len(existing_edges)))
                if candidate.get("primary_family") == existing.get("primary_family") and overlap >= 0.6:
                    duplicate = existing
                    break
            if duplicate is None:
                merged.append(candidate)
                continue
            duplicate["tags"] = self._unique([*duplicate.get("tags", []), *candidate.get("tags", [])])[:8]
            duplicate["merged_source_signatures"] = self._unique([
                duplicate.get("source_signature"),
                *duplicate.get("merged_source_signatures", []),
                candidate.get("source_signature"),
                *candidate.get("merged_source_signatures", []),
            ])
            primary_path = {
                "source_signature": duplicate.get("source_signature"),
                "mechanism_node_ids": duplicate.get("mechanism_node_ids") or [],
                "mechanism_edge_ids": duplicate.get("mechanism_edge_ids") or [],
            }
            duplicate["alternative_mechanism_paths"] = self._unique_dicts([
                primary_path,
                *duplicate.get("alternative_mechanism_paths", []),
                {
                    "source_signature": candidate.get("source_signature"),
                    "mechanism_node_ids": candidate.get("mechanism_node_ids") or [],
                    "mechanism_edge_ids": candidate.get("mechanism_edge_ids") or [],
                },
            ], "source_signature")
        return merged

    def _epistemic_index(self, relations: List[Dict[str, Any]]) -> Dict[str, str]:
        ranks = {"speculative": 0, "inferred": 1, "observed": 2}
        result: Dict[str, str] = {}
        for relation in relations:
            status = str(relation.get("epistemic_status") or "").strip().lower()
            validation = str(relation.get("validation_status") or "").strip().lower()
            origin = str(relation.get("origin") or "").strip().lower()
            if "fallback" in validation or "fallback" in origin:
                status = "speculative"
            if status not in ranks:
                status = "inferred" if relation.get("mechanism") else "speculative"
            for edge_id in relation.get("mechanism_edge_ids") or []:
                token = str(edge_id or "").strip()
                if not token:
                    continue
                current = result.get(token)
                if current is None or ranks[status] > ranks[current]:
                    result[token] = status
        return result

    def _actors_by_mechanism_edge(
        self,
        relations: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        profile_index: Dict[str, Dict[str, Any]] = {}
        for profile in profiles:
            for value in (profile.get("agent_id"), profile.get("actor_id"), profile.get("id")):
                if value is not None:
                    profile_index[str(value)] = profile
        candidates: Dict[str, List[tuple[float, int, List[Dict[str, Any]]]]] = {}
        for index, relation in enumerate(relations):
            status = str(relation.get("epistemic_status") or "").strip().lower()
            validation = str(relation.get("validation_status") or "").strip().lower()
            origin = str(relation.get("origin") or "").strip().lower()
            if "fallback" in validation or "fallback" in origin:
                status = "speculative"
            if status not in {"observed", "inferred"}:
                continue
            linked = []
            for key in ("source_agent_id", "target_agent_id"):
                profile = profile_index.get(str(relation.get(key)))
                if profile:
                    ref = self._actor_ref(profile)
                    if ref:
                        linked.append({
                            **ref,
                            "scope_basis": "validated_relation",
                            "epistemic_status": status,
                        })
            if not linked:
                continue
            score = (2.0 if status == "observed" else 1.0) + self._probability(relation.get("confidence"), 0.5)
            for edge_id in relation.get("mechanism_edge_ids") or []:
                token = str(edge_id or "").strip()
                if token:
                    candidates.setdefault(token, []).append((score, index, linked))
        result: Dict[str, List[Dict[str, Any]]] = {}
        for edge_id, rows in candidates.items():
            refs: List[Dict[str, Any]] = []
            for _score, _index, linked in sorted(rows, key=lambda item: (-item[0], item[1])):
                refs = self._unique_dicts([*refs, *linked], "actor_id")
                if len(refs) >= 4:
                    break
            result[edge_id] = refs[:4]
        return result

    def _infer_edge_status(
        self,
        edge: Dict[str, Any],
        node_index: Dict[str, Dict[str, Any]],
        anchor_names: set[str],
        corpus: str,
    ) -> str:
        origin = str(edge.get("origin") or "").strip().lower()
        epistemic_status = str(edge.get("epistemic_status") or "").strip()
        if (
            "fallback" in origin
            or origin == "user_order"
            or "仅确认先后顺序" in epistemic_status
            or "具体因果机制待审阅" in epistemic_status
        ):
            return "speculative"
        evidence = [
            self._display_name(item)
            for item in (edge.get("evidence") or [])
            if self._valid_evidence(item) and self._evidence_resolves(item, corpus)
        ]
        mechanism = self._display_name(edge.get("mechanism") or "")
        if not evidence and not self._valid_evidence(mechanism):
            return "speculative"
        if origin in {"heuristic_emergent", "runtime_heuristic", "agent_interaction_heuristic"}:
            return "inferred"
        declared_status = epistemic_status.strip().lower()
        if declared_status in {"observed", "inferred"}:
            return declared_status
        for text in evidence:
            lowered = text.lower()
            if any(name in lowered for name in anchor_names):
                return "observed"
            if corpus:
                for fragment in re.findall(r"[\u4e00-\u9fff]{4,}", text):
                    if fragment.lower() in corpus:
                        return "observed"
        if corpus and mechanism:
            for fragment in re.findall(r"[\u4e00-\u9fff]{6,}", mechanism):
                if fragment.lower() in corpus:
                    return "observed"
        if self._valid_evidence(mechanism):
            return "inferred"
        return "speculative"

    def _matching_refs(self, text: str, items: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
        lowered = text.lower()
        refs: List[Dict[str, Any]] = []
        for item in items:
            name = str(item.get("name") or item.get("region_name") or item.get("title") or "").strip()
            grounded_terms = self._grounded_terms(item)
            if len(name) < 2 or (name.lower() not in lowered and not any(term in lowered for term in grounded_terms)):
                continue
            if kind == "region":
                region_id = str(item.get("region_id") or item.get("id") or name).strip()
                refs.append({"region_id": region_id, "region_name": name})
            else:
                ref = self._entity_ref(item)
                if ref:
                    refs.append(ref)
        key = "region_id" if kind == "region" else "entity_uuid"
        deduped = self._unique_dicts(refs, key)
        if kind != "region":
            return deduped
        visible_refs: List[Dict[str, Any]] = []
        seen_names: set[str] = set()
        for ref in deduped:
            name_key = str(ref.get("region_name") or "").strip().lower()
            if name_key and name_key in seen_names:
                continue
            if name_key:
                seen_names.add(name_key)
            visible_refs.append(ref)
        return visible_refs

    def _entity_refs_for_family(
        self,
        refs: List[Dict[str, Any]],
        family: str,
    ) -> List[Dict[str, Any]]:
        if family in {"compound_cascade", "other_emergent"}:
            return refs
        type_terms = FAMILY_ENTITY_TYPE_TERMS.get(family) or ()
        name_terms = FAMILY_ENTITY_NAME_TERMS.get(family) or ()
        compatible: List[Dict[str, Any]] = []
        for ref in refs:
            type_text = self._join_text(ref.get("entity_type"), ref.get("labels")).lower().replace("_", "")
            name_text = self._join_text(ref.get("entity_name"), ref.get("entity_summary")).lower()
            # Explicit source types are authoritative. Name matching only helps
            # legacy entities whose source data does not carry a usable type.
            if type_text:
                is_compatible = any(term in type_text for term in type_terms)
            else:
                is_compatible = any(term in name_text for term in name_terms)
            if is_compatible:
                compatible.append(ref)
        return compatible

    def _entity_refs_for_candidate(
        self,
        *,
        path_corpus: str,
        scope_corpus: str,
        path_nodes: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        family: str,
    ) -> List[Dict[str, Any]]:
        explicit_ids: set[str] = set()
        for node in path_nodes:
            value = node.get("target_entity_ids")
            values = value if isinstance(value, (list, tuple, set)) else [value]
            explicit_ids.update(str(item or "").strip() for item in values if str(item or "").strip())

        exact_refs = self._entity_refs_for_family(
            self._matching_refs(path_corpus, entities, "entity"),
            family,
        )
        exact_ids = {str(item.get("entity_uuid") or "") for item in exact_refs}
        refs: List[Dict[str, Any]] = []
        for ref in exact_refs:
            enriched = dict(ref)
            if str(ref.get("entity_uuid") or "") in explicit_ids:
                enriched["scope_basis"] = "mechanism_reference"
                enriched["epistemic_status"] = "observed"
            else:
                enriched["scope_basis"] = "scenario_text_mention"
                enriched["epistemic_status"] = "observed"
            refs.append(enriched)

        broad_text = path_corpus.lower()
        narrow_text = scope_corpus.lower()
        family_terms = FAMILY_ENTITY_NAME_TERMS.get(family) or ()
        for entity in entities:
            ref = self._entity_ref(entity)
            if not ref:
                continue
            entity_id = str(ref.get("entity_uuid") or "")
            if entity_id in exact_ids:
                continue
            compatible = self._entity_refs_for_family([ref], family)
            if not compatible:
                continue
            attributes = self._as_dict(entity.get("attributes") or entity.get("properties") or {})
            source_kind = str(entity.get("source_kind") or attributes.get("source_kind") or "").strip().lower()
            category = str(entity.get("category") or attributes.get("category") or "").strip().lower()
            is_proxy = entity_id.startswith("proxy_") or source_kind == "inferred" or category == "human_proxy"
            descriptor = self._join_text(
                ref.get("entity_name"),
                ref.get("entity_summary"),
                ref.get("entity_type"),
                ref.get("labels"),
                attributes.get("category"),
                attributes.get("subtype"),
                attributes.get("evidence_summary"),
            ).lower()
            shared_terms = [
                term
                for term in family_terms
                if term in descriptor and (term in narrow_text or term in broad_text)
            ]
            explicit_reference = entity_id in explicit_ids
            if not explicit_reference and (is_proxy or not shared_terms):
                continue
            enriched = dict(ref)
            enriched["scope_basis"] = (
                "mechanism_reference" if explicit_reference else "scene_metadata_inference"
            )
            enriched["epistemic_status"] = "inferred"
            refs.append(enriched)
        return self._unique_dicts(refs, "entity_uuid")

    def _entity_ref(self, item: Dict[str, Any]) -> Dict[str, Any]:
        entity_uuid = str(item.get("uuid") or item.get("entity_uuid") or item.get("id") or "").strip()
        name = str(item.get("name") or item.get("title") or "").strip()
        if not entity_uuid or len(name) < 2:
            return {}
        ref: Dict[str, Any] = {"entity_uuid": entity_uuid, "entity_name": name}
        entity_type = self._entity_reference_type(item)
        entity_labels = self._entity_reference_labels(item)
        if entity_type:
            ref["entity_type"] = entity_type
        if entity_labels:
            ref["labels"] = entity_labels
        entity_summary = self._display_name(item.get("summary") or item.get("description") or "")
        if entity_summary:
            ref["entity_summary"] = entity_summary
        return ref

    def _region_refs_for_candidate(
        self,
        *,
        path_corpus: str,
        scope_corpus: str,
        path_nodes: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        entities: List[Dict[str, Any]],
        entity_refs: List[Dict[str, Any]],
        family: str,
    ) -> List[Dict[str, Any]]:
        explicit_ids: set[str] = set()
        for node in path_nodes:
            for key in ("region_id", "target_region_ids"):
                value = node.get(key)
                values = value if isinstance(value, (list, tuple, set)) else [value]
                explicit_ids.update(str(item or "").strip() for item in values if str(item or "").strip())

        entity_names_by_id: Dict[str, str] = {}
        for entity in entities:
            entity_id = str(entity.get("uuid") or entity.get("entity_uuid") or entity.get("id") or "").strip()
            entity_name = str(entity.get("name") or entity.get("title") or "").strip()
            if entity_id and entity_name:
                entity_names_by_id[entity_id] = entity_name
        explicit_anchor_names = [entity_names_by_id[item] for item in explicit_ids if item in entity_names_by_id]
        selected_entity_names = [str(item.get("entity_name") or "").strip() for item in entity_refs]

        narrow_text = scope_corpus.lower()
        broad_text = path_corpus.lower()
        family_terms = FAMILY_REGION_TEXT_TERMS.get(family) or ()
        scored: List[tuple[bool, bool, bool, int, float, int, Dict[str, Any]]] = []
        for region_index, region in enumerate(regions):
            region_id = str(region.get("region_id") or region.get("id") or region.get("name") or "").strip()
            region_name = str(region.get("name") or region.get("region_name") or region_id).strip()
            if not region_id or len(region_name) < 2:
                continue
            grounded_terms = self._grounded_terms(region)
            direct_scope = region_name.lower() in narrow_text or any(term in narrow_text for term in grounded_terms)
            broad_mention = region_name.lower() in broad_text or any(term in broad_text for term in grounded_terms)
            path_positions = [
                position
                for position in [
                    narrow_text.find(region_name.lower()),
                    *[narrow_text.find(term) for term in grounded_terms],
                ]
                if position >= 0
            ]
            path_position = min(path_positions) if path_positions else len(narrow_text) + region_index
            direct_reference = (
                region_id in explicit_ids
                or region_name in explicit_ids
                or any(
                    self._names_overlap(alias, explicit_id)
                    for alias in (region_id, region_name)
                    for explicit_id in explicit_ids
                )
                or any(
                    self._normalized_name_key(region_name) == self._normalized_name_key(name)
                    for name in explicit_anchor_names
                )
            )
            parent_region_id = str(region.get("parent_region_id") or "").strip()
            parent_reference = bool(parent_region_id) and (
                any(
                    self._names_overlap(parent_region_id, explicit_id)
                    for explicit_id in explicit_ids
                )
                or any(
                    self._names_overlap(parent_region_id, name)
                    for name in explicit_anchor_names
                )
            )
            explicit_reference = direct_reference or parent_reference
            entity_anchor = any(self._names_overlap(region_name, name) for name in selected_entity_names if name)
            region_name_key = self._normalized_name_key(region_name)
            exact_entity_anchor = any(
                region_name_key == self._normalized_name_key(name)
                for name in selected_entity_names
                if name
            )
            region_text = self._region_descriptor_text(region)
            shared_terms = [term for term in family_terms if term in broad_text and term in region_text]
            compatible = self._region_is_family_compatible(region, family)
            layer = str(region.get("layer") or "").strip().lower()

            if layer == "subregion" and not any((direct_scope, explicit_reference, entity_anchor)):
                continue
            if not any((direct_scope, broad_mention, explicit_reference, entity_anchor, shared_terms)):
                continue
            # A direct cross-stage region reference remains authoritative when
            # no more concrete entity anchor exists. A parent reference may
            # select a subregion only when that subregion is family-compatible.
            if (
                not direct_scope
                and not compatible
                and not (direct_reference and not entity_refs)
            ):
                continue

            score = 0.0
            score += 140.0 if direct_scope else 0.0
            score += 120.0 if entity_anchor else 0.0
            score += 110.0 if explicit_reference else 0.0
            score += 55.0 if broad_mention else 0.0
            score += min(60.0, len(shared_terms) * 15.0)
            score += 20.0 if compatible else 0.0
            score += 5.0 if layer != "subregion" else 0.0
            if direct_scope:
                basis = "mechanism_path_mention"
                epistemic_status = "observed"
            elif entity_anchor:
                basis = "entity_anchor"
                epistemic_status = "observed"
            elif explicit_reference:
                basis = "mechanism_reference"
                epistemic_status = "inferred"
            elif broad_mention:
                basis = "scenario_text_mention"
                epistemic_status = "inferred"
            else:
                basis = "scene_metadata_inference"
                epistemic_status = "inferred"
            ref = {
                "region_id": region_id,
                "region_name": region_name,
                "scope_basis": basis,
                "epistemic_status": epistemic_status,
            }
            region_type = str(region.get("region_type") or region.get("type") or "").strip()
            if region_type:
                ref["region_type"] = region_type
            scored.append(
                (
                    direct_scope,
                    entity_anchor,
                    exact_entity_anchor,
                    path_position,
                    score,
                    region_index,
                    ref,
                )
            )

        scored.sort(
            key=lambda item: (
                0 if item[0] else 1,
                item[3] if item[0] else 0,
                -item[4],
                item[5],
            )
        )
        exact_entity_scored = [item for item in scored if item[2]]
        overlapping_entity_scored = [item for item in scored if item[1]]
        grounded_scored = [
            item
            for item in scored
            if item[6].get("scope_basis") != "scene_metadata_inference"
        ]
        if exact_entity_scored:
            selected_scored = [item for item in scored if item[0] or item[2]]
        elif overlapping_entity_scored:
            selected_scored = [item for item in scored if item[0] or item[1]]
        else:
            selected_scored = grounded_scored or scored
        refs: List[Dict[str, Any]] = []
        seen_names: set[str] = set()
        for _direct, _entity, _exact_entity, _position, _score, _index, ref in selected_scored:
            name_key = str(ref.get("region_name") or "").strip().lower()
            if name_key in seen_names:
                continue
            seen_names.add(name_key)
            refs.append(ref)
        return refs

    def _region_is_family_compatible(self, region: Dict[str, Any], family: str) -> bool:
        if family in {"compound_cascade", "other_emergent"}:
            return True
        type_text = self._join_text(
            region.get("region_type"),
            region.get("type"),
            region.get("land_use_class"),
            region.get("layer"),
            region.get("tags"),
        ).lower()
        descriptor_text = self._region_descriptor_text(region)
        return (
            any(
                self._region_type_term_matches(type_text, term)
                for term in (FAMILY_REGION_TYPE_TERMS.get(family) or ())
            )
            or any(term in descriptor_text for term in (FAMILY_REGION_TEXT_TERMS.get(family) or ()))
        )

    def _region_type_term_matches(self, type_text: str, term: str) -> bool:
        normalized_term = str(term or "").strip().lower()
        if not normalized_term:
            return False
        if re.search(r"[\u4e00-\u9fff]", normalized_term):
            return normalized_term in type_text
        tokens = set(re.findall(r"[a-z0-9]+", str(type_text or "").lower()))
        if normalized_term in {"ecolog", "agricultur", "logistic"}:
            return any(token.startswith(normalized_term) for token in tokens)
        return normalized_term in tokens

    def _region_descriptor_text(self, region: Dict[str, Any]) -> str:
        return self._join_text(
            region.get("name"),
            region.get("region_name"),
            region.get("description"),
            region.get("region_type"),
            region.get("land_use_class"),
            region.get("tags"),
            region.get("industry_tags"),
            region.get("ecology_assets"),
            region.get("region_constraints"),
            region.get("exposure_channels"),
        ).lower()

    def _names_overlap(self, left: str, right: str) -> bool:
        left_key = self._normalized_name_key(left)
        right_key = self._normalized_name_key(right)
        return bool(left_key and right_key and (left_key in right_key or right_key in left_key))

    def _normalized_name_key(self, value: Any) -> str:
        return re.sub(r"[\s·:：()（）_-]+", "", str(value or "").lower())

    def _entity_reference_type(self, item: Dict[str, Any]) -> str:
        attributes = self._as_dict(item.get("attributes") or item.get("properties") or {})
        direct_candidates = (
            item.get("entity_type"),
            item.get("node_family"),
            item.get("type"),
        )
        for value in direct_candidates:
            normalized = str(value or "").strip()
            if normalized and normalized.lower() not in {"entity", "node"}:
                return normalized
        labels = self._entity_reference_labels(item)
        if labels:
            return labels[0]
        for value in (
            attributes.get("entity_type"),
            attributes.get("node_family"),
            attributes.get("type"),
            attributes.get("category"),
        ):
            normalized = str(value or "").strip()
            if normalized and normalized.lower() not in {"entity", "node"}:
                return normalized
        return ""

    def _entity_reference_labels(self, item: Dict[str, Any]) -> List[str]:
        raw_labels = item.get("labels") or []
        if isinstance(raw_labels, str):
            raw_labels = [raw_labels]
        return self._unique([
            str(value).strip()
            for value in raw_labels
            if str(value or "").strip()
            and str(value).strip().lower() not in {"entity", "node"}
        ])

    def _actor_refs(
        self,
        path_edges: List[Dict[str, Any]],
        path_nodes: List[Dict[str, Any]],
        actors_by_edge: Dict[str, List[Dict[str, Any]]],
        profiles: List[Dict[str, Any]],
        role_demands: List[Dict[str, Any]],
        family: str,
        receptor_node: Dict[str, Any],
        region_refs: List[Dict[str, Any]],
        entity_refs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        demand_refs = self._role_demand_actor_refs(
            path_edges=path_edges,
            receptor_node=receptor_node,
            profiles=profiles,
            role_demands=role_demands,
            family=family,
            region_refs=region_refs,
            entity_refs=entity_refs,
        )
        if role_demands:
            return demand_refs

        refs: List[Dict[str, Any]] = []
        for edge in path_edges:
            refs.extend(actors_by_edge.get(edge["id"], []))
        profile_index: Dict[str, Dict[str, Any]] = {}
        for profile in profiles:
            for value in (profile.get("agent_id"), profile.get("actor_id"), profile.get("id")):
                if value is not None:
                    profile_index[str(value)] = profile
        for node in path_nodes:
            node_id = str(node.get("id") or "")
            if not node_id.startswith("actor::"):
                continue
            profile = profile_index.get(node_id.split("actor::", 1)[1])
            ref = self._actor_ref(profile or {})
            if ref:
                refs.append({
                    **ref,
                    "scope_basis": "mechanism_reference",
                    "epistemic_status": "inferred",
                })
        return self._unique_dicts(
            [
                ref
                for ref in refs
                if self._actor_matches_scope(ref, region_refs, entity_refs)
            ],
            "actor_id",
        )

    def _role_demand_actor_refs(
        self,
        *,
        path_edges: List[Dict[str, Any]],
        receptor_node: Dict[str, Any],
        profiles: List[Dict[str, Any]],
        role_demands: List[Dict[str, Any]],
        family: str,
        region_refs: List[Dict[str, Any]],
        entity_refs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not path_edges or not role_demands:
            return []

        demand_index: Dict[str, Dict[str, Any]] = {}
        for demand in role_demands:
            demand_id = str(
                demand.get("demand_id")
                or demand.get("role_demand_id")
                or demand.get("id")
                or ""
            ).strip()
            if demand_id:
                demand_index[demand_id] = demand
        if not demand_index:
            return []

        path_edge_ids = {str(edge.get("id") or "") for edge in path_edges}
        terminal_edge_id = str(path_edges[-1].get("id") or "")
        receptor_id = str(receptor_node.get("id") or "")
        family_tokens = tuple(token.lower() for token in FAMILY_ROLE_DEMAND_TOKENS.get(family, ()))
        scored: List[tuple[float, str, Dict[str, Any]]] = []

        for profile in profiles:
            if not self._actor_matches_scope(profile, region_refs, entity_refs):
                continue
            best_score = 0.0
            best_demand_id = ""
            for demand_ref in profile.get("role_demand_refs") or []:
                demand_id = str(demand_ref or "").strip()
                demand = demand_index.get(demand_id)
                if not demand:
                    continue
                mechanism_ids = {
                    str(value or "").strip()
                    for value in (demand.get("caused_by_mechanism_ids") or demand.get("mechanism_edge_ids") or [])
                    if str(value or "").strip()
                }
                event_ids = {
                    str(value or "").strip()
                    for value in (demand.get("caused_by_event_ids") or demand.get("event_ids") or [])
                    if str(value or "").strip()
                }
                demand_text = self._join_text(
                    demand.get("demand_key"),
                    demand.get("label_zh"),
                    demand.get("rationale_zh"),
                    demand.get("required_capability_keys"),
                ).lower()
                family_match = bool(family_tokens and any(token in demand_text for token in family_tokens))
                terminal_match = terminal_edge_id in mechanism_ids
                receptor_match = receptor_id in event_ids
                if not family_match:
                    continue

                score = 0.0
                if terminal_match:
                    score += 4.0
                if receptor_match:
                    score += 4.0
                if path_edge_ids & mechanism_ids:
                    score += 1.0
                if family_match:
                    score += 6.0
                if mechanism_ids:
                    score += min(2.0, 2.0 / len(mechanism_ids))
                if event_ids:
                    score += min(2.0, 2.0 / len(event_ids))
                if score > best_score:
                    best_score = score
                    best_demand_id = demand_id

            if best_score <= 0:
                continue
            ref = self._actor_ref(profile)
            if not ref:
                continue
            scored.append((best_score, best_demand_id, ref))

        if not scored:
            return []
        best = max(item[0] for item in scored)
        selected = [item for item in scored if item[0] >= max(8.0, best - 1.0)]
        selected.sort(key=lambda item: (-item[0], str(item[2].get("actor_id") or "")))
        return [
            {
                **ref,
                "matched_role_demand_id": demand_id,
                "matched_role_demand_label": self._display_name(
                    demand_index.get(demand_id, {}).get("label_zh")
                    or demand_index.get(demand_id, {}).get("label")
                    or "受影响对象匹配"
                ),
                "scope_basis": "receptor_role_demand",
                "epistemic_status": "inferred",
            }
            for _score, demand_id, ref in selected[:4]
        ]

    def _actor_matches_scope(
        self,
        profile: Dict[str, Any],
        region_refs: List[Dict[str, Any]],
        entity_refs: List[Dict[str, Any]],
    ) -> bool:
        risk_region_names = [
            str(item.get("region_name") or item.get("region_id") or "").strip()
            for item in region_refs
        ]
        risk_entity_ids = {
            str(item.get("entity_uuid") or "").strip()
            for item in entity_refs
            if str(item.get("entity_uuid") or "").strip()
        }
        profile_regions = self._unique([
            profile.get("primary_region"),
            profile.get("home_region_id"),
            profile.get("home_subregion_id"),
        ])
        profile_entity_ids = {
            str(value or "").strip()
            for value in [
                profile.get("source_entity_uuid"),
                *(profile.get("represented_entity_ids") or []),
            ]
            if str(value or "").strip()
        }
        if not profile_regions and not profile_entity_ids:
            return True
        if risk_entity_ids & profile_entity_ids:
            return True
        return any(
            self._names_overlap(profile_region, risk_region)
            for profile_region in profile_regions
            for risk_region in risk_region_names
            if profile_region and risk_region
        )

    def _actor_ref(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        raw_id = item.get("agent_id", item.get("actor_id", item.get("id")))
        if raw_id is None:
            return None
        try:
            actor_id: int | str = int(raw_id)
        except (TypeError, ValueError):
            actor_id = str(raw_id)
        name = self._display_name(item.get("name") or item.get("username") or item.get("agent_name") or raw_id)
        ref: Dict[str, Any] = {"actor_id": actor_id, "actor_name": name}
        actor_type = self._display_name(item.get("agent_type") or item.get("node_family") or item.get("role_type") or "")
        profession = self._display_name(item.get("profession") or item.get("role_name") or "")
        primary_region = self._display_name(item.get("primary_region") or item.get("home_region_id") or "")
        if actor_type:
            ref["actor_type"] = actor_type
        if profession:
            ref["profession"] = profession
        if primary_region:
            ref["primary_region"] = primary_region
        source_entity_uuid = str(item.get("source_entity_uuid") or "").strip()
        if source_entity_uuid:
            ref["source_entity_uuid"] = source_entity_uuid
        archetype_key = str(item.get("archetype_key") or "").strip()
        if archetype_key:
            ref["archetype_key"] = archetype_key
        representation_level = str(item.get("representation_level") or "").strip()
        if representation_level:
            ref["representation_level"] = representation_level
        lifecycle = item.get("runtime_lifecycle") or {}
        lifecycle_status = str(
            item.get("lifecycle_status")
            or (lifecycle.get("lifecycle_status") if isinstance(lifecycle, Mapping) else "")
            or "active"
        )
        ref["lifecycle_status"] = lifecycle_status
        ref["role_demand_refs"] = self._unique(item.get("role_demand_refs") or [])
        ref["spatial_anchor_refs"] = self._unique(item.get("spatial_anchor_refs") or [])
        ref["evidence_refs"] = self._unique(item.get("evidence_refs") or [])
        ref["profile_confidence"] = self._probability(
            item.get("profile_confidence", item.get("evidence_confidence")),
            0.5,
        )
        return ref

    def _evidence_row(
        self,
        edge: Dict[str, Any],
        node_index: Dict[str, Dict[str, Any]],
        status: str,
        confidence: float,
        corpus: str,
    ) -> Dict[str, Any]:
        source_name = self._display_name(node_index[edge["source"]].get("name") or edge["source"])
        target_name = self._display_name(node_index[edge["target"]].get("name") or edge["target"])
        facts = [
            self._display_name(item)
            for item in (edge.get("evidence") or [])
            if self._valid_evidence(item) and self._evidence_resolves(item, corpus)
        ]
        mechanism = self._display_name(edge.get("mechanism") or edge.get("relation_label") or "机制关系推断")
        summary = "；".join(facts[:3]) or f"机制推断：{mechanism}"
        return {
            "evidence_id": f"evidence_{edge['id']}",
            "source_type": "mechanism_edge",
            "title": f"机制依据：{source_name}至{target_name}",
            "summary": summary,
            "confidence": confidence,
            "epistemic_status": status,
            "epistemic_status_label": {"observed": "有来源支撑", "inferred": "机制推断", "speculative": "推测"}[status],
            "source_ref": edge["id"],
            "related_chain_steps": [source_name, target_name],
            "region_scope": [],
            "entity_refs": [],
            "extracted_facts": facts[:6],
        }

    def _family(self, text: str, receptor_text: str = "", receptor_type: str = "") -> str:
        lowered = text.lower()
        receptor_lowered = receptor_text.lower()
        receptor_type = receptor_type.lower()
        if receptor_type == "governance":
            return "governance_response"
        if receptor_type == "infrastructure":
            if any(token in receptor_lowered for token in ("交通", "道路", "物流", "港口", "机场", "航班", "transport", "road")):
                return "mobility_logistics"
            return "infrastructure_continuity"
        if receptor_type == "human":
            return "health_safety"
        if receptor_type == "ecological":
            return "ecological_environment"
        if receptor_type == "economy":
            return "economy_livelihood"

        receptor_ranked = []
        for key, definition in RISK_FAMILIES.items():
            if key == "other_emergent":
                continue
            keyword_hits = sum(
                1
                for token in definition["keywords"]
                if token and token.lower() in receptor_lowered
            )
            strong_hits = sum(
                1
                for token in RECEPTOR_STRONG_TERMS.get(key, ())
                if token and token.lower() in receptor_lowered
            )
            receptor_ranked.append((strong_hits * 20 + keyword_hits * 5, key))

        receptor_ranked.sort(
            key=lambda item: (
                -item[0],
                FAMILY_CLASSIFICATION_PRIORITY.get(item[1], 99),
                item[1],
            )
        )
        if receptor_ranked and receptor_ranked[0][0] > 0:
            return receptor_ranked[0][1]

        path_ranked = []
        for key, definition in RISK_FAMILIES.items():
            if key == "other_emergent":
                continue
            score = sum(1 for token in definition["keywords"] if token and token.lower() in lowered)
            path_ranked.append((score, key))
        path_ranked.sort(
            key=lambda item: (
                -item[0],
                FAMILY_CLASSIFICATION_PRIORITY.get(item[1], 99),
                item[1],
            )
        )
        return path_ranked[0][1] if path_ranked and path_ranked[0][0] > 0 else "other_emergent"

    def _monitoring_metrics(
        self,
        family: str,
        receptor: Dict[str, Any],
        scenario_state_schema: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        family_metrics = {
            key: {"key": key, "label": label, "polarity": polarity, "weight": weight}
            for key, label, polarity, weight in RISK_FAMILIES[family]["metrics"]
        }
        receptor_text = self._join_text(receptor.get("name"), receptor.get("description"), receptor.get("node_type")).lower()
        family_keywords = [str(item).lower() for item in RISK_FAMILIES[family].get("keywords") or []]
        generic_receptor_terms = {"风险", "影响", "安全", "健康", "暴露", "响应", "传播", "中断", "系统", "受体"}
        distinctive_terms = [
            token
            for token in family_keywords
            if re.search(r"[\u4e00-\u9fff]", token)
            and len(token) >= 2
            and token not in generic_receptor_terms
            and token in receptor_text
        ]
        scenario_metrics: List[tuple[int, Dict[str, Any]]] = []
        for key, definition in scenario_state_schema.items():
            if not isinstance(definition, dict):
                continue
            legacy_metric = str(definition.get("legacy_metric") or "").strip()
            text = self._join_text(key, definition.get("label"), definition.get("description")).lower()
            relevance_score = 0
            if legacy_metric in family_metrics or str(key) in family_metrics:
                relevance_score += 100
            relevance_score += sum(8 for token in distinctive_terms if token in text)
            relevance_score += sum(1 for token in family_keywords if token and token in text)
            if relevance_score < 3:
                continue
            label = self._display_name(definition.get("label") or "")
            if not re.search(r"[\u4e00-\u9fff]", label):
                label = family_metrics.get(legacy_metric, {}).get("label") or f"{RISK_FAMILIES[family]['label']}状态"
            polarity = str(definition.get("polarity") or family_metrics.get(legacy_metric, {}).get("polarity") or "higher_is_worse")
            if polarity not in {"higher_is_worse", "higher_is_better"}:
                polarity = family_metrics.get(legacy_metric, {}).get("polarity") or "higher_is_worse"
            scenario_metrics.append((relevance_score, {
                "key": str(key),
                "label": label,
                "polarity": polarity,
                "weight": float(family_metrics.get(legacy_metric, {}).get("weight") or 0.5),
                "legacy_metric": legacy_metric,
            }))

        scenario_metrics.sort(key=lambda item: (-item[0], item[1]["key"]))
        metrics = [item[1] for item in scenario_metrics[:1]]
        used_legacy = {item.get("legacy_metric") or item["key"] for item in metrics}
        for key, metric in family_metrics.items():
            if key in used_legacy:
                continue
            metrics.append(dict(metric))
            if len(metrics) >= 3:
                break
        total_weight = sum(float(item.get("weight") or 0) for item in metrics) or 1.0
        for metric in metrics:
            metric["weight"] = round(float(metric.get("weight") or 0) / total_weight, 3)
            metric["thresholds"] = {"elevated": 52, "critical": 72, "resolved": 35}
        return metrics

    def _impact_score(
        self,
        variables: List[Dict[str, Any]],
        receptor_node: Dict[str, Any],
        region_refs: List[Dict[str, Any]],
        actor_refs: List[Dict[str, Any]],
    ) -> float:
        intensities = [
            self._score(item.get("intensity_0_100", item.get("intensity")), 50.0)
            for item in variables
            if item.get("intensity_0_100") is not None or item.get("intensity") is not None
        ]
        intensity = max(intensities) if intensities else 50.0
        receptor_confidence = self._probability(receptor_node.get("confidence"), 0.6) * 100.0
        scope_load = min(15.0, len(region_refs) * 3.0 + len(actor_refs))
        return round(min(100.0, intensity * 0.5 + receptor_confidence * 0.35 + scope_load), 1)

    def _propagation_score(self, edges: List[Dict[str, Any]]) -> float:
        confidence = sum(self._probability(item.get("confidence"), 0.6) for item in edges) / max(1, len(edges))
        cross_region = any(str(item.get("scope") or "").lower() in {"cross_region", "cross_scale", "systemic"} for item in edges)
        return round(min(100.0, confidence * 70.0 + (15.0 if cross_region else 0.0) + min(15.0, len(edges) * 4.0)), 1)

    def _actionability_score(
        self,
        metrics: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        actors: List[Dict[str, Any]],
    ) -> float:
        return round(min(92.0, 38.0 + len(metrics) * 8.0 + len(regions) * 4.0 + len(actors) * 2.0), 1)

    def _grounded_receptor_name(
        self,
        receptor: Dict[str, Any],
        entity_refs: List[Dict[str, Any]],
        actor_refs: List[Dict[str, Any]],
        region_refs: List[Dict[str, Any]],
    ) -> str:
        mechanism_name = self._display_name(receptor.get("name") or receptor.get("id") or "受影响对象")
        generic_receptors = {
            "受影响人群",
            "敏感生态系统",
            "渔业水域与食品供应链",
            "交通与疏散系统",
            "应急治理与跨部门协同体系",
            "关键物资供应体系",
            "医疗服务系统",
        }
        if mechanism_name not in generic_receptors:
            return mechanism_name

        concrete_entities = []
        for ref in entity_refs:
            entity_id = str(ref.get("entity_uuid") or "")
            entity_name = self._display_name(ref.get("entity_name") or "")
            entity_type = self._join_text(ref.get("entity_type"), ref.get("labels")).lower()
            if not entity_name or entity_id.startswith("proxy_") or "region" in entity_type:
                continue
            type_priority = 0
            if "ecologicalreceptor" in entity_type:
                type_priority = 30
            elif "infrastructure" in entity_type:
                type_priority = 25
            elif any(token in entity_type for token in ("human", "government", "organization")):
                type_priority = 20
            elif "environmentalcarrier" in entity_type:
                type_priority = 10
            evidence_priority = 5 if str(ref.get("epistemic_status") or "") == "observed" else 0
            concrete_entities.append((type_priority + evidence_priority, entity_name))
        if concrete_entities:
            concrete_entities.sort(key=lambda item: (-item[0], item[1]))
            return concrete_entities[0][1]

        for ref in region_refs:
            region_name = self._display_name(ref.get("region_name") or "")
            if region_name and region_name not in mechanism_name:
                return f"{region_name}{mechanism_name}"

        for ref in actor_refs:
            actor_name = self._display_name(ref.get("actor_name") or "")
            if actor_name:
                return actor_name
        return mechanism_name

    def _deterministic_title(self, receptor: Dict[str, Any], family: str) -> str:
        name = self._display_name(receptor.get("name") or receptor.get("id") or "受影响对象")
        if name.endswith("风险"):
            return name
        if not name.startswith("受影响") and any(
            token in name
            for token in (
                "污染",
                "中断",
                "受损",
                "受影响",
                "影响",
                "暴露",
                "恐慌",
                "失效",
                "短缺",
                "退化",
                "承压",
                "受阻",
                "过载",
                "下降",
            )
        ):
            return f"{name}风险"
        if name.endswith("受体"):
            name = name[:-2]
            if family == "ecological_environment":
                return f"{name}暴露风险"
            if family == "health_safety":
                return f"{name}安全暴露风险"
        if family == "governance_response" and any(token in name for token in ("政府", "治理", "应急", "响应", "协调")):
            return f"{name}承压风险"
        suffixes = {
            "ecological_environment": "功能受损风险",
            "health_safety": "暴露与健康风险",
            "infrastructure_continuity": "连续性风险",
            "mobility_logistics": "中断风险",
            "resource_supply": "污染与供应风险",
            "economy_livelihood": "生计受损风险",
            "governance_response": "响应承压风险",
            "information_trust": "信任受损风险",
            "compound_cascade": "复合级联风险",
            "other_emergent": "场景影响风险",
        }
        return f"{name}{suffixes.get(family, '影响风险')}"

    def _stronger_epistemic_status(self, first: str | None, second: str | None) -> str:
        ranks = {"speculative": 0, "inferred": 1, "observed": 2}
        values = [item for item in (first, second) if item in ranks]
        if not values:
            return "speculative"
        return max(values, key=lambda item: ranks[item])

    def _disambiguate_titles(self, candidates: List[Dict[str, Any]]) -> None:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for candidate in candidates:
            grouped.setdefault(str(candidate.get("title") or ""), []).append(candidate)
        for title, items in grouped.items():
            if not title or len(items) < 2:
                continue
            for candidate in items:
                steps = list(candidate.get("chain_steps") or [])
                qualifier = steps[-2] if len(steps) >= 2 else "不同机制路径"
                candidate["title"] = f"{qualifier}引发的{title}"

    def _deterministic_summary(
        self,
        trigger_name: str,
        path_nodes: List[Dict[str, Any]],
        receptor: Dict[str, Any],
        family: str,
    ) -> str:
        middle = [self._display_name(item.get("name") or item["id"]) for item in path_nodes[1:-1]]
        pathway = "、".join(middle) or "当前机制路径"
        receptor_name = self._display_name(receptor.get("name") or receptor["id"])
        return f"{trigger_name}通过{pathway}作用于{receptor_name}，可能造成{RISK_FAMILIES[family]['outcome']}。"

    def _consequence(
        self,
        receptor: Dict[str, Any],
        family: str,
        *,
        receptor_name: str = "",
    ) -> str:
        description = self._display_name(receptor.get("description") or "")
        if description:
            event_clause = re.search(r"用户描述中的[“\"](.+?)[”\"].*?明确指向", description)
            if event_clause:
                return f"{event_clause.group(1)}，可能造成{RISK_FAMILIES[family]['outcome']}。"
            if "明确指向" in description and "环节" in description:
                return str(RISK_FAMILIES[family]["outcome"])
            if not any(token in description for token in ("系统暂推断", "待审阅", "为连接")):
                return description[:240]
        name = receptor_name or self._display_name(receptor.get("name") or receptor.get("id") or "受影响对象")
        templates = {
            "ecological_environment": f"{name}的栖息地完整性与生态功能可能下降。",
            "health_safety": f"{name}的暴露水平与人身安全风险可能上升。",
            "infrastructure_continuity": f"{name}的关键服务可能中断或降级。",
            "mobility_logistics": f"{name}的通行、运输或疏散能力可能下降。",
            "resource_supply": f"{name}的供应能力与使用安全可能受损。",
            "economy_livelihood": f"{name}的经营、生计与收入稳定性可能受损。",
            "governance_response": f"{name}的协调、执行与应急响应能力可能承压。",
            "information_trust": f"{name}的信息可信度与公众信任可能下降。",
            "compound_cascade": f"{name}可能在反馈路径中与其他系统相互放大。",
            "other_emergent": f"{name}可能出现可监测的场景特异影响。",
        }
        return templates.get(family, f"{name}可能受到具体机制路径影响。")

    def _trigger_name(self, variables: List[Dict[str, Any]], source_node: Dict[str, Any]) -> str:
        if variables:
            variable = variables[0]
            raw_name = str(variable.get("name") or variable.get("title") or "").strip()
            if raw_name and raw_name.lower() not in INTERNAL_DISPLAY_TOKENS:
                return self._display_name(raw_name)
            description = self._display_name(variable.get("description") or "")
            if description:
                return description[:80]
        return self._display_name(source_node.get("name") or source_node["id"])

    def _tags(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[str]:
        values = [
            *[self._display_name(item.get("name") or "") for item in nodes],
            *[self._display_name(item.get("relation_label") or "") for item in edges],
        ]
        return [item for item in self._unique(values) if 2 <= len(item) <= 30 and item.lower() not in INTERNAL_DISPLAY_TOKENS][:8]

    def _interventions(self, risk_id: str, title: str, chain_steps: List[str], regions: List[str]) -> List[Dict[str, Any]]:
        target = regions[0] if regions else "关键受影响对象"
        return [
            {
                "intervention_id": f"monitor_{risk_id}",
                "name": f"监测{target}关键指标",
                "policy_type": "monitor",
                "description": f"围绕{title}的机制路径持续监测并复核证据。",
                "target_chain_steps": chain_steps[:3],
                "expected_direct_effects": ["提前识别风险升级"],
                "expected_second_order_effects": ["为干预比较保留时间窗口"],
                "benefit_clusters": [],
                "hurt_clusters": [],
                "friction_points": ["需要持续更新监测数据"],
                "confidence": 0.68,
            }
        ]

    def _branches(self, risk_id: str, title: str) -> List[Dict[str, Any]]:
        return [
            {
                "branch_id": f"baseline_{risk_id}",
                "name": "维持当前响应",
                "description": f"保持当前参数，观察{title}的自然演化。",
                "assumptions": ["不新增提前干预"],
                "target_interventions": [],
                "comparison_focus": ["风险峰值", "影响范围", "持续时间"],
                "branch_type": "baseline",
            },
            {
                "branch_id": f"monitor_{risk_id}",
                "name": "提前监测与干预",
                "description": f"围绕{title}提前监测并比较干预效果。",
                "assumptions": ["监测信号能够及时触发"],
                "target_interventions": [f"monitor_{risk_id}"],
                "comparison_focus": ["处置窗口", "风险张力", "受影响对象"],
                "branch_type": "intervention",
            },
        ]

    def _source_signature(
        self,
        *,
        variable_refs: List[str],
        source_node_id: str,
        mechanism_edge_ids: List[str],
        receptor_node_id: str,
        region_ids: List[str],
        family: str,
    ) -> str:
        payload = {
            "variables": sorted(variable_refs),
            "source": source_node_id,
            "edges": mechanism_edge_ids,
            "receptor": receptor_node_id,
            "regions": sorted(region_ids),
            "family": family,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()

    def _time_horizon(self, edges: List[Dict[str, Any]], temporal_profile: Dict[str, Any]) -> str:
        labels = [str(item.get("latency") or "").strip() for item in edges if item.get("latency")]
        if labels:
            return "至".join(self._unique([self._latency_label(item) for item in labels]))
        rounds = temporal_profile.get("total_rounds")
        minutes = temporal_profile.get("minutes_per_round")
        if rounds and minutes:
            return f"约 {max(1, round(float(rounds) * float(minutes) / 60))} 小时"
        return "当前推演窗口"

    def _latency_label(self, value: str) -> str:
        return {
            "immediate": "即时",
            "hours": "数小时",
            "days": "数天",
            "weeks": "数周",
            "months": "数月",
            "unknown": "时间待确认",
        }.get(value.lower(), self._display_name(value))

    def _normalize_node(self, item: Any, index: int) -> Dict[str, Any]:
        payload = self._as_dict(item)
        node_id = str(payload.get("id") or payload.get("node_id") or f"mechanism_node_{index + 1}").strip()
        display_values = [payload.get("name"), payload.get("label"), payload.get("description")]
        return {
            **payload,
            "id": node_id,
            "name": self._display_name(payload.get("name") or payload.get("label") or node_id),
            "node_type": str(payload.get("node_type") or payload.get("type") or "process").strip().lower(),
            "has_forbidden_display_value": any(self._contains_forbidden_display_value(value) for value in display_values),
        }

    def _build_minimal_graph(
        self,
        *,
        variables: List[Dict[str, Any]],
        regions: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        transport_edges: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        region_node_ids: Dict[str, str] = {}
        for region in regions:
            region_id = str(region.get("region_id") or region.get("id") or region.get("name") or "").strip()
            if not region_id:
                continue
            node_id = f"region::{region_id}"
            region_node_ids[region_id] = node_id
            name = self._display_name(region.get("name") or region_id)
            if name:
                region_node_ids[name] = node_id
            nodes.append({
                "id": node_id,
                "name": name,
                "node_type": self._region_node_type(region),
                "node_origin": "spatial_region",
                "region_id": region_id,
                "region_type": str(region.get("region_type") or ""),
                "description": self._display_name(region.get("description") or f"{name}场景区域"),
                "evidence": [f"场景区域：{name}"],
                "confidence": 0.7,
            })
        for edge in transport_edges:
            source_region = str(edge.get("source_region_id") or "").strip()
            target_region = str(edge.get("target_region_id") or "").strip()
            source = region_node_ids.get(source_region)
            target = region_node_ids.get(target_region)
            if not source or not target:
                continue
            source_name = next((item["name"] for item in nodes if item["id"] == source), source_region)
            target_name = next((item["name"] for item in nodes if item["id"] == target), target_region)
            channel_label = self._channel_label(edge.get("channel_type"))
            edge_evidence = self._as_dict(edge.get("evidence") or {})
            neighbour_fallback = str(edge_evidence.get("ordering") or "").lower() == "neighbor_fallback"
            edges.append({
                "id": str(edge.get("edge_id") or edge.get("id") or f"transport::{source_region}::{target_region}"),
                "source": source,
                "target": target,
                "relation_label": channel_label,
                "mechanism": f"{source_name}通过{channel_label}影响{target_name}",
                "edge_role": "transport_connectivity",
                "relation_kind": str(edge.get("channel_type") or "spatial_connectivity"),
                "origin": "spatial_neighbor_fallback" if neighbour_fallback else str(edge.get("origin") or "transport_graph"),
                "epistemic_status": "speculative" if neighbour_fallback else str(edge.get("epistemic_status") or "inferred"),
                "trigger_conditions": [f"{channel_label}处于活跃状态"],
                "latency": "hours" if int(edge.get("travel_time_rounds") or 1) <= 1 else "days",
                "direction": "positive",
                "scope": "cross_region" if source_region != target_region else "local",
                "evidence": [
                    "地图空间邻接仅用于定位，不代表风险因果机制"
                    if neighbour_fallback
                    else f"场景运输关系：{source_name}至{target_name}"
                ],
                "confidence": self._probability(edge.get("confidence"), 0.6),
            })

        for index, variable in enumerate(variables):
            variable_id = str(variable.get("variable_id") or variable.get("id") or f"variable_{index + 1}")
            source_id = f"variable::{variable_id}"
            variable_name = self._trigger_name([variable], {"id": source_id, "name": "场景变量"})
            nodes.append({
                "id": source_id,
                "name": variable_name,
                "node_type": "source",
                "description": self._display_name(variable.get("description") or variable_name),
                "evidence": [f"用户注入变量：{variable_name}"],
                "confidence": 0.9,
            })
            for target_region in variable.get("target_regions") or []:
                target_id = region_node_ids.get(str(target_region))
                if not target_id:
                    target_id = next(
                        (node_id for region_id, node_id in region_node_ids.items() if str(target_region) in region_id),
                        None,
                    )
                if not target_id:
                    continue
                target_name = next((item["name"] for item in nodes if item["id"] == target_id), str(target_region))
                edges.append({
                    "id": f"variable_edge::{variable_id}::{target_id}",
                    "source": source_id,
                    "target": target_id,
                    "relation_label": "变量直接作用",
                    "mechanism": f"{variable_name}直接作用于{target_name}",
                    "edge_role": "direct_spatial_scope",
                    "origin": "user_variable_target",
                    "epistemic_status": "observed",
                    "trigger_conditions": ["变量进入生效轮次"],
                    "latency": "immediate",
                    "direction": "positive",
                    "scope": "local",
                    "evidence": [f"变量目标区域：{target_name}"],
                    "confidence": 0.9,
                })

        if relationships:
            profile_index = {
                str(item.get("agent_id") or item.get("actor_id") or item.get("id")): item
                for item in profiles
                if item.get("agent_id") is not None or item.get("actor_id") is not None or item.get("id") is not None
            }
            actor_nodes: Dict[str, str] = {}
            for relation in relationships:
                source_actor = str(relation.get("source_agent_id") or "")
                target_actor = str(relation.get("target_agent_id") or "")
                if source_actor not in profile_index or target_actor not in profile_index:
                    continue
                for actor_id in (source_actor, target_actor):
                    if actor_id in actor_nodes:
                        continue
                    profile = profile_index[actor_id]
                    node_id = f"actor::{actor_id}"
                    actor_nodes[actor_id] = node_id
                    nodes.append({
                        "id": node_id,
                        "name": self._display_name(profile.get("name") or profile.get("username") or f"主体{actor_id}"),
                        "node_type": self._profile_node_type(profile),
                        "node_origin": "agent_profile",
                        "actor_id": actor_id,
                        "description": self._display_name(profile.get("description") or profile.get("profession") or "场景主体"),
                        "evidence": [],
                        "confidence": 0.6,
                    })
                label = self._display_name(relation.get("relation_label_zh") or relation.get("relation_label") or "主体机制关系")
                if not re.search(r"[\u4e00-\u9fff]", label):
                    label = "主体机制关系"
                edges.append({
                    "id": str(relation.get("edge_id") or relation.get("id") or f"agent_edge::{source_actor}::{target_actor}"),
                    "source": actor_nodes[source_actor],
                    "target": actor_nodes[target_actor],
                    "relation_label": label,
                    "mechanism": self._display_name(relation.get("mechanism") or f"两个主体通过{label}相互作用"),
                    "edge_role": "agent_relationship",
                    "relation_kind": str(relation.get("edge_type") or relation.get("relation_type") or "agent_relationship"),
                    "origin": str(relation.get("origin") or "agent_relationship"),
                    "epistemic_status": str(relation.get("epistemic_status") or ""),
                    "trigger_conditions": list(relation.get("trigger_conditions") or []),
                    "latency": str(relation.get("latency") or "unknown"),
                    "direction": str(relation.get("direction") or "conditional"),
                    "scope": str(relation.get("scope") or "local"),
                    "evidence": list(relation.get("evidence_anchors") or relation.get("evidence") or []),
                    "confidence": self._probability(relation.get("confidence"), 0.5),
                })
        return {"source": "minimal_transport_relation_graph", "nodes": nodes, "edges": edges}

    def _region_node_type(self, region: Dict[str, Any]) -> str:
        text = self._join_text(region.get("region_type"), region.get("name"), region.get("tags")).lower()
        if any(token in text for token in ("transport", "infrastructure", "交通", "基础设施", "港口", "机场")):
            return "infrastructure"
        if any(token in text for token in ("governance", "civic", "治理", "应急")):
            return "governance"
        if any(token in text for token in ("ecolog", "wetland", "habitat", "生态", "湿地", "栖息地", "保护区")):
            return "ecological"
        return "receptor"

    def _profile_node_type(self, profile: Dict[str, Any]) -> str:
        text = self._join_text(profile.get("agent_type"), profile.get("role_type"), profile.get("profession")).lower()
        if any(token in text for token in ("government", "governance", "regulator", "政府", "监管", "应急")):
            return "governance"
        if any(token in text for token in ("infrastructure", "carrier", "交通", "设施")):
            return "infrastructure"
        if any(token in text for token in ("human", "resident", "tourist", "居民", "游客", "人群")):
            return "human"
        return "receptor"

    def _channel_label(self, value: Any) -> str:
        token = str(value or "").strip().lower()
        labels = {
            "river_reach": "河流水文传输",
            "marine_current": "海洋洋流传输",
            "water_flow": "水流传输",
            "surface_runoff": "地表径流传输",
            "transport_flow": "交通网络传输",
            "road_corridor": "道路走廊传输",
            "atmospheric": "大气扩散",
            "environmental_link": "环境介质传输",
        }
        return labels.get(token, "场景传播关系")

    def _normalize_edge(self, item: Any, index: int) -> Dict[str, Any]:
        payload = self._as_dict(item)
        edge_id = str(payload.get("id") or payload.get("edge_id") or f"mechanism_edge_{index + 1}").strip()
        evidence = list(payload.get("evidence") or [])
        display_values = [payload.get("relation_label"), payload.get("label"), payload.get("mechanism"), *evidence]
        return {
            **payload,
            "id": edge_id,
            "source": str(payload.get("source") or payload.get("source_id") or "").strip(),
            "target": str(payload.get("target") or payload.get("target_id") or "").strip(),
            "relation_label": self._display_name(payload.get("relation_label") or payload.get("label") or "机制关联"),
            "evidence": evidence,
            "has_forbidden_display_value": (
                any(self._contains_forbidden_display_value(value) for value in display_values)
                or any(self._contains_placeholder_evidence(value) for value in evidence)
            ),
        }

    def _node_type(self, node: Dict[str, Any]) -> str:
        return str(node.get("node_type") or "process").strip().lower()

    def _anchor_names(self, regions: List[Dict[str, Any]], entities: List[Dict[str, Any]]) -> set[str]:
        names = set()
        for item in [*regions, *entities]:
            name = str(item.get("name") or item.get("region_name") or "").strip().lower()
            if len(name) >= 2:
                names.add(name)
            names.update(self._grounded_terms(item))
        return names

    def _grounded_terms(self, item: Dict[str, Any]) -> set[str]:
        values: List[str] = []
        for key in ("feature_names", "aliases", "source_names", "source_feature_names"):
            value = item.get(key)
            if isinstance(value, (list, tuple, set)):
                values.extend(str(entry or "").strip() for entry in value)
            elif value:
                values.extend(re.split(r"[、,，;/；|]", str(value)))

        description = str(item.get("description") or "")
        source_match = re.search(r"由\s*(.+?)\s*等\s*\d+\s*个空间要素归并", description)
        if source_match:
            values.extend(re.split(r"[、,，;/；|]", source_match.group(1)))

        terms = set()
        for value in values:
            term = re.sub(r"^[\s·:：-]+|[\s·:：-]+$", "", str(value or "")).lower()
            if 2 <= len(term) <= 24 and re.search(r"[\u4e00-\u9fff]", term):
                terms.add(term)
                reduced = re.sub(r"(?:水域|湿地|海岸线|周边|片区|街道|公园|区域)$", "", term).strip()
                if len(reduced) >= 2:
                    terms.add(reduced)
        return terms

    def _valid_evidence(self, value: Any) -> bool:
        text = str(value or "").strip()
        return bool(text) and not self._contains_placeholder_evidence(text) and not self._contains_forbidden_display_value(text)

    def _evidence_resolves(self, value: Any, corpus: str) -> bool:
        text = str(value or "").strip()
        section_match = re.search(r"第\s*(\d+)\s*节", text)
        if not section_match:
            return True
        section = section_match.group(1)
        return any(
            marker in corpus
            for marker in (f"第{section}节", f"## {section}.", f"##{section}.")
        )

    def _contains_placeholder_evidence(self, value: Any) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False
        return any(token in text for token in PLACEHOLDER_EVIDENCE)

    def _contains_forbidden_display_value(self, value: Any) -> bool:
        text = str(value or "").strip().lower()
        if not text:
            return False
        if any(token in text for token in INTERNAL_VARIABLE_TOKENS):
            return True
        if text in COLOR_DISPLAY_TOKENS:
            return True
        color_pattern = "|".join(re.escape(token) for token in sorted(COLOR_DISPLAY_TOKENS))
        if re.search(rf"(?<![a-z0-9_])(?:{color_pattern})(?![a-z0-9_])", text):
            return True
        if re.fullmatch(r"#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})", text):
            return True
        if re.fullmatch(r"(?:rgb|rgba|hsl|hsla)\([^)]*\)", text):
            return True
        return False

    def _display_name(self, value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if self._contains_forbidden_display_value(text):
            return ""
        return text

    def _candidate_ledger_item(self, candidate: Dict[str, Any], status: str, reason: str) -> Dict[str, Any]:
        return {
            "risk_id": candidate.get("risk_id"),
            "source_signature": candidate.get("source_signature"),
            "status": status,
            "reason": reason,
            "title": candidate.get("title"),
            "primary_family": candidate.get("primary_family"),
            "priority_score": candidate.get("priority_score"),
            "evidence_strength_score": candidate.get("evidence_strength_score"),
            "mechanism_node_ids": candidate.get("mechanism_node_ids") or [],
            "mechanism_edge_ids": candidate.get("mechanism_edge_ids") or [],
        }

    def _rejected_edge(self, edge: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "status": "rejected",
            "reason": reason,
            "mechanism_edge_ids": [edge.get("id")],
            "source": edge.get("source"),
            "target": edge.get("target"),
        }

    def _zero_reason(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        paths: List[List[Dict[str, Any]]],
        ledger: List[Dict[str, Any]],
    ) -> str:
        if not nodes:
            return "场景尚未形成可用机制节点"
        if not edges:
            return "场景尚未形成引用完整的机制关系"
        if not paths:
            return "机制图中没有从压力源到受影响对象的有效路径"
        reasons = [str(item.get("reason") or "") for item in ledger if item.get("status") == "rejected"]
        return reasons[0] if reasons else "没有候选风险通过证据校验"

    def _quality_flags(
        self,
        dangling_count: int,
        invalid_display_count: int,
        definitions: List[Dict[str, Any]],
        paths: List[Any],
    ) -> List[str]:
        flags = []
        if dangling_count:
            flags.append("dangling_mechanism_references_rejected")
        if invalid_display_count:
            flags.append("invalid_display_references_rejected")
        if paths and not definitions:
            flags.append("no_risk_candidate_passed_evidence_threshold")
        if not paths:
            flags.append("no_valid_mechanism_path")
        for definition in definitions:
            flags.extend(str(item) for item in (definition.get("quality_flags") or []) if item)
        return self._unique(flags)

    def _data_source_summary(self, value: Any) -> Dict[str, Any]:
        payload = self._as_dict(value)
        if not payload:
            return {"source": "未提供数据来源摘要", "region_count": 0, "entity_count": 0}
        return {
            "source": self._display_name(payload.get("source") or "场景准备产物"),
            "region_count": len(payload.get("regions") or []),
            "entity_count": len(payload.get("entities") or []),
            "agent_count": len(payload.get("profiles") or payload.get("agents") or []),
        }

    def _as_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "to_dict"):
            payload = value.to_dict()
            return dict(payload) if isinstance(payload, dict) else {}
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return {}

    def _probability(self, value: Any, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if number > 1:
            number /= 100.0
        return max(0.0, min(1.0, number))

    def _score(self, value: Any, default: float) -> float:
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _join_text(self, *values: Any) -> str:
        parts = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                parts.extend(str(item) for item in value if item is not None)
            elif isinstance(value, dict):
                parts.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
            else:
                parts.append(str(value))
        return " ".join(item for item in parts if item.strip())

    def _unique(self, values: Iterable[Any]) -> List[Any]:
        result = []
        seen = set()
        for value in values:
            key = str(value)
            if value in (None, "") or key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    def _unique_dicts(self, values: Iterable[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
        result = []
        seen = set()
        for item in values:
            token = str(item.get(key) or "")
            if not token or token in seen:
                continue
            seen.add(token)
            result.append(item)
        return result
