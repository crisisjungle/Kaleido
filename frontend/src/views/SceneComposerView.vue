<template>
  <div class="scene-composer-page">
    <header class="topbar">
      <KaleidoNavBrand to="/" />

      <div class="topbar-step">
        <span class="topbar-step-num">Step 1/5</span>
        <span class="topbar-step-name">背景生成</span>
      </div>
    </header>

    <main class="workspace-shell">
      <section class="setup-column">
        <div class="setup-scroll" :class="{ 'has-report': showReportStage }">
          <section v-if="!showReportStage" class="panel setup-panel" :class="{ 'compact-mode': !showReportStage }">
            <div class="panel-head">
              <div>
                <span class="panel-kicker">01 / 参数设置</span>
                <h2>背景参数</h2>
              </div>
              <button class="advanced-toggle" type="button" @click="advancedOpen = !advancedOpen">
                {{ advancedOpen ? '收起高级设置' : '高级设置' }}
              </button>
            </div>

            <div class="setup-form">
              <label class="field">
                <span>地点 / 区域</span>
                <input
                  v-model="form.location"
                  type="text"
                  placeholder="例：深圳前海石公园 / 切尔诺贝利核电站周边"
                  @input="handleLocationManualInput"
                />
                <small class="field-hint">{{ locationMessage }}</small>
              </label>

              <label class="field">
                <span>背景时间</span>
                <input
                  v-model="form.timeScope"
                  type="text"
                  placeholder="例：1986 年事故发生至长期恢复期 / 2024 年夏季常态"
                />
              </label>

              <label class="field field-grow">
                <span>稳态描述</span>
                <textarea
                  v-model="form.eventOrBaseline"
                  rows="4"
                  placeholder="说明这个地点在所选时间背景下的常态结构、生态基线、活动节奏和关键约束。"
                ></textarea>
              </label>

              <label class="field">
                <span>推演变量</span>
                <textarea
                  v-model="initialVariablesText"
                  rows="4"
                  placeholder="- 台风蓝色预警：增加滨海步道关闭和游客疏散压力&#10;- 周末游客峰值：提高人流和服务设施负荷"
                ></textarea>
                <small class="field-hint">支持逐行填写，也支持贴入 JSON 数组。</small>
              </label>

              <section v-if="advancedOpen" class="advanced-panel">
                <label class="field">
                  <span>重点关系 / 关注问题</span>
                  <textarea
                    v-model="form.focus"
                    rows="3"
                    placeholder="例：游客活动、滨海生态、城市开发与公园管理之间的关系。"
                  ></textarea>
                </label>

                <label class="field">
                  <span>补充背景线索</span>
                  <textarea
                    v-model="form.additionalContext"
                    rows="4"
                    placeholder="补充这个区域的历史机制、已知事实、治理背景、生态过程或其他上下文。"
                  ></textarea>
                </label>

                <label class="field">
                  <span>已知主体 / 设施 / 环境对象</span>
                  <textarea
                    v-model="form.knownEntities"
                    rows="4"
                    placeholder="- 社区居民、游客、环卫部门&#10;- 医院、污水厂、港口、地铁站&#10;- 河流、湿地、海岸带、栖息地"
                  ></textarea>
                </label>

                <label class="field">
                  <span>分析边界 / 排除项</span>
                  <textarea
                    v-model="form.analysisBoundaries"
                    rows="3"
                    placeholder="- 只分析当前片区稳态，不扩展到全市&#10;- 不讨论长期政策争议，只关注生态与运行机制"
                  ></textarea>
                </label>

                <label class="field">
                  <span>希望报告重点回答的问题</span>
                  <textarea
                    v-model="form.reportQuestions"
                    rows="4"
                    placeholder="- 这个区域的稳态主要由哪些主体和设施维持？&#10;- 哪些生态受体最敏感？&#10;- 哪些扰动会最先打破当前平衡？"
                  ></textarea>
                </label>

                <label class="field">
                  <span>进入推演的默认目标</span>
                  <textarea
                    v-model="form.simulationRequirement"
                    rows="3"
                    placeholder="例：围绕滨海公园高峰期人流、设施负荷与生态受体之间的扰动传播进行推演。"
                  ></textarea>
                </label>

                <div class="field">
                  <span>上传参考文档</span>
                  <div class="upload-box compact-upload" @click="fileInput?.click()">
                    <input ref="fileInput" class="hidden-input" type="file" multiple accept=".pdf,.md,.txt,.markdown" @change="handleFileSelect" />
                    <strong>拖入或点击上传参考文档</strong>
                    <p>支持 PDF / MD / TXT。</p>
                  </div>

                  <div v-if="files.length" class="file-list">
                    <div v-for="(file, index) in files" :key="`${file.name}-${file.size}-${index}`" class="file-chip">
                      <span>{{ file.name }}</span>
                      <button type="button" @click="removeFile(index)">×</button>
                    </div>
                  </div>
                </div>
              </section>
            </div>

            <div class="setup-actions">
              <p v-if="message" class="message">{{ message }}</p>

              <div class="button-row">
                <button class="primary-btn" type="button" :disabled="composeDisabled" @click="composeBackground">
                  {{ backgroundActionLabel }}
                </button>
              </div>
            </div>
          </section>

          <section v-else class="panel report-panel" :class="{ 'is-generating': composing }">
            <div class="panel-head panel-head-stack">
              <div>
                <span class="panel-kicker">02 / 背景报告</span>
                <h2>背景素材报告</h2>
                <p class="report-stage-summary">
                  {{ composing ? '正在基于地图分析、文档线索和输入变量生成背景报告。' : '背景报告已经生成，可以继续修改或进入场景配置。' }}
                </p>
              </div>
              <div class="panel-head-actions">
                <button v-if="composing" class="secondary-btn" type="button" @click="returnToSetup">
                  返回参数设置
                </button>
                <span class="status-pill">{{ reportStageLabel }}</span>
              </div>
            </div>

            <div class="report-progress-grid">
              <article class="report-progress-card">
                <span>地图分析</span>
                <strong>{{ mapSeedStatusLabel }}</strong>
                <p>{{ mapSeedMessage }}</p>
              </article>
              <article class="report-progress-card">
                <span>报告状态</span>
                <strong>{{ composing ? '生成中' : reportTyping ? '打字机排版中' : '已完成' }}</strong>
                <p>{{ message || '报告将按 Markdown 结构直接排版展示。' }}</p>
              </article>
            </div>

            <div class="report-surface">
              <div
                v-if="renderedReportMarkdown"
                class="report-preview prose-markdown"
                v-html="renderedReportMarkdown"
              ></div>
              <div v-else class="report-preview-empty">
                背景生成完成后，报告会显示在这里。
              </div>
            </div>

            <div class="typing-status" v-if="composing || reportTyping">
              <span class="typing-dot"></span>
              <span>{{ composing ? '正在生成背景素材报告...' : '正在逐步排版报告...' }}</span>
            </div>

            <label class="field">
              <span>补充修改说明</span>
              <textarea
                v-model="revisionInstruction"
                rows="3"
                placeholder="例：把重点改成台风天气下游客疏散和海岸线设施风险。"
              ></textarea>
            </label>

            <div class="button-row report-actions">
              <button class="secondary-btn" type="button" :disabled="!sceneId || revising || !revisionInstruction.trim()" @click="reviseReport">
                {{ revising ? '修改中...' : '按说明修改背景' }}
              </button>
              <button class="primary-btn" type="button" :disabled="!reportMarkdown.trim()" @click="enterProcess">
                进入场景配置
              </button>
            </div>
          </section>
        </div>
      </section>

      <section class="map-column">
        <div class="map-stage">
          <div class="map-head">
            <div>
              <h2>区域定位与地理分析</h2>
            </div>
            <div class="map-meta">
              <strong>{{ mapPointLabel }}</strong>
              <small>{{ mapMetaHint }}</small>
            </div>
          </div>

          <div class="map-frame">
            <div class="map-canvas">
              <LeafletMapPicker
                :center="mapCenter"
                :zoom="selectedPoint ? 12 : 10"
                :selected-point="selectedPoint"
                :radius-meters="radiusMeters"
                :layers="mapLayers"
                :read-only="showReportStage"
                @pick="handlePickPoint"
              />
            </div>

            <div v-if="!showReportStage" class="map-overlay radius-overlay">
              <div class="radius-header">
                <span>分析半径</span>
                <strong>{{ radiusMetersDisplay }}</strong>
              </div>
              <input v-model.number="radiusMeters" type="range" min="1000" max="50000" step="500" />
            </div>

          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import LeafletMapPicker from '../components/LeafletMapPicker.vue'
import { composeSceneMaterial, reviseSceneMaterial } from '../api/sceneMaterial'
import {
  createMapSeed,
  geocodeMapLocation,
  getMapSeed,
  getMapSeedLayers,
  getMapSeedStatus,
  reverseGeocodeMapLocation
} from '../api/mapSeed'
import { setPendingUpload } from '../store/pendingUpload'
import { renderMarkdown } from '../utils/markdown'

const router = useRouter()
const DEFAULT_CENTER = [22.5431, 114.0579]

const form = ref({
  location: '',
  timeScope: '',
  eventOrBaseline: '',
  focus: '',
  additionalContext: '',
  knownEntities: '',
  analysisBoundaries: '',
  reportQuestions: '',
  simulationRequirement: ''
})

const files = ref([])
const fileInput = ref(null)
const initialVariablesText = ref('')
const selectedPoint = ref(null)
const mapCenter = ref([...DEFAULT_CENTER])
const radiusMeters = ref(3000)
const mapLayers = ref([])
const mapSeedId = ref('')
const mapSeedTaskId = ref('')
const mapSeedStatus = ref('idle')
const mapSeedLoading = ref(false)
const mapSeedMessage = ref('等待背景生成时触发区域地理分析')
const locationSyncMode = ref('empty')
const locationResolving = ref(false)
const locationMessage = ref('输入地点会自动定位地图，也可以直接在地图上选点。')
const advancedOpen = ref(false)
const autoAreaLabel = ref('')
const resolvedAdminContext = ref(null)
const sceneId = ref('')
const sceneSeed = ref(null)
const reportMarkdown = ref('')
const displayedReportMarkdown = ref('')
const composing = ref(false)
const revising = ref(false)
const revisionInstruction = ref('')
const message = ref('')
const showReportStage = ref(false)
const reportTyping = ref(false)

let suppressLocationWatcher = false
let locationResolveTimer = null
let pointResolveTimer = null
let geocodeRequestId = 0
let reverseRequestId = 0
let reportTypingTimer = null
let reportTypingRequestId = 0

const radiusMetersDisplay = computed(() => {
  if (radiusMeters.value >= 1000) return `${(radiusMeters.value / 1000).toFixed(1)} km`
  return `${radiusMeters.value} m`
})

const derivedSimulationRequirement = computed(() => {
  return (
    form.value.simulationRequirement.trim() ||
    form.value.reportQuestions.trim() ||
    form.value.focus.trim() ||
    form.value.eventOrBaseline.trim() ||
    form.value.location.trim() ||
    autoAreaLabel.value ||
    '场景背景分析'
  )
})

const composeDisabled = computed(() => {
  if (composing.value || locationResolving.value) return true
  if (!selectedPoint.value) return true
  return !(
    form.value.location.trim() ||
    form.value.timeScope.trim() ||
    form.value.eventOrBaseline.trim() ||
    form.value.additionalContext.trim() ||
    form.value.knownEntities.trim() ||
    form.value.analysisBoundaries.trim() ||
    form.value.reportQuestions.trim() ||
    form.value.focus.trim() ||
    form.value.simulationRequirement.trim() ||
    initialVariablesText.value.trim() ||
    files.value.length > 0
  )
})

const backgroundActionLabel = computed(() => {
  if (composing.value) return '背景生成中...'
  if (reportMarkdown.value.trim()) return '重新生成背景'
  return '背景生成'
})

const areaNamePreview = computed(() => {
  return autoAreaLabel.value || form.value.location.trim() || '尚未确定分析区域'
})

const mapPointLabel = computed(() => {
  if (!selectedPoint.value) return '未定位'
  return areaNamePreview.value !== '尚未确定分析区域' ? areaNamePreview.value : '已锁定地图点位'
})

const mapMetaHint = computed(() => {
  if (showReportStage.value && selectedPoint.value) {
    return `${radiusMetersDisplay.value} 分析范围 · 点击区域或节点查看详情`
  }
  if (selectedPoint.value) return `${radiusMetersDisplay.value} 分析范围 · ${selectedPoint.value.lat.toFixed(5)}, ${selectedPoint.value.lon.toFixed(5)}`
  return '输入地点或点击地图锁定中心点'
})

const mapSeedStatusLabel = computed(() => {
  if (mapSeedLoading.value || mapSeedStatus.value === 'processing') return '分析中'
  if (mapSeedStatus.value === 'ready') return '已完成'
  if (mapSeedStatus.value === 'failed') return '失败'
  return '待开始'
})

const reportStageLabel = computed(() => {
  if (composing.value) return '生成中'
  if (reportTyping.value) return '排版中'
  if (reportMarkdown.value.trim()) return `${reportMarkdown.value.length} chars`
  return '待开始'
})

const previewReportMarkdown = computed(() => {
  if (displayedReportMarkdown.value.trim()) return displayedReportMarkdown.value
  if (reportMarkdown.value.trim()) return reportMarkdown.value
  if (showReportStage.value) return buildPendingReportDraft()
  return ''
})

const renderedReportMarkdown = computed(() => {
  return renderMarkdown(previewReportMarkdown.value)
})

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function clearReportTyping() {
  reportTypingRequestId += 1
  reportTyping.value = false
  if (reportTypingTimer) {
    window.clearTimeout(reportTypingTimer)
    reportTypingTimer = null
  }
}

function startReportTyping(targetText, { reset = true, interval = 16 } = {}) {
  clearReportTyping()
  const finalText = String(targetText || '')

  if (reset) {
    displayedReportMarkdown.value = ''
  }
  if (!finalText) return

  const requestId = ++reportTypingRequestId
  reportTyping.value = true

  const tick = () => {
    if (requestId !== reportTypingRequestId) return

    const currentLength = displayedReportMarkdown.value.length
    if (currentLength >= finalText.length) {
      displayedReportMarkdown.value = finalText
      reportTyping.value = false
      reportTypingTimer = null
      return
    }

    const remaining = finalText.length - currentLength
    const chunkSize = remaining > 900 ? 34 : remaining > 400 ? 20 : remaining > 120 ? 10 : 4
    displayedReportMarkdown.value = finalText.slice(0, currentLength + chunkSize)
    reportTypingTimer = window.setTimeout(tick, interval)
  }

  tick()
}

function buildPendingReportDraft() {
  const location = areaNamePreview.value
  const pointText = selectedPoint.value
    ? `${selectedPoint.value.lat.toFixed(5)}, ${selectedPoint.value.lon.toFixed(5)}`
    : '待定位'
  const variableItems = parseVariables(initialVariablesText.value)
    .slice(0, 4)
    .map((item) => `- **${item.name || '变量'}**：${item.description || item.name || '正在整理变量影响链路'}`)
  const stableDescription = form.value.eventOrBaseline.trim() || '系统正在根据输入与地图范围整理该区域的稳态描述。'

  return [
    `# ${location} 背景素材报告`,
    '',
    '> 系统已进入背景报告步骤，正在把地图分析、输入约束和上传材料整理成正式 Markdown 报告。',
    '',
    '## 区域范围',
    `- **地点 / 区域**：${location}`,
    `- **分析半径**：${radiusMetersDisplay.value}`,
    `- **中心点**：${pointText}`,
    '',
    '## 时间背景',
    form.value.timeScope.trim() || '正在整理时间范围与历史背景线索。',
    '',
    '## 当前稳态',
    stableDescription,
    '',
    '## 初始变量',
    variableItems.length ? variableItems.join('\n') : '- 正在根据输入变量生成影响链与敏感对象。',
    '',
    '## 生成状态',
    `- **地图分析**：${mapSeedStatusLabel.value} / ${mapSeedMessage.value}`,
    '- **背景报告**：正在生成结构化章节、主体关系和后续推演入口。'
  ].join('\n')
}

function clearTimers() {
  if (locationResolveTimer) {
    window.clearTimeout(locationResolveTimer)
    locationResolveTimer = null
  }
  if (pointResolveTimer) {
    window.clearTimeout(pointResolveTimer)
    pointResolveTimer = null
  }
}

function handleFileSelect(event) {
  const nextFiles = Array.from(event.target.files || [])
  const allowed = new Set(['pdf', 'md', 'txt', 'markdown'])
  const existing = new Set(files.value.map((file) => `${file.name}-${file.size}-${file.lastModified}`))
  nextFiles.forEach((file) => {
    const ext = file.name.split('.').pop()?.toLowerCase()
    const key = `${file.name}-${file.size}-${file.lastModified}`
    if (allowed.has(ext) && !existing.has(key)) {
      files.value.push(file)
      existing.add(key)
    }
  })
  event.target.value = ''
}

function removeFile(index) {
  files.value.splice(index, 1)
}

function parseVariables(text) {
  const trimmed = String(text || '').trim()
  if (!trimmed) return []
  try {
    const parsed = JSON.parse(trimmed)
    if (Array.isArray(parsed)) return parsed
    if (parsed && typeof parsed === 'object') return parsed.variables || [parsed]
  } catch {
    return trimmed
      .split('\n')
      .map((line) => line.trim().replace(/^[-•]\s*/, ''))
      .filter(Boolean)
      .map((line) => ({
        name: line.split(/[：:]/)[0].slice(0, 48),
        description: line
      }))
  }
  return []
}

function normalizeLayers(source) {
  const featurePoints = Array.isArray(source?.feature_points) ? source.feature_points : []
  const graphNodes = Array.isArray(source?.graph_nodes) ? source.graph_nodes : []
  const coordKey = (lat, lon) => `${Number(lat).toFixed(5)},${Number(lon).toFixed(5)}`
  const detailKey = (name, lat, lon) => `${String(name || '').trim()}::${coordKey(lat, lon)}`
  const featurePointMap = new Map(
    featurePoints.map((item) => [detailKey(item.name, item.lat, item.lon), item])
  )
  const graphNodeMap = new Map(
    graphNodes.map((item) => [detailKey(item.name, item.lat, item.lon), item])
  )
  const rawLayers = source?.layers || source?.geojson_layers || source?.items || source?.data || []
  if (!Array.isArray(rawLayers)) return []
  return rawLayers.map((layer, index) => ({
    id: layer.id || layer.layer_id || `layer_${index}`,
    name: layer.name || layer.title || `Layer ${index + 1}`,
    type: layer.type || layer.kind || (Array.isArray(layer.points) ? 'points' : 'geojson'),
    color: layer.color || ['#1f5d45', '#0f766e', '#d97706', '#2563eb'][index % 4],
    visible: layer.visible !== false,
    note: layer.note || layer.description || '',
    data: Array.isArray(layer.data || layer.geojson || layer.features || layer.geometry || layer.points)
      ? (layer.data || layer.geojson || layer.features || layer.geometry || layer.points).map((item) => {
        if (!item || typeof item !== 'object') return item
        const lat = Number(item.lat ?? item.latitude ?? item.y)
        const lon = Number(item.lon ?? item.lng ?? item.longitude ?? item.x)
        const matchedFeature = Number.isFinite(lat) && Number.isFinite(lon)
          ? featurePointMap.get(detailKey(item.label || item.name, lat, lon))
          : null
        const matchedGraph = Number.isFinite(lat) && Number.isFinite(lon)
          ? graphNodeMap.get(detailKey(item.label || item.name, lat, lon))
          : null
        return {
          ...item,
          popupTitle: item.popupTitle || item.label || item.name || layer.name,
          popupSummary: item.popupSummary || layer.note || '',
          popupMeta: {
            layerName: layer.name || '',
            layerNote: layer.note || '',
            featureCategory: matchedFeature?.category || '',
            featureSubtype: matchedFeature?.subtype || '',
            featureSourceKind: matchedFeature?.source_kind || matchedGraph?.source_kind || '',
            nodeLabel: matchedGraph?.label || '',
            nodeCategory: matchedGraph?.category || '',
            nodeConfidence: matchedGraph?.confidence,
          }
        }
      })
      : (layer.data || layer.geojson || layer.features || layer.geometry || layer.points || [])
  }))
}

function resetMapAnalysis(statusMessage = '等待背景生成时触发区域地理分析') {
  mapLayers.value = []
  mapSeedId.value = ''
  mapSeedTaskId.value = ''
  mapSeedStatus.value = 'idle'
  mapSeedLoading.value = false
  mapSeedMessage.value = statusMessage
}

function updateLocationValue(nextValue, mode = 'auto') {
  suppressLocationWatcher = true
  form.value.location = nextValue
  locationSyncMode.value = mode
  window.setTimeout(() => {
    suppressLocationWatcher = false
  }, 0)
}

function handleLocationManualInput() {
  locationSyncMode.value = 'manual'
  autoAreaLabel.value = ''
  resolvedAdminContext.value = null
  selectedPoint.value = null
  mapCenter.value = [...DEFAULT_CENTER]
  resetMapAnalysis('等待地点定位后开始分析')
  message.value = ''
  locationMessage.value = form.value.location.trim()
    ? '正在根据输入地点定位地图...'
    : '输入地点会自动定位地图，也可以直接在地图上选点。'
}

async function resolveLocationQuery(query) {
  const requestId = ++geocodeRequestId
  locationResolving.value = true
  locationMessage.value = `正在定位“${query}”...`

  try {
    const res = await geocodeMapLocation({
      query,
      radius_m: Number(radiusMeters.value),
      limit: 1
    })
    if (requestId !== geocodeRequestId) return

    const primary = res.data?.primary
    if (!primary) {
      locationMessage.value = `没有找到“${query}”对应的位置`
      return
    }

    selectedPoint.value = {
      lat: Number(primary.lat),
      lon: Number(primary.lon)
    }
    mapCenter.value = [selectedPoint.value.lat, selectedPoint.value.lon]
    autoAreaLabel.value = primary.area_label || primary.display_name || query
    resolvedAdminContext.value = primary.admin_context || null
    resetMapAnalysis('地点已定位，背景生成时会启动区域分析')
    locationMessage.value = `已定位到 ${primary.area_label || primary.display_name || query}`
  } catch (error) {
    if (requestId !== geocodeRequestId) return
    locationMessage.value = error.message || '地点定位失败'
  } finally {
    if (requestId === geocodeRequestId) {
      locationResolving.value = false
    }
  }
}

async function resolveAreaNameFromPoint({ updateField = false } = {}) {
  if (!selectedPoint.value) return
  const requestId = ++reverseRequestId
  locationResolving.value = true
  locationMessage.value = '正在根据点位和半径分析区域名称...'

  try {
    const res = await reverseGeocodeMapLocation({
      lat: selectedPoint.value.lat,
      lon: selectedPoint.value.lon,
      radius_m: Number(radiusMeters.value)
    })
    if (requestId !== reverseRequestId) return
    if (!res.success || !res.data) return

    autoAreaLabel.value = res.data.area_label || ''
    resolvedAdminContext.value = res.data.admin_context || null
    if (updateField) {
      updateLocationValue(autoAreaLabel.value || form.value.location || '', 'auto')
    }
    locationMessage.value = autoAreaLabel.value
      ? `已根据点位和半径锁定区域：${autoAreaLabel.value}`
      : '已根据点位分析区域名称'
  } catch (error) {
    if (requestId !== reverseRequestId) return
    locationMessage.value = error.message || '区域名称分析失败'
  } finally {
    if (requestId === reverseRequestId) {
      locationResolving.value = false
    }
  }
}

async function handlePickPoint(point) {
  selectedPoint.value = point
  mapCenter.value = [point.lat, point.lon]
  resetMapAnalysis('点位已更新，等待背景生成')
  message.value = ''
  await resolveAreaNameFromPoint({
    updateField: true
  })
}

async function waitForMapSeedReady() {
  const deadline = Date.now() + 180000
  while (Date.now() < deadline) {
    const res = await getMapSeedStatus({
      seed_id: mapSeedId.value,
      task_id: mapSeedTaskId.value || undefined
    })
    if (!res.success || !res.data) {
      await sleep(2200)
      continue
    }
    const status = String(res.data.status || '').toLowerCase()
    mapSeedMessage.value = res.data.message || mapSeedMessage.value
    if (status === 'ready' || status === 'completed') {
      mapSeedStatus.value = 'ready'
      return
    }
    if (status === 'failed' || status === 'cancelled') {
      mapSeedStatus.value = 'failed'
      throw new Error(res.data.error || (status === 'cancelled' ? '区域分析已停止' : '区域分析失败'))
    }
    await sleep(2200)
  }
  mapSeedStatus.value = 'failed'
  throw new Error('区域地理分析超时，请重试')
}

async function loadMapSeedArtifacts() {
  if (!mapSeedId.value) return
  const [seedRes, layerRes] = await Promise.allSettled([
    getMapSeed(mapSeedId.value),
    getMapSeedLayers(mapSeedId.value)
  ])

  if (layerRes.status === 'fulfilled' && layerRes.value?.success) {
    mapLayers.value = normalizeLayers(layerRes.value.data)
  }

  if (seedRes.status === 'fulfilled' && seedRes.value?.success) {
    const seed = seedRes.value.data || {}
    const input = seed.input || {}
    if (!selectedPoint.value && input.lat && input.lon) {
      selectedPoint.value = { lat: Number(input.lat), lon: Number(input.lon) }
      mapCenter.value = [selectedPoint.value.lat, selectedPoint.value.lon]
    }
    if (seed.admin_context) {
      resolvedAdminContext.value = seed.admin_context
    }
    if (seed.area_of_interest?.label) {
      autoAreaLabel.value = seed.area_of_interest.label
      if (!form.value.location.trim() || locationSyncMode.value === 'auto') {
        updateLocationValue(seed.area_of_interest.label, 'auto')
      }
    }
  }
}

async function ensureMapSeedReady() {
  if (!selectedPoint.value) {
    throw new Error('请先输入地点或在地图上选择中心点')
  }
  if (mapSeedStatus.value === 'ready' && mapSeedId.value) {
    return mapSeedId.value
  }

  mapSeedLoading.value = true
  mapSeedStatus.value = 'processing'
  mapSeedMessage.value = '正在基于地理信息分析区域...'

  try {
    const res = await createMapSeed({
      lat: selectedPoint.value.lat,
      lon: selectedPoint.value.lon,
      radius_m: Number(radiusMeters.value),
      title: areaNamePreview.value,
      simulation_requirement: derivedSimulationRequirement.value
    })
    if (!res.success || !res.data) {
      throw new Error(res.error || '区域分析任务启动失败')
    }

    mapSeedId.value = res.data.seed_id
    mapSeedTaskId.value = res.data.task_id || ''
    await waitForMapSeedReady()
    await loadMapSeedArtifacts()
    mapSeedMessage.value = '区域地理分析已完成'
    return mapSeedId.value
  } finally {
    mapSeedLoading.value = false
  }
}

function buildFormData() {
  const data = new FormData()
  files.value.forEach((file) => data.append('files', file))
  data.append('scene_type', 'stable_environment')
  data.append('location', form.value.location || autoAreaLabel.value)
  data.append('time_scope', form.value.timeScope)
  data.append('event_or_baseline', form.value.eventOrBaseline)
  data.append('focus', form.value.focus)
  data.append('additional_context', form.value.additionalContext)
  data.append('known_entities', form.value.knownEntities)
  data.append('analysis_boundaries', form.value.analysisBoundaries)
  data.append('report_questions', form.value.reportQuestions)
  data.append('simulation_requirement', derivedSimulationRequirement.value)
  data.append('initial_variables', JSON.stringify(parseVariables(initialVariablesText.value)))
  if (selectedPoint.value) {
    data.append('selected_points', JSON.stringify([
      {
        name: areaNamePreview.value || '地图主锚点',
        role: 'primary_anchor',
        lat: selectedPoint.value.lat,
        lon: selectedPoint.value.lon,
        source: 'user_map'
      }
    ]))
  }
  if (mapSeedId.value) data.append('map_seed_id', mapSeedId.value)
  return data
}

async function composeBackground() {
  if (composeDisabled.value) return
  composing.value = true
  showReportStage.value = true
  startReportTyping(buildPendingReportDraft(), { reset: true, interval: 14 })
  message.value = '正在准备区域背景...'

  try {
    await resolveAreaNameFromPoint({
      updateField: !form.value.location.trim() || locationSyncMode.value === 'auto'
    })
    await ensureMapSeedReady()
    message.value = '正在生成背景素材报告...'

    const res = await composeSceneMaterial(buildFormData())
    if (res.success && res.data) {
      applySceneSeed(res.data)
      message.value = '背景报告已生成，可以继续修改或进入场景配置。'
    }
  } catch (error) {
    message.value = error.message || '背景生成失败'
  } finally {
    composing.value = false
  }
}

async function reviseReport() {
  if (!sceneId.value || revising.value || !revisionInstruction.value.trim()) return
  revising.value = true
  message.value = '正在按说明修改背景报告...'

  try {
    const res = await reviseSceneMaterial(sceneId.value, {
      instruction: revisionInstruction.value,
      current_report: reportMarkdown.value,
      initial_variables: parseVariables(initialVariablesText.value)
    })
    if (res.success && res.data) {
      applySceneSeed(res.data)
      revisionInstruction.value = ''
      message.value = '背景报告已按说明修改。'
    }
  } catch (error) {
    message.value = error.message || '背景报告修改失败'
  } finally {
    revising.value = false
  }
}

function applySceneSeed(seed) {
  sceneSeed.value = seed
  sceneId.value = seed.scene_id || sceneId.value
  reportMarkdown.value = seed.report_markdown || ''
  showReportStage.value = true
  startReportTyping(reportMarkdown.value, { reset: true, interval: 10 })
  if (seed.recommended_simulation_requirement && !form.value.simulationRequirement.trim()) {
    form.value.simulationRequirement = seed.recommended_simulation_requirement
  }
}

function returnToSetup() {
  showReportStage.value = false
}

function enterProcess() {
  const title = sceneSeed.value?.title || areaNamePreview.value || 'scene_material'
  const filename = `${title.replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]+/g, '_').slice(0, 48) || 'scene_material'}.md`
  const file = new File([reportMarkdown.value], filename, { type: 'text/markdown' })
  const selectedPoints = selectedPoint.value
    ? [{
        name: areaNamePreview.value || autoAreaLabel.value || form.value.location || '地图主锚点',
        role: 'primary_anchor',
        lat: selectedPoint.value.lat,
        lon: selectedPoint.value.lon,
        source: 'user_map'
      }]
    : []
  setPendingUpload([file], sceneSeed.value?.recommended_simulation_requirement || derivedSimulationRequirement.value, {
    initialVariables: Array.isArray(sceneSeed.value?.initial_variables) ? sceneSeed.value.initial_variables : [],
    selectedPoints,
    mapSeedId: mapSeedId.value || sceneSeed.value?.map_seed_id || '',
    areaLabel: areaNamePreview.value || autoAreaLabel.value || form.value.location || ''
  })
  router.push({ name: 'Process', params: { projectId: 'new' } })
}

function resetComposer() {
  clearTimers()
  geocodeRequestId += 1
  reverseRequestId += 1
  form.value = {
    location: '',
    timeScope: '',
    eventOrBaseline: '',
    focus: '',
    additionalContext: '',
    knownEntities: '',
    analysisBoundaries: '',
    reportQuestions: '',
    simulationRequirement: ''
  }
  files.value = []
  initialVariablesText.value = ''
  advancedOpen.value = false
  selectedPoint.value = null
  mapCenter.value = [...DEFAULT_CENTER]
  resetMapAnalysis('等待背景生成时触发区域地理分析')
  locationSyncMode.value = 'empty'
  locationResolving.value = false
  locationMessage.value = '输入地点会自动定位地图，也可以直接在地图上选点。'
  autoAreaLabel.value = ''
  resolvedAdminContext.value = null
  sceneId.value = ''
  sceneSeed.value = null
  reportMarkdown.value = ''
  displayedReportMarkdown.value = ''
  revisionInstruction.value = ''
  message.value = ''
  showReportStage.value = false
  clearReportTyping()
}

watch(
  () => form.value.location,
  (value) => {
    if (suppressLocationWatcher || locationSyncMode.value !== 'manual') return
    const text = String(value || '').trim()
    if (locationResolveTimer) {
      window.clearTimeout(locationResolveTimer)
      locationResolveTimer = null
    }
    if (!text) {
      locationMessage.value = '输入地点会自动定位地图，也可以直接在地图上选点。'
      return
    }
    locationResolveTimer = window.setTimeout(() => {
      resolveLocationQuery(text)
    }, 500)
  }
)

watch(radiusMeters, () => {
  resetMapAnalysis(selectedPoint.value ? '分析半径已变化，需重新生成区域分析' : '等待背景生成时触发区域地理分析')
  if (!selectedPoint.value) return
  if (pointResolveTimer) {
    window.clearTimeout(pointResolveTimer)
    pointResolveTimer = null
  }
  pointResolveTimer = window.setTimeout(() => {
    resolveAreaNameFromPoint({
      updateField: !form.value.location.trim() || locationSyncMode.value === 'auto'
    })
  }, 280)
})

onBeforeUnmount(() => {
  clearTimers()
  clearReportTyping()
  geocodeRequestId += 1
  reverseRequestId += 1
})
</script>

<style scoped>
.scene-composer-page {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(25, 106, 84, 0.08), transparent 34%),
    linear-gradient(180deg, #f4f6f1 0%, #eef2ee 100%);
  color: #10231d;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 60px;
  padding: 0 24px;
  background: rgba(244, 246, 241, 0.92);
  border-bottom: 1px solid rgba(16, 35, 29, 0.08);
  backdrop-filter: blur(14px);
}
.panel-kicker,
.field-hint,
.status-label {
  color: rgba(16, 35, 29, 0.62);
}

.topbar-links {
  display: flex;
  gap: 0.75rem;
}

.topbar-step {
  display: flex;
  align-items: center;
  gap: 10px;
}

.topbar-step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  color: #999;
  letter-spacing: 0.08em;
}

.topbar-step-name {
  font-size: 14px;
  font-weight: 700;
  color: #000;
}

.ghost-link,
.primary-btn,
.secondary-btn {
  min-height: 2.75rem;
  padding: 0 1rem;
  border-radius: 12px;
  border: 1px solid rgba(16, 35, 29, 0.12);
  cursor: pointer;
  font-weight: 700;
  text-decoration: none;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.ghost-link,
.secondary-btn {
  background: rgba(255, 255, 255, 0.88);
  color: #10231d;
}

.primary-btn {
  background: linear-gradient(135deg, #174c3a, #1f7d5d);
  color: #ffffff;
  border-color: transparent;
}

.ghost-link:hover,
.secondary-btn:hover,
.primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(18, 49, 39, 0.12);
}

.primary-btn:disabled,
.secondary-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: none;
}

.workspace-shell {
  display: grid;
  grid-template-columns: minmax(420px, 520px) minmax(0, 1fr);
  gap: 1rem;
  padding: 1rem;
  min-height: calc(100vh - 60px);
}

.setup-column {
  min-width: 0;
}

.setup-scroll {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: calc(100vh - 106px);
}

.setup-scroll:not(.has-report) {
  overflow: hidden;
}

.map-column {
  min-width: 0;
}

.panel,
.map-stage {
  border-radius: 24px;
  border: 1px solid rgba(16, 35, 29, 0.08);
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 18px 48px rgba(16, 35, 29, 0.08);
}

.panel {
  padding: 1.25rem;
}

.setup-panel {
  display: flex;
  flex-direction: column;
}

.setup-panel.compact-mode {
  min-height: calc(100vh - 106px);
}

.panel-head,
.map-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.panel-head-stack {
  flex-wrap: wrap;
}

.panel-head h2,
.map-head h2 {
  margin: 0.35rem 0 0;
  font-size: 1.5rem;
}

.advanced-toggle {
  min-height: 2.5rem;
  padding: 0 0.95rem;
  border-radius: 999px;
  border: 1px solid rgba(16, 35, 29, 0.12);
  background: rgba(244, 248, 244, 0.96);
  color: #174c3a;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  height: 2.1rem;
  padding: 0 0.8rem;
  border-radius: 999px;
  background: rgba(23, 76, 58, 0.08);
  color: #174c3a;
  font-weight: 700;
}

.panel-head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.9rem;
}

.field span {
  font-size: 0.95rem;
  font-weight: 700;
}

.setup-form {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.field-grow {
  flex: 1;
  min-height: 0;
}

.field-grow textarea {
  flex: 1;
  min-height: 150px;
}

input,
textarea {
  width: 100%;
  border-radius: 16px;
  border: 1px solid rgba(16, 35, 29, 0.12);
  background: rgba(248, 251, 247, 0.92);
  color: #10231d;
  padding: 0.9rem 1rem;
  font: inherit;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

input:focus,
textarea:focus {
  outline: none;
  border-color: rgba(31, 125, 93, 0.55);
  box-shadow: 0 0 0 4px rgba(31, 125, 93, 0.1);
  background: #ffffff;
}

textarea {
  resize: vertical;
}

.upload-box {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 1rem;
  border-radius: 18px;
  border: 1px dashed rgba(16, 35, 29, 0.18);
  background: rgba(243, 247, 242, 0.88);
  cursor: pointer;
}

.upload-box strong {
  font-size: 1rem;
}

.upload-box p {
  margin: 0;
  color: rgba(16, 35, 29, 0.64);
  line-height: 1.55;
}

.compact-upload {
  padding: 0.85rem 1rem;
}

.hidden-input {
  display: none;
}

.file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.85rem;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.75rem;
  border-radius: 999px;
  background: rgba(23, 76, 58, 0.08);
  color: #174c3a;
}

.file-chip button {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 1rem;
}

.advanced-panel {
  margin-top: 1rem;
  padding-top: 0.9rem;
  border-top: 1px solid rgba(16, 35, 29, 0.08);
}

.setup-actions {
  margin-top: auto;
  padding-top: 1rem;
}

.map-meta strong {
  font-size: 1rem;
}

.map-meta small,
.field-hint {
  line-height: 1.5;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1rem;
}

.message {
  margin: 1rem 0 0;
  color: #174c3a;
  line-height: 1.6;
}

.report-panel {
  margin-bottom: 2rem;
}

.report-stage-summary {
  margin-top: 0.65rem;
  color: rgba(16, 35, 29, 0.68);
  line-height: 1.65;
}

.report-progress-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
  margin-top: 1rem;
}

.report-progress-card {
  padding: 1rem;
  border-radius: 18px;
  background: rgba(245, 249, 244, 0.9);
  border: 1px solid rgba(16, 35, 29, 0.08);
}

.report-progress-card span {
  display: block;
  font-size: 0.82rem;
  color: rgba(16, 35, 29, 0.58);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.report-progress-card strong {
  display: block;
  margin-top: 0.35rem;
  font-size: 1rem;
}

.report-progress-card p {
  margin-top: 0.45rem;
  color: rgba(16, 35, 29, 0.68);
  line-height: 1.6;
}

.report-surface {
  min-height: 380px;
  margin-top: 1rem;
  padding: 1.15rem 1.2rem;
  border-radius: 22px;
  border: 1px solid rgba(16, 35, 29, 0.08);
  background: rgba(248, 251, 247, 0.92);
}

.report-preview {
  line-height: 1.78;
  color: #173126;
}

.report-preview-empty {
  color: rgba(16, 35, 29, 0.48);
}

.typing-status {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  margin-top: 0.9rem;
  color: #174c3a;
  font-weight: 700;
}

.typing-dot {
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  background: #1f7d5d;
  animation: pulse-dot 1.1s ease-in-out infinite;
}

.report-actions {
  align-items: center;
}

.prose-markdown :deep(.md-p) {
  margin: 0 0 1em;
}

.prose-markdown :deep(.md-h2),
.prose-markdown :deep(.md-h3),
.prose-markdown :deep(.md-h4),
.prose-markdown :deep(.md-h5) {
  margin: 1.3em 0 0.65em;
  color: #10231d;
  font-weight: 800;
  line-height: 1.3;
}

.prose-markdown :deep(.md-h2) {
  font-size: 1.3rem;
  padding-bottom: 0.4rem;
  border-bottom: 1px solid rgba(16, 35, 29, 0.08);
}

.prose-markdown :deep(.md-h3) {
  font-size: 1.1rem;
}

.prose-markdown :deep(.md-h4),
.prose-markdown :deep(.md-h5) {
  font-size: 1rem;
}

.prose-markdown :deep(.md-ul),
.prose-markdown :deep(.md-ol) {
  padding-left: 1.3rem;
  margin: 0 0 1rem;
}

.prose-markdown :deep(.md-li),
.prose-markdown :deep(.md-oli) {
  margin-bottom: 0.4rem;
}

.prose-markdown :deep(.md-quote) {
  margin: 1rem 0;
  padding: 0.8rem 1rem;
  border-left: 3px solid rgba(31, 125, 93, 0.5);
  background: rgba(31, 125, 93, 0.06);
  color: rgba(16, 35, 29, 0.76);
}

.prose-markdown :deep(.code-block) {
  margin: 1rem 0;
  padding: 0.95rem 1rem;
  border-radius: 16px;
  background: #10231d;
  color: #ecf5ef;
  overflow-x: auto;
}

.prose-markdown :deep(.inline-code) {
  padding: 0.12rem 0.36rem;
  border-radius: 8px;
  background: rgba(23, 76, 58, 0.08);
  color: #174c3a;
  font-size: 0.92em;
}

.prose-markdown :deep(.md-link) {
  color: #1f7d5d;
  font-weight: 700;
  text-decoration: none;
}

.prose-markdown :deep(.md-link:hover) {
  text-decoration: underline;
}

@keyframes pulse-dot {
  50% {
    opacity: 0.35;
    transform: scale(0.85);
  }
}

.map-stage {
  position: sticky;
  top: 88px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  min-height: calc(100vh - 106px);
}

.map-head {
  margin-bottom: 0.25rem;
}

.map-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.2rem;
  text-align: right;
}

.map-frame {
  position: relative;
  flex: 1;
  min-height: 520px;
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid rgba(16, 35, 29, 0.08);
  background: #d9e6de;
}

.map-canvas {
  position: absolute;
  inset: 0;
}

.map-canvas :deep(.leaflet-map-picker) {
  height: 100%;
  width: 100%;
  min-height: 0;
}

.map-overlay {
  position: absolute;
  z-index: 500;
  backdrop-filter: blur(12px);
}

.radius-overlay {
  left: 1rem;
  right: 1rem;
  bottom: 1rem;
  padding: 0.9rem 1rem;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(16, 35, 29, 0.08);
  box-shadow: 0 16px 36px rgba(16, 35, 29, 0.12);
}

.radius-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.55rem;
  font-weight: 700;
}

.radius-overlay input[type='range'] {
  padding: 0;
  background: transparent;
  border: 0;
  box-shadow: none;
}

@media (max-width: 1180px) {
  .workspace-shell {
    grid-template-columns: 1fr;
  }

  .setup-scroll {
    min-height: auto;
    overflow: visible;
  }

  .setup-panel.compact-mode {
    min-height: auto;
  }

  .map-stage {
    position: static;
    min-height: 720px;
  }

  .report-progress-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .topbar,
  .topbar-step,
  .panel-head,
  .map-head,
  .button-row {
    flex-direction: column;
  }

  .workspace-shell {
    padding: 0.75rem;
  }

  .panel,
  .map-stage {
    padding: 1rem;
    border-radius: 20px;
  }

  .map-meta {
    align-items: flex-start;
    text-align: left;
  }

  .map-frame,
  .map-canvas :deep(.leaflet-map-picker) {
    min-height: 420px;
  }

  .panel-head-actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
