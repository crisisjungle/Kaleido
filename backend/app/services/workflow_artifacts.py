"""Versioned workflow projections for the four-step Kaleido product flow.

These DTOs do not replace the existing runtime artifacts.  They provide a
stable, user-facing contract over the current Step 1-4 truth sources so each
step can evolve without teaching the frontend every legacy file shape.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional


BACKGROUND_FOUNDATION_CONTRACT_VERSION = "background-foundation.v2"
SCENARIO_DEFINITION_CONTRACT_VERSION = "scenario-definition.v2"
RUNTIME_LEDGER_CONTRACT_VERSION = "runtime-ledger.v2"
ANALYSIS_BUNDLE_CONTRACT_VERSION = "analysis-bundle.v2"


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        token = _text(value)
        if token and token not in seen:
            result.append(token)
            seen.add(token)
    return result


def project_background_foundation(
    foundation: Optional[Mapping[str, Any]],
    *,
    effort_snapshot_ref: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    source = _mapping(foundation)
    scene_semantics = _mapping(source.get("scene_semantics"))
    known_entities = _list(scene_semantics.get("known_entities"))
    target_catalog = _list(source.get("target_catalog"))
    foundation_id = _text(
        source.get("foundation_id")
        or source.get("artifact_id")
        or source.get("scene_id")
        or source.get("seed_id")
        or source.get("project_id")
    )
    return {
        "foundation_id": foundation_id,
        "contract_version": BACKGROUND_FOUNDATION_CONTRACT_VERSION,
        "source_contract_version": _text(source.get("contract_version")) or "foundation.legacy",
        "area_of_interest": {
            "location": source.get("location") or source.get("area_label") or "",
            "region_ids": _unique(source.get("region_ids") or []),
            "regions": _list(source.get("regions") or source.get("selected_regions")),
        },
        "spatial_anchors": target_catalog or _list(source.get("spatial_anchors")) or known_entities,
        "baseline_state": _mapping(source.get("baseline_state") or source.get("system_baseline")) or {
            "stable_contexts": _list(scene_semantics.get("stable_contexts")),
            "time_scope": scene_semantics.get("time_scope") or "",
        },
        "source_refs": _list(source.get("source_refs") or source.get("materials")) or (
            [_mapping(source.get("semantic_artifact_ref"))]
            if _mapping(source.get("semantic_artifact_ref")) else []
        ),
        "research_questions": _list(source.get("research_questions")) or _list(scene_semantics.get("questions")),
        "analysis_boundaries": _list(source.get("analysis_boundaries")) or _list(scene_semantics.get("analysis_boundaries")),
        "open_data_gaps": _list(source.get("open_data_gaps")),
        "effort_snapshot_ref": _mapping(effort_snapshot_ref),
    }


def build_scenario_readiness_checks(
    planning_input: Optional[Mapping[str, Any]],
    config: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    planning = _mapping(planning_input)
    runtime = _mapping(config)
    events = [_mapping(item) for item in _list(planning.get("normalized_user_events"))]
    temporal = _mapping(planning.get("temporal_plan"))
    graph = _mapping(planning.get("event_mechanism_graph"))
    nodes = [_mapping(item) for item in _list(graph.get("nodes"))]
    edges = [_mapping(item) for item in _list(graph.get("edges"))]
    role_demands = [_mapping(item) for item in _list(planning.get("role_demands"))]
    policies = [_mapping(item) for item in _list(planning.get("policy_plan"))]
    regions = [_mapping(item) for item in _list(runtime.get("region_graph"))]
    agent_plan = _mapping(runtime.get("agent_plan"))
    policy_execution = _mapping(runtime.get("policy_execution_plan"))
    risk_definitions = [_mapping(item) for item in _list(runtime.get("risk_definitions"))]

    checks: List[Dict[str, Any]] = []

    def add(
        key: str,
        label: str,
        status: str,
        summary: str,
        tab: str,
        *,
        blocking: bool = False,
        count: int = 0,
    ) -> None:
        checks.append({
            "key": key,
            "label_zh": label,
            "status": status,
            "status_label_zh": {"pass": "已就绪", "warning": "需复核", "blocking": "需处理"}.get(status, "需复核"),
            "summary_zh": summary,
            "target_tab": tab,
            "blocking": bool(blocking),
            "issue_count": max(0, int(count or 0)),
        })

    untargeted_events = [
        item for item in events
        if not _list(item.get("target_region_ids")) and not _list(item.get("target_entity_ids"))
    ]
    if not events:
        add("event_targets", "事件与作用范围", "blocking", "至少需要一个事件才能形成可运行场景。", "plan", blocking=True, count=1)
    elif untargeted_events:
        add("event_targets", "事件与作用范围", "warning", f"{len(untargeted_events)} 个事件沿用背景范围，进入推演前建议确认具体作用对象。", "plan", count=len(untargeted_events))
    else:
        add("event_targets", "事件与作用范围", "pass", f"{len(events)} 个事件均已绑定作用范围。", "plan")

    rounds = int(temporal.get("total_rounds") or 0)
    windows = [_mapping(item) for item in _list(temporal.get("event_windows"))]
    if rounds <= 0:
        add("temporal_coverage", "时间覆盖", "blocking", "时间计划缺少有效轮数。", "plan", blocking=True, count=1)
    elif events and len(windows) < len(events):
        add("temporal_coverage", "时间覆盖", "warning", f"计划为 {rounds} 轮，但仍有事件未形成独立时间窗口。", "plan", count=len(events) - len(windows))
    else:
        add("temporal_coverage", "时间覆盖", "pass", f"已覆盖 {rounds} 轮，事件窗口完整。", "plan")

    node_ids = {
        _text(item.get("event_id") or item.get("node_id") or item.get("id"))
        for item in nodes
    }
    dangling_edges = []
    for item in edges:
        source_id = _text(item.get("source_event_id") or item.get("source") or item.get("source_id"))
        target_id = _text(item.get("target_event_id") or item.get("target") or item.get("target_id"))
        if (source_id and source_id not in node_ids) or (target_id and target_id not in node_ids):
            dangling_edges.append(item)
    if dangling_edges:
        add("mechanism_graph", "机制连通性", "blocking", f"{len(dangling_edges)} 条机制关系引用了不存在的节点。", "mechanism", blocking=True, count=len(dangling_edges))
    elif events and not nodes:
        add("mechanism_graph", "机制连通性", "blocking", "事件尚未形成机制节点。", "mechanism", blocking=True, count=1)
    elif len(nodes) > 1 and not edges:
        add("mechanism_graph", "机制连通性", "warning", "存在多个机制节点，但节点之间尚未形成传播或反馈关系。", "mechanism", count=len(nodes))
    else:
        add("mechanism_graph", "机制连通性", "pass", f"{len(nodes)} 个节点、{len(edges)} 条关系可被运行时读取。", "mechanism")

    target_region_ids = _unique(
        token
        for item in events
        for token in _list(item.get("target_region_ids"))
    )
    known_region_ids = {
        _text(item.get("region_id") or item.get("id") or item.get("name"))
        for item in regions
    }
    unresolved_regions = [token for token in target_region_ids if regions and token not in known_region_ids]
    if unresolved_regions:
        add("region_references", "空间引用", "warning", f"{len(unresolved_regions)} 个事件区域未与正式区域图直接匹配。", "region", count=len(unresolved_regions))
    elif not regions:
        add("region_references", "空间引用", "warning", "正式区域图仍在生成，暂按背景范围检查。", "region", count=1)
    else:
        add("region_references", "空间引用", "pass", f"正式区域图包含 {len(regions)} 个区域。", "region")

    generation = _mapping(agent_plan.get("generation_audit"))
    unresolved_demands = _list(agent_plan.get("unresolved_demands"))
    if role_demands and not agent_plan:
        add("role_coverage", "主体能力覆盖", "warning", "主体规划尚未完成，角色能力需求暂未核验。", "agents", count=len(role_demands))
    elif unresolved_demands:
        add("role_coverage", "主体能力覆盖", "warning", f"{len(unresolved_demands)} 项角色能力需求尚未完全覆盖。", "agents", count=len(unresolved_demands))
    else:
        covered = int(generation.get("covered_role_demand_count") or len(role_demands))
        add("role_coverage", "主体能力覆盖", "pass", f"已覆盖 {covered} 项角色能力需求。", "agents")

    policy_bindings = [_mapping(item) for item in _list(policy_execution.get("policy_bindings"))]
    unbound = [item for item in policy_bindings if _text(item.get("binding_status")) not in {"bound", "not_required"}]
    if policies and not policy_execution:
        add("policy_binding", "政策执行绑定", "warning", "政策已定义，但执行主体尚未完成绑定。", "agents", count=len(policies))
    elif unbound:
        add("policy_binding", "政策执行绑定", "warning", f"{len(unbound)} 项政策尚无可执行主体。", "agents", count=len(unbound))
    else:
        add("policy_binding", "政策执行绑定", "pass", "当前政策均已绑定执行主体，或本场景未设置政策。", "agents")

    mechanism_ids = node_ids | {
        _text(item.get("edge_id") or item.get("id")) for item in edges
    }
    dangling_risk_refs = 0
    for item in risk_definitions:
        refs = _unique([
            *_list(item.get("mechanism_node_ids")),
            *_list(item.get("mechanism_edge_ids")),
        ])
        dangling_risk_refs += sum(1 for token in refs if token not in mechanism_ids)
    if dangling_risk_refs:
        add("risk_references", "风险证据引用", "warning", f"{dangling_risk_refs} 个风险机制引用需要复核。", "risk", count=dangling_risk_refs)
    elif not risk_definitions:
        add("risk_references", "风险证据引用", "pass", "当前没有通过证据校验的风险对象；这不会阻止推演。", "risk")
    else:
        add("risk_references", "风险证据引用", "pass", f"{len(risk_definitions)} 个风险对象已连接到场景证据。", "risk")

    return checks


def project_scenario_definition(
    planning_input: Optional[Mapping[str, Any]],
    config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    planning = _mapping(planning_input)
    runtime = _mapping(config)
    planning_id = _text(planning.get("planning_input_id"))
    checks = build_scenario_readiness_checks(planning, runtime)
    return {
        "scenario_definition_id": planning_id,
        "contract_version": SCENARIO_DEFINITION_CONTRACT_VERSION,
        "source_contract_version": _text(planning.get("contract_version")),
        "foundation_ref": project_background_foundation(
            _mapping(planning.get("foundation_ref")),
            effort_snapshot_ref=_mapping(planning.get("effort_snapshot_ref")),
        ),
        "event_plan": _list(planning.get("normalized_user_events")),
        "temporal_plan": _mapping(planning.get("temporal_plan")),
        "scenario_state_schema": _mapping(runtime.get("scenario_state_schema")),
        "mechanism_graph": _mapping(planning.get("event_mechanism_graph")),
        "regions": _list(runtime.get("region_graph")),
        "agent_profiles": _list(runtime.get("agent_configs") or runtime.get("actor_profiles")),
        "initial_relationships": _list(runtime.get("agent_relationship_graph")),
        "policy_plans": _list(planning.get("policy_plan")),
        "risk_definitions": _list(runtime.get("risk_definitions")),
        "readiness_checks": checks,
        "readiness_summary": {
            "blocking_count": sum(1 for item in checks if item.get("blocking")),
            "warning_count": sum(1 for item in checks if item.get("status") == "warning"),
            "pass_count": sum(1 for item in checks if item.get("status") == "pass"),
            "ready": not any(item.get("blocking") for item in checks),
        },
    }


def project_runtime_ledger(artifacts: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    source = _mapping(artifacts)
    return {
        "contract_version": RUNTIME_LEDGER_CONTRACT_VERSION,
        "round_snapshots": _list(source.get("round_snapshots")),
        "spread_event_ledger": _list(source.get("spread_events")),
        "agent_action_decision_ledger": _list(source.get("agent_action_decisions")),
        "state_mutation_ledger": _list(source.get("state_mutations")),
        "policy_execution_ledger": _list(source.get("policy_execution_events")),
        "relationship_event_ledger": _list(source.get("relationship_events")),
        "relationship_state_ledger": _list(source.get("relationship_states")),
        "agent_emergence_ledger": _list(source.get("agent_emergence_events")),
        "agent_lineage_ledger": _list(source.get("agent_lineage")),
        "risk_runtime_state": _mapping(source.get("latest_risk_runtime_state")),
        "risk_events": _list(source.get("risk_events")),
        "intervention_ledger": _list(source.get("interventions")),
    }


def project_analysis_bundle(
    *,
    executive_findings: Optional[List[Dict[str, Any]]] = None,
    turning_points: Optional[List[Dict[str, Any]]] = None,
    risk_outcomes: Optional[List[Dict[str, Any]]] = None,
    intervention_observations: Optional[List[Dict[str, Any]]] = None,
    impact_scope: Optional[Mapping[str, Any]] = None,
    evidence_index: Optional[List[Dict[str, Any]]] = None,
    uncertainty_boundaries: Optional[List[str]] = None,
    report_artifact_ref: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "contract_version": ANALYSIS_BUNDLE_CONTRACT_VERSION,
        "executive_findings": executive_findings or [],
        "turning_points": turning_points or [],
        "risk_outcomes": risk_outcomes or [],
        "intervention_observations": intervention_observations or [],
        "impact_scope": _mapping(impact_scope),
        "evidence_index": evidence_index or [],
        "uncertainty_boundaries": uncertainty_boundaries or [],
        "report_artifact_ref": _mapping(report_artifact_ref),
    }


__all__ = [
    "ANALYSIS_BUNDLE_CONTRACT_VERSION",
    "BACKGROUND_FOUNDATION_CONTRACT_VERSION",
    "RUNTIME_LEDGER_CONTRACT_VERSION",
    "SCENARIO_DEFINITION_CONTRACT_VERSION",
    "build_scenario_readiness_checks",
    "project_analysis_bundle",
    "project_background_foundation",
    "project_runtime_ledger",
    "project_scenario_definition",
]
