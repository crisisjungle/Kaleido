<template>
  <div class="envfish-step envfish-step2">
    <div class="hero">
      <div class="hero-copy">
        <div class="eyebrow">ENVFISH / STEP 2</div>
        <h2>生态社会场景设计</h2>
        <p>
          从稳态报告或危机报告中提取区域、角色和关系，生成可注入变量的半定量推演场景。
        </p>
      </div>

      <div class="hero-metrics">
        <div class="metric-card">
          <span class="metric-label">Simulation</span>
          <span class="metric-value mono">{{ simulationId || 'pending' }}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Regions</span>
          <span class="metric-value">{{ graphStats.regions }}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Actors</span>
          <span class="metric-value">{{ graphStats.actors }}</span>
        </div>
        <div class="metric-card">
          <span class="metric-label">Relations</span>
          <span class="metric-value">{{ graphStats.edges }}</span>
        </div>
      </div>
    </div>

    <section class="workspace-shell">
      <div class="workspace-topbar">
        <div class="workspace-copy">
          <div class="eyebrow workspace-eyebrow">SCENARIO WORKBENCH</div>
          <h3>区域划分、Agent 配置与交互关系</h3>
          <p>通过顶部标签在区域划分、Agent 配置、交互关系和变量注入之间切换。区域层负责纳入，Agent 层负责交互，变量层负责干预。</p>
        </div>

        <div class="workspace-tabs" role="tablist" aria-label="Step2 工作台标签页">
          <button
            v-for="tab in workspaceTabs"
            :key="tab.value"
            type="button"
            :id="`workspace-tab-${tab.value}`"
            role="tab"
            class="workspace-tab"
            :class="{ active: activeWorkspaceTab === tab.value }"
            :aria-selected="activeWorkspaceTab === tab.value"
            :aria-controls="`workspace-panel-${tab.value}`"
            @click="activeWorkspaceTab = tab.value"
          >
            <span class="workspace-tab-label">{{ tab.label }}</span>
            <span class="workspace-tab-meta">{{ tab.meta }}</span>
          </button>
        </div>
      </div>

      <section
        v-show="activeWorkspaceTab === 'region'"
        id="workspace-panel-region"
        role="tabpanel"
        aria-labelledby="workspace-tab-region"
        class="panel workspace-panel region"
      >
        <div class="panel-title-row">
          <h3>区域划分</h3>
          <span class="hint">基线 / 灾难态</span>
        </div>
        <div class="mode-grid">
          <button
            v-for="mode in scenarioModes"
            :key="mode.value"
            class="mode-card"
            :class="{ active: scenarioMode === mode.value }"
            @click="scenarioMode = mode.value"
          >
            <span class="mode-tag">{{ mode.tag }}</span>
            <span class="mode-name">{{ mode.label }}</span>
            <p>{{ mode.description }}</p>
          </button>
        </div>

        <div class="slider-shell">
          <div class="panel-title-row">
            <h3>推演轮数上限</h3>
            <span class="hint mono">{{ maxRounds }}</span>
          </div>
          <input
            v-model.number="maxRounds"
            type="range"
            min="12"
            max="72"
            step="4"
            class="range"
          />
          <div class="range-labels">
            <span>12</span>
            <span>36</span>
            <span>72</span>
          </div>
        </div>

        <div class="panel-title-row">
          <h3>时间尺度</h3>
          <span class="hint mono">{{ configuredMinutesPerRound }} min / round</span>
        </div>
        <div class="template-grid">
          <button
            v-for="profile in temporalProfiles"
            :key="profile.value"
            class="template-card"
            :class="{ active: temporalPreset === profile.value }"
            @click="temporalPreset = profile.value"
          >
            <div class="template-head">
              <span class="template-name">{{ profile.label }}</span>
              <span class="template-badge">{{ profile.badge }}</span>
            </div>
            <p>{{ profile.description }}</p>
          </button>
        </div>

        <div class="catalog">
          <div class="panel-title-row">
            <h3>参考时间</h3>
            <span class="hint">{{ referenceTimeLocal ? '历史/指定时间场景' : '留空即实时场景' }}</span>
          </div>
          <label>
            <span>用于解释大气与海洋方向场的时间锚点</span>
            <input v-model="referenceTimeLocal" type="datetime-local" />
          </label>
        </div>

        <div class="panel-title-row">
          <h3>扩散模板</h3>
          <span class="hint">模板只定义传播语法，不接真实物理场</span>
        </div>
        <div class="template-grid">
          <button
            v-for="template in diffusionTemplates"
            :key="template.value"
            class="template-card"
            :class="{ active: diffusionTemplate === template.value }"
            @click="diffusionTemplate = template.value"
          >
            <div class="template-head">
              <span class="template-name">{{ template.label }}</span>
              <span class="template-badge">{{ template.scope }}</span>
            </div>
            <p>{{ template.description }}</p>
          </button>
        </div>

        <div class="panel-title-row">
          <h3>关系搜索模式</h3>
          <span class="hint">Fast 控预算，Deep Search 放大跨区关系发现</span>
        </div>
        <div class="template-grid">
          <button
            v-for="mode in searchModes"
            :key="mode.value"
            class="template-card"
            :class="{ active: searchMode === mode.value }"
            @click="searchMode = mode.value"
          >
            <div class="template-head">
              <span class="template-name">{{ mode.label }}</span>
              <span class="template-badge">{{ mode.badge }}</span>
            </div>
            <p>{{ mode.description }}</p>
          </button>
        </div>

        <div class="catalog">
        <div class="panel-title-row">
          <h3>细分区域预览</h3>
          <span class="hint">{{ regionSourceLabel }}</span>
        </div>

          <div class="summary-grid">
            <div class="summary-card">
              <span>Region layers</span>
              <strong>{{ regionRecords.length }}</strong>
            </div>
            <div class="summary-card">
              <span>Agent anchors</span>
              <strong>{{ regionAnchorTotal }}</strong>
            </div>
            <div class="summary-card">
              <span>Adjacency links</span>
              <strong>{{ regionNeighborLinks }}</strong>
            </div>
            <div class="summary-card">
              <span>Coverage</span>
              <strong>{{ regionCoverageLabel }}</strong>
            </div>
          </div>

          <div v-if="regionAnchorMatrix.length > 0" class="region-grid">
            <article v-for="(region, index) in regionAnchorMatrix" :key="region.regionKey" class="region-card">
              <div class="region-card-head">
                <div>
                  <div class="region-card-index mono">R{{ String(index + 1).padStart(2, '0') }}</div>
                  <strong>{{ region.displayName }}</strong>
                </div>
                <span class="region-card-type">{{ region.regionTypeLabel }}</span>
              </div>
              <p>{{ region.summary }}</p>
              <div class="region-card-meta">
                <span>{{ region.layerLabel }}</span>
                <span>{{ region.subregionLabel }}</span>
                <span>{{ region.neighborCount }} neighbors</span>
                <span>{{ region.agentCount }} agents</span>
              </div>
              <div class="chip-wrap">
                <span v-for="tag in region.tags.slice(0, 4)" :key="tag" class="chip">{{ tag }}</span>
                <span v-for="neighbor in region.neighbors.slice(0, 2)" :key="neighbor" class="chip chip-soft">{{ neighbor }}</span>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">
            当前没有可用的区域配置，系统会使用图谱节点作为降级区域骨架。
          </div>
        </div>
      </section>

      <section
        v-show="activeWorkspaceTab === 'agents'"
        id="workspace-panel-agents"
        role="tabpanel"
        aria-labelledby="workspace-tab-agents"
        class="panel workspace-panel agents"
      >
        <div class="panel-title-row">
          <h3>Agent 配置</h3>
          <span class="hint">{{ agentSourceLabel }}</span>
        </div>

        <div class="summary-grid">
          <div class="summary-card">
            <span>Total agents</span>
            <strong>{{ agentCards.length }}</strong>
          </div>
          <div class="summary-card">
            <span>Human / Org</span>
            <strong>{{ agentCategorySummary.human + agentCategorySummary.organization }}</strong>
          </div>
          <div class="summary-card">
            <span>Eco / Gov</span>
            <strong>{{ agentCategorySummary.ecology + agentCategorySummary.governance }}</strong>
          </div>
          <div class="summary-card">
            <span>Fallback</span>
            <strong>{{ agentSourceMode === 'graph' ? 'ON' : 'OFF' }}</strong>
          </div>
        </div>

        <div class="catalog">
          <div class="catalog-title">分类摘要</div>
          <div class="chip-wrap">
            <span v-for="group in agentCategoryGroups" :key="group.key" class="chip agent-group-chip">
              {{ group.label }} · {{ group.count }}
            </span>
          </div>
        </div>

        <div class="catalog">
          <div class="catalog-title">Agent 卡片总览</div>
          <div v-if="agentCards.length > 0" class="agent-grid">
            <AgentCard
              v-for="(agent, index) in agentCards"
              :key="agent.agentKey"
              :agent="agent"
              :index="index + 1"
            />
          </div>
          <div v-else class="empty-state">
            当前配置里还没有可展示的 agent，系统会在后续用图谱节点自动降级生成。
          </div>
        </div>

        <div class="catalog" v-if="agentSourceMode === 'graph'">
          <div class="catalog-title">降级说明</div>
          <div class="grounding-box">
            <p>这里展示的是图谱预览，不是最终 Agent 档案。系统会自动生成正式 Agent 配置，完成后这里会切换成每个 Agent 的主区域、影响范围、初始状态、倾向、动机和敏感项。</p>
          </div>
        </div>
      </section>

      <section
        v-show="activeWorkspaceTab === 'relations'"
        id="workspace-panel-relations"
        role="tabpanel"
        aria-labelledby="workspace-tab-relations"
        class="panel workspace-panel relations"
      >
        <div class="panel-title-row">
          <h3>{{ relationSectionTitle }}</h3>
          <span class="hint">{{ relationSourceLabel }}</span>
        </div>

        <div class="summary-grid">
          <div class="summary-card">
            <span>Interaction edges</span>
            <strong>{{ relationSummary.total }}</strong>
          </div>
          <div class="summary-card">
            <span>Cross-region</span>
            <strong>{{ relationSummary.crossRegionCount }}</strong>
          </div>
          <div class="summary-card">
            <span>Channels</span>
            <strong>{{ relationSummary.channels.length }}</strong>
          </div>
          <div class="summary-card">
            <span>Relation types</span>
            <strong>{{ relationSummary.types.length }}</strong>
          </div>
        </div>

        <div class="catalog">
          <div class="catalog-title">关系类型</div>
          <div class="chip-wrap">
            <span
              v-for="item in relationSummary.types.slice(0, 12)"
              :key="item.label"
              class="chip relation-chip"
            >
              {{ item.displayLabel }} · {{ item.count }}
            </span>
            <span v-if="relationSummary.types.length === 0" class="empty-chip">
              当前没有可识别的关系标签。
            </span>
          </div>
        </div>

        <div class="catalog" v-if="relationSummary.channels.length > 0">
          <div class="catalog-title">互动渠道</div>
          <div class="chip-wrap">
            <span
              v-for="item in relationSummary.channels.slice(0, 8)"
              :key="item.label"
              class="chip relation-chip"
            >
              {{ item.displayLabel }} · {{ item.count }}
            </span>
          </div>
        </div>

        <div class="catalog">
          <div class="catalog-title">这部分在看什么</div>
          <div class="grounding-box">
            <p>{{ relationPanelExplanation }}</p>
          </div>
        </div>

        <div class="catalog">
          <div class="panel-title-row">
            <h3>区域与 Agent 归属</h3>
            <span class="hint">按主区域汇总正式 Agent；未生成前仅显示区域骨架</span>
          </div>
          <div v-if="regionAnchorMatrix.length > 0" class="relation-grid">
            <article v-for="region in regionAnchorMatrix" :key="region.regionKey" class="relation-card">
              <div class="region-card-head">
                <div>
                  <div class="region-card-index mono">R{{ region.rank }}</div>
                  <strong>{{ region.displayName }}</strong>
                </div>
                <span class="region-card-type">{{ region.agentCount }} agents</span>
              </div>
              <p>{{ region.summary }}</p>
              <div class="chip-wrap">
                <span v-for="family in region.topFamilies" :key="family" class="chip">{{ family }}</span>
                <span v-if="region.topFamilies.length === 0" class="empty-chip">暂无分类聚合</span>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">
            当前还没有可用的区域锚点，系统会在配置完成后补全关系矩阵。
          </div>
        </div>

        <div class="catalog" v-if="relationSummary.sampleEdges.length > 0">
          <div class="catalog-title">关系样例</div>
          <div class="grounding-box">
            <div class="relation-edge-list">
              <div v-for="edge in relationSummary.sampleEdges" :key="edge.key" class="relation-edge-row">
                <strong>{{ edge.displayLabel }}</strong>
                <span>{{ edge.summary }}</span>
                <small>{{ edge.rationale || edge.hint }}<template v-if="edge.channelLabel || edge.strengthLabel"> · {{ [edge.channelLabel, edge.strengthLabel && `强度 ${edge.strengthLabel}`].filter(Boolean).join(' · ') }}</template></small>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        v-show="activeWorkspaceTab === 'variables'"
        id="workspace-panel-variables"
        role="tabpanel"
        aria-labelledby="workspace-tab-variables"
        class="panel workspace-panel variables"
      >
        <div class="panel-title-row">
          <h3>中途变量</h3>
          <button class="ghost-btn" @click="addVariable('disaster')">+ 灾难变量</button>
        </div>

        <div class="variable-list">
          <article v-for="(variable, index) in injectedVariables" :key="variable.id" class="variable-card">
            <div class="variable-header">
              <div>
                <span class="variable-index">V{{ index + 1 }}</span>
                <strong>{{ variable.type === 'policy' ? '政策/干预变量' : '灾难变量' }}</strong>
              </div>
              <button class="remove-btn" @click="removeVariable(variable.id)">删除</button>
            </div>

            <div class="field-row">
              <label>
                类型
                <select v-model="variable.type">
                  <option value="disaster">disaster</option>
                  <option value="policy">policy</option>
                </select>
              </label>
              <label>
                变量名
                <input v-model="variable.name" type="text" placeholder="核废水排放 / 强制撤离" />
              </label>
            </div>

            <label>
              描述
              <textarea v-model="variable.description" rows="3" placeholder="一句话描述变量如何改变生态或社会状态"></textarea>
            </label>

            <div class="field-row">
              <label>
                目标区域
                <input v-model="variable.targetRegions" type="text" placeholder="滨海区,渔港,近岸海域" />
              </label>
              <label>
                目标节点
                <input v-model="variable.targetNodes" type="text" placeholder="渔民,海流,环保局" />
              </label>
            </div>

            <div class="field-row">
              <label>
                起始轮次
                <input v-model.number="variable.startRound" type="number" min="0" />
              </label>
              <label>
                持续轮次
                <input v-model.number="variable.durationRounds" type="number" min="1" />
              </label>
              <label>
                强度
                <input v-model.number="variable.intensity" type="range" min="0" max="100" />
              </label>
            </div>

            <div v-if="variable.type === 'policy'" class="policy-row">
              <label>
                干预模式
                <select v-model="variable.policyMode">
                  <option v-for="mode in policyModes" :key="mode.value" :value="mode.value">
                    {{ mode.label }}
                  </option>
                </select>
              </label>
            </div>
          </article>
        </div>
      </section>
    </section>

    <section class="risk-preview-shell">
      <div class="panel-title-row">
        <h3>风险对象预览</h3>
        <span class="hint">{{ riskObjects.length }} objects / step 2 preview</span>
      </div>

      <div v-if="riskObjects.length > 0" class="risk-preview-grid">
        <div class="risk-preview-list">
          <button
            v-for="item in riskObjects"
            :key="item.risk_object_id"
            type="button"
            class="risk-preview-card"
            :class="{ active: item.risk_object_id === selectedRiskObjectId }"
            @click="selectedRiskObjectId = item.risk_object_id"
          >
            <div class="risk-preview-head">
              <span class="risk-mode-tag">{{ item.mode || 'watch' }}</span>
              <span v-if="item.risk_object_id === primaryRiskObjectId" class="risk-primary-tag">PRIMARY</span>
            </div>
            <strong>{{ item.title }}</strong>
            <p>{{ item.why_now || item.summary || '等待风险对象摘要。' }}</p>
            <div class="risk-meta">
              <span>Sev {{ normalizeScore(item.severity_score) }}</span>
              <span>Act {{ normalizeScore(item.actionability_score) }}</span>
            </div>
          </button>
        </div>

        <div v-if="selectedRiskObject" class="risk-preview-detail">
          <div class="risk-detail-top">
            <div>
              <div class="eyebrow risk-eyebrow">
                {{ selectedRiskObject.mode === 'incident' ? 'INCIDENT PREVIEW' : 'WATCH PREVIEW' }}
              </div>
              <h3>{{ selectedRiskObject.title }}</h3>
              <p>{{ selectedRiskObject.summary || selectedRiskObject.why_now || '等待风险对象摘要。' }}</p>
            </div>

            <div class="risk-score-strip">
              <div class="summary-card compact">
                <span>Severity</span>
                <strong>{{ normalizeScore(selectedRiskObject.severity_score) }}</strong>
              </div>
              <div class="summary-card compact">
                <span>Confidence</span>
                <strong>{{ formatPercent(selectedRiskObject.confidence_score) }}</strong>
              </div>
            </div>
          </div>

          <div class="risk-note-box">
            <span>Why Now</span>
            <strong>{{ selectedRiskObject.why_now || '场景配置完成后会显示 why now。' }}</strong>
          </div>

          <div class="risk-step-list">
            <span v-for="step in selectedRiskObject.chain_steps || []" :key="step" class="chip">{{ step }}</span>
          </div>

          <div class="risk-node-grid">
            <section class="risk-mini-panel">
              <div class="catalog-title">相关实体节点</div>
              <div v-if="riskObjectEntityNodes.length > 0" class="node-list">
                <article v-for="node in riskObjectEntityNodes" :key="node.id" class="node-card">
                  <div class="node-card-head">
                    <strong>{{ node.name }}</strong>
                    <span class="node-state" :class="{ matched: node.matched }">{{ node.matched ? 'graph node' : 'risk ref' }}</span>
                  </div>
                  <div class="tag-wrap">
                    <span v-for="label in node.labels" :key="label" class="mini-tag">{{ label }}</span>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">生成配置后将展示相关实体节点。</div>
            </section>

            <section class="risk-mini-panel">
              <div class="catalog-title">相关区域</div>
              <div v-if="riskObjectRegionNodes.length > 0" class="node-list">
                <article v-for="region in riskObjectRegionNodes" :key="region.id" class="node-card">
                  <div class="node-card-head">
                    <strong>{{ region.name }}</strong>
                    <span class="node-state" :class="{ matched: region.matched }">{{ region.matched ? 'graph node' : 'scope' }}</span>
                  </div>
                  <div class="tag-wrap">
                    <span v-for="label in region.labels" :key="label" class="mini-tag">{{ label }}</span>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">当前没有可映射的区域节点。</div>
            </section>
          </div>

          <div class="risk-node-grid secondary">
            <section class="risk-mini-panel">
              <div class="catalog-title">受影响群簇</div>
              <div v-if="riskObjectClusters.length > 0" class="cluster-list">
                <article v-for="cluster in riskObjectClusters" :key="cluster.cluster_id" class="cluster-mini-card">
                  <div class="node-card-head">
                    <strong>{{ cluster.name }}</strong>
                    <span class="mini-tag accent">Mismatch {{ normalizeScore(cluster.mismatch_risk) }}</span>
                  </div>
                  <p>{{ formatInlineList(cluster.dependency_profile, '暂无依赖结构') }}</p>
                </article>
              </div>
              <div v-else class="empty-state">当前还没有受影响群簇预览。</div>
            </section>

            <section class="risk-mini-panel">
              <div class="catalog-title">转折点</div>
              <ul v-if="(selectedRiskObject.turning_points || []).length > 0" class="bullet-list">
                <li v-for="point in selectedRiskObject.turning_points" :key="point">{{ point }}</li>
              </ul>
              <div v-else class="empty-state">当前对象还没有显式转折点。</div>
            </section>
          </div>
        </div>
      </div>

      <div v-else class="empty-state">
        生成场景定义后，这里会出现风险定义预览，并可联动左侧图谱高亮相关节点。
      </div>
    </section>

    <section class="progress-shell">
      <div class="progress-head">
        <div>
          <div class="panel-title-row">
            <h3>准备进度</h3>
            <span class="hint">{{ prepareStageLabel }}</span>
          </div>
          <p class="progress-note">{{ prepareMessage || '等待用户触发场景配置生成' }}</p>
        </div>
        <div class="progress-score mono">{{ prepareProgress }}%</div>
      </div>

      <div class="progress-bar">
        <div class="progress-bar-fill" :style="{ width: `${prepareProgress}%` }"></div>
      </div>

      <div class="action-row">
        <button class="secondary-btn" @click="$emit('go-back')">返回图谱构建</button>
        <button class="primary-btn" :disabled="isPreparing" @click="handlePrepare">
          {{ isPreparing ? '生成中...' : (phase === 'ready' ? '重算场景配置' : '生成场景配置') }}
        </button>
        <button class="secondary-btn" :disabled="!isReady" @click="handleNextStep">
          进入推演
        </button>
      </div>
    </section>

    <section class="log-shell">
      <div class="panel-title-row">
        <h3>系统日志</h3>
        <span class="hint mono">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="logs">
        <div v-for="(log, index) in systemLogs" :key="index" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getPrepareStatus, getSimulationConfig, getSimulationConfigRealtime, prepareSimulation, getSimulation } from '../api/simulation'
import AgentCard from './step2/AgentCard.vue'

const props = defineProps({
  simulationId: String,
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  initialScenarioMode: String,
  initialDiffusionTemplate: String,
  initialSearchMode: String
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status', 'risk-object-focus'])

const scenarioModes = [
  {
    value: 'baseline_mode',
    tag: 'BASELINE',
    label: '常态 + 灾难变量注入',
    description: '从平稳生态和社会网络出发，观察变量首次跨界触发后的破窗效应。'
  },
  {
    value: 'crisis_mode',
    tag: 'CRISIS',
    label: '灾难态 + 干预变量注入',
    description: '从破碎结构出发，评估政策执行摩擦、信任崩塌与次生灾害。'
  }
]

const diffusionTemplates = [
  {
    value: 'air',
    label: 'AIR',
    scope: '气团',
    description: '邻接扩散、滞后传播、衰减延展，适合大气污染与跨区漂移。'
  },
  {
    value: 'inland_water',
    label: 'WATER',
    scope: '河网',
    description: '沿上游/下游、支流与库区传播，适合内陆水体和流域污染。'
  },
  {
    value: 'marine',
    label: 'MARINE',
    scope: '海洋',
    description: '沿岸流和海流驱动，扩散更慢但影响范围更宽。'
  }
]

const searchModes = [
  {
    value: 'fast',
    label: 'FAST',
    badge: '默认',
    description: '更少跨区候选和新边，优先稳定、快速和解释性。'
  },
  {
    value: 'deep_search',
    label: 'DEEP SEARCH',
    badge: '探索',
    description: '更高跨区候选预算和更长 TTL，更容易发现隐藏桥接关系。'
  }
]

const temporalProfiles = [
  {
    value: 'rapid',
    label: 'RAPID',
    badge: '20 min',
    minutes: 20,
    description: '更短轮次，适合突发扩散、预警窗口和快速干预评估。'
  },
  {
    value: 'standard',
    label: 'STANDARD',
    badge: '60 min',
    minutes: 60,
    description: '默认时标，适合大多数区域级生态社会推演。'
  },
  {
    value: 'slow',
    label: 'SLOW',
    badge: '180 min',
    minutes: 180,
    description: '更长轮次，适合海洋、慢变量和恢复期传播。'
  }
]

const policyModes = [
  { value: 'restrict', label: 'restrict' },
  { value: 'relocate', label: 'relocate' },
  { value: 'subsidize', label: 'subsidize' },
  { value: 'monitor', label: 'monitor' },
  { value: 'disclose', label: 'disclose' },
  { value: 'repair', label: 'repair' },
  { value: 'ban', label: 'ban' },
  { value: 'reopen', label: 'reopen' }
]

const scenarioMode = ref(props.initialScenarioMode || 'baseline_mode')
const diffusionTemplate = ref(props.initialDiffusionTemplate || 'marine')
const searchMode = ref(props.initialSearchMode || 'fast')
const temporalPreset = ref('standard')
const configuredMinutesPerRound = ref(60)
const referenceTimeLocal = ref('')
const maxRounds = ref(36)
const activeWorkspaceTab = ref('region')
const injectedVariables = ref([createVariable('disaster')])
const phase = ref('idle')
const prepareProgress = ref(0)
const prepareMessage = ref('')
const prepareStage = ref('')
const prepareTaskId = ref('')
const isPreparing = ref(false)
const configSnapshot = ref(null)
const configRealtime = ref(null)
const simulationSnapshot = ref(null)
const autoPrepareAttempted = ref(false)

let progressTimer = null
let configTimer = null

const graphNodes = computed(() => collectGraphNodes(props.graphData))
const graphEdges = computed(() => collectGraphEdges(props.graphData))

const diffusionTemplateLabel = computed(() => {
  return diffusionTemplates.find(template => template.value === diffusionTemplate.value)?.label || '未设置模板'
})

const temporalProfileLabel = computed(() => {
  return temporalProfiles.find(profile => profile.value === temporalPreset.value)?.label || 'STANDARD'
})

const graphStats = computed(() => {
  const nodes = graphNodes.value
  const edges = graphEdges.value
  const families = categorizeNodes(nodes)
  return {
    regions: families.regions.length,
    humanActors: families.human.length,
    organizationActors: families.organization.length,
    ecologyActors: families.ecology.length,
    governanceActors: families.governance.length,
    infrastructureActors: families.infrastructure.length,
    actors:
      families.human.length +
      families.organization.length +
      families.ecology.length +
      families.governance.length +
      families.infrastructure.length,
    edges: edges.length
  }
})

const resolvedConfig = computed(() => {
  return configRealtime.value?.config || configSnapshot.value || {}
})

const agentSourceMode = computed(() => {
  if (Array.isArray(resolvedConfig.value.agent_configs) && resolvedConfig.value.agent_configs.length > 0) {
    return 'agent_configs'
  }
  if (Array.isArray(resolvedConfig.value.actor_profiles) && resolvedConfig.value.actor_profiles.length > 0) {
    return 'actor_profiles'
  }
  if (graphStats.value.actors > 0) {
    return 'graph'
  }
  return 'empty'
})

const regionRecords = computed(() => {
  const regions = normalizeRegionRecords(resolvedConfig.value.region_graph)
  if (regions.length > 0) {
    return regions
  }
  return normalizeRegionRecordsFromGraph(graphNodes.value)
})

const agentCards = computed(() => {
  const configAgents = normalizeAgentRecords(resolvedConfig.value, regionRecords.value)
  if (configAgents.length > 0) {
    return configAgents
  }
  return normalizeAgentRecordsFromGraph(graphNodes.value, regionRecords.value)
})

const agentCategorySummary = computed(() => summarizeAgentCategories(agentCards.value))

const agentCategoryGroups = computed(() => {
  return [
    { key: 'human', label: '个体', count: agentCategorySummary.value.human },
    { key: 'organization', label: '组织', count: agentCategorySummary.value.organization },
    { key: 'ecology', label: '生态', count: agentCategorySummary.value.ecology },
    { key: 'governance', label: '治理', count: agentCategorySummary.value.governance },
    { key: 'infrastructure', label: '基础设施', count: agentCategorySummary.value.infrastructure },
    { key: 'other', label: '其他', count: agentCategorySummary.value.other }
  ].filter(item => item.count > 0 || item.key === 'other')
})

const regionAgentMap = computed(() => buildRegionAgentMap(regionRecords.value, agentCards.value))

const regionSourceLabel = computed(() => {
  if (resolvedConfig.value.region_graph?.length) {
    return `${resolvedConfig.value.region_graph.length} 个配置区域`
  }
  if (regionRecords.value.length > 0) {
    return '图谱降级区域'
  }
  return '暂无区域来源'
})

const agentSourceLabel = computed(() => {
  if (agentSourceMode.value === 'agent_configs') {
    return 'agent_configs / 配置'
  }
  if (agentSourceMode.value === 'actor_profiles') {
    return 'actor_profiles / 配置'
  }
  if (agentSourceMode.value === 'graph') {
    if (phase.value === 'preparing') return '自动生成正式配置中 · 当前为图谱预览'
    if (phase.value === 'idle') return '图谱预览 · 尚未生成正式 Agent 配置'
    return '图谱预览'
  }
  return '暂无 agent 来源'
})

const relationGraphEdges = computed(() => {
  const configured = resolvedConfig.value?.agent_relationship_graph
  if (Array.isArray(configured) && configured.length > 0) {
    return configured
  }
  return graphEdges.value
})

const relationSourceMode = computed(() => {
  const configured = resolvedConfig.value?.agent_relationship_graph
  if (Array.isArray(configured) && configured.length > 0) {
    return 'agent_graph'
  }
  return 'graph'
})

const relationSummary = computed(() => summarizeRelations(relationGraphEdges.value))

const relationSectionTitle = computed(() => {
  return relationSourceMode.value === 'agent_graph' ? 'Agent 关系图' : '图谱关系骨架'
})

const relationPanelExplanation = computed(() => {
  if (relationSourceMode.value === 'agent_graph') {
    return '这里展示的是正式生成的 Agent 关系图，表示谁会影响谁、依赖谁、受谁约束。它会作为后续推演里 Agent 互动的基础网络。'
  }
  return '这里展示的是原始图谱里的关系骨架，不是最终 Agent 互动网络。当前这些关系表示节点之间已有的事实连接，比如监管、依赖、影响、连接、位于某区域等，用来给后续正式 Agent 配置和风险链路提供底稿。'
})

const relationSourceLabel = computed(() => {
  if (relationSourceMode.value === 'agent_graph') {
    return `${relationSummary.value.total} 条正式 Agent 关系`
  }
  if (relationSummary.value.total > 0) {
    return `${relationSummary.value.total} 条图谱关系骨架`
  }
  return '暂无关系来源'
})

const regionNeighborLinks = computed(() => {
  return regionRecords.value.reduce((sum, region) => sum + region.neighborCount, 0)
})

const regionAnchorTotal = computed(() => {
  return regionAnchorMatrix.value.reduce((sum, region) => sum + region.agentCount, 0)
})

const regionCoverageLabel = computed(() => {
  if (regionAnchorMatrix.value.length === 0) return '0%'
  const activeRegions = regionAnchorMatrix.value.filter((region) => region.agentCount > 0).length
  const percentage = Math.round((activeRegions / Math.max(regionAnchorMatrix.value.length, 1)) * 100)
  return `${percentage}%`
})

const regionAnchorMatrix = computed(() => {
  return regionAgentMap.value
    .slice()
    .sort((left, right) => right.agentCount - left.agentCount)
    .map((item, index) => ({
      ...item,
      rank: index + 1
    }))
})

const workspaceTabs = computed(() => {
  return [
    {
      value: 'region',
      label: '区域划分',
      meta: `${regionRecords.value.length} 个区域 · ${diffusionTemplateLabel.value}`
    },
    {
      value: 'agents',
      label: 'Agent配置',
      meta: `${agentCards.value.length} 个 · ${agentSourceLabel.value}`
    },
    {
      value: 'relations',
      label: '关系骨架',
      meta: `${relationSummary.value.total} 条 · ${relationSummary.value.types.length} 类`
    },
    {
      value: 'variables',
      label: '变量注入',
      meta: `${injectedVariables.value.length} 项变量`
    }
  ]
})

const groundingSummary = computed(() => {
  const source = configRealtime.value?.data_grounding_summary || configSnapshot.value?.data_grounding_summary
  if (typeof source === 'string' && source.trim()) return source
  if (Array.isArray(source) && source.length > 0) return source.join(' · ')
  return '无外部数据时使用报告先验与图谱结构初始化。'
})

const groundingHints = computed(() => {
  const hints = []
  if (configRealtime.value?.grounding_sources) {
    const value = configRealtime.value.grounding_sources
    if (Array.isArray(value)) hints.push(...value.map(String))
  }
  if (hints.length === 0) {
    hints.push('EPA / USGS / Copernicus / NOAA 均可作为可选地基')
  }
  return hints
})

const selectedRiskObjectId = ref('')

const riskSourceCandidates = computed(() => [
  resolvedConfig.value,
  configRealtime.value,
  configSnapshot.value,
  simulationSnapshot.value
].filter(Boolean))

function asArray(value) {
  return Array.isArray(value) ? value : []
}

function firstNonEmptyString(...values) {
  for (const value of values) {
    const text = String(value || '').trim()
    if (text) return text
  }
  return ''
}

function normalizeRegionRef(value) {
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? { region_id: text, region_name: text } : null
  }
  if (!value || typeof value !== 'object') return null
  const regionId = firstNonEmptyString(value.region_id, value.regionId, value.id, value.key, value.uuid, value.code)
  const regionName = firstNonEmptyString(value.region_name, value.regionName, value.name, value.label, value.title, regionId)
  if (!regionId && !regionName) return null
  return {
    region_id: regionId || regionName,
    region_name: regionName || regionId
  }
}

function normalizeEntityRef(value) {
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? { entity_uuid: text, entity_name: text } : null
  }
  if (!value || typeof value !== 'object') return null
  const entityUuid = firstNonEmptyString(value.entity_uuid, value.entityUuid, value.uuid, value.id, value.key)
  const entityName = firstNonEmptyString(value.entity_name, value.entityName, value.name, value.label, value.title, entityUuid)
  if (!entityUuid && !entityName) return null
  return {
    entity_uuid: entityUuid || entityName,
    entity_name: entityName || entityUuid
  }
}

function normalizeClusterRef(value) {
  if (!value || typeof value !== 'object') return value
  return {
    ...value,
    cluster_id: firstNonEmptyString(value.cluster_id, value.clusterId, value.id, value.key, value.name),
    name: firstNonEmptyString(value.name, value.label, value.title, value.cluster_id, value.clusterId),
    primary_regions: uniqueList(asArray(value.primary_regions).map(String)),
    actor_ids: uniqueList(asArray(value.actor_ids).map(String)).map(item => Number(item) || item),
    dependency_profile: uniqueList(asArray(value.dependency_profile).map(String)),
    early_loss_signals: uniqueList(asArray(value.early_loss_signals).map(String))
  }
}

function collectRiskEdgeIds(raw, chainTemplate = []) {
  const templateEdgeIds = chainTemplate.flatMap((step) => {
    if (!step || typeof step !== 'object') return []
    return [
      step.edge_id,
      step.edgeId,
      step.edge_ids,
      step.edgeIds,
      step.relationship_id,
      step.relationshipId,
      step.link_id,
      step.linkId
    ]
  })

  return uniqueList([
    ...asArray(raw.edge_ids ?? raw.edgeIds),
    ...asArray(raw.path_edge_ids ?? raw.pathEdgeIds),
    ...asArray(raw.related_edge_ids ?? raw.relatedEdgeIds),
    ...asArray(raw.related_dynamic_edge_ids ?? raw.relatedDynamicEdgeIds),
    ...asArray(raw.highlight_edge_ids ?? raw.highlightEdgeIds),
    ...templateEdgeIds
  ].flat().map(item => String(item || '').trim()))
}

function normalizeRiskDefinition(raw = {}, index = 0) {
  const scope = raw.scope && typeof raw.scope === 'object' ? raw.scope : {}
  const scopeRegions = uniqueList([
    ...asArray(scope.regions),
    ...asArray(scope.region_refs),
    ...asArray(raw.regions),
    ...asArray(raw.region_scope)
  ].flatMap(item => {
    const ref = normalizeRegionRef(item)
    return ref ? [ref] : []
  }).map(item => JSON.stringify(item)))
    .map(item => JSON.parse(item))

  const scopeEntities = uniqueList([
    ...asArray(scope.entities),
    ...asArray(scope.entity_refs),
    ...asArray(raw.entities),
    ...asArray(raw.source_entity_uuids)
  ].flatMap(item => {
    const ref = normalizeEntityRef(item)
    return ref ? [ref] : []
  }).map(item => JSON.stringify(item)))
    .map(item => JSON.parse(item))

  const scopeActors = uniqueList([
    ...asArray(scope.actors),
    ...asArray(scope.actor_refs),
    ...asArray(raw.actors),
    ...asArray(raw.source_actor_ids)
  ].flatMap(item => {
    if (typeof item === 'number' || typeof item === 'string') {
      const text = String(item).trim()
      return text ? [{ actor_id: text, actor_name: text }] : []
    }
    if (!item || typeof item !== 'object') return []
    const actorId = firstNonEmptyString(item.actor_id, item.actorId, item.agent_id, item.agentId, item.id, item.key)
    const actorName = firstNonEmptyString(item.actor_name, item.actorName, item.agent_name, item.agentName, item.name, item.username, item.label, actorId)
    if (!actorId && !actorName) return []
    return [{
      actor_id: actorId || actorName,
      actor_name: actorName || actorId
    }]
  }).filter(Boolean))

  const chainTemplate = asArray(raw.chain_template)
  const chainSteps = uniqueList(
    asArray(raw.chain_steps).flatMap(step => {
      if (typeof step === 'string') return [step]
      if (!step || typeof step !== 'object') return []
      return [firstNonEmptyString(step.label, step.name, step.title, step.step_name, step.step_id)]
    }).filter(Boolean)
  )
  const resolvedChainSteps = chainSteps.length > 0
    ? chainSteps
    : uniqueList(chainTemplate.flatMap(step => {
        if (typeof step === 'string') return [step]
        if (!step || typeof step !== 'object') return []
        return [firstNonEmptyString(step.label, step.name, step.title, step.step_name, step.step_id)]
      }).filter(Boolean))

  const rootPressures = uniqueList([
    ...asArray(raw.root_pressures),
    ...asArray(scope.variable_types),
    ...asArray(raw.trigger_rules?.variable_types),
    ...asArray(raw.trigger_rules?.policy_modes),
    firstNonEmptyString(raw.category, raw.risk_type).replace(/[_-]+/g, ' ')
  ].flat().map(item => String(item || '').trim()).filter(Boolean))

  const turningPoints = uniqueList([
    ...asArray(raw.turning_points),
    ...resolvedChainSteps.slice(-1)
  ])

  const interventionTemplates = asArray(raw.intervention_templates).map(item => {
    if (!item || typeof item !== 'object') return item
    return {
      ...item,
      target_chain_steps: uniqueList(asArray(item.target_chain_steps).map(String)),
      benefit_clusters: uniqueList(asArray(item.benefit_clusters).map(String)),
      hurt_clusters: uniqueList(asArray(item.hurt_clusters).map(String)),
      friction_points: uniqueList(asArray(item.friction_points).map(String))
    }
  })

  const branchTemplates = asArray(raw.branch_templates).map(item => {
    if (!item || typeof item !== 'object') return item
    return {
      ...item,
      assumptions: uniqueList(asArray(item.assumptions).map(String)),
      target_interventions: uniqueList(asArray(item.target_interventions).map(String)),
      comparison_focus: uniqueList(asArray(item.comparison_focus).map(String))
    }
  })

  const riskType = firstNonEmptyString(raw.risk_type, raw.category, 'baseline')
  const mode = raw.mode || (riskType === 'variable_triggered' || riskType === 'emergent' ? 'incident' : 'watch')
  const prioritySeed = Number(raw.priority_seed ?? raw.prioritySeed ?? raw.severity_score ?? 0.68)
  const severityScore = Number.isFinite(Number(raw.severity_score))
    ? Number(raw.severity_score)
    : Math.round(Math.max(0, Math.min(100, prioritySeed * 100)))
  const confidenceScore = Number.isFinite(Number(raw.confidence_score))
    ? Number(raw.confidence_score)
    : Number.isFinite(Number(raw.confidence))
      ? Number(raw.confidence)
      : 0.72

  return {
    ...raw,
    risk_object_id: firstNonEmptyString(raw.risk_id, raw.risk_object_id, raw.id, `risk_definition_${index + 1}`),
    risk_id: firstNonEmptyString(raw.risk_id, raw.risk_object_id, raw.id, `risk_definition_${index + 1}`),
    title: firstNonEmptyString(raw.title, raw.name, raw.label, raw.summary, `风险定义 ${index + 1}`),
    summary: firstNonEmptyString(raw.summary, raw.description, raw.summary_text, '场景定义完成后会在此展示风险链路摘要。'),
    why_now: firstNonEmptyString(raw.why_now, raw.trigger_summary, raw.summary, '当前风险定义已就绪，等待推演运行态刷新。'),
    risk_type: riskType,
    mode,
    status: firstNonEmptyString(raw.status, 'tracked'),
    time_horizon: firstNonEmptyString(raw.time_horizon, raw.horizon, '30d'),
    region_scope: uniqueList(scopeRegions.map(item => item.region_name || item.region_id)),
    primary_regions: uniqueList([
      ...asArray(raw.primary_regions).map(value => normalizeRegionRef(value)?.region_name).filter(Boolean),
      ...scopeRegions.slice(0, 2).map(item => item.region_name || item.region_id)
    ]),
    severity_score: severityScore,
    confidence_score: confidenceScore,
    actionability_score: Number.isFinite(Number(raw.actionability_score))
      ? Number(raw.actionability_score)
      : Math.round(Math.max(0, Math.min(100, prioritySeed * 85))),
    novelty_score: Number.isFinite(Number(raw.novelty_score))
      ? Number(raw.novelty_score)
      : 0,
    root_pressures: rootPressures,
    chain_steps: resolvedChainSteps,
    turning_points: turningPoints,
    amplifiers: uniqueList(asArray(raw.amplifiers).map(String)),
    buffers: uniqueList(asArray(raw.buffers).map(String)),
    source_entity_uuids: uniqueList(scopeEntities.map(item => item.entity_uuid)),
    source_actor_ids: uniqueList(scopeActors.map(item => item.actor_id)),
    source_actor_names: uniqueList(scopeActors.map(item => item.actor_name)),
    evidence: asArray(raw.evidence),
    affected_clusters: asArray(raw.affected_clusters).map(normalizeClusterRef),
    intervention_options: interventionTemplates,
    scenario_branches: branchTemplates,
    edge_ids: collectRiskEdgeIds(raw, chainTemplate),
    scope_regions: scopeRegions,
    trigger_rules: raw.trigger_rules || {},
    priority_seed: prioritySeed,
    highlight_mode: 'risk_definition',
    source_kind: 'definition'
  }
}

function normalizeLegacyRiskObject(raw = {}, index = 0) {
  return {
    ...raw,
    risk_object_id: firstNonEmptyString(raw.risk_object_id, raw.risk_id, raw.id, `risk_legacy_${index + 1}`),
    risk_id: firstNonEmptyString(raw.risk_id, raw.risk_object_id, raw.id, `risk_legacy_${index + 1}`),
    title: firstNonEmptyString(raw.title, raw.name, `风险对象 ${index + 1}`),
    summary: firstNonEmptyString(raw.summary, raw.description, ''),
    why_now: firstNonEmptyString(raw.why_now, raw.summary, '等待风险对象摘要。'),
    risk_type: firstNonEmptyString(raw.risk_type, raw.category, 'legacy'),
    mode: firstNonEmptyString(raw.mode, 'watch'),
    status: firstNonEmptyString(raw.status, 'candidate'),
    time_horizon: firstNonEmptyString(raw.time_horizon, '30d'),
    region_scope: uniqueList([...asArray(raw.region_scope), ...asArray(raw.primary_regions)].map(String)),
    primary_regions: uniqueList(asArray(raw.primary_regions).map(String)).slice(0, 2),
    severity_score: normalizeScore(raw.severity_score),
    confidence_score: Number(raw.confidence_score || 0),
    actionability_score: normalizeScore(raw.actionability_score),
    novelty_score: normalizeScore(raw.novelty_score),
    root_pressures: uniqueList(asArray(raw.root_pressures).map(String)),
    chain_steps: uniqueList(asArray(raw.chain_steps).map(String)),
    turning_points: uniqueList(asArray(raw.turning_points).map(String)),
    amplifiers: uniqueList(asArray(raw.amplifiers).map(String)),
    buffers: uniqueList(asArray(raw.buffers).map(String)),
    source_entity_uuids: uniqueList(asArray(raw.source_entity_uuids).map(String)),
    source_actor_ids: uniqueList(asArray(raw.source_actor_ids).map(String)),
    source_actor_names: uniqueList(asArray(raw.source_actor_names).map(String)),
    evidence: asArray(raw.evidence),
    affected_clusters: asArray(raw.affected_clusters).map(normalizeClusterRef),
    intervention_options: asArray(raw.intervention_options),
    scenario_branches: asArray(raw.scenario_branches),
    edge_ids: uniqueList([...asArray(raw.edge_ids), ...asArray(raw.edgeIds)].map(String)),
    scope_regions: uniqueList([...asArray(raw.region_scope), ...asArray(raw.primary_regions)].map(String)).map(name => ({ region_id: name, region_name: name })),
    highlight_mode: 'legacy',
    source_kind: 'legacy'
  }
}

function resolveRiskDefinitions(source) {
  const definitions = asArray(source?.risk_definitions ?? source?.risk_definition_list ?? source?.risk_definition_items)
  if (definitions.length > 0) {
    return definitions.map((item, index) => normalizeRiskDefinition(item, index))
  }
  return []
}

function resolveLegacyRiskObjects(source) {
  const legacy = asArray(source?.risk_objects)
  if (legacy.length > 0) {
    return legacy.map((item, index) => normalizeLegacyRiskObject(item, index))
  }
  return []
}

const riskObjects = computed(() => {
  for (const source of riskSourceCandidates.value) {
    const definitions = resolveRiskDefinitions(source)
    if (definitions.length > 0) return definitions
  }

  for (const source of riskSourceCandidates.value) {
    const legacy = resolveLegacyRiskObjects(source)
    if (legacy.length > 0) return legacy
  }

  return []
})

const primaryRiskObjectId = computed(() => {
  for (const source of riskSourceCandidates.value) {
    const candidate = firstNonEmptyString(
      source?.primary_risk_definition_id,
      source?.primary_active_risk_id,
      source?.primary_risk_object_id,
      source?.primary_risk_id,
      source?.risk_definitions_summary?.primary_risk_id,
      source?.risk_objects_summary?.primary_risk_object_id,
      source?.primary_risk_object?.risk_object_id
    )
    if (candidate) return candidate
  }

  return riskObjects.value[0]?.risk_object_id || ''
})

const selectedRiskObject = computed(() => {
  if (riskObjects.value.length === 0) return null
  return riskObjects.value.find(item => item.risk_object_id === selectedRiskObjectId.value) || riskObjects.value[0]
})

const graphNodeByUuid = computed(() => {
  const map = new Map()
  graphNodes.value.forEach(node => {
    if (node?.uuid) {
      map.set(node.uuid, node)
    }
  })
  return map
})

const graphNodesByName = computed(() => {
  const map = new Map()
  graphNodes.value.forEach(node => {
    const name = String(node?.name || node?.label || '').trim().toLowerCase()
    if (!name) return
    if (!map.has(name)) {
      map.set(name, [])
    }
    map.get(name).push(node)
  })
  return map
})

const riskObjectEntityNodes = computed(() => {
  if (!selectedRiskObject.value) return []

  const evidenceByUuid = new Map()
  ;(selectedRiskObject.value.evidence || []).forEach(item => {
    ;(item.entity_refs || []).forEach(uuid => {
      if (uuid && !evidenceByUuid.has(uuid)) {
        evidenceByUuid.set(uuid, item)
      }
    })
  })

  const entityTokens = uniqueList([
    ...(selectedRiskObject.value.source_entity_uuids || []),
    ...(selectedRiskObject.value.source_actor_ids || []),
    ...(selectedRiskObject.value.source_actor_names || [])
  ])

  return entityTokens.map((token, index) => {
    const node = graphNodeByUuid.value.get(token) || graphNodesByName.value.get(String(token).toLowerCase())?.[0]
    const evidence = evidenceByUuid.get(token)
    return {
      id: node?.uuid || `risk-entity-${index}`,
      uuid: node?.uuid || token,
      name: node?.name || evidence?.title || token || `entity_${index + 1}`,
      labels: normalizeLabels(node?.labels),
      matched: Boolean(node)
    }
  })
})

const riskObjectRegionNodes = computed(() => {
  if (!selectedRiskObject.value) return []

  const scopeRegions = Array.isArray(selectedRiskObject.value.scope_regions) && selectedRiskObject.value.scope_regions.length > 0
    ? selectedRiskObject.value.scope_regions
    : uniqueList([
        ...(selectedRiskObject.value.primary_regions || []),
        ...(selectedRiskObject.value.region_scope || [])
      ]).map(name => ({ region_id: name, region_name: name }))

  return scopeRegions.map((ref, index) => {
    const regionName = firstNonEmptyString(ref.region_name, ref.region_id)
    const matched = [
      ...(graphNodesByName.value.get(regionName.toLowerCase()) || []),
      ...(ref.region_id ? graphNodesByName.value.get(String(ref.region_id).toLowerCase()) || [] : [])
    ]
    const node = matched[0]
    return {
      id: node?.uuid || `risk-region-${index}`,
      name: regionName,
      labels: normalizeLabels(node?.labels),
      matched: Boolean(node)
    }
  })
})

const riskObjectClusters = computed(() => {
  if (!selectedRiskObject.value || !Array.isArray(selectedRiskObject.value.affected_clusters)) return []
  return selectedRiskObject.value.affected_clusters
})

const riskObjectHighlightPayload = computed(() => {
  if (!selectedRiskObject.value) {
    return {
      label: '',
      riskObjectId: '',
      nodeIds: [],
      nodeNames: [],
      edgeIds: [],
      mode: ''
    }
  }

  return {
    label: selectedRiskObject.value.title || '',
    riskObjectId: selectedRiskObject.value.risk_object_id || '',
    nodeIds: uniqueList(riskObjectEntityNodes.value.map(item => item.uuid)),
    nodeNames: uniqueList([
      ...riskObjectEntityNodes.value.map(item => item.name),
      ...riskObjectRegionNodes.value.map(item => item.name)
    ]),
    edgeIds: uniqueList(selectedRiskObject.value.edge_ids || []),
    mode: selectedRiskObject.value.highlight_mode || selectedRiskObject.value.source_kind || selectedRiskObject.value.mode || 'risk_definition'
  }
})

const isReady = computed(() => phase.value === 'ready' || Boolean(configSnapshot.value))

const prepareStageLabel = computed(() => {
  if (phase.value === 'ready') return 'ready'
  if (phase.value === 'preparing') return prepareStage.value || 'preparing'
  if (phase.value === 'error') return 'failed'
  return 'idle'
})

const payloadPreview = computed(() => {
  return JSON.stringify({
    simulation_id: props.simulationId,
    engine_mode: 'envfish',
    scenario_mode: scenarioMode.value,
    diffusion_template: diffusionTemplate.value,
    search_mode: searchMode.value,
    temporal_profile: {
      preset: temporalPreset.value,
      total_rounds: maxRounds.value,
      minutes_per_round: configuredMinutesPerRound.value
    },
    reference_time: toIsoFromLocal(referenceTimeLocal.value),
    diffusion_provider: 'auto',
    max_rounds: maxRounds.value,
    spatial_grain: 'region',
    injected_variables: injectedVariables.value.map(serializeVariable)
  }, null, 2)
})

function resolvePhaseFromSnapshots() {
  const simulationStatus = String(simulationSnapshot.value?.status || '').toLowerCase()
  const realtimeMeta = configRealtime.value || {}
  const hasConfig = Boolean(configSnapshot.value) || Boolean(realtimeMeta.config) || Boolean(realtimeMeta.config_generated)

  if (hasConfig || ['ready', 'running', 'paused', 'stopped', 'completed'].includes(simulationStatus)) {
    return 'ready'
  }

  if (simulationStatus === 'failed') {
    return 'error'
  }

  if (realtimeMeta.is_generating || simulationStatus === 'preparing') {
    return 'preparing'
  }

  return 'idle'
}

function syncPhaseFromSnapshots() {
  phase.value = resolvePhaseFromSnapshots()

  if (phase.value === 'ready') {
    prepareProgress.value = 100
    if (!prepareMessage.value) {
      prepareMessage.value = '已存在可复用的场景配置'
    }
    return
  }

  if (phase.value === 'error') {
    prepareProgress.value = clamp(Number(prepareProgress.value) || 0, 0, 100)
    if (!prepareMessage.value) {
      prepareMessage.value = simulationSnapshot.value?.error || '场景配置生成失败'
    }
    return
  }

  if (phase.value === 'preparing') {
    prepareProgress.value = clamp(Number(prepareProgress.value) || 0, 0, 100)
    if (!prepareMessage.value) {
      prepareMessage.value = '正在准备场景配置'
    }
    return
  }

  prepareProgress.value = 0
  prepareStage.value = ''
  prepareMessage.value = '尚未开始生成场景配置'
}

function emitPhaseStatus(nextPhase = phase.value) {
  if (nextPhase === 'ready') {
    emit('update-status', 'completed')
    return
  }
  if (nextPhase === 'error') {
    emit('update-status', 'error')
    return
  }
  if (nextPhase === 'preparing') {
    emit('update-status', 'processing')
    return
  }
  emit('update-status', 'idle')
}

const addLog = (msg) => {
  emit('add-log', msg)
}

function createVariable(type = 'disaster') {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type,
    name: '',
    description: '',
    targetRegions: '',
    targetNodes: '',
    startRound: 0,
    durationRounds: 4,
    intensity: 70,
    policyMode: 'restrict'
  }
}

function serializeVariable(variable) {
  return {
    type: variable.type,
    name: variable.name || (variable.type === 'policy' ? 'policy_injection' : 'disaster_injection'),
    description: variable.description || '',
    target_regions: splitList(variable.targetRegions),
    target_nodes: splitList(variable.targetNodes),
    start_round: Number(variable.startRound) || 0,
    duration_rounds: Math.max(1, Number(variable.durationRounds) || 1),
    intensity: clamp(Number(variable.intensity) || 0, 0, 100),
    policy_mode: variable.type === 'policy' ? variable.policyMode : undefined
  }
}

function toIsoFromLocal(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toISOString()
}

function toDateTimeLocal(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (num) => String(num).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate())
  ].join('-') + `T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function splitList(value) {
  if (!value) return []
  return String(value)
    .split(/[,\n;]/)
    .map(item => item.trim())
    .filter(Boolean)
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value))
}

function normalizeScore(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return 0
  return Math.max(0, Math.min(100, Math.round(number)))
}

function formatPercent(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return 'n/a'
  if (number <= 1) return `${Math.round(number * 100)}%`
  return `${Math.round(Math.max(0, Math.min(100, number)))}%`
}

function formatInlineList(items, fallback = '—') {
  const values = uniqueList(Array.isArray(items) ? items : [])
  return values.length > 0 ? values.join(' · ') : fallback
}

function uniqueList(items) {
  return Array.from(
    new Set(
      (items || [])
        .map(item => String(item || '').trim())
        .filter(Boolean)
    )
  )
}

function normalizeLabels(labels) {
  return uniqueList(Array.isArray(labels) ? labels : []).slice(0, 3)
}

function collectGraphNodes(data) {
  if (!data) return []
  if (Array.isArray(data.nodes)) return data.nodes
  if (Array.isArray(data.graph?.nodes)) return data.graph.nodes
  if (Array.isArray(data.data?.nodes)) return data.data.nodes
  return []
}

function collectGraphEdges(data) {
  if (!data) return []
  if (Array.isArray(data.edges)) return data.edges
  if (Array.isArray(data.graph?.edges)) return data.graph.edges
  if (Array.isArray(data.data?.edges)) return data.data.edges
  return []
}

function getNodeLabel(node, fallback = '') {
  return node?.label || node?.name || node?.title || node?.entity_name || node?.username || fallback
}

function getNodeType(node) {
  const directType = node?.type || node?.entity_type || node?.category || node?.node_type
  const labelType = Array.isArray(node?.labels)
    ? node.labels.find(label => label && label !== 'Entity' && label !== 'Node')
    : ''
  const attrType =
    node?.attributes?.entity_type ||
    node?.attributes?.type ||
    node?.attributes?.category ||
    node?.attributes?.scene_type

  return String(directType || labelType || attrType || '').toLowerCase()
}

function categorizeNodes(nodes) {
  const grouped = {
    regions: [],
    human: [],
    organization: [],
    ecology: [],
    governance: [],
    infrastructure: []
  }

  nodes.forEach((node, index) => {
    const labels = Array.isArray(node?.labels) ? node.labels.map(label => String(label).toLowerCase()) : []
    const type = getNodeType(node)
    const rawType = [type, ...labels, node?.name, node?.label, node?.entity_type]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    const label = getNodeLabel(node, `node_${index}`)
    const normalized = { ...node, label }

    if (
      rawType.includes('region') ||
      rawType.includes('city') ||
      rawType.includes('district') ||
      rawType.includes('zone') ||
      rawType.includes('bay') ||
      rawType.includes('coast') ||
      rawType.includes('basin')
    ) {
      grouped.regions.push(normalized)
      return
    }

    if (
      rawType.includes('governmentactor') ||
      rawType.includes('regulator') ||
      rawType.includes('bureau') ||
      rawType.includes('authority') ||
      rawType.includes('agency') ||
      rawType.includes('office') ||
      rawType.includes('committee')
    ) {
      grouped.governance.push(normalized)
      return
    }

    if (
      rawType.includes('organizationactor') ||
      rawType.includes('ngo') ||
      rawType.includes('media') ||
      rawType.includes('school') ||
      rawType.includes('hospital') ||
      rawType.includes('company') ||
      rawType.includes('enterprise') ||
      rawType.includes('association') ||
      rawType.includes('organization')
    ) {
      grouped.organization.push(normalized)
      return
    }

    if (
      rawType.includes('resident') ||
      rawType.includes('fisher') ||
      rawType.includes('farmer') ||
      rawType.includes('consumer') ||
      rawType.includes('tourist') ||
      rawType.includes('humanactor') ||
      rawType.includes('residentgroup') ||
      rawType.includes('human')
    ) {
      grouped.human.push(normalized)
      return
    }

    if (
      rawType.includes('fish') ||
      rawType.includes('bird') ||
      rawType.includes('crop') ||
      rawType.includes('species') ||
      rawType.includes('eco') ||
      rawType.includes('receptor') ||
      rawType.includes('wetland') ||
      rawType.includes('mangrove')
    ) {
      grouped.ecology.push(normalized)
      return
    }

    if (
      rawType.includes('port') ||
      rawType.includes('market') ||
      rawType.includes('plant') ||
      rawType.includes('transport') ||
      rawType.includes('infra') ||
      rawType.includes('carrier') ||
      rawType.includes('current') ||
      rawType.includes('pipeline')
    ) {
      grouped.infrastructure.push(normalized)
      return
    }
  })

  return grouped
}

function normalizeKey(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, '')
}

function toList(value) {
  if (Array.isArray(value)) return value.filter(Boolean)
  if (!value) return []
  return [value]
}

function toDisplayString(value, fallback = '') {
  if (value === null || value === undefined) return fallback
  const text = String(value).trim()
  return text || fallback
}

function buildRegionLookup(records) {
  const map = new Map()
  ;(records || []).forEach((record) => {
    const keys = [
      record.regionKey,
      record.region_id,
      record.regionId,
      record.name,
      record.displayName,
      record.label
    ]
    keys.forEach((key) => {
      const normalized = normalizeKey(key)
      if (normalized) {
        map.set(normalized, record)
      }
    })
  })
  return map
}

function buildEntityLookup(nodes, agents = []) {
  const map = new Map()
  ;(nodes || []).forEach((node, index) => {
    const label = toDisplayString(getNodeLabel(node, `node_${index}`), `node_${index}`)
    const keys = [
      node?.id,
      node?.uuid,
      node?.node_id,
      node?.entity_uuid,
      node?.entity_id,
      node?.name,
      node?.label,
      node?.entity_name
    ]
    keys.forEach((key) => {
      const normalized = normalizeKey(key)
      if (normalized && !map.has(normalized)) {
        map.set(normalized, label)
      }
    })
  })
  ;(agents || []).forEach((agent, index) => {
    const label = toDisplayString(agent?.displayName || agent?.username || agent?.handle || `agent_${index}`, `agent_${index}`)
    const keys = [
      agent?.agentId,
      agent?.agent_id,
      agent?.agentKey,
      agent?.sourceEntityUuid,
      agent?.displayName,
      agent?.username,
      agent?.handle
    ]
    keys.forEach((key) => {
      const normalized = normalizeKey(key)
      if (normalized && !map.has(normalized)) {
        map.set(normalized, label)
      }
    })
  })
  return map
}

function resolveRegionLabel(value, lookup) {
  const normalized = normalizeKey(value)
  if (!normalized) return toDisplayString(value, 'Unknown region')
  const found = lookup.get(normalized)
  return found?.displayName || found?.name || found?.label || toDisplayString(value, 'Unknown region')
}

function resolveRegionKey(value, lookup) {
  const normalized = normalizeKey(value)
  if (!normalized) return ''
  const found = lookup.get(normalized)
  return found?.regionKey || found?.region_id || found?.regionId || normalized
}

function humanizeSnakeCase(value, fallback = '') {
  const text = toDisplayString(value, fallback)
  if (!text) return fallback
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function relationDisplayMeta(label) {
  const normalized = normalizeKey(label)
  const relationMap = {
    connects: {
      displayLabel: '连接',
      hint: '表示两者存在连接、流通或协作通道。'
    },
    dependson: {
      displayLabel: '依赖',
      hint: '表示前者的状态或活动依赖后者。'
    },
    regulates: {
      displayLabel: '监管',
      hint: '表示前者会对后者进行规制、约束或治理。'
    },
    affects: {
      displayLabel: '影响',
      hint: '表示前者会对后者造成影响。'
    },
    directlyaffects: {
      displayLabel: '直接影响',
      hint: '表示前者会直接改变后者状态。'
    },
    impactsorobserves: {
      displayLabel: '影响 / 观测',
      hint: '表示前者会影响后者，或持续观测后者状态。'
    },
    isatypeof: {
      displayLabel: '类型归属',
      hint: '表示前者属于后者这一类型。'
    },
    communitylink: {
      displayLabel: '同社区联动',
      hint: '表示同一区域内会互相传递观察、情绪和行动建议。'
    },
    trusts: {
      displayLabel: '信任',
      hint: '表示前者在信息或判断上依赖后者。'
    },
    overseenby: {
      displayLabel: '受监管',
      hint: '表示前者受后者监管或监督。'
    },
    locatedin: {
      displayLabel: '位于',
      hint: '表示前者处于后者区域或空间范围内。'
    },
    transmitsto: {
      displayLabel: '传导到',
      hint: '表示风险、信息或影响会从前者传到后者。'
    },
    flowsto: {
      displayLabel: '流向',
      hint: '表示物质、流体或影响从前者流向后者。'
    },
    carriessubstanceto: {
      displayLabel: '携带至',
      hint: '表示前者把物质或污染带到后者。'
    },
    regulatesoralters: {
      displayLabel: '调节 / 改变',
      hint: '表示前者的行动会直接改变后者的环境或状态。'
    },
    hasnormalcapacitywith: {
      displayLabel: '常态供给',
      hint: '表示前者在正常状态下与后者存在供给或容量联系。'
    },
    reportsto: {
      displayLabel: '上报 / 汇报',
      hint: '表示前者会向后者汇报情况或传递信息。'
    }
  }

  return relationMap[normalized] || {
    displayLabel: humanizeSnakeCase(label, '关系'),
    hint: '表示两个节点之间存在一条已知关系。'
  }
}

function bandFromScore(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return 'neutral'
  if (number >= 80) return 'critical'
  if (number >= 60) return 'watch'
  if (number >= 35) return 'stable'
  return 'calm'
}

function familyKeyFromText(value) {
  const text = String(value || '').toLowerCase()
  if (text.includes('government') || text.includes('gov') || text.includes('agency') || text.includes('bureau') || text.includes('authority') || text.includes('regulator') || text.includes('committee')) {
    return 'governance'
  }
  if (text.includes('organization') || text.includes('company') || text.includes('enterprise') || text.includes('media') || text.includes('ngo') || text.includes('school') || text.includes('hospital') || text.includes('association')) {
    return 'organization'
  }
  if (text.includes('eco') || text.includes('species') || text.includes('bird') || text.includes('fish') || text.includes('mangrove') || text.includes('seagull') || text.includes('reef') || text.includes('forest') || text.includes('wetland') || text.includes('carrier') || text.includes('river') || text.includes('air') || text.includes('ocean')) {
    return 'ecology'
  }
  if (text.includes('infra') || text.includes('port') || text.includes('road') || text.includes('plant') || text.includes('pipeline') || text.includes('transport') || text.includes('market')) {
    return 'infrastructure'
  }
  if (text.includes('region') || text.includes('district') || text.includes('coast') || text.includes('bay') || text.includes('zone')) {
    return 'region'
  }
  return 'human'
}

function familyLabel(key) {
  const labels = {
    human: '个体',
    organization: '组织',
    ecology: '生态',
    governance: '治理',
    infrastructure: '基础设施',
    region: '区域',
    other: '其他'
  }
  return labels[key] || labels.other
}

function pickArrayValue(...values) {
  for (const value of values) {
    if (Array.isArray(value) && value.length > 0) return value
  }
  return []
}

function summarizeStateVector(stateVector) {
  if (!stateVector || typeof stateVector !== 'object') return 'state n/a'
  const exposure = normalizeScore(stateVector.exposure_score)
  const trust = normalizeScore(stateVector.public_trust)
  const stress = normalizeScore(stateVector.economic_stress || stateVector.vulnerability_score)
  if (!exposure && !trust && !stress) return 'state n/a'
  return `E${exposure} · T${trust} · S${stress}`
}

function deriveStanceLabel(agent = {}) {
  const rawStance = toDisplayString(agent.stance_label || agent.stance || agent.stance_profile?.stance || agent.position, '').toLowerCase()
  if (rawStance) {
    if (rawStance.includes('opp')) return 'opposing'
    if (rawStance.includes('supp')) return 'supporting'
    if (rawStance.includes('obs')) return 'observer'
    if (rawStance.includes('neutral')) return 'neutral'
  }
  const bias = Number(agent.sentiment_bias ?? agent.stance_profile?.sentiment_bias ?? 0)
  if (Number.isFinite(bias)) {
    if (bias > 0.15) return 'supporting'
    if (bias < -0.15) return 'opposing'
  }
  return 'neutral'
}

function normalizeRegionRecords(rawRegions) {
  const source = Array.isArray(rawRegions) ? rawRegions : []
  if (source.length === 0) return []

  const baseRecords = source.map((region, index) => {
    const regionKey = normalizeKey(region?.region_id || region?.regionId || region?.id || region?.name || `region-${index}`)
    return {
      regionKey,
      region_id: toDisplayString(region?.region_id || region?.regionId || region?.id || regionKey, regionKey),
      displayName: toDisplayString(region?.name || region?.label || region?.title || regionKey, `Region ${index + 1}`),
      name: toDisplayString(region?.name || region?.label || region?.title || regionKey, `Region ${index + 1}`),
      regionTypeLabel: humanizeSnakeCase(region?.region_type || region?.subregion_type || region?.layer || 'region', 'Region'),
      layerLabel: region?.layer ? `Layer ${region.layer}` : 'Layer 1',
      subregionLabel: humanizeSnakeCase(region?.subregion_type || region?.land_use_class || region?.distance_band || region?.region_type || 'general', 'General'),
      summary: toDisplayString(region?.description || region?.summary || region?.notes || region?.tags?.[0], '暂无区域描述'),
      tags: uniqueList([
        ...(region?.tags || []),
        region?.land_use_class,
        region?.distance_band
      ]),
      carriers: uniqueList(region?.carriers || []),
      neighbors: uniqueList(region?.neighbors || []),
      stateVector: region?.state_vector || {},
      populationCapacity: region?.population_capacity ?? region?.populationCapacity ?? null,
      ecologyAssets: uniqueList(region?.ecology_assets || []),
      industryTags: uniqueList(region?.industry_tags || []),
      agentCount: Number(region?.agentCount || 0)
    }
  })

  const lookup = buildRegionLookup(baseRecords)

  return baseRecords.map((region) => ({
    ...region,
    neighbors: region.neighbors.map((item) => resolveRegionLabel(item, lookup)).filter(Boolean),
    neighborCount: region.neighbors.length
  }))
}

function normalizeRegionRecordsFromGraph(nodes) {
  const grouped = categorizeNodes(nodes)
  const regionNodes = grouped.regions || []
  if (regionNodes.length === 0) return []

  return regionNodes.map((node, index) => {
    const regionKey = normalizeKey(node?.uuid || node?.id || node?.name || node?.label || `graph-region-${index}`)
    return {
      regionKey,
      region_id: regionKey,
      displayName: toDisplayString(node?.label || node?.name || `Region ${index + 1}`, `Region ${index + 1}`),
      name: toDisplayString(node?.label || node?.name || `Region ${index + 1}`, `Region ${index + 1}`),
      regionTypeLabel: humanizeSnakeCase(node?.type || node?.entity_type || node?.category || 'region', 'Region'),
      layerLabel: 'Layer 1',
      subregionLabel: 'Graph node',
      summary: toDisplayString(node?.description || node?.summary || node?.label, '来自图谱的区域骨架'),
      tags: uniqueList(node?.tags || []),
      carriers: uniqueList(node?.carriers || []),
      neighbors: [],
      stateVector: node?.state_vector || {},
      populationCapacity: node?.population_capacity ?? null,
      ecologyAssets: uniqueList(node?.ecology_assets || []),
      industryTags: uniqueList(node?.industry_tags || []),
      agentCount: 0,
      neighborCount: 0
    }
  })
}

function inferAgentFamily(agent = {}) {
  const raw = [
    agent.agent_type,
    agent.node_family,
    agent.role_type,
    agent.profession,
    agent.entity_type,
    agent.name,
    agent.username
  ]
    .filter(Boolean)
    .join(' ')
  return familyKeyFromText(raw)
}

function resolvePrimaryRegion(agent = {}, regionLookup) {
  const candidates = toList(agent.primary_region || agent.home_region_id || agent.region_id || agent.region || agent.location)
  for (const candidate of candidates) {
    const normalized = normalizeKey(candidate)
    if (!normalized) continue
    const matched = regionLookup.get(normalized)
    if (matched) {
      return {
        key: matched.regionKey,
        label: matched.displayName
      }
    }
  }

  const fallbackValue = toDisplayString(candidates[0] || '', '')
  return {
    key: normalizeKey(fallbackValue),
    label: fallbackValue || 'Unknown region'
  }
}

function normalizeAgentRecords(config, regions) {
  const regionLookup = buildRegionLookup(regions)
  const sourceAgents = pickArrayValue(config?.agent_configs, config?.actor_profiles)
  if (sourceAgents.length === 0) return []

  return sourceAgents.map((agent, index) => {
    const family = inferAgentFamily(agent)
    const primaryRegion = resolvePrimaryRegion(agent, regionLookup)
    const influencedRegions = uniqueList(
      pickArrayValue(agent?.influenced_regions, agent?.influencedRegions).map((item) => resolveRegionLabel(item, regionLookup))
    )
    const goals = uniqueList(agent?.goals || [])
    const sensitivities = uniqueList(agent?.sensitivities || [])
    const displayName = toDisplayString(agent?.name || agent?.username || agent?.agent_name || agent?.entity_name || `Agent ${index + 1}`, `Agent ${index + 1}`)
    const agentKey = normalizeKey(agent?.agent_id || agent?.user_id || agent?.uuid || agent?.source_entity_uuid || agent?.username || displayName || `agent-${index}`)
    return {
      agentKey: agentKey || `agent-${index}`,
      agentId: agent?.agent_id ?? agent?.user_id ?? index,
      displayName,
      username: toDisplayString(agent?.username || agent?.agent_name || displayName, displayName),
      handle: agent?.username ? `@${agent.username}` : `@${normalizeKey(displayName) || `agent_${index + 1}`}`,
      agentTypeLabel: toDisplayString(agent?.agent_type || agent?.node_family || agent?.role_type || familyLabel(family), familyLabel(family)),
      familyKey: family,
      familyLabel: familyLabel(family),
      familyClass: family,
      roleTypeLabel: toDisplayString(agent?.role_type || agent?.profession || agent?.node_family || 'profile', 'profile'),
      sourceLabel: 'simulation config / 配置',
      summary: toDisplayString(agent?.bio || agent?.persona || agent?.summary, `${displayName} anchored in ${primaryRegion.label}`),
      bio: toDisplayString(agent?.bio || '', ''),
      persona: toDisplayString(agent?.persona || '', ''),
      profession: toDisplayString(agent?.profession || agent?.role_type || agent?.node_family || familyLabel(family), familyLabel(family)),
      primaryRegionKey: primaryRegion.key,
      primaryRegionLabel: primaryRegion.label,
      primaryRegionText: primaryRegion.label,
      influencedRegionKeys: uniqueList(agent?.influenced_regions || []).map((item) => normalizeKey(item)),
      influencedRegionLabels: influencedRegions,
      influencedRegionsCount: influencedRegions.length,
      goals,
      sensitivities,
      stateVector: agent?.state_vector || {},
      stateSignal: summarizeStateVector(agent?.state_vector || {}),
      stateBand: bandFromScore(agent?.state_vector?.vulnerability_score || agent?.state_vector?.exposure_score),
      stanceLabel: deriveStanceLabel(agent),
      sourceEntityUuid: agent?.source_entity_uuid || '',
      sourceEntityType: toDisplayString(agent?.source_entity_type || '', ''),
      isFallback: false
    }
  })
}

function normalizeAgentRecordsFromGraph(nodes, regions) {
  const grouped = categorizeNodes(nodes)
  const regionLookup = buildRegionLookup(regions)
  const categoryMap = [
    { key: 'human', items: grouped.human || [] },
    { key: 'organization', items: grouped.organization || [] },
    { key: 'ecology', items: grouped.ecology || [] },
    { key: 'governance', items: grouped.governance || [] },
    { key: 'infrastructure', items: grouped.infrastructure || [] }
  ]

  return categoryMap.flatMap(({ key, items }) => {
    return items.map((node, index) => {
      const displayName = toDisplayString(node?.label || node?.name || `Node ${index + 1}`, `Node ${index + 1}`)
      const regionSource = toDisplayString(node?.primary_region || node?.region || node?.location || '', '')
      const resolvedRegion = resolvePrimaryRegion({ primary_region: regionSource }, regionLookup)
      return {
        agentKey: normalizeKey(node?.uuid || node?.id || node?.name || displayName || `graph-agent-${key}-${index}`),
        agentId: index,
        displayName,
        username: toDisplayString(node?.username || node?.label || displayName, displayName),
        handle: `@${normalizeKey(displayName) || `graph_${index + 1}`}`,
        agentTypeLabel: familyLabel(key),
        familyKey: key,
        familyLabel: familyLabel(key),
        familyClass: key,
        roleTypeLabel: toDisplayString(node?.type || node?.entity_type || key, familyLabel(key)),
        sourceLabel: 'graph fallback / 图谱降级',
        summary: toDisplayString(node?.description || node?.summary || node?.label, `${displayName} synthesized from graph`),
        bio: toDisplayString(node?.description || node?.summary || '', ''),
        persona: '',
        profession: toDisplayString(node?.entity_type || node?.type || familyLabel(key), familyLabel(key)),
        primaryRegionKey: resolvedRegion.key,
        primaryRegionLabel: resolvedRegion.label,
        primaryRegionText: resolvedRegion.label,
        influencedRegionKeys: [],
        influencedRegionLabels: [],
        influencedRegionsCount: 0,
        goals: uniqueList(node?.tags || []).slice(0, 3),
        sensitivities: uniqueList(node?.labels || []).slice(0, 2),
        stateVector: node?.state_vector || {},
        stateSignal: summarizeStateVector(node?.state_vector || {}),
        stateBand: bandFromScore(node?.state_vector?.vulnerability_score || node?.state_vector?.exposure_score),
        stanceLabel: 'neutral',
        sourceEntityUuid: node?.uuid || node?.id || '',
        sourceEntityType: toDisplayString(node?.entity_type || node?.type || '', ''),
        isFallback: true
      }
    })
  })
}

function summarizeAgentCategories(agents) {
  return (agents || []).reduce((acc, agent) => {
    const key = agent?.familyKey || 'other'
    if (key in acc) {
      acc[key] += 1
    } else {
      acc.other += 1
    }
    return acc
  }, {
    human: 0,
    organization: 0,
    ecology: 0,
    governance: 0,
    infrastructure: 0,
    region: 0,
    other: 0
  })
}

function buildRegionAgentMap(regions, agents) {
  const regionLookup = buildRegionLookup(regions)
  return (regions || []).map((region) => {
    const regionKey = normalizeKey(region.regionKey || region.region_id || region.name || region.displayName)
    const matchingAgents = (agents || []).filter((agent) => {
      const primaryMatch = normalizeKey(agent.primaryRegionKey) === regionKey || normalizeKey(agent.primaryRegionLabel) === regionKey
      const influencedMatch = (agent.influencedRegionKeys || []).some((key) => key === regionKey)
      return primaryMatch || influencedMatch
    })
    const categorySummary = summarizeAgentCategories(matchingAgents)
    const topFamilies = [
      categorySummary.human ? familyLabel('human') : '',
      categorySummary.organization ? familyLabel('organization') : '',
      categorySummary.ecology ? familyLabel('ecology') : '',
      categorySummary.governance ? familyLabel('governance') : '',
      categorySummary.infrastructure ? familyLabel('infrastructure') : ''
    ].filter(Boolean).slice(0, 3)

    return {
      regionKey: region.regionKey,
      displayName: region.displayName,
      summary: matchingAgents.length > 0
        ? `${matchingAgents.length} agents anchored here`
        : region.summary,
      agentCount: matchingAgents.length,
      topFamilies,
      neighbors: region.neighbors,
      neighborCount: region.neighborCount,
      regionTypeLabel: region.regionTypeLabel,
      layerLabel: region.layerLabel,
      subregionLabel: region.subregionLabel,
      tags: region.tags,
      carriers: region.carriers,
      stateVector: region.stateVector,
      primaryRegionLabel: resolveRegionLabel(region.regionKey, regionLookup)
    }
  })
}

function getEdgeLabel(edge) {
  return toDisplayString(
    edge?.relation_type || edge?.label || edge?.relation || edge?.relationship || edge?.type || edge?.name || edge?.kind,
    'unlabeled'
  )
}

function getEdgeEndpoint(edge, prefixes, lookup) {
  for (const prefix of prefixes) {
    const candidates = [
      edge?.[`${prefix}_name`],
      edge?.[`${prefix}Name`],
      edge?.[`${prefix}_label`],
      edge?.[`${prefix}Label`],
      edge?.[`${prefix}_title`],
      edge?.[`${prefix}Title`],
      edge?.[`${prefix}_entity_name`],
      edge?.[`${prefix}EntityName`],
      edge?.[`${prefix}_agent_name`],
      edge?.[`${prefix}AgentName`],
      edge?.[`${prefix}_agent_id`],
      edge?.[`${prefix}AgentId`],
      edge?.[`${prefix}_id`],
      edge?.[`${prefix}Id`]
    ]
    for (const candidate of candidates) {
      const normalized = normalizeKey(candidate)
      if (!normalized) continue
      const lookupValue = lookup.get(normalized)
      return lookupValue || toDisplayString(candidate, '')
    }
  }
  return ''
}

function summarizeRelations(edges) {
  const lookup = buildEntityLookup(graphNodes.value, agentCards.value)
  const labelCounts = new Map()
  const channelCounts = new Map()
  const sampleEdges = []
  let crossRegionCount = 0

  ;(edges || []).forEach((edge, index) => {
    const label = getEdgeLabel(edge)
    const relationMeta = relationDisplayMeta(label)
    labelCounts.set(label, (labelCounts.get(label) || 0) + 1)
    const channel = toDisplayString(edge?.interaction_channel || edge?.channel || edge?.interactionChannel, '')
    if (channel) {
      channelCounts.set(channel, (channelCounts.get(channel) || 0) + 1)
    }
    if (
      edge?.source_region_id &&
      edge?.target_region_id &&
      normalizeKey(edge.source_region_id) !== normalizeKey(edge.target_region_id)
    ) {
      crossRegionCount += 1
    }
    if (sampleEdges.length < 6) {
      const source = getEdgeEndpoint(edge, ['source', 'from', 'head'], lookup)
      const target = getEdgeEndpoint(edge, ['target', 'to', 'tail'], lookup)
      const channelLabel = humanizeSnakeCase(channel, 'general')
      sampleEdges.push({
        key: `${label}-${index}`,
        label,
        displayLabel: relationMeta.displayLabel,
        hint: relationMeta.hint,
        summary: source && target
          ? `${source} ${relationMeta.displayLabel} ${target}`
          : source || target || '关系边',
        rationale: toDisplayString(edge?.rationale || '', ''),
        channelLabel,
        strengthLabel: Number.isFinite(Number(edge?.strength)) ? Number(edge.strength).toFixed(2) : ''
      })
    }
  })

  return {
    total: (edges || []).length,
    crossRegionCount,
    channels: Array.from(channelCounts.entries())
      .map(([label, count]) => ({ label, count, displayLabel: humanizeSnakeCase(label, 'General') }))
      .sort((left, right) => right.count - left.count),
    types: Array.from(labelCounts.entries())
      .map(([label, count]) => ({
        label,
        count,
        ...relationDisplayMeta(label)
      }))
      .sort((left, right) => right.count - left.count),
    sampleEdges
  }
}

function addVariable(type = 'disaster') {
  injectedVariables.value.push(createVariable(type))
}

function removeVariable(id) {
  if (injectedVariables.value.length === 1) return
  injectedVariables.value = injectedVariables.value.filter(variable => variable.id !== id)
}

async function bootstrapSimulation() {
  if (!props.simulationId) return

  try {
    const [simulationRes, configRes, realtimeRes] = await Promise.allSettled([
      getSimulation(props.simulationId),
      getSimulationConfig(props.simulationId),
      getSimulationConfigRealtime(props.simulationId)
    ])

    if (simulationRes.status === 'fulfilled' && simulationRes.value?.success) {
      simulationSnapshot.value = simulationRes.value.data || null
      if (simulationSnapshot.value?.scenario_mode) scenarioMode.value = simulationSnapshot.value.scenario_mode
      if (simulationSnapshot.value?.diffusion_template) diffusionTemplate.value = simulationSnapshot.value.diffusion_template
      if (simulationSnapshot.value?.search_mode) searchMode.value = simulationSnapshot.value.search_mode
      if (simulationSnapshot.value?.temporal_preset) temporalPreset.value = simulationSnapshot.value.temporal_preset
      if (simulationSnapshot.value?.configured_minutes_per_round) {
        configuredMinutesPerRound.value = Number(simulationSnapshot.value.configured_minutes_per_round) || configuredMinutesPerRound.value
      }
      if (simulationSnapshot.value?.configured_total_rounds) {
        maxRounds.value = Number(simulationSnapshot.value.configured_total_rounds) || maxRounds.value
      }
      if (simulationSnapshot.value?.reference_time) referenceTimeLocal.value = toDateTimeLocal(simulationSnapshot.value.reference_time)
    }

    if (configRes.status === 'fulfilled' && configRes.value?.success && configRes.value.data) {
      configSnapshot.value = configRes.value.data
      if (configRes.value.data.scenario_mode) scenarioMode.value = configRes.value.data.scenario_mode
      if (configRes.value.data.diffusion_template) diffusionTemplate.value = configRes.value.data.diffusion_template
      if (configRes.value.data.search_mode) searchMode.value = configRes.value.data.search_mode
      if (configRes.value.data.temporal_profile?.preset) temporalPreset.value = configRes.value.data.temporal_profile.preset
      if (configRes.value.data.temporal_profile?.minutes_per_round) {
        configuredMinutesPerRound.value = Number(configRes.value.data.temporal_profile.minutes_per_round) || configuredMinutesPerRound.value
      }
      if (configRes.value.data.temporal_profile?.total_rounds) {
        maxRounds.value = Number(configRes.value.data.temporal_profile.total_rounds) || maxRounds.value
      }
      if (configRes.value.data.reference_time) referenceTimeLocal.value = toDateTimeLocal(configRes.value.data.reference_time)
    }

    if (realtimeRes.status === 'fulfilled' && realtimeRes.value?.success && realtimeRes.value.data) {
      configRealtime.value = realtimeRes.value.data
      if (realtimeRes.value.data.generation_stage) {
        prepareStage.value = realtimeRes.value.data.generation_stage
      }
      if (realtimeRes.value.data.progress !== undefined) {
        prepareProgress.value = realtimeRes.value.data.progress
      }
      if (realtimeRes.value.data.search_mode) {
        searchMode.value = realtimeRes.value.data.search_mode
      }
      if (realtimeRes.value.data.temporal_profile?.preset) temporalPreset.value = realtimeRes.value.data.temporal_profile.preset
      if (realtimeRes.value.data.temporal_profile?.minutes_per_round) {
        configuredMinutesPerRound.value = Number(realtimeRes.value.data.temporal_profile.minutes_per_round) || configuredMinutesPerRound.value
      }
      if (realtimeRes.value.data.temporal_profile?.total_rounds) {
        maxRounds.value = Number(realtimeRes.value.data.temporal_profile.total_rounds) || maxRounds.value
      }
      if (realtimeRes.value.data.reference_time) referenceTimeLocal.value = toDateTimeLocal(realtimeRes.value.data.reference_time)
    }

    syncPhaseFromSnapshots()
    if (phase.value === 'preparing') {
      startTimers()
    }
  } catch (err) {
    addLog(`加载场景上下文失败: ${err.message}`)
  }
}

function startTimers(taskId = '') {
  stopTimers()
  prepareTaskId.value = taskId
  progressTimer = setInterval(pollPrepareStatus, 2000)
  configTimer = setInterval(fetchConfigRealtime, 2500)
}

function stopTimers() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
  if (configTimer) {
    clearInterval(configTimer)
    configTimer = null
  }
}

async function handlePrepare(options = {}) {
  if (!props.simulationId || isPreparing.value) return

  const autoTriggered = Boolean(options.auto)

  isPreparing.value = true
  phase.value = 'preparing'
  prepareProgress.value = 0
  prepareMessage.value = autoTriggered ? '正在自动生成正式 Agent 配置' : '正在提交 EnvFish 场景配置'
  emit('update-status', 'processing')
  addLog(
    `${autoTriggered ? '自动' : '手动'}提交 EnvFish 场景配置: ${scenarioMode.value} / ${diffusionTemplate.value} / ${searchMode.value} / ${temporalProfileLabel.value}`
  )

  try {
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      engine_mode: 'envfish',
      scenario_mode: scenarioMode.value,
      diffusion_template: diffusionTemplate.value,
      search_mode: searchMode.value,
      temporal_preset: temporalPreset.value,
      temporal_profile: {
        preset: temporalPreset.value,
        total_rounds: maxRounds.value,
        minutes_per_round: configuredMinutesPerRound.value
      },
      reference_time: toIsoFromLocal(referenceTimeLocal.value),
      diffusion_provider: 'auto',
      minutes_per_round: configuredMinutesPerRound.value,
      max_rounds: maxRounds.value,
      region_granularity: 'region',
      injected_variables: injectedVariables.value.map(serializeVariable)
    })

    if (res.success && res.data) {
      if (res.data.temporal_profile?.minutes_per_round) {
        configuredMinutesPerRound.value = Number(res.data.temporal_profile.minutes_per_round) || configuredMinutesPerRound.value
      }
      if (res.data.already_prepared) {
        phase.value = 'ready'
        prepareProgress.value = 100
        prepareMessage.value = '检测到已完成的场景配置'
        addLog('✓ 场景配置已存在，直接复用')
        await bootstrapSimulation()
      } else {
        prepareTaskId.value = res.data.task_id || ''
        addLog(`✓ 准备任务已启动${prepareTaskId.value ? `: ${prepareTaskId.value}` : ''}`)
        if (res.data.expected_entities_count) {
          addLog(`预期角色/节点数: ${res.data.expected_entities_count}`)
        }
        startTimers(prepareTaskId.value)
        await fetchConfigRealtime()
      }
    } else {
      phase.value = 'error'
      emit('update-status', 'error')
      addLog(`✗ 场景配置提交失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    phase.value = 'error'
    emit('update-status', 'error')
    addLog(`✗ 场景配置异常: ${err.message}`)
  } finally {
    isPreparing.value = false
  }
}

async function pollPrepareStatus() {
  if (!props.simulationId) return

  try {
    const res = await getPrepareStatus({
      simulation_id: props.simulationId,
      task_id: prepareTaskId.value || undefined
    })

    if (res.success && res.data) {
      const data = res.data
      if (data.progress !== undefined) prepareProgress.value = clamp(Number(data.progress) || 0, 0, 100)
      if (data.message) prepareMessage.value = data.message
      if (data.progress_detail?.current_stage_name) {
        prepareStage.value = data.progress_detail.current_stage_name
      } else if (data.current_stage_name) {
        prepareStage.value = data.current_stage_name
      }

      if (data.status === 'completed' || data.already_prepared) {
        phase.value = 'ready'
        prepareProgress.value = 100
        prepareMessage.value = '场景配置已完成'
        emit('update-status', 'completed')
        addLog('✓ EnvFish 场景配置完成')
        stopTimers()
        await fetchConfigRealtime()
      } else if (data.status === 'failed') {
        phase.value = 'error'
        emit('update-status', 'error')
        addLog(`✗ 场景配置失败: ${data.error || '未知错误'}`)
        stopTimers()
      } else if (data.status === 'not_started') {
        phase.value = 'idle'
        prepareProgress.value = 0
        prepareMessage.value = data.message || '尚未开始生成场景配置'
        prepareStage.value = ''
        stopTimers()
      }
    }
  } catch (err) {
    console.warn('poll prepare failed', err)
  }
}

async function fetchConfigRealtime() {
  if (!props.simulationId) return

  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res.success && res.data) {
      configRealtime.value = res.data
      if (res.data.generation_stage) prepareStage.value = res.data.generation_stage
      if (res.data.progress !== undefined) prepareProgress.value = clamp(Number(res.data.progress) || 0, 0, 100)
      if (res.data.message) prepareMessage.value = res.data.message
      if (res.data.scenario_mode) scenarioMode.value = res.data.scenario_mode
      if (res.data.diffusion_template) diffusionTemplate.value = res.data.diffusion_template
      if (res.data.search_mode) searchMode.value = res.data.search_mode
      if (res.data.temporal_profile?.preset) temporalPreset.value = res.data.temporal_profile.preset
      if (res.data.temporal_profile?.minutes_per_round) {
        configuredMinutesPerRound.value = Number(res.data.temporal_profile.minutes_per_round) || configuredMinutesPerRound.value
      }
      if (res.data.temporal_profile?.total_rounds) {
        maxRounds.value = Number(res.data.temporal_profile.total_rounds) || maxRounds.value
      }
      if (res.data.reference_time) referenceTimeLocal.value = toDateTimeLocal(res.data.reference_time)
      syncPhaseFromSnapshots()
    }
  } catch (err) {
    console.warn('fetch config realtime failed', err)
  }
}

function handleNextStep() {
  emit('next-step', {
    scenarioMode: scenarioMode.value,
    diffusionTemplate: diffusionTemplate.value,
    searchMode: searchMode.value,
    temporalPreset: temporalPreset.value,
    minutesPerRound: configuredMinutesPerRound.value,
    referenceTime: toIsoFromLocal(referenceTimeLocal.value),
    maxRounds: maxRounds.value,
    variableCount: injectedVariables.value.length,
    injectedVariables: injectedVariables.value.map(serializeVariable)
  })
}

watch(
  () => props.initialScenarioMode,
  (value) => {
    if (value) scenarioMode.value = value
  }
)

watch(
  () => props.initialDiffusionTemplate,
  (value) => {
    if (value) diffusionTemplate.value = value
  }
)

watch(
  () => props.initialSearchMode,
  (value) => {
    if (value) searchMode.value = value
  }
)

watch(
  temporalPreset,
  (value) => {
    const matched = temporalProfiles.find(profile => profile.value === value)
    if (matched) {
      configuredMinutesPerRound.value = matched.minutes
    }
  },
  { immediate: true }
)

watch(
  [riskObjects, primaryRiskObjectId],
  ([items, primaryId]) => {
    if (!items.length) {
      selectedRiskObjectId.value = ''
      return
    }

    const hasSelected = items.some(item => item.risk_object_id === selectedRiskObjectId.value)
    if (hasSelected) return

    const fallback = items.some(item => item.risk_object_id === primaryId)
      ? primaryId
      : items[0].risk_object_id

    selectedRiskObjectId.value = fallback
  },
  { immediate: true }
)

watch(
  riskObjectHighlightPayload,
  (payload) => {
    emit('risk-object-focus', payload)
  },
  { immediate: true, deep: true }
)

watch(
  phase,
  (value) => {
    emitPhaseStatus(value)
  }
)

onMounted(async () => {
  addLog('EnvFish Step2 初始化')
  await bootstrapSimulation()
  if (props.simulationId) emitPhaseStatus()
  if (props.simulationId && phase.value === 'idle' && !autoPrepareAttempted.value) {
    autoPrepareAttempted.value = true
    handlePrepare({ auto: true })
  }
})

onUnmounted(() => {
  stopTimers()
})
</script>

<style scoped>
.envfish-step {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
  overflow: auto;
  background:
    radial-gradient(circle at top left, rgba(88, 159, 255, 0.18), transparent 32%),
    radial-gradient(circle at top right, rgba(28, 196, 135, 0.16), transparent 30%),
    linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
  color: #132033;
}

.hero,
.workspace-shell,
.progress-shell,
.log-shell {
  border: 1px solid rgba(20, 33, 61, 0.08);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
  box-shadow: 0 12px 32px rgba(17, 31, 59, 0.06);
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  border-radius: 24px;
  padding: 20px 22px;
}

.eyebrow {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.2em;
  color: #5d78a7;
}

.hero h2 {
  margin: 10px 0 8px;
  font-size: 28px;
  line-height: 1.1;
}

.hero p {
  margin: 0;
  max-width: 680px;
  color: #5d687f;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 10px;
  min-width: 280px;
}

.metric-card,
.summary-card {
  border-radius: 18px;
  padding: 12px 14px;
  background: linear-gradient(180deg, rgba(245, 248, 255, 0.98), rgba(235, 242, 255, 0.86));
  border: 1px solid rgba(97, 125, 175, 0.14);
}

.metric-label,
.summary-card span,
.hint,
.catalog-title {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7382a3;
}

.metric-value {
  display: block;
  margin-top: 8px;
  font-size: 17px;
  font-weight: 800;
  color: #183058;
}

.workspace-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: none;
  border-radius: 24px;
  padding: 18px;
  overflow: visible;
}

.workspace-topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.workspace-copy {
  max-width: 560px;
}

.workspace-eyebrow {
  margin-bottom: 8px;
}

.workspace-copy h3 {
  margin: 0;
  font-size: 22px;
  color: #183058;
}

.workspace-copy p {
  margin: 8px 0 0;
  color: #5d687f;
  line-height: 1.5;
  font-size: 13px;
}

.workspace-tabs {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.workspace-tab {
  min-width: 150px;
  text-align: left;
  border-radius: 18px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  background: linear-gradient(180deg, rgba(248, 250, 255, 0.96), rgba(239, 244, 255, 0.92));
  padding: 12px 14px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}

.workspace-tab:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(31, 57, 98, 0.08);
}

.workspace-tab.active {
  border-color: rgba(47, 110, 255, 0.36);
  background: linear-gradient(180deg, rgba(238, 244, 255, 1), rgba(224, 235, 255, 0.96));
  box-shadow: 0 10px 24px rgba(31, 57, 98, 0.1);
}

.workspace-tab-label,
.workspace-tab-meta {
  display: block;
}

.workspace-tab-label {
  font-size: 14px;
  font-weight: 800;
  color: #183058;
}

.workspace-tab-meta {
  margin-top: 6px;
  font-size: 11px;
  color: #7382a3;
  letter-spacing: 0.04em;
}

.panel {
  border-radius: 22px;
  padding: 18px;
  overflow: auto;
  border: 1px solid rgba(20, 33, 61, 0.08);
  background: linear-gradient(180deg, rgba(250, 252, 255, 0.96), rgba(239, 245, 255, 0.82));
}

.workspace-panel {
  flex: none;
  min-height: 360px;
}

.panel-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-title-row h3 {
  margin: 0;
  font-size: 16px;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.mode-card,
.template-card {
  text-align: left;
  border-radius: 18px;
  border: 1px solid rgba(20, 33, 61, 0.1);
  background: linear-gradient(180deg, #fff, #f3f7ff);
  padding: 14px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.mode-card:hover,
.template-card:hover,
.ghost-btn:hover,
.secondary-btn:hover,
.primary-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(31, 57, 98, 0.1);
}

.mode-card.active,
.template-card.active {
  border-color: rgba(47, 110, 255, 0.55);
  background: linear-gradient(180deg, rgba(240, 245, 255, 1), rgba(227, 237, 255, 0.95));
}

.mode-tag,
.template-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(48, 89, 178, 0.1);
  color: #3357a8;
}

.mode-name,
.template-name {
  display: block;
  margin-top: 8px;
  font-weight: 800;
}

.mode-card p,
.template-card p,
.progress-note,
.grounding-box p {
  margin: 8px 0 0;
  color: #5e6782;
  line-height: 1.5;
  font-size: 13px;
}

.slider-shell {
  margin: 18px 0 16px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(240, 244, 252, 0.8);
  border: 1px solid rgba(20, 33, 61, 0.08);
}

.range {
  width: 100%;
  margin-top: 10px;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 11px;
  color: #7b86a3;
}

.field-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #4d5874;
}

input,
select,
textarea {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(20, 33, 61, 0.12);
  background: #fff;
  color: #132033;
  padding: 10px 12px;
  font: inherit;
}

textarea {
  resize: vertical;
}

.variable-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.variable-card {
  border-radius: 18px;
  padding: 14px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  background: linear-gradient(180deg, #ffffff, #f7faff);
}

.variable-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.variable-index {
  display: inline-flex;
  margin-right: 8px;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(43, 94, 215, 0.08);
  color: #2e5cc8;
  font-size: 10px;
  font-weight: 800;
}

.remove-btn,
.ghost-btn,
.secondary-btn,
.primary-btn {
  border: none;
  border-radius: 14px;
  padding: 10px 14px;
  font-weight: 700;
  cursor: pointer;
}

.remove-btn,
.ghost-btn,
.secondary-btn {
  background: rgba(24, 48, 88, 0.06);
  color: #213553;
}

.primary-btn {
  background: linear-gradient(135deg, #113a7a, #2f76f1);
  color: #fff;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.summary-card.compact {
  min-width: 132px;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 18px;
  color: #16315a;
}

.catalog {
  margin-top: 14px;
}

.chip-wrap,
.grounding-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip,
.grounding-item,
.empty-chip {
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  background: rgba(28, 68, 154, 0.08);
  color: #21427d;
}

.grounding-box,
.payload-box {
  border-radius: 18px;
  padding: 14px;
  background: rgba(242, 246, 255, 0.72);
  border: 1px solid rgba(20, 33, 61, 0.08);
}

.payload-box pre {
  margin: 10px 0 0;
  max-height: 220px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.5;
  color: #24314a;
  white-space: pre-wrap;
}

.region-grid,
.agent-grid,
.relation-grid {
  display: grid;
  gap: 12px;
}

.region-grid,
.relation-grid {
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.agent-grid {
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

.region-card,
.relation-card {
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(20, 33, 61, 0.08);
  box-shadow: 0 8px 20px rgba(17, 31, 59, 0.04);
}

.region-card p,
.relation-card p {
  margin: 8px 0 0;
  color: #5e6782;
  line-height: 1.5;
  font-size: 13px;
}

.region-card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.region-card-index {
  display: inline-flex;
  margin-bottom: 6px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(47, 110, 255, 0.08);
  color: #2d5be3;
  font-size: 10px;
  font-weight: 800;
}

.region-card-type {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 8px;
  background: rgba(24, 48, 88, 0.06);
  color: #5d687f;
  font-size: 10px;
  font-weight: 700;
}

.region-card strong,
.relation-card strong {
  color: #16315a;
  font-size: 15px;
}

.region-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 12px 0 10px;
}

.region-card-meta span {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 5px 8px;
  background: rgba(47, 110, 255, 0.08);
  color: #3357a8;
  font-size: 11px;
  font-weight: 700;
}

.chip-soft {
  background: rgba(28, 196, 135, 0.08);
  color: #13805c;
}

.agent-group-chip {
  background: rgba(24, 48, 88, 0.06);
  color: #213553;
}

.relation-edge-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.relation-edge-row {
  display: grid;
  grid-template-columns: minmax(160px, auto) 1fr;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(20, 33, 61, 0.06);
}

.relation-edge-row strong {
  color: #16315a;
  font-size: 12px;
}

.relation-edge-row span {
  color: #5d687f;
  font-size: 12px;
}

.relation-edge-row small {
  grid-column: 2;
  color: #7b86a0;
  font-size: 11px;
  line-height: 1.4;
}

.risk-preview-shell {
  border-radius: 24px;
  padding: 16px 18px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(10px);
  box-shadow: 0 12px 32px rgba(17, 31, 59, 0.06);
}

.risk-preview-grid {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 14px;
}

.risk-preview-list,
.node-list,
.cluster-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.risk-preview-card {
  width: 100%;
  text-align: left;
  border-radius: 18px;
  border: 1px solid rgba(20, 33, 61, 0.1);
  background: linear-gradient(180deg, #fff, #f4f8ff);
  padding: 14px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.risk-preview-card:hover,
.risk-preview-card.active {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(31, 57, 98, 0.08);
  border-color: rgba(47, 110, 255, 0.32);
}

.risk-preview-card.active {
  background: linear-gradient(180deg, rgba(240, 245, 255, 1), rgba(227, 237, 255, 0.95));
}

.risk-preview-head,
.risk-detail-top,
.risk-score-strip,
.node-card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.risk-mode-tag,
.risk-primary-tag,
.node-state,
.mini-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 700;
}

.risk-mode-tag {
  background: rgba(48, 89, 178, 0.1);
  color: #3357a8;
}

.risk-primary-tag {
  background: rgba(28, 196, 135, 0.12);
  color: #13805c;
}

.risk-preview-card strong,
.risk-preview-detail h3 {
  display: block;
  margin-top: 8px;
  color: #16315a;
}

.risk-preview-card p,
.risk-preview-detail p,
.cluster-mini-card p {
  margin: 8px 0 0;
  color: #5e6782;
  line-height: 1.5;
  font-size: 13px;
}

.risk-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.risk-meta span,
.mini-tag.accent {
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(24, 48, 88, 0.06);
  color: #213553;
  font-size: 12px;
}

.risk-preview-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-eyebrow {
  color: #4f69a5;
}

.risk-note-box,
.risk-mini-panel {
  border-radius: 18px;
  padding: 14px;
  background: rgba(242, 246, 255, 0.72);
  border: 1px solid rgba(20, 33, 61, 0.08);
}

.risk-note-box span {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7382a3;
}

.risk-note-box strong {
  display: block;
  margin-top: 8px;
  color: #183058;
  line-height: 1.5;
}

.risk-step-list,
.tag-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.risk-step-list {
  margin-top: 2px;
}

.risk-node-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.risk-node-grid.secondary {
  align-items: start;
}

.node-card,
.cluster-mini-card {
  border-radius: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(20, 33, 61, 0.08);
}

.node-state {
  background: rgba(123, 134, 163, 0.12);
  color: #6a7897;
}

.node-state.matched {
  background: rgba(47, 110, 255, 0.12);
  color: #2d5be3;
}

.mini-tag {
  background: rgba(48, 89, 178, 0.08);
  color: #3357a8;
}

.empty-state {
  padding: 14px;
  border-radius: 16px;
  background: rgba(24, 48, 88, 0.04);
  color: #65728f;
  font-size: 13px;
}

.bullet-list {
  margin: 0;
  padding-left: 18px;
  color: #4d5874;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.progress-shell {
  border-radius: 24px;
  padding: 16px 18px;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.progress-score {
  font-size: 22px;
  font-weight: 900;
  color: #183058;
}

.progress-bar {
  height: 10px;
  border-radius: 999px;
  background: rgba(22, 44, 88, 0.08);
  overflow: hidden;
  margin-top: 12px;
}

.progress-bar-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2d5be3, #35c98b);
  transition: width 0.25s ease;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.log-shell {
  border-radius: 24px;
  padding: 16px 18px;
  min-height: 0;
}

.logs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 180px;
  overflow: auto;
  padding-right: 4px;
}

.log-line {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 10px;
  font-size: 12px;
  color: #31425f;
}

.log-time {
  color: #7b86a3;
  font-family: monospace;
}

.log-msg {
  line-height: 1.45;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

@media (max-width: 1280px) {
  .risk-preview-grid,
  .risk-node-grid {
    grid-template-columns: 1fr;
  }

  .hero,
  .workspace-topbar {
    flex-direction: column;
  }

  .workspace-tabs {
    width: 100%;
    justify-content: flex-start;
  }

  .workspace-tab {
    flex: 1 1 180px;
  }

  .workspace-panel {
    min-height: 300px;
  }
}
</style>
