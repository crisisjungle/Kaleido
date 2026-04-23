import environmentPresets from '../data/environment-presets.json'
import { clamp, lerp, ratio, round } from './math'

const sortedPresets = [...environmentPresets.presets].sort((a, b) => a.year - b.year)

export function getAvailableEnvironmentYears() {
  return sortedPresets.map((preset) => preset.year)
}

export function cloneEnvironment(environment) {
  return {
    year: environment.year,
    shellStates: environment.shellStates.map((shell) => ({ ...shell }))
  }
}

function interpolateShellState(lower, upper, t) {
  const activeSatellites = Math.max(0, Math.round(lerp(lower.activeSatellites, upper.activeSatellites, t)))
  return {
    id: lower.id,
    label: lower.label,
    altitudeMinKm: round(lerp(lower.altitudeMinKm, upper.altitudeMinKm, t), 0),
    altitudeMaxKm: round(lerp(lower.altitudeMaxKm, upper.altitudeMaxKm, t), 0),
    activeSatellites,
    survivingActiveSatellites: activeSatellites,
    derelictObjects: Math.max(0, Math.round(lerp(lower.derelictObjects, upper.derelictObjects, t))),
    largeDebris: Math.max(0, Math.round(lerp(lower.largeDebris, upper.largeDebris, t))),
    mediumDebris: Math.max(0, Math.round(lerp(lower.mediumDebris, upper.mediumDebris, t))),
    smallDebris: Math.max(0, Math.round(lerp(lower.smallDebris, upper.smallDebris, t))),
    collisionRatePerYear: round(lerp(lower.collisionRatePerYear, upper.collisionRatePerYear, t), 3),
    naturalDecayRate: round(lerp(lower.naturalDecayRate, upper.naturalDecayRate, t), 3),
    avoidanceEffectiveness: round(lerp(lower.avoidanceEffectiveness, upper.avoidanceEffectiveness, t), 3),
    disposalRate: round(lerp(lower.disposalRate, upper.disposalRate, t), 3),
    launchIntensity: Math.max(0, Math.round(lerp(lower.launchIntensity, upper.launchIntensity, t))),
    debrisGrowthStreak: Math.max(0, Math.round(lerp(lower.debrisGrowthStreak, upper.debrisGrowthStreak, t)))
  }
}

function pickBoundingPresets(year) {
  if (year <= sortedPresets[0].year) {
    return { lower: sortedPresets[0], upper: sortedPresets[0], t: 0 }
  }

  const last = sortedPresets[sortedPresets.length - 1]
  if (year >= last.year) {
    return { lower: last, upper: last, t: 0 }
  }

  for (let index = 0; index < sortedPresets.length - 1; index += 1) {
    const lower = sortedPresets[index]
    const upper = sortedPresets[index + 1]
    if (year >= lower.year && year <= upper.year) {
      return { lower, upper, t: ratio(year, lower.year, upper.year) }
    }
  }

  return { lower: last, upper: last, t: 0 }
}

export function generateEnvironmentByStartTime(year) {
  const { lower, upper, t } = pickBoundingPresets(year)

  if (lower.year === upper.year) {
    return cloneEnvironment(lower)
  }

  return {
    year,
    shellStates: lower.shellStates.map((shell, index) =>
      interpolateShellState(shell, upper.shellStates[index], clamp(t, 0, 1))
    )
  }
}

export function getShellIndex(environment, shellId) {
  return environment.shellStates.findIndex((shell) => shell.id === shellId)
}
