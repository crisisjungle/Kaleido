import json
import os
import shutil
import tempfile
from unittest.mock import patch

from app.services.effort_contract import build_effort_snapshot
from app.services.env_simulation_config_generator import (
    EnvSimulationConfig,
    EnvSimulationConfigGenerator,
)
from app.services.envfish_models import EnvProfileGenerationResult
from app.services.risk_definition_builder import RiskBuildResult
from app.services.simulation_manager import SimulationManager, SimulationStatus
from app.services.zep_entity_reader import EntityNode, FilteredEntities


def test_step2_graph_is_the_single_config_and_risk_fact_source():
    root = tempfile.mkdtemp(prefix="kaleido_step2_runtime_")
    original_dir = SimulationManager.SIMULATION_DATA_DIR
    SimulationManager.SIMULATION_DATA_DIR = root
    try:
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id="proj_step2_runtime",
            graph_id="graph_step2_runtime",
            simulation_architecture="llm_mechanism_v1",
            effort_snapshot=build_effort_snapshot(
                "high", effort_snapshot_id="effort_step2runtime"
            ),
        )
        planned_graph = {
            "graph_id": "mechanism_graph_step2_reviewed",
            "nodes": [
                {
                    "event_id": "event_typhoon",
                    "label_zh": "台风登陆",
                    "description_zh": "台风影响沿海核电设施。",
                    "event_kind": "external_disturbance",
                    "confidence": 0.86,
                },
                {
                    "event_id": "event_release",
                    "label_zh": "放射性释放",
                    "description_zh": "冷却失效后发生放射性释放。",
                    "event_kind": "hazard_release",
                    "confidence": 0.76,
                },
                {
                    "event_id": "event_marine",
                    "label_zh": "海洋传播",
                    "description_zh": "放射性物质进入近岸海流。",
                    "event_kind": "hazard_propagation",
                    "confidence": 0.74,
                },
                {
                    "event_id": "event_air",
                    "label_zh": "大气传播",
                    "description_zh": "放射性物质形成大气羽流。",
                    "event_kind": "hazard_propagation",
                    "confidence": 0.72,
                },
            ],
            "edges": [
                {
                    "mechanism_id": "mechanism_typhoon_release",
                    "label_zh": "设施失效触发释放",
                    "source_event_id": "event_typhoon",
                    "target_event_id": "event_release",
                    "propagation_medium": "system_coupling",
                    "confidence": 0.74,
                },
                {
                    "mechanism_id": "mechanism_release_marine",
                    "label_zh": "放射性物质进入海流",
                    "source_event_id": "event_release",
                    "target_event_id": "event_marine",
                    "propagation_medium": "marine_current",
                    "confidence": 0.78,
                },
                {
                    "mechanism_id": "mechanism_release_air",
                    "label_zh": "放射性物质进入大气羽流",
                    "source_event_id": "event_release",
                    "target_event_id": "event_air",
                    "propagation_medium": "atmospheric_plume",
                    "confidence": 0.76,
                },
            ],
            "primary_event_ids": ["event_typhoon"],
            "branching_event_ids": ["event_release"],
            "assumptions": ["设施失效链需要在审阅中确认。"],
        }
        temporal_plan = {
            "plan_id": "temporal_step2_reviewed",
            "step_unit": "hour",
            "step_unit_label_zh": "小时",
            "step_value": 6,
            "total_rounds": 12,
            "coverage_label_zh": "共 12 轮，每轮 6 小时",
            "event_windows": [
                {
                    "event_id": "event_typhoon",
                    "start_round": 0,
                    "duration_rounds": 3,
                    "end_round": 2,
                },
                {
                    "event_id": "event_release",
                    "start_round": 2,
                    "duration_rounds": 4,
                    "end_round": 5,
                },
            ],
            "policy_windows": [],
            "generation_reason_zh": "系统依据复合灾害因果顺序生成时间计划。",
        }
        planning_input = {
            "contract_version": "scenario_planning.v1",
            "planning_input_id": "scenario_plan_runtime_test",
            "content_hash": "planning_hash_runtime_test",
            "simulation_architecture": "llm_mechanism_v1",
            "normalized_user_events": [
                {
                    "input_id": "event_input_1",
                    "name": "台风引发核事故",
                    "description": "台风导致核电站失效并发生放射性释放。",
                    "order": 1,
                }
            ],
            "event_mechanism_graph": planned_graph,
            "temporal_plan": temporal_plan,
            "policy_plan": [],
            "role_demands": [],
            "assumptions": ["设施失效链需要在审阅中确认。"],
        }
        filtered = FilteredEntities(
            entities=[
                EntityNode(
                    uuid="entity_nuclear_plant",
                    name="沿海核电站",
                    labels=["Infrastructure"],
                    summary="沿海关键能源设施",
                )
            ],
            entity_types={"Infrastructure"},
            total_count=1,
            filtered_count=1,
        )
        generated = EnvProfileGenerationResult(
            regions=[],
            subregions=[],
            profiles=[],
            agent_relationships=[],
            transport_edges=[],
            region_agent_index={},
            grounding_summary={},
            diffusion_context={},
            generation_summary={},
        )
        risk_kwargs = {}
        config_kwargs = {}

        def fake_risk_build(**kwargs):
            risk_kwargs.update(kwargs)
            return RiskBuildResult(
                risk_definitions=[],
                primary_risk_id="",
                generation_notes=["测试风险结果"],
                generation_audit={"generation_mode": "测试"},
                candidate_ledger=[],
                risk_contract_version=2,
            )

        def fake_config(**kwargs):
            config_kwargs.update(kwargs)
            return EnvSimulationConfig(
                simulation_id=kwargs["simulation_id"],
                project_id=kwargs["project_id"],
                graph_id=kwargs["graph_id"],
                simulation_architecture=kwargs["simulation_architecture"],
                hazard_template_id="radioactive_fallout",
                hazard_template_mode="auto",
                transport_profile={"primary_family": "atmospheric_plume"},
                temporal_profile={"preset": "slow", "total_rounds": 99, "minutes_per_round": 180},
                time_plan={"step_unit": "day", "step_size": 1, "total_rounds": 99},
                scenario_model={"source": "不应保留的旧配置"},
                mechanism_graph={"graph_id": "不应保留的旧机制图"},
            )

        with patch(
            "app.services.simulation_manager.ZepEntityReader.filter_defined_entities",
            return_value=filtered,
        ), patch(
            "app.services.simulation_manager.EnvProfileGenerator.generate_from_entities",
            return_value=generated,
        ), patch(
            "app.services.simulation_manager.MechanismSimulationPlanner.build_prepare_artifacts"
        ) as legacy_planner, patch(
            "app.services.simulation_manager.RiskDefinitionBuilder.build",
            side_effect=fake_risk_build,
        ), patch(
            "app.services.simulation_manager.EnvSimulationConfigGenerator.generate_config",
            side_effect=fake_config,
        ):
            result = manager.prepare_simulation(
                simulation_id=state.simulation_id,
                simulation_requirement="台风引发沿海核事故",
                document_text="沿海核电站与周边居民区。",
                scenario_planning_input=planning_input,
                agent_plan_source="agent_v2",
                simulation_architecture="llm_mechanism_v1",
            )

        assert result.status == SimulationStatus.READY
        legacy_planner.assert_not_called()
        assert risk_kwargs["mechanism_graph"] == planned_graph
        assert risk_kwargs["temporal_profile"]["total_rounds"] == 12
        assert risk_kwargs["temporal_profile"]["minutes_per_round"] == 360
        assert config_kwargs["scenario_planning_input"] == planning_input

        sim_dir = os.path.join(root, state.simulation_id)
        with open(os.path.join(sim_dir, "simulation_config.json"), encoding="utf-8") as handle:
            config = json.load(handle)
        with open(os.path.join(sim_dir, "mechanism_graph.json"), encoding="utf-8") as handle:
            saved_graph = json.load(handle)
        with open(os.path.join(sim_dir, "policy_execution_plan.json"), encoding="utf-8") as handle:
            saved_policy_execution_plan = json.load(handle)

        assert config["mechanism_graph"] == planning_input["event_mechanism_graph"]
        assert saved_graph == planning_input["event_mechanism_graph"]
        assert config["scenario_model"]["source"] == "scenario_planner"
        assert config["scenario_model"]["event_mechanism_graph_id"] == planned_graph["graph_id"]
        assert config["scenario_model"]["planning_input_id"] == planning_input["planning_input_id"]
        assert config["simulation_audit"]["legacy_mechanism_planner_used"] is False
        assert config["scenario_planning_input"] == planning_input
        assert config["agent_plan_source"] == "agent_v2"
        assert config["policy_execution_plan"] == saved_policy_execution_plan
        assert saved_policy_execution_plan["contract_version"] == "policy-execution-plan.v2"
        assert config["temporal_plan"] == temporal_plan
        assert config["scenario_model"]["temporal_plan"] == temporal_plan
        assert config["time_plan"]["step_unit"] == temporal_plan["step_unit"]
        assert config["time_plan"]["step_size"] == temporal_plan["step_value"]
        assert config["time_plan"]["total_rounds"] == temporal_plan["total_rounds"]
        assert config["time_plan"]["source"] == "scenario_planner"
        assert config["temporal_profile"]["total_rounds"] == temporal_plan["total_rounds"]
        assert config["temporal_profile"]["minutes_per_round"] == 360
        assert config["time_config"]["total_rounds"] == temporal_plan["total_rounds"]
        assert config["time_config"]["minutes_per_round"] == 360
        assert config["hazard_template_id"] == "radioactive_fallout"
        assert config["hazard_template_mode"] == "compatibility_projection"
        assert config["hazard_template_recommendation"]["projection_only"] is True
        assert config["transport_profile"]["primary_family"] == "generic"
        assert config["transport_profile"]["source"] == "event_mechanism_graph"
        assert set(config["transport_profile"]["propagation_media"]) >= {
            "marine_current",
            "atmospheric_plume",
        }
        assert config["simulation_audit"]["temporal_plan_source"] == "scenario_planner"
        assert config["simulation_audit"]["transport_plan_source"] == "event_mechanism_graph"
        assert config["simulation_audit"]["hazard_template_role"] == "legacy_projection"
        assert result.temporal_plan == temporal_plan
        assert result.time_plan["step_unit"] == "hour"
        assert result.configured_minutes_per_round == 360
        assert result.configured_total_rounds == 12
        assert set(result.transport_profile["propagation_media"]) >= {
            "marine_current",
            "atmospheric_plume",
        }

        with open(os.path.join(sim_dir, "temporal_plan.json"), encoding="utf-8") as handle:
            saved_temporal_plan = json.load(handle)
        assert saved_temporal_plan == temporal_plan
    finally:
        SimulationManager.SIMULATION_DATA_DIR = original_dir
        shutil.rmtree(root, ignore_errors=True)


def test_config_generator_does_not_replan_a_reviewed_step2_plan():
    temporal_plan = {
        "plan_id": "temporal_direct_generator",
        "step_unit": "day",
        "step_value": 2,
        "total_rounds": 7,
        "coverage_label_zh": "共 7 轮，每轮 2 天",
        "event_windows": [],
        "policy_windows": [],
        "generation_reason_zh": "按已审阅事件链生成。",
    }
    mechanism_graph = {
        "graph_id": "mechanism_direct_generator",
        "nodes": [],
        "edges": [
            {
                "mechanism_id": "marine_branch",
                "label_zh": "海流传播",
                "propagation_medium": "marine_current",
                "confidence": 0.8,
            },
            {
                "mechanism_id": "air_branch",
                "label_zh": "大气传播",
                "propagation_medium": "atmospheric_plume",
                "confidence": 0.78,
            },
        ],
    }
    planning_input = {
        "planning_input_id": "scenario_direct_generator",
        "temporal_plan": temporal_plan,
        "event_mechanism_graph": mechanism_graph,
    }
    generator = EnvSimulationConfigGenerator()

    with patch.object(generator, "_generate_plan_with_llm") as llm_plan, patch.object(
        generator,
        "_fallback_plan",
    ) as fallback_plan:
        config = generator.generate_config(
            simulation_id="sim_direct_generator",
            project_id="proj_direct_generator",
            graph_id="graph_direct_generator",
            simulation_requirement="复合传播测试",
            document_text="",
            regions=[],
            subregions=[],
            transport_edges=[],
            profiles=[],
            agent_relationships=[],
            scenario_planning_input=planning_input,
            mechanism_graph=mechanism_graph,
            hazard_template_id="radioactive_fallout",
            time_plan={"step_unit": "hour", "step_size": 1, "total_rounds": 99},
        )

    llm_plan.assert_not_called()
    fallback_plan.assert_not_called()
    assert config.temporal_plan == temporal_plan
    assert config.time_plan["step_unit"] == "day"
    assert config.time_plan["step_size"] == 2
    assert config.time_plan["total_rounds"] == 7
    assert config.time_plan["source"] == "scenario_planner"
    assert config.hazard_template_mode == "compatibility_projection"
    assert config.hazard_template_recommendation["projection_only"] is True
    assert config.transport_profile["primary_family"] == "generic"
    assert set(config.transport_profile["propagation_media"]) == {
        "marine_current",
        "atmospheric_plume",
    }
