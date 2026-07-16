from app.services.workflow_artifacts import (
    ANALYSIS_BUNDLE_CONTRACT_VERSION,
    RUNTIME_LEDGER_CONTRACT_VERSION,
    SCENARIO_DEFINITION_CONTRACT_VERSION,
    project_analysis_bundle,
    project_runtime_ledger,
    project_background_foundation,
    project_scenario_definition,
)


def _planning_input():
    return {
        "contract_version": "scenario-planning.v2",
        "planning_input_id": "scenario_plan_1",
        "foundation_ref": {"artifact_id": "foundation_1", "region_ids": ["coast"]},
        "effort_snapshot_ref": {"effort_snapshot_id": "effort_1"},
        "normalized_user_events": [
            {"input_id": "event_input_1", "name": "风暴潮", "target_region_ids": ["coast"]}
        ],
        "event_mechanism_graph": {
            "nodes": [{"event_id": "event_1", "label_zh": "风暴潮影响"}],
            "edges": [],
        },
        "temporal_plan": {
            "total_rounds": 12,
            "event_windows": [{"event_id": "event_1", "start_round": 1, "duration_rounds": 12}],
        },
        "role_demands": [],
        "policy_plan": [],
    }


def test_scenario_definition_projects_readiness_without_inventing_required_risks():
    payload = project_scenario_definition(
        _planning_input(),
        {
            "region_graph": [{"region_id": "coast", "name": "沿海区域"}],
            "risk_definitions": [],
        },
    )

    assert payload["contract_version"] == SCENARIO_DEFINITION_CONTRACT_VERSION
    assert payload["readiness_summary"]["ready"] is True
    assert payload["readiness_summary"]["blocking_count"] == 0
    risk_check = next(item for item in payload["readiness_checks"] if item["key"] == "risk_references")
    assert risk_check["status"] == "pass"
    assert "不会阻止推演" in risk_check["summary_zh"]


def test_background_foundation_preserves_step1_semantics_and_spatial_catalog():
    payload = project_background_foundation({
        "artifact_id": "foundation_1",
        "location": "深圳湾",
        "region_ids": ["coast"],
        "target_catalog": [{"id": "coast", "name": "沿海区域", "kind": "region"}],
        "scene_semantics": {
            "stable_contexts": ["常住人口与旅游人口叠加"],
            "time_scope": "台风登陆前后 48 小时",
            "known_entities": ["口岸"],
            "questions": ["交通与公共服务如何承压？"],
            "analysis_boundaries": ["不预测具体人员伤亡"],
        },
        "semantic_artifact_ref": {"artifact_id": "semantic_1", "revision": 2},
    })

    assert payload["area_of_interest"]["location"] == "深圳湾"
    assert payload["spatial_anchors"][0]["name"] == "沿海区域"
    assert payload["baseline_state"]["stable_contexts"] == ["常住人口与旅游人口叠加"]
    assert payload["research_questions"] == ["交通与公共服务如何承压？"]
    assert payload["analysis_boundaries"] == ["不预测具体人员伤亡"]
    assert payload["source_refs"][0]["artifact_id"] == "semantic_1"


def test_scenario_definition_blocks_dangling_mechanism_edges():
    planning = _planning_input()
    planning["event_mechanism_graph"]["edges"] = [
        {"edge_id": "edge_1", "source_event_id": "event_1", "target_event_id": "missing_event"}
    ]

    payload = project_scenario_definition(planning, {"region_graph": [{"region_id": "coast"}]})

    assert payload["readiness_summary"]["ready"] is False
    mechanism_check = next(item for item in payload["readiness_checks"] if item["key"] == "mechanism_graph")
    assert mechanism_check["blocking"] is True
    assert mechanism_check["target_tab"] == "mechanism"


def test_runtime_ledger_keeps_existing_ledgers_under_one_versioned_projection():
    payload = project_runtime_ledger({
        "round_snapshots": [{"round": 1}],
        "relationship_events": [{"round": 1, "event": "formed"}],
        "policy_execution_events": [{"round_number": 1, "execution_status": "executed"}],
        "latest_risk_runtime_state": {"round": 1, "risk_states": []},
    })

    assert payload["contract_version"] == RUNTIME_LEDGER_CONTRACT_VERSION
    assert payload["round_snapshots"] == [{"round": 1}]
    assert payload["relationship_event_ledger"][0]["event"] == "formed"
    assert payload["policy_execution_ledger"][0]["execution_status"] == "executed"
    assert ANALYSIS_BUNDLE_CONTRACT_VERSION == "analysis-bundle.v2"


def test_analysis_bundle_keeps_impact_scope_with_evidence_and_boundaries():
    payload = project_analysis_bundle(
        executive_findings=[{"finding_id": "finding_1", "title": "服务压力持续上升"}],
        impact_scope={"region_count": 2, "subject_count": 3},
        evidence_index=[{"evidence_id": "evidence_1"}],
        uncertainty_boundaries=["当前结果不代表确定因果。"],
    )

    assert payload["contract_version"] == ANALYSIS_BUNDLE_CONTRACT_VERSION
    assert payload["impact_scope"] == {"region_count": 2, "subject_count": 3}
    assert payload["evidence_index"][0]["evidence_id"] == "evidence_1"
    assert payload["uncertainty_boundaries"] == ["当前结果不代表确定因果。"]
