import { reactive } from 'vue'

const STORAGE_KEY = 'kaleido.workflow.navigation.v1'
const SCENE_SNAPSHOT_KEY = 'kaleido.sceneComposer.snapshot.v1'

const createDefaultSteps = () => [
  { step: 1, name: '背景生成', route: { name: 'SceneComposer', query: { restore: '1' } }, visited: false, status: 'todo', summary: '' },
  { step: 2, name: '场景设计', route: null, visited: false, status: 'todo', summary: '' },
  { step: 3, name: '开始模拟', route: null, visited: false, status: 'todo', summary: '' },
  { step: 4, name: '报告互动', route: null, visited: false, status: 'todo', summary: '' }
]

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
  state.steps[index] = {
    ...state.steps[index],
    ...updates,
    step: Number(step),
    visited: updates.visited ?? true,
    updatedAt: new Date().toISOString()
  }
  persist()
}

export function getWorkflowSteps() {
  return state.steps
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
