const DIRECT_MAP = {
  regionlayers: '区域层级',
  agentanchors: '代理锚点',
  adjacencylinks: '邻接连接',
  coverage: '覆盖率',
  totalagents: '代理体总数',
  humanorg: '个体 / 组织',
  ecogov: '生态 / 治理',
  fallback: '降级模式',
  interactionedges: '交互边',
  crossregion: '跨区域',
  channels: '互动渠道',
  relationtypes: '关系类型',
  primaryobject: '主要风险对象',
  entitylinks: '实体关联',
  regionscope: '区域范围',
  affectedclusters: '受影响群簇',
  agentscope: '代理体范围',
  subregionheat: '子区域热度',
  interactionview: '交互视图',
  leadagent: '领先代理体',
  seedstatus: '种子状态',
  nodes: '节点',
  edges: '边',
  layers: '图层',
  avgconfidence: '平均置信度',
  hidden: '隐藏',
  focus: '聚焦',
  loading: '加载中',
  ready: '就绪',
  idle: '空闲',
  refresh: '刷新',
  result: '结果',
  simulation: '推演',
  radius: '半径',
  mapfirst: '地图优先',
  maprelationshipvisualization: '地图关系可视化',
  residentialzone: '居住区',
  coastalzone: '滨海区',
  urbanedge: '城市边缘区',
  infrastructurecorridor: '基础设施廊道',
  layermacro: '宏观分层',
  city: '城市区',
  ecological: '生态',
  ecology: '生态',
  commercial: '商业',
  residential: '居住',
  coastal: '滨海',
  water: '水域',
  forest: '林地',
  urban: '城市',
  expansion: '扩展区',
  mixeduse: '混合用地',
  inlandwater: '内陆水体',
  marine: '海洋',
  air: '大气',
  graphnode: '图谱节点',
  riskref: '风险引用',
  scope: '作用域',
  profile: '档案',
  general: '综合',
  branch: '分支',
  all: '全域',
  watch: '观察',
  incident: '事件',
  primary: '主要',
  severity: '严重性',
  actionability: '可行动性',
  confidence: '置信度',
  disaster: '污染变量',
  policy: '政策变量',
  whynow: '当前触发原因',
  rootpressures: '根源压力',
  simulationconfig: '模拟配置',
  graphfallback: '图谱降级',
  unknownregion: '未知区域',
  supporting: '支持',
  opposing: '反对',
  observer: '观察',
  neutral: '中立',
  critical: '紧急',
  watchstate: '预警',
  stable: '稳定',
  calm: '平稳',
  human: '个体',
  organization: '组织',
  governance: '治理',
  infrastructure: '基础设施',
  carrier: '环境载体',
  agent: '代理体',
  restrict: '限制',
  relocate: '迁移',
  subsidize: '补贴',
  monitor: '监测',
  disclose: '披露',
  repair: '修复',
  ban: '禁止',
  reopen: '重开',
  social: '社会',
  generalchannel: '通用',
  subregion: '子区域',
  macroregion: '宏观区域',
  region: '区域',
  cluster: '群簇',
  interaction: '交互',
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  accepted: '已接收',
  active: '生效中',
  configured: '已配置',
  queued: '排队中',
  running: '运行中',
  stopped: '已停止',
  starting: '启动中',
  monitors: '监测',
  graphfallbackpreview: '图谱降级预览',
  source: '来源',
  target: '目标',
}

const LAND_USE_MAP = {
  urban: '城市建成',
  residential: '居住',
  commercial: '商业',
  industrial: '工业',
  civic: '公共服务',
  ecology: '生态',
  water: '水域',
  transport: '交通',
  open: '开放地表',
}

const DISTANCE_MAP = {
  core: '核心带',
  near: '近岸影响带',
  transition: '过渡带',
  far: '远距缓冲带',
}

function normalizeKey(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '')
}

export function translateDisplayToken(value, fallback = '') {
  const raw = String(value || '').trim()
  if (!raw) return fallback

  const key = normalizeKey(raw)
  if (DIRECT_MAP[key]) return DIRECT_MAP[key]

  const layerMatch = raw.match(/^layer\s+(\d+)$/i)
  if (layerMatch) return `第 ${layerMatch[1]} 层`

  const neighborsMatch = raw.match(/^(\d+)\s+neighbors?$/i)
  if (neighborsMatch) return `${neighborsMatch[1]} 个相邻区域`

  const agentsMatch = raw.match(/^(\d+)\s+agents?$/i)
  if (agentsMatch) return `${agentsMatch[1]} 个代理体`

  const subregionsMatch = raw.match(/^(\d+)\s+subregions?$/i)
  if (subregionsMatch) return `${subregionsMatch[1]} 个子区域`

  const interactionsMatch = raw.match(/^(\d+)\s+interactions?$/i)
  if (interactionsMatch) return `${interactionsMatch[1]} 次交互`

  const roundsMatch = raw.match(/^(\d+)\s+rounds?$/i)
  if (roundsMatch) return `${roundsMatch[1]} 轮`

  const objectsMatch = raw.match(/^(\d+)\s+objects?$/i)
  if (objectsMatch) return `${objectsMatch[1]} 个对象`

  const linkedNodesMatch = raw.match(/^(\d+)\s+linked\s+nodes?$/i)
  if (linkedNodesMatch) return `${linkedNodesMatch[1]} 个关联节点`

  const taskMatch = raw.match(/^task\s+(.+)$/i)
  if (taskMatch) return `任务 ${taskMatch[1]}`

  const fromMatch = raw.match(/^from\s+(.+)$/i)
  if (fromMatch) return `来源 ${fromMatch[1]}`

  const toMatch = raw.match(/^to\s+(.+)$/i)
  if (toMatch) return `到 ${toMatch[1]}`

  const intensityMatch = raw.match(/^intensity\s+(.+)$/i)
  if (intensityMatch) return `强度 ${intensityMatch[1]}`

  const confidenceMatch = raw.match(/^confidence\s+(.+)$/i)
  if (confidenceMatch) return `置信度 ${confidenceMatch[1]}`

  const vulMatch = raw.match(/^vul\s+(.+)$/i)
  if (vulMatch) return `脆弱性 ${vulMatch[1]}`

  const sevMatch = raw.match(/^sev\s+(.+)$/i)
  if (sevMatch) return `严重性 ${sevMatch[1]}`

  const actMatch = raw.match(/^act\s+(.+)$/i)
  if (actMatch) return `可行动性 ${actMatch[1]}`

  const mismatchMatch = raw.match(/^mismatch\s+(.+)$/i)
  if (mismatchMatch) return `错配风险 ${mismatchMatch[1]}`

  const targetsMatch = raw.match(/^targets\s+(.+)$/i)
  if (targetsMatch) return `目标 ${targetsMatch[1] === 'all' ? '全域' : targetsMatch[1]}`

  return raw
}

export function formatTokenLabelZh(value, fallback = '') {
  const translated = translateDisplayToken(value, '')
  if (translated) return translated
  const text = String(value || '')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
  return text || fallback
}

export function formatLandUseLabelZh(value) {
  return LAND_USE_MAP[String(value || '').toLowerCase()] || formatTokenLabelZh(value, '子区域')
}

export function formatDistanceLabelZh(value) {
  return DISTANCE_MAP[String(value || '').toLowerCase()] || formatTokenLabelZh(value, '未知')
}
