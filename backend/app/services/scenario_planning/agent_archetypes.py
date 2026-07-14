"""Versioned Agent archetypes and deterministic role-to-archetype mapping."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Mapping


AGENT_ARCHETYPE_CONTRACT_VERSION = "agent-archetype.v2"


def _archetype(
    *,
    label_zh: str,
    agent_type: str,
    node_family: str,
    agent_subtype: str,
    capabilities: Iterable[str],
    capability_labels_zh: Iterable[str],
    permissions: Iterable[str],
    resource_types: Iterable[str],
    actions: Iterable[str],
    action_labels_zh: Iterable[str],
    constraints_zh: Iterable[str],
    relationship_roles: Iterable[str],
    observables: Iterable[str],
    resources: Mapping[str, float],
) -> Dict[str, Any]:
    return {
        "version": AGENT_ARCHETYPE_CONTRACT_VERSION,
        "label_zh": label_zh,
        "agent_type": agent_type,
        "node_family": node_family,
        "agent_subtype": agent_subtype,
        "capabilities": list(capabilities),
        "capability_labels_zh": list(capability_labels_zh),
        "permissions": list(permissions),
        "resource_types": list(resource_types),
        "available_action_keys": list(actions),
        "available_action_labels_zh": list(action_labels_zh),
        "decision_constraints_zh": list(constraints_zh),
        "relationship_roles": list(relationship_roles),
        "observable_state_keys": list(observables),
        "default_resources": dict(resources),
        "default_uncertainty_ratio": 0.2,
    }


AGENT_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "local_government": _archetype(
        label_zh="地方政府与应急指挥主体",
        agent_type="governance",
        node_family="GovernmentActor",
        agent_subtype="emergency_office",
        capabilities=["emergency_command", "evacuation_coordination", "resource_dispatch", "public_information", "cross_agency_coordination", "compensation_administration", "fiscal_resource_allocation"],
        capability_labels_zh=["应急指挥", "疏散协调", "资源调度", "公众信息发布", "跨部门协调", "补偿执行", "财政资源配置"],
        permissions=["issue_public_warning", "coordinate_emergency_resources", "order_area_evacuation", "administer_compensation"],
        resource_types=["command_capacity", "coordination_capacity", "public_information_capacity", "relative_fiscal_capacity"],
        actions=["issue_alert", "coordinate_response", "evacuate", "public_briefing", "stabilize_services"],
        action_labels_zh=["发布预警", "协调响应", "组织疏散", "公开简报", "稳定公共服务"],
        constraints_zh=["行动必须在管辖范围内", "高权限行动需要行政依据和资源条件"],
        relationship_roles=["commands", "coordinates", "informs"],
        observables=["response_capacity", "service_capacity", "public_trust", "panic_level"],
        resources={"attention": 70, "coordination": 80, "response": 65, "authority": 75, "fiscal": 50},
    ),
    "education_authority": _archetype(
        label_zh="教育主管与学校应急主体",
        agent_type="governance",
        node_family="GovernmentActor",
        agent_subtype="education_authority",
        capabilities=["education_emergency_management", "school_closure_execution", "student_safety_communication"],
        capability_labels_zh=["教育应急管理", "停课执行", "学生安全沟通"],
        permissions=["issue_school_closure", "publish_student_safety_guidance"],
        resource_types=["education_coordination_capacity", "student_communication_capacity"],
        actions=["close_school", "issue_alert", "coordinate_response", "public_briefing"],
        action_labels_zh=["执行停课", "发布校园预警", "协调教育响应", "发布学生安全提示"],
        constraints_zh=["只在教育系统职责范围内执行", "停课安排必须与区域风险和通行条件一致"],
        relationship_roles=["governs_school", "informs_family", "coordinates_with_emergency_command"],
        observables=["exposure_score", "service_capacity", "public_trust"],
        resources={"attention": 65, "coordination": 70, "authority": 70},
    ),
    "workplace_authority": _archetype(
        label_zh="劳动安全与企业连续性主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="workplace_authority",
        capabilities=["workplace_safety_enforcement", "business_continuity_coordination", "labor_communication"],
        capability_labels_zh=["工作场所安全执行", "企业连续性协调", "劳动沟通"],
        permissions=["issue_workplace_shutdown", "coordinate_business_continuity", "publish_workplace_safety_guidance"],
        resource_types=["workplace_coordination_capacity", "business_continuity_capacity"],
        actions=["close_workplace", "coordinate_response", "public_briefing", "maintain_business_continuity"],
        action_labels_zh=["执行停工", "协调企业响应", "发布劳动安全提示", "安排连续性措施"],
        constraints_zh=["只对有职责或证据绑定的工作场所生效", "不得替代教育或交通主管权限"],
        relationship_roles=["regulates_workplace", "coordinates_employer", "informs_worker"],
        observables=["exposure_score", "economic_stress", "livelihood_stability", "service_capacity"],
        resources={"attention": 60, "coordination": 65, "authority": 65},
    ),
    "industry_regulator": _archetype(
        label_zh="行业与安全监管主体",
        agent_type="governance",
        node_family="GovernmentActor",
        agent_subtype="safety_inspector",
        capabilities=["nuclear_safety_regulation", "radiation_emergency_oversight", "regulatory_enforcement", "infrastructure_damage_assessment"],
        capability_labels_zh=["安全监管", "辐射应急监督", "监管执法", "设施损伤评估"],
        permissions=["inspect_regulated_facility", "issue_regulatory_order", "classify_incident"],
        resource_types=["inspection_capacity", "technical_review_capacity", "regulatory_authority"],
        actions=["inspect", "issue_alert", "enforce_restriction", "public_briefing"],
        action_labels_zh=["开展检查", "发布监管预警", "执行监管限制", "发布监管简报"],
        constraints_zh=["监管判断必须引用设施和监测证据", "不得替代设施运营方执行现场操作"],
        relationship_roles=["regulates", "audits", "receives_incident_report"],
        observables=["vulnerability_score", "exposure_score", "response_capacity"],
        resources={"attention": 65, "inspection": 70, "coordination": 55, "authority": 80},
    ),
    "critical_facility_operator": _archetype(
        label_zh="关键设施运营主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="plant_operator",
        capabilities=["facility_safety_operation", "emergency_shutdown", "cooling_system_recovery", "facility_damage_control"],
        capability_labels_zh=["设施安全运行", "应急停机", "冷却系统恢复", "设施损伤控制"],
        permissions=["operate_assigned_facility", "shutdown_assigned_facility", "deploy_internal_response_resources"],
        resource_types=["facility_control_capacity", "technical_staff", "backup_power", "damage_control_capacity"],
        actions=["monitor", "shutdown_line", "mitigate_emission", "coordinate_response", "report_hazard"],
        action_labels_zh=["监测设施状态", "执行应急停机", "控制释放", "协调现场响应", "报告事故状态"],
        constraints_zh=["仅能操作有证据绑定的设施", "应急资源受设施实际状态约束"],
        relationship_roles=["operates", "reports_to_regulator", "requests_support"],
        observables=["service_capacity", "vulnerability_score", "spread_pressure", "exposure_score"],
        resources={"attention": 70, "response": 80, "technical": 85, "coordination": 45, "authority": 65},
    ),
    "healthcare_provider": _archetype(
        label_zh="医院与医疗服务主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="healthcare_provider",
        capabilities=["emergency_medical_response", "radiation_injury_treatment", "patient_transport", "hospital_capacity_management", "patient_triage", "medical_supply_dispatch"],
        capability_labels_zh=["医疗应急响应", "辐射损伤救治", "患者转运", "医院容量管理", "患者分诊", "医疗物资调度"],
        permissions=["triage_patients", "provide_medical_treatment", "request_patient_transfer", "publish_medical_advisory"],
        resource_types=["treatment_capacity", "staff_capacity", "bed_capacity", "medical_supply_capacity"],
        actions=["monitor", "patient_triage", "coordinate_response", "request_transfer", "public_briefing"],
        action_labels_zh=["监测就诊压力", "开展患者分诊", "协调医疗响应", "请求患者转运", "发布医疗提示"],
        constraints_zh=["救治能力受床位、人员和物资约束", "具体医院实例必须有医疗设施证据"],
        relationship_roles=["treats", "receives_referral", "requests_supply"],
        observables=["service_capacity", "exposure_score", "vulnerability_score"],
        resources={"attention": 65, "response": 75, "treatment": 70, "coordination": 55, "authority": 30},
    ),
    "environmental_monitoring": _archetype(
        label_zh="环境与灾害监测主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="environmental_monitoring",
        capabilities=["environmental_monitoring", "radiation_monitoring", "laboratory_analysis", "data_analysis", "meteorological_monitoring", "coastal_flood_forecasting", "risk_early_warning", "seismic_monitoring", "geological_hazard_assessment"],
        capability_labels_zh=["环境监测", "辐射监测", "实验室分析", "数据分析", "气象监测", "沿海洪水预测", "风险预警", "地震监测", "地质灾害评估"],
        permissions=["collect_environmental_samples", "publish_monitoring_result", "issue_technical_warning"],
        resource_types=["monitoring_capacity", "sampling_capacity", "laboratory_capacity", "analysis_capacity"],
        actions=["monitor", "sample_collect", "publish_assessment", "issue_alert", "advise_policy"],
        action_labels_zh=["持续监测", "采集样本", "发布评估", "发布技术预警", "提出政策建议"],
        constraints_zh=["结论必须与采样和数据证据一致", "不得执行行政强制措施"],
        relationship_roles=["monitors", "reports", "advises"],
        observables=["spread_pressure", "exposure_score", "ecosystem_integrity", "vulnerability_score"],
        resources={"attention": 75, "monitoring": 80, "analysis": 75, "coordination": 45, "authority": 15},
    ),
    "emergency_response": _archetype(
        label_zh="应急救援主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="emergency_response",
        capabilities=["emergency_response", "search_and_rescue", "evacuation_support", "field_damage_control", "resource_dispatch"],
        capability_labels_zh=["应急响应", "搜索救援", "疏散支援", "现场损伤控制", "资源调度"],
        permissions=["enter_emergency_zone", "deploy_rescue_resources", "request_mutual_aid"],
        resource_types=["rescue_capacity", "field_staff", "protective_equipment", "mobility_capacity"],
        actions=["coordinate_response", "evacuate", "deploy_remediation", "report_hazard"],
        action_labels_zh=["协调救援", "支援疏散", "部署现场处置", "报告现场风险"],
        constraints_zh=["进入高风险区域需要防护条件", "行动受交通和物资可达性约束"],
        relationship_roles=["rescues", "supports", "requests_mutual_aid"],
        observables=["response_capacity", "service_capacity", "exposure_score"],
        resources={"attention": 60, "response": 80, "mobility": 70, "coordination": 60, "authority": 35},
    ),
    "transport_operator": _archetype(
        label_zh="交通与基础设施运营主体",
        agent_type="infrastructure",
        node_family="Infrastructure",
        agent_subtype="transport_node",
        capabilities=["traffic_control", "evacuation_routing", "transport_dispatch", "road_clearance", "infrastructure_damage_assessment"],
        capability_labels_zh=["交通管制", "疏散路径规划", "运力调度", "道路清障", "设施损伤评估"],
        permissions=["manage_assigned_transport_network", "reroute_traffic", "report_network_disruption"],
        resource_types=["transport_capacity", "route_capacity", "maintenance_capacity"],
        actions=["route_flow", "reroute", "throttle_capacity", "report_disruption", "coordinate_response"],
        action_labels_zh=["调度交通流", "调整路线", "限制通行能力", "报告中断", "协调运输响应"],
        constraints_zh=["只能调整已绑定的交通网络", "运力受道路和设施状态约束"],
        relationship_roles=["transports", "connects", "supports_evacuation"],
        observables=["service_capacity", "spread_pressure", "vulnerability_score"],
        resources={"attention": 55, "transport": 75, "maintenance": 60, "coordination": 50, "authority": 40},
    ),
    "affected_population": _archetype(
        label_zh="受影响居民群体",
        agent_type="human",
        node_family="HumanActor",
        agent_subtype="resident",
        capabilities=["public_risk_response", "evacuation_participation", "local_information_reporting"],
        capability_labels_zh=["公众风险响应", "参与疏散", "本地信息反馈"],
        permissions=["self_protection", "request_public_service", "report_local_condition"],
        resource_types=["mobility_capacity", "household_supply", "information_access"],
        actions=["observe", "report_hazard", "evacuate", "request_support", "adapt"],
        action_labels_zh=["观察环境", "报告风险", "参与疏散", "请求支持", "调整生活行为"],
        constraints_zh=["信息和行动能力存在差异", "不得代表未覆盖群体执行公共权力"],
        relationship_roles=["receives_service", "reports", "complies_or_resists"],
        observables=["exposure_score", "panic_level", "public_trust", "livelihood_stability"],
        resources={"attention": 45, "mobility": 45, "household_supply": 40, "authority": 0},
    ),
    "livelihood_group": _archetype(
        label_zh="渔业、农业与生计群体",
        agent_type="human",
        node_family="HumanActor",
        agent_subtype="livelihood_group",
        capabilities=["livelihood_impact_reporting", "fisheries_self_organization", "restriction_compliance", "local_information_reporting"],
        capability_labels_zh=["生计影响反馈", "行业自组织", "遵守限制措施", "本地信息反馈"],
        permissions=["organize_members", "report_livelihood_loss", "request_compensation"],
        resource_types=["livelihood_capacity", "mobility_capacity", "local_knowledge"],
        actions=["report_hazard", "adapt", "coordinate_response", "request_support"],
        action_labels_zh=["报告影响", "调整生产活动", "组织行业协作", "申请支持"],
        constraints_zh=["行动受生计依赖和替代收入限制", "不得虚构具体资产规模"],
        relationship_roles=["supplies", "reports_loss", "negotiates"],
        observables=["livelihood_stability", "economic_stress", "exposure_score", "public_trust"],
        resources={"attention": 50, "mobility": 45, "livelihood": 65, "coordination": 35, "authority": 5},
    ),
    "community_organization": _archetype(
        label_zh="社区与社会组织",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="community_committee",
        capabilities=["community_coordination", "local_information_reporting", "vulnerable_group_support", "public_information"],
        capability_labels_zh=["社区协调", "本地信息反馈", "脆弱群体支持", "公众信息传递"],
        permissions=["coordinate_community_support", "distribute_local_notice", "request_public_resources"],
        resource_types=["community_network", "volunteer_capacity", "local_information_capacity"],
        actions=["issue_notice", "coordinate_response", "resource_queue", "report_hazard"],
        action_labels_zh=["发布社区通知", "协调社区响应", "组织资源队列", "报告社区风险"],
        constraints_zh=["不能替代政府发布强制命令", "资源覆盖受社区网络限制"],
        relationship_roles=["coordinates_community", "relays_information", "supports_population"],
        observables=["panic_level", "public_trust", "response_capacity", "service_capacity"],
        resources={"attention": 55, "coordination": 65, "volunteer": 50, "authority": 15},
    ),
    "supply_logistics": _archetype(
        label_zh="物资供应与物流主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="supply_logistics",
        capabilities=["supply_chain_monitoring", "inventory_allocation", "logistics_dispatch", "emergency_procurement", "medical_supply_dispatch"],
        capability_labels_zh=["供应链监测", "库存分配", "物流调度", "应急采购", "医疗物资调度"],
        permissions=["allocate_owned_inventory", "dispatch_logistics_capacity", "request_emergency_procurement", "publish_supply_status"],
        resource_types=["inventory_capacity", "logistics_capacity", "procurement_capacity"],
        actions=["adjust_supply", "coordinate_response", "route_flow", "public_briefing"],
        action_labels_zh=["调整供应", "协调物资响应", "调度物流路线", "发布供应信息"],
        constraints_zh=["只能分配已掌握的库存和运力", "供应能力受交通网络约束"],
        relationship_roles=["supplies", "delivers", "requests_transport"],
        observables=["service_capacity", "economic_stress", "livelihood_stability"],
        resources={"attention": 50, "inventory": 70, "transport": 60, "coordination": 50, "authority": 10},
    ),
    "media_information": _archetype(
        label_zh="媒体与信息发布主体",
        agent_type="organization",
        node_family="OrganizationActor",
        agent_subtype="media_outlet",
        capabilities=["public_information", "information_verification", "risk_communication"],
        capability_labels_zh=["公众信息发布", "信息核验", "风险沟通"],
        permissions=["publish_verified_information", "request_public_statement"],
        resource_types=["verification_capacity", "communication_reach"],
        actions=["verify", "broadcast", "public_briefing", "question_authority"],
        action_labels_zh=["核验信息", "传播消息", "发布简报", "提出公开质询"],
        constraints_zh=["不得把未经核验的信息作为事实发布", "不具有行政处置权限"],
        relationship_roles=["informs", "verifies", "questions"],
        observables=["public_trust", "panic_level", "information_reliability"],
        resources={"attention": 65, "verification": 55, "communication": 75, "authority": 0},
    ),
    "ecological_receptor": _archetype(
        label_zh="生态受体",
        agent_type="ecology",
        node_family="EcologicalReceptor",
        agent_subtype="habitat_species",
        capabilities=["ecological_response", "habitat_stress_signal"],
        capability_labels_zh=["生态响应", "栖息地压力信号"],
        permissions=[],
        resource_types=["ecosystem_resilience"],
        actions=["stress_signal", "migration_shift", "partial_recovery"],
        action_labels_zh=["产生压力信号", "发生迁移变化", "局部恢复"],
        constraints_zh=["生态受体不执行治理决策", "状态变化必须来自环境机制"],
        relationship_roles=["receives_environmental_pressure", "signals_ecological_change"],
        observables=["ecosystem_integrity", "exposure_score", "spread_pressure"],
        resources={"resilience": 55, "authority": 0},
    ),
    "environmental_carrier": _archetype(
        label_zh="环境传播载体",
        agent_type="carrier",
        node_family="EnvironmentalCarrier",
        agent_subtype="environmental_carrier",
        capabilities=["environmental_transport", "pressure_propagation"],
        capability_labels_zh=["环境介质输运", "压力传播"],
        permissions=[],
        resource_types=["transport_capacity", "retention_capacity"],
        actions=["transport_pressure", "retain_pollutant", "dilute"],
        action_labels_zh=["传输压力", "滞留污染物", "稀释压力"],
        constraints_zh=["传播载体不具有人类意图或治理权限", "状态变化必须服从机制图"],
        relationship_roles=["transports_environmental_pressure"],
        observables=["spread_pressure", "exposure_score", "ecosystem_integrity"],
        resources={"transport": 70, "retention": 45, "authority": 0},
    ),
}


DEMAND_ARCHETYPE_MAP = {
    "hazard_monitoring": "environmental_monitoring",
    "geological_emergency_monitoring": "environmental_monitoring",
    "critical_facility_operator": "critical_facility_operator",
    "nuclear_safety_regulator": "industry_regulator",
    "environmental_monitoring": "environmental_monitoring",
    "emergency_medical_response": "healthcare_provider",
    "healthcare_capacity_coordination": "healthcare_provider",
    "public_emergency_command": "local_government",
    "cross_agency_governance": "local_government",
    "policy_execution": "local_government",
    "education_emergency_execution": "education_authority",
    "workplace_shutdown_execution": "workplace_authority",
    "transport_restriction_execution": "transport_operator",
    "community_shelter_coordination": "community_organization",
    "emergency_resource_dispatch": "emergency_response",
    "affected_population": "affected_population",
    "fisheries_stakeholders": "livelihood_group",
    "transport_continuity": "transport_operator",
    "critical_supply_coordination": "supply_logistics",
    "community_coordination": "community_organization",
    "public_information": "media_information",
    "environmental_carrier": "environmental_carrier",
    "ecological_receptor": "ecological_receptor",
    "cross_region_coordination": "local_government",
}


PROFILE_SUBTYPE_ARCHETYPE_MAP = {
    "emergency_office": "local_government",
    "public_agency": "local_government",
    "environment_bureau": "environmental_monitoring",
    "safety_inspector": "industry_regulator",
    "plant_operator": "critical_facility_operator",
    "healthcare_provider": "healthcare_provider",
    "hospital": "healthcare_provider",
    "conservation_station": "environmental_monitoring",
    "scientist": "environmental_monitoring",
    "transport_node": "transport_operator",
    "transport_operator": "transport_operator",
    "resident": "affected_population",
    "community_committee": "community_organization",
    "field_observer": "livelihood_group",
    "livelihood_group": "livelihood_group",
    "market_association": "supply_logistics",
    "supply_logistics": "supply_logistics",
    "media_outlet": "media_information",
    "journalist": "media_information",
    "urban_ecology": "ecological_receptor",
    "urban_birds": "ecological_receptor",
    "soil_biome": "ecological_receptor",
    "habitat_species": "ecological_receptor",
    "environmental_carrier": "environmental_carrier",
    "marine_current": "environmental_carrier",
    "coastal_current": "environmental_carrier",
    "surface_runoff": "environmental_carrier",
    "water_flow": "environmental_carrier",
}


def get_agent_archetype(archetype_key: str) -> Dict[str, Any]:
    key = str(archetype_key or "").strip()
    if key not in AGENT_ARCHETYPES:
        raise KeyError(f"未知 Agent 原型: {archetype_key}")
    return {"archetype_key": key, **copy.deepcopy(AGENT_ARCHETYPES[key])}


def list_agent_archetypes() -> List[Dict[str, Any]]:
    return [get_agent_archetype(key) for key in AGENT_ARCHETYPES]


def archetype_for_demand(demand: Mapping[str, Any]) -> str:
    role_key = str(
        demand.get("role_key")
        or demand.get("demand_key")
        or demand.get("role_demand_key")
        or ""
    ).strip()
    if role_key in DEMAND_ARCHETYPE_MAP:
        return DEMAND_ARCHETYPE_MAP[role_key]
    capabilities = {
        str(item or "").strip()
        for item in (
            demand.get("required_capabilities")
            or demand.get("required_capability_keys")
            or []
        )
        if str(item or "").strip()
    }
    best_key = "community_organization"
    best_overlap = 0
    for key, archetype in AGENT_ARCHETYPES.items():
        overlap = len(capabilities.intersection(archetype["capabilities"]))
        if overlap > best_overlap:
            best_key = key
            best_overlap = overlap
    return best_key


def infer_profile_archetype(profile: Mapping[str, Any]) -> str:
    explicit = str(profile.get("archetype_key") or "").strip()
    if explicit in AGENT_ARCHETYPES:
        return explicit
    subtype = str(profile.get("agent_subtype") or "").strip().lower()
    if subtype in PROFILE_SUBTYPE_ARCHETYPE_MAP:
        return PROFILE_SUBTYPE_ARCHETYPE_MAP[subtype]
    node_family = str(profile.get("node_family") or "").strip()
    agent_type = str(profile.get("agent_type") or "").strip().lower()
    text = " ".join(
        str(profile.get(key) or "").lower()
        for key in ("name", "profession", "role_type", "agent_subtype")
    )
    if any(token in text for token in ("医院", "医疗", "hospital", "clinic")):
        return "healthcare_provider"
    if any(token in text for token in ("核电", "电厂", "工厂", "plant", "operator")):
        return "critical_facility_operator"
    if any(token in text for token in ("监管", "监察", "regulator", "inspector")):
        return "industry_regulator"
    if node_family == "EnvironmentalCarrier" or agent_type == "carrier":
        return "environmental_carrier"
    if node_family == "EcologicalReceptor" or agent_type == "ecology":
        return "ecological_receptor"
    if node_family == "GovernmentActor" or agent_type == "governance":
        return "local_government"
    if node_family == "Infrastructure" or agent_type == "infrastructure":
        return "transport_operator"
    if agent_type == "human":
        return "affected_population"
    return "community_organization"


__all__ = [
    "AGENT_ARCHETYPE_CONTRACT_VERSION",
    "AGENT_ARCHETYPES",
    "DEMAND_ARCHETYPE_MAP",
    "archetype_for_demand",
    "get_agent_archetype",
    "infer_profile_archetype",
    "list_agent_archetypes",
]
