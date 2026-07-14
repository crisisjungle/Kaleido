import unittest

from app.services.risk_definition_builder import RiskDefinitionBuilder
from app.services.risk_projection import project_legacy_risk_objects


class RiskDefinitionBuilderTestCase(unittest.TestCase):
    def test_typhoon_scenario_generates_multiple_grounded_risks(self):
        builder = RiskDefinitionBuilder()

        result = builder.build(
            risk_contract_version=2,
            simulation_requirement=(
                "模拟台风红色预警下深圳市福田区及周边湿地、水库、森林公园、"
                "城市建成区之间的生态-社会耦合响应，重点关注水位、生态服务与居民安全风险。"
            ),
            injected_variables=[
                {
                    "variable_id": "var_typhoon_red",
                    "type": "disaster",
                    "template": "storm",
                    "name": "模拟台风红色预警",
                    "description": "台风红色预警叠加强降雨和风暴潮。",
                    "intensity_0_100": 86,
                }
            ],
            regions=[
                {
                    "region_id": "region_wetland",
                    "name": "深圳湾湿地",
                    "tags": ["湿地", "滨海", "生态"],
                    "carriers": ["水位", "径流"],
                    "ecology_assets": ["候鸟栖息地", "湿地缓冲"],
                },
                {
                    "region_id": "region_reservoir",
                    "name": "石岩水库",
                    "tags": ["水库", "水体"],
                    "exposure_channels": ["水位"],
                },
                {
                    "region_id": "region_urban",
                    "name": "福田城市建成区",
                    "tags": ["城区", "建成区", "居民"],
                    "exposure_channels": ["排水", "道路积水"],
                },
                {
                    "region_id": "region_transport",
                    "name": "关键交通通道",
                    "tags": ["交通", "道路", "救援"],
                },
            ],
            profiles=[
                {
                    "agent_id": 1,
                    "name": "社区居民",
                    "role_type": "Resident",
                    "profession": "居民",
                    "primary_region": "福田城市建成区",
                    "source_entity_uuid": "agent::resident",
                    "sensitivities": ["预警", "避险", "居民安全"],
                },
                {
                    "agent_id": 2,
                    "name": "公园游客",
                    "role_type": "Tourist",
                    "profession": "游客",
                    "primary_region": "深圳湾湿地",
                    "source_entity_uuid": "agent::tourist",
                    "sensitivities": ["疏散", "公园封闭"],
                },
                {
                    "agent_id": 3,
                    "name": "应急调度员",
                    "role_type": "EmergencyWorker",
                    "profession": "应急",
                    "primary_region": "关键交通通道",
                    "source_entity_uuid": "agent::emergency",
                    "action_space": ["救援", "调度"],
                },
            ],
            entities=[
                {"uuid": "entity::wetland", "name": "深圳湾湿地", "summary": "滨海湿地生态受体"},
                {"uuid": "entity::urban", "name": "福田城市建成区", "summary": "排水与居民暴露区域"},
            ],
            mechanism_graph={
                "nodes": [
                    {"id": "source_typhoon", "name": "台风红色预警", "node_type": "source", "confidence": 0.9},
                    {"id": "process_rain", "name": "强降雨与地表汇流", "node_type": "process", "confidence": 0.85},
                    {"id": "receptor_wetland", "name": "深圳湾湿地生态受体", "node_type": "receptor", "confidence": 0.8},
                    {"id": "infra_drainage", "name": "福田城市建成区排水系统", "node_type": "infrastructure", "confidence": 0.8},
                    {"id": "human_resident", "name": "福田社区居民健康暴露", "node_type": "human", "confidence": 0.75},
                ],
                "edges": [
                    {"id": "edge_rain", "source": "source_typhoon", "target": "process_rain", "relation_label": "台风触发强降雨", "mechanism": "台风红色预警带来持续强降雨", "evidence": ["模拟台风红色预警"], "confidence": 0.9},
                    {"id": "edge_wetland", "source": "process_rain", "target": "receptor_wetland", "relation_label": "汇流进入湿地", "mechanism": "径流压力进入深圳湾湿地", "evidence": ["深圳湾湿地承担蓄滞与生态缓冲"], "confidence": 0.8},
                    {"id": "edge_drainage", "source": "process_rain", "target": "infra_drainage", "relation_label": "排水系统承压", "mechanism": "强降雨超过福田城市建成区排水承载", "evidence": ["福田城市建成区存在排水和道路积水通道"], "confidence": 0.8},
                    {"id": "edge_resident", "source": "infra_drainage", "target": "human_resident", "relation_label": "积水增加居民暴露", "mechanism": "道路积水增加社区居民安全暴露", "evidence": ["社区居民对预警、避险和居民安全敏感"], "confidence": 0.75},
                ],
            },
            temporal_profile={"total_rounds": 12, "minutes_per_round": 60},
        )

        self.assertGreaterEqual(len(result.risk_definitions), 3)
        self.assertEqual(result.primary_risk_id, result.risk_definitions[0]["risk_id"])

        self.assertEqual(result.risk_contract_version, 2)
        families = {item["primary_family"] for item in result.risk_definitions}
        self.assertIn("ecological_environment", families)
        self.assertIn("infrastructure_continuity", families)
        self.assertIn("health_safety", families)

        for definition in result.risk_definitions:
            self.assertGreater(definition["severity_score"], 50)
            self.assertGreater(definition["actionability_score"], 40)
            self.assertGreater(definition["confidence_score"], 0)
            self.assertLessEqual(definition["confidence_score"], 1)
            self.assertTrue(definition["scope"]["regions"])
            self.assertTrue(definition["affected_clusters"])
            self.assertTrue(definition["chain_steps"])
            self.assertTrue(definition["turning_points"])
            self.assertTrue(definition["intervention_templates"])
            self.assertTrue(definition["mechanism_edge_ids"])
            self.assertTrue(definition["risk_statement"]["receptor_node_ids"])
            self.assertNotIn(definition["title"], {template["title"] for template in builder.RISK_TEMPLATES})

        objects = project_legacy_risk_objects(result.risk_definitions, {})
        projected = {item["risk_object_id"]: item for item in objects}
        primary = projected[result.primary_risk_id]
        self.assertEqual(primary["confidence_score"], result.risk_definitions[0]["confidence_score"])
        self.assertTrue(primary["affected_clusters"])
        self.assertTrue(primary["turning_points"])

    def test_internal_variable_tokens_do_not_leak_into_risk_copy(self):
        builder = RiskDefinitionBuilder()

        result = builder.build(
            risk_contract_version=2,
            simulation_requirement="模拟南侧近岸水域、东侧湿地生态带和交通走廊的台风暴雨复合影响。",
            injected_variables=[
                {
                    "variable_id": "var_runtime_1",
                    "type": "disaster",
                    "name": "disaster_injection",
                    "description": "短时强降雨叠加风暴潮。",
                    "target_regions": ["南侧近岸水域"],
                    "intensity_0_100": 82,
                }
            ],
            regions=[
                {
                    "region_id": "south_coast",
                    "name": "南侧近岸水域",
                    "tags": ["水域", "滨海", "风暴潮"],
                    "exposure_channels": ["水位"],
                },
                {
                    "region_id": "east_wetland",
                    "name": "东侧湿地生态带",
                    "tags": ["湿地", "生态"],
                },
            ],
            profiles=[],
            mechanism_graph={
                "nodes": [
                    {"id": "storm_source", "name": "短时强降雨叠加风暴潮", "node_type": "source", "confidence": 0.9},
                    {"id": "coast_receptor", "name": "南侧近岸水域生态受体", "node_type": "receptor", "confidence": 0.8},
                ],
                "edges": [
                    {"id": "storm_to_coast", "source": "storm_source", "target": "coast_receptor", "relation_label": "风暴潮抬升水位", "mechanism": "短时强降雨与风暴潮共同抬升南侧近岸水域水位", "evidence": ["南侧近岸水域"], "confidence": 0.85},
                ],
            },
        )

        self.assertTrue(result.risk_definitions)
        joined_copy = "\n".join(
            " ".join(
                [
                    str(item.get("summary") or ""),
                    str(item.get("why_now") or ""),
                    " ".join(str(value) for value in item.get("root_pressures") or []),
                ]
            )
            for item in result.risk_definitions
        )
        self.assertNotIn("disaster_injection", joined_copy)
        self.assertIn("短时强降雨叠加风暴潮", joined_copy)

        reframe = builder.reframe_runtime(
            existing_definitions=result.risk_definitions,
            risk_contract_version=2,
            injected_variables=[
                {
                    "variable_id": "var_runtime_2",
                    "type": "policy",
                    "name": "policy_injection",
                    "description": "临时关闭高暴露岸线入口。",
                    "target_regions": ["南侧近岸水域"],
                    "intensity": 70,
                }
            ],
        )
        runtime_copy = "\n".join(
            f"{item.get('title')} {' '.join(str(value) for value in item.get('root_pressures') or [])}"
            for item in reframe["risk_definitions"]
        )
        self.assertNotIn("policy_injection", runtime_copy)
        self.assertEqual(reframe["created_risk_ids"], [])
        self.assertEqual(reframe["candidate_variable_ids"], ["var_runtime_2"])

    def test_v1_contract_keeps_template_compatibility(self):
        result = RiskDefinitionBuilder().build(
            risk_contract_version=1,
            simulation_requirement="模拟台风暴雨对湿地和居民的影响。",
            injected_variables=[{"variable_id": "v1", "name": "台风暴雨", "intensity_0_100": 80}],
            regions=[{"region_id": "wetland", "name": "滨海湿地", "tags": ["湿地", "生态"]}],
            profiles=[],
        )
        self.assertEqual(result.risk_contract_version, 1)
        self.assertTrue(result.risk_definitions)
        self.assertTrue(any(item["risk_id"].startswith("risk_") for item in result.risk_definitions))


if __name__ == "__main__":
    unittest.main()
