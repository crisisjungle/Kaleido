import json

import pytest

from app.services.risk_definition_builder import RiskDefinitionBuilder
from app.config import Config


class CandidateAwareLLM:
    def __init__(self, mode="valid"):
        self.mode = mode
        self.calls = []

    def chat_json(self, *, messages, temperature, max_tokens):
        self.calls.append({"messages": messages, "temperature": temperature, "max_tokens": max_tokens})
        if self.mode == "timeout":
            raise TimeoutError("命名服务超时")
        if self.mode == "invalid_json":
            return {"items": "not-an-array"}

        request = json.loads(messages[-1]["content"])
        items = []
        for candidate in request["candidates"]:
            receptor = candidate["receptor_name"]
            item = {
                "risk_id": candidate["risk_id"],
                "title": f"{receptor}现实暴露风险",
                "summary": f"已校验机制路径正在作用于{receptor}，需要持续监测具体后果。",
                "consequence": f"{receptor}的安全与连续性受到影响。",
                "primary_family": "health_safety",
                "tags": ["场景特异", "真实受体"],
                "reason": "标题保留了真实受体并概括已校验机制。",
                "mechanism_node_ids": list(candidate["mechanism_node_ids"]),
                "mechanism_edge_ids": list(candidate["mechanism_edge_ids"]),
            }
            if self.mode == "no_suffix":
                item["title"] = f"{receptor}现实暴露"
            if self.mode == "changed_reference":
                item["mechanism_edge_ids"] = ["fake_edge"]
            if self.mode == "changed_family":
                item["primary_family"] = "ecological_environment"
            if self.mode == "fake_entity":
                item["entity_refs"] = [{"entity_uuid": "fake", "entity_name": "不存在医院"}]
            items.append(item)
        return {"items": items}


def _build(llm):
    return RiskDefinitionBuilder(llm_client=llm).build(
        risk_contract_version=2,
        simulation_requirement="模拟风暴潮通过海水倒灌影响滨海区居民。",
        regions=[{"region_id": "coast", "name": "滨海区"}],
        entities=[{"uuid": "resident", "name": "滨海区居民"}],
        profiles=[],
        mechanism_graph={
            "nodes": [
                {"id": "source", "name": "风暴潮", "node_type": "source", "confidence": 0.9},
                {"id": "process", "name": "海水倒灌", "node_type": "process", "confidence": 0.85},
                {"id": "resident", "name": "滨海区居民", "node_type": "human", "confidence": 0.8},
            ],
            "edges": [
                {"id": "edge_1", "source": "source", "target": "process", "mechanism": "风暴潮推动海水进入滨海区", "evidence": ["滨海区潮位记录"], "confidence": 0.9},
                {"id": "edge_2", "source": "process", "target": "resident", "mechanism": "海水倒灌增加居民暴露", "evidence": ["滨海区居民记录"], "confidence": 0.85},
            ],
        },
    )


def test_llm_only_names_validated_candidates_at_fixed_temperature():
    llm = CandidateAwareLLM()
    result = _build(llm)

    assert result.risk_definitions
    risk = result.risk_definitions[0]
    assert result.generation_audit["llm_participation"] == "live"
    assert result.generation_audit["llm_fallback_rate"] == 0
    assert risk["generation_mode"] == "mechanism_graph_hybrid"
    assert risk["title"] == "滨海区居民现实暴露风险"
    assert risk["mechanism_node_ids"] == ["source", "process", "resident"]
    assert risk["mechanism_edge_ids"] == ["edge_1", "edge_2"]
    assert llm.calls[0]["temperature"] == 0.2


def test_llm_title_is_normalized_to_a_risk_object_name():
    result = _build(CandidateAwareLLM("no_suffix"))

    assert result.risk_definitions[0]["title"] == "滨海区居民现实暴露风险"


@pytest.mark.parametrize("mode", ["timeout", "invalid_json", "changed_reference", "changed_family", "fake_entity"])
def test_llm_failure_or_reference_mutation_uses_deterministic_fallback(mode):
    result = _build(CandidateAwareLLM(mode))

    assert result.risk_definitions
    risk = result.risk_definitions[0]
    assert result.generation_audit["llm_participation"] == "deterministic_fallback"
    assert result.generation_audit["llm_fallback_rate"] == 1
    assert "llm_naming_fallback" in result.generation_audit["quality_flags"]
    assert risk["generation_mode"] == "mechanism_graph_deterministic"
    assert risk["title"] == "滨海区居民暴露与健康风险"
    assert risk["mechanism_node_ids"] == ["source", "process", "resident"]
    assert risk["mechanism_edge_ids"] == ["edge_1", "edge_2"]
    assert "不存在医院" not in json.dumps(risk, ensure_ascii=False)


def test_missing_llm_configuration_is_recorded_as_a_named_fallback(monkeypatch):
    monkeypatch.setattr(Config, "LLM_API_KEY", "")

    result = _build(None)

    assert result.generation_audit["llm_participation"] == "not_configured"
    assert result.generation_audit["llm_fallback_reason"] == "llm_client_unavailable"
    assert result.generation_audit["llm_fallback_rate"] == 1
    assert "llm_naming_fallback" in result.risk_definitions[0]["quality_flags"]
