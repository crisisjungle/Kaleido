import { KESSLER_SUSTAINED_MONTHS } from './cascadeModel'

export function checkKesslerThreshold(shells, currentYear) {
  const sustainedShell = [...shells]
    .filter((shell) => (shell.kesslerSustainedMonths || 0) >= KESSLER_SUSTAINED_MONTHS)
    .sort((left, right) => {
      if ((right.kesslerRatio || 0) !== (left.kesslerRatio || 0)) {
        return (right.kesslerRatio || 0) - (left.kesslerRatio || 0)
      }
      return (right.collisionRatePerYear || 0) - (left.collisionRatePerYear || 0)
    })[0]

  if (sustainedShell) {
    return {
      reached: true,
      triggerShellId: sustainedShell.id,
      triggerReason: 'self_sustaining',
      kesslerRatio: sustainedShell.kesslerRatio || 0,
      sustainedMonths: sustainedShell.kesslerSustainedMonths || 0,
      yearReached: currentYear
    }
  }

  return { reached: false }
}
