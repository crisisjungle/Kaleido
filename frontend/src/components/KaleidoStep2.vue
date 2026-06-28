<template>
  <div class="envfish-step envfish-step2">
    <section class="workspace-shell">
      <!-- 场景简报：一句话讲清整个场景 + 常驻"进入推演" -->
      <header class="briefing-header">
        <div class="briefing-head-copy">
          <div class="briefing-kicker">场景简报</div>
          <h2 class="briefing-title">{{ hazardTemplateMeta.label }}</h2>
          <p class="briefing-summary-line">{{ sceneSummaryLine }}</p>
        </div>
        <button class="primary-btn briefing-cta" :disabled="!isReady" @click="handleNextStep">进入推演 →</button>
      </header>

      <div class="briefing-stats">
        <span class="briefing-stats-label">系统从你的背景生成了这个场景</span>
        <div class="briefing-stat-row">
          <div class="briefing-stat"><strong>{{ riskObjects.length }}</strong><span>风险对象</span></div>
          <div class="briefing-stat"><strong>{{ regionRecords.length }}</strong><span>区域</span></div>
          <div class="briefing-stat"><strong>{{ agentCards.length }}</strong><span>代理体</span></div>
          <div class="briefing-stat"><strong>{{ relationSummary.total }}</strong><span>关系</span></div>
        </div>
      </div>

      <section
        class="briefing-section bsec-parameters panel workspace-panel parameters"
        :class="{ collapsed: !isExpanded('parameters') }"
      >
        <div class="panel-title-row briefing-head" @click="toggleSection('parameters')">
          <h3>推演参数</h3>
          <span class="hint">{{ paramsSummaryLine }}</span>
          <i class="bh-chev" aria-hidden="true">⌄</i>
        </div>

        <div class="grounding-box parameter-lock-note">
          <p>{{ parameterIntroCopy }}</p>
        </div>

        <div class="catalog">
          <div class="panel-title-row">
            <h3>时间计划</h3>
            <span class="hint">{{ timePlanMode === 'manual' ? '已微调' : '自动推荐' }}</span>
          </div>
          <div class="summary-grid">
            <div class="summary-card">
              <span>每轮步长</span>
              <strong>{{ temporalProfileLabel }}</strong>
            </div>
            <div class="summary-card">
              <span>推演轮次</span>
              <strong>{{ maxRounds }}</strong>
            </div>
            <div class="summary-card">
              <span>总覆盖时长</span>
              <strong>{{ totalCoverageLabel }}</strong>
            </div>
            <div class="summary-card">
              <span>参考时间</span>
              <strong>当前时间</strong>
            </div>
          </div>
          <div class="field-row">
            <label>
              步长单位
              <select v-model="timeStepUnit" :disabled="!canEditParameters" @change="markTimePlanManual">
                <option v-for="option in timePlanUnitOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label>
              每轮步长
              <input v-model.number="timeStepSize" type="number" min="1" :disabled="!canEditParameters" @input="markTimePlanManual" />
            </label>
            <label>
              推演轮次
              <input v-model.number="maxRounds" type="number" min="4" :disabled="!canEditParameters" @input="markTimePlanManual" />
            </label>
          </div>
        </div>

        <div class="catalog">
          <div class="panel-title-row">
            <h3>微调模板</h3>
            <span class="hint">自动匹配 · 主传播族 {{ diffusionTemplateLabel }}</span>
          </div>
          <article class="auto-template-card">
            <div class="template-head">
              <span class="template-name">{{ hazardTemplateMeta.label }}</span>
              <span class="template-badge">{{ hazardTemplateMeta.badge }}</span>
            </div>
            <p>{{ hazardTemplateReasoning || hazardTemplateMeta.description }}</p>
            <small>{{ hazardTemplateMeta.impactChain }}</small>
          </article>
        </div>

        <div class="panel-title-row">
          <h3>关系搜索模式</h3>
          <span class="hint">{{ searchMode === 'deep_search' ? 'LLM 机制链路' : '模板化链路' }}</span>
        </div>
        <div class="template-grid">
          <button
            v-for="mode in searchModes"
            :key="mode.value"
            class="template-card"
            :class="{ active: searchMode === mode.value }"
            :disabled="!canEditParameters"
            @click="setSearchMode(mode.value)"
          >
            <div class="template-head">
              <span class="template-name">{{ mode.label }}</span>
              <span class="template-badge">{{ mode.badge }}</span>
            </div>
            <p>{{ mode.description }}</p>
          </button>
        </div>
        <div v-if="searchMode === 'deep_search'" class="catalog">
          <div class="panel-title-row">
            <h3>深度搜索样本</h3>
            <span class="hint">LLM 机制发现 · 可微调</span>
          </div>
          <div class="field-row">
            <label>
              机制样本数
              <input v-model.number="mechanismTargetAgentCount" type="number" min="8" max="80" :disabled="!canEditParameters" />
            </label>
          </div>
        </div>

        <div class="catalog">
          <div class="panel-title-row">
            <h3>变量注入<span class="variable-kind-tag perturbation">扰动</span></h3>
            <div class="action-row compact">
              <button class="ghost-btn" :disabled="!canEditParameters" @click="addVariable('disaster')">+ 灾难变量</button>
              <button class="ghost-btn" :disabled="!canEditParameters" @click="addVariable('policy')">+ 政策变量</button>
            </div>
          </div>

          <div class="variable-list">
            <article v-for="(variable, index) in injectedVariables" :key="variable.id" class="variable-card">
              <div class="variable-header">
                <div>
                  <span class="variable-index">V{{ index + 1 }}</span>
                  <strong>{{ variable.type === 'policy' ? '政策/干预变量' : '灾难变量' }}</strong>
                  <div class="variable-badges">
                    <span v-if="variable.sourceOrigin === 'seed'" class="variable-badge origin">来自场景先验</span>
                    <span v-else-if="variable.sourceOrigin === 'manual'" class="variable-badge manual">第二步新增</span>
                    <span v-if="variable.sourceOrigin === 'seed' && variable.defaultedRuntimeFields.length" class="variable-badge hint">
                      已补默认参数
                    </span>
                  </div>
                </div>
                <button class="remove-btn" :disabled="!canEditParameters" @click="removeVariable(variable.id)">删除</button>
              </div>

              <div v-if="variable.sourceOrigin === 'seed'" class="variable-draft-note">
                <strong>场景先验草稿</strong>
                <span>{{ variableDraftSummary(variable) }}</span>
              </div>

              <div class="field-row">
                <label>
                  类型
                  <select v-model="variable.type" :disabled="!canEditParameters">
                    <option value="disaster">污染变量</option>
                    <option value="policy">政策变量</option>
                  </select>
                </label>
                <label>
                  变量名
                  <input v-model="variable.name" type="text" placeholder="核废水排放 / 强制撤离" :disabled="!canEditParameters" />
                </label>
              </div>

              <label>
                描述
                <textarea v-model="variable.description" rows="3" placeholder="一句话描述变量如何改变生态或社会状态" :disabled="!canEditParameters"></textarea>
              </label>

              <div class="field-row">
                <label>
                  目标区域
                  <select v-model="variable.targetRegionId" :disabled="!canEditParameters">
                    <option value="">{{ variableRegionOptions.length ? '请选择目标区域' : '暂无可选区域' }}</option>
                    <option v-for="option in variableRegionOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label>
                  目标节点
                  <select v-model="variable.targetNodeId" :disabled="!canEditParameters">
                    <option value="">{{ variableNodeOptions.length ? '请选择目标节点' : '暂无可选节点' }}</option>
                    <option v-for="option in variableNodeOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
              </div>

              <div class="field-row">
                <label>
                  起始轮次
                  <input v-model.number="variable.startRound" type="number" min="0" :disabled="!canEditParameters" />
                </label>
                <label>
                  持续轮次
                  <input v-model.number="variable.durationRounds" type="number" min="1" :disabled="!canEditParameters" />
                </label>
                <label>
                  强度
                  <input v-model.number="variable.intensity" type="range" min="0" max="100" :disabled="!canEditParameters" />
                </label>
              </div>

              <div v-if="variable.type === 'policy'" class="policy-row">
                <label>
                  干预模式
                  <select v-model="variable.policyMode" :disabled="!canEditParameters">
                    <option v-for="mode in policyModes" :key="mode.value" :value="mode.value">
                      {{ mode.label }}
                    </option>
                  </select>
                </label>
              </div>
            </article>
          </div>
        </div>

        <div class="catalog" v-if="stableContextVariables.length > 0">
          <div class="panel-title-row">
            <h3>稳态背景变量<span class="variable-kind-tag stable">稳态</span></h3>
            <span class="hint">{{ stableContextVariables.length }} 项 · 不进入扰动注入，仅作为背景上下文</span>
          </div>
          <div class="stable-context-list">
            <article v-for="item in stableContextVariables" :key="item.key" class="stable-context-card">
              <div class="stable-context-head">
                <strong>{{ item.name }}</strong>
                <span v-if="item.epistemicRole" class="stable-context-role">{{ displayToken(item.epistemicRole) }}</span>
              </div>
              <p v-if="item.description">{{ item.description }}</p>
              <div class="stable-context-meta">
                <span v-if="item.direction">方向 {{ displayToken(item.direction) }}</span>
                <span v-if="item.intensity !== null && item.intensity !== undefined">强度 {{ normalizeScore(item.intensity) }}</span>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section
        class="briefing-section bsec-agents panel workspace-panel agents"
        :class="{ collapsed: !isExpanded('agents') }"
      >
        <div class="panel-title-row briefing-head" @click="toggleSection('agents')">
          <h3>代理体配置</h3>
          <span class="hint">{{ agentSourceLabel }}</span>
          <i class="bh-chev" aria-hidden="true">⌄</i>
        </div>

        <div class="summary-grid">
          <div class="summary-card">
            <span>代理体总数</span>
            <strong>{{ agentCards.length }}</strong>
          </div>
          <div class="summary-card">
            <span>个体 / 组织</span>
            <strong>{{ agentCategorySummary.human + agentCategorySummary.organization }}</strong>
          </div>
          <div class="summary-card">
            <span>生态 / 治理</span>
            <strong>{{ agentCategorySummary.ecology + agentCategorySummary.governance }}</strong>
          </div>
          <div class="summary-card">
            <span>配置状态</span>
            <strong>{{ agentConfigStatusLabel }}</strong>
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
          <div class="catalog-title">代理体卡片总览</div>
          <div v-if="agentCards.length > 0" class="agent-grid">
            <AgentCard
              v-for="(agent, index) in agentCards"
              :key="agent.agentKey"
              :agent="agent"
              :index="index + 1"
            />
          </div>
          <div v-else class="empty-state">
            当前配置里还没有可展示的代理体，系统会在后续用图谱节点生成临时预览。
          </div>
        </div>

      </section>

      <section
        class="briefing-section bsec-relations panel workspace-panel relations"
        :class="{ collapsed: !isExpanded('relations') }"
      >
        <div class="panel-title-row briefing-head" @click="toggleSection('relations')">
          <h3>{{ relationSectionTitle }}</h3>
          <span class="hint">{{ relationSourceLabel }}</span>
          <i class="bh-chev" aria-hidden="true">⌄</i>
        </div>

        <div class="summary-grid">
          <div class="summary-card">
            <span>交互边</span>
            <strong>{{ relationSummary.total }}</strong>
          </div>
          <div class="summary-card">
            <span>跨区域</span>
            <strong>{{ relationSummary.crossRegionCount }}</strong>
          </div>
          <div class="summary-card">
            <span>互动渠道</span>
            <strong>{{ relationSummary.channels.length }}</strong>
          </div>
          <div class="summary-card">
            <span>关系类型</span>
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


        <!-- 区域与代理体归属矩阵已并入「区域划分」tab（同源 regionAnchorMatrix），此处不再重复渲染 -->

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
        class="briefing-section bsec-region panel workspace-panel region"
        :class="{ collapsed: !isExpanded('region') }"
      >
        <div class="panel-title-row briefing-head" @click="toggleSection('region')">
          <h3>区域划分</h3>
          <span class="hint">{{ regionSourceLabel }}</span>
          <i class="bh-chev" aria-hidden="true">⌄</i>
        </div>

        <div class="catalog baseline-panel">
          <div class="panel-title-row">
            <h3>环境基线</h3>
            <span class="hint">{{ environmentBaselineSourceLabel }}</span>
          </div>
          <div v-if="environmentBaselineRows.length" class="baseline-grid">
            <div v-for="item in environmentBaselineRows" :key="item.key" class="baseline-metric">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <small>{{ item.note }}</small>
            </div>
          </div>
          <div v-else class="grounding-box">
            <p>当前图谱里还没有可展示的天气基线。完成地图种子分析后，温度、湿度、降水和风速会在这里展示，不进入变量注入列表。</p>
          </div>
        </div>

        <div class="summary-grid">
          <div class="summary-card">
            <span>区域层级</span>
            <strong>{{ regionRecords.length }}</strong>
          </div>
          <div class="summary-card">
            <span>代理体覆盖</span>
            <strong>{{ regionAnchorTotal }}</strong>
          </div>
          <div class="summary-card">
            <span>邻接连接</span>
            <strong>{{ regionNeighborLinks }}</strong>
          </div>
          <div class="summary-card">
            <span>覆盖率</span>
            <strong>{{ regionCoverageLabel }}</strong>
          </div>
        </div>

        <div class="grounding-box region-explain-box">
          <p>{{ regionAnchorExplanation }}</p>
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
              <span>{{ region.neighborCount }} 个相邻区域</span>
              <span>{{ region.agentCount }} 个代理体</span>
            </div>
            <div class="region-detail-grid">
              <div v-for="group in region.tagGroups" :key="group.key" class="region-tag-group">
                <span class="region-tag-title">{{ group.label }}</span>
                <div class="chip-wrap">
                  <span v-for="tag in group.items" :key="tag" class="chip">{{ tag }}</span>
                  <span v-if="group.items.length === 0" class="empty-chip">{{ group.emptyLabel }}</span>
                </div>
              </div>
              <div class="region-tag-group">
                <span class="region-tag-title">相邻区域</span>
                <div class="chip-wrap">
                  <span v-for="neighbor in region.neighbors.slice(0, 3)" :key="neighbor" class="chip chip-soft">{{ neighbor }}</span>
                  <span v-if="region.neighbors.length === 0" class="empty-chip">暂无相邻区域</span>
                </div>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="empty-state">
          当前没有可用的区域配置，系统会使用图谱节点作为区域预览骨架。
        </div>
      </section>

      <section
        class="briefing-section bsec-risk panel workspace-panel risk-preview-shell"
        :class="{ collapsed: !isExpanded('risk') }"
      >
      <div class="panel-title-row briefing-head" @click="toggleSection('risk')">
        <h3>风险对象</h3>
        <span class="hint">{{ riskObjects.length }} 个 · 推演前为定义</span>
        <i class="bh-chev" aria-hidden="true">⌄</i>
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
              <span class="risk-mode-tag">{{ displayToken(item.mode || 'watch') }}</span>
              <span v-if="item.risk_object_id === primaryRiskObjectId" class="risk-primary-tag">主要</span>
            </div>
            <strong>{{ item.title }}</strong>
            <p v-if="!isRiskPlaceholderText(item.why_now || item.summary)">{{ item.why_now || item.summary }}</p>
            <div class="risk-meta">
              <span>严重性 {{ normalizeScore(item.severity_score) }}</span>
              <span>可行动性 {{ normalizeScore(item.actionability_score) }}</span>
            </div>
          </button>
        </div>

        <div v-if="selectedRiskObject" class="risk-preview-detail">
          <div class="risk-detail-top">
            <div>
              <div class="eyebrow risk-eyebrow">
                {{ selectedRiskObject.mode === 'incident' ? '事件预览' : '观察预览' }}
              </div>
              <h3>{{ selectedRiskObject.title }}</h3>
              <p v-if="!isRiskPlaceholderText(selectedRiskObject.summary || selectedRiskObject.why_now)">{{ selectedRiskObject.summary || selectedRiskObject.why_now }}</p>
            </div>

            <div class="risk-score-strip">
              <div class="summary-card compact">
                <span>严重性</span>
                <strong>{{ normalizeScore(selectedRiskObject.severity_score) }}</strong>
              </div>
              <div class="summary-card compact">
                <span>置信度</span>
                <strong>{{ formatPercent(selectedRiskObject.confidence_score) }}</strong>
              </div>
            </div>
          </div>

          <div
            v-if="selectedRiskObject.has_runtime_signal || (selectedRiskObject.tension_trace || []).length || selectedRiskObject.uncertainty_band"
            class="risk-runtime-box"
          >
            <div class="risk-runtime-head">
              <span class="catalog-title">运行态张力</span>
              <span class="runtime-hint">{{ selectedRiskObject.has_runtime_signal ? '随推演演化' : '尚无运行信号 · 暂用静态严重性' }}</span>
            </div>
            <div class="risk-runtime-row">
              <div v-if="selectedRiskObject.has_runtime_signal && normalizeTension(selectedRiskObject.runtime_tension) !== null" class="runtime-tension-pill">
                <span>当前张力</span>
                <strong>{{ normalizeTension(selectedRiskObject.runtime_tension) }}</strong>
              </div>
              <span
                v-if="runtimeStatusMeta(selectedRiskObject.runtime_status)"
                class="runtime-status-tag"
                :class="`is-${runtimeStatusMeta(selectedRiskObject.runtime_status).cls}`"
              >
                {{ runtimeStatusMeta(selectedRiskObject.runtime_status).label }}
              </span>
              <span v-if="selectedRiskObject.turning_point" class="runtime-turning-tag">⚑ 转折点</span>
              <svg
                v-if="buildTensionSparkline(selectedRiskObject.tension_trace)"
                class="tension-sparkline"
                :viewBox="`0 0 ${buildTensionSparkline(selectedRiskObject.tension_trace).width} ${buildTensionSparkline(selectedRiskObject.tension_trace).height}`"
                :width="buildTensionSparkline(selectedRiskObject.tension_trace).width"
                :height="buildTensionSparkline(selectedRiskObject.tension_trace).height"
                preserveAspectRatio="none"
                role="img"
                aria-label="张力轨迹"
              >
                <polyline
                  :points="buildTensionSparkline(selectedRiskObject.tension_trace).polyline"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linejoin="round"
                  stroke-linecap="round"
                />
                <circle
                  :cx="buildTensionSparkline(selectedRiskObject.tension_trace).lastX"
                  :cy="buildTensionSparkline(selectedRiskObject.tension_trace).lastY"
                  r="2.2"
                  fill="currentColor"
                />
              </svg>
            </div>
            <div v-if="formatUncertaintyBand(selectedRiskObject.uncertainty_band)" class="risk-uncertainty-band">
              <span class="band-label">{{ formatUncertaintyBand(selectedRiskObject.uncertainty_band).label }}</span>
              <strong>
                {{ formatUncertaintyBand(selectedRiskObject.uncertainty_band).center }}
                <small v-if="formatUncertaintyBand(selectedRiskObject.uncertainty_band).range">
                  ({{ formatUncertaintyBand(selectedRiskObject.uncertainty_band).range }})
                </small>
              </strong>
            </div>
          </div>

          <div v-if="!isRiskPlaceholderText(selectedRiskObject.why_now)" class="risk-note-box">
            <span>当前触发原因</span>
            <strong>{{ selectedRiskObject.why_now }}</strong>
          </div>

          <div class="risk-step-list">
            <span v-for="step in selectedRiskObject.chain_steps || []" :key="step" class="chip">{{ displayToken(step) }}</span>
          </div>

          <!-- 层级：运行态明细有数据才展开，且只渲染非空的小节；全空时折叠成一句话，不再堆 4 张空卡 -->
          <template v-if="riskRuntimeHasDetail">
            <div v-if="riskObjectEntityNodes.length > 0 || riskObjectRegionNodes.length > 0" class="risk-node-grid">
              <section v-if="riskObjectEntityNodes.length > 0" class="risk-mini-panel">
                <div class="catalog-title">相关实体节点</div>
                <div class="node-list">
                  <article v-for="node in riskObjectEntityNodes" :key="node.id" class="node-card">
                    <div class="node-card-head">
                      <strong>
                        <span
                          v-if="provenanceMeta(node.provenance)"
                          class="provenance-dot"
                          :class="`is-${provenanceMeta(node.provenance).cls}`"
                          :title="`来源：${provenanceMeta(node.provenance).label}`"
                        ></span>
                        {{ node.name }}
                      </strong>
                      <span class="node-state" :class="{ matched: node.matched }">{{ node.matched ? '图谱节点' : '风险引用' }}</span>
                    </div>
                    <div class="tag-wrap">
                      <span v-for="label in node.labels" :key="label" class="mini-tag">{{ displayToken(label) }}</span>
                    </div>
                  </article>
                </div>
              </section>

              <section v-if="riskObjectRegionNodes.length > 0" class="risk-mini-panel">
                <div class="catalog-title">相关区域</div>
                <div class="node-list">
                  <article v-for="region in riskObjectRegionNodes" :key="region.id" class="node-card">
                    <div class="node-card-head">
                      <strong>{{ region.name }}</strong>
                      <span class="node-state" :class="{ matched: region.matched }">{{ region.matched ? '图谱节点' : '作用域' }}</span>
                    </div>
                    <div class="tag-wrap">
                      <span v-for="label in region.labels" :key="label" class="mini-tag">{{ displayToken(label) }}</span>
                    </div>
                  </article>
                </div>
              </section>
            </div>

            <div v-if="riskObjectClusters.length > 0 || (selectedRiskObject.turning_points || []).length > 0" class="risk-node-grid secondary">
              <section v-if="riskObjectClusters.length > 0" class="risk-mini-panel">
                <div class="catalog-title">受影响群簇</div>
                <div class="cluster-list">
                  <article v-for="cluster in riskObjectClusters" :key="cluster.cluster_id" class="cluster-mini-card">
                    <div class="node-card-head">
                      <strong>{{ cluster.name }}</strong>
                      <span class="mini-tag accent">错配风险 {{ normalizeScore(cluster.mismatch_risk) }}</span>
                    </div>
                    <p>{{ formatInlineList(cluster.dependency_profile, '暂无依赖结构') }}</p>
                  </article>
                </div>
              </section>

              <section v-if="(selectedRiskObject.turning_points || []).length > 0" class="risk-mini-panel">
                <div class="catalog-title">转折点</div>
                <ul class="bullet-list">
                  <li v-for="point in selectedRiskObject.turning_points" :key="point">{{ point }}</li>
                </ul>
              </section>
            </div>
          </template>
          <div v-else class="risk-runtime-empty">
            运行推演后，这里会显示该风险对象的关联实体、作用区域、受影响群簇与转折点。
          </div>
        </div>
      </div>

      <div v-else class="empty-state">
        生成场景定义后，这里会出现风险定义预览，并可联动左侧图谱高亮相关节点。
      </div>
    </section>
    </section>

    <section class="progress-shell">
      <div class="progress-head">
        <div>
          <div class="panel-title-row">
            <h3>准备进度</h3>
            <span class="hint">{{ prepareStageLabel }}</span>
          </div>
          <p class="progress-note">{{ prepareMessage || '等待用户触发场景配置生成' }}</p>
          <p class="prepare-requirements">{{ prepareActionHint }}</p>
        </div>
        <div class="progress-score mono">{{ prepareProgress }}%</div>
      </div>

      <div class="progress-bar">
        <div class="progress-bar-fill" :style="{ width: `${prepareProgress}%` }"></div>
      </div>

      <div class="action-row">
        <button class="secondary-btn" @click="$emit('go-back')">返回图谱构建</button>
        <button class="primary-btn" :disabled="!canPrepare" @click="handlePrepare">
          {{ prepareActionLabel }}
        </button>
        <button class="secondary-btn" :disabled="!isReady" @click="handleNextStep">
          进入推演
        </button>
      </div>
    </section>

    <details class="log-shell">
      <summary class="log-summary">
        <div class="panel-title-row">
          <h3>系统日志</h3>
          <span class="hint mono">{{ simulationId || '未生成模拟' }}</span>
        </div>
      </summary>
      <div class="logs">
        <div v-for="(log, index) in systemLogs" :key="index" class="log-line">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getPrepareStatus, getSimulationConfig, getSimulationConfigRealtime, prepareSimulation, getSimulation } from '../api/simulation'
import AgentCard from './step2/AgentCard.vue'
import { formatTokenLabelZh, translateDisplayToken } from '../utils/displayText'

const props = defineProps({
  simulationId: String,
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  initialScenarioMode: String,
  initialDiffusionTemplate: String,
  initialSearchMode: String,
  initialSimulationArchitecture: String,
  initialInjectedVariables: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status', 'risk-object-focus'])

const hazardTemplates = [
  { value: 'coastal_radioactive_release', label: '核废水/近海放射性释放', family: 'marine_current', badge: '海流', description: '海流输运、沉积物滞留、食物网累积与岸线暴露。', impactChain: '海流输运 · 沉积物滞留 · 食物网累积' },
  { value: 'radioactive_fallout', label: '放射性沉降', family: 'atmospheric_plume', badge: '大气', description: '核爆或核事故后的羽流、沉降、径流和土壤累积。', impactChain: '大气羽流 · 干湿沉降 · 土壤累积' },
  { value: 'industrial_toxic_release', label: '工业有毒物质释放', family: 'terrestrial_surface', badge: '工业', description: '化工泄漏、危险品释放和设施排放导致的多介质污染。', impactChain: '介质释放 · 地表累积 · 食物链暴露' },
  { value: 'inland_water_contamination', label: '内陆水体污染', family: 'inland_water_network', badge: '流域', description: '河流、湖库、尾矿和污水外泄导致的流域污染链。', impactChain: '沿河输运 · 库区滞留 · 灌溉暴露' },
  { value: 'marine_pollution_bloom', label: '海洋污染/赤潮', family: 'marine_current', badge: '海洋', description: '近海污染、富营养化、赤潮与低氧过程。', impactChain: '近海输运 · 营养盐累积 · 低氧区' },
  { value: 'wildfire_smoke_ash', label: '山火烟尘与灰烬', family: 'atmospheric_plume', badge: '烟羽', description: '烟尘扩散、灰烬径流、土壤疏水化和栖息地损失。', impactChain: '烟羽扩散 · 灰烬径流 · 栖息地损失' },
  { value: 'volcanic_eruption', label: '火山喷发', family: 'ash_plume', badge: '火山', description: '火山灰、火山泥流、酸性沉降与下游泥沙压力。', impactChain: '火山灰扩散 · 火山泥流 · 河道淤积' },
  { value: 'earthquake_secondary_cascade', label: '地震次生级联', family: 'infrastructure_failure', badge: '地质', description: '滑坡、液化、基础设施中断和次生泄漏。', impactChain: '设施失效 · 滑坡 · 次生泄漏' },
  { value: 'tsunami_inundation', label: '海啸淹没', family: 'coastal_inundation', badge: '海啸', description: '沿海淹没、盐水入侵、漂浮碎片和港湾污染。', impactChain: '沿海淹没 · 盐水入侵 · 漂浮碎片' },
  { value: 'flood_storm_surge', label: '洪水/风暴潮', family: 'surface_flood_flow', badge: '洪泛', description: '洪水、风暴潮、内涝和复合淹没。', impactChain: '洪泛流动 · 污水外溢 · 沉积再悬浮' },
  { value: 'drought_ecosystem_stress', label: '干旱生态压力', family: 'slow_ecosystem_decline', badge: '慢变量', description: '干旱、热浪与长期水资源压力驱动的生态退化。', impactChain: '水资源短缺 · 植被衰退 · 火险易感' },
  { value: 'invasive_species_spread', label: '外来物种入侵', family: 'ecological_mobility', badge: '生物', description: '扩散走廊、人为携带、种群建立和治理摩擦。', impactChain: '扩散走廊 · 人为携带 · 种群建立' },
  { value: 'pest_disease_ecology', label: '虫害/生态病害', family: 'bio_ecological_transmission', badge: '病媒', description: '虫害、野生动物疫病和生态系统病害传播。', impactChain: '宿主密度 · 媒介移动 · 生态受体损伤' },
  { value: 'asteroid_impact_cascade', label: '小行星撞击级联', family: 'impact_blast', badge: '极端', description: '冲击波、抛射物、火灾和撞击海啸的复合级联。', impactChain: '冲击波 · 抛射物沉降 · 次生火灾' },
  { value: 'generic', label: '通用生态危机', family: 'generic', badge: '兜底', description: '在识别失败或信息过弱时使用的兜底模板。', impactChain: '局地扩散 · 生态承压 · 社会响应' }
]

const transportFamilies = [
  { value: 'atmospheric_plume', label: '大气羽流' },
  { value: 'marine_current', label: '海流输运' },
  { value: 'inland_water_network', label: '流域网络' },
  { value: 'surface_flood_flow', label: '洪泛流' },
  { value: 'coastal_inundation', label: '沿海淹没' },
  { value: 'ecological_mobility', label: '生态迁移' },
  { value: 'bio_ecological_transmission', label: '生物传播' },
  { value: 'ash_plume', label: '火山灰羽流' },
  { value: 'infrastructure_failure', label: '设施级联' },
  { value: 'impact_blast', label: '冲击波' },
  { value: 'slow_ecosystem_decline', label: '慢变量退化' },
  { value: 'terrestrial_surface', label: '地表暴露' },
  { value: 'generic', label: '通用链路' }
]

const searchModes = [
  {
    value: 'fast',
    label: '快速搜索',
    badge: '模板',
    description: '使用模板化关系扩展，优先稳定、快速和低成本。'
  },
  {
    value: 'deep_search',
    label: '深度搜索',
    badge: 'LLM',
    description: '使用 LLM 机制发现链路生成机制图、开放关系和推理账本。'
  }
]

const timePlanUnitOptions = [
  { value: 'hour', label: '小时', minutes: 60 },
  { value: 'day', label: '天', minutes: 1440 },
  { value: 'week', label: '周', minutes: 10080 },
  { value: 'month', label: '月', minutes: 43200 },
  { value: 'quarter', label: '季度', minutes: 129600 },
  { value: 'year', label: '年', minutes: 525600 }
]

const policyModes = [
  { value: 'restrict', label: '限制' },
  { value: 'relocate', label: '迁移' },
  { value: 'subsidize', label: '补贴' },
  { value: 'monitor', label: '监测' },
  { value: 'disclose', label: '披露' },
  { value: 'repair', label: '修复' },
  { value: 'ban', label: '禁止' },
  { value: 'reopen', label: '重开' }
]

const scenarioMode = ref(props.initialScenarioMode || 'baseline_mode')
const diffusionTemplate = ref(props.initialDiffusionTemplate || 'marine_current')
const hazardTemplateId = ref('generic')
const hazardTemplateMode = ref('auto')
const hazardTemplateReasoning = ref('')
const searchMode = ref(props.initialSearchMode || 'fast')
const simulationArchitecture = ref(props.initialSimulationArchitecture || 'legacy_envfish_v1')
const mechanismTargetAgentCount = ref(32)
const temporalPreset = ref('standard')
const configuredMinutesPerRound = ref(60)
const timePlanMode = ref('auto')
const timeStepUnit = ref('hour')
const timeStepSize = ref(1)
const timePlanReasoning = ref('')
const referenceTimeLocal = ref('')
const maxRounds = ref(36)
const activeWorkspaceTab = ref('parameters')
const injectedVariables = ref(buildInitialVariables(props.initialInjectedVariables, { sourceOrigin: 'seed' }))
const phase = ref('idle')
const prepareProgress = ref(0)
const prepareMessage = ref('')
const prepareStage = ref('')
const prepareTaskId = ref('')
const isPreparing = ref(false)
const configSnapshot = ref(null)
const configRealtime = ref(null)
const simulationSnapshot = ref(null)
const hasSubmittedParameters = ref(false)
const userAdjustedTimePlan = ref(false)

const resolvedSimulationArchitecture = computed(() => {
  return searchMode.value === 'deep_search' ? 'llm_mechanism_v1' : 'legacy_envfish_v1'
})

const isMechanismArchitecture = computed(() => resolvedSimulationArchitecture.value === 'llm_mechanism_v1')
const isParameterLocked = computed(() => hasSubmittedParameters.value || phase.value === 'preparing' || isReady.value)
const canEditParameters = computed(() => !isParameterLocked.value && !isPreparing.value)
const shouldShowDisplayTabs = computed(() => isParameterLocked.value)

const parameterStatusLabel = computed(() => {
  if (isReady.value) return '已确认 · 已生成'
  if (phase.value === 'preparing') return '已确认 · 生成中'
  if (hasSubmittedParameters.value) return '已确认 · 等待生成'
  return '待填写'
})

const parameterIntroCopy = computed(() => {
  if (isParameterLocked.value) {
    return '参数已经确认，后续内容只作为生成结果展示；如需改变场景，请回到上一阶段重新生成图谱入口。'
  }
  return '先补充变量、时间计划和搜索模式；确认后系统会生成风险对象、区域划分、代理体配置和关系骨架。'
})

let progressTimer = null
let configTimer = null

const graphNodes = computed(() => collectGraphNodes(props.graphData))
const graphEdges = computed(() => collectGraphEdges(props.graphData))
const environmentBaseline = computed(() => extractEnvironmentBaseline(graphNodes.value))
const environmentBaselineRows = computed(() => buildEnvironmentBaselineRows(environmentBaseline.value))
const environmentBaselineSourceLabel = computed(() => {
  if (!environmentBaseline.value) return '等待地图基线'
  const provider = environmentBaseline.value.provider === 'open-meteo' ? 'Open-Meteo' : environmentBaseline.value.provider
  return provider ? `${provider} · 地图观测基线` : '地图观测基线'
})

const hazardTemplateMeta = computed(() => {
  return hazardTemplates.find(template => template.value === hazardTemplateId.value) || hazardTemplates[hazardTemplates.length - 1]
})

const diffusionTemplateLabel = computed(() => {
  return transportFamilies.find(template => template.value === diffusionTemplate.value)?.label || '未设置'
})

const temporalProfileLabel = computed(() => {
  const unit = timePlanUnitOptions.find(option => option.value === timeStepUnit.value)?.label || timeStepUnit.value
  return `${timeStepSize.value}${unit} / 轮`
})

const totalCoverageLabel = computed(() => {
  const unit = timePlanUnitOptions.find(option => option.value === timeStepUnit.value)?.label || timeStepUnit.value
  return `${Math.max(1, Number(maxRounds.value) || 1) * Math.max(1, Number(timeStepSize.value) || 1)}${unit}`
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
    return '图谱预览区域'
  }
  return '暂无区域来源'
})

const agentSourceLabel = computed(() => {
  if (agentSourceMode.value === 'agent_configs') {
    return '正式代理体配置'
  }
  if (agentSourceMode.value === 'actor_profiles') {
    return '角色画像配置'
  }
  if (agentSourceMode.value === 'graph') {
    if (phase.value === 'preparing') return '自动生成正式配置中 · 当前为图谱预览'
    if (phase.value === 'idle') return '图谱预览 · 尚未生成正式代理体配置'
    return '图谱预览'
  }
  return '暂无代理体来源'
})

const agentConfigStatusLabel = computed(() => {
  if (agentSourceMode.value === 'agent_configs') return '正式配置'
  if (agentSourceMode.value === 'actor_profiles') return '角色配置'
  if (agentSourceMode.value === 'graph') return '图谱预览'
  return '待生成'
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
  return relationSourceMode.value === 'agent_graph' ? '代理体关系图' : '图谱关系骨架'
})

const relationPanelExplanation = computed(() => {
  if (relationSourceMode.value === 'agent_graph') {
    return '这里展示的是正式生成的代理体关系图，表示谁会影响谁、依赖谁、受谁约束。它会作为后续推演里代理体互动的基础网络。'
  }
  return '这里展示的是原始图谱里的关系骨架，不是最终代理体互动网络。当前这些关系表示节点之间已有的事实连接，比如监管、依赖、影响、连接、位于某区域等，用来给后续正式代理体配置和风险链路提供底稿。'
})

const relationSourceLabel = computed(() => {
  if (relationSourceMode.value === 'agent_graph') {
    return `${relationSummary.value.total} 条正式代理体关系`
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

const regionAnchorExplanation = computed(() => {
  if (agentCards.value.length === 0) {
    return '代理体覆盖表示区域与代理体的归属或影响范围关系。当前还没有可展示的代理体配置，所以这里只显示区域骨架。'
  }
  return `代理体覆盖不是代理体总数：右侧代理体配置里有 ${agentCards.value.length} 个代理体；这里的 ${regionAnchorTotal.value} 是按区域累计的覆盖计数，一个代理体如果绑定主区域并影响多个相邻区域，会在多个区域卡片里各计一次。`
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

const variableRegionOptions = computed(() => {
  const seen = new Set()
  return regionRecords.value
    .map((region) => {
      const value = String(region.region_id || region.regionKey || '').trim()
      if (!value || seen.has(value)) return null
      seen.add(value)
      return {
        value,
        label: `${region.displayName} · ${region.regionTypeLabel}`
      }
    })
    .filter(Boolean)
})

const variableNodeOptions = computed(() => {
  const seen = new Set()
  return agentCards.value
    .map((agent) => {
      const value = String(agent.agentId ?? '').trim()
      if (!/^-?\d+$/.test(value) || seen.has(value)) return null
      seen.add(value)
      return {
        value,
        label: `${agent.displayName} · ${agent.familyLabel}${agent.primaryRegionLabel ? ` · ${agent.primaryRegionLabel}` : ''}`
      }
    })
    .filter(Boolean)
})

function resolveRegionOptionValue(value) {
  const raw = toDisplayString(value, '')
  if (!raw) return ''
  if (variableRegionOptions.value.length === 0) return raw
  const direct = variableRegionOptions.value.find((option) => option.value === raw)
  if (direct) return direct.value
  const regionLookup = buildRegionLookup(regionRecords.value)
  const matched = regionLookup.get(normalizeKey(raw))
  return matched ? String(matched.region_id || matched.regionKey || '') : ''
}

function resolveNodeOptionValue(value) {
  const raw = toDisplayString(value, '')
  if (!raw) return ''
  if (variableNodeOptions.value.length === 0) return raw
  const direct = variableNodeOptions.value.find((option) => option.value === raw)
  if (direct) return direct.value
  const normalized = normalizeKey(raw)
  const matchedAgent = agentCards.value.find((agent) => {
    return [
      agent.displayName,
      agent.username,
      agent.sourceEntityUuid,
      agent.sourceEntityType,
      agent.agentId
    ].some((item) => normalizeKey(item) === normalized)
  })
  return matchedAgent ? String(matchedAgent.agentId) : ''
}

function syncVariableSelections() {
  injectedVariables.value = injectedVariables.value.map((variable) => ({
    ...variable,
    targetRegionId: resolveRegionOptionValue(variable.targetRegionId),
    targetNodeId: resolveNodeOptionValue(variable.targetNodeId)
  }))
}

// 场景简报：分节折叠状态（风险默认展开，其余收起）+ 一句话摘要
const expandedSections = ref({ parameters: false, risk: true, region: false, agents: false, relations: false })
const isExpanded = (key) => !!expandedSections.value[key]
const toggleSection = (key) => { expandedSections.value[key] = !expandedSections.value[key] }

const sceneSummaryLine = computed(() => {
  const scenario = translateDisplayToken(scenarioMode.value, '常态')
  const search = String(searchMode.value).includes('deep') ? '深度搜索' : '快速搜索'
  return [scenario, search, temporalProfileLabel.value].filter(Boolean).join(' · ')
})
const paramsSummaryLine = computed(() => {
  const search = String(searchMode.value).includes('deep') ? '深度搜索' : '快速搜索'
  return [temporalProfileLabel.value, search, `${injectedVariables.value.length} 个变量`].filter(Boolean).join(' · ')
})

const workspaceTabs = computed(() => {
  const inputTab = {
    value: 'parameters',
    label: '推演参数',
    meta: isParameterLocked.value
      ? `${hazardTemplateMeta.value.badge} · ${temporalProfileLabel.value} · 已锁定`
      : `${hazardTemplateMeta.value.badge} · ${temporalProfileLabel.value} · ${injectedVariables.value.length} 项变量`
  }
  if (!shouldShowDisplayTabs.value) {
    return [inputTab]
  }
  return [
    inputTab,
    {
      value: 'risk',
      label: '风险对象预览',
      meta: `${riskObjects.value.length} 个对象 · ${primaryRiskObjectId.value ? '已聚焦' : '待生成'}`
    },
    {
      value: 'region',
      label: '区域划分',
      meta: `${regionRecords.value.length} 个区域 · ${regionAnchorTotal.value} 个锚点`
    },
    {
      value: 'agents',
      label: '代理体配置',
      meta: `${agentCards.value.length} 个 · ${agentSourceLabel.value}`
    },
    {
      value: 'relations',
      label: '关系骨架',
      meta: `${relationSummary.value.total} 条 · ${relationSummary.value.types.length} 类`
    },
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

const stableContextVariables = computed(() => {
  const candidates = [
    resolvedConfig.value?.stable_context_variables,
    configRealtime.value?.stable_context_variables,
    configRealtime.value?.config?.stable_context_variables,
    configSnapshot.value?.stable_context_variables,
    props.projectData?.scene_seed?.stable_context_variables,
    props.projectData?.sceneSeed?.stable_context_variables
  ]
  for (const source of candidates) {
    if (Array.isArray(source) && source.length > 0) {
      return source
        .map((item, index) => {
          if (!item || typeof item !== 'object') {
            const text = toDisplayString(item, '')
            return text ? { name: text, key: `stable-${index}` } : null
          }
          return {
            key: toDisplayString(item.id || item.variable_id || item.name || `stable-${index}`, `stable-${index}`),
            name: toDisplayString(item.name || item.title || item.label || `稳态背景 ${index + 1}`, `稳态背景 ${index + 1}`),
            description: toDisplayString(item.description || item.summary || '', ''),
            epistemicRole: toDisplayString(item.epistemic_role || item.epistemicRole || '', ''),
            direction: toDisplayString(item.direction || '', ''),
            intensity: item.intensity ?? item.intensity_0_100 ?? null
          }
        })
        .filter(Boolean)
    }
  }
  return []
})

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

// 层级：运行态明细（实体/区域/群簇/转折点）是否有真实数据 —— 没有就折叠成一句话，不渲染 4 张空卡
const riskRuntimeHasDetail = computed(() =>
  riskObjectEntityNodes.value.length > 0 ||
  riskObjectRegionNodes.value.length > 0 ||
  riskObjectClusters.value.length > 0 ||
  (selectedRiskObject.value?.turning_points || []).length > 0
)
// 占位/等待文案不重复上屏（推演前 why_now 只是占位，别在每张卡上重复）
const isRiskPlaceholderText = (text) => {
  const s = String(text || '')
  return !s || s.includes('等待推演运行态刷新') || s.includes('等待风险对象摘要') || s.includes('场景配置完成后')
}

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
      provenance: node?.provenance || node?.attributes?.provenance || evidence?.provenance || '',
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

const canPrepare = computed(() => {
  return Boolean(props.simulationId) && !isPreparing.value && (!isParameterLocked.value || phase.value === 'error')
})

const prepareActionLabel = computed(() => {
  if (!props.simulationId) return '等待图谱完成'
  if (isPreparing.value) return '生成中...'
  if (phase.value === 'ready') return '配置已确认'
  if (phase.value === 'error') return '重试生成'
  if (phase.value === 'preparing' || hasSubmittedParameters.value) return '参数已锁定'
  return '确认并生成配置'
})

const prepareActionHint = computed(() => {
  if (!props.simulationId) {
    return '需要先完成左侧图谱并创建模拟入口；入口就绪后这里会变为可点击。'
  }
  if (isPreparing.value || phase.value === 'preparing') {
    return '正在生成正式代理体、区域、关系和风险配置。'
  }
  if (phase.value === 'ready') {
    return '配置已生成，可以进入推演；参数区已锁定。'
  }
  if (phase.value === 'error') {
    return '上次生成失败，可以按已锁定参数重试。'
  }
  return '确认后会锁定当前参数，并开始生成后续展示内容。'
})

const prepareStageLabel = computed(() => {
  if (!props.simulationId) return '等待入口'
  if (phase.value === 'ready') return '已完成'
  if (phase.value === 'preparing') return translateDisplayToken(prepareStage.value || 'processing', '处理中')
  if (phase.value === 'error') return '失败'
  return '空闲'
})

const payloadPreview = computed(() => {
  return JSON.stringify({
    simulation_id: props.simulationId,
    engine_mode: 'envfish',
    simulation_architecture: resolvedSimulationArchitecture.value,
    scenario_mode: scenarioMode.value,
    hazard_template_id: hazardTemplateId.value,
    hazard_template_mode: hazardTemplateMode.value,
    diffusion_template: diffusionTemplate.value,
    search_mode: searchMode.value,
    time_plan_mode: timePlanMode.value,
    time_plan: {
      step_unit: timeStepUnit.value,
      step_size: timeStepSize.value,
      total_rounds: maxRounds.value,
      reference_time: '',
      reasoning_summary: timePlanReasoning.value
    },
    temporal_profile: {
      preset: temporalPreset.value,
      total_rounds: maxRounds.value,
      minutes_per_round: configuredMinutesPerRound.value
    },
    reference_time: '',
    diffusion_provider: 'auto',
    max_rounds: maxRounds.value,
    target_agent_count: isMechanismArchitecture.value ? mechanismTargetAgentCount.value : undefined,
    spatial_grain: 'region',
    injected_variables: injectedVariables.value.map(serializeVariable)
  }, null, 2)
})

function presetFromMinutes(minutes) {
  const resolved = Number(minutes) || 60
  if (resolved <= 30) return 'rapid'
  if (resolved >= 120) return 'slow'
  return 'standard'
}

function minutesForTimePlan(unit, stepSize = 1) {
  const matched = timePlanUnitOptions.find(option => option.value === unit)
  return Math.max(10, (matched?.minutes || 60) * Math.max(1, Number(stepSize) || 1))
}

function inferScenarioModeFromVariables(variables = []) {
  const hasActiveVariable = variables.some((variable) => {
    return [
      variable?.name,
      variable?.description,
      variable?.targetRegionId,
      variable?.targetNodeId
    ].some((item) => String(item || '').trim())
  })
  return hasActiveVariable ? 'crisis_mode' : 'baseline_mode'
}

function inferHazardTemplateFromVariables(variables = []) {
  const corpus = variables
    .flatMap((variable) => [variable?.name, variable?.description])
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  const rules = [
    { id: 'coastal_radioactive_release', tokens: ['核废水', '放射性水', '近海', '海流', 'marine', 'radioactive water'] },
    { id: 'radioactive_fallout', tokens: ['放射性沉降', '核爆', '核事故', '沉降', 'fallout'] },
    { id: 'industrial_toxic_release', tokens: ['化工', '有毒', '危险品', '工厂', '工业', 'toxic', 'chemical'] },
    { id: 'inland_water_contamination', tokens: ['河流', '湖库', '水体', '污水', '尾矿', '流域'] },
    { id: 'marine_pollution_bloom', tokens: ['赤潮', '富营养化', '海洋污染', '近海污染', '低氧'] },
    { id: 'wildfire_smoke_ash', tokens: ['山火', '野火', '烟尘', '灰烬', 'wildfire', 'smoke'] },
    { id: 'volcanic_eruption', tokens: ['火山', '火山灰', '泥流', 'eruption'] },
    { id: 'earthquake_secondary_cascade', tokens: ['地震', '液化', '滑坡', '断裂', 'earthquake'] },
    { id: 'tsunami_inundation', tokens: ['海啸', 'tsunami'] },
    { id: 'flood_storm_surge', tokens: ['洪水', '风暴潮', '内涝', '暴雨', '淹没', 'flood'] },
    { id: 'drought_ecosystem_stress', tokens: ['干旱', '热浪', '缺水', 'drought'] },
    { id: 'invasive_species_spread', tokens: ['外来物种', '入侵物种', '扩散走廊', 'invasive'] },
    { id: 'pest_disease_ecology', tokens: ['虫害', '病害', '疫病', '病媒', 'pest', 'disease'] },
    { id: 'asteroid_impact_cascade', tokens: ['小行星', '陨石', '撞击', 'asteroid'] }
  ]

  const matchedRule = rules.find((rule) => rule.tokens.some((token) => corpus.includes(token)))
  const template = hazardTemplates.find((item) => item.value === matchedRule?.id) || hazardTemplates[hazardTemplates.length - 1]
  const hasInput = Boolean(corpus.trim())
  return {
    template,
    reasoning: hasInput
      ? `已根据变量描述自动匹配 ${template.label}。`
      : '尚未识别到明确扰动，暂用通用生态危机模板。'
  }
}

function deriveAutomaticTimePlan(templateId, variables = []) {
  const fastTemplates = ['radioactive_fallout', 'tsunami_inundation', 'earthquake_secondary_cascade', 'flood_storm_surge', 'industrial_toxic_release', 'asteroid_impact_cascade']
  const slowTemplates = ['coastal_radioactive_release', 'drought_ecosystem_stress', 'invasive_species_spread', 'pest_disease_ecology']
  const scenario = inferScenarioModeFromVariables(variables)
  if (fastTemplates.includes(templateId)) {
    return {
      step_unit: 'hour',
      step_size: 6,
      total_rounds: scenario === 'crisis_mode' ? 16 : 12,
      reasoning_summary: '快过程风险自动使用小时级步长，便于观察级联响应。'
    }
  }
  if (slowTemplates.includes(templateId)) {
    return {
      step_unit: 'week',
      step_size: 1,
      total_rounds: variables.length > 0 ? 16 : 12,
      reasoning_summary: '慢过程风险自动使用周级步长，覆盖累积、迁移和长期反馈。'
    }
  }
  return {
    step_unit: 'day',
    step_size: 1,
    total_rounds: scenario === 'crisis_mode' ? 14 : 10,
    reasoning_summary: '中过程风险自动使用天级步长，平衡扩散、响应和恢复过程。'
  }
}

function applyAutoScenarioRecommendations() {
  if (isParameterLocked.value) return
  const recommendation = inferHazardTemplateFromVariables(injectedVariables.value)
  scenarioMode.value = inferScenarioModeFromVariables(injectedVariables.value)
  hazardTemplateId.value = recommendation.template.value
  hazardTemplateMode.value = 'auto'
  hazardTemplateReasoning.value = recommendation.reasoning
  diffusionTemplate.value = recommendation.template.family
  simulationArchitecture.value = resolvedSimulationArchitecture.value
  if (!userAdjustedTimePlan.value) {
    assignTimePlan(deriveAutomaticTimePlan(recommendation.template.value, injectedVariables.value), 'auto')
  }
}

function markTimePlanManual() {
  userAdjustedTimePlan.value = true
  timePlanMode.value = 'manual'
}

function setSearchMode(value) {
  if (!canEditParameters.value) return
  searchMode.value = value === 'deep_search' ? 'deep_search' : 'fast'
  simulationArchitecture.value = resolvedSimulationArchitecture.value
}

function assignTimePlan(payload = {}, mode = 'auto') {
  const unit = payload.step_unit || payload.stepUnit || timeStepUnit.value
  const size = Math.max(1, Number(payload.step_size ?? payload.stepSize ?? timeStepSize.value) || 1)
  timeStepUnit.value = unit
  timeStepSize.value = size
  if (payload.total_rounds !== undefined) {
    maxRounds.value = Math.max(4, Number(payload.total_rounds) || maxRounds.value)
  }
  const minutes = Number(payload.minutes_per_round) || minutesForTimePlan(unit, size)
  configuredMinutesPerRound.value = minutes
  temporalPreset.value = payload.preset || presetFromMinutes(minutes)
  if (payload.reference_time) {
    referenceTimeLocal.value = toDateTimeLocal(payload.reference_time)
  }
  timePlanReasoning.value = payload.reasoning_summary || payload.reasoningSummary || timePlanReasoning.value
  timePlanMode.value = mode || payload.source || timePlanMode.value
}

function applyHazardTemplate(payload = {}, mode = 'auto') {
  const nextId = payload.hazard_template_id || payload.hazardTemplateId || hazardTemplateId.value
  const nextMeta = hazardTemplates.find(item => item.value === nextId)
  hazardTemplateId.value = nextId
  hazardTemplateMode.value = mode
  hazardTemplateReasoning.value = payload.reasoning_summary || payload.reasoning || payload.hazard_template_reasoning || hazardTemplateReasoning.value
  if (payload.primary_family || payload.primaryFamily) {
    diffusionTemplate.value = payload.primary_family || payload.primaryFamily
  } else if (nextMeta?.family) {
    diffusionTemplate.value = nextMeta.family
  }
}

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
    hasSubmittedParameters.value = true
    prepareProgress.value = 100
    if (!prepareMessage.value) {
      prepareMessage.value = '已存在可复用的场景配置'
    }
    return
  }

  if (phase.value === 'error') {
    hasSubmittedParameters.value = true
    prepareProgress.value = clamp(Number(prepareProgress.value) || 0, 0, 100)
    if (!prepareMessage.value) {
      prepareMessage.value = simulationSnapshot.value?.error || '场景配置生成失败'
    }
    return
  }

  if (phase.value === 'preparing') {
    hasSubmittedParameters.value = true
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

function buildVariableId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function createVariable(type = 'disaster') {
  return {
    id: buildVariableId(),
    type,
    name: '',
    description: '',
    targetRegionId: '',
    targetNodeId: '',
    startRound: 0,
    durationRounds: 4,
    intensity: 70,
    policyMode: 'restrict',
    sourceOrigin: 'manual',
    defaultedRuntimeFields: []
  }
}

function normalizeExternalVariable(variable, index = 0, options = {}) {
  if (!variable || typeof variable !== 'object') return null
  if (isBaselineContextVariable(variable)) return null
  const type = variable.type === 'policy' ? 'policy' : 'disaster'
  const targetRegions = Array.isArray(variable.target_regions)
    ? variable.target_regions
    : Array.isArray(variable.targetRegions)
      ? variable.targetRegions
      : toDisplayString(variable.target_region || variable.targetRegion, '')
        ? [variable.target_region || variable.targetRegion]
        : []
  const targetNodes = Array.isArray(variable.target_nodes)
    ? variable.target_nodes
    : Array.isArray(variable.targetNodes)
      ? variable.targetNodes
      : toDisplayString(variable.target_node || variable.targetNode, '')
        ? [variable.target_node || variable.targetNode]
        : []
  const sourceOrigin = toDisplayString(variable.source_origin || variable.sourceOrigin || options.sourceOrigin, options.sourceOrigin || 'manual')
  const defaultedRuntimeFields = []
  if (sourceOrigin === 'seed') {
    if (variable.start_round === undefined && variable.startRound === undefined) defaultedRuntimeFields.push('起始轮次')
    if (variable.duration_rounds === undefined && variable.durationRounds === undefined) defaultedRuntimeFields.push('持续轮次')
    if (variable.intensity_0_100 === undefined && variable.intensity === undefined) defaultedRuntimeFields.push('强度')
  }

  return {
    id: String(variable.id || variable.variable_id || buildVariableId()),
    type,
    name: toDisplayString(variable.name || variable.title || `变量 ${index + 1}`, `变量 ${index + 1}`),
    description: toDisplayString(variable.description || '', ''),
    targetRegionId: toDisplayString(targetRegions[0], ''),
    targetNodeId: toDisplayString(targetNodes[0], ''),
    startRound: Number(variable.start_round ?? variable.startRound ?? 0) || 0,
    durationRounds: Math.max(1, Number(variable.duration_rounds ?? variable.durationRounds ?? 4) || 4),
    intensity: clamp(Number(variable.intensity_0_100 ?? variable.intensity ?? 70) || 70, 0, 100),
    policyMode: type === 'policy'
      ? toDisplayString(variable.policy_mode || variable.policyMode || 'restrict', 'restrict')
      : 'restrict',
    sourceOrigin,
    defaultedRuntimeFields
  }
}

function isBaselineContextVariable(variable) {
  const text = [
    variable?.name,
    variable?.title,
    variable?.description,
    variable?.summary,
    variable?.type,
    variable?.category
  ].filter(Boolean).join(' ').toLowerCase()
  if (!text) return false
  const baselineTerms = ['基线', '稳态', '常态', '当前', '现状', '观测', '环境背景', 'weather_baseline', 'baseline']
  const weatherTerms = ['温度', '气温', '湿度', '降水', '降雨', '风速', '风向', '天气', 'temperature', 'humidity', 'precipitation', 'wind', 'weather']
  return baselineTerms.some((term) => text.includes(term)) && weatherTerms.some((term) => text.includes(term))
}

function buildInitialVariables(source, options = {}) {
  const normalized = (Array.isArray(source) ? source : [])
    .map((item, index) => normalizeExternalVariable(item, index, options))
    .filter(Boolean)
  return normalized.length > 0 ? normalized : [createVariable('disaster')]
}

function applyInjectedVariables(source, options = {}) {
  injectedVariables.value = buildInitialVariables(source, options)
  syncVariableSelections()
}

function variableDraftSummary(variable) {
  const pending = []
  if (!variable.targetRegionId) pending.push('目标区域')
  if (!variable.targetNodeId) pending.push('目标节点')
  pending.push(...(variable.defaultedRuntimeFields || []))
  if (pending.length === 0) return '这条先验变量已经补全为可运行的正式变量。'
  return `待确认字段：${uniqueList(pending).join(' / ')}`
}

function serializeVariable(variable) {
  const targetNodeId = String(variable.targetNodeId || '').trim()
  return {
    type: variable.type,
    name: variable.name || (variable.type === 'policy' ? 'policy_injection' : 'disaster_injection'),
    description: variable.description || '',
    target_regions: variable.targetRegionId ? [String(variable.targetRegionId)] : [],
    target_nodes: /^-?\d+$/.test(targetNodeId) ? [Number(targetNodeId)] : [],
    start_round: Number(variable.startRound) || 0,
    duration_rounds: Math.max(1, Number(variable.durationRounds) || 1),
    intensity: clamp(Number(variable.intensity) || 0, 0, 100),
    policy_mode: variable.type === 'policy' ? variable.policyMode : undefined,
    source_origin: variable.sourceOrigin || 'manual'
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

function extractEnvironmentBaseline(nodes) {
  const regionBaseline = nodes
    .map((node) => node?.attributes?.environment_baseline)
    .find((baseline) => baseline && typeof baseline === 'object')
  if (regionBaseline) return regionBaseline

  const weatherNode = nodes.find((node) => {
    const subtype = String(node?.attributes?.subtype || node?.subtype || '').toLowerCase()
    return subtype === 'weather_baseline'
  })
  if (!weatherNode) return null
  return {
    provider: weatherNode?.attributes?.tags?.provider || weatherNode?.attributes?.provider || 'open-meteo',
    location: weatherNode?.attributes?.location || weatherNode?.name || '',
    summary: weatherNode?.summary || weatherNode?.attributes?.summary || '',
    current: weatherNode?.attributes?.current || {}
  }
}

function formatBaselineValue(value, unit = '') {
  if (value === null || value === undefined || value === '') return '暂无'
  const numeric = Number(value)
  const display = Number.isFinite(numeric) ? String(Math.round(numeric * 10) / 10) : String(value)
  return unit ? `${display}${unit}` : display
}

function buildEnvironmentBaselineRows(baseline) {
  if (!baseline || typeof baseline !== 'object') return []
  const current = baseline.current || {}
  const daily = baseline.daily || {}
  const rows = [
    {
      key: 'temperature_2m',
      label: '基线温度',
      value: formatBaselineValue(current.temperature_2m, '°C'),
      note: daily.temperature_2m_min !== undefined || daily.temperature_2m_max !== undefined
        ? `日范围 ${formatBaselineValue(daily.temperature_2m_min, '°C')} - ${formatBaselineValue(daily.temperature_2m_max, '°C')}`
        : '当前观测'
    },
    {
      key: 'relative_humidity_2m',
      label: '基线湿度',
      value: formatBaselineValue(current.relative_humidity_2m, '%'),
      note: '当前观测'
    },
    {
      key: 'precipitation',
      label: '基线降水',
      value: formatBaselineValue(current.precipitation, ' mm'),
      note: daily.precipitation_sum !== undefined ? `日累计 ${formatBaselineValue(daily.precipitation_sum, ' mm')}` : '当前观测'
    },
    {
      key: 'wind_speed_10m',
      label: '基线风速',
      value: formatBaselineValue(current.wind_speed_10m, ' m/s'),
      note: daily.wind_speed_10m_max !== undefined ? `日最大 ${formatBaselineValue(daily.wind_speed_10m_max, ' m/s')}` : '10m 风速'
    }
  ]
  return rows.filter((row) => row.value !== '暂无')
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
  if (!normalized) return toDisplayString(value, '未知区域')
  const found = lookup.get(normalized)
  return found?.displayName || found?.name || found?.label || toDisplayString(value, '未知区域')
}

function resolveRegionKey(value, lookup) {
  const normalized = normalizeKey(value)
  if (!normalized) return ''
  const found = lookup.get(normalized)
  return found?.regionKey || found?.region_id || found?.regionId || normalized
}

function humanizeSnakeCase(value, fallback = '') {
  return formatTokenLabelZh(toDisplayString(value, fallback), fallback)
}

function displayToken(value, fallback = '') {
  return translateDisplayToken(value, fallback || toDisplayString(value, fallback))
}

function formatLayerLabel(value) {
  const raw = toDisplayString(value, 'macro')
  const normalized = normalizeKey(raw)
  if (!normalized) return '宏观层'
  if (/^\d+$/.test(raw)) return `第 ${raw} 层`
  const map = {
    macro: '宏观层',
    meso: '中观层',
    micro: '微观层',
    region: '区域层',
    subregion: '细分区域层'
  }
  return map[normalized] || `${displayToken(raw)}层`
}

function categorizeRegionTags(tags = []) {
  const groups = [
    { key: 'spatial', label: '区域属性', emptyLabel: '暂无区域属性', items: [] },
    { key: 'risk', label: '风险与约束', emptyLabel: '暂无风险标签', items: [] },
    { key: 'function', label: '功能场景', emptyLabel: '暂无功能标签', items: [] }
  ]
  const seen = new Set()
  ;(tags || []).forEach((tag) => {
    const label = displayToken(tag)
    const normalized = normalizeKey(tag)
    if (!label || seen.has(label)) return
    seen.add(label)
    if (normalized.includes('risk') || normalized.includes('风险') || normalized.includes('flood') || normalized.includes('洪涝') || normalized.includes('landslide') || normalized.includes('滑坡') || normalized.includes('protected') || normalized.includes('保护') || normalized.includes('crossborder') || normalized.includes('跨边界')) {
      groups[1].items.push(label)
      return
    }
    if (normalized.includes('commercial') || normalized.includes('商业') || normalized.includes('urban') || normalized.includes('城市') || normalized.includes('infrastructure') || normalized.includes('基础设施') || normalized.includes('science') || normalized.includes('科学') || normalized.includes('watersource') || normalized.includes('水源') || normalized.includes('reservoir') || normalized.includes('水库')) {
      groups[2].items.push(label)
      return
    }
    groups[0].items.push(label)
  })
  return groups.map((group) => ({
    ...group,
    items: group.items.slice(0, 4)
  }))
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
  if (Number.isNaN(number)) return '中立'
  if (number >= 80) return '紧急'
  if (number >= 60) return '预警'
  if (number >= 35) return '稳定'
  return '平稳'
}

const RUNTIME_STATUS_META = {
  rising: { label: '上升', cls: 'rising' },
  falling: { label: '回落', cls: 'falling' },
  critical: { label: '临界', cls: 'critical' },
  elevated: { label: '偏高', cls: 'elevated' },
  steady: { label: '平稳', cls: 'steady' }
}

function runtimeStatusMeta(value) {
  const key = String(value || '').trim().toLowerCase()
  return RUNTIME_STATUS_META[key] || { label: displayToken(value, '平稳'), cls: 'steady' }
}

function tensionTraceValues(trace) {
  if (!Array.isArray(trace)) return []
  return trace
    .map((point) => {
      if (point && typeof point === 'object') {
        return Number(point.value ?? point.tension ?? point.runtime_tension ?? point.center)
      }
      return Number(point)
    })
    .filter((value) => Number.isFinite(value))
}

function buildTensionSparkline(trace, width = 96, height = 26) {
  const values = tensionTraceValues(trace)
  if (values.length < 2) return null
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const stepX = width / (values.length - 1)
  const points = values.map((value, index) => {
    const x = index * stepX
    const y = height - ((value - min) / span) * (height - 2) - 1
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const lastValue = values[values.length - 1]
  const lastX = (values.length - 1) * stepX
  const lastY = height - ((lastValue - min) / span) * (height - 2) - 1
  return {
    width,
    height,
    polyline: points.join(' '),
    lastX: lastX.toFixed(1),
    lastY: lastY.toFixed(1),
    count: values.length
  }
}

function normalizeTension(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return number <= 1 ? Math.round(number * 100) : Math.round(number)
}

function formatUncertaintyBand(band) {
  if (!band || typeof band !== 'object') return null
  const center = normalizeTension(band.center)
  if (center === null) return null
  const lower = normalizeTension(band.lower)
  const upper = normalizeTension(band.upper)
  const range = (lower !== null && upper !== null) ? `${lower} – ${upper}` : null
  return {
    center,
    range,
    label: toDisplayString(band.label, '推断区间(非测量)'),
    derived: band.derived !== false
  }
}

const PROVENANCE_META = {
  observed: { label: '观察', cls: 'observed' },
  inferred: { label: '推断', cls: 'inferred' },
  assumed: { label: '假设', cls: 'assumed' }
}

function provenanceMeta(value) {
  const key = String(value || '').trim().toLowerCase()
  return PROVENANCE_META[key] || null
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
  if (!stateVector || typeof stateVector !== 'object') return '状态 n/a'
  const exposure = normalizeScore(stateVector.exposure_score)
  const trust = normalizeScore(stateVector.public_trust)
  const stress = normalizeScore(stateVector.economic_stress || stateVector.vulnerability_score)
  if (!exposure && !trust && !stress) return '状态 n/a'
  return `E${exposure} · T${trust} · S${stress}`
}

function deriveStanceLabel(agent = {}) {
  const rawStance = toDisplayString(agent.stance_label || agent.stance || agent.stance_profile?.stance || agent.position, '').toLowerCase()
  if (rawStance) {
    if (rawStance.includes('opp')) return '反对'
    if (rawStance.includes('supp')) return '支持'
    if (rawStance.includes('obs')) return '观察'
    if (rawStance.includes('neutral')) return '中立'
  }
  const bias = Number(agent.sentiment_bias ?? agent.stance_profile?.sentiment_bias ?? 0)
  if (Number.isFinite(bias)) {
    if (bias > 0.15) return '支持'
    if (bias < -0.15) return '反对'
  }
  return '中立'
}

function normalizeRegionRecords(rawRegions) {
  const source = Array.isArray(rawRegions) ? rawRegions : []
  if (source.length === 0) return []

  const baseRecords = source.map((region, index) => {
    const regionKey = normalizeKey(region?.region_id || region?.regionId || region?.id || region?.name || `region-${index}`)
    const rawTags = uniqueList([
      region?.region_type,
      region?.subregion_type,
      region?.land_use_class,
      region?.distance_band,
      ...(region?.tags || [])
    ])
    return {
      regionKey,
      region_id: toDisplayString(region?.region_id || region?.regionId || region?.id || regionKey, regionKey),
      displayName: toDisplayString(region?.name || region?.label || region?.title || regionKey, `区域 ${index + 1}`),
      name: toDisplayString(region?.name || region?.label || region?.title || regionKey, `区域 ${index + 1}`),
      regionTypeLabel: humanizeSnakeCase(region?.region_type || region?.subregion_type || region?.layer || 'region', '区域'),
      layerLabel: formatLayerLabel(region?.layer),
      subregionLabel: humanizeSnakeCase(region?.subregion_type || region?.land_use_class || region?.distance_band || region?.region_type || 'general', '综合'),
      summary: toDisplayString(region?.description || region?.summary || region?.notes || region?.tags?.[0], '暂无区域描述'),
      tags: rawTags.map((item) => displayToken(item)),
      tagGroups: categorizeRegionTags(rawTags),
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
    const rawTags = uniqueList([
      node?.type,
      node?.entity_type,
      node?.category,
      ...(node?.tags || [])
    ])
    return {
      regionKey,
      region_id: regionKey,
      displayName: toDisplayString(node?.label || node?.name || `区域 ${index + 1}`, `区域 ${index + 1}`),
      name: toDisplayString(node?.label || node?.name || `区域 ${index + 1}`, `区域 ${index + 1}`),
      regionTypeLabel: humanizeSnakeCase(node?.type || node?.entity_type || node?.category || 'region', '区域'),
      layerLabel: '图谱区域层',
      subregionLabel: '图谱节点',
      summary: toDisplayString(node?.description || node?.summary || node?.label, '来自图谱的区域骨架'),
      tags: rawTags.map((item) => displayToken(item)),
      tagGroups: categorizeRegionTags(rawTags),
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
    label: fallbackValue || '未知区域'
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
    const displayName = toDisplayString(agent?.name || agent?.username || agent?.agent_name || agent?.entity_name || `代理体 ${index + 1}`, `代理体 ${index + 1}`)
    const agentKey = normalizeKey(agent?.agent_id || agent?.user_id || agent?.uuid || agent?.source_entity_uuid || agent?.username || displayName || `agent-${index}`)
    return {
      agentKey: agentKey || `agent-${index}`,
      agentId: agent?.agent_id ?? agent?.user_id ?? index,
      displayName,
      username: toDisplayString(agent?.username || agent?.agent_name || displayName, displayName),
      handle: agent?.username ? `@${agent.username}` : `@${normalizeKey(displayName) || `agent_${index + 1}`}`,
      agentTypeLabel: displayToken(agent?.agent_type || agent?.node_family || agent?.role_type || familyLabel(family), familyLabel(family)),
      familyKey: family,
      familyLabel: familyLabel(family),
      familyClass: family,
      roleTypeLabel: displayToken(agent?.role_type || agent?.profession || agent?.node_family || 'profile', '档案'),
      sourceLabel: '模拟配置',
      summary: toDisplayString(agent?.bio || agent?.persona || agent?.summary, `${displayName} 锚定于 ${primaryRegion.label}`),
      bio: toDisplayString(agent?.bio || '', ''),
      persona: toDisplayString(agent?.persona || '', ''),
      profession: displayToken(agent?.profession || agent?.role_type || agent?.node_family || familyLabel(family), familyLabel(family)),
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
        roleTypeLabel: displayToken(node?.type || node?.entity_type || key, familyLabel(key)),
        sourceLabel: '图谱预览',
        summary: toDisplayString(node?.description || node?.summary || node?.label, `${displayName} 由图谱骨架推断生成`),
        bio: toDisplayString(node?.description || node?.summary || '', ''),
        persona: '',
        profession: displayToken(node?.entity_type || node?.type || familyLabel(key), familyLabel(key)),
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
        stanceLabel: '中立',
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
        ? `${matchingAgents.length} 个代理体锚定于此`
        : region.summary,
      agentCount: matchingAgents.length,
      topFamilies,
      neighbors: region.neighbors,
      neighborCount: region.neighborCount,
      regionTypeLabel: region.regionTypeLabel,
      layerLabel: region.layerLabel,
      subregionLabel: region.subregionLabel,
      tags: region.tags,
      tagGroups: region.tagGroups || categorizeRegionTags(region.tags),
      carriers: region.carriers,
      stateVector: region.stateVector,
      primaryRegionLabel: resolveRegionLabel(region.regionKey, regionLookup)
    }
  })
}

function getEdgeLabel(edge) {
  return displayToken(
    edge?.relation_type || edge?.label || edge?.relation || edge?.relationship || edge?.type || edge?.name || edge?.kind,
    '未命名关系'
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
      const channelLabel = translateDisplayToken(channel, humanizeSnakeCase(channel, '综合'))
      // 清洗 rationale 句子里嵌入的内部渠道 token（如 governance_hierarchy）
      const rawRationale = toDisplayString(edge?.rationale || '', '')
      const rationale = channel
        ? rawRationale.split(channel).join(translateDisplayToken(channel, channelLabel))
        : rawRationale
      sampleEdges.push({
        key: `${label}-${index}`,
        label,
        displayLabel: relationMeta.displayLabel,
        hint: relationMeta.hint,
        summary: source && target
          ? `${source} ${relationMeta.displayLabel} ${target}`
          : source || target || '关系边',
        rationale,
        channelLabel,
        strengthLabel: Number.isFinite(Number(edge?.strength)) ? Number(edge.strength).toFixed(2) : ''
      })
    }
  })

  return {
    total: (edges || []).length,
    crossRegionCount,
    channels: Array.from(channelCounts.entries())
      .map(([label, count]) => ({ label, count, displayLabel: translateDisplayToken(label, humanizeSnakeCase(label, '综合')) }))
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
      if (simulationSnapshot.value?.hazard_template_id) {
        applyHazardTemplate(simulationSnapshot.value, simulationSnapshot.value.hazard_template_mode || 'auto')
      }
      if (simulationSnapshot.value?.transport_profile?.primary_family) {
        diffusionTemplate.value = simulationSnapshot.value.transport_profile.primary_family
      }
      if (simulationSnapshot.value?.diffusion_template) diffusionTemplate.value = simulationSnapshot.value.diffusion_template
      if (simulationSnapshot.value?.search_mode) searchMode.value = simulationSnapshot.value.search_mode
      if (simulationSnapshot.value?.simulation_architecture) simulationArchitecture.value = simulationSnapshot.value.simulation_architecture
      if (simulationSnapshot.value?.time_plan) {
        assignTimePlan(simulationSnapshot.value.time_plan, simulationSnapshot.value.time_plan_mode || 'auto')
      } else {
        assignTimePlan({
          total_rounds: simulationSnapshot.value?.configured_total_rounds,
          minutes_per_round: simulationSnapshot.value?.configured_minutes_per_round,
          preset: simulationSnapshot.value?.temporal_preset,
          reference_time: simulationSnapshot.value?.reference_time
        }, simulationSnapshot.value?.time_plan_mode || 'auto')
      }
    }

    if (configRes.status === 'fulfilled' && configRes.value?.success && configRes.value.data) {
      configSnapshot.value = configRes.value.data
      if (Array.isArray(configRes.value.data.injected_variables) && configRes.value.data.injected_variables.length > 0) {
        applyInjectedVariables(configRes.value.data.injected_variables, { sourceOrigin: 'runtime' })
      }
      if (configRes.value.data.scenario_mode) scenarioMode.value = configRes.value.data.scenario_mode
      if (configRes.value.data.hazard_template_recommendation || configRes.value.data.hazard_template_id) {
        applyHazardTemplate(configRes.value.data.hazard_template_recommendation || configRes.value.data, configRes.value.data.hazard_template_mode || 'auto')
      }
      if (configRes.value.data.transport_profile?.primary_family) {
        diffusionTemplate.value = configRes.value.data.transport_profile.primary_family
      }
      if (configRes.value.data.diffusion_template) diffusionTemplate.value = configRes.value.data.diffusion_template
      if (configRes.value.data.search_mode) searchMode.value = configRes.value.data.search_mode
      if (configRes.value.data.simulation_architecture) simulationArchitecture.value = configRes.value.data.simulation_architecture
      if (configRes.value.data.time_plan) {
        assignTimePlan(configRes.value.data.time_plan, configRes.value.data.time_plan_mode || 'auto')
      } else {
        assignTimePlan({
          total_rounds: configRes.value.data.temporal_profile?.total_rounds,
          minutes_per_round: configRes.value.data.temporal_profile?.minutes_per_round,
          preset: configRes.value.data.temporal_profile?.preset,
          reference_time: configRes.value.data.reference_time
        }, configRes.value.data.time_plan_mode || 'auto')
      }
    }

    if (realtimeRes.status === 'fulfilled' && realtimeRes.value?.success && realtimeRes.value.data) {
      configRealtime.value = realtimeRes.value.data
      const realtimeVariables = realtimeRes.value.data.config?.injected_variables || realtimeRes.value.data.injected_variables
      if (Array.isArray(realtimeVariables) && realtimeVariables.length > 0) {
        applyInjectedVariables(realtimeVariables, { sourceOrigin: 'runtime' })
      }
      if (realtimeRes.value.data.generation_stage) {
        prepareStage.value = realtimeRes.value.data.generation_stage
      }
      if (realtimeRes.value.data.progress !== undefined) {
        prepareProgress.value = realtimeRes.value.data.progress
      }
      if (realtimeRes.value.data.hazard_template_recommendation || realtimeRes.value.data.hazard_template_id) {
        applyHazardTemplate(realtimeRes.value.data.hazard_template_recommendation || realtimeRes.value.data, realtimeRes.value.data.hazard_template_mode || 'auto')
      }
      if (realtimeRes.value.data.transport_profile?.primary_family) {
        diffusionTemplate.value = realtimeRes.value.data.transport_profile.primary_family
      }
      if (realtimeRes.value.data.search_mode) {
        searchMode.value = realtimeRes.value.data.search_mode
      }
      if (realtimeRes.value.data.simulation_architecture || realtimeRes.value.data.config?.simulation_architecture) {
        simulationArchitecture.value = realtimeRes.value.data.simulation_architecture || realtimeRes.value.data.config?.simulation_architecture
      }
      if (realtimeRes.value.data.time_plan) {
        assignTimePlan(realtimeRes.value.data.time_plan, realtimeRes.value.data.time_plan_mode || 'auto')
      } else {
        assignTimePlan({
          total_rounds: realtimeRes.value.data.temporal_profile?.total_rounds,
          minutes_per_round: realtimeRes.value.data.temporal_profile?.minutes_per_round,
          preset: realtimeRes.value.data.temporal_profile?.preset,
          reference_time: realtimeRes.value.data.reference_time
        }, realtimeRes.value.data.time_plan_mode || 'auto')
      }
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
  if (isPreparing.value) return
  if (!props.simulationId) {
    prepareMessage.value = '请等待图谱完成并创建模拟入口'
    addLog('场景配置未提交：缺少 simulation_id')
    return
  }

  const autoTriggered = Boolean(options.auto)
  if (!isParameterLocked.value) {
    applyAutoScenarioRecommendations()
  }
  hasSubmittedParameters.value = true
  activeWorkspaceTab.value = 'risk'

  isPreparing.value = true
  phase.value = 'preparing'
  prepareProgress.value = 0
  prepareMessage.value = autoTriggered ? '正在自动生成正式代理体配置' : '正在提交 Kaleido 场景配置'
  emit('update-status', 'processing')
  addLog(
    `${autoTriggered ? '自动' : '手动'}提交 Kaleido 场景配置: ${scenarioMode.value} / ${hazardTemplateMeta.value.label} / ${searchMode.value} / ${temporalProfileLabel.value} / ${resolvedSimulationArchitecture.value}`
  )

  try {
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      engine_mode: 'envfish',
      simulation_architecture: resolvedSimulationArchitecture.value,
      scenario_mode: scenarioMode.value,
      hazard_template_id: hazardTemplateId.value,
      hazard_template_mode: hazardTemplateMode.value,
      diffusion_template: diffusionTemplate.value,
      search_mode: searchMode.value,
      temporal_preset: temporalPreset.value,
      time_plan_mode: timePlanMode.value,
      time_plan: {
        step_unit: timeStepUnit.value,
        step_size: timeStepSize.value,
        total_rounds: maxRounds.value,
        reference_time: '',
        reasoning_summary: timePlanReasoning.value
      },
      temporal_profile: {
        preset: temporalPreset.value,
        total_rounds: maxRounds.value,
        minutes_per_round: configuredMinutesPerRound.value
      },
      reference_time: '',
      diffusion_provider: 'auto',
      minutes_per_round: configuredMinutesPerRound.value,
      max_rounds: maxRounds.value,
      target_agent_count: isMechanismArchitecture.value ? mechanismTargetAgentCount.value : undefined,
      region_granularity: 'region',
      injected_variables: injectedVariables.value.map(serializeVariable)
    })

    if (res.success && res.data) {
      if (res.data.hazard_template_recommendation || res.data.hazard_template_id) {
        applyHazardTemplate(res.data.hazard_template_recommendation || res.data, res.data.hazard_template_mode || hazardTemplateMode.value)
      }
      if (res.data.time_plan) {
        assignTimePlan(res.data.time_plan, res.data.time_plan_mode || timePlanMode.value)
      } else if (res.data.temporal_profile?.minutes_per_round) {
        assignTimePlan({
          total_rounds: res.data.temporal_profile?.total_rounds,
          minutes_per_round: res.data.temporal_profile?.minutes_per_round,
          preset: res.data.temporal_profile?.preset,
          reference_time: res.data.reference_time
        }, res.data.time_plan_mode || timePlanMode.value)
      }
      if (res.data.simulation_architecture) simulationArchitecture.value = res.data.simulation_architecture
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
      if (data.hazard_template_recommendation || data.hazard_template_id) {
        applyHazardTemplate(data.hazard_template_recommendation || data, data.hazard_template_mode || hazardTemplateMode.value)
      }
      if (data.time_plan) {
        assignTimePlan(data.time_plan, data.time_plan_mode || timePlanMode.value)
      }
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
        addLog('✓ Kaleido 场景配置完成')
        stopTimers()
        await fetchConfigRealtime()
      } else if (data.status === 'failed' || data.status === 'cancelled') {
        phase.value = 'error'
        emit('update-status', 'error')
        addLog(data.status === 'cancelled'
          ? `✗ 场景配置已停止: ${data.error || '用户强制停止'}`
          : `✗ 场景配置失败: ${data.error || '未知错误'}`)
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
      if (res.data.hazard_template_recommendation || res.data.hazard_template_id) {
        applyHazardTemplate(res.data.hazard_template_recommendation || res.data, res.data.hazard_template_mode || hazardTemplateMode.value)
      }
      if (res.data.transport_profile?.primary_family) diffusionTemplate.value = res.data.transport_profile.primary_family
      if (res.data.diffusion_template) diffusionTemplate.value = res.data.diffusion_template
      if (res.data.search_mode) searchMode.value = res.data.search_mode
      if (res.data.time_plan) {
        assignTimePlan(res.data.time_plan, res.data.time_plan_mode || timePlanMode.value)
      } else {
        assignTimePlan({
          total_rounds: res.data.temporal_profile?.total_rounds,
          minutes_per_round: res.data.temporal_profile?.minutes_per_round,
          preset: res.data.temporal_profile?.preset,
          reference_time: res.data.reference_time
        }, res.data.time_plan_mode || timePlanMode.value)
      }
      syncPhaseFromSnapshots()
    }
  } catch (err) {
    console.warn('fetch config realtime failed', err)
  }
}

function handleNextStep() {
  emit('next-step', {
    scenarioMode: scenarioMode.value,
    simulationArchitecture: resolvedSimulationArchitecture.value,
    hazardTemplateId: hazardTemplateId.value,
    diffusionTemplate: diffusionTemplate.value,
    searchMode: searchMode.value,
    temporalPreset: temporalPreset.value,
    minutesPerRound: configuredMinutesPerRound.value,
    timePlan: {
      stepUnit: timeStepUnit.value,
      stepSize: timeStepSize.value,
      totalRounds: maxRounds.value,
      reasoningSummary: timePlanReasoning.value
    },
    referenceTime: toIsoFromLocal(referenceTimeLocal.value),
    maxRounds: maxRounds.value,
    targetAgentCount: isMechanismArchitecture.value ? mechanismTargetAgentCount.value : undefined,
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
  () => props.initialSimulationArchitecture,
  (value) => {
    if (value) simulationArchitecture.value = value
  }
)

watch(
  () => props.initialInjectedVariables,
  (value) => {
    const persistedVariables = configSnapshot.value?.injected_variables
    const realtimeVariables = configRealtime.value?.config?.injected_variables || configRealtime.value?.injected_variables
    const hasPersistedVariables = Array.isArray(persistedVariables) && persistedVariables.length > 0
    const hasRealtimeVariables = Array.isArray(realtimeVariables) && realtimeVariables.length > 0
    if (!hasPersistedVariables && !hasRealtimeVariables) {
      applyInjectedVariables(value, { sourceOrigin: 'seed' })
    }
  },
  { deep: true }
)

watch(
  () => props.simulationId,
  async (value, previousValue) => {
    if (!value || value === previousValue) return
    prepareMessage.value = '模拟入口已就绪，可以生成场景配置'
    await bootstrapSimulation()
  }
)

watch(
  [variableRegionOptions, variableNodeOptions],
  () => {
    syncVariableSelections()
  },
  { deep: true }
)

watch(
  injectedVariables,
  () => {
    applyAutoScenarioRecommendations()
  },
  { deep: true, immediate: true }
)

watch(
  shouldShowDisplayTabs,
  (visible) => {
    if (!visible && activeWorkspaceTab.value !== 'parameters') {
      activeWorkspaceTab.value = 'parameters'
    }
  },
  { immediate: true }
)

watch(
  searchMode,
  () => {
    simulationArchitecture.value = resolvedSimulationArchitecture.value
  },
  { immediate: true }
)

watch(
  [timeStepUnit, timeStepSize],
  ([unit, stepSize]) => {
    const nextMinutes = minutesForTimePlan(unit, stepSize)
    configuredMinutesPerRound.value = nextMinutes
    temporalPreset.value = presetFromMinutes(nextMinutes)
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
  addLog('Kaleido Step2 初始化')
  await bootstrapSimulation()
  if (props.simulationId) emitPhaseStatus()
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

/* ===== 场景简报布局：一句话头部 + 生成统计 + 可折叠分节（CSS order 重排，风险居前）===== */
.briefing-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.briefing-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #9aa3b2;
}
.briefing-title {
  margin: 5px 0 0;
  font-size: 20px;
  font-weight: 600;
  color: #173056;
}
.briefing-summary-line {
  margin: 6px 0 0;
  font-size: 13px;
  color: #5d687f;
}
.briefing-cta {
  flex-shrink: 0;
  white-space: nowrap;
}
.briefing-stats {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 14px 0;
  border-top: 0.5px solid rgba(29, 39, 58, 0.1);
  border-bottom: 0.5px solid rgba(29, 39, 58, 0.1);
}
.briefing-stats-label {
  font-size: 13px;
  color: #5d687f;
  max-width: 96px;
  line-height: 1.4;
  flex-shrink: 0;
}
.briefing-stat-row {
  display: flex;
  gap: 30px;
  flex-wrap: wrap;
}
.briefing-stat {
  display: flex;
  flex-direction: column;
}
.briefing-stat strong {
  font-size: 22px;
  font-weight: 600;
  color: #173056;
}
.briefing-stat span {
  font-size: 12px;
  color: #9aa3b2;
}

.briefing-section { order: 9; }
.bsec-parameters { order: 1; }
.bsec-risk { order: 2; }
.bsec-region { order: 3; }
.bsec-agents { order: 4; }
.bsec-relations { order: 5; }

.briefing-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  cursor: pointer;
  user-select: none;
}
.bh-chev {
  margin-left: auto;
  font-style: normal;
  font-size: 14px;
  color: #9aa3b2;
  transition: transform 0.18s ease;
}
.briefing-section.collapsed .bh-chev { transform: rotate(-90deg); }
.briefing-section.collapsed > :not(.briefing-head) { display: none !important; }
/* 折叠态紧凑：去掉 min-height 与标题下边距，只剩一行 */
.briefing-section.collapsed { min-height: 0 !important; overflow: visible; }
.briefing-section.collapsed .briefing-head { margin-bottom: 0; }

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
  flex-wrap: nowrap;
  justify-content: flex-start;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
  width: 100%;
}

.workspace-tab {
  min-width: 150px;
  flex-shrink: 0;
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

.secondary-btn:disabled,
.primary-btn:disabled,
.ghost-btn:disabled,
.remove-btn:disabled,
.template-card:disabled {
  cursor: not-allowed;
  opacity: 0.58;
  transform: none;
  box-shadow: none;
}

.mode-card.active,
.template-card.active {
  border-color: rgba(47, 110, 255, 0.55);
  background: linear-gradient(180deg, rgba(240, 245, 255, 1), rgba(227, 237, 255, 0.95));
}

.auto-template-card {
  border-radius: 18px;
  border: 1px solid rgba(47, 110, 255, 0.22);
  background: linear-gradient(180deg, rgba(248, 251, 255, 1), rgba(236, 244, 255, 0.94));
  padding: 14px;
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

.prepare-requirements {
  margin: 6px 0 0;
  color: #7b849e;
  font-size: 12px;
  line-height: 1.5;
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

input:disabled,
select:disabled,
textarea:disabled {
  background: rgba(240, 244, 252, 0.76);
  color: #7b849e;
  cursor: not-allowed;
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

.variable-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.variable-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 700;
}

.variable-badge.origin {
  background: rgba(48, 89, 178, 0.1);
  color: #3357a8;
}

.variable-badge.manual {
  background: rgba(24, 48, 88, 0.08);
  color: #42526f;
}

.variable-badge.hint {
  background: rgba(255, 180, 0, 0.12);
  color: #9a6b00;
}

.variable-draft-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(250, 244, 214, 0.7);
  border: 1px solid rgba(193, 152, 32, 0.18);
  color: #6a5520;
  font-size: 12px;
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

.baseline-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.baseline-metric {
  border: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 14px;
  padding: 12px;
  background: rgba(248, 251, 255, 0.86);
}

.baseline-metric span,
.baseline-metric small {
  display: block;
  font-size: 12px;
  color: #667899;
}

.baseline-metric strong {
  display: block;
  margin: 6px 0;
  font-size: 20px;
  color: #16315a;
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
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.agent-grid {
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}

.region-card,
.relation-card {
  border-radius: 18px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(20, 33, 61, 0.08);
  box-shadow: 0 8px 20px rgba(17, 31, 59, 0.04);
}

/* 说教灰字：折叠掉，不再用整段解释给数据缺陷打补丁 */
.parameter-lock-note,
.region-explain-box {
  display: none;
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

.region-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.region-tag-group {
  min-width: 0;
  padding: 10px;
  border-radius: 14px;
  background: rgba(247, 250, 255, 0.74);
  border: 1px solid rgba(20, 33, 61, 0.06);
}

.region-tag-title {
  display: block;
  margin-bottom: 8px;
  color: #60708f;
  font-size: 11px;
  font-weight: 800;
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

/* runtime tension / uncertainty band (additive) */
.risk-runtime-box {
  border-radius: 18px;
  padding: 14px;
  background: rgba(245, 248, 255, 0.78);
  border: 1px solid rgba(20, 33, 61, 0.08);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.risk-runtime-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.risk-runtime-head .runtime-hint {
  font-size: 11px;
  color: #7382a3;
}

.risk-runtime-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.runtime-tension-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(28, 196, 135, 0.12);
  color: #0d7a52;
  font-size: 12px;
}

.runtime-tension-pill strong {
  font-size: 15px;
  font-variant-numeric: tabular-nums;
}

.runtime-status-tag {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid currentColor;
}

.runtime-status-tag.is-rising,
.runtime-status-tag.is-elevated { color: #c2641a; }
.runtime-status-tag.is-critical { color: #c0392b; background: rgba(192, 57, 43, 0.08); }
.runtime-status-tag.is-falling { color: #0d7a52; }
.runtime-status-tag.is-steady { color: #5a6b8c; }

.runtime-turning-tag {
  font-size: 11px;
  padding: 3px 9px;
  border-radius: 999px;
  color: #8a4bcf;
  background: rgba(138, 75, 207, 0.1);
}

.tension-sparkline {
  color: #2f6fed;
  margin-left: auto;
}

.risk-uncertainty-band {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px dashed rgba(20, 33, 61, 0.14);
}

.risk-uncertainty-band .band-label {
  font-size: 11px;
  color: #7382a3;
}

.risk-uncertainty-band strong {
  color: #183058;
  font-variant-numeric: tabular-nums;
}

.risk-uncertainty-band small {
  color: #7382a3;
  font-weight: 500;
}

/* provenance tri-color dot (additive) */
.provenance-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 5px;
  vertical-align: middle;
}

.provenance-dot.is-observed { background: #1cc487; }
.provenance-dot.is-inferred {
  background: transparent;
  border: 1.5px dashed #e0a020;
}
.provenance-dot.is-assumed { background: #9aa6bd; }

/* perturbation vs stable-context (additive) */
.variable-kind-tag {
  margin-left: 8px;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 999px;
  vertical-align: middle;
}

.variable-kind-tag.perturbation {
  background: rgba(231, 111, 81, 0.14);
  color: #c2491f;
}

.variable-kind-tag.stable {
  background: rgba(90, 107, 140, 0.12);
  color: #4a5a7c;
}

.stable-context-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.stable-context-card {
  border-radius: 14px;
  padding: 12px;
  background: rgba(244, 246, 250, 0.7);
  border: 1px dashed rgba(74, 90, 124, 0.3);
}

.stable-context-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.stable-context-role {
  font-size: 10px;
  color: #4a5a7c;
}

.stable-context-card p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #4f5d78;
  line-height: 1.5;
}

.stable-context-meta {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  font-size: 11px;
  color: #7382a3;
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

/* 运行态明细全空时的一句话折叠（替代 4 张空卡） */
.risk-runtime-empty {
  font-size: 13px;
  color: #94a3b8;
  padding: 12px 14px;
  border: 1px dashed rgba(148, 163, 184, 0.32);
  border-radius: 12px;
  background: rgba(248, 250, 253, 0.5);
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

.log-summary {
  cursor: pointer;
  list-style-position: inside;
}

.log-summary .panel-title-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.logs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 180px;
  overflow: auto;
  padding-right: 4px;
  margin-top: 12px;
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

  .workspace-topbar {
    flex-direction: column;
  }

  .workspace-tabs {
    width: 100%;
    justify-content: flex-start;
  }

  .workspace-panel {
    min-height: 300px;
  }
}
</style>
