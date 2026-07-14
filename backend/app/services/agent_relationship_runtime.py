"""RelationshipEvent and RelationshipState contracts for Agent V2 runtime."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


RELATIONSHIP_EVENT_CONTRACT_VERSION = "relationship-event.v2"
RELATIONSHIP_STATE_CONTRACT_VERSION = "relationship-state.v2"


def initialize_relationship_states(
    relationship_contracts: Sequence[Mapping[str, Any]],
    existing_states: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    states: Dict[str, Dict[str, Any]] = {}
    for raw in existing_states or []:
        if not isinstance(raw, Mapping):
            continue
        state = deepcopy(dict(raw))
        key = str(state.get("relationship_contract_id") or state.get("relationship_state_id") or "")
        if key:
            states[key] = state
    for raw in relationship_contracts or []:
        if not isinstance(raw, Mapping):
            continue
        contract = dict(raw)
        contract_id = relationship_contract_id(contract)
        if contract_id in states:
            continue
        trust = _probability(contract.get("initial_trust", contract.get("confidence", 0.5)), 0.5)
        dependency = _probability(contract.get("initial_dependency", 0.35), 0.35)
        coordination = _probability(
            contract.get("initial_coordination", contract.get("strength", 0.45)),
            0.45,
        )
        states[contract_id] = {
            "contract_version": RELATIONSHIP_STATE_CONTRACT_VERSION,
            "relationship_state_id": _stable_id("relationship_state", contract_id),
            "relationship_contract_id": contract_id,
            "source_agent_id": contract.get("source_agent_id"),
            "target_agent_id": contract.get("target_agent_id"),
            "relationship_type": str(
                contract.get("relationship_type")
                or contract.get("relation_type")
                or contract.get("edge_type")
                or "interaction"
            ),
            "status": "active",
            "trust": trust,
            "dependency": dependency,
            "coordination": coordination,
            "tension": round(max(0.0, min(1.0, 0.35 - trust * 0.2)), 4),
            "resource_balance": {},
            "information_reliability": _probability(contract.get("confidence", trust), trust),
            "unfulfilled_commitments": 0,
            "last_event_ref": {},
            "active_since_round": 0,
            "last_updated_round": 0,
            "mechanism_edge_ids": _strings(contract.get("mechanism_edge_ids") or []),
            "evidence_refs": _strings(
                contract.get("evidence_refs")
                or contract.get("evidence")
                or contract.get("evidence_anchors")
                or []
            ),
        }
    return sorted(states.values(), key=lambda item: str(item["relationship_contract_id"]))


def relationship_contract_id(edge: Mapping[str, Any]) -> str:
    explicit = str(
        edge.get("relationship_contract_id")
        or edge.get("edge_id")
        or ""
    ).strip()
    if explicit:
        return explicit
    return _stable_id(
        "relationship_contract",
        edge.get("source_agent_id"),
        edge.get("target_agent_id"),
        edge.get("relationship_type") or edge.get("relation_type") or edge.get("edge_type"),
    )


def build_interaction_event(
    *,
    round_number: int,
    edge: Mapping[str, Any],
    action_key: str,
    action_label_zh: str,
    source_action_ref: Optional[Mapping[str, Any]],
    state_mutation_refs: Sequence[Mapping[str, Any]],
    success_status: str,
    scenario_version_ref: Optional[Mapping[str, Any]],
    resource_transfer: Optional[Mapping[str, float]] = None,
    causal_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    contract_id = relationship_contract_id(edge)
    event_type = _event_type_for_action(action_key)
    source_id = edge.get("source_agent_id")
    target_id = edge.get("target_agent_id")
    event_id = _stable_id(
        "relationship_event",
        contract_id,
        int(round_number),
        action_key,
        source_id,
        target_id,
    )
    mechanism_edge_ids = _strings(edge.get("mechanism_edge_ids") or [])
    return {
        "contract_version": RELATIONSHIP_EVENT_CONTRACT_VERSION,
        "relationship_event_id": event_id,
        **_causal_metadata(event_id, causal_context),
        "relationship_contract_id": contract_id,
        "path_edge_ids": [contract_id] if contract_id else [],
        "related_edge_ids": mechanism_edge_ids,
        "round_number": int(round_number),
        "event_type": event_type,
        "source_agent_id": source_id,
        "target_agent_id": target_id,
        "source_action_ref": deepcopy(dict(source_action_ref or {})),
        "mechanism_edge_ids": mechanism_edge_ids,
        "state_mutation_refs": [deepcopy(dict(item)) for item in state_mutation_refs if isinstance(item, Mapping)],
        "evidence_refs": _strings(
            edge.get("evidence_refs")
            or edge.get("evidence")
            or edge.get("evidence_anchors")
            or []
        ),
        "resource_transfer": {
            str(key): round(float(value), 6)
            for key, value in (resource_transfer or {}).items()
            if isinstance(value, (int, float))
        },
        "success_status": success_status if success_status in {"success", "partial", "failed"} else "partial",
        "scenario_version_ref": deepcopy(dict(scenario_version_ref or {})),
        "summary_zh": f"{action_label_zh}通过既有关系产生了{_event_label_zh(event_type)}。",
    }


def build_lifecycle_event(
    *,
    round_number: int,
    edge: Mapping[str, Any],
    lifecycle_event_type: str,
    scenario_version_ref: Optional[Mapping[str, Any]],
    causal_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    contract_id = relationship_contract_id(edge)
    event_type = {
        "created": "relationship_activated",
        "reawakened": "relationship_activated",
        "promoted": "relationship_promoted",
        "expired": "relationship_interrupted",
        "dormant": "relationship_interrupted",
    }.get(str(lifecycle_event_type), "relationship_updated")
    event_id = _stable_id(
        "relationship_event",
        contract_id,
        int(round_number),
        lifecycle_event_type,
    )
    mechanism_edge_ids = _strings(edge.get("mechanism_edge_ids") or [])
    return {
        "contract_version": RELATIONSHIP_EVENT_CONTRACT_VERSION,
        "relationship_event_id": event_id,
        **_causal_metadata(event_id, causal_context),
        "relationship_contract_id": contract_id,
        "path_edge_ids": [contract_id] if contract_id else [],
        "related_edge_ids": mechanism_edge_ids,
        "round_number": int(round_number),
        "event_type": event_type,
        "source_agent_id": edge.get("source_agent_id"),
        "target_agent_id": edge.get("target_agent_id"),
        "source_action_ref": {},
        "mechanism_edge_ids": mechanism_edge_ids,
        "state_mutation_refs": [],
        "evidence_refs": _strings(edge.get("evidence_refs") or edge.get("evidence") or []),
        "resource_transfer": {},
        "success_status": "success",
        "scenario_version_ref": deepcopy(dict(scenario_version_ref or {})),
        "summary_zh": _lifecycle_summary_zh(event_type),
    }


def apply_relationship_event(
    state: Mapping[str, Any],
    event: Mapping[str, Any],
) -> Dict[str, Any]:
    next_state = deepcopy(dict(state))
    event_type = str(event.get("event_type") or "relationship_updated")
    success = str(event.get("success_status") or "partial")
    factor = 1.0 if success == "success" else 0.45 if success == "partial" else -0.5
    deltas = _event_deltas(event_type)
    for key in ("trust", "dependency", "coordination", "tension", "information_reliability"):
        current = _probability(next_state.get(key), 0.0)
        next_state[key] = round(max(0.0, min(1.0, current + deltas.get(key, 0.0) * factor)), 4)
    if event_type in {"request", "commitment"} and success != "success":
        next_state["unfulfilled_commitments"] = int(next_state.get("unfulfilled_commitments") or 0) + 1
    elif success == "success" and int(next_state.get("unfulfilled_commitments") or 0) > 0:
        next_state["unfulfilled_commitments"] = int(next_state["unfulfilled_commitments"]) - 1
    balance = dict(next_state.get("resource_balance") or {})
    for key, value in (event.get("resource_transfer") or {}).items():
        if isinstance(value, (int, float)):
            balance[str(key)] = round(float(balance.get(str(key)) or 0.0) + float(value), 6)
    next_state["resource_balance"] = balance
    if event_type == "relationship_interrupted":
        next_state["status"] = "dormant"
    elif event_type in {"relationship_activated", "relationship_promoted"}:
        next_state["status"] = "active"
        if not int(next_state.get("active_since_round") or 0):
            next_state["active_since_round"] = int(event.get("round_number") or 0)
    next_state["last_event_ref"] = {
        "artifact_id": str(event.get("relationship_event_id") or ""),
        "contract_version": RELATIONSHIP_EVENT_CONTRACT_VERSION,
    }
    next_state["last_updated_round"] = int(event.get("round_number") or 0)
    return next_state


def upsert_relationship_state(
    states: Sequence[Mapping[str, Any]],
    edge: Mapping[str, Any],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    initialized = initialize_relationship_states([edge], states)
    contract_id = relationship_contract_id(edge)
    state = next(item for item in initialized if item["relationship_contract_id"] == contract_id)
    return initialized, state


def _event_type_for_action(action_key: str) -> str:
    action = str(action_key or "")
    if action in {"monitor", "issue_alert", "public_briefing", "publish_assessment", "report_hazard", "verify", "broadcast", "issue_notice"}:
        return "information_disclosure"
    if action in {"coordinate_response", "stabilize_services", "evacuate", "patient_triage", "deploy_remediation"}:
        return "cooperation"
    if action in {"request_transfer", "request_support"}:
        return "request"
    if action in {"adjust_supply", "route_flow", "reroute"}:
        return "resource_coordination"
    if action in {"enforce_restriction", "shutdown_line", "throttle_capacity"}:
        return "constraint_enforcement"
    if action in {"question_authority"}:
        return "challenge"
    return "interaction"


def _event_deltas(event_type: str) -> Dict[str, float]:
    return {
        "information_disclosure": {"trust": 0.025, "coordination": 0.01, "information_reliability": 0.035, "tension": -0.01},
        "cooperation": {"trust": 0.03, "coordination": 0.045, "dependency": 0.015, "tension": -0.02},
        "request": {"dependency": 0.025, "coordination": 0.015},
        "resource_coordination": {"coordination": 0.035, "dependency": 0.025, "trust": 0.015},
        "constraint_enforcement": {"coordination": 0.01, "tension": 0.045, "trust": -0.01},
        "challenge": {"tension": 0.04, "trust": -0.02, "information_reliability": 0.01},
        "relationship_activated": {"coordination": 0.02},
        "relationship_promoted": {"trust": 0.02, "coordination": 0.025},
        "relationship_interrupted": {"trust": -0.035, "coordination": -0.04, "tension": 0.04},
        "relationship_updated": {"coordination": 0.005},
        "interaction": {"coordination": 0.01},
    }.get(event_type, {"coordination": 0.005})


def _event_label_zh(event_type: str) -> str:
    return {
        "information_disclosure": "信息披露事件",
        "cooperation": "协作事件",
        "request": "请求事件",
        "resource_coordination": "资源协调事件",
        "constraint_enforcement": "限制执行事件",
        "challenge": "质询事件",
        "interaction": "互动事件",
    }.get(event_type, "关系事件")


def _lifecycle_summary_zh(event_type: str) -> str:
    return {
        "relationship_activated": "关系候选获得运行证据并进入活跃状态。",
        "relationship_promoted": "动态关系满足持续性门槛并升级。",
        "relationship_interrupted": "关系因时效或证据衰减转为休眠。",
        "relationship_updated": "关系状态依据运行事件完成更新。",
    }[event_type]


def _probability(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(1.0, parsed)), 4)


def _strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _causal_metadata(
    event_id: str,
    causal_context: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Return explicit causal fields without guessing from round or endpoints.

    Callers either provide a proven parent chain or leave the event as its own
    causal root.  This keeps relationship ledgers useful to Timeline V2 while
    preventing temporal or spatial correlation from being presented as cause.
    """

    context = dict(causal_context or {})
    parent_event_ids = [
        parent_id
        for parent_id in _strings(context.get("parent_event_ids") or [])
        if parent_id != event_id
    ]
    root_event_id = str(context.get("root_event_id") or "").strip()
    if not root_event_id:
        root_event_id = parent_event_ids[0] if parent_event_ids else event_id
    try:
        hop = max(0, int(context.get("hop")))
    except (TypeError, ValueError):
        hop = 1 if parent_event_ids else 0
    return {
        "root_event_id": root_event_id,
        "parent_event_ids": parent_event_ids,
        "hop": hop,
    }


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


__all__ = [
    "RELATIONSHIP_EVENT_CONTRACT_VERSION",
    "RELATIONSHIP_STATE_CONTRACT_VERSION",
    "apply_relationship_event",
    "build_interaction_event",
    "build_lifecycle_event",
    "initialize_relationship_states",
    "relationship_contract_id",
    "upsert_relationship_state",
]
