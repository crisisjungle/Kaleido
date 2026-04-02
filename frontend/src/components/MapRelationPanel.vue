<template>
  <div class="map-relation-panel" :class="{ loading: loading }">
    <header class="panel-header">
      <div class="title-group">
        <h3>Map Relationship Visualization</h3>
        <span class="phase-pill">运行态地图关系</span>
      </div>
      <div class="panel-actions">
        <button type="button" class="ghost-btn" @click="$emit('refresh')">Refresh</button>
        <button type="button" class="ghost-btn" @click="$emit('toggle-maximize')">⛶</button>
      </div>
    </header>

    <div class="map-shell">
      <LeafletMapPicker
        :center="mapCenter"
        :zoom="mapZoom"
        :layers="leafletLayers"
        :selected-point="null"
        :radius-meters="0"
        read-only
      />
      <div v-if="!hasData" class="empty-state">
        <span>等待地图关系数据...</span>
      </div>
    </div>

    <footer class="panel-footer">
      <div class="stat-chip">
        <span>Nodes</span>
        <strong>{{ nodeCount }}</strong>
      </div>
      <div class="stat-chip">
        <span>Edges</span>
        <strong>{{ edgeCount }}</strong>
      </div>
      <div class="stat-chip">
        <span>Key</span>
        <strong>{{ keyEdgeCount }}</strong>
      </div>
      <div class="stat-chip">
        <span>Focus</span>
        <strong>{{ highlightModeLabel }}</strong>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import LeafletMapPicker from './LeafletMapPicker.vue'

const props = defineProps({
  mapData: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  },
  highlightNodeIds: {
    type: Array,
    default: () => []
  },
  highlightNodeNames: {
    type: Array,
    default: () => []
  },
  highlightEdgeIds: {
    type: Array,
    default: () => []
  },
  highlightLabel: {
    type: String,
    default: ''
  },
  highlightMode: {
    type: String,
    default: ''
  }
})

defineEmits(['refresh', 'toggle-maximize'])

const nodeList = computed(() => {
  const raw = props.mapData?.nodes
  return Array.isArray(raw) ? raw : []
})

const edgeList = computed(() => {
  const raw = props.mapData?.edges
  return Array.isArray(raw) ? raw : []
})

const nodeCount = computed(() => nodeList.value.length)
const edgeCount = computed(() => edgeList.value.length)
const keyEdgeCount = computed(() => edgeList.value.filter((edge) => edge?.is_key_interaction || edge?.attributes?.is_key_interaction).length)
const hasData = computed(() => nodeCount.value > 0 || edgeCount.value > 0)

const mapCenter = computed(() => {
  const center = props.mapData?.center || {}
  const lat = Number(center.lat)
  const lon = Number(center.lon)
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    return [lat, lon]
  }
  return [20, 0]
})

const mapZoom = computed(() => {
  const zoom = Number(props.mapData?.zoom_hint)
  if (Number.isFinite(zoom) && zoom > 0) return zoom
  return 9
})

const highlightedNodeIdSet = computed(() => {
  const set = new Set()
  for (const item of props.highlightNodeIds || []) {
    const token = String(item || '').trim()
    if (token) set.add(token)
  }
  return set
})

const highlightedNodeNameSet = computed(() => {
  const set = new Set()
  for (const item of props.highlightNodeNames || []) {
    const token = String(item || '').trim().toLowerCase()
    if (token) set.add(token)
  }
  if (props.highlightLabel) {
    set.add(String(props.highlightLabel).trim().toLowerCase())
  }
  return set
})

const highlightedEdgeIdSet = computed(() => {
  const set = new Set()
  for (const item of props.highlightEdgeIds || []) {
    const token = String(item || '').trim()
    if (token) set.add(token)
  }
  return set
})

const nodeById = computed(() => {
  const map = new Map()
  for (const node of nodeList.value) {
    const nodeId = String(node?.uuid || '')
    const lat = Number(node?.attributes?.lat)
    const lon = Number(node?.attributes?.lon)
    if (!nodeId || !Number.isFinite(lat) || !Number.isFinite(lon)) continue
    map.set(nodeId, { lat, lon, node })
  }
  return map
})

const normalizeLayer = (layer, index) => ({
  id: layer?.id || `map-layer-${index}`,
  name: layer?.name || `Layer ${index + 1}`,
  type: layer?.type || 'geojson',
  color: layer?.color || '#0f766e',
  visible: layer?.visible !== false,
  note: layer?.note || '',
  data: layer?.data || []
})

const baseLayers = computed(() => {
  const layers = props.mapData?.layers
  if (!Array.isArray(layers)) return []
  return layers.map((layer, index) => normalizeLayer(layer, index))
})

const nodeLayers = computed(() => {
  const grouped = new Map()
  for (const node of nodeList.value) {
    const lat = Number(node?.attributes?.lat)
    const lon = Number(node?.attributes?.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue
    const kind = String(node?.kind || node?.attributes?.map_kind || 'entity').toLowerCase()
    if (!grouped.has(kind)) grouped.set(kind, [])
    const isHighlighted = isNodeHighlighted(node)
    grouped.get(kind).push({
      lat,
      lon,
      label: showNodeLabel(node, isHighlighted) ? node?.name : '',
      radius: isHighlighted ? nodeRadius(kind) + 2 : nodeRadius(kind),
      fillColor: isHighlighted ? '#dc2626' : nodeColor(kind),
      fillOpacity: isHighlighted ? 0.95 : 0.82
    })
  }

  const layers = []
  let order = 0
  grouped.forEach((points, kind) => {
    layers.push({
      id: `nodes-${kind}`,
      name: `${kind} nodes`,
      type: 'points',
      color: nodeColor(kind),
      visible: true,
      note: `Projected ${kind} nodes`,
      data: points,
      order: 100 + order
    })
    order += 1
  })
  return layers
})

const edgeLayer = computed(() => {
  const features = []
  for (const edge of edgeList.value) {
    const source = nodeById.value.get(String(edge?.source_node_uuid || ''))
    const target = nodeById.value.get(String(edge?.target_node_uuid || ''))
    if (!source || !target) continue
    const highlighted = isEdgeHighlighted(edge) || (isNodeHighlighted(source.node) && isNodeHighlighted(target.node))
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [source.lon, source.lat],
          [target.lon, target.lat]
        ]
      },
      properties: {
        name: edge?.name || edge?.fact_type || 'relation',
        color: edgeColor(edge, highlighted),
        weight: highlighted ? 3 : 2,
        opacity: highlighted ? 0.95 : 0.7,
        fillOpacity: 0
      }
    })
  }

  if (!features.length) return null
  return {
    id: 'relation-edges',
    name: 'key interactions',
    type: 'geojson',
    color: '#475569',
    visible: true,
    note: 'Key interaction edges on map',
    data: {
      type: 'FeatureCollection',
      features
    }
  }
})

const leafletLayers = computed(() => {
  const result = [...baseLayers.value]
  if (edgeLayer.value) result.push(edgeLayer.value)
  return result.concat(nodeLayers.value)
})

const highlightModeLabel = computed(() => {
  if (props.highlightMode) return props.highlightMode
  return props.highlightLabel ? 'focus' : 'none'
})

function isNodeHighlighted(node) {
  const id = String(node?.uuid || '').trim()
  const name = String(node?.name || '').trim().toLowerCase()
  if (id && highlightedNodeIdSet.value.has(id)) return true
  if (name && highlightedNodeNameSet.value.has(name)) return true
  return false
}

function isEdgeHighlighted(edge) {
  const edgeId = String(edge?.uuid || '').trim()
  return edgeId ? highlightedEdgeIdSet.value.has(edgeId) : false
}

function showNodeLabel(node, highlighted) {
  if (highlighted) return true
  const kind = String(node?.kind || node?.attributes?.map_kind || '').toLowerCase()
  return kind === 'region' || kind === 'subregion'
}

function nodeRadius(kind) {
  if (kind === 'region') return 8
  if (kind === 'subregion') return 6
  if (kind === 'agent') return 5
  return 4
}

function nodeColor(kind) {
  if (kind === 'region') return '#ea580c'
  if (kind === 'subregion') return '#f97316'
  if (kind === 'agent') return '#1d4ed8'
  return '#0f766e'
}

function edgeColor(edge, highlighted) {
  if (highlighted) return '#dc2626'
  const type = String(edge?.fact_type || edge?.name || '').toLowerCase()
  if (type === 'dynamic_edge') return '#b45309'
  if (type === 'agent_influence' || type === 'influences_region') return '#2563eb'
  if (type.includes('depend') || type.includes('affect') || type.includes('regulat')) return '#7c3aed'
  return '#64748b'
}
</script>

<style scoped>
.map-relation-panel {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  overflow: hidden;
}

.panel-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e2e8f0;
  padding: 0 14px;
  background: #ffffff;
}

.title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-group h3 {
  margin: 0;
  font-size: 17px;
  color: #0f172a;
  font-weight: 700;
}

.phase-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #1e3a8a;
  background: #dbeafe;
}

.panel-actions {
  display: inline-flex;
  gap: 8px;
}

.ghost-btn {
  border: 1px solid #dbe2ea;
  border-radius: 999px;
  background: #ffffff;
  height: 32px;
  min-width: 32px;
  padding: 0 12px;
  font-size: 12px;
  color: #334155;
  cursor: pointer;
}

.map-shell {
  position: relative;
  flex: 1;
  min-height: 0;
}

.empty-state {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  color: #64748b;
  font-size: 14px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.75) 0%, rgba(248, 250, 252, 0.92) 100%);
}

.panel-footer {
  height: 50px;
  border-top: 1px solid #e2e8f0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  background: #ffffff;
}

.stat-chip {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}

.stat-chip strong {
  color: #0f172a;
  font-weight: 700;
  font-size: 14px;
}
</style>
