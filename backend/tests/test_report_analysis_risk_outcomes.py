from types import SimpleNamespace

from app.services.report_analysis import ReportAnalysisService


def _service():
    service = ReportAnalysisService.__new__(ReportAnalysisService)
    service.risk_artifacts = {
        "risk_definitions": [
            {
                "risk_id": "risk_flooding",
                "title": "低洼社区积水风险",
                "description": "强降雨可能使低洼社区积水。",
                "region_scope": ["低洼社区"],
                "mechanism_node_ids": ["rain"],
            },
            {
                "risk_id": "risk_supply",
                "title": "生活物资供应压力",
                "description": "道路受阻可能影响物资供应。",
                "region_scope": ["城区"],
            },
        ],
        "latest_risk_runtime_state": {
            "round": 8,
            "primary_active_risk_id": "risk_flooding",
            "risk_states": [
                {
                    "risk_id": "risk_flooding",
                    "status": "critical",
                    "runtime_tension": 81,
                    "tension_trace": [55, 67, 81],
                },
                {
                    "risk_id": "risk_emerged",
                    "status": "elevated",
                    "runtime_tension": 64,
                    "tension_trace": [48, 64],
                },
            ],
        },
        "risk_events": [
            {"id": "event_1", "risk_id": "risk_flooding", "round": 7, "event_type": "risk_escalation"}
        ],
        "risk_runtime_state": [],
    }
    service.artifacts = {"risk_objects": [], "risk_objects_summary": {}}
    service.latest_snapshot = {"round": 8}
    service.round_snapshots = []
    return service


def test_risk_outcomes_compare_definitions_runtime_and_emerged_risks():
    payload = _service()._build_risk_outcomes_tab()

    assert payload["tab"] == "risk-outcomes"
    assert payload["contract_version"] == "analysis-bundle.v2"
    outcomes = {item["risk_id"]: item for item in payload["risk_outcomes"]}
    assert outcomes["risk_flooding"]["outcome_label_zh"] == "持续增强"
    assert outcomes["risk_flooding"]["risk_events"][0]["id"] == "event_1"
    assert outcomes["risk_flooding"]["risk_event_count"] == 1
    assert outcomes["risk_flooding"]["lifecycle_status"] == "critical"
    assert outcomes["risk_supply"]["outcome_label_zh"] == "未被验证"
    assert outcomes["risk_emerged"]["outcome_label_zh"] == "运行中新出现"
    assert payload["status_counts"] == {"emerged": 1, "increasing": 1, "unverified": 1}
    assert payload["analysis_bundle"]["risk_outcomes"] == payload["risk_outcomes"]


def test_risk_outcomes_do_not_mark_declining_trace_as_increasing():
    service = _service()
    service.risk_artifacts["latest_risk_runtime_state"]["risk_states"][0].update({
        "status": "elevated",
        "runtime_tension": 48,
        "tension_trace": [72, 61, 48],
    })

    payload = service._build_risk_outcomes_tab()
    flooding = next(item for item in payload["risk_outcomes"] if item["risk_id"] == "risk_flooding")

    assert flooding["outcome_label_zh"] == "得到缓解"


def test_analysis_bundle_connects_findings_turning_points_scope_and_evidence():
    service = _service()
    service.report_id = "report_1"
    service.simulation_id = "simulation_1"
    service.report = SimpleNamespace(status=SimpleNamespace(value="completed"))
    service._get_default_round = lambda: 8
    service._build_narrative_tab = lambda: {
        "rounds": [{
            "round": 8,
            "headline": "服务压力持续上升",
            "amplifier": "道路受阻放大了供应压力。",
            "top_region": {"name": "低洼社区"},
            "uncertainty": "尚无对照分支。",
            "turning_points": ["第 8 轮道路中断后风险加速。"],
        }],
    }
    service._build_risk_outcomes_tab = lambda: {
        "latest_round": 8,
        "risk_outcomes": [{
            "risk_id": "risk_supply",
            "affected_regions": ["低洼社区"],
            "affected_subjects": ["居民", "物流企业"],
        }],
        "analysis_boundary": "风险结果来自运行账本。",
    }
    service._build_intervention_tab = lambda: {
        "policy_events": [{"id": "policy_1", "status": "executed"}],
        "interventions": [],
        "causality_boundary": "没有对照分支时不表述为确定因果。",
    }
    service._load_graph_data = lambda: {
        "nodes": [{
            "uuid": "node_1",
            "name": "道路中断",
            "attributes": {"evidence_refs": [{"label": "运行记录"}]},
        }],
    }

    payload = service._build_analysis_bundle_tab()
    bundle = payload["analysis_bundle"]

    assert payload["tab"] == "analysis-bundle"
    assert bundle["executive_findings"][0]["title"] == "服务压力持续上升"
    assert bundle["turning_points"][0]["round"] == 8
    assert bundle["impact_scope"]["region_count"] == 1
    assert bundle["impact_scope"]["subject_count"] == 2
    assert bundle["evidence_index"][0]["node_name"] == "道路中断"
    assert len(bundle["uncertainty_boundaries"]) == 3
