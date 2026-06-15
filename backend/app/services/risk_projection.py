from typing import Any, Dict, List


def project_legacy_risk_objects(risk_definitions: List[Dict[str, Any]], runtime_bundle: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    runtime_bundle = runtime_bundle or {}
    risk_states = {
        item.get("risk_id") or item.get("risk_object_id"): item
        for item in runtime_bundle.get("risk_states", []) or []
        if isinstance(item, dict)
    }
    objects = []
    for index, item in enumerate(risk_definitions or []):
        if not isinstance(item, dict):
            continue
        risk_id = str(item.get("risk_id") or item.get("risk_object_id") or f"risk_{index + 1}")
        state = risk_states.get(risk_id) or {}
        objects.append({
            "risk_object_id": risk_id,
            "title": item.get("title") or item.get("name") or risk_id,
            "summary": item.get("summary") or item.get("description") or "",
            "status": state.get("status") or item.get("status") or "watch",
            "mode": item.get("mode") or "watch",
            "risk_type": item.get("risk_type") or item.get("category") or "",
            "severity_score": state.get("severity_score") or item.get("severity_score") or item.get("severity") or 0,
            "confidence_score": state.get("confidence_score") or item.get("confidence_score") or item.get("confidence") or 0,
            "actionability_score": item.get("actionability_score") or 0,
            "region_scope": item.get("region_scope") or item.get("regions") or [],
            "primary_regions": item.get("primary_regions") or [],
            "source_entity_uuids": item.get("source_entity_uuids") or [],
            "source_actor_ids": item.get("source_actor_ids") or [],
            "source_actor_names": item.get("source_actor_names") or [],
            "source_variable_ids": item.get("source_variable_ids") or [],
            "root_pressures": item.get("root_pressures") or [],
            "chain_steps": item.get("chain_steps") or [],
            "turning_points": item.get("turning_points") or item.get("turning_point_candidates") or [],
            "amplifiers": item.get("amplifiers") or [],
            "buffers": item.get("buffers") or [],
            "evidence": item.get("evidence") or [],
            "affected_clusters": item.get("affected_clusters") or [],
            "intervention_options": item.get("intervention_options") or item.get("intervention_templates") or [],
            "scenario_branches": item.get("scenario_branches") or item.get("branch_templates") or [],
            "why_now": item.get("why_now") or "",
        })
    return objects


def build_legacy_risk_summary(
    risk_objects: List[Dict[str, Any]],
    primary_risk_object_id: str = "",
    generation_notes: List[str] | None = None,
    primary_active_risk_id: str = "",
    pinned_risk_ids: List[str] | None = None,
) -> Dict[str, Any]:
    objects = [item for item in risk_objects or [] if isinstance(item, dict)]
    primary = primary_active_risk_id or primary_risk_object_id
    if not primary and objects:
        primary = str(objects[0].get("risk_object_id") or "")
    return {
        "risk_objects_count": len(objects),
        "primary_risk_object_id": primary,
        "primary_active_risk_id": primary_active_risk_id or primary,
        "pinned_risk_ids": pinned_risk_ids or [],
        "generation_notes": generation_notes or [],
    }
