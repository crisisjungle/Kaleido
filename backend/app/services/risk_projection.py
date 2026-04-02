"""
Risk definition/runtime projection helpers.

These helpers keep the new risk definition/runtime artifacts as the internal
source of truth while continuing to emit legacy `risk_objects` payloads for
older consumers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .envfish_models import (
    EnvAgentProfile,
    RiskAffectedCluster,
    RiskChainStepDefinition,
    RiskDefinition,
    RiskEvidence,
    RiskInterventionOption,
    RiskRuntimeStateBundle,
    RiskScenarioBranch,
    RiskScopeActorRef,
    RiskScopeEntityRef,
    RiskScopeRegionRef,
    clamp_probability,
    clamp_score,
    ensure_unique_slug,
)


def _now() -> str:
    return datetime.now().isoformat()


def _to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return {}


def _unique_strings(values: Iterable[Any]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def _coerce_region_refs(
    region_names_or_ids: Iterable[Any],
    regions: Optional[Iterable[Any]] = None,
) -> List[RiskScopeRegionRef]:
    region_by_id: Dict[str, Dict[str, Any]] = {}
    region_by_name: Dict[str, Dict[str, Any]] = {}
    for region in regions or []:
        payload = _to_dict(region)
        region_id = str(payload.get("region_id") or "").strip()
        region_name = str(payload.get("name") or payload.get("region_name") or region_id).strip()
        if region_id:
            region_by_id[region_id] = payload
        if region_name:
            region_by_name[region_name.lower()] = payload

    refs: List[RiskScopeRegionRef] = []
    seen: set[tuple[str, str]] = set()
    used: set[str] = set()
    for raw in region_names_or_ids:
        token = str(raw or "").strip()
        if not token:
            continue
        match = region_by_id.get(token) or region_by_name.get(token.lower())
        region_id = str((match or {}).get("region_id") or ensure_unique_slug(token, used))
        region_name = str((match or {}).get("name") or (match or {}).get("region_name") or token)
        key = (region_id, region_name)
        if key in seen:
            continue
        seen.add(key)
        refs.append(RiskScopeRegionRef(region_id=region_id, region_name=region_name))
    return refs


def _coerce_actor_refs(
    actor_ids: Iterable[Any],
    profiles: Optional[Iterable[Any]] = None,
) -> List[RiskScopeActorRef]:
    profile_lookup: Dict[int, Dict[str, Any]] = {}
    for profile in profiles or []:
        payload = _to_dict(profile)
        try:
            actor_id = int(payload.get("agent_id"))
        except Exception:
            continue
        profile_lookup[actor_id] = payload

    refs: List[RiskScopeActorRef] = []
    seen: set[int] = set()
    for raw in actor_ids:
        try:
            actor_id = int(raw)
        except Exception:
            continue
        if actor_id in seen:
            continue
        seen.add(actor_id)
        payload = profile_lookup.get(actor_id) or {}
        refs.append(
            RiskScopeActorRef(
                actor_id=actor_id,
                actor_name=str(payload.get("username") or payload.get("name") or actor_id),
            )
        )
    return refs


def _coerce_entity_refs(
    uuids: Iterable[Any],
    entities: Optional[Iterable[Any]] = None,
) -> List[RiskScopeEntityRef]:
    entity_lookup: Dict[str, Dict[str, Any]] = {}
    for entity in entities or []:
        payload = _to_dict(entity)
        uuid = str(payload.get("uuid") or payload.get("entity_uuid") or "").strip()
        if uuid:
            entity_lookup[uuid] = payload

    refs: List[RiskScopeEntityRef] = []
    seen: set[str] = set()
    for raw in uuids:
        uuid = str(raw or "").strip()
        if not uuid or uuid in seen:
            continue
        seen.add(uuid)
        payload = entity_lookup.get(uuid) or {}
        refs.append(RiskScopeEntityRef(entity_uuid=uuid, entity_name=str(payload.get("name") or uuid)))
    return refs


def _default_metrics_for_risk_type(risk_type: str, index: int) -> List[str]:
    mapping = {
        "eco_social_cascade": [
            ["exposure_score", "spread_pressure"],
            ["ecosystem_integrity", "vulnerability_score"],
            ["livelihood_stability", "economic_stress"],
            ["public_trust", "panic_level"],
            ["response_capacity", "service_capacity"],
        ],
        "market_trust_stress": [
            ["economic_stress", "public_trust"],
            ["panic_level", "economic_stress"],
            ["livelihood_stability", "economic_stress"],
            ["public_trust", "panic_level"],
            ["service_capacity", "vulnerability_score"],
        ],
        "governance_response_friction": [
            ["response_capacity", "service_capacity"],
            ["economic_stress", "response_capacity"],
            ["livelihood_stability", "economic_stress"],
            ["public_trust", "response_capacity"],
            ["public_trust", "panic_level"],
        ],
    }
    metric_sets = mapping.get(risk_type) or mapping["eco_social_cascade"]
    return list(metric_sets[min(index, len(metric_sets) - 1)])


def _coerce_evidence(items: Iterable[Any]) -> List[RiskEvidence]:
    evidence: List[RiskEvidence] = []
    for index, raw in enumerate(items or [], 1):
        payload = _to_dict(raw)
        evidence.append(
            RiskEvidence(
                evidence_id=str(payload.get("evidence_id") or f"evidence_{index}"),
                source_type=str(payload.get("source_type") or "scenario"),
                title=str(payload.get("title") or payload.get("source_ref") or f"Evidence {index}"),
                summary=str(payload.get("summary") or ""),
                confidence=clamp_probability(payload.get("confidence", 0.6)),
                source_ref=str(payload.get("source_ref") or ""),
                related_chain_steps=list(payload.get("related_chain_steps") or []),
                region_scope=list(payload.get("region_scope") or []),
                entity_refs=list(payload.get("entity_refs") or []),
                extracted_facts=list(payload.get("extracted_facts") or []),
            )
        )
    return evidence


def _coerce_clusters(items: Iterable[Any]) -> List[RiskAffectedCluster]:
    clusters: List[RiskAffectedCluster] = []
    for index, raw in enumerate(items or [], 1):
        payload = _to_dict(raw)
        clusters.append(
            RiskAffectedCluster(
                cluster_id=str(payload.get("cluster_id") or f"cluster_{index}"),
                name=str(payload.get("name") or f"Cluster {index}"),
                cluster_type=str(payload.get("cluster_type") or "community"),
                primary_regions=list(payload.get("primary_regions") or []),
                actor_ids=[int(item) for item in (payload.get("actor_ids") or []) if str(item).lstrip("-").isdigit()],
                dependency_profile=list(payload.get("dependency_profile") or []),
                early_loss_signals=list(payload.get("early_loss_signals") or []),
                vulnerability_score=clamp_score(payload.get("vulnerability_score", 0)),
                mismatch_risk=clamp_score(payload.get("mismatch_risk", 0)),
                notes=str(payload.get("notes") or ""),
            )
        )
    return clusters


def _coerce_interventions(items: Iterable[Any]) -> List[RiskInterventionOption]:
    interventions: List[RiskInterventionOption] = []
    for index, raw in enumerate(items or [], 1):
        payload = _to_dict(raw)
        interventions.append(
            RiskInterventionOption(
                intervention_id=str(payload.get("intervention_id") or f"intervention_{index}"),
                name=str(payload.get("name") or f"Intervention {index}"),
                policy_type=str(payload.get("policy_type") or "monitor"),
                description=str(payload.get("description") or ""),
                target_chain_steps=list(payload.get("target_chain_steps") or []),
                expected_direct_effects=list(payload.get("expected_direct_effects") or []),
                expected_second_order_effects=list(payload.get("expected_second_order_effects") or []),
                benefit_clusters=list(payload.get("benefit_clusters") or []),
                hurt_clusters=list(payload.get("hurt_clusters") or []),
                friction_points=list(payload.get("friction_points") or []),
                confidence=clamp_probability(payload.get("confidence", 0.55)),
                source_variable_id=str(payload.get("source_variable_id") or ""),
            )
        )
    return interventions


def _coerce_branches(items: Iterable[Any]) -> List[RiskScenarioBranch]:
    branches: List[RiskScenarioBranch] = []
    for index, raw in enumerate(items or [], 1):
        payload = _to_dict(raw)
        branches.append(
            RiskScenarioBranch(
                branch_id=str(payload.get("branch_id") or f"branch_{index}"),
                name=str(payload.get("name") or f"Branch {index}"),
                description=str(payload.get("description") or ""),
                assumptions=list(payload.get("assumptions") or []),
                target_interventions=list(payload.get("target_interventions") or []),
                comparison_focus=list(payload.get("comparison_focus") or []),
                branch_type=str(payload.get("branch_type") or "baseline"),
            )
        )
    return branches


def risk_objects_to_definitions(
    risk_objects: Iterable[Any],
    regions: Optional[Iterable[Any]] = None,
    profiles: Optional[Iterable[Any]] = None,
    entities: Optional[Iterable[Any]] = None,
) -> List[RiskDefinition]:
    definitions: List[RiskDefinition] = []
    for raw in risk_objects or []:
        risk = _to_dict(raw)
        risk_id = str(risk.get("risk_object_id") or risk.get("risk_id") or "").strip()
        if not risk_id:
            continue

        region_refs = _coerce_region_refs(
            list(risk.get("primary_regions") or []) + list(risk.get("region_scope") or []),
            regions=regions,
        )
        cluster_payloads = list(risk.get("affected_clusters") or [])
        actor_ids: List[int] = []
        for cluster in cluster_payloads:
            cluster_dict = _to_dict(cluster)
            for item in cluster_dict.get("actor_ids") or []:
                if str(item).lstrip("-").isdigit():
                    actor_ids.append(int(item))
        actor_refs = _coerce_actor_refs(actor_ids, profiles=profiles)
        entity_refs = _coerce_entity_refs(risk.get("source_entity_uuids") or [], entities=entities)

        step_used: set[str] = set()
        chain_steps = []
        for index, label in enumerate(risk.get("chain_steps") or [], 1):
            step_id = ensure_unique_slug(f"{risk_id}_{label}", step_used)
            chain_steps.append(
                RiskChainStepDefinition(
                    step_id=step_id,
                    label=str(label),
                    step_type=str(risk.get("risk_type") or "generic"),
                    monitor_metrics=_default_metrics_for_risk_type(str(risk.get("risk_type") or ""), index - 1),
                )
            )

        priority_seed = clamp_probability(
            (
                float(risk.get("severity_score") or 0) * 0.45
                + float(risk.get("actionability_score") or 0) * 0.35
                + float(risk.get("confidence_score") or 0) * 100 * 0.2
            )
            / 100
        )

        source_variable_ids = list(risk.get("source_variable_ids") or [])
        category = "variable_triggered" if source_variable_ids else "baseline"
        definitions.append(
            RiskDefinition(
                risk_id=risk_id,
                legacy_risk_object_id=risk_id,
                category=category,
                risk_type=str(risk.get("risk_type") or ""),
                title=str(risk.get("title") or risk_id),
                summary=str(risk.get("summary") or ""),
                status=str(risk.get("status") or "tracked"),
                mode=str(risk.get("mode") or "watch"),
                time_horizon=str(risk.get("time_horizon") or "30d"),
                priority_seed=priority_seed,
                scope_regions=region_refs,
                scope_entities=entity_refs,
                scope_actors=actor_refs,
                chain_template=chain_steps,
                root_pressures=list(risk.get("root_pressures") or []),
                turning_point_candidates=list(risk.get("turning_points") or []),
                amplifiers=list(risk.get("amplifiers") or []),
                buffers=list(risk.get("buffers") or []),
                source_entity_uuids=list(risk.get("source_entity_uuids") or []),
                source_variable_ids=source_variable_ids,
                evidence=_coerce_evidence(risk.get("evidence") or []),
                affected_clusters=_coerce_clusters(cluster_payloads),
                intervention_templates=_coerce_interventions(risk.get("intervention_options") or []),
                branch_templates=_coerce_branches(risk.get("scenario_branches") or []),
                trigger_rules={
                    "variable_types": [str(risk.get("mode") or "watch")],
                    "has_source_variables": bool(source_variable_ids),
                },
                created_at=str(risk.get("created_at") or _now()),
                updated_at=_now(),
            )
        )
    return definitions


def project_legacy_risk_objects(
    risk_definitions: Iterable[Any],
    runtime_bundle: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    runtime_bundle = runtime_bundle or {}
    runtime_states = runtime_bundle.get("risk_states") or []
    runtime_by_id = {
        str(item.get("risk_id") or "").strip(): _to_dict(item)
        for item in runtime_states
        if str(_to_dict(item).get("risk_id") or "").strip()
    }
    projected: List[Dict[str, Any]] = []
    for raw in risk_definitions or []:
        definition = _to_dict(raw)
        risk_id = str(definition.get("risk_id") or definition.get("legacy_risk_object_id") or "").strip()
        if not risk_id:
            continue
        runtime = runtime_by_id.get(risk_id) or {}
        scope = definition.get("scope") or {}
        scope_regions = list(scope.get("regions") or [])
        impacted_regions = list(runtime.get("impacted_regions") or scope_regions)
        region_names = _unique_strings(
            [item.get("region_name") or item.get("name") for item in impacted_regions]
            + [item.get("region_name") or item.get("name") for item in scope_regions]
        )
        chain_template = list(definition.get("chain_template") or [])
        chain_steps = [str(item.get("label") or item.get("step_id") or "") for item in chain_template]
        drivers = _unique_strings(runtime.get("drivers") or [])
        why_now = runtime.get("explanation") or " · ".join(drivers[:2]) or definition.get("summary") or ""
        summary = str(definition.get("summary") or "")
        explanation = str(runtime.get("explanation") or "")
        if summary and explanation and explanation not in summary:
            summary = f"{summary} 当前阶段：{explanation}"
        elif explanation:
            summary = explanation

        impacted_actor_ids = [item.get("actor_id") for item in (runtime.get("impacted_actors") or [])]
        affected_clusters = []
        for cluster in definition.get("affected_clusters") or []:
            cluster_dict = _to_dict(cluster)
            actor_ids = [int(item) for item in (cluster_dict.get("actor_ids") or []) if str(item).lstrip("-").isdigit()]
            if impacted_actor_ids and not set(actor_ids).intersection(set(int(item) for item in impacted_actor_ids if str(item).isdigit())):
                pass
            affected_clusters.append(cluster_dict)

        severity_score = runtime.get("severity_score")
        if severity_score is None:
            severity_score = clamp_score(float(definition.get("priority_seed") or 0) * 100)
        confidence_score = runtime.get("confidence_score", 0.62)
        actionability = 50.0
        interventions = definition.get("intervention_templates") or []
        if interventions:
            confidences = [float(_to_dict(item).get("confidence") or 0.55) for item in interventions]
            actionability = clamp_score(sum(confidences) / max(len(confidences), 1) * 100)

        projected.append(
            {
                "risk_object_id": risk_id,
                "title": definition.get("title") or risk_id,
                "summary": summary,
                "why_now": why_now,
                "risk_type": definition.get("risk_type") or "",
                "mode": definition.get("mode") or "watch",
                "status": "active" if clamp_score(severity_score) >= 35 else (definition.get("status") or "tracked"),
                "time_horizon": definition.get("time_horizon") or "30d",
                "region_scope": region_names,
                "primary_regions": region_names[:2],
                "severity_score": clamp_score(severity_score),
                "confidence_score": clamp_probability(confidence_score),
                "actionability_score": actionability,
                "novelty_score": clamp_score(58 + (12 if definition.get("category") != "baseline" else 0)),
                "root_pressures": list(definition.get("root_pressures") or []),
                "chain_steps": chain_steps,
                "turning_points": _unique_strings(
                    list(runtime.get("turning_points") or []) + list(definition.get("turning_point_candidates") or [])
                ),
                "amplifiers": list(definition.get("amplifiers") or []),
                "buffers": _unique_strings(list(runtime.get("buffers") or []) + list(definition.get("buffers") or [])),
                "source_entity_uuids": _unique_strings(
                    list(definition.get("source_entity_uuids") or [])
                    + [item.get("entity_uuid") for item in (scope.get("entities") or [])]
                ),
                "source_variable_ids": list(definition.get("source_variable_ids") or []),
                "evidence": [item if isinstance(item, dict) else _to_dict(item) for item in (definition.get("evidence") or [])],
                "affected_clusters": affected_clusters,
                "intervention_options": [
                    item if isinstance(item, dict) else _to_dict(item)
                    for item in interventions
                ],
                "scenario_branches": [
                    item if isinstance(item, dict) else _to_dict(item)
                    for item in (definition.get("branch_templates") or [])
                ],
                "created_at": definition.get("created_at") or _now(),
            }
        )
    projected.sort(
        key=lambda item: (
            float(item.get("severity_score") or 0),
            float(item.get("actionability_score") or 0),
            float(item.get("confidence_score") or 0),
        ),
        reverse=True,
    )
    return projected


def build_legacy_risk_summary(
    legacy_risk_objects: Iterable[Dict[str, Any]],
    primary_risk_object_id: str = "",
    generation_notes: Optional[List[str]] = None,
    primary_active_risk_id: str = "",
    pinned_risk_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    items = list(legacy_risk_objects or [])
    selected_primary = primary_active_risk_id or primary_risk_object_id
    primary = None
    if selected_primary:
        for item in items:
            if str(item.get("risk_object_id") or "") == selected_primary:
                primary = item
                break
    if primary is None and items:
        primary = items[0]
        selected_primary = str(primary.get("risk_object_id") or "")
    return {
        "primary_risk_object_id": primary_risk_object_id or selected_primary,
        "primary_active_risk_id": primary_active_risk_id or selected_primary,
        "pinned_risk_ids": _unique_strings(pinned_risk_ids or []),
        "risk_objects_count": len(items),
        "risk_objects": items,
        "primary_risk_object": primary,
        "generation_notes": list(generation_notes or []),
    }


def build_initial_runtime_bundle_from_legacy(
    risk_objects: Iterable[Any],
    risk_definitions: Iterable[Any],
    primary_risk_id: str = "",
) -> Dict[str, Any]:
    definition_by_id = {
        str(_to_dict(item).get("risk_id") or _to_dict(item).get("legacy_risk_object_id") or ""): _to_dict(item)
        for item in risk_definitions or []
    }
    risk_states: List[Dict[str, Any]] = []
    for raw in risk_objects or []:
        risk = _to_dict(raw)
        risk_id = str(risk.get("risk_object_id") or risk.get("risk_id") or "").strip()
        if not risk_id:
            continue
        definition = definition_by_id.get(risk_id) or {}
        chain_template = list(definition.get("chain_template") or [])
        step_states = []
        active_step_ids = []
        severity_score = clamp_score(risk.get("severity_score", 0))
        confidence_score = clamp_probability(risk.get("confidence_score", 0.62))
        step_count = max(1, len(chain_template))
        activation_threshold = max(1, min(step_count, round(severity_score / 35)))
        for index, step in enumerate(chain_template):
            score = clamp_probability(max(0.12, min(0.95, severity_score / 100 - index * 0.12)))
            status = "active" if index < activation_threshold else ("watch" if score >= 0.28 else "inactive")
            if status == "active":
                active_step_ids.append(step.get("step_id"))
            step_states.append(
                {
                    "step_id": step.get("step_id"),
                    "label": step.get("label"),
                    "status": status,
                    "score": score,
                    "evidence_refs": [item.get("evidence_id") for item in (definition.get("evidence") or [])[:2] if item.get("evidence_id")],
                }
            )
        scope = definition.get("scope") or {}
        risk_states.append(
            {
                "risk_id": risk_id,
                "title": risk.get("title") or definition.get("title") or risk_id,
                "round": 0,
                "category": definition.get("category") or "baseline",
                "risk_type": risk.get("risk_type") or definition.get("risk_type") or "",
                "severity_score": severity_score,
                "confidence_score": confidence_score,
                "trend": "stable",
                "runtime_priority": clamp_probability(
                    0.55 * (severity_score / 100) + 0.2 * confidence_score + 0.25 * clamp_probability(definition.get("priority_seed", 0))
                ),
                "active_step_ids": active_step_ids,
                "step_states": step_states,
                "impacted_regions": list(scope.get("regions") or []),
                "impacted_actors": list(scope.get("actors") or []),
                "related_dynamic_edge_ids": [],
                "drivers": _unique_strings(list(risk.get("root_pressures") or []) + [risk.get("why_now")]),
                "buffers": list(risk.get("buffers") or []),
                "turning_points": list(risk.get("turning_points") or []),
                "explanation": str(risk.get("why_now") or risk.get("summary") or ""),
                "triggered_by_event_ids": [],
                "updated_at": _now(),
            }
        )
    risk_states.sort(
        key=lambda item: (
            float(item.get("runtime_priority") or 0),
            float(item.get("severity_score") or 0),
        ),
        reverse=True,
    )
    primary_active_risk_id = primary_risk_id or (risk_states[0]["risk_id"] if risk_states else "")
    pinned_risk_ids = [item["risk_id"] for item in risk_states[:3]]
    bundle = RiskRuntimeStateBundle(
        round=0,
        risk_states=[],
        primary_active_risk_id=primary_active_risk_id,
        pinned_risk_ids=pinned_risk_ids,
        refresh_reason="prepare_initialization",
    )
    payload = bundle.to_dict()
    payload["risk_states"] = risk_states
    if not payload.get("primary_active_risk") and risk_states:
        payload["primary_active_risk"] = risk_states[0]
    return payload
