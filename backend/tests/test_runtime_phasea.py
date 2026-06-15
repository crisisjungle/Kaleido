"""Phase A regression tests for the envfish runtime.

Covers two newly-wired behaviours, both forced onto the deterministic / fallback
path (no live LLM, no network):

M8  — agents that merely SHARE A REGION now produce real agent-agent interactions,
      so the agent_interaction_ledger is non-empty even when the shipped config
      carries an empty agent_relationship_graph (the real-run failure mode).

M6  — a scenario's propagation channels MODULATE the diffusion transfer: with a
      channel present the applied delta differs from the channel-absent baseline.

The runtimes are built with ``EnvFishRuntime.__new__`` + minimal attributes, the
same construction pattern used by the existing coupling/loop runtime tests.
"""

import importlib.util
import json
import os
import tempfile
from collections import defaultdict

_SPEC = importlib.util.spec_from_file_location(
    "run_envfish_simulation",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "run_envfish_simulation.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
EnvFishRuntime = _MOD.EnvFishRuntime


# --------------------------------------------------------------------------- #
# M8: agents interact via co-location -> non-empty interaction ledger
# --------------------------------------------------------------------------- #
def _interaction_runtime(ledger_path):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.search_mode = "fast"
    runtime.llm = None
    runtime.llm_relation_search_budget = 0
    runtime.runtime_limits = {"max_active_agents_per_round": 8}
    runtime.agent_interaction_log = ledger_path
    runtime._colocation_candidate_limit = 3

    region = {
        "region_id": "R1",
        "name": "测试区",
        "state_vector": {
            "exposure_score": 70, "spread_pressure": 40, "panic_level": 50, "economic_stress": 40,
            "ecosystem_integrity": 50, "public_trust": 50, "service_capacity": 50,
            "response_capacity": 50, "livelihood_stability": 50, "vulnerability_score": 55,
        },
        "neighbors": [],
    }
    runtime.region_graph = [region]
    runtime.region_lookup = {"R1": region}
    runtime.subregion_lookup = {}
    runtime.subregion_graph = []
    runtime.transport_edges_by_source = defaultdict(list)

    # Two co-located agents, no structural relationship graph at all (the real-run
    # condition that left the ledger empty).
    actors = [
        {
            "agent_id": 1, "username": "gov_a", "name": "环保局",
            "agent_type": "governance", "agent_subtype": "",
            "primary_region": "R1", "home_region_id": "R1",
            "action_space": ["issue_alert", "monitor"], "impact_profile": {},
            "state_vector": {"vulnerability_score": 30, "response_capacity": 60},
        },
        {
            "agent_id": 2, "username": "resident_b", "name": "居民",
            "agent_type": "human", "agent_subtype": "",
            "primary_region": "R1", "home_region_id": "R1",
            "action_space": ["panic_buy", "monitor"], "impact_profile": {},
            "state_vector": {"vulnerability_score": 60, "response_capacity": 40},
        },
    ]
    runtime.actor_profiles = actors
    runtime.actor_lookup = {1: actors[0], 2: actors[1]}
    runtime.agents_by_region = defaultdict(list, {"R1": list(actors)})
    runtime.relationships_by_source = defaultdict(list)
    runtime.relationships_by_target = defaultdict(list)
    runtime.dynamic_edge_lookup = {}
    runtime.dynamic_edges_by_source = defaultdict(list)

    # Neutralise the side-effecting / out-of-scope helpers so the test stays on the
    # deterministic co-location interaction path.
    runtime._maybe_create_dynamic_edges = lambda actor, rnd, budget: ([], budget)
    runtime._write_action = lambda **kwargs: None
    runtime._activate_dynamic_edge = lambda *a, **k: None
    runtime._now = lambda: "2026-06-15T00:00:00"
    return runtime


def test_colocated_agents_produce_nonempty_interaction_ledger():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = os.path.join(tmp, "agent_interaction_ledger.jsonl")
        runtime = _interaction_runtime(ledger)

        result = runtime._agent_interaction_update(1, [], {})

        # interactions surfaced in the round result ...
        assert len(result["agent_interactions"]) >= 1
        first = result["agent_interactions"][0]
        assert first["source_agent_id"] in (1, 2)
        assert first["target_agent_id"] in (1, 2)
        assert first["source_agent_id"] != first["target_agent_id"]
        assert first["delta"]  # a real (non-empty) effect was applied

        # ... and persisted to the ledger file.
        assert os.path.exists(ledger)
        with open(ledger, "r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        assert len(lines) >= 1


def test_colocation_candidates_bounded_by_limit():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = _interaction_runtime(os.path.join(tmp, "ledger.jsonl"))
        # 6 peers in the same region, limit is 3 -> at most 3 candidates.
        peers = []
        for idx in range(10, 16):
            peer = {
                "agent_id": idx, "username": f"p{idx}", "name": f"peer{idx}",
                "agent_type": "human", "primary_region": "R1", "home_region_id": "R1",
            }
            peers.append(peer)
            runtime.actor_lookup[idx] = peer
        runtime.agents_by_region["R1"].extend(peers)

        actor = runtime.actor_lookup[1]
        candidates = runtime._colocation_candidate_edges(actor, set())
        assert 1 <= len(candidates) <= 3
        # never points at itself
        assert all(int(edge["target_agent_id"]) != 1 for edge in candidates)
        assert all(edge["epistemic_status"] == "speculative" for edge in candidates)


# --------------------------------------------------------------------------- #
# M6: a propagation channel modulates a diffusion transfer
# --------------------------------------------------------------------------- #
def _channel_runtime(channels, enabled=True, gain=0.5):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.propagation_channels = list(channels)
    runtime.propagation_channels_by_id = {
        str(c.get("channel_id") or "").lower(): c for c in channels if c.get("channel_id")
    }
    runtime.propagation_channels_enabled = enabled
    runtime.propagation_channel_gain = gain
    return runtime


_CHANNEL = {
    "channel_id": "shoreline_exposure",
    "label": "岸线暴露",
    "receptor_dim": "exposure_score",
    "gain": 1.4,
    "epistemic_status": "inferred",
}


def test_channel_present_changes_applied_delta():
    transfer = {"transfer_intensity": 60.0, "channel_type": "shoreline_exposure"}

    with_channel = _channel_runtime([_CHANNEL], enabled=True)
    without_channel = _channel_runtime([_CHANNEL], enabled=False)

    mod_present = with_channel._channel_modulation_for_transfer(transfer)
    mod_absent = without_channel._channel_modulation_for_transfer(transfer)

    # disabled => no modulation at all (legacy behaviour preserved)
    assert mod_absent == {}
    # enabled => the receptor dimension gets an extra, positive load
    assert "exposure_score" in mod_present
    assert mod_present["exposure_score"] > 0
    # the two paths produce a DIFFERENT applied delta
    assert mod_present != mod_absent


def test_ecosystem_channel_loads_negative_and_unknown_channel_is_noop():
    eco_channel = {
        "channel_id": "habitat_loss", "receptor_dim": "ecosystem_integrity", "gain": 1.3,
    }
    runtime = _channel_runtime([eco_channel], enabled=True)
    transfer = {"transfer_intensity": 50.0, "channel_type": "habitat_loss"}
    mod = runtime._channel_modulation_for_transfer(transfer)
    # ecosystem_integrity is "higher = better": a loading channel erodes it.
    assert mod["ecosystem_integrity"] < 0

    # No channels configured at all -> graceful no-op regardless of transfer.
    empty_runtime = _channel_runtime([], enabled=True)
    assert empty_runtime._channel_modulation_for_transfer(transfer) == {}
