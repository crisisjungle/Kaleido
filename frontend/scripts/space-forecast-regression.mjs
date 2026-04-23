import assert from 'node:assert/strict'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { createServer } from 'vite'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(scriptDir, '..')

function snapshot(core, state) {
  const metrics = core.getEnvironmentMetrics(state.environment)
  const totals = core.getEnvironmentTotals(state.environment)
  const totalDebris = totals.totalLargeDebris + totals.totalMediumDebris + totals.totalSmallDebris
  return {
    month: state.monthsElapsed,
    phase: state.phase,
    stopReason: state.stopReason,
    expectedCollisionCount: state.expectedCollisionCount,
    collisionCount: state.collisionCount,
    activeSatellites: totals.totalActiveSatellites,
    survivingActiveSatellites: totals.totalSurvivingActiveSatellites,
    totalDebris,
    globalCollisionRatePerYear: metrics.globalCollisionRatePerYear,
    kesslerRatio: metrics.maxKesslerRatio,
    threshold: state.threshold ? { ...state.threshold } : null
  }
}

function runScenario(core, { startYear, collisionType, shellId, months }) {
  let state = core.injectInitialCollision(
    core.generateEnvironmentByStartTime(startYear),
    collisionType,
    shellId,
    startYear,
    core.DEFAULT_SIMULATION_PACING
  )
  const history = [snapshot(core, state)]

  while (state.phase === 'running' && state.monthsElapsed < months) {
    state = core.advanceSimulationByMonths(state, 1, core.DEFAULT_SIMULATION_PACING)
    history.push(snapshot(core, state))
  }

  return {
    state,
    history,
    final: history[history.length - 1],
    at(month) {
      return history.find((entry) => entry.month === month)
    },
    thresholdEntry() {
      return history.find((entry) => entry.threshold?.reached)
    }
  }
}

function runOneYearStep(core, { startYear, collisionType, shellId }) {
  return core.advanceSimulationByMonths(
    core.injectInitialCollision(
      core.generateEnvironmentByStartTime(startYear),
      collisionType,
      shellId,
      startYear,
      core.DEFAULT_SIMULATION_PACING
    ),
    12,
    core.DEFAULT_SIMULATION_PACING
  )
}

function runTwelveMonthlySteps(core, { startYear, collisionType, shellId }) {
  let state = core.injectInitialCollision(
    core.generateEnvironmentByStartTime(startYear),
    collisionType,
    shellId,
    startYear,
    core.DEFAULT_SIMULATION_PACING
  )
  const pendingVisualEvents = []
  for (let month = 0; month < 12; month += 1) {
    state = core.advanceSimulationByMonths(state, 1, core.DEFAULT_SIMULATION_PACING)
    pendingVisualEvents.push(...state.pendingVisualEvents)
  }
  return { ...state, pendingVisualEvents }
}

function assertAccelerating(series, key, firstMonth, secondMonth, thirdMonth) {
  const first = series.at(firstMonth)
  const second = series.at(secondMonth)
  const third = series.at(thirdMonth)
  assert(first && second && third, `missing ${key} checkpoints`)
  const earlyGain = second[key] - first[key]
  const laterGain = third[key] - second[key]
  assert(laterGain > earlyGain, `${key} should accelerate between ${firstMonth}-${thirdMonth} months`)
}

const server = await createServer({
  root: frontendRoot,
  logLevel: 'error',
  server: { middlewareMode: true }
})

try {
  const core = await server.ssrLoadModule('/src/features/space-forecast/core/index.js')
  const baseline2030 = core.getEnvironmentMetrics(core.generateEnvironmentByStartTime(2030))
  assert(
    baseline2030.globalCollisionRatePerYear < 1,
    '2030 baseline should represent major collision rate, not routine avoidance alerts'
  )

  const yearlyStep = runOneYearStep(core, {
    startYear: 2040,
    collisionType: 'asat_like',
    shellId: '900-1200'
  })
  const monthlySteps = runTwelveMonthlySteps(core, {
    startYear: 2040,
    collisionType: 'asat_like',
    shellId: '900-1200'
  })
  assert.equal(yearlyStep.monthsElapsed, monthlySteps.monthsElapsed, 'one-year visual step should still advance 12 monthly logic steps')
  assert.equal(yearlyStep.collisionCount, monthlySteps.collisionCount, 'one-year visual step should match monthly collision count')
  assert.equal(
    yearlyStep.pendingVisualEvents.length,
    monthlySteps.pendingVisualEvents.length,
    'one-year visual step should retain visual events from every internal month'
  )

  const highRisk = runScenario(core, {
    startYear: 2030,
    collisionType: 'asat_like',
    shellId: '700-900',
    months: 360
  })
  assert(!highRisk.at(24).threshold, '2030 ASAT 700-900 should not mark Kessler threshold after only two years')
  assert(!highRisk.at(120).threshold, '2030 ASAT 700-900 should not mark Kessler threshold within ten years')
  assert(
    highRisk.at(24).globalCollisionRatePerYear < 5,
    'two-year 2030 ASAT case should not explode to hundreds of major collisions per year'
  )
  assert(highRisk.final.expectedCollisionCount > 50, 'high-risk cascade should still accumulate collisions over decades')
  assert(
    highRisk.final.survivingActiveSatellites < highRisk.at(0).survivingActiveSatellites,
    'surviving original active satellites should decline even when new launches increase net active satellites'
  )
  assertAccelerating(highRisk, 'expectedCollisionCount', 0, 120, 240)

  const lowOrbitSmall = runScenario(core, {
    startYear: 2030,
    collisionType: 'small',
    shellId: '300-500',
    months: 120
  })
  assert(!lowOrbitSmall.final.threshold, 'low-orbit small collision should not enter Kessler threshold within ten years')
  assert.equal(lowOrbitSmall.final.phase, 'running')
  assert(lowOrbitSmall.final.totalDebris < lowOrbitSmall.at(0).totalDebris, 'low orbit debris should be decay dominated')

  const severeHighOrbit = runScenario(core, {
    startYear: 2040,
    collisionType: 'asat_like',
    shellId: '900-1200',
    months: 600
  })
  assert(!severeHighOrbit.at(60).threshold, '2040 ASAT 900-1200 should not mark Kessler threshold within five years')
  assert(severeHighOrbit.final.expectedCollisionCount > 500, 'severe high-orbit case should cascade into high long-term collision pressure')
  assert.equal(severeHighOrbit.final.stopReason, 'operational_collapse')
  assert.equal(
    severeHighOrbit.final.survivingActiveSatellites,
    0,
    'severe high-orbit case should stop only after affected active satellites reach zero'
  )

  console.log('Space Forecast cascade regression checks passed.')
} finally {
  await server.close()
}
