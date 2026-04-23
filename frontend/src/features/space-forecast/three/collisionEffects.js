import * as THREE from 'three'
import { seededRandom } from '../core/math'
import { orbitalPosition, radialDirection } from './coordinates'
import { COLLISION_VISUAL_PRESET } from './styles'

function createCircleTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 64
  canvas.height = 64
  const context = canvas.getContext('2d')
  if (!context) return null

  const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32)
  gradient.addColorStop(0, 'rgba(255, 255, 255, 1)')
  gradient.addColorStop(0.2, 'rgba(255, 255, 255, 0.8)')
  gradient.addColorStop(0.5, 'rgba(255, 255, 255, 0.2)')
  gradient.addColorStop(1, 'rgba(255, 255, 255, 0)')

  context.fillStyle = gradient
  context.fillRect(0, 0, 64, 64)

  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true
  return texture
}

const particleTexture = createCircleTexture()

export function createCollisionSite(event, plane) {
  const random = seededRandom(`collision:${event.id}`)
  const viewDirection = new THREE.Vector3(0, 0.46, 0.9).normalize()
  let position = orbitalPosition(plane.radius, random() * Math.PI * 2, plane.inclinationDeg, plane.raanDeg)
  let bestScore = position.clone().normalize().dot(viewDirection)

  for (let sample = 0; sample < 28; sample += 1) {
    const candidate = orbitalPosition(
      plane.radius,
      (sample / 28) * Math.PI * 2 + random() * 0.08,
      plane.inclinationDeg,
      plane.raanDeg
    )
    const score = candidate.clone().normalize().dot(viewDirection)
    if (score > bestScore) {
      bestScore = score
      position = candidate
    }
  }

  const direction = radialDirection(position)
  return { position, direction }
}

export function createCollisionEffect(event, shell, plane, collisionType, options = {}) {
  const preset = COLLISION_VISUAL_PRESET[collisionType] ?? COLLISION_VISUAL_PRESET.iridium_like
  const random = seededRandom(`collision:${event.id}`)
  const { position, direction } = options.position
    ? { position: options.position.clone(), direction: radialDirection(options.position) }
    : createCollisionSite(event, plane)
  const group = new THREE.Group()
  group.name = `collision-effect-${event.id}`
  group.position.copy(position)

  const flash = new THREE.Mesh(
    new THREE.SphereGeometry(preset.flashRadius, 24, 16),
    new THREE.MeshBasicMaterial({
      color: '#fff7ad',
      transparent: true,
      opacity: 1,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false
    })
  )
  flash.renderOrder = 30
  group.add(flash)

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.005, 0.012, 96),
    new THREE.MeshBasicMaterial({
      color: '#fb923c',
      transparent: true,
      opacity: 0.72,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false
    })
  )
  ring.lookAt(position.clone().add(direction))
  ring.renderOrder = 29
  group.add(ring)

  const burstCount = Math.round(preset.burstParticles * (options.particleMultiplier || 1))
  const geometry = new THREE.BufferGeometry()
  const positions = new Float32Array(burstCount * 3)
  const velocities = []
  const colors = new Float32Array(burstCount * 3)

  for (let index = 0; index < burstCount; index += 1) {
    const spread = new THREE.Vector3(random() - 0.5, random() - 0.5, random() - 0.5).normalize()
    spread.add(direction.clone().multiplyScalar(1.2)).normalize()
    velocities.push(spread.multiplyScalar(0.005 + random() * 0.025))
    colors[index * 3] = 1
      colors[index * 3 + 1] = 0.45 + random() * 0.35
    colors[index * 3 + 2] = 0.08
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const material = new THREE.PointsMaterial({
    size: 0.022,
    map: particleTexture,
    vertexColors: true,
    transparent: true,
    opacity: 0.9,
    depthTest: false,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    sizeAttenuation: true
  })
  const burst = new THREE.Points(geometry, material)
  burst.renderOrder = 31
  group.add(burst)

  return {
    id: event.id,
    shellId: event.shellId,
    group,
    flash,
    ring,
    burst,
    positions,
    velocities,
    maxShockwaveRadius: preset.shockwaveRadius * (options.scale || 1),
    startedAt: performance.now(),
    finished: false,
    shell
  }
}

export function updateCollisionEffect(effect, now) {
  const ageSeconds = (now - effect.startedAt) / 1000
  const flashOpacity = Math.max(0, 1 - ageSeconds / 1.8)
  effect.flash.material.opacity = flashOpacity
  effect.flash.scale.setScalar(1 + Math.pow(ageSeconds * 1.5, 0.6))

  const ringScale = Math.min(effect.maxShockwaveRadius, 0.05 + ageSeconds * 0.45)
  effect.ring.scale.setScalar(ringScale)
  effect.ring.material.opacity = Math.max(0, 0.72 - ageSeconds / 3.2)

  for (let index = 0; index < effect.velocities.length; index += 1) {
    effect.positions[index * 3] += effect.velocities[index].x
    effect.positions[index * 3 + 1] += effect.velocities[index].y
    effect.positions[index * 3 + 2] += effect.velocities[index].z
  }
  effect.burst.geometry.attributes.position.needsUpdate = true
  effect.burst.material.opacity = Math.max(0, 0.9 - ageSeconds / 6)

  if (ageSeconds > 6) {
    effect.finished = true
  }
}
