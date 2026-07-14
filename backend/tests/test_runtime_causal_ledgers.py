import json

from scripts.run_envfish_simulation import EnvFishRuntime


def _spread_runtime():
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.config = {"simulation_id": "causal_spread_test"}
    runtime.template_rules = {
        "default_decay": 0.8,
        "default_lag_rounds": 1,
        "default_persistence": 60,
        "max_neighbor_spread": 2,
    }
    runtime.region_graph = [
        {
            "region_id": region_id,
            "name": name,
            "state_vector": {
                "exposure_score": 0,
                "spread_pressure": 0,
                "ecosystem_integrity": 100,
            },
        }
        for region_id, name in [("A", "甲区"), ("B", "乙区"), ("C", "丙区")]
    ]
    runtime.region_lookup = {item["region_id"]: item for item in runtime.region_graph}
    runtime.transport_edges_by_source = {
        "A": [
            {
                "edge_id": "transport_A_B",
                "source_region_id": "A",
                "target_region_id": "B",
                "channel_type": "water_flow",
                "travel_time_rounds": 1,
                "attenuation_rate": 0.1,
                "confidence": 0.8,
                "rationale": "沿水流通道传播。",
            }
        ],
        "B": [
            {
                "edge_id": "transport_B_C",
                "source_region_id": "B",
                "target_region_id": "C",
                "channel_type": "water_flow",
                "travel_time_rounds": 1,
                "attenuation_rate": 0.1,
                "confidence": 0.75,
                "rationale": "沿下游水流继续传播。",
            }
        ],
    }
    return runtime


def test_fallback_spread_builds_stable_proven_multihop_chain():
    runtime = _spread_runtime()
    variable = {
        "variable_id": "storm_release",
        "name": "污染物释放",
        "target_regions": ["A"],
        "intensity_0_100": 80,
    }

    first = runtime._fallback_diffusion(1, [variable], [])["transfers"]
    root = next(item for item in first if item["source_region"] == item["target_region"])
    first_hop = next(item for item in first if item["target_region"] == "B")

    assert root["root_event_id"] == root["event_id"]
    assert root["parent_event_ids"] == []
    assert root["hop"] == 0
    assert first_hop["root_event_id"] == root["event_id"]
    assert first_hop["parent_event_ids"] == [root["event_id"]]
    assert first_hop["hop"] == 1

    second = runtime._fallback_diffusion(2, [], [first_hop])["transfers"]
    second_hop = next(item for item in second if item["target_region"] == "C")
    assert second_hop["root_event_id"] == root["event_id"]
    assert second_hop["parent_event_ids"] == [first_hop["event_id"]]
    assert second_hop["hop"] == 2

    replay = runtime._fallback_diffusion(2, [], [first_hop])["transfers"][0]
    assert replay["event_id"] == second_hop["event_id"]

    validated = runtime._validate_transfer(second_hop, [])
    assert validated is not None
    assert validated["event_id"] == second_hop["event_id"]
    assert validated["parent_event_ids"] == [first_hop["event_id"]]
    assert validated["root_event_id"] == root["event_id"]
    assert validated["hop"] == 2


def test_applied_spread_ledger_keeps_the_fallback_chain(tmp_path):
    runtime = _spread_runtime()
    runtime.pending_transfers = []
    runtime.llm = None
    runtime.propagation_channels = []
    runtime.propagation_channels_by_id = {}
    runtime.propagation_channels_enabled = False
    runtime.propagation_channel_gain = 0.5
    runtime.spread_log = str(tmp_path / "spread_event_ledger.jsonl")
    runtime._now = lambda: "2026-07-14T00:00:00"
    runtime._write_action = lambda **kwargs: None
    variable = {
        "variable_id": "storm_release",
        "name": "污染物释放",
        "target_regions": ["A"],
        "intensity_0_100": 80,
    }

    runtime._environmental_diffusion_update(1, [variable])
    runtime._environmental_diffusion_update(2, [])
    runtime._environmental_diffusion_update(3, [])

    records = _read_jsonl(tmp_path / "spread_event_ledger.jsonl")
    root = next(item for item in records if item["source_region"] == item["target_region"])
    first_hop = next(item for item in records if item["target_region"] == "B")
    second_hop = next(item for item in records if item["target_region"] == "C")
    assert [root["hop"], first_hop["hop"], second_hop["hop"]] == [0, 1, 2]
    assert root["path_edge_ids"] == []
    assert first_hop["path_edge_ids"] == ["transport_A_B"]
    assert second_hop["path_edge_ids"] == ["transport_B_C"]
    assert all(item["related_edge_ids"] == [] for item in (root, first_hop, second_hop))
    assert first_hop["parent_event_ids"] == [root["event_id"]]
    assert second_hop["parent_event_ids"] == [first_hop["event_id"]]
    assert {item["root_event_id"] for item in (root, first_hop, second_hop)} == {
        root["event_id"]
    }


def _dynamic_runtime(tmp_path, *, edge):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.config = {"simulation_id": "causal_dynamic_test"}
    runtime.agent_plan_source = "agent_v2"
    runtime.scenario_version_ref = {"artifact_id": "scenario_v2"}
    runtime.dynamic_edge_log = str(tmp_path / "dynamic_edge_ledger.jsonl")
    runtime.relationship_event_log = str(tmp_path / "relationship_event_ledger.jsonl")
    runtime.relationship_state_path = str(tmp_path / "latest_relationship_states.json")
    runtime.relationship_states = []
    runtime.relationship_state_lookup = {}
    runtime.dynamic_edge_lookup = {edge["edge_id"]: edge}
    runtime.default_dynamic_ttl = 3
    runtime.default_dynamic_decay = 0.2
    runtime.edge_promotion_enabled = True
    runtime.total_rounds = 10
    runtime._now = lambda: "2026-07-14T00:00:00"
    runtime._rebuild_dynamic_edge_index()
    return runtime


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_interaction_activation_promotes_through_explicit_dynamic_chain(tmp_path):
    edge = {
        "edge_id": "dynamic::1::2::response_bridge",
        "source_agent_id": 1,
        "target_agent_id": 2,
        "source_region_id": "A",
        "target_region_id": "B",
        "edge_type": "response_bridge",
        "interaction_channel": "information",
        "layer": "dynamic",
        "status": "active",
        "strength": 0.56,
        "confidence": 0.61,
        "ttl_rounds": 3,
        "reconfirm_count": 1,
    }
    runtime = _dynamic_runtime(tmp_path, edge=edge)
    interaction_event_id = "agent_interaction_event_proven"

    runtime._activate_dynamic_edge(
        edge["edge_id"],
        3,
        causal_context={
            "root_event_id": interaction_event_id,
            "parent_event_ids": [interaction_event_id],
            "hop": 1,
        },
    )

    dynamic_events = _read_jsonl(tmp_path / "dynamic_edge_ledger.jsonl")
    activated, promoted = dynamic_events
    assert all(item["path_edge_ids"] == [edge["edge_id"]] for item in dynamic_events)
    assert all(item["related_edge_ids"] == [] for item in dynamic_events)
    assert [item["event_type"] for item in dynamic_events] == ["activated", "promoted"]
    assert activated["root_event_id"] == interaction_event_id
    assert activated["parent_event_ids"] == [interaction_event_id]
    assert activated["hop"] == 1
    assert promoted["root_event_id"] == interaction_event_id
    assert promoted["parent_event_ids"] == [activated["event_id"]]
    assert promoted["hop"] == 2

    relationship_events = _read_jsonl(tmp_path / "relationship_event_ledger.jsonl")
    updated_relationship, promoted_relationship = relationship_events
    assert all(item["path_edge_ids"] == [edge["edge_id"]] for item in relationship_events)
    assert all(item["related_edge_ids"] == [] for item in relationship_events)
    assert updated_relationship["event_type"] == "relationship_updated"
    assert updated_relationship["parent_event_ids"] == [activated["event_id"]]
    assert updated_relationship["root_event_id"] == interaction_event_id
    assert updated_relationship["hop"] == 2
    assert promoted_relationship["event_type"] == "relationship_promoted"
    assert promoted_relationship["parent_event_ids"] == [promoted["event_id"]]
    assert promoted_relationship["root_event_id"] == interaction_event_id
    assert promoted_relationship["hop"] == 3


def test_updated_dynamic_edge_is_direct_parent_of_promotion(tmp_path):
    edge_id = "dynamic::1::2::response_bridge"
    edge = {
        "edge_id": edge_id,
        "source_agent_id": 1,
        "target_agent_id": 2,
        "source_region_id": "A",
        "target_region_id": "B",
        "edge_type": "response_bridge",
        "interaction_channel": "information",
        "layer": "dynamic",
        "status": "active",
        "strength": 0.6,
        "confidence": 0.65,
        "ttl_rounds": 3,
        "reconfirm_count": 1,
        "routing_basis": ["neighbor_region"],
        "evidence": {},
    }
    runtime = _dynamic_runtime(tmp_path, edge=edge)
    source = {"agent_id": 1, "agent_type": "human", "primary_region": "A"}
    target = {"agent_id": 2, "agent_type": "human", "primary_region": "B"}

    runtime._upsert_dynamic_edge(
        source,
        target,
        {
            "edge_type": "response_bridge",
            "strength": 0.6,
            "confidence": 0.65,
            "ttl_rounds": 3,
            "routing_basis": ["neighbor_region"],
            "rationale": "运行证据再次确认该关系。",
        },
        {"route_sources": ["neighbor_region"], "evidence": {}},
        4,
        "heuristic_emergent",
    )

    dynamic_events = _read_jsonl(tmp_path / "dynamic_edge_ledger.jsonl")
    updated, promoted = dynamic_events
    assert [item["event_type"] for item in dynamic_events] == ["updated", "promoted"]
    assert updated["parent_event_ids"] == []
    assert updated["root_event_id"] == updated["event_id"]
    assert updated["hop"] == 0
    assert promoted["parent_event_ids"] == [updated["event_id"]]
    assert promoted["root_event_id"] == updated["event_id"]
    assert promoted["hop"] == 1
