from app.services.env_simulation_config_generator import EnvSimulationConfigGenerator


class _ForbiddenLegacyLlm:
    def chat_json(self, **_kwargs):
        raise AssertionError("ScenarioPlanner 正常路径不应再次调用旧配置 LLM")


def _has_chinese(value):
    return any("\u3400" <= char <= "\u9fff" for char in str(value or ""))


def test_scenario_planner_config_persists_chinese_display_fields_only():
    mechanism_graph = {
        "graph_id": "mechanism_graph_localization",
        "nodes": [
            {
                "event_id": "event_typhoon",
                "label_zh": "台风登陆",
                "description_zh": "台风影响沿海设施。",
            },
            {
                "event_id": "event_release",
                "label_zh": "放射性释放",
                "description_zh": "设施失效后发生放射性释放。",
            },
        ],
        "edges": [
            {
                "mechanism_id": "mechanism_typhoon_release",
                "source_event_id": "event_typhoon",
                "target_event_id": "event_release",
                "label_zh": "设施失效触发释放",
                "propagation_medium": "system_coupling",
                "confidence": 0.76,
            }
        ],
        "primary_event_ids": ["event_typhoon"],
        "branching_event_ids": [],
        "assumptions": [],
    }
    temporal_plan = {
        "plan_id": "temporal_localization",
        "step_unit": "hour",
        "step_unit_label_zh": "小时",
        "step_value": 6,
        "total_rounds": 12,
        "coverage_label_zh": "共 12 轮，每轮 6 小时",
        "event_windows": [],
        "policy_windows": [],
        "generation_reason_zh": "系统根据事件因果顺序生成时间计划。",
    }
    planning_input = {
        "contract_version": "scenario_planning.v1",
        "planning_input_id": "scenario_plan_localization",
        "content_hash": "planning_hash_localization",
        "simulation_architecture": "llm_mechanism_v1",
        "normalized_user_events": [
            {
                "input_id": "event_input_1",
                "name": "typhoon induced release",
                "description": "machine-facing English input",
                "order": 1,
            }
        ],
        "normalized_user_policies": [
            {
                "input_id": "policy_input_1",
                "name": "evacuation",
                "intent": "reduce exposure",
            }
        ],
        "event_mechanism_graph": mechanism_graph,
        "temporal_plan": temporal_plan,
        "policy_plan": [{"policy_id": "policy_1", "label_zh": "组织疏散"}],
        "role_demands": [
            {
                "demand_id": "role_demand_1",
                "label_zh": "应急疏散能力",
                "required_capability_keys": ["emergency_evacuation"],
            }
        ],
        "assumptions": [],
    }

    config = EnvSimulationConfigGenerator(llm_client=_ForbiddenLegacyLlm()).generate_config(
        simulation_id="simulation_localization",
        project_id="project_localization",
        graph_id="graph_localization",
        simulation_requirement=(
            "分析沿海复合灾害。\n\n"
            "Step 2 场景规划补充：role capability emergency_evacuation"
        ),
        document_text="",
        regions=[],
        subregions=[],
        transport_edges=[],
        profiles=[],
        agent_relationships=[],
        scenario_mode="crisis_mode",
        diffusion_template="generic",
        hazard_template_id="generic",
        search_mode="deep_search",
        simulation_architecture="llm_mechanism_v1",
        scenario_model={
            "source": "scenario_planner",
            "scenario_title": "English legacy title",
            "scenario_summary": "English legacy scenario summary",
        },
        mechanism_graph=mechanism_graph,
        scenario_planning_input=planning_input,
    )

    payload = config.to_dict()
    assert payload["simulation_requirement"] == "分析沿海复合灾害。"
    assert _has_chinese(payload["generation_reasoning"])
    assert _has_chinese(payload["scenario_summary"])
    assert payload["time_config"]["round_label"] == "推演轮次"
    assert payload["time_plan"]["reasoning_summary"] == temporal_plan["generation_reason_zh"]
    assert payload["hazard_template_reasoning"].startswith("兼容字段")
    assert payload["scenario_model"]["scenario_title"] == "台风登陆 → 放射性释放"
    assert _has_chinese(payload["scenario_model"]["scenario_summary"])
    assert all(_has_chinese(item) for item in payload["report_focus"])
    assert _has_chinese(payload["uncertainty_policy"]["explanation"])

    visible_text = "\n".join(
        [
            payload["generation_reasoning"],
            payload["scenario_summary"],
            payload["time_config"]["round_label"],
            *payload["report_focus"],
            payload["uncertainty_policy"]["explanation"],
            payload["scenario_model"]["scenario_title"],
            payload["scenario_model"]["scenario_summary"],
        ]
    )
    assert "English legacy" not in visible_text
    assert "risk object summary" not in visible_text
    assert "simulation round" not in visible_text

