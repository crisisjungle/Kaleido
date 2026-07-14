import json
import os
from typing import Any, Dict, List

from .risk_projection import build_legacy_risk_summary, project_legacy_risk_objects


EMPTY_RISK_BUNDLE = {
    "risk_contract_version": 1,
    "risk_generation_audit": {},
    "risk_candidate_ledger": [],
    "risk_definitions": [],
    "latest_risk_runtime_state": {},
    "risk_runtime_history": [],
    "risk_runtime_state": [],
    "risk_events": [],
    "risk_objects": [],
    "primary_risk_object": None,
    "risk_objects_summary": {},
}


def _read_json(path: str, fallback: Any) -> Any:
    try:
        if not os.path.exists(path):
            return fallback
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return fallback


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    try:
        if not os.path.exists(path):
            return rows
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception:
        return rows
    return rows


def _write_json(path: str, value: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def _write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_risk_artifacts(sim_dir: str) -> Dict[str, Any]:
    bundle = dict(EMPTY_RISK_BUNDLE)
    if not sim_dir:
        return bundle
    risk_definitions = _read_json(os.path.join(sim_dir, "risk_definitions.json"), [])
    manifest = _read_json(os.path.join(sim_dir, "risk_manifest.json"), {})
    candidate_ledger = _read_jsonl(os.path.join(sim_dir, "risk_candidate_ledger.jsonl"))
    latest_runtime = _read_json(os.path.join(sim_dir, "latest_risk_runtime_state.json"), {})
    runtime_history = _read_jsonl(os.path.join(sim_dir, "risk_runtime_state.jsonl"))
    risk_events = _read_jsonl(os.path.join(sim_dir, "risk_events.jsonl"))
    risk_objects = _read_json(os.path.join(sim_dir, "risk_objects.json"), None)
    if not isinstance(risk_objects, list):
        risk_objects = project_legacy_risk_objects(risk_definitions if isinstance(risk_definitions, list) else [], latest_runtime if isinstance(latest_runtime, dict) else {})
    summary = _read_json(os.path.join(sim_dir, "risk_objects_summary.json"), {})
    if not isinstance(summary, dict) or not summary:
        summary = build_legacy_risk_summary(risk_objects, primary_active_risk_id=str((latest_runtime or {}).get("primary_active_risk_id") or ""))
    primary_id = summary.get("primary_risk_object_id") or summary.get("primary_active_risk_id")
    primary = next((item for item in risk_objects if str(item.get("risk_object_id")) == str(primary_id)), None)
    contract_version = 1
    if isinstance(manifest, dict) and manifest.get("risk_contract_version") is not None:
        try:
            contract_version = int(manifest.get("risk_contract_version"))
        except (TypeError, ValueError):
            contract_version = 1
    elif isinstance(risk_definitions, list):
        first_version = next(
            (item.get("risk_contract_version") for item in risk_definitions if isinstance(item, dict) and item.get("risk_contract_version") is not None),
            None,
        )
        if first_version is not None:
            try:
                contract_version = int(first_version)
            except (TypeError, ValueError):
                contract_version = 1
    bundle.update({
        "risk_contract_version": contract_version,
        "risk_generation_audit": manifest if isinstance(manifest, dict) else {},
        "risk_candidate_ledger": candidate_ledger,
        "risk_definitions": risk_definitions if isinstance(risk_definitions, list) else [],
        "latest_risk_runtime_state": latest_runtime if isinstance(latest_runtime, dict) else {},
        "risk_runtime_history": runtime_history,
        "risk_runtime_state": runtime_history,
        "risk_events": risk_events,
        "risk_objects": risk_objects,
        "primary_risk_object": primary,
        "risk_objects_summary": summary,
    })
    return bundle


def write_risk_artifacts(
    sim_dir: str,
    risk_definitions: List[Dict[str, Any]] | None = None,
    latest_runtime_bundle: Dict[str, Any] | None = None,
    primary_risk_id: str = "",
    generation_notes: List[str] | None = None,
    risk_events: List[Dict[str, Any]] | None = None,
    append_runtime_history: bool = False,
    runtime_history_entry: Dict[str, Any] | None = None,
    rewrite_runtime_history: List[Dict[str, Any]] | None = None,
    risk_contract_version: int | None = None,
    generation_audit: Dict[str, Any] | None = None,
    candidate_ledger: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    os.makedirs(sim_dir, exist_ok=True)
    risk_definitions = risk_definitions or []
    latest_runtime_bundle = latest_runtime_bundle or {}
    risk_events = risk_events or []
    existing_manifest = _read_json(os.path.join(sim_dir, "risk_manifest.json"), {})
    if risk_contract_version is None:
        first_version = next(
            (item.get("risk_contract_version") for item in risk_definitions if isinstance(item, dict) and item.get("risk_contract_version") is not None),
            None,
        )
        risk_contract_version = int(first_version or (existing_manifest or {}).get("risk_contract_version") or 1)
    if generation_audit is None:
        generation_audit = existing_manifest if isinstance(existing_manifest, dict) else {}
    if candidate_ledger is None:
        candidate_ledger = _read_jsonl(os.path.join(sim_dir, "risk_candidate_ledger.jsonl"))
    risk_objects = project_legacy_risk_objects(risk_definitions, latest_runtime_bundle)
    runtime_states = [item for item in (latest_runtime_bundle.get("risk_states") or []) if isinstance(item, dict)]
    if runtime_states:
        active_count = sum(1 for item in runtime_states if str(item.get("status") or "watch") not in {"dormant", "resolved"})
    else:
        active_count = sum(
            1
            for item in risk_definitions
            if str(item.get("lifecycle_status") or item.get("runtime_status") or "watch") not in {"dormant", "resolved"}
        )
    summary = build_legacy_risk_summary(
        risk_objects,
        primary_risk_object_id=primary_risk_id,
        generation_notes=generation_notes or [],
        primary_active_risk_id=str(latest_runtime_bundle.get("primary_active_risk_id") or primary_risk_id or ""),
        pinned_risk_ids=list(latest_runtime_bundle.get("pinned_risk_ids") or []),
    )
    summary["risk_contract_version"] = int(risk_contract_version)
    summary["generation_mode"] = str((generation_audit or {}).get("generation_mode") or ("legacy_template_v1" if int(risk_contract_version) == 1 else "mechanism_graph_deterministic"))
    summary["candidate_count"] = int((generation_audit or {}).get("candidate_count") or 0)
    summary["rejected_count"] = int((generation_audit or {}).get("rejected_count") or 0)
    summary["zero_reason"] = str((generation_audit or {}).get("zero_reason") or "")
    summary["active_count"] = active_count
    summary["total_definition_count"] = len(risk_definitions)

    manifest = {
        **(generation_audit or {}),
        "risk_contract_version": int(risk_contract_version),
        "active_count": active_count,
        "total_definition_count": len(risk_definitions),
        "primary_risk_id": str(primary_risk_id or latest_runtime_bundle.get("primary_active_risk_id") or ""),
    }

    if rewrite_runtime_history is not None:
        history = rewrite_runtime_history
    else:
        history = _read_jsonl(os.path.join(sim_dir, "risk_runtime_state.jsonl"))
        if append_runtime_history:
            history.append(runtime_history_entry or latest_runtime_bundle)

    _write_json(os.path.join(sim_dir, "risk_definitions.json"), risk_definitions)
    _write_json(os.path.join(sim_dir, "risk_manifest.json"), manifest)
    _write_json(os.path.join(sim_dir, "latest_risk_runtime_state.json"), latest_runtime_bundle)
    _write_json(os.path.join(sim_dir, "risk_objects.json"), risk_objects)
    _write_json(os.path.join(sim_dir, "risk_objects_summary.json"), summary)
    _write_jsonl(os.path.join(sim_dir, "risk_runtime_state.jsonl"), history)
    _write_jsonl(os.path.join(sim_dir, "risk_events.jsonl"), risk_events)
    _write_jsonl(os.path.join(sim_dir, "risk_candidate_ledger.jsonl"), candidate_ledger or [])
    return load_risk_artifacts(sim_dir)
