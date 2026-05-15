from datetime import datetime
from typing import Any, Dict, List


class RiskEventEngine:
    def build_transition_events(self, previous_bundle: Dict[str, Any], next_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
        previous_primary = (previous_bundle or {}).get("primary_active_risk_id")
        next_primary = (next_bundle or {}).get("primary_active_risk_id")
        if previous_primary and next_primary and previous_primary != next_primary:
            return [self.build_reframed_event(next_primary, int(next_bundle.get("round") or 0), "runtime:transition", "主风险链路发生切换。")]
        return []

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
