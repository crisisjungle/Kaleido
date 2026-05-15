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
    reopen: '重开'
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
