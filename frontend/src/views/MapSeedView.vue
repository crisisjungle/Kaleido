<template>
  <div class="map-seed-page">
    <header class="topbar">
      <button class="brand-lockup" type="button" @click="router.push('/')">
        <span class="brand-mark">EF</span>
        <span class="brand-copy">
          <strong>ENVFISH</strong>
          <small>Map-First Seed Workspace</small>
        </span>
      </button>

      <div class="topbar-links">
        <button class="ghost-link" type="button" @click="resetSeed">重新选点</button>
        <button class="ghost-link" type="button" @click="router.push('/')">返回首页</button>
      </div>
    </header>

    <main class="page-shell">
      <section class="hero-grid">
        <div class="hero-copy">
          <div class="eyebrow-row">
            <span class="eyebrow-pill">Map First</span>
            <span class="eyebrow-note">点选位置，自动生成实景图谱</span>
          </div>

          <h1 class="hero-title">先选点，再让系统把周边世界展开。</h1>
          <p class="hero-lead">
            地图模式会先抓取周边开放生态数据和卫星底图，再把节点、关系和环境基线组织成可切换的实景图谱。
            你仍然可以随时切回纯图谱视图继续编辑和推演。
          </p>
        </div>

        <div class="hero-stage">
          <div class="status-card">
            <div>
              <span class="status-label">Seed Status</span>
              <strong>{{ statusText }}</strong>
            </div>
            <div class="status-meta">
              <span class="mono">{{ seedId || 'no seed yet' }}</span>
              <span>{{ seedTaskId ? `Task ${seedTaskId.slice(0, 8)}` : '等待选点' }}</span>
            </div>
          </div>
        </div>
      </section>

      <section class="workspace">
        <div class="map-panel">
          <div class="panel-head">
            <div>
              <span class="panel-kicker">01 / Pick Point</span>
              <h2>地图选点</h2>
            </div>
            <div class="view-switcher">
              <button
                v-for="mode in viewModes"
                :key="mode.value"
                class="switch-btn"
                :class="{ active: viewMode === mode.value }"
                type="button"
                @click="viewMode = mode.value"
              >
                {{ mode.label }}
              </button>
            </div>
          </div>

          <div class="map-stage" :class="`mode-${viewMode}`">
            <LeafletMapPicker
              v-if="viewMode !== 'graph'"
              :center="mapCenter"
              :selected-point="selectedPoint"
              :radius-meters="radiusMeters"
              :layers="mapLayers"
              @pick="handlePickPoint"
            />

            <div v-if="viewMode === 'graph'" class="graph-shell">
              <GraphPanel
                :graphData="graphData"
                :loading="graphLoading"
                :currentPhase="2"
                :highlightLabel="graphHighlightLabel"
                @refresh="loadSeedArtifacts"
                @toggle-maximize="viewMode = 'split'"
              />
            </div>

            <div v-if="viewMode === 'split'" class="split-shell">
              <div class="split-left">
                <LeafletMapPicker
                  :center="mapCenter"
                  :selected-point="selectedPoint"
                  :radius-meters="radiusMeters"
                  :layers="mapLayers"
                  @pick="handlePickPoint"
                />
              </div>
              <div class="split-right">
                <GraphPanel
                  :graphData="graphData"
                  :loading="graphLoading"
                  :currentPhase="2"
                  :highlightLabel="graphHighlightLabel"
                  @refresh="loadSeedArtifacts"
                  @toggle-maximize="viewMode = 'map'"
                />
              </div>
            </div>

            <div v-if="viewMode === 'map'" class="map-overlay-card">
              <div class="overlay-head">
                <strong>{{ selectedPoint ? '已选定点位' : '点击地图选择点位' }}</strong>
                <span class="mono">
                  {{ selectedPoint ? `${selectedPoint.lat.toFixed(4)}, ${selectedPoint.lon.toFixed(4)}` : 'lat, lon' }}
                </span>
              </div>

              <div class="overlay-grid">
                <div class="overlay-item">
                  <span>半径</span>
                  <strong>{{ radiusMetersDisplay }}</strong>
                </div>
                <div class="overlay-item">
                  <span>图层</span>
                  <strong>{{ layerCount }}</strong>
                </div>
                <div class="overlay-item">
                  <span>节点</span>
                  <strong>{{ nodeCount }}</strong>
                </div>
                <div class="overlay-item">
                  <span>状态</span>
                  <strong>{{ statusText }}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>

        <aside class="side-panel">
          <section class="card">
            <div class="card-head">
              <div>
                <span class="panel-kicker">02 / Radius</span>
                <h3>分析半径</h3>
              </div>
              <button class="secondary-btn" type="button" :disabled="!selectedPoint || creatingSeed" @click="submitSeed">
                {{ creatingSeed ? '生成中...' : '生成实景图谱' }}
              </button>
            </div>

            <div class="field-grid">
              <label>
                <span>纬度</span>
                <input v-model="draftLat" type="number" step="0.000001" placeholder="点击地图后自动填入" />
              </label>
              <label>
                <span>经度</span>
                <input v-model="draftLon" type="number" step="0.000001" placeholder="点击地图后自动填入" />
              </label>
            </div>

            <label class="radius-field">
              <span>半径：{{ radiusMetersDisplay }}</span>
              <input v-model.number="radiusMeters" type="range" min="1000" max="50000" step="500" />
            </label>

            <p class="hint">
              选点后系统会自动拉取周边开放数据、卫星底图和代理节点，再生成可切换的地图图谱。
            </p>
          </section>

          <section class="card">
            <div class="card-head">
              <div>
                <span class="panel-kicker">03 / Result</span>
                <h3>实景图谱结果</h3>
              </div>
              <span class="pill">{{ graphLoading ? 'Loading' : (graphData ? 'Ready' : 'Idle') }}</span>
            </div>

            <div class="summary-grid">
              <article class="summary-card">
                <span>Nodes</span>
                <strong>{{ nodeCount }}</strong>
              </article>
              <article class="summary-card">
                <span>Edges</span>
                <strong>{{ edgeCount }}</strong>
              </article>
              <article class="summary-card">
                <span>Layers</span>
                <strong>{{ layerCount }}</strong>
              </article>
              <article class="summary-card">
                <span>Confidence</span>
                <strong>{{ confidenceLabel }}</strong>
              </article>
            </div>

            <div v-if="seedSummary" class="note-box">
              <span>摘要</span>
              <p>{{ seedSummary }}</p>
            </div>
          </section>

          <section class="card">
            <div class="card-head">
              <div>
                <span class="panel-kicker">04 / Layers</span>
                <h3>图层列表</h3>
              </div>
            </div>

            <div class="layer-list">
              <label v-for="layer in visibleLayers" :key="layer.id" class="layer-item">
                <input v-model="layer.visible" type="checkbox" @change="syncLayerVisibility" />
                <span class="layer-swatch" :style="{ background: layer.color }"></span>
                <div>
                  <strong>{{ layer.name }}</strong>
                  <p>{{ layer.note }}</p>
                </div>
              </label>
            </div>
          </section>

          <section class="card">
            <div class="card-head">
              <div>
                <span class="panel-kicker">05 / Simulation</span>
                <h3>进入推演</h3>
              </div>
              <button class="primary-btn" type="button" :disabled="!seedId || converting" @click="proceedToSimulation">
                {{ converting ? '创建中...' : '创建模拟' }}
              </button>
            </div>

            <p class="hint">
              生成完成后可以直接进入现有环境搭建流程，不需要再上传文档。
            </p>
            <p v-if="message" class="message">{{ message }}</p>
          </section>
        </aside>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import LeafletMapPicker from '../components/LeafletMapPicker.vue'
import { convertMapSeedToSimulation, createMapSeed, getMapSeed, getMapSeedLayers, getMapSeedStatus } from '../api/mapSeed'

const props = defineProps({
  seedId: {
    type: String,
    default: ''
  }
})

const router = useRouter()

const viewModes = [
  { value: 'map', label: '地图' },
  { value: 'split', label: '双栏' },
  { value: 'graph', label: '图谱' }
]

const viewMode = ref('split')
const selectedPoint = ref(null)
const draftLat = ref('')
const draftLon = ref('')
const radiusMeters = ref(5000)
const seedId = ref(props.seedId || '')
const seedTaskId = ref('')
const seedData = ref(null)
const layersData = ref(null)
const graphLoading = ref(false)
const creatingSeed = ref(false)
const converting = ref(false)
const message = ref('')
const pollTimer = ref(null)
const graphHighlightLabel = ref('')
const mapCenter = ref([20, 0])
const visibleLayers = ref([])

const radiusMetersDisplay = computed(() => `${Math.round(radiusMeters.value / 1000)} km`)

const statusText = computed(() => {
  if (converting.value) return 'Converting'
  if (creatingSeed.value) return 'Seeding'
  if (!seedId.value) return 'Idle'
  if (seedData.value?.status) return String(seedData.value.status)
  return 'Ready'
})

const confidenceLabel = computed(() => {
  const raw = seedData.value?.confidence || seedData.value?.confidence_score || seedData.value?.summary?.confidence
  if (raw === undefined || raw === null || raw === '') return 'n/a'
  const number = Number(raw)
  if (Number.isNaN(number)) return String(raw)
  return number <= 1 ? `${Math.round(number * 100)}%` : `${Math.round(number)}%`
})

const graphData = computed(() => (seedData.value ? normalizeGraphData(seedData.value) : null))

const nodeCount = computed(() => graphData.value?.node_count || graphData.value?.nodes?.length || 0)
const edgeCount = computed(() => graphData.value?.edge_count || graphData.value?.edges?.length || 0)
const seedSummary = computed(() => {
  const source = seedData.value || {}
  return (
    source.summary ||
    source.description ||
    source.report_summary ||
    source.brief ||
    source.note ||
    (source.location ? `${source.location}` : '')
  )
})

function normalizeGraphData(source) {
  const raw = source?.graph_data || source?.graph || source?.map_graph || source?.graph_snapshot || source || {}
  const nodes = normalizeNodes(raw.nodes || source?.nodes || source?.graph_nodes || [])
  const edges = normalizeEdges(raw.edges || source?.edges || source?.graph_edges || [])
  return {
    ...raw,
    nodes,
    edges,
    node_count: raw.node_count ?? nodes.length,
    edge_count: raw.edge_count ?? edges.length
  }
}

function normalizeNodes(items) {
  return (Array.isArray(items) ? items : []).map((item, index) => {
    const point = extractPoint(item)
    const category = item.category || item.type || item.node_type || inferCategory(item)
    const sourceKind = item.source_kind || item.sourceType || item.source || inferSourceKind(item)
    return {
      uuid: item.uuid || item.id || item.node_id || `node_${index}`,
      name: item.name || item.label || item.title || `Node ${index + 1}`,
      labels: Array.isArray(item.labels) && item.labels.length > 0 ? item.labels : [category].filter(Boolean),
      summary: item.summary || item.description || '',
      attributes: {
        ...(item.attributes || {}),
        category,
        source_kind: sourceKind,
        confidence: item.confidence ?? item.confidence_score ?? item.score ?? null,
        lat: point?.lat,
        lon: point?.lon
      }
    }
  })
}

function normalizeEdges(items) {
  return (Array.isArray(items) ? items : []).map((item, index) => ({
    uuid: item.uuid || item.id || item.edge_id || `edge_${index}`,
    name: item.name || item.relation || item.label || 'RELATED_TO',
    fact: item.fact || item.description || item.summary || '',
    fact_type: item.fact_type || item.relation || item.type || 'RELATED_TO',
    source_node_uuid: item.source_node_uuid || item.source || item.from || '',
    target_node_uuid: item.target_node_uuid || item.target || item.to || '',
    source_node_name: item.source_node_name || item.source_name || '',
    target_node_name: item.target_node_name || item.target_name || '',
    attributes: item.attributes || {},
    created_at: item.created_at || null
  }))
}

function inferCategory(item) {
  const text = `${item?.name || ''} ${item?.type || ''} ${item?.summary || ''}`.toLowerCase()
  if (text.includes('human') || text.includes('resident') || text.includes('visitor') || text.includes('proxy')) return 'human_proxy'
  if (text.includes('facility') || text.includes('road') || text.includes('port') || text.includes('plant')) return 'facility'
  return 'ecology'
}

function inferSourceKind(item) {
  const text = `${item?.name || ''} ${item?.summary || ''} ${item?.type || ''}`.toLowerCase()
  if (text.includes('infer')) return 'inferred'
  if (text.includes('detect')) return 'detected'
  return 'observed'
}

function extractPoint(item) {
  if (!item) return null
  const anchor = item.anchor_point || item.anchorPoint || item.point || null
  const lat = Number(anchor?.lat ?? anchor?.latitude ?? item.lat ?? item.latitude)
  const lon = Number(anchor?.lon ?? anchor?.lng ?? anchor?.longitude ?? item.lon ?? item.lng ?? item.longitude)
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    return { lat, lon }
  }

  const geometry = item.geometry || item.geom || null
  if (geometry?.type === 'Point' && Array.isArray(geometry.coordinates) && geometry.coordinates.length >= 2) {
    return {
      lon: Number(geometry.coordinates[0]),
      lat: Number(geometry.coordinates[1])
    }
  }

  if (geometry?.coordinates) {
    const flat = flattenCoordinates(geometry.coordinates)
    if (flat.length > 0) {
      const latAvg = flat.reduce((sum, pair) => sum + pair[1], 0) / flat.length
      const lonAvg = flat.reduce((sum, pair) => sum + pair[0], 0) / flat.length
      if (Number.isFinite(latAvg) && Number.isFinite(lonAvg)) {
        return { lat: latAvg, lon: lonAvg }
      }
    }
  }

  return null
}

function flattenCoordinates(coords) {
  if (!Array.isArray(coords)) return []
  if (coords.length === 0) return []
  if (typeof coords[0]?.[0] === 'number') return coords
  return coords.flatMap((item) => flattenCoordinates(item))
}

function normalizeLayers(source) {
  const rawLayers = source?.layers || source?.geojson_layers || source?.items || source?.data || []
  if (Array.isArray(rawLayers) && rawLayers.length > 0) {
    return rawLayers.map((layer, index) => ({
      id: layer.id || layer.layer_id || `layer_${index}`,
      name: layer.name || layer.title || `Layer ${index + 1}`,
      type: layer.type || layer.kind || inferLayerType(layer),
      color: layer.color || pickLayerColor(index, layer.type || layer.kind),
      visible: layer.visible !== false,
      note: layer.note || layer.description || '',
      data: layer.data || layer.geojson || layer.features || layer.geometry || layer.points || []
    }))
  }

  const derivedLayers = []

  if (source?.analysis_polygon) {
    derivedLayers.push({
      id: 'analysis-polygon',
      name: '分析范围',
      type: 'geojson',
      color: '#0f766e',
      visible: true,
      note: '地图选点分析范围',
      data: {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: source.analysis_polygon,
            properties: { name: '分析范围', color: '#0f766e' }
          }
        ]
      }
    })
  }

  if (Array.isArray(source?.feature_points) && source.feature_points.length > 0) {
    const grouped = source.feature_points.reduce((acc, item) => {
      const sourceKind = item?.source_kind || 'observed'
      if (!acc[sourceKind]) acc[sourceKind] = []
      acc[sourceKind].push({
        lat: item.lat,
        lon: item.lon,
        label: item.name,
        radius: sourceKind === 'detected' ? 7 : 6
      })
      return acc
    }, {})

    Object.entries(grouped).forEach(([key, points], index) => {
      derivedLayers.push({
        id: `legacy-${key}`,
        name: `${key} 特征`,
        type: 'points',
        color: pickLayerColor(index, key),
        visible: true,
        note: '后端兼容层转换出的空间节点',
        data: points
      })
    })
  }

  return derivedLayers
}

function inferLayerType(layer) {
  if (Array.isArray(layer?.points)) return 'points'
  if (layer?.geometry || layer?.geojson || layer?.features) return 'geojson'
  return 'points'
}

function pickLayerColor(index, kind = '') {
  const palette = ['#1f5d45', '#0f766e', '#d97706', '#7c3aed', '#2563eb', '#b45309']
  if (kind === 'observed') return '#1f5d45'
  if (kind === 'detected') return '#0f766e'
  if (kind === 'inferred') return '#d97706'
  return palette[index % palette.length]
}

const KEY_RELATION_TOKENS = new Set([
  'depends_on',
  'affects',
  'exposed_to',
  'regulates',
  'monitors',
  'uses',
  'dynamic_edge',
  'agent_influence',
  'influences_region'
])

function isKeyInteractionEdge(edge) {
  const name = String(edge?.name || '').toLowerCase()
  const factType = String(edge?.fact_type || '').toLowerCase()
  const attrs = edge?.attributes || {}
  if (attrs?.is_key_interaction) return true
  if (KEY_RELATION_TOKENS.has(name) || KEY_RELATION_TOKENS.has(factType)) return true
  const confidence = Number(attrs?.confidence || 0)
  return confidence >= 0.62
}

const mapLayers = computed(() => {
  const derived = []
  const graphNodes = graphData.value?.nodes || []
  const graphEdges = graphData.value?.edges || []
  const grouped = new Map()
  const nodePointById = new Map()

  graphNodes.forEach((node) => {
    const point = extractPoint(node)
    if (!point) return
    nodePointById.set(String(node?.uuid || ''), point)
    const sourceKind = String(node?.attributes?.source_kind || node?.source_kind || 'observed')
    if (!grouped.has(sourceKind)) {
      grouped.set(sourceKind, [])
    }
    grouped.get(sourceKind).push({
      lat: point.lat,
      lon: point.lon,
      label: node.name,
      radius: sourceKind === 'inferred' ? 7 : 6
    })
  })

  if (graphEdges.length > 0 && nodePointById.size > 0) {
    const features = []
    graphEdges.forEach((edge) => {
      if (!isKeyInteractionEdge(edge)) return
      const sourceId = String(edge?.source_node_uuid || edge?.source || '')
      const targetId = String(edge?.target_node_uuid || edge?.target || '')
      const sourcePoint = nodePointById.get(sourceId)
      const targetPoint = nodePointById.get(targetId)
      if (!sourcePoint || !targetPoint) return
      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [sourcePoint.lon, sourcePoint.lat],
            [targetPoint.lon, targetPoint.lat]
          ]
        },
        properties: {
          name: edge?.name || edge?.fact_type || 'relation',
          color: '#a16207',
          weight: 2,
          opacity: 0.78,
          fillOpacity: 0
        }
      })
    })
    if (features.length > 0) {
      derived.push({
        id: 'derived-key-relations',
        name: '关键关系链路',
        type: 'geojson',
        color: '#a16207',
        visible: true,
        note: '关键交互关系线',
        data: {
          type: 'FeatureCollection',
          features
        }
      })
    }
  }

  grouped.forEach((points, key) => {
    derived.push({
      id: `derived-${key}`,
      name: `${key} nodes`,
      type: 'points',
      color: pickLayerColor(derived.length, key),
      visible: true,
      note: `Derived from ${key} nodes`,
      data: points
    })
  })

  const explicitLayers = visibleLayers.value.length > 0 ? visibleLayers.value : normalizeLayers(layersData.value)
  return [...explicitLayers, ...derived]
})

const layerCount = computed(() => mapLayers.value.filter((layer) => layer.visible !== false).length)

function syncLayerVisibility() {
  visibleLayers.value = visibleLayers.value.map((layer) => ({ ...layer }))
}

async function handlePickPoint(point) {
  selectedPoint.value = point
  draftLat.value = String(point.lat)
  draftLon.value = String(point.lon)
  seedData.value = null
  layersData.value = null
  seedId.value = ''
  seedTaskId.value = ''
  message.value = ''
  visibleLayers.value = []
  mapCenter.value = [point.lat, point.lon]
  graphHighlightLabel.value = ''
  await nextTick()
}

async function submitSeed() {
  if (!selectedPoint.value || creatingSeed.value) return

  creatingSeed.value = true
  message.value = '地图种子任务已提交'

  try {
    const payload = {
      lat: Number(draftLat.value),
      lon: Number(draftLon.value),
      radius_m: Number(radiusMeters.value)
    }
    const res = await createMapSeed(payload)
    if (res.success && res.data) {
      seedId.value = res.data.seed_id || res.data.map_seed_id || res.data.id || seedId.value
      seedTaskId.value = res.data.task_id || ''
      graphHighlightLabel.value = res.data.title || res.data.name || 'Map Seed'
      message.value = res.data.message || '地图种子任务已启动'
      startPolling()
      await loadSeedArtifacts()
    } else {
      message.value = res.error || '地图种子提交失败'
    }
  } catch (error) {
    message.value = error.message || '地图种子提交失败'
  } finally {
    creatingSeed.value = false
  }
}

async function loadSeedArtifacts() {
  if (!seedId.value) return

  graphLoading.value = true
  try {
    const [detailRes, layerRes] = await Promise.allSettled([
      getMapSeed(seedId.value),
      getMapSeedLayers(seedId.value)
    ])

    if (detailRes.status === 'fulfilled' && detailRes.value?.success && detailRes.value.data) {
      seedData.value = detailRes.value.data
      const point = extractPoint(detailRes.value.data)
      if (point && !selectedPoint.value) {
        selectedPoint.value = point
        draftLat.value = String(point.lat)
        draftLon.value = String(point.lon)
        mapCenter.value = [point.lat, point.lon]
      }
    }

    if (layerRes.status === 'fulfilled' && layerRes.value?.success) {
      layersData.value = layerRes.value.data || {}
      const normalized = normalizeLayers(layerRes.value.data)
      visibleLayers.value = normalized
    } else if (!visibleLayers.value.length) {
      visibleLayers.value = normalizeLayers(seedData.value)
    }
  } catch (error) {
    message.value = error.message || '加载地图种子失败'
  } finally {
    graphLoading.value = false
  }
}

async function pollStatus() {
  if (!seedId.value) return

  try {
    const res = await getMapSeedStatus({
      seed_id: seedId.value,
      task_id: seedTaskId.value || undefined
    })

    if (res.success && res.data) {
      const status = String(res.data.status || '').toLowerCase()
      if (res.data.message) {
        message.value = res.data.message
      }
      if (status === 'completed' || status === 'ready') {
        stopPolling()
        await loadSeedArtifacts()
      } else if (status === 'failed') {
        stopPolling()
        message.value = res.data.error || '地图种子任务失败'
      }
    }
  } catch (error) {
    console.warn('poll map seed failed', error)
  }
}

function startPolling() {
  stopPolling()
  pollTimer.value = window.setInterval(pollStatus, 2500)
}

function stopPolling() {
  if (pollTimer.value) {
    window.clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

async function proceedToSimulation() {
  if (!seedId.value || converting.value) return

  converting.value = true
  message.value = '正在创建模拟...'

  try {
    const res = await convertMapSeedToSimulation(seedId.value, {
      seed_id: seedId.value
    })

    if (res.success && res.data) {
      const simulationId = res.data.simulation_id || res.data.simulationId
      message.value = res.data.message || '模拟已创建'
      if (simulationId) {
        router.push({ name: 'Simulation', params: { simulationId } })
      }
    } else {
      message.value = res.error || '创建模拟失败'
    }
  } catch (error) {
    message.value = error.message || '创建模拟失败'
  } finally {
    converting.value = false
  }
}

function resetSeed() {
  stopPolling()
  seedId.value = ''
  seedTaskId.value = ''
  seedData.value = null
  layersData.value = null
  selectedPoint.value = null
  draftLat.value = ''
  draftLon.value = ''
  radiusMeters.value = 5000
  visibleLayers.value = []
  graphHighlightLabel.value = ''
  message.value = ''
  mapCenter.value = [20, 0]
}

watch(
  () => props.seedId,
  async (value) => {
    if (!value) return
    seedId.value = value
    await loadSeedArtifacts()
  },
  { immediate: true }
)

watch(
  () => selectedPoint.value,
  (value) => {
    if (value) {
      mapCenter.value = [value.lat, value.lon]
    }
  },
  { deep: true }
)

watch(
  () => graphData.value,
  (value) => {
    graphHighlightLabel.value = value?.name || graphHighlightLabel.value
  }
)

onMounted(() => {
  if (props.seedId) {
    loadSeedArtifacts()
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.map-seed-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(191, 214, 167, 0.28), transparent 30%),
    radial-gradient(circle at top right, rgba(217, 176, 120, 0.24), transparent 28%),
    linear-gradient(180deg, #f7f4ea 0%, #f1eadc 100%);
  color: #173126;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  backdrop-filter: blur(18px);
  background: rgba(247, 244, 234, 0.84);
  border-bottom: 1px solid rgba(35, 74, 54, 0.08);
}

.brand-lockup {
  display: inline-flex;
  align-items: center;
  gap: 0.9rem;
  padding: 0;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 3rem;
  height: 3rem;
  border-radius: 1rem;
  background: linear-gradient(135deg, #1f5d45, #7faa5d);
  color: #f6f4eb;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 0.95rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.brand-copy strong,
.panel-kicker,
.eyebrow-pill {
  font-family: 'IBM Plex Mono', monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.brand-copy small {
  font-size: 0.82rem;
  color: rgba(23, 49, 38, 0.68);
}

.topbar-links {
  display: flex;
  gap: 0.75rem;
}

.ghost-link,
.secondary-btn,
.primary-btn,
.switch-btn {
  font: inherit;
}

.ghost-link,
.secondary-btn,
.switch-btn {
  border-radius: 999px;
  border: 1px solid rgba(23, 49, 38, 0.12);
  background: rgba(255, 255, 255, 0.62);
  color: inherit;
  cursor: pointer;
  transition: transform 0.24s ease, background 0.24s ease, border-color 0.24s ease;
}

.ghost-link,
.secondary-btn {
  min-height: 2.6rem;
  padding: 0 1rem;
}

.primary-btn {
  min-height: 2.8rem;
  padding: 0 1.2rem;
  border-radius: 999px;
  border: 0;
  cursor: pointer;
  color: #f7f4ea;
  background: linear-gradient(135deg, #1f5d45, #82a95f);
}

.page-shell {
  display: grid;
  gap: 1.5rem;
  max-width: 1440px;
  margin: 0 auto;
  padding: 1.5rem;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 1.5rem;
}

.hero-copy,
.hero-stage,
.map-panel,
.side-panel .card {
  border: 1px solid rgba(23, 49, 38, 0.1);
  background: rgba(252, 249, 241, 0.84);
  box-shadow: 0 1.2rem 2.8rem rgba(31, 50, 40, 0.08);
}

.hero-copy {
  border-radius: 1.8rem;
  padding: 1.5rem;
}

.hero-stage {
  border-radius: 1.8rem;
  padding: 1.5rem;
}

.eyebrow-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1rem;
}

.eyebrow-pill {
  padding: 0.35rem 0.7rem;
  border-radius: 999px;
  background: #1f5d45;
  color: #f7f4ea;
  font-size: 0.75rem;
}

.eyebrow-note {
  color: rgba(23, 49, 38, 0.66);
}

.hero-title {
  margin: 0;
  max-width: 12ch;
  font-family: 'Fraunces', 'Noto Serif SC', serif;
  font-size: clamp(2.8rem, 5vw, 5rem);
  line-height: 0.96;
  letter-spacing: -0.04em;
}

.hero-lead {
  margin-top: 1rem;
  max-width: 44rem;
  font-size: 1.02rem;
  line-height: 1.72;
  color: rgba(23, 49, 38, 0.74);
}

.status-card {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  border-radius: 1.4rem;
  padding: 1rem 1.2rem;
  background: linear-gradient(135deg, rgba(31, 93, 69, 0.08), rgba(130, 169, 95, 0.14));
}

.status-label,
.panel-kicker {
  display: block;
  font-size: 0.75rem;
  color: rgba(23, 49, 38, 0.55);
}

.status-card strong {
  display: block;
  margin-top: 0.35rem;
  font-size: 1.1rem;
}

.status-meta {
  display: grid;
  gap: 0.35rem;
  text-align: right;
  color: rgba(23, 49, 38, 0.68);
}

.mono {
  font-family: 'IBM Plex Mono', monospace;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.6fr);
  gap: 1.5rem;
  min-height: calc(100vh - 190px);
}

.map-panel {
  border-radius: 1.8rem;
  padding: 1.2rem;
  overflow: hidden;
}

.panel-head,
.card-head,
.overlay-head {
  display: flex;
  justify-content: space-between;
  gap: 0.9rem;
  align-items: center;
}

.panel-head h2,
.card h3 {
  margin: 0;
  font-family: 'Fraunces', 'Noto Serif SC', serif;
}

.view-switcher {
  display: inline-flex;
  gap: 0.35rem;
  padding: 0.25rem;
  border-radius: 999px;
  background: rgba(23, 49, 38, 0.06);
}

.switch-btn.active {
  background: #fff;
  border-color: rgba(23, 49, 38, 0.12);
}

.map-stage {
  position: relative;
  margin-top: 1rem;
  min-height: 680px;
  border-radius: 1.5rem;
  overflow: hidden;
}

.map-stage.mode-map,
.map-stage.mode-graph {
  min-height: 760px;
}

.graph-shell,
.split-shell {
  width: 100%;
  height: 100%;
}

.split-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.84fr);
  gap: 1rem;
}

.split-left,
.split-right {
  min-height: 680px;
  border-radius: 1.3rem;
  overflow: hidden;
  background: #fff;
}

.map-overlay-card {
  position: absolute;
  left: 1rem;
  bottom: 1rem;
  width: min(420px, calc(100% - 2rem));
  padding: 1rem;
  border-radius: 1.3rem;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(23, 49, 38, 0.1);
}

.overlay-grid,
.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.overlay-item,
.summary-card {
  border-radius: 1rem;
  padding: 0.85rem;
  background: rgba(23, 49, 38, 0.04);
}

.overlay-item span,
.summary-card span {
  display: block;
  font-size: 0.78rem;
  color: rgba(23, 49, 38, 0.56);
}

.overlay-item strong,
.summary-card strong {
  display: block;
  margin-top: 0.35rem;
  font-size: 1rem;
}

.side-panel {
  display: grid;
  gap: 1rem;
}

.card {
  border-radius: 1.5rem;
  padding: 1.1rem;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}

.field-grid label,
.radius-field {
  display: grid;
  gap: 0.4rem;
}

.field-grid span,
.radius-field span,
.hint,
.layer-item p,
.note-box span {
  font-size: 0.82rem;
  color: rgba(23, 49, 38, 0.62);
}

input[type='number'],
input[type='text'] {
  min-height: 2.6rem;
  padding: 0.6rem 0.8rem;
  border: 1px solid rgba(23, 49, 38, 0.12);
  border-radius: 0.9rem;
  background: #fff;
}

.radius-field {
  margin-top: 1rem;
}

.radius-field input[type='range'] {
  width: 100%;
}

.hint {
  margin-top: 0.85rem;
  line-height: 1.6;
}

.pill {
  display: inline-flex;
  align-items: center;
  min-height: 2rem;
  padding: 0 0.75rem;
  border-radius: 999px;
  background: rgba(31, 93, 69, 0.1);
  color: #1f5d45;
  font-size: 0.78rem;
}

.note-box {
  margin-top: 0.9rem;
  padding: 0.95rem;
  border-radius: 1rem;
  background: rgba(31, 93, 69, 0.05);
}

.note-box p {
  margin-top: 0.35rem;
  line-height: 1.6;
}

.layer-list {
  display: grid;
  gap: 0.7rem;
  margin-top: 1rem;
}

.layer-item {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 0.75rem;
  align-items: start;
  padding: 0.8rem;
  border-radius: 1rem;
  background: rgba(23, 49, 38, 0.04);
}

.layer-swatch {
  width: 0.85rem;
  height: 0.85rem;
  border-radius: 999px;
  margin-top: 0.25rem;
}

.layer-item strong {
  display: block;
}

.layer-item p {
  margin-top: 0.25rem;
  line-height: 1.5;
}

.message {
  margin-top: 0.9rem;
  padding: 0.8rem 0.95rem;
  border-radius: 0.95rem;
  background: rgba(217, 119, 6, 0.08);
  color: #9a4f08;
}

.graph-shell :deep(.graph-panel) {
  height: 100%;
}

.graph-shell :deep(.graph-container),
.split-right :deep(.graph-container) {
  min-height: 620px;
}

@media (max-width: 1180px) {
  .hero-grid,
  .workspace,
  .split-shell {
    grid-template-columns: 1fr;
  }

  .map-stage {
    min-height: 520px;
  }

  .split-left,
  .split-right {
    min-height: 520px;
  }
}

@media (max-width: 720px) {
  .topbar,
  .panel-head,
  .card-head,
  .hero-grid {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }

  .page-shell {
    padding: 1rem;
  }

  .field-grid,
  .overlay-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .map-stage {
    min-height: 460px;
  }
}
</style>
