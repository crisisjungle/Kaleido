from app.services.risk_candidate_extractor import RiskCandidateExtractionResult
from app.services.risk_emergence_detector import RiskEmergenceDetector


def _runtime_inputs():
    return {
        "active_variables": [
            {
                "variable_id": "storm_runtime",
                "name": "突发风暴潮",
                "description": "突发风暴潮进入滨海区。",
                "target_regions": ["coast"],
                "intensity_0_100": 90,
            }
        ],
        "regions": [
            {"region_id": "coast", "name": "滨海区", "region_type": "coastal_zone"},
            {"region_id": "port", "name": "港口区", "region_type": "infrastructure"},
        ],
        "transport_edges": [
            {
                "edge_id": "runtime_transport_coast_port",
                "source_region_id": "coast",
                "target_region_id": "port",
                "channel_type": "marine_current",
                "confidence": 0.85,
            }
        ],
        "profiles": [],
        "agent_relationships": [],
    }


def test_candidate_must_persist_two_rounds_before_emerging():
    detector = RiskEmergenceDetector()
    round_one = detector.detect(
        existing_definitions=[],
        previous_runtime_bundle={},
        current_round=1,
        **_runtime_inputs(),
    )
    assert round_one.created_risk_ids == []
    assert round_one.candidate_state
    assert all(item["consecutive_rounds"] == 1 for item in round_one.candidate_state.values())

    round_two = detector.detect(
        existing_definitions=[],
        previous_runtime_bundle={
            "emergence_candidates": round_one.candidate_state,
            "risk_states": [],
        },
        current_round=2,
        **_runtime_inputs(),
    )
    assert round_two.created_risk_ids
    assert all(item["created_round"] == 2 for item in round_two.risk_definitions)
    assert all(item["generation_mode"] == "runtime_emergent_deterministic" for item in round_two.risk_definitions)
    assert all(item["event_type"] == "risk_emerged" for item in round_two.events)


def test_single_round_noise_never_emerges():
    detector = RiskEmergenceDetector()
    round_one = detector.detect(
        existing_definitions=[],
        previous_runtime_bundle={},
        current_round=1,
        **_runtime_inputs(),
    )
    round_two = detector.detect(
        existing_definitions=[],
        previous_runtime_bundle={"emergence_candidates": round_one.candidate_state},
        current_round=2,
        active_variables=[],
        regions=_runtime_inputs()["regions"],
        transport_edges=_runtime_inputs()["transport_edges"],
        profiles=[],
        agent_relationships=[],
    )
    assert round_two.created_risk_ids == []
    assert round_two.events == []


def test_runtime_agent_coordination_cycle_never_enters_emergence_state():
    result = RiskEmergenceDetector().detect(
        existing_definitions=[],
        previous_runtime_bundle={},
        current_round=1,
        active_variables=[],
        regions=[
            {"region_id": "coast", "name": "滨海区"},
            {"region_id": "port", "name": "港口区"},
            {"region_id": "city", "name": "中心城区"},
        ],
        transport_edges=[],
        profiles=[
            {"agent_id": 1, "name": "滨海区应急协调员", "primary_region": "滨海区", "profession": "应急协调员"},
            {"agent_id": 2, "name": "港口区应急协调员", "primary_region": "港口区", "profession": "应急协调员"},
            {"agent_id": 3, "name": "中心城区应急协调员", "primary_region": "中心城区", "profession": "应急协调员"},
        ],
        agent_relationships=[
            {
                "edge_id": f"dynamic::{source}::{target}::governance_coordination",
                "source_agent_id": source,
                "target_agent_id": target,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": [evidence],
            }
            for source, target, evidence in (
                (1, 2, "滨海区与港口区临时协调记录"),
                (2, 3, "港口区与中心城区临时协调记录"),
                (3, 1, "中心城区与滨海区临时协调记录"),
            )
        ],
    )

    assert result.created_risk_ids == []
    assert result.candidate_state == {}
    assert result.events == []
    rejection = next(
        item
        for item in result.candidate_ledger
        if item.get("reason") == "纯主体协同关系闭环不构成风险因果反馈"
    )
    assert rejection["status"] == "rejected"
    assert rejection["rejected_candidate_count"] >= 1
    assert rejection["source"] == "runtime_candidate_extraction"


def test_runtime_agent_coordination_chain_never_enters_emergence_state():
    result = RiskEmergenceDetector().detect(
        existing_definitions=[],
        previous_runtime_bundle={},
        current_round=1,
        active_variables=[],
        regions=[
            {"region_id": "coast", "name": "滨海区"},
            {"region_id": "port", "name": "港口区"},
            {"region_id": "city", "name": "中心城区"},
        ],
        transport_edges=[],
        profiles=[
            {"agent_id": 1, "name": "滨海区应急协调员", "primary_region": "滨海区", "profession": "应急协调员"},
            {"agent_id": 2, "name": "港口区应急协调员", "primary_region": "港口区", "profession": "应急协调员"},
            {"agent_id": 3, "name": "中心城区应急协调员", "primary_region": "中心城区", "profession": "应急协调员"},
        ],
        agent_relationships=[
            {
                "edge_id": "dynamic::1::2::governance_coordination",
                "source_agent_id": 1,
                "target_agent_id": 2,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["滨海区与港口区临时协调记录"],
            },
            {
                "edge_id": "dynamic::2::3::governance_coordination",
                "source_agent_id": 2,
                "target_agent_id": 3,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["港口区与中心城区临时协调记录"],
            },
        ],
    )

    assert result.created_risk_ids == []
    assert result.candidate_state == {}
    assert result.events == []
    rejection = next(
        item
        for item in result.candidate_ledger
        if item.get("reason") == "纯主体关系路径缺少压力源、传播过程和真实受体"
    )
    assert rejection["status"] == "rejected"
    assert rejection["rejected_candidate_count"] >= 1
    assert rejection["source"] == "runtime_candidate_extraction"


def test_high_evidence_high_impact_candidate_emerges_immediately(monkeypatch):
    candidate = {
        "risk_contract_version": 2,
        "risk_id": "risk_v2_immediate",
        "source_signature": "immediate_signature",
        "title": "港口应急通行中断风险",
        "primary_family": "mobility_logistics",
        "priority_score": 88,
        "evidence_strength_score": 86,
        "impact_score": 91,
        "mechanism_edge_ids": ["runtime_edge_1"],
        "risk_statement": {
            "trigger_variable_ids": ["storm_runtime"],
            "source_node_ids": ["variable::storm_runtime"],
            "receptor_node_ids": ["port"],
            "receptor_name": "港口应急通道",
        },
    }
    monkeypatch.setattr(
        "app.services.risk_emergence_detector.RiskCandidateExtractor.extract",
        lambda self, **kwargs: RiskCandidateExtractionResult(definitions=[candidate]),
    )

    result = RiskEmergenceDetector().detect(
        existing_definitions=[],
        previous_runtime_bundle={},
        current_round=3,
        **_runtime_inputs(),
    )
    assert result.created_risk_ids == ["risk_v2_immediate"]
    assert result.events[0]["immediate"] is True


def _definition(index, priority):
    return {
        "risk_id": f"risk_{index}",
        "title": f"风险对象{index}",
        "priority_score": priority,
        "risk_statement": {"receptor_name": f"受体{index}"},
    }


def test_full_capacity_replaces_only_watch_object_with_ten_point_lead():
    detector = RiskEmergenceDetector()
    definitions = [_definition(index, 20 + index) for index in range(8)]
    runtime_states = {item["risk_id"]: {"status": "watch"} for item in definitions}
    candidate = _definition("new", 31)

    admitted, dormant_id = detector._admit_candidate(candidate, definitions, runtime_states)
    assert admitted is True
    assert dormant_id == "risk_0"
    assert definitions[0]["lifecycle_status"] == "dormant"

    insufficient = [_definition(index, 20 + index) for index in range(8)]
    admitted, dormant_id = detector._admit_candidate(_definition("weak", 29), insufficient, runtime_states)
    assert admitted is False
    assert dormant_id == ""

    protected = [_definition(index, 20 + index) for index in range(8)]
    elevated_states = {item["risk_id"]: {"status": "elevated"} for item in protected}
    admitted, dormant_id = detector._admit_candidate(_definition("strong", 99), protected, elevated_states)
    assert admitted is False
    assert dormant_id == ""
