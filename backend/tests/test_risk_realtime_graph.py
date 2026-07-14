import json

from app.services.simulation_map_projection import SimulationMapProjectionBuilder
from app.services.simulation_realtime_graph import SimulationRealtimeGraphBuilder


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_risk_mechanism_references_exist_in_graph_but_are_not_synthetically_placed_on_map(tmp_path):
    _write_json(
        tmp_path / "region_graph_snapshot.json",
        [{"region_id": "coast", "name": "滨海区", "lat": 22.5, "lon": 114.1}],
    )
    _write_json(
        tmp_path / "profiles_full.json",
        [
            {"agent_id": 1, "name": "监测员", "primary_region": "coast", "lat": 22.51, "lon": 114.11},
            {"agent_id": 2, "name": "响应员", "primary_region": "coast", "lat": 22.52, "lon": 114.12},
        ],
    )
    _write_json(
        tmp_path / "agent_relationship_graph.json",
        [
            {
                "edge_id": "agent_edge",
                "source_agent_id": 1,
                "target_agent_id": 2,
                "relation_type": "reports_to",
                "mechanism": "监测员向响应员上报污染信号",
                "mechanism_edge_ids": ["mechanism_edge_1"],
                "epistemic_status": "observed",
            }
        ],
    )
    _write_json(
        tmp_path / "mechanism_graph.json",
        {
            "nodes": [
                {"id": "mechanism_source", "name": "污染释放源", "node_type": "source"},
                {"id": "mechanism_receptor", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "mechanism_edge_1",
                    "source": "mechanism_source",
                    "target": "mechanism_receptor",
                    "relation_label": "污染暴露",
                    "mechanism": "污染物经水体作用于居民",
                    "evidence": ["滨海区监测记录"],
                }
            ],
        },
    )

    graph = SimulationRealtimeGraphBuilder(str(tmp_path)).build()
    node_ids = {item["uuid"] for item in graph["nodes"]}
    edge_ids = {item["uuid"] for item in graph["edges"]}
    assert {"mechanism_source", "mechanism_receptor"} <= node_ids
    assert "mechanism_edge_1" in edge_ids
    assert graph["meta"]["mechanism_node_count"] == 2
    assert graph["meta"]["mechanism_edge_count"] == 1
    mechanism_edge = next(item for item in graph["edges"] if item["uuid"] == "mechanism_edge_1")
    assert mechanism_edge["epistemic"] == "observed"

    relationship_edge = next(item for item in graph["edges"] if item["uuid"] == "agent_edge")
    assert relationship_edge["attributes"]["mechanism_edge_ids"] == ["mechanism_edge_1"]

    projection = SimulationMapProjectionBuilder(
        sim_dir=str(tmp_path),
        simulation_id="risk_graph_test",
        source_mode="graph",
    ).build(graph, key_edges_only=False)
    map_node_ids = {item["uuid"] for item in projection["nodes"]}
    map_edge_ids = {item["uuid"] for item in projection["edges"]}
    assert "mechanism_source" not in map_node_ids
    assert "mechanism_receptor" not in map_node_ids
    assert "mechanism_edge_1" not in map_edge_ids
    assert {"region::coast", "agent::1", "agent::2"} <= map_node_ids
