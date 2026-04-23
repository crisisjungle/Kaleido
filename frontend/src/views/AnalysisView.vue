<template>
  <div class="main-view">
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
          <span class="step-num">Step 4/4</span>
          <span class="step-name">结果分析</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <main class="content-area">
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="4"
          :isSimulating="false"
          :enableAnalysisActions="true"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
          @node-select="handleNodeSelect"
          @node-action="handleNodeAction"
        />
      </div>

      <div class="panel-wrapper right" :style="rightPanelStyle">
        <div class="analysis-panel">
          <div v-if="overviewLoading" class="analysis-state loading">
            <div class="loading-spinner"></div>
            <p>结果分析准备中...</p>
          </div>

          <div v-else-if="overviewError" class="analysis-state error">
            <div class="state-icon">!</div>
            <p>{{ overviewError }}</p>
          </div>

          <template v-else-if="overview">
            <section class="analysis-hero">
              <div class="hero-main">
                <div class="hero-kicker">Result Analysis</div>
                <h1 class="hero-title">{{ overview.report_title || 'Kaleido 结果分析' }}</h1>
                <p class="hero-summary">
                  {{ overview.report_summary || '基于多轮区域状态、反馈链、角色透镜与节点探索的统一结果输出。' }}
                </p>
              </div>
              <div class="hero-metrics">
                <div class="hero-metric">
                  <span class="metric-label">默认轮次</span>
                  <strong>{{ overview.default_round || 0 }}</strong>
                </div>
                <div class="hero-metric">
                  <span class="metric-label">Agents</span>
                  <strong>{{ overview.node_stats?.agent_count || 0 }}</strong>
                </div>
                <div class="hero-metric">
                  <span class="metric-label">区域</span>
                  <strong>{{ overview.node_stats?.region_count || 0 }}</strong>
                </div>
                <div class="hero-metric">
                  <span class="metric-label">子区域</span>
                  <strong>{{ overview.node_stats?.subregion_count || 0 }}</strong>
                </div>
                <div class="hero-metric">
                  <span class="metric-label">风险对象</span>
                  <strong>{{ overview.node_stats?.risk_object_count || 0 }}</strong>
                </div>
                <div class="hero-metric">
                  <span class="metric-label">Emergent</span>
                  <strong>{{ overview.node_stats?.dynamic_edge_count || 0 }}</strong>
                </div>
              </div>
            </section>

            <section class="tab-bar">
              <button
                v-for="tab in tabs"
                :key="tab.id"
                class="tab-btn"
                :class="{ active: activeTab === tab.id }"
                @click="selectTab(tab.id)"
              >
                {{ tab.label }}
              </button>
            </section>

            <section class="tab-content">
              <div v-if="activeTab !== 'node-explore' && activeTab !== 'report' && tabLoading[activeTab]" class="analysis-state loading compact">
                <div class="loading-spinner"></div>
                <p>正在加载 {{ activeTabLabel }}...</p>
              </div>

              <div v-else-if="activeTab !== 'node-explore' && activeTab !== 'report' && tabErrors[activeTab]" class="analysis-state error compact">
                <div class="state-icon">!</div>
                <p>{{ tabErrors[activeTab] }}</p>
              </div>

              <template v-else-if="activeTab === 'regions'">
                <section class="control-bar" v-if="regionsTab">
                  <div class="control-group">
                    <span class="control-label">指标</span>
                    <select v-model="selectedMetric" class="control-select">
                      <option v-for="metric in regionsTab.metric_options || []" :key="metric.key" :value="metric.key">
                        {{ metric.label }}
                      </option>
                    </select>
                  </div>
                  <div class="control-group playback-group">
                    <button class="mini-btn" @click="stepRound(-1)">上一轮</button>
                    <button class="mini-btn primary" @click="togglePlayback">
                      {{ isPlaying ? '暂停' : '播放' }}
                    </button>
                    <button class="mini-btn" @click="stepRound(1)">下一轮</button>
                  </div>
                  <div class="control-group slider-group">
                    <span class="control-label">轮次 {{ selectedRound }}</span>
                    <input
                      v-if="regionsRounds.length > 0"
                      v-model.number="selectedRound"
                      class="round-slider"
                      type="range"
                      :min="regionsRounds[0]?.round || 1"
                      :max="regionsRounds[regionsRounds.length - 1]?.round || 1"
                      step="1"
                    />
                  </div>
                </section>

                <section v-if="currentRoundSnapshot" class="region-layout">
                  <div class="metric-highlight">
                    <div class="metric-highlight-head">
                      <span class="metric-highlight-title">区域态势</span>
                      <span class="metric-highlight-meta">当前指标：{{ currentMetricLabel }}</span>
                    </div>
                    <div class="metric-highlight-sub">
                      当前展示第 {{ selectedRound }} 轮的区域与子区域状态，数值越高表示该指标越强。
                    </div>
                  </div>

                  <div class="region-section">
                    <div class="section-header">
                      <h3>宏观区域</h3>
                      <span>{{ currentRoundSnapshot.regions?.length || 0 }} 个</span>
                    </div>
                    <div class="card-grid">
                      <article v-for="region in currentRoundSnapshot.regions || []" :key="region.region_id || region.name" class="metric-card">
                        <div class="metric-card-head">
                          <div>
                            <h4>{{ region.name }}</h4>
                            <p>{{ region.region_type || 'region' }}</p>
                          </div>
                          <span class="metric-pill">{{ formatMetricValue(region[selectedMetric]) }}</span>
                        </div>
                        <div class="metric-bar-track">
                          <div class="metric-bar-fill" :style="{ width: metricWidth(region[selectedMetric]) }"></div>
                        </div>
                        <div class="metric-card-stats">
                          <span>暴露 {{ formatMetricValue(region.exposure_score) }}</span>
                          <span>扩散 {{ formatMetricValue(region.spread_pressure) }}</span>
                          <span>脆弱性 {{ formatMetricValue(region.vulnerability_score) }}</span>
                        </div>
                      </article>
                    </div>
                  </div>

                  <div class="region-section">
                    <div class="section-header">
                      <h3>子区域</h3>
                      <span>{{ currentRoundSnapshot.subregions?.length || 0 }} 个</span>
                    </div>
                    <div class="card-grid dense">
                      <article v-for="subregion in currentRoundSnapshot.subregions || []" :key="subregion.region_id || subregion.name" class="metric-card compact">
                        <div class="metric-card-head">
                          <div>
                            <h4>{{ subregion.name }}</h4>
                            <p>{{ subregion.parent_region_id || subregion.region_type || 'subregion' }}</p>
                          </div>
                          <span class="metric-pill">{{ formatMetricValue(subregion[selectedMetric]) }}</span>
                        </div>
                        <div class="metric-bar-track">
                          <div class="metric-bar-fill" :style="{ width: metricWidth(subregion[selectedMetric]) }"></div>
                        </div>
                      </article>
                    </div>
                  </div>
                </section>
              </template>

              <template v-else-if="activeTab === 'feedback'">
                <section class="feedback-header" v-if="feedbackTab">
                  <div class="feedback-chain-template">
                    <span v-for="(stage, idx) in feedbackTab.chain_template || []" :key="stage" class="chain-stage">
                      {{ stage }}<span v-if="idx < (feedbackTab.chain_template || []).length - 1" class="chain-arrow">→</span>
                    </span>
                  </div>
                </section>
                <section class="feedback-grid" v-if="feedbackTab">
                  <article v-for="item in feedbackTab.items || []" :key="item.id" class="feedback-card">
                    <div class="feedback-card-head">
                      <div>
                        <h4>{{ item.region_name || item.region_id || '未命名节点' }}</h4>
                        <p>Round {{ item.round || feedbackTab.current_round }}</p>
                      </div>
                      <span class="source-chip">{{ item.source_type }}</span>
                    </div>
                    <div class="feedback-loop">{{ item.loop }}</div>
                    <div class="delta-grid">
                      <span v-for="(value, key) in item.delta || {}" :key="key" class="delta-chip">
                        {{ feedbackDeltaLabel(key) }} {{ formatDelta(value) }}
                      </span>
                    </div>
                    <div class="feedback-source">{{ item.source }}</div>
                  </article>
                </section>
                <section v-if="feedbackTab?.ecological_impacts?.length" class="secondary-section">
                  <div class="section-header">
                    <h3>生态影响</h3>
                    <span>{{ feedbackTab.ecological_impacts.length }} 条</span>
                  </div>
                  <div class="secondary-list">
                    <article v-for="item in feedbackTab.ecological_impacts" :key="item.id" class="secondary-card">
                      <strong>{{ item.region_name }}</strong>
                      <p>{{ item.note }}</p>
                    </article>
                  </div>
                </section>
              </template>

              <template v-else-if="activeTab === 'roles'">
                <section class="role-grid" v-if="rolesTab">
                  <article v-for="group in rolesTab.groups || []" :key="group.group_id" class="role-card">
                    <div class="role-card-head">
                      <div>
                        <h3>{{ group.title }}</h3>
                        <p>{{ group.description }}</p>
                      </div>
                      <span class="metric-pill">{{ group.node_count }} 个节点</span>
                    </div>
                    <div class="role-metrics">
                      <div v-for="metric in group.focus_metrics || []" :key="metric.key" class="role-metric-item">
                        <span>{{ metric.label }}</span>
                        <strong>{{ formatMetricValue(group.metric_averages?.[metric.key]) }}</strong>
                      </div>
                    </div>
                    <div class="role-subsection">
                      <span class="subsection-title">代表节点</span>
                      <div class="chip-wrap">
                        <span v-for="node in group.sample_nodes || []" :key="`${group.group_id}-${node.agent_id || node.name}`" class="data-chip">
                          {{ node.name }}
                        </span>
                      </div>
                    </div>
                    <div class="role-subsection" v-if="group.dominant_regions?.length">
                      <span class="subsection-title">主受影响区域</span>
                      <div class="region-score-list">
                        <div v-for="region in group.dominant_regions" :key="`${group.group_id}-${region.region_name}`" class="region-score-item">
                          <span>{{ region.region_name }}</span>
                          <strong>{{ formatMetricValue(region.score) }}</strong>
                        </div>
                      </div>
                    </div>
                  </article>
                </section>
              </template>

              <template v-else-if="activeTab === 'narrative'">
                <section class="narrative-list" v-if="narrativeTab">
                  <article v-for="round in narrativeTab.rounds || []" :key="round.round" class="narrative-card">
                    <div class="narrative-head">
                      <div>
                        <h3>Round {{ round.round }}</h3>
                        <p>{{ formatTimestamp(round.timestamp) }}</p>
                      </div>
                      <span class="metric-pill">
                        {{ round.top_region?.name || '未识别区域' }}
                      </span>
                    </div>
                    <div class="narrative-columns">
                      <div class="narrative-block">
                        <span class="block-label">本轮最关键变化</span>
                        <p>{{ round.headline }}</p>
                      </div>
                      <div class="narrative-block">
                        <span class="block-label">主要传播/放大器</span>
                        <p>{{ round.amplifier }}</p>
                      </div>
                      <div class="narrative-block">
                        <span class="block-label">最大不确定性</span>
                        <p>{{ round.uncertainty }}</p>
                      </div>
                    </div>
                  </article>
                </section>
              </template>

              <template v-else-if="activeTab === 'node-explore'">
                <section v-if="!selectedNode" class="analysis-state empty-node">
                  <div class="state-icon">◎</div>
                  <p>点击左侧图谱中的任意节点，然后选择“查看详情”、“开始交流”或“深度探索”。</p>
                </section>

                <template v-else>
                  <section class="node-hero">
                    <div class="node-hero-main">
                      <div class="hero-kicker">Node Exploration</div>
                      <h2>{{ selectedNode.name }}</h2>
                      <div class="chip-wrap">
                        <span v-for="label in selectedNode.labels || []" :key="label" class="data-chip">{{ label }}</span>
                      </div>
                    </div>
                    <div class="node-hero-actions">
                      <button class="mini-btn" @click="refreshNodeContext">刷新上下文</button>
                      <button class="mini-btn primary" :disabled="nodeExploreLoading" @click="runNodeExplore">
                        {{ nodeExploreLoading ? '分析中...' : '深度探索' }}
                      </button>
                    </div>
                  </section>

                  <div v-if="nodeContextLoading" class="analysis-state loading compact">
                    <div class="loading-spinner"></div>
                    <p>正在加载节点上下文...</p>
                  </div>

                  <div v-else-if="nodeContextError" class="analysis-state error compact">
                    <div class="state-icon">!</div>
                    <p>{{ nodeContextError }}</p>
                  </div>

                  <template v-else-if="nodeContext">
                    <section class="node-context-grid">
                      <article class="context-card">
                        <div class="section-header">
                          <h3>上下文摘要</h3>
                          <span>{{ nodeContext.supported_modes?.exploration_mode }}</span>
                        </div>
                        <div class="context-list">
                          <div class="context-item">
                            <span>节点类型</span>
                            <strong>{{ nodeContext.node_kind }}</strong>
                          </div>
                          <div class="context-item">
                            <span>轮次范围</span>
                            <strong>{{ formatRoundRange(nodeContext.round_range) }}</strong>
                          </div>
                          <div class="context-item">
                            <span>状态记录</span>
                            <strong>{{ nodeContext.time_series?.length || 0 }} 条</strong>
                          </div>
                          <div class="context-item">
                            <span>反馈事件</span>
                            <strong>{{ nodeContext.related_feedback?.length || 0 }} 条</strong>
                          </div>
                          <div class="context-item">
                            <span>一跳邻居</span>
                            <strong>{{ nodeContext.subgraph?.direct_neighbor_count || 0 }}</strong>
                          </div>
                          <div class="context-item">
                            <span>二跳扩展</span>
                            <strong>{{ nodeContext.subgraph?.second_hop_count || 0 }}</strong>
                          </div>
                        </div>
                        <div v-if="nodeContext.missing_data?.length" class="warning-list">
                          <span v-for="item in nodeContext.missing_data" :key="item" class="warning-chip">{{ item }}</span>
                        </div>
                      </article>

                      <article class="context-card">
                        <div class="section-header">
                          <h3>关系子图预览</h3>
                          <span>{{ nodeContext.subgraph?.edges?.length || 0 }} 条边</span>
                        </div>
                        <div class="subgraph-list">
                          <div v-for="edge in (nodeContext.subgraph?.edges || []).slice(0, 8)" :key="edge.uuid || `${edge.source_node_uuid}-${edge.target_node_uuid}`" class="subgraph-item">
                            <strong>{{ edge.source_node_name }}</strong>
                            <span>{{ edge.name }}</span>
                            <strong>{{ edge.target_node_name }}</strong>
                          </div>
                        </div>
                      </article>
                    </section>

                    <section v-if="nodeExploreError" class="analysis-state error compact">
                      <div class="state-icon">!</div>
                      <p>{{ nodeExploreError }}</p>
                    </section>

                    <section v-if="nodeExploreResult" class="explore-sections">
                      <article v-for="section in nodeExploreResult.sections || []" :key="section.id" class="explore-card">
                        <div class="section-header">
                          <h3>{{ section.title }}</h3>
                          <span>{{ selectedNode.name }}</span>
                        </div>
                        <div class="explore-items">
                          <div v-for="item in section.items || []" :key="`${section.id}-${item.label}-${item.content}`" class="explore-item">
                            <div class="explore-item-head">
                              <strong>{{ item.label }}</strong>
                              <span class="source-chip">{{ item.source_type }}</span>
                            </div>
                            <p>{{ item.content }}</p>
                          </div>
                        </div>
                      </article>
                    </section>

                    <section class="chat-box">
                      <div class="section-header">
                        <h3>围绕该节点继续追问</h3>
                        <span>上下文锁定为 {{ selectedNode.name }}</span>
                      </div>
                      <div class="chat-history">
                        <div v-if="nodeChatHistory.length === 0" class="chat-empty">
                          先点击“深度探索”，或直接围绕该节点提问。
                        </div>
                        <div
                          v-for="(message, idx) in nodeChatHistory"
                          :key="`${message.role}-${idx}`"
                          class="chat-message"
                          :class="message.role"
                        >
                          <span class="chat-role">{{ message.role === 'user' ? '你' : '系统' }}</span>
                          <p>{{ message.content }}</p>
                        </div>
                      </div>
                      <div class="chat-input-row">
                        <textarea
                          v-model="nodeChatInput"
                          class="chat-input"
                          rows="3"
                          placeholder="例如：解释这个节点为什么在最后两轮发生变化？"
                          @keydown.enter.exact.prevent="sendNodeChat"
                        ></textarea>
                        <button class="mini-btn primary send-btn" :disabled="nodeChatLoading || !nodeChatInput.trim()" @click="sendNodeChat">
                          {{ nodeChatLoading ? '发送中...' : '发送' }}
                        </button>
                      </div>
                    </section>
                  </template>
                </template>
              </template>

              <template v-else-if="activeTab === 'report'">
                <div class="report-tab-shell">
                  <Step4Report
                    v-if="reportId && simulationId"
                    :reportId="reportId"
                    :simulationId="simulationId"
                    :systemLogs="systemLogs"
                    :showNextStep="false"
                    @add-log="addLog"
                    @update-status="updateStatus"
                  />
                </div>
              </template>
            </section>
          </template>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import GraphPanel from '../components/GraphPanel.vue'
import Step4Report from '../components/Step4Report.vue'
import {
  chatWithReportNode,
  exploreReportNode,
  getReportAnalysisGraph,
  getReportAnalysisOverview,
  getReportAnalysisTab,
  getReportNodeContext,
} from '../api/report'

const route = useRoute()
const router = useRouter()

const tabs = [
  { id: 'regions', label: '区域态势' },
  { id: 'feedback', label: '反馈环' },
  { id: 'roles', label: '角色透镜' },
  { id: 'narrative', label: '轮次叙事' },
  { id: 'node-explore', label: '节点探索' },
  { id: 'report', label: '报告' },
]

const viewMode = ref('split')
const reportId = ref(route.params.reportId)
const simulationId = ref('')
const graphId = ref('')
const graphData = ref(null)
const graphLoading = ref(false)
const systemLogs = ref([])
const currentStatus = ref('processing')

const overview = ref(null)
const overviewLoading = ref(false)
const overviewError = ref('')

const activeTab = ref('regions')
const loadedTabs = ref(new Set())
const tabData = ref({
  regions: null,
  feedback: null,
  roles: null,
  narrative: null,
  report: null,
})
const tabLoading = ref({
  regions: false,
  feedback: false,
  roles: false,
  narrative: false,
  report: false,
})
const tabErrors = ref({
  regions: '',
  feedback: '',
  roles: '',
  narrative: '',
  report: '',
})

const selectedMetric = ref('vulnerability_score')
const selectedRound = ref(1)
const isPlaying = ref(false)
let playbackTimer = null

const selectedNode = ref(null)
const nodeContext = ref(null)
const nodeContextLoading = ref(false)
const nodeContextError = ref('')
const nodeExploreResult = ref(null)
const nodeExploreLoading = ref(false)
const nodeExploreError = ref('')
const nodeChatHistory = ref([])
const nodeChatInput = ref('')
const nodeChatLoading = ref(false)
let overviewPoller = null

const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '46%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '54%', opacity: 1, transform: 'translateX(0)' }
})

const statusClass = computed(() => currentStatus.value)

const statusText = computed(() => {
  if (currentStatus.value === 'error') return 'Error'
  if (currentStatus.value === 'completed') return 'Completed'
  if (currentStatus.value === 'ready') return 'Ready'
  return 'Generating'
})

const activeTabLabel = computed(() => tabs.find(tab => tab.id === activeTab.value)?.label || '分析')
const regionsTab = computed(() => tabData.value.regions)
const feedbackTab = computed(() => tabData.value.feedback)
const rolesTab = computed(() => tabData.value.roles)
const narrativeTab = computed(() => tabData.value.narrative)
const regionsRounds = computed(() => regionsTab.value?.rounds || [])
const currentRoundSnapshot = computed(() => {
  if (!regionsRounds.value.length) return null
  return regionsRounds.value.find(item => Number(item.round) === Number(selectedRound.value)) || regionsRounds.value[regionsRounds.value.length - 1]
})
const currentMetricLabel = computed(() => {
  const options = regionsTab.value?.metric_options || []
  return options.find(item => item.key === selectedMetric.value)?.label || selectedMetric.value
})

const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 200) systemLogs.value.shift()
}

const updateStatus = (status) => {
  currentStatus.value = status
}

const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const metricWidth = (value) => {
  const safe = Number(value || 0)
  return `${Math.max(0, Math.min(100, safe))}%`
}

const formatMetricValue = (value) => {
  if (value === null || value === undefined || value === '') return 'NA'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(1) : value
}

const formatDelta = (value) => {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return value
  return `${num > 0 ? '+' : ''}${num.toFixed(1)}`
}

const formatTimestamp = (value) => {
  if (!value) return '无时间戳'
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

const formatRoundRange = (value) => {
  if (!Array.isArray(value) || value.length < 2) return '全范围'
  return `${value[0]} - ${value[1]}`
}

const feedbackDeltaLabel = (key) => {
  const map = {
    panic_level: '恐慌',
    public_trust: '信任',
    service_capacity: '服务',
    livelihood_stability: '生计',
    economic_stress: '经济',
    ecosystem_integrity: '生态',
    spread_pressure: '扩散',
    vulnerability_score: '脆弱性',
  }
  return map[key] || key
}

const resolveAnalysisStatus = (data) => {
  if (data?.analysis_ready && data?.report_status !== 'completed') return 'ready'
  const statusMap = {
    pending: 'processing',
    planning: 'processing',
    generating: 'processing',
    completed: 'completed',
    failed: 'error',
  }
  return statusMap[data?.report_status] || 'ready'
}

const normalizeTab = (value) => {
  const valid = new Set(tabs.map(tab => tab.id))
  return valid.has(value) ? value : 'regions'
}

const refreshGraph = async () => {
  if (!reportId.value) return
  graphLoading.value = true
  try {
    const res = await getReportAnalysisGraph(reportId.value)
    if (res.success && res.data) {
      graphData.value = res.data
      addLog(`结果图谱加载成功：${res.data.node_count || 0} 节点 / ${res.data.edge_count || 0} 条边`)
    } else {
      graphData.value = null
      addLog(`结果图谱加载失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    graphData.value = null
    addLog(`结果图谱加载异常: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const stopOverviewPolling = () => {
  if (overviewPoller) {
    window.clearInterval(overviewPoller)
    overviewPoller = null
  }
}

const syncOverviewStatus = async () => {
  if (!reportId.value) return
  try {
    const res = await getReportAnalysisOverview(reportId.value)
    if (!res.success || !res.data) return
    overview.value = {
      ...(overview.value || {}),
      ...res.data,
    }
    currentStatus.value = resolveAnalysisStatus(res.data)
    if (res.data.report_status === 'completed' || res.data.report_status === 'failed') {
      stopOverviewPolling()
    }
  } catch (err) {
    addLog(`结果分析状态轮询失败: ${err.message}`)
    stopOverviewPolling()
  }
}

const startOverviewPolling = () => {
  stopOverviewPolling()
  if (!['pending', 'planning', 'generating'].includes(overview.value?.report_status)) return
  overviewPoller = window.setInterval(syncOverviewStatus, 6000)
}

const loadOverview = async () => {
  if (!reportId.value) return
  overviewLoading.value = true
  overviewError.value = ''

  try {
    const res = await getReportAnalysisOverview(reportId.value)
    if (!res.success || !res.data) {
      throw new Error(res.error || '无法获取结果分析总览')
    }

    overview.value = res.data
    simulationId.value = res.data.simulation_id || ''
    graphId.value = res.data.graph_id || ''

    currentStatus.value = resolveAnalysisStatus(res.data)
    selectedRound.value = res.data.default_round || 1

    await refreshGraph()

    const nextTab = normalizeTab(route.query.tab)
    activeTab.value = nextTab
    if (nextTab !== 'node-explore') {
      await ensureTabLoaded(nextTab)
    }
    startOverviewPolling()
  } catch (err) {
    overviewError.value = err.message || '结果分析加载失败'
    currentStatus.value = 'error'
    stopOverviewPolling()
  } finally {
    overviewLoading.value = false
  }
}

const ensureTabLoaded = async (tabId) => {
  if (!['regions', 'feedback', 'roles', 'narrative', 'report'].includes(tabId)) return
  if (loadedTabs.value.has(tabId)) return
  tabLoading.value[tabId] = true
  tabErrors.value[tabId] = ''
  try {
    const res = await getReportAnalysisTab(reportId.value, tabId)
    if (!res.success || !res.data) {
      throw new Error(res.error || `无法加载 ${tabId}`)
    }
    tabData.value[tabId] = res.data
    loadedTabs.value.add(tabId)

    if (tabId === 'regions') {
      selectedMetric.value = res.data.default_metric || 'vulnerability_score'
      selectedRound.value = res.data.current_round || selectedRound.value
    }
  } catch (err) {
    tabErrors.value[tabId] = err.message || `加载 ${tabId} 失败`
  } finally {
    tabLoading.value[tabId] = false
  }
}

const selectTab = async (tabId) => {
  activeTab.value = tabId
  await router.replace({ query: { ...route.query, tab: tabId } })
  stopPlayback()
  if (tabId !== 'node-explore') {
    await ensureTabLoaded(tabId)
  }
}

const stopPlayback = () => {
  if (playbackTimer) {
    window.clearInterval(playbackTimer)
    playbackTimer = null
  }
  isPlaying.value = false
}

const stepRound = (direction) => {
  if (!regionsRounds.value.length) return
  const roundValues = regionsRounds.value.map(item => Number(item.round))
  const currentIndex = roundValues.findIndex(item => item === Number(selectedRound.value))
  const nextIndex = currentIndex < 0 ? 0 : Math.max(0, Math.min(roundValues.length - 1, currentIndex + direction))
  selectedRound.value = roundValues[nextIndex]
}

const togglePlayback = () => {
  if (isPlaying.value) {
    stopPlayback()
    return
  }
  if (!regionsRounds.value.length) return
  isPlaying.value = true
  playbackTimer = window.setInterval(() => {
    const roundValues = regionsRounds.value.map(item => Number(item.round))
    const currentIndex = roundValues.findIndex(item => item === Number(selectedRound.value))
    const nextIndex = currentIndex >= roundValues.length - 1 ? 0 : currentIndex + 1
    selectedRound.value = roundValues[nextIndex]
  }, 1600)
}

const resetNodeConversation = () => {
  nodeExploreResult.value = null
  nodeExploreError.value = ''
  nodeChatHistory.value = []
  nodeChatInput.value = ''
}

const fetchNodeContext = async (node, { reset = false } = {}) => {
  if (!node?.uuid || !reportId.value) return
  if (reset) resetNodeConversation()
  nodeContextLoading.value = true
  nodeContextError.value = ''
  try {
    const res = await getReportNodeContext(reportId.value, { node_id: node.uuid })
    if (!res.success || !res.data) {
      throw new Error(res.error || '无法获取节点上下文')
    }
    nodeContext.value = res.data
  } catch (err) {
    nodeContext.value = null
    nodeContextError.value = err.message || '节点上下文加载失败'
  } finally {
    nodeContextLoading.value = false
  }
}

const handleNodeSelect = async (node) => {
  const changed = node?.uuid !== selectedNode.value?.uuid
  selectedNode.value = node
  await fetchNodeContext(node, { reset: changed })
}

const handleNodeAction = async (payload) => {
  if (!payload?.node) return
  const changed = payload.node.uuid !== selectedNode.value?.uuid
  selectedNode.value = payload.node
  await selectTab('node-explore')
  await fetchNodeContext(payload.node, { reset: changed })
  if (payload.action === 'explore') {
    await runNodeExplore()
  }
}

const refreshNodeContext = async () => {
  if (!selectedNode.value) return
  await fetchNodeContext(selectedNode.value, { reset: false })
}

const runNodeExplore = async () => {
  if (!selectedNode.value?.uuid || !reportId.value) return
  nodeExploreLoading.value = true
  nodeExploreError.value = ''
  try {
    const res = await exploreReportNode(reportId.value, { node_id: selectedNode.value.uuid })
    if (!res.success || !res.data) {
      throw new Error(res.error || '节点深度探索失败')
    }
    nodeExploreResult.value = res.data
  } catch (err) {
    nodeExploreError.value = err.message || '节点深度探索失败'
  } finally {
    nodeExploreLoading.value = false
  }
}

const sendNodeChat = async () => {
  const message = nodeChatInput.value.trim()
  if (!message || !selectedNode.value?.uuid || !reportId.value) return

  nodeChatHistory.value.push({ role: 'user', content: message })
  nodeChatInput.value = ''
  nodeChatLoading.value = true
  try {
    const res = await chatWithReportNode(reportId.value, {
      node_id: selectedNode.value.uuid,
      message,
      chat_history: nodeChatHistory.value,
    })
    if (!res.success || !res.data) {
      throw new Error(res.error || '节点追问失败')
    }
    nodeChatHistory.value.push({
      role: 'assistant',
      content: res.data.response,
    })
  } catch (err) {
    nodeChatHistory.value.push({
      role: 'assistant',
      content: `请求失败：${err.message || '未知错误'}`,
    })
  } finally {
    nodeChatLoading.value = false
  }
}

watch(
  () => route.params.reportId,
  async (newId) => {
    if (!newId) return
    reportId.value = newId
    loadedTabs.value = new Set()
    tabData.value = { regions: null, feedback: null, roles: null, narrative: null, report: null }
    await loadOverview()
  },
  { immediate: true }
)

watch(
  () => route.query.tab,
  async (tab) => {
    const normalized = normalizeTab(tab)
    if (normalized !== activeTab.value) {
      activeTab.value = normalized
      if (normalized !== 'node-explore') {
        await ensureTabLoaded(normalized)
      }
    }
  }
)

onMounted(() => {
  addLog('AnalysisView 初始化')
})

onBeforeUnmount(() => {
  stopPlayback()
  stopOverviewPolling()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
}

.app-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid rgba(16, 35, 29, 0.08);
  background: rgba(244, 246, 241, 0.92);
  backdrop-filter: blur(14px);
}

.view-switcher {
  display: inline-flex;
  gap: 8px;
  padding: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(16, 35, 29, 0.08);
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 13px;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s ease;
}

.switch-btn.active {
  background: #ffffff;
  color: #0f172a;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.workflow-step {
  display: flex;
  flex-direction: column;
  gap: 2px;
  text-align: right;
}

.step-num {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748b;
}

.step-name {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.step-divider {
  width: 1px;
  height: 28px;
  background: rgba(148, 163, 184, 0.4);
  margin: 0 14px;
}

.header-right {
  display: flex;
  align-items: center;
}

.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.status-indicator .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.status-indicator.processing {
  background: rgba(37, 99, 235, 0.12);
  color: #2563eb;
}

.status-indicator.completed,
.status-indicator.ready {
  background: rgba(5, 150, 105, 0.12);
  color: #059669;
}

.status-indicator.error {
  background: rgba(220, 38, 38, 0.12);
  color: #dc2626;
}

.content-area {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  transition: width 0.28s ease, opacity 0.28s ease, transform 0.28s ease;
  overflow: hidden;
}

.analysis-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
  gap: 16px;
  overflow: hidden;
}

.analysis-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px;
  border-radius: 24px;
  background: linear-gradient(135deg, #102a43 0%, #1f5f5b 56%, #d8b04c 100%);
  color: #f8fafc;
}

.hero-main {
  min-width: 0;
}

.hero-kicker {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: rgba(248, 250, 252, 0.72);
}

.hero-title {
  margin: 6px 0 10px;
  font-size: 32px;
  line-height: 1.1;
}

.hero-summary {
  margin: 0;
  max-width: 760px;
  line-height: 1.6;
  color: rgba(248, 250, 252, 0.88);
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 12px;
  min-width: 280px;
}

.hero-metric {
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-label {
  font-size: 12px;
  color: rgba(248, 250, 252, 0.7);
}

.hero-metric strong {
  font-size: 24px;
}

.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tab-btn {
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: #ffffff;
  padding: 10px 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn.active {
  background: #0f172a;
  color: #f8fafc;
  border-color: #0f172a;
}

.tab-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.analysis-state {
  min-height: 240px;
  border-radius: 24px;
  border: 1px dashed rgba(148, 163, 184, 0.36);
  background: #ffffff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: #64748b;
}

.analysis-state.compact {
  min-height: 160px;
}

.analysis-state.error {
  color: #b91c1c;
}

.state-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 24px;
  background: rgba(148, 163, 184, 0.12);
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid rgba(148, 163, 184, 0.18);
  border-top-color: #0f766e;
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.control-bar,
.metric-highlight,
.feedback-header,
.node-hero,
.context-card,
.explore-card,
.chat-box,
.secondary-section,
.role-card,
.narrative-card,
.report-tab-shell {
  border-radius: 22px;
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}

.control-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 16px 18px;
  align-items: center;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.control-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 700;
}

.control-select,
.chat-input {
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 12px;
  padding: 10px 12px;
  background: #ffffff;
  font: inherit;
}

.round-slider {
  width: 220px;
}

.mini-btn {
  border: 1px solid rgba(148, 163, 184, 0.24);
  background: #ffffff;
  border-radius: 12px;
  padding: 9px 14px;
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  cursor: pointer;
}

.mini-btn.primary {
  background: #0f766e;
  color: #ffffff;
  border-color: #0f766e;
}

.mini-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.region-layout,
.feedback-grid,
.role-grid,
.narrative-list,
.node-context-grid,
.explore-sections {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.metric-highlight {
  padding: 18px 20px;
}

.metric-highlight-head,
.section-header,
.feedback-card-head,
.role-card-head,
.narrative-head,
.node-hero,
.explore-item-head,
.hero-main,
.chat-input-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.metric-highlight-title,
.section-header h3,
.role-card-head h3,
.narrative-head h3,
.node-hero h2 {
  margin: 0;
}

.metric-highlight-meta,
.section-header span,
.feedback-source,
.source-chip {
  font-size: 12px;
  color: #64748b;
}

.metric-highlight-sub {
  margin-top: 8px;
  color: #475569;
  line-height: 1.6;
}

.region-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 14px;
}

.card-grid.dense {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.metric-card {
  border-radius: 18px;
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.16);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.metric-card.compact {
  gap: 12px;
}

.metric-card-head h4,
.feedback-card h4,
.node-hero h2 {
  margin: 0 0 4px;
  font-size: 17px;
  color: #0f172a;
}

.metric-card-head p,
.feedback-card p,
.role-card-head p,
.narrative-head p,
.secondary-card p {
  margin: 0;
  color: #64748b;
  line-height: 1.5;
}

.metric-pill,
.source-chip,
.warning-chip,
.data-chip,
.delta-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 700;
}

.metric-pill {
  background: rgba(15, 118, 110, 0.12);
  color: #0f766e;
}

.source-chip {
  background: rgba(15, 23, 42, 0.08);
  color: #334155;
}

.warning-chip {
  background: rgba(202, 138, 4, 0.14);
  color: #854d0e;
}

.data-chip {
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
}

.delta-chip {
  background: rgba(148, 163, 184, 0.12);
  color: #334155;
}

.metric-bar-track {
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(226, 232, 240, 0.88);
}

.metric-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f766e 0%, #d8b04c 100%);
}

.metric-card-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  font-size: 12px;
  color: #475569;
}

.feedback-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.feedback-card,
.role-card,
.narrative-card,
.context-card,
.explore-card,
.chat-box {
  padding: 18px 20px;
}

.feedback-loop {
  margin: 12px 0;
  line-height: 1.65;
  color: #0f172a;
}

.delta-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-source {
  margin-top: 12px;
}

.feedback-chain-template {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 16px 18px;
  border-radius: 18px;
  background: rgba(15, 23, 42, 0.04);
}

.chain-stage {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.chain-arrow {
  margin-left: 8px;
  color: #94a3b8;
}

.secondary-section {
  padding: 18px 20px;
}

.secondary-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.secondary-card {
  border-radius: 16px;
  background: rgba(15, 118, 110, 0.06);
  padding: 14px;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

.role-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.role-metric-item {
  padding: 12px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.04);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.role-subsection {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.subsection-title {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.region-score-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.region-score-item,
.context-item,
.subgraph-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
}

.narrative-columns {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.narrative-block {
  padding: 14px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.04);
}

.block-label {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.narrative-block p,
.explore-item p {
  margin: 0;
  line-height: 1.65;
  color: #0f172a;
}

.node-hero {
  padding: 18px 20px;
}

.node-hero-actions {
  display: flex;
  gap: 10px;
}

.node-context-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.context-list,
.subgraph-list,
.explore-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.warning-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chat-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-history {
  min-height: 180px;
  max-height: 320px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.04);
}

.chat-empty {
  color: #64748b;
  font-size: 13px;
}

.chat-message {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 16px;
}

.chat-message.user {
  background: rgba(37, 99, 235, 0.08);
}

.chat-message.assistant {
  background: rgba(15, 118, 110, 0.08);
}

.chat-role {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.chat-message p {
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
}

.chat-input-row {
  align-items: stretch;
}

.chat-input {
  width: 100%;
  min-height: 88px;
  resize: vertical;
}

.send-btn {
  min-width: 104px;
}

.report-tab-shell {
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 1280px) {
  .analysis-hero,
  .node-context-grid,
  .narrative-columns {
    grid-template-columns: 1fr;
    display: grid;
  }

  .hero-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    min-width: 0;
  }
}

@media (max-width: 900px) {
  .app-header {
    padding: 0 14px;
  }

  .content-area {
    flex-direction: column;
  }

  .panel-wrapper.left,
  .panel-wrapper.right {
    width: 100% !important;
    opacity: 1 !important;
    transform: none !important;
  }

  .analysis-panel {
    padding: 14px;
  }

  .hero-metrics,
  .card-grid,
  .feedback-grid,
  .role-grid,
  .secondary-list {
    grid-template-columns: 1fr;
  }
}
</style>
