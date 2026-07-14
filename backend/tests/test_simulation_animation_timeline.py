import json
import re
from types import SimpleNamespace

from app.services import simulation_animation_service as animation_module
from app.services.simulation_animation_service import (
    TIMELINE_CONTRACT_VERSION,
    SimulationAnimationService,
)


def _service(tmp_path=None):
    service = SimulationAnimationService.__new__(SimulationAnimationService)
    service.simulation_id = "sim_timeline_test"
    if tmp_path is not None:
        service.sim_dir = str(tmp_path)
    return service


def _layout():
    nodes = [
        {
            "id": "region::source",
            "name": "源水域",
            "kind": "region",
            "attributes": {"region_id": "source"},
        },
        {
            "id": "region::target",
            "name": "目标水域",
            "kind": "region",
            "attributes": {"region_id": "target"},
        },
        {
            "id": "agent::9",
            "name": "监测主体",
            "kind": "agent",
            "attributes": {"agent_id": 9},
        },
        {
            "id": "agent::2",
            "name": "响应主体",
            "kind": "agent",
            "attributes": {"agent_id": 2},
        },
    ]
    edges = [
        {
            "id": "region_neighbor::source::target",
            "source": "region::source",
            "target": "region::target",
            "fact_type": "region_neighbor",
            "attributes": {},
        },
        {
            "id": "transport::source::target",
            "source": "region::source",
            "target": "region::target",
            "fact_type": "transport_edge",
            "attributes": {},
        },
        {
            "id": "dynamic::9::2::coordination",
            "source": "agent::9",
            "target": "agent::2",
            "fact_type": "dynamic_edge",
            "attributes": {"edge_id": "dynamic::9::2::coordination"},
        },
    ]
    return nodes, edges


def _build_observed_timeline(service):
    nodes, edges = _layout()
    return service._build_timeline(
        spread_events=[
            {
                "event_id": "spread-1",
                "round": 2,
                "timestamp": "2026-07-13T10:00:00",
                "source_region": "source",
                "target_region": "target",
                "transfer_intensity": 64,
                "delay_rounds": 2,
                "persistence": 3,
                "confidence": 0.82,
                "transport_edge_id": "transport::source::target",
            }
        ],
        agent_interactions=[
            {
                "event_id": "interaction-1",
                "round": 2,
                "timestamp": "2026-07-13T10:01:00",
                "source_agent_id": 9,
                "target_agent_id": 2,
                "source_region_id": "source",
                "target_region_id": "target",
                "action_type": "issue_alert",
                "action_label_zh": "发布预警",
                "edge_id": "dynamic::9::2::coordination",
                "delta": {"response_capacity": 6},
                "relationship_event_id": "relationship-1",
            }
        ],
        dynamic_edge_events=[
            {
                "round": 2,
                "timestamp": "2026-07-13T10:02:00",
                "event_type": "created",
                "edge_id": "dynamic::9::2::coordination",
                "source_agent_id": 9,
                "target_agent_id": 2,
                "source_region_id": "source",
                "target_region_id": "target",
                "strength": 0.7,
                "confidence": 0.76,
                "created_round": 2,
                "ttl_rounds": 4,
            }
        ],
        relationship_events=[
            {
                "relationship_event_id": "relationship-1",
                "round_number": 2,
                "event_type": "cooperation",
                "source_agent_id": 9,
                "target_agent_id": 2,
                "relationship_contract_id": "dynamic::9::2::coordination",
                "summary_zh": "预警行动推动两个主体进入协作状态。",
            }
        ],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )


def test_timeline_projects_real_ledgers_in_deterministic_causal_phase_order():
    service = _service()
    timeline = _build_observed_timeline(service)
    repeated = _build_observed_timeline(service)

    assert timeline == repeated
    assert timeline["contract_version"] == TIMELINE_CONTRACT_VERSION
    assert timeline["edge_reference_contract"] == "split-path-related.v1"
    assert timeline["source_mode"] == "observed_ledgers"
    assert timeline["cursor"] == 4
    assert [event["sequence"] for event in timeline["events"]] == [1, 2, 3, 4]
    assert [event["kind"] for event in timeline["events"]] == [
        "spread_applied",
        "agent_interaction",
        "dynamic_edge_created",
        "relationship_event",
    ]

    spread, interaction, dynamic, relationship = timeline["events"]
    assert spread["source"]["node_ids"] == ["region::source"]
    assert spread["target"]["node_ids"] == ["region::target"]
    assert spread["edge_ids"] == ["transport::source::target"]
    assert spread["path_edge_ids"] == ["transport::source::target"]
    assert spread["related_edge_ids"] == []
    assert interaction["source"]["node_ids"] == ["agent::9"]
    assert interaction["path_edge_ids"] == ["dynamic::9::2::coordination"]
    assert interaction["related_edge_ids"] == []
    assert dynamic["edge_ids"] == ["dynamic::9::2::coordination"]
    assert dynamic["path_edge_ids"] == ["dynamic::9::2::coordination"]
    assert dynamic["related_edge_ids"] == []
    assert relationship["path_edge_ids"] == ["dynamic::9::2::coordination"]
    assert relationship["related_edge_ids"] == []
    assert relationship["parent_event_ids"] == [interaction["id"]]
    assert spread["parent_event_ids"] == []

    for event in timeline["events"]:
        assert event["timing"]["start_ms"] >= 0
        assert event["timing"]["duration_ms"] > 0
        assert event["grounding"]["mode"] == "observed"
        assert event["grounding"]["fallback"] is False
        assert re.search(r"[\u3400-\u9fff]", event["display"]["title_zh"])
        assert re.search(r"[\u3400-\u9fff]", event["display"]["summary_zh"])
        assert not re.search(r"[A-Za-z_]{3,}", event["display"]["title_zh"])
        assert not re.search(r"[A-Za-z_]{3,}", event["display"]["summary_zh"])


def test_timeline_uses_explicit_legacy_fallback_only_without_primary_ledgers():
    service = _service()
    nodes, edges = _layout()
    frames = [
        {"round": 0, "timestamp": "", "focus_ids": {"node_ids": ["region::source"], "edge_ids": []}},
        {
            "round": 1,
            "timestamp": "2026-07-13T11:00:00",
            "focus_ids": {
                "node_ids": ["agent::9"],
                "edge_ids": ["dynamic::9::2::coordination"],
            },
        },
    ]
    timeline = service._build_timeline(
        spread_events=[],
        dynamic_edge_events=[],
        agent_interactions=[],
        relationship_events=[],
        risk_events=[],
        frames=frames,
        layout_nodes=nodes,
        layout_edges=edges,
    )

    assert timeline["source_mode"] == "legacy_frame_fallback"
    assert timeline["grounding"]["fallback_used"] is True
    assert timeline["fallback_event_count"] == 2
    assert timeline["grounding"]["missing_ledgers"] == [
        "spread_event_ledger.jsonl",
        "dynamic_edge_ledger.jsonl",
        "agent_interaction_ledger.jsonl",
        "relationship_event_ledger.jsonl",
    ]
    assert all(event["kind"] == "legacy_frame" for event in timeline["events"])
    assert all(event["grounding"]["mode"] == "legacy_fallback" for event in timeline["events"])
    assert all(event["parent_event_ids"] == [] for event in timeline["events"])


def test_legacy_animation_prefers_available_ledger_and_supports_cursor_window(tmp_path):
    service = _service(tmp_path)
    nodes, edges = _layout()
    spread = {
        "round": 1,
        "source_region": "source",
        "target_region": "target",
        "transfer_intensity": 48,
        "confidence": 0.7,
    }
    (tmp_path / "spread_event_ledger.jsonl").write_text(
        json.dumps(spread, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    payload = {
        "meta": {"total_rounds": 1},
        "layout": {"nodes": nodes, "edges": edges},
        "frames": [
            {
                "round": 1,
                "node_states": [],
                "edge_states": [],
                "focus_ids": {"node_ids": [], "edge_ids": []},
            }
        ],
    }

    normalized = service._normalize_animation_payload(payload)
    assert normalized["timeline"]["source_mode"] == "observed_ledgers"
    assert [event["kind"] for event in normalized["timeline"]["events"]] == ["spread_applied"]
    assert normalized["frames"][0]["timeline_event_ids"] == [
        normalized["timeline"]["events"][0]["id"]
    ]

    window = service._filter_timeline_after_cursor(normalized, 1)
    assert window["timeline"]["cursor"] == 1
    assert window["timeline"]["events"] == []
    assert window["timeline"]["window"] == {
        "after_cursor": 1,
        "after_round": None,
        "returned_count": 0,
        "returned_frame_count": 0,
        "has_more": False,
        "frames_included": False,
        "layout_included": False,
    }
    assert "frames" not in window
    assert "layout" not in window

    first_window = service._filter_timeline_after_cursor(normalized, 0)
    assert len(first_window["timeline"]["events"]) == 1
    assert first_window["timeline"]["window"]["layout_included"] is True
    assert first_window["layout"] == normalized["layout"]
    assert "frames" not in first_window


def test_relationship_alias_resolves_to_relationship_event_without_losing_trigger_parent():
    service = _service()
    nodes, edges = _layout()
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "event_id": "interaction-1",
                "round": 2,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "relationship_event_id": "relationship-1",
                "root_event_id": "interaction-1",
                "hop": 0,
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[
            {
                "relationship_event_id": "relationship-1",
                "round_number": 2,
                "event_type": "cooperation",
                "source_agent_id": 9,
                "target_agent_id": 2,
                "root_event_id": "interaction-1",
                "hop": 1,
            }
        ],
        risk_events=[
            {
                "event_id": "risk-1",
                "round": 2,
                "risk_id": "risk::1",
                "parent_event_ids": ["relationship-1"],
                "root_event_id": "interaction-1",
                "hop": 2,
            }
        ],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    interaction, relationship, risk = timeline["events"]
    assert relationship["parent_event_ids"] == [interaction["id"]]
    assert risk["parent_event_ids"] == [relationship["id"]]
    assert interaction["root_event_id"] == interaction["id"]
    assert relationship["root_event_id"] == interaction["id"]
    assert risk["root_event_id"] == interaction["id"]
    assert [interaction["hop"], relationship["hop"], risk["hop"]] == [0, 1, 2]


def test_legacy_dynamic_status_preserves_created_transition():
    service = _service()
    nodes, edges = _layout()
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[],
        dynamic_edge_events=[
            {
                "edge_id": "dynamic::9::2::coordination",
                "source_agent_id": 9,
                "target_agent_id": 2,
                "status": "created",
                "created_round": 1,
            }
        ],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    assert timeline["events"][0]["kind"] == "dynamic_edge_created"
    assert timeline["events"][0]["display"]["title_zh"] == "动态关系建立"


def test_live_waiting_timeline_does_not_consume_cursor_with_legacy_baseline():
    service = _service()
    nodes, edges = _layout()
    waiting = service._build_timeline(
        spread_events=[],
        agent_interactions=[],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[
            {
                "round": 0,
                "focus_ids": {"node_ids": ["region::source"], "edge_ids": []},
            }
        ],
        layout_nodes=nodes,
        layout_edges=edges,
        allow_legacy_fallback=False,
    )
    observed = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "event_id": "first-observed-event",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
        completed_rounds={1},
        allow_legacy_fallback=False,
    )

    assert waiting["source_mode"] == "awaiting_runtime_ledgers"
    assert waiting["cursor"] == 0
    assert waiting["events"] == []
    assert observed["cursor"] == 1
    payload = {"meta": {}, "layout": {"nodes": nodes, "edges": edges}, "frames": [], "timeline": observed}
    assert len(service._filter_timeline_after_cursor(payload, waiting["cursor"])["timeline"]["events"]) == 1


def test_explicit_edge_does_not_expand_to_parallel_pair_edges():
    service = _service()
    nodes, edges = _layout()
    edges.append(
        {
            "id": "dynamic::9::2::parallel",
            "source": "agent::9",
            "target": "agent::2",
            "fact_type": "dynamic_edge",
            "attributes": {},
        }
    )
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "event_id": "interaction-explicit-edge",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "edge_id": "dynamic::9::2::coordination",
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    assert timeline["events"][0]["edge_ids"] == ["dynamic::9::2::coordination"]
    assert timeline["events"][0]["path_edge_ids"] == ["dynamic::9::2::coordination"]


def test_explicit_multi_edge_path_requires_directional_continuity():
    service = _service()
    nodes, edges = _layout()
    nodes.append(
        {
            "id": "agent::middle",
            "name": "中继主体",
            "kind": "agent",
            "attributes": {"agent_id": "middle"},
        }
    )
    edges.extend(
        [
            {
                "id": "path::9::middle",
                "source": "agent::9",
                "target": "agent::middle",
                "fact_type": "dynamic_edge",
                "attributes": {},
            },
            {
                "id": "path::middle::2",
                "source": "agent::middle",
                "target": "agent::2",
                "fact_type": "dynamic_edge",
                "attributes": {},
            },
        ]
    )
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "event_id": "interaction-ordered-path",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "path_edge_ids": ["path::9::middle", "path::middle::2"],
            },
            {
                "event_id": "interaction-broken-path",
                "round": 2,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "path_edge_ids": ["path::middle::2", "path::9::middle"],
            },
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    ordered, broken = timeline["events"]
    assert ordered["path_edge_ids"] == ["path::9::middle", "path::middle::2"]
    assert ordered["related_edge_ids"] == []
    assert broken["path_edge_ids"] == []
    assert broken["related_edge_ids"] == ["path::middle::2", "path::9::middle"]
    assert broken["grounding"]["reference_quality"] == "unresolved"


def test_raw_untyped_multi_edge_sets_remain_related_evidence():
    service = _service()
    nodes, edges = _layout()
    edges.append(
        {
            "id": "dynamic::9::2::parallel",
            "source": "agent::9",
            "target": "agent::2",
            "fact_type": "dynamic_edge",
            "attributes": {},
        }
    )
    timeline = service._build_timeline(
        spread_events=[
            {
                "event_id": "spread-untyped-multi",
                "round": 1,
                "source_region": "source",
                "target_region": "target",
                "edge_ids": [
                    "transport::source::target",
                    "region_neighbor::source::target",
                ],
            }
        ],
        agent_interactions=[
            {
                "event_id": "interaction-untyped-multi",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "edge_ids": [
                    "dynamic::9::2::coordination",
                    "dynamic::9::2::parallel",
                ],
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    spread = next(event for event in timeline["events"] if event["kind"] == "spread_applied")
    interaction = next(event for event in timeline["events"] if event["kind"] == "agent_interaction")
    assert spread["path_edge_ids"] == []
    assert spread["related_edge_ids"] == [
        "transport::source::target",
        "region_neighbor::source::target",
    ]
    assert interaction["path_edge_ids"] == []
    assert interaction["related_edge_ids"] == [
        "dynamic::9::2::coordination",
        "dynamic::9::2::parallel",
    ]


def test_existing_typed_path_is_revalidated_against_layout_direction():
    service = _service()
    nodes, edges = _layout()
    nodes.append(
        {
            "id": "agent::middle",
            "name": "中继主体",
            "kind": "agent",
            "attributes": {"agent_id": "middle"},
        }
    )
    edges.extend(
        [
            {
                "id": "path::9::middle",
                "source": "agent::9",
                "target": "agent::middle",
                "fact_type": "dynamic_edge",
                "attributes": {},
            },
            {
                "id": "path::middle::2",
                "source": "agent::middle",
                "target": "agent::2",
                "fact_type": "dynamic_edge",
                "attributes": {},
            },
        ]
    )
    references = service._build_timeline_reference_index(nodes, edges)
    timeline = service._normalize_timeline_edge_references(
        {
            "contract_version": TIMELINE_CONTRACT_VERSION,
            "events": [
                {
                    "id": "persisted-broken-path",
                    "source": {"node_ids": ["agent::9"]},
                    "target": {"node_ids": ["agent::2"]},
                    "path_edge_ids": ["path::middle::2", "path::9::middle"],
                    "related_edge_ids": [],
                    "grounding": {"reference_quality": "resolved"},
                }
            ],
        },
        references=references,
    )

    event = timeline["events"][0]
    assert event["path_edge_ids"] == []
    assert event["related_edge_ids"] == ["path::middle::2", "path::9::middle"]
    assert event["grounding"]["reference_quality"] == "unresolved"


def test_relationship_mechanism_edges_are_related_evidence_not_a_route():
    service = _service()
    nodes, edges = _layout()
    edges.extend(
        [
            {
                "id": "mechanism::release",
                "source": "agent::9",
                "target": "region::source",
                "fact_type": "mechanism_edge",
                "attributes": {},
            },
            {
                "id": "mechanism::response",
                "source": "region::source",
                "target": "agent::2",
                "fact_type": "mechanism_edge",
                "attributes": {},
            },
        ]
    )
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[],
        dynamic_edge_events=[],
        relationship_events=[
            {
                "relationship_event_id": "relationship-with-evidence",
                "round_number": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "relationship_contract_id": "dynamic::9::2::coordination",
                "mechanism_edge_ids": ["mechanism::release", "mechanism::response"],
            }
        ],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    event = timeline["events"][0]
    assert event["path_edge_ids"] == ["dynamic::9::2::coordination"]
    assert event["related_edge_ids"] == [
        "mechanism::release",
        "mechanism::response",
    ]
    assert event["edge_ids"] == [
        "dynamic::9::2::coordination",
        "mechanism::release",
        "mechanism::response",
    ]


def test_existing_v2_multi_edge_ids_upgrade_to_related_without_path_invention():
    service = _service()
    timeline = service._normalize_timeline_edge_references(
        {
            "contract_version": TIMELINE_CONTRACT_VERSION,
            "events": [
                {
                    "id": "old-relationship-event",
                    "kind": "relationship_event",
                    "edge_ids": ["mechanism::a", "mechanism::b"],
                },
                {
                    "id": "old-single-spread",
                    "kind": "spread_applied",
                    "edge_ids": ["transport::a::b"],
                },
            ],
        }
    )

    relationship, spread = timeline["events"]
    assert relationship["path_edge_ids"] == []
    assert relationship["related_edge_ids"] == ["mechanism::a", "mechanism::b"]
    assert spread["path_edge_ids"] == ["transport::a::b"]
    assert spread["related_edge_ids"] == []


def test_legacy_interaction_chooses_one_parallel_path_and_marks_ambiguity():
    service = _service()
    nodes, edges = _layout()
    edges.append(
        {
            "id": "dynamic::9::2::parallel",
            "source": "agent::9",
            "target": "agent::2",
            "fact_type": "dynamic_edge",
            "attributes": {},
        }
    )
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "id": "legacy-interaction-ambiguous",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "action_type": "COORDINATE",
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    event = timeline["events"][0]
    assert event["edge_ids"] == ["dynamic::9::2::coordination"]
    assert event["grounding"]["reference_quality"] == "partial"


def test_frozen_interaction_adapter_resolves_legacy_id_region_names_and_action():
    service = _service()
    nodes, edges = _layout()
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "id": "legacy-interaction-1",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "source_region_name": "source",
                "target_region_name": "target",
                "action_type": "COORDINATE",
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[
            {
                "event_id": "risk-after-interaction",
                "round": 1,
                "risk_id": "risk::1",
                "parent_event_ids": ["legacy-interaction-1"],
            }
        ],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    interaction, risk = timeline["events"]
    assert interaction["source"]["region_node_ids"] == ["region::source"]
    assert interaction["target"]["region_node_ids"] == ["region::target"]
    assert "协调响应" in interaction["display"]["summary_zh"]
    assert risk["parent_event_ids"] == [interaction["id"]]


def test_historical_dynamic_edge_union_keeps_timeline_path_renderable():
    service = _service()
    nodes, edges = _layout()
    historical_record = {
        "edge_id": "dynamic::2::9::historical",
        "source_agent_id": 2,
        "target_agent_id": 9,
        "event_type": "dormant",
        "round": 3,
        "created_round": 1,
        "last_activated_round": 2,
        "status": "dormant",
    }
    merged_edges = service._merge_historical_dynamic_edges(
        nodes,
        edges,
        [historical_record],
    )
    historical_edge = next(
        edge for edge in merged_edges if edge["id"] == "dynamic::2::9::historical"
    )
    assert historical_edge["source"] == "agent::2"
    assert historical_edge["target"] == "agent::9"
    assert historical_edge["fact_type"] == "dynamic_edge"
    assert historical_edge["attributes"]["historical_timeline_edge"] is True

    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[],
        dynamic_edge_events=[historical_record],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=merged_edges,
    )
    assert timeline["events"][0]["edge_ids"] == ["dynamic::2::9::historical"]
    assert timeline["events"][0]["path_edge_ids"] == ["dynamic::2::9::historical"]
    assert timeline["events"][0]["related_edge_ids"] == []
    assert timeline["events"][0]["grounding"]["reference_quality"] == "resolved"


def test_unknown_explicit_edge_is_marked_unresolved():
    service = _service()
    nodes, edges = _layout()
    timeline = service._build_timeline(
        spread_events=[],
        agent_interactions=[
            {
                "event_id": "interaction-with-missing-edge",
                "round": 1,
                "source_agent_id": 9,
                "target_agent_id": 2,
                "edge_id": "dynamic::missing",
            }
        ],
        dynamic_edge_events=[],
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
    )

    assert timeline["events"][0]["edge_ids"] == ["dynamic::missing"]
    assert timeline["events"][0]["grounding"]["reference_quality"] == "unresolved"


def test_uncommitted_round_records_do_not_enter_live_layout_or_frames():
    service = _service()
    records = [
        {"event_id": "baseline", "round": 0},
        {"event_id": "committed", "round": 1},
        {"event_id": "in-progress", "round": 2},
    ]

    eligible = service._records_for_completed_rounds(records, {1})

    assert [record["event_id"] for record in eligible] == ["baseline", "committed"]


def test_normalization_does_not_reintroduce_uncommitted_historical_edge(tmp_path):
    service = _service(tmp_path)
    records = [
        {
            "edge_id": "dynamic::9::2::committed",
            "source_agent_id": 9,
            "target_agent_id": 2,
            "round": 1,
        },
        {
            "edge_id": "dynamic::9::2::in-progress",
            "source_agent_id": 9,
            "target_agent_id": 2,
            "round": 2,
        },
    ]
    (tmp_path / "dynamic_edge_ledger.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )
    nodes, _ = _layout()
    payload = {
        "meta": {},
        "layout": {
            "nodes": nodes,
            "edges": [
                {
                    "id": "dynamic::9::2::in-progress",
                    "source": "agent::9",
                    "target": "agent::2",
                    "fact_type": "dynamic_edge",
                    "attributes": {},
                }
            ],
        },
        "frames": [],
        "timeline": {
            "contract_version": TIMELINE_CONTRACT_VERSION,
            "cursor": 1,
            "events": [
                {
                    "id": "event-1",
                    "sequence": 1,
                    "round": 1,
                    "edge_ids": ["dynamic::9::2::committed"],
                }
            ],
        },
    }

    normalized = service._normalize_animation_payload(payload)

    assert [edge["id"] for edge in normalized["layout"]["edges"]] == [
        "dynamic::9::2::committed"
    ]


def test_cursor_order_is_append_stable_across_completed_rounds():
    service = _service()
    nodes, edges = _layout()
    interactions = [
        {
            "event_id": "interaction-round-1",
            "round": 1,
            "source_agent_id": 9,
            "target_agent_id": 2,
            "edge_id": "dynamic::9::2::coordination",
            "action_type": "monitor",
        },
        {
            "event_id": "interaction-round-2",
            "round": 2,
            "source_agent_id": 2,
            "target_agent_id": 9,
            "edge_id": "dynamic::9::2::coordination",
            "action_type": "coordinate_response",
        },
    ]
    first = service._build_timeline(
        spread_events=[],
        dynamic_edge_events=[],
        agent_interactions=interactions,
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
        completed_rounds={1},
    )
    second = service._build_timeline(
        spread_events=[],
        dynamic_edge_events=[],
        agent_interactions=interactions,
        relationship_events=[],
        risk_events=[],
        frames=[],
        layout_nodes=nodes,
        layout_edges=edges,
        completed_rounds={1, 2},
    )

    assert first["cursor"] == 1
    assert first["events"][0]["id"] == second["events"][0]["id"]
    assert first["events"][0]["sequence"] == second["events"][0]["sequence"] == 1
    assert second["cursor"] == 2
    assert second["events"][1]["sequence"] == 2


def test_agent_identity_no_longer_creates_fake_batch_reveal_rounds():
    service = _service()
    first_seen = service._compute_node_first_seen(
        [
            {"id": "agent::1", "kind": "agent", "attributes": {"agent_id": 1}},
            {"id": "agent::99", "kind": "agent", "attributes": {"agent_id": 99}},
            {
                "id": "agent::runtime",
                "kind": "agent",
                "attributes": {
                    "agent_id": 100,
                    "runtime_lifecycle": {"created_round": 4},
                },
            },
        ]
    )

    assert first_seen == {"agent::1": 0, "agent::99": 0, "agent::runtime": 4}


def test_live_animation_commits_frames_and_layout_atomically_across_eventless_round(
    tmp_path,
    monkeypatch,
):
    graph = {
        "nodes": [
            {
                "uuid": "agent::1",
                "name": "基线主体一",
                "labels": ["Agent"],
                "attributes": {"agent_id": 1, "created_round": 0},
            },
            {
                "uuid": "agent::2",
                "name": "基线主体二",
                "labels": ["Agent"],
                "attributes": {"agent_id": 2, "created_round": 0},
            },
            {
                "uuid": "agent::99",
                "name": "第二轮涌现主体",
                "labels": ["Agent"],
                "attributes": {
                    "agent_id": 99,
                    "runtime_lifecycle": {
                        "created_round": 2,
                        "activation_round": 2,
                    },
                },
            },
            {
                "uuid": "agent::100",
                "name": "快照运行主体",
                "labels": ["Agent"],
                "attributes": {
                    "agent_id": 100,
                    "source": "runtime_snapshot",
                },
            },
        ],
        "edges": [
            {
                "uuid": "baseline::1::2",
                "source_node_uuid": "agent::1",
                "target_node_uuid": "agent::2",
                "fact_type": "agent_influence",
                "attributes": {},
            },
            {
                "uuid": "future::1::99",
                "source_node_uuid": "agent::1",
                "target_node_uuid": "agent::99",
                "fact_type": "agent_influence",
                "attributes": {"first_seen_round": 2},
            },
            {
                "uuid": "future::1::100",
                "source_node_uuid": "agent::1",
                "target_node_uuid": "agent::100",
                "fact_type": "agent_influence",
                "attributes": {},
            },
        ],
    }
    monkeypatch.setattr(
        animation_module.SimulationRealtimeGraphBuilder,
        "build",
        lambda _builder: graph,
    )
    monkeypatch.setattr(
        animation_module.SimulationMapProjectionBuilder,
        "build",
        lambda _builder, _graph, key_edges_only=False: {
            "center": {},
            "source_mode": "map_seed",
            "map_seed_id": "seed_spatial_contract",
            "geographic_grounding": "map_seed",
            "data_quality": {"status": "complete", "formal_ready": True},
            "selection_summary": {"selected": 2},
            "meta": {"projection_version": "spatial-v1"},
            "nodes": [],
            "layers": [],
        },
    )
    (tmp_path / "simulation_config.json").write_text(
        json.dumps({"time_config": {"total_rounds": 4, "minutes_per_round": 60}}),
        encoding="utf-8",
    )
    service = _service(tmp_path)
    service.state = SimpleNamespace(
        map_seed_id=None,
        source_mode="graph",
        artifact_mode="live",
        is_replay_only=False,
        configured_total_rounds=4,
        configured_minutes_per_round=60,
        reference_time="2026-07-14T00:00:00",
        golden_case_id="",
    )

    initial = service.get_animation()

    assert [frame["round"] for frame in initial["frames"]] == [0]
    assert initial["layout"]["source_mode"] == "map_seed"
    assert initial["layout"]["map_seed_id"] == "seed_spatial_contract"
    assert initial["layout"]["geographic_grounding"] == "map_seed"
    assert initial["layout"]["data_quality"] == {"status": "complete", "formal_ready": True}
    assert initial["layout"]["selection_summary"] == {"selected": 2}
    assert initial["layout"]["meta"]["projection_version"] == "spatial-v1"
    assert {node["id"] for node in initial["layout"]["nodes"]} == {
        "agent::1",
        "agent::2",
    }
    assert {edge["id"] for edge in initial["layout"]["edges"]} == {
        "baseline::1::2"
    }

    round_one_snapshot = {
        "round": 1,
        "agents": [{"agent_id": 1}, {"agent_id": 2}],
    }
    (tmp_path / "round_state_matrix.jsonl").write_text(
        json.dumps(round_one_snapshot, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "agent_interaction_ledger.jsonl").write_text(
        json.dumps(
            {
                "event_id": "round-one-interaction",
                "round": 1,
                "source_agent_id": 1,
                "target_agent_id": 2,
                "edge_id": "baseline::1::2",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    after_round_one = service.get_animation()

    assert [frame["round"] for frame in after_round_one["frames"]] == [0, 1]
    assert after_round_one["timeline"]["cursor"] == 1
    assert "agent::99" not in {
        node["id"] for node in after_round_one["layout"]["nodes"]
    }
    assert "agent::100" not in {
        node["id"] for node in after_round_one["layout"]["nodes"]
    }

    round_two_snapshot = {
        "round": 2,
        "agents": [
            {"agent_id": 1},
            {"agent_id": 2},
            {"agent_id": 99},
            {"agent_id": 100},
        ],
    }
    (tmp_path / "round_state_matrix.jsonl").write_text(
        "\n".join(
            json.dumps(snapshot, ensure_ascii=False)
            for snapshot in (round_one_snapshot, round_two_snapshot)
        )
        + "\n",
        encoding="utf-8",
    )

    delta = service.get_animation(after_cursor=1, after_round=1)

    assert delta["timeline"]["events"] == []
    assert [frame["round"] for frame in delta["frames"]] == [2]
    assert delta["frames"][0]["timeline_event_ids"] == []
    assert delta["timeline"]["window"] == {
        "after_cursor": 1,
        "after_round": 1,
        "returned_count": 0,
        "returned_frame_count": 1,
        "has_more": False,
        "frames_included": True,
        "layout_included": True,
    }
    assert {"agent::99", "agent::100"}.issubset(
        {node["id"] for node in delta["layout"]["nodes"]}
    )
    assert {"future::1::99", "future::1::100"}.issubset(
        {edge["id"] for edge in delta["layout"]["edges"]}
    )


def test_frozen_animation_keeps_configured_replay_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(
        animation_module.SimulationRealtimeGraphBuilder,
        "build",
        lambda _builder: {"nodes": [], "edges": []},
    )
    monkeypatch.setattr(
        animation_module.SimulationMapProjectionBuilder,
        "build",
        lambda _builder, _graph, key_edges_only=False: {
            "center": {},
            "nodes": [],
            "layers": [],
        },
    )
    (tmp_path / "simulation_config.json").write_text(
        json.dumps({"time_config": {"total_rounds": 3, "minutes_per_round": 60}}),
        encoding="utf-8",
    )
    service = _service(tmp_path)
    service.state = SimpleNamespace(
        map_seed_id=None,
        source_mode="graph",
        artifact_mode="frozen",
        is_replay_only=True,
        configured_total_rounds=3,
        configured_minutes_per_round=60,
        reference_time="2026-07-14T00:00:00",
        golden_case_id="fixture",
    )

    payload = service.get_animation()

    assert [frame["round"] for frame in payload["frames"]] == [0, 1, 2, 3]


def test_animation_endpoint_keeps_full_default_and_forwards_cursor_alias(monkeypatch):
    from flask import Flask

    from app.api import simulation as simulation_api
    from app.api import simulation_bp

    calls = []

    class FakeAnimationService:
        def __init__(self, simulation_id):
            self.simulation_id = simulation_id

        def get_animation(
            self,
            after_cursor="not-provided",
            after_round="not-provided",
        ):
            calls.append((after_cursor, after_round))
            return {
                "meta": {"simulation_id": self.simulation_id},
                "frames": [],
                "timeline": {
                    "contract_version": TIMELINE_CONTRACT_VERSION,
                    "cursor": 9,
                    "events": [],
                },
            }

    monkeypatch.setattr(simulation_api, "SimulationAnimationService", FakeAnimationService)
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    client = app.test_client()

    full_response = client.get("/api/simulation/sim_cursor/animation")
    window_response = client.get(
        "/api/simulation/sim_cursor/animation?since_cursor=7"
    )
    round_window_response = client.get(
        "/api/simulation/sim_cursor/animation?since_round=4"
    )
    combined_window_response = client.get(
        "/api/simulation/sim_cursor/animation?after_cursor=8&after_round=5"
    )
    invalid_response = client.get(
        "/api/simulation/sim_cursor/animation?after_cursor=not-a-number"
    )
    negative_cursor_response = client.get(
        "/api/simulation/sim_cursor/animation?after_cursor=-1"
    )
    invalid_round_response = client.get(
        "/api/simulation/sim_cursor/animation?after_round=not-a-number"
    )
    negative_round_response = client.get(
        "/api/simulation/sim_cursor/animation?after_round=-1"
    )

    assert full_response.status_code == 200
    assert window_response.status_code == 200
    assert round_window_response.status_code == 200
    assert combined_window_response.status_code == 200
    assert invalid_response.status_code == 400
    assert negative_cursor_response.status_code == 400
    assert invalid_round_response.status_code == 400
    assert negative_round_response.status_code == 400
    assert calls == [
        ("not-provided", "not-provided"),
        (7, None),
        (None, 4),
        (8, 5),
    ]
