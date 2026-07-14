<template>
  <KaleidoWorkflowShell
    :step="4"
    step-name="分析与报告"
    :status-text="statusText"
    :status-tone="shellStatusTone"
    :view-mode="viewMode"
    :visual-ratio="46"
    @toggle-visual="toggleGraphCollapse"
  >
    <template #visual>
        <GraphPanel
          :graphData="animatedGraphData"
          :mapData="animatedMapProjection"
          :loading="graphLoading"
          :currentPhase="4"
          :isSimulating="false"
          :highlightNodeIds="graphHighlight.nodeIds"
          :highlightNodeNames="graphHighlight.nodeNames"
          :highlightEdgeIds="graphHighlight.edgeIds"
          :highlightLabel="graphHighlight.label"
          :highlightMode="graphHighlight.mode"
          :enableAnalysisActions="true"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
          @node-select="handleNodeSelect"
          @node-action="handleNodeAction"
        />
    </template>

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
            <div class="analysis-top-context">
              <section class="analysis-hero">
                <div class="hero-main">
                  <div class="hero-kicker">推演分析 · 第四步</div>
                  <h1 class="hero-title">{{ sanitizeDisplayCopy(overview.report_title, 'Kaleido 分析与报告') }}</h1>
                  <p class="hero-summary">
                    {{ overviewSummaryText }}
                  </p>
                </div>
                <div class="hero-metrics">
                  <div class="hero-metric">
                    <span class="metric-label">推演轮次</span>
                    <strong>{{ overview.max_round || overview.default_round || 0 }}</strong>
                  </div>
                  <div class="hero-metric">
                    <span class="metric-label">代理体</span>
                    <strong>{{ overview.node_stats?.agent_count || 0 }}</strong>
                  </div>
                  <div class="hero-metric">
                    <span class="metric-label">区域</span>
                    <strong>{{ overview.node_stats?.region_count || 0 }}</strong>
                  </div>
                  <div class="hero-metric">
                    <span class="metric-label">风险对象</span>
                    <strong>{{ overview.node_stats?.risk_object_count || 0 }}</strong>
                  </div>
                  <div class="hero-metric">
                    <span class="metric-label">涌现关系</span>
                    <strong>{{ overview.node_stats?.dynamic_edge_count || 0 }}</strong>
                  </div>
                </div>
              </section>

              <KWorkflowTabs
                class="analysis-primary-tabs"
                :items="tabs"
                :model-value="activeTab"
                variant="compact"
                :equal="true"
                :collapse-on-narrow="false"
                aria-label="分析与报告视图"
                @change="selectTab"
              />
            </div>

            <section class="tab-content">
              <div v-if="activeDataTab && tabLoading[activeDataTab]" class="analysis-state loading compact">
                <div class="loading-spinner"></div>
                <p>正在加载 {{ activeTabLabel }}...</p>
              </div>

              <div v-else-if="activeDataTab && tabErrors[activeDataTab]" class="analysis-state error compact">
                <div class="state-icon">!</div>
                <p>{{ tabErrors[activeDataTab] }}</p>
              </div>

              <template v-else-if="activeTab === 'conclusion'">
                <section class="conclusion-lead">
                  <div class="conclusion-lead-copy">
                    <span class="conclusion-label">当前结论</span>
                    <h2>{{ conclusionHeadline }}</h2>
                    <p>{{ conclusionSummary }}</p>
                  </div>
                  <div class="conclusion-round">
                    <span>结论轮次</span>
                    <strong>R{{ conclusionLatestRound?.round || overview.default_round || 0 }}</strong>
                  </div>
                </section>

                <section class="conclusion-grid">
                  <article class="conclusion-card is-focus">
                    <span>重点区域</span>
                    <strong>{{ safeVisibleText(conclusionLatestRound?.top_region?.name, '当前分析范围') }}</strong>
                    <p>脆弱性 {{ formatMetricValue(conclusionLatestRound?.top_region?.vulnerability_score) }}</p>
                  </article>
                  <article class="conclusion-card">
                    <span>主要放大器</span>
                    <strong>{{ safeVisibleText(conclusionLatestRound?.amplifier, '尚未检测到明确放大器') }}</strong>
                  </article>
                  <article class="conclusion-card">
                    <span>结论边界</span>
                    <strong>{{ safeVisibleText(conclusionLatestRound?.uncertainty, '当前结论需要结合演化轨迹和证据图理解。') }}</strong>
                  </article>
                </section>

                <section class="conclusion-evidence">
                  <div class="section-header">
                    <div>
                      <h3>结论依据</h3>
                      <p>结论来自真实轮次叙事、风险对象、动态关系和机制工件，不替代对原始证据的核查。</p>
                    </div>
                    <span>{{ conclusionEvidenceCount }} 项可追溯产物</span>
                  </div>
                  <div class="conclusion-stat-grid">
                    <div><span>轮次记录</span><strong>{{ narrativeTab?.rounds?.length || 0 }}</strong></div>
                    <div><span>风险事件</span><strong>{{ overview.node_stats?.risk_event_count || 0 }}</strong></div>
                    <div><span>机制关系</span><strong>{{ overview.node_stats?.mechanism_edge_count || 0 }}</strong></div>
                    <div><span>图谱证据</span><strong>{{ overview.node_stats?.graph_node_count || 0 }}</strong></div>
                  </div>
                </section>

                <section v-if="conclusionTurningPoints.length" class="conclusion-evidence">
                  <div class="section-header">
                    <h3>关键转折点</h3>
                    <span>{{ conclusionTurningPoints.length }} 条</span>
                  </div>
                  <ol class="turning-timeline conclusion-turning-list">
                    <li v-for="point in conclusionTurningPoints" :key="point" class="turning-item">
                      <span class="turning-marker"></span>
                      <span class="turning-text">{{ point }}</span>
                    </li>
                  </ol>
                </section>

                <nav class="conclusion-next-actions" aria-label="继续查看分析">
                  <button type="button" class="mini-btn primary" @click="openEvolutionView('narrative')">查看演化过程</button>
                  <button type="button" class="mini-btn" @click="selectTab('mechanisms')">查看风险与机制</button>
                  <button type="button" class="mini-btn" @click="selectTab('node-explore')">追溯图谱证据</button>
                  <button type="button" class="mini-btn" @click="selectTab('report')">打开正式报告</button>
                </nav>
              </template>

              <template v-else-if="activeTab === 'evolution'">
                <KWorkflowTabs
                  class="evolution-view-tabs"
                  :items="evolutionViews"
                  :model-value="evolutionView"
                  variant="compact"
                  :equal="true"
                  :collapse-on-narrow="false"
                  aria-label="演化复盘视角"
                  @change="setEvolutionView"
                />
                <section class="control-bar" v-if="regionsTab" v-show="evolutionView === 'regions'">
                  <div class="control-group">
                    <span class="control-label">指标</span>
                    <select v-model="selectedMetric" class="control-select">
                      <option v-for="metric in regionsTab.metric_options || []" :key="metric.key" :value="metric.key">
                        {{ safeVisibleText(metric.label, '状态指标') }}
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
                      v-if="timelineRoundValues.length > 0"
                      v-model.number="selectedRound"
                      class="round-slider"
                      type="range"
                      :min="timelineRoundValues[0] || 1"
                      :max="timelineRoundValues[timelineRoundValues.length - 1] || 1"
                      step="1"
                    />
                  </div>
                </section>

                <section v-if="currentRoundSnapshot" v-show="evolutionView === 'regions'" class="region-layout">
                  <div class="metric-highlight">
                    <div class="metric-highlight-head">
                      <span class="metric-highlight-title">区域态势</span>
                      <span class="metric-highlight-meta">当前指标：{{ currentMetricLabel }}</span>
                    </div>
                    <div class="metric-highlight-sub">
                      {{ safeVisibleText(selectedFrameNarrative, `当前展示第 ${selectedRound} 轮的区域与子区域状态，数值越高表示该指标越强。`) }}
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
                            <h4>{{ safeVisibleText(region.name, '未命名区域') }}</h4>
                            <p>{{ safeToken(region.region_type, '区域') }}</p>
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
                            <h4>{{ safeVisibleText(subregion.name, '未命名子区域') }}</h4>
                            <p>{{ resolveRegionName(subregion.parent_region_id) || safeToken(subregion.region_type, '子区域') }}</p>
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
                <section class="role-comparison" v-if="rolesTab" v-show="evolutionView === 'roles'">
                  <div class="role-table-head" aria-hidden="true">
                    <span>角色群体</span>
                    <span>节点</span>
                    <span>核心状态</span>
                    <span>主要影响区域</span>
                  </div>
                  <article v-for="group in roleGroupsForDisplay" :key="group.group_id" class="role-table-row">
                    <div class="role-identity">
                      <h3>{{ safeVisibleText(group.title, '角色分组') }}</h3>
                      <p>{{ safeVisibleText(group.description, '该分组汇总了相近角色的状态。') }}</p>
                    </div>
                    <strong class="role-node-count">{{ group.node_count }}</strong>
                    <dl class="role-metrics-flat">
                      <div v-for="metric in group.focus_metrics || []" :key="metric.key">
                        <dt>{{ safeVisibleText(metric.label, '状态指标') }}</dt>
                        <dd>{{ formatMetricValue(group.metric_averages?.[metric.key]) }}</dd>
                      </div>
                    </dl>
                    <div v-if="group.visible_dominant_regions.length" class="role-region-primary">
                      <span>{{ group.visible_dominant_regions[0].display_name }}</span>
                      <strong>{{ formatMetricValue(group.visible_dominant_regions[0].score) }}</strong>
                    </div>
                    <span v-else class="role-region-empty">暂无明确区域</span>
                  </article>
                </section>

                <template v-if="evolutionView === 'feedback'">
                  <section class="feedback-header" v-if="feedbackTab">
                    <div class="feedback-chain-template">
                      <span v-for="(stage, idx) in feedbackTab.chain_template || []" :key="stage" class="chain-stage">
                        {{ safeVisibleText(stage, '反馈阶段') }}<span v-if="idx < (feedbackTab.chain_template || []).length - 1" class="chain-arrow">→</span>
                      </span>
                    </div>
                  </section>
                  <section class="feedback-grid" v-if="feedbackTab">
                    <article v-for="item in feedbackTab.items || []" :key="item.id" class="feedback-card">
                      <div class="feedback-card-head">
                        <div>
                          <h4>{{ safeVisibleText(item.region_name, resolveRegionName(item.region_id) || '反馈传播链') }}</h4>
                          <p>第 {{ item.round || feedbackTab.current_round }} 轮</p>
                        </div>
                        <span class="source-chip">{{ safeToken(item.source_type, '运行反馈') }}</span>
                      </div>
                      <div class="feedback-loop">{{ safeVisibleText(item.loop, '系统记录到一次反馈变化。') }}</div>
                      <div class="delta-grid">
                        <span v-for="(value, key) in item.delta || {}" :key="key" class="delta-chip">
                          {{ feedbackDeltaLabel(key) }} {{ formatDelta(value) }}
                        </span>
                      </div>
                      <div v-if="safeSourceText(item.source)" class="feedback-source">{{ safeSourceText(item.source) }}</div>
                    </article>
                  </section>
                  <section v-if="feedbackTab?.ecological_impacts?.length" class="secondary-section">
                    <div class="section-header">
                      <h3>生态影响</h3>
                      <span>{{ feedbackTab.ecological_impacts.length }} 条</span>
                    </div>
                    <div class="secondary-list">
                      <article v-for="item in feedbackTab.ecological_impacts" :key="item.id" class="secondary-card">
                        <strong>{{ safeVisibleText(item.region_name, '未知区域') }}</strong>
                        <p>{{ safeVisibleText(item.note, '已记录生态影响。') }}</p>
                      </article>
                    </div>
                  </section>
                </template>

                <template v-if="evolutionView === 'narrative'">
                  <section class="narrative-trace-note" v-if="narrativeTab">
                    这是一条<strong>探索轨迹</strong>，记录每轮的关系张力与不确定性，不是对未来的预测。
                  </section>
                  <section class="narrative-list" v-if="narrativeTab">
                    <article v-for="round in (narrativeTab.rounds || []).slice(-4).reverse()" :key="round.round" class="narrative-card">
                      <div class="narrative-head">
                        <div>
                          <h3>第 {{ round.round }} 轮</h3>
                          <p>{{ formatTimestamp(round.timestamp) }}</p>
                        </div>
                        <div class="narrative-head-tags">
                          <span
                            v-if="round.narrative_source"
                            class="source-badge"
                            :class="isLiveNarrative(round.narrative_source) ? 'live' : 'template'"
                            :title="isLiveNarrative(round.narrative_source) ? '叙事来源：实时推理' : '叙事来源：规则归纳'"
                          >
                            {{ isLiveNarrative(round.narrative_source) ? '实时推理' : '规则归纳' }}
                          </span>
                          <span class="metric-pill">
                            {{ safeVisibleText(round.top_region?.name, '当前分析范围') }}
                          </span>
                        </div>
                      </div>
                      <div class="narrative-columns">
                        <div class="narrative-block">
                          <span class="block-label">本轮最关键变化</span>
                          <p>{{ safeVisibleText(round.headline, '本轮未记录显著变化。') }}</p>
                        </div>
                        <div class="narrative-block">
                          <span class="block-label">主要传播或放大器</span>
                          <p>{{ safeVisibleText(round.amplifier, '本轮变化主要由场景内既有机制共同作用。') }}</p>
                        </div>
                        <div class="narrative-block">
                          <span class="block-label">最大不确定性</span>
                          <p>{{ safeVisibleText(round.uncertainty, '当前结论仍需结合证据核查。') }}</p>
                        </div>
                      </div>

                      <div
                        v-if="normalizeFeedbackLoops(round.detected_feedback_loops).length"
                        class="loop-chip-section"
                      >
                        <span class="block-label">检测到的反馈环</span>
                        <div class="loop-chip-wrap">
                          <span
                            v-for="(loop, idx) in normalizeFeedbackLoops(round.detected_feedback_loops).slice(0, 3)"
                            :key="`${round.round}-loop-${idx}`"
                            class="loop-chip"
                            :class="`loop-${loop.loopType || 'unknown'}`"
                            :title="loop.loopType ? loopTypeLabel(loop.loopType) + '回路' : '反馈环'"
                          >
                            <span class="loop-chip-dot"></span>
                            <span class="loop-chip-label">{{ safeVisibleText(loop.label, '反馈环') }}</span>
                            <span v-if="loop.loopType" class="loop-chip-type">{{ loopTypeLabel(loop.loopType) }}</span>
                          </span>
                          <span v-if="normalizeFeedbackLoops(round.detected_feedback_loops).length > 3" class="loop-chip">+{{ normalizeFeedbackLoops(round.detected_feedback_loops).length - 3 }}</span>
                        </div>
                      </div>

                      <div
                        v-if="normalizeTurningPoints(round.turning_points).length"
                        class="turning-section"
                      >
                        <span class="block-label">转折点</span>
                        <ol class="turning-timeline">
                          <li
                            v-for="(point, idx) in normalizeTurningPoints(round.turning_points).slice(0, 3)"
                            :key="`${round.round}-turn-${idx}`"
                            class="turning-item"
                          >
                            <span class="turning-marker"></span>
                            <span class="turning-text">{{ safeVisibleText(point, '已记录一次转折。') }}</span>
                          </li>
                        </ol>
                      </div>
                    </article>
                  </section>
                </template>
              </template>

              <template v-else-if="activeTab === 'mechanisms'">
                <section class="mechanism-layout" v-if="mechanismsTab">
                  <header class="mechanism-overview">
                    <div class="mechanism-overview-copy">
                      <h2>风险与机制链</h2>
                      <p>{{ safeVisibleText(mechanismsTab.scenario_model?.scenario_summary, '当前案例尚未生成机制工件。') }}</p>
                    </div>
                    <dl class="mechanism-inline-stats" aria-label="风险与机制统计">
                      <div><dt>风险对象</dt><dd>{{ overview.node_stats?.risk_object_count || 0 }}</dd></div>
                      <div><dt>风险事件</dt><dd>{{ overview.node_stats?.risk_event_count || 0 }}</dd></div>
                      <div><dt>机制节点</dt><dd>{{ overview.node_stats?.mechanism_node_count || 0 }}</dd></div>
                      <div><dt>机制关系</dt><dd>{{ overview.node_stats?.mechanism_edge_count || 0 }}</dd></div>
                    </dl>
                  </header>

                  <template v-if="mechanismHasDetail">
                  <section v-if="mechanismsTab.scenario_model?.state_variables?.length" class="mechanism-section">
                    <div class="mechanism-section-head">
                      <h3>场景状态变量</h3>
                      <span>{{ mechanismsTab.scenario_model?.state_variables?.length || 0 }} 个</span>
                    </div>
                    <div class="mechanism-state-list">
                      <article v-for="item in mechanismsTab.scenario_model.state_variables" :key="item.key" class="mechanism-state-row">
                        <strong>{{ safeVisibleText(item.label, '状态变量') }}</strong>
                        <span>{{ safeToken(item.polarity, '中性') }}</span>
                        <p>{{ safeVisibleText(item.description, '该变量参与场景状态演化。') }}</p>
                      </article>
                    </div>
                  </section>

                  <section v-if="mechanismsTab.mechanism_graph?.edges?.length" class="mechanism-section">
                    <div class="mechanism-section-head">
                      <h3>机制链</h3>
                      <span>前 {{ Math.min(mechanismsTab.mechanism_graph.edges.length, 5) }} 条 · 共 {{ mechanismsTab.mechanism_graph.edges.length }} 条</span>
                    </div>
                    <div class="mechanism-relation-list">
                      <article v-for="edge in mechanismsTab.mechanism_graph.edges.slice(0, 5)" :key="edge.id" class="mechanism-relation-row">
                        <div class="mechanism-relation-route">
                          <span>{{ safeVisibleText(edge.source_label, '上游机制') }}</span>
                          <span aria-hidden="true">→</span>
                          <span>{{ safeVisibleText(edge.target_label, '下游机制') }}</span>
                        </div>
                        <div class="mechanism-relation-copy">
                          <strong>{{ safeVisibleText(edge.relation_label, safeToken(edge.relation_type, '机制链')) }}</strong>
                          <p>{{ safeVisibleText(edge.mechanism, '已记录机制关系。') }}</p>
                        </div>
                        <div class="mechanism-relation-meta">
                          <span>{{ safeVisibleText(edge.scope_label, safeToken(edge.scope, '机制')) }}</span>
                          <span>延迟 {{ safeToken(edge.latency, '未知') }}</span>
                          <span>置信 {{ formatMetricValue((edge.confidence || 0) * 100) }}</span>
                        </div>
                      </article>
                    </div>
                  </section>

                  <section v-if="mechanismsTab.relation_samples?.length" class="mechanism-section">
                    <div class="mechanism-section-head">
                      <h3>关系发现样本</h3>
                      <span>前 {{ Math.min(mechanismsTab.relation_samples.length, 5) }} 条 · 共 {{ mechanismsTab.relation_samples.length }} 条</span>
                    </div>
                    <div class="mechanism-note-list">
                      <article v-for="item in mechanismsTab.relation_samples.slice(0, 5)" :key="item.edge_id || item.index" class="mechanism-note-row">
                        <strong>{{ safeVisibleText(item.relation_label, safeToken(item.candidate?.relation_label, '关系')) }}</strong>
                        <p>{{ safeVisibleText(item.candidate?.mechanism || item.reason, '已记录一条关系发现。') }}</p>
                      </article>
                    </div>
                  </section>

                  <section v-if="mechanismsTab.round_reasoning?.length" class="mechanism-section">
                    <div class="mechanism-section-head">
                      <h3>轮次推理账本</h3>
                      <span>最近 {{ Math.min(mechanismsTab.round_reasoning.length, 5) }} 轮 · 共 {{ mechanismsTab.round_reasoning.length }} 轮</span>
                    </div>
                    <div class="mechanism-note-list">
                      <article v-for="item in mechanismsTab.round_reasoning.slice(-5).reverse()" :key="item.round" class="mechanism-note-row">
                        <strong>第 {{ item.round }} 轮 · {{ safeToken(item.llm_participation, '已记录') }}</strong>
                        <p>{{ safeVisibleText(item.summary || item.reasoning_summary, safeToken(item.fallback_reason, '本轮已记录机制推理。')) }}</p>
                      </article>
                    </div>
                  </section>

                  <section v-if="mechanismsTab.simulation_audit?.quality_flags?.length" class="mechanism-section">
                    <div class="mechanism-section-head">
                      <h3>质量标记</h3>
                      <span>{{ mechanismsTab.simulation_audit.quality_flags.length }} 个</span>
                    </div>
                    <ul class="mechanism-quality-list">
                      <li v-for="flag in mechanismsTab.simulation_audit.quality_flags" :key="flag">
                        {{ safeVisibleText(flag, '质量复核项') }}
                      </li>
                    </ul>
                  </section>
                  </template>
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
                      <div class="hero-kicker node-kicker">证据探索</div>
                      <h2>{{ safeVisibleText(selectedNode.name, '未命名节点') }}</h2>
                      <div class="chip-wrap">
                        <span
                          v-if="selectedNodeProvenance"
                          class="provenance-badge"
                          :class="`prov-${selectedNodeProvenance.tone}`"
                          :title="selectedNodeGroundingReason || selectedNodeProvenance.label"
                        >
                          {{ selectedNodeProvenance.label }}
                        </span>
                        <span v-for="label in safeVisibleList(selectedNode.labels, 3)" :key="label" class="data-chip">{{ label }}</span>
                      </div>
                      <p v-if="selectedNodeGroundingReason" class="grounding-reason">
                        来源说明：{{ safeVisibleText(selectedNodeGroundingReason, '来源信息已记录。') }}
                      </p>
                    </div>
                    <div class="node-hero-actions">
                      <button
                        v-if="selectedNodeEvidenceRefs.length"
                        class="mini-btn"
                        :class="{ active: evidenceDrawerOpen }"
                        @click="toggleEvidenceDrawer"
                      >
                        证据 ({{ selectedNodeEvidenceRefs.length }})
                      </button>
                      <button class="mini-btn" @click="refreshNodeContext">刷新上下文</button>
                      <button class="mini-btn primary" :disabled="nodeExploreLoading" @click="runNodeExplore">
                        {{ nodeExploreLoading ? '分析中...' : '深度探索' }}
                      </button>
                    </div>
                  </section>

                  <section
                    v-if="evidenceDrawerOpen && selectedNodeEvidenceRefs.length"
                    class="evidence-drawer"
                  >
                    <div class="section-header">
                      <h3>证据来源</h3>
                      <span>{{ selectedNodeEvidenceRefs.length }} 条</span>
                    </div>
                    <ul class="evidence-list">
                      <li v-for="(ref, idx) in selectedNodeEvidenceRefs" :key="`evidence-${idx}`" class="evidence-item">
                        <strong>{{ safeVisibleText(ref.label, `证据 ${idx + 1}`) }}</strong>
                        <span v-if="ref.detail">{{ safeVisibleText(ref.detail, '已记录证据说明。') }}</span>
                      </li>
                    </ul>
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
                          <span>{{ safeToken(nodeContext.supported_modes?.exploration_mode, '上下文探索') }}</span>
                        </div>
                        <div class="context-list">
                          <div class="context-item">
                            <span>节点类型</span>
                            <strong>{{ safeToken(nodeContext.node_kind, '图谱节点') }}</strong>
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
                          <span v-for="item in safeVisibleList(nodeContext.missing_data, 3, '待补充数据')" :key="item" class="warning-chip">{{ item }}</span>
                        </div>
                      </article>

                      <article class="context-card">
                        <div class="section-header">
                          <h3>关系子图预览</h3>
                          <span>{{ nodeContext.subgraph?.edges?.length || 0 }} 条边</span>
                        </div>
                        <div class="subgraph-list">
                          <div v-for="edge in (nodeContext.subgraph?.edges || []).slice(0, 8)" :key="edge.uuid || `${edge.source_node_uuid}-${edge.target_node_uuid}`" class="subgraph-item">
                            <strong>{{ safeVisibleText(edge.source_node_name, '来源节点') }}</strong>
                            <span>{{ safeToken(edge.name, '关联') }}</span>
                            <strong>{{ safeVisibleText(edge.target_node_name, '目标节点') }}</strong>
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
                          <h3>{{ safeVisibleText(section.title, '探索结果') }}</h3>
                          <span>{{ safeVisibleText(selectedNode.name, '当前节点') }}</span>
                        </div>
                        <div class="explore-items">
                          <div v-for="item in section.items || []" :key="`${section.id}-${item.label}-${item.content}`" class="explore-item">
                            <div class="explore-item-head">
                              <strong>{{ safeVisibleText(item.label, '分析项') }}</strong>
                              <span
                                class="source-chip"
                                :class="provenanceMeta(item.source_type) ? `prov-${provenanceMeta(item.source_type).tone}` : ''"
                              >{{ provenanceMeta(item.source_type)?.label || '推断' }}</span>
                            </div>
                            <p>{{ safeVisibleText(item.content, '该分析项暂无可展示内容。') }}</p>
                          </div>
                        </div>
                      </article>
                    </section>

                    <section class="chat-box">
                      <div class="section-header">
                        <h3>围绕该节点继续追问</h3>
                        <span>上下文锁定为 {{ safeVisibleText(selectedNode.name, '当前节点') }}</span>
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
                          <p>{{ safeVisibleText(message.content, '消息内容不可用。') }}</p>
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
                    v-if="reportId"
                    :reportId="reportId"
                    :simulationId="simulationId"
                    :systemLogs="systemLogs"
                    @add-log="addLog"
                    @update-status="updateStatus"
                  />
                </div>
              </template>
            </section>
          </template>
        </div>
  </KaleidoWorkflowShell>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoWorkflowShell from '../components/KaleidoWorkflowShell.vue'
import GraphPanel from '../components/GraphPanel.vue'
import Step4Report from '../components/Step4Report.vue'
import KWorkflowTabs from '../components/ui/KWorkflowTabs.vue'
import {
  chatWithReportNode,
  exploreReportNode,
  getReportAnalysisGraph,
  getReportAnalysisOverview,
  getReportAnalysisTab,
  getReportNodeContext,
} from '../api/report'
import { getSimulationAnimation } from '../api/simulation'
import { markWorkflowStep } from '../store/workflowNavigation'
import { safeDisplayError, safeDisplayText as safeDisplayCopyText, sanitizeDisplayCopy, translateDisplayToken } from '../utils/displayText'
import { normalizeDominantRegions } from '../utils/analysisDisplay'

const route = useRoute()
const router = useRouter()

const INVALID_VISIBLE_COPY = new Set(['内部标识', '未命名项', '内容待本地化'])
const safeVisibleText = (value, fallback = '') => {
  const text = safeDisplayCopyText(value, '').trim()
  if (!text || INVALID_VISIBLE_COPY.has(text)) return fallback
  return text
}
const safeToken = (value, fallback = '') => safeVisibleText(translateDisplayToken(value, ''), fallback)
const safeVisibleList = (values, limit = 3, fallback = '') => {
  if (!Array.isArray(values)) return []
  const normalized = values.map(value => safeVisibleText(value, fallback)).filter(Boolean)
  return [...new Set(normalized)].slice(0, limit)
}
const safeErrorMessage = (error, fallback) => {
  return safeDisplayError(error, fallback)
}

// Step 4 保持五个稳定入口；旧的数据 tab 作为「演化复盘」子视图继续按需读取。
const tabs = [
  { id: 'conclusion', label: '结论总览' },
  { id: 'evolution', label: '演化复盘' },
  { id: 'mechanisms', label: '风险与机制' },
  { id: 'node-explore', label: '证据探索' },
  { id: 'report', label: '正式报告' },
]

const evolutionViews = [
  { id: 'narrative', label: '轮次叙事' },
  { id: 'regions', label: '区域态势' },
  { id: 'roles', label: '角色透镜' },
  { id: 'feedback', label: '反馈链' },
]

const viewMode = ref('split') // 与 Step 2/3 保持一致，默认同时查看图谱与分析内容
const reportId = ref(route.params.reportId)
const simulationId = ref('')
const graphId = ref('')
const graphData = ref(null)
const graphLoading = ref(false)
const animationData = ref(null)
const graphHighlight = ref({ nodeIds: [], nodeNames: [], edgeIds: [], label: '', mode: '' })
const systemLogs = ref([])
const currentStatus = ref('processing')

const overview = ref(null)
const overviewLoading = ref(false)
const overviewError = ref('')

const activeTab = ref('conclusion')
const evolutionView = ref('narrative')
const loadedTabs = ref(new Set())
const tabData = ref({
  regions: null,
  mechanisms: null,
  feedback: null,
  roles: null,
  narrative: null,
})
const tabLoading = ref({
  regions: false,
  mechanisms: false,
  feedback: false,
  roles: false,
  narrative: false,
})
const tabErrors = ref({
  regions: '',
  mechanisms: '',
  feedback: '',
  roles: '',
  narrative: '',
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
let overviewPollErrorCount = 0

const statusClass = computed(() => {
  if (overview.value?.report_status === 'failed') return 'error'
  if (overview.value?.report_status === 'completed') return 'completed'
  return currentStatus.value
})

const statusText = computed(() => {
  if (statusClass.value === 'error') return '展示当前可用分析内容'
  if (statusClass.value === 'completed') return '分析与报告'
  if (currentStatus.value === 'ready' && overview.value?.report_status !== 'completed') return '分析结果 · 报告生成中'
  if (currentStatus.value === 'ready') return '分析结果'
  return '分析生成中'
})

const shellStatusTone = computed(() => {
  if (statusClass.value === 'error') return 'error'
  if (statusClass.value === 'processing') return 'processing'
  return 'ready'
})

const activeTabLabel = computed(() => tabs.find(tab => tab.id === activeTab.value)?.label || '分析')
const regionsTab = computed(() => tabData.value.regions)
const mechanismsTab = computed(() => tabData.value.mechanisms)
const feedbackTab = computed(() => tabData.value.feedback)
const rolesTab = computed(() => tabData.value.roles)
const narrativeTab = computed(() => tabData.value.narrative)
const activeDataTab = computed(() => {
  if (activeTab.value === 'conclusion') return 'narrative'
  if (activeTab.value === 'evolution') return evolutionView.value
  if (activeTab.value === 'mechanisms') return 'mechanisms'
  return ''
})
const conclusionRounds = computed(() => Array.isArray(narrativeTab.value?.rounds) ? narrativeTab.value.rounds : [])
const conclusionLatestRound = computed(() => conclusionRounds.value[conclusionRounds.value.length - 1] || null)
const GENERIC_REPORT_SUMMARIES = new Set(['暂无摘要', '暂无说明', '暂无可展示内容', '结果正在整理'])
const concreteReportSummary = value => {
  const text = sanitizeDisplayCopy(value, '').trim()
  return text && !GENERIC_REPORT_SUMMARIES.has(text) ? text : ''
}
const reportSummaryText = computed(() => concreteReportSummary(overview.value?.report_summary))
const overviewSummaryText = computed(() => (
  reportSummaryText.value
  || concreteReportSummary(conclusionLatestRound.value?.headline)
  || concreteReportSummary(conclusionLatestRound.value?.amplifier)
  || '基于多轮区域状态、反馈链、角色透镜与节点证据形成分析结果。'
))
const conclusionHeadline = computed(() => sanitizeDisplayCopy(
  conclusionLatestRound.value?.headline || reportSummaryText.value,
  '推演结果正在形成结论。'
))
const conclusionSummary = computed(() => {
  if (reportSummaryText.value) return reportSummaryText.value
  if (conclusionLatestRound.value?.amplifier) return sanitizeDisplayCopy(conclusionLatestRound.value.amplifier)
  return '请结合演化复盘、机制链和证据图理解本次推演结果。'
})
const conclusionTurningPoints = computed(() => {
  const points = conclusionRounds.value.flatMap(round => normalizeTurningPoints(round?.turning_points))
  return [...new Set(points.filter(Boolean))].slice(-6)
})
const conclusionEvidenceCount = computed(() => {
  const stats = overview.value?.node_stats || {}
  return Number(conclusionRounds.value.length || 0)
    + Number(stats.risk_event_count || 0)
    + Number(stats.mechanism_edge_count || 0)
    + Number(stats.graph_node_count || 0)
})
// 机制空则折叠：没有任何机制工件时，只显示一句说明，不再渲染 5 个空段
const mechanismHasDetail = computed(() => {
  const m = mechanismsTab.value
  if (!m) return false
  return Boolean(
    m.scenario_model?.state_variables?.length ||
    m.mechanism_graph?.edges?.length ||
    m.relation_samples?.length ||
    m.round_reasoning?.length ||
    m.simulation_audit?.quality_flags?.length
  )
})
const regionsRounds = computed(() => regionsTab.value?.rounds || [])
const animationFrames = computed(() => Array.isArray(animationData.value?.frames) ? animationData.value.frames : [])
const timelineRoundValues = computed(() => {
  const animationRounds = animationFrames.value
    .map(frame => Number(frame.round))
    .filter(round => Number.isFinite(round) && round > 0)
  if (animationRounds.length) return animationRounds
  return regionsRounds.value
    .map(item => Number(item.round))
    .filter(round => Number.isFinite(round))
})
const selectedAnimationFrame = computed(() => {
  if (!animationFrames.value.length) return null
  return animationFrames.value.find(frame => Number(frame.round) === Number(selectedRound.value)) || null
})
const selectedFrameNarrative = computed(() => selectedAnimationFrame.value?.narrative?.summary || '')
const animationBaseMapProjection = computed(() => {
  const layout = animationData.value?.layout || {}
  const layoutNodes = Array.isArray(layout.nodes) ? layout.nodes : []
  const layoutEdges = Array.isArray(layout.edges) ? layout.edges : []
  return {
    center: layout.center || {},
    zoom_hint: layout.zoom_hint || 10,
    radius_m: layout.radius_m || 0,
    layers: Array.isArray(layout.base_layers) ? layout.base_layers : [],
    nodes: layoutNodes.map((node) => ({
      uuid: node.id,
      name: node.name,
      kind: node.kind,
      labels: node.labels || [],
      summary: node.summary || '',
      attributes: {
        ...(node.attributes || {}),
        lat: node.lat ?? node.attributes?.lat,
        lon: node.lon ?? node.attributes?.lon,
      },
    })),
    edges: layoutEdges.map((edge) => ({
      uuid: edge.id,
      source_node_uuid: edge.source,
      target_node_uuid: edge.target,
      fact_type: edge.fact_type,
      name: edge.name,
      fact: edge.fact || '',
      attributes: { ...(edge.attributes || {}) },
    })),
  }
})
const animatedGraphData = computed(() => applyAnimationToGraph(graphData.value, selectedAnimationFrame.value))
const animatedMapProjection = computed(() => applyAnimationToMapProjection(animationBaseMapProjection.value, selectedAnimationFrame.value))
const currentRoundSnapshot = computed(() => {
  if (!regionsRounds.value.length) return null
  return regionsRounds.value.find(item => Number(item.round) === Number(selectedRound.value)) || regionsRounds.value[regionsRounds.value.length - 1]
})
const currentMetricLabel = computed(() => {
  const options = regionsTab.value?.metric_options || []
  const configuredLabel = options.find(item => item.key === selectedMetric.value)?.label
  return safeVisibleText(configuredLabel, safeToken(selectedMetric.value, '状态指标'))
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

const buildStateMap = (items = []) => {
  const map = new Map()
  ;(Array.isArray(items) ? items : []).forEach((item) => {
    const id = String(item?.id || '')
    if (id) map.set(id, item)
  })
  return map
}

const applyAnimationToGraph = (graph, frame) => {
  if (!graph || !frame) return graph
  const nodeStates = buildStateMap(frame.node_states)
  const edgeStates = buildStateMap(frame.edge_states)
  if (!nodeStates.size) return graph
  const nodes = (Array.isArray(graph.nodes) ? graph.nodes : [])
    .filter((node) => {
      const nodeId = String(node?.uuid || node?.id || '')
      const state = nodeStates.get(nodeId)
      return !state || state.status !== 'hidden'
    })
    .map((node) => {
      const nodeId = String(node?.uuid || node?.id || '')
      const state = nodeStates.get(nodeId) || {}
      return {
        ...node,
        attributes: {
          ...(node?.attributes || {}),
          animation_status: state.status || 'steady',
          first_seen_round: state.first_seen_round,
          last_active_round: state.last_active_round,
          delay_ms: state.delay_ms,
        },
      }
    })
  const visibleNodeIds = new Set(nodes.map((node) => String(node?.uuid || node?.id || '')))
  const edges = (Array.isArray(graph.edges) ? graph.edges : [])
    .filter((edge) => {
      const edgeId = String(edge?.uuid || edge?.id || '')
      const sourceId = String(edge?.source_node_uuid || edge?.source || '')
      const targetId = String(edge?.target_node_uuid || edge?.target || '')
      const state = edgeStates.get(edgeId)
      return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId) && (!state || state.status !== 'hidden')
    })
    .map((edge) => {
      const edgeId = String(edge?.uuid || edge?.id || '')
      const state = edgeStates.get(edgeId) || {}
      return {
        ...edge,
        attributes: {
          ...(edge?.attributes || {}),
          animation_status: state.status || 'steady',
          first_seen_round: state.first_seen_round,
          last_active_round: state.last_active_round,
          delay_ms: state.delay_ms,
        },
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
      edge_count: edges.length,
    },
  }
}

const applyAnimationToMapProjection = (projection, frame) => {
  if (!projection || !frame) return projection
  const nodeStates = buildStateMap(frame.node_states)
  const edgeStates = buildStateMap(frame.edge_states)
  if (!nodeStates.size) return projection
  const nodes = (Array.isArray(projection.nodes) ? projection.nodes : [])
    .filter((node) => {
      const state = nodeStates.get(String(node?.uuid || node?.id || ''))
      return !state || state.status !== 'hidden'
    })
    .map((node) => {
      const nodeId = String(node?.uuid || node?.id || '')
      const state = nodeStates.get(nodeId) || {}
      return {
        ...node,
        attributes: {
          ...(node?.attributes || {}),
          animation_status: state.status || 'steady',
          first_seen_round: state.first_seen_round,
          last_active_round: state.last_active_round,
          delay_ms: state.delay_ms,
        },
      }
    })
  const visibleNodeIds = new Set(nodes.map((node) => String(node?.uuid || node?.id || '')))
  const edges = (Array.isArray(projection.edges) ? projection.edges : [])
    .filter((edge) => {
      const edgeId = String(edge?.uuid || edge?.id || '')
      const sourceId = String(edge?.source_node_uuid || edge?.source || '')
      const targetId = String(edge?.target_node_uuid || edge?.target || '')
      const state = edgeStates.get(edgeId)
      return visibleNodeIds.has(sourceId) && visibleNodeIds.has(targetId) && (!state || state.status !== 'hidden')
    })
    .map((edge) => {
      const edgeId = String(edge?.uuid || edge?.id || '')
      const state = edgeStates.get(edgeId) || {}
      return {
        ...edge,
        attributes: {
          ...(edge?.attributes || {}),
          animation_status: state.status || 'steady',
          first_seen_round: state.first_seen_round,
          last_active_round: state.last_active_round,
          delay_ms: state.delay_ms,
        },
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
      edge_count: edges.length,
    },
  }
}

const updateStatus = (status) => {
  if (!status) return
  overview.value = {
    ...(overview.value || {}),
    report_status: status,
  }
  currentStatus.value = resolveAnalysisStatus(overview.value)
  syncWorkflowStatus(currentStatus.value)
  if (status === 'completed' || status === 'failed') stopOverviewPolling()
}

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

const metricWidth = (value) => {
  const safe = Number(value || 0)
  return `${Math.max(0, Math.min(100, safe))}%`
}

// 区域 ID（slug/uuid）→ 真实名称查表，杜绝 jianghan_market_corridor / 未命名节点 之类泄漏
const regionNameById = computed(() => {
  const map = {}
  const add = (list) => {
    ;(list || []).forEach(r => {
      const id = r?.region_id || r?.id || r?.uuid
      const name = safeVisibleText(r?.name || r?.region_name, '')
      if (id && name) map[String(id)] = name
    })
  }
  add(currentRoundSnapshot.value?.regions)
  add(currentRoundSnapshot.value?.subregions)
  add(regionsTab.value?.regions)
  add(regionsTab.value?.subregions)
  add(graphData.value?.nodes)
  return map
})
const resolveRegionName = (id) => (id ? safeVisibleText(regionNameById.value[String(id)], '') : '')
const roleGroupsForDisplay = computed(() => (rolesTab.value?.groups || []).map(group => ({
  ...group,
  visible_dominant_regions: normalizeDominantRegions(group?.dominant_regions, resolveRegionName),
})))
// 内部点分路径（latest_snapshot.feedback.xxx）不上屏
const isInternalSourcePath = (text) => /^[a-z0-9_]+(\.[a-z0-9_]+)+$/i.test(String(text || '').trim())
const safeSourceText = (value) => {
  if (!value || isInternalSourcePath(value)) return ''
  return safeVisibleText(value, '')
}

const formatMetricValue = (value) => {
  if (value === null || value === undefined || value === '') return '暂无'
  const num = Number(value)
  return Number.isFinite(num) ? num.toFixed(1) : '暂无'
}

const formatDelta = (value) => {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '暂无'
  return `${num > 0 ? '+' : ''}${num.toFixed(1)}`
}

const formatTimestamp = (value) => {
  if (!value) return '无时间戳'
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return '时间不可用'
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return '时间不可用'
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
  return map[key] || '其他指标'
}

// --- M9 honesty helpers (additive, guarded) -------------------------------
// detected_feedback_loops / turning_points may arrive as plain strings OR as
// objects ({region_names, loop_type, description, ...}); normalize both shapes
// so the UI never breaks on missing fields.
const normalizeFeedbackLoop = (loop) => {
  if (loop === null || loop === undefined) return null
  if (typeof loop === 'string') {
    const text = loop.trim()
    if (!text) return null
    return { label: safeVisibleText(text, '反馈环'), loopType: '', regions: [] }
  }
  if (typeof loop !== 'object') return null
  const regions = Array.isArray(loop.region_names)
    ? loop.region_names.filter(Boolean).map(item => String(item))
    : []
  const loopType = String(loop.loop_type || '').toLowerCase()
  const label = regions.length
    ? regions.join(' → ')
    : String(loop.loop || loop.description || loop.label || loop.name || '反馈环')
  return { label: safeVisibleText(label, '反馈环'), loopType, regions: safeVisibleList(regions, 3, '未知区域') }
}

const normalizeFeedbackLoops = (loops) => {
  if (!Array.isArray(loops)) return []
  return loops.map(normalizeFeedbackLoop).filter(Boolean)
}

const loopTypeLabel = (loopType) => {
  if (loopType === 'reinforcing') return '增强'
  if (loopType === 'balancing') return '平衡'
  return safeToken(loopType, '回路')
}

const normalizeTurningPoint = (point) => {
  if (point === null || point === undefined) return null
  if (typeof point === 'string') {
    const text = point.trim()
    return safeVisibleText(text, '') || null
  }
  if (typeof point !== 'object') return null
  const text = point.description || point.note || point.label || point.name || ''
  return safeVisibleText(text, '') || null
}

const normalizeTurningPoints = (points) => {
  if (!Array.isArray(points)) return []
  return points.map(normalizeTurningPoint).filter(Boolean)
}

const isLiveNarrative = (source) => source === 'snapshot.reasoning.summary'

// Provenance / source_type honesty tri-state. Maps observed/inferred/assumed
// (and the Chinese deterministic labels the backend already emits) onto a
// stable {key, label, tone} triple for badge styling.
const provenanceMeta = (raw) => {
  const token = String(raw || '').trim().toLowerCase()
  const observed = new Set(['observed', '直接观测', '观测'])
  const inferred = new Set(['inferred', '多轮推断', '推断', '机制工件'])
  const assumed = new Set(['assumed', '假设', '图谱补全', '模板'])
  if (observed.has(token) || observed.has(String(raw || '').trim())) {
    return { key: 'observed', label: '观测', tone: 'observed' }
  }
  if (inferred.has(token) || inferred.has(String(raw || '').trim())) {
    return { key: 'inferred', label: '推断', tone: 'inferred' }
  }
  if (assumed.has(token) || assumed.has(String(raw || '').trim())) {
    return { key: 'assumed', label: '假设', tone: 'assumed' }
  }
  if (!raw) return null
  return { key: 'other', label: '其他来源', tone: 'neutral' }
}

const selectedNodeProvenance = computed(() => {
  const attrs = nodeContext.value?.node?.attributes || {}
  return provenanceMeta(attrs.provenance || attrs.source_type)
})

const selectedNodeEvidenceRefs = computed(() => {
  const attrs = nodeContext.value?.node?.attributes || {}
  const refs = attrs.evidence_refs
  if (!Array.isArray(refs)) return []
  return refs
    .map((ref) => {
      if (ref === null || ref === undefined) return null
      if (typeof ref === 'string') {
        const label = safeVisibleText(ref, '')
        return label ? { label, detail: '' } : null
      }
      if (typeof ref !== 'object') return null
      const label = ref.label || ref.ref || ref.source || ref.name || ''
      const detail = ref.detail || ref.note || ref.description || ref.quote || ''
      return {
        label: safeVisibleText(label, ''),
        detail: safeVisibleText(detail, '')
      }
    })
    .filter((item) => item && item.label)
})

const selectedNodeGroundingReason = computed(() => {
  const attrs = nodeContext.value?.node?.attributes || {}
  const reason = attrs.grounding_reason
  return safeVisibleText(reason, '')
})

const evidenceDrawerOpen = ref(false)
const toggleEvidenceDrawer = () => {
  evidenceDrawerOpen.value = !evidenceDrawerOpen.value
}

const resolveAnalysisStatus = (data) => {
  const statusMap = {
    pending: 'processing',
    planning: 'processing',
    generating: 'processing',
    completed: 'completed',
    failed: 'error',
  }
  if (data?.report_status === 'failed' || data?.report_status === 'completed') {
    return statusMap[data.report_status]
  }
  if (data?.analysis_ready) return 'ready'
  return statusMap[data?.report_status] || 'ready'
}

const syncWorkflowStatus = (status = currentStatus.value) => {
  const reportStatus = overview.value?.report_status || ''
  const reportDone = reportStatus === 'completed' || status === 'completed'
  const reportFailed = reportStatus === 'failed' || status === 'error'
  const analysisAvailable = Boolean(overview.value?.analysis_ready) || ['ready', 'completed'].includes(status)
  const simulationRoute = simulationId.value
    ? { name: 'SimulationRun', params: { simulationId: simulationId.value } }
    : null
  markWorkflowStep(3, {
    visited: true,
    status: 'done',
    summary: '推演结果',
    route: simulationRoute
  })
  markWorkflowStep(4, {
    visited: true,
    status: reportDone ? 'done' : 'active',
    summary: reportDone
      ? '分析与正式报告'
      : reportFailed
        ? '当前展示已生成的分析内容'
        : analysisAvailable
          ? '分析可查看，正式报告生成中'
          : '结果分析中',
    route: { name: 'Analysis', params: { reportId: reportId.value }, query: { ...route.query } }
  })
}

const normalizeTab = (value) => {
  if (['narrative', 'feedback', 'regions', 'roles'].includes(value)) return 'evolution'
  const valid = new Set(tabs.map(tab => tab.id))
  return valid.has(value) ? value : 'conclusion'
}

const normalizeEvolutionView = (value) => {
  const valid = new Set(['narrative', 'regions', 'roles', 'feedback'])
  return valid.has(value) ? value : 'narrative'
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
      addLog(`结果图谱加载失败：${safeErrorMessage(res.error, '服务暂时不可用')}`)
    }
  } catch (err) {
    graphData.value = null
    addLog(`结果图谱加载异常：${safeErrorMessage(err, '服务暂时不可用')}`)
  } finally {
    graphLoading.value = false
  }
}

const loadAnimationData = async () => {
  animationData.value = null
  if (!simulationId.value) return
  try {
    const res = await getSimulationAnimation(simulationId.value)
    if (res.success && res.data) {
      animationData.value = res.data
      addLog(`统一动画载入：${res.data.frames?.length || 0} 帧 / ${res.data.layout?.nodes?.length || 0} 节点`)
    } else {
      addLog(`统一动画载入失败：${safeErrorMessage(res.error, '动画数据不可用')}`)
    }
  } catch (err) {
    addLog(`统一动画载入异常：${safeErrorMessage(err, '动画数据不可用')}`)
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
    overviewPollErrorCount = 0
    currentStatus.value = resolveAnalysisStatus(res.data)
    syncWorkflowStatus(currentStatus.value)
    if (res.data.report_status === 'completed' || res.data.report_status === 'failed') {
      stopOverviewPolling()
    }
  } catch (err) {
    overviewPollErrorCount += 1
    if (overviewPollErrorCount === 1 || overviewPollErrorCount % 5 === 0) {
      addLog(`结果分析状态轮询暂时失败，将继续重试：${safeErrorMessage(err, '服务暂时不可用')}`)
    }
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
    syncWorkflowStatus(currentStatus.value)
    selectedRound.value = res.data.default_round || 1

    await loadAnimationData()
    await refreshGraph()

    const nextTab = normalizeTab(route.query.tab)
    activeTab.value = nextTab
    const legacyEvolutionView = ['narrative', 'feedback', 'regions', 'roles'].includes(route.query.tab)
      ? route.query.tab
      : route.query.view
    evolutionView.value = normalizeEvolutionView(legacyEvolutionView)
    await ensureActiveViewLoaded(nextTab)
    startOverviewPolling()
  } catch (err) {
    overviewError.value = safeErrorMessage(err, '结果分析加载失败')
    currentStatus.value = 'error'
    stopOverviewPolling()
  } finally {
    overviewLoading.value = false
  }
}

const ensureTabLoaded = async (tabId) => {
  if (!['regions', 'mechanisms', 'feedback', 'roles', 'narrative'].includes(tabId)) return
  if (loadedTabs.value.has(tabId) || tabLoading.value[tabId]) return
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
    tabErrors.value[tabId] = safeErrorMessage(err, '当前分析视图加载失败')
  } finally {
    tabLoading.value[tabId] = false
  }
}

const ensureActiveViewLoaded = async (tabId = activeTab.value) => {
  if (tabId === 'conclusion') {
    await ensureTabLoaded('narrative')
    return
  }
  if (tabId === 'evolution') {
    await ensureTabLoaded(evolutionView.value)
    return
  }
  if (tabId === 'mechanisms') await ensureTabLoaded('mechanisms')
}

const setEvolutionView = async (view) => {
  const normalized = normalizeEvolutionView(view)
  evolutionView.value = normalized
  stopPlayback()
  if (activeTab.value === 'evolution') {
    await router.replace({ query: { ...route.query, tab: 'evolution', view: normalized } })
    await ensureTabLoaded(normalized)
  }
}

const openEvolutionView = async (view = 'narrative') => {
  const normalized = normalizeEvolutionView(view)
  activeTab.value = 'evolution'
  evolutionView.value = normalized
  stopPlayback()
  await router.replace({ query: { ...route.query, tab: 'evolution', view: normalized } })
  await ensureTabLoaded(normalized)
}

const selectTab = async (tabId) => {
  const normalized = normalizeTab(tabId)
  activeTab.value = normalized
  const nextQuery = { ...route.query, tab: normalized }
  if (normalized === 'evolution') nextQuery.view = evolutionView.value
  await router.replace({ query: nextQuery })
  stopPlayback()
  await ensureActiveViewLoaded(normalized)
}

const stopPlayback = () => {
  if (playbackTimer) {
    window.clearTimeout(playbackTimer)
    playbackTimer = null
  }
  isPlaying.value = false
}

const resolvePlaybackDelayMs = (frame = null) => {
  const baseSpeed = Number(animationData.value?.meta?.default_speed_ms || 1800)
  const frameDuration = Number(frame?.playback_duration_ms || baseSpeed)
  return Math.max(420, Math.round(frameDuration))
}

const queueNextPlaybackTick = () => {
  if (!isPlaying.value || !timelineRoundValues.value.length) return
  const waitMs = resolvePlaybackDelayMs(selectedAnimationFrame.value)
  playbackTimer = window.setTimeout(() => {
    const roundValues = timelineRoundValues.value
    const currentIndex = roundValues.findIndex(item => item === Number(selectedRound.value))
    const nextIndex = currentIndex >= roundValues.length - 1 ? 0 : currentIndex + 1
    selectedRound.value = roundValues[nextIndex]
    queueNextPlaybackTick()
  }, waitMs)
}

const stepRound = (direction) => {
  if (!timelineRoundValues.value.length) return
  const roundValues = timelineRoundValues.value
  const currentIndex = roundValues.findIndex(item => item === Number(selectedRound.value))
  const nextIndex = currentIndex < 0 ? 0 : Math.max(0, Math.min(roundValues.length - 1, currentIndex + direction))
  selectedRound.value = roundValues[nextIndex]
}

const togglePlayback = () => {
  if (isPlaying.value) {
    stopPlayback()
    return
  }
  if (!timelineRoundValues.value.length) return
  isPlaying.value = true
  queueNextPlaybackTick()
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
    nodeContextError.value = safeErrorMessage(err, '节点上下文加载失败')
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
    nodeExploreError.value = safeErrorMessage(err, '节点深度探索失败')
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
      content: '当前节点证据暂不足以形成进一步判断，请补充轮次范围或换一个具体问题。',
    })
    addLog(`节点追问处理异常: ${safeErrorMessage(err, '服务暂时不可用')}`)
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
    tabData.value = { regions: null, mechanisms: null, feedback: null, roles: null, narrative: null }
    await loadOverview()
  },
  { immediate: true }
)

watch(
  [() => route.query.tab, () => route.query.view],
  async ([tab, view]) => {
    const normalized = normalizeTab(tab)
    activeTab.value = normalized
    if (normalized === 'evolution') {
      const legacyView = ['narrative', 'feedback', 'regions', 'roles'].includes(tab) ? tab : view
      evolutionView.value = normalizeEvolutionView(legacyView)
    }
    stopPlayback()
    await ensureActiveViewLoaded(normalized)
  }
)

watch(
  selectedAnimationFrame,
  (frame) => {
    if (!frame) {
      graphHighlight.value = { nodeIds: [], nodeNames: [], edgeIds: [], label: '', mode: '' }
      return
    }
    graphHighlight.value = {
      nodeIds: Array.isArray(frame.focus_ids?.node_ids) ? frame.focus_ids.node_ids : [],
      nodeNames: [],
      edgeIds: Array.isArray(frame.focus_ids?.edge_ids) ? frame.focus_ids.edge_ids : [],
      label: safeVisibleText(frame.narrative?.title, '当前轮次'),
      mode: 'animation',
    }
    if (isPlaying.value) {
      window.clearTimeout(playbackTimer)
      playbackTimer = null
      queueNextPlaybackTick()
    }
  },
  { immediate: true }
)

onMounted(() => {
  addLog('AnalysisView 初始化')
  syncWorkflowStatus('processing')
})

onBeforeUnmount(() => {
  stopPlayback()
  stopOverviewPolling()
})
</script>

<style scoped>
.main-view {
  height: 100dvh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  background: #f5f6f8;
  overflow: hidden;
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
  position: relative;
  z-index: 1000;
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
  flex: 1 1 auto;
  display: flex;
  height: calc(100dvh - 60px);
  min-height: 0;
  overflow: hidden;
}

.panel-wrapper {
  min-height: 0;
  height: 100%;
  transition: width 0.28s ease, opacity 0.28s ease, transform 0.28s ease;
  overflow: hidden;
}

.panel-wrapper.left {
  height: 100%;
}

.analysis-panel {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px 20px 0;
  gap: 0;
  overflow: hidden;
}

.analysis-top-context {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 12px;
  background: #f5f6f8;
}

/* 巨型竖排 hero → 单行细条：标题 + 摘要（截断）在左，指标内联在右 */
.analysis-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 28px;
  padding: 12px 22px;
  border-radius: 16px;
  background: linear-gradient(135deg, #102a43 0%, #1f5f5b 56%, #d8b04c 100%);
  color: #f8fafc;
}

.hero-main {
  flex: 1 1 340px;
  min-width: 0;
}

.hero-kicker {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: rgba(248, 250, 252, 0.58);
  flex-shrink: 0;
}

.hero-title {
  margin: 2px 0 0;
  font-size: 19px;
  line-height: 1.25;
}

.hero-summary {
  margin: 0;
  flex: 1 1 220px;
  min-width: 0;
  font-size: 12px;
  line-height: 1.4;
  color: rgba(248, 250, 252, 0.78);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 20px;
  min-width: 0;
  flex-shrink: 0;
}

.hero-metric {
  padding: 0;
  border-radius: 0;
  background: transparent;
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.metric-label {
  font-size: 12px;
  color: rgba(248, 250, 252, 0.7);
}

.hero-metric strong {
  font-size: 18px;
}

.tab-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.1);
}

.tab-btn {
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  padding: 8px 2px 10px;
  font-size: 13px;
  font-weight: 700;
  color: #475569;
  cursor: pointer;
  transition: color 0.2s ease, border-color 0.2s ease;
}

.tab-btn.active {
  color: #0f5f58;
  border-bottom-color: #0f766e;
}

.tab-btn:hover {
  color: #0f172a;
}

.tab-btn:focus-visible {
  outline: 2px solid #0f766e;
  outline-offset: 3px;
}

.tab-content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 4px 4px 24px;
  overscroll-behavior: contain;
}

.evolution-view-tabs {
  flex: 0 0 auto;
}

.analysis-primary-tabs :deep(.k-workflow-tabs__list) {
  gap: 0;
}

.analysis-primary-tabs :deep(.k-workflow-tabs__tab) {
  justify-content: center;
  min-width: 0;
  padding-inline: 4px;
  font-size: 13px;
  white-space: nowrap;
}

.evolution-view-tabs :deep(.k-workflow-tabs__list) {
  gap: 0;
}

.evolution-view-tabs :deep(.k-workflow-tabs__tab) {
  justify-content: center;
  min-width: 7rem;
  min-height: 2.75rem;
  padding-inline: 12px;
  font-size: 13px;
}

.role-comparison {
  display: flex;
  flex-direction: column;
}

.role-table-head,
.role-table-row {
  display: grid;
  grid-template-columns: minmax(170px, 1.15fr) 52px minmax(220px, 1fr) minmax(120px, 0.7fr);
  gap: 18px;
  align-items: center;
}

.role-table-head {
  padding: 10px 12px;
  border-bottom: 1px solid var(--k-color-border-strong);
  color: var(--k-color-text-muted);
  font-size: 11px;
  font-weight: 650;
}

.role-table-row {
  padding: 18px 12px;
  border-bottom: 1px solid var(--k-color-border);
}

.role-identity {
  min-width: 0;
}

.role-identity h3 {
  margin: 0;
  color: var(--k-color-text);
  font-size: 16px;
  line-height: 1.35;
}

.role-identity p {
  display: -webkit-box;
  margin: 5px 0 0;
  overflow: hidden;
  color: var(--k-color-text-muted);
  font-size: 12px;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.role-node-count {
  color: var(--k-color-text);
  font-size: 18px;
  font-variant-numeric: tabular-nums;
}

.role-metrics-flat {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
}

.role-metrics-flat div {
  min-width: 0;
}

.role-metrics-flat dt {
  overflow: hidden;
  color: var(--k-color-text-muted);
  font-size: 11px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-metrics-flat dd {
  margin: 4px 0 0;
  color: var(--k-color-text);
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.role-region-primary {
  display: flex;
  min-width: 0;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.role-region-primary span {
  overflow: hidden;
  color: var(--k-color-text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-region-primary strong {
  flex: 0 0 auto;
  color: var(--k-color-brand-700);
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.role-region-empty {
  color: var(--k-color-text-muted);
  font-size: 12px;
}

.mechanism-layout {
  display: flex;
  flex-direction: column;
}

.mechanism-overview {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) auto;
  gap: 32px;
  align-items: start;
  padding: 18px 4px 24px;
  border-bottom: 1px solid var(--k-color-border-strong);
}

.mechanism-overview-copy h2 {
  margin: 0;
  color: var(--k-color-text);
  font-size: 20px;
  line-height: 1.3;
}

.mechanism-overview-copy p {
  max-width: 72ch;
  margin: 9px 0 0;
  color: var(--k-color-text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.mechanism-inline-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(72px, 1fr));
  margin: 0;
}

.mechanism-inline-stats div {
  min-width: 0;
  padding: 2px 14px;
  border-left: 1px solid var(--k-color-border);
}

.mechanism-inline-stats dt {
  color: var(--k-color-text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.mechanism-inline-stats dd {
  margin: 5px 0 0;
  color: var(--k-color-text);
  font-size: 19px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.mechanism-section {
  padding: 24px 4px;
  border-bottom: 1px solid var(--k-color-border);
}

.mechanism-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 8px;
}

.mechanism-section-head h3 {
  margin: 0;
  color: var(--k-color-text);
  font-size: 16px;
}

.mechanism-section-head span {
  color: var(--k-color-text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.mechanism-state-list,
.mechanism-relation-list,
.mechanism-note-list {
  display: flex;
  flex-direction: column;
}

.mechanism-state-row {
  display: grid;
  grid-template-columns: minmax(170px, 0.7fr) 92px minmax(280px, 1.7fr);
  gap: 18px;
  align-items: start;
  padding: 14px 0;
  border-top: 1px solid var(--k-color-border);
}

.mechanism-state-row strong,
.mechanism-relation-copy strong,
.mechanism-note-row strong {
  color: var(--k-color-text);
  font-size: 13px;
  line-height: 1.5;
}

.mechanism-state-row > span {
  color: var(--k-color-text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.mechanism-state-row p,
.mechanism-relation-copy p,
.mechanism-note-row p {
  margin: 0;
  color: var(--k-color-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.mechanism-relation-row {
  display: grid;
  grid-template-columns: minmax(180px, 0.85fr) minmax(260px, 1.5fr) auto;
  gap: 20px;
  align-items: start;
  padding: 16px 0;
  border-top: 1px solid var(--k-color-border);
}

.mechanism-relation-route {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 7px;
  align-items: center;
  color: var(--k-color-text-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.mechanism-relation-route span:not(:nth-child(2)) {
  overflow: hidden;
  text-overflow: ellipsis;
}

.mechanism-relation-copy {
  min-width: 0;
}

.mechanism-relation-copy p {
  margin-top: 4px;
}

.mechanism-relation-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px 0;
  max-width: 190px;
  color: var(--k-color-text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.mechanism-relation-meta span + span::before {
  margin: 0 6px;
  content: '\00b7';
}

.mechanism-note-row {
  display: grid;
  grid-template-columns: minmax(170px, 0.55fr) minmax(280px, 1.45fr);
  gap: 20px;
  align-items: start;
  padding: 14px 0;
  border-top: 1px solid var(--k-color-border);
}

.mechanism-quality-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.mechanism-quality-list li {
  padding: 12px 0;
  border-top: 1px solid var(--k-color-border);
  color: var(--k-color-text-secondary);
  font-size: 12px;
  line-height: 1.55;
}

@container analysis (max-width: 44rem) {
  .role-table-head {
    display: none;
  }

  .role-table-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 14px 18px;
  }

  .role-node-count::after {
    margin-left: 4px;
    color: var(--k-color-text-muted);
    font-size: 11px;
    font-weight: 500;
    content: '个节点';
  }

  .role-metrics-flat,
  .role-region-primary,
  .role-region-empty {
    grid-column: 1 / -1;
  }

  .mechanism-overview {
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .mechanism-inline-stats div:first-child {
    border-left: 0;
  }

  .mechanism-state-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 5px 18px;
  }

  .mechanism-state-row p {
    grid-column: 1 / -1;
  }

  .mechanism-relation-row,
  .mechanism-note-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .mechanism-relation-meta {
    justify-content: flex-start;
    max-width: none;
  }
}

@container analysis (max-width: 34rem) {
  .mechanism-inline-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mechanism-inline-stats div:nth-child(3) {
    border-left: 0;
  }

  .mechanism-inline-stats div:nth-child(n + 3) {
    margin-top: 12px;
  }

  .mechanism-state-row {
    grid-template-columns: 1fr;
  }

  .mechanism-state-row p {
    grid-column: auto;
  }
}

.conclusion-lead {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 28px;
  align-items: end;
  padding: 26px 28px 30px;
  border-radius: 22px;
  background: #ffffff;
  border: 1px solid rgba(15, 118, 110, 0.14);
}

.conclusion-label {
  display: block;
  margin-bottom: 10px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.conclusion-lead h2 {
  max-width: 920px;
  margin: 0;
  color: #10231d;
  font-size: var(--k-text-display);
  line-height: 1.25;
  letter-spacing: -0.025em;
  text-wrap: balance;
}

.conclusion-lead p {
  max-width: 72ch;
  margin: 14px 0 0;
  color: #52635b;
  line-height: 1.7;
}

.conclusion-round {
  min-width: 112px;
  padding-left: 24px;
  border-left: 1px solid rgba(15, 118, 110, 0.16);
}

.conclusion-round span,
.conclusion-card > span,
.conclusion-stat-grid span {
  display: block;
  color: #6d7d74;
  font-size: 11px;
  font-weight: 700;
}

.conclusion-round strong {
  display: block;
  margin-top: 5px;
  color: #0f5f58;
  font-size: 28px;
  font-variant-numeric: tabular-nums;
}

.conclusion-grid {
  display: grid;
  grid-template-columns: 0.85fr 1.2fr 1.2fr;
  gap: 12px;
}

.conclusion-card {
  min-width: 0;
  padding: 18px 20px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.conclusion-card.is-focus {
  background: rgba(15, 118, 110, 0.08);
  border-color: rgba(15, 118, 110, 0.14);
}

.conclusion-card strong {
  display: block;
  margin-top: 9px;
  color: #173126;
  font-size: 15px;
  line-height: 1.55;
}

.conclusion-card p {
  margin: 7px 0 0;
  color: #5f7067;
  font-size: 12px;
}

.conclusion-evidence {
  padding: 20px 22px;
  border-radius: 18px;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.conclusion-evidence .section-header p {
  max-width: 72ch;
  margin: 5px 0 0;
  color: #647067;
  font-size: 12px;
  line-height: 1.55;
}

.conclusion-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.conclusion-stat-grid > div {
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
}

.conclusion-stat-grid strong {
  display: block;
  margin-top: 5px;
  color: #173126;
  font-size: 20px;
  font-variant-numeric: tabular-nums;
}

.conclusion-turning-list {
  margin-top: 16px;
}

.conclusion-next-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.node-kicker {
  color: #0f766e;
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

.chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

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
  min-height: auto;
  overflow: visible;
}

/* --- M9 honesty UI (narrative loops / turning points / provenance) ------ */
.narrative-trace-note {
  padding: 12px 16px;
  border-radius: 16px;
  background: rgba(15, 118, 110, 0.08);
  border: 1px dashed rgba(15, 118, 110, 0.3);
  color: #0f766e;
  font-size: 13px;
  line-height: 1.6;
}

.narrative-trace-note strong {
  color: #0f5f58;
}

.narrative-head-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.source-badge {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--k-color-border-strong);
  border-radius: 999px;
  padding: 3px 8px;
  background: transparent;
  font-size: var(--k-text-caption);
  font-weight: var(--k-weight-semibold);
}

.source-badge.live {
  border-color: rgba(31, 93, 69, 0.35);
  background: transparent;
  color: var(--k-color-brand-600);
}

.source-badge.template {
  border-color: var(--k-color-border-strong);
  background: transparent;
  color: var(--k-color-text-muted);
}

.loop-chip-section,
.turning-section {
  margin-top: 16px;
}

.loop-chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.loop-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
  background: rgba(148, 163, 184, 0.14);
  color: #334155;
  border: 1px solid transparent;
}

.loop-chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  flex: 0 0 auto;
}

.loop-chip-type {
  font-size: 10px;
  font-weight: 700;
  opacity: 0.85;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
}

.loop-chip.loop-reinforcing {
  background: rgba(220, 38, 38, 0.1);
  color: #b91c1c;
  border-color: rgba(220, 38, 38, 0.24);
}

.loop-chip.loop-balancing {
  background: rgba(37, 99, 235, 0.1);
  color: #1d4ed8;
  border-color: rgba(37, 99, 235, 0.24);
}

.turning-timeline {
  list-style: none;
  margin: 10px 0 0;
  padding: 0 0 0 6px;
  border-left: 2px solid rgba(216, 176, 76, 0.5);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.turning-item {
  position: relative;
  padding-left: 16px;
  line-height: 1.6;
  color: #0f172a;
  font-size: 13px;
}

.turning-marker {
  position: absolute;
  left: -7px;
  top: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #d8b04c;
  box-shadow: 0 0 0 3px rgba(216, 176, 76, 0.2);
}

.provenance-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 700;
}

.provenance-badge.prov-observed,
.source-chip.prov-observed {
  background: rgba(5, 150, 105, 0.14);
  color: #047857;
}

.provenance-badge.prov-inferred,
.source-chip.prov-inferred {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.provenance-badge.prov-assumed,
.source-chip.prov-assumed {
  background: rgba(202, 138, 4, 0.16);
  color: #92600a;
}

.provenance-badge.prov-neutral,
.source-chip.prov-neutral {
  background: rgba(148, 163, 184, 0.16);
  color: #475569;
}

.grounding-reason {
  margin: 8px 0 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.55;
}

.mini-btn.active {
  background: rgba(15, 118, 110, 0.12);
  border-color: rgba(15, 118, 110, 0.4);
  color: #0f766e;
}

.evidence-drawer {
  border-radius: 22px;
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  padding: 18px 20px;
}

.evidence-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.evidence-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.04);
}

.evidence-item strong {
  font-size: 13px;
  color: #0f172a;
}

.evidence-item span {
  font-size: 12px;
  color: #64748b;
  line-height: 1.55;
}

@media (max-width: 1280px) {
  .analysis-hero,
  .node-context-grid,
  .narrative-columns,
  .conclusion-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .hero-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    min-width: 0;
  }
}

@media (max-width: 900px) {
  .main-view {
    height: auto;
    min-height: 100dvh;
    overflow: visible;
  }

  .app-header {
    padding: 0 14px;
  }

  .content-area {
    flex-direction: column;
    height: auto;
    min-height: calc(100dvh - 60px);
    overflow: visible;
  }

  .panel-wrapper.left,
  .panel-wrapper.right {
    width: 100% !important;
    height: auto;
    min-height: 0;
    opacity: 1 !important;
    transform: none !important;
    overflow: visible;
  }

  .panel-wrapper.left {
    height: 52dvh;
  }

  .analysis-panel {
    height: auto;
    padding: 14px;
    overflow: visible;
  }

  .analysis-top-context {
    position: static;
  }

  .tab-content {
    flex: 0 0 auto;
    overflow: visible;
    padding-inline: 0;
  }

  .hero-metrics,
  .card-grid,
  .feedback-grid,
  .secondary-list,
  .conclusion-stat-grid {
    grid-template-columns: 1fr;
  }

  .conclusion-lead {
    grid-template-columns: 1fr;
    align-items: start;
  }

  .conclusion-round {
    padding: 14px 0 0;
    border-top: 1px solid rgba(15, 118, 110, 0.16);
    border-left: 0;
  }
}

/* Step 4 visual contract: shared shell, green interaction color and outline metadata. */
.analysis-panel {
  container-name: analysis;
  container-type: inline-size;
  padding: 14px 16px 0;
  color: var(--k-color-text);
  background: var(--k-color-page);
}

.analysis-top-context {
  gap: 8px;
  padding-bottom: 8px;
  background: var(--k-color-page);
}

.analysis-hero {
  padding: 12px 16px;
  border: 1px solid var(--k-color-border);
  border-radius: var(--k-radius-lg);
  background: var(--k-color-surface);
  color: var(--k-color-text);
  box-shadow: var(--k-shadow-raised);
}

.hero-kicker,
.metric-label,
.hero-summary {
  color: var(--k-color-text-muted);
}

.hero-title,
.hero-metric strong {
  color: var(--k-color-text);
}

.control-select,
.chat-input {
  min-height: var(--k-control-height-md);
  border: 1px solid var(--k-color-border-strong);
  border-radius: var(--k-radius-sm);
  background: var(--k-color-surface);
  color: var(--k-color-text);
}

.control-bar,
.metric-highlight,
.feedback-header,
.node-hero,
.context-card,
.explore-card,
.chat-box,
.secondary-section,
.narrative-card,
.report-tab-shell,
.conclusion-lead,
.conclusion-card,
.conclusion-evidence,
.metric-card,
.feedback-card,
.evidence-drawer {
  border-color: var(--k-color-border);
  background: var(--k-color-surface);
  box-shadow: none;
}

.conclusion-card.is-focus {
  border-color: var(--k-color-border-strong);
  background: var(--k-color-brand-050);
}

.conclusion-label,
.conclusion-round strong,
.node-kicker {
  color: var(--k-color-brand-600);
}

.mini-btn {
  border-color: var(--k-color-border-strong);
  background: var(--k-color-surface);
  color: var(--k-color-text-secondary);
}

.mini-btn.primary {
  border-color: var(--k-color-brand-600);
  background: var(--k-color-brand-600);
  color: #fff;
}

.mini-btn.primary:hover {
  border-color: var(--k-color-brand-hover);
  background: var(--k-color-brand-hover);
}

.round-slider {
  accent-color: var(--k-color-brand-600);
}

.metric-bar-track {
  background: var(--k-color-surface-muted);
}

.metric-bar-fill {
  background: var(--k-color-brand-600);
}

.metric-pill,
.source-chip,
.warning-chip,
.data-chip,
.delta-chip,
.loop-chip,
.loop-chip.loop-reinforcing,
.loop-chip.loop-balancing,
.provenance-badge,
.provenance-badge.prov-observed,
.provenance-badge.prov-inferred,
.provenance-badge.prov-assumed,
.provenance-badge.prov-neutral,
.source-chip.prov-observed,
.source-chip.prov-inferred,
.source-chip.prov-assumed,
.source-chip.prov-neutral {
  border: 1px solid var(--k-color-border-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--k-color-text-secondary);
}

.loop-chip-type {
  padding: 0;
  background: transparent;
}

.loading-spinner {
  border-color: var(--k-color-border);
  border-top-color: var(--k-color-brand-600);
}

.turning-timeline {
  border-left-color: var(--k-color-border-strong);
}

.turning-marker {
  background: var(--k-color-brand-600);
  box-shadow: 0 0 0 3px var(--k-color-brand-100);
}

.status-indicator.processing {
  background: var(--k-color-brand-100);
  color: var(--k-color-brand-700);
}

.chat-message.user {
  border: 1px solid var(--k-color-border);
  background: var(--k-color-brand-050);
}

.chat-message.assistant {
  border: 1px solid var(--k-color-border);
  background: var(--k-color-surface-subtle);
}

/*
 * Step 4 is a reading workspace, not a stack of cards. Section wrappers keep
 * their semantic/layout role, but the page surface and dividers carry the
 * hierarchy. Only repeated, comparable data items remain card-like.
 */
.analysis-hero,
.conclusion-lead,
.conclusion-evidence,
.control-bar,
.metric-highlight,
.feedback-header,
.node-hero,
.context-card,
.explore-card,
.chat-box,
.secondary-section,
.narrative-card,
.report-tab-shell,
.evidence-drawer,
.analysis-state {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.analysis-hero {
  padding: 10px 4px 14px;
  border-bottom: 1px solid var(--k-color-border-strong);
}

.tab-content {
  gap: 0;
}

.conclusion-lead {
  padding: 20px 4px 24px;
  border-bottom: 1px solid var(--k-color-border);
}

.conclusion-grid {
  grid-template-columns: minmax(150px, 0.8fr) minmax(0, 1.1fr) minmax(0, 1.4fr);
  gap: 0;
  border-bottom: 1px solid var(--k-color-border);
}

.conclusion-card,
.conclusion-card.is-focus {
  padding: 18px;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.conclusion-card + .conclusion-card {
  border-left: 1px solid var(--k-color-border);
}

.conclusion-evidence {
  padding: 22px 4px;
  border-bottom: 1px solid var(--k-color-border);
}

.conclusion-stat-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
}

.conclusion-stat-grid > div {
  padding: 12px 16px;
  border-radius: 0;
  background: transparent;
}

.conclusion-stat-grid > div + div {
  border-left: 1px solid var(--k-color-border);
}

.control-bar,
.metric-highlight,
.feedback-header,
.node-hero,
.context-card,
.explore-card,
.chat-box,
.secondary-section,
.evidence-drawer {
  padding: 18px 4px;
  border-bottom: 1px solid var(--k-color-border);
}

.feedback-chain-template {
  padding: 12px 0;
  border-radius: 0;
  background: transparent;
}

.narrative-list {
  gap: 0;
}

.narrative-card {
  padding: 20px 4px;
  border-bottom: 1px solid var(--k-color-border);
}

.narrative-columns {
  gap: 0;
}

.narrative-block {
  padding: 10px 14px;
  border-radius: 0;
  background: transparent;
}

.narrative-block + .narrative-block {
  border-left: 1px solid var(--k-color-border);
}

@container analysis (max-width: 34rem) {
  .conclusion-grid {
    grid-template-columns: 1fr;
  }

  .conclusion-card + .conclusion-card {
    border-top: 1px solid var(--k-color-border);
    border-left: 0;
  }

  .conclusion-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .conclusion-stat-grid > div:nth-child(3) {
    border-left: 0;
  }

  .conclusion-stat-grid > div:nth-child(n + 3) {
    border-top: 1px solid var(--k-color-border);
  }

  .narrative-block + .narrative-block {
    border-top: 1px solid var(--k-color-border);
    border-left: 0;
  }
}

/*
 * Step 4 typography contract. The analysis workspace previously mixed
 * browser-default 16px copy with 11–34px local declarations. These semantic
 * roles keep every tab on the same scale while preserving data hierarchy.
 */
.analysis-panel {
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.hero-title,
.conclusion-lead h2,
.mechanism-overview-copy h2,
.node-hero h2,
.report-tab-shell h2 {
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
  letter-spacing: 0;
}

.conclusion-lead h2 {
  max-width: 62ch;
  font-size: var(--k-text-display);
}

.section-header h3,
.narrative-head h3,
.mechanism-section-head h3,
.metric-highlight-title,
.explore-card h3,
.chat-box h3 {
  font-size: var(--k-text-section);
  line-height: var(--k-leading-ui);
}

.analysis-primary-tabs :deep(.k-workflow-tabs__tab),
.evolution-view-tabs :deep(.k-workflow-tabs__tab),
.mini-btn,
.conclusion-next-actions button {
  font-size: var(--k-text-ui);
  line-height: var(--k-leading-ui);
}

.hero-kicker,
.metric-label,
.conclusion-label,
.conclusion-round span,
.conclusion-card > span,
.conclusion-stat-grid span,
.section-header span,
.block-label,
.narrative-head p,
.context-item > span,
.subgraph-item > span,
.evidence-item span,
.explore-item-head span,
.source-chip,
.data-chip,
.warning-chip,
.delta-chip,
.metric-pill {
  font-size: var(--k-text-meta);
  line-height: var(--k-leading-ui);
}

.hero-summary,
.conclusion-lead p,
.conclusion-card p,
.conclusion-evidence .section-header p,
.mechanism-overview-copy p,
.mechanism-state-row p,
.mechanism-relation-copy p,
.mechanism-note-row p,
.narrative-block p,
.explore-item p,
.grounding-reason,
.analysis-state p {
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.conclusion-card strong,
.context-item strong,
.subgraph-item strong,
.explore-item-head strong,
.evidence-item strong,
.mechanism-state-row strong,
.mechanism-relation-copy strong,
.mechanism-note-row strong {
  font-size: var(--k-text-ui);
  line-height: var(--k-leading-ui);
}

.hero-metric strong,
.conclusion-round strong,
.conclusion-stat-grid strong,
.mechanism-inline-stats dd,
.role-node-count {
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
}
</style>
