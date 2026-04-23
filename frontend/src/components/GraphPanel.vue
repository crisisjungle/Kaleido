<template>
  <div class="graph-panel">
    <div class="panel-header">
      <div class="panel-title-wrap">
        <span class="panel-title">Graph Relationship Visualization</span>
        <span v-if="highlightLabel" class="focus-badge">{{ highlightLabel }}</span>
      </div>
      <!-- 顶部工具栏 (Internal Top Right) -->
      <div class="header-tools">
        <div class="mode-switch">
          <button
            class="mode-btn"
            :class="{ active: graphMode === 'map' }"
            @click="setGraphMode('map')"
            title="地图关系"
          >
            地图
          </button>
          <button
            class="mode-btn"
            :class="{ active: graphMode === '2d' }"
            @click="setGraphMode('2d')"
            title="2D 图谱"
          >
            2D
          </button>
          <button
            class="mode-btn"
            :class="{ active: graphMode === '3d' }"
            @click="setGraphMode('3d')"
            title="3D 球形图谱"
          >
            3D
          </button>
        </div>
        <button class="tool-btn" @click="$emit('refresh')" :disabled="loading" title="刷新图谱">
          <span class="icon-refresh" :class="{ 'spinning': loading }">↻</span>
          <span class="btn-text">Refresh</span>
        </button>
        <button class="tool-btn" @click="$emit('toggle-maximize')" title="最大化/还原">
          <span class="icon-maximize">⛶</span>
        </button>
      </div>
    </div>
    
    <div class="graph-container" ref="graphContainer">
      <MapRelationPanel
        v-show="graphMode === 'map'"
        class="embedded-map-panel"
        :mapData="mapData"
        :loading="loading"
        :highlightNodeIds="highlightNodeIds"
        :highlightNodeNames="highlightNodeNames"
        :highlightEdgeIds="highlightEdgeIds"
        :highlightLabel="highlightLabel"
        :highlightMode="highlightMode"
        embedded
        @refresh="$emit('refresh')"
        @toggle-maximize="$emit('toggle-maximize')"
      />

      <!-- 图谱可视化 -->
      <div v-if="hasGraphContent" v-show="graphMode !== 'map'" class="graph-view">
        <svg v-show="graphMode === '2d'" ref="graphSvg" class="graph-svg"></svg>
        <div v-show="graphMode === '3d'" ref="graph3dContainer" class="graph-3d-view"></div>
        
        <!-- 构建中/模拟中提示 -->
        <div v-if="currentPhase === 1 || isSimulating" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
              <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-4.04z" />
            </svg>
          </div>
          {{ isSimulating ? 'GraphRAG长短期记忆实时更新中' : '实时更新中...' }}
        </div>
        
        <!-- 模拟结束后的提示 -->
        <div v-if="showSimulationFinishedHint" class="graph-building-hint finished-hint">
          <div class="hint-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="hint-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <span class="hint-text">还有少量内容处理中，建议稍后手动刷新图谱</span>
          <button class="hint-close-btn" @click="dismissFinishedHint" title="关闭提示">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <!-- 节点/边详情面板 -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-panel-header">
            <span class="detail-title">{{ selectedItem.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
            <span v-if="selectedItem.type === 'node'" class="detail-type-badge" :style="{ background: selectedItem.color, color: '#fff' }">
              {{ selectedItem.entityType }}
            </span>
            <button class="detail-close" @click="closeDetailPanel">×</button>
          </div>
          
          <!-- 节点详情 -->
          <div v-if="selectedItem.type === 'node'" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">Name:</span>
              <span class="detail-value">{{ selectedItem.data.name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">UUID:</span>
              <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
            </div>
            <div class="detail-row" v-if="selectedItem.data.created_at">
              <span class="detail-label">Created:</span>
              <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
            </div>
            
            <!-- Properties -->
            <div class="detail-section" v-if="selectedItem.data.attributes && Object.keys(selectedItem.data.attributes).length > 0">
              <div class="section-title">Properties:</div>
              <div class="properties-list">
                <div v-for="(value, key) in selectedItem.data.attributes" :key="key" class="property-item">
                  <span class="property-key">{{ key }}:</span>
                  <span class="property-value">{{ value || 'None' }}</span>
                </div>
              </div>
            </div>
            
            <!-- Summary -->
            <div class="detail-section" v-if="selectedItem.data.summary">
              <div class="section-title">Summary:</div>
              <div class="summary-text">{{ selectedItem.data.summary }}</div>
            </div>
            
            <!-- Labels -->
            <div class="detail-section" v-if="selectedItem.data.labels && selectedItem.data.labels.length > 0">
              <div class="section-title">Labels:</div>
              <div class="labels-list">
                <span v-for="label in selectedItem.data.labels" :key="label" class="label-tag">
                  {{ label }}
                </span>
              </div>
            </div>

            <div v-if="enableAnalysisActions" class="detail-section node-action-section">
              <div class="section-title">节点操作</div>
              <div class="node-action-buttons">
                <button class="node-action-btn" @click="triggerNodeAction('view')">查看详情</button>
                <button class="node-action-btn" @click="triggerNodeAction('chat')">开始交流</button>
                <button class="node-action-btn primary" @click="triggerNodeAction('explore')">深度探索</button>
              </div>
            </div>
          </div>
          
          <!-- 边详情 -->
          <div v-else class="detail-content">
            <!-- 自环组详情 -->
            <template v-if="selectedItem.data.isSelfLoopGroup">
              <div class="edge-relation-header self-loop-header">
                {{ selectedItem.data.source_name }} - Self Relations
                <span class="self-loop-count">{{ selectedItem.data.selfLoopCount }} items</span>
              </div>
              
              <div class="self-loop-list">
                <div 
                  v-for="(loop, idx) in selectedItem.data.selfLoopEdges" 
                  :key="loop.uuid || idx" 
                  class="self-loop-item"
                  :class="{ expanded: expandedSelfLoops.has(loop.uuid || idx) }"
                >
                  <div 
                    class="self-loop-item-header"
                    @click="toggleSelfLoop(loop.uuid || idx)"
                  >
                    <span class="self-loop-index">#{{ idx + 1 }}</span>
                    <span class="self-loop-name">{{ loop.name || loop.fact_type || 'RELATED' }}</span>
                    <span class="self-loop-toggle">{{ expandedSelfLoops.has(loop.uuid || idx) ? '−' : '+' }}</span>
                  </div>
                  
                  <div class="self-loop-item-content" v-show="expandedSelfLoops.has(loop.uuid || idx)">
                    <div class="detail-row" v-if="loop.uuid">
                      <span class="detail-label">UUID:</span>
                      <span class="detail-value uuid-text">{{ loop.uuid }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact">
                      <span class="detail-label">Fact:</span>
                      <span class="detail-value fact-text">{{ loop.fact }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact_type">
                      <span class="detail-label">Type:</span>
                      <span class="detail-value">{{ loop.fact_type }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.created_at">
                      <span class="detail-label">Created:</span>
                      <span class="detail-value">{{ formatDateTime(loop.created_at) }}</span>
                    </div>
                    <div v-if="loop.episodes && loop.episodes.length > 0" class="self-loop-episodes">
                      <span class="detail-label">Episodes:</span>
                      <div class="episodes-list compact">
                        <span v-for="ep in loop.episodes" :key="ep" class="episode-tag small">{{ ep }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            
            <!-- 普通边详情 -->
            <template v-else>
              <div class="edge-relation-header">
                {{ selectedItem.data.source_name }} → {{ selectedItem.data.name || 'RELATED_TO' }} → {{ selectedItem.data.target_name }}
              </div>
              
              <div class="detail-row">
                <span class="detail-label">UUID:</span>
                <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Label:</span>
                <span class="detail-value">{{ selectedItem.data.name || 'RELATED_TO' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">Type:</span>
                <span class="detail-value">{{ selectedItem.data.fact_type || 'Unknown' }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.fact">
                <span class="detail-label">Fact:</span>
                <span class="detail-value fact-text">{{ selectedItem.data.fact }}</span>
              </div>
              
              <!-- Episodes -->
              <div class="detail-section" v-if="selectedItem.data.episodes && selectedItem.data.episodes.length > 0">
                <div class="section-title">Episodes:</div>
                <div class="episodes-list">
                  <span v-for="ep in selectedItem.data.episodes" :key="ep" class="episode-tag">
                    {{ ep }}
                  </span>
                </div>
              </div>
              
              <div class="detail-row" v-if="selectedItem.data.created_at">
                <span class="detail-label">Created:</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.valid_at">
                <span class="detail-label">Valid From:</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.valid_at) }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- Step 2 图谱准备态 -->
      <div v-if="graphMode !== 'map' && !hasGraphContent && showSceneDesignLoadingState" class="graph-state graph-state-network">
        <div class="network-loader" aria-hidden="true">
          <span class="network-ring ring-a"></span>
          <span class="network-ring ring-b"></span>
          <span class="network-ring ring-c"></span>
          <span class="network-node node-core"></span>
          <span class="network-node node-top"></span>
          <span class="network-node node-right"></span>
          <span class="network-node node-bottom"></span>
          <span class="network-node node-left"></span>
          <span class="network-link link-top"></span>
          <span class="network-link link-right"></span>
          <span class="network-link link-bottom"></span>
          <span class="network-link link-left"></span>
        </div>
        <p class="graph-state-title">{{ loading ? '图谱正在接入场景设计' : '场景图谱准备中' }}</p>
        <p class="graph-state-subtitle">
          {{ loading ? '正在同步区域、主体和关系节点，请稍候。' : '区域、主体和交互关系会在图谱就绪后自动填入右侧配置。' }}
        </p>
        <div class="graph-loading-tags">
          <span class="loading-tag">区域骨架</span>
          <span class="loading-tag">主体锚点</span>
          <span class="loading-tag">关系网络</span>
        </div>
      </div>

      <!-- 通用加载状态 -->
      <div v-else-if="graphMode !== 'map' && loading" class="graph-state">
        <div class="loading-spinner"></div>
        <p>图谱数据加载中...</p>
      </div>
      
      <!-- 等待/空状态 -->
      <div v-else-if="graphMode !== 'map'" class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ currentPhase === 4 ? '结果图谱暂无可用节点' : '等待本体生成...' }}</p>
      </div>
    </div>

    <!-- 底部图例 (Bottom Left) -->
    <div v-if="hasGraphContent && graphMode !== 'map' && entityTypes.length" class="graph-legend">
      <span class="legend-title">Entity Types</span>
      <div class="legend-items">
        <div class="legend-item" v-for="type in entityTypes" :key="type.name">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.name }}</span>
        </div>
      </div>
    </div>
    
    <!-- 显示边标签开关 -->
    <div v-if="hasGraphContent && graphMode === '2d'" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">Show Edge Labels</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'
import MapRelationPanel from './MapRelationPanel.vue'

const props = defineProps({
  graphData: Object,
  mapData: {
    type: Object,
    default: null
  },
  loading: Boolean,
  currentPhase: Number,
  isSimulating: Boolean,
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
  enableAnalysisActions: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['refresh', 'toggle-maximize', 'node-select', 'node-action'])

const graphContainer = ref(null)
const graphSvg = ref(null)
const graph3dContainer = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(false)
const graphMode = ref('map')
const expandedSelfLoops = ref(new Set()) // 展开的自环项
const showSimulationFinishedHint = ref(false) // 模拟结束后的提示
const wasSimulating = ref(false) // 追踪之前是否在模拟中

const setGraphMode = (mode) => {
  graphMode.value = ['map', '2d', '3d'].includes(mode) ? mode : '2d'
}

const normalizeHighlightToken = (value) => String(value || '').trim().toLowerCase()

const uniqueTokens = (items) => Array.from(
  new Set(
    (items || [])
      .map(item => normalizeHighlightToken(item))
      .filter(Boolean)
  )
)

const buildEdgeHighlightKeys = (edge, fallbackSource = '', fallbackTarget = '', fallbackType = '', fallbackIndex = 0) => {
  const source = normalizeHighlightToken(fallbackSource || edge?.source_node_uuid || edge?.source || edge?.from)
  const target = normalizeHighlightToken(fallbackTarget || edge?.target_node_uuid || edge?.target || edge?.to)
  const type = normalizeHighlightToken(fallbackType || edge?.fact_type || edge?.name || edge?.type || 'related')
  const pairKey = source && target ? `${source}::${target}` : ''
  const reversePairKey = source && target ? `${target}::${source}` : ''
  const labeledPairKey = pairKey && type ? `${pairKey}::${type}` : ''
  const reverseLabeledPairKey = reversePairKey && type ? `${reversePairKey}::${type}` : ''
  return uniqueTokens([
    edge?.edge_id,
    edge?.edgeId,
    edge?.uuid,
    edge?.id,
    edge?.fact_id,
    edge?.factId,
    edge?.relationship_id,
    edge?.relationshipId,
    edge?.link_id,
    edge?.linkId,
    edge?.transport_edge_id,
    edge?.transportEdgeId,
    edge?.dynamic_edge_id,
    edge?.dynamicEdgeId,
    edge?.source_target_id,
    edge?.sourceTargetId,
    pairKey,
    reversePairKey,
    labeledPairKey,
    reverseLabeledPairKey,
    `${labeledPairKey}::${fallbackIndex}`,
    `${reverseLabeledPairKey}::${fallbackIndex}`,
    `${source}::${target}::${fallbackIndex}`,
  ])
}

// 关闭模拟结束提示
const dismissFinishedHint = () => {
  showSimulationFinishedHint.value = false
}

// 监听 isSimulating 变化，检测模拟结束
watch(() => props.isSimulating, (newValue, oldValue) => {
  if (newValue) {
    showEdgeLabels.value = false
  }
  if (wasSimulating.value && !newValue) {
    // 从模拟中变为非模拟状态，显示结束提示
    showSimulationFinishedHint.value = true
  }
  wasSimulating.value = newValue
}, { immediate: true })

// 切换自环项展开/折叠状态
const toggleSelfLoop = (id) => {
  const newSet = new Set(expandedSelfLoops.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  expandedSelfLoops.value = newSet
}

// 计算实体类型用于图例
const entityTypes = computed(() => {
  if (!props.graphData?.nodes) return []
  const typeMap = {}
  // 美观的颜色调色板
  const colors = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']
  
  props.graphData.nodes.forEach(node => {
    const type = node.labels?.find(l => l !== 'Entity') || 'Entity'
    if (!typeMap[type]) {
      typeMap[type] = { name: type, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
    }
    typeMap[type].count++
  })
  return Object.values(typeMap)
})

const hasGraphContent = computed(() => {
  const nodes = props.graphData?.nodes || []
  const edges = props.graphData?.edges || []
  return nodes.length > 0 || edges.length > 0
})

const showSceneDesignLoadingState = computed(() => {
  return props.currentPhase === 2 && !hasGraphContent.value
})

// 格式化时间
const formatDateTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true 
    })
  } catch {
    return dateStr
  }
}

const buildNodePayload = (item) => {
  if (!item || item.type !== 'node' || !item.data) return null
  return {
    uuid: item.data.uuid,
    name: item.data.name,
    labels: item.data.labels || [],
    summary: item.data.summary || '',
    attributes: item.data.attributes || {},
    entityType: item.entityType,
    color: item.color,
  }
}

const closeDetailPanel = () => {
  selectedItem.value = null
  expandedSelfLoops.value = new Set() // 重置展开状态
}

const triggerNodeAction = (action) => {
  const payload = buildNodePayload(selectedItem.value)
  if (!payload) return
  emit('node-action', {
    action,
    node: payload,
    timestamp: Date.now(),
  })
}

let currentSimulation = null
let linkLabelsRef = null
let linkLabelBgRef = null
let graph3DInstance = null
let forceGraph3DFactory = null
let THREERef = null
let SpriteTextClass = null
let renderFrame = null
let resizeTimer = null

const scheduleGraphRender = () => {
  if (renderFrame !== null) {
    cancelAnimationFrame(renderFrame)
  }
  renderFrame = requestAnimationFrame(() => {
    renderFrame = null
    void renderActiveGraph()
  })
}

const load3DDeps = async () => {
  if (forceGraph3DFactory && THREERef && SpriteTextClass) {
    return {
      createGraph3D: forceGraph3DFactory,
      THREE: THREERef,
      SpriteText: SpriteTextClass,
    }
  }

  const [graphModule, threeModule, spriteTextModule] = await Promise.all([
    import('3d-force-graph'),
    import('three'),
    import('three-spritetext'),
  ])
  forceGraph3DFactory = graphModule.default || graphModule
  THREERef = threeModule
  SpriteTextClass = spriteTextModule.default || spriteTextModule

  return {
    createGraph3D: forceGraph3DFactory,
    THREE: THREERef,
    SpriteText: SpriteTextClass,
  }
}

const stop2DSimulation = () => {
  if (currentSimulation) {
    currentSimulation.stop()
    currentSimulation = null
  }
}

const destroy3DGraph = () => {
  if (!graph3DInstance) return
  try {
    graph3DInstance._destructor?.()
  } catch {
    // ignore cleanup failures from underlying 3D engine
  }
  graph3DInstance = null
}

const getNodeColorByType = (type) => {
  const colorMap = {}
  entityTypes.value.forEach(t => {
    colorMap[t.name] = t.color
  })
  return colorMap[type] || '#999'
}

const nodeLayerKey = (node) => {
  const type = String(node.type || '').toLowerCase()
  const labels = (node.rawData?.labels || []).map(item => String(item || '').toLowerCase())
  if (type.includes('region') && !labels.includes('subregion')) return 'macro'
  if (type.includes('subregion') || labels.includes('subregion')) return 'subregion'
  if (type.includes('actor') || type.includes('receptor') || type.includes('carrier') || type.includes('infrastructure')) return 'agent'
  return 'agent'
}

const fibonacciSpherePoint = (index, total, radius) => {
  if (total <= 0) return { x: 0, y: 0, z: 0 }
  if (total === 1) return { x: radius, y: 0, z: 0 }
  const offset = 2 / total
  const y = ((index * offset) - 1) + (offset / 2)
  const r = Math.sqrt(Math.max(0, 1 - y * y))
  const phi = index * Math.PI * (3 - Math.sqrt(5))
  return {
    x: Math.cos(phi) * r * radius,
    y: y * radius,
    z: Math.sin(phi) * r * radius,
  }
}

const applySphereLayout = (nodes) => {
  const groups = {
    macro: [],
    subregion: [],
    agent: [],
  }
  nodes.forEach(node => {
    const key = nodeLayerKey(node)
    groups[key].push(node)
  })

  const radiusByLayer = {
    macro: 170,
    subregion: 300,
    agent: 430,
  }

  Object.entries(groups).forEach(([layer, list]) => {
    const radius = radiusByLayer[layer] || 320
    list.forEach((node, index) => {
      const point = fibonacciSpherePoint(index, list.length, radius)
      node.x = point.x
      node.y = point.y
      node.z = point.z
      node.fx = point.x
      node.fy = point.y
      node.fz = point.z
    })
  })
}

const formatSurfaceLabel = (name) => {
  const text = String(name || '').trim()
  if (!text) return ''
  return text.length > 8 ? `${text.slice(0, 8)}…` : text
}

const renderGraph3D = async () => {
  if (!graph3dContainer.value || !props.graphData) return

  stop2DSimulation()
  const container = graph3dContainer.value
  const width = container.clientWidth || 800
  const height = container.clientHeight || 600

  const nodesData = props.graphData.nodes || []
  const edgesData = props.graphData.edges || []
  if (nodesData.length === 0) {
    destroy3DGraph()
    return
  }

  const nodes = nodesData.map(node => ({
    id: node.uuid,
    name: node.name || 'Unnamed',
    type: node.labels?.find(label => label !== 'Entity') || 'Entity',
    rawData: node,
  }))
  nodes.forEach(node => {
    node.layer = nodeLayerKey(node)
    node.showSurfaceLabel = node.layer === 'agent'
    node.surfaceLabel = formatSurfaceLabel(node.name)
  })
  const nodeMap = new Map(nodes.map(node => [node.id, node]))
  const nodeIds = new Set(nodes.map(node => node.id))
  const highlightedIdSet = new Set(
    (props.highlightNodeIds || [])
      .map(item => String(item || '').trim())
      .filter(Boolean)
  )
  const highlightedNameSet = new Set(
    (props.highlightNodeNames || [])
      .map(item => String(item || '').trim().toLowerCase())
      .filter(Boolean)
  )
  const highlightedEdgeIdSet = new Set(uniqueTokens(props.highlightEdgeIds || []))

  nodes.forEach(node => {
    const nodeName = String(node.name || '').trim().toLowerCase()
    node.externallyHighlighted = highlightedIdSet.has(node.id) || highlightedNameSet.has(nodeName)
  })
  const highlightedNodeIds = new Set(
    nodes
      .filter(node => node.externallyHighlighted)
      .map(node => node.id)
  )
  const highlightActive = highlightedNodeIds.size > 0 || highlightedEdgeIdSet.size > 0

  const links = edgesData
    .filter(edge => nodeIds.has(edge.source_node_uuid) && nodeIds.has(edge.target_node_uuid))
    .map((edge, index) => ({
      source: edge.source_node_uuid,
      target: edge.target_node_uuid,
      name: edge.name || edge.fact_type || 'RELATED',
      type: edge.fact_type || edge.name || 'RELATED',
      highlightKeys: buildEdgeHighlightKeys(
        edge,
        edge.source_node_uuid,
        edge.target_node_uuid,
        edge.fact_type || edge.name || 'RELATED',
        index
      ),
      rawData: {
        ...edge,
        source_name: nodeMap.get(edge.source_node_uuid)?.name,
        target_name: nodeMap.get(edge.target_node_uuid)?.name,
      },
    }))

  const isEdgeHighlighted = (linkData) => (linkData.highlightKeys || []).some(token => highlightedEdgeIdSet.has(token))
  const getNodeId = (nodeRef) => (typeof nodeRef === 'object' ? nodeRef?.id : nodeRef)
  const isLinkFocused = (linkData) => {
    if (isEdgeHighlighted(linkData)) return true
    const sourceId = getNodeId(linkData.source)
    const targetId = getNodeId(linkData.target)
    return highlightedNodeIds.has(sourceId) || highlightedNodeIds.has(targetId)
  }

  const edgeHighlightColor = props.highlightMode === 'risk_runtime'
    ? '#E04F39'
    : props.highlightMode === 'risk_definition'
      ? '#F08A24'
      : '#E0A25A'
  const edgeNeighborColor = '#E0A25A'

  let previousCamera = null
  let previousTarget = null
  let previousNodePosById = null
  if (graph3DInstance) {
    const camera = graph3DInstance.camera?.()
    if (camera) {
      previousCamera = { x: camera.position.x, y: camera.position.y, z: camera.position.z }
    }
    const controls = graph3DInstance.controls?.()
    if (controls?.target) {
      previousTarget = {
        x: controls.target.x,
        y: controls.target.y,
        z: controls.target.z,
      }
    }
    const previousGraph = graph3DInstance.graphData?.()
    if (previousGraph?.nodes?.length) {
      previousNodePosById = new Map(
        previousGraph.nodes.map(node => [
          String(node.id),
          { x: Number(node.x) || 0, y: Number(node.y) || 0, z: Number(node.z) || 0 },
        ])
      )
    }
  }

  applySphereLayout(nodes)
  if (previousNodePosById) {
    nodes.forEach(node => {
      const oldPos = previousNodePosById.get(String(node.id))
      if (!oldPos) return
      node.x = oldPos.x
      node.y = oldPos.y
      node.z = oldPos.z
      node.fx = oldPos.x
      node.fy = oldPos.y
      node.fz = oldPos.z
    })
  }

  const { createGraph3D, THREE, SpriteText } = await load3DDeps()
  if (graphMode.value !== '3d') return

  const createdNewInstance = !graph3DInstance
  if (createdNewInstance) {
    graph3DInstance = createGraph3D()(container)
  }
  const createNodeObject = (node) => {
    const group = new THREE.Group()
    const baseColor = getNodeColorByType(node.type)
    const highlighted = Boolean(node.externallyHighlighted)
    const radius = !highlightActive ? 4 : highlighted ? 6 : 3

    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(radius, 18, 18),
      new THREE.MeshLambertMaterial({
        color: baseColor,
        transparent: true,
        opacity: highlightActive ? (highlighted ? 0.98 : 0.42) : 0.95,
      })
    )
    group.add(sphere)

    if (node.showSurfaceLabel && node.surfaceLabel) {
      const label = new SpriteText(node.surfaceLabel)
      label.textHeight = highlighted ? 11 : 9.5
      label.color = highlighted ? '#111111' : '#1F2933'
      label.backgroundColor = highlightActive && !highlighted ? 'rgba(255,255,255,0.78)' : 'rgba(255,255,255,0.95)'
      label.padding = 2.2
      label.borderWidth = 1.2
      label.borderColor = 'rgba(55,65,81,0.35)'
      label.strokeWidth = 1.8
      label.strokeColor = 'rgba(255,255,255,0.98)'
      if (label.material) {
        label.material.depthWrite = false
        label.material.depthTest = false
        label.material.transparent = true
        label.material.opacity = highlightActive && !highlighted ? 0.95 : 1
      }
      label.renderOrder = 999
      const x = Number(node.x) || 0
      const y = Number(node.y) || 0
      const z = Number(node.z) || 0
      const length = Math.sqrt(x * x + y * y + z * z) || 1
      const outward = radius + 10
      label.position.set((x / length) * outward, (y / length) * outward, (z / length) * outward)
      group.add(label)
    }

    return group
  }

  graph3DInstance
    .width(width)
    .height(height)
    .backgroundColor('rgba(0,0,0,0)')
    .graphData({ nodes, links })
    .nodeId('id')
    .nodeThreeObject(createNodeObject)
    .nodeThreeObjectExtend(false)
    .nodeLabel(node => `${node.name}\n${node.type}`)
    .nodeVal(node => {
      if (!highlightActive) return 4
      return node.externallyHighlighted ? 8 : 3
    })
    .nodeColor(node => {
      const base = getNodeColorByType(node.type)
      if (!highlightActive) return base
      return node.externallyHighlighted ? base : '#BDBDBD'
    })
    .linkColor(link => {
      if (!highlightActive) return 'rgba(170,170,170,0.42)'
      if (isEdgeHighlighted(link)) return edgeHighlightColor
      if (isLinkFocused(link)) return edgeNeighborColor
      return 'rgba(170,170,170,0.1)'
    })
    .linkWidth(link => {
      if (!highlightActive) return 0.55
      if (isEdgeHighlighted(link)) return 1.8
      if (isLinkFocused(link)) return 1.15
      return 0.16
    })
    .linkOpacity(link => {
      if (!highlightActive) return 0.26
      return isLinkFocused(link) ? 0.62 : 0.06
    })
    .linkDirectionalParticles(link => (isEdgeHighlighted(link) ? 2 : 0))
    .linkDirectionalParticleWidth(link => (isEdgeHighlighted(link) ? 2.2 : 0))
    .onNodeClick((node) => {
      selectedItem.value = {
        type: 'node',
        data: node.rawData,
        entityType: node.type,
        color: getNodeColorByType(node.type),
      }
      emit('node-select', buildNodePayload(selectedItem.value))
    })
    .onLinkClick((link) => {
      selectedItem.value = {
        type: 'edge',
        data: link.rawData,
      }
    })
    .onBackgroundClick(() => {
      selectedItem.value = null
    })

  const controls = graph3DInstance.controls?.()
  if (controls) {
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.rotateSpeed = 0.65
    controls.zoomSpeed = 0.9
    controls.panSpeed = 0.45
  }
  if (createdNewInstance) {
    graph3DInstance.cameraPosition({ x: 0, y: 0, z: 1050 })
  } else if (previousCamera) {
    graph3DInstance.cameraPosition(previousCamera)
    const nextControls = graph3DInstance.controls?.()
    if (nextControls?.target && previousTarget) {
      nextControls.target.set(previousTarget.x, previousTarget.y, previousTarget.z)
      nextControls.update?.()
    }
  }
}

const renderActiveGraph = async () => {
  if (graphMode.value === 'map') {
    stop2DSimulation()
    destroy3DGraph()
    return
  }
  if (graphMode.value === '3d') {
    await renderGraph3D()
  } else {
    destroy3DGraph()
    renderGraph()
  }
}

const renderGraph = () => {
  if (!graphSvg.value || !props.graphData) return
  
  // 停止之前的仿真并保存节点位置以防止图谱不必要地跳动
  const oldNodeMap = new Map()
  if (currentSimulation) {
    currentSimulation.nodes().forEach(oldNode => {
      oldNodeMap.set(oldNode.id, oldNode)
    })
    currentSimulation.stop()
  }
  
  const container = graphContainer.value
  const width = container.clientWidth
  const height = container.clientHeight
  
  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)
    
  svg.selectAll('*').remove()
  
  const nodesData = props.graphData.nodes || []
  const edgesData = props.graphData.edges || []
  
  if (nodesData.length === 0) return

  // Prep data
  const nodeMap = {}
  nodesData.forEach(n => nodeMap[n.uuid] = n)
  
  const nodes = nodesData.map(n => {
    const oldNode = oldNodeMap.get(n.uuid)
    return {
      id: n.uuid,
      name: n.name || 'Unnamed',
      type: n.labels?.find(l => l !== 'Entity') || 'Entity',
      rawData: n,
      x: oldNode ? oldNode.x : undefined,
      y: oldNode ? oldNode.y : undefined,
      fx: oldNode && oldNode.fx !== null ? oldNode.fx : undefined,
      fy: oldNode && oldNode.fy !== null ? oldNode.fy : undefined,
      vx: oldNode ? oldNode.vx : undefined,
      vy: oldNode ? oldNode.vy : undefined,
      _isDragging: oldNode ? oldNode._isDragging : false
    }
  })

  const highlightedIdSet = new Set(
    (props.highlightNodeIds || [])
      .map(item => String(item || '').trim())
      .filter(Boolean)
  )
  const highlightedNameSet = new Set(
    (props.highlightNodeNames || [])
      .map(item => String(item || '').trim().toLowerCase())
      .filter(Boolean)
  )
  const highlightedEdgeIdSet = new Set(uniqueTokens(props.highlightEdgeIds || []))
  const highlightActive = highlightedIdSet.size > 0 || highlightedNameSet.size > 0 || highlightedEdgeIdSet.size > 0

  nodes.forEach(node => {
    const nodeName = String(node.name || '').trim().toLowerCase()
    node.externallyHighlighted = highlightedIdSet.has(node.id) || highlightedNameSet.has(nodeName)
  })

  const highlightedNodeIds = new Set(
    nodes
      .filter(node => node.externallyHighlighted)
      .map(node => node.id)
  )
  
  const nodeIds = new Set(nodes.map(n => n.id))
  
  // 处理边数据，计算同一对节点间的边数量和索引
  const edgePairCount = {}
  const selfLoopEdges = {} // 按节点分组的自环边
  const tempEdges = edgesData
    .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))
  
  // 统计每对节点之间的边数量，收集自环边
  tempEdges.forEach(e => {
    if (e.source_node_uuid === e.target_node_uuid) {
      // 自环 - 收集到数组中
      if (!selfLoopEdges[e.source_node_uuid]) {
        selfLoopEdges[e.source_node_uuid] = []
      }
      selfLoopEdges[e.source_node_uuid].push({
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      })
    } else {
      const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
      edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
    }
  })
  
  // 记录当前处理到每对节点的第几条边
  const edgePairIndex = {}
  const processedSelfLoopNodes = new Set() // 已处理的自环节点
  
  const edges = []
  
  tempEdges.forEach(e => {
    const isSelfLoop = e.source_node_uuid === e.target_node_uuid
    
    if (isSelfLoop) {
      // 自环边 - 每个节点只添加一条合并的自环
      if (processedSelfLoopNodes.has(e.source_node_uuid)) {
        return // 已处理过，跳过
      }
      processedSelfLoopNodes.add(e.source_node_uuid)
      
      const allSelfLoops = selfLoopEdges[e.source_node_uuid]
      const nodeName = nodeMap[e.source_node_uuid]?.name || 'Unknown'
      const highlightKeys = uniqueTokens(
        allSelfLoops.flatMap((loopEdge, loopIndex) =>
          buildEdgeHighlightKeys(loopEdge, e.source_node_uuid, e.target_node_uuid, loopEdge.fact_type || loopEdge.name || 'SELF_LOOP', loopIndex)
        ).concat([`self_loop::${e.source_node_uuid}`])
      )
      
      edges.push({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: 'SELF_LOOP',
        name: `Self Relations (${allSelfLoops.length})`,
        curvature: 0,
        isSelfLoop: true,
        highlightKeys,
        rawData: {
          isSelfLoopGroup: true,
          source_name: nodeName,
          target_name: nodeName,
          selfLoopCount: allSelfLoops.length,
          selfLoopEdges: allSelfLoops // 存储所有自环边的详细信息
        }
      })
      return
    }
    
    const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
    const totalCount = edgePairCount[pairKey]
    const currentIndex = edgePairIndex[pairKey] || 0
    edgePairIndex[pairKey] = currentIndex + 1
    
    // 判断边的方向是否与标准化方向一致（源UUID < 目标UUID）
    const isReversed = e.source_node_uuid > e.target_node_uuid
    
    // 计算曲率：多条边时分散开，单条边为直线
    let curvature = 0
    if (totalCount > 1) {
      // 均匀分布曲率，确保明显区分
      // 曲率范围根据边数量增加，边越多曲率范围越大
      const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
      curvature = ((currentIndex / (totalCount - 1)) - 0.5) * curvatureRange * 2
      
      // 如果边的方向与标准化方向相反，翻转曲率
      // 这样确保所有边在同一参考系下分布，不会因方向不同而重叠
      if (isReversed) {
        curvature = -curvature
      }
    }
    const highlightKeys = buildEdgeHighlightKeys(e, e.source_node_uuid, e.target_node_uuid, e.fact_type || e.name || 'RELATED', currentIndex)
    
    edges.push({
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      type: e.fact_type || e.name || 'RELATED',
      name: e.name || e.fact_type || 'RELATED',
      curvature,
      isSelfLoop: false,
      pairIndex: currentIndex,
      pairTotal: totalCount,
      highlightKeys,
      rawData: {
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      }
    })
  })

  edges.forEach(edge => {
    const label = String(edge.name || '')
    edge.labelWidth = Math.min(180, Math.max(28, label.length * 5.8 + 10))
    edge.labelHeight = 14
  })
    
  // Color scale
  const colorMap = {}
  entityTypes.value.forEach(t => colorMap[t.name] = t.color)
  const getColor = (type) => colorMap[type] || '#999'
  const isEdgeHighlighted = (linkData) => (linkData.highlightKeys || []).some(token => highlightedEdgeIdSet.has(token))
  const isLinkFocused = (linkData) => isEdgeHighlighted(linkData) || highlightedNodeIds.has(linkData.source.id) || highlightedNodeIds.has(linkData.target.id)
  const edgeHighlightColor = props.highlightMode === 'risk_runtime'
    ? '#E04F39'
    : props.highlightMode === 'risk_definition'
      ? '#F08A24'
      : '#E0A25A'
  const edgeNeighborColor = '#E0A25A'

  // Simulation - 根据边数量动态调整节点间距
  const simulation = d3.forceSimulation(nodes)
    .alpha(oldNodeMap.size > 0 ? 0.3 : 1) // 降低热度避免图谱位置突变跳动
    .alphaDecay(oldNodeMap.size > 0 ? 0.09 : 0.06)
    .velocityDecay(0.55)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
      // 根据这对节点之间的边数量动态调整距离
      // 基础距离 150，每多一条边增加 40
      const baseDistance = 150
      const edgeCount = d.pairTotal || 1
      return baseDistance + (edgeCount - 1) * 50
    }))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(50))
    // 添加向中心的引力，让独立的节点群聚集到中心区域
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))
  
  currentSimulation = simulation

  const g = svg.append('g')
  
  // Zoom
  svg.call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  }))

  // Links - 使用 path 支持曲线
  const linkGroup = g.append('g').attr('class', 'links')
  
  // 计算曲线路径
  const getLinkPath = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y
    
    // 检测自环
    if (d.isSelfLoop) {
      // 自环：绘制一个圆弧从节点出发再返回
      const loopRadius = 30
      // 从节点右侧出发，绕一圈回来
      const x1 = sx + 8  // 起点偏移
      const y1 = sy - 4
      const x2 = sx + 8  // 终点偏移
      const y2 = sy + 4
      // 使用圆弧绘制自环（sweep-flag=1 顺时针）
      return `M${x1},${y1} A${loopRadius},${loopRadius} 0 1,1 ${x2},${y2}`
    }
    
    if (d.curvature === 0) {
      // 直线
      return `M${sx},${sy} L${tx},${ty}`
    }
    
    // 计算曲线控制点 - 根据边数量和距离动态调整
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    // 垂直于连线方向的偏移，根据距离比例计算，保证曲线明显可见
    // 边越多，偏移量占距离的比例越大
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05 // 基础25%，每多一条边增加5%
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY
    
    return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
  }
  
  // 计算曲线中点（用于标签定位）
  const getLinkMidpoint = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y
    
    // 检测自环
    if (d.isSelfLoop) {
      // 自环标签位置：节点右侧
      return { x: sx + 70, y: sy }
    }
    
    if (d.curvature === 0) {
      return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
    }
    
    // 二次贝塞尔曲线的中点 t=0.5
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY
    
    // 二次贝塞尔曲线公式 B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2, t=0.5
    const midX = 0.25 * sx + 0.5 * cx + 0.25 * tx
    const midY = 0.25 * sy + 0.5 * cy + 0.25 * ty
    
    return { x: midX, y: midY }
  }
  
  const link = linkGroup.selectAll('path')
    .data(edges)
    .enter().append('path')
    .attr('stroke', '#C0C0C0')
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      applyBaseGraphState()
      // 高亮当前选中的边
      d3.select(event.target).attr('stroke', '#3498db').attr('stroke-width', 3).attr('opacity', 1)
      
      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels background (白色背景使文字更清晰)
  const linkLabelBg = linkGroup.selectAll('rect')
    .data(edges)
    .enter().append('rect')
    .attr('fill', 'rgba(255,255,255,0.95)')
    .attr('rx', 3)
    .attr('ry', 3)
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      applyBaseGraphState()
      // 高亮对应的边
      link.filter(l => l === d).attr('stroke', '#3498db').attr('stroke-width', 3).attr('opacity', 1)
      d3.select(event.target).attr('fill', 'rgba(52, 152, 219, 0.1)').attr('opacity', 1)
      
      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels
  const linkLabels = linkGroup.selectAll('text')
    .data(edges)
    .enter().append('text')
    .text(d => d.name)
    .attr('font-size', '9px')
    .attr('fill', '#666')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('font-family', 'system-ui, sans-serif')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      applyBaseGraphState()
      // 高亮对应的边
      link.filter(l => l === d).attr('stroke', '#3498db').attr('stroke-width', 3).attr('opacity', 1)
      d3.select(event.target).attr('fill', '#3498db').attr('opacity', 1)
      
      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })
  
  // 保存引用供外部控制显隐
  linkLabelsRef = linkLabels
  linkLabelBgRef = linkLabelBg

  // Nodes group
  const nodeGroup = g.append('g').attr('class', 'nodes')
  
  // Node circles
  const node = nodeGroup.selectAll('circle')
    .data(nodes)
    .enter().append('circle')
    .attr('r', 10)
    .attr('fill', d => getColor(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2.5)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        // 只记录位置，不重启仿真（区分点击和拖拽）
        d.fx = d.x
        d.fy = d.y
        d._dragStartX = event.x
        d._dragStartY = event.y
        d._isDragging = false
      })
      .on('drag', (event, d) => {
        // 检测是否真正开始拖拽（移动超过阈值）
        const dx = event.x - d._dragStartX
        const dy = event.y - d._dragStartY
        const distance = Math.sqrt(dx * dx + dy * dy)
        
        if (!d._isDragging && distance > 3) {
          // 首次检测到真正拖拽，才重启仿真
          d._isDragging = true
          simulation.alphaTarget(0.3).restart()
        }
        
        if (d._isDragging) {
          d.fx = event.x
          d.fy = event.y
        }
      })
      .on('end', (event, d) => {
        // 只有真正拖拽过才让仿真逐渐停止
        if (d._isDragging) {
          simulation.alphaTarget(0)
        }
        d.fx = null
        d.fy = null
        d._isDragging = false
      })
    )
    .on('click', (event, d) => {
      event.stopPropagation()
      applyBaseGraphState()
      // 高亮选中节点
      d3.select(event.target).attr('stroke', '#E91E63').attr('stroke-width', 4).attr('opacity', 1)
      // 高亮与此节点相连的边
      link.filter(l => l.source.id === d.id || l.target.id === d.id)
        .attr('stroke', '#E91E63')
        .attr('stroke-width', 2.5)
        .attr('opacity', 1)
      
      selectedItem.value = {
        type: 'node',
        data: d.rawData,
        entityType: d.type,
        color: getColor(d.type)
      }
      emit('node-select', buildNodePayload(selectedItem.value))
    })
    .on('mouseenter', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', '#333').attr('stroke-width', 3)
      }
    })
    .on('mouseleave', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        if (highlightActive && d.externallyHighlighted) {
          d3.select(event.target).attr('stroke', '#F08A24').attr('stroke-width', 4)
        } else {
          d3.select(event.target).attr('stroke', '#fff').attr('stroke-width', 2.5)
        }
      }
    })

  // Node Labels
  const nodeLabels = nodeGroup.selectAll('text')
    .data(nodes)
    .enter().append('text')
    .text(d => d.name.length > 8 ? d.name.substring(0, 8) + '…' : d.name)
    .attr('font-size', '11px')
    .attr('fill', '#333')
    .attr('font-weight', '500')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', 'system-ui, sans-serif')

  const applyBaseGraphState = () => {
    node
      .attr('r', d => (highlightActive && d.externallyHighlighted ? 12 : 10))
      .attr('opacity', d => (highlightActive ? (d.externallyHighlighted ? 1 : 0.24) : 1))
      .attr('stroke', d => (highlightActive && d.externallyHighlighted ? '#F08A24' : '#fff'))
      .attr('stroke-width', d => (highlightActive && d.externallyHighlighted ? 4 : 2.5))

    nodeLabels
      .attr('opacity', d => (highlightActive ? (d.externallyHighlighted ? 1 : 0.32) : 1))

    link
      .attr('stroke', d => {
        if (!highlightActive) return '#C0C0C0'
        if (isEdgeHighlighted(d)) return edgeHighlightColor
        if (isLinkFocused(d)) return edgeNeighborColor
        return '#C0C0C0'
      })
      .attr('stroke-width', d => {
        if (!highlightActive) return 1.5
        if (isEdgeHighlighted(d)) return 3
        if (isLinkFocused(d)) return 2.2
        return 1.5
      })
      .attr('opacity', d => (highlightActive ? (isLinkFocused(d) ? 0.98 : 0.12) : 1))

    linkLabelBg
      .attr('fill', 'rgba(255,255,255,0.95)')
      .attr('opacity', d => (highlightActive ? (isLinkFocused(d) ? 0.96 : 0.12) : 1))

    linkLabels
      .attr('fill', d => (highlightActive && isEdgeHighlighted(d) ? edgeHighlightColor : '#666'))
      .attr('opacity', d => (highlightActive ? (isLinkFocused(d) ? 1 : 0.18) : 1))
  }

  applyBaseGraphState()

  const maxTicks = oldNodeMap.size > 0 ? 70 : 140
  let tickCount = 0

  simulation.on('tick', () => {
    tickCount += 1
    // 更新曲线路径
    link.attr('d', d => getLinkPath(d))
    
    if (showEdgeLabels.value) {
      // 更新边标签位置（无旋转，水平显示更清晰）
      linkLabels.each(function(d) {
        const mid = getLinkMidpoint(d)
        d3.select(this)
          .attr('x', mid.x)
          .attr('y', mid.y)
          .attr('transform', '') // 移除旋转，保持水平
      })

      // 使用预估尺寸，避免在每个 tick 中触发 getBBox() 同步布局。
      linkLabelBg.each(function(d) {
        const mid = getLinkMidpoint(d)
        const width = d.labelWidth || 36
        const height = d.labelHeight || 14
        d3.select(this)
          .attr('x', mid.x - width / 2 - 4)
          .attr('y', mid.y - height / 2 - 2)
          .attr('width', width + 8)
          .attr('height', height + 4)
          .attr('transform', '') // 移除旋转
      })
    }

    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)

    nodeLabels
      .attr('x', d => d.x)
      .attr('y', d => d.y)

    if (tickCount >= maxTicks) {
      simulation.stop()
    }
  })
  
  // 点击空白处关闭详情面板
  svg.on('click', () => {
    selectedItem.value = null
    applyBaseGraphState()
  })
}

watch(() => props.graphData, () => {
  nextTick(scheduleGraphRender)
})

watch(
  () => [
    props.highlightLabel,
    (props.highlightNodeIds || []).join('|'),
    (props.highlightNodeNames || []).join('|'),
    (props.highlightEdgeIds || []).join('|'),
    props.highlightMode,
    graphMode.value
  ],
  () => {
    nextTick(scheduleGraphRender)
  }
)

// 监听边标签显示开关
watch(showEdgeLabels, (newVal) => {
  if (linkLabelsRef) {
    linkLabelsRef.style('display', newVal ? 'block' : 'none')
  }
  if (linkLabelBgRef) {
    linkLabelBgRef.style('display', newVal ? 'block' : 'none')
  }
  if (newVal) {
    nextTick(scheduleGraphRender)
  }
})

const handleResize = () => {
  if (resizeTimer) {
    clearTimeout(resizeTimer)
  }
  resizeTimer = window.setTimeout(() => {
    resizeTimer = null
    nextTick(scheduleGraphRender)
  }, 120)
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  nextTick(scheduleGraphRender)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) {
    clearTimeout(resizeTimer)
    resizeTimer = null
  }
  if (renderFrame !== null) {
    cancelAnimationFrame(renderFrame)
    renderFrame = null
  }
  stop2DSimulation()
  destroy3DGraph()
})
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: #FAFAFA;
  background-image: radial-gradient(#D0D0D0 1.5px, transparent 1.5px);
  background-size: 24px 24px;
  overflow: hidden;
}

.panel-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 16px 20px;
  z-index: 1200;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(to bottom, rgba(255,255,255,0.95), rgba(255,255,255,0));
  pointer-events: none;
}

.panel-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  pointer-events: auto;
}

.focus-badge {
  display: inline-flex;
  align-items: center;
  max-width: 320px;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(240, 138, 36, 0.14);
  color: #9a5b11;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: auto;
}

.header-tools {
  pointer-events: auto;
  display: flex;
  gap: 10px;
  align-items: center;
}

.mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border: 1px solid #E0E0E0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.04);
}

.mode-btn {
  min-width: 40px;
  height: 26px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #666;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.3px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.mode-btn:hover {
  color: #111;
  background: rgba(0, 0, 0, 0.04);
}

.mode-btn.active {
  background: #111;
  color: #FFF;
}

.tool-btn {
  height: 32px;
  padding: 0 12px;
  border: 1px solid #E0E0E0;
  background: #FFF;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  color: #666;
  transition: all 0.2s;
  box-shadow: 0 2px 4px rgba(0,0,0,0.02);
  font-size: 13px;
}

.tool-btn:hover {
  background: #F5F5F5;
  color: #000;
  border-color: #CCC;
}

.tool-btn .btn-text {
  font-size: 12px;
}

.icon-refresh.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.graph-container {
  width: 100%;
  height: 100%;
}

.embedded-map-panel {
  width: 100%;
  height: 100%;
}

.graph-view, .graph-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.graph-3d-view {
  width: 100%;
  height: 100%;
  display: block;
}

.graph-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #999;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: min(420px, calc(100% - 48px));
}

.graph-state-network {
  color: #123127;
}

.network-loader {
  position: relative;
  width: 210px;
  height: 210px;
  margin-bottom: 4px;
}

.network-ring,
.network-node,
.network-link {
  position: absolute;
  display: block;
}

.network-ring {
  inset: 0;
  border-radius: 50%;
  border: 1px solid rgba(31, 125, 93, 0.14);
}

.ring-a {
  animation: graphPulse 2.8s ease-out infinite;
}

.ring-b {
  inset: 24px;
  animation: graphPulse 2.8s ease-out 0.45s infinite;
}

.ring-c {
  inset: 48px;
  animation: graphPulse 2.8s ease-out 0.9s infinite;
}

.network-node {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1f7d5d, #f08a24);
  box-shadow: 0 0 0 8px rgba(240, 138, 36, 0.08);
}

.node-core {
  top: 98px;
  left: 98px;
  width: 18px;
  height: 18px;
  background: linear-gradient(135deg, #174c3a, #1f7d5d);
  box-shadow: 0 0 0 12px rgba(31, 125, 93, 0.12);
  animation: graphNodeBeat 1.8s ease-in-out infinite;
}

.node-top {
  top: 26px;
  left: 98px;
  animation: graphNodeFloat 2.4s ease-in-out infinite;
}

.node-right {
  top: 98px;
  right: 26px;
  animation: graphNodeFloat 2.4s ease-in-out 0.4s infinite;
}

.node-bottom {
  bottom: 26px;
  left: 98px;
  animation: graphNodeFloat 2.4s ease-in-out 0.8s infinite;
}

.node-left {
  top: 98px;
  left: 26px;
  animation: graphNodeFloat 2.4s ease-in-out 1.2s infinite;
}

.network-link {
  top: 105px;
  left: 105px;
  transform-origin: left center;
  height: 2px;
  width: 72px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(31, 125, 93, 0.85), rgba(240, 138, 36, 0.2));
  animation: graphLinkPulse 1.8s ease-in-out infinite;
}

.link-top {
  transform: rotate(-90deg);
}

.link-right {
  transform: rotate(0deg);
  animation-delay: 0.25s;
}

.link-bottom {
  transform: rotate(90deg);
  animation-delay: 0.5s;
}

.link-left {
  transform: rotate(180deg);
  animation-delay: 0.75s;
}

.graph-state-title {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  font-weight: 700;
  color: #123127;
}

.graph-state-subtitle {
  margin: 0;
  max-width: 360px;
  font-size: 14px;
  line-height: 1.6;
  color: rgba(18, 49, 39, 0.72);
}

.graph-loading-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 2px;
}

.loading-tag {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(18, 49, 39, 0.08);
  box-shadow: 0 8px 20px rgba(18, 49, 39, 0.06);
  color: #174c3a;
  font-size: 12px;
  font-weight: 700;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.2;
}

.empty-text {
  margin: 0;
}

@keyframes graphPulse {
  0% {
    opacity: 0.22;
    transform: scale(0.88);
  }
  60% {
    opacity: 0.52;
  }
  100% {
    opacity: 0;
    transform: scale(1.08);
  }
}

@keyframes graphNodeBeat {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.14);
  }
}

@keyframes graphNodeFloat {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-6px);
  }
}

@keyframes graphLinkPulse {
  0%, 100% {
    opacity: 0.35;
  }
  50% {
    opacity: 1;
  }
}

/* Entity Types Legend - Bottom Left */
.graph-legend {
  position: absolute;
  bottom: 24px;
  left: 24px;
  background: rgba(255,255,255,0.95);
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #EAEAEA;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  z-index: 10;
}

.legend-title {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #E91E63;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  max-width: 320px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #555;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  white-space: nowrap;
}

/* Edge Labels Toggle - Top Right */
.edge-labels-toggle {
  position: absolute;
  top: 60px;
  right: 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  background: #FFF;
  padding: 8px 14px;
  border-radius: 20px;
  border: 1px solid #E0E0E0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  z-index: 10;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #E0E0E0;
  border-radius: 22px;
  transition: 0.3s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  transition: 0.3s;
}

input:checked + .slider {
  background-color: #7B2D8E;
}

input:checked + .slider:before {
  transform: translateX(18px);
}

.toggle-label {
  font-size: 12px;
  color: #666;
}

/* Detail Panel - Right Side */
.detail-panel {
  position: absolute;
  top: 60px;
  right: 20px;
  width: 320px;
  max-height: calc(100% - 100px);
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.1);
  overflow: hidden;
  font-family: 'Noto Sans SC', system-ui, sans-serif;
  font-size: 13px;
  z-index: 20;
  display: flex;
  flex-direction: column;
}

.detail-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: #FAFAFA;
  border-bottom: 1px solid #EEE;
  flex-shrink: 0;
}

.detail-title {
  font-weight: 600;
  color: #333;
  font-size: 14px;
}

.detail-type-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
  margin-left: auto;
  margin-right: 12px;
}

.detail-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  line-height: 1;
  padding: 0;
  transition: color 0.2s;
}

.detail-close:hover {
  color: #333;
}

.detail-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.detail-row {
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-label {
  color: #888;
  font-size: 12px;
  font-weight: 500;
  min-width: 80px;
}

.detail-value {
  color: #333;
  flex: 1;
  word-break: break-word;
}

.detail-value.uuid-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #666;
}

.detail-value.fact-text {
  line-height: 1.5;
  color: #444;
}

.detail-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #F0F0F0;
}

.node-action-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.node-action-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.node-action-btn {
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid #E2E8F0;
  background: #FFF;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.node-action-btn:hover {
  background: #F8FAFC;
  border-color: #CBD5E1;
}

.node-action-btn.primary {
  background: #0F766E;
  color: #FFF;
  border-color: #0F766E;
}

.node-action-btn.primary:hover {
  background: #0B5F59;
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  margin-bottom: 10px;
}

.properties-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.property-item {
  display: flex;
  gap: 8px;
}

.property-key {
  color: #888;
  font-weight: 500;
  min-width: 90px;
}

.property-value {
  color: #333;
  flex: 1;
}

.summary-text {
  line-height: 1.6;
  color: #444;
  font-size: 12px;
}

.labels-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.label-tag {
  display: inline-block;
  padding: 4px 12px;
  background: #F5F5F5;
  border: 1px solid #E0E0E0;
  border-radius: 16px;
  font-size: 11px;
  color: #555;
}

.episodes-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.episode-tag {
  display: inline-block;
  padding: 6px 10px;
  background: #F8F8F8;
  border: 1px solid #E8E8E8;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #666;
  word-break: break-all;
}

/* Edge relation header */
.edge-relation-header {
  background: #F8F8F8;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  font-weight: 500;
  color: #333;
  line-height: 1.5;
  word-break: break-word;
}

/* Building hint */
.graph-building-hint {
  position: absolute;
  top: 72px; /* Move to top center to prevent overlap with bottom legend */
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(8px);
  color: #fff;
  padding: 10px 20px;
  border-radius: 30px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-weight: 500;
  letter-spacing: 0.5px;
  z-index: 100;
}

.memory-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  animation: breathe 2s ease-in-out infinite;
}

.memory-icon {
  width: 18px;
  height: 18px;
  color: #4CAF50;
}

@keyframes breathe {
  0%, 100% { opacity: 0.7; transform: scale(1); filter: drop-shadow(0 0 2px rgba(76, 175, 80, 0.3)); }
  50% { opacity: 1; transform: scale(1.15); filter: drop-shadow(0 0 8px rgba(76, 175, 80, 0.6)); }
}

/* 模拟结束后的提示样式 */
.graph-building-hint.finished-hint {
  background: rgba(0, 0, 0, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.finished-hint .hint-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

.finished-hint .hint-icon {
  width: 18px;
  height: 18px;
  color: #FFF;
}

.finished-hint .hint-text {
  flex: 1;
  white-space: nowrap;
}

.hint-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  border-radius: 50%;
  cursor: pointer;
  color: #FFF;
  transition: all 0.2s;
  margin-left: 8px;
  flex-shrink: 0;
}

.hint-close-btn:hover {
  background: rgba(255, 255, 255, 0.35);
  transform: scale(1.1);
}

/* Loading spinner */
.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #E0E0E0;
  border-top-color: #7B2D8E;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

/* Self-loop styles */
.self-loop-header {
  display: flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #E8F5E9 0%, #F1F8E9 100%);
  border: 1px solid #C8E6C9;
}

.self-loop-count {
  margin-left: auto;
  font-size: 11px;
  color: #666;
  background: rgba(255,255,255,0.8);
  padding: 2px 8px;
  border-radius: 10px;
}

.self-loop-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.self-loop-item {
  background: #FAFAFA;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
}

.self-loop-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #F5F5F5;
  cursor: pointer;
  transition: background 0.2s;
}

.self-loop-item-header:hover {
  background: #EEEEEE;
}

.self-loop-item.expanded .self-loop-item-header {
  background: #E8E8E8;
}

.self-loop-index {
  font-size: 10px;
  font-weight: 600;
  color: #888;
  background: #E0E0E0;
  padding: 2px 6px;
  border-radius: 4px;
}

.self-loop-name {
  font-size: 12px;
  font-weight: 500;
  color: #333;
  flex: 1;
}

.self-loop-toggle {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: #888;
  background: #E0E0E0;
  border-radius: 4px;
  transition: all 0.2s;
}

.self-loop-item.expanded .self-loop-toggle {
  background: #D0D0D0;
  color: #666;
}

.self-loop-item-content {
  padding: 12px;
  border-top: 1px solid #EAEAEA;
}

.self-loop-item-content .detail-row {
  margin-bottom: 8px;
}

.self-loop-item-content .detail-label {
  font-size: 11px;
  min-width: 60px;
}

.self-loop-item-content .detail-value {
  font-size: 12px;
}

.self-loop-episodes {
  margin-top: 8px;
}

.episodes-list.compact {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 4px;
}

.episode-tag.small {
  padding: 3px 6px;
  font-size: 9px;
}
</style>
