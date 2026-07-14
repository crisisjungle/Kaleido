// 统一显示文本清洗层：任何要上屏的 token / 字段 key 都走这里，
// 杜绝裸英文 key、内部 token（dynamic_edge / self_loop / *_round / animation_* 等）泄漏。

const TOKEN_MAP = {
  // —— 场景/模式 ——
  baseline_mode: '基线态', crisis_mode: '灾难态',
  legacy_envfish_v1: '经典推演', llm_mechanism_v1: '机制推演',
  // —— 扩散/传播模板 ——
  bio_ecological_transmission: '生物生态传播', marine: '海洋扩散',
  atmospheric_dispersion: '大气扩散', hydrological_flow: '水文流动',
  human_mobility: '人口流动', supply_chain_propagation: '供应链传导',
  // —— 干预/变量类型 ——
  policy: '政策', disaster: '灾害', restrict: '限制', relocate: '迁移',
  subsidize: '补贴', monitor: '监测', disclose: '披露', repair: '修复',
  ban: '禁用', reopen: '重开', variable_triggered: '变量触发',
  // —— 尺度 ——
  macro: '宏观', meso: '中观', micro: '微观',
  // —— 区域/地理类型 ——
  region: '区域', subregion: '细分区域', agent: '代理体', profile: '画像', general: '综合',
  coastal_zone: '近海区域', 'coastal zone': '近海区域', coast: '海岸', coastal: '沿海',
  outer_ring: '外围区域', inner_ring: '核心区域', transition_ring: '过渡区域',
  ecology_zone: '生态分区', urban_zone: '建成分区',
  residential_zone: '居住分区', city_zone: '城市分区', admin_city: '行政城市',
  high_density: '高密度', transport_hub: '交通枢纽', emergency_response: '应急响应',
  feature_relation: '地理关系', feature_context_admin_district: '行政区背景',
  feature_context_admin_city: '城市背景', feature_context: '地理背景',
  infrastructure_corridor: '基础设施走廊', transport_corridor: '交通走廊',
  river_basin: '流域', 'river basin': '流域', city: '城市区域', district: '行政区',
  administrative_region: '行政区域', administrativeregion: '行政区域',
  AdministrativeRegion: '行政区域', ADMINISTRATIVEREGION: '行政区域',
  ecological: '生态', wetland: '湿地', forest_park: '森林公园', 'forest park': '森林公园',
  forest: '林地', mountain: '山地', reservoir: '水库',
  water_source: '水源地', 'water source': '水源地', water: '水域',
  commercial: '商业', urban: '城市建成区', residential: '居住', industrial: '工业',
  agricultural: '农业', conservation: '保护区',
  flood_risk: '洪涝风险', 'flood risk': '洪涝风险',
  landslide_risk: '滑坡风险', 'landslide risk': '滑坡风险',
  infrastructure: '基础设施', science_city: '科学城', 'science city': '科学城',
  protected_area: '保护区', 'protected area': '保护区',
  cross_border: '跨边界', 'cross border': '跨边界',
  support_belt: '支撑带', transport_belt: '交通带', industrial_belt: '工业带',
  ecological_belt: '生态带', residential_belt: '居住带',
  urban_core: '城市核心', civic: '公共服务', mixed_use: '混合功能',
  near: '近距', mid: '中距', far: '远距',
  // —— 主体/节点类型（图例、节点详情都用到）——
  government: '政府', governance: '治理', organization: '组织', human: '个体',
  ecology: '生态', actor: '行动者', entity: '实体', Entity: '实体',
  place: '地点', data_signal: '数据信号', physical_process: '物理过程',
  MechanismNode: '机制节点', mechanismnode: '机制节点', mechanism_node: '机制节点',
  mechanism_source: '压力源', mechanism_pressure: '压力源', mechanism_hazard: '灾害源',
  mechanism_driver: '驱动因素', mechanism_trigger: '触发源', mechanism_process: '传播过程',
  mechanism_receptor: '受影响对象', mechanism_infrastructure: '基础设施受体',
  mechanism_governance: '治理受体', mechanism_human: '人群受体',
  mechanism_ecological: '生态受体', mechanism_economy: '经济受体',
  mechanism_service: '服务受体', mechanism_outcome: '后果节点', mechanism_edge: '机制传导',
  mechanism_graph: '场景机制图', mechanism_path: '机制路径',
  humanactor: '个体', governmentactor: '政府', organizationactor: '组织',
  governanceactor: '治理主体', governance_actor: '治理主体',
  GovernanceActor: '治理主体', GOVERNANCEACTOR: '治理主体',
  ecologicalreceptor: '生态受体', ecological_receptor: '生态受体',
  environmentalcarrier: '环境载体', environmental_carrier: '环境载体',
  HumanActor: '人群主体', GovernmentActor: '治理主体', OrganizationActor: '组织主体',
  HumanAgent: '人群主体', humanagent: '人群主体',
  GovernanceAgent: '治理主体', governanceagent: '治理主体',
  GovernmentAgent: '治理主体', governmentagent: '治理主体',
  OrganizationAgent: '组织主体', organizationagent: '组织主体',
  EcologyAgent: '生态主体', ecologyagent: '生态主体',
  EnvironmentalAgent: '环境主体', environmentalagent: '环境主体',
  CarrierAgent: '环境载体', carrieragent: '环境载体',
  InfrastructureAgent: '基础设施主体', infrastructureagent: '基础设施主体',
  ResourceAgent: '资源主体', resourceagent: '资源主体',
  EcologicalReceptor: '生态受体', EnvironmentalCarrier: '环境载体',
  Infrastructure: '基础设施',
  carrier: '载体', institution: '机构', process: '过程', resource: '资源',
  riskobject: '风险对象', risk_object: '风险对象', threshold: '阈值',
  resident: '居民', tourist: '游客', scientist: '科研人员', journalist: '媒体',
  worker: '工作者', field_observer: '现场观察员', activist: '行动者',
  community_committee: '社区委员会', white_collar: '白领', plant_operator: '设施运营方',
  transport_node: '交通节点', emergencyworker: '应急人员', unspecified: '未明确',
  Region: '区域', Risk: '风险', Actor: '行动者', risk: '风险',
  // —— 后端角色枚举 / profile role_type ——
  residentgroup: '居民群体', residents: '居民',
  fieldobserver: '现场观察员', farmer: '农业生产者',
  transportworker: '交通运维员', emergency_worker: '应急人员',
  shop_owner: '商户', shopowner: '商户',
  communitycommittee: '社区委员会', environmentalvolunteer: '环保志愿者',
  market_association: '商圈协会', marketassociation: '商圈协会',
  safety_inspector: '安全监察员', safetyinspector: '安全监察员',
  soil_biome: '土壤微生境', soilbiome: '土壤微生境',
  environment_bureau: '环保部门', environmentbureau: '环保部门',
  emergency_office: '应急管理部门', emergencyoffice: '应急管理部门',
  conservation_station: '保育站', conservationstation: '保育站',
  carrier_node: '环境载体', carriernode: '环境载体',
  habitat_species: '栖息地物种', habitatspecies: '栖息地物种',
  urban_birds: '城市鸟群', urbanbirds: '城市鸟群',
  urban_ecology: '城市生态', ecologysentinel: '生态哨兵',
  plantoperator: '设施运营方', whitecollar: '白领',
  RoleType: '角色类型', roletype: '角色类型',
  source: '来源', target: '目标',
  coastal_current: '近岸洋流', marine_current: '海洋环流',
  surface_runoff: '地表径流', environmental_link: '环境通道',
  // —— 行动空间 / 后端策略 token ——
  action_space: '行动空间', action_space_hint: '行动提示',
  transport_pressure: '传导压力', retain_pollutant: '滞留污染物',
  issue_alert: '发布预警', publish_assessment: '发布评估',
  report_hazard: '上报风险', stress_signal: '压力信号',
  reroute: '改道', adapt: '适应调整', migrate: '迁移',
  dilute: '稀释', restore: '修复', inspect: '巡查',
  observe: '观察', complain: '投诉反馈', volunteer_cleanup: '志愿清理',
  panic_buy: '恐慌采购', sample_collect: '采样', public_campaign: '公开倡议',
  petition: '联名请愿', share_update: '分享动态', remote_work: '远程办公',
  market_shift: '消费转移', halt_line: '暂停产线', continue_production: '继续生产',
  advise_policy: '政策建议', verify: '核实', broadcast: '发布传播',
  question_authority: '追问责任', coordinate_cleanup: '协调清理',
  issue_notice: '发布通知', resource_queue: '资源排队', adjust_supply: '调整供给',
  price_signal: '价格信号', mitigate_emission: '减排缓释',
  continue_output: '维持产出', shutdown_line: '关闭产线',
  enforce_restriction: '执行限制', deploy_remediation: '部署修复',
  coordinate_response: '协调响应', evacuate: '疏散', stabilize_services: '稳定服务',
  fine_operator: '处罚运营方', restore_habitat: '修复栖息地',
  restrict_access: '限制进入', partial_recovery: '部分恢复',
  migration_shift: '迁移变化', bioaccumulate: '生物累积',
  breed_decline: '繁殖下降', signal_loss: '信号减弱',
  route_flow: '路径导流', throttle_capacity: '限制承载',
  report_disruption: '上报中断', signal: '发出信号', respond: '响应',
  local_observation: '本地观察', resource_mobilization: '资源动员',
  local_coordination: '本地协调', resource_dispatch: '资源调度',
  enforcement: '执法约束', monitoring: '监测', public_briefing: '公开通报',
  response_command: '响应指挥', inspection: '巡查',
  compliance_enforcement: '合规执法', routing: '路径调度',
  flow_observation: '流量观察', traffic_control: '交通管制',
  hydro_observation: '水文观察',
  // —— Agent V2 原型、能力与权限 ——
  local_government: '地方政府与应急指挥主体', industry_regulator: '行业与安全监管主体',
  critical_facility_operator: '关键设施运营主体', healthcare_provider: '医院与医疗服务主体',
  environmental_monitoring: '环境与灾害监测主体', transport_operator: '交通与基础设施运营主体',
  affected_population: '受影响居民群体', livelihood_group: '渔业、农业与生计群体',
  community_organization: '社区与社会组织', supply_logistics: '物资供应与物流主体',
  media_information: '媒体与信息发布主体',
  coastal_flood_forecasting: '沿海洪水预测', community_coordination: '社区协调',
  compensation_administration: '补偿执行', cooling_system_recovery: '冷却系统恢复',
  cross_agency_coordination: '跨部门协调', data_analysis: '数据分析',
  ecological_response: '生态响应', emergency_command: '应急指挥',
  emergency_medical_response: '医疗应急响应', emergency_procurement: '应急采购',
  emergency_shutdown: '应急停机', environmental_transport: '环境介质输运',
  evacuation_coordination: '疏散协调', evacuation_participation: '参与疏散',
  evacuation_routing: '疏散路径规划', evacuation_support: '疏散支援',
  facility_damage_control: '设施损伤控制', facility_safety_operation: '设施安全运行',
  field_damage_control: '现场损伤控制', fiscal_resource_allocation: '财政资源配置',
  fisheries_self_organization: '行业自组织', geological_hazard_assessment: '地质灾害评估',
  habitat_stress_signal: '栖息地压力信号', hospital_capacity_management: '医院容量管理',
  information_verification: '信息核验', infrastructure_damage_assessment: '设施损伤评估',
  inventory_allocation: '库存分配', laboratory_analysis: '实验室分析',
  livelihood_impact_reporting: '生计影响反馈', local_information_reporting: '本地信息反馈',
  logistics_dispatch: '物流调度', medical_supply_dispatch: '医疗物资调度',
  meteorological_monitoring: '气象监测', nuclear_safety_regulation: '核安全监管',
  patient_transport: '患者转运', patient_triage: '患者分诊',
  pressure_propagation: '压力传播', public_information: '公众信息发布',
  public_risk_response: '公众风险响应', radiation_emergency_oversight: '辐射应急监督',
  radiation_injury_treatment: '辐射损伤救治', radiation_monitoring: '辐射监测',
  regulatory_enforcement: '监管执法', restriction_compliance: '遵守限制措施',
  risk_communication: '风险沟通', risk_early_warning: '风险预警',
  road_clearance: '道路清障', search_and_rescue: '搜索救援', seismic_monitoring: '地震监测',
  supply_chain_monitoring: '供应链监测', transport_dispatch: '运力调度',
  vulnerable_group_support: '脆弱群体支持',
  administer_compensation: '执行补偿', allocate_owned_inventory: '调配自有库存',
  classify_incident: '划分事故等级', collect_environmental_samples: '采集环境样本',
  coordinate_community_support: '协调社区支持', coordinate_emergency_resources: '协调应急资源',
  deploy_internal_response_resources: '部署内部响应资源', deploy_rescue_resources: '部署救援资源',
  dispatch_logistics_capacity: '调度物流运力', distribute_local_notice: '发布属地通知',
  enter_emergency_zone: '进入应急区域', inspect_regulated_facility: '检查受监管设施',
  issue_public_warning: '发布公众预警', issue_regulatory_order: '发布监管指令',
  issue_technical_warning: '发布技术预警', manage_assigned_transport_network: '管理授权交通网络',
  operate_assigned_facility: '运行授权设施', order_area_evacuation: '下达区域疏散命令',
  organize_members: '组织成员行动', provide_medical_treatment: '提供医疗救治',
  publish_medical_advisory: '发布医疗建议', publish_monitoring_result: '发布监测结果',
  publish_supply_status: '发布供应状态', publish_verified_information: '发布已核验信息',
  report_livelihood_loss: '报告生计损失', report_local_condition: '报告属地情况',
  report_network_disruption: '报告网络中断', request_compensation: '申请补偿',
  request_emergency_procurement: '申请应急采购', request_mutual_aid: '请求协同支援',
  request_patient_transfer: '申请患者转运', request_public_resources: '申请公共资源',
  request_public_service: '申请公共服务', request_public_statement: '请求公开说明',
  reroute_traffic: '调整交通路线', self_protection: '采取自我防护',
  shutdown_assigned_facility: '关闭授权设施', triage_patients: '开展患者分诊',
  wait: '保持待命', request_transfer: '请求患者转运', request_support: '请求支持',
  // —— Agent V2 资源、生命周期与执行状态 ——
  attention: '注意力', coordination: '协调能力', response: '响应能力', authority: '行政权限',
  fiscal: '相对财政容量', facility_control: '设施控制能力',
  technical: '技术能力', analysis: '分析能力', treatment: '救治能力',
  bed: '床位容量', supply: '供应能力', mobility: '机动能力', livelihood: '生计能力',
  volunteer: '志愿服务能力', inventory: '库存能力', logistics: '物流能力',
  procurement: '采购能力', verification: '核验能力', reach: '信息触达',
  resilience: '生态韧性', retention: '滞留能力',
  active: '活跃', pending_activation: '待激活', retired: '已退出', merged: '已合并',
  provisional: '临时', runtime_provisional: '运行期临时主体', runtime_specialist: '运行期专业单元', institution_required: '需机构主体',
  facility_required: '需具体设施', subunit_required: '需具体单元', aggregate_allowed: '允许聚合表示',
  population_group: '人群聚合', specific_facility: '具体设施',
  region_aggregate: '区域聚合', group_representative: '群体代表',
  subunit: '具体单元', facility: '具体设施',
  bound: '已绑定', partial: '部分绑定', unbound: '未绑定', blocked: '执行受阻', executed: '已执行',
  policy_explicit: '政策明确指定', executor_jurisdiction_inferred: '依据执行者辖区推断',
  agent_created: '创建临时代理体', agent_split: '拆分聚合代理体',
  agent_reactivated: '唤醒休眠代理体', agent_activated: '代理体已激活',
  relationship_activated: '关系已激活', relationship_promoted: '关系已固化',
  relationship_interrupted: '关系已中断', relationship_updated: '关系已更新',
  information_disclosure: '信息披露', coordination_success: '协同达成',
  cooperation: '协作事件', resource_coordination: '资源协调',
  constraint_enforcement: '限制执行', challenge: '公开质询',
  success: '成功', failed: '失败',
  // —— 关系/边类型 ——
  dynamic_edge: '动态关系', self_loop: '自关联', structural: '结构关系',
  spatial_fact: '空间事实', causal: '因果关系', edge: '关系', relationship: '关系',
  anchor: '锚定', agent_anchor: '区域锚定', region_neighbor: '区域邻接',
  subregion_parent: '所属区域', agent_relationship: '主体关系', agent_influence: '主体影响',
  RELATED_TO: '相关', RELATED: '相关', related_to: '相关', related: '相关',
  affects: '影响', AFFECTS: '影响', located_in: '位于', LOCATED_IN: '位于',
  transmits_to: '向下游传导', competes_for: '竞争资源', depends_on: '依赖',
  reports_to: '上报给', coordinates_with: '协同',
  regulates: '调控', exposes: '暴露', amplifies: '放大', mitigates: '缓解',
  triggers: '触发', approaches_threshold: '逼近阈值', triggers_collapse: '触发崩溃',
  collaborates_with: '协作', 'collaborates with': '协作', collaborates: '协作',
  supports: '支持', uses: '使用', coordinates: '协调', collaborate: '协作',
  coordinate: '协调', inform: '通知', request: '请求', escalate: '上报',
  comply: '配合', mobilize: '动员', interaction: '交互',
  // —— 互动/传播渠道 ——
  water_flow: '水流', information: '信息', social: '社会', community: '社区',
  economic: '经济', mechanism: '机制', transport: '交通',
  ecology_corridor_signal: '生态廊道', governance_hierarchy: '治理层级',
  local_contact: '就近接触', health_response: '卫生响应', supply_chain: '供应链',
  media_reach: '媒体触达', physical_contact: '物理接触', information_flow: '信息流',
  media_link: '媒体触达', response_bridge: '响应桥接',
  cross_region_mechanism_bridge: '跨区域机制桥接',
  local_mechanism_coupling: '局部机制耦合',
  // —— 状态向量字段（节点详情）——
  exposure_score: '暴露度', spread_pressure: '扩散压力', panic_level: '恐慌度',
  vulnerability_score: '脆弱性', ecosystem_integrity: '生态完整度',
  public_trust: '公众信任', service_capacity: '服务承载', response_capacity: '响应能力',
  economic_stress: '经济压力', livelihood_stability: '生计稳定',
  contaminant_concentration: '污染物浓度', exposure: '暴露', panic: '恐慌',
  trust: '信任', vulnerability: '脆弱性',
  // —— 代理体/节点字段 ——
  agent_name: '名称', agent_type: '类型', agent_subtype: '子类型',
  node_family: '节点族', role_type: '角色', home_region_id: '主区域',
  home_subregion_id: '主子区域', primary_region: '主区域', profession: '职业',
  scope: '范围', source_entity_type: '来源类型', summary: '摘要', name: '名称',
  location: '位置', scene_type: '场景类型', source_kind: '来源类型',
  service_scope: '服务范围', jurisdiction: '管辖范围',
  // —— 认知来源 / 校验 ——
  observed: '观测', inferred: '推断', speculative: '推测', assumed: '假设',
  imagined: '想象', accepted: '已采纳', accepted_low_confidence: '低置信采纳',
  fallback_explicit: '显式降级', llm_relation_candidate: '模型候选',
  map_seed_grounded: '地图接地', local_fallback: '本地回退',
  live: '实时推理', derived_template: '规则归纳', rule_based: '规则归纳',
  // —— 时滞 / 方向 ——
  immediate: '即时', hours: '小时级', days: '天级', weeks: '周级', months: '月级',
  positive: '正向', negative: '负向', neutral: '中性', bidirectional: '双向', conditional: '条件性',
  increase: '增强', decrease: '减弱', higher_is_worse: '越高越差', higher_is_better: '越高越好',
  // —— 风险/运行态 ——
  watch: '观察', incident: '事件', tracked: '跟踪', elevated: '升高',
  critical: '危急', resolved: '已解除', dormant: '休眠', candidate: '候选',
  rising: '上升', falling: '回落', steady: '平稳',
  reinforcing: '增强环', balancing: '平衡环', emergent: '涌现', emergent_count: '涌现',
  status_escalation: '张力升级', status_deescalation: '张力回落', turning_point: '拐点',
  ecological_coupling: '生态耦合', baseline: '基线方案', intervention: '干预方案',
  branch: '方案分支', cluster: '影响群簇',
  infrastructure_access: '基础设施可达性', response_capacity: '响应能力',
  population_exposure: '人群暴露', water_ecology: '水生态', urban_flood: '城市洪涝',
  risk_emerged: '风险涌现', primary_risk_switched: '主风险切换', reframed: '主风险切换',
  variable_injected: '变量注入',
  disaster_injection: '灾害扰动', policy_injection: '政策干预',
  // —— 风险对象 V2 主分类 / 生成方式 / 质量标记 ——
  ecological_environment: '生态环境', health_safety: '健康安全',
  infrastructure_continuity: '基础设施连续性', mobility_logistics: '交通与物流',
  resource_supply: '资源供应', economy_livelihood: '经济与生计',
  governance_response: '治理响应', information_trust: '信息与信任',
  compound_cascade: '复合级联', other_emergent: '其他涌现风险',
  mechanism_graph_deterministic: '机制图规则生成',
  mechanism_graph_llm_named: '机制图生成 · 模型归纳命名',
  mechanism_graph_hybrid: '机制图生成 · 模型归纳命名',
  runtime_emergent_deterministic: '运行时机制涌现',
  deterministic_fallback: '确定性命名降级',
  no_risk_candidate_passed_evidence_threshold: '没有候选通过证据阈值',
  no_valid_mechanism_path: '没有有效机制路径',
  dangling_mechanism_references_rejected: '已拒绝悬空机制引用',
  invalid_display_references_rejected: '已拒绝占位或内部显示值',
  validated_cross_region_feedback_loop: '已校验跨区域反馈环',
  unresolved_source_citation_removed: '未解析来源引用已剔除',
  llm_naming_fallback: '模型命名降级为确定性标题',
  mechanism_reference: '机制节点引用',
  receptor_role_demand: '受影响对象匹配',
  mechanism_path_mention: '机制路径点名',
  entity_anchor: '真实实体锚定',
  scenario_text_mention: '场景文本点名',
  scene_metadata_inference: '场景元数据推断',
  region_scope_inferred_from_scene_metadata: '部分作用区域来自场景元数据推断',
  entity_scope_inferred_from_scene_metadata: '部分受影响主体来自场景元数据推断',
  structural_fallback: '低置信结构候选',
  llm_timeout: '模型命名超时，已确定性降级',
  llm_invalid_json: '模型返回无效，已确定性降级',
  llm_reference_mismatch: '模型引用不一致，已确定性降级',
  llm_unavailable: '模型命名不可用，已确定性降级',
  dangling_reference: '存在悬空引用', speculative_only: '仅有推测关系',
  // —— 运行状态（英文状态泄漏）——
  idle: '空闲', preparing: '准备中', initializing: '初始化', ready: '就绪',
  processing: '处理中', running: '运行中', generating: '生成中', completed: '已完成',
  error: '错误', stopped: '已停止', pending: '等待中', failed: '失败',
  building_graph: '构建图谱', generating_config: '生成配置', config_ready: '配置就绪',
  generating_ontology: '生成本体', reading: '读取图谱实体',
  generating_profiles: '生成代理体画像', copying_scripts: '准备模拟脚本',
  // —— 通用 ——
  Unknown: '未知', unknown: '未知', Unnamed: '未命名', none: '无',
  runtime: '运行时', stable_context: '稳态背景', seed: '场景先验', manual: '手动新增',
  local: '局部', global: '全局', systemic: '系统性', cross_region: '跨区域',
  cross_scale: '跨尺度',
  fallback_explicit_low_confidence: '低置信显式降级',
}

// 永不上屏的内部/动画/调试字段 —— 节点详情等处直接过滤掉。
const INTERNAL_KEY_SET = new Set([
  'uuid', 'id', 'edge_id', 'group_id', 'name_embedding', 'username',
  'source_entity_uuid', 'simulation_id', 'project_id', 'graph_id',
  'first_seen_round', 'last_active_round', 'created_round', 'reconfirm_count',
  'delay_ms', 'timeline_delay_ms', 'animation_elapsed_ms', 'animation_progress',
  'animation_due', 'animation_status', 'raw_animation_status', 'state_status',
  'value', 'delta', 'is_synthesized', 'is_geographic', 'placement',
  'edge_layer', 'epistemic', 'provenance', 'channel', 'origin', 'validation_status',
])

const INTERNAL_DISPLAY_TOKEN_SET = new Set([
  'entity', 'node', 'nodes', 'object', 'thing',
  'blue', 'brown', 'orange', 'green', 'purple', 'cyan', 'red', 'yellow', 'gray', 'grey',
])

const GENERIC_DISPLAY_LABEL_SET = new Set(['实体', '节点', '对象'])

export function isInternalAttributeKey(key) {
  const text = String(key || '').trim().toLowerCase()
  if (!text) return true
  if (INTERNAL_KEY_SET.has(text)) return true
  // 任何 *_round / animation_* / *_uuid / *_id 内部字段
  return /(_round$|^animation_|_uuid$|_id$|_ms$)/.test(text)
}

export function translateDisplayToken(value, fallback = '') {
  const raw = String(value ?? fallback ?? '').trim()
  if (!raw) return fallback
  if (TOKEN_MAP[raw]) return TOKEN_MAP[raw]
  const lower = raw.toLowerCase()
  if (TOKEN_MAP[lower]) return TOKEN_MAP[lower]
  const normalized = lower.replace(/[\s-]+/g, '_')
  if (TOKEN_MAP[normalized]) return TOKEN_MAP[normalized]
  const inferred = inferDisplayTokenZh(raw)
  if (inferred) return inferred
  return raw || fallback
}

const INVALID_DISPLAY_COPY_SET = new Set([
  '内部标识',
  '未命名项',
  '未命名节点',
  '未命名区域',
  '未命名子区域',
  '未命名代理体',
  '未命名对象',
  '未命名关系',
  '内容待本地化',
])

// 用户可见正文的统一出口。未知英文、类名和机器 token 会由
// sanitizeDisplayCopy 剔除；调用方必须提供有业务含义的中文 fallback，
// 不再把原始值作为 fallback 传回界面。
export function safeDisplayText(value, fallback = '') {
  const text = sanitizeDisplayCopy(value, '').trim()
  if (!text || INVALID_DISPLAY_COPY_SET.has(text)) return fallback
  if (/^[\d\s.%‰+-]+$/.test(text)) return fallback
  return text
}

// 枚举 / 标签的统一出口。已知 token 先翻译，未知 token 进入正文清洗；
// 最终仍不可展示时只返回中文 fallback。
export function safeDisplayToken(value, fallback = '其他') {
  const raw = String(value ?? '').trim()
  if (!raw) return fallback
  if (/^\d+$/.test(raw)) return fallback
  if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(raw)) return fallback
  return safeDisplayText(translateDisplayToken(raw, ''), fallback)
}

// API、网络与运行时错误不得把英文异常、路由或内部调用信息直接上屏。
export function safeDisplayError(error, fallback = '操作失败，请稍后重试。') {
  const payload = error?.response?.data
  const raw = payload?.error || payload?.message || error?.error || error?.message || error
  const rawText = String(raw || '')
  if (
    /(?:Traceback|[A-Za-z]+(?:Error|Exception)|\b(?:GET|POST|PUT|PATCH|DELETE)\b|\/api\/|https?:\/\/|\b(?:\d{1,3}\.){3}\d{1,3}\b|\/(?:tmp|var|private|Users|home|opt|srv|app|etc)\/|\\(?:Users|Windows)\\)/i.test(rawText)
    || /\bNo match for\b|\bMissing required param\b|\[object Object\]|Cannot read (?:properties|property)/i.test(rawText)
    || /[\[{][\s\S]*(?:["'][^"']+["']|[A-Za-z_$][\w$]*)\s*:/.test(rawText)
  ) {
    return fallback
  }
  const text = safeDisplayText(raw, '')
  if (!text || !/[\u4e00-\u9fff]/.test(text)) return fallback
  if (['失败', '错误', '未知', '异常'].includes(text)) return fallback
  return text
}

export function formatTokenLabelZh(value, fallback = '') {
  const translated = translateDisplayToken(value, fallback)
  // 已译成中文则原样返回；否则把 snake/kebab 转成可读空格分隔
  if (/[一-鿿]/.test(translated)) return translated
  return translated.replace(/[_-]+/g, ' ')
}

export function normalizeDisplayLabels(labels, limit = 3) {
  if (!Array.isArray(labels)) return []
  const seen = new Set()
  const result = []
  labels.forEach((value) => {
    const raw = String(value || '').trim()
    if (!raw) return
    const lower = raw.toLowerCase()
    if (INTERNAL_DISPLAY_TOKEN_SET.has(lower)) return
    const translated = formatTokenLabelZh(raw, '').trim()
    const label = sanitizeDisplayCopy(translated, '').trim()
    if (!label || ['内部标识', '未命名项', '内容待本地化'].includes(label) || GENERIC_DISPLAY_LABEL_SET.has(label)) return
    const key = label.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    result.push(label)
  })
  return result.slice(0, limit)
}

function splitTokenParts(value) {
  return String(value || '')
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-]+/g, '_')
    .split('_')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
}

function inferDisplayTokenZh(value) {
  const parts = splitTokenParts(value)
  if (parts.length === 0) return ''

  const exact = TOKEN_MAP[parts.join('_')] || TOKEN_MAP[parts.join('')]
  if (exact) return exact

  const suffix = parts[parts.length - 1]
  const head = parts.slice(0, -1)
  const headLabel = head
    .map((part) => TOKEN_MAP[part])
    .filter(Boolean)
    .join('')

  const suffixMap = {
    actor: '行动者',
    bureau: '部门',
    office: '办公室',
    committee: '委员会',
    association: '协会',
    station: '站点',
    worker: '工作人员',
    operator: '运营方',
    owner: '经营者',
    inspector: '监察员',
    volunteer: '志愿者',
    scientist: '科研人员',
    journalist: '记者',
    farmer: '农业生产者',
    node: '节点',
    carrier: '载体',
    receptor: '受体',
    species: '物种',
    birds: '鸟群',
    biome: '生境',
    ecology: '生态',
    sentinel: '哨兵',
    group: '群体',
    type: '类型',
    role: '角色',
  }

  if (headLabel && suffixMap[suffix]) return `${headLabel}${suffixMap[suffix]}`
  if (!headLabel && suffixMap[suffix]) return suffixMap[suffix]
  if (parts.length === 1 && TOKEN_MAP[parts[0]]) return TOKEN_MAP[parts[0]]
  return ''
}

// 字段 key → 中文标签（节点详情等）。未收录的内部 key 由调用方先用
// isInternalAttributeKey 过滤；其余回落到通用清洗。
export function formatFieldLabelZh(key, fallback = '') {
  const text = String(key || '').trim()
  if (!text) return fallback
  return TOKEN_MAP[text] || TOKEN_MAP[text.toLowerCase()] || formatTokenLabelZh(text, fallback)
}

export function formatDistanceLabelZh(value) {
  if (value === null || value === undefined || value === '') return ''
  const number = Number(value)
  // 分类型距离带（near/mid/far 等）走中文清洗层，不再裸露英文
  if (!Number.isFinite(number)) return safeDisplayToken(value, '')
  if (Math.abs(number) >= 1000) return `${(number / 1000).toFixed(1)} km`
  return `${Math.round(number)} m`
}

export function formatLandUseLabelZh(value) {
  const text = String(value ?? '').trim()
  const map = {
    residential: '居住', commercial: '商业', industrial: '工业', agricultural: '农业',
    forest: '林地', wetland: '湿地', water: '水域', conservation: '保护区',
  }
  return map[text] || safeDisplayToken(text, '')
}

const DISPLAY_ONLY_ALLOWED_LATIN_RE = /^(?:Kaleido|PDF|JSON|CSV|URL|EPA|USGS|NOAA|OSM|WMS)$/i

function stripUnsafeDisplayBlocks(value) {
  return String(value || '')
    .replace(/<tool_calls?\b[^>]*>[\s\S]*?<\/tool_calls?>/gi, '')
    .replace(/```[\s\S]*?```/g, '')
    .split(/\r?\n/)
    .filter((line) => {
      const text = line.trim()
      if (!text) return true
      if (/^<\/?[A-Za-z][^>]*>$/.test(text)) return false
      if (/^["']?[A-Za-z_][A-Za-z0-9_-]*["']?\s*:\s*/.test(text)) return false
      if (/^[{}\[\],]+$/.test(text)) return false
      return true
    })
    .join('\n')
}

function hasMeaningfulDisplayLine(line) {
  const semantic = String(line || '')
    .replace(/^[\s#>*+\-]+/, '')
    .replace(/[\s\d.,，。；;：:！？!?、()（）\[\]{}'"`~_*+=<>|\\/→←–—%‰]+/g, '')
  if (!semantic) return false
  if (/[一-鿿]/.test(semantic)) return true
  return DISPLAY_ONLY_ALLOWED_LATIN_RE.test(semantic)
}

export function sanitizeDisplayCopy(value, fallback = '') {
  const raw = String(value ?? fallback ?? '').trim()
  if (!raw) return fallback
  const cleaned = stripUnsafeDisplayBlocks(raw)
    .replace(/!?\[([^\]]+)\]\((?:https?:\/\/|\/(?:api|v\d+)\/)[^)]+\)/gi, '$1')
    // 地图/图谱历史数据里可能把机器前缀和中文名称拼在同一字段中，
    // 例如 feature_context_admin_district_南山区。保留中文业务名，丢弃内部前缀。
    .replace(/\b(?:[A-Za-z][A-Za-z0-9]*[_-])+(?=[\u3400-\u9fff])/g, '')
    .replace(/([\u3400-\u9fff])[_-]+(?=[\u3400-\u9fff])/g, '$1 · ')
    .replace(/\bStep\s*1\b/gi, '第一步')
    .replace(/\bStep\s*2\b/gi, '第二步')
    .replace(/\bStep\s*3\b/gi, '第三步')
    .replace(/\bStep\s*4\b/gi, '第四步')
    .replace(/https?:\/\/\S+/gi, '')
    .replace(/\/(?:api|v\d+)\/[A-Za-z0-9_./?=&%:-]+/gi, '')
    .replace(/\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:\/\S*)?/g, '')
    .replace(/\/(?:tmp|var|private|Users|home|opt|srv|app|etc)(?:\/[^\s"'`)<>{}\]]+)+/gi, '')
    .replace(/[A-Za-z]:\\(?:Users|Windows|Temp)(?:\\[^\s"'`)<>{}\]]+)+/gi, '')
    .replace(/\[(?:Errno|Error)?\s*\d+\]/gi, '')
    .replace(/<\/?[A-Za-z][^>]*>/g, '')
    .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi, '')
    .replace(/\bcrisis_mode\b/gi, '灾难态')
    .replace(/\bbaseline_mode\b/gi, '基线态')
    .replace(/\bmarine_current\b/gi, '海洋环流')
    .replace(/\benvfish_summary\b/gi, '推演摘要')
    .replace(/\btool_calls?\b/gi, '工具调用')
    .replace(/\bEnvFish\b/g, 'Kaleido')
    .replace(/\bdisaster_injection\b/gi, '灾害扰动')
    .replace(/\bpolicy_injection\b/gi, '政策干预')
    .replace(/\bgenerating_profiles\b/gi, '生成代理体画像')
    .replace(/\bgenerating_config\b/gi, '生成推演配置')
    .replace(/\bcopying_scripts\b/gi, '准备模拟脚本')
    .replace(/\bADMINISTRATIVEREGION\b/g, '行政区域')
    .replace(/\bGOVERNANCEACTOR\b/g, '治理主体')
    .replace(/Agent人设/gi, '代理体画像')
    .replace(/代理体人设/g, '代理体画像')
    .replace(/\bagent interaction\b/gi, '代理体互动')
    .replace(/\bagents?\b/gi, '代理体')
    .replace(/\bRESTRICT\b/g, '限制干预')
    .replace(/\bDISCLOSE\b/g, '信息公开')
    .replace(/\bvs\.?/gi, '与')
    .replace(/\bshort cycle present\b/gi, '存在短反馈环')
    .replace(/\btwo cycle present\b/gi, '存在双节点反馈环')

  const withoutMachineTokens = cleaned.replace(
    /\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b/g,
    (token) => {
      const translated = translateDisplayToken(token, '')
      if (translated && translated !== token && /[一-鿿]/.test(translated)) return translated
      return ''
    }
  )

  const withoutClassNames = withoutMachineTokens.replace(
    /\b[A-Z][A-Za-z0-9]*(?:Agent|Actor|Region|Node|Object|Edge|Profile)\b/g,
    (token) => {
      const translated = translateDisplayToken(token, '')
      return translated && /[一-鿿]/.test(translated) ? translated : ''
    }
  )

  const withoutUnknownEnglish = withoutClassNames.replace(
    /\b[A-Za-z][A-Za-z0-9]*\b/g,
    (token) => {
      if (/^(?:KALEIDO|PDF|JSON|CSV|URL|EPA|USGS|NOAA|OSM|WMS)$/i.test(token)) return token
      const translated = translateDisplayToken(token, '')
      return translated && translated !== token && /[一-鿿]/.test(translated) ? translated : ''
    }
  )
    .replace(/["']?[\\/]{2,}[^\s，。；：！？、]*/g, '')
    .replace(/([:：])(?:\s*[:：])+/g, '$1')
    .replace(/[ \t]+\.[ \t]+/g, ' ')
    .replace(/[:：][ \t]*["']{1,2}[ \t]*$/gm, '')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/[ \t]+([，。；：！？、])/g, '$1')
    .replace(/([\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])/g, '$1')
    .replace(/^[\s,.;:：|/\\\-=<>→←]+|[\s,.;:：|/\\\-=<>→←]+$/g, '')
    .trim()

  const meaningfulText = withoutUnknownEnglish
    .split(/\r?\n/)
    .map(line => line.trimEnd())
    .filter(line => !line.trim() || hasMeaningfulDisplayLine(line))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

  if (!meaningfulText) return fallback && fallback !== raw ? fallback : ''
  if (/[一-鿿]/.test(meaningfulText)) return meaningfulText
  if (DISPLAY_ONLY_ALLOWED_LATIN_RE.test(meaningfulText)) return meaningfulText

  const translated = translateDisplayToken(meaningfulText, '')
  if (translated && /[一-鿿]/.test(translated)) return translated
  return fallback && fallback !== raw ? fallback : '内容待本地化'
}

function isSafeMarkdownStructuralLine(line) {
  const text = String(line || '').trim()
  if (!text) return false
  const compact = text.replace(/\s+/g, '')
  if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(compact)) return true
  return text.includes('|') && /^[:|\-\s]+$/.test(text) && /-{3,}/.test(text)
}

// 正式报告需要在清洗显示字段的同时保留 Markdown 的段落、分隔线和表格
// 分隔行。不要把整篇报告当成普通短文案清洗，否则表格和段落会被压平。
export function sanitizeDisplayMarkdown(value, fallback = '') {
  const raw = String(value ?? '').trim()
  if (!raw) return fallback

  let hasReadableContent = false
  const result = stripUnsafeDisplayBlocks(raw)
    .split(/\r?\n/)
    .map((line) => {
      if (!line.trim()) return ''
      if (isSafeMarkdownStructuralLine(line)) return line.trimEnd()
      const sanitized = sanitizeDisplayCopy(line, '')
      if (sanitized && hasMeaningfulDisplayLine(sanitized)) hasReadableContent = true
      return sanitized
    })
    .filter((line, index, lines) => line || (index > 0 && lines[index - 1]))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()

  return hasReadableContent && result ? result : fallback
}
