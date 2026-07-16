"""Focused contract tests for the unified semantic input boundary."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.semantic_input import SemanticArtifactStore, SemanticInputNormalizer
from app.services.scenario_planner import ScenarioPlanner


def _event_payload(input_id: str, **overrides):
    payload = {
        "input_id": input_id,
        "raw_text": "模型整理文本",
        "name": "模型事件",
        "description": "模型事件描述",
        "order": 1,
        "atomic_keys": ["typhoon"],
        "open_concept": "",
        "target_region_ids": [],
        "target_entity_ids": [],
        "target_labels": [],
        "time": {"start_round": None, "duration_rounds": None, "time_text": ""},
        "intensity": {"score": None, "direction": "", "label_zh": ""},
        "source_origin": "system_inference",
    }
    payload.update(overrides)
    return payload


def _policy_payload(input_id: str, **overrides):
    payload = {
        "input_id": input_id,
        "raw_text": "模型整理文本",
        "name": "模型政策",
        "intent": "模型政策意图",
        "order": 1,
        "action_primitives": ["governance_intervention"],
        "executor_capability_keys": [],
        "expected_effects": [],
        "target_event_keys": [],
        "target_region_ids": [],
        "target_entity_ids": [],
        "target_labels": [],
        "time": {"start_round": None, "duration_rounds": None, "time_text": ""},
        "intensity": {"score": None, "direction": "", "label_zh": ""},
        "source_origin": "system_inference",
    }
    payload.update(overrides)
    return payload


def _scene_output(*, events=None, policies=None):
    return {
        "scene": {
            "location": "香港",
            "time_scope": "",
            "stable_contexts": [],
            "analysis_boundaries": [],
            "questions": [],
            "known_entities": [],
            "simulation_requirement": "",
        },
        "events": events or [],
        "policies": policies or [],
        "assumptions": [],
    }


class SequenceLLM:
    model = "semantic-test-model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat_json(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)


@pytest.fixture(autouse=True)
def semantic_store_root(monkeypatch, tmp_path):
    monkeypatch.setattr(SemanticArtifactStore, "ROOT", str(tmp_path / "semantic_inputs"))


@pytest.mark.parametrize(
    "phrase",
    ["8号风球袭港", "香港挂八号", "T8 生效", "八号烈风或暴风信号现正生效"],
)
def test_wind_signal_paraphrases_share_controlled_weather_mechanisms(phrase):
    artifact = SemanticInputNormalizer(use_llm=False).normalize_scene(
        payload={"location": "香港", "event_or_baseline": phrase},
    )

    keys = set(artifact.events[0].atomic_keys)
    assert {"typhoon", "strong_wind", "traffic_pressure", "storm_surge"}.issubset(keys)
    assert artifact.authority == "draft"
    assert artifact.events[0].source_origin == "step1_suggestion"


@pytest.mark.parametrize(
    "phrase",
    ["停工停学", "学校停课，公司停工", "关闭学校和办公室"],
)
def test_policy_paraphrases_split_education_and_workplace_actions(phrase):
    artifact = SemanticInputNormalizer(use_llm=False).normalize_scenario(
        foundation={"location": "香港", "region_ids": []},
        event_inputs=[],
        policy_inputs=[{"input_id": "policy_1", "name": phrase, "intent": phrase}],
    )

    assert set(artifact.policies[0].action_primitives) >= {"school_closure", "workplace_shutdown"}
    assert "education_emergency_management" in artifact.policies[0].executor_capability_keys
    assert "workplace_safety_enforcement" in artifact.policies[0].executor_capability_keys


def test_wind_signal_and_shutdown_policy_produce_distinct_authority_demands():
    semantic = SemanticInputNormalizer(use_llm=False).normalize_scenario(
        foundation={"location": "香港", "region_ids": ["region_hk"]},
        event_inputs=[{"input_id": "event_t8", "name": "香港挂八号", "description": "T8 生效"}],
        policy_inputs=[{"input_id": "policy_close", "name": "停工停学", "intent": "关闭学校和办公室"}],
    )
    planning = ScenarioPlanner().build(
        foundation={"artifact_id": "foundation_hk", "location": "香港", "region_ids": ["region_hk"]},
        effort_snapshot_ref={
            "effort_snapshot_id": "effort_high",
            "effort_level": "high",
            "profile_version": "effort.v1",
            "content_hash": "effort-hash",
            "stage_budgets": {},
        },
        user_events=[item.model_dump(mode="json") for item in semantic.events],
        user_policies=[item.model_dump(mode="json") for item in semantic.policies],
        semantic_artifact_ref=semantic.ref().model_dump(mode="json"),
    )
    demand_keys = {item["demand_key"] for item in planning.role_demands}

    assert planning.contract_version == "scenario_planning.v2"
    assert "education_emergency_execution" in demand_keys
    assert "workplace_shutdown_execution" in demand_keys
    assert semantic.authority == "authoritative"
    assert planning.input_authority == "authoritative"


def test_scenario_configuration_does_not_revive_deleted_step1_policy():
    normalizer = SemanticInputNormalizer(use_llm=False)
    scene = normalizer.normalize_scene(
        payload={
            "location": "香港",
            "initial_variables": [
                {"input_id": "event_1", "type": "disaster", "name": "台风", "description": "台风增强"},
                {"input_id": "policy_1", "type": "policy", "name": "停课", "description": "学校停课"},
            ],
        }
    )
    assert scene.policies

    scenario = normalizer.normalize_scenario(
        foundation={"location": "香港", "region_ids": []},
        event_inputs=[{"input_id": "event_1", "name": "台风", "description": "台风增强"}],
        policy_inputs=[],
        previous_artifact_ref=scene.ref().model_dump(mode="json"),
    )

    assert scenario.authority == "authoritative"
    assert scenario.policies == []


def test_compound_scene_input_preserves_weather_event_when_llm_returns_only_policy():
    llm = SequenceLLM(_scene_output(policies=[_policy_payload(
        "compound_1",
        name="停工停学",
        intent="八号风球期间关闭学校和办公室",
        action_primitives=["school_closure", "workplace_shutdown"],
    )]))
    artifact = SemanticInputNormalizer(llm_client=llm).normalize_scene(payload={
        "location": "香港",
        "initial_variables": [{
            "input_id": "compound_1",
            "name": "8号风球袭港 + 停工停学",
            "description": "8号风球袭港 + 停工停学；重点关注学校、办公室与公共交通。",
        }],
    })

    assert [item.input_id for item in artifact.events] == ["compound_1"]
    assert {"typhoon", "strong_wind", "traffic_pressure", "storm_surge"}.issubset(
        artifact.events[0].atomic_keys
    )
    assert [item.input_id for item in artifact.policies] == ["compound_1"]
    assert set(artifact.policies[0].action_primitives) >= {"school_closure", "workplace_shutdown"}
    assert "typhoon" in artifact.policies[0].target_event_keys


def test_llm_can_reclassify_an_implicit_input_but_cannot_invent_input_ids():
    llm = SequenceLLM(_scene_output(
        events=[_event_payload("invented_event")],
        policies=[_policy_payload(
            "input_1",
            name="中小学居家教学安排",
            intent="降低学生集中活动",
            action_primitives=["school_closure"],
        )],
    ))
    artifact = SemanticInputNormalizer(llm_client=llm).normalize_scene(payload={
        "location": "香港",
        "initial_variables": [{
            "input_id": "input_1",
            "name": "红色响应安排",
            "description": "所有中小学转为居家教学",
        }],
    })

    assert artifact.events == []
    assert [item.input_id for item in artifact.policies] == ["input_1"]
    assert artifact.policies[0].action_primitives == ["school_closure"]


def test_explicit_structure_wins_over_llm_values_and_targets():
    llm = SequenceLLM(_scene_output(events=[_event_payload(
        "event_1",
        atomic_keys=["typhoon"],
        target_region_ids=["invented_region"],
        time={"start_round": 9, "duration_rounds": 9, "time_text": ""},
        intensity={"score": 5, "direction": "下降", "label_zh": "低"},
    )]))
    artifact = SemanticInputNormalizer(llm_client=llm).normalize_scenario(
        foundation={
            "location": "南山区",
            "region_ids": ["region_nanshan"],
            "target_catalog": [{"id": "region_nanshan", "name": "南山区", "kind": "region"}],
        },
        event_inputs=[{
            "input_id": "event_1",
            "type": "disaster",
            "name": "显式暴雨事件",
            "description": "暴雨扰动",
            "atomic_keys": ["heavy_rain"],
            "target_region_ids": ["region_nanshan"],
            "start_round": 0,
            "duration_rounds": 3,
            "intensity_0_100": 85,
            "direction": "上升",
            "expected_effects": ["排水系统负荷上升"],
        }],
        policy_inputs=[],
    )

    event = artifact.events[0]
    assert event.atomic_keys == ["heavy_rain"]
    assert event.target_region_ids == ["region_nanshan"]
    assert event.time.start_round == 0
    assert event.time.duration_rounds == 3
    assert event.intensity.score == 85
    assert event.intensity.direction == "上升"
    assert event.expected_effects == ["排水系统负荷上升"]
    planned_event = ScenarioPlanner.normalize_user_events([event.model_dump(mode="json")])[0]
    assert planned_event.intensity_score == 85
    assert planned_event.intensity_direction == "上升"
    assert planned_event.expected_effects == ["排水系统负荷上升"]


def test_invalid_llm_json_gets_one_repair_call_and_internal_audit():
    llm = SequenceLLM(
        {"unexpected": True},
        _scene_output(events=[_event_payload("event_1", atomic_keys=["heavy_rain"])]),
    )
    artifact = SemanticInputNormalizer(llm_client=llm).normalize_scenario(
        foundation={"location": "城区", "region_ids": []},
        event_inputs=[{"input_id": "event_1", "name": "强降水", "description": "城区水量快速增加"}],
        policy_inputs=[],
    )
    audit = SemanticArtifactStore.get_audit(artifact.artifact_id, artifact.revision)

    assert len(llm.calls) == 2
    assert audit["processing_mode"] == "llm_repaired"
    assert audit["repair_attempted"] is True


def test_target_resolution_handles_chinese_punctuation_aliases_duplicates_and_unknowns():
    artifact = SemanticInputNormalizer(use_llm=False).normalize_intervention(
        payload={
            "type": "policy",
            "name": "交通限制",
            "description": "对指定范围实施交通限制",
            "target_text": "南山区、后海湾；南山；不存在的设施",
            "start_round": 0,
            "duration_rounds": 2,
            "intensity_0_100": 70,
        },
        target_catalog=[
            {"id": "region_nanshan", "name": "南山区", "aliases": ["南山"], "kind": "region"},
            {"id": "entity_deep_bay", "name": "深圳湾口岸", "aliases": ["后海湾"], "kind": "entity"},
        ],
        default_region_ids=["region_nanshan"],
        current_round=8,
    )
    intervention = artifact.interventions[-1]
    audit = SemanticArtifactStore.get_audit(artifact.artifact_id, artifact.revision)

    assert intervention.target_region_ids == ["region_nanshan"]
    assert intervention.target_entity_ids == ["entity_deep_bay"]
    assert intervention.time.start_round == 0
    assert intervention.time.duration_rounds == 2
    assert intervention.action_primitives == ["transport_restriction"]
    assert "不存在的设施" in audit["unresolved_target_refs"]
    assert "不存在的设施" not in intervention.target_region_ids + intervention.target_entity_ids


def test_runtime_revision_preserves_prior_semantics_and_appends_interventions():
    normalizer = SemanticInputNormalizer(use_llm=False)
    scene = normalizer.normalize_scene(
        payload={"location": "香港", "event_or_baseline": "8号风球袭港"},
    )
    first_runtime = normalizer.normalize_intervention(
        payload={"type": "policy", "name": "停学", "description": "学校停课"},
        previous_artifact_ref=scene.ref().model_dump(mode="json"),
    )
    second_runtime = normalizer.normalize_intervention(
        payload={"type": "policy", "name": "停工", "description": "公司停工"},
        previous_artifact_ref=first_runtime.ref().model_dump(mode="json"),
    )

    assert second_runtime.artifact_id == scene.artifact_id
    assert second_runtime.revision == 3
    assert second_runtime.events[0].input_id == scene.events[0].input_id
    assert [item.action_primitives[0] for item in second_runtime.interventions] == [
        "school_closure",
        "workplace_shutdown",
    ]


def test_scene_revision_is_a_versioned_patch_not_a_fresh_reinterpretation():
    normalizer = SemanticInputNormalizer(use_llm=False)
    scene = normalizer.normalize_scene(
        payload={"location": "香港", "event_or_baseline": "8号风球袭港"},
    )
    with_policy = normalizer.normalize_revision(
        instruction="增加停工停学",
        previous_artifact_ref=scene.ref().model_dump(mode="json"),
    )
    with_intensity = normalizer.normalize_revision(
        instruction="将8号风球袭港强度改为80",
        previous_artifact_ref=with_policy.ref().model_dump(mode="json"),
    )

    assert with_policy.artifact_id == scene.artifact_id
    assert with_policy.revision == 2
    assert set(with_policy.policies[0].action_primitives) == {"school_closure", "workplace_shutdown"}
    assert len(with_intensity.events) == 1
    assert with_intensity.events[0].input_id == scene.events[0].input_id
    assert with_intensity.events[0].intensity.score == 80
    assert with_intensity.policies[0].input_id == with_policy.policies[0].input_id
