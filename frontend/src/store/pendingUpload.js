/**
 * 临时存储待上传的文件和需求
 * 用于首页点击启动引擎后立即跳转，在Process页面再进行API调用
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  initialVariables: [],
  normalizedEventInputs: [],
  normalizedPolicyInputs: [],
  selectedPoints: [],
  mapSeedId: '',
  areaLabel: '',
  radiusMeters: 0,
  effortLevel: 'high',
  effortLocked: false,
  effortSnapshotId: '',
  effortSnapshot: null,
  sceneId: '',
  semanticArtifactRef: null,
  semanticRevision: 0,
  isPending: false
})

export function setPendingUpload(files, requirement, options = {}) {
  state.files = files
  state.simulationRequirement = requirement
  state.initialVariables = Array.isArray(options.initialVariables) ? options.initialVariables : []
  state.normalizedEventInputs = Array.isArray(options.normalizedEventInputs) ? options.normalizedEventInputs : []
  state.normalizedPolicyInputs = Array.isArray(options.normalizedPolicyInputs) ? options.normalizedPolicyInputs : []
  state.selectedPoints = Array.isArray(options.selectedPoints) ? options.selectedPoints : []
  state.mapSeedId = String(options.mapSeedId || '').trim()
  state.areaLabel = String(options.areaLabel || '').trim()
  state.radiusMeters = Number(options.radiusMeters || options.radius_m || 0)
  state.effortLevel = String(options.effortLevel || options.effort_level || 'high').trim()
  state.effortLocked = Boolean(options.effortLocked ?? options.effort_locked)
  state.effortSnapshotId = String(options.effortSnapshotId || options.effort_snapshot_id || '').trim()
  state.effortSnapshot = options.effortSnapshot && typeof options.effortSnapshot === 'object'
    ? JSON.parse(JSON.stringify(options.effortSnapshot))
    : null
  state.sceneId = String(options.sceneId || options.scene_id || '').trim()
  state.semanticArtifactRef = options.semanticArtifactRef && typeof options.semanticArtifactRef === 'object'
    ? JSON.parse(JSON.stringify(options.semanticArtifactRef))
    : null
  state.semanticRevision = Number(options.semanticRevision || options.semantic_revision || state.semanticArtifactRef?.revision || 0)
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    initialVariables: state.initialVariables,
    normalizedEventInputs: state.normalizedEventInputs,
    normalizedPolicyInputs: state.normalizedPolicyInputs,
    selectedPoints: state.selectedPoints,
    mapSeedId: state.mapSeedId,
    areaLabel: state.areaLabel,
    radiusMeters: state.radiusMeters,
    effortLevel: state.effortLevel,
    effortLocked: state.effortLocked,
    effortSnapshotId: state.effortSnapshotId,
    effortSnapshot: state.effortSnapshot ? JSON.parse(JSON.stringify(state.effortSnapshot)) : null,
    sceneId: state.sceneId,
    semanticArtifactRef: state.semanticArtifactRef ? JSON.parse(JSON.stringify(state.semanticArtifactRef)) : null,
    semanticRevision: state.semanticRevision,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.initialVariables = []
  state.normalizedEventInputs = []
  state.normalizedPolicyInputs = []
  state.selectedPoints = []
  state.mapSeedId = ''
  state.areaLabel = ''
  state.radiusMeters = 0
  state.effortLevel = 'high'
  state.effortLocked = false
  state.effortSnapshotId = ''
  state.effortSnapshot = null
  state.sceneId = ''
  state.semanticArtifactRef = null
  state.semanticRevision = 0
  state.isPending = false
}

export default state
