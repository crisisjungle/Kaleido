import * as THREE from 'three'
import { seededRandom, clamp, lerp } from '../core/math'
import { degToRad } from './coordinates'

const DUST_POINT_CAPACITY = 18900
const GLINT_POINT_CAPACITY = 3520
const DUST_BASE_COUNT = 900
const GLINT_BASE_COUNT = 120
const DUST_MAX_TARGET = 18000
const GLINT_MAX_TARGET = 3400
const DUST_OPACITY = 0.68
const GLINT_OPACITY = 0.88
const SMOOTHING_SPEED = 0.9

function shellDebrisTotal(shell) {
  return (shell.largeDebris || 0) + (shell.mediumDebris || 0) + (shell.smallDebris || 0)
}

function shellKesslerIntensity(shell) {
  const debrisTotal = shellDebrisTotal(shell)
  const debrisDensity = clamp((Math.log10(debrisTotal + 1) - 6.4) / 3.4, 0, 1)
  const kessler = clamp(Math.log1p(Math.max(0, shell.kesslerRatio || 0)) / Math.log(18), 0, 1)
  const exposure = clamp((shell.cascadeExposure || 0) / 2.4, 0, 1)
  const growth = clamp((shell.debrisGrowthStreak || 0) / 10, 0, 1)
  const collapse = Math.max(kessler, exposure * 0.75, growth * 0.85)

  if (collapse < 0.14 || debrisDensity < 0.08) return 0
  return clamp(debrisDensity * 0.55 + collapse * 0.65, 0, 1)
}

function countForShell(shell, maxCount, baseCount, capacity) {
  const intensity = shellKesslerIntensity(shell)
  if (intensity <= 0) return 0
  return Math.min(capacity, Math.round(baseCount + maxCount * Math.pow(intensity, 1.15)))
}

function writeShellPoints(shell, shellPlanes, positions, colors, random, count, kind, intensity) {
  if (!shellPlanes.length || count <= 0) return

  const radialThickness = 0.03 + intensity * 0.16
  const alongTrackJitter = kind === 'glint' ? 0.012 : 0.032

  for (let index = 0; index < count; index += 1) {
    const plane = shellPlanes[Math.floor(random() * shellPlanes.length)] ?? shellPlanes[0]
    const radius = plane.radius + (random() - 0.5) * radialThickness
    const theta = random() * Math.PI * 2 + (random() - 0.5) * alongTrackJitter
    const inclination = degToRad(plane.inclinationDeg + (random() - 0.5) * 1.8)
    const raan = degToRad(plane.raanDeg + (random() - 0.5) * 2.5)

    const cosTheta = Math.cos(theta)
    const sinTheta = Math.sin(theta)
    const xOrb = radius * cosTheta
    const yOrb = radius * sinTheta
    const yInc = yOrb * Math.cos(inclination)
    const zInc = yOrb * Math.sin(inclination)
    const cosRaan = Math.cos(raan)
    const sinRaan = Math.sin(raan)
    let x = xOrb * cosRaan - yInc * sinRaan
    let y = zInc
    let z = xOrb * sinRaan + yInc * cosRaan

    const length = Math.sqrt(x * x + y * y + z * z) || 1
    const radialOffset = (random() - 0.5) * radialThickness * 0.6
    x += (x / length) * radialOffset
    y += (y / length) * radialOffset
    z += (z / length) * radialOffset

    const cursor = index * 3
    positions[cursor] = x
    positions[cursor + 1] = y
    positions[cursor + 2] = z

    if (kind === 'glint') {
      const warm = random() > 0.78
      colors[cursor] = warm ? 1 : 0.82
      colors[cursor + 1] = warm ? 0.78 : 0.92
      colors[cursor + 2] = warm ? 0.24 : 1
    } else {
      const blue = 0.38 + random() * 0.34
      const brightness = 0.35 + random() * 0.45
      colors[cursor] = brightness * 0.72
      colors[cursor + 1] = brightness * 0.85
      colors[cursor + 2] = blue + brightness * 0.26
    }
  }
}

function createPoints(name, positions, colors, size) {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
  geometry.setDrawRange(0, 0)

  const points = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      size,
      vertexColors: true,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true
    })
  )
  points.name = name
  points.frustumCulled = false
  return points
}

function createShellHaze(shell, shellPlanes) {
  if (!shellPlanes.length) return null

  const radius =
    shellPlanes.reduce((sum, plane) => sum + plane.radius, 0) / Math.max(1, shellPlanes.length)
  const geometry = new THREE.SphereGeometry(radius, 96, 48)
  const material = new THREE.MeshBasicMaterial({
    color: '#bae6fd',
    transparent: true,
    opacity: 0,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide
  })
  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = `kessler-haze-${shell.id}`
  mesh.renderOrder = 1
  return mesh
}

function createShellVisual(shell, shellPlanes) {
  const dustPositions = new Float32Array(DUST_POINT_CAPACITY * 3)
  const dustColors = new Float32Array(DUST_POINT_CAPACITY * 3)
  const glintPositions = new Float32Array(GLINT_POINT_CAPACITY * 3)
  const glintColors = new Float32Array(GLINT_POINT_CAPACITY * 3)
  const random = seededRandom(`kessler-shell:${shell.id}:stable-capacity`)

  writeShellPoints(shell, shellPlanes, dustPositions, dustColors, random, DUST_POINT_CAPACITY, 'dust', 1)
  writeShellPoints(shell, shellPlanes, glintPositions, glintColors, random, GLINT_POINT_CAPACITY, 'glint', 1)

  const dust = createPoints(`kessler-dust-${shell.id}`, dustPositions, dustColors, 0.014)
  const glints = createPoints(`kessler-glints-${shell.id}`, glintPositions, glintColors, 0.024)
  const haze = createShellHaze(shell, shellPlanes)

  return {
    shellId: shell.id,
    dust,
    glints,
    haze,
    currentIntensity: 0,
    currentDustCount: 0,
    currentGlintCount: 0,
    targetIntensity: 0,
    targetDustCount: 0,
    targetGlintCount: 0,
    targetHazeOpacity: 0
  }
}

function applyShellVisual(visual) {
  const intensity = clamp(visual.currentIntensity, 0, 1)
  const dustCount = Math.max(0, Math.min(DUST_POINT_CAPACITY, Math.round(visual.currentDustCount)))
  const glintCount = Math.max(0, Math.min(GLINT_POINT_CAPACITY, Math.round(visual.currentGlintCount)))

  visual.dust.geometry.setDrawRange(0, dustCount)
  visual.glints.geometry.setDrawRange(0, glintCount)
  visual.dust.material.opacity = DUST_OPACITY * intensity
  visual.glints.material.opacity = GLINT_OPACITY * Math.pow(intensity, 0.8)
  if (visual.haze) visual.haze.material.opacity = visual.currentHazeOpacity || 0
}

function shellTarget(shell) {
  const intensity = shellKesslerIntensity(shell)
  return {
    intensity,
    dustCount: countForShell(shell, DUST_MAX_TARGET, DUST_BASE_COUNT, DUST_POINT_CAPACITY),
    glintCount: countForShell(shell, GLINT_MAX_TARGET, GLINT_BASE_COUNT, GLINT_POINT_CAPACITY),
    hazeOpacity: intensity > 0 ? 0.012 + intensity * 0.034 : 0
  }
}

function publishDebugState(system) {
  if (!import.meta.env.DEV || typeof window === 'undefined') return
  const shells = system.shellVisuals
    .filter((visual) => visual.currentDustCount >= 1 || visual.currentGlintCount >= 1)
    .map((visual) => ({
      id: visual.shellId,
      intensity: Number(visual.currentIntensity.toFixed(3)),
      dustCount: Math.round(visual.currentDustCount),
      glintCount: Math.round(visual.currentGlintCount)
    }))

  window.__envfishDebrisShell = {
    pointCount: shells.reduce((sum, shell) => sum + shell.dustCount + shell.glintCount, 0),
    hazeCount: system.shellVisuals.filter((visual) => (visual.currentHazeOpacity || 0) > 0.001).length,
    shells
  }
}

export function setDebrisShellTargets(system, shellStates, options = {}) {
  if (!system) return
  const shellsById = new Map(shellStates.map((shell) => [shell.id, shell]))

  system.shellVisuals.forEach((visual) => {
    const shell = shellsById.get(visual.shellId)
    const target = shell
      ? shellTarget(shell)
      : { intensity: 0, dustCount: 0, glintCount: 0, hazeOpacity: 0 }
    visual.targetIntensity = target.intensity
    visual.targetDustCount = target.dustCount
    visual.targetGlintCount = target.glintCount
    visual.targetHazeOpacity = target.hazeOpacity

    if (options.immediate) {
      visual.currentIntensity = visual.targetIntensity
      visual.currentDustCount = visual.targetDustCount
      visual.currentGlintCount = visual.targetGlintCount
      visual.currentHazeOpacity = visual.targetHazeOpacity
      applyShellVisual(visual)
    }
  })

  publishDebugState(system)
}

export function createDebrisShellSystem(shellStates, planes) {
  const group = new THREE.Group()
  group.name = 'kessler-debris-shell'

  const planesByShell = new Map()
  planes.forEach((plane) => {
    if (!planesByShell.has(plane.shellId)) planesByShell.set(plane.shellId, [])
    planesByShell.get(plane.shellId).push(plane)
  })

  const shellVisuals = shellStates.map((shell) => {
    const visual = createShellVisual(shell, planesByShell.get(shell.id) ?? [])
    if (visual.haze) group.add(visual.haze)
    group.add(visual.dust)
    group.add(visual.glints)
    return visual
  })

  const system = {
    group,
    shellVisuals,
    lastElapsed: 0,
    signature: planes.map((plane) => `${plane.id}:${plane.radius.toFixed(4)}`).join('|')
  }

  setDebrisShellTargets(system, shellStates, { immediate: true })
  return system
}

export function updateDebrisShellSystem(system, elapsedSeconds) {
  if (!system?.group) return
  const deltaSeconds = system.lastElapsed ? Math.max(0.001, elapsedSeconds - system.lastElapsed) : 0.016
  const alpha = 1 - Math.exp(-deltaSeconds * SMOOTHING_SPEED)
  system.lastElapsed = elapsedSeconds

  system.shellVisuals.forEach((visual) => {
    visual.currentIntensity = lerp(visual.currentIntensity, visual.targetIntensity, alpha)
    visual.currentDustCount = lerp(visual.currentDustCount, visual.targetDustCount, alpha)
    visual.currentGlintCount = lerp(visual.currentGlintCount, visual.targetGlintCount, alpha)
    visual.currentHazeOpacity = lerp(visual.currentHazeOpacity || 0, visual.targetHazeOpacity, alpha)
    applyShellVisual(visual)
  })

  system.group.rotation.y = elapsedSeconds * 0.006
  system.group.rotation.x = Math.sin(elapsedSeconds * 0.08) * 0.006
  publishDebugState(system)
}

export function disposeDebrisShellSystem(system) {
  if (!system) return
  system.shellVisuals.forEach((visual) => {
    system.group.remove(visual.dust)
    system.group.remove(visual.glints)
    visual.dust.geometry.dispose()
    visual.dust.material.dispose()
    visual.glints.geometry.dispose()
    visual.glints.material.dispose()
    if (visual.haze) {
      system.group.remove(visual.haze)
      visual.haze.geometry.dispose()
      visual.haze.material.dispose()
    }
  })
}
