<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <KaleidoNavBrand to="/" />
      </div>

      <div class="header-right">
        <button class="layout-toggle" @click="toggleGraphCollapse">
          {{ viewMode === 'workbench' ? '◧ 展开图谱' : '▣ 收起图谱' }}
        </button>
        <WorkflowStepMenu :current-step="3" current-name="推演播放" />
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <template v-if="graphPanelVisible">
          <GraphPanel
            :graphData="animatedGraphData"
            :mapData="animatedMapProjection"
            :loading="graphLoading"
            :currentPhase="3"
            :isSimulating="isSimulating"
            :highlightNodeIds="graphHighlight.nodeIds"
            :highlightNodeNames="graphHighlight.nodeNames"
            :highlightEdgeIds="graphHighlight.edgeIds"
            :highlightLabel="graphHighlight.label"
            :highlightMode="graphHighlight.mode"
            @refresh="refreshGraph"
            @toggle-maximize="toggleMaximize('graph')"
          />
        </template>
      </div>

      <!-- Right Panel: Step3 开始模拟 -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <Step3Simulation
          :simulationId="currentSimulationId"
          :maxRounds="maxRounds"
          :minutesPerRound="minutesPerRound"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          :initialScenarioMode="route.query.scenario_mode"
          :initialDiffusionTemplate="route.query.diffusion_template"
          :initialSearchMode="route.query.search_mode"
          :initialSimulationArchitecture="route.query.simulation_architecture"
          :animationData="animationData"
          :isReplayOnly="isReplayOnly"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
          @risk-object-focus="updateGraphHighlight"
          @animation-frame-change="handleAnimationFrameChange"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import WorkflowStepMenu from '../components/WorkflowStepMenu.vue'
import GraphPanel from '../components/GraphPanel.vue'
import Step3Simulation from '../components/Step3Simulation.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation, getSimulationAnimation, getSimulationConfig, getSimulationGraphRealtime, stopSimulation, closeSimulationEnv, getEnvStatus } from '../api/simulation'
import { markWorkflowStep } from '../store/workflowNavigation'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  simulationId: String
})

// Layout State
const viewMode = ref('workbench') // Step3 推演：默认内容全宽（早期图谱稀疏、50/50 会空半屏）；一键「展开图谱」看演化

// Data State
const currentSimulationId = ref(route.params.simulationId)
// 直接在初始化时从 query 参数获取 maxRounds，确保子组件能立即获取到值
const maxRounds = ref(route.query.maxRounds ? parseInt(route.query.maxRounds) : null)
const minutesPerRound = ref(30) // 默认每轮30分钟
const projectData = ref(null)
const graphData = ref(null)
const displayGraphData = ref(null)
const mapProjection = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing') // processing | completed | error
const graphHighlight = ref({ nodeIds: [], nodeNames: [], edgeIds: [], label: '', mode: '' })
const animationData = ref(null)
const animationFrame = ref(null)
const isReplayOnly = ref(route.query.replay === '1')

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph' || viewMode.value === 'map') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph' || viewMode.value === 'map') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  return 'Running'
})

const isSimulating = computed(() => currentStatus.value === 'processing')
const graphPanelVisible = computed(() => viewMode.value !== 'workbench')
const shouldRefreshGraph = computed(() => isSimulating.value && graphPanelVisible.value && !isReplayOnly.value)
const animatedGraphData = computed(() => applyAnimationToGraph(displayGraphData.value, animationFrame.value))
const animatedMapProjection = computed(() => applyAnimationToMapProjection(mapProjection.value, animationFrame.value))

const GRAPH_REFRESH_INTERVAL_MS = 7000
const GRAPH_COMPACT_NODE_THRESHOLD = 220
const GRAPH_COMPACT_EDGE_THRESHOLD = 260

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) {
    systemLogs.value.shift()
  }
}

const updateStatus = (status) => {
  currentStatus.value = status
}

const updateGraphHighlight = (payload = {}) => {
  graphHighlight.value = {
    nodeIds: Array.isArray(payload.nodeIds) ? payload.nodeIds : [],
    nodeNames: Array.isArray(payload.nodeNames) ? payload.nodeNames : [],
    edgeIds: Array.isArray(payload.edgeIds) ? payload.edgeIds : [],
    label: payload.label || '',
    mode: payload.mode || ''
  }
}

const handleAnimationFrameChange = (frame = null) => {
  animationFrame.value = frame
  if (!frame) return
  graphHighlight.value = {
    nodeIds: Array.isArray(frame.focus_ids?.node_ids) ? frame.focus_ids.node_ids : [],
    nodeNames: [],
    edgeIds: Array.isArray(frame.focus_ids?.edge_ids) ? frame.focus_ids.edge_ids : [],
    label: frame.narrative?.title || '',
    mode: 'animation'
  }
}

const buildStateMap = (items = []) => {
  const map = new Map()
  ;(Array.isArray(items) ? items : []).forEach((item) => {
    const id = String(item?.id || '')
    if (id) map.set(id, item)
  })
  return map
}

const readNodeId = (node) => String(node?.uuid || node?.id || '')

const readEdgeId = (edge) => String(edge?.uuid || edge?.id || edge?.edge_id || '')

const readEdgeSourceId = (edge) => String(edge?.source_node_uuid || edge?.source || edge?.from || '')

const readEdgeTargetId = (edge) => String(edge?.target_node_uuid || edge?.target || edge?.to || '')

const buildTimelineState = (state = {}, frame = {}, maxDelay = 0, focusIds = new Set()) => {
  const rawStatus = String(state.status || 'steady').toLowerCase()
  const id = String(state.id || '')
  const isFocused = id && focusIds.has(id)
  const participatesInPulse = focusIds.size > 0 ? isFocused : ['new', 'active'].includes(rawStatus)
  const duration = Math.max(800, Number(frame.playback_duration_ms || 1600))
  const elapsed = Math.max(0, Number(frame.playback_elapsed_ms || duration))
  const rawDelay = Math.max(0, Number(state.delay_ms || 0))
  const timelineDelay = maxDelay > 0
    ? Math.round((rawDelay / maxDelay) * duration * 0.72)
    : Math.min(rawDelay, duration * 0.72)
  const revealWindow = Math.max(180, duration * 0.16)
  const progress = rawStatus === 'hidden' || !participatesInPulse
    ? 0
    : Math.max(0, Math.min(1, (elapsed - timelineDelay) / revealWindow))
  const isDue = progress > 0
  // 已建立的背景网络（steady）必须常显（淡）——不能因为"本帧不参与脉冲"被判成 hidden，
  // 否则回放时整张关系网消失、只剩本轮的几个脉冲节点（"显示不出来"的根因）。
  // 只有尚未揭示的 new/active 才在到达各自揭示时刻前暂隐。
  let visualStatus = rawStatus
  let revealProgress = progress
  let due = isDue
  if (rawStatus === 'hidden') {
    visualStatus = 'hidden'
  } else if (rawStatus === 'steady') {
    // 已建立的背景网络：完整可见（不再淡到看不见），脉冲交给 new/active 高亮
    visualStatus = 'steady'
    revealProgress = 1
    due = true
  } else if (!isDue) {
    visualStatus = 'hidden'
  }

  return {
    ...state,
    raw_animation_status: rawStatus,
    status: visualStatus,
    delay_ms: timelineDelay,
    timeline_delay_ms: timelineDelay,
    animation_elapsed_ms: elapsed,
    animation_progress: revealProgress,
    animation_due: due
  }
}

const maxStateDelay = (items = []) => {
  return Math.max(
    0,
    ...(Array.isArray(items) ? items : []).map((item) => Number(item?.delay_ms || 0)).filter(Number.isFinite)
  )
}

const normalizeAnimationNode = (node = {}, index = 0) => {
  const attrs = node.attributes || {}
  const lat = toNumber(node.lat ?? attrs.lat)
  const lon = toNumber(node.lon ?? attrs.lon)
  return {
    ...node,
    uuid: readNodeId(node) || `animation_node_${index}`,
    id: readNodeId(node) || `animation_node_${index}`,
    name: node.name || `Node ${index + 1}`,
    labels: Array.isArray(node.labels) ? node.labels : ['Entity'],
    kind: node.kind || attrs.kind || nodeKindFromNode(node),
    attributes: {
      ...attrs,
      ...(Number.isFinite(lat) ? { lat } : {}),
      ...(Number.isFinite(lon) ? { lon } : {})
    }
  }
}

const normalizeAnimationEdge = (edge = {}, index = 0) => {
  const sourceId = readEdgeSourceId(edge)
  const targetId = readEdgeTargetId(edge)
  const edgeId = readEdgeId(edge) || `${sourceId}->${targetId}:${edge.fact_type || edge.name || 'related'}:${index}`
  return {
    ...edge,
    uuid: edgeId,
    id: edgeId,
    source_node_uuid: sourceId,
    target_node_uuid: targetId,
    name: edge.name || edge.fact_type || 'related_to',
    fact_type: edge.fact_type || edge.name || 'related_to',
    attributes: {
      ...(edge.attributes || {})
    }
  }
}

const buildGraphFromAnimationLayout = (layout = {}) => {
  const nodes = Array.isArray(layout.nodes) ? layout.nodes.map(normalizeAnimationNode) : []
  const nodeIds = new Set(nodes.map((node) => readNodeId(node)).filter(Boolean))
  const edges = (Array.isArray(layout.edges) ? layout.edges : [])
    .map(normalizeAnimationEdge)
    .filter((edge) => nodeIds.has(readEdgeSourceId(edge)) && nodeIds.has(readEdgeTargetId(edge)))
  if (!nodes.length && !edges.length) return null
  return {
    nodes,
    edges,
    meta: {
      source: 'animation_layout',
      node_count: nodes.length,
      edge_count: edges.length
    }
  }
}

const buildMapProjectionFromAnimationLayout = (layout = {}) => {
  const graph = buildGraphFromAnimationLayout(layout)
  if (!graph) return null
  const nodes = graph.nodes
    .filter((node) => Number.isFinite(toNumber(node.attributes?.lat)) && Number.isFinite(toNumber(node.attributes?.lon)))
    .map((node) => ({
      ...node,
      attributes: {
        ...(node.attributes || {}),
        lat: toNumber(node.attributes?.lat),
        lon: toNumber(node.attributes?.lon)
      }
    }))
  const nodeById = new Map(nodes.map((node) => [readNodeId(node), node]))
  const edges = graph.edges
    .filter((edge) => nodeById.has(readEdgeSourceId(edge)) && nodeById.has(readEdgeTargetId(edge)))
    .map((edge) => {
      const sourceNode = nodeById.get(readEdgeSourceId(edge))
      const targetNode = nodeById.get(readEdgeTargetId(edge))
      return {
        ...edge,
        source_lat: sourceNode.attributes.lat,
        source_lon: sourceNode.attributes.lon,
        target_lat: targetNode.attributes.lat,
        target_lon: targetNode.attributes.lon
      }
    })
  return {
    simulation_id: currentSimulationId.value,
    source_mode: 'animation_layout',
    map_seed_id: '',
    center: layout.center || mapProjection.value?.center || { lat: 20, lon: 0 },
    radius_m: Number(layout.radius_m || 0),
    zoom_hint: Number(layout.zoom_hint || 0) || mapProjection.value?.zoom_hint || 9,
    analysis_polygon: layout.analysis_polygon || null,
    layers: Array.isArray(layout.base_layers) ? layout.base_layers : [],
    nodes,
    edges,
    meta: {
      source: 'animation_layout',
      node_count: nodes.length,
      edge_count: edges.length
    }
  }
}

const applyAnimationToGraph = (graph, frame) => {
  if (!graph || !frame) return graph
  const nodeMaxDelay = maxStateDelay(frame.node_states)
  const edgeMaxDelay = maxStateDelay(frame.edge_states)
  const focusNodeIds = new Set((frame.focus_ids?.node_ids || []).map((item) => String(item || '')).filter(Boolean))
  const focusEdgeIds = new Set((frame.focus_ids?.edge_ids || []).map((item) => String(item || '')).filter(Boolean))
  const nodeStates = buildStateMap((frame.node_states || []).map((state) => buildTimelineState(state, frame, nodeMaxDelay, focusNodeIds)))
  const edgeStates = buildStateMap((frame.edge_states || []).map((state) => buildTimelineState(state, frame, edgeMaxDelay, focusEdgeIds)))
  if (!nodeStates.size) return graph
  const nodes = (Array.isArray(graph.nodes) ? graph.nodes : [])
    .map((node) => {
      const nodeId = readNodeId(node)
      const state = nodeStates.get(nodeId) || { status: 'hidden', raw_animation_status: 'hidden', animation_progress: 0 }
      return {
        ...node,
        attributes: {
          ...(node?.attributes || {}),
          animation_status: state.status || 'steady',
          raw_animation_status: state.raw_animation_status,
          first_seen_round: state.first_seen_round,
          last_active_round: state.last_active_round,
          delay_ms: state.delay_ms,
          timeline_delay_ms: state.timeline_delay_ms,
          animation_elapsed_ms: state.animation_elapsed_ms,
          animation_progress: state.animation_progress,
          animation_due: state.animation_due,
          value: state.value,
          delta: state.delta,
          state_status: state.state_status
        }
      }
    })
  const visibleNodeIds = new Set(nodes.map((node) => readNodeId(node)))
  const edges = (Array.isArray(graph.edges) ? graph.edges : [])
    .filter((edge) => {
      const sourceId = readEdgeSourceId(edge)
      const targetId = readEdgeTargetId(edge)
      return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId)
    })
    .map((edge) => {
      const edgeId = readEdgeId(edge)
      const state = edgeStates.get(edgeId) || { status: 'hidden', raw_animation_status: 'hidden', animation_progress: 0 }
      return {
        ...edge,
        attributes: {
          ...(edge?.attributes || {}),
          animation_status: state.status || 'steady',
          raw_animation_status: state.raw_animation_status,
          first_seen_round: state.first_seen_round,
          last_active_round: state.last_active_round,
          delay_ms: state.delay_ms,
          timeline_delay_ms: state.timeline_delay_ms,
          animation_elapsed_ms: state.animation_elapsed_ms,
          animation_progress: state.animation_progress,
          animation_due: state.animation_due,
          value: state.value,
          delta: state.delta,
          state_status: state.state_status
        }
      }
    })
  return {
    ...graph,
    nodes,
    edges,
    meta: {
      ...(graph.meta || {}),
      animation_round: frame.round,
      node_count: nodes.length,
      edge_count: edges.length
    }
  }
}

const applyAnimationToMapProjection = (projection, frame) => {
  if (!projection || !frame) return projection
  const nodeMaxDelay = maxStateDelay(frame.node_states)
  const edgeMaxDelay = maxStateDelay(frame.edge_states)
  const focusNodeIds = new Set((frame.focus_ids?.node_ids || []).map((item) => String(item || '')).filter(Boolean))
  const focusEdgeIds = new Set((frame.focus_ids?.edge_ids || []).map((item) => String(item || '')).filter(Boolean))
  const nodeStates = buildStateMap((frame.node_states || []).map((state) => buildTimelineState(state, frame, nodeMaxDelay, focusNodeIds)))
  const edgeStates = buildStateMap((frame.edge_states || []).map((state) => buildTimelineState(state, frame, edgeMaxDelay, focusEdgeIds)))
  if (!nodeStates.size) return projection
  const nodes = (Array.isArray(projection.nodes) ? projection.nodes : []).map((node) => {
    const state = nodeStates.get(readNodeId(node)) || { status: 'hidden', raw_animation_status: 'hidden', animation_progress: 0 }
    return {
      ...node,
      attributes: {
        ...(node?.attributes || {}),
        animation_status: state.status || 'steady',
        raw_animation_status: state.raw_animation_status,
        first_seen_round: state.first_seen_round,
        last_active_round: state.last_active_round,
        delay_ms: state.delay_ms,
        timeline_delay_ms: state.timeline_delay_ms,
        animation_elapsed_ms: state.animation_elapsed_ms,
        animation_progress: state.animation_progress,
        animation_due: state.animation_due
      }
    }
  })
  const visibleNodeIds = new Set(nodes.map((node) => readNodeId(node)))
  const edges = (Array.isArray(projection.edges) ? projection.edges : []).filter((edge) => {
    const sourceId = readEdgeSourceId(edge)
    const targetId = readEdgeTargetId(edge)
    return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId)
  }).map((edge) => {
    const edgeId = readEdgeId(edge)
    const state = edgeStates.get(edgeId) || { status: 'hidden', raw_animation_status: 'hidden', animation_progress: 0 }
    return {
      ...edge,
      attributes: {
        ...(edge?.attributes || {}),
        animation_status: state.status || 'steady',
        raw_animation_status: state.raw_animation_status,
        first_seen_round: state.first_seen_round,
        last_active_round: state.last_active_round,
        delay_ms: state.delay_ms,
        timeline_delay_ms: state.timeline_delay_ms,
        animation_elapsed_ms: state.animation_elapsed_ms,
        animation_progress: state.animation_progress,
        animation_due: state.animation_due
      }
    }
  })
  return {
    ...projection,
    nodes,
    edges,
    meta: {
      ...(projection.meta || {}),
      animation_round: frame.round,
      node_count: nodes.length,
      edge_count: edges.length
    }
  }
}

const buildGraphSignature = (graph) => {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []
  const nodePart = nodes
    .map((node) => String(node?.uuid || node?.id || ''))
    .filter(Boolean)
    .join('|')
  const edgePart = edges
    .map((edge) => {
      const attrs = edge?.attributes || {}
      return [
        edge?.uuid || edge?.id || '',
        edge?.source_node_uuid || edge?.source || '',
        edge?.target_node_uuid || edge?.target || '',
        edge?.fact_type || edge?.name || '',
        attrs?.status || '',
        attrs?.last_activated_round || attrs?.created_round || '',
        attrs?.strength || '',
        attrs?.confidence || ''
      ].join(':')
    })
    .join('|')
  return `${nodes.length}:${edges.length}:${nodePart}::${edgePart}`
}

const buildMapProjectionSignature = (projection) => {
  if (!projection) return ''
  const nodes = Array.isArray(projection?.nodes) ? projection.nodes : []
  const edges = Array.isArray(projection?.edges) ? projection.edges : []
  const center = projection?.center || {}
  return [
    Number(center.lat || 0).toFixed(5),
    Number(center.lon || 0).toFixed(5),
    nodes.map((node) => `${node?.uuid || ''}:${node?.attributes?.lat || ''}:${node?.attributes?.lon || ''}`).join('|'),
    edges.map((edge) => `${edge?.uuid || ''}:${edge?.source_node_uuid || ''}:${edge?.target_node_uuid || ''}`).join('|')
  ].join('::')
}

const compactGraphForDisplay = (graph) => {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []
  if (nodes.length <= GRAPH_COMPACT_NODE_THRESHOLD && edges.length <= GRAPH_COMPACT_EDGE_THRESHOLD) {
    return graph
  }

  const keyEdges = edges.filter(isKeyEdge)
  const displayEdges = keyEdges.length > 0 ? keyEdges : edges.slice(0, GRAPH_COMPACT_EDGE_THRESHOLD)
  const visibleNodeIds = new Set()
  displayEdges.forEach((edge) => {
    const sourceId = String(edge?.source_node_uuid || edge?.source || '')
    const targetId = String(edge?.target_node_uuid || edge?.target || '')
    if (sourceId) visibleNodeIds.add(sourceId)
    if (targetId) visibleNodeIds.add(targetId)
  })

  const displayNodes = nodes.filter((node) => {
    const nodeId = String(node?.uuid || node?.id || '')
    if (visibleNodeIds.has(nodeId)) return true
    const kind = nodeKindFromNode(node)
    return kind === 'region' || kind === 'subregion'
  })
  const displayNodeIds = new Set(displayNodes.map((node) => String(node?.uuid || node?.id || '')))
  const safeEdges = displayEdges.filter((edge) => {
    const sourceId = String(edge?.source_node_uuid || edge?.source || '')
    const targetId = String(edge?.target_node_uuid || edge?.target || '')
    return displayNodeIds.has(sourceId) && displayNodeIds.has(targetId)
  })

  return {
    ...graph,
    nodes: displayNodes,
    edges: safeEdges,
    meta: {
      ...(graph?.meta || {}),
      display_compacted: true,
      input_node_count: nodes.length,
      input_edge_count: edges.length,
      node_count: displayNodes.length,
      edge_count: safeEdges.length
    }
  }
}

let lastGraphSignature = ''
let lastDisplayGraphSignature = ''
let lastMapProjectionSignature = ''

const applyGraphData = (graph, { compact = false } = {}) => {
  const fullSignature = buildGraphSignature(graph)
  let graphChanged = false
  if (!fullSignature || fullSignature !== lastGraphSignature) {
    graphData.value = graph
    lastGraphSignature = fullSignature
    graphChanged = true
  }

  const nextDisplayGraph = compact ? compactGraphForDisplay(graph) : graph
  const displaySignature = buildGraphSignature(nextDisplayGraph)
  let displayChanged = false
  if (!displaySignature || displaySignature !== lastDisplayGraphSignature) {
    displayGraphData.value = nextDisplayGraph
    lastDisplayGraphSignature = displaySignature
    displayChanged = true
  }

  return graphChanged || displayChanged
}

const applyMapProjection = (projection) => {
  const signature = buildMapProjectionSignature(projection)
  if (signature && signature === lastMapProjectionSignature) return false
  mapProjection.value = projection
  lastMapProjectionSignature = signature
  return true
}

const extractGraphData = (payload) => {
  if (!payload) return null
  if (payload.graph_data) return payload.graph_data
  if (payload.map_graph_data) return payload.map_graph_data
  if (payload.map_graph?.graph_data) return payload.map_graph.graph_data
  if (payload.map_graph) return payload.map_graph
  if (payload.graph) return payload.graph
  return payload
}

const KEY_RELATION_TOKENS = new Set([
  'dynamic_edge',
  'agent_influence',
  'influences_region',
  'depends_on',
  'affects',
  'exposed_to',
  'regulates',
  'monitors',
  'uses',
  'supports',
  'blocks',
  'collaborates_with'
])

const NON_KEY_RELATION_TOKENS = new Set([
  'agent_anchor',
  'region_neighbor',
  'region_hierarchy',
  'belongs_to',
  'neighbor_of'
])

const toNumber = (value) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

const nodeKindFromNode = (node) => {
  const nodeId = String(node?.uuid || '')
  if (nodeId.startsWith('region::')) return 'region'
  if (nodeId.startsWith('subregion::')) return 'subregion'
  if (nodeId.startsWith('agent::')) return 'agent'
  const labels = (Array.isArray(node?.labels) ? node.labels : []).map((item) => String(item).toLowerCase())
  if (labels.includes('subregion')) return 'subregion'
  if (labels.includes('region')) return 'region'
  if (labels.includes('humanactor') || labels.includes('governmentactor') || labels.includes('organizationactor')) return 'agent'
  return 'entity'
}

const isKeyEdge = (edge) => {
  const factType = String(edge?.fact_type || '').toLowerCase()
  const name = String(edge?.name || '').toLowerCase()
  const attrs = edge?.attributes || {}
  if (attrs?.is_key_interaction) return true
  if (KEY_RELATION_TOKENS.has(factType) || KEY_RELATION_TOKENS.has(name)) return true
  if (NON_KEY_RELATION_TOKENS.has(factType) || NON_KEY_RELATION_TOKENS.has(name)) return false
  if (String(attrs?.kind || '').toLowerCase() === 'structural_agent_relationship') {
    const strength = Number(attrs?.strength || 0)
    return strength >= 0.45 || Boolean(attrs?.interaction_channel)
  }
  const confidence = Number(attrs?.confidence || 0)
  return confidence >= 0.68
}

const buildMapProjectionFallback = ({ graph, layersPayload = null, sourceMode = 'graph', mapSeedId = '' }) => {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []
  const projectedNodes = []
  const nodeCoordById = new Map()

  nodes.forEach((node, index) => {
    const attrs = node?.attributes || {}
    const lat = toNumber(attrs?.lat)
    const lon = toNumber(attrs?.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    const normalized = {
      uuid: node?.uuid || node?.id || `node_${index}`,
      name: node?.name || `Node ${index + 1}`,
      labels: Array.isArray(node?.labels) ? node.labels : [],
      summary: node?.summary || '',
      kind: node?.kind || nodeKindFromNode(node),
      attributes: {
        ...attrs,
        lat,
        lon
      }
    }
    projectedNodes.push(normalized)
    nodeCoordById.set(String(normalized.uuid), normalized)
  })

  const projectedEdges = []
  edges.forEach((edge, index) => {
    const sourceId = String(edge?.source_node_uuid || edge?.source || '')
    const targetId = String(edge?.target_node_uuid || edge?.target || '')
    const sourceNode = nodeCoordById.get(sourceId)
    const targetNode = nodeCoordById.get(targetId)
    if (!sourceNode || !targetNode) return
    const keyInteraction = isKeyEdge(edge)
    if (!keyInteraction) return
    projectedEdges.push({
      uuid: edge?.uuid || edge?.id || `edge_${index}`,
      name: edge?.name || edge?.fact_type || 'related_to',
      fact_type: edge?.fact_type || edge?.name || 'related_to',
      fact: edge?.fact || '',
      source_node_uuid: sourceId,
      target_node_uuid: targetId,
      source_lat: sourceNode.attributes.lat,
      source_lon: sourceNode.attributes.lon,
      target_lat: targetNode.attributes.lat,
      target_lon: targetNode.attributes.lon,
      attributes: { ...(edge?.attributes || {}), is_key_interaction: true },
      is_key_interaction: true
    })
  })

  let center = null
  if (layersPayload?.center) {
    const lat = toNumber(layersPayload.center.lat)
    const lon = toNumber(layersPayload.center.lon)
    if (Number.isFinite(lat) && Number.isFinite(lon)) center = { lat, lon }
  }
  if (!center && projectedNodes.length > 0) {
    const lat = projectedNodes.reduce((sum, item) => sum + item.attributes.lat, 0) / projectedNodes.length
    const lon = projectedNodes.reduce((sum, item) => sum + item.attributes.lon, 0) / projectedNodes.length
    center = { lat, lon }
  }
  if (!center) center = { lat: 20, lon: 0 }

  return {
    simulation_id: currentSimulationId.value,
    source_mode: sourceMode || 'graph',
    map_seed_id: mapSeedId || '',
    center,
    radius_m: Number(layersPayload?.radius_m || 0),
    zoom_hint: Number(layersPayload?.radius_m || 0) > 0 ? 10 : 9,
    analysis_polygon: layersPayload?.analysis_polygon || null,
    layers: Array.isArray(layersPayload?.layers) ? layersPayload.layers : [],
    nodes: projectedNodes,
    edges: projectedEdges,
    meta: {
      key_edges_only: true,
      input_node_count: nodes.length,
      input_edge_count: edges.length,
      node_count: projectedNodes.length,
      edge_count: projectedEdges.length,
      key_edge_count: projectedEdges.length
    }
  }
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

// 收起/展开左侧图谱：收起后右栏内容全宽铺开（解决 50/50 挤压）
const toggleGraphCollapse = () => {
  viewMode.value = viewMode.value === 'workbench' ? 'split' : 'workbench'
}

const handleGoBack = async () => {
  // 在返回 Step 2 之前，先关闭正在运行的模拟
  addLog('准备返回 Step 2，正在关闭模拟...')
  
  // 停止轮询
  stopGraphRefresh()
  
  try {
    // 先尝试优雅关闭模拟环境
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      addLog('正在关闭模拟环境...')
      try {
        await closeSimulationEnv({ 
          simulation_id: currentSimulationId.value,
          timeout: 10
        })
        addLog('✓ 模拟环境已关闭')
      } catch (closeErr) {
        addLog(`关闭模拟环境失败，尝试强制停止...`)
        try {
          await stopSimulation({ simulation_id: currentSimulationId.value })
          addLog('✓ 模拟已强制停止')
        } catch (stopErr) {
          addLog(`强制停止失败: ${stopErr.message}`)
        }
      }
    } else {
      // 环境未运行，检查是否需要停止进程
      if (isSimulating.value) {
        addLog('正在停止模拟进程...')
        try {
          await stopSimulation({ simulation_id: currentSimulationId.value })
          addLog('✓ 模拟已停止')
        } catch (err) {
          addLog(`停止模拟失败: ${err.message}`)
        }
      }
    }
  } catch (err) {
    addLog(`检查模拟状态失败: ${err.message}`)
  }
  
  // 返回到 Step 2 (环境搭建)
  const query = {}
  if (route.query.scenario_mode) query.scenario_mode = route.query.scenario_mode
  if (route.query.diffusion_template) query.diffusion_template = route.query.diffusion_template
  if (route.query.search_mode) query.search_mode = route.query.search_mode
  if (route.query.simulation_architecture) query.simulation_architecture = route.query.simulation_architecture
  if (route.query.temporal_preset) query.temporal_preset = route.query.temporal_preset
  if (route.query.reference_time) query.reference_time = route.query.reference_time
  if (route.query.maxRounds) query.maxRounds = route.query.maxRounds
  router.push({ name: 'Simulation', params: { simulationId: currentSimulationId.value }, query })
}

const handleNextStep = () => {
  // Step3Simulation 组件会直接处理报告生成和路由跳转
  // 这个方法仅作为备用
  addLog('进入 Step 4: 报告生成')
}

// --- Data Logic ---
const loadSimulationData = async () => {
  try {
    addLog(`加载模拟数据: ${currentSimulationId.value}`)
    
    // 获取 simulation 信息
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      const simData = simRes.data
      isReplayOnly.value = Boolean(simData.is_replay_only || route.query.replay === '1')
      if (isReplayOnly.value) {
        currentStatus.value = 'completed'
      }
      let graphLoaded = false

      try {
        const realtimeRes = await getSimulationGraphRealtime(currentSimulationId.value, {
          include_map: 1,
          key_edges_only: 1
        })
        if (realtimeRes.success) {
          const realtimeGraph = extractGraphData(realtimeRes.data)
          if (realtimeGraph) {
            applyGraphData(realtimeGraph, { compact: true })
            graphLoaded = true
            addLog('实时图谱加载成功')
          }
          if (realtimeRes.data?.map_projection) {
            applyMapProjection(realtimeRes.data.map_projection)
          }
        }
      } catch (realtimeErr) {
        console.warn('实时图谱加载失败:', realtimeErr)
      }
      
      // 获取 simulation config 以获取 minutes_per_round
      try {
        const configRes = await getSimulationConfig(currentSimulationId.value)
        if (configRes.success && configRes.data?.time_config?.minutes_per_round) {
          minutesPerRound.value = configRes.data.time_config.minutes_per_round
          addLog(`时间配置: 每轮 ${minutesPerRound.value} 分钟`)
        }
      } catch (configErr) {
        addLog(`获取时间配置失败，使用默认值: ${minutesPerRound.value}分钟/轮`)
      }
      
      // 获取 project 信息
      if (simData.project_id) {
        const projRes = await getProject(simData.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          addLog(`项目加载成功: ${projRes.data.project_id}`)
          
          // 获取 graph 数据
          if (!graphLoaded && projRes.data.graph_id) {
            await loadGraph(projRes.data.graph_id)
            graphLoaded = true
          }
        }
      }

      if (!graphLoaded) {
        applyMapSeedGraph(simData)
      }
      if (!mapProjection.value) {
        applyMapProjection(buildMapProjectionFallback({
          graph: graphData.value,
          layersPayload: simData?.map_layers || null,
          sourceMode: simData?.source_mode || 'graph',
          mapSeedId: simData?.map_seed_id || ''
        }))
      }
      await loadAnimationData()
    } else {
      addLog(`加载模拟数据失败: ${simRes.error || '未知错误'}`)
    }
  } catch (err) {
    addLog(`加载异常: ${err.message}`)
  }
}

const loadAnimationData = async () => {
  if (!currentSimulationId.value) return
  try {
    const res = await getSimulationAnimation(currentSimulationId.value)
    if (res.success && res.data) {
      animationData.value = res.data
      const animationGraph = buildGraphFromAnimationLayout(res.data.layout || {})
      if (animationGraph) {
        applyGraphData(animationGraph, { compact: false })
        const animationProjection = buildMapProjectionFromAnimationLayout(res.data.layout || {})
        if (animationProjection) {
          applyMapProjection(animationProjection)
        }
      }
      const firstFrame = Array.isArray(res.data.frames) ? res.data.frames[0] : null
      handleAnimationFrameChange(firstFrame)
      addLog(`动画数据加载成功：${res.data.frames?.length || 0} 帧`)
    }
  } catch (err) {
    if (isReplayOnly.value) {
      addLog(`动画数据加载失败: ${err.message}`)
    }
  }
}

const applyMapSeedGraph = (simData) => {
  const mapGraph = simData?.map_graph_data || simData?.map_graph?.graph_data || simData?.map_graph
  if (!mapGraph) {
    if (!isSimulating.value && simData?.source_mode === 'map_seed') {
      addLog('地图图谱尚未就绪')
    }
    return false
  }

  applyGraphData(mapGraph, { compact: true })
  applyMapProjection(buildMapProjectionFallback({
    graph: mapGraph,
    layersPayload: simData?.map_layers || null,
    sourceMode: simData?.source_mode || 'map_seed',
    mapSeedId: simData?.map_seed_id || ''
  }))
  if (!isSimulating.value) {
    addLog('地图图谱加载成功')
  }
  return true
}

const loadGraph = async (graphId) => {
  // 当正在模拟时，自动刷新不显示全屏 loading，以免闪烁
  // 手动刷新或初始加载时显示 loading
  if (!isSimulating.value) {
    graphLoading.value = true
  }
  
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      applyGraphData(res.data, { compact: true })
      applyMapProjection(buildMapProjectionFallback({
        graph: res.data,
        layersPayload: null,
        sourceMode: 'graph'
      }))
      if (!isSimulating.value) {
        addLog('图谱数据加载成功')
      }
    }
  } catch (err) {
    addLog(`图谱加载失败: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = async () => {
  if (graphRefreshInFlight) return
  graphRefreshInFlight = true

  try {
    const realtimeRes = await getSimulationGraphRealtime(currentSimulationId.value, {
      include_map: 1,
      key_edges_only: 1
    })
    if (realtimeRes.success) {
      const realtimeGraph = extractGraphData(realtimeRes.data)
      if (realtimeGraph) {
        const graphChanged = applyGraphData(realtimeGraph, { compact: true })
        if (realtimeRes.data?.map_projection) {
          applyMapProjection(realtimeRes.data.map_projection)
        } else {
          applyMapProjection(buildMapProjectionFallback({
            graph: realtimeGraph,
            layersPayload: null,
            sourceMode: 'graph'
          }))
        }
        if (graphChanged && !isSimulating.value) {
          addLog('实时图谱刷新成功')
        }
        return
      }
    }

    if (projectData.value?.graph_id) {
      await loadGraph(projectData.value.graph_id)
      return
    }

    if (!isSimulating.value) {
      graphLoading.value = true
    }

    const simRes = await getSimulation(currentSimulationId.value)
    if (!simRes.success || !applyMapSeedGraph(simRes.data)) {
      if (!isSimulating.value) {
        addLog('当前模拟没有可刷新的图谱数据')
      }
    }
  } catch (err) {
    addLog(`地图图谱刷新失败: ${err.message}`)
  } finally {
    graphLoading.value = false
    graphRefreshInFlight = false
  }
}

// --- Auto Refresh Logic ---
let graphRefreshTimer = null
let graphRefreshInFlight = false

const startGraphRefresh = () => {
  if (graphRefreshTimer) return
  addLog(`开启图谱实时刷新 (${Math.round(GRAPH_REFRESH_INTERVAL_MS / 1000)}s)`)
  refreshGraph()
  graphRefreshTimer = setInterval(refreshGraph, GRAPH_REFRESH_INTERVAL_MS)
}

const stopGraphRefresh = () => {
  if (graphRefreshTimer) {
    clearInterval(graphRefreshTimer)
    graphRefreshTimer = null
    addLog('停止图谱实时刷新')
  }
}

watch(shouldRefreshGraph, (newValue) => {
  if (newValue) {
    startGraphRefresh()
  } else {
    stopGraphRefresh()
  }
}, { immediate: true })

onMounted(() => {
  addLog('SimulationRunView 初始化')
  markWorkflowStep(2, {
    visited: true,
    status: 'done',
    summary: '场景配置已完成',
    route: { name: 'Simulation', params: { simulationId: currentSimulationId.value }, query: { ...route.query } }
  })
  markWorkflowStep(3, {
    visited: true,
    status: 'active',
    summary: '推演播放中',
    route: { name: 'SimulationRun', params: { simulationId: currentSimulationId.value }, query: { ...route.query } }
  })
  
  if (route.query.scenario_mode) {
    addLog(`场景模式: ${route.query.scenario_mode}`)
  }
  if (route.query.hazard_template_id) {
    addLog(`危机模板: ${route.query.hazard_template_id}`)
  }
  if (route.query.diffusion_template) {
    addLog(`主传播族: ${route.query.diffusion_template}`)
  }
  if (route.query.search_mode) {
    addLog(`搜索模式: ${route.query.search_mode}`)
  }
  if (route.query.simulation_architecture) {
    addLog(`推演架构: ${route.query.simulation_architecture}`)
  }
  if (route.query.temporal_preset) {
    addLog(`时间尺度: ${route.query.temporal_preset}`)
  }
  if (route.query.reference_time) {
    addLog(`参考时间: ${route.query.reference_time}`)
  }

  // 记录 maxRounds 配置（值已在初始化时从 query 参数获取）
  if (maxRounds.value) {
    addLog(`自定义模拟轮数: ${maxRounds.value}`)
  }
  
  loadSimulationData()
})

onUnmounted(() => {
  stopGraphRefresh()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  flex: 0 0 60px;
  height: 60px;
  border-bottom: 1px solid rgba(16, 35, 29, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: rgba(244, 246, 241, 0.92);
  backdrop-filter: blur(14px);
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.view-switcher {
  display: flex;
  background: rgba(255, 255, 255, 0.78);
  padding: 4px;
  border: 1px solid rgba(16, 35, 29, 0.08);
  border-radius: 10px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 6px 16px rgba(16, 35, 29, 0.08);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.layout-toggle {
  border: 1px solid rgba(16, 35, 29, 0.12);
  background: rgba(255, 255, 255, 0.78);
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #10231D;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
  font-family: inherit;
  white-space: nowrap;
}

.layout-toggle:hover {
  background: #FFF;
  box-shadow: 0 4px 12px rgba(16, 35, 29, 0.1);
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1 1 auto;
  display: flex;
  position: relative;
  min-height: 0;
  height: calc(100vh - 60px);
  overflow: hidden;
}

.panel-wrapper {
  min-height: 0;
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  height: 100%;
  border-right: 1px solid #EAEAEA;
}

.panel-wrapper.right {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
