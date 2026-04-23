<template>
  <div class="space-forecast-page">
    <div class="scene-shell">
      <SpaceScene
        :key="sceneInstanceKey"
        :environment="sceneEnvironment"
        :events="visualEvents"
        :focus-shell-id="focusShellId"
        :collision-type="controls.collisionType"
        :running="isRunning"
      />
    </div>

    <div class="ui-layer">
      <header class="top-overlay">
        <KaleidoNavBrand class="brand-logo" to="/" tone="light" />
        
        <SpaceForecastStatus :snapshot="statusSnapshot" />
        
        <div v-if="forecastAlert" class="threshold-alert-center" :class="forecastAlert.type" @click="showResult = true">
          <svg class="warning-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
          <span class="alert-text">{{ forecastAlert.label }}</span>
        </div>
      </header>

      <main class="content-overlay">
        <SpaceForecastControl
          v-model="controls"
          v-model:collapsed="sidebarCollapsed"
          :years="availableYears"
          :collision-types="collisionTypeOptions"
          :shell-bands="shellBands"
          :disabled="isRunning"
          @start="startSimulation"
          @reset="resetSimulation"
        />

        <aside class="right-panels">
          <SpaceForecastCharts :points="chartPoints" v-model:collapsed="rightSidebarCollapsed" />
        </aside>
      </main>

      <footer class="bottom-left-floating">
        <SpaceForecastLegend />
      </footer>
      
      <SpaceForecastResult 
        v-if="showResult" 
        :summary="resultSummary" 
        @close="showResult = false"
        @reset="handleReset" 
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import SpaceForecastControl from '../features/space-forecast/components/SpaceForecastControl.vue'
import SpaceForecastLegend from '../features/space-forecast/components/SpaceForecastLegend.vue'
import SpaceForecastStatus from '../features/space-forecast/components/SpaceForecastStatus.vue'
import SpaceForecastCharts from '../features/space-forecast/components/SpaceForecastCharts.vue'
import SpaceForecastResult from '../features/space-forecast/components/SpaceForecastResult.vue'
import SpaceScene from '../features/space-forecast/three/SpaceScene.vue'
import {
  COLLISION_DESCRIPTIONS,
  COLLISION_LABELS,
  DEFAULT_SIMULATION_PACING,
  advanceSimulationByMonths,
  generateEnvironmentByStartTime,
  getAvailableEnvironmentYears,
  getEnvironmentMetrics,
  getEnvironmentTotals,
  injectInitialCollision,
  listCollisionTemplates
} from '../features/space-forecast/core'

const availableYears = getAvailableEnvironmentYears()
const defaultYear = availableYears.includes(2030) ? 2030 : availableYears[0]
const pacing = DEFAULT_SIMULATION_PACING
const FIRST_COLLISION_CINEMATIC_DELAY_MS = 5600

const controls = ref({
  startYear: defaultYear,
  collisionType: 'iridium_like',
  shellBand: '700-900 km'
})
const sidebarCollapsed = ref(true)
const rightSidebarCollapsed = ref(true)
const simulation = ref(null)
const sceneEnvironment = ref(generateEnvironmentByStartTime(defaultYear))
const visualEvents = ref([])
const sceneInstanceKey = ref(0)
const chartPoints = ref([])
const showResult = ref(false)
let simulationTimer = null
let simulationStartDelayTimer = null

const collisionTypeOptions = listCollisionTemplates().map((template) => ({
  value: template.id,
  label: COLLISION_LABELS[template.id] || template.label,
  description: COLLISION_DESCRIPTIONS[template.id] || template.description
}))

const shellBands = computed(() =>
  generateEnvironmentByStartTime(controls.value.startYear).shellStates.map((shell) => shell.label)
)

const currentEnvironment = computed(() => simulation.value?.environment || sceneEnvironment.value)
const currentMetrics = computed(() => getEnvironmentMetrics(currentEnvironment.value))
const currentTotals = computed(() => getEnvironmentTotals(currentEnvironment.value))
const isRunning = computed(() => simulation.value?.phase === 'running')

const forecastAlert = computed(() => {
  const state = simulation.value
  if (!state) return null

  if (state.threshold?.reached) {
    return {
      key: `threshold-${state.threshold.elapsedMonths ?? state.threshold.yearReached}`,
      type: 'threshold',
      label: '已达到凯斯勒阈值'
    }
  }

  if (state.phase === 'stopped' && state.stopReason === 'operational_collapse') {
    return {
      key: `collapse-${state.monthsElapsed}`,
      type: 'collapse',
      label: '已达到凯斯勒阈值'
    }
  }

  return null
})

watch(isRunning, (running) => {
  if (running) {
    sidebarCollapsed.value = true
  }
})

const focusShellId = computed(() => {
  return (
    simulation.value?.threshold?.triggerShellId ||
    simulation.value?.thresholdCandidate?.triggerShellId ||
    simulation.value?.initialShellId ||
    shellIdFromBand(controls.value.shellBand)
  )
})

const statusSnapshot = computed(() => {
  const metrics = currentMetrics.value
  const totals = currentTotals.value
  const totalDebris = totals.totalLargeDebris + totals.totalMediumDebris + totals.totalSmallDebris

  return {
    currentYear: formatYear(simulation.value?.currentYear || controls.value.startYear),
    activeSatellites: totals.totalSurvivingActiveSatellites ?? totals.totalActiveSatellites,
    derelictObjects: totals.totalDerelictObjects,
    totalDebris,
    globalCollisionRatePerYear: metrics.globalCollisionRatePerYear,
    kesslerRatio: metrics.maxKesslerRatio,
    riskiestShell: metrics.riskiestShell?.label || '未知',
    nextCollisionWait: formatWait(metrics.averageNextMajorCollisionWaitMonths)
  }
})

const resultSummary = computed(() => {
  if (!simulation.value || (simulation.value.phase !== 'stopped' && !showResult.value)) return null
  const finalTotals = getEnvironmentTotals(simulation.value.environment)
  const baselineTotals = getEnvironmentTotals(simulation.value.baselineEnvironment)
  const finalDebris = finalTotals.totalLargeDebris + finalTotals.totalMediumDebris + finalTotals.totalSmallDebris
  const baselineDebris =
    baselineTotals.totalLargeDebris + baselineTotals.totalMediumDebris + baselineTotals.totalSmallDebris
  const triggerShell = simulation.value.environment.shellStates.find(
    (shell) => shell.id === (simulation.value.threshold?.triggerShellId || simulation.value.thresholdCandidate?.triggerShellId)
  )
  const thresholdReached = simulation.value.threshold?.reached
  const expectedCollisionCount = simulation.value.expectedCollisionCount ?? simulation.value.collisionCount
  const thresholdMilestoneOnly = thresholdReached && simulation.value.phase !== 'stopped'

  return {
    reason: simulation.value.stopReason,
    reasonText: thresholdMilestoneOnly ? '已进入凯斯勒阈值，推演继续记录后续级联。' : reasonText(simulation.value.stopReason),
    elapsed: formatElapsed(simulation.value.monthsElapsed),
    collisionCount: simulation.value.collisionCount,
    expectedCollisionCount,
    thresholdReached,
    triggerShell: triggerShell?.label || '未触发',
    yearReached: formatYear(simulation.value.threshold?.yearReached || simulation.value.currentYear),
    debrisGrowth: `+${Math.max(0, finalDebris - baselineDebris).toLocaleString('zh-CN')}`,
    narrative:
      simulation.value.stopReason === 'hard_limit'
        ? '系统在 50 年内部上限内没有形成持续自我增殖。'
        : thresholdReached
          ? '阈值只是级联开始自我维持的节点，后续推演继续记录了轨道运营失效过程。'
          : '系统进入运营不可用状态，但未形成长期自维持阈值记录。'
  }
})

watch(
  () => controls.value.startYear,
  () => {
    if (!isRunning.value) resetSimulation()
  }
)

watch(
  () => simulation.value?.phase,
  (phase) => {
    if (phase === 'stopped') {
       // Optional: auto-show results or just let the label handle it
    }
  }
)

function shellIdFromBand(band) {
  return String(band || '').replace(/\s*km\s*$/i, '')
}

function stopTimer() {
  if (simulationStartDelayTimer) {
    window.clearTimeout(simulationStartDelayTimer)
    simulationStartDelayTimer = null
  }
  if (simulationTimer) {
    window.clearInterval(simulationTimer)
    simulationTimer = null
  }
}

function startSimulation() {
  stopTimer()
  showResult.value = false
  sceneInstanceKey.value += 1
  const baseEnvironment = generateEnvironmentByStartTime(controls.value.startYear)
  const targetShellId = shellIdFromBand(controls.value.shellBand)
  const initialState = injectInitialCollision(
    baseEnvironment,
    controls.value.collisionType,
    targetShellId,
    controls.value.startYear,
    pacing
  )

  simulation.value = initialState
  sceneEnvironment.value = initialState.environment
  visualEvents.value = [...initialState.pendingVisualEvents]
  chartPoints.value = [makeChartPoint(initialState.environment, 0, initialState.collisionCount, '首次碰撞后')]

  simulationStartDelayTimer = window.setTimeout(() => {
    simulationStartDelayTimer = null
    simulationTimer = window.setInterval(tickSimulation, pacing.visualTickMs)
  }, FIRST_COLLISION_CINEMATIC_DELAY_MS)
}

function tickSimulation() {
  if (!simulation.value || simulation.value.phase !== 'running') {
    stopTimer()
    return
  }

  const nextState = advanceSimulationByMonths(simulation.value, pacing.monthsPerTick, pacing)
  simulation.value = nextState
  sceneEnvironment.value = nextState.environment

  if (nextState.pendingVisualEvents.length) {
    visualEvents.value = [...visualEvents.value, ...nextState.pendingVisualEvents]
  }

  chartPoints.value = [
    ...chartPoints.value,
    makeChartPoint(
      nextState.environment,
      nextState.monthsElapsed,
      nextState.collisionCount,
      formatChartLabel(nextState.monthsElapsed)
    )
  ].slice(-80)

  if (nextState.phase === 'stopped') stopTimer()
}

function handleReset() {
  showResult.value = false
  resetSimulation()
}

function resetSimulation() {
  stopTimer()
  sceneInstanceKey.value += 1
  simulation.value = null
  visualEvents.value = []
  chartPoints.value = []
  showResult.value = false
  sceneEnvironment.value = generateEnvironmentByStartTime(controls.value.startYear)
}

function makeChartPoint(environment, monthsElapsed, collisionCount, label) {
  const metrics = getEnvironmentMetrics(environment)
  const totals = getEnvironmentTotals(environment)
  return {
    month: monthsElapsed,
    label,
    collisionRate: metrics.globalCollisionRatePerYear,
    collisionCount,
    survivingActiveSatellites: totals.totalSurvivingActiveSatellites,
    totalDebris: totals.totalLargeDebris + totals.totalMediumDebris + totals.totalSmallDebris
  }
}

function formatChartLabel(months) {
  if (months <= 0) return '起点'
  if (months < 12) return `${months} 月`
  return `${Math.round(months / 12)} 年`
}

function formatYear(year) {
  const value = Number(year || 0)
  return `${Math.round(value)}年`
}

function formatWait(months) {
  const value = Number(months || 0)
  if (!Number.isFinite(value) || value <= 0) return '正在重算'
  if (value < 1) return '少于 1 个月'
  if (value < 12) return `约 ${Math.round(value)} 个月`
  return `约 ${(value / 12).toFixed(1)} 年`
}

function formatElapsed(months) {
  const value = Number(months || 0)
  if (value < 12) return `${value} 个月`
  const years = Math.floor(value / 12)
  const rest = value % 12
  return rest ? `${years} 年 ${rest} 个月` : `${years} 年`
}

function reasonText(reason) {
  return {
    operational_collapse: '级联碰撞已使关键轨道壳层进入运营不可用状态。',
    self_sustaining: '碎片净增长已经进入持续自我增殖。',
    hard_limit: '内部硬上限到达，未触发工程阈值。'
  }[reason] || '推演已停止。'
}

onBeforeUnmount(() => {
  stopTimer()
})
</script>

<style scoped>
.space-forecast-page {
  width: 100vw;
  height: 100vh;
  background: radial-gradient(circle at 20% 50%, #050810 0%, #02040a 100%);
  color: #fff;
  overflow: hidden;
  position: relative;
}

.scene-shell {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.ui-layer {
  position: relative;
  z-index: 10;
  width: 100%;
  height: 100%;
  pointer-events: none;
  display: flex;
  flex-direction: column;
}

.ui-layer > * {
  pointer-events: auto;
}

.top-overlay {
  min-height: 60px;
  padding: 0 24px;
}

.brand-logo {
  position: absolute;
  left: 24px;
  top: 18px;
  z-index: 200;
}

.content-overlay {
  flex: 1;
  display: flex;
  justify-content: flex-end;
  padding: 24px;
  padding-left: 0;
  pointer-events: none;
  position: relative;
}

.right-panels {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  pointer-events: none;
}

.bottom-left-floating {
  position: fixed;
  left: 40px;
  bottom: 40px;
  pointer-events: auto;
  z-index: 50;
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s;
}

.space-forecast-page:has(.is-collapsed) .bottom-left-floating {
  /* Legend can move or just stay */
}


.threshold-alert-center {
  position: fixed;
  background: rgba(220, 38, 38, 0.95);
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  cursor: pointer;
  box-shadow: 0 0 40px rgba(220, 38, 38, 0.6);
  z-index: 1000;
  border: 1px solid rgba(255, 255, 255, 0.2);
  
  /* Target (Resting) State */
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 24px;
  border-radius: 6px;
  gap: 12px;
  
  animation: center-flash-to-top-right 3s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.threshold-alert-center .warning-icon {
  width: 22px;
  height: 22px;
  color: #fff;
}

.threshold-alert-center .alert-text {
  font-size: 15px;
  font-weight: 900;
  color: #fff;
}

@keyframes center-flash-to-top-right {
  0% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 0; }
  10% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 1; }
  20% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 0.2; }
  30% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 1; }
  40% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 0.2; }
  50% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 1; }
  80% { top: 50%; left: 50%; transform: translate(-50%, -50%) scale(2.5); opacity: 1; }
  100% { top: 24px; left: calc(100% - 220px); transform: scale(0.9); opacity: 1; }
}

.bottom-overlay {
  margin-top: auto;
}

/* Ensure components have dark/glass style */
:deep(.control-panel), :deep(.chart-panel) {
  background: rgba(15, 23, 42, 0.6) !important;
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  color: #fff !important;
}

:deep(.control-panel h2), :deep(.chart-panel h2) {
  color: #94a3b8 !important;
}

:deep(input), :deep(select) {
  background: rgba(0, 0, 0, 0.3) !important;
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
  color: #fff !important;
}
</style>
