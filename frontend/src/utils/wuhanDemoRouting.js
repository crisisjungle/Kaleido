const firstQueryValue = (value) => (Array.isArray(value) ? value[0] : value)

const parseStep = (value) => {
  const step = Number.parseInt(String(firstQueryValue(value) || ''), 10)
  return [1, 2, 3, 4].includes(step) ? step : null
}

export function resolveWuhanDemoVersion(value) {
  return String(firstQueryValue(value) || '').trim().toLowerCase() === 'v1' ? 'v1' : 'v2'
}

export function resolveWuhanDemoStep({
  version,
  requestedStep,
  playback = false,
  defaultStep = 1
} = {}) {
  const normalizedVersion = resolveWuhanDemoVersion(version)
  const explicitStep = parseStep(requestedStep)

  if (normalizedVersion === 'v1') {
    return explicitStep === 3 || playback ? 3 : 2
  }
  if (explicitStep) return explicitStep
  if (playback) return 3
  return parseStep(defaultStep) || 1
}
