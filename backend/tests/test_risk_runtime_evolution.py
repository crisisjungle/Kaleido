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


def test_v2_uses_only_each_risks_monitoring_metrics_and_referenced_regions():
    tracker = RiskRuntimeTracker()
    definitions = [
        {
            "risk_id": "exposure_only",
            "severity_score": 50,
            "region_scope": ["深圳湾"],
            "monitoring_metrics": [
                {"key": "exposure_score", "polarity": "higher_is_worse", "weight": 1.0}
            ],
        },
        {
            "risk_id": "trust_only",
            "severity_score": 50,
            "region_scope": ["深圳湾"],
            "monitoring_metrics": [
                {"key": "public_trust", "polarity": "higher_is_better", "weight": 1.0}
            ],
        },
    ]
    snapshot = {
        "round": 1,
        "regions": [
            {
                "region_id": "r_bay",
                "name": "深圳湾",
                "state_vector": {"exposure_score": 20, "public_trust": 10, "panic_level": 100},
            },
            {
                "region_id": "other",
                "name": "其他区域",
                "state_vector": {"exposure_score": 100, "public_trust": 100},
            },
        ],
    }
    result = tracker.refresh(
        risk_definitions=definitions,
        snapshot=snapshot,
        previous_bundle=tracker.build_initial_bundle(definitions),
    )
    states = {item["risk_id"]: item for item in result["risk_states"]}
    assert states["exposure_only"]["runtime_tension"] == 20
    assert states["trust_only"]["runtime_tension"] == 90


def test_v2_initial_status_is_threshold_based_and_region_aliases_are_not_double_weighted():
    tracker = RiskRuntimeTracker()
    definition = {
        "risk_contract_version": 2,
        "risk_id": "risk_alias",
        "status": "tracked",
        "severity_score": 80,
        "region_scope": ["甲区", "乙区"],
        "scope": {"regions": [{"region_id": "region_a", "region_name": "甲区"}]},
        "monitoring_metrics": [
            {"key": "exposure_score", "polarity": "higher_is_worse", "weight": 1.0}
        ],
    }
    initial = tracker.build_initial_bundle([definition])
    assert initial["risk_states"][0]["status"] == "critical"

    refreshed = tracker.refresh(
        risk_definitions=[definition],
        snapshot={
            "round": 1,
            "regions": [
                {"region_id": "region_a", "name": "甲区", "state_vector": {"exposure_score": 100}},
                {"region_id": "region_b", "name": "乙区", "state_vector": {"exposure_score": 0}},
            ],
        },
        previous_bundle=initial,
    )
    assert refreshed["risk_states"][0]["runtime_tension"] == 50


def test_scenario_state_metric_falls_back_to_its_declared_legacy_metric():
    tracker = RiskRuntimeTracker()
    definitions = [
        {
            "risk_id": "scenario_metric",
            "severity_score": 50,
            "region_scope": ["深圳湾"],
            "monitoring_metrics": [
                {
                    "key": "coastal_access_pressure",
                    "legacy_metric": "spread_pressure",
                    "polarity": "higher_is_worse",
                    "weight": 1.0,
                }
            ],
        }
    ]
    result = tracker.refresh(
        risk_definitions=definitions,
        snapshot={
            "round": 1,
            "regions": [
                {
                    "region_id": "bay",
                    "name": "深圳湾",
                    "state_vector": {"spread_pressure": 74},
                }
            ],
        },
        previous_bundle=tracker.build_initial_bundle(definitions),
    )
    assert result["risk_states"][0]["runtime_tension"] == 74


def test_three_low_rounds_resolve_risk_and_status_events_are_chinese():
    tracker = RiskRuntimeTracker()
    definition = {
        "risk_id": "risk_resolve",
        "severity_score": 70,
        "region_scope": ["深圳湾"],
        "monitoring_metrics": [
            {"key": "exposure_score", "polarity": "higher_is_worse", "weight": 1.0}
        ],
    }
    bundle = tracker.build_initial_bundle([definition], primary_risk_id="risk_resolve")
    for round_num in range(1, 4):
        previous = bundle
        bundle = tracker.refresh(
            risk_definitions=[definition],
            snapshot={
                "round": round_num,
                "regions": [{"region_id": "bay", "name": "深圳湾", "state_vector": {"exposure_score": 20}}],
            },
            previous_bundle=bundle,
            primary_hint="risk_resolve",
        )
    assert bundle["risk_states"][0]["status"] == "resolved"
    assert bundle["primary_active_risk_id"] == ""
    events = RiskEventEngine().build_runtime_events(previous, bundle)
    assert events[0]["event_type"] == "status_deescalation"
    assert "已解除" in events[0]["summary"]
    assert "resolved" not in events[0]["summary"]


def test_primary_risk_switch_requires_five_point_lead_and_emits_switch_event():
    tracker = RiskRuntimeTracker()
    definitions = [
        {
            "risk_id": "risk_a",
            "severity_score": 55,
            "region_scope": ["甲区"],
            "monitoring_metrics": [{"key": "exposure_score", "polarity": "higher_is_worse", "weight": 1.0}],
        },
        {
            "risk_id": "risk_b",
            "severity_score": 55,
            "region_scope": ["乙区"],
            "monitoring_metrics": [{"key": "exposure_score", "polarity": "higher_is_worse", "weight": 1.0}],
        },
    ]
    initial = tracker.build_initial_bundle(definitions, primary_risk_id="risk_a")
    close = tracker.refresh(
        risk_definitions=definitions,
        snapshot={
            "round": 1,
            "regions": [
                {"region_id": "a", "name": "甲区", "state_vector": {"exposure_score": 60}},
                {"region_id": "b", "name": "乙区", "state_vector": {"exposure_score": 64}},
            ],
        },
        previous_bundle=initial,
        primary_hint="risk_a",
    )
    assert close["primary_active_risk_id"] == "risk_a"

    switched = tracker.refresh(
        risk_definitions=definitions,
        snapshot={
            "round": 2,
            "regions": [
                {"region_id": "a", "name": "甲区", "state_vector": {"exposure_score": 60}},
                {"region_id": "b", "name": "乙区", "state_vector": {"exposure_score": 66}},
            ],
        },
        previous_bundle=close,
        primary_hint="risk_a",
    )
    assert switched["primary_active_risk_id"] == "risk_b"
    events = RiskEventEngine().build_transition_events(close, switched)
    assert events[0]["event_type"] == "primary_risk_switched"
    assert events[0]["from_risk_id"] == "risk_a"
    assert events[0]["to_risk_id"] == "risk_b"
