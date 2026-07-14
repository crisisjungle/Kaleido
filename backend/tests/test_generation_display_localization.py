import json
import re

from app.api.simulation import _grounding_source_labels, _prepare_stage_label
from app.services.env_profile_generator import EnvProfileGenerator, PreparedEntityContext
from app.services.envfish_models import RegionNode
from app.services.zep_entity_reader import EntityNode
from scripts.run_envfish_simulation import EnvFishRuntime


def _has_chinese(value):
    return any("\u3400" <= char <= "\u9fff" for char in str(value or ""))


def _assert_chinese_display(value):
    text = str(value or "")
    assert _has_chinese(text)
    assert not re.search(r"[A-Za-z_]", text)


class _EnglishProfileLlm:
    def __init__(self):
        self.prompt = None

    def chat_json(self, *, messages, temperature, max_tokens):
        self.prompt = json.loads(messages[-1]["content"])
        return {
            "profession": "EmergencyResponseAgent",
            "bio": "Entity rooted in Region_01.",
            "persona": "Fallback profile for agent_01.",
            "goals": ["protect_supply_chain"],
            "sensitivities": ["unknown_risk"],
        }


class _EnglishRuntimeLlm:
    def __init__(self, payload):
        self.payload = payload
        self.prompt = None

    def chat_json(self, *, messages, temperature, max_tokens):
        self.prompt = json.loads(messages[-1]["content"])
        return self.payload


def test_profile_llm_display_fields_fall_back_to_chinese():
    llm = _EnglishProfileLlm()
    generator = EnvProfileGenerator(llm_client=llm)
    prepared = PreparedEntityContext(
        entity=EntityNode(
            uuid="entity_01",
            name="Agent 01",
            labels=["Entity", "HumanActor"],
            summary="English summary",
            attributes={},
        ),
        entity_type="HumanActor",
        node_family="HumanActor",
        summary="English summary",
        relation_hints=[],
    )
    region = RegionNode(region_id="region_01", name="Region 01")

    payload = generator._generate_profile_with_llm(
        prepared=prepared,
        primary_region=region,
        simulation_requirement="测试场景",
        injected_variables=[],
    )

    assert "snake_case" in " ".join(llm.prompt["rules"])
    for field in ("profession", "bio", "persona"):
        _assert_chinese_display(payload[field])
    for field in ("goals", "sensitivities"):
        assert payload[field]
        for item in payload[field]:
            _assert_chinese_display(item)


def test_entity_template_profile_does_not_render_class_names_or_internal_ids():
    generator = EnvProfileGenerator(llm_client=None)
    generator.llm_client = None
    prepared = PreparedEntityContext(
        entity=EntityNode(
            uuid="entity_02",
            name="UnnamedEntity_02",
            labels=["Entity", "HumanActor"],
            summary="unknown entity",
            attributes={"source_kind": "inferred"},
        ),
        entity_type="HumanActor",
        node_family="HumanActor",
        summary="unknown entity",
        relation_hints=[],
    )
    profile = generator._build_profile(
        index=0,
        prepared=prepared,
        regions=[RegionNode(region_id="region_01", name="Region_01", land_use_class="mixed")],
        subregions=[],
        scenario_mode="baseline_mode",
        simulation_requirement="测试场景",
        injected_variables=[],
        use_llm=False,
    )

    for value in [
        profile.name,
        profile.profession,
        profile.bio,
        profile.persona,
        profile.grounding_reason,
        *profile.goals,
        *profile.sensitivities,
    ]:
        _assert_chinese_display(value)
    assert profile.review_status == "assumed"


def test_runtime_llm_display_fields_are_validated_without_changing_machine_enums():
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.llm = _EnglishRuntimeLlm(
        {
            "proposals": [
                {
                    "target_agent_id": 2,
                    "edge_type": "governance_coordination",
                    "routing_basis": ["neighbor_region"],
                    "strength": 0.6,
                    "confidence": 0.7,
                    "ttl_rounds": 2,
                    "rationale": "Fallback edge from Agent_01.",
                }
            ]
        }
    )
    runtime.max_new_dynamic_edges_per_agent = 1
    runtime.risk_contract_version = 2
    runtime.search_mode = "deep_search"
    runtime.agent_risk_lookup = {}

    proposals = runtime._llm_dynamic_edge_search(
        {
            "agent_id": 1,
            "name": "测试主体",
            "primary_region": "region_a",
            "agent_type": "human",
            "agent_subtype": "resident",
        },
        [{"target_agent_id": 2, "target_region_id": "region_b"}],
        1,
    )

    assert proposals[0]["edge_type"] == "governance_coordination"
    assert proposals[0]["routing_basis"] == ["neighbor_region"]
    _assert_chinese_display(proposals[0]["rationale"])
    assert "snake_case" in " ".join(runtime.llm.prompt["constraints"])


def test_runtime_reasoning_and_diffusion_fallback_copy_is_chinese():
    runtime = EnvFishRuntime.__new__(EnvFishRuntime)
    runtime.mechanism_graph = {"edges": [{"id": "edge_01", "mechanism": "agent_feedback"}]}
    runtime._now = lambda: "2026-07-13T00:00:00"
    reasoning = runtime._fallback_round_reasoning(
        round_num=1,
        active_variables=[],
        diffusion={},
        interactions={
            "new_dynamic_edges": [
                {"edge_id": "edge_02", "rationale": "Fallback relation from Agent_02."}
            ]
        },
        feedback={"turning_points": ["snapshot_transition"]},
        risk_runtime={"primary_active_risk_id": "risk_01"},
        snapshot={"vulnerability_ranking": [{"region_id": "Region_01", "name": "Region_01"}]},
    )
    _assert_chinese_display(reasoning["summary"])
    _assert_chinese_display(reasoning["activated_mechanisms"][0]["reason"])
    _assert_chinese_display(reasoning["relation_change_reasons"][0]["reason"])
    _assert_chinese_display(reasoning["uncertainty_notes"][0])
    _assert_chinese_display(reasoning["feedback_turning_points"][0])

    runtime.template_rules = {
        "default_decay": 0.5,
        "default_lag_rounds": 1,
        "default_persistence": 50,
        "max_neighbor_spread": 1,
    }
    runtime.region_graph = [{"region_id": "region_a"}]
    runtime._transport_edges_from_region = lambda _region_id: []
    diffusion = runtime._fallback_diffusion(
        1,
        [{"name": "Injected Variable", "target_regions": ["region_a"], "intensity_0_100": 50}],
        [],
    )
    _assert_chinese_display(diffusion["transfers"][0]["rationale"])


def test_api_stage_and_grounding_display_fallbacks_are_chinese():
    assert _prepare_stage_label("internal_stage_name") == "正在准备场景"
    labels = _grounding_source_labels(["openstreetmap", "internal_provider"])
    assert labels == ["开放地图", "外部资料"]
    assert all(_has_chinese(item) for item in labels)
