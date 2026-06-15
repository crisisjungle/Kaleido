"""M2 deepening tests for scene_material_generator.

These tests exercise the machine-enforced variable discipline (perturbation gate)
and the honest no-LLM fallback skeleton. They run on the deterministic / fallback
path only and require no LLM or network access (use_llm=False).
"""

import os

from app.services import scene_material_generator as smg
from app.services.scene_material_generator import (
    SceneMaterialGenerator,
    _classify_variable,
    _is_true_perturbation_variable,
    _normalize_initial_variables,
    _split_variables_by_role,
)


def _generator():
    # use_llm=False guarantees the no-LLM fallback path; no network is touched.
    return SceneMaterialGenerator(use_llm=False)


def test_baseline_pseudo_variable_excluded_real_perturbation_kept():
    """A weather-baseline pseudo-variable is demoted to stable-context, while a
    variable carrying genuine change semantics stays in the perturbation track."""
    baseline = {"name": "基线气温", "type": "weather", "description": "当前观测气温稳态背景"}
    perturbation = {
        "name": "极端暴雨",
        "type": "weather",
        "description": "短时强降雨大幅上升，冲击排水系统",
    }

    assert _is_true_perturbation_variable(baseline) is False
    assert _is_true_perturbation_variable(perturbation) is True

    perturbations, stable_context = _split_variables_by_role([baseline, perturbation])

    kept_names = {item["name"] for item in perturbations}
    demoted_names = {item["name"] for item in stable_context}
    assert "极端暴雨" in kept_names
    assert "基线气温" not in kept_names
    assert "基线气温" in demoted_names

    # Classification is additive and honest: role + a change signal is annotated.
    classified = _classify_variable(perturbation)
    assert classified["epistemic_role"] == "perturbation"
    assert classified.get("direction") or classified.get("intensity")

    demoted = _classify_variable(baseline)
    assert demoted["epistemic_role"] == "stable_context"
    assert "context_reason" in demoted


def test_bare_observation_without_change_semantics_is_demoted():
    """A variable with no direction / intensity / action verb is NOT a perturbation,
    even when it slips past the narrow weather-baseline guard."""
    # Not weather, not flagged 基线 -> old guard passes it, new gate must still demote.
    bare = {"name": "当前人口数量", "type": "resource", "description": "区域常住人口规模"}
    assert _is_true_perturbation_variable(bare) is False

    intervention = {"name": "限行政策", "type": "policy", "description": "对核心区机动车实施管制"}
    assert _is_true_perturbation_variable(intervention) is True

    normalized = _normalize_initial_variables([bare, intervention])
    roles = {item["name"]: item["epistemic_role"] for item in normalized}
    assert roles["当前人口数量"] == "stable_context"
    assert roles["限行政策"] == "perturbation"


def test_fallback_skeleton_labels_missing_sections_and_omits_fabricated_prose():
    """The no-LLM fallback must be an honest skeleton: it labels synthesis sections
    as not-generated and must NOT contain the old fabricated generic relationship /
    subject / metric prose that downstream extraction would treat as fact."""
    gen = _generator()
    assert gen.llm_client is None  # no-LLM path guaranteed

    input_bundle = {
        "scene_id": "scene_test",
        "scene_type": "stable_environment",
        "location": "测试湖区",
        "time_scope": "2026 春季",
        "event_or_baseline": "湖区水质稳态",
        "focus": "水体与周边社区关系",
        "simulation_requirement": "",
        "additional_context": "",
        "known_entities": "湖区管理处",
        "analysis_boundaries": "",
        "report_questions": "",
        "document_texts": [],
        "uploaded_files": [],
        "selected_points": [],
        "initial_variables": _normalize_initial_variables(
            [{"name": "污染泄漏", "description": "上游污染物大幅排放泄漏"}]
        ),
        "map_context": {},
        "created_at": "2026-06-15T00:00:00",
    }

    generated = gen._fallback_generate(input_bundle)
    report = generated["report_markdown"]

    # Honest skeleton marker present, and synthesis sections are explicitly labeled.
    assert generated.get("fallback_mode") == "honest_skeleton"
    assert smg.SceneMaterialGenerator._LLM_REQUIRED_SECTION_LABEL in report
    assert "关键关系网络" in report
    # The relation section line must carry the not-generated label, not real prose.
    assert "## 7. 关键关系网络: 未生成（需 LLM）" in report

    # The OLD fabricated generic prose must be gone (would pollute downstream facts).
    fabricated_phrases = [
        "主区域承载居民、管理者、设施运营者和环境受体",
        "交通、人流、物资流和信息流连接区域内外主体",
        "管理主体：负责监测、管控、维护、通告和资源协调",
        "区域暴露水平、设施负荷、生态完整性",
        "将风险、压力、信任、舆情和稳定性作为状态指标",
    ]
    for phrase in fabricated_phrases:
        assert phrase not in report, f"fallback still fabricates: {phrase}"

    # User-confirmed input IS echoed (the only thing the skeleton is allowed to assert).
    assert "测试湖区" in report
    assert "湖区管理处" in report

    # The real perturbation survived the gate into initial_variables.
    assert any(v["name"] == "污染泄漏" for v in generated["initial_variables"])


def test_compose_no_llm_persists_honest_skeleton(monkeypatch, tmp_path):
    """End-to-end no-LLM compose() yields a seed whose initial_variables passed the
    gate and whose report is the honest skeleton (additive keys present)."""
    seeds_dir = os.path.join(str(tmp_path), "scene_seeds")
    monkeypatch.setattr(SceneMaterialGenerator, "SCENE_SEEDS_DIR", seeds_dir)

    gen = _generator()
    payload = {
        "scene_type": "historical_event",
        "location": "测试城区",
        "initial_variables": [
            {"name": "极端高温", "description": "持续高温大幅上升"},
            {"name": "基线湿度", "description": "当前观测湿度背景"},
        ],
    }
    seed = gen.compose(payload=payload, uploaded_files=[])

    perturbation_names = {v["name"] for v in seed["initial_variables"]}
    context_names = {v["name"] for v in seed.get("stable_context_variables", [])}
    assert "极端高温" in perturbation_names
    assert "基线湿度" not in perturbation_names
    assert "基线湿度" in context_names

    assert seed.get("fallback_mode") == "honest_skeleton"
    assert SceneMaterialGenerator._LLM_REQUIRED_SECTION_LABEL in seed["report_markdown"]

    # Seed was persisted and is re-readable via the public accessor.
    reloaded = SceneMaterialGenerator.get_seed(seed["scene_id"])
    assert reloaded is not None
    assert reloaded["scene_id"] == seed["scene_id"]
