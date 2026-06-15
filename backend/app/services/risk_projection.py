from typing import Any, Dict, List, Optional


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
        confidence_score = state.get("confidence_score") or item.get("confidence_score") or item.get("confidence") or 0
        obj = {
            "risk_object_id": risk_id,
            "title": item.get("title") or item.get("name") or risk_id,
            "summary": item.get("summary") or item.get("description") or "",
            "status": state.get("status") or item.get("status") or "watch",
            "mode": item.get("mode") or "watch",
            "risk_type": item.get("risk_type") or item.get("category") or "",
            "severity_score": state.get("severity_score") or item.get("severity_score") or item.get("severity") or 0,
            "confidence_score": confidence_score,
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
        }
        _merge_runtime_signals(obj, state, confidence_score)
        objects.append(obj)
    return objects


def _merge_runtime_signals(obj: Dict[str, Any], state: Dict[str, Any], confidence_score: Any) -> None:
    """Project the evolving runtime signals (from RiskRuntimeTracker) onto the
    legacy risk object as ADDITIVE keys, so the UI can render a tension curve and
    an uncertainty band instead of a static scalar.

    Honesty principle: these are derived signals. The uncertainty band is labelled
    as derived and carries its provenance — we never dress it up as a measurement.
    """
    has_runtime = isinstance(state, dict) and bool(state)

    tension_trace = [
        _coerce_float(value)
        for value in (state.get("tension_trace") if isinstance(state, dict) else None) or []
        if _coerce_float(value) is not None
    ]
    runtime_tension = _coerce_float(state.get("runtime_tension")) if isinstance(state, dict) else None
    if runtime_tension is None and tension_trace:
        runtime_tension = tension_trace[-1]

    runtime_status = state.get("status") if isinstance(state, dict) else None
    turning_point = bool(state.get("turning_point")) if isinstance(state, dict) else False

    # Additive runtime keys — absent runtime state leaves these empty/None so
    # callers can distinguish "no run yet" from "ran and was flat".
    obj["runtime_tension"] = runtime_tension
    obj["tension_trace"] = tension_trace
    obj["runtime_status"] = runtime_status
    obj["turning_point"] = turning_point
    obj["has_runtime_signal"] = has_runtime

    obj["uncertainty_band"] = _derive_uncertainty_band(
        confidence_score=confidence_score,
        tension_trace=tension_trace,
        runtime_tension=runtime_tension,
        has_runtime=has_runtime,
    )


def _derive_uncertainty_band(
    confidence_score: Any,
    tension_trace: List[float],
    runtime_tension: Optional[float],
    has_runtime: bool,
) -> Dict[str, Any]:
    """Derive an uncertainty band around the current tension so the product can
    show uncertainty as a feature (a band, not a false-precision point).

    Width is driven by two honest sources:
      - epistemic uncertainty: low confidence_score -> wider band.
      - observed volatility: spread (max-min) of the realised tension_trace.

    Clearly labelled derived=True with the components that fed it.
    """
    confidence = _coerce_float(confidence_score)
    # confidence may be stored as 0..1 probability or 0..100; normalise to 0..1.
    if confidence is None:
        confidence_unit = 0.5
    elif confidence > 1.0:
        confidence_unit = max(0.0, min(1.0, confidence / 100.0))
    else:
        confidence_unit = max(0.0, min(1.0, confidence))

    # Epistemic half-width: 0 confidence -> +/-30, full confidence -> +/-5.
    epistemic_half_width = round(5.0 + (1.0 - confidence_unit) * 25.0, 1)

    # Volatility half-width: half the observed spread of the trace.
    spread = 0.0
    if len(tension_trace) >= 2:
        spread = max(tension_trace) - min(tension_trace)
    volatility_half_width = round(spread / 2.0, 1)

    half_width = round(epistemic_half_width + volatility_half_width, 1)

    center = runtime_tension
    band: Dict[str, Any] = {
        "derived": True,
        "label": "derived uncertainty band (not a measurement)",
        "confidence_score": confidence_score,
        "confidence_unit": round(confidence_unit, 3),
        "epistemic_half_width": epistemic_half_width,
        "volatility_half_width": volatility_half_width,
        "half_width": half_width,
        "components": ["confidence_score", "tension_trace_spread"],
        "has_runtime_signal": has_runtime,
    }
    if center is not None:
        band["center"] = center
        band["lower"] = round(max(0.0, center - half_width), 1)
        band["upper"] = round(min(100.0, center + half_width), 1)
    else:
        band["center"] = None
        band["lower"] = None
        band["upper"] = None
    return band


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
