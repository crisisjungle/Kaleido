/**
 * 临时存储待上传的文件和需求
 * 用于首页点击启动引擎后立即跳转，在Process页面再进行API调用
 */
import { reactive } from 'vue'

const state = reactive({
  files: [],
  simulationRequirement: '',
  initialVariables: [],
  selectedPoints: [],
  mapSeedId: '',
  areaLabel: '',
  isPending: false
})

export function setPendingUpload(files, requirement, options = {}) {
  state.files = files
  state.simulationRequirement = requirement
  state.initialVariables = Array.isArray(options.initialVariables) ? options.initialVariables : []
  state.selectedPoints = Array.isArray(options.selectedPoints) ? options.selectedPoints : []
  state.mapSeedId = String(options.mapSeedId || '').trim()
  state.areaLabel = String(options.areaLabel || '').trim()
  state.isPending = true
}

export function getPendingUpload() {
  return {
    files: state.files,
    simulationRequirement: state.simulationRequirement,
    initialVariables: state.initialVariables,
    selectedPoints: state.selectedPoints,
    mapSeedId: state.mapSeedId,
    areaLabel: state.areaLabel,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.files = []
  state.simulationRequirement = ''
  state.initialVariables = []
  state.selectedPoints = []
  state.mapSeedId = ''
  state.areaLabel = ''
  state.isPending = false
}

export default state
