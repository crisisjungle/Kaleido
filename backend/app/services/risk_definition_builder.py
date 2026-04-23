"""
Risk definition builder.

Phase 1 keeps the existing deterministic `RiskObjectBuilder` as the scenario
compression layer, then projects those legacy risk objects into the new
definition model. Runtime reframing is handled with lightweight heuristics so
variable injection can create or update tracked risk definitions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..utils.logger import get_logger
from .envfish_models import (
    InjectedVariable,
    RiskChainStepDefinition,
    RiskDefinition,
    RiskDefinitionBuildResult,
    RiskScopeActorRef,
    RiskScopeRegionRef,
    clamp_probability,
    ensure_unique_slug,
)
from .risk_object_builder import RiskObjectBuilder
from .risk_projection import risk_objects_to_definitions

logger = get_logger("envfish.risk_definition_builder")


def _to_dict(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return {}


class RiskDefinitionBuilder:
    def __init__(self):
        self.legacy_builder = RiskObjectBuilder()

    def build(
        self,
        simulation_requirement: str,
        document_text: str,
        entities: List[Any],
        regions: List[Any],
        profiles: List[Any],
        injected_variables: Optional[List[InjectedVariable]] = None,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        hazard_template_id: str = "generic",
    ) -> RiskDefinitionBuildResult:
        legacy_result = self.legacy_builder.build(
            simulation_requirement=simulation_requirement,
            document_text=document_text,
            entities=entities,
            regions=regions,
            profiles=profiles,
            injected_variables=injected_variables,
            scenario_mode=scenario_mode,
            diffusion_template=diffusion_template,
            hazard_template_id=hazard_template_id,
        )
        definitions = risk_objects_to_definitions(
            risk_objects=[item.to_dict() for item in legacy_result.risk_objects],
            regions=regions,
            profiles=profiles,
            entities=entities,
        )
        return RiskDefinitionBuildResult(
            risk_definitions=definitions,
            primary_risk_id=legacy_result.primary_risk_object_id,
            generation_notes=list(legacy_result.generation_notes or []),
        )

    def reframe_runtime(
        self,
        existing_definitions: Iterable[Any],
        regions: Iterable[Any],
        profiles: Iterable[Any],
        injected_variables: Iterable[Any],
        current_round: int,
        scenario_mode: str = "baseline_mode",
        diffusion_template: str = "marine",
        max_total: int = 12,
    ) -> Dict[str, Any]:
        definitions = [_to_dict(item) for item in (existing_definitions or []) if _to_dict(item)]
        created_risk_ids: List[str] = []
        updated_risk_ids: List[str] = []
        region_lookup: Dict[str, Dict[str, Any]] = {}
        region_name_lookup: Dict[str, Dict[str, Any]] = {}
        for region in regions or []:
            payload = _to_dict(region)
            region_id = str(payload.get("region_id") or "").strip()
            region_name = str(payload.get("name") or payload.get("region_name") or region_id).strip()
            if region_id:
                region_lookup[region_id] = payload
            if region_name:
                region_name_lookup[region_name.lower()] = payload
        profile_lookup: Dict[int, Dict[str, Any]] = {}
        for profile in profiles or []:
            payload = _to_dict(profile)
            try:
                actor_id = int(payload.get("agent_id"))
            except Exception:
                continue
            profile_lookup[actor_id] = payload

        for raw_variable in injected_variables or []:
            variable = _to_dict(raw_variable)
            variable_id = str(variable.get("variable_id") or "").strip()
            if not variable_id:
                continue
            target_region_ids = [
                str(item or "").strip()
                for item in (variable.get("target_regions") or [])
                if str(item or "").strip()
            ]
            matched_ids = self._matching_definition_ids(definitions, target_region_ids, variable_id)
            if matched_ids:
                updated_risk_ids.extend(matched_ids)
                for definition in definitions:
                    if str(definition.get("risk_id") or "") not in matched_ids:
                        continue
                    source_variable_ids = list(definition.get("source_variable_ids") or [])
                    if variable_id not in source_variable_ids:
                        source_variable_ids.append(variable_id)
                    definition["source_variable_ids"] = source_variable_ids
                    definition["updated_at"] = datetime.now().isoformat()
                    definition["category"] = definition.get("category") or "variable_triggered"
                    trigger_rules = dict(definition.get("trigger_rules") or {})
                    variable_types = list(trigger_rules.get("variable_types") or [])
                    variable_type = str(variable.get("type") or "disaster")
                    if variable_type not in variable_types:
                        variable_types.append(variable_type)
                    trigger_rules["variable_types"] = variable_types
                    definition["trigger_rules"] = trigger_rules
                continue
            if len(definitions) >= max_total:
                logger.info("Skip derived risk creation because risk definition cap reached.")
                continue
            derived = self._build_variable_triggered_definition(
                variable=variable,
                regions=region_lookup,
                region_name_lookup=region_name_lookup,
                profile_lookup=profile_lookup,
                current_round=current_round,
                scenario_mode=scenario_mode,
                diffusion_template=diffusion_template,
            )
            definitions.append(derived.to_dict())
            created_risk_ids.append(derived.risk_id)

        primary_risk_id = ""
        if definitions:
            ranked = sorted(
                definitions,
                key=lambda item: (
                    float(item.get("priority_seed") or 0),
                    len((item.get("scope") or {}).get("regions") or []),
                    len((item.get("scope") or {}).get("actors") or []),
                ),
                reverse=True,
            )
            primary_risk_id = str(ranked[0].get("risk_id") or "")
        return {
            "risk_definitions": definitions,
            "created_risk_ids": list(dict.fromkeys(created_risk_ids)),
            "updated_risk_ids": list(dict.fromkeys(updated_risk_ids)),
            "primary_risk_id": primary_risk_id,
        }

    def _matching_definition_ids(
        self,
        definitions: List[Dict[str, Any]],
        target_region_ids: List[str],
        variable_id: str,
    ) -> List[str]:
        matches: List[Tuple[float, str]] = []
        target_set = {item for item in target_region_ids if item}
        for definition in definitions:
            risk_id = str(definition.get("risk_id") or "").strip()
            if not risk_id:
                continue
            if variable_id and variable_id in (definition.get("source_variable_ids") or []):
                matches.append((1.0, risk_id))
                continue
            scope = definition.get("scope") or {}
            scope_regions = {
                str(item.get("region_id") or "").strip()
                for item in (scope.get("regions") or [])
                if str(item.get("region_id") or "").strip()
            }
            if not scope_regions or not target_set:
                continue
            overlap = len(scope_regions & target_set) / max(len(target_set), 1)
            if overlap >= 0.5:
                matches.append((overlap, risk_id))
        matches.sort(reverse=True)
        return [risk_id for _, risk_id in matches[:2]]

    def _build_variable_triggered_definition(
        self,
        variable: Dict[str, Any],
        regions: Dict[str, Dict[str, Any]],
        region_name_lookup: Dict[str, Dict[str, Any]],
        profile_lookup: Dict[int, Dict[str, Any]],
        current_round: int,
        scenario_mode: str,
        diffusion_template: str,
    ) -> RiskDefinition:
        del scenario_mode, diffusion_template
        used: set[str] = set()
        variable_id = str(variable.get("variable_id") or f"variable_round_{current_round}").strip()
        risk_id = ensure_unique_slug(f"risk_{variable_id}", used)
        variable_type = str(variable.get("type") or "disaster")
        policy_mode = str(variable.get("policy_mode") or "").strip()
        target_regions: List[RiskScopeRegionRef] = []
        target_region_ids = [
            str(item or "").strip()
            for item in (variable.get("target_regions") or [])
            if str(item or "").strip()
        ]
        for region_id in target_region_ids:
            match = regions.get(region_id) or region_name_lookup.get(region_id.lower()) or {}
            target_regions.append(
                RiskScopeRegionRef(
                    region_id=str(match.get("region_id") or region_id),
                    region_name=str(match.get("name") or match.get("region_name") or region_id),
                )
            )
        actor_refs: List[RiskScopeActorRef] = []
        for profile in profile_lookup.values():
            primary_region = str(profile.get("primary_region") or profile.get("home_region_id") or "").strip()
            if primary_region in target_region_ids:
                actor_refs.append(
                    RiskScopeActorRef(
                        actor_id=int(profile.get("agent_id")),
                        actor_name=str(profile.get("username") or profile.get("name") or profile.get("agent_id")),
                    )
                )
            if len(actor_refs) >= 6:
                break

        step_seed = [
            ("new_source_pressure", "新变量压力进入场景", "source_hazard", ["exposure_score", "spread_pressure"]),
            ("localized_disruption", "局部扰动扩散到关键区域", "disruption_spread", ["exposure_score", "economic_stress"]),
            ("affected_groups", "受损群体与区域发生重排", "distributional_impact", ["vulnerability_score", "livelihood_stability"]),
            ("response_shift", "治理与市场响应重新分配", "response_shift", ["response_capacity", "public_trust"]),
        ]
        if variable_type == "policy":
            step_seed = [
                ("policy_entry", "政策变量进入场景", "policy_entry", ["response_capacity", "public_trust"]),
                ("execution_friction", "执行与合规摩擦出现", "execution_friction", ["economic_stress", "response_capacity"]),
                ("distribution_shift", "成本与收益重新分配", "distributional_impact", ["economic_stress", "livelihood_stability"]),
                ("secondary_effect", "次生社会或生态效应显现", "secondary_effect", ["panic_level", "vulnerability_score"]),
            ]
        chain_template = [
            RiskChainStepDefinition(step_id=step_id, label=label, step_type=step_type, monitor_metrics=metrics)
            for step_id, label, step_type, metrics in step_seed
        ]
        title_core = variable.get("name") or variable_id
        if variable_type == "policy":
            title = f"{title_core} 政策响应链风险"
        else:
            title = f"{title_core} 变量触发风险"
        summary = f"由 {title_core} 引入的新变量改变了区域受损路径和响应节奏，需要单独追踪。"
        category = "variable_triggered"
        trigger_rules = {
            "variable_types": [variable_type],
            "policy_modes": [policy_mode] if policy_mode else [],
            "source_variable_id": variable_id,
            "introduced_round": current_round,
        }
        source_variable_ids = [variable_id]
        root_pressures = [title_core, variable_type]
        if policy_mode:
            root_pressures.append(policy_mode)
        priority_seed = clamp_probability((float(variable.get("intensity_0_100") or variable.get("intensity") or 50) / 100) * 0.82)
        return RiskDefinition(
            risk_id=risk_id,
            legacy_risk_object_id=risk_id,
            category=category,
            risk_type="governance_response_friction" if variable_type == "policy" else "eco_social_cascade",
            title=title,
            summary=summary,
            status="tracked",
            mode="incident",
            time_horizon="72h",
            priority_seed=priority_seed,
            scope_regions=target_regions,
            scope_actors=actor_refs,
            chain_template=chain_template,
            root_pressures=root_pressures,
            turning_point_candidates=[
                "关键区域暴露快速抬升",
                "受损群体从局部转向跨区",
                "治理或市场响应出现新的主链路",
            ],
            amplifiers=[
                "高强度变量进入场景",
                "跨区路径与动态边扩张",
            ],
            buffers=["及时披露", "定向缓冲", "快速协同响应"],
            source_variable_ids=source_variable_ids,
            trigger_rules=trigger_rules,
        )
