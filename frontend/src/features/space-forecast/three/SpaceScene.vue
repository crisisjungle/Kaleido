<template>
  <div ref="containerRef" class="space-scene"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch, ref } from 'vue'
import * as THREE from 'three'
import { EARTH_RADIUS } from './styles'
import { applyOverviewCamera, easeCameraTo } from './cameraController'
import { buildOrbitPlanes, createOrbitLineGroup } from './orbitPlanes'
import { createOrbitParticles, createParticleSystem, updateParticleSystem } from './orbitParticles'
import { createSatelliteModelSystem, disposeSatelliteModelSystem, updateSatelliteModelSystem } from './satelliteModels'
import { createDebrisShellSystem, disposeDebrisShellSystem, setDebrisShellTargets, updateDebrisShellSystem } from './debrisShell'
import { createCollisionEffect, updateCollisionEffect } from './collisionEffects'
import {
  createFirstCollisionCinematic,
  disposeFirstCollisionCinematic,
  updateFirstCollisionCinematic
} from './firstCollisionCinematic'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls'

const props = defineProps({
  environment: {
    type: Object,
    required: true
  },
  events: {
    type: Array,
    default: () => []
  },
  focusShellId: {
    type: String,
    default: ''
  },
  collisionType: {
    type: String,
    default: 'iridium_like'
  },
  running: {
    type: Boolean,
    default: false
  }
})

const containerRef = ref(null)

let renderer
let scene
let camera
let animationFrame = 0
let resizeObserver
let orbitLineGroup
let particleSystem
let satelliteModelSystem
let debrisShellSystem
let planes = []
let planesById = new Map()
let handledEventIds = new Set()
let effects = []
let startedAt = performance.now()
let cameraTarget = null
let cameraLookAtTarget = new THREE.Vector3(0, 0, 0)
let controls
let introCinematic

const MULTI_COLLISION_OVERVIEW_THRESHOLD = 3
const COLLISION_OVERVIEW_DISTANCE = 13.5
const COLLISION_OVERVIEW_MIN_HEIGHT = 0.58
const COLLISION_CAMERA_NUDGE_MAX_ANGLE = 0.14
const COLLISION_CAMERA_NUDGE_DISTANCE = 12.4
const EARTH_DAY_TEXTURE_URL = '/textures/earth/nasa-svs-clouded-earth-2048.jpg'

function disposeObject(object) {
  object.traverse?.((child) => {
    child.geometry?.dispose?.()
    if (Array.isArray(child.material)) {
      child.material.forEach((material) => material.dispose?.())
    } else {
      child.material?.dispose?.()
    }
  })
}

function planeSignature(nextPlanes) {
  return nextPlanes.map((plane) => `${plane.id}:${plane.radius.toFixed(4)}`).join('|')
}

function setCameraTarget(position, lookAt = new THREE.Vector3(0, 0, 0)) {
  cameraTarget = position.clone()
  cameraLookAtTarget = lookAt.clone()
}

function setSimulationLayerVisibility(visible) {
  if (orbitLineGroup) orbitLineGroup.visible = visible
  if (particleSystem?.points) particleSystem.points.visible = visible
  if (satelliteModelSystem?.group) satelliteModelSystem.group.visible = visible
  if (debrisShellSystem?.group) debrisShellSystem.group.visible = visible
}

let earthMesh
let cloudMesh

function createEarth() {
  const loader = new THREE.TextureLoader()
  loader.setCrossOrigin('anonymous')
  const dayTexture = loader.load(EARTH_DAY_TEXTURE_URL)
  dayTexture.colorSpace = THREE.SRGBColorSpace
  dayTexture.anisotropy = Math.min(8, renderer?.capabilities?.getMaxAnisotropy?.() || 1)
  
  const geometry = new THREE.SphereGeometry(EARTH_RADIUS, 64, 64)
  const material = new THREE.MeshStandardMaterial({
    map: dayTexture,
    roughness: 0.6,
    metalness: 0.1
  })
  
  earthMesh = new THREE.Mesh(geometry, material)
  earthMesh.name = 'earth'
  scene.add(earthMesh)

  // Subtle Glow
  const glow = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS * 1.02, 64, 64),
    new THREE.MeshBasicMaterial({
      color: '#7dd3fc',
      transparent: true,
      opacity: 0.1,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false
    })
  )
  scene.add(glow)
}

function createStars() {
  const geometry = new THREE.BufferGeometry()
  const count = 1500 // Increased density for deeper feel
  const positions = new Float32Array(count * 3)
  for (let index = 0; index < count; index += 1) {
    const radius = 25 + Math.random() * 25
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(Math.random() * 2 - 1)
    positions[index * 3] = radius * Math.sin(phi) * Math.cos(theta)
    positions[index * 3 + 1] = radius * Math.cos(phi)
    positions[index * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta)
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const stars = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({
      color: '#ffffff',
      size: 0.02,
      transparent: true,
      opacity: 0.6,
      depthWrite: false
    })
  )
  scene.add(stars)
}

function rebuildEnvironment() {
  if (!scene || !props.environment) return
  if (orbitLineGroup) {
    scene.remove(orbitLineGroup)
    disposeObject(orbitLineGroup)
  }
  if (particleSystem?.points) {
    scene.remove(particleSystem.points)
    disposeObject(particleSystem.points)
  }
  if (satelliteModelSystem?.group) {
    scene.remove(satelliteModelSystem.group)
    disposeSatelliteModelSystem(satelliteModelSystem)
  }
  planes = buildOrbitPlanes(props.environment.shellStates)
  planesById = new Map(planes.map((plane) => [plane.id, plane]))
  orbitLineGroup = createOrbitLineGroup(planes, props.focusShellId)
  const particles = createInitialParticles()
  particleSystem = createParticleSystem(particles, planesById, {
    excludedKinds: ['active_satellite', 'derelict_satellite', 'large_debris']
  })
  satelliteModelSystem = createSatelliteModelSystem(particles, planesById)

  const nextDebrisSignature = planeSignature(planes)
  if (debrisShellSystem?.signature !== nextDebrisSignature) {
    if (debrisShellSystem?.group) {
      scene.remove(debrisShellSystem.group)
      disposeDebrisShellSystem(debrisShellSystem)
    }
    debrisShellSystem = createDebrisShellSystem(props.environment.shellStates, planes)
  } else {
    setDebrisShellTargets(debrisShellSystem, props.environment.shellStates, { immediate: !props.running })
  }

  scene.add(orbitLineGroup)
  scene.add(debrisShellSystem.group)
  scene.add(particleSystem.points)
  scene.add(satelliteModelSystem.group)
}

function createInitialParticles() {
  return createOrbitParticles(props.environment.shellStates, planes)
}

function handleNewEvents(events) {
  if (!scene || !planes.length) return

  const newCollisionEvents = events.filter((event) => {
    if (handledEventIds.has(event.id)) return false
    return event.type === 'initial_collision' || event.type === 'cascade_collision'
  })

  const newCollisionCount = newCollisionEvents.reduce(
    (sum, event) => sum + Math.max(1, event.eventCount || 1),
    0
  )
  const useOverviewCamera = newCollisionCount >= MULTI_COLLISION_OVERVIEW_THRESHOLD
  if (useOverviewCamera && !introCinematic) setCollisionOverviewCameraTarget()

  newCollisionEvents.forEach((event) => {
    const shell = props.environment.shellStates.find((entry) => entry.id === event.shellId)
    const shellPlanes = planes.filter((plane) => plane.shellId === event.shellId)
    const plane = shellPlanes[0] ?? planes[0]
    if (!shell || !plane) return

    handledEventIds.add(event.id)

    if (event.type === 'initial_collision' && !introCinematic) {
      startFirstCollisionCinematic(event, shell, plane)
      triggerAggregateEffects(event, shell, shellPlanes.length ? shellPlanes : [plane], 3600)
      return
    }

    addCollisionEffect(event, shell, plane, 0, useOverviewCamera || introCinematic ? 'none' : 'focus')
    triggerAggregateEffects(event, shell, shellPlanes.length ? shellPlanes : [plane])
  })
}

function setCollisionOverviewCameraTarget() {
  if (!camera) return
  const direction = camera.position.clone()
  if (direction.lengthSq() < 0.000001) direction.set(0, 0.6, 1)
  direction.normalize()
  direction.y = Math.max(direction.y, COLLISION_OVERVIEW_MIN_HEIGHT)
  direction.normalize()
  setCameraTarget(direction.multiplyScalar(COLLISION_OVERVIEW_DISTANCE))
}

function setCollisionNudgeCameraTarget(position) {
  if (!camera) return
  const currentDirection = camera.position.clone()
  if (currentDirection.lengthSq() < 0.000001) currentDirection.set(0, 0.6, 1)
  currentDirection.normalize()

  const collisionDirection = position.clone().normalize()
  const angle = currentDirection.angleTo(collisionDirection)
  const blend = angle > 0 ? Math.min(1, COLLISION_CAMERA_NUDGE_MAX_ANGLE / angle) : 0
  const direction = currentDirection.lerp(collisionDirection, blend).normalize()
  direction.y = Math.max(direction.y, 0.32)
  direction.normalize()
  setCameraTarget(direction.multiplyScalar(COLLISION_CAMERA_NUDGE_DISTANCE))
}

function startFirstCollisionCinematic(event, shell, plane) {
  if (!scene) return
  introCinematic = createFirstCollisionCinematic(event, plane)
  scene.add(introCinematic.group)
  setCameraTarget(introCinematic.closeCamera, introCinematic.position)
}

function clearIntroCinematic() {
  if (!introCinematic) return
  scene?.remove(introCinematic.group)
  disposeFirstCollisionCinematic(introCinematic)
  introCinematic = null
}

function addCollisionEffect(event, shell, plane, offsetScale = 0, cameraBehavior = 'focus', options = {}) {
  if (!scene) return
  const effect = createCollisionEffect(event, shell, plane, event.collisionTypeId || props.collisionType, options)
  if (offsetScale > 0) {
    effect.group.position.add(
      new THREE.Vector3(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).multiplyScalar(offsetScale)
    )
  }
  effects.push(effect)
  scene.add(effect.group)
  if (cameraBehavior === 'focus') {
    setCollisionNudgeCameraTarget(effect.group.position)
  }
}

function triggerAggregateEffects(event, shell, shellPlanes, delayOffset = 0) {
  const count = Math.min(Math.max((event.eventCount || 1) - 1, 0), 6)
  for (let i = 0; i < count; i++) {
    setTimeout(() => {
      if (!scene || !props.events.some((entry) => entry.id === event.id)) return
      const plane = shellPlanes[Math.floor(Math.random() * shellPlanes.length)] ?? shellPlanes[0]
      const subEvent = {
        ...event,
        id: `${event.id}-sub-${i}`,
        collisionTypeId: 'small'
      }
      addCollisionEffect(subEvent, shell, plane, 0.4, 'none')
    }, delayOffset + 400 + Math.random() * 1200)
  }
}

function updateFocus() {
  if (!orbitLineGroup) return
  orbitLineGroup.children.forEach((line) => {
    const focused = props.focusShellId && line.userData.shellId === props.focusShellId
    line.material.opacity = focused ? 0.58 : 0.16
    line.material.color.set(focused ? '#67e8f9' : '#1e293b')
  })
}

function animate() {
  const elapsed = (performance.now() - startedAt) / 1000
  updateParticleSystem(particleSystem, elapsed)
  updateSatelliteModelSystem(satelliteModelSystem, elapsed)
  updateDebrisShellSystem(debrisShellSystem, elapsed)

  if (earthMesh) earthMesh.rotation.y += 0.0002

  const now = performance.now()
  const cinematicUpdate = updateFirstCollisionCinematic(introCinematic, now)
  if (cinematicUpdate) {
    setCameraTarget(cinematicUpdate.cameraPosition, cinematicUpdate.lookAt)
    setSimulationLayerVisibility(cinematicUpdate.pullbackProgress > 0.12)
    if (cinematicUpdate.impactStarted) {
      const impactEvent = {
        ...introCinematic.event,
        id: `${introCinematic.event.id}-cinematic-impact`
      }
      addCollisionEffect(impactEvent, props.environment.shellStates.find((entry) => entry.id === introCinematic.event.shellId), planes[0], 0, 'none', {
        position: introCinematic.position,
        scale: 1.45,
        particleMultiplier: 1.35
      })
    }
    if (cinematicUpdate.finished) {
      clearIntroCinematic()
      setSimulationLayerVisibility(true)
      setCollisionOverviewCameraTarget()
    }
  }

  effects.forEach((effect) => updateCollisionEffect(effect, now))
  effects = effects.filter((effect) => {
    if (!effect.finished) return true
    scene.remove(effect.group)
    disposeObject(effect.group)
    return false
  })

  if (cameraTarget) {
    easeCameraTo(camera, cameraTarget, cameraLookAtTarget, introCinematic ? 0.07 : 0.025)
    if (controls) controls.target.copy(cameraLookAtTarget)
  }

  if (controls) controls.update()

  renderer.render(scene, camera)
  animationFrame = requestAnimationFrame(animate)
}

function resize() {
  if (!containerRef.value || !renderer || !camera) return
  const rect = containerRef.value.getBoundingClientRect()
  renderer.setSize(rect.width, rect.height, false)
  camera.aspect = rect.width / Math.max(1, rect.height)
  camera.updateProjectionMatrix()
}

onMounted(() => {
  scene = new THREE.Scene()
  scene.background = new THREE.Color('#020617')
  camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000)
  applyOverviewCamera(camera)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.25 // Brighten up the scene cinematic-style
  containerRef.value.appendChild(renderer.domElement)

  scene.add(new THREE.AmbientLight('#bfe7ff', 0.45))
  const keyLight = new THREE.DirectionalLight('#ffffff', 3.5)
  keyLight.position.set(5, 8, 9)
  scene.add(keyLight)

  // Rim Light for atmospheric scattering effect
  const rimLight = new THREE.PointLight('#7dd3fc', 1.0)
  rimLight.position.set(-5, -5, -5)
  scene.add(rimLight)

  createStars()
  createEarth()
  rebuildEnvironment()
  handleNewEvents(props.events)
  resize()

  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(containerRef.value)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05
  controls.rotateSpeed = 0.6
  controls.minDistance = 5
  controls.maxDistance = 25
  controls.target.set(0, 0, 0)

  animate()
})

watch(
  () => props.environment,
  () => {
    rebuildEnvironment()
    updateFocus()
  },
  { deep: false }
)

watch(
  () => props.events,
  (events) => {
    if (!events.length) {
      handledEventIds = new Set()
      effects.forEach((effect) => {
        scene?.remove(effect.group)
        disposeObject(effect.group)
      })
      effects = []
      cameraTarget = null
      cameraLookAtTarget.set(0, 0, 0)
      clearIntroCinematic()
      setSimulationLayerVisibility(true)
      if (camera) applyOverviewCamera(camera)
      return
    }
    handleNewEvents(events)
  },
  { deep: true }
)

watch(
  () => props.focusShellId,
  updateFocus
)

onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame)
  resizeObserver?.disconnect()
  if (scene) {
    clearIntroCinematic()
    if (satelliteModelSystem) disposeSatelliteModelSystem(satelliteModelSystem)
    if (debrisShellSystem) disposeDebrisShellSystem(debrisShellSystem)
    disposeObject(scene)
  }
  renderer?.dispose()
  renderer?.domElement?.remove()
  controls?.dispose()
})
</script>

<style scoped>
.space-scene {
  width: 100%;
  height: 100%;
  min-height: 520px;
  background: #020617;
  overflow: hidden;
}

.space-scene :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
