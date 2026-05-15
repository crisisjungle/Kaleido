import * as THREE from 'three'
import { EARTH_RADIUS, SHELL_VISUAL_SCALE } from './styles'

export function altitudeToRadius(altitudeKm) {
  return EARTH_RADIUS + altitudeKm * SHELL_VISUAL_SCALE
}

export function degToRad(deg) {
  return (deg * Math.PI) / 180
}

export function orbitalPosition(radius, theta, inclinationDeg, raanDeg) {
  const cosTheta = Math.cos(theta)
  const sinTheta = Math.sin(theta)
  const inc = degToRad(inclinationDeg)
  const raan = degToRad(raanDeg)

  const xOrb = radius * cosTheta
  const yOrb = radius * sinTheta
  const zOrb = 0

  const xInc = xOrb
  const yInc = yOrb * Math.cos(inc) - zOrb * Math.sin(inc)
  const zInc = yOrb * Math.sin(inc) + zOrb * Math.cos(inc)

  const x = xInc * Math.cos(raan) - yInc * Math.sin(raan)
  const y = xInc * Math.sin(raan) + yInc * Math.cos(raan)
  const z = zInc

  return new THREE.Vector3(x, z, y)
}

export function radialDirection(position) {
  return position.clone().normalize()
}
