"""Deterministic Agent V2 action validation and resource settlement."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Sequence


AGENT_ACTION_CONTRACT_VERSION = "agent-action.v2"


def _action(
    label_zh: str,
    *,
    capabilities: Sequence[str] = (),
    permissions: Sequence[str] = (),
    minimum_resources: Mapping[str, float] | None = None,
    resource_costs: Mapping[str, float] | None = None,
    irreversible: bool = False,
) -> Dict[str, Any]:
    return {
        "label_zh": label_zh,
        "required_capability_any": list(capabilities),
        "required_permission_any": list(permissions),
        "minimum_resources": dict(minimum_resources or {}),
        "resource_costs": dict(resource_costs or {}),
        "irreversible": irreversible,
    }


ACTION_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "wait": _action("保持待命"),
    "observe": _action("观察状态", minimum_resources={"attention": 0.5}, resource_costs={"attention": 0.5}),
    "monitor": _action("持续监测", minimum_resources={"attention": 1}, resource_costs={"attention": 1}),
    "close_school": _action(
        "执行停课",
        capabilities=["school_closure_execution"],
        permissions=["issue_school_closure"],
        minimum_resources={"authority": 1},
        resource_costs={"attention": 1, "coordination": 1},
        irreversible=True,
    ),
    "close_workplace": _action(
        "执行停工",
        capabilities=["workplace_safety_enforcement"],
        permissions=["issue_workplace_shutdown"],
        minimum_resources={"authority": 1},
        resource_costs={"attention": 1, "coordination": 1},
        irreversible=True,
    ),
    "maintain_business_continuity": _action(
        "安排企业连续性措施",
        capabilities=["business_continuity_coordination"],
        permissions=["coordinate_business_continuity"],
        minimum_resources={"coordination": 1},
        resource_costs={"attention": 0.5, "coordination": 1},
    ),
    "issue_alert": _action(
        "发布预警",
        capabilities=["risk_early_warning", "public_information", "radiation_emergency_oversight", "student_safety_communication", "labor_communication"],
        permissions=["issue_public_warning", "issue_technical_warning", "classify_incident", "publish_student_safety_guidance", "publish_workplace_safety_guidance"],
        minimum_resources={"attention": 2},
        resource_costs={"attention": 1.5, "coordination": 0.5},
    ),
    "coordinate_response": _action(
        "协调响应",
        capabilities=["emergency_command", "evacuation_coordination", "resource_dispatch", "community_coordination", "cross_region_coordination", "logistics_dispatch", "facility_damage_control", "facility_safety_operation", "emergency_medical_response", "hospital_capacity_management", "transport_dispatch", "traffic_control", "fisheries_self_organization", "livelihood_impact_reporting", "education_emergency_management", "business_continuity_coordination"],
        minimum_resources={"coordination": 1},
        resource_costs={"attention": 0.5, "coordination": 1},
    ),
    "evacuate": _action(
        "组织或参与疏散",
        capabilities=["evacuation_coordination", "evacuation_participation", "evacuation_support"],
        permissions=["order_area_evacuation", "self_protection", "enter_emergency_zone"],
        minimum_resources={"attention": 1},
        resource_costs={"attention": 1, "coordination": 1},
    ),
    "public_briefing": _action(
        "发布公开简报",
        capabilities=["public_information", "risk_communication", "environmental_monitoring", "emergency_command", "radiation_emergency_oversight", "emergency_medical_response", "supply_chain_monitoring", "student_safety_communication", "labor_communication"],
        permissions=["issue_public_warning", "publish_monitoring_result", "publish_verified_information", "classify_incident", "publish_medical_advisory", "publish_supply_status", "publish_student_safety_guidance", "publish_workplace_safety_guidance"],
        minimum_resources={"attention": 1},
        resource_costs={"attention": 1},
    ),
    "stabilize_services": _action(
        "稳定公共服务",
        capabilities=["resource_dispatch", "emergency_command"],
        minimum_resources={"response": 1, "coordination": 1},
        resource_costs={"response": 1, "coordination": 1},
    ),
    "inspect": _action(
        "开展检查",
        capabilities=["nuclear_safety_regulation", "regulatory_enforcement", "infrastructure_damage_assessment"],
        permissions=["inspect_regulated_facility"],
        minimum_resources={"inspection": 1},
        resource_costs={"inspection": 1, "attention": 0.5},
    ),
    "enforce_restriction": _action(
        "执行限制措施",
        capabilities=["regulatory_enforcement", "emergency_command"],
        permissions=["issue_regulatory_order", "order_area_evacuation"],
        minimum_resources={"authority": 1},
        resource_costs={"attention": 1, "coordination": 1},
        irreversible=True,
    ),
    "shutdown_line": _action(
        "执行应急停机",
        capabilities=["emergency_shutdown", "facility_safety_operation"],
        permissions=["shutdown_assigned_facility"],
        minimum_resources={"technical": 1},
        resource_costs={"technical": 1, "attention": 1},
        irreversible=True,
    ),
    "mitigate_emission": _action(
        "控制释放",
        capabilities=["facility_damage_control", "cooling_system_recovery"],
        permissions=["operate_assigned_facility", "deploy_internal_response_resources"],
        minimum_resources={"technical": 1, "response": 1},
        resource_costs={"technical": 1, "response": 1},
    ),
    "report_hazard": _action(
        "报告风险",
        capabilities=["local_information_reporting", "facility_safety_operation", "infrastructure_damage_assessment", "environmental_monitoring", "emergency_response", "field_damage_control"],
        minimum_resources={"attention": 0.5},
        resource_costs={"attention": 0.5},
    ),
    "patient_triage": _action(
        "开展患者分诊",
        capabilities=["patient_triage", "emergency_medical_response"],
        permissions=["triage_patients"],
        minimum_resources={"treatment": 1},
        resource_costs={"treatment": 1, "attention": 0.5},
    ),
    "request_transfer": _action(
        "请求患者转运",
        capabilities=["patient_transport", "hospital_capacity_management"],
        permissions=["request_patient_transfer"],
        minimum_resources={"coordination": 1},
        resource_costs={"coordination": 1},
    ),
    "sample_collect": _action(
        "采集样本",
        capabilities=["environmental_monitoring", "radiation_monitoring"],
        permissions=["collect_environmental_samples"],
        minimum_resources={"monitoring": 1},
        resource_costs={"monitoring": 1, "attention": 0.5},
    ),
    "publish_assessment": _action(
        "发布评估",
        capabilities=["data_analysis", "laboratory_analysis", "environmental_monitoring"],
        permissions=["publish_monitoring_result", "publish_verified_information"],
        minimum_resources={"analysis": 1},
        resource_costs={"analysis": 1, "attention": 0.5},
    ),
    "advise_policy": _action(
        "提出政策建议",
        capabilities=["data_analysis", "environmental_monitoring", "radiation_monitoring"],
        minimum_resources={"analysis": 1},
        resource_costs={"analysis": 0.5, "attention": 0.5},
    ),
    "deploy_remediation": _action(
        "部署现场处置",
        capabilities=["field_damage_control", "emergency_response", "facility_damage_control"],
        permissions=["deploy_rescue_resources", "deploy_internal_response_resources"],
        minimum_resources={"response": 1},
        resource_costs={"response": 1, "attention": 0.5},
    ),
    "route_flow": _action(
        "调度交通流",
        capabilities=["transport_dispatch", "evacuation_routing", "logistics_dispatch"],
        permissions=["manage_assigned_transport_network", "dispatch_logistics_capacity"],
        minimum_resources={"transport": 1},
        resource_costs={"transport": 1, "attention": 0.5},
    ),
    "reroute": _action(
        "调整路线",
        capabilities=["evacuation_routing", "traffic_control"],
        permissions=["reroute_traffic"],
        minimum_resources={"transport": 1},
        resource_costs={"transport": 1, "coordination": 0.5},
    ),
    "throttle_capacity": _action(
        "限制通行能力",
        capabilities=["traffic_control"],
        permissions=["manage_assigned_transport_network"],
        minimum_resources={"authority": 1},
        resource_costs={"attention": 0.5},
    ),
    "report_disruption": _action(
        "报告网络中断",
        capabilities=["infrastructure_damage_assessment", "road_clearance"],
        permissions=["report_network_disruption"],
        minimum_resources={"attention": 0.5},
        resource_costs={"attention": 0.5},
    ),
    "request_support": _action("请求支持", minimum_resources={"attention": 0.5}, resource_costs={"attention": 0.5}),
    "adapt": _action("调整行为", minimum_resources={"attention": 0.5}, resource_costs={"attention": 0.5}),
    "issue_notice": _action(
        "发布社区通知",
        capabilities=["public_information", "community_coordination"],
        permissions=["distribute_local_notice"],
        minimum_resources={"coordination": 1},
        resource_costs={"coordination": 0.5, "attention": 0.5},
    ),
    "resource_queue": _action(
        "组织资源队列",
        capabilities=["community_coordination", "vulnerable_group_support"],
        minimum_resources={"coordination": 1},
        resource_costs={"coordination": 1},
    ),
    "adjust_supply": _action(
        "调整供应",
        capabilities=["inventory_allocation", "logistics_dispatch"],
        permissions=["allocate_owned_inventory", "dispatch_logistics_capacity"],
        minimum_resources={"inventory": 1},
        resource_costs={"inventory": 1, "coordination": 0.5},
    ),
    "verify": _action("核验信息", capabilities=["information_verification"], minimum_resources={"verification": 1}, resource_costs={"verification": 1}),
    "broadcast": _action(
        "传播已核验信息",
        capabilities=["public_information", "risk_communication"],
        permissions=["publish_verified_information"],
        minimum_resources={"communication": 1},
        resource_costs={"communication": 1, "attention": 0.5},
    ),
    "question_authority": _action("提出公开质询", capabilities=["risk_communication"], minimum_resources={"attention": 1}, resource_costs={"attention": 1}),
    "stress_signal": _action("产生压力信号"),
    "migration_shift": _action("发生迁移变化"),
    "partial_recovery": _action("局部恢复"),
    "transport_pressure": _action("传输环境压力", capabilities=["environmental_transport", "pressure_propagation"], minimum_resources={"transport": 1}, resource_costs={"transport": 0.5}),
    "retain_pollutant": _action("滞留污染物", capabilities=["environmental_transport"], minimum_resources={"retention": 1}, resource_costs={"retention": 0.5}),
    "dilute": _action("稀释环境压力", capabilities=["environmental_transport"], minimum_resources={"transport": 1}, resource_costs={"transport": 0.5}),
}


def action_label_zh(action_key: Any) -> str:
    key = str(action_key or "").strip().lower()
    contract = ACTION_CONTRACTS.get(key)
    system_labels = {
        "spread_update": "扩散状态更新",
        "eco_impact": "生态影响更新",
    }
    return str((contract or {}).get("label_zh") or system_labels.get(key) or "执行动作")


def validate_agent_action(actor: Mapping[str, Any], action_key: Any) -> Dict[str, Any]:
    key = str(action_key or "").strip()
    contract = ACTION_CONTRACTS.get(key)
    reasons: List[str] = []
    action_space = _strings(actor.get("action_space") or [])
    if key not in {"observe", "wait"} and key not in action_space:
        reasons.append("动作不在该 Agent 的行动空间内")
    if contract is None:
        reasons.append("动作没有已注册的执行合同")
        return _validation_result(key, {}, reasons)

    available_capabilities = set(_strings(actor.get("capability_keys") or []))
    required_capabilities = set(contract["required_capability_any"])
    if required_capabilities and not available_capabilities.intersection(required_capabilities):
        reasons.append("缺少动作所需能力")

    available_permissions = set(_strings(actor.get("permission_keys") or []))
    required_permissions = set(contract["required_permission_any"])
    if required_permissions and not available_permissions.intersection(required_permissions):
        reasons.append("缺少动作所需权限")

    resources = dict(actor.get("resource_budget") or {})
    missing_resources = []
    for resource_key, minimum in contract["minimum_resources"].items():
        if _number(resources.get(resource_key)) < float(minimum):
            missing_resources.append(resource_key)
    if missing_resources:
        reasons.append("可用资源不足")

    lifecycle = str(
        actor.get("lifecycle_status")
        or (actor.get("runtime_lifecycle") or {}).get("lifecycle_status")
        or "active"
    )
    if lifecycle != "active":
        reasons.append("Agent 当前未处于可行动状态")
    if contract["irreversible"] and str(actor.get("representation_level") or "") == "runtime_provisional":
        reasons.append("临时 Agent 不得执行不可逆或高权限动作")

    return _validation_result(key, contract, reasons)


def consume_action_resources(actor: Dict[str, Any], validation: Mapping[str, Any]) -> Dict[str, Any]:
    before = {str(key): _number(value) for key, value in (actor.get("resource_budget") or {}).items()}
    after = dict(before)
    consumed: Dict[str, float] = {}
    if bool(validation.get("accepted")):
        for key, raw_cost in (validation.get("resource_costs") or {}).items():
            cost = max(0.0, _number(raw_cost))
            available = max(0.0, after.get(str(key), 0.0))
            actual = min(cost, available)
            after[str(key)] = round(available - actual, 6)
            consumed[str(key)] = round(actual, 6)
        actor["resource_budget"] = after
        uncertainty = dict(actor.get("resource_uncertainty") or {})
        for key, value in after.items():
            uncertainty[key] = [round(max(0.0, value * 0.8), 3), round(value * 1.2, 3)]
        actor["resource_uncertainty"] = uncertainty
    return {
        "before": before,
        "after": after,
        "consumed": consumed,
    }


def _validation_result(key: str, contract: Mapping[str, Any], reasons: Iterable[str]) -> Dict[str, Any]:
    reason_list = list(dict.fromkeys(str(item) for item in reasons if str(item).strip()))
    return {
        "contract_version": AGENT_ACTION_CONTRACT_VERSION,
        "action_key": key,
        "action_label_zh": str(contract.get("label_zh") or "未知动作"),
        "accepted": not reason_list,
        "rejection_reasons_zh": reason_list,
        "required_capability_any": list(contract.get("required_capability_any") or []),
        "required_permission_any": list(contract.get("required_permission_any") or []),
        "minimum_resources": deepcopy(dict(contract.get("minimum_resources") or {})),
        "resource_costs": deepcopy(dict(contract.get("resource_costs") or {})),
        "irreversible": bool(contract.get("irreversible")),
    }


def _strings(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "ACTION_CONTRACTS",
    "AGENT_ACTION_CONTRACT_VERSION",
    "action_label_zh",
    "consume_action_resources",
    "validate_agent_action",
]
