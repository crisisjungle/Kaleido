"""
Risk runtime tracker.

Turns risk definitions plus live simulation snapshots into runtime risk states.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .envfish_models import RiskRuntimeStateBundle, clamp_probability, clamp_score
from .risk_projection import build_initial_runtime_bundle_from_legacy


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


def _is_inverse_metric(metric: str) -> bool:
    return metric in {
        "ecosystem_integrity",
        "livelihood_stability",
        "public_trust",
        "service_capacity",
        "response_capacity",
    }


def _metric_score(metric: str, value: float) -> float:
    score = clamp_score(value)
    if _is_inverse_metric(metric):
        score = 100 - score
    return clamp_probability(score / 100)


class RiskRuntimeTracker:
    def build_initial_bundle(
        self,
        risk_definitions: Iterable[Any],
        primary_risk_id: str = "",
        source_risk_objects: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        definitions = [_to_dict(item) for item in (risk_definitions or []) if _to_dict(item)]
        if source_risk_objects:
            return build_initial_runtime_bundle_from_legacy(
                risk_objects=source_risk_objects,
                risk_definitions=definitions,
                primary_risk_id=primary_risk_id,
            )
        bundle = RiskRuntimeStateBundle(
            round=0,
            risk_states=[],
            primary_active_risk_id=primary_risk_id,
            pinned_risk_ids=[],
            refresh_reason="prepare_initialization",
        ).to_dict()
        risk_states: List[Dict[str, Any]] = []
        for definition in definitions:
            chain_template = list((definition.get("chain_template") or []))
            step_states = []
            active_step_ids = []
            for index, step in enumerate(chain_template):
                score = clamp_probability(max(0.12, 0.42 - index * 0.08))
                status = "active" if index == 0 else ("watch" if score >= 0.25 else "inactive")
                if status == "active":
                    active_step_ids.append(step.get("step_id"))
                step_states.append(
                    {
                        "step_id": step.get("step_id"),
                        "label": step.get("label"),
                        "status": status,
                        "score": score,
                        "evidence_refs": [],
                    }
                )
            severity = clamp_score(float(definition.get("priority_seed") or 0) * 100)
            risk_states.append(
                {
                    "risk_id": definition.get("risk_id"),
                    "title": definition.get("title"),
                    "round": 0,
                    "category": definition.get("category") or "baseline",
                    "risk_type": definition.get("risk_type") or "",
                    "severity_score": severity,
                    "confidence_score": 0.62,
                    "trend": "stable",
                    "runtime_priority": clamp_probability(
                        0.6 * (severity / 100) + 0.4 * float(definition.get("priority_seed") or 0)
                    ),
                    "active_step_ids": active_step_ids,
                    "step_states": step_states,
                    "impacted_regions": list((definition.get("scope") or {}).get("regions") or []),
                    "impacted_actors": list((definition.get("scope") or {}).get("actors") or []),
                    "related_dynamic_edge_ids": [],
                    "drivers": _unique_strings(
                        list(definition.get("root_pressures") or []) + list(definition.get("source_variable_ids") or [])
                    ),
                    "buffers": list(definition.get("buffers") or []),
                    "turning_points": list(definition.get("turning_point_candidates") or []),
                    "explanation": str(definition.get("summary") or ""),
                    "triggered_by_event_ids": [],
                    "updated_at": _now(),
                }
            )
        risk_states.sort(
            key=lambda item: (float(item.get("runtime_priority") or 0), float(item.get("severity_score") or 0)),
            reverse=True,
        )
        bundle["risk_states"] = risk_states
        if not bundle.get("primary_active_risk_id") and risk_states:
            bundle["primary_active_risk_id"] = risk_states[0]["risk_id"]
        bundle["pinned_risk_ids"] = [item["risk_id"] for item in risk_states[:3]]
        bundle["primary_active_risk"] = risk_states[0] if risk_states else None
        return bundle

    def refresh(
        self,
        risk_definitions: Iterable[Any],
        snapshot: Optional[Dict[str, Any]],
        previous_bundle: Optional[Dict[str, Any]] = None,
        risk_events: Optional[Iterable[Any]] = None,
        primary_hint: str = "",
        pinned_risk_ids: Optional[List[str]] = None,
        refresh_reason: str = "round_refresh",
    ) -> Dict[str, Any]:
        if not snapshot:
            return previous_bundle or self.build_initial_bundle(risk_definitions, primary_risk_id=primary_hint)

        definitions = [_to_dict(item) for item in (risk_definitions or []) if _to_dict(item)]
        round_num = int(snapshot.get("round") or 0)
        previous_lookup = {
            str(item.get("risk_id") or ""): item
            for item in (previous_bundle or {}).get("risk_states") or []
            if str(item.get("risk_id") or "")
        }
        region_lookup = {
            str(item.get("region_id") or ""): item
            for item in snapshot.get("regions") or []
            if str(item.get("region_id") or "")
        }
        actor_lookup = {
            int(item.get("agent_id")): item
            for item in snapshot.get("agents") or []
            if str(item.get("agent_id") or "").isdigit()
        }
        feedback = snapshot.get("feedback") or {}
        feedback_loops = [item.get("loop") for item in (feedback.get("feedback_propagation") or []) if item.get("loop")]
        turning_points = [str(item) for item in (feedback.get("turning_points") or []) if str(item or "").strip()]
        dynamic_edges = list(snapshot.get("dynamic_edges") or [])
        active_variables = list(snapshot.get("active_variables") or [])
        risk_events = [_to_dict(item) for item in (risk_events or []) if _to_dict(item)]
        recent_events_by_risk: Dict[str, List[Dict[str, Any]]] = {}
        for event in risk_events:
            risk_id = str(event.get("risk_id") or "").strip()
            if not risk_id:
                continue
            recent_events_by_risk.setdefault(risk_id, []).append(event)
        risk_states: List[Dict[str, Any]] = []
        for definition in definitions:
            risk_states.append(
                self._build_runtime_state(
                    definition=definition,
                    round_num=round_num,
                    region_lookup=region_lookup,
                    actor_lookup=actor_lookup,
                    feedback_loops=feedback_loops,
                    feedback_turning_points=turning_points,
                    dynamic_edges=dynamic_edges,
                    active_variables=active_variables,
                    previous_state=previous_lookup.get(str(definition.get("risk_id") or "")),
                    recent_events=recent_events_by_risk.get(str(definition.get("risk_id") or ""), []),
                )
            )

        selected_pins = list(pinned_risk_ids or (previous_bundle or {}).get("pinned_risk_ids") or [])
        risk_states.sort(
            key=lambda item: (
                float(item.get("runtime_priority") or 0),
                float(item.get("severity_score") or 0),
                1 if item.get("risk_id") in selected_pins else 0,
            ),
            reverse=True,
        )
        if not selected_pins:
            selected_pins = [item.get("risk_id") for item in risk_states[:3] if item.get("risk_id")]
        primary_active_risk_id = primary_hint or (risk_states[0].get("risk_id") if risk_states else "")
        bundle = RiskRuntimeStateBundle(
            round=round_num,
            risk_states=[],
            primary_active_risk_id=primary_active_risk_id,
            pinned_risk_ids=selected_pins,
            refresh_reason=refresh_reason,
            updated_at=_now(),
        ).to_dict()
        bundle["risk_states"] = risk_states
        bundle["primary_active_risk"] = None
        for item in risk_states:
            if item.get("risk_id") == primary_active_risk_id:
                bundle["primary_active_risk"] = item
                break
        if bundle["primary_active_risk"] is None and risk_states:
            bundle["primary_active_risk"] = risk_states[0]
            bundle["primary_active_risk_id"] = risk_states[0].get("risk_id")
        return bundle

    def _build_runtime_state(
        self,
        definition: Dict[str, Any],
        round_num: int,
        region_lookup: Dict[str, Dict[str, Any]],
        actor_lookup: Dict[int, Dict[str, Any]],
        feedback_loops: List[str],
        feedback_turning_points: List[str],
        dynamic_edges: List[Dict[str, Any]],
        active_variables: List[Dict[str, Any]],
        previous_state: Optional[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        scope = definition.get("scope") or {}
        scope_regions = list(scope.get("regions") or [])
        scope_actors = list(scope.get("actors") or [])
        region_payloads = []
        for ref in scope_regions:
            region_id = str(ref.get("region_id") or "").strip()
            if region_id and region_id in region_lookup:
                region_payloads.append(region_lookup[region_id])
        if not region_payloads:
            ranked_regions = sorted(
                region_lookup.values(),
                key=lambda item: (
                    float((item.get("state_vector") or {}).get("vulnerability_score", item.get("vulnerability_score", 0))),
                    float((item.get("state_vector") or {}).get("exposure_score", item.get("exposure_score", 0))),
                ),
                reverse=True,
            )
            region_payloads = ranked_regions[:2]

        actor_payloads = []
        for ref in scope_actors:
            try:
                actor_id = int(ref.get("actor_id"))
            except Exception:
                continue
            actor = actor_lookup.get(actor_id)
            if actor:
                actor_payloads.append(actor)

        if not actor_payloads and region_payloads:
            region_ids = {str(item.get("region_id") or "") for item in region_payloads}
            actor_payloads = [
                item
                for item in actor_lookup.values()
                if str(item.get("primary_region") or "").strip() in region_ids
            ][:6]

        severity_score = self._severity_score(definition, region_payloads, actor_payloads, active_variables, dynamic_edges)
        confidence_score = self._confidence_score(definition, region_payloads, actor_payloads, recent_events)
        step_states = self._step_states(definition, region_payloads, actor_payloads, recent_events, severity_score)
        active_step_ids = [item["step_id"] for item in step_states if item.get("status") == "active"]
        related_dynamic_edge_ids = self._related_dynamic_edge_ids(definition, dynamic_edges, region_payloads, actor_payloads)
        drivers = self._drivers(definition, region_payloads, active_variables, feedback_loops, recent_events, related_dynamic_edge_ids)
        buffers = self._buffers(definition, region_payloads, actor_payloads)
        turning_points = self._turning_points(definition, feedback_turning_points, severity_score)
        trend = self._trend(previous_state, severity_score)
        impacted_regions = [
            {
                "region_id": str(item.get("region_id") or ""),
                "region_name": str(item.get("name") or item.get("region_name") or item.get("region_id") or ""),
            }
            for item in region_payloads
        ]
        impacted_actors = [
            {
                "actor_id": int(item.get("agent_id")),
                "actor_name": str(item.get("agent_name") or item.get("username") or item.get("name") or item.get("agent_id")),
            }
            for item in actor_payloads
            if str(item.get("agent_id") or "").isdigit()
        ]
        runtime_priority = self._runtime_priority(
            severity_score=severity_score,
            trend=trend,
            breadth=len(impacted_regions) + len(impacted_actors),
            recent_event_count=len(recent_events),
        )
        explanation = self._explanation(definition, severity_score, trend, drivers, turning_points)
        return {
            "risk_id": definition.get("risk_id"),
            "title": definition.get("title"),
            "round": round_num,
            "category": definition.get("category") or "baseline",
            "risk_type": definition.get("risk_type") or "",
            "severity_score": severity_score,
            "confidence_score": confidence_score,
            "trend": trend,
            "runtime_priority": runtime_priority,
            "active_step_ids": active_step_ids,
            "step_states": step_states,
            "impacted_regions": impacted_regions,
            "impacted_actors": impacted_actors,
            "related_dynamic_edge_ids": related_dynamic_edge_ids,
            "drivers": drivers,
            "buffers": buffers,
            "turning_points": turning_points,
            "explanation": explanation,
            "triggered_by_event_ids": [item.get("event_id") for item in recent_events if item.get("event_id")],
            "updated_at": _now(),
        }

    def _severity_score(
        self,
        definition: Dict[str, Any],
        region_payloads: List[Dict[str, Any]],
        actor_payloads: List[Dict[str, Any]],
        active_variables: List[Dict[str, Any]],
        dynamic_edges: List[Dict[str, Any]],
    ) -> float:
        metrics: List[float] = []
        for region in region_payloads:
            vector = region.get("state_vector") or region
            metrics.extend(
                [
                    float(vector.get("exposure_score", region.get("exposure_score", 0))),
                    float(vector.get("spread_pressure", region.get("spread_pressure", 0))),
                    100 - float(vector.get("ecosystem_integrity", region.get("ecosystem_integrity", 100))),
                    100 - float(vector.get("livelihood_stability", region.get("livelihood_stability", 100))),
                    float(vector.get("economic_stress", region.get("economic_stress", 0))),
                    float(vector.get("panic_level", region.get("panic_level", 0))),
                    float(vector.get("vulnerability_score", region.get("vulnerability_score", 0))),
                ]
            )
        for actor in actor_payloads:
            vector = actor.get("state_vector") or actor
            metrics.extend(
                [
                    float(vector.get("vulnerability_score", 0)),
                    float(vector.get("economic_stress", 0)),
                    float(vector.get("panic_level", 0)),
                    100 - float(vector.get("public_trust", 100)),
                ]
            )
        if not metrics:
            metrics.append(float(definition.get("priority_seed") or 0) * 100)
        base = sum(metrics) / max(len(metrics), 1)
        variable_bonus = sum(float(item.get("intensity_0_100") or item.get("intensity") or 0) for item in active_variables[:2]) / 18
        dynamic_bonus = min(12.0, len(dynamic_edges) * 1.2)
        risk_type = str(definition.get("risk_type") or "")
        if risk_type == "market_trust_stress":
            base = base * 0.88 + variable_bonus * 0.8
        elif risk_type == "governance_response_friction":
            base = base * 0.82 + dynamic_bonus * 0.7
        else:
            base = base * 0.9 + variable_bonus * 0.9
        return clamp_score(base + variable_bonus + dynamic_bonus)

    def _confidence_score(
        self,
        definition: Dict[str, Any],
        region_payloads: List[Dict[str, Any]],
        actor_payloads: List[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
    ) -> float:
        evidence_count = len(definition.get("evidence") or [])
        scope_regions = len((definition.get("scope") or {}).get("regions") or [])
        scope_actors = len((definition.get("scope") or {}).get("actors") or [])
        coverage = 0.0
        if scope_regions:
            coverage += min(1.0, len(region_payloads) / scope_regions) * 0.35
        if scope_actors:
            coverage += min(1.0, len(actor_payloads) / scope_actors) * 0.25
        event_signal = min(0.18, len(recent_events) * 0.04)
        evidence_signal = min(0.22, evidence_count * 0.03)
        return clamp_probability(0.38 + coverage + event_signal + evidence_signal)

    def _step_states(
        self,
        definition: Dict[str, Any],
        region_payloads: List[Dict[str, Any]],
        actor_payloads: List[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
        severity_score: float,
    ) -> List[Dict[str, Any]]:
        chain_template = list(definition.get("chain_template") or [])
        states: List[Dict[str, Any]] = []
        activation_cap = max(1, min(len(chain_template), round(severity_score / 32)))
        evidence_ids = [item.get("event_id") for item in recent_events if item.get("event_id")]
        for index, step in enumerate(chain_template):
            metrics = list(step.get("monitor_metrics") or [])
            metric_scores: List[float] = []
            for metric in metrics:
                for region in region_payloads:
                    vector = region.get("state_vector") or region
                    if metric in vector:
                        metric_scores.append(_metric_score(metric, float(vector.get(metric, 0))))
                for actor in actor_payloads:
                    vector = actor.get("state_vector") or actor
                    if metric in vector:
                        metric_scores.append(_metric_score(metric, float(vector.get(metric, 0))))
            if not metric_scores:
                score = clamp_probability(max(0.15, severity_score / 100 - index * 0.11))
            else:
                score = clamp_probability(sum(metric_scores) / max(len(metric_scores), 1))
            status = "active" if score >= 0.62 or index < activation_cap else ("watch" if score >= 0.28 else "inactive")
            states.append(
                {
                    "step_id": step.get("step_id"),
                    "label": step.get("label"),
                    "status": status,
                    "score": score,
                    "evidence_refs": evidence_ids[:2],
                }
            )
        return states

    def _related_dynamic_edge_ids(
        self,
        definition: Dict[str, Any],
        dynamic_edges: List[Dict[str, Any]],
        region_payloads: List[Dict[str, Any]],
        actor_payloads: List[Dict[str, Any]],
    ) -> List[str]:
        scope_region_ids = {
            str(item.get("region_id") or "").strip()
            for item in (definition.get("scope") or {}).get("regions") or []
            if str(item.get("region_id") or "").strip()
        }
        scope_actor_ids = {
            int(item.get("actor_id"))
            for item in (definition.get("scope") or {}).get("actors") or []
            if str(item.get("actor_id") or "").isdigit()
        }
        impacted_region_ids = {str(item.get("region_id") or "") for item in region_payloads}
        impacted_actor_ids = {int(item.get("agent_id")) for item in actor_payloads if str(item.get("agent_id") or "").isdigit()}
        matched: List[str] = []
        for edge in dynamic_edges:
            edge_id = str(edge.get("edge_id") or "").strip()
            if not edge_id:
                continue
            source_region = str(edge.get("source_region_id") or "").strip()
            target_region = str(edge.get("target_region_id") or "").strip()
            source_actor = edge.get("source_agent_id")
            target_actor = edge.get("target_agent_id")
            actor_match = False
            if str(source_actor or "").isdigit() and int(source_actor) in scope_actor_ids | impacted_actor_ids:
                actor_match = True
            if str(target_actor or "").isdigit() and int(target_actor) in scope_actor_ids | impacted_actor_ids:
                actor_match = True
            region_match = bool({source_region, target_region} & (scope_region_ids | impacted_region_ids))
            if actor_match or region_match:
                matched.append(edge_id)
        return matched[:8]

    def _drivers(
        self,
        definition: Dict[str, Any],
        region_payloads: List[Dict[str, Any]],
        active_variables: List[Dict[str, Any]],
        feedback_loops: List[str],
        recent_events: List[Dict[str, Any]],
        related_dynamic_edge_ids: List[str],
    ) -> List[str]:
        drivers = list(definition.get("root_pressures") or [])
        region_names = [item.get("name") or item.get("region_name") for item in region_payloads]
        if region_names:
            drivers.append(f"{' / '.join(region_names[:2])} 区域状态持续承压")
        for variable in active_variables[:3]:
            name = str(variable.get("name") or variable.get("variable_id") or "").strip()
            if name:
                drivers.append(f"变量 {name} 正在作用")
        drivers.extend(feedback_loops[:2])
        if related_dynamic_edge_ids:
            drivers.append(f"{len(related_dynamic_edge_ids)} 条动态边与该风险链路相关")
        for event in recent_events[:2]:
            summary = str(event.get("summary") or "").strip()
            if summary:
                drivers.append(summary)
        return _unique_strings(drivers)[:6]

    def _buffers(
        self,
        definition: Dict[str, Any],
        region_payloads: List[Dict[str, Any]],
        actor_payloads: List[Dict[str, Any]],
    ) -> List[str]:
        buffers = list(definition.get("buffers") or [])
        avg_response = 0.0
        values: List[float] = []
        for region in region_payloads:
            vector = region.get("state_vector") or region
            if "response_capacity" in vector:
                values.append(float(vector.get("response_capacity", 0)))
        for actor in actor_payloads:
            vector = actor.get("state_vector") or actor
            if "response_capacity" in vector:
                values.append(float(vector.get("response_capacity", 0)))
        if values:
            avg_response = sum(values) / len(values)
        if avg_response >= 55:
            buffers.append("当前响应能力仍具缓冲作用")
        return _unique_strings(buffers)[:5]

    def _turning_points(
        self,
        definition: Dict[str, Any],
        feedback_turning_points: List[str],
        severity_score: float,
    ) -> List[str]:
        candidates = list(definition.get("turning_point_candidates") or [])
        turning_points = list(feedback_turning_points or [])
        if severity_score >= 70 and candidates:
            turning_points.extend(candidates[:2])
        elif severity_score >= 45 and candidates:
            turning_points.extend(candidates[:1])
        return _unique_strings(turning_points)[:5]

    def _trend(self, previous_state: Optional[Dict[str, Any]], severity_score: float) -> str:
        if not previous_state:
            return "stable"
        delta = severity_score - float(previous_state.get("severity_score") or 0)
        if delta >= 4:
            return "rising"
        if delta <= -4:
            return "falling"
        return "stable"

    def _runtime_priority(
        self,
        severity_score: float,
        trend: str,
        breadth: int,
        recent_event_count: int,
    ) -> float:
        trend_weight = {"rising": 0.92, "stable": 0.58, "falling": 0.34}.get(trend, 0.58)
        breadth_weight = min(1.0, breadth / 8)
        recency_weight = min(1.0, recent_event_count / 4)
        return clamp_probability(
            0.45 * (severity_score / 100)
            + 0.2 * trend_weight
            + 0.15 * breadth_weight
            + 0.2 * recency_weight
        )

    def _explanation(
        self,
        definition: Dict[str, Any],
        severity_score: float,
        trend: str,
        drivers: List[str],
        turning_points: List[str],
    ) -> str:
        title = str(definition.get("title") or definition.get("risk_id") or "风险")
        direction = {"rising": "进入上升阶段", "falling": "出现回落迹象", "stable": "保持高位或平稳"}[trend]
        driver_text = "、".join(drivers[:2]) if drivers else "区域与群体状态持续变化"
        point_text = f"；关键转折点包括 {turning_points[0]}" if turning_points else ""
        return f"{title} 当前严重度约为 {round(severity_score, 1)}，{direction}，主要受 {driver_text} 推动{point_text}。"
