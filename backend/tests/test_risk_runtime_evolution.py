"""M5 regression tests: risk scores must differentiate and evolve from real
per-round region state, and risk_events must fire on status escalation —
fixing the "five risks frozen at 68.4 / risk_events.jsonl empty" problem.
"""

from app.services.risk_event_engine import RiskEventEngine
from app.services.risk_runtime_tracker import RiskRuntimeTracker


def _snapshot(round_num, shenzhen_bad, guangming_good):
    return {
        "round": round_num,
        "regions": [
            {"region_id": "r_bay", "name": "深圳湾", "state_vector": shenzhen_bad},
            {"region_id": "r_gm", "name": "光明", "state_vector": guangming_good},
        ],
    }


def _defs():
    return [
        {"risk_id": "risk_bay", "severity_score": 50.0, "confidence_score": 0.6,
         "status": "watch", "region_scope": ["深圳湾"]},
        {"risk_id": "risk_gm", "severity_score": 50.0, "confidence_score": 0.6,
         "status": "watch", "region_scope": ["光明"]},
    ]


def test_runtime_tension_tracks_region_state_and_differentiates():
    tracker = RiskRuntimeTracker()
    definitions = _defs()
    initial = tracker.build_initial_bundle(definitions, primary_risk_id="risk_bay")

    bad = {"exposure_score": 90, "spread_pressure": 90, "panic_level": 90,
           "vulnerability_score": 90, "ecosystem_integrity": 10, "public_trust": 10}
    good = {"exposure_score": 30, "spread_pressure": 30, "panic_level": 30,
            "vulnerability_score": 30, "ecosystem_integrity": 70, "public_trust": 70}

    refreshed = tracker.refresh(
        risk_definitions=definitions,
        snapshot=_snapshot(1, bad, good),
        previous_bundle=initial,
        primary_hint="risk_bay",
    )
    states = {s["risk_id"]: s for s in refreshed["risk_states"]}

    # tension reflects the affected region's real badness
    assert states["risk_bay"]["runtime_tension"] > 80
    assert states["risk_gm"]["runtime_tension"] < 40
    # severities are no longer identical
    assert states["risk_bay"]["severity_score"] != states["risk_gm"]["severity_score"]
    # status differentiates
    assert states["risk_bay"]["status"] == "critical"
    assert states["risk_gm"]["status"] == "watch"
    # the high-tension risk becomes the dominant/primary risk
    assert refreshed["primary_active_risk_id"] == "risk_bay"

    # escalation event fires (watch -> critical) even without injected variables
    events = RiskEventEngine().build_runtime_events(initial, refreshed)
    bay_events = [e for e in events if e["risk_id"] == "risk_bay"]
    assert any(e["event_type"] == "status_escalation" for e in bay_events)


def test_severity_evolves_across_rounds():
    tracker = RiskRuntimeTracker()
    definitions = _defs()
    bundle = tracker.build_initial_bundle(definitions, primary_risk_id="risk_bay")

    # round 1: bay calm; round 2: bay deteriorates -> severity must move
    calm = {"exposure_score": 40, "spread_pressure": 40, "panic_level": 40, "vulnerability_score": 40}
    spike = {"exposure_score": 95, "spread_pressure": 95, "panic_level": 95, "vulnerability_score": 95}
    other = {"exposure_score": 50, "spread_pressure": 50, "panic_level": 50, "vulnerability_score": 50}

    r1 = tracker.refresh(risk_definitions=definitions, snapshot=_snapshot(1, calm, other), previous_bundle=bundle)
    r2 = tracker.refresh(risk_definitions=definitions, snapshot=_snapshot(2, spike, other), previous_bundle=r1)

    sev1 = next(s["severity_score"] for s in r1["risk_states"] if s["risk_id"] == "risk_bay")
    sev2 = next(s["severity_score"] for s in r2["risk_states"] if s["risk_id"] == "risk_bay")
    assert sev2 > sev1  # severity tracks the deteriorating state
    trace = next(s["tension_trace"] for s in r2["risk_states"] if s["risk_id"] == "risk_bay")
    assert len(trace) >= 3  # initial + r1 + r2 accumulated
