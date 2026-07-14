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
        :fit-key="mapViewportKey"
        :selected-point="null"
        :radius-meters="0"
        read-only
      />
      <div v-if="hasData" class="map-summary-overlay" :class="{ 'is-embedded': embedded }">
        <span class="summary-chip summary-chip-accent">{{ safeMapText(highlightLabel, '推演关系回放') }}</span>
        <span
          v-if="hasDegradedSpatialEvidence"
          class="summary-chip summary-chip-quality"
          title="公网空间事实不足；参考节点和示意落点不等同于真实观测"
        >空间证据降级</span>
        <span class="summary-chip">{{ nodeCount }} 个节点 · {{ shownEdgeCount }} 条连线</span>
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
import { safeDisplayText, safeDisplayToken } from '../utils/displayText'
import {
  CURATED_FIXTURE_GROUNDING,
  isCuratedFixtureNode,
  normalizeMapAnimationStatus,
  resolveCuratedFixtureEdgeGrounding,
  resolveEdgeGeometry,
  sliceGeometryByProgress,
} from '../utils/mapRelationGeometry'

const INVALID_MAP_COPY = new Set(['内部标识', '未命名项', '内容待本地化'])
const safeMapText = (value, fallback = '') => {
  const text = safeDisplayText(value, '').trim()
  return !text || INVALID_MAP_COPY.has(text) ? fallback : text
}
const safeMapToken = (value, fallback = '') => safeDisplayToken(value, fallback)

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
const spatialQuality = computed(() => props.mapData?.data_quality || {})
const hasDegradedSpatialEvidence = computed(() => (
  spatialQuality.value?.formal_ready === false
  || ['partial', 'unavailable'].includes(String(spatialQuality.value?.status || '').toLowerCase())
))

// M10 honesty: never dress a synthetic (hash/radial) layout as real geography.
const geographicGrounding = computed(() => {
  const top = String(props.mapData?.geographic_grounding || '').trim().toLowerCase()
  if (top === 'map_seed' || top === 'synthetic' || top === CURATED_FIXTURE_GROUNDING) return top
  const meta = String(props.mapData?.meta?.geographic_grounding || '').trim().toLowerCase()
  if (meta === 'map_seed' || meta === 'synthetic' || meta === CURATED_FIXTURE_GROUNDING) return meta
  return ''
})

function nodePlacementOf(node) {
  if (node?.is_geographic === true || node?.attributes?.is_geographic === true) return 'geographic'
  if (node?.is_geographic === false || node?.attributes?.is_geographic === false) return 'synthetic'
  const placement = String(node?.attributes?.placement || node?.placement || '').trim().toLowerCase()
  if (['geographic', 'map_seed', 'anchored', 'real'].includes(placement)) return 'geographic'
  if (['synthetic', 'non_geographic', 'radial', 'hash'].includes(placement)) return 'synthetic'
  return 'unknown'
}

function effectiveNodePlacement(node) {
  const placement = nodePlacementOf(node)
  if (placement !== 'unknown') return placement
  if (geographicGrounding.value === 'map_seed') return 'geographic'
  if (geographicGrounding.value === 'synthetic') return 'synthetic'
  return 'unknown'
}

const placementSummary = computed(() => {
  const result = { geographic: 0, synthetic: 0, unknown: 0 }
  for (const node of nodeList.value) {
    result[effectiveNodePlacement(node)] += 1
  }

  // Older payloads may only carry the projection-level marker. Keep that as a
  // compatibility fallback, but never let it overwrite explicit node markers.
  if (result.geographic === 0 && result.synthetic === 0 && result.unknown > 0) {
    if (geographicGrounding.value === 'map_seed') {
      result.geographic = result.unknown
      result.unknown = 0
    } else if (geographicGrounding.value === 'synthetic') {
      result.synthetic = result.unknown
      result.unknown = 0
    }
  }
  return result
})

const hasMixedGrounding = computed(() => (
  placementSummary.value.geographic > 0 && placementSummary.value.synthetic > 0
))

const isSyntheticGrounding = computed(() => {
  if (placementSummary.value.synthetic > 0) {
    return placementSummary.value.geographic === 0
  }
  return geographicGrounding.value === 'synthetic'
})

// M10 edge-layer summary (prefer backend meta, recount as fallback).
const edgeLayerSummary = computed(() => {
  const meta = props.mapData?.meta || {}
  let spatial = Number(meta.spatial_fact_edge_count)
  let causal = Number(meta.causal_edge_count)
  if (!Number.isFinite(spatial) || !Number.isFinite(causal)) {
    spatial = 0
    causal = 0
    for (const edge of edgeList.value) {
      const layer = edgeLayerOf(edge)
      if (layer === 'spatial_fact') spatial += 1
      else if (layer === 'causal') causal += 1
    }
  }
  if (spatial <= 0 && causal <= 0) return null
  return { spatial, causal }
})

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

const mapViewportKey = computed(() => {
  const center = mapCenter.value
  const meta = props.mapData?.meta || {}
  return [
    props.mapData?.simulation_id || props.mapData?.map_seed_id || props.mapData?.source_mode || 'map',
    props.mapData?.map_seed_id || geographicGrounding.value || 'unanchored',
    meta.projection_version || meta.layout_version || '',
    Number(center[0]).toFixed(5),
    Number(center[1]).toFixed(5)
  ].join(':')
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
  name: safeMapText(layer?.name, `地图图层 ${index + 1}`),
  type: layer?.type || 'geojson',
  color: layer?.color || '#0f766e',
  visible: layer?.visible !== false,
  note: safeMapText(layer?.note, ''),
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
    const placement = effectiveNodePlacement(node)
    const isSynthetic = placement === 'synthetic'
    const visual = nodeVisualState(node, kind, isHighlighted, isSynthetic)
    if (visual.status === 'hidden') continue
    const key = `${placement}:${kind}:${visual.group}`
    if (!grouped.has(key)) grouped.set(key, { placement, kind, group: visual.group, points: [] })
    const displayName = nodeTooltip(node)
    grouped.get(key).points.push({
      id: String(node?.uuid || ''),
      renderKey: String(node?.uuid || `${kind}:${lat}:${lon}`),
      lat,
      lon,
      tooltip: isSynthetic ? `${displayName}（示意位置）` : displayName,
      label: showNodeLabel(node, isHighlighted, visual.status) ? displayName : '',
      popupTitle: displayName,
      popupSubtitle: isSynthetic
        ? '示意位置 · 非真实地理锚点'
        : (placement === 'geographic' ? '地理锚定节点' : '位置状态未标注'),
      popupSummary: isSynthetic
        ? '该节点用于展示关系结构，位置由系统散布，不代表真实地点。'
        : '',
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
      return nodeKindPriority(left.kind) - nodeKindPriority(right.kind)
    })
    .map((entry, index) => ({
      id: `nodes-${entry.placement}-${entry.kind}-${entry.group}`,
      name: `${safeMapToken(entry.kind, '节点')} · 推演状态`,
      type: 'points',
      color: nodeColor(null, entry.kind, entry.group),
      visible: true,
      note: '推演节点投影',
      data: entry.points,
      order: 100 + index
    }))
})

const drawableEdgeEntries = computed(() => {
  const result = []
  for (const edge of compactedEdgeResult.value.edges) {
    const source = nodeById.value.get(String(edge?.source_node_uuid || ''))
    const target = nodeById.value.get(String(edge?.target_node_uuid || ''))
    if (!source || !target) continue
    const grounding = edgeGroundingPolicy(source.node, target.node, edge)
    if (grounding === 'omit') continue
    result.push({ edge, source, target, grounding })
  }
  return result
})

const edgeLayer = computed(() => {
  const features = []
  for (const { edge, source, target, grounding } of drawableEdgeEntries.value) {
    const edgeId = String(edge?.uuid || `${edge?.source_node_uuid}-${edge?.target_node_uuid}`)
    const highlighted = isEdgeHighlighted(edge)
    const status = entityAnimationStatus(edge)
    if (status === 'hidden') continue
    const propagationGrounding = String(edge?.attributes?.propagation_grounding || '').trim().toLowerCase()
    const schematicPropagation = ['new', 'active'].includes(status)
      && (propagationGrounding.includes('schematic') || propagationGrounding.includes('partial'))
    const hasCuratedFixtureEndpoint = isCuratedFixtureNode(source.node) || isCuratedFixtureNode(target.node)
    const eligibleSchematicPropagation = schematicPropagation && !hasCuratedFixtureEndpoint
    // An event with geographic endpoints but no authoritative edge may still
    // be shown as a neutral endpoint bridge.  It must not borrow a candidate
    // business edge's route geometry and masquerade as an observed path.
    const geometry = schematicPropagation
      ? {
          type: 'LineString',
          coordinates: [[source.lon, source.lat], [target.lon, target.lat]]
        }
      : resolveEdgeGeometry(source, target, edge)
    const schematic = grounding === 'schematic' || schematicPropagation
    const isPropagationWave = props.highlightMode === 'animation'
      && ['new', 'active'].includes(status)
      && (grounding === 'geographic' || grounding === 'curated_fixture' || eligibleSchematicPropagation)

    const addFeature = (id, featureGeometry, visual, role) => {
      features.push({
        id,
        type: 'Feature',
        geometry: featureGeometry,
        properties: {
          id,
          edge_id: edgeId,
          renderKey: id,
          name: schematicPropagation
            ? '节点响应示意（非物理路径）'
            : grounding === 'curated_fixture'
              ? `${safeMapToken(edge?.name || edge?.fact_type, '传播通道')}（金标推演路径）`
            : schematic
              ? '区域关系示意（非物理路径）'
              : safeMapToken(edge?.name || edge?.fact_type, '关联'),
          color: visual.color,
          weight: visual.weight,
          opacity: visual.opacity,
          dashArray: visual.dashArray,
          fillOpacity: 0,
          relation_role: role,
          geographic_grounding: grounding === 'curated_fixture'
            ? CURATED_FIXTURE_GROUNDING
            : grounding
        }
      })
    }

    if (isPropagationWave) {
      addFeature(`${edgeId}:base`, geometry, edgeContextVisualState(edge, schematic), schematic ? 'schematic_context' : 'context')
      addFeature(
        `${edgeId}:wave`,
        sliceGeometryByProgress(geometry, entityAnimationProgress(edge)),
        edgeVisualState(edge, highlighted, false),
        'propagation_wave'
      )
      continue
    }

    const visual = schematic
      ? edgeContextVisualState(edge, true)
      : edgeVisualState(edge, highlighted, false)
    addFeature(`${edgeId}:base`, geometry, visual, schematic ? 'schematic_context' : 'context')
  }

  if (!features.length) return null
  return {
    id: 'relation-edges',
    name: '重点关系',
    type: 'geojson',
    color: '#475569',
    visible: true,
    note: '地图中的重点关系连线',
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
    const placement = effectiveNodePlacement(node)
    const visual = nodeVisualState(node, kind, isHighlighted, placement === 'synthetic')
    if (visual.status === 'hidden') continue
    if (!['new', 'active'].includes(visual.status) && !isHighlighted) continue
    const key = `${placement}:${kind}:${visual.group}`
    if (!grouped.has(key)) grouped.set(key, { placement, kind, group: visual.group, points: [] })
    grouped.get(key).points.push({
      id: `${String(node?.uuid || `${kind}:${lat}:${lon}`)}:halo`,
      renderKey: `${String(node?.uuid || `${kind}:${lat}:${lon}`)}:halo`,
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
    id: `halo-${entry.placement}-${entry.kind}-${entry.group}`,
    name: `${safeMapToken(entry.kind, '节点')} · 动态光环`,
    type: 'points',
  color: nodeColor(null, entry.kind, entry.group),
    visible: true,
    note: '推演节点动态光环',
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
  if (props.highlightMode) return safeMapToken(props.highlightMode, '聚焦')
  return props.highlightLabel ? '聚焦' : '无'
})

const HUB_EDGE_CAP = 16
const HUB_PRIORITY_KEEP = 5
const RELATION_GROUP_CAP = 42
const RELATION_GROUP_PRIORITY_KEEP = 10

const shownEdgeCount = computed(() => drawableEdgeEntries.value.length)
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
    if (entityAnimationStatus(edge) === 'hidden') continue
    if (highlighted) {
      alwaysVisible.push(edge)
      continue
    }

    const hubNodeId = resolveHubNodeId(edge, source.node, target.node)
    const relationGroupKey = resolveRelationGroupKey(edge, source.node, target.node)
    if (!hubNodeId && relationGroupKey) {
      if (!hubGroups.has(relationGroupKey)) hubGroups.set(relationGroupKey, [])
      hubGroups.get(relationGroupKey).push(edge)
      continue
    }

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
    const isRelationGroup = String(hubNodeId).startsWith('relgroup::')
    const cap = isRelationGroup ? RELATION_GROUP_CAP : HUB_EDGE_CAP
    const priorityKeep = isRelationGroup ? RELATION_GROUP_PRIORITY_KEEP : HUB_PRIORITY_KEEP
    if (edges.length <= cap) {
      hubVisible.push(...edges)
      return
    }
    const kept = pickHubEdges(edges, hubNodeId, cap, priorityKeep)
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
  if (edgeId && highlightedEdgeIdSet.value.has(edgeId)) return true
  const attributes = edge?.attributes || {}
  const mechanismIds = [
    attributes.mechanism_edge_id,
    attributes.mechanismEdgeId,
    ...(Array.isArray(attributes.mechanism_edge_ids) ? attributes.mechanism_edge_ids : []),
    ...(Array.isArray(attributes.mechanismEdgeIds) ? attributes.mechanismEdgeIds : [])
  ]
  return mechanismIds.some(item => highlightedEdgeIdSet.value.has(String(item || '').trim()))
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

function resolveRelationGroupKey(edge, sourceNode, targetNode) {
  const type = String(edge?.fact_type || edge?.name || '').toLowerCase()
  if (['region_neighbor', 'region_hierarchy', 'transport_edge', 'agent_anchor', 'located_in'].includes(type)) return ''
  const sourceRegion = String(edge?.attributes?.source_region_id || sourceNode?.attributes?.home_region_id || sourceNode?.attributes?.primary_region || '').trim()
  const targetRegion = String(edge?.attributes?.target_region_id || targetNode?.attributes?.home_region_id || targetNode?.attributes?.primary_region || '').trim()
  const channel = String(edge?.attributes?.interaction_channel || edge?.attributes?.channel_type || type || 'relation').trim()
  if (!sourceRegion && !targetRegion) return ''
  return `relgroup::${sourceRegion || 'unknown'}::${targetRegion || 'unknown'}::${channel}`
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
  const name = safeMapText(node?.name, '')
  if (name && !placeholderNames.has(String(node?.name || '').trim().toLowerCase())) return name
  const attrs = node?.attributes || {}
  const displayName = safeMapText(attrs?.display_name || attrs?.actor_name || attrs?.title, '')
  if (displayName) return displayName
  return '未命名节点'
}

function showNodeLabel(node, highlighted, status = 'steady') {
  if (highlighted) return true
  const kind = String(node?.kind || node?.attributes?.map_kind || '').toLowerCase()
  if (status === 'new' || status === 'active') return true
  return kind === 'region' || kind === 'subregion'
}

function nodeRadius(kind, group = '') {
  if (kind === 'region') return 9
  if (kind === 'subregion') return 6.2
  if (kind === 'agent') {
    if (group === 'governance') return 6.4
    if (group === 'organization') return 5.5
    if (group === 'human') return 4.3
    return 4.8
  }
  return 4
}

function nodeGroup(node, kind) {
  if (kind !== 'agent') return kind
  const attrs = node?.attributes || {}
  const labels = Array.isArray(node?.labels) ? node.labels.join(' ') : ''
  const text = `${attrs.node_family || ''} ${attrs.agent_type || ''} ${attrs.agent_subtype || ''} ${labels}`.toLowerCase()
  if (text.includes('governance') || text.includes('government') || text.includes('治理') || text.includes('政府')) return 'governance'
  if (text.includes('organization') || text.includes('组织') || text.includes('机构')) return 'organization'
  if (text.includes('human') || text.includes('居民') || text.includes('社区') || text.includes('人')) return 'human'
  return 'agent'
}

function nodeColor(node, kind, fallbackGroup = '') {
  const group = fallbackGroup || nodeGroup(node, kind)
  if (kind === 'region') return '#ea580c'
  if (kind === 'subregion') return '#f59e0b'
  if (kind === 'agent') {
    if (group === 'governance') return '#0f766e'
    if (group === 'organization') return '#7c3aed'
    if (group === 'human') return '#2563eb'
    return '#334155'
  }
  return '#0f766e'
}

// --- M10 honesty helpers: split spatial skeleton vs causal coupling ---------
function edgeLayerOf(edge) {
  const layer = String(edge?.edge_layer || edge?.attributes?.edge_layer || '').trim().toLowerCase()
  if (layer === 'spatial_fact' || layer === 'causal') return layer
  return ''
}

function isSpatialFactEdge(edge) {
  return edgeLayerOf(edge) === 'spatial_fact'
}

function edgeChannelOf(edge) {
  return String(
    edge?.channel
    || edge?.attributes?.interaction_channel
    || edge?.attributes?.channel_type
    || edge?.attributes?.channel
    || ''
  ).trim().toLowerCase()
}

const MAP_CHANNEL_COLORS = {
  physical: '#0891b2',
  transport: '#0d9488',
  mobility: '#0d9488',
  information: '#7c3aed',
  social: '#7c3aed',
  economic: '#b45309',
  supply: '#b45309',
  governance: '#0f766e',
  policy: '#0f766e',
  health: '#dc2626',
  ecological: '#16a34a',
  environment: '#16a34a',
}

function edgeEpistemicOf(edge) {
  return String(
    edge?.epistemic
    || edge?.provenance
    || edge?.attributes?.epistemic_status
    || edge?.attributes?.validation_status
    || ''
  ).trim().toLowerCase()
}

// observed/structural -> solid, inferred -> dashed, speculative/assumed -> dotted
function epistemicDashArray(edge) {
  const token = edgeEpistemicOf(edge)
  if (!token) return undefined
  if (token.includes('observ') || token.includes('structural') || token.includes('confirm') || token.includes('fact')) {
    return undefined
  }
  if (token.includes('specul') || token.includes('assum') || token.includes('hypo')) return '1.5 5'
  if (token.includes('infer') || token.includes('estimat') || token.includes('derive')) return '7 5'
  return undefined
}

function edgeClusterId(edge, endpoint) {
  const attrs = edge?.attributes || {}
  if (endpoint === 'source') {
    return String(attrs.source_region_id || attrs.source_cluster_id || attrs.source_community_id || '').trim()
  }
  return String(attrs.target_region_id || attrs.target_cluster_id || attrs.target_community_id || '').trim()
}

function isIntraClusterSpatialEdge(edge) {
  if (!isSpatialFactEdge(edge)) return false
  const source = edgeClusterId(edge, 'source')
  const target = edgeClusterId(edge, 'target')
  return Boolean(source) && Boolean(target) && source === target
}

function edgeColor(edge, highlighted) {
  if (highlighted) return '#dc2626'
  // M10: spatial skeleton reads faint grey; causal reads channel-colored.
  if (isSpatialFactEdge(edge)) return '#94a3b8'
  const channel = edgeChannelOf(edge)
  if (channel) {
    for (const [token, color] of Object.entries(MAP_CHANNEL_COLORS)) {
      if (channel.includes(token)) return color
    }
  }
  const type = String(edge?.fact_type || edge?.name || '').toLowerCase()
  if (type === 'dynamic_edge') return '#b45309'
  if (type === 'agent_influence' || type === 'influences_region') return '#2563eb'
  if (type.includes('depend') || type.includes('affect') || type.includes('regulat')) return '#7c3aed'
  return '#64748b'
}

function nodeKindPriority(kind) {
  if (kind === 'region') return 0
  if (kind === 'subregion') return 1
  if (kind === 'agent') return 2
  return 3
}

function entityAnimationStatus(entity) {
  return normalizeMapAnimationStatus(entity?.attributes?.animation_status)
}

function entityAnimationProgress(entity) {
  const value = Number(entity?.attributes?.animation_progress ?? 1)
  if (!Number.isFinite(value)) return 1
  return Math.max(0, Math.min(1, value))
}

function nodeVisualState(node, kind, highlighted, synthetic = false) {
  const status = entityAnimationStatus(node)
  const progress = entityAnimationProgress(node)
  const group = nodeGroup(node, kind)
  const baseRadius = nodeRadius(kind, group)
  const baseColor = nodeColor(node, kind, group)
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
  } else if (status === 'hidden') {
    radius = Math.max(1, radius - 2)
    color = '#cbd5e1'
    fillColor = '#cbd5e1'
    weight = 0
    opacity = 0
    fillOpacity = 0
  }

  if (status !== 'hidden') {
    const revealScale = 0.62 + progress * 0.38
    radius *= revealScale
    opacity *= 0.18 + progress * 0.82
    fillOpacity *= 0.18 + progress * 0.82
  }

  if (synthetic && !highlighted && !['hidden', 'new', 'active'].includes(status)) {
    radius = Math.max(2.5, radius * 0.82)
    color = '#64748b'
    fillColor = '#cbd5e1'
    weight = Math.min(weight, 1.1)
    opacity = Math.min(opacity, 0.5)
    fillOpacity = Math.min(fillOpacity, 0.42)
  }

  if (highlighted && status !== 'hidden') {
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
    fillOpacity,
    group
  }
}

function edgeVisualState(edge, highlighted) {
  const status = entityAnimationStatus(edge)
  const progress = entityAnimationProgress(edge)
  // M10: classify so the spatial skeleton stays faint and causal coupling
  // reads bold; intra-cluster spatial edges are further de-emphasized.
  const spatial = isSpatialFactEdge(edge)
  const intraCluster = isIntraClusterSpatialEdge(edge)
  let color = edgeColor(edge, false)
  let weight = spatial ? 0.8 : 1.6
  let opacity = spatial ? (intraCluster ? 0.1 : 0.2) : 0.42
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
  } else if (status === 'hidden') {
    color = '#cbd5e1'
    weight = 0
    opacity = 0
    dashArray = undefined
  }

  if (status !== 'hidden') {
    weight *= 0.55 + progress * 0.45
    opacity *= 0.08 + progress * 0.92
  }

  // M10 epistemic honesty dash, only when the edge is in a steady (non-pulse)
  // state so reveal animation dashes win during playback.
  if (!highlighted && status !== 'new' && status !== 'active' && status !== 'faded') {
    const epistemicDash = epistemicDashArray(edge)
    if (epistemicDash !== undefined) dashArray = epistemicDash
  }

  // Keep the spatial skeleton subdued behind causal structure.
  if (spatial && !highlighted && status !== 'new' && status !== 'active') {
    weight = Math.min(weight, 1)
    opacity = Math.min(opacity, intraCluster ? 0.1 : 0.22)
  }

  if (highlighted && status !== 'hidden') {
    color = '#dc2626'
    weight = 3
    opacity = 0.98
    dashArray = undefined
  }

  return { color, weight, opacity, dashArray }
}

function edgeContextVisualState(edge, schematic = false) {
  if (schematic) {
    return {
      color: '#64748b',
      weight: 1,
      opacity: 0.2,
      dashArray: '3 7'
    }
  }
  const spatial = isSpatialFactEdge(edge)
  const intraCluster = isIntraClusterSpatialEdge(edge)
  return {
    color: spatial ? '#94a3b8' : edgeColor(edge, false),
    weight: spatial ? 0.75 : 1.1,
    opacity: spatial ? (intraCluster ? 0.08 : 0.16) : 0.24,
    dashArray: epistemicDashArray(edge)
  }
}

function edgeGroundingPolicy(sourceNode, targetNode, edge) {
  const sourcePlacement = effectiveNodePlacement(sourceNode)
  const targetPlacement = effectiveNodePlacement(targetNode)
  const curatedFixtureDecision = resolveCuratedFixtureEdgeGrounding(sourceNode, targetNode, edge)
  if (curatedFixtureDecision) return curatedFixtureDecision
  if (sourcePlacement === 'geographic' && targetPlacement === 'geographic') return 'geographic'

  const sourceKind = nodeKind(sourceNode)
  const targetKind = nodeKind(targetNode)
  const regionKinds = new Set(['region', 'subregion'])
  if (regionKinds.has(sourceKind) && regionKinds.has(targetKind)) {
    // A synthetic region layout may retain a quiet relationship overview, but
    // it must never look like a physical route or an animated diffusion path.
    return 'schematic'
  }
  return 'omit'
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
  color: var(--k-color-brand-600);
  background: transparent;
  border: 1px solid var(--k-color-border-strong);
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
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--k-color-border-strong);
  box-shadow: 0 8px 20px rgba(28, 59, 46, 0.08);
  color: var(--k-color-text-secondary);
  font-size: 12px;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

.summary-chip-accent {
  background: rgba(255, 255, 255, 0.92);
  color: var(--k-color-brand-600);
  border-color: var(--k-color-border-strong);
}

.summary-chip-muted {
  color: #475569;
}

.summary-chip-synthetic {
  background: rgba(241, 245, 249, 0.94);
  color: #475569;
  border-color: rgba(148, 163, 184, 0.4);
  border-style: dashed;
}

.summary-chip-mixed {
  background: rgba(254, 252, 232, 0.94);
  color: #854d0e;
  border-color: rgba(202, 138, 4, 0.38);
  border-style: dashed;
}

.summary-chip-quality {
  background: rgba(255, 247, 237, 0.96);
  color: #9a3412;
  border-color: rgba(234, 88, 12, 0.38);
}

.summary-chip-layers {
  background: rgba(255, 255, 255, 0.92);
  color: var(--k-color-text-secondary);
  border-color: var(--k-color-border-strong);
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
