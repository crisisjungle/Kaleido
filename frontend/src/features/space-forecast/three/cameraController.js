import * as THREE from 'three'

export function applyOverviewCamera(camera) {
  camera.position.set(0, 4.8, 9.5)
  camera.lookAt(0, 0, 0)
}

export function easeCameraTo(camera, targetPosition, lookAt = new THREE.Vector3(0, 0, 0), alpha = 0.04) {
  camera.position.lerp(targetPosition, alpha)
  camera.lookAt(lookAt)
}
