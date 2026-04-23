import collisionPresets from '../data/collision-presets.json'
import { cloneEnvironment, getShellIndex } from './environment'
import { clamp, round } from './math'
import { computeCascadeSeverity, computeKesslerRatio, computeShellCollisionRate } from './cascadeModel'
import { getRiskiestShell } from './metrics'

const templatesById = new Map(collisionPresets.presets.map((template) => [template.id, template]))

export function getCollisionTemplate(collisionType) {
  const template = templatesById.get(collisionType)
  if (!template) {
    throw new Error(`Unknown collision template: ${collisionType}`)
  }
  return template
}

export function listCollisionTemplates() {
  return [...collisionPresets.presets]
}

function applyCollisionShock(environment, shellIndex, template, scale) {
  const updatedShells = environment.shellStates.map((shell) => ({ ...shell }))
  const impactIndexes = [
    { index: shellIndex, factor: 1 },
    { index: shellIndex - 1, factor: template.spreadFactor * 0.65 },
    { index: shellIndex + 1, factor: template.spreadFactor * 0.5 }
  ]

  for (const impact of impactIndexes) {
    const shell = updatedShells[impact.index]
    if (!shell) continue

    const appliedScale = scale * impact.factor
    const directActiveLoss = Math.min(
      shell.activeSatellites,
      Math.max(appliedScale >= 0.5 ? 1 : 0, Math.round(template.rateShock * 6 * appliedScale))
    )
    shell.largeDebris += Math.round(template.largeDebrisDelta * appliedScale)
    shell.mediumDebris += Math.round(template.mediumDebrisDelta * appliedScale)
    shell.smallDebris += Math.round(template.smallDebrisFactor * appliedScale)
    shell.derelictObjects += Math.max(1, Math.round(template.rateShock * 14 * appliedScale))
    shell.activeSatellites = Math.max(0, shell.activeSatellites - directActiveLoss)
    shell.survivingActiveSatellites = Math.max(
      0,
      (shell.survivingActiveSatellites ?? shell.activeSatellites + directActiveLoss) - directActiveLoss
    )
    shell.collisionRatePerYear = round(shell.collisionRatePerYear + template.rateShock * appliedScale, 3)
    const exposureShock = appliedScale * clamp(template.growthShock, 0.08, 1.2)
    shell.cascadeExposure = round(clamp((shell.cascadeExposure || 0) + exposureShock, 0, 3), 3)
    shell.debrisGrowthStreak = Math.min(12, shell.debrisGrowthStreak + Math.max(1, Math.round(template.growthShock * 3 * appliedScale)))
    shell.avoidanceEffectiveness = round(clamp(shell.avoidanceEffectiveness - template.rateShock * 0.04 * appliedScale, 0.45, 0.95), 3)
  }

  return { ...environment, shellStates: updatedShells }
}

function recomputeCollisionRates(environment, baselineEnvironment = environment, template = getCollisionTemplate('small')) {
  return {
    ...environment,
    shellStates: environment.shellStates.map((shell) => {
      const baselineShell = baselineEnvironment.shellStates.find((entry) => entry.id === shell.id) || shell
      const collisionRatePerYear = computeShellCollisionRate(shell, baselineShell)
      const ratedShell = {
        ...shell,
        collisionRatePerYear,
        collisionDebt: shell.collisionDebt || 0,
        kesslerRatio: 0,
        kesslerSustainedMonths: shell.kesslerSustainedMonths || 0
      }
      return {
        ...ratedShell,
        kesslerRatio: computeKesslerRatio(ratedShell, baselineShell, template)
      }
    })
  }
}

export function injectInitialCollision(environment, collisionType, shellId, startYear, pacing) {
  const collisionTemplate = getCollisionTemplate(collisionType)
  const clonedEnvironment = {
    ...cloneEnvironment(environment),
    shellStates: environment.shellStates.map((shell) => ({
      ...shell,
      survivingActiveSatellites: shell.survivingActiveSatellites ?? shell.activeSatellites
    }))
  }
  const targetIndex = getShellIndex(clonedEnvironment, shellId)
  const impactIndex = targetIndex >= 0 ? targetIndex : 0
  const shockedEnvironment = applyCollisionShock(clonedEnvironment, impactIndex, collisionTemplate, 1)
  const rebasedEnvironment = recomputeCollisionRates(shockedEnvironment, clonedEnvironment, collisionTemplate)
  const targetShell = rebasedEnvironment.shellStates[impactIndex]

  const event = {
    id: 'initial_collision-0-0',
    type: 'initial_collision',
    shellId: targetShell.id,
    year: startYear,
    monthIndex: 0,
    elapsedMonths: 0,
    title: `${collisionTemplate.label} initiated`,
    collisionTypeId: collisionType,
    eventCount: 1,
    collisionRatePerYear: targetShell.collisionRatePerYear,
    debrisDelta: {
      large: collisionTemplate.largeDebrisDelta,
      medium: collisionTemplate.mediumDebrisDelta,
      small: collisionTemplate.smallDebrisFactor
    }
  }

  return {
    environment: rebasedEnvironment,
    baselineEnvironment: cloneEnvironment(environment),
    collisionType,
    collisionTemplate,
    startYear,
    currentYear: startYear,
    currentMonthIndex: 0,
    monthsElapsed: 0,
    visualSecondsElapsed: 0,
    phase: 'running',
    events: [event],
    expectedCollisionCount: 1,
    collisionCount: 1,
    initialShellId: targetShell.id,
    hardLimitYears: pacing?.hardLimitYears ?? 50,
    thresholdCandidate: null,
    threshold: null,
    stopReason: null,
    pendingVisualEvents: [event]
  }
}

export function applyFollowOnShock(environment, collisionType, collisionCount) {
  const template = getCollisionTemplate(collisionType)
  const riskiestShell = getRiskiestShell(environment)
  const targetIndex = Math.max(0, environment.shellStates.findIndex((shell) => shell.id === riskiestShell?.id))
  const scale = clamp(computeCascadeSeverity(riskiestShell || environment.shellStates[targetIndex], environment.shellStates[targetIndex]), 0.7, 3.8)
  return recomputeCollisionRates(applyCollisionShock(environment, targetIndex, template, scale), environment, template)
}

export { recomputeCollisionRates }
