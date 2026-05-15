<template>
  <div class="map-relation-panel" :class="{ loading: loading, embedded: embedded }">
    <header v-if="!embedded" class="panel-header">
      <div class="title-group">
        <h3>地图关系可视化</h3>
        <span class="phase-pill">运行态地图关系</span>
      </div>
      <div class="panel-actions">
        <button type="button" class="ghost-btn" @click="$emit('refresh')">刷新</button>
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
      <div v-if="hasData" class="map-summary-overlay" :class="{ 'is-embedded': embedded }">
        <span class="summary-chip summary-chip-accent">{{ highlightLabel || '推演关系回放' }}</span>
        <span class="summary-chip">{{ nodeCount }} 个节点</span>
        <span class="summary-chip">{{ shownEdgeCount }} 条连线</span>
        <span v-if="suppressedEdgeCount > 0" class="summary-chip summary-chip-muted">
          已整理 {{ suppressedEdgeCount }} 条高密度连线
        </span>
      </div>
      <div v-if="!hasData" class="empty-state">
        <span>等待地图关系数据...</span>
      </div>
    </div>


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
  },
  embedded: {
    type: Boolean,
    default: false
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
    const isHighlighted = isNodeHighlighted(node)
    const visual = nodeVisualState(node, kind, isHighlighted)
    const key = `${visual.status}:${kind}`
    if (!grouped.has(key)) grouped.set(key, { kind, status: visual.status, points: [] })
    grouped.get(key).points.push({
      lat,
      lon,
      tooltip: nodeTooltip(node),
      label: showNodeLabel(node, isHighlighted, visual.status) ? node?.name : '',
      radius: visual.radius,
      color: visual.color,
      weight: visual.weight,
      opacity: visual.opacity,
      fillColor: visual.fillColor,
      fillOpacity: visual.fillOpacity
    })
  }

  return [...grouped.values()]
    .sort((left, right) => {
      const statusDelta = animationStatusPriority(left.status) - animationStatusPriority(right.status)
      if (statusDelta !== 0) return statusDelta
      return nodeKindPriority(left.kind) - nodeKindPriority(right.kind)
    })
    .map((entry, index) => ({
      id: `nodes-${entry.status}-${entry.kind}`,
      name: `${entry.kind} ${entry.status} nodes`,
      type: 'points',
      color: nodeColor(entry.kind),
      visible: true,
      note: `Projected ${entry.kind} nodes`,
      data: entry.points,
      order: 100 + index
    }))
})

const edgeLayer = computed(() => {
  const { edges: visibleEdges } = compactedEdgeResult.value
  const features = []
  for (const edge of visibleEdges) {
    const source = nodeById.value.get(String(edge?.source_node_uuid || ''))
    const target = nodeById.value.get(String(edge?.target_node_uuid || ''))
    if (!source || !target) continue
    const highlighted = isEdgeHighlighted(edge)
    const visual = edgeVisualState(edge, highlighted)
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
        color: visual.color,
        weight: visual.weight,
        opacity: visual.opacity,
        dashArray: visual.dashArray,
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

const nodeHaloLayers = computed(() => {
  const grouped = new Map()
  for (const node of nodeList.value) {
    const lat = Number(node?.attributes?.lat)
    const lon = Number(node?.attributes?.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue
    const kind = String(node?.kind || node?.attributes?.map_kind || 'entity').toLowerCase()
    const isHighlighted = isNodeHighlighted(node)
    const visual = nodeVisualState(node, kind, isHighlighted)
    if (!['new', 'active'].includes(visual.status) && !isHighlighted) continue
    const key = `${visual.status}:${kind}`
    if (!grouped.has(key)) grouped.set(key, { kind, status: visual.status, points: [] })
    grouped.get(key).points.push({
      lat,
      lon,
      tooltip: nodeTooltip(node),
      label: '',
      radius: visual.radius + (visual.status === 'active' ? 6 : 4),
      color: visual.fillColor,
      weight: 1.2,
      opacity: visual.status === 'active' ? 0.36 : 0.24,
      fillColor: visual.fillColor,
      fillOpacity: visual.status === 'active' ? 0.14 : 0.08,
    })
  }

  return [...grouped.values()].map((entry, index) => ({
    id: `halo-${entry.status}-${entry.kind}`,
    name: `${entry.kind} ${entry.status} halo`,
    type: 'points',
    color: nodeColor(entry.kind),
    visible: true,
    note: `Projected ${entry.kind} halo`,
    data: entry.points,
    order: 80 + index,
  }))
})

const leafletLayers = computed(() => {
  const result = [...baseLayers.value]
  if (edgeLayer.value) result.push(edgeLayer.value)
  return result
    .concat(nodeHaloLayers.value)
    .concat(nodeLayers.value)
    .sort((left, right) => (Number(left?.order) || 0) - (Number(right?.order) || 0))
})

const highlightModeLabel = computed(() => {
  if (props.highlightMode === 'focus') return '聚焦'
  if (props.highlightMode === 'none') return '无'
  if (props.highlightMode) return props.highlightMode
  return props.highlightLabel ? '聚焦' : '无'
})

const HUB_EDGE_CAP = 24
const HUB_PRIORITY_KEEP = 8

const shownEdgeCount = computed(() => compactedEdgeResult.value.edges.length)
const suppressedEdgeCount = computed(() => compactedEdgeResult.value.suppressedCount)

const compactedEdgeResult = computed(() => {
  const alwaysVisible = []
  const directEdges = []
  const hubGroups = new Map()

  for (const edge of edgeList.value) {
    const source = nodeById.value.get(String(edge?.source_node_uuid || ''))
    const target = nodeById.value.get(String(edge?.target_node_uuid || ''))
    if (!source || !target) continue

    const highlighted = isEdgeHighlighted(edge)
    if (highlighted) {
      alwaysVisible.push(edge)
      continue
    }

    const hubNodeId = resolveHubNodeId(edge, source.node, target.node)
    if (!hubNodeId) {
      directEdges.push(edge)
      continue
    }

    if (!hubGroups.has(hubNodeId)) hubGroups.set(hubNodeId, [])
    hubGroups.get(hubNodeId).push(edge)
  }

  const hubVisible = []
  let suppressedCount = 0
  hubGroups.forEach((edges, hubNodeId) => {
    if (edges.length <= HUB_EDGE_CAP) {
      hubVisible.push(...edges)
      return
    }
    const kept = pickHubEdges(edges, hubNodeId, HUB_EDGE_CAP, HUB_PRIORITY_KEEP)
    suppressedCount += Math.max(0, edges.length - kept.length)
    hubVisible.push(...kept)
  })

  return {
    edges: dedupeEdges([...alwaysVisible, ...directEdges, ...hubVisible]),
    suppressedCount
  }
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

function resolveHubNodeId(edge, sourceNode, targetNode) {
  const type = String(edge?.fact_type || edge?.name || '').toLowerCase()
  if (!['agent_influence', 'influences_region', 'agent_anchor', 'located_in', 'depends_on', 'affects'].includes(type)) {
    return ''
  }
  const sourceKind = nodeKind(sourceNode)
  const targetKind = nodeKind(targetNode)
  if (isHubKind(sourceKind) && targetKind === 'agent') return String(sourceNode?.uuid || '')
  if (isHubKind(targetKind) && sourceKind === 'agent') return String(targetNode?.uuid || '')
  return ''
}

function pickHubEdges(edges, hubNodeId, cap, mustKeepCount) {
  const sorted = [...edges].sort((left, right) => edgeScore(right) - edgeScore(left))
  const mustKeep = sorted.slice(0, Math.min(mustKeepCount, cap))
  const selected = new Set(mustKeep.map((edge) => String(edge?.uuid || '')))
  const rest = sorted.filter((edge) => !selected.has(String(edge?.uuid || '')))
  if (mustKeep.length >= cap) return mustKeep
  const spread = sampleEdgesByAngle(rest, hubNodeId, cap - mustKeep.length)
  return dedupeEdges([...mustKeep, ...spread])
}

function sampleEdgesByAngle(edges, hubNodeId, limit) {
  if (limit <= 0 || edges.length === 0) return []
  if (edges.length <= limit) return edges
  const projected = edges
    .map((edge) => {
      const sourceId = String(edge?.source_node_uuid || '')
      const targetId = String(edge?.target_node_uuid || '')
      const source = nodeById.value.get(sourceId)
      const target = nodeById.value.get(targetId)
      if (!source || !target) return null
      const hub = sourceId === hubNodeId ? source : target
      const peer = sourceId === hubNodeId ? target : source
      const angle = Math.atan2(peer.lat - hub.lat, peer.lon - hub.lon)
      return { edge, angle }
    })
    .filter(Boolean)
    .sort((a, b) => a.angle - b.angle)
  if (projected.length <= limit) return projected.map((item) => item.edge)
  const selected = []
  const step = projected.length / limit
  for (let i = 0; i < limit; i += 1) {
    const idx = Math.min(projected.length - 1, Math.floor(i * step))
    selected.push(projected[idx].edge)
  }
  return selected
}

function edgeScore(edge) {
  const attrs = edge?.attributes || {}
  let score = 0
  const factType = String(edge?.fact_type || edge?.name || '').toLowerCase()
  if (factType === 'dynamic_edge') score += 0.5
  if (isEdgeHighlighted(edge)) score += 1
  score += Number(attrs?.strength || 0) * 0.9
  score += Number(attrs?.confidence || 0) * 0.8
  return score
}

function dedupeEdges(edges) {
  const map = new Map()
  for (const edge of edges) {
    const key = String(edge?.uuid || '')
    if (!key || map.has(key)) continue
    map.set(key, edge)
  }
  return [...map.values()]
}

function nodeKind(node) {
  return String(node?.kind || node?.attributes?.map_kind || '').toLowerCase()
}

function isHubKind(kind) {
  return kind === 'region' || kind === 'subregion'
}

function nodeTooltip(node) {
  const placeholderNames = new Set([
    'agent node',
    'agent nodes',
    'region node',
    'region nodes',
    'subregion node',
    'subregion nodes',
    'entity node',
    'entity nodes',
    'node',
    'nodes'
  ])
  const name = String(node?.name || '').trim()
  if (name && !placeholderNames.has(name.toLowerCase())) return name
  const attrs = node?.attributes || {}
  const displayName = String(attrs?.display_name || attrs?.actor_name || attrs?.title || '').trim()
  if (displayName) return displayName
  const summary = String(node?.summary || '').trim()
  if (summary) return summary.length > 56 ? `${summary.slice(0, 53)}...` : summary
  const nodeId = String(node?.uuid || '').trim()
  if (nodeId.includes('::')) return nodeId.split('::').slice(-1)[0]
  if (nodeId) return nodeId
  return 'node'
}

function showNodeLabel(node, highlighted, status = 'steady') {
  if (highlighted) return true
  const kind = String(node?.kind || node?.attributes?.map_kind || '').toLowerCase()
  if (status === 'new' || status === 'active') return true
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

function normalizeAnimationStatus(value) {
  const status = String(value || '').trim().toLowerCase()
  return ['hidden', 'new', 'steady', 'active', 'faded'].includes(status) ? status : 'steady'
}

function animationStatusPriority(status) {
  if (status === 'faded') return 0
  if (status === 'steady') return 1
  if (status === 'new') return 2
  if (status === 'active') return 3
  return 1
}

function nodeKindPriority(kind) {
  if (kind === 'region') return 0
  if (kind === 'subregion') return 1
  if (kind === 'agent') return 2
  return 3
}

function entityAnimationStatus(entity) {
  return normalizeAnimationStatus(entity?.attributes?.animation_status)
}

function nodeVisualState(node, kind, highlighted) {
  const status = entityAnimationStatus(node)
  const baseRadius = nodeRadius(kind)
  const baseColor = nodeColor(kind)
  let radius = baseRadius
  let color = baseColor
  let fillColor = baseColor
  let weight = 1.4
  let opacity = 0.72
  let fillOpacity = 0.82

  if (status === 'new') {
    radius += 2.5
    color = '#b45309'
    fillColor = '#f59e0b'
    weight = 2.1
    opacity = 0.94
    fillOpacity = 0.96
  } else if (status === 'active') {
    radius += 3
    color = '#7f1d1d'
    fillColor = '#ef4444'
    weight = 2.5
    opacity = 0.96
    fillOpacity = 0.98
  } else if (status === 'faded') {
    radius = Math.max(2.5, radius - 1.5)
    color = '#64748b'
    fillColor = '#94a3b8'
    weight = 1
    opacity = 0.18
    fillOpacity = 0.2
  }

  if (highlighted) {
    radius += 1.5
    color = '#7f1d1d'
    fillColor = '#dc2626'
    weight = Math.max(weight, 2.6)
    opacity = 0.98
    fillOpacity = 0.98
  }

  return {
    status,
    radius,
    color,
    fillColor,
    weight,
    opacity,
    fillOpacity
  }
}

function edgeVisualState(edge, highlighted) {
  const status = entityAnimationStatus(edge)
  let color = edgeColor(edge, false)
  let weight = 1.35
  let opacity = 0.38
  let dashArray = undefined

  if (status === 'new') {
    color = '#f59e0b'
    weight = 2.2
    opacity = 0.84
    dashArray = '7 6'
  } else if (status === 'active') {
    color = '#ef4444'
    weight = 2.8
    opacity = 0.96
  } else if (status === 'faded') {
    color = '#94a3b8'
    weight = 0.9
    opacity = 0.16
    dashArray = '3 7'
  }

  if (highlighted) {
    color = '#dc2626'
    weight = 3
    opacity = 0.98
    dashArray = undefined
  }

  return { color, weight, opacity, dashArray }
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

.map-relation-panel.embedded {
  border: none;
  border-radius: 0;
  background: transparent;
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

.map-summary-overlay {
  position: absolute;
  top: 14px;
  left: 14px;
  right: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  pointer-events: none;
  z-index: 420;
}

.map-summary-overlay.is-embedded {
  top: 68px;
}

.summary-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(226, 232, 240, 0.92);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

.summary-chip-accent {
  background: rgba(255, 247, 237, 0.92);
  color: #b45309;
  border-color: rgba(245, 158, 11, 0.26);
}

.summary-chip-muted {
  color: #475569;
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


</style>
