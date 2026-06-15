"""
Phase-A 测试：ontology_generator 的确定性 fallback（无 LLM / 离线）。

覆盖：
- fallback 产出比旧 3 类型 stub 更丰富的实体类型；
- 据场景需求命中相应的关系类型（关系是本体核心）；
- source 标记为 "deterministic_fallback"（诚实降级，取代旧 stub 的假日志）；
- 返回保留 api/graph.py 读取所需的键（entity_types/edge_types/analysis_summary）。

所有用例均通过强制 Config.LLM_API_KEY=None 走 fallback，无任何网络/LLM 调用。
"""

import pytest

from app.config import Config
from app.services.ontology_generator import OntologyGenerator


@pytest.fixture
def offline(monkeypatch):
    """强制走确定性 fallback：清空 LLM_API_KEY。"""
    monkeypatch.setattr(Config, "LLM_API_KEY", None, raising=False)
    return OntologyGenerator()


def test_fallback_richer_than_legacy_stub_and_tagged(offline):
    result = offline.generate(
        document_texts=["武汉某流域的渔业与水资源治理材料。"],
        simulation_requirement="探索疫情在城市人群中的传播与扩散，以及政策监管的调控作用。",
    )

    # 诚实降级标记，而非旧 stub 的假“调用 LLM”。
    assert result["source"] == "deterministic_fallback"

    # 比旧 3 类型 stub 丰富。
    entity_names = {e["name"] for e in result["entity_types"]}
    assert len(result["entity_types"]) > 3
    # 核心实体仍在。
    assert {"Actor", "Region", "Risk"}.issubset(entity_names)


def test_fallback_includes_scenario_relevant_relations(offline):
    result = offline.generate(
        document_texts=None,
        simulation_requirement=(
            "疫情传播扩散，资源争夺与短缺，政策监管调控，并存在阈值触发的崩溃拐点。"
        ),
    )

    edge_names = {e["name"] for e in result["edge_types"]}

    # 关系是本体核心：必含兜底 AFFECTS/LOCATED_IN。
    assert {"AFFECTS", "LOCATED_IN"}.issubset(edge_names)
    # 场景关键词应命中专属关系类型。
    assert "TRANSMITS_TO" in edge_names      # 传播/扩散
    assert "COMPETES_FOR" in edge_names      # 资源争夺/短缺
    assert "REGULATES" in edge_names         # 政策监管调控
    assert "TRIGGERS" in edge_names          # 阈值触发拐点

    # 关系携带复杂性词汇（channel/direction/sign）。
    for edge in result["edge_types"]:
        assert "channel" in edge
        assert edge["direction"] in {"directed", "undirected"}
        assert edge["sign"] in {"+", "-", "±", "0"}

    # 命中的关键词被如实记录。
    assert result["scenario_keywords"]


def test_return_preserves_caller_required_keys(offline):
    """api/graph.py 读取 entity_types/edge_types/analysis_summary —— 必须保留。"""
    result = offline.generate(simulation_requirement="任意需求")

    for key in ("entity_types", "edge_types", "analysis_summary"):
        assert key in result

    assert isinstance(result["entity_types"], list)
    assert isinstance(result["edge_types"], list)
    assert isinstance(result["analysis_summary"], str)
    assert result["analysis_summary"]  # 非空

    # 每个实体/关系条目都有 name（调用方 len() 计数即可用）。
    assert all("name" in e for e in result["entity_types"])
    assert all("name" in e for e in result["edge_types"])


def test_empty_input_still_yields_baseline_ontology(offline):
    """空输入也应给出比旧 stub 丰富的基线本体（含兜底关系）。"""
    result = offline.generate()

    assert result["source"] == "deterministic_fallback"
    assert len(result["entity_types"]) > 3
    edge_names = {e["name"] for e in result["edge_types"]}
    assert {"AFFECTS", "LOCATED_IN"}.issubset(edge_names)
