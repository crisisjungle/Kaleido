import json
from collections import defaultdict

from scripts.run_envfish_simulation import EnvFishRuntime


class RecordingLLM:
    def __init__(self):
        self.payload = None

    def chat_json(self, *, messages, temperature, max_tokens):
        self.payload = json.loads(messages[-1]["content"])
        return {"proposals": []}


def _bare_runtime(contract_version):
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.risk_contract_version = contract_version
    runtime.allowed_cross_region_hops = 1
    runtime.cross_region_candidate_limit = 8
    runtime.relationships_by_source = defaultdict(list)
    runtime.agents_by_region = defaultdict(list)
    runtime.agents_by_type = defaultdict(list)
    runtime.agents_by_subtype = defaultdict(list)
    runtime.agent_risk_lookup = defaultdict(list, {1: ["risk_shared"]})
    runtime.risk_region_lookup = defaultdict(list, {"risk_shared": ["region_a"]})
    runtime.risk_actor_lookup = defaultdict(list, {"risk_shared": [2]})
    runtime.actor_lookup = {
        2: {
            "agent_id": 2,
            "name": "乙区设施运维员",
            "primary_region": "region_b",
            "agent_type": "carrier",
            "state_vector": {"vulnerability_score": 60},
        }
    }
    runtime._reachable_regions = lambda source, hops: []
    runtime._dynamic_edges_for_source = lambda source: []
    runtime._agent_activation_score = lambda actor: 60
    runtime._merge_dynamic_evidence = lambda first, second: {**first, **second}
    return runtime


def test_v2_risk_objects_do_not_create_agent_interaction_candidates():
    actor = {
        "agent_id": 1,
        "name": "甲区生态观察员",
        "primary_region": "region_a",
        "agent_type": "ecology",
        "state_vector": {"vulnerability_score": 50},
    }
    v2_runtime = _bare_runtime(2)
    assert v2_runtime._collect_cross_region_candidates(actor, 1) == []

    v1_runtime = _bare_runtime(1)
    legacy_candidates = v1_runtime._collect_cross_region_candidates(actor, 1)
    assert legacy_candidates[0]["target_agent_id"] == 2
    assert legacy_candidates[0]["route_sources"] == ["shared_risk_object"]


def test_v2_agent_decision_prompt_does_not_receive_risk_object_ids():
    runtime = _bare_runtime(2)
    runtime.llm = RecordingLLM()
    runtime.max_new_dynamic_edges_per_agent = 1
    runtime.search_mode = "deep_search"
    actor = {
        "agent_id": 1,
        "name": "甲区生态观察员",
        "primary_region": "region_a",
        "agent_type": "ecology",
        "state_vector": {"vulnerability_score": 50},
    }
    runtime._llm_dynamic_edge_search(
        actor,
        [{"target_agent_id": 2, "target_region_id": "region_b", "route_sources": ["neighbor_region"]}],
        1,
    )
    assert "risk_object_ids" not in runtime.llm.payload["source_agent"]
