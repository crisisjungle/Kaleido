import { round } from './math'
import { collisionPressure } from './cascadeModel'

export function getEnvironmentTotals(environment) {
  const totals = environment.shellStates.reduce(
    (acc, shell) => {
      acc.totalActiveSatellites += shell.activeSatellites
      acc.totalSurvivingActiveSatellites += shell.survivingActiveSatellites ?? shell.activeSatellites
      acc.totalDerelictObjects += shell.derelictObjects
      acc.totalLargeDebris += shell.largeDebris
      acc.totalMediumDebris += shell.mediumDebris
      acc.totalSmallDebris += shell.smallDebris
      return acc
    },
    {
      totalActiveSatellites: 0,
      totalSurvivingActiveSatellites: 0,
      totalDerelictObjects: 0,
      totalLargeDebris: 0,
      totalMediumDebris: 0,
      totalSmallDebris: 0
    }
  )

  return {
    ...totals,
    totalTrackedObjects: totals.totalActiveSatellites + totals.totalDerelictObjects + totals.totalLargeDebris
  }
}

export function getGlobalCollisionRatePerYear(environment) {
  return round(
    environment.shellStates.reduce((sum, shell) => sum + Math.max(0, shell.collisionRatePerYear || 0), 0),
    2
  )
}

export function getRiskiestShell(environment) {
  const shells = [...environment.shellStates]
  if (shells.length === 0) return null

  shells.sort((left, right) => {
    if (right.collisionRatePerYear !== left.collisionRatePerYear) {
      return right.collisionRatePerYear - left.collisionRatePerYear
    }
    const leftDebris = left.largeDebris + left.mediumDebris + left.smallDebris
    const rightDebris = right.largeDebris + right.mediumDebris + right.smallDebris
    return rightDebris - leftDebris
  })

  return shells[0] ?? null
}

export function getAverageNextMajorCollisionWaitMonths(environment) {
  const globalRate = getGlobalCollisionRatePerYear(environment)
  if (globalRate <= 0) return 0
  return round(12 / globalRate, 1)
}

export function getEnvironmentMetrics(environment) {
  const maxKesslerRatio = Math.max(...environment.shellStates.map((shell) => Number(shell.kesslerRatio || 0)), 0)
  const totalCollisionPressure = environment.shellStates.reduce((sum, shell) => sum + collisionPressure(shell), 0)
  return {
    ...getEnvironmentTotals(environment),
    globalCollisionRatePerYear: getGlobalCollisionRatePerYear(environment),
    riskiestShell: getRiskiestShell(environment),
    averageNextMajorCollisionWaitMonths: getAverageNextMajorCollisionWaitMonths(environment),
    maxKesslerRatio: round(maxKesslerRatio, 2),
    totalCollisionPressure: round(totalCollisionPressure, 1)
  }
}
