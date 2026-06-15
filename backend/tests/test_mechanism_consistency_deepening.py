"""M7 deepening regression tests.

Two halves of "make the mechanism graph defensible AND let it drive state":

  (1) mechanism_simulation_service._relation_consistency_report — a bounded causal
      consistency pass over validated edges that detects DIRECTION/POLARITY
      contradictions (same ordered endpoint pair asserted positive AND negative)
      and short directed cycles (2-cycles up through length 4). It only counts and
      lists — it never silently merges a contradiction into a clean number.

  (2) run_envfish_simulation._apply_mechanism_propagation — the scenario mechanism
      graph used to be written-then-frozen. It now applies a LIGHT, BOUNDED, signed
      nudge to a target region's pressure dimensions when an edge's endpoints map to
      regions. Guarded behind is_mechanism_runtime + mechanism_propagation_enabled,
      and a graceful no-op when nothing maps.

All deterministic: no LLM, no network.
"""

import importlib.util
import os

from app.services.envfish_models import AgentRelationshipEdge
from app.services.mechanism_simulation_service import MechanismSimulationPlanner

_SPEC = importlib.util.spec_from_file_location(
    "run_envfish_simulation",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "run_envfish_simulation.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
EnvFishRuntime = _MOD.EnvFishRuntime


def _edge(edge_id, src_agent, dst_agent, *, direction, src_region="", dst_region=""):
    return AgentRelationshipEdge(
        edge_id=edge_id,
        source_agent_id=src_agent,
        target_agent_id=dst_agent,
        relation_type="rel",
        source_region_id=src_region,
        target_region_id=dst_region,
        direction=direction,
    )


def test_detects_direction_polarity_contradiction():
    planner = MechanismSimulationPlanner(llm_client=None)
    # Same ordered region pair A->B asserted BOTH positive and negative.
    edges = [
        _edge("e1", 1, 2, direction="positive", src_region="A", dst_region="B"),
        _edge("e2", 3, 4, direction="negative", src_region="A", dst_region="B"),
        # A clean, single-polarity pair — must NOT be a contradiction.
        _edge("e3", 5, 6, direction="positive", src_region="B", dst_region="C"),
    ]
    report = planner._relation_consistency_report(edges)
    assert report["contradiction_count"] == 1
    assert len(report["contradictions"]) == 1
    contradiction = report["contradictions"][0]
    assert contradiction["source"] == "region:A"
    assert contradiction["target"] == "region:B"
    assert "e1" in contradiction["positive_edge_ids"]
    assert "e2" in contradiction["negative_edge_ids"]
    assert "direction_contradiction_present" in report["quality_flags"]


def test_bidirectional_and_conditional_are_not_contradictions():
    planner = MechanismSimulationPlanner(llm_client=None)
    # Sign-ambiguous directions on the same pair carry no defensible sign and
    # must never be flagged as a polarity contradiction.
    edges = [
        _edge("e1", 1, 2, direction="bidirectional", src_region="A", dst_region="B"),
        _edge("e2", 3, 4, direction="conditional", src_region="A", dst_region="B"),
        _edge("e3", 5, 6, direction="positive", src_region="A", dst_region="B"),
    ]
    report = planner._relation_consistency_report(edges)
    assert report["contradiction_count"] == 0
    assert "direction_contradiction_present" not in report["quality_flags"]


def test_detects_two_cycle_and_longer_cycle():
    planner = MechanismSimulationPlanner(llm_client=None)
    # 2-cycle A<->B and a 3-cycle C->D->E->C, all at region level.
    edges = [
        _edge("e1", 1, 2, direction="positive", src_region="A", dst_region="B"),
        _edge("e2", 2, 1, direction="positive", src_region="B", dst_region="A"),
        _edge("e3", 3, 4, direction="positive", src_region="C", dst_region="D"),
        _edge("e4", 4, 5, direction="positive", src_region="D", dst_region="E"),
        _edge("e5", 5, 3, direction="positive", src_region="E", dst_region="C"),
    ]
    report = planner._relation_consistency_report(edges)
    lengths = sorted(c["length"] for c in report["cycles"])
    assert lengths == [2, 3]
    assert report["cycle_count"] == 2
    assert "short_cycle_present" in report["quality_flags"]
    assert "two_cycle_present" in report["quality_flags"]
    # The validated graph surfaces the counts and flags at the top level too.
    graph = planner._validated_relation_graph(edges)
    assert graph["cycle_count"] == 2
    assert graph["contradiction_count"] == 0
    assert "short_cycle_present" in graph["quality_flags"]


def test_acyclic_consistent_graph_is_clean():
    planner = MechanismSimulationPlanner(llm_client=None)
    edges = [
        _edge("e1", 1, 2, direction="positive", src_region="A", dst_region="B"),
        _edge("e2", 2, 3, direction="negative", src_region="B", dst_region="C"),
    ]
    report = planner._relation_consistency_report(edges)
    assert report["contradiction_count"] == 0
    assert report["cycle_count"] == 0
    assert report["quality_flags"] == []


def _propagation_runtime(*, mechanism_runtime=True, enabled=True):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.is_mechanism_runtime = mechanism_runtime
    runtime.mechanism_propagation_enabled = enabled
    runtime.mechanism_propagation_gain = 0.04
    runtime.latest_mechanism_propagation = {}
    runtime._mechanism_region_index = None
    target = {
        "region_id": "rb",
        "name": "深圳湾",
        "state_vector": {
            "exposure_score": 50, "spread_pressure": 50, "panic_level": 50, "economic_stress": 50,
            "ecosystem_integrity": 50, "public_trust": 50, "service_capacity": 50,
            "response_capacity": 50, "livelihood_stability": 50, "vulnerability_score": 50,
        },
    }
    runtime.region_lookup = {"ra": {"region_id": "ra", "name": "茅洲河"}, "rb": target}
    runtime.region_name_lookup = {"茅洲河": "ra", "深圳湾": "rb"}
    # place_<region_id> id convention -> resolves to region "rb".
    runtime.mechanism_graph = {
        "nodes": [
            {"id": "place_ra", "name": "茅洲河", "node_type": "place"},
            {"id": "place_rb", "name": "深圳湾", "node_type": "place"},
        ],
        "edges": [
            {"id": "m1", "source": "place_ra", "target": "place_rb", "direction": "positive", "confidence": 0.8},
        ],
    }
    return runtime, target


def test_positive_mechanism_edge_raises_target_pressure():
    runtime, target = _propagation_runtime()
    before = dict(target["state_vector"])
    summary = runtime._apply_mechanism_propagation(1)
    assert summary["nudged_edges"] == 1
    assert summary["total_nudge"] > 0
    # positive edge raises the target region's pressure dims, but bounded.
    assert target["state_vector"]["spread_pressure"] > before["spread_pressure"]
    assert target["state_vector"]["exposure_score"] > before["exposure_score"]
    assert target["state_vector"]["spread_pressure"] < 100


def test_negative_mechanism_edge_lowers_target_pressure():
    runtime, target = _propagation_runtime()
    runtime.mechanism_graph["edges"][0]["direction"] = "negative"
    before = dict(target["state_vector"])
    runtime._apply_mechanism_propagation(1)
    assert target["state_vector"]["spread_pressure"] < before["spread_pressure"]
    assert target["state_vector"]["panic_level"] < before["panic_level"]


def test_propagation_is_noop_when_disabled_or_legacy():
    # Flag off => untouched.
    runtime, target = _propagation_runtime(enabled=False)
    before = dict(target["state_vector"])
    summary = runtime._apply_mechanism_propagation(1)
    assert summary["nudged_edges"] == 0
    assert target["state_vector"] == before

    # Legacy (non-mechanism) runtime => untouched even if the flag is on.
    runtime2, target2 = _propagation_runtime(mechanism_runtime=False, enabled=True)
    before2 = dict(target2["state_vector"])
    assert runtime2._apply_mechanism_propagation(1)["nudged_edges"] == 0
    assert target2["state_vector"] == before2


def test_propagation_noop_when_no_endpoint_maps_to_region():
    runtime, target = _propagation_runtime()
    # Mechanism endpoints that do NOT resolve to any region -> graceful no-op.
    runtime.mechanism_graph = {
        "nodes": [
            {"id": "proc_1", "name": "传输路径", "node_type": "process"},
            {"id": "proc_2", "name": "受体响应", "node_type": "process"},
        ],
        "edges": [
            {"id": "m1", "source": "proc_1", "target": "proc_2", "direction": "positive", "confidence": 0.8},
        ],
    }
    runtime._mechanism_region_index = None
    before = dict(target["state_vector"])
    summary = runtime._apply_mechanism_propagation(1)
    assert summary["nudged_edges"] == 0
    assert target["state_vector"] == before
