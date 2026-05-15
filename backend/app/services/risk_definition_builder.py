from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class RiskBuildResult:
    risk_definitions: List[Dict[str, Any]]
    primary_risk_id: str
    generation_notes: List[str]


class RiskDefinitionBuilder:
    def build(self, **kwargs) -> RiskBuildResult:
        variables = kwargs.get("injected_variables") or []
        regions = kwargs.get("regions") or []
        primary_region = ""
        if regions and isinstance(regions[0], dict):
            primary_region = regions[0].get("name") or regions[0].get("region_id") or ""
        risk_id = "risk_primary"
        title = "核心生态风险"
        if variables and isinstance(variables[0], dict):
            title = variables[0].get("name") or title
        definition = {
            "risk_id": risk_id,
            "title": title,
            "summary": kwargs.get("simulation_requirement") or "由场景材料和推演变量生成的风险链路。",
            "region_scope": [primary_region] if primary_region else [],
            "severity_score": 0.5,
            "status": "watch",
        }
        return RiskBuildResult([definition], risk_id, ["迁移兼容风险定义生成器"])

    def reframe_runtime(self, existing_definitions=None, injected_variables=None, current_round=0, **kwargs) -> Dict[str, Any]:
        definitions = list(existing_definitions or [])
        created = []
        updated = []
        for variable in injected_variables or []:
            risk_id = f"risk_variable_{len(definitions) + 1}"
            definitions.append({
                "risk_id": risk_id,
                "title": variable.get("name") or "注入变量风险",
                "summary": variable.get("description") or "",
                "region_scope": variable.get("target_regions") or [],
                "severity_score": variable.get("intensity") or 0.5,
                "status": "watch",
                "created_round": current_round,
            })
            created.append(risk_id)
        if not created and definitions:
            updated.append(str(definitions[0].get("risk_id") or "risk_primary"))
        return {
            "risk_definitions": definitions,
            "primary_risk_id": (definitions[0].get("risk_id") if definitions else ""),
            "created_risk_ids": created,
            "updated_risk_ids": updated,
        }
