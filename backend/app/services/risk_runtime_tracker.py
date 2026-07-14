from typing import Any, Dict, List, Optional


class RiskRuntimeTracker:
    """Track how each risk object evolves across simulation rounds.

    Previously `refresh()` just re-copied the static definitions every round, so
    severity never moved (the "five risks frozen at 68.4" problem). Now each
    round derives a per-risk *runtime tension* from the snapshot's real region
    state vectors, accumulates a tension trace, detects turning points, and lets
    status escalate/de-escalate — which in turn drives risk_events.
    """

    # state-vector keys where a HIGHER value means a WORSE situation
    _WORSE_WHEN_HIGH = (
        "exposure_score",
        "spread_pressure",
        "panic_level",
        "vulnerability_score",
        "economic_stress",
    )
    # state-vector keys where a LOWER value means a WORSE situation (inverted)
    _WORSE_WHEN_LOW = (
        "ecosystem_integrity",
        "public_trust",
        "service_capacity",
        "response_capacity",
        "livelihood_stability",
    )

    def build_initial_bundle(
        self,
        risk_definitions: Optional[List[Dict[str, Any]]] = None,
        primary_risk_id: str = "",
        source_risk_objects=None,
    ) -> Dict[str, Any]:
        definitions = risk_definitions or []
        primary = primary_risk_id or (definitions[0].get("risk_id") if definitions else "")
        states: List[Dict[str, Any]] = []
        for item in definitions:
            if not isinstance(item, dict):
                continue
            severity = self._coerce(item.get("severity_score"), 50.0)
            try:
                contract_version = int(item.get("risk_contract_version") or 1)
            except (TypeError, ValueError):
                contract_version = 1
            definition_status = str(item.get("runtime_status") or item.get("lifecycle_status") or "").strip()
            if definition_status == "dormant":
                initial_status = "dormant"
            elif contract_version >= 2:
                initial_status = self._status(severity, [severity])
            else:
                initial_status = str(item.get("status") or "watch")
            states.append(
                {
                    "risk_id": item.get("risk_id") or item.get("risk_object_id"),
                    "status": initial_status,
                    "previous_status": initial_status,
                    "severity_score": round(severity, 1),
                    "confidence_score": self._coerce(item.get("confidence_score"), 0.5, probability=True),
                    "runtime_tension": round(severity, 1),
                    "tension_trace": [round(severity, 1)],
                    "turning_point": False,
                    "created_round": int(item.get("created_round") or 0),
                    "monitoring_metrics": list(item.get("monitoring_metrics") or []),
                }
            )
        return {
            "round": 0,
            "primary_active_risk_id": primary,
            "pinned_risk_ids": [],
            "emergence_candidates": {},
            "risk_states": states,
        }

    def refresh(
        self,
        risk_definitions=None,
        snapshot=None,
        previous_bundle=None,
        primary_hint: str = "",
        pinned_risk_ids=None,
        refresh_reason: str = "round_refresh",
        **kwargs,
    ) -> Dict[str, Any]:
        previous_bundle = previous_bundle or {}
        definitions = risk_definitions or []
        snapshot = snapshot or {}
        round_num = int(snapshot.get("round") or previous_bundle.get("round") or 0)
        region_index = self._index_regions(snapshot)
        prev_states = {
            state.get("risk_id"): state
            for state in (previous_bundle.get("risk_states") or [])
            if isinstance(state, dict)
        }

        states: List[Dict[str, Any]] = []
        for item in definitions:
            if not isinstance(item, dict):
                continue
            risk_id = item.get("risk_id") or item.get("risk_object_id")
            static_severity = self._coerce(item.get("severity_score"), 50.0)
            tension = self._risk_tension(item, region_index)
            if tension is None:
                # no matching region state this round: hold the static value so we
                # never fabricate movement we cannot ground.
                tension = static_severity
            # runtime severity tracks live state but stays anchored to the static
            # definition so it cannot drift arbitrarily.
            severity = round(0.35 * static_severity + 0.65 * tension, 1)
            prev = prev_states.get(risk_id) or {}
            trace = list(prev.get("tension_trace") or [])
            trace.append(round(tension, 1))
            trace = trace[-24:]
            definition_status = str(item.get("runtime_status") or item.get("lifecycle_status") or "").strip()
            runtime_status = "dormant" if definition_status == "dormant" else self._status(tension, trace)
            states.append(
                {
                    "risk_id": risk_id,
                    "status": runtime_status,
                    "previous_status": prev.get("status") or "watch",
                    "severity_score": severity,
                    "confidence_score": self._coerce(item.get("confidence_score"), 0.5, probability=True),
                    "runtime_tension": round(tension, 1),
                    "tension_trace": trace,
                    "turning_point": self._is_turning_point(trace),
                    "created_round": int(item.get("created_round") or 0),
                    "monitoring_metrics": list(item.get("monitoring_metrics") or []),
                }
            )

        primary = self._select_primary(states, previous_bundle, primary_hint)
        return {
            "round": round_num,
            "primary_active_risk_id": primary,
            "pinned_risk_ids": pinned_risk_ids or previous_bundle.get("pinned_risk_ids") or [],
            "emergence_candidates": dict(previous_bundle.get("emergence_candidates") or {}),
            "refresh_reason": refresh_reason,
            "risk_states": states,
        }

    # -- helpers ---------------------------------------------------------------

    def _index_regions(self, snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        index: Dict[str, Dict[str, Any]] = {}
        for region in (snapshot.get("regions") or []) + (snapshot.get("subregions") or []):
            if not isinstance(region, dict):
                continue
            state_vector = dict(region.get("state_vector")) if isinstance(region.get("state_vector"), dict) else dict(region)
            if isinstance(region.get("scenario_state"), dict):
                state_vector.update(region.get("scenario_state") or {})
            for key in (region.get("region_id"), region.get("name")):
                token = str(key or "").strip().lower()
                if token:
                    index[token] = state_vector
        return index

    def _risk_region_tokens(self, item: Dict[str, Any]) -> List[str]:
        tokens: List[str] = []
        for name in item.get("region_scope") or []:
            tokens.append(str(name or "").strip().lower())
        for name in item.get("primary_regions") or []:
            tokens.append(str(name or "").strip().lower())
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        for region in scope.get("regions") or []:
            if isinstance(region, dict):
                tokens.append(str(region.get("region_id") or "").strip().lower())
                tokens.append(str(region.get("region_name") or "").strip().lower())
        return [token for token in dict.fromkeys(tokens) if token]

    def _risk_tension(self, item: Dict[str, Any], region_index: Dict[str, Dict[str, Any]]) -> Optional[float]:
        if not region_index:
            return None
        matched: List[Dict[str, Any]] = []
        matched_state_ids: set[int] = set()
        for token in self._risk_region_tokens(item):
            state = region_index.get(token)
            if state and id(state) not in matched_state_ids:
                matched.append(state)
                matched_state_ids.add(id(state))
        if not matched:
            return None
        badness_values: List[float] = []
        monitoring_metrics = self._monitoring_metrics(item)
        for state in matched:
            badness_values.append(
                self._metric_badness(state, monitoring_metrics)
                if monitoring_metrics
                else self._region_badness(state)
            )
        return sum(badness_values) / len(badness_values)

    def _monitoring_metrics(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        metrics = []
        for metric in item.get("monitoring_metrics") or []:
            if not isinstance(metric, dict):
                continue
            key = str(metric.get("key") or "").strip()
            if not key:
                continue
            metrics.append({
                "key": key,
                "polarity": str(metric.get("polarity") or "higher_is_worse"),
                "weight": max(0.0, self._coerce(metric.get("weight"), 1.0)),
                "legacy_metric": str(metric.get("legacy_metric") or "").strip(),
            })
        return metrics

    def _metric_badness(self, state: Dict[str, Any], metrics: List[Dict[str, Any]]) -> float:
        weighted = 0.0
        total_weight = 0.0
        for metric in metrics:
            key = metric["key"]
            state_key = key if key in state else metric.get("legacy_metric")
            if not state_key or state_key not in state:
                continue
            weight = float(metric.get("weight") or 0.0)
            value = self._coerce(state.get(state_key), 50.0)
            badness = 100.0 - value if metric.get("polarity") == "higher_is_better" else value
            weighted += max(0.0, min(100.0, badness)) * weight
            total_weight += weight
        if total_weight <= 0:
            return self._region_badness(state)
        return weighted / total_weight

    def _region_badness(self, state: Dict[str, Any]) -> float:
        values: List[float] = []
        for key in self._WORSE_WHEN_HIGH:
            if key in state:
                values.append(self._coerce(state.get(key), 50.0))
        for key in self._WORSE_WHEN_LOW:
            if key in state:
                values.append(100.0 - self._coerce(state.get(key), 50.0))
        if not values:
            return 50.0
        return max(0.0, min(100.0, sum(values) / len(values)))

    def _status(self, tension: float, trace: Optional[List[float]] = None) -> str:
        if trace and len(trace) >= 3 and all(value < 35 for value in trace[-3:]):
            return "resolved"
        if tension >= 72:
            return "critical"
        if tension >= 52:
            return "elevated"
        return "watch"

    def _is_turning_point(self, trace: List[float]) -> bool:
        if len(trace) < 3:
            return False
        last_delta = trace[-1] - trace[-2]
        prev_delta = trace[-2] - trace[-3]
        # a turning point = the trend changed sign with a meaningful magnitude
        return (last_delta * prev_delta < 0) and (abs(last_delta) >= 3.0)

    def _select_primary(self, states: List[Dict[str, Any]], previous_bundle: Dict[str, Any], primary_hint: str) -> str:
        active_states = [state for state in states if state.get("status") not in {"resolved", "dormant"}]
        if not active_states:
            return ""
        ranked = sorted(active_states, key=lambda state: state.get("runtime_tension", 0.0), reverse=True)
        leader = ranked[0]
        previous_primary = primary_hint or previous_bundle.get("primary_active_risk_id") or ""
        previous_tension = next(
            (state.get("runtime_tension", 0.0) for state in active_states if state.get("risk_id") == previous_primary),
            -1.0,
        )
        # only switch the dominant risk when the new leader clearly leads, to
        # avoid round-to-round jitter in the headline risk.
        if leader.get("risk_id") != previous_primary and leader.get("runtime_tension", 0.0) >= previous_tension + 5.0:
            return leader.get("risk_id")
        return previous_primary or leader.get("risk_id")

    def _coerce(self, value: Any, default: float, probability: bool = False) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if probability:
            return max(0.0, min(1.0, number))
        return number
