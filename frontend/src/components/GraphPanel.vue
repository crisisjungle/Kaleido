<template>
  <div
    class="graph-panel"
    :data-animation-active-edge-count="activeAnimationEdgeCount"
    :data-animation-renderable-edge-count="renderableAnimationEdgeCount"
    :data-animation-focus-edge-count="highlightEdgeIds.length"
  >
    <div class="panel-header">
      <div class="panel-title-wrap">
        <span v-if="graphMode !== 'map'" class="panel-title">图谱关系可视化</span>
        <span v-if="safeDisplayText(highlightLabel, '') && graphMode !== 'map'" class="focus-badge">{{ safeDisplayText(highlightLabel, '当前焦点') }}</span>
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
        <!-- 治毛球：图谱密度 — 默认只显最关键的连线，聚焦因果网络 -->
        <label v-if="graphMode !== 'map'" class="density-select" title="只影响当前视图，不改变推演数据">
          <span>关系密度</span>
          <select v-model="edgeDensity">
            <option value="strong">重点关系</option>
            <option value="standard">标准视图</option>
            <option value="all">全量关系</option>
          </select>
        </label>
        <button class="tool-btn" @click="$emit('refresh')" :disabled="loading" title="刷新图谱">
          <span class="icon-refresh" :class="{ 'spinning': loading }">↻</span>
          <span class="btn-text">刷新</span>
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
        <transition name="graph-3d-overlay-fade">
          <div v-if="show3DOverlay" class="graph-3d-overlay" :class="`is-${graph3DState}`">
            <div class="graph-3d-overlay-card">
              <div class="graph-3d-orbit" aria-hidden="true">
                <span class="orbit-ring orbit-ring-a"></span>
                <span class="orbit-ring orbit-ring-b"></span>
                <span class="orbit-core"></span>
              </div>
              <div class="graph-3d-overlay-title">{{ graph3DOverlayTitle }}</div>
              <div class="graph-3d-overlay-subtitle">{{ graph3DOverlaySubtitle }}</div>
            </div>
          </div>
        </transition>
        
        <!-- 构建中/模拟中提示 -->
        <div v-if="currentPhase === 1 || isSimulating" class="graph-building-hint">
          <div class="memory-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="memory-icon">
              <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-4.04z" />
              <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-4.04z" />
            </svg>
          </div>
          {{ isSimulating ? '图谱记忆实时更新中' : '图谱实时更新中...' }}
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
            <span class="detail-title">{{ selectedItem.type === 'node' ? '节点详情' : '关系详情' }}</span>
            <span v-if="selectedItem.type === 'node'" class="detail-type-badge">
              {{ displayToken(selectedItem.entityType) }}
            </span>
            <button class="detail-close" @click="closeDetailPanel">×</button>
          </div>
          
          <!-- 节点详情 -->
          <div v-if="selectedItem.type === 'node'" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">名称：</span>
              <span class="detail-value">{{ safeDisplayText(selectedItem.data.name, '未命名节点') }}</span>
            </div>
            <div class="detail-row" v-if="selectedItem.data.created_at">
              <span class="detail-label">创建时间：</span>
              <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
            </div>
            
            <!-- Properties -->
            <div class="detail-section" v-if="visibleAttributeEntries(selectedItem.data.attributes).length > 0">
              <div class="section-title">属性</div>
              <div class="properties-list">
                <div v-for="[key, value] in visibleAttributeEntries(selectedItem.data.attributes)" :key="key" class="property-item">
                  <span class="property-key">{{ formatPropertyKey(key) }}：</span>
                  <span class="property-value">{{ formatPropertyValue(value) }}</span>
                </div>
              </div>
            </div>
            
            <!-- Summary -->
            <div class="detail-section" v-if="selectedItem.data.summary">
              <div class="section-title">摘要</div>
              <div class="summary-text">{{ safeDisplayText(selectedItem.data.summary, '暂无摘要') }}</div>
            </div>
            
            <!-- Labels -->
            <div class="detail-section" v-if="selectedItem.data.labels && selectedItem.data.labels.length > 0">
              <div class="section-title">标签</div>
              <div class="labels-list">
                <span v-for="label in visibleLabels(selectedItem.data.labels)" :key="label" class="label-tag">
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
                {{ safeDisplayText(selectedItem.data.source_name, '当前节点') }} - 自关联
                <span class="self-loop-count">{{ selectedItem.data.selfLoopCount }} 条</span>
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
                    <span class="self-loop-name">{{ safeToken(loop.name || loop.fact_type, '关联') }}</span>
                    <span class="self-loop-toggle">{{ expandedSelfLoops.has(loop.uuid || idx) ? '−' : '+' }}</span>
                  </div>
                  
                  <div class="self-loop-item-content" v-show="expandedSelfLoops.has(loop.uuid || idx)">
                    <div class="detail-row" v-if="loop.fact">
                      <span class="detail-label">事实：</span>
                      <span class="detail-value fact-text">{{ safeDisplayText(loop.fact, '已记录关联事实') }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact_type">
                      <span class="detail-label">类型：</span>
                      <span class="detail-value">{{ displayToken(loop.fact_type) }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.created_at">
                      <span class="detail-label">创建时间：</span>
                      <span class="detail-value">{{ formatDateTime(loop.created_at) }}</span>
                    </div>
                    <div v-if="loop.episodes && loop.episodes.length > 0" class="self-loop-episodes">
                      <span class="detail-label">片段：</span>
                      <div class="episodes-list compact">
                        <span v-for="(ep, epIndex) in loop.episodes.slice(0, 3)" :key="ep" class="episode-tag small">片段 {{ epIndex + 1 }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            
            <!-- 普通边详情 -->
            <template v-else>
              <div class="edge-relation-header">
                {{ safeDisplayText(selectedItem.data.source_name, '来源节点') }} → {{ safeToken(selectedItem.data.name, '关联') }} → {{ safeDisplayText(selectedItem.data.target_name, '目标节点') }}
              </div>
              
              <div class="detail-row">
                <span class="detail-label">标签：</span>
                <span class="detail-value">{{ displayToken(selectedItem.data.name || '关联') }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">类型：</span>
                <span class="detail-value">{{ displayToken(selectedItem.data.fact_type || '其他') }}</span>
              </div>
              <!-- M10 honesty badges: edge layer / epistemic / channel -->
              <div class="detail-row" v-if="edgeHonesty(selectedItem.data)">
                <span class="detail-label">关系性质：</span>
                <span class="detail-value edge-honesty-badges">
                  <span
                    v-if="edgeHonesty(selectedItem.data).layerLabel"
                    class="edge-badge"
                    :class="edgeHonesty(selectedItem.data).layer === 'spatial_fact' ? 'edge-badge-spatial' : 'edge-badge-causal'"
                  >{{ edgeHonesty(selectedItem.data).layerLabel }}</span>
                  <span
                    v-if="edgeHonesty(selectedItem.data).epistemicLabel"
                    class="edge-badge edge-badge-epistemic"
                  >{{ edgeHonesty(selectedItem.data).epistemicLabel }}</span>
                  <span
                    v-if="edgeHonesty(selectedItem.data).channelLabel"
                    class="edge-badge edge-badge-channel"
                  >{{ edgeHonesty(selectedItem.data).channelLabel }}</span>
                </span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.fact">
                <span class="detail-label">事实：</span>
                <span class="detail-value fact-text">{{ safeDisplayText(selectedItem.data.fact, '已记录关联事实') }}</span>
              </div>
              
              <!-- Episodes -->
              <div class="detail-section" v-if="selectedItem.data.episodes && selectedItem.data.episodes.length > 0">
                <div class="section-title">片段</div>
                <div class="episodes-list">
                  <span v-for="(ep, epIndex) in selectedItem.data.episodes.slice(0, 3)" :key="ep" class="episode-tag">
                    片段 {{ epIndex + 1 }}
                  </span>
                </div>
              </div>
              
              <div class="detail-row" v-if="selectedItem.data.created_at">
                <span class="detail-label">创建时间：</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.valid_at">
                <span class="detail-label">生效时间：</span>
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
      <div v-else-if="graphMode !== 'map' && !hasGraphContent" class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ currentPhase === 4 ? '结果图谱暂无可用节点' : '等待本体生成...' }}</p>
      </div>
    </div>

    <!-- 底部图例 (Bottom Left) -->
    <div v-if="hasGraphContent && graphMode !== 'map' && entityTypes.length" class="graph-legend">
      <span class="legend-title">实体类型</span>
      <div class="legend-items">
        <div class="legend-item" v-for="type in entityTypes.slice(0, 5)" :key="type.name">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.name }}</span>
        </div>
        <span v-if="entityTypes.length > 5" class="legend-more">+{{ entityTypes.length - 5 }}</span>
      </div>
      <!-- M10 edge-layer legend: spatial skeleton vs causal coupling -->
      <div v-if="edgeLayerSummary" class="legend-edge-layers">
        <span class="legend-edge-item">
          <span class="legend-edge-line legend-edge-spatial"></span>
          <span class="legend-label">空间骨架 {{ edgeLayerSummary.spatial }}</span>
        </span>
        <span class="legend-edge-item">
          <span class="legend-edge-line legend-edge-causal"></span>
          <span class="legend-label">因果连线 {{ edgeLayerSummary.causal }}</span>
        </span>
        <span v-if="renderedEdgeStats.total && renderedEdgeStats.shown < renderedEdgeStats.total" class="legend-edge-shown">
          当前显示 {{ renderedEdgeStats.shown }} / 共 {{ renderedEdgeStats.total }} 条
        </span>
      </div>
    </div>
    
    <!-- 显示边标签开关 -->
    <div v-if="hasGraphContent && graphMode === '2d' && !selectedItem" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">显示关系标签</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'
import MapRelationPanel from './MapRelationPanel.vue'
import { formatTokenLabelZh, translateDisplayToken, formatFieldLabelZh, isInternalAttributeKey, normalizeDisplayLabels, safeDisplayText as safeDisplayCopyText, safeDisplayToken } from '../utils/displayText'
import { reconcileVisibleGraphSelection } from '../utils/simulationPlayback'

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

const activeAnimationEdgeCount = computed(() => (
  Array.isArray(props.graphData?.edges)
    ? props.graphData.edges.filter(edge => ['new', 'active'].includes(
      String(edge?.attributes?.animation_status || '').trim().toLowerCase(),
    )).length
    : 0
))

const renderableAnimationEdgeCount = computed(() => {
  const nodeIds = new Set((Array.isArray(props.graphData?.nodes) ? props.graphData.nodes : [])
    .map(node => String(node?.uuid || node?.id || ''))
    .filter(Boolean))
  return (Array.isArray(props.graphData?.edges) ? props.graphData.edges : []).filter((edge) => {
    const status = String(edge?.attributes?.animation_status || '').trim().toLowerCase()
    const sourceId = String(edge?.source_node_uuid || edge?.source || '')
    const targetId = String(edge?.target_node_uuid || edge?.target || '')
    return ['new', 'active'].includes(status) && nodeIds.has(sourceId) && nodeIds.has(targetId)
  }).length
})

const propagationEdgeSignature = computed(() => (
  (Array.isArray(props.graphData?.edges) ? props.graphData.edges : [])
    .filter(edge => ['new', 'active'].includes(
      String(edge?.attributes?.animation_status || '').trim().toLowerCase(),
    ))
    .map((edge, index) => [
      edge?.uuid || edge?.id || edge?.edge_id || index,
      edge?.attributes?.animation_status || '',
      Number(edge?.attributes?.animation_progress || 0).toFixed(3),
    ].join(':'))
    .join('|')
))

const emit = defineEmits(['refresh', 'toggle-maximize', 'node-select', 'node-action'])

const graphContainer = ref(null)
const graphSvg = ref(null)
const graph3dContainer = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(false)
const edgeDensity = ref('strong') // strong | standard | all — 治毛球：默认只显强关系(去骨架+去推测+封顶)，展开即可读，不再是毛球
const renderedEdgeStats = ref({ shown: 0, total: 0 })
const graphMode = ref('2d')
const graph3DState = ref('idle')
const graph3DErrorMessage = ref('')
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
    edge?.attributes?.mechanism_edge_id,
    edge?.attributes?.mechanismEdgeId,
    ...(Array.isArray(edge?.attributes?.mechanism_edge_ids) ? edge.attributes.mechanism_edge_ids : []),
    ...(Array.isArray(edge?.attributes?.mechanismEdgeIds) ? edge.attributes.mechanismEdgeIds : []),
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

const INVALID_GRAPH_COPY = new Set(['内部标识', '未命名项', '内容待本地化'])
const safeDisplayText = (value, fallback = '') => {
  const text = safeDisplayCopyText(value, '').trim()
  return !text || INVALID_GRAPH_COPY.has(text) ? fallback : text
}
const safeToken = (value, fallback = '') => safeDisplayToken(value, fallback)
const displayToken = (value, fallback = '其他') => safeToken(value, fallback)
const visibleLabels = (labels) => normalizeDisplayLabels(labels, 3)

const formatPropertyKey = (key) => safeDisplayText(formatFieldLabelZh(key, ''), '属性')

// 只展示有意义的字段，过滤动画/内部/调试 key（*_round、animation_*、uuid、id…）
const visibleAttributeEntries = (attributes) => {
  if (!attributes || typeof attributes !== 'object') return []
  return Object.entries(attributes)
    .filter(([key, value]) => !isInternalAttributeKey(key) && value !== null && value !== undefined && typeof value !== 'object')
    .filter(([, value]) => Boolean(formatPropertyValue(value)))
    .slice(0, 8)
}

const formatPropertyValue = (value) => {
  if (value === null || value === undefined || value === '') return '无'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(1)
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return ''
  return safeDisplayText(value, '')
}

// 监听 isSimulating 变化，检测模拟结束
watch(() => props.isSimulating, (newValue, oldValue) => {
  if (newValue) {
    showEdgeLabels.value = false
  }
  if (wasSimulating.value && !newValue) {
    // 从模拟中变为非模拟状态，显示结束提示；几秒后自动消失，不再常驻挡视线
    showSimulationFinishedHint.value = true
    setTimeout(() => { showSimulationFinishedHint.value = false }, 6000)
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
    const type = node.labels?.find(l => l !== 'Entity') || '其他类型'
    const displayName = displayToken(type, '其他类型')
    if (!typeMap[type]) {
      typeMap[type] = { rawType: type, name: displayName, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
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

// M10: summarize spatial_fact vs causal edge counts (prefer backend meta, but
// recount from edges so it survives the animation-filtered graph too).
const edgeLayerSummary = computed(() => {
  const meta = props.graphData?.meta || {}
  let spatial = Number(meta.spatial_fact_edge_count)
  let causal = Number(meta.causal_edge_count)
  if (!Number.isFinite(spatial) || !Number.isFinite(causal)) {
    spatial = 0
    causal = 0
    for (const edge of (props.graphData?.edges || [])) {
      const layer = String(edge?.edge_layer || edge?.attributes?.edge_layer || '').toLowerCase()
      if (layer === 'spatial_fact') spatial += 1
      else if (layer === 'causal') causal += 1
    }
  }
  if (spatial <= 0 && causal <= 0) return null
  return { spatial, causal }
})

const show3DOverlay = computed(() => {
  return graphMode.value === '3d' && ['loading', 'unsupported'].includes(graph3DState.value)
})

const graph3DOverlayTitle = computed(() => {
  if (graph3DState.value === 'unsupported') return '当前环境暂时无法打开 3D 图谱'
  return '3D 图谱构图中'
})

const graph3DOverlaySubtitle = computed(() => {
  if (graph3DState.value === 'unsupported') {
    return graph3DErrorMessage.value || '可以先查看地图或 2D 图谱，换到支持 WebGL 的浏览器环境后会自动恢复。'
  }
  return '正在整理层级、镜头和关系脉络，让第一眼就能看到风险主轴。'
})

const showSceneDesignLoadingState = computed(() => {
  return props.currentPhase < 2 && !hasGraphContent.value
})

// 格式化时间
const formatDateTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    if (Number.isNaN(date.getTime())) return '时间不可用'
    return date.toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric', 
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: false
    })
  } catch {
    return '时间不可用'
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
  graph2DState?.refreshNodeLabelVisibility?.({ interrupt: true })
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
let containerResizeObserver = null
let graph2DState = null
let last2DStructureSignature = ''
let currentZoomTransform = d3.zoomIdentity
let graph2DDataFrame = null

// 2D uses semantic zoom: positions move, while glyphs and text stay readable.
// Going below this floor only collapses the layout beneath fixed-size glyphs,
// so it can never produce a useful overview.
const MIN_2D_ZOOM = 0.5
const MAX_2D_ZOOM = 5
const NODE_LABEL_LOD_ZOOM = 0.7

const scheduleGraphRender = () => {
  // Coalesce invalidations. Cancelling and rescheduling on every playback RAF
  // can starve the first render completely when animation data starts flowing
  // before the SVG has mounted.
  if (renderFrame !== null) return
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
    colorMap[t.rawType || t.name] = t.color
    colorMap[t.name] = t.color
  })
  return colorMap[type] || '#999'
}

const nodeLayerKey = (node) => {
  const type = String(node.type || '').toLowerCase()
  const labels = (node.rawData?.labels || []).map(item => String(item || '').toLowerCase())
  const nodeFamily = String(
    node.rawData?.attributes?.node_family
    || node.rawData?.node_family
    || '',
  ).toLowerCase()
  const isSubregion = type.includes('subregion')
    || type.includes('细分区域')
    || labels.some(label => label.includes('subregion') || label.includes('细分区域'))
    || nodeFamily.includes('subregion')
  if (isSubregion) return 'subregion'
  const isRegion = type.includes('region')
    || type.includes('区域')
    || labels.some(label => label === 'region' || label.endsWith('region') || label === '区域')
    || nodeFamily === 'region'
  if (isRegion) return 'macro'
  if (
    type.includes('actor')
    || type.includes('receptor')
    || type.includes('carrier')
    || type.includes('infrastructure')
    || nodeFamily.includes('actor')
    || nodeFamily.includes('receptor')
    || nodeFamily.includes('carrier')
    || nodeFamily.includes('infrastructure')
  ) return 'agent'
  return 'agent'
}

const nodeRegionKey = (node) => {
  const raw = node?.rawData || node || {}
  const attributes = raw.attributes || {}
  const id = String(node?.id || raw.uuid || raw.id || '')
  if (id.startsWith('region::')) return id.slice('region::'.length)
  const explicit = [
    attributes.primary_region,
    attributes.primary_region_id,
    attributes.region_id,
    attributes.parent_region_id,
    attributes.home_region_id,
    raw.primary_region,
    raw.region_id,
  ].map(value => String(value || '').trim()).find(Boolean)
  if (explicit) return explicit.replace(/^region::/, '')
  const subregion = String(
    attributes.home_subregion_id
    || attributes.subregion_id
    || raw.home_subregion_id
    || '',
  ).trim()
  if (subregion) return subregion.replace(/^region::/, '').split('::')[0]
  return ''
}

const buildRegionClusterTargets = (nodes, width, height) => {
  const keys = [...new Set((Array.isArray(nodes) ? nodes : [])
    .map(nodeRegionKey)
    .filter(Boolean))].sort()
  if (!keys.length) return new Map()
  const columns = Math.max(1, Math.ceil(Math.sqrt(keys.length * Math.max(width, 1) / Math.max(height, 1))))
  const rows = Math.max(1, Math.ceil(keys.length / columns))
  const marginX = Math.min(88, Math.max(42, width * 0.11))
  const marginY = Math.min(88, Math.max(48, height * 0.12))
  const spanX = Math.max(1, width - marginX * 2)
  const spanY = Math.max(1, height - marginY * 2)
  return new Map(keys.map((key, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    const x = columns === 1 ? width / 2 : marginX + (column / (columns - 1)) * spanX
    const y = rows === 1 ? height / 2 : marginY + (row / (rows - 1)) * spanY
    return [key, { x, y }]
  }))
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

const computeGraphCentroid = (nodes) => {
  if (!Array.isArray(nodes) || nodes.length === 0) return { x: 0, y: 0, z: 0 }
  const total = nodes.reduce((acc, node) => {
    acc.x += Number(node.x) || 0
    acc.y += Number(node.y) || 0
    acc.z += Number(node.z) || 0
    return acc
  }, { x: 0, y: 0, z: 0 })
  return {
    x: total.x / nodes.length,
    y: total.y / nodes.length,
    z: total.z / nodes.length,
  }
}

const compute3DCameraPose = (nodes, highlightedNodeIds = new Set()) => {
  const fallbackPose = {
    position: { x: 620, y: 260, z: 920 },
    target: { x: 0, y: 0, z: 0 },
  }
  if (!Array.isArray(nodes) || nodes.length === 0) return fallbackPose

  const focusNodes = highlightedNodeIds.size
    ? nodes.filter(node => highlightedNodeIds.has(node.id))
    : nodes.filter(node => ['macro', 'subregion'].includes(node.layer))
  const targetNodes = focusNodes.length ? focusNodes : nodes
  const target = computeGraphCentroid(targetNodes)

  let maxDistance = 0
  nodes.forEach((node) => {
    const dx = (Number(node.x) || 0) - target.x
    const dy = (Number(node.y) || 0) - target.y
    const dz = (Number(node.z) || 0) - target.z
    maxDistance = Math.max(maxDistance, Math.sqrt(dx * dx + dy * dy + dz * dz))
  })

  const distance = clamp(maxDistance * 2.4, 760, 1380)
  return {
    position: {
      x: target.x + distance * 0.7,
      y: target.y + distance * 0.34,
      z: target.z + distance * 0.92,
    },
    target,
  }
}

const formatSurfaceLabel = (name) => {
  const text = safeDisplayText(name, '')
  if (!text) return ''
  return text.length > 8 ? `${text.slice(0, 8)}…` : text
}

const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

const clamp2DZoomTransform = (transform, width = 0, height = 0) => {
  const source = transform
    && Number.isFinite(transform.k)
    && Number.isFinite(transform.x)
    && Number.isFinite(transform.y)
    && transform.k > 0
    ? transform
    : d3.zoomIdentity
  const nextScale = clamp(source.k, MIN_2D_ZOOM, MAX_2D_ZOOM)
  if (nextScale === source.k) return source

  // Keep the graph point currently under the viewport centre anchored while
  // repairing a transform restored from the old 0.1 zoom range.
  const centreX = Number.isFinite(width) ? width / 2 : 0
  const centreY = Number.isFinite(height) ? height / 2 : 0
  const graphX = (centreX - source.x) / source.k
  const graphY = (centreY - source.y) / source.k
  return d3.zoomIdentity
    .translate(centreX - graphX * nextScale, centreY - graphY * nextScale)
    .scale(nextScale)
}

const normalizeAnimationStatus = (value) => {
  const status = String(value || '').trim().toLowerCase()
  return ['hidden', 'new', 'steady', 'active', 'faded'].includes(status) ? status : 'steady'
}

const animationStatusRank = (status) => {
  if (status === 'active') return 4
  if (status === 'new') return 3
  if (status === 'steady') return 2
  if (status === 'faded') return 1
  return 0
}

const getDominantAnimationStatus = (items = []) => {
  let best = 'hidden'
  ;(Array.isArray(items) ? items : []).forEach((item) => {
    const status = normalizeAnimationStatus(item?.attributes?.animation_status)
    if (animationStatusRank(status) > animationStatusRank(best)) {
      best = status
    }
  })
  return best
}

const mergeAnimationAttributes = (items = []) => {
  const source = Array.isArray(items) ? items : []
  const firstSeenValues = source
    .map(item => Number(item?.attributes?.first_seen_round))
    .filter(Number.isFinite)
  const lastActiveValues = source
    .map(item => Number(item?.attributes?.last_active_round))
    .filter(Number.isFinite)
  const delayValues = source
    .map(item => Number(item?.attributes?.delay_ms))
    .filter(Number.isFinite)
  const dominant = source.reduce((best, item) => {
    if (!best) return item
    const bestStatus = normalizeAnimationStatus(best?.attributes?.animation_status)
    const itemStatus = normalizeAnimationStatus(item?.attributes?.animation_status)
    const rankDelta = animationStatusRank(itemStatus) - animationStatusRank(bestStatus)
    if (rankDelta > 0) return item
    if (rankDelta < 0) return best
    const bestProgress = Number(best?.attributes?.animation_progress ?? 0)
    const itemProgress = Number(item?.attributes?.animation_progress ?? 0)
    return itemProgress > bestProgress ? item : best
  }, null)
  const dominantAttrs = dominant?.attributes || {}

  return {
    animation_status: getDominantAnimationStatus(source),
    raw_animation_status: dominantAttrs.raw_animation_status,
    first_seen_round: firstSeenValues.length ? Math.min(...firstSeenValues) : undefined,
    last_active_round: lastActiveValues.length ? Math.max(...lastActiveValues) : undefined,
    delay_ms: delayValues.length ? Math.min(...delayValues) : undefined,
    timeline_delay_ms: dominantAttrs.timeline_delay_ms,
    animation_elapsed_ms: dominantAttrs.animation_elapsed_ms,
    animation_progress: dominantAttrs.animation_progress,
    animation_due: dominantAttrs.animation_due,
    propagation_event_id: dominantAttrs.propagation_event_id,
    propagation_kind: dominantAttrs.propagation_kind,
    propagation_phase: dominantAttrs.propagation_phase,
    propagation_role: dominantAttrs.propagation_role,
    propagation_intensity: dominantAttrs.propagation_intensity,
    propagation_confidence: dominantAttrs.propagation_confidence,
    propagation_grounding: dominantAttrs.propagation_grounding,
    propagation_current: dominantAttrs.propagation_current,
  }
}

const hexToRgb = (value) => {
  const input = String(value || '').trim().replace('#', '')
  if (![3, 6].includes(input.length)) return null
  const full = input.length === 3
    ? input.split('').map(char => `${char}${char}`).join('')
    : input
  const int = Number.parseInt(full, 16)
  if (!Number.isFinite(int)) return null
  return {
    r: (int >> 16) & 255,
    g: (int >> 8) & 255,
    b: int & 255,
  }
}

const blendColors = (base, accent, amount = 0.5) => {
  const from = hexToRgb(base)
  const to = hexToRgb(accent)
  if (!from || !to) return base || accent || '#999999'
  const ratio = clamp(Number(amount) || 0, 0, 1)
  const r = Math.round(from.r + (to.r - from.r) * ratio)
  const g = Math.round(from.g + (to.g - from.g) * ratio)
  const b = Math.round(from.b + (to.b - from.b) * ratio)
  return `rgb(${r}, ${g}, ${b})`
}

const getEntityAnimationStatus = (entity) => normalizeAnimationStatus(
  entity?.rawData?.attributes?.animation_status ?? entity?.attributes?.animation_status
)

const getEntityDelayMs = (entity, ratio = 1) => {
  const raw = Number(entity?.rawData?.attributes?.delay_ms ?? entity?.attributes?.delay_ms ?? 0)
  if (!Number.isFinite(raw)) return 0
  return clamp(Math.round(raw * ratio), 0, 520)
}

const getEntityAnimationProgress = (entity) => {
  const raw = Number(entity?.rawData?.attributes?.animation_progress ?? entity?.attributes?.animation_progress ?? 1)
  if (!Number.isFinite(raw)) return 1
  return clamp(raw, 0, 1)
}

const getNodeStableId = (node) => String(node?.uuid || node?.id || '')

const getEdgeStableId = (edge, fallbackIndex = 0) => {
  const explicit = edge?.uuid || edge?.id || edge?.edge_id || edge?.edgeId || edge?.fact_id || edge?.factId
  if (explicit) return String(explicit)
  const source = edge?.source_node_uuid || edge?.source || edge?.from || ''
  const target = edge?.target_node_uuid || edge?.target || edge?.to || ''
  const type = edge?.fact_type || edge?.name || edge?.type || 'related'
  return `${source}->${target}:${type}:${fallbackIndex}`
}

const buildGraphStructureSignature = (graph) => {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []
  const nodePart = nodes
    .map(node => getNodeStableId(node))
    .filter(Boolean)
    .sort()
    .join('|')
  const edgePart = edges
    .map((edge, index) => [
      getEdgeStableId(edge, index),
      edge?.source_node_uuid || edge?.source || '',
      edge?.target_node_uuid || edge?.target || '',
      edge?.fact_type || edge?.name || ''
    ].join(':'))
    .sort()
    .join('|')
  return `${nodes.length}:${edges.length}:${nodePart}::${edgePart}`
}

const updateRenderedGraphData = () => {
  if (!graph2DState || graphMode.value !== '2d' || !props.graphData) return false
  const latestNodes = new Map(
    (Array.isArray(props.graphData.nodes) ? props.graphData.nodes : [])
      .map(node => [getNodeStableId(node), node])
      .filter(([id]) => Boolean(id))
  )
  const latestEdges = new Map(
    (Array.isArray(props.graphData.edges) ? props.graphData.edges : [])
      .map((edge, index) => [getEdgeStableId(edge, index), edge])
      .filter(([id]) => Boolean(id))
  )

  graph2DState.nodes.forEach((node) => {
    const latest = latestNodes.get(node.id)
    if (!latest) return
    node.name = safeDisplayText(latest.name, node.name || '未命名节点')
    node.type = safeToken(latest.labels?.find(label => label !== 'Entity'), node.type || '其他类型')
    node.rawData = latest
    node.layer = nodeLayerKey(node)
  })

  graph2DState.edges.forEach((edge) => {
    if (edge.rawData?.isSelfLoopGroup) {
      const updatedLoops = (edge.rawData.selfLoopEdges || []).map((loopEdge, index) => {
        const latest = latestEdges.get(getEdgeStableId(loopEdge, index))
        return latest ? { ...loopEdge, ...latest } : loopEdge
      })
      edge.rawData = {
        ...edge.rawData,
        selfLoopEdges: updatedLoops,
        attributes: mergeAnimationAttributes(updatedLoops)
      }
      return
    }
    if (edge.rawData?.isParallelGroup) {
      const updatedParallelEdges = (edge.rawData.parallelEdges || []).map((memberEdge, index) => {
        const latest = latestEdges.get(getEdgeStableId(memberEdge, index))
        return latest ? { ...memberEdge, ...latest } : memberEdge
      })
      const first = updatedParallelEdges[0] || edge.rawData
      edge.type = first.fact_type || first.name || edge.type
      edge.name = `${first.name || first.fact_type || edge.name}（${updatedParallelEdges.length}）`
      edge.rawData = {
        ...edge.rawData,
        ...first,
        uuid: edge.rawData.uuid,
        id: edge.rawData.id,
        name: edge.name,
        isParallelGroup: true,
        parallelEdges: updatedParallelEdges,
        source_name: graph2DState.nodeMap.get(first.source_node_uuid || first.source)?.name,
        target_name: graph2DState.nodeMap.get(first.target_node_uuid || first.target)?.name,
        attributes: {
          ...(first.attributes || {}),
          ...mergeAnimationAttributes(updatedParallelEdges),
          aggregate_count: updatedParallelEdges.length,
          is_parallel_group: true,
        }
      }
      return
    }
    const latest = latestEdges.get(getEdgeStableId(edge.rawData))
    if (!latest) return
    edge.type = latest.fact_type || latest.name || edge.type
    edge.name = latest.name || latest.fact_type || edge.name
    edge.rawData = {
      ...latest,
      source_name: graph2DState.nodeMap.get(latest.source_node_uuid || latest.source)?.name,
      target_name: graph2DState.nodeMap.get(latest.target_node_uuid || latest.target)?.name
    }
  })

  // Density filtering intentionally keeps only a stable, readable baseline.
  // The current propagation wave is a separate overlay so an active ledger
  // edge can never disappear merely because it was not in the initial top-N.
  graph2DState.updatePulseLinks?.(
    Array.isArray(props.graphData.edges) ? props.graphData.edges : [],
  )

  graph2DState.nodeLabels?.text(d => {
    const label = displayToken(d.name)
    return label.length > 8 ? `${label.substring(0, 8)}…` : label
  })
  graph2DState.linkLabels?.text(d => displayToken(d.name))
  // The parent advances animation_progress on every playback frame. Apply
  // those state/style deltas in place instead of restarting 380-420ms D3
  // transitions (or, worse, rebuilding the force layout) on every RAF.
  graph2DState.applyBaseGraphState?.({ animate: false })
  return true
}

const scheduleRenderedGraphDataUpdate = () => {
  if (graph2DDataFrame !== null) return
  graph2DDataFrame = requestAnimationFrame(() => {
    graph2DDataFrame = null
    const nextSignature = buildGraphStructureSignature(props.graphData)
    if (
      graphMode.value === '2d'
      && graph2DState
      && nextSignature
      && nextSignature === last2DStructureSignature
    ) {
      updateRenderedGraphData()
      return
    }
    scheduleGraphRender()
  })
}

const getLinkBaseColorByType = (type) => {
  const token = String(type || '').trim().toLowerCase()
  if (token === 'dynamic_edge') return '#b45309'
  if (token === 'agent_influence' || token === 'influences_region') return '#2563eb'
  if (token.includes('depend') || token.includes('affect') || token.includes('regulat')) return '#7c3aed'
  if (token === 'self_loop') return '#64748b'
  return '#64748b'
}

// --- M10 honesty helpers: split spatial skeleton vs causal coupling -------
// Read the Phase A backend keys directly off each edge (additive, guarded).
const readEdgeRaw = (edge) => edge?.rawData || edge || {}

const getEdgeLayer = (edge) => {
  const raw = readEdgeRaw(edge)
  const layer = String(raw.edge_layer || raw.attributes?.edge_layer || '').trim().toLowerCase()
  if (layer === 'spatial_fact' || layer === 'causal') return layer
  return ''
}

const isSpatialFactEdge = (edge) => getEdgeLayer(edge) === 'spatial_fact'

const getEdgeEpistemic = (edge) => {
  const raw = readEdgeRaw(edge)
  return String(
    raw.epistemic || raw.provenance || raw.attributes?.epistemic_status || raw.attributes?.validation_status || ''
  ).trim().toLowerCase()
}

// Style edges by epistemic/provenance honesty:
//   observed/structural -> solid, inferred -> dashed, speculative/assumed -> dotted.
const getEpistemicDashArray = (edge, is3D = false) => {
  const token = getEdgeEpistemic(edge)
  if (!token) return undefined
  if (token.includes('observ') || token.includes('structural') || token.includes('confirm') || token.includes('fact')) {
    return undefined
  }
  if (token.includes('specul') || token.includes('assum') || token.includes('hypo')) {
    return is3D ? undefined : '1.5 5'
  }
  if (token.includes('infer') || token.includes('estimat') || token.includes('derive')) {
    return is3D ? undefined : '7 5'
  }
  return undefined
}

// Channel-driven color for causal edges so structure reads by interaction type.
const getEdgeChannel = (edge) => {
  const raw = readEdgeRaw(edge)
  return String(
    raw.channel || raw.attributes?.interaction_channel || raw.attributes?.channel_type || raw.attributes?.channel || ''
  ).trim().toLowerCase()
}

const CHANNEL_COLORS = {
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

const getCausalChannelColor = (edge, fallback) => {
  const channel = getEdgeChannel(edge)
  if (!channel) return fallback
  for (const [token, color] of Object.entries(CHANNEL_COLORS)) {
    if (channel.includes(token)) return color
  }
  return fallback
}

// De-emphasize intra-cluster spatial edges when a community/cluster id is present.
const getNodeClusterId = (edge, endpoint) => {
  const raw = readEdgeRaw(edge)
  const attrs = raw.attributes || {}
  if (endpoint === 'source') {
    return String(attrs.source_region_id || attrs.source_cluster_id || attrs.source_community_id || '').trim()
  }
  return String(attrs.target_region_id || attrs.target_cluster_id || attrs.target_community_id || '').trim()
}

const isIntraClusterSpatialEdge = (edge) => {
  if (!isSpatialFactEdge(edge)) return false
  const source = getNodeClusterId(edge, 'source')
  const target = getNodeClusterId(edge, 'target')
  return Boolean(source) && Boolean(target) && source === target
}

// --- 治毛球：按密度筛选要渲染的边 -----------------------------------------
// 思路：空间骨架边本就是淡化噪声，先移除；推测性因果边降级；必要时按
// "证据强度 + 节点度数"封顶，让强关系浮现而不糊成一团。诚实显示
// "当前显示 N / 共 M"，不做静默截断。
const edgeEpistemicScore = (edge) => {
  const token = getEdgeEpistemic(edge)
  if (!token) return 2
  if (token.includes('observ') || token.includes('structural') || token.includes('confirm') || token.includes('fact')) return 3
  if (token.includes('specul') || token.includes('assum') || token.includes('hypo')) return 1
  return 2
}

const DENSITY_CAP = { strong: 84, standard: 220 }
const DENSITY_NODE_EDGE_CAP = { strong: 6, standard: 10 }

const normalizedEdgeMetric = (value) => {
  const number = Number(value)
  if (!Number.isFinite(number)) return 0
  return clamp(number > 1 ? number / 100 : number, 0, 1)
}

const densityEdgeScore = (edge, degree) => {
  const raw = readEdgeRaw(edge)
  const attrs = raw.attributes || {}
  const strength = normalizedEdgeMetric(attrs.strength ?? raw.strength)
  const confidence = normalizedEdgeMetric(attrs.confidence ?? raw.confidence)
  const keyBonus = attrs.is_key_interaction || raw.is_key_interaction ? 360 : 0
  const hubPenalty = Math.max(
    degree.get(raw.source_node_uuid) || 0,
    degree.get(raw.target_node_uuid) || 0,
  ) * 4
  return edgeEpistemicScore(edge) * 1000 + keyBonus + strength * 240 + confidence * 180 - hubPenalty
}

const computeDensityPlan = (edgesData, nodeIds) => {
  const connected = (edgesData || []).filter(
    e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid)
  )
  const total = connected.length
  const mode = edgeDensity.value
  if (mode === 'all') {
    return { allow: () => true, shown: total, total }
  }

  // 节点度数（用于重要度排序的次级信号）
  const degree = new Map()
  connected.forEach(e => {
    degree.set(e.source_node_uuid, (degree.get(e.source_node_uuid) || 0) + 1)
    degree.set(e.target_node_uuid, (degree.get(e.target_node_uuid) || 0) + 1)
  })

  // 回放中本轮"活跃/新增"的边：无论档位与封顶，永远保留（否则会把正在演化的关系筛掉）
  const isLiveAnimatedEdge = (e) => {
    const s = String(readEdgeRaw(e)?.attributes?.animation_status || '').toLowerCase()
    return s === 'active' || s === 'new'
  }

  const alwaysKeep = []   // 标准模式下保留的（已淡化的）空间骨架 + 回放活跃边
  const causalPool = []
  for (const e of connected) {
    if (isLiveAnimatedEdge(e)) {
      alwaysKeep.push(e)
      continue
    }
    if (isSpatialFactEdge(e)) {
      if (mode === 'strong') continue   // 强关系：去掉空间骨架
      alwaysKeep.push(e)                 // 标准：保留骨架（本就淡化），与图例一致
      continue
    }
    if (mode === 'strong' && edgeEpistemicScore(e) <= 1) continue // 强关系：再去掉推测性因果
    causalPool.push(e)
  }

  // 只对因果边封顶。上限随节点数变化，并对单个枢纽设扇出限制；
  // 这样重点关系仍覆盖网络，但不会因为“节点度数高”反而优先制造毛球。
  const absoluteCap = DENSITY_CAP[mode] || 220
  const scaledCap = mode === 'strong'
    ? Math.max(36, Math.round(nodeIds.size * 1.15))
    : Math.max(90, Math.round(nodeIds.size * 2.4))
  const cap = Math.min(absoluteCap, scaledCap)
  const perNodeCap = DENSITY_NODE_EDGE_CAP[mode] || 10
  const ranked = causalPool
    .map(e => ({ e, score: densityEdgeScore(e, degree) }))
    .sort((a, b) => b.score - a.score)
  const causalKept = []
  const selectedDegree = new Map()
  const selectedSet = new Set()
  const addEdge = (edge) => {
    if (!edge || selectedSet.has(edge) || causalKept.length >= cap) return false
    selectedSet.add(edge)
    causalKept.push(edge)
    selectedDegree.set(edge.source_node_uuid, (selectedDegree.get(edge.source_node_uuid) || 0) + 1)
    selectedDegree.set(edge.target_node_uuid, (selectedDegree.get(edge.target_node_uuid) || 0) + 1)
    return true
  }

  // First preserve broad node coverage, then fill by evidence/strength while
  // respecting the hub cap.
  ranked.forEach(({ e }) => {
    if (causalKept.length >= cap) return
    const sourceSeen = (selectedDegree.get(e.source_node_uuid) || 0) > 0
    const targetSeen = (selectedDegree.get(e.target_node_uuid) || 0) > 0
    const sourceCount = selectedDegree.get(e.source_node_uuid) || 0
    const targetCount = selectedDegree.get(e.target_node_uuid) || 0
    if (sourceCount >= perNodeCap || targetCount >= perNodeCap) return
    if (!sourceSeen || !targetSeen) addEdge(e)
  })
  ranked.forEach(({ e }) => {
    if (causalKept.length >= cap || selectedSet.has(e)) return
    const sourceCount = selectedDegree.get(e.source_node_uuid) || 0
    const targetCount = selectedDegree.get(e.target_node_uuid) || 0
    if (sourceCount >= perNodeCap || targetCount >= perNodeCap) return
    addEdge(e)
  })
  const allowSet = new Set([...alwaysKeep, ...causalKept])
  return { allow: (e) => allowSet.has(e), shown: allowSet.size, total }
}

const aggregateParallelEdges2D = (edges = []) => {
  const groups = new Map()
  const order = []
  edges.forEach((edge, index) => {
    if (edge.source_node_uuid === edge.target_node_uuid) {
      order.push({ key: `self:${getEdgeStableId(edge, index)}`, edges: [edge] })
      return
    }
    const channel = getEdgeChannel(edge)
    const layer = getEdgeLayer(edge) || 'relation'
    const type = String(edge.fact_type || edge.name || 'related').toLowerCase()
    const semanticKey = channel || type
    const key = `${edge.source_node_uuid}->${edge.target_node_uuid}:${layer}:${semanticKey}`
    if (!groups.has(key)) {
      const group = { key, edges: [] }
      groups.set(key, group)
      order.push(group)
    }
    groups.get(key).edges.push(edge)
  })

  return order.map((group) => {
    if (group.edges.length === 1) return group.edges[0]
    const first = group.edges[0]
    const label = first.name || first.fact_type || 'RELATED'
    return {
      ...first,
      uuid: `parallel::${group.key}`,
      id: `parallel::${group.key}`,
      name: `${label}（${group.edges.length}）`,
      attributes: {
        ...(first.attributes || {}),
        ...mergeAnimationAttributes(group.edges),
        aggregate_count: group.edges.length,
        is_parallel_group: true,
      },
      isParallelGroup: true,
      parallelEdges: group.edges,
    }
  })
}

// --- M10 node playback: bind radius/color to the frame's real value/delta ----
const readNodeStateStatus = (node) => {
  const attrs = node?.rawData?.attributes ?? node?.attributes ?? {}
  return String(attrs.state_status || '').trim().toLowerCase()
}

const readNodeDelta = (node) => {
  const attrs = node?.rawData?.attributes ?? node?.attributes ?? {}
  const value = Number(attrs.delta)
  return Number.isFinite(value) ? value : null
}

// Returns a value-driven tint/scale overlay only when the frame carries real
// state. Falls back to {} (no override) so reveal animation stays intact.
const getNodeStateOverlay = (node) => {
  const status = readNodeStateStatus(node)
  const delta = readNodeDelta(node)
  if (!status && delta === null) return null
  const magnitude = delta === null ? 0 : clamp(Math.abs(delta) / 0.25, 0, 1)
  let tint = null
  let scale = 1
  if (status === 'critical') {
    tint = '#dc2626'; scale = 1.28
  } else if (status === 'rising' || status === 'elevated' || (delta !== null && delta > 0.0001)) {
    tint = '#f97316'; scale = 1 + 0.18 * magnitude
  } else if (status === 'falling' || (delta !== null && delta < -0.0001)) {
    tint = '#0ea5e9'; scale = Math.max(0.82, 1 - 0.16 * magnitude)
  } else {
    return null
  }
  return { status, delta, tint, scale, blend: status === 'critical' ? 0.55 : 0.38 + 0.32 * magnitude }
}

// Template-facing: build human-readable honesty badges for the edge detail card.
const edgeHonesty = (edgeData) => {
  if (!edgeData) return null
  const layer = getEdgeLayer(edgeData)
  const epistemic = getEdgeEpistemic(edgeData)
  const channel = getEdgeChannel(edgeData)
  if (!layer && !epistemic && !channel) return null
  const layerLabel = layer === 'spatial_fact' ? '空间事实' : layer === 'causal' ? '因果关系' : ''
  let epistemicLabel = ''
  if (epistemic) {
    if (epistemic.includes('observ') || epistemic.includes('structural') || epistemic.includes('fact')) {
      epistemicLabel = '观察'
    } else if (epistemic.includes('specul') || epistemic.includes('assum') || epistemic.includes('hypo')) {
      epistemicLabel = '推测'
    } else if (epistemic.includes('infer') || epistemic.includes('estimat') || epistemic.includes('derive')) {
      epistemicLabel = '推断'
    } else {
      epistemicLabel = displayToken(epistemic)
    }
  }
  const channelLabel = channel ? displayToken(channel) : ''
  return { layer, layerLabel, epistemicLabel, channelLabel }
}

const getNodeBaseRadius = (node, is3D = false) => {
  const layer = node.layer || nodeLayerKey(node)
  if (is3D) {
    if (layer === 'macro') return 5.6
    if (layer === 'subregion') return 4.8
    return 4
  }
  if (layer === 'macro') return 12
  if (layer === 'subregion') return 10
  return 8.6
}

const getNodeAnimationStyle = (node, { highlightActive = false, highlighted = false, is3D = false } = {}) => {
  const rawStatus = getEntityAnimationStatus(node)
  // 回放/动画中不再把"非脉冲"元素整体藏掉——否则整张关系网消失（"显示不出来"）。
  // 直接采用每个节点/边自身的状态：steady 背景常显、new/active 高亮跳动、hidden 才隐藏。
  const status = rawStatus
  const progress = getEntityAnimationProgress(node)
  const baseColor = getNodeColorByType(node.type)
  const baseRadius = getNodeBaseRadius(node, is3D)
  let color = baseColor
  let radius = baseRadius
  let opacity = is3D ? 0.9 : 0.96
  let strokeColor = '#ffffff'
  let strokeWidth = is3D ? 0 : 2.5
  let labelOpacity = node.layer === 'agent' ? 0.18 : 0.84
  let labelScale = 1
  let haloColor = baseColor
  let haloOpacity = 0

  if (status === 'new') {
    color = blendColors(baseColor, '#f59e0b', 0.46)
    radius += is3D ? 1.35 : 2.6
    opacity = is3D ? 0.96 : 0.98
    strokeColor = '#b45309'
    strokeWidth = is3D ? 0 : 3.2
    labelOpacity = 0.92
    labelScale = 1.08
    haloColor = '#f59e0b'
    haloOpacity = 0.22
  } else if (status === 'active') {
    color = blendColors(baseColor, '#ef4444', 0.56)
    radius += is3D ? 2.1 : 3.4
    opacity = is3D ? 0.98 : 1
    strokeColor = '#7f1d1d'
    strokeWidth = is3D ? 0 : 3.8
    labelOpacity = 1
    labelScale = 1.16
    haloColor = '#ef4444'
    haloOpacity = 0.3
  } else if (status === 'faded') {
    color = blendColors(baseColor, '#cbd5e1', 0.72)
    radius = Math.max(is3D ? 2.6 : 6.2, radius - (is3D ? 1.2 : 2.1))
    opacity = is3D ? 0.18 : 0.22
    strokeColor = '#cbd5e1'
    strokeWidth = is3D ? 0 : 1.5
    labelOpacity = 0.08
    labelScale = 0.9
  } else if (status === 'hidden') {
    radius = Math.max(is3D ? 1.8 : 4.4, radius - (is3D ? 1.6 : 3))
    opacity = 0
    strokeColor = '#d7dee8'
    strokeWidth = is3D ? 0 : 0.8
    labelOpacity = 0
    haloOpacity = 0
  }

  if (status !== 'hidden') {
    const revealScale = 0.58 + (progress * 0.42)
    radius *= revealScale
    opacity *= 0.18 + (progress * 0.82)
    labelOpacity *= progress
    haloOpacity *= progress
  }

  // M10 playback: bind radius + color to the frame's real value/delta so a
  // rising metric reads warm + larger and a falling one reads cool + smaller,
  // instead of only the reveal animation. Guarded: no-op when no real state.
  if (status !== 'hidden') {
    const overlay = getNodeStateOverlay(node)
    if (overlay) {
      color = blendColors(color, overlay.tint, overlay.blend)
      radius *= overlay.scale
      if (overlay.status === 'critical') {
        haloColor = overlay.tint
        haloOpacity = Math.max(haloOpacity, 0.28)
        strokeColor = is3D ? strokeColor : '#7f1d1d'
      }
    }
  }

  if (highlightActive) {
    if (highlighted && status !== 'hidden') {
      radius += is3D ? 1.1 : 1.8
      opacity = 1
      strokeColor = '#7c2d12'
      strokeWidth = is3D ? 0 : Math.max(strokeWidth, 4)
      labelOpacity = 1
      labelScale = Math.max(labelScale, 1.14)
      haloColor = '#dc2626'
      haloOpacity = Math.max(haloOpacity, 0.34)
    } else if (status === 'active') {
      opacity = Math.max(opacity, is3D ? 0.9 : 0.92)
      labelOpacity = Math.max(labelOpacity, 0.92)
    } else if (status === 'new') {
      opacity = Math.max(opacity, is3D ? 0.8 : 0.86)
      labelOpacity = Math.max(labelOpacity, 0.74)
    } else if (status === 'faded') {
      opacity = Math.min(opacity, 0.08)
      labelOpacity = 0.04
    } else if (status === 'hidden') {
      opacity = 0
      labelOpacity = 0
    } else {
      // 回放/动画模式：非焦点的"背景网络"必须保持清晰可见（不要压到 0.24 看不清整张网，
      // 那正是"显示不出来"的观感来源）；点击聚焦等其它高亮场景仍强压暗以突出选中项。
      opacity = props.highlightMode === 'animation' ? Math.max(opacity * 0.62, 0.5) : 0.24
      labelOpacity = node.layer === 'agent' ? 0.08 : 0.22
    }
  }

  return {
    status,
    color,
    radius,
    opacity,
    strokeColor,
    strokeWidth,
    labelOpacity,
    labelScale,
    haloColor,
    haloOpacity,
    delayMs: getEntityDelayMs(node),
  }
}

const isTruthyGraphFlag = (value) => value === true
  || value === 1
  || ['true', 'yes', 'key', 'critical'].includes(String(value || '').trim().toLowerCase())

const isOverviewPriorityNode = (node) => {
  const raw = node?.rawData || node || {}
  const attributes = raw.attributes || {}
  if (
    isTruthyGraphFlag(raw.is_key)
    || isTruthyGraphFlag(raw.is_key_node)
    || isTruthyGraphFlag(raw.isKey)
    || isTruthyGraphFlag(attributes.is_key)
    || isTruthyGraphFlag(attributes.is_key_node)
    || isTruthyGraphFlag(attributes.isKey)
    || isTruthyGraphFlag(attributes.focus_node)
  ) return true

  const priority = String(attributes.priority || attributes.importance || raw.priority || '').trim().toLowerCase()
  if (priority === 'critical' || priority === 'high') return true
  const priorityScore = Number(attributes.priority_score ?? raw.priority_score)
  return Number.isFinite(priorityScore) && priorityScore >= 70
}

const isSelectedGraphNode = (node) => {
  if (selectedItem.value?.type !== 'node') return false
  return getNodeStableId(selectedItem.value.data) === String(node?.id || '')
}

const shouldShowNodeLabel = (
  node,
  {
    highlightActive = false,
    highlighted = false,
    zoomScale = 1,
  } = {},
) => {
  const rawStatus = getEntityAnimationStatus(node)
  // 回放/动画中不再把"非脉冲"元素整体藏掉——否则整张关系网消失（"显示不出来"）。
  // 直接采用每个节点/边自身的状态：steady 背景常显、new/active 高亮跳动、hidden 才隐藏。
  const status = rawStatus
  if (status === 'hidden') return false
  if (highlighted || isSelectedGraphNode(node)) return true
  if (status === 'active') return true
  if (status === 'new' && zoomScale >= NODE_LABEL_LOD_ZOOM) return true
  const layer = node.layer || nodeLayerKey(node)
  if (layer === 'macro' || layer === 'subregion') return true
  const type = String(node.type || '').toLowerCase()
  if (type.includes('risk') || type.includes('风险')) return true
  if (isOverviewPriorityNode(node)) return true
  if (zoomScale < NODE_LABEL_LOD_ZOOM && layer === 'agent') return false
  return !highlightActive && layer !== 'agent'
}

const getLinkAnimationStyle = (
  link,
  {
    highlightActive = false,
    highlighted = false,
    focused = false,
    is3D = false,
    highlightColor = '#dc2626',
    neighborColor = '#E0A25A',
  } = {},
) => {
  const rawStatus = getEntityAnimationStatus(link)
  // 回放/动画中不再把"非脉冲"元素整体藏掉——否则整张关系网消失（"显示不出来"）。
  // 直接采用每个节点/边自身的状态：steady 背景常显、new/active 高亮跳动、hidden 才隐藏。
  const status = rawStatus
  const progress = getEntityAnimationProgress(link)
  // M10: classify the edge so the spatial skeleton reads faint while causal
  // coupling reads bold + channel-colored (kills the undifferentiated hairball).
  const edgeLayer = getEdgeLayer(link)
  const spatial = edgeLayer === 'spatial_fact'
  const intraCluster = isIntraClusterSpatialEdge(link)
  const typeColor = getLinkBaseColorByType(link.type || link?.rawData?.fact_type || link?.name)
  const baseColor = spatial
    ? '#94a3b8'
    : getCausalChannelColor(link, typeColor)
  let color = baseColor
  let width = spatial ? (is3D ? 0.35 : 0.85) : (is3D ? 0.7 : 1.8)
  let opacity = spatial
    ? (intraCluster ? (is3D ? 0.08 : 0.07) : (is3D ? 0.16 : 0.14))
    : (is3D ? 0.32 : 0.32)
  let dashArray = undefined
  let labelOpacity = 0.32
  let labelColor = '#666666'
  let particles = 0
  let particleWidth = 0

  if (status === 'new') {
    color = blendColors(baseColor, '#f59e0b', 0.56)
    width += is3D ? 0.8 : 1.05
    opacity = is3D ? 0.72 : 0.68
    dashArray = '8 6'
    labelOpacity = 0.72
    labelColor = color
    particles = 1
    particleWidth = 1.8
  } else if (status === 'active') {
    color = blendColors(baseColor, '#ef4444', 0.62)
    width += is3D ? 1.05 : 1.55
    opacity = is3D ? 0.92 : 0.86
    labelOpacity = 1
    labelColor = color
    particles = 2
    particleWidth = 2.4
  } else if (status === 'faded') {
    color = blendColors(baseColor, '#cbd5e1', 0.72)
    width = is3D ? 0.18 : 0.9
    opacity = is3D ? 0.08 : 0.16
    dashArray = '3 7'
    labelOpacity = 0.08
    labelColor = '#94a3b8'
  } else if (status === 'hidden') {
    color = '#d8dee8'
    width = is3D ? 0.08 : 0.45
    opacity = 0
    dashArray = '2 9'
    labelOpacity = 0
    labelColor = '#cbd5e1'
  }

  if (status !== 'hidden') {
    width *= 0.55 + (progress * 0.45)
    opacity *= 0.12 + (progress * 0.88)
    labelOpacity *= progress
    particles = progress >= 0.35 ? particles : 0
  }

  if (highlightActive) {
    if (highlighted && status !== 'hidden') {
      color = highlightColor
      width = is3D ? 2.05 : 3.2
      opacity = 1
      dashArray = undefined
      labelOpacity = 1
      labelColor = highlightColor
      particles = Math.max(particles, 2.5)
      particleWidth = Math.max(particleWidth, 2.6)
    } else if (focused && status !== 'hidden') {
      color = status === 'active' ? color : neighborColor
      width = Math.max(width, is3D ? 1.15 : 2.1)
      opacity = Math.max(opacity, is3D ? 0.62 : 0.9)
      labelOpacity = Math.max(labelOpacity, 0.86)
      particles = Math.max(particles, status === 'faded' ? 0 : 1)
      particleWidth = Math.max(particleWidth, particles ? 1.9 : 0)
    } else if (status === 'new' || status === 'active') {
      opacity = Math.max(opacity, is3D ? 0.56 : 0.74)
      labelOpacity = Math.max(labelOpacity, 0.6)
    } else if (status === 'hidden') {
      opacity = 0
      labelOpacity = 0
      particles = 0
    } else {
      opacity = status === 'faded' ? 0.04 : (is3D ? 0.06 : 0.1)
      labelOpacity = Math.min(labelOpacity, 0.16)
    }
  }

  // M10 epistemic honesty: observed=solid, inferred=dashed, speculative=dotted.
  // Only override the dash pattern when the edge is not already animating /
  // highlighted with its own dash, so reveal pulses stay legible.
  if (!highlighted && status !== 'new' && status !== 'active') {
    const epistemicDash = getEpistemicDashArray(link, is3D)
    if (epistemicDash !== undefined) dashArray = epistemicDash
  }

  // Keep the spatial skeleton quiet so causal structure stays readable, except
  // when an edge is explicitly highlighted/focused (handled above).
  if (spatial && !highlighted && !(highlightActive && focused) && status !== 'active' && status !== 'new') {
    width = Math.min(width, is3D ? 0.4 : 1)
    opacity = Math.min(opacity, intraCluster ? (is3D ? 0.08 : 0.07) : (is3D ? 0.18 : 0.16))
    labelOpacity = Math.min(labelOpacity, 0.08)
  }

  return {
    status,
    color,
    width,
    opacity,
    dashArray,
    labelOpacity,
    labelColor,
    particles,
    particleWidth,
    delayMs: getEntityDelayMs(link, 0.72),
  }
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
    graph3DState.value = 'idle'
    destroy3DGraph()
    return
  }
  graph3DState.value = 'loading'
  graph3DErrorMessage.value = ''

  const nodes = nodesData.map(node => ({
    id: node.uuid,
    name: safeDisplayText(node.name, '未命名节点'),
    type: safeToken(node.labels?.find(label => label !== 'Entity'), '其他类型'),
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

  // 治毛球：按当前密度档位筛选要渲染的边
  const densityPlan = computeDensityPlan(edgesData, nodeIds)
  renderedEdgeStats.value = { shown: densityPlan.shown, total: densityPlan.total }

  const links = edgesData
    .filter(edge => nodeIds.has(edge.source_node_uuid) && nodeIds.has(edge.target_node_uuid) && densityPlan.allow(edge))
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
    if (props.highlightMode === 'animation') return false
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
  const shouldAnimateFrameTransition = props.highlightMode === 'animation'

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

  try {
    const { createGraph3D, THREE, SpriteText } = await load3DDeps()
    if (graphMode.value !== '3d') return

    const createdNewInstance = !graph3DInstance
    if (createdNewInstance) {
      graph3DInstance = createGraph3D()(container)
    }
    const cameraPose = compute3DCameraPose(nodes, highlightedNodeIds)

    const createNodeObject = (node) => {
      const group = new THREE.Group()
      const highlighted = Boolean(node.externallyHighlighted)
      const style = getNodeAnimationStyle(node, {
        highlightActive,
        highlighted,
        is3D: true,
      })

      if (style.haloOpacity > 0) {
        const halo = new THREE.Mesh(
          new THREE.SphereGeometry(style.radius + 1.25, 18, 18),
          new THREE.MeshBasicMaterial({
            color: style.haloColor,
            transparent: true,
            opacity: style.haloOpacity,
            depthWrite: false,
          })
        )
        group.add(halo)
      }

      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(style.radius, 18, 18),
        new THREE.MeshLambertMaterial({
          color: style.color,
          transparent: true,
          opacity: style.opacity,
        })
      )
      group.add(sphere)

      if (node.surfaceLabel && shouldShowNodeLabel(node, { highlightActive, highlighted })) {
        const label = new SpriteText(node.surfaceLabel)
        label.textHeight = 9.5 * style.labelScale
        label.color = highlighted || style.status === 'active' ? '#111111' : '#1F2933'
        label.backgroundColor = style.status === 'active'
          ? 'rgba(255,244,238,0.96)'
          : style.status === 'new'
            ? 'rgba(255,248,235,0.94)'
            : highlightActive && !highlighted
              ? 'rgba(255,255,255,0.78)'
              : 'rgba(255,255,255,0.95)'
        label.padding = 2.2
        label.borderWidth = 1.2
        label.borderColor = 'rgba(55,65,81,0.35)'
        label.strokeWidth = 1.8
        label.strokeColor = 'rgba(255,255,255,0.98)'
        if (label.material) {
          label.material.depthWrite = false
          label.material.depthTest = false
          label.material.transparent = true
          label.material.opacity = style.labelOpacity
        }
        label.renderOrder = 999
        const x = Number(node.x) || 0
        const y = Number(node.y) || 0
        const z = Number(node.z) || 0
        const length = Math.sqrt(x * x + y * y + z * z) || 1
        const outward = style.radius + 10
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
      .nodeLabel(node => `${safeDisplayText(node.name, '未命名节点')}\n${safeToken(node.type, '其他类型')}`)
      .nodeVal(node => getNodeAnimationStyle(node, {
        highlightActive,
        highlighted: Boolean(node.externallyHighlighted),
        is3D: true,
      }).radius)
      .nodeColor(node => getNodeAnimationStyle(node, {
        highlightActive,
        highlighted: Boolean(node.externallyHighlighted),
        is3D: true,
      }).color)
      .linkColor(link => {
        return getLinkAnimationStyle(link, {
          highlightActive,
          highlighted: isEdgeHighlighted(link),
          focused: isLinkFocused(link),
          is3D: true,
          highlightColor: edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        }).color
      })
      .linkWidth(link => {
        return getLinkAnimationStyle(link, {
          highlightActive,
          highlighted: isEdgeHighlighted(link),
          focused: isLinkFocused(link),
          is3D: true,
          highlightColor: edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        }).width
      })
      .linkOpacity(link => {
        return getLinkAnimationStyle(link, {
          highlightActive,
          highlighted: isEdgeHighlighted(link),
          focused: isLinkFocused(link),
          is3D: true,
          highlightColor: edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        }).opacity
      })
      .linkDirectionalParticles(link => getLinkAnimationStyle(link, {
        highlightActive,
        highlighted: isEdgeHighlighted(link),
        focused: isLinkFocused(link),
        is3D: true,
        highlightColor: edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).particles)
      .linkDirectionalParticleWidth(link => getLinkAnimationStyle(link, {
        highlightActive,
        highlighted: isEdgeHighlighted(link),
        focused: isLinkFocused(link),
        is3D: true,
        highlightColor: edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).particleWidth)
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
      controls.minDistance = 260
      controls.maxDistance = 2200
    }
    if (createdNewInstance || !previousCamera) {
      graph3DInstance.cameraPosition(cameraPose.position, cameraPose.target, 900)
    } else {
      graph3DInstance.cameraPosition(previousCamera)
      const nextControls = graph3DInstance.controls?.()
      if (nextControls?.target && previousTarget) {
        nextControls.target.set(previousTarget.x, previousTarget.y, previousTarget.z)
        nextControls.update?.()
      }
    }
    graph3DState.value = 'ready'
  } catch (error) {
    console.error('3D graph render failed', error)
    graph3DState.value = 'unsupported'
    graph3DErrorMessage.value = '这个环境暂时不支持 3D 图谱渲染，可以先切换到地图或 2D 图谱继续回放。'
    destroy3DGraph()
  }
}

const renderActiveGraph = async () => {
  if (graphMode.value === 'map') {
    graph3DState.value = 'idle'
    stop2DSimulation()
    destroy3DGraph()
    return
  }
  if (graphMode.value === '3d') {
    await renderGraph3D()
  } else {
    graph3DState.value = 'idle'
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
  const nodeLookup = new Map()
  nodesData.forEach(n => {
    nodeMap[n.uuid] = n
    nodeLookup.set(n.uuid, n)
  })
  
  const nodes = nodesData.map(n => {
    const oldNode = oldNodeMap.get(n.uuid)
    const graphNode = {
      id: n.uuid,
      name: safeDisplayText(n.name, '未命名节点'),
      type: safeToken(n.labels?.find(l => l !== 'Entity'), '其他类型'),
      rawData: n,
      x: oldNode ? oldNode.x : undefined,
      y: oldNode ? oldNode.y : undefined,
      fx: oldNode && oldNode.fx !== null ? oldNode.fx : undefined,
      fy: oldNode && oldNode.fy !== null ? oldNode.fy : undefined,
      vx: oldNode ? oldNode.vx : undefined,
      vy: oldNode ? oldNode.vy : undefined,
      _isDragging: oldNode ? oldNode._isDragging : false
    }
    graphNode.layer = nodeLayerKey(graphNode)
    return graphNode
  })

  const nodeIds = new Set(nodes.map(n => n.id))

  // 治毛球：按当前密度档位筛选要渲染的边
  const densityPlan = computeDensityPlan(edgesData, nodeIds)
  renderedEdgeStats.value = { shown: densityPlan.shown, total: densityPlan.total }

  // 处理边数据，计算同一对节点间的边数量和索引
  const edgePairCount = {}
  const selfLoopEdges = {} // 按节点分组的自环边
  const filteredEdges = edgesData
    .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid) && densityPlan.allow(e))
  const tempEdges = aggregateParallelEdges2D(filteredEdges)
  renderedEdgeStats.value = { shown: tempEdges.length, total: densityPlan.total }
  
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
      const nodeName = nodeMap[e.source_node_uuid]?.name || '未知节点'
      const highlightKeys = uniqueTokens(
        allSelfLoops.flatMap((loopEdge, loopIndex) =>
          buildEdgeHighlightKeys(loopEdge, e.source_node_uuid, e.target_node_uuid, loopEdge.fact_type || loopEdge.name || 'SELF_LOOP', loopIndex)
        ).concat([`self_loop::${e.source_node_uuid}`])
      )
      
      edges.push({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: 'SELF_LOOP',
        name: `自关联（${allSelfLoops.length}）`,
        curvature: 0,
        isSelfLoop: true,
        highlightKeys,
        rawData: {
          isSelfLoopGroup: true,
          source_name: nodeName,
          target_name: nodeName,
          selfLoopCount: allSelfLoops.length,
          selfLoopEdges: allSelfLoops, // 存储所有自环边的详细信息
          attributes: mergeAnimationAttributes(allSelfLoops)
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
    const parallelMembers = Array.isArray(e.parallelEdges) && e.parallelEdges.length ? e.parallelEdges : [e]
    const highlightKeys = uniqueTokens(parallelMembers.flatMap((member, memberIndex) => (
      buildEdgeHighlightKeys(
        member,
        member.source_node_uuid,
        member.target_node_uuid,
        member.fact_type || member.name || 'RELATED',
        memberIndex,
      )
    )))
    
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
  entityTypes.value.forEach(t => {
    colorMap[t.rawType || t.name] = t.color
    colorMap[t.name] = t.color
  })
  const getColor = (type) => colorMap[type] || '#999'
  const edgeNeighborColor = '#E0A25A'
  const getCurrentHighlightState = () => {
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
    const isEdgeHighlighted = (linkData) => (linkData.highlightKeys || []).some(token => highlightedEdgeIdSet.has(token))
    const getLinkedNodeId = (nodeRef) => typeof nodeRef === 'object' ? nodeRef?.id : nodeRef
    const isLinkFocused = (linkData) => {
      if (isEdgeHighlighted(linkData)) return true
      if (props.highlightMode === 'animation') return false
      return highlightedNodeIds.has(getLinkedNodeId(linkData.source)) || highlightedNodeIds.has(getLinkedNodeId(linkData.target))
    }
    const highlightActive = highlightedIdSet.size > 0 || highlightedNameSet.size > 0 || highlightedEdgeIdSet.size > 0
    const edgeHighlightColor = props.highlightMode === 'risk_runtime'
      ? '#E04F39'
      : props.highlightMode === 'risk_definition'
        ? '#F08A24'
        : '#E0A25A'
    return {
      highlightedNodeIds,
      highlightActive,
      isEdgeHighlighted,
      isLinkFocused,
      edgeHighlightColor,
    }
  }
  const shouldAnimateFrameTransition = props.highlightMode === 'animation'

  const labelLayoutActive = showEdgeLabels.value
  const clusterTargets = buildRegionClusterTargets(nodes, width, height)
  const clusterTargetFor = (node) => clusterTargets.get(nodeRegionKey(node)) || { x: width / 2, y: height / 2 }

  // Simulation: keep each Agent around its real owning region. Once the
  // density view removes most baseline edges, a plain global force would let
  // same-region Agents drift to opposite sides and turn local propagation into
  // full-screen spaghetti.
  const simulation = d3.forceSimulation(nodes)
    .alpha(labelLayoutActive ? 0.9 : (oldNodeMap.size > 0 ? 0.3 : 1)) // 标签模式需要重新展开；普通刷新降低热度避免位置突变
    .alphaDecay(labelLayoutActive ? 0.045 : (oldNodeMap.size > 0 ? 0.09 : 0.06))
    .velocityDecay(labelLayoutActive ? 0.5 : 0.55)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
      const sourceLayer = d.source?.layer || nodeLayerKey(d.source)
      const targetLayer = d.target?.layer || nodeLayerKey(d.target)
      const localAgentLink = sourceLayer === 'agent' && targetLayer === 'agent'
      const macroLink = sourceLayer === 'macro' && targetLayer === 'macro'
      const baseDistance = labelLayoutActive
        ? (localAgentLink ? 118 : macroLink ? 220 : 168)
        : (localAgentLink ? 58 : macroLink ? 150 : 92)
      const edgeCount = d.pairTotal || 1
      return baseDistance + (edgeCount - 1) * (labelLayoutActive ? 30 : 12)
    }))
    .force('charge', d3.forceManyBody().strength(d => {
      if (labelLayoutActive) return d.layer === 'agent' ? -170 : -320
      if (d.layer === 'macro') return -190
      if (d.layer === 'subregion') return -125
      return -58
    }))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(d => {
      if (labelLayoutActive) return d.layer === 'agent' ? 46 : 62
      if (d.layer === 'macro') return 34
      if (d.layer === 'subregion') return 29
      return 22
    }))
    .force('x', d3.forceX(d => clusterTargetFor(d).x).strength(d => d.layer === 'macro' ? 0.3 : 0.16))
    .force('y', d3.forceY(d => clusterTargetFor(d).y).strength(d => d.layer === 'macro' ? 0.3 : 0.16))
  
  currentSimulation = simulation

  const g = svg.append('g')

  // 语义缩放：缩放只改变节点之间的投影距离，不把节点、文字和线宽当图片一起放大。
  const projectPoint = (x = 0, y = 0) => ({
    x: currentZoomTransform.applyX(Number.isFinite(x) ? x : 0),
    y: currentZoomTransform.applyY(Number.isFinite(y) ? y : 0),
  })
  const invertPoint = (x = 0, y = 0) => {
    const [gx, gy] = currentZoomTransform.invert([x, y])
    return { x: gx, y: gy }
  }

  // Links - 使用 path 支持曲线
  const linkGroup = g.append('g').attr('class', 'links')
  const pulseLinkGroup = g.append('g').attr('class', 'propagation-links')
  let pulseLink = pulseLinkGroup.selectAll('path')
  const renderedNodeMap = new Map(nodes.map(node => [node.id, node]))
  
  // 计算曲线路径
  const getLinkPath = (d) => {
    const source = projectPoint(d.source.x, d.source.y)
    const target = projectPoint(d.target.x, d.target.y)
    const sx = source.x, sy = source.y
    const tx = target.x, ty = target.y
    
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
    const source = projectPoint(d.source.x, d.source.y)
    const target = projectPoint(d.target.x, d.target.y)
    const sx = source.x, sy = source.y
    const tx = target.x, ty = target.y
    
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
    .attr('stroke-linecap', 'round')
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
      refreshNodeLabelVisibility({ interrupt: true })
    })

  const getRenderedLinkStyle = (edge, highlightState) => getLinkAnimationStyle(edge, {
    highlightActive: highlightState.highlightActive,
    highlighted: highlightState.isEdgeHighlighted(edge),
    focused: highlightState.isLinkFocused(edge),
    is3D: false,
    highlightColor: highlightState.edgeHighlightColor,
    neighborColor: edgeNeighborColor,
  })

  const buildPulseEdges = (sourceEdges = []) => aggregateParallelEdges2D(
    (Array.isArray(sourceEdges) ? sourceEdges : []).filter((edge) => {
      const status = normalizeAnimationStatus(edge?.attributes?.animation_status)
      return ['new', 'active'].includes(status)
        && renderedNodeMap.has(String(edge?.source_node_uuid || edge?.source || ''))
        && renderedNodeMap.has(String(edge?.target_node_uuid || edge?.target || ''))
    }),
  ).map((edge, index) => {
    const sourceId = String(edge?.source_node_uuid || edge?.source || '')
    const targetId = String(edge?.target_node_uuid || edge?.target || '')
    return {
      id: getEdgeStableId(edge, index),
      source: renderedNodeMap.get(sourceId),
      target: renderedNodeMap.get(targetId),
      type: edge.fact_type || edge.name || 'RELATED',
      name: edge.name || edge.fact_type || 'RELATED',
      curvature: 0,
      isSelfLoop: sourceId === targetId,
      pairTotal: 1,
      rawData: edge,
    }
  })

  const applyPulseLinkProgress = () => {
    pulseLink.each(function(d) {
      const path = d3.select(this)
      const style = getLinkAnimationStyle(d, { is3D: false })
      path
        .attr('stroke', style.color)
        .attr('stroke-width', Math.max(style.width, style.status === 'active' ? 3.4 : 2.6))
        .attr('opacity', Math.max(style.opacity, style.status === 'active' ? 0.92 : 0.72))

      const progress = getEntityAnimationProgress(d)
      if (progress >= 0.999) {
        path.attr('stroke-dasharray', style.dashArray || null).attr('stroke-dashoffset', null)
        return
      }
      let pathLength = 0
      try {
        pathLength = this.getTotalLength()
      } catch {
        pathLength = 0
      }
      if (!Number.isFinite(pathLength) || pathLength <= 0) return
      const visibleLength = Math.max(0.01, pathLength * progress)
      path
        .attr('stroke-dasharray', `${visibleLength} ${pathLength + 1}`)
        .attr('stroke-dashoffset', 0)
    })
  }

  const updatePulseLinks = (sourceEdges = []) => {
    pulseLink = pulseLinkGroup
      .selectAll('path')
      .data(buildPulseEdges(sourceEdges), d => d.id)
      .join(
        enter => enter.append('path')
          .attr('class', 'propagation-link')
          .attr('fill', 'none')
          .attr('stroke-linecap', 'round')
          .attr('pointer-events', 'none'),
        update => update,
        exit => exit.remove(),
      )
      .attr('d', d => getLinkPath(d))
    applyPulseLinkProgress()
  }

  // Draw current propagation from source to target. The progress mask is
  // applied after all highlight styling, so selecting/highlighting an edge
  // cannot accidentally reveal the unfinished remainder of its path.
  const applyLinkPathProgress = ({ currentOnly = false } = {}) => {
    const highlightState = getCurrentHighlightState()
    link.each(function(d) {
      const status = getEntityAnimationStatus(d)
      const isCurrentPropagation = status === 'new' || status === 'active'
      if (currentOnly && !isCurrentPropagation) return

      const path = d3.select(this)
      if (isCurrentPropagation) {
        const progress = getEntityAnimationProgress(d)
        if (progress >= 0.999) {
          path.attr('stroke-dasharray', null).attr('stroke-dashoffset', null)
          return
        }
        let pathLength = 0
        try {
          pathLength = this.getTotalLength()
        } catch {
          pathLength = 0
        }
        if (!Number.isFinite(pathLength) || pathLength <= 0) return
        const visibleLength = Math.max(0.01, pathLength * progress)
        path
          .attr('stroke-dasharray', `${visibleLength} ${pathLength + 1}`)
          .attr('stroke-dashoffset', 0)
        return
      }

      const style = getRenderedLinkStyle(d, highlightState)
      path
        .attr('stroke-dasharray', style.dashArray || null)
        .attr('stroke-dashoffset', null)
    })
  }

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
      refreshNodeLabelVisibility({ interrupt: true })
    })

  // Link labels
  const linkLabels = linkGroup.selectAll('text')
    .data(edges)
    .enter().append('text')
    .text(d => displayToken(d.name))
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
      refreshNodeLabelVisibility({ interrupt: true })
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
        const point = invertPoint(event.x, event.y)
        d.fx = d.x
        d.fy = d.y
        d._dragStartX = point.x
        d._dragStartY = point.y
        d._isDragging = false
      })
      .on('drag', (event, d) => {
        const point = invertPoint(event.x, event.y)
        // 检测是否真正开始拖拽（移动超过阈值）
        const dx = point.x - d._dragStartX
        const dy = point.y - d._dragStartY
        const distance = Math.sqrt(dx * dx + dy * dy)
        
        if (!d._isDragging && distance > 3) {
          // 首次检测到真正拖拽，才重启仿真
          d._isDragging = true
          simulation.alphaTarget(0.3).restart()
        }
        
        if (d._isDragging) {
          d.fx = point.x
          d.fy = point.y
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
      refreshNodeLabelVisibility({ interrupt: true })
      emit('node-select', buildNodePayload(selectedItem.value))
    })
    .on('mouseenter', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', '#333').attr('stroke-width', 3)
      }
    })
    .on('mouseleave', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        const highlightState = getCurrentHighlightState()
        const style = getNodeAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: Boolean(d.externallyHighlighted),
          is3D: false,
        })
        d3.select(event.target)
          .attr('stroke', style.strokeColor)
          .attr('stroke-width', style.strokeWidth)
      }
    })

  // Node Labels
  const nodeLabels = nodeGroup.selectAll('text')
    .data(nodes)
    .enter().append('text')
    .text(d => {
      const label = displayToken(d.name)
      return label.length > 8 ? label.substring(0, 8) + '…' : label
    })
    .attr('font-size', '11px')
    .attr('fill', '#333')
    .attr('font-weight', '500')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', 'system-ui, sans-serif')

  const getRenderedNodeLabelOpacity = (graphNode, highlightState) => {
    const highlighted = Boolean(graphNode.externallyHighlighted)
    const visible = shouldShowNodeLabel(graphNode, {
      highlightActive: highlightState.highlightActive,
      highlighted,
      zoomScale: currentZoomTransform.k,
    })
    if (!visible) return 0

    const style = getNodeAnimationStyle(graphNode, {
      highlightActive: highlightState.highlightActive,
      highlighted,
      is3D: false,
    })
    if (isSelectedGraphNode(graphNode)) return Math.max(style.labelOpacity, 0.96)
    if (
      currentZoomTransform.k < NODE_LABEL_LOD_ZOOM
      && isOverviewPriorityNode(graphNode)
    ) return Math.max(style.labelOpacity, 0.58)
    return style.labelOpacity
  }

  const refreshNodeLabelVisibility = ({ interrupt = false } = {}) => {
    const highlightState = getCurrentHighlightState()
    if (interrupt) nodeLabels.interrupt()
    nodeLabels.attr('opacity', d => getRenderedNodeLabelOpacity(d, highlightState))
  }

  const drawGraphFrame = () => {
    link.attr('d', d => getLinkPath(d))
    applyLinkPathProgress({ currentOnly: true })
    pulseLink.attr('d', d => getLinkPath(d))
    applyPulseLinkProgress()

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

    node
      .attr('cx', d => projectPoint(d.x, d.y).x)
      .attr('cy', d => projectPoint(d.x, d.y).y)

    nodeLabels
      .attr('x', d => projectPoint(d.x, d.y).x)
      .attr('y', d => projectPoint(d.x, d.y).y)
  }

  // Zoom: 不再 transform 整个 g，避免节点和文字被当成图片一起放大。
  // Clamp both interactive zoom and transforms restored from an older render.
  currentZoomTransform = clamp2DZoomTransform(currentZoomTransform, width, height)
  svg.attr('data-graph-zoom', currentZoomTransform.k.toFixed(4))
  const zoomBehavior = d3.zoom()
    .extent([[0, 0], [width, height]])
    .scaleExtent([MIN_2D_ZOOM, MAX_2D_ZOOM])
    .on('zoom', (event) => {
      currentZoomTransform = clamp2DZoomTransform(event.transform, width, height)
      svg.attr('data-graph-zoom', currentZoomTransform.k.toFixed(4))
      drawGraphFrame()
      refreshNodeLabelVisibility({ interrupt: true })
    })
  svg.call(zoomBehavior)
  svg.call(zoomBehavior.transform, currentZoomTransform)

  if (shouldAnimateFrameTransition) {
    const highlightState = getCurrentHighlightState()
    node
      .attr('r', d => {
        const style = getNodeAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: Boolean(d.externallyHighlighted),
          is3D: false,
        })
        return Math.max(4.2, style.radius * (style.status === 'active' ? 0.6 : 0.7))
      })
      .attr('opacity', d => {
        const style = getNodeAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: Boolean(d.externallyHighlighted),
          is3D: false,
        })
        return style.status === 'faded' ? 0.05 : Math.min(style.opacity, 0.3)
      })

    link
      .attr('opacity', d => {
        const style = getLinkAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: highlightState.isEdgeHighlighted(d),
          focused: highlightState.isLinkFocused(d),
          is3D: false,
          highlightColor: highlightState.edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        })
        return style.status === 'faded' ? 0.03 : Math.min(style.opacity, 0.12)
      })

    nodeLabels.attr('opacity', 0)
    linkLabelBg.attr('opacity', 0)
    linkLabels.attr('opacity', 0)
  }

  const applyBaseGraphState = ({ animate = shouldAnimateFrameTransition } = {}) => {
    const highlightState = getCurrentHighlightState()
    const animateNode = animate
      ? node.transition().duration(420).delay(d => getEntityDelayMs(d)).ease(d3.easeCubicOut)
      : node
    const animateNodeLabels = animate
      ? nodeLabels.transition().duration(420).delay(d => getEntityDelayMs(d)).ease(d3.easeCubicOut)
      : nodeLabels
    const animateLink = animate
      ? link.transition().duration(380).delay(d => getEntityDelayMs(d, 0.72)).ease(d3.easeCubicOut)
      : link
    const animateLinkLabelBg = animate
      ? linkLabelBg.transition().duration(380).delay(d => getEntityDelayMs(d, 0.72)).ease(d3.easeCubicOut)
      : linkLabelBg
    const animateLinkLabels = animate
      ? linkLabels.transition().duration(380).delay(d => getEntityDelayMs(d, 0.72)).ease(d3.easeCubicOut)
      : linkLabels

    animateNode
      .attr('r', d => getNodeAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: Boolean(d.externallyHighlighted),
        is3D: false,
      }).radius)
      .attr('fill', d => getNodeAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: Boolean(d.externallyHighlighted),
        is3D: false,
      }).color)
      .attr('opacity', d => getNodeAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: Boolean(d.externallyHighlighted),
        is3D: false,
      }).opacity)
      .attr('stroke', d => getNodeAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: Boolean(d.externallyHighlighted),
        is3D: false,
      }).strokeColor)
      .attr('stroke-width', d => getNodeAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: Boolean(d.externallyHighlighted),
        is3D: false,
      }).strokeWidth)

    animateNodeLabels
      .attr('opacity', d => getRenderedNodeLabelOpacity(d, highlightState))
      .attr('font-weight', d => getNodeAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: Boolean(d.externallyHighlighted),
        is3D: false,
      }).status === 'active' ? 700 : 500)

    animateLink
      .attr('stroke', d => getLinkAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: highlightState.isEdgeHighlighted(d),
        focused: highlightState.isLinkFocused(d),
        is3D: false,
        highlightColor: highlightState.edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).color)
      .attr('stroke-width', d => getLinkAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: highlightState.isEdgeHighlighted(d),
        focused: highlightState.isLinkFocused(d),
        is3D: false,
        highlightColor: highlightState.edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).width)
      .attr('opacity', d => getLinkAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: highlightState.isEdgeHighlighted(d),
        focused: highlightState.isLinkFocused(d),
        is3D: false,
        highlightColor: highlightState.edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).opacity)

    animateLinkLabelBg
      .attr('fill', d => {
        const style = getLinkAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: highlightState.isEdgeHighlighted(d),
          focused: highlightState.isLinkFocused(d),
          is3D: false,
          highlightColor: highlightState.edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        })
        if (style.status === 'active') return 'rgba(255,245,240,0.96)'
        if (style.status === 'new') return 'rgba(255,248,235,0.94)'
        return 'rgba(255,255,255,0.95)'
      })
      .attr('opacity', d => showEdgeLabels.value
        ? getLinkAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: highlightState.isEdgeHighlighted(d),
          focused: highlightState.isLinkFocused(d),
          is3D: false,
          highlightColor: highlightState.edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        }).labelOpacity
        : 0)

    animateLinkLabels
      .attr('fill', d => getLinkAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: highlightState.isEdgeHighlighted(d),
        focused: highlightState.isLinkFocused(d),
        is3D: false,
        highlightColor: highlightState.edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).labelColor)
      .attr('opacity', d => showEdgeLabels.value
        ? getLinkAnimationStyle(d, {
          highlightActive: highlightState.highlightActive,
          highlighted: highlightState.isEdgeHighlighted(d),
          focused: highlightState.isLinkFocused(d),
          is3D: false,
          highlightColor: highlightState.edgeHighlightColor,
          neighborColor: edgeNeighborColor,
        }).labelOpacity
        : 0)
      .attr('font-weight', d => getLinkAnimationStyle(d, {
        highlightActive: highlightState.highlightActive,
        highlighted: highlightState.isEdgeHighlighted(d),
        focused: highlightState.isLinkFocused(d),
        is3D: false,
        highlightColor: highlightState.edgeHighlightColor,
        neighborColor: edgeNeighborColor,
      }).status === 'active' ? 700 : 500)

    applyLinkPathProgress()
  }

  graph2DState = {
    nodes,
    edges,
    nodeMap: nodeLookup,
    node,
    nodeLabels,
    link,
    linkLabelBg,
    linkLabels,
    applyBaseGraphState,
    refreshNodeLabelVisibility,
    updatePulseLinks,
  }
  last2DStructureSignature = buildGraphStructureSignature(props.graphData)
  updatePulseLinks(edgesData)
  applyBaseGraphState()
  drawGraphFrame()

  const maxTicks = labelLayoutActive ? 220 : (oldNodeMap.size > 0 ? 70 : 140)
  let tickCount = 0

  simulation.on('tick', () => {
    tickCount += 1
    drawGraphFrame()

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
  selectedItem.value = reconcileVisibleGraphSelection(selectedItem.value, props.graphData)
  const nextSignature = buildGraphStructureSignature(props.graphData)
  if (graphMode.value === '2d' && graph2DState && nextSignature && nextSignature === last2DStructureSignature) {
    nextTick(scheduleRenderedGraphDataUpdate)
    return
  }
  nextTick(scheduleGraphRender)
})

watch(propagationEdgeSignature, () => {
  if (graphMode.value === '2d' && graph2DState) {
    nextTick(scheduleRenderedGraphDataUpdate)
  }
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
    if (graphMode.value === '2d' && graph2DState) {
      nextTick(scheduleRenderedGraphDataUpdate)
      return
    }
    nextTick(scheduleGraphRender)
  }
)

// 治毛球：切换密度档位时整图重渲染（边集合变了，需重建结构）
watch(edgeDensity, () => {
  nextTick(scheduleGraphRender)
})

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
  if (graphContainer.value) {
    containerResizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    containerResizeObserver.observe(graphContainer.value)
  }
  nextTick(scheduleGraphRender)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (containerResizeObserver) {
    containerResizeObserver.disconnect()
    containerResizeObserver = null
  }
  if (resizeTimer) {
    clearTimeout(resizeTimer)
    resizeTimer = null
  }
  if (renderFrame !== null) {
    cancelAnimationFrame(renderFrame)
    renderFrame = null
  }
  if (graph2DDataFrame !== null) {
    cancelAnimationFrame(graph2DDataFrame)
    graph2DDataFrame = null
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
  background: transparent;
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

/* 治毛球：密度档位按钮（标签更长，放开最小宽度） */
.density-switch .mode-btn {
  min-width: auto;
  padding: 0 10px;
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

.graph-3d-overlay {
  position: absolute;
  inset: 0;
  z-index: 8;
  display: grid;
  place-items: center;
  padding: 24px;
  pointer-events: none;
  background:
    radial-gradient(circle at 25% 18%, rgba(240, 138, 36, 0.1), transparent 28%),
    radial-gradient(circle at 78% 72%, rgba(0, 78, 137, 0.12), transparent 30%),
    linear-gradient(180deg, rgba(250, 250, 250, 0.18) 0%, rgba(250, 250, 250, 0.56) 100%);
  backdrop-filter: blur(2px);
}

.graph-3d-overlay-card {
  width: min(340px, 100%);
  padding: 20px 22px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 24px 56px rgba(15, 23, 42, 0.1);
  color: #10231d;
}

.graph-3d-overlay-title {
  margin-top: 14px;
  font-size: 14px;
  font-weight: 800;
}

.graph-3d-overlay-subtitle {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(16, 35, 29, 0.7);
}

.graph-3d-overlay.is-unsupported .graph-3d-overlay-card {
  background: rgba(255, 249, 245, 0.9);
}

.graph-3d-orbit {
  position: relative;
  width: 76px;
  height: 76px;
}

.orbit-ring,
.orbit-core {
  position: absolute;
  inset: 0;
  border-radius: 999px;
}

.orbit-ring {
  border: 1px solid rgba(31, 125, 93, 0.2);
  animation: orbitSpin 4.8s linear infinite;
}

.orbit-ring-a {
  inset: 0;
}

.orbit-ring-b {
  inset: 11px;
  border-color: rgba(240, 138, 36, 0.28);
  animation-direction: reverse;
  animation-duration: 3.8s;
}

.orbit-core {
  inset: 26px;
  background: radial-gradient(circle at 30% 30%, #f08a24 0%, #1f7d5d 100%);
  box-shadow: 0 0 0 12px rgba(31, 125, 93, 0.08);
  animation: orbitCorePulse 1.8s ease-in-out infinite;
}

.graph-3d-overlay-fade-enter-active,
.graph-3d-overlay-fade-leave-active {
  transition: opacity 0.24s ease;
}

.graph-3d-overlay-fade-enter-from,
.graph-3d-overlay-fade-leave-to {
  opacity: 0;
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

@keyframes orbitSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes orbitCorePulse {
  0%, 100% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.08); opacity: 1; }
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

/* M10 edge-layer legend */
.legend-edge-layers {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #ececec;
}

.legend-edge-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #555;
}

.legend-edge-line {
  width: 18px;
  height: 0;
  flex-shrink: 0;
}

.legend-edge-spatial {
  border-top: 1px solid #94a3b8;
  opacity: 0.7;
}

.legend-edge-causal {
  border-top: 2.5px solid #6d28d9;
}

.legend-edge-shown {
  width: 100%;
  font-size: 11px;
  font-weight: 600;
  color: #7B2D8E;
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
  border: 1px solid var(--k-color-border-strong);
  border-radius: 12px;
  background: transparent;
  color: var(--k-color-text-secondary);
  font-size: var(--k-text-caption);
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

/* M10 honesty badges (edge detail) */
.edge-honesty-badges {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 5px;
}

.edge-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.6;
  border: 1px solid transparent;
}

.edge-badge-spatial {
  background: #f1f5f9;
  color: #475569;
  border-color: #e2e8f0;
}

.edge-badge-causal {
  background: #ede9fe;
  color: #6d28d9;
  border-color: #ddd6fe;
}

.edge-badge-epistemic {
  background: #fff7ed;
  color: #b45309;
  border-color: #fed7aa;
}

.edge-badge-channel {
  background: #ecfeff;
  color: #0e7490;
  border-color: #cffafe;
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

/* Shared workflow chrome: graph categories may keep data colors; controls stay green. */
.graph-panel {
  container-type: inline-size;
}

.mode-btn.active {
  background: var(--k-color-brand-600);
  color: #fff;
}

.density-select {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 8px 0 10px;
  border: 1px solid var(--k-color-border-strong);
  border-radius: 999px;
  background: var(--k-color-surface);
  color: var(--k-color-text-muted);
  font-size: 11px;
  font-weight: 650;
}

.density-select select {
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--k-color-text);
  font: inherit;
}

.focus-badge,
.label-tag,
.episode-tag,
.edge-badge,
.legend-more {
  border: 1px solid var(--k-color-border-strong);
  background: transparent;
  color: var(--k-color-text-secondary);
}

.graph-3d-overlay {
  background:
    radial-gradient(circle at 25% 18%, rgba(31, 93, 69, 0.09), transparent 28%),
    linear-gradient(180deg, rgba(247, 249, 247, 0.2) 0%, rgba(247, 249, 247, 0.68) 100%);
}

.legend-title,
.legend-edge-shown {
  color: var(--k-color-brand-600);
}

.legend-edge-causal {
  border-top-color: var(--k-color-brand-600);
}

input:checked + .slider {
  background-color: var(--k-color-brand-600);
}

.graph-legend,
.edge-labels-toggle,
.detail-panel {
  border-color: var(--k-color-border);
  background: color-mix(in srgb, var(--k-color-surface) 96%, transparent);
  box-shadow: var(--k-shadow-raised);
}

.legend-more {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
}

@container (max-width: 760px) {
  .panel-title-wrap {
    display: none;
  }

  .panel-header {
    justify-content: flex-end;
    padding-inline: 12px;
  }

  .header-tools {
    gap: 6px;
  }

  .density-select > span,
  .tool-btn .btn-text {
    display: none;
  }
}
</style>
