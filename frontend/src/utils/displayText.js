export function translateDisplayToken(value, fallback = '') {
  const text = String(value ?? fallback ?? '').trim()
  const map = {
    baseline_mode: '基线态',
    crisis_mode: '灾难态',
    legacy_envfish_v1: '经典推演',
    llm_mechanism_v1: '机制推演',
    policy: '政策',
    disaster: '灾害',
    restrict: '限制',
    relocate: '迁移',
    subsidize: '补贴',
    monitor: '监测',
    disclose: '披露',
    repair: '修复',
    ban: '禁用',
    reopen: '重开',
    macro: '宏观',
    meso: '中观',
    micro: '微观',
    region: '区域',
    subregion: '细分区域',
    agent: '代理体',
    profile: '画像',
    general: '综合',
    coastal_zone: '近海区域',
    'coastal zone': '近海区域',
    coast: '海岸',
    coastal: '沿海',
    river_basin: '流域',
    'river basin': '流域',
    city: '城市区域',
    district: '行政区',
    ecological: '生态',
    wetland: '湿地',
    forest_park: '森林公园',
    'forest park': '森林公园',
    mountain: '山地',
    reservoir: '水库',
    water_source: '水源地',
    'water source': '水源地',
    commercial: '商业',
    urban: '城市建成区',
    flood_risk: '洪涝风险',
    'flood risk': '洪涝风险',
    landslide_risk: '滑坡风险',
    'landslide risk': '滑坡风险',
    infrastructure: '基础设施',
    science_city: '科学城',
    'science city': '科学城',
    protected_area: '保护区',
    'protected area': '保护区',
    cross_border: '跨边界',
    'cross border': '跨边界',
    residential: '居住',
    industrial: '工业',
    agricultural: '农业',
    conservation: '保护区',
    government: '政府',
    governance: '治理',
    organization: '组织',
    human: '个体',
    ecology: '生态',
    actor: '行动者',
    entity: '实体',
    Entity: '实体',
    Region: '区域',
    Risk: '风险',
    Actor: '行动者',
    risk: '风险',
    watch: '观察',
    incident: '事件',
    RELATED_TO: '相关',
    RELATED: '相关',
    related_to: '相关',
    related: '相关',
    Unknown: '未知',
    unknown: '未知',
    Unnamed: '未命名'
  }
  return map[text] || text || fallback
}

export function formatTokenLabelZh(value, fallback = '') {
  return translateDisplayToken(value, fallback).replace(/[_-]+/g, ' ')
}

export function formatDistanceLabelZh(value) {
  if (value === null || value === undefined || value === '') return ''
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  if (Math.abs(number) >= 1000) return `${(number / 1000).toFixed(1)} km`
  return `${Math.round(number)} m`
}

export function formatLandUseLabelZh(value) {
  const text = String(value ?? '').trim()
  const map = {
    residential: '居住',
    commercial: '商业',
    industrial: '工业',
    agricultural: '农业',
    forest: '林地',
    wetland: '湿地',
    water: '水域',
    conservation: '保护区'
  }
  return map[text] || formatTokenLabelZh(text)
}
