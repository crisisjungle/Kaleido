import unittest

from app.services.risk_definition_builder import RiskDefinitionBuilder
from app.services.risk_projection import project_legacy_risk_objects


class RiskDefinitionBuilderTestCase(unittest.TestCase):
    def test_typhoon_scenario_generates_multiple_grounded_risks(self):
        builder = RiskDefinitionBuilder()

        result = builder.build(
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
            temporal_profile={"total_rounds": 12, "minutes_per_round": 60},
        )

        self.assertGreaterEqual(len(result.risk_definitions), 3)
        self.assertEqual(result.primary_risk_id, result.risk_definitions[0]["risk_id"])

        risk_ids = {item["risk_id"] for item in result.risk_definitions}
        self.assertIn("risk_water_ecology", risk_ids)
        self.assertIn("risk_urban_flood", risk_ids)
        self.assertIn("risk_public_exposure", risk_ids)

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

        objects = project_legacy_risk_objects(result.risk_definitions, {})
        projected = {item["risk_object_id"]: item for item in objects}
        self.assertEqual(
            projected["risk_water_ecology"]["confidence_score"],
            next(item["confidence_score"] for item in result.risk_definitions if item["risk_id"] == "risk_water_ecology"),
        )
        self.assertTrue(projected["risk_water_ecology"]["affected_clusters"])
        self.assertTrue(projected["risk_water_ecology"]["turning_points"])


if __name__ == "__main__":
    unittest.main()
