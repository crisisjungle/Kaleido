from typing import Any, Dict, List


class RiskRuntimeTracker:
    def build_initial_bundle(self, risk_definitions: List[Dict[str, Any]] | None = None, primary_risk_id: str = "", source_risk_objects=None) -> Dict[str, Any]:
        definitions = risk_definitions or []
        primary = primary_risk_id or (definitions[0].get("risk_id") if definitions else "")
        return {
            "round": 0,
            "primary_active_risk_id": primary,
            "pinned_risk_ids": [],
            "risk_states": [
                {
                    "risk_id": item.get("risk_id") or item.get("risk_object_id"),
                    "status": item.get("status") or "watch",
                    "severity_score": item.get("severity_score") or 0.5,
                    "confidence_score": item.get("confidence_score") or 0.5,
                }
                for item in definitions
                if isinstance(item, dict)
            ],
        }

    def refresh(self, risk_definitions=None, snapshot=None, previous_bundle=None, primary_hint: str = "", pinned_risk_ids=None, refresh_reason: str = "round_refresh", **kwargs) -> Dict[str, Any]:
        previous_bundle = previous_bundle or {}
        bundle = self.build_initial_bundle(risk_definitions or [], primary_hint or previous_bundle.get("primary_active_risk_id") or "")
        bundle["round"] = (snapshot or {}).get("round") or previous_bundle.get("round") or 0
        bundle["pinned_risk_ids"] = pinned_risk_ids or previous_bundle.get("pinned_risk_ids") or []
        bundle["refresh_reason"] = refresh_reason
        return bundle
