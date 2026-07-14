"""Runtime validation and resource settlement for Agent-bound policies."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


POLICY_EXECUTION_EVENT_CONTRACT_VERSION = "policy-execution-event.v2"


def execute_policy_binding(
    *,
    binding: Mapping[str, Any],
    actor_lookup: Mapping[int, Dict[str, Any]],
    round_number: int,
    available_target_region_ids: Iterable[Any],
    scenario_version_ref: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Validate one due policy and settle its relative Agent resources.

    The function deliberately does not mutate region state. It returns a
    validated effect delta that the runtime can apply through the shared state
    mutation ledger only after every execution condition succeeds.
    """

    item = deepcopy(dict(binding or {}))
    start_round = max(0, int(item.get("start_round") or 0))
    duration_rounds = max(1, int(item.get("duration_rounds") or 1))
    end_round = start_round + duration_rounds - 1
    current_round = int(round_number or 0)
    if current_round < start_round or current_round > end_round:
        return None

    reasons: list[str] = []
    if str(item.get("binding_status") or "unbound") != "bound":
        reasons.append("准备阶段尚未完成全部执行条件绑定")

    executor_ids = _integers(item.get("executor_agent_ids") or [])
    executors = [actor_lookup[agent_id] for agent_id in executor_ids if agent_id in actor_lookup]
    if len(executors) != len(executor_ids) or not executors:
        reasons.append("一个或多个政策执行 Agent 当前不存在")

    inactive_ids = [
        int(actor.get("agent_id"))
        for actor in executors
        if _lifecycle_status(actor) != "active"
    ]
    if inactive_ids:
        reasons.append("一个或多个政策执行 Agent 当前未激活")

    required_capabilities = set(_strings(item.get("required_capability_keys") or []))
    available_capabilities = {
        capability
        for actor in executors
        for capability in _strings(actor.get("capability_keys") or [])
    }
    missing_capabilities = sorted(required_capabilities.difference(available_capabilities))
    if missing_capabilities:
        reasons.append("执行 Agent 的联合能力不足")

    available_permissions = {
        permission
        for actor in executors
        for permission in _strings(actor.get("permission_keys") or [])
    }
    missing_permission_groups = [
        _strings(group)
        for group in item.get("required_permission_groups") or []
        if not available_permissions.intersection(_strings(group))
    ]
    if missing_permission_groups:
        reasons.append("执行 Agent 的联合权限不足")

    target_region_ids = _strings(item.get("target_region_ids") or [])
    available_targets = set(_strings(available_target_region_ids))
    missing_target_region_ids = sorted(set(target_region_ids).difference(available_targets))
    if not target_region_ids:
        reasons.append("政策缺少明确或可推断的目标区域")
    elif missing_target_region_ids:
        reasons.append("一个或多个政策目标区域不在当前场景中")

    executor_regions = {
        region
        for actor in executors
        for region in _strings(
            [
                actor.get("primary_region"),
                actor.get("home_region_id"),
                actor.get("home_subregion_id"),
                *(actor.get("coverage_region_ids") or []),
                *(actor.get("influenced_regions") or []),
            ]
        )
    }
    outside_jurisdiction = sorted(set(target_region_ids).difference(executor_regions))
    if outside_jurisdiction:
        reasons.append("一个或多个目标区域缺少执行 Agent 的辖区依据")

    total_resource_requirements = {
        str(key): max(0.0, _number(value))
        for key, value in (item.get("resource_requirements") or {}).items()
    }
    per_round_costs = {
        key: round(value / duration_rounds, 6)
        for key, value in total_resource_requirements.items()
        if value > 0
    }
    available_resources: Dict[str, float] = {}
    for actor in executors:
        for key, value in (actor.get("resource_budget") or {}).items():
            available_resources[str(key)] = available_resources.get(str(key), 0.0) + max(
                0.0, _number(value)
            )
    missing_resource_keys = sorted(
        key
        for key, cost in per_round_costs.items()
        if available_resources.get(key, 0.0) < cost
    )
    if missing_resource_keys:
        reasons.append("执行 Agent 的本轮可用资源不足")

    policy_id = str(item.get("policy_id") or "policy")
    event_id = _stable_id(
        "policy_execution",
        policy_id,
        current_round,
        executor_ids,
        target_region_ids,
    )
    accepted = not reasons
    resource_settlements: list[Dict[str, Any]] = []
    if accepted:
        resource_settlements = _settle_resources(executors, per_round_costs)

    intensity = max(0.0, min(100.0, _number(item.get("intensity_0_100"), 100.0))) / 100.0
    effect_delta = {
        str(key): round(_number(value) * intensity / duration_rounds, 6)
        for key, value in (item.get("state_effect_template") or {}).items()
        if _number(value) != 0
    }
    label_zh = str(item.get("label_zh") or "政策措施")
    return {
        "contract_version": POLICY_EXECUTION_EVENT_CONTRACT_VERSION,
        "policy_execution_id": event_id,
        "policy_id": policy_id,
        "policy_label_zh": label_zh,
        "round_number": current_round,
        "execution_status": "executed" if accepted else "blocked",
        "executor_agent_ids": executor_ids,
        "target_region_ids": target_region_ids,
        "target_scope_source": str(item.get("target_scope_source") or "unresolved"),
        "required_capability_keys": sorted(required_capabilities),
        "missing_capability_keys": missing_capabilities,
        "required_permission_groups": [
            _strings(group) for group in item.get("required_permission_groups") or []
        ],
        "missing_permission_groups": missing_permission_groups,
        "resource_requirements": total_resource_requirements,
        "per_round_resource_costs": per_round_costs,
        "missing_resource_keys": missing_resource_keys,
        "missing_target_region_ids": missing_target_region_ids,
        "outside_jurisdiction_region_ids": outside_jurisdiction,
        "resource_settlements": resource_settlements,
        "state_effect_delta": effect_delta if accepted else {},
        "effect_primitives": _strings(item.get("effect_primitives") or []),
        "side_effects_zh": _strings(item.get("side_effects_zh") or []),
        "blocking_reasons_zh": reasons,
        "summary_zh": (
            f"{label_zh} 已由绑定 Agent 在本轮执行。"
            if accepted
            else f"{label_zh} 本轮未生效：{'；'.join(reasons)}。"
        ),
        "scenario_version_ref": deepcopy(dict(scenario_version_ref or {})),
        "state_mutation_refs": [],
    }


def _settle_resources(
    executors: Sequence[Dict[str, Any]],
    per_round_costs: Mapping[str, float],
) -> list[Dict[str, Any]]:
    settlements: Dict[int, Dict[str, Any]] = {}
    for resource_key, total_cost in per_round_costs.items():
        remaining = max(0.0, float(total_cost))
        for actor in sorted(executors, key=lambda item: int(item.get("agent_id") or 0)):
            if remaining <= 0:
                break
            budget = dict(actor.get("resource_budget") or {})
            available = max(0.0, _number(budget.get(resource_key)))
            if available <= 0:
                continue
            consumed = min(available, remaining)
            actor_id = int(actor.get("agent_id") or 0)
            settlement = settlements.setdefault(
                actor_id,
                {
                    "agent_id": actor_id,
                    "before": dict(budget),
                    "after": dict(budget),
                    "consumed": {},
                },
            )
            settlement["after"][resource_key] = round(available - consumed, 6)
            settlement["consumed"][resource_key] = round(consumed, 6)
            actor["resource_budget"] = dict(settlement["after"])
            remaining = round(remaining - consumed, 6)
    return [settlements[key] for key in sorted(settlements)]


def _lifecycle_status(actor: Mapping[str, Any]) -> str:
    lifecycle = actor.get("runtime_lifecycle") or {}
    return str(
        actor.get("lifecycle_status")
        or lifecycle.get("lifecycle_status")
        or "active"
    )


def _integers(values: Iterable[Any]) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed not in result:
            result.append(parsed)
    return result


def _strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


__all__ = [
    "POLICY_EXECUTION_EVENT_CONTRACT_VERSION",
    "execute_policy_binding",
]
