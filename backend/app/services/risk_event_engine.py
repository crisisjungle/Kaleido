from datetime import datetime
from typing import Any, Dict, List


class RiskEventEngine:
    def build_transition_events(self, previous_bundle: Dict[str, Any], next_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        previous_primary = (previous_bundle or {}).get("primary_active_risk_id")
        next_primary = (next_bundle or {}).get("primary_active_risk_id")
        if previous_primary and next_primary and previous_primary != next_primary:
            return [self.build_reframed_event(next_primary, int(next_bundle.get("round") or 0), "runtime:transition", "主风险链路发生切换。")]
        return []

    _STATUS_RANK = {"watch": 0, "elevated": 1, "critical": 2}

    def build_runtime_events(self, previous_bundle: Dict[str, Any], next_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Emit events when a risk's runtime status escalates/de-escalates or a
        turning point appears. This is what makes risk_events non-empty even
        without injected variables — events now track real state evolution."""
        events: List[Dict[str, Any]] = []
        round_num = int((next_bundle or {}).get("round") or 0)
        prev_states = {
            state.get("risk_id"): state
            for state in (previous_bundle or {}).get("risk_states") or []
            if isinstance(state, dict)
        }
        for state in (next_bundle or {}).get("risk_states") or []:
            if not isinstance(state, dict):
                continue
            risk_id = state.get("risk_id")
            prev = prev_states.get(risk_id) or {}
            prev_status = prev.get("status") or "watch"
            new_status = state.get("status") or "watch"
            tension = state.get("runtime_tension")
            new_rank = self._STATUS_RANK.get(new_status, 0)
            prev_rank = self._STATUS_RANK.get(prev_status, 0)
            if new_rank > prev_rank:
                events.append(
                    {
                        "event_id": f"risk_event_{risk_id}_{round_num}_escalation",
                        "risk_id": risk_id,
                        "round": round_num,
                        "event_type": "status_escalation",
                        "from_status": prev_status,
                        "to_status": new_status,
                        "runtime_tension": tension,
                        "summary": f"风险张力升级：{prev_status}→{new_status}（张力 {tension}）。",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            elif new_rank < prev_rank:
                events.append(
                    {
                        "event_id": f"risk_event_{risk_id}_{round_num}_deescalation",
                        "risk_id": risk_id,
                        "round": round_num,
                        "event_type": "status_deescalation",
                        "from_status": prev_status,
                        "to_status": new_status,
                        "runtime_tension": tension,
                        "summary": f"风险张力回落：{prev_status}→{new_status}（张力 {tension}）。",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            if state.get("turning_point") and not prev.get("turning_point"):
                events.append(
                    {
                        "event_id": f"risk_event_{risk_id}_{round_num}_turning",
                        "risk_id": risk_id,
                        "round": round_num,
                        "event_type": "turning_point",
                        "runtime_tension": tension,
                        "summary": f"风险出现拐点（当前张力 {tension}）。",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
        return events

    def build_variable_events(self, variable: Dict[str, Any], round_num: int, matched_risk_ids=None, created_risk_ids=None) -> List[Dict[str, Any]]:
        ids = list(created_risk_ids or matched_risk_ids or [])
        return [
            {
                "event_id": f"risk_event_{round_num}_{index}",
                "risk_id": risk_id,
                "round": round_num,
                "event_type": "variable_injected",
                "summary": variable.get("name") or "变量已注入",
                "timestamp": datetime.now().isoformat(),
            }
            for index, risk_id in enumerate(ids)
        ]

    def build_reframed_event(self, risk_id: str, round_num: int, source_ref: str, summary: str) -> Dict[str, Any]:
        return {
            "event_id": f"risk_event_{risk_id}_{round_num}",
            "risk_id": risk_id,
            "round": round_num,
            "event_type": "reframed",
            "source_ref": source_ref,
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
        }
