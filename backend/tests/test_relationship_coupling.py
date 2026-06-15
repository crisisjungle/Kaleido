"""M8 regression test: active dynamic edges must DRIVE region state (a strong
relationship pulls the target region toward the source region's stressed state),
instead of being a read-only decorative layer.
"""

import importlib.util
import os

_SPEC = importlib.util.spec_from_file_location(
    "run_envfish_simulation",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "run_envfish_simulation.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
EnvFishRuntime = _MOD.EnvFishRuntime


def _runtime(enabled=True):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.relationship_coupling_enabled = enabled
    runtime.relationship_coupling_gain = 0.06
    runtime.latest_relationship_coupling = {}
    runtime._record_dynamic_edge_event = lambda *a, **k: None
    source = {
        "region_id": "A",
        "state_vector": {
            "exposure_score": 90, "spread_pressure": 90, "panic_level": 90, "economic_stress": 80,
            "ecosystem_integrity": 20, "public_trust": 20, "service_capacity": 30,
            "response_capacity": 30, "livelihood_stability": 30, "vulnerability_score": 80,
        },
    }
    target = {
        "region_id": "B",
        "state_vector": {
            "exposure_score": 30, "spread_pressure": 30, "panic_level": 30, "economic_stress": 30,
            "ecosystem_integrity": 80, "public_trust": 80, "service_capacity": 80,
            "response_capacity": 80, "livelihood_stability": 80, "vulnerability_score": 30,
        },
    }
    runtime.region_lookup = {"A": source, "B": target}
    runtime.dynamic_edge_lookup = {
        "e1": {
            "edge_id": "e1", "status": "active", "strength": 0.8,
            "source_region_id": "A", "target_region_id": "B", "interaction_channel": "water_flow",
        }
    }
    return runtime, source, target


def test_active_edge_transmits_stress_to_target_region():
    runtime, _source, target = _runtime(enabled=True)
    before = dict(target["state_vector"])

    summary = runtime._apply_relationship_coupling(1)

    assert summary["coupled_edges"] == 1
    assert summary["total_transfer"] > 0
    # stressed upstream pushes the target's pressure dimensions UP
    assert target["state_vector"]["exposure_score"] > before["exposure_score"]
    assert target["state_vector"]["spread_pressure"] > before["spread_pressure"]
    # a degraded upstream erodes the target's protective dimensions DOWN
    assert target["state_vector"]["public_trust"] < before["public_trust"]
    # but it is bounded, not a teleport to the source value
    assert target["state_vector"]["exposure_score"] < 90


def test_coupling_can_be_disabled():
    runtime, _source, target = _runtime(enabled=False)
    before = dict(target["state_vector"])
    summary = runtime._apply_relationship_coupling(1)
    assert summary["coupled_edges"] == 0
    assert target["state_vector"] == before


def test_weak_or_cooling_edges_do_not_couple():
    runtime, _source, target = _runtime(enabled=True)
    runtime.dynamic_edge_lookup["e1"]["strength"] = 0.1  # below 0.25 threshold
    before = dict(target["state_vector"])
    summary = runtime._apply_relationship_coupling(1)
    assert summary["coupled_edges"] == 0
    assert target["state_vector"] == before


def _promo_runtime():
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.edge_promotion_enabled = True
    runtime.total_rounds = 10
    runtime.default_dynamic_ttl = 3
    runtime._record_dynamic_edge_event = lambda *a, **k: None
    return runtime


def test_reconfirmed_strong_edge_promotes_to_structural():
    runtime = _promo_runtime()
    edge = {"edge_id": "e1", "layer": "dynamic", "reconfirm_count": 2,
            "strength": 0.6, "confidence": 0.65, "ttl_rounds": 3}
    assert runtime._maybe_promote_edge(edge, 3) is True
    assert edge["layer"] == "structural"
    assert edge["status"] == "stable"
    assert edge["origin"] == "runtime_promoted"


def test_weak_or_single_confirm_edge_not_promoted():
    runtime = _promo_runtime()
    edge = {"edge_id": "e2", "layer": "dynamic", "reconfirm_count": 1,
            "strength": 0.4, "confidence": 0.5, "ttl_rounds": 3}
    assert runtime._maybe_promote_edge(edge, 3) is False
    assert edge["layer"] == "dynamic"


def _loop_runtime(edges):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.region_lookup = {
        "A": {"region_id": "A", "name": "甲区"},
        "B": {"region_id": "B", "name": "乙区"},
        "C": {"region_id": "C", "name": "丙区"},
    }
    runtime.dynamic_edge_lookup = edges
    return runtime


def test_detects_reinforcing_loop():
    edges = {
        "e1": {"status": "active", "source_region_id": "A", "target_region_id": "B", "interaction_channel": "water_flow"},
        "e2": {"status": "active", "source_region_id": "B", "target_region_id": "C", "interaction_channel": "ecological"},
        "e3": {"status": "active", "source_region_id": "C", "target_region_id": "A", "interaction_channel": "social"},
    }
    loops = _loop_runtime(edges)._detect_feedback_loops()
    assert len(loops) == 1
    assert loops[0]["length"] == 3
    assert set(loops[0]["regions"]) == {"A", "B", "C"}
    assert loops[0]["loop_type"] == "reinforcing"


def test_governance_channel_makes_loop_balancing():
    edges = {
        "e1": {"status": "active", "source_region_id": "A", "target_region_id": "B", "interaction_channel": "water_flow"},
        "e2": {"status": "active", "source_region_id": "B", "target_region_id": "A", "interaction_channel": "governance"},
    }
    loops = _loop_runtime(edges)._detect_feedback_loops()
    assert len(loops) == 1
    assert loops[0]["loop_type"] == "balancing"


def test_no_loop_when_acyclic():
    edges = {
        "e1": {"status": "active", "source_region_id": "A", "target_region_id": "B", "interaction_channel": "water_flow"},
        "e2": {"status": "active", "source_region_id": "B", "target_region_id": "C", "interaction_channel": "social"},
    }
    assert _loop_runtime(edges)._detect_feedback_loops() == []


def test_dormant_edge_keeps_history_and_drops_from_active_index():
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime._record_dynamic_edge_event = lambda *a, **k: None
    edge = {"edge_id": "e1", "source_agent_id": 1, "status": "active", "strength": 0.05}
    runtime._mark_edge_dormant(edge, 4, "decayed")
    assert edge["status"] == "dormant"
    assert edge["dormant_since_round"] == 4
    assert edge["history"][-1]["event"] == "dormant"
    runtime.dynamic_edge_lookup = {"e1": edge}
    runtime._rebuild_dynamic_edge_index()
    assert runtime.dynamic_edges_by_source.get(1, []) == []
