import { clamp, round } from './math'
import { getEnvironmentTotals, getRiskiestShell } from './metrics'
import { getCollisionTemplate } from './collisions'
import { checkKesslerThreshold } from './threshold'
import { DEFAULT_SIMULATION_PACING } from './types'
import {
  computeCascadeSeverity,
  computeAutonomousAvoidance,
  computeKesslerProgressGain,
  computeKesslerRatio,
  computePressureRatio,
  computeShellCollisionRate,
  getFollowOnDebrisYield,
  getAltitudeRetention,
  getAtmosphericDecayBoost
} from './cascadeModel'

function cloneState(state) {
  return {
    ...state,
    events: state.events.map((event) => ({
      ...event,
      debrisDelta: event.debrisDelta ? { ...event.debrisDelta } : undefined
    })),
    environment: {
      ...state.environment,
      shellStates: state.environment.shellStates.map((shell) => ({ ...shell }))
    },
    baselineEnvironment: {
      ...state.baselineEnvironment,
      shellStates: state.baselineEnvironment.shellStates.map((shell) => ({ ...shell }))
    },
    thresholdCandidate: state.thresholdCandidate ? { ...state.thresholdCandidate } : null,
    threshold: state.threshold ? { ...state.threshold } : null,
    pendingVisualEvents: []
  }
}

function createThresholdEvent(state, threshold) {
  const shell =
    state.environment.shellStates.find((entry) => entry.id === threshold.triggerShellId) ??
    getRiskiestShell(state.environment) ??
    state.environment.shellStates[0]

  return {
    id: `threshold-${state.monthsElapsed}-${state.collisionCount}`,
    type: 'threshold_reached',
    shellId: shell?.id ?? state.initialShellId,
    year: state.currentYear,
    monthIndex: state.currentMonthIndex,
    elapsedMonths: state.monthsElapsed,
    title: '进入凯斯勒阈值',
    collisionRatePerYear: shell?.collisionRatePerYear ?? 0,
    kesslerRatio: threshold.kesslerRatio ?? shell?.kesslerRatio ?? 0,
    debrisDelta: { large: 0, medium: 0, small: 0 }
  }
}

function createCascadeEvent(state, shell, eventCount, expectedCollisions, debrisDelta) {
  return {
    id: `cascade-${state.monthsElapsed}-${shell.id}-${state.collisionCount + eventCount}`,
    type: 'cascade_collision',
    shellId: shell.id,
    year: state.currentYear,
    monthIndex: state.currentMonthIndex,
    elapsedMonths: state.monthsElapsed,
    title: eventCount > 1 ? `${eventCount} 次级联碰撞` : '后续级联碰撞',
    collisionTypeId: state.collisionType,
    eventCount,
    expectedCollisions: round(expectedCollisions, 3),
    collisionRatePerYear: shell.collisionRatePerYear ?? 0,
    debrisDelta
  }
}

function createHardLimitEvent(state) {
  const riskiestShell = getRiskiestShell(state.environment) ?? state.environment.shellStates[0]
  return {
    id: `hard_limit-${state.monthsElapsed}-${state.collisionCount}`,
    type: 'hard_limit',
    shellId: riskiestShell?.id ?? state.initialShellId,
    year: state.currentYear,
    monthIndex: state.currentMonthIndex,
    elapsedMonths: state.monthsElapsed,
    title: 'Simulation reached hard limit',
    collisionRatePerYear: riskiestShell?.collisionRatePerYear ?? 0,
    debrisDelta: { large: 0, medium: 0, small: 0 }
  }
}

function createOperationalCollapseEvent(state, shell, reason) {
  return {
    id: `operational_collapse-${state.monthsElapsed}-${state.collisionCount}`,
    type: 'operational_collapse',
    shellId: shell?.id ?? state.initialShellId,
    year: state.currentYear,
    monthIndex: state.currentMonthIndex,
    elapsedMonths: state.monthsElapsed,
    title: '轨道运营不可用',
    collapseReason: reason,
    collisionRatePerYear: shell?.collisionRatePerYear ?? 0,
    debrisDelta: { large: 0, medium: 0, small: 0 }
  }
}

function findBaselineShell(state, shell) {
  return state.baselineEnvironment.shellStates.find((entry) => entry.id === shell.id) ?? shell
}

function getShellDecay(shell) {
  const decay = Math.max(0, shell.naturalDecayRate || 0) * getAtmosphericDecayBoost(shell)
  return {
    large: decay * 0.018 / 12,
    medium: decay * 0.045 / 12,
    small: decay * 0.09 / 12
  }
}

function advanceShell(shell, baselineShell, template, thresholdReached) {
  const collisionRatePerYear = computeShellCollisionRate(shell, baselineShell)
  const ratedShell = { ...shell, collisionRatePerYear }
  const expectedCollisions = collisionRatePerYear / 12
  const pressureRatio = computePressureRatio(ratedShell, baselineShell)
  const severity = computeCascadeSeverity(ratedShell, baselineShell)
  const avoidance = computeAutonomousAvoidance(ratedShell)
  const retention = getAltitudeRetention(ratedShell)
  const decay = getShellDecay(ratedShell)
  const disposal = Math.max(0, ratedShell.disposalRate || 0)
  const exposureDecay = clamp(
    1 - ((ratedShell.naturalDecayRate || 0) * getAtmosphericDecayBoost(ratedShell) * 0.12 + disposal * 0.035),
    0.82,
    0.998
  )
  const cascadeExposure = clamp((ratedShell.cascadeExposure || 0) * exposureDecay, 0, 3)
  const productionScale = expectedCollisions * severity * retention * cascadeExposure
  const followOnYield = getFollowOnDebrisYield(template)
  const launchSuppression = thresholdReached ? 0.02 : pressureRatio >= 8 ? 0.45 : 1

  const produced = {
    large: followOnYield.large * productionScale,
    medium: followOnYield.medium * productionScale,
    small: followOnYield.small * productionScale
  }
  const removed = {
    large: ratedShell.largeDebris * (decay.large + disposal * 0.004 / 12),
    medium: ratedShell.mediumDebris * decay.medium,
    small: ratedShell.smallDebris * decay.small
  }

  const collisionLoss = expectedCollisions * (0.8 + severity * 0.22) * avoidance.lossMultiplier
  const pressureAttrition =
    ratedShell.activeSatellites *
    Math.max(0, pressureRatio - 1) *
    (1 - ratedShell.avoidanceEffectiveness) *
    0.00026 *
    avoidance.lossMultiplier
  const postThresholdAttritionRate = thresholdReached
    ? clamp(
        0.075 +
          Math.log1p(Math.max(0, ratedShell.kesslerRatio || 0)) * 0.026 +
          Math.max(0, pressureRatio - 1) * 0.016,
        0.08,
        0.32
      )
    : 0
  const postThresholdAttrition =
    ratedShell.activeSatellites *
    postThresholdAttritionRate *
    clamp(getAltitudeRetention(ratedShell), 0.65, 1.15) *
    avoidance.lossMultiplier
  const activeLoss = collisionLoss + pressureAttrition + postThresholdAttrition
  const derelictFailures =
    ratedShell.activeSatellites *
    Math.max(0, pressureRatio - 1) *
    (1 - ratedShell.avoidanceEffectiveness) *
    0.0002 *
    avoidance.lossMultiplier
  const disposedDerelicts = ratedShell.derelictObjects * disposal * 0.055 / 12
  const activeLossPool = (ratedShell.activeLossDebt || 0) + activeLoss
  const realizedActiveLoss = Math.floor(activeLossPool)
  const activeLossDebt = round(activeLossPool - realizedActiveLoss, 3)

  const activeSatellites = Math.max(
    0,
    Math.round(
      ratedShell.activeSatellites +
        (ratedShell.launchIntensity * launchSuppression) / 12
    ) - realizedActiveLoss
  )
  const survivingActiveSatellites = Math.max(
    0,
    Math.round(ratedShell.survivingActiveSatellites ?? ratedShell.activeSatellites) - realizedActiveLoss
  )
  const convertedDerelicts = Math.max(0, Math.round(realizedActiveLoss * (thresholdReached ? 0.22 : 0.4)))
  const convertedLargeDebris = Math.max(0, Math.round(realizedActiveLoss * (thresholdReached ? 4.5 : 1.2)))
  const convertedMediumDebris = Math.max(0, Math.round(realizedActiveLoss * (thresholdReached ? 64 : 12)))
  const convertedSmallDebris = Math.max(0, Math.round(realizedActiveLoss * (thresholdReached ? 1400 : 180)))

  const derelictObjects = Math.max(
    0,
    Math.round(
      ratedShell.derelictObjects +
        derelictFailures +
        expectedCollisions * (1.15 + severity * 0.35) -
        disposedDerelicts +
        convertedDerelicts
    )
  )
  const largeDebris = Math.max(0, Math.round(ratedShell.largeDebris + produced.large + convertedLargeDebris - removed.large))
  const mediumDebris = Math.max(0, Math.round(ratedShell.mediumDebris + produced.medium + convertedMediumDebris - removed.medium))
  const smallDebris = Math.max(0, Math.round(ratedShell.smallDebris + produced.small + convertedSmallDebris - removed.small))
  const avoidanceEffectiveness = round(
    clamp(
      ratedShell.avoidanceEffectiveness -
        expectedCollisions * 0.0009 -
        Math.max(0, pressureRatio - 1) * 0.00018,
      0.35,
      0.95
    ),
    3
  )

  const collisionDebt = (ratedShell.collisionDebt || 0) + expectedCollisions
  const integerCollisions = Math.floor(collisionDebt)
  const nextDebt = round(collisionDebt - integerCollisions, 3)
  const updatedShell = {
    ...ratedShell,
    activeSatellites,
    survivingActiveSatellites,
    activeLossDebt,
    derelictObjects,
    largeDebris,
    mediumDebris,
    smallDebris,
    avoidanceEffectiveness,
    collisionDebt: nextDebt,
    cascadeExposure: round(clamp(cascadeExposure + expectedCollisions * 0.006 + productionScale * 0.0012, 0, 3), 3),
    debrisGrowthStreak:
      largeDebris + mediumDebris + smallDebris > ratedShell.largeDebris + ratedShell.mediumDebris + ratedShell.smallDebris
        ? (ratedShell.debrisGrowthStreak || 0) + 1
        : 0
  }

  updatedShell.collisionRatePerYear = computeShellCollisionRate(updatedShell, baselineShell)
  updatedShell.kesslerRatio = computeKesslerRatio(updatedShell, baselineShell, template)
  const progressGain = computeKesslerProgressGain(updatedShell, baselineShell)
  updatedShell.kesslerSustainedMonths =
    progressGain > 0
      ? round((ratedShell.kesslerSustainedMonths || 0) + progressGain, 3)
      : Math.max(0, round((ratedShell.kesslerSustainedMonths || 0) + progressGain, 3))

  return {
    shell: updatedShell,
    expectedCollisions,
    integerCollisions,
    debrisDelta: {
      large: Math.max(0, Math.round(produced.large + convertedLargeDebris)),
      medium: Math.max(0, Math.round(produced.medium + convertedMediumDebris)),
      small: Math.max(0, Math.round(produced.small + convertedSmallDebris))
    }
  }
}

function findOperationalCollapse(state, environment) {
  const riskiestShell = getRiskiestShell(environment) ?? environment.shellStates[0]
  const totals = getEnvironmentTotals(environment)

  if (totals.totalSurvivingActiveSatellites <= 0) {
    return { reached: true, shell: riskiestShell, reason: 'active_satellite_loss' }
  }

  return { reached: false }
}

function advanceMonth(state) {
  const nextMonthsElapsed = state.monthsElapsed + 1
  const nextYear = state.startYear + nextMonthsElapsed / 12
  const nextMonthIndex = nextMonthsElapsed % 12
  const template = state.collisionTemplate || getCollisionTemplate(state.collisionType)
  const exposedShells = state.environment.shellStates.map((shell, index, shells) => {
    const neighborExposure = (shells[index - 1]?.cascadeExposure || 0) * 0.01 + (shells[index + 1]?.cascadeExposure || 0) * 0.01
    return {
      ...shell,
      cascadeExposure: round(clamp((shell.cascadeExposure || 0) + neighborExposure, 0, 3), 3)
    }
  })
  const shellResults = exposedShells.map((shell) =>
    advanceShell(shell, findBaselineShell(state, shell), template, Boolean(state.threshold))
  )
  const postEnvironment = {
    ...state.environment,
    year: nextYear,
    shellStates: shellResults.map((result) => result.shell)
  }

  const nextState = {
    ...state,
    environment: postEnvironment,
    currentYear: nextYear,
    currentMonthIndex: nextMonthIndex,
    monthsElapsed: nextMonthsElapsed,
    expectedCollisionCount: round(
      (state.expectedCollisionCount || state.collisionCount || 0) +
        shellResults.reduce((sum, result) => sum + result.expectedCollisions, 0),
      3
    ),
    events: [...state.events],
    pendingVisualEvents: []
  }

  for (const result of shellResults) {
    if (result.integerCollisions <= 0) continue
    const event = createCascadeEvent(
      nextState,
      result.shell,
      result.integerCollisions,
      result.expectedCollisions,
      result.debrisDelta
    )
    nextState.events.push(event)
    nextState.pendingVisualEvents.push(event)
    nextState.collisionCount += result.integerCollisions
  }

  const threshold = checkKesslerThreshold(nextState.environment.shellStates, nextYear)
  if (threshold.reached && !nextState.threshold) {
    const thresholdWithElapsed = { ...threshold, elapsedMonths: nextState.monthsElapsed }
    nextState.thresholdCandidate = thresholdWithElapsed
    nextState.threshold = thresholdWithElapsed
    const thresholdEvent = createThresholdEvent(nextState, thresholdWithElapsed)
    nextState.events.push(thresholdEvent)
    nextState.pendingVisualEvents.push(thresholdEvent)
  }

  const collapse = findOperationalCollapse(nextState, nextState.environment)
  const monthsSinceThreshold = nextState.threshold?.reached
    ? nextState.monthsElapsed - (nextState.threshold.elapsedMonths || nextState.monthsElapsed)
    : 0
  const collapseDelaySatisfied = nextState.threshold?.reached ? monthsSinceThreshold >= 12 : nextState.monthsElapsed >= 12
  if (collapse.reached && collapseDelaySatisfied) {
    const collapseEvent = createOperationalCollapseEvent(nextState, collapse.shell, collapse.reason)
    nextState.phase = 'stopped'
    nextState.stopReason = 'operational_collapse'
    if (!nextState.threshold) {
      nextState.threshold = {
        reached: false,
        triggerReason: 'operational_collapse',
        yearReached: nextYear,
        triggerShellId: collapse.shell?.id
      }
    }
    nextState.events.push(collapseEvent)
    nextState.pendingVisualEvents.push(collapseEvent)
  }

  return nextState
}

export function advanceSimulationByMonths(state, months = 1, pacingInput = {}) {
  const pacing = { ...DEFAULT_SIMULATION_PACING, ...pacingInput }
  if (state.phase === 'stopped') return cloneState(state)

  let nextState = cloneState(state)
  nextState.visualSecondsElapsed = (state.visualSecondsElapsed ?? 0) + ((pacing.visualTickMs ?? 650) / 1000)

  const hardLimitMonths = Math.max(1, Math.round(Math.min(pacing.hardLimitYears, state.hardLimitYears) * 12))
  const targetMonths = Math.min(hardLimitMonths, nextState.monthsElapsed + Math.max(1, Math.round(months)))
  const visualEvents = []

  while (nextState.phase === 'running' && nextState.monthsElapsed < targetMonths) {
    nextState = advanceMonth(nextState)
    visualEvents.push(...nextState.pendingVisualEvents)
    nextState.pendingVisualEvents = []
    if (nextState.phase === 'stopped') {
      nextState.pendingVisualEvents = visualEvents
      return nextState
    }
  }

  if (nextState.phase === 'running' && nextState.monthsElapsed >= hardLimitMonths) {
    const hardLimitEvent = createHardLimitEvent(nextState)
    nextState.phase = 'stopped'
    nextState.stopReason = 'hard_limit'
    nextState.threshold = {
      reached: false,
      triggerReason: 'hard_limit',
      yearReached: nextState.currentYear,
      triggerShellId: (getRiskiestShell(nextState.environment) ?? nextState.environment.shellStates[0])?.id
    }
    nextState.events.push(hardLimitEvent)
    nextState.pendingVisualEvents.push(hardLimitEvent)
  }

  nextState.pendingVisualEvents = [...visualEvents, ...nextState.pendingVisualEvents]

  return nextState
}
