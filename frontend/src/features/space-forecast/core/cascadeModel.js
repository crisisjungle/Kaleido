import { clamp, round } from './math'

const PRESSURE_WEIGHTS = {
  activeSatellites: 0.3,
  derelictObjects: 0.62,
  largeDebris: 1.15,
  mediumDebris: 0.012,
  smallDebris: 0.00006
}

export const KESSLER_SUSTAINED_MONTHS = 120

const FOLLOW_ON_FRAGMENT_YIELD = {
  large: 1200,
  medium: 18000,
  small: 240000
}

const FOLLOW_ON_YIELD_SCALE = {
  small: 0.28,
  iridium_like: 0.16,
  large_catastrophic: 0.12,
  asat_like: 0.08
}

export function collisionPressure(shell) {
  return (
    shell.activeSatellites * PRESSURE_WEIGHTS.activeSatellites +
    shell.derelictObjects * PRESSURE_WEIGHTS.derelictObjects +
    shell.largeDebris * PRESSURE_WEIGHTS.largeDebris +
    shell.mediumDebris * PRESSURE_WEIGHTS.mediumDebris +
    shell.smallDebris * PRESSURE_WEIGHTS.smallDebris
  )
}

export function debrisPressure(debrisDelta) {
  return (
    (debrisDelta.large || 0) * PRESSURE_WEIGHTS.largeDebris +
    (debrisDelta.medium || 0) * PRESSURE_WEIGHTS.mediumDebris +
    (debrisDelta.small || 0) * PRESSURE_WEIGHTS.smallDebris
  )
}

export function debrisInventoryPressure(shell) {
  return debrisPressure({
    large: shell.largeDebris || 0,
    medium: shell.mediumDebris || 0,
    small: shell.smallDebris || 0
  })
}

export function getAltitudeRetention(shell) {
  const midpointKm = ((shell.altitudeMinKm || 0) + (shell.altitudeMaxKm || 0)) / 2
  return round(clamp(0.3 + ((midpointKm - 350) / 950) * 0.92, 0.28, 1.22), 3)
}

export function getAtmosphericDecayBoost(shell) {
  const midpointKm = ((shell.altitudeMinKm || 0) + (shell.altitudeMaxKm || 0)) / 2
  if (midpointKm < 500) return 3.2
  if (midpointKm < 650) return 1.75
  if (midpointKm < 900) return 0.85
  if (midpointKm < 1200) return 0.48
  return 0.32
}

export function computePressureRatio(shell, baselineShell) {
  const baselinePressure = Math.max(1, collisionPressure(baselineShell || shell))
  return collisionPressure(shell) / baselinePressure
}

export function computeAutonomousAvoidance(shell) {
  const effectiveness = clamp(shell.avoidanceEffectiveness ?? 0.78, 0.35, 0.98)
  const fleetCoordination = clamp(Math.log10((shell.activeSatellites || 0) + 10) / 6, 0.45, 0.9)
  const autonomy = clamp(effectiveness * (0.82 + fleetCoordination * 0.18), 0.35, 0.97)
  const referenceMissRate = Math.pow(1 - 0.78, 1.2)
  const missRate = Math.pow(1 - autonomy, 1.2)
  const lossReference = Math.pow(1 - 0.78, 1.35)
  const lossRate = Math.pow(1 - autonomy, 1.35)

  return {
    autonomy: round(autonomy, 3),
    collisionMultiplier: round(clamp(missRate / referenceMissRate, 0.08, 1.28), 3),
    lossMultiplier: round(clamp(lossRate / lossReference, 0.06, 1.18), 3),
    collapseBuffer: round(clamp(1 + autonomy * 2.4, 1.7, 3.4), 3)
  }
}

export function computeShellCollisionRate(shell, baselineShell) {
  const baseline = baselineShell || shell
  const baselineRate = Math.max(0.015, baseline.collisionRatePerYear || shell.collisionRatePerYear || 0.015)
  const pressureRatio = computePressureRatio(shell, baseline)
  const mitigationRatio = clamp(
    (1 - (shell.avoidanceEffectiveness ?? 0.78) + 0.08) /
      (1 - (baseline.avoidanceEffectiveness ?? 0.78) + 0.08),
    0.45,
    3.5
  )
  const launchRatio = clamp((shell.launchIntensity + 18) / ((baseline.launchIntensity || 0) + 18), 0.65, 1.8)
  const retentionRatio = getAltitudeRetention(shell) / Math.max(0.01, getAltitudeRetention(baseline))
  const avoidance = computeAutonomousAvoidance(shell)
  const rate = baselineRate * pressureRatio * pressureRatio * mitigationRatio * launchRatio * retentionRatio * avoidance.collisionMultiplier
  return round(clamp(rate, 0.005, 240), 3)
}

export function computeTemplatePressure(template, scale = 1) {
  return debrisPressure({
    large: template.largeDebrisDelta * scale,
    medium: template.mediumDebrisDelta * scale,
    small: template.smallDebrisFactor * scale
  })
}

export function getFollowOnDebrisYield(template) {
  const scale = FOLLOW_ON_YIELD_SCALE[template?.id] ?? 0.14
  return {
    large: FOLLOW_ON_FRAGMENT_YIELD.large * scale,
    medium: FOLLOW_ON_FRAGMENT_YIELD.medium * scale,
    small: FOLLOW_ON_FRAGMENT_YIELD.small * scale
  }
}

export function computeFollowOnFragmentPressure(template, scale = 1) {
  const yieldTemplate = getFollowOnDebrisYield(template)
  return debrisPressure({
    large: yieldTemplate.large * scale,
    medium: yieldTemplate.medium * scale,
    small: yieldTemplate.small * scale
  })
}

export function computeCascadeSeverity(shell, baselineShell) {
  const pressureRatio = computePressureRatio(shell, baselineShell)
  return round(clamp(0.72 + Math.log1p(Math.max(0, pressureRatio - 1)) * 0.34, 0.7, 3.8), 3)
}

export function computeAnnualRemovalPressure(shell) {
  const decayBoost = getAtmosphericDecayBoost(shell)
  const naturalDecay = Math.max(0, shell.naturalDecayRate || 0)
  const disposal = Math.max(0, shell.disposalRate || 0)

  const debrisRemovalPressure =
    shell.largeDebris * PRESSURE_WEIGHTS.largeDebris * naturalDecay * decayBoost * 0.018 +
    shell.mediumDebris * PRESSURE_WEIGHTS.mediumDebris * naturalDecay * decayBoost * 0.045 +
    shell.smallDebris * PRESSURE_WEIGHTS.smallDebris * naturalDecay * decayBoost * 0.09

  const disposalPressure =
    shell.derelictObjects * PRESSURE_WEIGHTS.derelictObjects * disposal * 0.75 +
    shell.largeDebris * PRESSURE_WEIGHTS.largeDebris * disposal * 0.012

  return Math.max(1, debrisRemovalPressure + disposalPressure)
}

export function computeKesslerRatio(shell, baselineShell, template) {
  const severity = computeCascadeSeverity(shell, baselineShell)
  const baseline = baselineShell || shell
  const baselineRate = Math.max(0, baselineShell?.collisionRatePerYear || 0)
  const excessCollisionRate = Math.max(0, (shell.collisionRatePerYear || 0) - baselineRate)
  const catastrophicCollisionRate = excessCollisionRate * 0.18
  const exposure = clamp(shell.cascadeExposure || 0, 0, 3)
  const baselineDebrisPressure = Math.max(1, debrisInventoryPressure(baseline))
  const debrisGrowthRatio = debrisInventoryPressure(shell) / baselineDebrisPressure
  const maturity = clamp((debrisGrowthRatio - 1) / 4.5, 0, 1)
  const exposureFactor = clamp(exposure / 2.2, 0, 1)
  const retainedProduction =
    computeFollowOnFragmentPressure(template, severity) *
    getAltitudeRetention(shell) *
    exposure *
    maturity *
    exposureFactor
  const annualProductionPressure = catastrophicCollisionRate * retainedProduction
  const annualRemovalPressure = computeAnnualRemovalPressure(shell)
  return round(annualProductionPressure / annualRemovalPressure, 3)
}

export function computeKesslerProgressGain(shell, baselineShell) {
  const ratio = Number(shell.kesslerRatio || 0)
  if (ratio < 1) return -1.6

  const baselineDebrisPressure = Math.max(1, debrisInventoryPressure(baselineShell || shell))
  const debrisGrowthRatio = debrisInventoryPressure(shell) / baselineDebrisPressure
  const maturity = clamp((debrisGrowthRatio - 1) / 5.5, 0, 1)
  const altitudePersistence = getAltitudeRetention(shell)
  const ratioGain = Math.log1p(ratio) / Math.log(80)

  return round(clamp(ratioGain * (0.15 + maturity * 0.85) * altitudePersistence, 0.015, 0.55), 3)
}

export function computeOperationalPressureRatio(environment, baselineEnvironment) {
  const current = environment.shellStates.reduce((sum, shell) => sum + collisionPressure(shell), 0)
  const baseline = baselineEnvironment.shellStates.reduce((sum, shell) => sum + collisionPressure(shell), 0)
  return current / Math.max(1, baseline)
}
