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
      ...safeClone(item),
      input_id: String(item.input_id || item.variable_id || item.id || '').trim(),
      variable_id: String(item.variable_id || item.input_id || item.id || '').trim(),
      type: String(item.type || item.input_type || item.kind || 'custom').trim(),
      name: String(item.name || item.title || '').trim(),
      description: String(item.description || item.intent || '').trim(),
      direction: item.direction ?? null,
      intensity: item.intensity ?? item.intensity_0_100 ?? null,
      intensity_0_100: item.intensity_0_100 ?? (typeof item.intensity === 'number' ? item.intensity : null),
      expected_effects: Array.isArray(item.expected_effects) ? [...item.expected_effects] : [],
      target_region_ids: Array.isArray(item.target_region_ids)
        ? [...item.target_region_ids]
        : Array.isArray(item.target_regions) ? [...item.target_regions] : [],
      target_entity_ids: Array.isArray(item.target_entity_ids)
        ? [...item.target_entity_ids]
        : Array.isArray(item.target_nodes) ? [...item.target_nodes] : [],
      atomic_keys: Array.isArray(item.atomic_keys) ? [...item.atomic_keys] : [],
      action_primitives: Array.isArray(item.action_primitives) ? [...item.action_primitives] : [],
      executor_capability_keys: Array.isArray(item.executor_capability_keys) ? [...item.executor_capability_keys] : [],
      source_origin: String(item.source_origin || 'user_input').trim()
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
  const normalizedEventInputs = normalizeVariableList(
    value.suggestedEventInputs
    || value.suggested_event_inputs
    || value.normalizedEventInputs
    || value.normalized_event_inputs
  ).map((item) => ({
    ...item,
    source_origin: 'step1_suggestion',
    authority: 'draft'
  }))
  const normalizedPolicyInputs = normalizeVariableList(
    value.suggestedPolicyInputs
    || value.suggested_policy_inputs
    || value.normalizedPolicyInputs
    || value.normalized_policy_inputs
  ).map((item) => ({
    ...item,
    source_origin: 'step1_suggestion',
    authority: 'draft'
  }))
  const selectedPoints = normalizePointList(
    value.selectedPoints || value.selected_points || value.locations
  )
  const mapSeedId = String(value.mapSeedId || value.map_seed_id || '').trim()
  const areaLabel = String(value.areaLabel || value.area_label || value.location || '').trim()
  const radiusMeters = Number(value.radiusMeters || value.radius_m || 0)
  const rawEffortSnapshot = value.effortSnapshot || value.effort_snapshot
  const effortSnapshot = rawEffortSnapshot && typeof rawEffortSnapshot === 'object'
    ? safeClone(rawEffortSnapshot)
    : null
  const effortSnapshotId = String(
    value.effortSnapshotId
    || value.effort_snapshot_id
    || effortSnapshot?.effort_snapshot_id
    || effortSnapshot?.snapshot_id
    || ''
  ).trim()
  const effortLevel = String(
    value.effortLevel
    || value.effort_level
    || effortSnapshot?.effort_level
    || effortSnapshot?.level
    || 'high'
  ).trim()
  const effortLocked = Boolean(
    value.effortLocked
    ?? value.effort_locked
    ?? effortSnapshot?.locked
    ?? effortSnapshotId
  )
  const sceneId = String(value.sceneId || value.scene_id || '').trim()
  const rawSemanticRef = value.semanticArtifactRef || value.semantic_artifact_ref
  const semanticArtifactRef = rawSemanticRef && typeof rawSemanticRef === 'object'
    ? safeClone(rawSemanticRef)
    : null
  const semanticRevision = Number(
    value.semanticRevision
    || value.semantic_revision
    || semanticArtifactRef?.revision
    || 0
  )
  const rawFoundationRef = value.foundationRef || value.foundation_ref
  const foundationRef = rawFoundationRef && typeof rawFoundationRef === 'object'
    ? safeClone(rawFoundationRef)
    : (mapSeedId ? { map_seed_id: mapSeedId } : null)
  if (
    initialVariables.length === 0
    && normalizedEventInputs.length === 0
    && normalizedPolicyInputs.length === 0
    && selectedPoints.length === 0
    && !mapSeedId
    && !areaLabel
    && !effortSnapshotId
    && !semanticArtifactRef
  ) return null
  return {
    initialVariables,
    normalizedEventInputs,
    normalizedPolicyInputs,
    selectedPoints,
    mapSeedId,
    areaLabel,
    radiusMeters: Number.isFinite(radiusMeters) ? radiusMeters : 0,
    effortLevel,
    effortLocked,
    effortSnapshotId,
    effortSnapshot,
    sceneId,
    semanticArtifactRef,
    semanticRevision: Number.isFinite(semanticRevision) ? semanticRevision : 0,
    foundationRef
  }
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

export function mergeProjectSceneSeedContext(project, recoveryContext = null) {
  if (!project || typeof project !== 'object') return normalizeContext(recoveryContext)

  const context = normalizeContext(recoveryContext) || {}
  const semanticInput = project.semantic_input && typeof project.semantic_input === 'object'
    ? project.semantic_input
    : null
  const mapSeedId = String(project.map_seed_id || context.mapSeedId || '').trim()
  const foundationRef = {
    ...(context.foundationRef || {}),
    ...(mapSeedId ? { map_seed_id: mapSeedId } : {})
  }

  return normalizeContext({
    ...context,
    initialVariables: semanticInput ? [] : (context.initialVariables || []),
    normalizedEventInputs: semanticInput
      ? semanticInput.events || []
      : context.normalizedEventInputs || [],
    normalizedPolicyInputs: semanticInput
      ? semanticInput.policies || []
      : context.normalizedPolicyInputs || [],
    mapSeedId,
    areaLabel: semanticInput?.scene?.location || context.areaLabel || project.name || '',
    semanticArtifactRef: project.semantic_artifact_ref || context.semanticArtifactRef || null,
    semanticRevision: Number(semanticInput?.revision || context.semanticRevision || 0),
    effortSnapshot: project.effort_snapshot || context.effortSnapshot || null,
    effortSnapshotId: project.effort_snapshot?.effort_snapshot_id || context.effortSnapshotId || '',
    effortLevel: project.effort_snapshot?.effort_level || context.effortLevel || 'high',
    effortLocked: Boolean(project.effort_snapshot || context.effortLocked),
    sceneId: project.scene_id || context.sceneId || '',
    foundationRef
  })
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
