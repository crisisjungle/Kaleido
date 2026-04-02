"""
Risk artifact read/write helpers.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from .envfish_models import dump_json
from .risk_event_engine import append_risk_events, load_risk_events
from .risk_projection import (
    build_initial_runtime_bundle_from_legacy,
    build_legacy_risk_summary,
    project_legacy_risk_objects,
    risk_objects_to_definitions,
)


RISK_DEFINITIONS_FILE = "risk_definitions.json"
RISK_RUNTIME_HISTORY_FILE = "risk_runtime_state.jsonl"
LATEST_RISK_RUNTIME_FILE = "latest_risk_runtime_state.json"
RISK_EVENTS_FILE = "risk_events.jsonl"
LEGACY_RISK_OBJECTS_FILE = "risk_objects.json"
LEGACY_RISK_SUMMARY_FILE = "risk_object_summary.json"


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _read_jsonl(path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit is not None and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def _write_jsonl(path: str, rows: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows or []:
            handle.write(json.dumps(dict(row or {}), ensure_ascii=False) + "\n")


def write_risk_artifacts(
    sim_dir: str,
    risk_definitions: Iterable[Any],
    latest_runtime_bundle: Dict[str, Any],
    primary_risk_id: str = "",
    generation_notes: Optional[List[str]] = None,
    risk_events: Optional[Iterable[Dict[str, Any]]] = None,
    append_runtime_history: bool = False,
    runtime_history_entry: Optional[Dict[str, Any]] = None,
    rewrite_runtime_history: Optional[Iterable[Dict[str, Any]]] = None,
    append_events: bool = False,
) -> Dict[str, Any]:
    os.makedirs(sim_dir, exist_ok=True)
    definitions_payload = [
        item if isinstance(item, dict) else item.to_dict()
        for item in (risk_definitions or [])
    ]
    runtime_payload = dict(latest_runtime_bundle or {})
    legacy_risk_objects = project_legacy_risk_objects(definitions_payload, runtime_payload)
    summary = build_legacy_risk_summary(
        legacy_risk_objects=legacy_risk_objects,
        primary_risk_object_id=primary_risk_id,
        generation_notes=generation_notes or [],
        primary_active_risk_id=str(runtime_payload.get("primary_active_risk_id") or ""),
        pinned_risk_ids=list(runtime_payload.get("pinned_risk_ids") or []),
    )

    dump_json(os.path.join(sim_dir, RISK_DEFINITIONS_FILE), definitions_payload)
    dump_json(os.path.join(sim_dir, LATEST_RISK_RUNTIME_FILE), runtime_payload)
    dump_json(os.path.join(sim_dir, LEGACY_RISK_OBJECTS_FILE), legacy_risk_objects)
    dump_json(os.path.join(sim_dir, LEGACY_RISK_SUMMARY_FILE), summary)

    runtime_history_path = os.path.join(sim_dir, RISK_RUNTIME_HISTORY_FILE)
    if rewrite_runtime_history is not None:
        _write_jsonl(runtime_history_path, rewrite_runtime_history)
    elif append_runtime_history:
        rows = list(_read_jsonl(runtime_history_path))
        rows.append(dict(runtime_history_entry or runtime_payload))
        _write_jsonl(runtime_history_path, rows)

    if risk_events is not None:
        event_path = os.path.join(sim_dir, RISK_EVENTS_FILE)
        if append_events:
            append_risk_events(event_path, risk_events)
        else:
            _write_jsonl(event_path, risk_events)

    return {
        "risk_definitions": definitions_payload,
        "latest_risk_runtime_state": runtime_payload,
        "risk_objects": legacy_risk_objects,
        "risk_objects_summary": summary,
    }


def load_risk_artifacts(
    sim_dir: str,
    runtime_limit: int = 32,
    event_limit: int = 160,
) -> Dict[str, Any]:
    definitions = _read_json(os.path.join(sim_dir, RISK_DEFINITIONS_FILE), [])
    latest_runtime = _read_json(os.path.join(sim_dir, LATEST_RISK_RUNTIME_FILE), {})
    runtime_history = _read_jsonl(os.path.join(sim_dir, RISK_RUNTIME_HISTORY_FILE), limit=runtime_limit)
    events = load_risk_events(os.path.join(sim_dir, RISK_EVENTS_FILE), limit=event_limit)
    legacy_risk_objects = _read_json(os.path.join(sim_dir, LEGACY_RISK_OBJECTS_FILE), [])
    legacy_summary = _read_json(os.path.join(sim_dir, LEGACY_RISK_SUMMARY_FILE), {})

    if not definitions and legacy_risk_objects:
        definitions = [item.to_dict() for item in risk_objects_to_definitions(legacy_risk_objects)]
    if not latest_runtime and legacy_risk_objects:
        latest_runtime = build_initial_runtime_bundle_from_legacy(
            risk_objects=legacy_risk_objects,
            risk_definitions=definitions,
            primary_risk_id=str(
                legacy_summary.get("primary_risk_object_id")
                or legacy_summary.get("primary_active_risk_id")
                or ""
            ),
        )
    if not legacy_risk_objects and definitions:
        legacy_risk_objects = project_legacy_risk_objects(definitions, latest_runtime)
    if not legacy_summary and legacy_risk_objects:
        legacy_summary = build_legacy_risk_summary(
            legacy_risk_objects=legacy_risk_objects,
            primary_risk_object_id=str(latest_runtime.get("primary_active_risk_id") or ""),
            primary_active_risk_id=str(latest_runtime.get("primary_active_risk_id") or ""),
            pinned_risk_ids=list(latest_runtime.get("pinned_risk_ids") or []),
        )

    return {
        "risk_definitions": definitions,
        "latest_risk_runtime_state": latest_runtime,
        "risk_runtime_history": runtime_history,
        "risk_events": events,
        "risk_objects": legacy_risk_objects,
        "risk_objects_summary": legacy_summary,
        "primary_risk_object": legacy_summary.get("primary_risk_object"),
    }
