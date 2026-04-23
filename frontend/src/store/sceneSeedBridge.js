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

function normalizeContext(value) {
  if (!value || typeof value !== 'object') return null
  const initialVariables = normalizeVariableList(value.initialVariables)
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
