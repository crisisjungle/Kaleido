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
  river_basin: '流域', 'river basin': '流域', city: '城市区域', district: '行政区',
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
  humanactor: '个体', governmentactor: '政府', organizationactor: '组织',
  ecologicalreceptor: '生态受体', ecological_receptor: '生态受体',
  environmentalcarrier: '环境载体', environmental_carrier: '环境载体',
  carrier: '载体', institution: '机构', process: '过程', resource: '资源',
  riskobject: '风险对象', risk_object: '风险对象', threshold: '阈值',
  resident: '居民', tourist: '游客', scientist: '科研人员', journalist: '媒体',
  worker: '工作者', field_observer: '现场观察员', activist: '行动者',
  community_committee: '社区委员会', white_collar: '白领', plant_operator: '设施运营方',
  transport_node: '交通节点', emergencyworker: '应急人员', unspecified: '未明确',
  Region: '区域', Risk: '风险', Actor: '行动者', risk: '风险',
  // —— 关系/边类型 ——
  dynamic_edge: '动态关系', self_loop: '自关联', structural: '结构关系',
  spatial_fact: '空间事实', causal: '因果关系', edge: '关系', relationship: '关系',
  anchor: '锚定', agent_anchor: '区域锚定', region_neighbor: '区域邻接',
  subregion_parent: '所属区域', agent_relationship: '主体关系', agent_influence: '主体影响',
  RELATED_TO: '相关', RELATED: '相关', related_to: '相关', related: '相关',
  affects: '影响', AFFECTS: '影响', located_in: '位于', LOCATED_IN: '位于',
  transmits_to: '向下游传导', competes_for: '竞争资源', depends_on: '依赖',
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
  // —— 认知来源 / 校验 ——
  observed: '观测', inferred: '推断', speculative: '推测', assumed: '假设',
  imagined: '想象', accepted: '已采纳', accepted_low_confidence: '低置信采纳',
  fallback_explicit: '显式降级', llm_relation_candidate: '模型候选',
  map_seed_grounded: '地图接地', local_fallback: '本地回退',
  // —— 时滞 / 方向 ——
  immediate: '即时', hours: '小时级', days: '天级', weeks: '周级', months: '月级',
  positive: '正向', negative: '负向', neutral: '中性', bidirectional: '双向', conditional: '条件性',
  increase: '增强', decrease: '减弱', higher_is_worse: '越高越差', higher_is_better: '越高越好',
  // —— 风险/运行态 ——
  watch: '观察', incident: '事件', tracked: '跟踪', elevated: '升高',
  critical: '危急', rising: '上升', falling: '回落', steady: '平稳',
  reinforcing: '增强环', balancing: '平衡环', emergent: '涌现', emergent_count: '涌现',
  status_escalation: '张力升级', status_deescalation: '张力回落', turning_point: '拐点',
  // —— 运行状态（英文状态泄漏）——
  idle: '空闲', preparing: '准备中', initializing: '初始化', ready: '就绪',
  processing: '处理中', running: '运行中', generating: '生成中', completed: '已完成',
  error: '错误', stopped: '已停止', pending: '等待中', failed: '失败',
  building_graph: '构建图谱', generating_config: '生成配置', config_ready: '配置就绪',
  generating_ontology: '生成本体',
  // —— 通用 ——
  Unknown: '未知', unknown: '未知', Unnamed: '未命名', none: '无',
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

export function isInternalAttributeKey(key) {
  const text = String(key || '').trim().toLowerCase()
  if (!text) return true
  if (INTERNAL_KEY_SET.has(text)) return true
  // 任何 *_round / animation_* / *_uuid / *_id 内部字段
  return /(_round$|^animation_|_uuid$|_ms$)/.test(text)
}

export function translateDisplayToken(value, fallback = '') {
  const raw = String(value ?? fallback ?? '').trim()
  if (!raw) return fallback
  if (TOKEN_MAP[raw]) return TOKEN_MAP[raw]
  const lower = raw.toLowerCase()
  if (TOKEN_MAP[lower]) return TOKEN_MAP[lower]
  return raw || fallback
}

export function formatTokenLabelZh(value, fallback = '') {
  const translated = translateDisplayToken(value, fallback)
  // 已译成中文则原样返回；否则把 snake/kebab 转成可读空格分隔
  if (/[一-鿿]/.test(translated)) return translated
  return translated.replace(/[_-]+/g, ' ')
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
  if (!Number.isFinite(number)) return translateDisplayToken(value, String(value))
  if (Math.abs(number) >= 1000) return `${(number / 1000).toFixed(1)} km`
  return `${Math.round(number)} m`
}

export function formatLandUseLabelZh(value) {
  const text = String(value ?? '').trim()
  const map = {
    residential: '居住', commercial: '商业', industrial: '工业', agricultural: '农业',
    forest: '林地', wetland: '湿地', water: '水域', conservation: '保护区',
  }
  return map[text] || formatTokenLabelZh(text)
}
