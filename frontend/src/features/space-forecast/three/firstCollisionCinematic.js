import * as THREE from 'three'
import { seededRandom, clamp, lerp } from '../core/math'
import { createCollisionSite } from './collisionEffects'

const APPROACH_SECONDS = 2.4
const HOLD_SECONDS = 0.8
const PULLBACK_SECONDS = 4.8
const FINISH_SECONDS = APPROACH_SECONDS + HOLD_SECONDS + PULLBACK_SECONDS

function smoothstep(value) {
  const t = clamp(value, 0, 1)
  return t * t * (3 - 2 * t)
}

function createSatellite(color, panelColor) {
  const group = new THREE.Group()
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.16, 0.09, 0.09),
    new THREE.MeshStandardMaterial({
      color,
      emissive: '#082f49',
      emissiveIntensity: 0.25,
      metalness: 0.5,
      roughness: 0.38
    })
  )
  const panelMaterial = new THREE.MeshStandardMaterial({
    color: panelColor,
    emissive: '#0e7490',
    emissiveIntensity: 0.2,
    metalness: 0.25,
    roughness: 0.42,
    side: THREE.DoubleSide
  })
  const leftPanel = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.012, 0.09), panelMaterial.clone())
  const rightPanel = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.012, 0.09), panelMaterial.clone())
  const antenna = new THREE.Mesh(
    new THREE.CylinderGeometry(0.004, 0.004, 0.14, 6),
    new THREE.MeshStandardMaterial({ color: '#f8fafc', metalness: 0.65, roughness: 0.28 })
  )

  leftPanel.position.x = -0.21
  rightPanel.position.x = 0.21
  antenna.position.y = 0.11
  group.add(body, leftPanel, rightPanel, antenna)
  group.traverse((child) => {
    if (child.isMesh) {
      child.renderOrder = 24
      child.frustumCulled = false
    }
  })
  return group
}

function createBurst(random) {
  const count = 1100
  const geometry = new THREE.BufferGeometry()
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  const velocities = []

  for (let index = 0; index < count; index += 1) {
    const direction = new THREE.Vector3(random() - 0.5, random() - 0.5, random() - 0.5).normalize()
    direction.x += (random() - 0.5) * 1.8
    direction.z += 0.35 + random() * 0.8
    direction.normalize()
    velocities.push(direction.multiplyScalar(0.22 + random() * 0.72))

    const cursor = index * 3
    const hot = random() > 0.72
    colors[cursor] = hot ? 1 : 0.72 + random() * 0.2
    colors[cursor + 1] = hot ? 0.78 : 0.9 + random() * 0.1
    colors[cursor + 2] = hot ? 0.22 : 1
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const points = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      size: 0.026,
      vertexColors: true,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true
    })
  )
  points.renderOrder = 34
  points.frustumCulled = false

  return { points, positions, velocities }
}

function createBasis(direction) {
  const approach = new THREE.Vector3(-direction.z, 0, direction.x)
  if (approach.lengthSq() < 0.0001) approach.set(1, 0, 0)
  approach.normalize()
  const vertical = new THREE.Vector3().crossVectors(direction, approach).normalize()
  const matrix = new THREE.Matrix4().makeBasis(approach, vertical, direction)
  return { approach, vertical, matrix }
}

export function createFirstCollisionCinematic(event, plane) {
  const random = seededRandom(`first-collision-cinematic:${event.id}`)
  const { position, direction } = createCollisionSite(event, plane)
  const { approach, vertical, matrix } = createBasis(direction)
  const group = new THREE.Group()
  group.name = `first-collision-cinematic-${event.id}`
  group.position.copy(position)
  group.setRotationFromMatrix(matrix)

  const satelliteA = createSatellite('#dbeafe', '#38bdf8')
  const satelliteB = createSatellite('#fef9c3', '#a7f3d0')
  satelliteA.scale.setScalar(1.8)
  satelliteB.scale.setScalar(1.8)
  satelliteA.position.x = -1.05
  satelliteB.position.x = 1.05
  satelliteB.rotation.z = Math.PI
  group.add(satelliteA, satelliteB)

  const flash = new THREE.Mesh(
    new THREE.SphereGeometry(0.12, 32, 18),
    new THREE.MeshBasicMaterial({
      color: '#fff7ad',
      transparent: true,
      opacity: 0,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false
    })
  )
  flash.renderOrder = 35
  group.add(flash)

  const burst = createBurst(random)
  group.add(burst.points)

  const closeCamera = position
    .clone()
    .add(direction.clone().multiplyScalar(0.86))
    .add(approach.clone().multiplyScalar(0.05))
    .add(vertical.clone().multiplyScalar(0.42))
  const overviewCamera = position.clone().normalize().multiplyScalar(12.8)
  overviewCamera.y = Math.max(overviewCamera.y, 6.4)
  overviewCamera.normalize().multiplyScalar(13.4)

  return {
    group,
    position,
    closeCamera,
    overviewCamera,
    lookAt: position.clone(),
    satelliteA,
    satelliteB,
    flash,
    burst,
    startedAt: performance.now(),
    impactTriggered: false,
    finished: false,
    event
  }
}

export function updateFirstCollisionCinematic(cinematic, now) {
  if (!cinematic || cinematic.finished) return null

  const ageSeconds = (now - cinematic.startedAt) / 1000
  const approachProgress = smoothstep(ageSeconds / APPROACH_SECONDS)
  const impactAge = Math.max(0, ageSeconds - APPROACH_SECONDS)

  cinematic.satelliteA.position.x = lerp(-1.05, -0.07, approachProgress)
  cinematic.satelliteB.position.x = lerp(1.05, 0.07, approachProgress)
  cinematic.satelliteA.rotation.y += 0.012
  cinematic.satelliteB.rotation.y -= 0.014

  let impactStarted = false
  if (ageSeconds >= APPROACH_SECONDS && !cinematic.impactTriggered) {
    cinematic.impactTriggered = true
    impactStarted = true
    cinematic.satelliteA.visible = false
    cinematic.satelliteB.visible = false
  }

  if (cinematic.impactTriggered) {
    const flashProgress = clamp(impactAge / 1.4, 0, 1)
    cinematic.flash.material.opacity = Math.max(0, 1 - flashProgress)
    cinematic.flash.scale.setScalar(1 + flashProgress * 7)
    cinematic.burst.points.material.opacity = Math.max(0, 0.95 - impactAge / 5.4)

    const positions = cinematic.burst.positions
    cinematic.burst.velocities.forEach((velocity, index) => {
      const cursor = index * 3
      positions[cursor] += velocity.x * 0.012
      positions[cursor + 1] += velocity.y * 0.012
      positions[cursor + 2] += velocity.z * 0.012
    })
    cinematic.burst.points.geometry.attributes.position.needsUpdate = true
  }

  const pullbackProgress = smoothstep((ageSeconds - APPROACH_SECONDS - HOLD_SECONDS) / PULLBACK_SECONDS)
  const cameraPosition = cinematic.closeCamera.clone().lerp(cinematic.overviewCamera, pullbackProgress)
  const lookAt = cinematic.position.clone().lerp(new THREE.Vector3(0, 0, 0), pullbackProgress)

  if (ageSeconds >= FINISH_SECONDS) cinematic.finished = true
  return { cameraPosition, lookAt, impactStarted, pullbackProgress, finished: cinematic.finished }
}

export function disposeFirstCollisionCinematic(cinematic) {
  if (!cinematic) return
  cinematic.group.traverse((child) => {
    child.geometry?.dispose?.()
    if (Array.isArray(child.material)) {
      child.material.forEach((material) => material.dispose?.())
    } else {
      child.material?.dispose?.()
    }
  })
}
