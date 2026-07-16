from app.services.workflow_artifacts import (
    ANALYSIS_BUNDLE_CONTRACT_VERSION,
    BACKGROUND_FOUNDATION_CONTRACT_VERSION,
    RUNTIME_LEDGER_CONTRACT_VERSION,
    SCENARIO_DEFINITION_CONTRACT_VERSION,
    project_analysis_bundle,
    project_background_foundation,
    project_runtime_ledger,
    project_scenario_definition,
)


def _formal_v2_fixture():
    mechanism_nodes = [
        {"event_id": f"mechanism_{index}", "label_zh": f"机制节点 {index}"}
        for index in range(1, 13)
    ]
    mechanism_edges = [
        {
            "edge_id": f"edge_{index}",
            "source_event_id": f"mechanism_{index}",
            "target_event_id": f"mechanism_{index + 1}",
        }
        for index in range(1, 12)
    ]
    regions = [
        {"region_id": f"region_{index}", "name": f"区域 {index}"}
        for index in range(1, 13)
    ]
    agents = [
        {
            "agent_id": f"agent_{index}",
            "name": f"主体 {index}",
            "primary_region": regions[(index - 1) % len(regions)]["region_id"],
        }
        for index in range(1, 241)
    ]
    planning = {
        "contract_version": "scenario-planning.v2",
        "planning_input_id": "acceptance_scenario_1",
        "foundation_ref": {
            "artifact_id": "acceptance_foundation_1",
            "location": "验收区域",
            "region_ids": [item["region_id"] for item in regions],
        },
        "effort_snapshot_ref": {"effort_snapshot_id": "effort_ultra_1"},
        "normalized_user_events": [{
            "input_id": "event_1",
            "name": "复合扰动",
            "target_region_ids": ["region_1"],
        }],
        "event_mechanism_graph": {
            "nodes": mechanism_nodes,
            "edges": mechanism_edges,
        },
        "temporal_plan": {
            "total_rounds": 100,
            "event_windows": [{"event_id": "event_1", "start_round": 1, "duration_rounds": 100}],
        },
        "role_demands": [],
        "policy_plan": [],
    }
    config = {
        "region_graph": regions,
        "agent_configs": agents,
        "agent_relationship_graph": [
            {"relationship_id": f"relationship_{index}", "source": f"agent_{index}", "target": f"agent_{index + 1}"}
            for index in range(1, 240)
        ],
        "agent_plan": {"generation_audit": {"covered_role_demand_count": 0}},
        "risk_definitions": [],
    }
    return planning, config


def test_formal_v2_fixture_preserves_scale_zero_risk_and_report_delivery():
    planning, config = _formal_v2_fixture()
    foundation = project_background_foundation(
        planning["foundation_ref"],
        effort_snapshot_ref=planning["effort_snapshot_ref"],
    )
    scenario = project_scenario_definition(planning, config)
    ledger = project_runtime_ledger({
        "round_snapshots": [{"round": index} for index in range(1, 101)],
        "relationship_events": [{"round": 50, "event": "strengthened"}],
        "agent_action_decisions": [{"round": 50, "agent_id": "agent_1", "status": "selected"}],
        "latest_risk_runtime_state": {"round": 100, "risk_states": []},
        "risk_events": [],
    })
    analysis = project_analysis_bundle(
        executive_findings=[{"finding_id": "finding_1", "title": "系统完成 100 轮演化"}],
        turning_points=[{"turning_point_id": "turn_50", "round": 50, "summary": "主体关系在第 50 轮增强。"}],
        risk_outcomes=[],
        impact_scope={"region_count": 12, "subject_count": 240},
        evidence_index=[{"evidence_id": "evidence_1", "round": 50}],
        uncertainty_boundaries=["零风险表示没有风险假设通过证据校验，不表示现实世界绝对安全。"],
        report_artifact_ref={"report_id": "report_acceptance_1", "status": "completed", "formats": ["markdown", "print_pdf"]},
    )

    assert foundation["contract_version"] == BACKGROUND_FOUNDATION_CONTRACT_VERSION
    assert foundation["effort_snapshot_ref"]["effort_snapshot_id"] == "effort_ultra_1"
    assert scenario["contract_version"] == SCENARIO_DEFINITION_CONTRACT_VERSION
    assert len(scenario["mechanism_graph"]["nodes"]) == 12
    assert len(scenario["mechanism_graph"]["edges"]) == 11
    assert len(scenario["agent_profiles"]) == 240
    assert len(scenario["initial_relationships"]) == 239
    assert scenario["risk_definitions"] == []
    assert scenario["readiness_summary"] == {
        "blocking_count": 0,
        "warning_count": 0,
        "pass_count": 7,
        "ready": True,
    }
    assert ledger["contract_version"] == RUNTIME_LEDGER_CONTRACT_VERSION
    assert len(ledger["round_snapshots"]) == 100
    assert ledger["risk_runtime_state"]["risk_states"] == []
    assert analysis["contract_version"] == ANALYSIS_BUNDLE_CONTRACT_VERSION
    assert analysis["risk_outcomes"] == []
    assert analysis["impact_scope"] == {"region_count": 12, "subject_count": 240}
    assert analysis["report_artifact_ref"]["formats"] == ["markdown", "print_pdf"]
