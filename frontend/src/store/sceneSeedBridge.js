const STORAGE_KEY = 'envfish.scene-seed-bridge.v1'

const EMPTY_STATE = {
  pending: null,
  byProject: {},
  bySimulation: {}
}

function safeClone(value) {
  return JSON.parse(JSON.stringify(value))
}

function normalizeVariableList(value) {
  if (!Array.isArray(value)) return []
  return value
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      name: String(item.name || item.title || '').trim(),
      description: String(item.description || '').trim()
    }))
    .filter((item) => item.name || item.description)
}

function normalizePoint(value, fallbackName = '') {
  if (!value || typeof value !== 'object') return null
  const lat = Number(value.lat ?? value.latitude)
  const lon = Number(value.lon ?? value.lng ?? value.longitude)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return {
    name: String(value.name || value.label || fallbackName || '地图主锚点').trim(),
    role: String(value.role || 'primary_anchor').trim(),
    lat,
    lon,
    source: String(value.source || 'user_map').trim()
  }
}

function normalizePointList(value) {
  if (!Array.isArray(value)) return []
  return value
    .map((item, index) => normalizePoint(item, index === 0 ? '地图主锚点' : `地图锚点 ${index + 1}`))
    .filter(Boolean)
}

function isBaselineContextVariable(item) {
  const text = [
    item?.name,
    item?.title,
    item?.description,
    item?.summary,
    item?.type,
    item?.category
  ].filter(Boolean).join(' ').toLowerCase()
  if (!text) return false
  const baselineTerms = ['基线', '稳态', '常态', '当前', '现状', '观测', '环境背景', 'weather_baseline', 'baseline']
  const weatherTerms = ['温度', '气温', '湿度', '降水', '降雨', '风速', '风向', '天气', 'temperature', 'humidity', 'precipitation', 'wind', 'weather']
  return baselineTerms.some((term) => text.includes(term)) && weatherTerms.some((term) => text.includes(term))
}

function normalizeContext(value) {
  if (!value || typeof value !== 'object') return null
  const initialVariables = normalizeVariableList(value.initialVariables)
    .filter((item) => !isBaselineContextVariable(item))
  const selectedPoints = normalizePointList(
    value.selectedPoints || value.selected_points || value.locations
  )
  const mapSeedId = String(value.mapSeedId || value.map_seed_id || '').trim()
  const areaLabel = String(value.areaLabel || value.area_label || value.location || '').trim()
  if (initialVariables.length === 0 && selectedPoints.length === 0 && !mapSeedId && !areaLabel) return null
  return { initialVariables, selectedPoints, mapSeedId, areaLabel }
}

function readState() {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return safeClone(EMPTY_STATE)
    const parsed = JSON.parse(raw)
    return {
      pending: normalizeContext(parsed.pending),
      byProject: parsed.byProject && typeof parsed.byProject === 'object' ? parsed.byProject : {},
      bySimulation: parsed.bySimulation && typeof parsed.bySimulation === 'object' ? parsed.bySimulation : {}
    }
  } catch {
    return safeClone(EMPTY_STATE)
  }
}

function writeState(state) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function stashPendingSceneSeedContext(context) {
  const normalized = normalizeContext(context)
  if (!normalized) return
  const state = readState()
  state.pending = normalized
  writeState(state)
}

export function consumePendingSceneSeedContext() {
  const state = readState()
  const context = normalizeContext(state.pending)
  state.pending = null
  writeState(state)
  return context
}

export function attachSceneSeedContextToProject(projectId, context) {
  const normalized = normalizeContext(context)
  if (!projectId || !normalized) return
  const state = readState()
  state.byProject[String(projectId)] = normalized
  writeState(state)
}

export function getSceneSeedContextByProject(projectId) {
  if (!projectId) return null
  const state = readState()
  return normalizeContext(state.byProject[String(projectId)])
}

export function attachSceneSeedContextToSimulation(simulationId, context) {
  const normalized = normalizeContext(context)
  if (!simulationId || !normalized) return
  const state = readState()
  state.bySimulation[String(simulationId)] = normalized
  writeState(state)
}

export function getSceneSeedContextBySimulation(simulationId) {
  if (!simulationId) return null
  const state = readState()
  return normalizeContext(state.bySimulation[String(simulationId)])
}
