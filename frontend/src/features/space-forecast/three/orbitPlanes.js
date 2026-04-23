import * as THREE from 'three'
import { seededRandom } from '../core/math'
import { altitudeToRadius, orbitalPosition } from './coordinates'

const PLANE_COUNTS = {
  '300-500': 8,
  '500-600': 12,
  '600-700': 14,
  '700-900': 18,
  '900-1200': 12,
  '1200-1400': 8
}

const INCLINATIONS = [53, 70, 82, 97.4, 98.6]

export function buildOrbitPlanes(shellStates) {
  const planes = []
  shellStates.forEach((shell, shellIndex) => {
    const count = PLANE_COUNTS[shell.id] ?? 8
    const random = seededRandom(`planes:${shell.id}`)
    const altitudeKm = (shell.altitudeMinKm + shell.altitudeMaxKm) / 2
    for (let index = 0; index < count; index += 1) {
      planes.push({
        id: `${shell.id}-plane-${index}`,
        shellId: shell.id,
        shellLabel: shell.label,
        altitudeKm,
        radius: altitudeToRadius(altitudeKm + (random() - 0.5) * 40),
        inclinationDeg: INCLINATIONS[(index + shellIndex) % INCLINATIONS.length] + (random() - 0.5) * 4,
        raanDeg: (index / count) * 360 + random() * 10,
        phaseOffsetRad: random() * Math.PI * 2,
        angularVelocity: 0.04 + random() * 0.035 + shellIndex * 0.002
      })
    }
  })
  return planes
}

export function createOrbitLineGroup(planes, focusShellId = '') {
  const group = new THREE.Group()
  group.name = 'orbit-line-group'

  planes.forEach((plane, index) => {
    const points = []
    const segmentCount = 160
    for (let segment = 0; segment <= segmentCount; segment += 1) {
      const theta = (segment / segmentCount) * Math.PI * 2
      points.push(orbitalPosition(plane.radius, theta, plane.inclinationDeg, plane.raanDeg))
    }

    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    const isFocused = focusShellId && plane.shellId === focusShellId
    const material = new THREE.LineBasicMaterial({
      color: isFocused ? '#67e8f9' : index % 3 === 0 ? '#155e75' : '#1e293b',
      transparent: true,
      opacity: isFocused ? 0.55 : 0.16,
      blending: THREE.AdditiveBlending
    })
    const line = new THREE.Line(geometry, material)
    line.userData.shellId = plane.shellId
    group.add(line)
  })

  return group
}
