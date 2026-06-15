"""
Phase-A honest-visualization tests for the M10 backend-half rebuild.

These tests construct payloads deterministically (no live LLM / no network) and
assert the additive honesty/semantic keys introduced in:
  - simulation_realtime_graph: edge_layer separating spatial_fact vs causal
  - simulation_map_projection: is_geographic=false for synthetic placement
  - simulation_animation_service: frame value/delta bound to real round state
"""

import json
import os
import tempfile

from app.services.simulation_animation_service import SimulationAnimationService
from app.services.simulation_map_projection import SimulationMapProjectionBuilder
from app.services.simulation_realtime_graph import SimulationRealtimeGraphBuilder


def _write_json(sim_dir, name, payload):
    with open(os.path.join(sim_dir, name), "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def test_realtime_edges_carry_edge_layer_separating_spatial_vs_causal():
    with tempfile.TemporaryDirectory() as sim_dir:
        # Two adjacent regions (spatial skeleton), one agent anchored to a region
        # (spatial), and one inferred agent->region influence (causal) plus a
        # dynamic edge (causal).
        _write_json(
            sim_dir,
            "region_graph_snapshot.json",
            [
                {"region_id": "R1", "name": "Region One", "neighbors": ["R2"]},
                {"region_id": "R2", "name": "Region Two", "neighbors": ["R1"]},
            ],
        )
        _write_json(
            sim_dir,
            "profiles_full.json",
            [
                {
                    "agent_id": 1,
                    "name": "Agent One",
                    "home_region_id": "R1",
                    "influenced_regions": ["R2"],
                }
            ],
        )
        _write_json(
            sim_dir,
            "latest_round_snapshot.json",
            {
                "dynamic_edges": [
                    {
                        "source_agent_id": 1,
                        "target_agent_id": 1,
                        "edge_id": "dyn-1",
                        "edge_type": "affects",
                        "interaction_channel": "social",
                    }
                ]
            },
        )

        graph = SimulationRealtimeGraphBuilder(sim_dir).build()
        edges_by_type = {edge["fact_type"]: edge for edge in graph["edges"]}

        # Every edge must carry the additive edge_layer tag.
        assert all("edge_layer" in edge for edge in graph["edges"])

        # Spatial skeleton edges.
        assert edges_by_type["region_neighbor"]["edge_layer"] == "spatial_fact"
        assert edges_by_type["agent_anchor"]["edge_layer"] == "spatial_fact"
        # Causal coupling edges.
        assert edges_by_type["agent_influence"]["edge_layer"] == "causal"
        assert edges_by_type["dynamic_edge"]["edge_layer"] == "causal"

        # Channel is surfaced where present (dynamic edge had interaction_channel).
        assert edges_by_type["dynamic_edge"].get("channel") == "social"

        # Meta exposes the split so the frontend can separate skeleton from coupling.
        assert graph["meta"]["spatial_fact_edge_count"] >= 2
        assert graph["meta"]["causal_edge_count"] >= 2

        # Epistemic honesty: spatial facts observed, causal inferred (by default).
        assert edges_by_type["region_neighbor"]["epistemic"] == "observed"
        assert edges_by_type["agent_influence"]["epistemic"] == "inferred"


def test_projection_marks_synthetic_placement_non_geographic():
    # No map seed -> no anchor context -> radial/hash placement is synthetic.
    graph_data = {
        "nodes": [
            {
                "uuid": "region::R1",
                "name": "Region One",
                "labels": ["Entity", "Region"],
                "attributes": {"region_id": "R1", "region_type": "urban"},
            },
            {
                "uuid": "agent::1",
                "name": "Agent One",
                "labels": ["Entity"],
                "attributes": {"agent_id": 1, "home_region_id": "R1"},
            },
        ],
        "edges": [],
    }

    projection = SimulationMapProjectionBuilder(
        sim_dir="/tmp/does-not-exist",
        simulation_id="sim-test",
        map_seed_id=None,
        source_mode="graph",
    ).build(graph_data, key_edges_only=False)

    # Top-level honesty flag.
    assert projection["geographic_grounding"] == "synthetic"
    assert projection["meta"]["synthetic_node_count"] == len(projection["nodes"])
    assert projection["meta"]["geographic_node_count"] == 0

    # Every synthetic node is flagged honestly so the frontend can show "非地理示意".
    for node in projection["nodes"]:
        assert node["is_geographic"] is False
        assert node["attributes"]["is_geographic"] is False
        assert node["attributes"]["placement"] == "synthetic"


def test_animation_frame_value_delta_reflect_two_round_state_difference():
    # Build the service without touching SimulationManager / disk.
    service = SimulationAnimationService.__new__(SimulationAnimationService)

    layout_nodes = [
        {"id": "region::R1", "name": "Region One", "kind": "region", "attributes": {"region_id": "R1"}},
        {"id": "agent::1", "name": "Agent One", "kind": "agent", "attributes": {"agent_id": 1}},
    ]

    round1_snapshot = {
        "regions": [{"region_id": "R1", "vulnerability_score": 60.0}],
        "agents": [{"agent_id": 1, "state_vector": {"vulnerability_score": 40.0}}],
    }
    round2_snapshot = {
        "regions": [{"region_id": "R1", "vulnerability_score": 67.0}],
        "agents": [{"agent_id": 1, "state_vector": {"vulnerability_score": 38.0}}],
    }

    value_map_r1 = service._node_values_from_snapshot(round1_snapshot)
    value_map_r2 = service._node_values_from_snapshot(round2_snapshot)

    # Real values were extracted from the snapshots.
    assert value_map_r1["region::R1"] == 60.0
    assert value_map_r2["region::R1"] == 67.0

    frame = service._build_frame(
        round_num=2,
        timestamp="",
        snapshot=round2_snapshot,
        interactions=[],
        risk_events=[],
        reasoning=[],
        layout_nodes=layout_nodes,
        layout_edges=[],
        node_first_seen={"region::R1": 0, "agent::1": 1},
        edge_first_seen={},
        edge_last_active={},
        map_projection={"center": {}, "layers": []},
        value_map=value_map_r2,
        prev_value_map=value_map_r1,
    )

    node_states = {item["id"]: item for item in frame["node_states"]}

    # Region rose 60 -> 67: value/delta carry the REAL state difference, and the
    # status derives from the real positive drift (not the reveal order).
    region_state = node_states["region::R1"]
    assert region_state["value"] == 67.0
    assert region_state["delta"] == 7.0
    assert region_state["state_status"] == "rising"

    # Agent fell 40 -> 38: delta is negative, status is falling.
    agent_state = node_states["agent::1"]
    assert agent_state["value"] == 38.0
    assert agent_state["delta"] == -2.0
    assert agent_state["state_status"] == "falling"
