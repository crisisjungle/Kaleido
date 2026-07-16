import { reactive } from 'vue'

const STORAGE_KEY = 'kaleido.workflow.navigation.v1'
const SCENE_SNAPSHOT_KEY = 'kaleido.sceneComposer.snapshot.v1'
const STATUS_PRIORITY = {
  todo: 0,
  active: 1,
  done: 2
}

const createDefaultSteps = () => [
  { step: 1, name: '背景定义', route: null, visited: false, status: 'todo', summary: '' },
  { step: 2, name: '场景生成', route: null, visited: false, status: 'todo', summary: '' },
  { step: 3, name: '推演运行', route: null, visited: false, status: 'todo', summary: '' },
  { step: 4, name: '分析与报告', route: null, visited: false, status: 'todo', summary: '' }
]

function cleanQuery(query = {}) {
  return Object.entries(query || {}).reduce((next, [key, value]) => {
    if (value === undefined || value === null || value === '') return next
    next[key] = value
    return next
  }, {})
}

function cleanId(value) {
  if (Array.isArray(value)) return cleanId(value[0])
  return String(value || '').trim()
}

function safeParse(value, fallback) {
  try {
    return value ? JSON.parse(value) : fallback
  } catch {
    return fallback
  }
}

function loadState() {
  const defaultSteps = createDefaultSteps()
  if (typeof window === 'undefined') return { steps: defaultSteps }
  const saved = safeParse(window.sessionStorage.getItem(STORAGE_KEY), null)
  if (!saved?.steps) return { steps: defaultSteps }
  const savedByStep = new Map(saved.steps.map((item) => [Number(item.step), item]))
  return {
    steps: defaultSteps.map((item) => ({
      ...item,
      ...(savedByStep.get(item.step) || {}),
      name: item.name,
      route: savedByStep.get(item.step)?.route ?? item.route
    }))
  }
}

const state = reactive(loadState())

function persist() {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ steps: state.steps }))
}

export function markWorkflowStep(step, updates = {}) {
  const index = state.steps.findIndex((item) => item.step === Number(step))
  if (index === -1) return
  const current = state.steps[index]
  const nextUpdates = { ...updates }
  const requestedStatus = nextUpdates.status
  const currentPriority = STATUS_PRIORITY[current.status] ?? 0
  const requestedPriority = STATUS_PRIORITY[requestedStatus] ?? currentPriority

  if (requestedStatus && requestedPriority < currentPriority && !nextUpdates.forceStatus) {
    nextUpdates.status = current.status
    if (current.summary && nextUpdates.summary) {
      nextUpdates.summary = current.summary
    }
  }
  delete nextUpdates.forceStatus

  state.steps[index] = {
    ...current,
    ...nextUpdates,
    step: Number(step),
    visited: nextUpdates.visited ?? true,
    updatedAt: new Date().toISOString()
  }
  persist()
}

export function getWorkflowSteps() {
  return state.steps
}

export function hasWorkflowRoute(item) {
  return Boolean(item?.route?.name)
}

export function hydrateWorkflowFromSimulation({
  simulationId = '',
  projectId = '',
  reportId = '',
  query = {},
  step3Status = '',
  step3Summary = '',
  step4Status = 'done',
  step4Summary = '分析与报告'
} = {}) {
  const safeSimulationId = cleanId(simulationId)
  const safeProjectId = cleanId(projectId)
  const safeReportId = cleanId(reportId)
  const baseQuery = cleanQuery(query)
  const reportQuery = safeReportId
    ? { ...baseQuery, report_id: safeReportId }
    : baseQuery
  const resolvedStep3Status = step3Status || (safeReportId ? 'done' : 'active')
  const resolvedStep3Summary = step3Summary || (safeReportId ? '推演结果' : '推演播放中')

  if (safeSimulationId || safeProjectId) {
    markWorkflowStep(2, {
      visited: true,
      status: 'done',
      summary: '场景配置',
      route: safeSimulationId
        ? { name: 'Simulation', params: { simulationId: safeSimulationId }, query: baseQuery }
        : { name: 'Process', params: { projectId: safeProjectId }, query: baseQuery }
    })
  }

  if (safeSimulationId) {
    markWorkflowStep(3, {
      visited: true,
      status: resolvedStep3Status,
      summary: resolvedStep3Summary,
      route: { name: 'SimulationRun', params: { simulationId: safeSimulationId }, query: reportQuery }
    })
  }

  if (safeReportId) {
    markWorkflowStep(4, {
      visited: true,
      status: step4Status,
      summary: step4Summary,
      route: { name: 'Analysis', params: { reportId: safeReportId }, query: baseQuery }
    })
  }
}

export function hydrateWorkflowFromGoldenCase({ stepRoutes = {}, currentStep = 1 } = {}) {
  const routeByStep = {
    1: stepRoutes.foundation,
    2: stepRoutes.scenario,
    3: stepRoutes.runtime,
    4: stepRoutes.analysis
  }
  const summaries = {
    1: '研究范围与事实边界',
    2: '故事线、主体与机制',
    3: '36轮城市系统演化',
    4: '转折、风险与政策观察'
  }
  for (const step of [1, 2, 3, 4]) {
    const targetRoute = routeByStep[step]
    if (!targetRoute?.name) continue
    markWorkflowStep(step, {
      visited: true,
      status: step === Number(currentStep) ? 'active' : 'done',
      forceStatus: true,
      summary: summaries[step],
      route: {
        ...targetRoute,
        params: { ...(targetRoute.params || {}) },
        query: cleanQuery(targetRoute.query || {})
      }
    })
  }
}

export function saveSceneComposerSnapshot(snapshot) {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(SCENE_SNAPSHOT_KEY, JSON.stringify(snapshot || {}))
  const hasReport = Boolean(String(snapshot?.reportMarkdown || '').trim())
  markWorkflowStep(1, {
    visited: true,
    status: hasReport ? 'done' : 'active',
    summary: hasReport ? '已生成背景报告' : '已填写背景参数',
    route: { name: 'SceneComposer', query: { restore: '1' } }
  })
}

export function getSceneComposerSnapshot() {
  if (typeof window === 'undefined') return null
  return safeParse(window.sessionStorage.getItem(SCENE_SNAPSHOT_KEY), null)
}

export function clearSceneComposerSnapshot() {
  if (typeof window === 'undefined') return
  window.sessionStorage.removeItem(SCENE_SNAPSHOT_KEY)
}

export function resetWorkflowNavigation() {
  state.steps = createDefaultSteps()
  persist()
}

export default state
