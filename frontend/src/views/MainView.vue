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
        <WorkflowStepMenu :current-step="currentStep" :current-name="stepNames[currentStep - 1]" />
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
          :currentPhase="currentPhase"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step Components -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <!-- Step 2: 场景设计 -->
        <Step2EnvSetup
          v-if="currentStep === 2"
          :simulationId="currentSimulationId"
          :projectData="projectData"
          :graphData="graphData"
          :systemLogs="systemLogs"
          :initialInjectedVariables="initialInjectedVariables"
          @go-back="handleGoBack"
          @next-step="handleNextStep"
          @add-log="addLog"
          @update-status="updateStepStatus"
        />
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import WorkflowStepMenu from '../components/WorkflowStepMenu.vue'
import GraphPanel from '../components/GraphPanel.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { generateOntology, getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { createSimulation, getSimulationGraphRealtime, listSimulations } from '../api/simulation'
import { attachSceneSeedContextToProject, attachSceneSeedContextToSimulation, getSceneSeedContextByProject } from '../store/sceneSeedBridge'
import { markWorkflowStep } from '../store/workflowNavigation'

const route = useRoute()
const router = useRouter()

// Layout State
const viewMode = ref('split') // graph | split | workbench

// Step State
const currentStep = ref(2) // 1: 背景生成, 2: 场景设计, 3: 开始模拟, 4: 报告互动
const stepNames = ['背景生成', '场景设计', '开始模拟', '报告互动']

// Data State
const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const realtimeMapProjection = ref(null)
const currentSimulationId = ref('')
const initialInjectedVariables = ref([])
const stepStatus = ref('idle')
const currentPhase = ref(-1) // -1: Upload, 0: Ontology, 1: Build, 2: Complete
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])

const extractLatLonFromText = (value) => {
  const text = String(value || '')
  const match = text.match(/(-?\d{1,2}(?:\.\d+)?)\s*[,，]\s*(-?\d{1,3}(?:\.\d+)?)/)
  if (!match) return null
  const lat = Number(match[1])
  const lon = Number(match[2])
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return { lat, lon }
}

const extractNodeLatLon = (node) => {
  const attrs = node?.attributes || node?.properties || {}
  const directLat = Number(attrs.lat ?? attrs.latitude ?? node?.lat ?? node?.latitude)
  const directLon = Number(attrs.lon ?? attrs.lng ?? attrs.longitude ?? node?.lon ?? node?.lng ?? node?.longitude)
  if (Number.isFinite(directLat) && Number.isFinite(directLon)) {
    return { lat: directLat, lon: directLon }
  }

  const candidates = [
    attrs.location,
    attrs.region_name,
    attrs.address,
    node?.summary,
    node?.name
  ]
  for (const candidate of candidates) {
    const parsed = extractLatLonFromText(candidate)
    if (parsed) return parsed
  }
  return null
}

const hashString = (value) => {
  const text = String(value || '')
  let hash = 2166136261
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

const mapKindForNode = (node) => {
  const labels = (node?.labels || []).map(label => String(label || '').toLowerCase())
  const labelText = labels.join(' ')
  if (labelText.includes('region') || labelText.includes('patch') || labelText.includes('body')) return 'region'
  if (labelText.includes('actor') || labelText.includes('government') || labelText.includes('organization')) return 'agent'
  if (labelText.includes('carrier') || labelText.includes('infrastructure') || labelText.includes('receptor')) return 'subregion'

  const name = String(node?.name || '').toLowerCase()
  if (name.includes('区') || name.includes('街道') || name.includes('社区') || name.includes('红树林') || name.includes('水体')) return 'region'
  if (name.includes('居民') || name.includes('游客') || name.includes('政府') || name.includes('企业') || name.includes('群体')) return 'agent'
  return 'subregion'
}

const radiusToZoomHint = (radiusMeters = 0) => {
  const radius = Number(radiusMeters) || 0
  if (radius <= 3000) return 12
  if (radius <= 10000) return 11
  if (radius <= 20000) return 10
  if (radius <= 50000) return 9
  return 8
}

const projectNodeToMap = (node, index, center, radiusMeters = 12000) => {
  const parsed = extractNodeLatLon(node)
  const attrs = { ...(node?.attributes || {}) }
  const kind = mapKindForNode(node)
  const spreadRadiusMeters = Math.max(2500, Math.min(Number(radiusMeters) || 12000, 50000))

  let lat = parsed?.lat
  let lon = parsed?.lon
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    const hash = hashString(node?.uuid || node?.name || index)
    const angle = (hash % 3600) / 3600 * Math.PI * 2
    const ringRatioByKind = { region: 0.18, subregion: 0.38, agent: 0.62 }
    const ringMeters = spreadRadiusMeters * (ringRatioByKind[kind] || 0.48)
    const jitterMeters = (((hash >>> 8) % 1000) / 1000) * spreadRadiusMeters * 0.18
    const offsetMeters = ringMeters + jitterMeters
    lat = center.lat + Math.sin(angle) * offsetMeters / 111320
    lon = center.lon + Math.cos(angle) * offsetMeters / Math.max(1, Math.cos(center.lat * Math.PI / 180) * 111320)
  }

  return {
    ...node,
    kind,
    attributes: {
      ...attrs,
      lat,
      lon,
      map_kind: kind
    }
  }
}

const mapProjection = computed(() => {
  if (realtimeMapProjection.value?.nodes?.length || realtimeMapProjection.value?.edges?.length) {
    return realtimeMapProjection.value
  }

  const pending = currentProjectId.value === 'new' ? getPendingUpload() : null
  const context = getSceneSeedContextByProject(currentProjectId.value) || pending
  const nodes = Array.isArray(graphData.value?.nodes) ? graphData.value.nodes : []
  const edges = Array.isArray(graphData.value?.edges) ? graphData.value.edges : []
  const radiusMeters = Number(context?.radiusMeters || context?.radius_m || realtimeMapProjection.value?.radius_m || 12000)
  let center = null

  if (context?.selectedPoints?.[0]) {
    const lat = Number(context.selectedPoints[0].lat)
    const lon = Number(context.selectedPoints[0].lon)
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      center = { lat, lon }
    }
  }

  if (!center && nodes.length > 0) {
    const geoPoints = nodes
      .map(node => extractNodeLatLon(node))
      .filter(Boolean)
    if (geoPoints.length > 0) {
      center = {
        lat: geoPoints.reduce((sum, point) => sum + point.lat, 0) / geoPoints.length,
        lon: geoPoints.reduce((sum, point) => sum + point.lon, 0) / geoPoints.length
      }
    }
  }

  if (!center) return null

  return {
    center,
    radius_m: radiusMeters,
    zoom_hint: radiusToZoomHint(radiusMeters),
    nodes: nodes.map((node, index) => projectNodeToMap(node, index, center, radiusMeters)),
    edges,
    meta: {
      source: 'frontend_fallback_projection'
    }
  }
})

// Polling timers
let pollTimer = null
let graphPollTimer = null

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
  if (error.value) return 'error'
  if (stepStatus.value === 'processing') return 'processing'
  if (stepStatus.value === 'completed') return 'completed'
  if (stepStatus.value === 'error') return 'error'
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return '错误'
  if (stepStatus.value === 'processing') return '生成配置中'
  if (stepStatus.value === 'completed') return '配置就绪'
  if (stepStatus.value === 'error') return '配置错误'
  if (currentPhase.value >= 2) return '就绪'
  if (currentPhase.value === 1) return '构建图谱中'
  if (currentPhase.value === 0) return '生成本体中'
  return '初始化中'
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  // Keep last 100 logs
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
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

const buildSimulationRunRoute = (simulationId, params = {}) => {
  const routeParams = {
    name: 'SimulationRun',
    params: { simulationId }
  }

  const query = {}
  if (params.maxRounds) query.maxRounds = params.maxRounds
  if (params.scenarioMode) query.scenario_mode = params.scenarioMode
  if (params.hazardTemplateId) query.hazard_template_id = params.hazardTemplateId
  if (params.diffusionTemplate) query.diffusion_template = params.diffusionTemplate
  if (params.searchMode) query.search_mode = params.searchMode
  if (params.simulationArchitecture) query.simulation_architecture = params.simulationArchitecture
  if (params.temporalPreset) query.temporal_preset = params.temporalPreset
  if (params.referenceTime) query.reference_time = params.referenceTime
  if (params.variableCount !== undefined) query.variable_count = params.variableCount
  if (Object.keys(query).length > 0) routeParams.query = query

  return routeParams
}

const handleNextStep = async (params = {}) => {
  const simulationId = currentSimulationId.value || await ensureSimulationForProject()
  if (!simulationId) {
    addLog('进入 Step 3 失败：模拟入口尚未就绪')
    return
  }

  const routeParams = buildSimulationRunRoute(simulationId, params)
  markWorkflowStep(2, {
    visited: true,
    status: 'done',
    summary: '场景配置已完成',
    route: { name: 'Process', params: { projectId: currentProjectId.value || route.params.projectId || 'new' } }
  })
  markWorkflowStep(3, {
    visited: true,
    status: 'active',
    summary: '推演播放准备中',
    route: routeParams
  })

  addLog('进入 Step 3: 开始模拟')
  if (params.maxRounds) {
    addLog(`自定义模拟轮数: ${params.maxRounds} 轮`)
  }
  router.push(routeParams)
}

const handleGoBack = () => {
  if (currentStep.value > 2) {
    currentStep.value--
    markCurrentWorkflowStep()
    addLog(`返回 Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  } else {
    // 返回到背景生成页
    router.push({ name: 'SceneComposer', query: { restore: '1' } })
  }
}

const markCurrentWorkflowStep = () => {
  const routePayload = currentStep.value === 2
    ? { name: 'Process', params: { projectId: currentProjectId.value || route.params.projectId || 'new' } }
    : null
  markWorkflowStep(currentStep.value, {
    visited: true,
    status: currentStep.value === 2 ? 'active' : 'done',
    summary: currentStep.value === 2 ? '场景设计进行中' : '',
    route: routePayload
  })
}

const updateStepStatus = (status) => {
  stepStatus.value = status || 'idle'
}

const getLatestProjectSimulation = async () => {
  if (!currentProjectId.value || currentProjectId.value === 'new') return null

  try {
    const res = await listSimulations(currentProjectId.value)
    if (!res.success || !Array.isArray(res.data) || res.data.length === 0) return null

    return [...res.data]
      .filter(item => item?.simulation_id)
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0] || null
  } catch (err) {
    addLog(`读取已有模拟入口失败: ${err.message}`)
    return null
  }
}

const ensureSimulationForProject = async () => {
  if (currentSimulationId.value) return currentSimulationId.value
  if (!projectData.value?.project_id || !projectData.value?.graph_id) return ''

  const sceneSeedContext = getSceneSeedContextByProject(projectData.value.project_id)
  initialInjectedVariables.value = sceneSeedContext?.initialVariables || []

  const existing = await getLatestProjectSimulation()
  if (existing?.simulation_id) {
    currentSimulationId.value = existing.simulation_id
    if (sceneSeedContext) {
      attachSceneSeedContextToSimulation(existing.simulation_id, sceneSeedContext)
    }
    addLog(`已复用模拟入口: ${existing.simulation_id}`)
    await refreshMapProjection()
    return existing.simulation_id
  }

  const res = await createSimulation({
    project_id: projectData.value.project_id,
    graph_id: projectData.value.graph_id,
    enable_twitter: true,
    enable_reddit: true,
    source_mode: sceneSeedContext?.mapSeedId ? 'map_seed' : 'graph',
    map_seed_id: sceneSeedContext?.mapSeedId || undefined
  })

  if (res.success && res.data?.simulation_id) {
    currentSimulationId.value = res.data.simulation_id
    if (sceneSeedContext) {
      attachSceneSeedContextToSimulation(res.data.simulation_id, sceneSeedContext)
    }
    addLog(`已创建模拟入口: ${res.data.simulation_id}`)
    await refreshMapProjection()
    return res.data.simulation_id
  }

  error.value = res.error || '创建模拟入口失败'
  addLog(`创建模拟入口失败: ${error.value}`)
  return ''
}

// --- Data Logic ---

const initProject = async () => {
  addLog('Project view initialized.')
  if (currentProjectId.value === 'new') {
    await handleNewProject()
  } else {
    await loadProject()
  }
}

const handleNewProject = async () => {
  const pending = getPendingUpload()
  if (!pending.isPending || pending.files.length === 0) {
    error.value = 'No pending files found.'
    addLog('Error: No pending files found for new project.')
    return
  }
  
  try {
    loading.value = true
    currentPhase.value = 0
    ontologyProgress.value = { message: 'Uploading and analyzing docs...' }
    addLog('Starting ontology generation: Uploading files...')
    
    const formData = new FormData()
    pending.files.forEach(f => formData.append('files', f))
    formData.append('simulation_requirement', pending.simulationRequirement)
    
    const res = await generateOntology(formData)
    if (res.success) {
      if (res.data?.project_id) {
        attachSceneSeedContextToProject(res.data.project_id, {
          initialVariables: pending.initialVariables,
          selectedPoints: pending.selectedPoints,
          mapSeedId: pending.mapSeedId,
          areaLabel: pending.areaLabel,
          radiusMeters: pending.radiusMeters
        })
      }
      clearPendingUpload()
      currentProjectId.value = res.data.project_id
      projectData.value = res.data
      
      router.replace({ name: 'Process', params: { projectId: res.data.project_id } })
      markCurrentWorkflowStep()
      ontologyProgress.value = null
      addLog(`Ontology generated successfully for project ${res.data.project_id}`)
      await startBuildGraph()
    } else {
      error.value = res.error || 'Ontology generation failed'
      addLog(`Error generating ontology: ${error.value}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in handleNewProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const loadProject = async () => {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}...`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status)
      addLog(`Project loaded. Status: ${res.data.status}`)
      
      if (res.data.status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (res.data.status === 'graph_building' && res.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (res.data.status === 'graph_completed' && res.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(res.data.graph_id)
        await ensureSimulationForProject()
      }
    } else {
      error.value = res.error
      addLog(`Error loading project: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in loadProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
    case 'ontology_generated':
      error.value = ''
      currentPhase.value = 0
      break;
    case 'graph_building':
      error.value = ''
      currentPhase.value = 1
      break;
    case 'graph_completed':
      error.value = ''
      currentPhase.value = 2
      break;
    case 'failed':
      error.value = projectData.value?.error || '图谱构建失败'
      stopGraphPolling()
      stopPolling()
      break;
  }
}

const startBuildGraph = async () => {
  try {
    error.value = ''
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: 'Starting build...' }
    addLog('Initiating graph build...')
    
    const res = await buildGraph({ project_id: currentProjectId.value })
    if (res.success) {
      addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
      startGraphPolling()
      startPollingTask(res.data.task_id)
    } else {
      error.value = res.error
      addLog(`Error starting build: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in startBuildGraph: ${err.message}`)
  }
}

const startGraphPolling = () => {
  stopGraphPolling()
  addLog('Started polling for graph data...')
  fetchGraphData()
  graphPollTimer = setInterval(fetchGraphData, 10000)
}

const fetchGraphData = async () => {
  try {
    // Refresh project info to check for graph_id
    const projRes = await getProject(currentProjectId.value)
    if (projRes.success && projRes.data?.status === 'failed') {
      projectData.value = projRes.data
      error.value = projRes.data.error || '图谱构建失败'
      addLog(`Graph build failed: ${error.value}`)
      stopGraphPolling()
      return
    }

    if (projRes.success && projRes.data.graph_id) {
      const gRes = await getGraphData(projRes.data.graph_id)
      if (gRes.success) {
        graphData.value = gRes.data
        const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
        const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
        addLog(`Graph data refreshed. Nodes: ${nodeCount}, Edges: ${edgeCount}`)
      }
    }
  } catch (err) {
    console.warn('Graph fetch error:', err)
  }
}

const startPollingTask = (taskId) => {
  stopPolling()
  pollTaskStatus(taskId)
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
}

const pollTaskStatus = async (taskId) => {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data
      
      // Log progress message if it changed
      if (task.message && task.message !== buildProgress.value?.message) {
        addLog(task.message)
      }
      
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      
      if (task.status === 'completed') {
        addLog('Graph build task completed.')
        stopPolling()
        stopGraphPolling() // Stop polling, do final load
        currentPhase.value = 2
        
        // Final load
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
            projectData.value = projRes.data
            await loadGraph(projRes.data.graph_id)
            await ensureSimulationForProject()
        }
      } else if (task.status === 'failed' || task.status === 'cancelled') {
        stopPolling()
        stopGraphPolling()
        error.value = task.message || task.error || (task.status === 'cancelled' ? '用户强制停止' : '未知错误')
        addLog(task.status === 'cancelled'
          ? `Graph build task cancelled: ${error.value}`
          : `Graph build task failed: ${error.value}`)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  addLog(`Loading full graph data: ${graphId}`)
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      addLog('Graph data loaded successfully.')
      if (projectData.value?.graph_id) {
        await ensureSimulationForProject()
      }
    } else {
      addLog(`Failed to load graph data: ${res.error}`)
    }
  } catch (e) {
    addLog(`Exception loading graph: ${e.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshMapProjection = async () => {
  if (!currentSimulationId.value) return
  try {
    const res = await getSimulationGraphRealtime(currentSimulationId.value, {
      include_map: true,
      key_edges_only: true
    })
    const projection = res?.data?.map_projection
    if (res.success && projection && Array.isArray(projection.nodes)) {
      realtimeMapProjection.value = projection
      const nodeCount = projection.meta?.node_count || projection.nodes.length
      const source = projection.source_mode || res.data?.source || 'map_projection'
      addLog(`地图投影已刷新: ${nodeCount} 个节点 / ${source}`)
    }
  } catch (err) {
    console.warn('Map projection refresh failed:', err)
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    addLog('Manual graph refresh triggered.')
    loadGraph(projectData.value.graph_id)
  }
  refreshMapProjection()
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const stopGraphPolling = () => {
  if (graphPollTimer) {
    clearInterval(graphPollTimer)
    graphPollTimer = null
    addLog('Graph polling stopped.')
  }
}

onMounted(() => {
  markCurrentWorkflowStep()
  initProject()
})

onUnmounted(() => {
  stopPolling()
  stopGraphPolling()
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

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
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
