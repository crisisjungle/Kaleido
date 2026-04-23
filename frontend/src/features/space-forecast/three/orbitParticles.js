import * as THREE from 'three'
import { seededRandom } from '../core/math'
import { orbitalPosition } from './coordinates'
import { PARTICLE_LIMITS, PARTICLE_STYLE } from './styles'

function sampleCount(rawCount, limit, divisor) {
  return Math.max(8, Math.min(limit, Math.round(rawCount / divisor)))
}

function makeParticle(kind, shell, plane, index, random) {
  const style = PARTICLE_STYLE[kind]
  return {
    id: `${kind}:${shell.id}:${plane.id}:${index}`,
    kind,
    shellId: shell.id,
    planeId: plane.id,
    phase: random() * Math.PI * 2,
    angularVelocity: plane.angularVelocity * (0.82 + random() * 0.36),
    size: style.size,
    color: new THREE.Color(style.color),
    opacity: style.opacity,
    drift: (random() - 0.5) * 0.03,
    alive: true
  }
}

export function createOrbitParticles(shellStates, planes) {
  const particles = []
  const planesByShell = new Map()
  planes.forEach((plane) => {
    if (!planesByShell.has(plane.shellId)) planesByShell.set(plane.shellId, [])
    planesByShell.get(plane.shellId).push(plane)
  })

  shellStates.forEach((shell) => {
    const shellPlanes = planesByShell.get(shell.id) ?? []
    const random = seededRandom(`particles:${shell.id}`)
    const survivingActiveSatellites = shell.survivingActiveSatellites ?? shell.activeSatellites
    const typeCounts = {
      active_satellite: sampleCount(survivingActiveSatellites, PARTICLE_LIMITS.active_satellite, 6),
      derelict_satellite: sampleCount(shell.derelictObjects, PARTICLE_LIMITS.derelict_satellite, 7),
      large_debris: sampleCount(shell.largeDebris, PARTICLE_LIMITS.large_debris, 10),
      medium_debris: sampleCount(shell.mediumDebris, PARTICLE_LIMITS.medium_debris, 90),
      micro_debris: sampleCount(shell.smallDebris, PARTICLE_LIMITS.micro_debris, 1800)
    }

    Object.entries(typeCounts).forEach(([kind, count]) => {
      for (let index = 0; index < count; index += 1) {
        const plane = shellPlanes[index % shellPlanes.length]
        if (plane) particles.push(makeParticle(kind, shell, plane, index, random))
      }
    })
  })

  return particles
}

export function createParticleSystem(particles, planesById, options = {}) {
  const group = new THREE.Group()
  const groupedParticles = new Map()
  const buckets = new Map()
  const excludedKinds = new Set(options.excludedKinds ?? [])

  particles.forEach((particle) => {
    if (excludedKinds.has(particle.kind)) return
    if (!groupedParticles.has(particle.kind)) groupedParticles.set(particle.kind, [])
    groupedParticles.get(particle.kind).push(particle)
  })

  groupedParticles.forEach((bucketParticles, kind) => {
    const style = PARTICLE_STYLE[kind]
    const geometry = new THREE.BufferGeometry()
    const positions = new Float32Array(bucketParticles.length * 3)

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

    const points = new THREE.Points(
      geometry,
      new THREE.PointsMaterial({
        color: style.color,
        size: style.size,
        transparent: true,
        opacity: style.opacity,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true
      })
    )
    points.frustumCulled = false
    points.userData.kind = kind
    group.add(points)
    buckets.set(kind, { particles: bucketParticles, positions, points })
  })

  return { points: group, particles, planesById, buckets }
}

export function updateParticleSystem(system, elapsedSeconds) {
  if (!system?.buckets) return
  const { planesById } = system
  system.buckets.forEach((bucket) => {
    bucket.particles.forEach((particle, index) => {
      const plane = planesById.get(particle.planeId)
      if (!plane) return
      const position = orbitalPosition(
        plane.radius + particle.drift,
        particle.phase + particle.angularVelocity * elapsedSeconds,
        plane.inclinationDeg,
        plane.raanDeg
      )
      bucket.positions[index * 3] = position.x
      bucket.positions[index * 3 + 1] = position.y
      bucket.positions[index * 3 + 2] = position.z
    })
    bucket.points.geometry.attributes.position.needsUpdate = true
  })
}

export function addDebrisParticles(system, shell, planes, count, seed) {
  if (!system || !shell || !planes.length) return
  const random = seededRandom(seed)
  const additions = []
  const cappedCount = Math.min(count, 700)
  for (let index = 0; index < cappedCount; index += 1) {
    const plane = planes[index % planes.length]
    additions.push(makeParticle(index % 3 === 0 ? 'large_debris' : index % 3 === 1 ? 'medium_debris' : 'micro_debris', shell, plane, index, random))
  }
  system.particles.push(...additions)
}
