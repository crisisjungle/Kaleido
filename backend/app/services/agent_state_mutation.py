"""Append-only state mutation records for Agent V2 action execution."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from .envfish_models import merge_state_vectors, normalize_state_vector


STATE_MUTATION_CONTRACT_VERSION = "state-mutation.v2"


def apply_state_delta(
    *,
    current_vector: Mapping[str, Any],
    delta: Mapping[str, Any],
    round_number: int,
    source_ref: Mapping[str, Any],
    target_type: str,
    target_id: Any,
    evidence_refs: Iterable[Any],
    scenario_version_ref: Mapping[str, Any],
    source_type: str = "agent_action",
) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
    before = normalize_state_vector(dict(current_vector or {}))
    next_vector = merge_state_vectors(before, dict(delta or {}))
    records: List[Dict[str, Any]] = []
    for state_key in delta or {}:
        previous_value = _number(before.get(state_key))
        next_value = _number(next_vector.get(state_key))
        if previous_value == next_value:
            continue
        records.append(
            _record(
                round_number=round_number,
                source_ref=source_ref,
                target_type=target_type,
                target_id=target_id,
                state_key=str(state_key),
                previous_value=previous_value,
                next_value=next_value,
                evidence_refs=evidence_refs,
                scenario_version_ref=scenario_version_ref,
                source_type=source_type,
            )
        )
    return next_vector, records


def resource_mutation_records(
    *,
    settlement: Mapping[str, Any],
    round_number: int,
    source_ref: Mapping[str, Any],
    agent_id: Any,
    evidence_refs: Iterable[Any],
    scenario_version_ref: Mapping[str, Any],
    source_type: str = "agent_action",
) -> List[Dict[str, Any]]:
    before = dict(settlement.get("before") or {})
    after = dict(settlement.get("after") or {})
    records = []
    for resource_key in sorted(set(before).union(after)):
        previous_value = _number(before.get(resource_key))
        next_value = _number(after.get(resource_key))
        if previous_value == next_value:
            continue
        records.append(
            _record(
                round_number=round_number,
                source_ref=source_ref,
                target_type="resource_pool",
                target_id=agent_id,
                state_key=str(resource_key),
                previous_value=previous_value,
                next_value=next_value,
                evidence_refs=evidence_refs,
                scenario_version_ref=scenario_version_ref,
                source_type=source_type,
            )
        )
    return records


def mutation_refs(records: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "artifact_id": str(item.get("mutation_id") or ""),
            "contract_version": str(item.get("contract_version") or STATE_MUTATION_CONTRACT_VERSION),
        }
        for item in records
        if str(item.get("mutation_id") or "")
    ]


def _record(
    *,
    round_number: int,
    source_ref: Mapping[str, Any],
    target_type: str,
    target_id: Any,
    state_key: str,
    previous_value: float,
    next_value: float,
    evidence_refs: Iterable[Any],
    scenario_version_ref: Mapping[str, Any],
    source_type: str,
) -> Dict[str, Any]:
    source = deepcopy(dict(source_ref or {}))
    mutation_id = _stable_id(
        "state_mutation",
        int(round_number),
        source.get("artifact_id"),
        target_type,
        target_id,
        state_key,
        previous_value,
        next_value,
    )
    return {
        "contract_version": STATE_MUTATION_CONTRACT_VERSION,
        "mutation_id": mutation_id,
        "round_number": int(round_number),
        "source_type": str(source_type or "agent_action"),
        "source_ref": source,
        "target_type": target_type,
        "target_id": str(target_id),
        "state_key": state_key,
        "previous_value": previous_value,
        "next_value": next_value,
        "delta": round(next_value - previous_value, 6),
        "evidence_refs": _strings(evidence_refs),
        "scenario_version_ref": deepcopy(dict(scenario_version_ref or {})),
    }


def _strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _number(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


__all__ = [
    "STATE_MUTATION_CONTRACT_VERSION",
    "apply_state_delta",
    "mutation_refs",
    "resource_mutation_records",
]
