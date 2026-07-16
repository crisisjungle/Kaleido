from app.services.report_analysis import ReportAnalysisService


def test_intervention_tab_separates_execution_truth_from_causal_claims():
    service = ReportAnalysisService.__new__(ReportAnalysisService)
    service.artifacts = {
        "interventions": [
            {
                "intervention_id": "intervention_1",
                "round": 3,
                "label_zh": "临时关闭滨海步道",
                "description_zh": "降低游客进入高暴露区域的速度。",
            }
        ]
    }

    policy_events = [
        {
            "policy_execution_id": "policy_execution_1",
            "round_number": 2,
            "policy_label_zh": "加强近岸监测",
            "execution_status": "executed",
            "executor_agent_ids": [1],
            "target_region_ids": ["coast"],
            "state_effect_delta": {"response_capacity": 0.1},
            "summary_zh": "加强近岸监测已由绑定 Agent 在本轮执行。",
        },
        {
            "policy_execution_id": "policy_execution_2",
            "round_number": 4,
            "policy_label_zh": "扩大交通管制",
            "execution_status": "blocked",
            "blocking_reasons_zh": ["执行 Agent 的联合资源不足"],
            "summary_zh": "扩大交通管制本轮未生效。",
        },
    ]

    def read_jsonl(filename, default):
        if filename == "policy_execution_ledger.jsonl":
            return policy_events
        return default

    service._read_simulation_jsonl = read_jsonl
    payload = service._build_intervention_tab()

    assert payload["summary"] == {
        "policy_event_count": 2,
        "executed_count": 1,
        "blocked_count": 1,
        "intervention_count": 1,
    }
    assert payload["policy_events"][0]["status_label"] == "已执行"
    assert payload["policy_events"][1]["blocking_reasons"] == ["执行 Agent 的联合资源不足"]
    assert "没有对照分支" in payload["causality_boundary"]
