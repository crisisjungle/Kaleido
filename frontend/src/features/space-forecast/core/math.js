export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

export function lerp(start, end, t) {
  return start + (end - start) * t
}

export function ratio(value, min, max) {
  if (max === min) return 0
  return clamp((value - min) / (max - min), 0, 1)
}

export function round(value, decimals = 2) {
  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}

export function hashString(input) {
  let hash = 2166136261
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function seededRandom(seed) {
  let state = hashString(String(seed)) || 1
  return () => {
    state ^= state << 13
    state ^= state >>> 17
    state ^= state << 5
    return (state >>> 0) / 4294967296
  }
}
