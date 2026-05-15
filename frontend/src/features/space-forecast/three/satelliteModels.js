import * as THREE from 'three'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { orbitalPosition } from './coordinates'

const SATELLITE_KIND = 'active_satellite'
const WRECKAGE_KINDS = new Set(['derelict_satellite', 'large_debris'])
const MAX_DETAIL_SATELLITES = 72
const MAX_WRECKAGE_OBJECTS = 4200

const NASA_FLEET_MODELS = [
  {
    id: 'landsat-8',
    name: 'Landsat 8',
    url: '/models/nasa-satellite-fleet/landsat-8.glb',
    size: 0.22,
    tint: '#e2e8f0'
  },
  {
    id: 'cubesat-icecube',
    name: 'CubeSat ICECube',
    url: '/models/nasa-satellite-fleet/cubesat-icecube.glb',
    size: 0.18,
    tint: '#bfdbfe'
  },
  {
    id: 'cloudsat-b',
    name: 'CloudSat',
    url: '/models/nasa-satellite-fleet/cloudsat-b.glb',
    size: 0.2,
    tint: '#dbeafe'
  },
  {
    id: 'acrimsat-b',
    name: 'AcrimSAT',
    url: '/models/nasa-satellite-fleet/acrimsat-b.glb',
    size: 0.2,
    tint: '#f8fafc'
  },
  {
    id: 'mars-global-surveyor-mapping',
    name: 'Mars Global Surveyor',
    url: '/models/nasa-satellite-fleet/mars-global-surveyor-mapping.glb',
    size: 0.22,
    tint: '#fef3c7'
  }
]

let nasaFleetPromise

function createProxyMaterial(color, emissive = '#0e7490') {
  return new THREE.MeshStandardMaterial({
    color,
    emissive,
    emissiveIntensity: 0.26,
    metalness: 0.36,
    roughness: 0.46,
    side: THREE.DoubleSide
  })
}

function createWreckageMaterial(color, emissive = '#3f3f46') {
  return new THREE.MeshStandardMaterial({
    color,
    emissive,
    emissiveIntensity: 0.16,
    metalness: 0.22,
    roughness: 0.72,
    side: THREE.DoubleSide
  })
}

function prepareGeometryForMerge(sourceGeometry) {
  let geometry = sourceGeometry
  Object.keys(geometry.attributes).forEach((attributeName) => {
    if (attributeName !== 'position' && attributeName !== 'normal') {
      geometry.deleteAttribute(attributeName)
    }
  })
  if (geometry.index) {
    const nonIndexedGeometry = geometry.toNonIndexed()
    geometry.dispose()
    geometry = nonIndexedGeometry
  }
  return geometry
}

function mergedGeometry(geometries) {
  const preparedGeometries = geometries.map((geometry) => prepareGeometryForMerge(geometry))
  const geometry = mergeGeometries(preparedGeometries, false)
  preparedGeometries.forEach((entry) => entry.dispose())
  if (!geometry) return new THREE.BoxGeometry(0.12, 0.08, 0.08)
  geometry.computeVertexNormals()
  geometry.computeBoundingSphere()
  return geometry
}

function createWingedProxyGeometry() {
  const body = new THREE.BoxGeometry(0.34, 0.12, 0.12)
  const leftPanel = new THREE.BoxGeometry(0.38, 0.018, 0.13)
  leftPanel.translate(-0.38, 0, 0)
  const rightPanel = new THREE.BoxGeometry(0.38, 0.018, 0.13)
  rightPanel.translate(0.38, 0, 0)
  const antenna = new THREE.CylinderGeometry(0.006, 0.006, 0.28, 5)
  antenna.translate(0, 0.22, 0)
  return mergedGeometry([body, leftPanel, rightPanel, antenna])
}

function createLongPanelProxyGeometry() {
  const body = new THREE.BoxGeometry(0.18, 0.16, 0.12)
  const panel = new THREE.BoxGeometry(0.86, 0.014, 0.12)
  const mast = new THREE.CylinderGeometry(0.006, 0.006, 0.34, 5)
  mast.rotateZ(Math.PI / 2)
  mast.translate(0, 0.11, 0)
  return mergedGeometry([body, panel, mast])
}

function createCubesatProxyGeometry() {
  const body = new THREE.BoxGeometry(0.2, 0.2, 0.2)
  const sidePanel = new THREE.BoxGeometry(0.28, 0.014, 0.14)
  sidePanel.translate(0.28, 0, 0)
  const topPanel = new THREE.BoxGeometry(0.14, 0.014, 0.28)
  topPanel.translate(-0.2, 0.16, 0)
  const antenna = new THREE.CylinderGeometry(0.005, 0.005, 0.32, 5)
  antenna.translate(0, 0.3, 0)
  return mergedGeometry([body, sidePanel, topPanel, antenna])
}

function createDishProxyGeometry() {
  const body = new THREE.BoxGeometry(0.22, 0.16, 0.14)
  const dish = new THREE.ConeGeometry(0.13, 0.08, 12)
  dish.rotateX(Math.PI / 2)
  dish.translate(0.2, 0.02, 0)
  const boom = new THREE.CylinderGeometry(0.007, 0.007, 0.34, 5)
  boom.rotateZ(Math.PI / 2)
  boom.translate(-0.22, 0, 0)
  return mergedGeometry([body, dish, boom])
}

function createCompactProxyGeometry() {
  const body = new THREE.BoxGeometry(0.26, 0.12, 0.16)
  const top = new THREE.BoxGeometry(0.18, 0.12, 0.08)
  top.translate(0.02, 0.12, 0)
  const panel = new THREE.BoxGeometry(0.48, 0.014, 0.12)
  panel.translate(0, -0.12, 0)
  return mergedGeometry([body, top, panel])
}

function createPanelWreckageGeometry() {
  const panel = new THREE.BoxGeometry(0.42, 0.018, 0.12)
  panel.rotateZ(0.22)
  const bodyShard = new THREE.BoxGeometry(0.14, 0.09, 0.08)
  bodyShard.translate(-0.16, 0.05, 0.02)
  const spar = new THREE.CylinderGeometry(0.006, 0.006, 0.34, 5)
  spar.rotateZ(Math.PI / 2)
  spar.translate(0.12, -0.08, 0)
  return mergedGeometry([panel, bodyShard, spar])
}

function createAngularWreckageGeometry() {
  const shard = new THREE.TetrahedronGeometry(0.17, 0)
  shard.scale(1.45, 0.45, 0.72)
  shard.rotateZ(-0.42)
  const plate = new THREE.BoxGeometry(0.22, 0.018, 0.16)
  plate.rotateY(0.7)
  plate.translate(0.16, 0.04, -0.02)
  return mergedGeometry([shard, plate])
}

function createBusWreckageGeometry() {
  const bus = new THREE.BoxGeometry(0.18, 0.13, 0.12)
  bus.rotateX(0.18)
  const panelA = new THREE.BoxGeometry(0.28, 0.015, 0.09)
  panelA.translate(-0.24, -0.02, 0.04)
  panelA.rotateZ(-0.25)
  const panelB = new THREE.BoxGeometry(0.22, 0.015, 0.08)
  panelB.translate(0.22, 0.08, -0.04)
  panelB.rotateZ(0.45)
  return mergedGeometry([bus, panelA, panelB])
}

function createNeedleWreckageGeometry() {
  const body = new THREE.CylinderGeometry(0.025, 0.045, 0.34, 5)
  body.rotateZ(Math.PI / 2)
  const shard = new THREE.TetrahedronGeometry(0.1, 0)
  shard.translate(0.22, 0.02, 0)
  const rod = new THREE.CylinderGeometry(0.004, 0.004, 0.42, 4)
  rod.rotateZ(1.2)
  rod.translate(-0.1, 0.02, 0.03)
  return mergedGeometry([body, shard, rod])
}

function createProxyVariants() {
  return [
    {
      id: 'proxy-winged',
      name: 'Winged Orbiter',
      size: 0.13,
      parts: [{ geometry: createWingedProxyGeometry(), material: createProxyMaterial('#5eead4') }]
    },
    {
      id: 'proxy-long-panel',
      name: 'Long Panel Satellite',
      size: 0.14,
      parts: [{ geometry: createLongPanelProxyGeometry(), material: createProxyMaterial('#38bdf8') }]
    },
    {
      id: 'proxy-cubesat',
      name: 'CubeSat',
      size: 0.12,
      parts: [{ geometry: createCubesatProxyGeometry(), material: createProxyMaterial('#a7f3d0') }]
    },
    {
      id: 'proxy-dish',
      name: 'Dish Satellite',
      size: 0.13,
      parts: [{ geometry: createDishProxyGeometry(), material: createProxyMaterial('#bae6fd') }]
    },
    {
      id: 'proxy-compact',
      name: 'Compact Bus',
      size: 0.12,
      parts: [{ geometry: createCompactProxyGeometry(), material: createProxyMaterial('#fef08a', '#854d0e') }]
    }
  ]
}

function createWreckageVariants() {
  return [
    {
      id: 'wreckage-panel',
      name: 'Panel Wreckage',
      size: 0.13,
      parts: [{ geometry: createPanelWreckageGeometry(), material: createWreckageMaterial('#e2e8f0', '#64748b') }]
    },
    {
      id: 'wreckage-angular',
      name: 'Angular Fragment',
      size: 0.11,
      parts: [{ geometry: createAngularWreckageGeometry(), material: createWreckageMaterial('#f8fafc', '#475569') }]
    },
    {
      id: 'wreckage-bus',
      name: 'Broken Bus',
      size: 0.12,
      parts: [{ geometry: createBusWreckageGeometry(), material: createWreckageMaterial('#94a3b8', '#334155') }]
    },
    {
      id: 'wreckage-needle',
      name: 'Needle Fragment',
      size: 0.12,
      parts: [{ geometry: createNeedleWreckageGeometry(), material: createWreckageMaterial('#facc15', '#713f12') }]
    }
  ]
}

function createFallbackMaterial(role) {
  if (role === 'panel') {
    return new THREE.MeshStandardMaterial({
      color: '#2563eb',
      emissive: '#082f49',
      emissiveIntensity: 0.18,
      metalness: 0.25,
      roughness: 0.34,
      side: THREE.DoubleSide
    })
  }

  if (role === 'antenna') {
    return new THREE.MeshStandardMaterial({
      color: '#f8fafc',
      metalness: 0.72,
      roughness: 0.28
    })
  }

  return new THREE.MeshStandardMaterial({
    color: '#cbd5e1',
    metalness: 0.55,
    roughness: 0.36
  })
}

function createFallbackModelParts() {
  const body = new THREE.BoxGeometry(0.5, 0.28, 0.28)
  const leftPanel = new THREE.BoxGeometry(0.48, 0.035, 0.22)
  leftPanel.translate(-0.5, 0, 0)
  const rightPanel = new THREE.BoxGeometry(0.48, 0.035, 0.22)
  rightPanel.translate(0.5, 0, 0)
  const antenna = new THREE.CylinderGeometry(0.015, 0.015, 0.36, 8)
  antenna.translate(0, 0.32, 0)

  return [
    { geometry: body, material: createFallbackMaterial('body') },
    { geometry: leftPanel, material: createFallbackMaterial('panel') },
    { geometry: rightPanel, material: createFallbackMaterial('panel') },
    { geometry: antenna, material: createFallbackMaterial('antenna') }
  ]
}

function normalizeParts(parts) {
  const bounds = new THREE.Box3()
  parts.forEach((part) => {
    part.geometry.computeBoundingBox()
    if (part.geometry.boundingBox) bounds.union(part.geometry.boundingBox)
  })

  if (bounds.isEmpty()) return parts

  const center = bounds.getCenter(new THREE.Vector3())
  const size = bounds.getSize(new THREE.Vector3())
  const longestSide = Math.max(size.x, size.y, size.z)
  const scale = longestSide > 0 ? 1 / longestSide : 1

  parts.forEach((part) => {
    part.geometry.translate(-center.x, -center.y, -center.z)
    part.geometry.scale(scale, scale, scale)
    part.geometry.computeBoundingSphere()
  })

  return parts
}

function stableHash(value) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function materialWithModelTreatment(sourceMaterial, definition) {
  const source = Array.isArray(sourceMaterial) ? sourceMaterial.find(Boolean) : sourceMaterial
  const material = new THREE.MeshStandardMaterial({
    color: definition.tint,
    metalness: 0.42,
    roughness: 0.46,
    side: THREE.DoubleSide
  })

  if (source?.color) {
    material.color.copy(source.color).lerp(new THREE.Color(definition.tint), 0.35)
  }
  if (material.emissive) {
    material.emissive.lerp(new THREE.Color('#38bdf8'), 0.16)
    material.emissiveIntensity = Math.max(material.emissiveIntensity ?? 0, 0.12)
  }

  return material
}

function cloneMaterial(material) {
  if (Array.isArray(material)) return material.map((entry) => entry.clone())
  return material.clone()
}

function disposeMaterial(material) {
  if (Array.isArray(material)) {
    material.forEach((entry) => entry.dispose?.())
    return
  }
  material?.dispose?.()
}

async function loadModelVariant(loader, definition) {
  const gltf = await loader.loadAsync(definition.url)
  const geometries = []
  let material

  gltf.scene.updateWorldMatrix(true, true)
  gltf.scene.traverse((child) => {
    if (!child.isMesh || !child.geometry) return

    let geometry = child.geometry.clone()
    geometry.applyMatrix4(child.matrixWorld)
    geometry.clearGroups()
    geometry.computeVertexNormals()
    geometry.computeBoundingSphere()
    Object.keys(geometry.attributes).forEach((attributeName) => {
      if (attributeName !== 'position' && attributeName !== 'normal') {
        geometry.deleteAttribute(attributeName)
      }
    })
    if (geometry.index) {
      const nonIndexedGeometry = geometry.toNonIndexed()
      geometry.dispose()
      geometry = nonIndexedGeometry
    }
    geometries.push(geometry)

    if (!material) material = materialWithModelTreatment(child.material, definition)
  })

  const mergedGeometry = mergeGeometries(geometries, false)
  geometries.forEach((geometry) => geometry.dispose())
  if (!mergedGeometry) return { ...definition, parts: [] }

  return {
    ...definition,
    parts: normalizeParts([{
      geometry: mergedGeometry,
      material: material ?? materialWithModelTreatment(null, definition)
    }])
  }
}

function createFallbackVariant() {
  return {
    id: 'fallback-orbiter',
    name: 'Fallback Orbiter',
    size: 0.13,
    parts: normalizeParts(createFallbackModelParts())
  }
}

async function loadNasaFleetVariants() {
  const dracoLoader = new DRACOLoader()
  dracoLoader.setDecoderPath('/vendor/draco/')
  const loader = new GLTFLoader()
  loader.setDRACOLoader(dracoLoader)
  const results = await Promise.allSettled(
    NASA_FLEET_MODELS.map((definition) => loadModelVariant(loader, definition))
  )
  dracoLoader.dispose()
  const variants = []

  results.forEach((result, index) => {
    if (result.status === 'fulfilled' && result.value.parts.length) {
      variants.push(result.value)
      return
    }
    console.warn(`Unable to load NASA satellite model: ${NASA_FLEET_MODELS[index].name}`, result.reason)
  })

  return variants.length ? variants : [createFallbackVariant()]
}

function getNasaFleetVariants() {
  if (!nasaFleetPromise) {
    nasaFleetPromise = loadNasaFleetVariants().catch((error) => {
      console.warn('Unable to load NASA satellite fleet models; using fallback geometry.', error)
      return [createFallbackVariant()]
    })
  }
  return nasaFleetPromise
}

function disposeMeshes(system, meshes) {
  meshes.forEach((mesh) => {
    system.group.remove(mesh)
    mesh.geometry.dispose()
    disposeMaterial(mesh.material)
  })
}

function clearProxyMeshes(system) {
  disposeMeshes(system, system.proxyMeshes)
  system.proxyMeshes = []
  system.proxyBuckets = []
}

function clearDetailMeshes(system) {
  disposeMeshes(system, system.detailMeshes)
  system.detailMeshes = []
  system.detailBuckets = []
}

function clearWreckageMeshes(system) {
  disposeMeshes(system, system.wreckageMeshes)
  system.wreckageMeshes = []
  system.wreckageBuckets = []
}

function clearMeshes(system) {
  clearProxyMeshes(system)
  clearDetailMeshes(system)
  clearWreckageMeshes(system)
  system.meshes = []
}

function createBuckets(particles, variants) {
  const buckets = variants.map((variant) => ({
    variant,
    instances: [],
    meshes: []
  }))

  particles.forEach((particle) => {
    const bucketIndex = stableHash(particle.id) % variants.length
    buckets[bucketIndex].instances.push({
      particle,
      roll: (stableHash(`${particle.id}:roll`) % 360) * THREE.MathUtils.DEG2RAD,
      sizeJitter: 0.72 + (stableHash(`${particle.id}:size`) % 57) / 100
    })
  })

  return buckets
}

function publishDebugState(system) {
  if (!import.meta.env.DEV || typeof window === 'undefined') return
  window.__envfishSpaceForecastSatellites = {
    proxySatellites: system.proxyParticles.length,
    detailSatellites: system.detailParticles.length,
    meshCount: system.meshes.length,
    wreckageObjects: system.wreckageParticles.length,
    proxyVariants: system.proxyBuckets.map((bucket) => ({
      id: bucket.variant.id,
      name: bucket.variant.name,
      parts: bucket.variant.parts.length,
      instances: bucket.instances.length
    })),
    detailVariants: system.detailBuckets.map((bucket) => {
      return {
        id: bucket.variant.id,
        name: bucket.variant.name,
        parts: bucket.variant.parts.length,
        instances: bucket.instances.length
      }
    }),
    wreckageVariants: system.wreckageBuckets.map((bucket) => ({
      id: bucket.variant.id,
      name: bucket.variant.name,
      parts: bucket.variant.parts.length,
      instances: bucket.instances.length
    }))
  }
}

function createVariantMeshes(system, buckets, meshTarget, layerName) {
  buckets.forEach((bucket) => {
    if (!bucket.instances.length) return

    bucket.variant.parts.forEach((part) => {
      const mesh = new THREE.InstancedMesh(
        part.geometry.clone(),
        cloneMaterial(part.material),
        bucket.instances.length
      )
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
      mesh.frustumCulled = false
      mesh.renderOrder = layerName === 'detail' ? 5 : 4
      mesh.userData.kind = SATELLITE_KIND
      mesh.userData.layer = layerName
      mesh.userData.model = bucket.variant.id
      mesh.userData.modelName = bucket.variant.name
      system.group.add(mesh)
      bucket.meshes.push(mesh)
      meshTarget.push(mesh)
    })
  })
  system.meshes = [...system.proxyMeshes, ...system.detailMeshes, ...system.wreckageMeshes]
}

function disposeVariantSources(variants) {
  variants.forEach((variant) => {
    variant.parts.forEach((part) => {
      part.geometry.dispose()
      disposeMaterial(part.material)
    })
  })
}

function applyProxyVariants(system, variants) {
  clearProxyMeshes(system)
  if (!system.proxyParticles.length) {
    disposeVariantSources(variants)
    return
  }

  system.proxyBuckets = createBuckets(system.proxyParticles, variants)
  createVariantMeshes(system, system.proxyBuckets, system.proxyMeshes, 'proxy')
  disposeVariantSources(variants)
  publishDebugState(system)
}

function applyDetailVariants(system, variants) {
  clearDetailMeshes(system)
  if (!system.detailParticles.length) return

  system.detailBuckets = createBuckets(system.detailParticles, variants)
  createVariantMeshes(system, system.detailBuckets, system.detailMeshes, 'detail')
  publishDebugState(system)
}

function applyWreckageVariants(system, variants) {
  clearWreckageMeshes(system)
  if (!system.wreckageParticles.length) {
    disposeVariantSources(variants)
    return
  }

  system.wreckageBuckets = createBuckets(system.wreckageParticles, variants)
  createVariantMeshes(system, system.wreckageBuckets, system.wreckageMeshes, 'wreckage')
  disposeVariantSources(variants)
  publishDebugState(system)
}

export function createSatelliteModelSystem(particles, planesById) {
  const activeParticles = particles.filter((particle) => particle.kind === SATELLITE_KIND)
  const wreckageParticles = particles
    .filter((particle) => WRECKAGE_KINDS.has(particle.kind))
    .sort((left, right) => stableHash(left.id) - stableHash(right.id))
    .slice(0, MAX_WRECKAGE_OBJECTS)
  const detailParticles = [...activeParticles]
    .sort((left, right) => stableHash(left.id) - stableHash(right.id))
    .slice(0, MAX_DETAIL_SATELLITES)

  const system = {
    group: new THREE.Group(),
    proxyParticles: activeParticles,
    detailParticles,
    wreckageParticles,
    planesById,
    proxyBuckets: [],
    detailBuckets: [],
    wreckageBuckets: [],
    proxyMeshes: [],
    detailMeshes: [],
    wreckageMeshes: [],
    meshes: [],
    disposed: false
  }

  applyProxyVariants(system, createProxyVariants())
  applyWreckageVariants(system, createWreckageVariants())
  getNasaFleetVariants().then((variants) => {
    if (system.disposed) return
    applyDetailVariants(system, variants)
  })

  return system
}

const currentPosition = new THREE.Vector3()
const nextPosition = new THREE.Vector3()
const up = new THREE.Vector3()
const forward = new THREE.Vector3()
const right = new THREE.Vector3()
const correctedForward = new THREE.Vector3()
const basis = new THREE.Matrix4()
const rotation = new THREE.Quaternion()
const rollRotation = new THREE.Quaternion()
const finalRotation = new THREE.Quaternion()
const scale = new THREE.Vector3()
const matrix = new THREE.Matrix4()

function updateSatelliteBuckets(system, buckets, elapsedSeconds) {
  buckets.forEach((bucket) => {
    bucket.instances.forEach((instance, index) => {
      const particle = instance.particle
      const plane = system.planesById.get(particle.planeId)
      if (!plane) return

      const theta = particle.phase + particle.angularVelocity * elapsedSeconds
      currentPosition.copy(orbitalPosition(
        plane.radius + particle.drift,
        theta,
        plane.inclinationDeg,
        plane.raanDeg
      ))
      nextPosition.copy(orbitalPosition(
        plane.radius + particle.drift,
        theta + 0.01,
        plane.inclinationDeg,
        plane.raanDeg
      ))

      up.copy(currentPosition).normalize()
      forward.copy(nextPosition).sub(currentPosition).normalize()
      right.crossVectors(forward, up)
      if (right.lengthSq() < 0.000001) right.set(1, 0, 0)
      right.normalize()
      correctedForward.crossVectors(up, right).normalize()

      basis.makeBasis(right, up, correctedForward)
      rotation.setFromRotationMatrix(basis)
      rollRotation.setFromAxisAngle(up, instance.roll)
      finalRotation.copy(rollRotation).multiply(rotation)
      scale.setScalar(bucket.variant.size * instance.sizeJitter)
      matrix.compose(currentPosition, finalRotation, scale)

      bucket.meshes.forEach((mesh) => mesh.setMatrixAt(index, matrix))
    })

    bucket.meshes.forEach((mesh) => {
      mesh.instanceMatrix.needsUpdate = true
    })
  })
}

export function updateSatelliteModelSystem(system, elapsedSeconds) {
  if (!system) return
  updateSatelliteBuckets(system, system.proxyBuckets ?? [], elapsedSeconds)
  updateSatelliteBuckets(system, system.detailBuckets ?? [], elapsedSeconds)
  updateSatelliteBuckets(system, system.wreckageBuckets ?? [], elapsedSeconds)
}

export function disposeSatelliteModelSystem(system) {
  if (!system) return
  system.disposed = true
  clearMeshes(system)
}
