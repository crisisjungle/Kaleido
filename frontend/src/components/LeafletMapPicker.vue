<template>
  <div ref="mapEl" class="leaflet-map-picker"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
let map = null
let overlayGroup = null
let selectionGroup = null
let resizeHandler = null

const createMap = () => {
  if (!mapEl.value || map) return

  map = L.map(mapEl.value, {
    zoomControl: true,
    preferCanvas: true
  }).setView(props.center, props.zoom)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(map)

  overlayGroup = L.layerGroup().addTo(map)
  selectionGroup = L.layerGroup().addTo(map)

  if (!props.readOnly) {
    map.on('click', (event) => {
      emit('pick', {
        lat: Number(event.latlng.lat.toFixed(6)),
        lon: Number(event.latlng.lng.toFixed(6))
      })
    })
  }

  resizeHandler = () => {
    if (map) {
      map.invalidateSize()
    }
  }
  window.addEventListener('resize', resizeHandler)

  emit('ready', map)
  renderSelection(true)
  renderLayers()
}

const clearLayerGroup = (group) => {
  if (!group) return
  group.clearLayers()
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

const renderLayers = () => {
  if (!overlayGroup || !map) return

  clearLayerGroup(overlayGroup)

  const layers = Array.isArray(props.layers) ? props.layers : []
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

        L.circleMarker([lat, lon], {
          radius: point.radius || 6,
          color,
          weight,
          fillColor: point.fillColor || color,
          fillOpacity: point.fillOpacity ?? 0.8
        })
          .bindTooltip(point.label || layer.name || 'node', { direction: 'top' })
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
          weight: 2,
          fillColor: featureColor,
          fillOpacity: 0.85
        })
      },
      onEachFeature: (feature, leafletLayer) => {
        const title = feature?.properties?.name || layer.name
        if (title) {
          leafletLayer.bindTooltip(title, { sticky: true })
        }
      }
    }).addTo(overlayGroup)
  })
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

  if (centerMap) {
    map.setView([lat, lon], Math.max(map.getZoom(), 11))
  }
}

watch(
  () => props.layers,
  () => renderLayers(),
  { deep: true }
)

watch(
  () => props.selectedPoint,
  () => renderSelection(true),
  { deep: true }
)

watch(
  () => props.center,
  (value) => {
    if (!map || !Array.isArray(value) || value.length < 2) return
    const lat = Number(value[0])
    const lon = Number(value[1])
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    map.setView([lat, lon], map.getZoom(), { animate: false })
  },
  { deep: true }
)

watch(
  () => props.radiusMeters,
  () => renderSelection(false)
)

onMounted(() => {
  createMap()
})

onBeforeUnmount(() => {
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
  }
  if (map) {
    map.off()
    map.remove()
    map = null
  }
})
</script>

<style scoped>
.leaflet-map-picker {
  width: 100%;
  height: 100%;
  min-height: 360px;
  border-radius: 24px;
  overflow: hidden;
}
</style>
