<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <KaleidoNavBrand to="/" />
      </div>
      
      <div class="header-center">
        <div class="view-switcher">
          <button 
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: '图谱', split: '双栏', workbench: '工作台' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step 2/5</span>
          <span class="step-name">场景设计</span>
        </div>
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
        <GraphPanel
          :graphData="graphData"
          :mapData="mapProjection"
          :loading="graphLoading"
          :currentPhase="2"
          :highlightNodeIds="graphHighlight.nodeIds"
          :highlightNodeNames="graphHighlight.nodeNames"
          :highlightEdgeIds="graphHighlight.edgeIds"
          :highlightLabel="graphHighlight.label"
          :highlightMode="graphHighlight.mode"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step2 环境搭建 -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <Step2EnvSetup
          :simulationId="currentSimulationId"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          :initialScenarioMode="route.query.scenario_mode"
          :initialDiffusionTemplate="route.query.diffusion_template"
          :initialSearchMode="route.query.search_mode"
          :initialInjectedVariables="initialInjectedVariables"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStatus"
          @risk-object-focus="updateGraphHighlight"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import GraphPanel from '../components/GraphPanel.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { getProject, getGraphData } from '../api/graph'
import { getSimulation, getSimulationGraphRealtime, stopSimulation, getEnvStatus, closeSimulationEnv } from '../api/simulation'
import { getSceneSeedContextBySimulation } from '../store/sceneSeedBridge'

const route = useRoute()
const router = useRouter()

// Props
const props = defineProps({
  simulationId: String
})

// Layout State
const viewMode = ref('split')

// Data State
const currentSimulationId = ref(route.params.simulationId)
const projectData = ref(null)
const graphData = ref(null)
const mapProjection = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('idle') // idle | processing | completed | error
const graphHighlight = ref({ nodeIds: [], nodeNames: [], edgeIds: [], label: '', mode: '' })
const initialInjectedVariables = ref([])
const sceneSeedContext = ref(null)

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  return currentStatus.value
})

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Ready'
  if (currentStatus.value === 'idle') return 'Idle'
  return 'Preparing'
})

const isPreparing = computed(() => currentStatus.value === 'processing')

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 100) {
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
  if (!center) {
    center = resolveSceneSeedCenter()
  }
  if (!center && projectedNodes.length > 0) {
    const lat = projectedNodes.reduce((sum, item) => sum + item.attributes.lat, 0) / projectedNodes.length
    const lon = projectedNodes.reduce((sum, item) => sum + item.attributes.lon, 0) / projectedNodes.length
    center = { lat, lon }
  }
  if (!center) center = inferKnownMapCenter({ graph, project: projectData.value }) || { lat: 20, lon: 0 }

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

const resolveSceneSeedCenter = () => {
  const point = sceneSeedContext.value?.selectedPoints?.[0]
  const lat = toNumber(point?.lat)
  const lon = toNumber(point?.lon)
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    return { lat, lon }
  }
  return null
}

const inferKnownMapCenter = ({ graph, project }) => {
  const tokens = [
    project?.project_name,
    project?.simulation_requirement,
    project?.extracted_text,
    ...(Array.isArray(graph?.nodes) ? graph.nodes.flatMap((node) => [
      node?.name,
      node?.summary,
      ...(Array.isArray(node?.labels) ? node.labels : [])
    ]) : [])
  ].filter(Boolean).join(' ')

  if (/南沙|Nansha|珠江口|Pearl River|广州|Guangzhou/i.test(tokens)) {
    return { lat: 22.7946, lon: 113.5531 }
  }
  return null
}

const normalizeMapProjection = (projection, graph) => {
  if (!projection) return projection
  const desiredCenter = resolveSceneSeedCenter() || inferKnownMapCenter({ graph, project: projectData.value })
  if (!desiredCenter) return projection

  const currentLat = toNumber(projection.center?.lat)
  const currentLon = toNumber(projection.center?.lon)
  if (!Number.isFinite(currentLat) || !Number.isFinite(currentLon)) {
    return { ...projection, center: desiredCenter }
  }

  const hasMapSeedContext = Boolean(projection.meta?.has_map_seed_context || projection.map_seed_id)
  const distanceFromDesired = haversineKm(currentLat, currentLon, desiredCenter.lat, desiredCenter.lon)
  if (hasMapSeedContext || distanceFromDesired < 30) return projection

  const latDelta = desiredCenter.lat - currentLat
  const lonDelta = desiredCenter.lon - currentLon
  return {
    ...projection,
    center: desiredCenter,
    nodes: (projection.nodes || []).map((node) => {
      const attrs = node?.attributes || {}
      const lat = toNumber(attrs.lat)
      const lon = toNumber(attrs.lon)
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return node
      return {
        ...node,
        attributes: {
          ...attrs,
          lat: Number((lat + latDelta).toFixed(6)),
          lon: Number((lon + lonDelta).toFixed(6))
        }
      }
    }),
    edges: (projection.edges || []).map((edge) => ({
      ...edge,
      source_lat: shiftCoord(edge.source_lat, latDelta),
      source_lon: shiftCoord(edge.source_lon, lonDelta),
      target_lat: shiftCoord(edge.target_lat, latDelta),
      target_lon: shiftCoord(edge.target_lon, lonDelta)
    })),
    meta: {
      ...(projection.meta || {}),
      center_rebased_from: { lat: currentLat, lon: currentLon },
      center_rebased_reason: 'scene_seed_or_known_location'
    }
  }
}

const shiftCoord = (value, delta) => {
  const number = toNumber(value)
  return Number.isFinite(number) ? Number((number + delta).toFixed(6)) : value
}

const haversineKm = (lat1, lon1, lat2, lon2) => {
  const toRad = (value) => (value * Math.PI) / 180
  const earthKm = 6371
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return earthKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

let graphRefreshTimer = null
let graphRefreshInFlight = false

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleGoBack = () => {
  // 返回到 process 页面
  if (projectData.value?.project_id) {
    router.push({ name: 'Process', params: { projectId: projectData.value.project_id } })
  } else {
    router.push('/')
  }
}

const handleNextStep = (params = {}) => {
  addLog('进入 Step 3: 开始模拟')
  
  if (params.scenarioMode) {
    addLog(`场景模式: ${params.scenarioMode}`)
  }

  if (params.diffusionTemplate) {
    addLog(`扩散模板: ${params.diffusionTemplate}`)
  }

  if (params.searchMode) {
    addLog(`搜索模式: ${params.searchMode}`)
  }

  if (params.temporalPreset) {
    addLog(`时间尺度: ${params.temporalPreset}`)
  }

  if (params.minutesPerRound) {
    addLog(`每轮时长: ${params.minutesPerRound} 分钟`)
  }

  if (params.referenceTime) {
    addLog(`参考时间: ${params.referenceTime}`)
  }

  if (params.variableCount !== undefined) {
    addLog(`中途变量数: ${params.variableCount}`)
  }

  // 记录模拟轮数配置
  if (params.maxRounds) {
    addLog(`自定义模拟轮数: ${params.maxRounds} 轮`)
  } else {
    addLog('使用自动配置的模拟轮数')
  }
  
  // 构建路由参数
  const routeParams = {
    name: 'SimulationRun',
    params: { simulationId: currentSimulationId.value }
  }
  
  const query = {}
  if (params.maxRounds) query.maxRounds = params.maxRounds
  if (params.scenarioMode) query.scenario_mode = params.scenarioMode
  if (params.hazardTemplateId) query.hazard_template_id = params.hazardTemplateId
  if (params.diffusionTemplate) query.diffusion_template = params.diffusionTemplate
  if (params.searchMode) query.search_mode = params.searchMode
  if (params.temporalPreset) query.temporal_preset = params.temporalPreset
  if (params.referenceTime) query.reference_time = params.referenceTime
  if (params.variableCount !== undefined) query.variable_count = params.variableCount
  if (Object.keys(query).length > 0) routeParams.query = query
  
  // 跳转到 Step 3 页面
  router.push(routeParams)
}

// --- Data Logic ---

/**
 * 检查并关闭正在运行的模拟
 * 当用户从 Step 3 返回到 Step 2 时，默认用户要退出模拟
 */
const checkAndStopRunningSimulation = async () => {
  if (!currentSimulationId.value) return
  
  try {
    // 先检查模拟环境是否存活
    const envStatusRes = await getEnvStatus({ simulation_id: currentSimulationId.value })
    
    if (envStatusRes.success && envStatusRes.data?.env_alive) {
      addLog('检测到模拟环境正在运行，正在关闭...')
      
      // 尝试优雅关闭模拟环境
      try {
        const closeRes = await closeSimulationEnv({ 
          simulation_id: currentSimulationId.value,
          timeout: 10  // 10秒超时
        })
        
        if (closeRes.success) {
          addLog('✓ 模拟环境已关闭')
        } else {
          addLog(`关闭模拟环境失败: ${closeRes.error || '未知错误'}`)
          // 如果优雅关闭失败，尝试强制停止
          await forceStopSimulation()
        }
      } catch (closeErr) {
        addLog(`关闭模拟环境异常: ${closeErr.message}`)
        // 如果优雅关闭异常，尝试强制停止
        await forceStopSimulation()
      }
    } else {
      // 环境未运行，但可能进程还在，检查模拟状态
      const simRes = await getSimulation(currentSimulationId.value)
      if (simRes.success && simRes.data?.status === 'running') {
        addLog('检测到模拟状态为运行中，正在停止...')
        await forceStopSimulation()
      }
    }
  } catch (err) {
    // 检查环境状态失败不影响后续流程
    console.warn('检查模拟状态失败:', err)
  }
}

/**
 * 强制停止模拟
 */
const forceStopSimulation = async () => {
  try {
    const stopRes = await stopSimulation({ simulation_id: currentSimulationId.value })
    if (stopRes.success) {
      addLog('✓ 模拟已强制停止')
    } else {
      addLog(`强制停止模拟失败: ${stopRes.error || '未知错误'}`)
    }
  } catch (err) {
    addLog(`强制停止模拟异常: ${err.message}`)
  }
}

const loadSimulationData = async () => {
  try {
    addLog(`加载模拟数据: ${currentSimulationId.value}`)
    sceneSeedContext.value = getSceneSeedContextBySimulation(currentSimulationId.value)
    initialInjectedVariables.value = sceneSeedContext.value?.initialVariables || []
    
    // 获取 simulation 信息
    const simRes = await getSimulation(currentSimulationId.value)
    if (simRes.success && simRes.data) {
      const simData = simRes.data
      let graphLoaded = false

      try {
        const realtimeRes = await getSimulationGraphRealtime(currentSimulationId.value, {
          include_map: 1,
          key_edges_only: 1
        })
        if (realtimeRes.success) {
          const realtimeGraph = extractGraphData(realtimeRes.data)
          if (realtimeGraph) {
            graphData.value = realtimeGraph
            graphLoaded = true
            addLog('实时图谱加载成功')
          }
          if (realtimeRes.data?.map_projection) {
            mapProjection.value = normalizeMapProjection(realtimeRes.data.map_projection, realtimeGraph)
          }
        }
      } catch (realtimeErr) {
        console.warn('实时图谱加载失败:', realtimeErr)
      }
      
      // 获取 project 信息
      if (simData.project_id) {
        const projRes = await getProject(simData.project_id)
        if (projRes.success && projRes.data) {
          projectData.value = projRes.data
          if (mapProjection.value) {
            mapProjection.value = normalizeMapProjection(mapProjection.value, graphData.value)
          }
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
        mapProjection.value = normalizeMapProjection(buildMapProjectionFallback({
          graph: graphData.value,
          layersPayload: simData?.map_layers || null,
          sourceMode: simData?.source_mode || 'graph',
          mapSeedId: simData?.map_seed_id || ''
        }), graphData.value)
      }
    } else {
      addLog(`加载模拟数据失败: ${simRes.error || '未知错误'}`)
    }
  } catch (err) {
    addLog(`加载异常: ${err.message}`)
  }
}

const applyMapSeedGraph = (simData) => {
  const mapGraph = simData?.map_graph_data || simData?.map_graph?.graph_data || simData?.map_graph
  if (!mapGraph) {
    if (simData?.source_mode === 'map_seed') {
      addLog('地图图谱尚未就绪')
    }
    return false
  }

  graphData.value = mapGraph
  mapProjection.value = normalizeMapProjection(buildMapProjectionFallback({
    graph: mapGraph,
    layersPayload: simData?.map_layers || null,
    sourceMode: simData?.source_mode || 'map_seed',
    mapSeedId: simData?.map_seed_id || ''
  }), mapGraph)
  addLog('地图图谱加载成功')
  return true
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      mapProjection.value = normalizeMapProjection(buildMapProjectionFallback({
        graph: res.data,
        layersPayload: null,
        sourceMode: 'graph'
      }), res.data)
      addLog('图谱数据加载成功')
    }
  } catch (err) {
    addLog(`图谱加载失败: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = async (options = {}) => {
  const { silent = false } = options
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
        graphData.value = realtimeGraph
        if (!silent) {
          addLog('实时图谱刷新成功')
        }
        if (realtimeRes.data?.map_projection) {
          mapProjection.value = normalizeMapProjection(realtimeRes.data.map_projection, realtimeGraph)
        } else {
          mapProjection.value = normalizeMapProjection(buildMapProjectionFallback({
            graph: realtimeGraph,
            layersPayload: null,
            sourceMode: 'graph'
          }), realtimeGraph)
        }
        graphRefreshInFlight = false
        return
      }
    }
  } catch (realtimeErr) {
    console.warn('实时图谱刷新失败:', realtimeErr)
  }

  if (projectData.value?.graph_id) {
    await loadGraph(projectData.value.graph_id)
    graphRefreshInFlight = false
    return
  }

  graphLoading.value = true
  try {
    const simRes = await getSimulation(currentSimulationId.value)
    if (!simRes.success || !applyMapSeedGraph(simRes.data)) {
      if (!silent) {
        addLog('当前模拟没有可刷新的图谱数据')
      }
    }
  } catch (err) {
    if (!silent) {
      addLog(`地图图谱刷新失败: ${err.message}`)
    }
  } finally {
    graphLoading.value = false
    graphRefreshInFlight = false
  }
}

const startGraphRefresh = () => {
  if (graphRefreshTimer) return
  refreshGraph({ silent: true })
  graphRefreshTimer = setInterval(() => {
    refreshGraph({ silent: true })
  }, 2200)
}

const stopGraphRefresh = () => {
  if (!graphRefreshTimer) return
  clearInterval(graphRefreshTimer)
  graphRefreshTimer = null
}

watch(
  isPreparing,
  (active) => {
    if (active) {
      startGraphRefresh()
    } else {
      stopGraphRefresh()
    }
  },
  { immediate: true }
)

onMounted(async () => {
  addLog('SimulationView 初始化')
  
  // 检查并关闭正在运行的模拟（用户从 Step 3 返回时）
  await checkAndStopRunningSimulation()
  
  // 加载模拟数据
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

.status-indicator.idle .dot { background: #B0B8C7; }
.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid #EAEAEA;
}
</style>
