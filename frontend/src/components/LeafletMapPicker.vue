<template>
  <div class="leaflet-map-shell">
    <div ref="mapEl" class="leaflet-map-picker"></div>
    <transition name="map-overlay-fade">
      <div v-if="showMapOverlay" class="map-loading-overlay" :class="`is-${mapVisualState}`">
        <div class="map-loading-card">
          <div class="map-loading-pulse" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div class="map-loading-title">{{ mapOverlayTitle }}</div>
          <div class="map-loading-subtitle">{{ mapOverlaySubtitle }}</div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps({
  center: {
    type: Array,
    default: () => [20, 0]
  },
  zoom: {
    type: Number,
    default: 2
  },
  selectedPoint: {
    type: Object,
    default: null
  },
  radiusMeters: {
    type: Number,
    default: 5000
  },
  layers: {
    type: Array,
    default: () => []
  },
  readOnly: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['pick', 'ready'])

const mapEl = ref(null)
const mapVisualState = ref('loading')
let map = null
let baseTileLayer = null
let overlayGroup = null
let selectionGroup = null
let mapClickHandler = null
let resizeHandler = null
let containerResizeObserver = null
let parentResizeObserver = null
let resizeFrame = null
let fitFrame = null
let readyTimer = null
let fallbackTimer = null
let lastLayersSignature = ''
let loadedTileCount = 0

const CATEGORY_LABELS = {
  ecology: '生态对象',
  facility: '基础设施',
  human_proxy: '人类活动代理',
  region: '区域'
}

const SOURCE_KIND_LABELS = {
  detected: '遥感识别',
  observed: '地图观测',
  inferred: '推断生成'
}

const NODE_FAMILY_LABELS = {
  EcologicalReceptor: '生态受体',
  EnvironmentalCarrier: '环境载体',
  Infrastructure: '基础设施',
  Region: '区域',
  HumanActor: '人类主体',
  GovernmentActor: '治理主体',
  OrganizationActor: '组织主体'
}

const WORLDCOVER_LABELS = {
  worldcover_10: '树木覆盖',
  worldcover_20: '灌丛',
  worldcover_30: '草地',
  worldcover_40: '农田',
  worldcover_50: '建成区',
  worldcover_60: '裸地/稀疏植被',
  worldcover_70: '雪冰',
  worldcover_80: '永久水体',
  worldcover_90: '草本湿地',
  worldcover_95: '红树林',
  worldcover_100: '苔藓/地衣'
}

const SUBTYPE_LABELS = {
  weather_baseline: '局地天气基线',
  road_corridor: '道路廊道',
  transit_stop: '交通站点',
  rail_station: '轨道站点',
  protected_area: '保护区域',
  commercial_hub: '商业枢纽',
  office_cluster: '办公聚集区',
  power_plant: '电力设施',
  water: '水体',
  wetland: '湿地',
  wood: '林地',
  beach: '海滩',
  grassland: '草地',
  scrub: '灌丛',
  heath: '荒草地',
  sand: '沙地',
  coastline: '海岸线',
  breakwater: '防波堤',
  groyne: '丁坝',
  river: '河流',
  stream: '溪流',
  canal: '运河',
  ditch: '沟渠',
  industrial: '工业用地',
  commercial: '商业用地',
  residential: '居住用地',
  retail: '零售用地',
  farmland: '农田',
  forest: '森林',
  reservoir: '水库',
  meadow: '草甸',
  basin: '蓄水池',
  farmyard: '农场院落',
  park: '公园',
  nature_reserve: '自然保护地',
  garden: '花园绿地',
  tourism: '旅游设施',
  pier: '码头',
  airport: '机场',
  aerodrome: '机场/飞行场地',
  apron: '停机坪',
  taxiway: '滑行道',
  runway: '跑道',
  terminal: '航站楼',
  gate: '登机口',
  hangar: '机库',
  helipad: '直升机停机坪',
  highway: '公路/道路',
  road: '道路',
  path: '小路',
  track: '田间路/林道',
  building: '建筑',
  house: '房屋',
  apartments: '公寓',
  'scrub patch': '灌丛斑块',
  'river segment': '河流河段',
  'residential area': '居住区',
  'industrial area': '工业区',
  'commercial building': '商业建筑',
  'coastal edge': '海岸线',
  'water patch': '水体斑块',
  'wood patch': '林地斑块',
  'grass patch': '草地斑块',
  'nature reserve': '自然保护区'
}

const showMapOverlay = computed(() => mapVisualState.value !== 'ready')

const mapOverlayTitle = computed(() => {
  if (mapVisualState.value === 'degraded') return '底图连接较慢'
  return '地图基底载入中'
})

const mapOverlaySubtitle = computed(() => {
  if (mapVisualState.value === 'degraded') {
    return '底图还在补齐，先展示关键节点、路径和风险热点。'
  }
  return '正在对齐区域骨架、交通脉络和关键点位。'
})

const escapeHtml = (value) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const toDisplayLabel = (value) => {
  const text = String(value ?? '').trim()
  if (!text) return ''

  // Attempt case-insensitive lookup
  const key = text.toLowerCase()
  const match = WORLDCOVER_LABELS[key]
    || SUBTYPE_LABELS[key]
    || NODE_FAMILY_LABELS[key]
    || CATEGORY_LABELS[key]
    || SOURCE_KIND_LABELS[key]
    || WORLDCOVER_LABELS[text]
    || SUBTYPE_LABELS[text]
    || NODE_FAMILY_LABELS[text]
    || CATEGORY_LABELS[text]
    || SOURCE_KIND_LABELS[text]

  if (match) return match

  // Specific common patterns
  if (key === 'coastal edge') return '海岸线'
  if (key === 'river segment') return '河流河段'

  return text
}

const formatConfidence = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return ''
  return `${Math.round(num * 100)}%`
}

const distanceMeters = (lat1, lon1, lat2, lon2) => {
  const radius = 6371000
  const toRad = (value) => Number(value) * Math.PI / 180
  const phi1 = toRad(lat1)
  const phi2 = toRad(lat2)
  const deltaPhi = toRad(Number(lat2) - Number(lat1))
  const deltaLambda = toRad(Number(lon2) - Number(lon1))
  const a = Math.sin(deltaPhi / 2) ** 2
    + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2
  return 2 * radius * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(1e-12, 1 - a)))
}

const isPointWithinSelectedRadius = (lat, lon) => {
  if (!props.selectedPoint) return true
  const centerLat = Number(props.selectedPoint.lat)
  const centerLon = Number(props.selectedPoint.lon)
  const radius = Math.max(Number(props.radiusMeters) || 0, 200)
  if (!Number.isFinite(centerLat) || !Number.isFinite(centerLon)) return true
  return distanceMeters(centerLat, centerLon, lat, lon) <= radius + Math.max(150, Math.min(500, radius * 0.03))
}

const buildPopupHtml = ({ title = '', subtitle = '', summary = '', fields = [] } = {}) => {
  const safeFields = Array.isArray(fields)
    ? fields.filter((item) => item && item.value !== undefined && item.value !== null && String(item.value).trim())
    : []
  if (!title && !subtitle && !summary && safeFields.length === 0) return ''

  const fieldsHtml = safeFields.length
    ? `<div class="map-popup-fields">${safeFields
        .map((item) => `<div class="map-popup-row"><span>${escapeHtml(item.label || '')}</span><strong>${escapeHtml(item.value)}</strong></div>`)
        .join('')}</div>`
    : ''

  return `
    <div class="map-popup">
      ${title ? `<div class="map-popup-title">${escapeHtml(title)}</div>` : ''}
      ${subtitle ? `<div class="map-popup-subtitle">${escapeHtml(subtitle)}</div>` : ''}
      ${summary ? `<div class="map-popup-summary">${escapeHtml(summary)}</div>` : ''}
      ${fieldsHtml}
    </div>
  `
}

const buildPointPopup = (point, layer) => {
  const meta = point?.popupMeta || {}
  const objectType = toDisplayLabel(meta.nodeLabel || meta.featureCategory)
  const sourceKind = toDisplayLabel(meta.featureSourceKind)
  const subtype = toDisplayLabel(meta.featureSubtype)
  const confidence = formatConfidence(meta.nodeConfidence)
  const isRemoteSensingPoint = meta.featureSourceKind === 'detected'

  let summary = point?.popupSummary || ''
  if (!summary) {
    if (isRemoteSensingPoint && subtype) {
      summary = `这是地图分析中识别出的“${subtype}”节点。`
    } else if (sourceKind && subtype) {
      summary = `这是一个${sourceKind}得到的“${subtype}”点位。`
    } else if (subtype) {
      summary = `这是一个“${subtype}”相关点位。`
    } else if (layer?.note) {
      summary = layer.note
    }
  }

  return buildPopupHtml({
    title: toDisplayLabel(point?.popupTitle || point?.label || layer?.name || '节点'),
    subtitle: toDisplayLabel(point?.popupSubtitle || (isRemoteSensingPoint ? '遥感识别节点' : (sourceKind ? `${sourceKind}点位` : (layer?.name || '')))),
    summary,
    fields: [
      objectType ? { label: '对象类型', value: objectType } : null,
      subtype && subtype !== objectType ? { label: '识别结果', value: subtype } : null,
      sourceKind ? { label: '数据来源', value: sourceKind } : null,
      confidence ? { label: '可信度', value: confidence } : null
    ].filter(Boolean)
  })
}

const buildFeaturePopup = (feature, layer) => {
  const properties = feature?.properties || {}
  const coverType = toDisplayLabel(properties?.class_name || properties?.class_name_zh)
  const share = properties?.pixel_share_pct !== undefined && properties?.pixel_share_pct !== null
    ? `${properties.pixel_share_pct}%`
    : ''
  const isRemoteSensingLayer = Boolean(coverType) || String(layer?.id || '').startsWith('worldcover_')
  const summary = isRemoteSensingLayer
    ? (coverType ? `这块区域以“${coverType}”为主。` : '这是地图分析中识别出的一个覆盖斑块。')
    : (properties?.summary || layer?.note || '')

  return buildPopupHtml({
    title: toDisplayLabel(properties?.name || layer?.name || '区域'),
    subtitle: toDisplayLabel(isRemoteSensingLayer ? '遥感识别区域' : (layer?.name || '')),
    summary,
    fields: [
      coverType ? { label: '覆盖类型', value: coverType } : null,
      share ? { label: '估计占比', value: share } : null,
      isRemoteSensingLayer ? { label: '数据来源', value: '卫星土地覆盖识别' } : null
    ].filter(Boolean)
  })
}

const syncMapClickMode = () => {
  if (!map) return
  if (mapClickHandler) {
    map.off('click', mapClickHandler)
    mapClickHandler = null
  }
  if (props.readOnly) return

  mapClickHandler = (event) => {
    emit('pick', {
      lat: Number(event.latlng.lat.toFixed(6)),
      lon: Number(event.latlng.lng.toFixed(6))
    })
  }
  map.on('click', mapClickHandler)
}

const scheduleInvalidateSize = () => {
  if (!map || resizeFrame !== null) return
  resizeFrame = requestAnimationFrame(() => {
    resizeFrame = null
    if (map) {
      map.invalidateSize({ animate: false, pan: false })
    }
  })
}

const clearMapTimers = () => {
  if (readyTimer !== null) {
    window.clearTimeout(readyTimer)
    readyTimer = null
  }
  if (fallbackTimer !== null) {
    window.clearTimeout(fallbackTimer)
    fallbackTimer = null
  }
}

const scheduleMapReady = (delay = 180) => {
  if (mapVisualState.value === 'ready') return
  if (readyTimer !== null) {
    window.clearTimeout(readyTimer)
  }
  readyTimer = window.setTimeout(() => {
    mapVisualState.value = 'ready'
    readyTimer = null
  }, delay)
}

const bindBaseTileEvents = (tileLayer) => {
  if (!tileLayer) return
  tileLayer.on('loading', () => {
    if (loadedTileCount === 0 && mapVisualState.value !== 'ready') {
      mapVisualState.value = 'loading'
    }
  })
  tileLayer.on('tileloadstart', () => {
    if (loadedTileCount === 0 && mapVisualState.value !== 'ready') {
      mapVisualState.value = 'loading'
    }
  })
  tileLayer.on('tileload', () => {
    loadedTileCount += 1
    scheduleMapReady(loadedTileCount > 4 ? 120 : 180)
  })
  tileLayer.on('load', () => {
    scheduleMapReady(90)
  })
  tileLayer.on('tileerror', () => {
    if (loadedTileCount === 0 && mapVisualState.value !== 'ready') {
      mapVisualState.value = 'degraded'
    }
  })
}

const scheduleFitToContent = () => {
  if (!map || fitFrame !== null) return
  fitFrame = requestAnimationFrame(() => {
    fitFrame = null
    if (!map) return

    const layers = [
      ...(overlayGroup?.getLayers?.() || []),
      ...(selectionGroup?.getLayers?.() || [])
    ]
    if (!layers.length) return

    const bounds = L.featureGroup(layers).getBounds()
    if (!bounds.isValid()) return

    map.fitBounds(bounds.pad(0.08), {
      animate: false,
      padding: [28, 28],
      maxZoom: 13
    })
  })
}

const createMap = () => {
  if (!mapEl.value || map) return

  loadedTileCount = 0
  mapVisualState.value = 'loading'
  clearMapTimers()
  fallbackTimer = window.setTimeout(() => {
    if (loadedTileCount === 0 && mapVisualState.value !== 'ready') {
      mapVisualState.value = 'degraded'
    }
  }, 2200)

  map = L.map(mapEl.value, {
    zoomControl: true,
    preferCanvas: true
  }).setView(props.center, props.zoom)

  baseTileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  })
  bindBaseTileEvents(baseTileLayer)
  baseTileLayer.addTo(map)

  overlayGroup = L.layerGroup().addTo(map)
  selectionGroup = L.layerGroup().addTo(map)
  syncMapClickMode()

  resizeHandler = () => {
    scheduleInvalidateSize()
  }
  window.addEventListener('resize', resizeHandler)

  if (typeof ResizeObserver !== 'undefined' && mapEl.value) {
    containerResizeObserver = new ResizeObserver(() => {
      scheduleInvalidateSize()
    })
    containerResizeObserver.observe(mapEl.value)

    if (mapEl.value.parentElement) {
      parentResizeObserver = new ResizeObserver(() => {
        scheduleInvalidateSize()
      })
      parentResizeObserver.observe(mapEl.value.parentElement)
    }
  }

  emit('ready', map)
  renderSelection(true)
  renderLayers()

  // Panel width transitions (split -> map) do not trigger window resize.
  // Force delayed invalidation to avoid blank map area on the right side.
  window.setTimeout(() => {
    if (map) map.invalidateSize({ animate: false, pan: false })
  }, 60)
  window.setTimeout(() => {
    if (map) map.invalidateSize({ animate: false, pan: false })
  }, 320)
  window.setTimeout(() => {
    if (map) map.invalidateSize({ animate: false, pan: false })
  }, 720)
}

const clearLayerGroup = (group) => {
  if (!group) return
  group.clearLayers()
}

const buildLayersSignature = (layers) => {
  try {
    return JSON.stringify(layers || [])
  } catch {
    return `${Date.now()}`
  }
}

const toGeoJson = (data) => {
  if (!data) return null
  if (data.type === 'FeatureCollection' || data.type === 'Feature') return data
  if (Array.isArray(data)) {
    return {
      type: 'FeatureCollection',
      features: data
        .map((item) => toGeoJson(item))
        .flatMap((item) => {
          if (!item) return []
          if (item.type === 'FeatureCollection') return item.features || []
          return [item]
        })
    }
  }
  if (data.geometry) {
    return {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: data.geometry,
          properties: data.properties || {}
        }
      ]
    }
  }
  if (data.coordinates && data.type) {
    return {
      type: 'Feature',
      geometry: {
        type: data.type,
        coordinates: data.coordinates
      },
      properties: data.properties || {}
    }
  }
  return null
}

const renderLayers = (force = false) => {
  if (!overlayGroup || !map) return

  const layers = Array.isArray(props.layers) ? props.layers : []
  const signature = buildLayersSignature(layers)
  if (!force && signature === lastLayersSignature) return
  lastLayersSignature = signature

  clearLayerGroup(overlayGroup)

  layers.forEach((layer) => {
    if (layer?.visible === false) return

    const color = layer?.color || '#1f5d45'
    const weight = layer?.weight || 2
    const opacity = layer?.opacity ?? 0.75

    if (layer?.type === 'points' && Array.isArray(layer.data)) {
      layer.data.forEach((point) => {
        if (point == null) return
        const lat = Number(point.lat ?? point.latitude ?? point.y)
        const lon = Number(point.lon ?? point.lng ?? point.longitude ?? point.x)
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
        if (!isPointWithinSelectedRadius(lat, lon)) return

        L.circleMarker([lat, lon], {
          radius: point.radius || 6,
          color: point.color || color,
          weight: point.weight ?? weight,
          opacity: point.opacity ?? opacity,
          fillColor: point.fillColor || color,
          fillOpacity: point.fillOpacity ?? 0.8
        })
          .bindTooltip(toDisplayLabel(point.tooltip || point.label || layer.name || '节点'), { direction: 'top' })
          .bindPopup(buildPointPopup(point, layer), { maxWidth: 320 })
          .addTo(overlayGroup)
      })
      return
    }

    const geoJson = toGeoJson(layer?.data)
    if (!geoJson) return

    L.geoJSON(geoJson, {
      style: (feature) => {
        const featureColor = feature?.properties?.color || color
        const geometryType = String(feature?.geometry?.type || '')
        const isPolygon = geometryType.includes('Polygon')
        return {
          color: featureColor,
          weight: feature?.properties?.weight ?? weight,
          opacity: feature?.properties?.opacity ?? opacity,
          dashArray: feature?.properties?.dashArray ?? layer?.dashArray,
          fillColor: feature?.properties?.fillColor || layer?.fillColor || featureColor,
          fillOpacity: isPolygon
            ? (feature?.properties?.fillOpacity ?? layer?.fillOpacity ?? 0.25)
            : 0
        }
      },
      pointToLayer: (feature, latlng) => {
        const featureColor = feature?.properties?.color || color
        return L.circleMarker(latlng, {
          radius: feature?.properties?.radius || 5,
          color: featureColor,
          weight: feature?.properties?.weight ?? 2,
          opacity: feature?.properties?.opacity ?? opacity,
          fillColor: featureColor,
          fillOpacity: feature?.properties?.fillOpacity ?? 0.85
        })
      },
      onEachFeature: (feature, leafletLayer) => {
        const title = feature?.properties?.name || layer.name
        if (title) {
          leafletLayer.bindTooltip(title, { sticky: true })
        }
        const popupHtml = buildFeaturePopup(feature, layer)
        if (popupHtml) {
          leafletLayer.bindPopup(popupHtml, { maxWidth: 320 })
        }
      }
    }).addTo(overlayGroup)
  })

  scheduleInvalidateSize()
  if (layers.length > 0) {
    scheduleFitToContent()
  }
}

const renderSelection = (centerMap = false) => {
  if (!selectionGroup || !map) return

  clearLayerGroup(selectionGroup)

  const point = props.selectedPoint
  if (!point) return

  const lat = Number(point.lat)
  const lon = Number(point.lon)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return

  const pointMarker = L.circleMarker([lat, lon], {
    radius: 8,
    color: '#d97706',
    weight: 2,
    fillColor: '#f59e0b',
    fillOpacity: 0.92
  }).bindTooltip('选定点位', { direction: 'top' })

  const radiusCircle = L.circle([lat, lon], {
    radius: Math.max(Number(props.radiusMeters) || 0, 200),
    color: '#0f766e',
    weight: 2,
    opacity: 0.8,
    fillColor: '#14b8a6',
    fillOpacity: 0.08
  })

  pointMarker.addTo(selectionGroup)
  radiusCircle.addTo(selectionGroup)

  if (centerMap && overlayGroup?.getLayers?.().length) {
    scheduleFitToContent()
  } else if (centerMap) {
    map.setView([lat, lon], Math.max(map.getZoom(), 11))
  }

  scheduleInvalidateSize()
}

watch(
  () => props.layers,
  () => renderLayers()
)

watch(
  () => props.selectedPoint,
  () => {
    renderSelection(true)
    renderLayers(true)
  }
)

watch(
  () => [props.center?.[0], props.center?.[1], props.zoom],
  ([rawLat, rawLon, rawZoom]) => {
    if (!map) return
    const lat = Number(rawLat)
    const lon = Number(rawLon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    const zoom = Number(rawZoom)
    const nextZoom = Number.isFinite(zoom) && zoom > 0 ? zoom : map.getZoom()
    const currentCenter = map.getCenter()
    const centerUnchanged =
      Math.abs(currentCenter.lat - lat) < 0.00001 &&
      Math.abs(currentCenter.lng - lon) < 0.00001 &&
      map.getZoom() === nextZoom
    if (centerUnchanged) return
    map.setView([lat, lon], nextZoom, { animate: false })
  }
)

watch(
  () => props.radiusMeters,
  () => {
    renderSelection(false)
    renderLayers(true)
    if (overlayGroup?.getLayers?.().length) {
      scheduleFitToContent()
    }
  }
)

watch(
  () => props.readOnly,
  () => {
    syncMapClickMode()
  }
)

onMounted(() => {
  createMap()
})

onBeforeUnmount(() => {
  clearMapTimers()
  if (containerResizeObserver) {
    containerResizeObserver.disconnect()
    containerResizeObserver = null
  }
  if (parentResizeObserver) {
    parentResizeObserver.disconnect()
    parentResizeObserver = null
  }
  if (resizeFrame !== null) {
    cancelAnimationFrame(resizeFrame)
    resizeFrame = null
  }
  if (fitFrame !== null) {
    cancelAnimationFrame(fitFrame)
    fitFrame = null
  }
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
  }
  if (map) {
    if (mapClickHandler) {
      map.off('click', mapClickHandler)
      mapClickHandler = null
    }
    if (baseTileLayer) {
      baseTileLayer.off()
      baseTileLayer = null
    }
    map.off()
    map.remove()
    map = null
  }
})
</script>

<style scoped>
.leaflet-map-shell {
  position: relative;
  width: 100%;
  height: 100%;
}

.leaflet-map-picker {
  width: 100%;
  height: 100%;
  min-height: 360px;
  border-radius: 24px;
  overflow: hidden;
  background:
    radial-gradient(circle at 24% 18%, rgba(240, 138, 36, 0.18), transparent 32%),
    radial-gradient(circle at 78% 76%, rgba(31, 125, 93, 0.16), transparent 30%),
    linear-gradient(180deg, #f3f6f7 0%, #eef4f2 100%);
}

.map-loading-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  padding: 24px;
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.16) 0%, rgba(248, 250, 252, 0.62) 100%),
    radial-gradient(circle at 20% 18%, rgba(240, 138, 36, 0.16), transparent 32%),
    radial-gradient(circle at 80% 72%, rgba(31, 125, 93, 0.14), transparent 30%);
  backdrop-filter: blur(3px);
  transition: opacity 0.28s ease;
}

.map-loading-card {
  width: min(320px, 100%);
  padding: 18px 20px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(148, 163, 184, 0.22);
  box-shadow: 0 22px 50px rgba(15, 23, 42, 0.08);
  text-align: left;
  color: #10231d;
}

.map-loading-title {
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.01em;
}

.map-loading-subtitle {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(16, 35, 29, 0.68);
}

.map-loading-pulse {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.map-loading-pulse span {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f08a24, #1f7d5d);
  animation: mapPulseDot 1.2s ease-in-out infinite;
}

.map-loading-pulse span:nth-child(2) {
  animation-delay: 0.16s;
}

.map-loading-pulse span:nth-child(3) {
  animation-delay: 0.32s;
}

.map-loading-overlay.is-degraded .map-loading-card {
  background: rgba(255, 250, 244, 0.88);
}

.map-overlay-fade-enter-active,
.map-overlay-fade-leave-active {
  transition: opacity 0.26s ease;
}

.map-overlay-fade-enter-from,
.map-overlay-fade-leave-to {
  opacity: 0;
}

@keyframes mapPulseDot {
  0%, 80%, 100% {
    transform: translateY(0);
    opacity: 0.45;
  }
  40% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.leaflet-map-picker :deep(.map-popup) {
  min-width: 220px;
  color: #173126;
}

.leaflet-map-picker :deep(.map-popup-title) {
  font-size: 15px;
  font-weight: 800;
  color: #10231d;
}

.leaflet-map-picker :deep(.map-popup-subtitle) {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(16, 35, 29, 0.54);
}

.leaflet-map-picker :deep(.map-popup-summary) {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(16, 35, 29, 0.76);
}

.leaflet-map-picker :deep(.map-popup-fields) {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.leaflet-map-picker :deep(.map-popup-row) {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.leaflet-map-picker :deep(.map-popup-row span) {
  color: rgba(16, 35, 29, 0.56);
}

.leaflet-map-picker :deep(.map-popup-row strong) {
  color: #10231d;
  text-align: right;
}
</style>
