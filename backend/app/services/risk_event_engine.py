"""
Risk event helpers.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from .envfish_models import RiskEvent


def _now() -> str:
    return datetime.now().isoformat()


def _event_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def append_risk_events(path: str, events: Iterable[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for raw in events or []:
            payload = dict(raw or {})
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_risk_events(path: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit is not None and len(events) > limit:
        events = events[-limit:]
    return events


class RiskEventEngine:
    def build_variable_events(
        self,
        variable: Dict[str, Any],
        round_num: int,
        matched_risk_ids: Optional[List[str]] = None,
        created_risk_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        matched_risk_ids = list(matched_risk_ids or [])
        created_risk_ids = list(created_risk_ids or [])
        source_ref = f"variable:{variable.get('variable_id') or 'unknown'}"
        events: List[RiskEvent] = []
        for risk_id in matched_risk_ids:
            events.append(
                RiskEvent(
                    event_id=_event_id("risk_event"),
                    round=round_num,
                    event_type="variable_introduced",
                    risk_id=risk_id,
                    source_ref=source_ref,
                    summary=f"变量 {variable.get('name') or variable.get('variable_id')} 触发该风险刷新。",
                    delta={"variable_type": variable.get("type"), "intensity_0_100": variable.get("intensity_0_100")},
                    evidence_refs=[source_ref],
                )
            )
        for risk_id in created_risk_ids:
            events.append(
                RiskEvent(
                    event_id=_event_id("risk_event"),
                    round=round_num,
                    event_type="created",
                    risk_id=risk_id,
                    source_ref=source_ref,
                    summary=f"变量 {variable.get('name') or variable.get('variable_id')} 派生了新的风险链路。",
                    delta={"category": "variable_triggered"},
                    evidence_refs=[source_ref],
                )
            )
        return [item.to_dict() for item in events]

    def build_reframed_event(
        self,
        risk_id: str,
        round_num: int,
        source_ref: str,
        summary: str,
    ) -> Dict[str, Any]:
        return RiskEvent(
            event_id=_event_id("risk_event"),
            round=round_num,
            event_type="reframed",
            risk_id=risk_id,
            source_ref=source_ref,
            summary=summary,
            evidence_refs=[source_ref] if source_ref else [],
            timestamp=_now(),
        ).to_dict()

    def build_transition_events(
        self,
        previous_bundle: Optional[Dict[str, Any]],
        current_bundle: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        previous_lookup = {
            str(item.get("risk_id") or ""): item
            for item in (previous_bundle or {}).get("risk_states") or []
            if str(item.get("risk_id") or "")
        }
        events: List[Dict[str, Any]] = []
        for current in current_bundle.get("risk_states") or []:
            risk_id = str(current.get("risk_id") or "").strip()
            if not risk_id:
                continue
            previous = previous_lookup.get(risk_id)
            if not previous:
                continue
            previous_score = float(previous.get("severity_score") or 0)
            current_score = float(current.get("severity_score") or 0)
            delta = round(current_score - previous_score, 2)
            event_type = ""
            if delta >= 8:
                event_type = "escalated"
            elif delta <= -8:
                event_type = "cooled"
            elif current.get("trend") == "rising" and delta >= 4:
                event_type = "step_activated"
            if not event_type:
                continue
            events.append(
                RiskEvent(
                    event_id=_event_id("risk_event"),
                    round=int(current_bundle.get("round") or 0),
                    event_type=event_type,
                    risk_id=risk_id,
                    source_ref=f"round:{current_bundle.get('round')}",
                    summary=f"{current.get('title') or risk_id} 风险状态发生变化。",
                    delta={"severity_score": delta},
                    evidence_refs=list(current.get("triggered_by_event_ids") or []),
                    timestamp=_now(),
                ).to_dict()
            )
        return events
