<template>
  <div class="envfish-step envfish-step3">
    <div class="runtime-sticky">
      <section class="control-panel runtime-console runtime-transport" aria-label="推演播放控制">
        <span class="runtime-progress-label">{{ isReplayPlayback ? '回放进度' : '推演进度' }}</span>
        <input
          :value="playheadMs"
          type="range"
          :min="0"
          :max="playbackDurationMs"
          :disabled="playbackFrames.length <= 1"
          step="10"
          class="range compact-range"
          :style="{ '--range-progress': `${progressPercent}%` }"
          aria-label="选择推演进度"
          :aria-valuetext="`${selectedRoundLabel}，完成 ${progressPercent}%`"
          @input="handlePlaybackScrub"
        />
        <strong class="runtime-progress-value mono">{{ progressPercent }}%</strong>
        <button
          class="play-control runtime-play-toggle"
          type="button"
          :disabled="playbackFrames.length <= 1"
          :aria-pressed="isPlayingAnimation"
          @click="toggleAnimationPlayback"
        >
          <span aria-hidden="true">{{ isPlayingAnimation ? 'Ⅱ' : '▶' }}</span>
          {{ isPlayingAnimation ? '暂停' : '播放' }}
        </button>
      </section>

      <nav v-if="storyChapters.length" class="story-chapter-nav" aria-label="演化章节">
        <button
          v-for="chapter in storyChapters"
          :key="chapter.id"
          type="button"
          :class="{ 'is-active': activeStoryChapter?.id === chapter.id }"
          :aria-current="activeStoryChapter?.id === chapter.id ? 'step' : undefined"
          @click="seekToStoryChapter(chapter)"
        >
          <span>R{{ chapter.round_start }}–R{{ chapter.round_end }}</span>
          <strong>{{ safeRuntimeCopy(chapter.name, '演化章节') }}</strong>
        </button>
      </nav>

      <KWorkflowTabs
        class="step3-workflow-tabs"
        :items="workspaceTabs"
        :model-value="activeWorkspaceTab"
        variant="compact"
        aria-label="推演观察视图"
        @change="selectWorkspaceTab"
      />
    </div>

    <section ref="workspaceShellRef" class="workspace-shell" @scroll="handleWorkspaceScroll">
      <section
        v-if="['pulse', 'state', 'spread'].includes(activeWorkspaceTab)"
        :id="`workspace-panel-${activeWorkspaceTab}`"
        role="tabpanel"
        :aria-label="activeWorkspaceTabLabel"
        class="workspace-panel"
      >
        <div v-if="activeWorkspaceTab === 'state'" class="summary-grid">
          <article class="summary-card accent">
            <span>重点区域</span>
            <strong>{{ regionRows[0]?.name || '等待区域状态' }}</strong>
            <p>
              {{
                regionRows[0]
                  ? safeRuntimeCopy(regionRows[0].tagline, '区域')
                  : '等待区域矩阵返回。'
              }}
            </p>
          </article>
          <article class="summary-card">
            <span>高热子区域</span>
            <strong>{{ subregionRows[0]?.name || '等待子区域' }}</strong>
            <p>
              {{
                subregionRows[0]
                  ? `${subregionRows[0].parentName || '宏观区域'} · ${subregionRows[0].agentCount} 个代理体`
                  : '当前轮次还没有子区域热度。'
              }}
            </p>
          </article>
          <article class="summary-card">
            <span>{{ isCuratedShowcase ? '关键响应主体' : '领先代理体' }}</span>
            <strong>{{ agentRows[0]?.name || '等待代理体状态' }}</strong>
            <p>
              {{
                agentRows[0]
                  ? isCuratedShowcase
                    ? `${agentRows[0].familyLabel} · 医疗负荷 ${agentRows[0].healthcare_load}`
                    : `${agentRows[0].familyLabel} · 脆弱性 ${agentRows[0].vulnerability_score}`
                  : '系统尚未返回可排序的代理体快照。'
              }}
            </p>
          </article>
          <article class="summary-card">
            <span>主导渠道</span>
            <strong>{{ dominantInteractionLabel }}</strong>
            <p>{{ latestInteraction ? latestInteraction.summary : '当前还没有可展示的代理体互动。' }}</p>
          </article>
        </div>

        <div v-if="activeWorkspaceTab === 'pulse'" class="overview-top-grid">
          <section class="panel pulse-panel">
            <div class="panel-title-row">
              <h3>本轮演化</h3>
              <span class="hint">{{ selectedRoundLabel }}</span>
            </div>

            <div class="pulse-delta-grid">
              <article class="pulse-delta-card">
                <span>已延展关系</span>
                <strong class="mono">{{ playbackPulseStats.newEdges }}</strong>
              </article>
              <article class="pulse-delta-card">
                <span>当前传播波</span>
                <strong class="mono">{{ playbackPulseStats.activeEdges }}</strong>
              </article>
              <article class="pulse-delta-card">
                <span>响应节点</span>
                <strong class="mono">{{ playbackPulseStats.focusNodes }}</strong>
              </article>
            </div>

            <div class="pulse-relation-list">
              <article
                v-for="relation in playbackPulseRelations"
                :key="relation.id"
                class="pulse-relation-card"
                :class="`is-${relation.status}`"
              >
                <span>{{ relation.statusLabel }}</span>
                <strong>{{ relation.sourceName }}<template v-if="relation.targetName"> → {{ relation.targetName }}</template></strong>
                <p>{{ relation.typeLabel }}</p>
              </article>
              <div v-if="playbackPulseRelations.length === 0" class="empty-state compact">
                尚未出现显式连接，图谱保持稳定底图，等待传播链启动。
              </div>
            </div>

            <div class="spotlight-list">
              <article class="spotlight-card">
                <span>最新交互</span>
                <strong>{{ latestInteraction?.sourceName || '暂无交互' }}</strong>
                <p>
                  {{
                    latestInteraction
                      ? `${latestInteraction.actionLabel}${latestInteraction.targetName ? ` → ${latestInteraction.targetName}` : ''}`
                      : '还没有交互记录。'
                  }}
                </p>
              </article>
              <article class="spotlight-card">
                <span>反馈回路</span>
                <strong>{{ feedbackLoops[0] ? safeRuntimeCopy(feedbackLoops[0], '反馈链') : '等待反馈链' }}</strong>
                <p>{{ feedbackLoops.length > 1 ? feedbackLoops.slice(1, 3).map(item => safeRuntimeCopy(item, '反馈链')).join(' · ') : (isCuratedShowcase ? '以发现—检测—分诊—收治与社区—供应—信任反馈为主线。' : '以环境—生态—生计—治理链为主线。') }}</p>
              </article>
              <article class="spotlight-card">
                <span>生效变量</span>
                <strong>{{ activeVariableRows.length }}</strong>
                <p>
                  {{
                    activeVariableRows[0]
                      ? `${activeVariableRows[0].name} · R${activeVariableRows[0].startRound}`
                      : '当前没有处于生效窗口的变量。'
                  }}
                </p>
              </article>
            </div>
          </section>
        </div>

        <div v-if="['state', 'spread'].includes(activeWorkspaceTab)" class="overview-main-grid">
          <section v-if="activeWorkspaceTab === 'state'" class="panel region-panel">
            <div class="panel-title-row">
              <h3>区域状态矩阵</h3>
            </div>

            <div class="matrix-head" :class="{ 'is-curated': isCuratedShowcase }">
              <span>区域</span>
              <template v-if="isCuratedShowcase">
                <span>暴露压力</span>
                <span>发现可见度</span>
                <span>检测时效</span>
                <span>医疗负荷</span>
                <span>流动强度</span>
                <span>物资充足度</span>
                <span>社区支持度</span>
                <span>公共信任度</span>
              </template>
              <template v-else>
                <span>暴露</span>
                <span>恐慌</span>
                <span>信任</span>
                <span>脆弱性</span>
              </template>
            </div>

            <div class="region-list">
              <article v-for="region in (expandedLists.regions ? regionRows : regionRows.slice(0, LIST_PREVIEW.regions))" :key="region.id" class="region-row" :class="{ 'is-curated': isCuratedShowcase }">
                <div class="region-meta">
                  <strong>{{ region.name }}</strong>
                  <span>{{ safeRuntimeCopy(region.tagline, '区域') }}</span>
                </div>
                <template v-if="isCuratedShowcase">
                  <span class="metric mono">{{ region.exposure_pressure }}</span>
                  <span class="metric mono">{{ region.detection_visibility }}</span>
                  <span class="metric mono">{{ region.testing_turnaround }}</span>
                  <span class="metric mono">{{ region.healthcare_load }}</span>
                  <span class="metric mono">{{ region.mobility_intensity }}</span>
                  <span class="metric mono">{{ region.supply_sufficiency }}</span>
                  <span class="metric mono">{{ region.community_support }}</span>
                  <span class="metric mono">{{ region.public_trust }}</span>
                </template>
                <template v-else>
                  <span class="metric mono">{{ region.exposure_score }}</span>
                  <span class="metric mono">{{ region.panic_level }}</span>
                  <span class="metric mono">{{ region.public_trust }}</span>
                  <span class="metric mono">{{ region.vulnerability_score }}</span>
                </template>
              </article>
              <div v-if="regionRows.length === 0" class="empty-state">
                等待后端返回区域矩阵或轮次快照。
              </div>
              <button
                v-if="regionRows.length > LIST_PREVIEW.regions"
                type="button"
                class="list-expand-btn"
                @click="toggleList('regions')"
              >
                {{ expandedLists.regions ? '收起' : `展开全部 ${regionRows.length} 个区域 ↓` }}
              </button>
            </div>
          </section>

          <div v-if="activeWorkspaceTab === 'state'" class="state-secondary-grid">
            <section class="mini-panel subregion-panel">
              <div class="mini-panel-head">
                <h4>子区域热度</h4>
                <span class="hint mono">{{ subregionRows.length }} 个</span>
              </div>
              <div v-if="subregionRows.length > 0" class="subregion-list">
                <article v-for="subregion in subregionRows.slice(0, LIST_PREVIEW.subregions)" :key="subregion.id" class="subregion-card">
                  <div class="subregion-card-head">
                    <div>
                      <strong>{{ subregion.name }}</strong>
                      <span>{{ subregion.parentName || '宏观区域' }} · {{ subregion.agentCount }} 个代理体</span>
                    </div>
                    <span class="subregion-score mono">{{ subregion.selectedScore }}</span>
                  </div>
                  <div class="subregion-bar">
                    <div class="subregion-bar-fill" :style="{ width: `${subregion.selectedScore}%` }"></div>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">当前轮次还没有子区域状态。</div>
            </section>

            <section class="mini-panel decision-panel">
              <div class="mini-panel-head">
                <h4>当前轮决策</h4>
                <span class="hint mono">{{ agentInteractionScopeLabel }}</span>
              </div>
              <div v-if="agentInteractions.length > 0" class="interaction-timeline">
                <article v-for="item in agentInteractions.slice(0, LIST_PREVIEW.interactions)" :key="item.id" class="interaction-card">
                  <div class="interaction-head">
                    <span class="interaction-round mono">R{{ item.round }}</span>
                    <span class="interaction-channel">{{ item.channel }}</span>
                  </div>
                  <strong>{{ item.sourceName }} · {{ item.actionLabel }}</strong>
                  <p>{{ item.summary }}<span v-if="item.targetName"> → {{ item.targetName }}</span></p>
                  <div v-if="item.rationale" class="interaction-meta"><span>{{ item.rationale }}</span></div>
                </article>
              </div>
              <div v-else class="empty-state">当前轮次还没有记录代理体决策。</div>
            </section>
          </div>

          <section v-if="activeWorkspaceTab === 'spread'" class="panel timeline-panel">
            <div class="panel-title-row">
              <h3>传播机制与反馈</h3>
              <span class="hint">{{ spreadEvents.length }} 个事件</span>
            </div>

            <div class="event-list">
              <article
                v-for="event in spreadEvents"
                :key="event.id || `${event.round}-${event.source}-${event.target}`"
                class="event-card"
              >
                <div class="event-head">
                  <strong>{{ event.title || event.label || event.event_type || '扩散事件' }}</strong>
                  <span class="event-round mono">R{{ event.round || event.round_num || currentRoundNumber }}</span>
                </div>
                <p>{{ event.summary || event.description || event.rationale || '扩散/反馈事件正在被记录。' }}</p>
                <div class="event-pills">
                  <span v-if="event.source || event.source_region" class="pill">来源 {{ event.source || event.source_region }}</span>
                  <span v-if="event.target || event.target_region" class="pill">目标 {{ event.target || event.target_region }}</span>
                  <span v-if="event.intensity !== undefined" class="pill">强度 {{ normalizeScore(event.intensity) }}</span>
                  <span v-if="event.confidence !== undefined" class="pill">置信度 {{ Number(event.confidence).toFixed(2) }}</span>
                </div>
              </article>
              <div v-if="spreadEvents.length === 0" class="empty-state">
                当前轮次未返回显式事件，系统仍会刷新区域状态矩阵。
              </div>
            </div>

            <div class="loop-box">
              <div class="panel-title-row">
                <h3>反馈链路</h3>
                <span class="hint">人地反馈回路</span>
              </div>
              <div class="loop-list">
                <span v-for="loop in feedbackLoops" :key="loop" class="loop-pill">{{ safeRuntimeCopy(loop, '反馈链') }}</span>
                <span v-if="feedbackLoops.length === 0" class="empty-loop">{{ isCuratedShowcase ? '发现 → 检测 → 分诊 → 收治 → 社区支持 → 信任反馈' : '环境 → 生态 → 生计 → 恐慌/媒体 → 政策' }}</span>
              </div>
            </div>
          </section>
        </div>
      </section>

      <section
        v-if="activeWorkspaceTab === 'agents'"
        id="workspace-panel-agents"
        role="tabpanel"
        :aria-label="activeWorkspaceTabLabel"
        class="workspace-panel"
      >
        <section class="multi-agent-panel stage-panel">
          <div class="panel-title-row">
            <h3>主体响应</h3>
            <span class="hint">
              {{ subregionRows.length }} 个子区域 · {{ agentRows.length }} 个代理体 · {{ agentInteractions.length }} 次交互
            </span>
          </div>

          <div class="multi-agent-grid">
            <div class="mini-panel subregion-panel">
              <div class="mini-panel-head">
                <h4>子区域热度</h4>
                <span class="hint mono">{{ subregionRows.length }} 个</span>
              </div>
              <div v-if="subregionRows.length > 0" class="subregion-list">
                <article v-for="subregion in (expandedLists.subregions ? subregionRows : subregionRows.slice(0, LIST_PREVIEW.subregions))" :key="subregion.id" class="subregion-card">
                  <div class="subregion-card-head">
                    <div>
                      <strong>{{ subregion.name }}</strong>
                      <span>{{ safeRuntimeCopy(subregion.tagline || subregion.landUseLabel, '子区域') }}</span>
                    </div>
                    <span class="subregion-score mono">{{ subregion.selectedScore }}</span>
                  </div>
                  <div class="subregion-bar">
                    <div class="subregion-bar-fill" :style="{ width: `${subregion.selectedScore}%` }"></div>
                  </div>
                  <div class="subregion-meta">
                    <span>{{ subregion.parentName || subregion.parent_region_id || '宏观区域' }}</span>
                    <span>{{ subregion.agentCount }} 个代理体</span>
                    <span>{{ formatDistanceLabelZh(subregion.distanceLabel || subregion.distance_band) || '带状区域' }}</span>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">
                当前轮次还没有细分子区域数据。
              </div>
              <button
                v-if="subregionRows.length > LIST_PREVIEW.subregions"
                type="button"
                class="list-expand-btn"
                @click="toggleList('subregions')"
              >
                {{ expandedLists.subregions ? '收起' : `展开全部 ${subregionRows.length} 个 ↓` }}
              </button>
            </div>

            <div class="mini-panel agent-panel">
              <div class="mini-panel-head">
                <h4>代理体排行</h4>
                <span class="hint mono">{{ agentRows.length }}</span>
              </div>
              <div v-if="agentRows.length > 0" class="agent-leaderboard">
                <article v-for="agent in (expandedLists.agents ? agentRows : agentRows.slice(0, LIST_PREVIEW.agents))" :key="agent.id" class="agent-rank-card">
                  <div class="agent-rank-head">
                    <div class="agent-rank-name">
                      <strong>
                        <span
                          v-if="provenanceMeta(agent.provenance)"
                          class="provenance-dot"
                          :class="`is-${provenanceMeta(agent.provenance).cls}`"
                          :title="`来源：${provenanceMeta(agent.provenance).label}${agent.groundingReason ? ' · ' + agent.groundingReason : ''}`"
                        ></span>
                        {{ agent.name }}
                      </strong>
                      <span>{{ agent.familyLabel }} · {{ agent.subtypeLabel }}</span>
                    </div>
                    <span class="agent-rank-score mono">{{ agent.vulnerability_score }}</span>
                  </div>
                  <div class="agent-rank-strip">
                    <div class="agent-rank-strip-fill" :style="{ width: `${agent.selectedScore}%` }"></div>
                  </div>
                  <div class="agent-rank-meta">
                    <span>{{ agent.regionLabel || '—' }}</span>
                    <span>{{ agent.subregionLabel || '—' }}</span>
                    <span>{{ agent.lifecycleStatusLabel }}</span>
                    <span>{{ agent.representationLabel }}</span>
                  </div>
                  <div v-if="agent.latestAction" class="agent-action-line">
                    <strong>{{ agent.latestAction.actionLabel }}</strong>
                    <span>R{{ agent.latestAction.round }} · {{ agent.latestAction.statusLabel }}</span>
                  </div>
                  <div class="agent-rank-tags">
                    <span v-for="tag in agent.capabilityLabels.slice(0, 3)" :key="`capability-${tag}`" class="pill">{{ tag }}</span>
                    <span v-if="agent.capabilityLabels.length === 0" class="pill">能力待补证</span>
                  </div>
                  <p>{{ agent.summary }}<template v-if="agent.resourceSummary"> · {{ agent.resourceSummary }}</template></p>
                </article>
              </div>
              <div v-else class="empty-state">
                当前没有可展示的代理体排行。
              </div>
              <button
                v-if="agentRows.length > LIST_PREVIEW.agents"
                type="button"
                class="list-expand-btn"
                @click="toggleList('agents')"
              >
                {{ expandedLists.agents ? '收起' : `展开全部 ${agentRows.length} 个 ↓` }}
              </button>
            </div>

            <div class="mini-panel interaction-panel">
              <div class="mini-panel-head">
                <h4>代理体交互</h4>
                <span class="hint mono">{{ agentInteractionScopeLabel }}</span>
              </div>
              <div v-if="agentInteractions.length > 0" class="interaction-timeline">
                <article v-for="item in (expandedLists.interactions ? agentInteractions : agentInteractions.slice(0, LIST_PREVIEW.interactions))" :key="item.id" class="interaction-card">
                  <div class="interaction-head">
                    <span class="interaction-round mono">R{{ item.round }}</span>
                    <span class="interaction-channel">{{ item.channel }}</span>
                  </div>
                  <strong>{{ item.sourceName }}</strong>
                  <p>
                    {{ item.summary }}
                    <span v-if="item.targetName"> → {{ item.targetName }}</span>
                  </p>
                  <div class="interaction-meta">
                    <span v-if="item.sourceRegion">{{ item.sourceRegion }}</span>
                    <span v-if="item.targetRegion">{{ item.targetRegion }}</span>
                    <span v-if="item.actionType">{{ item.actionType }}</span>
                    <span v-if="item.targetDeltaLabel">{{ item.targetDeltaLabel }}</span>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">
                当前还没有代理体交互事件。
              </div>
              <button
                v-if="agentInteractions.length > LIST_PREVIEW.interactions"
                type="button"
                class="list-expand-btn"
                @click="toggleList('interactions')"
              >
                {{ expandedLists.interactions ? '收起' : `展开全部 ${agentInteractions.length} 条 ↓` }}
              </button>
            </div>
          </div>

          <section class="runtime-ledger-section policy-ledger-section">
            <div class="panel-title-row">
              <h3>政策执行台账</h3>
              <span class="hint">{{ policyExecutionSummary }}</span>
            </div>
            <div v-if="policyExecutionRows.length > 0" class="runtime-ledger-list">
              <article v-for="item in policyExecutionRows.slice(0, 8)" :key="item.id" class="runtime-ledger-row">
                <div>
                  <span class="runtime-ledger-round mono">R{{ item.round }}</span>
                  <strong>{{ item.label }}</strong>
                  <p>{{ item.summary }}</p>
                </div>
                <div class="runtime-ledger-meta">
                  <span :class="`is-${item.status}`">{{ item.statusLabel }}</span>
                  <span>{{ item.executorLabel }}</span>
                  <span>{{ item.targetLabel }}</span>
                </div>
              </article>
            </div>
            <div v-else class="empty-state">截至当前所选轮次，尚无到期的政策执行记录。</div>
          </section>

          <section class="relationship-runtime-panel stage-panel relationship-in-agent-panel">
            <div class="panel-title-row">
              <div>
                <h3>关系演化与角色涌现</h3>
                <p>关系变化来自主体行动与运行证据；这里与行动、政策和主体生命周期一起解释。</p>
              </div>
              <span class="hint">{{ relationshipStateRows.length }} 条关系 · {{ agentEmergenceRows.length }} 个生命周期事件</span>
            </div>

            <div class="relationship-summary-grid">
              <div><span>活跃关系</span><strong>{{ relationshipDynamics.activeCount }}</strong></div>
              <div><span>平均信任</span><strong>{{ relationshipDynamics.trustLabel }}</strong></div>
              <div><span>平均协同</span><strong>{{ relationshipDynamics.coordinationLabel }}</strong></div>
              <div><span>平均张力</span><strong>{{ relationshipDynamics.tensionLabel }}</strong></div>
            </div>

            <div class="relationship-runtime-grid">
              <section class="runtime-ledger-section">
                <div class="mini-panel-head">
                  <h4>关系状态</h4>
                  <span class="hint">随轮次变化</span>
                </div>
                <div v-if="relationshipStateRows.length > 0" class="relationship-state-list">
                  <article v-for="item in relationshipStateRows.slice(0, 10)" :key="item.id" class="relationship-state-row">
                    <div class="relationship-state-head">
                      <strong>{{ item.sourceName }} → {{ item.targetName }}</strong>
                      <span>{{ item.typeLabel }} · {{ item.statusLabel }}</span>
                    </div>
                    <div class="relationship-state-metrics">
                      <span>信任 {{ item.trustLabel }}</span>
                      <span>依赖 {{ item.dependencyLabel }}</span>
                      <span>协同 {{ item.coordinationLabel }}</span>
                      <span>张力 {{ item.tensionLabel }}</span>
                    </div>
                  </article>
                </div>
                <div v-else class="empty-state">截至当前所选轮次，尚未形成可核验的动态关系状态。</div>
              </section>

              <section class="runtime-ledger-section">
                <div class="mini-panel-head">
                  <h4>关系与主体变化</h4>
                  <span class="hint">只影响当前轮及未来</span>
                </div>
                <div v-if="relationshipEventRows.length > 0 || agentEmergenceRows.length > 0" class="runtime-event-list">
                  <article v-for="item in combinedRuntimeEvents.slice(0, 12)" :key="item.id" class="runtime-event-row">
                    <span class="runtime-ledger-round mono">R{{ item.round }}</span>
                    <div>
                      <strong>{{ item.typeLabel }}</strong>
                      <p>{{ item.summary }}</p>
                      <small v-if="item.effectiveRound > item.round">R{{ item.effectiveRound }} 起生效</small>
                    </div>
                  </article>
                </div>
                <div v-else class="empty-state">截至当前所选轮次，尚无关系或主体生命周期变化。</div>
              </section>
            </div>
          </section>
        </section>
      </section>

      <section
        v-if="activeWorkspaceTab === 'risk'"
        id="workspace-panel-risk"
        role="tabpanel"
        :aria-label="activeWorkspaceTabLabel"
        class="workspace-panel"
      >
        <section v-if="riskObjects.length > 0" class="risk-panel-shell">
          <div class="panel-title-row risk-panel-heading">
            <h3>风险对象</h3>
            <span class="hint">{{ riskObjects.length }} 个对象 · {{ activeRiskObjectCount }} 个活动</span>
          </div>

          <div class="risk-selector-shell" :class="{ 'has-overflow-controls': riskSelectorOverflow }">
            <button
              v-if="riskSelectorOverflow"
              type="button"
              class="risk-selector-nav"
              aria-label="向左浏览风险对象"
              :disabled="!canScrollRiskSelectorPrev"
              @click="scrollRiskSelector(-1)"
            >‹</button>
            <div
              ref="riskSelectorRef"
              class="risk-selector-track"
              role="tablist"
              aria-label="选择风险对象"
              @scroll.passive="syncRiskSelectorScrollState"
            >
              <button
                v-for="(item, index) in riskObjects"
                :key="item.risk_object_id"
                type="button"
                role="tab"
                class="risk-selector-option"
                :class="{ active: item.risk_object_id === selectedRiskObjectId }"
                :aria-selected="item.risk_object_id === selectedRiskObjectId"
                @click="selectRiskObject(item.risk_object_id)"
              >
                <span class="risk-selector-index mono">{{ String(index + 1).padStart(2, '0') }}</span>
                <span class="risk-selector-copy">
                  <strong>{{ item.title }}</strong>
                  <small>{{ riskFamilyLabel(item) }} · {{ runtimeStatusMeta(item.lifecycle_status || item.runtime_status || 'watch').label }}</small>
                </span>
                <span v-if="item.risk_object_id === primaryRiskObjectId" class="risk-primary-tag">主要</span>
              </button>
            </div>
            <button
              v-if="riskSelectorOverflow"
              type="button"
              class="risk-selector-nav"
              aria-label="向右浏览风险对象"
              :disabled="!canScrollRiskSelectorNext"
              @click="scrollRiskSelector(1)"
            >›</button>
          </div>

          <div v-if="selectedRiskObject" class="risk-detail">
              <div class="risk-detail-top">
                <div>
                  <div class="eyebrow risk-eyebrow">
                    {{ selectedRiskObject.mode === 'incident' ? '事件风险对象' : '观察风险对象' }} · {{ riskFamilyLabel(selectedRiskObject) }}
                  </div>
                  <h3>{{ selectedRiskObject.title }}</h3>
                  <p>{{ selectedRiskObject.summary || selectedRiskObject.why_now || '等待风险对象摘要。' }}</p>
                </div>

                <div class="risk-metrics">
                  <div
                    v-if="selectedRiskObject.has_runtime_signal && normalizeTension(selectedRiskObject.runtime_tension) !== null"
                    class="mini-pill runtime-pill"
                  >
                    <span>运行张力</span>
                    <strong>{{ normalizeTension(selectedRiskObject.runtime_tension) }}</strong>
                  </div>
                  <div class="mini-pill">
                    <span>影响潜力</span>
                    <strong>{{ normalizeScore(selectedRiskObject.impact_score ?? selectedRiskObject.severity_score) }}</strong>
                  </div>
                  <div class="mini-pill">
                    <span>可行动性</span>
                    <strong>{{ normalizeScore(selectedRiskObject.actionability_score) }}</strong>
                  </div>
                  <div class="mini-pill">
                    <span>证据充分度</span>
                    <strong>{{ riskEvidenceScore(selectedRiskObject) }}</strong>
                  </div>
                </div>
              </div>

              <div class="risk-detail-tabs" role="tablist" aria-label="风险对象详情">
                <button type="button" role="tab" :aria-selected="activeRiskDetailTab === 'chain'" :class="{ active: activeRiskDetailTab === 'chain' }" @click="activeRiskDetailTab = 'chain'">风险链与张力</button>
                <button type="button" role="tab" :aria-selected="activeRiskDetailTab === 'scope'" :class="{ active: activeRiskDetailTab === 'scope' }" @click="activeRiskDetailTab = 'scope'">受影响区域与主体</button>
                <button type="button" role="tab" :aria-selected="activeRiskDetailTab === 'branches'" :class="{ active: activeRiskDetailTab === 'branches' }" @click="activeRiskDetailTab = 'branches'">监测与生命周期</button>
              </div>

              <div v-if="activeRiskDetailTab === 'chain'" class="risk-detail-section">
                <div
                  v-if="selectedRiskObject.has_runtime_signal || (selectedRiskObject.tension_trace || []).length || selectedRiskObject.uncertainty_band"
                  class="risk-runtime-box"
                >
                <div class="risk-runtime-head">
                  <span>运行态张力</span>
                  <span class="runtime-hint">{{ selectedRiskObject.has_runtime_signal ? '随推演演化，替代静态严重性判读' : '尚无运行信号 · 暂用静态严重性' }}</span>
                </div>
                <div class="risk-runtime-row">
                  <span
                    v-if="runtimeStatusMeta(selectedRiskObject.runtime_status)"
                    class="runtime-status-tag"
                    :class="`is-${runtimeStatusMeta(selectedRiskObject.runtime_status).cls}`"
                  >
                    {{ runtimeStatusMeta(selectedRiskObject.runtime_status).label }}
                  </span>
                  <span v-if="selectedRiskObject.turning_point" class="runtime-turning-tag">出现转折点</span>
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
                      r="2.4"
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

                <KMechanismChain
                  :trigger="selectedRiskStatement.trigger_name || selectedRiskObject.root_pressures?.[0] || '场景触发因素'"
                  :steps="selectedRiskMechanismSteps.map(step => safeRuntimeCopy(step, '机制步骤'))"
                  :empty-step-label="`${selectedRiskObject.mechanism_edge_ids?.length || 0} 条已校验机制边`"
                  :receptor="selectedRiskStatement.receptor_name || '主要受影响对象'"
                  :consequence="selectedRiskStatement.consequence || selectedRiskObject.summary"
                  aria-label="风险对象机制链"
                />
              </div>

              <div v-if="activeRiskDetailTab === 'scope'" class="risk-related-grid">
                <section v-if="riskAffectedSubjectNodes.length > 0" class="risk-subpanel">
                  <div class="subpanel-head">
                    <h4>受影响主体与受体</h4>
                    <span>{{ riskAffectedSubjectNodes.length }}</span>
                  </div>
                  <div class="node-chip-list">
                    <article v-for="node in riskAffectedSubjectNodes" :key="node.id" class="node-chip">
                      <div class="node-chip-head">
                        <strong>{{ node.name }}</strong>
                        <span class="node-chip-state" :class="{ matched: node.matched }">
                          {{ node.stateLabel }}
                        </span>
                      </div>
                      <div class="node-chip-labels">
                        <span v-for="label in node.labels" :key="label" class="node-label">{{ safeRuntimeCopy(label, '关联主体') }}</span>
                        <span v-if="node.scopeBasisLabel" class="node-label">{{ node.scopeBasisLabel }}</span>
                      </div>
                      <p>{{ node.summary || '该主体或受体被当前机制路径直接引用。' }}</p>
                    </article>
                  </div>
                </section>

                <section v-if="riskObjectRegionNodes.length > 0" class="risk-subpanel">
                  <div class="subpanel-head">
                    <h4>作用区域</h4>
                    <span>{{ riskObjectRegionNodes.length }}</span>
                  </div>
                  <div class="node-chip-list compact">
                    <article v-for="region in riskObjectRegionNodes" :key="region.id" class="node-chip compact">
                      <div class="node-chip-head">
                        <strong>{{ region.name }}</strong>
                        <span class="node-chip-state" :class="{ matched: region.matched }">
                          {{ region.matched ? '地图节点' : '已校验区域' }}
                        </span>
                      </div>
                      <div class="node-chip-labels">
                        <span v-for="label in region.labels" :key="label" class="node-label">{{ safeRuntimeCopy(label, '作用区域') }}</span>
                        <span v-if="region.scopeBasisLabel" class="node-label">{{ region.scopeBasisLabel }}</span>
                      </div>
                      <p>{{ region.summary || '当前区域来自风险对象作用域。' }}</p>
                    </article>
                  </div>
                </section>

                <section v-if="selectedRiskEvidence.length > 0" class="risk-subpanel">
                  <div class="subpanel-head">
                    <h4>证据与认识状态</h4>
                    <span>{{ selectedRiskEvidence.length }}</span>
                  </div>
                  <div class="cluster-list">
                    <article v-for="item in selectedRiskEvidence" :key="item.evidence_id || item.title" class="cluster-card">
                      <div class="cluster-head">
                        <strong>{{ item.title || '机制依据' }}</strong>
                        <span class="pill">{{ item.epistemic_status_label || safeRuntimeCopy(translateDisplayToken(item.epistemic_status, ''), '机制推断') }}</span>
                      </div>
                      <p>{{ item.summary || formatInlineList(item.extracted_facts, '暂无证据摘要') }}</p>
                    </article>
                  </div>
                </section>

                <div
                  v-if="riskAffectedSubjectNodes.length === 0 && riskObjectRegionNodes.length === 0 && selectedRiskEvidence.length === 0"
                  class="empty-state risk-detail-empty"
                >
                  当前风险对象尚无可展示的影响范围或证据。
                </div>
              </div>

              <div v-if="activeRiskDetailTab === 'branches'" class="risk-related-grid secondary">
                <section v-if="selectedRiskMetrics.length > 0" class="risk-subpanel">
                  <div class="subpanel-head">
                    <h4>专属监测指标</h4>
                    <span>{{ selectedRiskMetrics.length }}</span>
                  </div>
                  <div class="metric-list">
                    <article v-for="metric in selectedRiskMetrics" :key="metric.key || metric.label" class="metric-row">
                      <strong>{{ metric.label }}</strong>
                      <span>升高 {{ metric.thresholds?.elevated ?? 52 }} · 危急 {{ metric.thresholds?.critical ?? 72 }} · 解除 {{ metric.thresholds?.resolved ?? 35 }}</span>
                    </article>
                  </div>
                </section>

                <section v-if="selectedRiskEvents.length > 0 || selectedRiskObject.created_round > 0" class="risk-subpanel">
                  <div class="subpanel-head">
                    <h4>生命周期记录</h4>
                    <span>{{ selectedRiskEvents.length }}</span>
                  </div>
                  <div v-if="selectedRiskEvents.length > 0" class="branch-list">
                    <article v-for="event in selectedRiskEvents" :key="event.event_id" class="branch-card">
                      <div class="branch-head">
                        <strong>第 {{ event.round ?? 0 }} 轮</strong>
                        <span class="pill">{{ safeRuntimeCopy(event.event_type, '状态变化') }}</span>
                      </div>
                      <p>{{ event.summary || '风险状态发生变化。' }}</p>
                    </article>
                  </div>
                  <div v-else class="empty-state">
                    {{ selectedRiskObject.created_round > 0 ? `第 ${selectedRiskObject.created_round} 轮自动涌现，暂无后续状态事件。` : '初始风险对象，暂无状态变化事件。' }}
                  </div>
                </section>

                <section v-if="selectedRiskObject.quality_flags?.length > 0" class="risk-subpanel">
                  <div class="subpanel-head">
                    <h4>质量标记</h4>
                    <span>{{ selectedRiskObject.quality_flags?.length || 0 }}</span>
                  </div>
                  <div class="node-chip-labels">
                    <span v-for="flag in selectedRiskObject.quality_flags.slice(0, 3)" :key="flag" class="node-label">{{ safeRuntimeCopy(translateDisplayToken(flag, ''), '质量复核项') }}</span>
                    <span v-if="selectedRiskObject.quality_flags.length > 3" class="node-label">+{{ selectedRiskObject.quality_flags.length - 3 }}</span>
                  </div>
                </section>

                <div
                  v-if="selectedRiskMetrics.length === 0 && selectedRiskEvents.length === 0 && !(selectedRiskObject.created_round > 0) && !(selectedRiskObject.quality_flags?.length > 0)"
                  class="empty-state risk-detail-empty"
                >
                  当前风险对象尚无监测或生命周期记录。
                </div>
              </div>
          </div>
        </section>

        <div v-else class="empty-state stage-empty">
          场景准备完成，未形成通过证据校验的风险对象
        </div>
      </section>

    </section>

    <WorkflowActionBar class="step3-action-bar" :sticky="false" :elevated="false" :compact="true" aria-label="推演流程操作">
      <div class="action-context">
        <span>{{ runStageLabel }}</span>
        <strong>{{ actionBarSummary }}</strong>
      </div>
      <template #actions>
        <button class="text-btn" type="button" @click="handleGoBack">返回场景设计</button>
        <button class="ghost-btn intervention-trigger" type="button" @click="handleInterventionAction">
          {{ isCuratedShowcase ? '查看介入节点' : '干预推演' }}
          <span v-if="activeVariableRows.length" class="control-count mono">{{ activeVariableRows.length }}</span>
        </button>
        <button v-if="!isReplayPlayback && (canStop || isStopping)" class="ghost-btn" type="button" :disabled="isStopping" @click="handleStop">
          {{ stopButtonLabel }}
        </button>
        <button class="primary-btn" type="button" :disabled="!canGenerateReport" @click="handleNextStep">
          {{ reportButtonLabel }}
        </button>
      </template>
    </WorkflowActionBar>

    <div v-if="isInterventionPanelOpen && !isCuratedShowcase" class="intervention-overlay" role="presentation" @click.self="isInterventionPanelOpen = false">
      <aside class="intervention-drawer" role="dialog" aria-modal="true" aria-labelledby="intervention-title">
        <header class="intervention-drawer-head">
          <div>
            <div class="eyebrow">运行控制</div>
            <h2 id="intervention-title">运行干预</h2>
            <p>新建干预、检查当前生效条件与历史记录。左侧运行图谱保持可见。</p>
          </div>
          <button type="button" class="drawer-close" aria-label="关闭运行干预" @click="isInterventionPanelOpen = false">×</button>
        </header>

        <div class="intervention-drawer-body">
          <section class="injection-panel">
            <div class="panel-title-row">
              <h3>新建干预</h3>
              <span class="hint">污染 / 政策 / 约束</span>
            </div>

            <div class="injection-presets">
              <button class="preset-btn" @click="applyPreset('disaster')">污染激增</button>
              <button class="preset-btn" @click="applyPreset('policy')">强制撤离</button>
              <button class="preset-btn" @click="applyPreset('monitor')">监测增强</button>
            </div>

            <div class="form-stack">
              <div class="field-row">
                <label>
                  类型
                  <select v-model="injection.type">
                    <option value="disaster">污染变量</option>
                    <option value="policy">政策变量</option>
                  </select>
                </label>
                <label>
                  干预模式
                  <select v-model="injection.policy_mode">
                    <option v-for="mode in policyModes" :key="mode" :value="mode">{{ safeRuntimeCopy(translateDisplayToken(mode, ''), '其他模式') }}</option>
                  </select>
                </label>
              </div>

              <label>
                名称
                <input v-model="injection.name" type="text" placeholder="核废水排放 / 强制撤离 / 信息公开" />
              </label>

              <label>
                描述
                <textarea v-model="injection.description" rows="4" placeholder="描述该变量如何作用于生态、治理或社会行为。"></textarea>
              </label>

              <div class="field-row">
                <label>
                  目标区域
                  <input v-model="injection.target_regions_text" type="text" placeholder="滨海区、渔港和下游社区" />
                </label>
                <label>
                  目标节点
                  <input v-model="injection.target_nodes_text" type="text" placeholder="渔民、居民、环保局与海流" />
                </label>
              </div>

              <div class="field-row">
                <label>
                  起始轮次
                  <input v-model.number="injection.start_round" type="number" min="0" />
                </label>
                <label>
                  持续轮次
                  <input v-model.number="injection.duration_rounds" type="number" min="1" />
                </label>
                <label>
                  强度
                  <input v-model.number="injection.intensity" type="range" min="0" max="100" />
                </label>
              </div>
            </div>

            <div class="action-row">
              <button class="secondary-btn" @click="clearInjection">清空</button>
              <button class="primary-btn" :disabled="!canInject" @click="handleInject">
                {{ isInjecting ? '实施中...' : canInject ? '确认实施干预' : '当前阶段不可干预' }}
              </button>
            </div>
            <p v-if="interventionMessage" class="intervention-message" aria-live="polite">{{ interventionMessage }}</p>

            <div class="injection-log">
              <div class="panel-title-row">
                <h3>历史记录</h3>
                <span class="hint">{{ interventionRows.length }}</span>
              </div>
              <div v-if="interventionRows.length > 0" class="history-list">
                <article v-for="item in interventionRows.slice(0, 10)" :key="item.id" class="history-card">
                  <div class="event-head">
                    <strong>
                      <span class="variable-kind-tag" :class="item.kindClass">{{ item.kindLabel }}</span>
                      {{ item.name }}
                    </strong>
                    <span class="pill">{{ item.statusLabel }}</span>
                  </div>
                  <p>{{ item.summary }}</p>
                  <div class="event-pills">
                    <span class="pill">{{ safeRuntimeCopy(translateDisplayToken(item.type, ''), '干预变量') }}</span>
                    <span class="pill">R{{ item.startRound }}</span>
                    <span class="pill">{{ item.duration }} 轮</span>
                    <span class="pill">强度 {{ item.intensity }}</span>
                    <span v-if="item.mode" class="pill">{{ safeRuntimeCopy(translateDisplayToken(item.mode, ''), '其他模式') }}</span>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">
                还没有运行干预记录。
              </div>
            </div>
          </section>

          <section class="active-intervention-panel">
            <div class="injection-log active-intervention-list">
              <div class="panel-title-row">
                <h3>当前生效</h3>
                <span class="hint">{{ activeVariableRows.length }}</span>
              </div>
              <div v-if="activeVariableRows.length > 0" class="history-list">
                <article v-for="item in activeVariableRows.slice(0, 8)" :key="item.id" class="history-card">
                  <strong>{{ item.name }}</strong>
                  <p>{{ item.summary }}</p>
                  <div class="event-pills">
                    <span class="pill">{{ safeRuntimeCopy(translateDisplayToken(item.type, ''), '干预变量') }}</span>
                    <span class="pill">目标 {{ item.targets.join(' · ') || '全域' }}</span>
                  </div>
                </article>
              </div>
              <div v-else class="empty-state">
                当前没有处于生效窗口的干预。
              </div>
            </div>
          </section>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getRunStatus, getRunStatusDetail, getSimulation, getSimulationConfig, injectSimulationVariable, startSimulation, stopSimulation } from '../api/simulation'
import { generateReportAsync } from '../api/report'
import { formatDistanceLabelZh, formatLandUseLabelZh, formatTokenLabelZh, normalizeDisplayLabels, safeDisplayError, safeDisplayText, sanitizeDisplayCopy, translateDisplayToken } from '../utils/displayText'
import {
  advanceContinuousPlayhead,
  buildContinuousPlaybackPlan,
  buildContinuousPlaybackSnapshot,
} from '../utils/simulationPlayback'
import { STEP3_WORKSPACE_TABS } from '../config/workflowArchitecture'
import KMechanismChain from './ui/KMechanismChain.vue'
import KWorkflowTabs from './ui/KWorkflowTabs.vue'
import WorkflowActionBar from './ui/WorkflowActionBar.vue'

const props = defineProps({
  simulationId: String,
  maxRounds: Number,
  minutesPerRound: {
    type: Number,
    default: 30
  },
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  initialScenarioMode: String,
  initialSearchMode: String,
  initialSimulationArchitecture: String,
  initialDiffusionTemplate: String,
  animationData: Object,
  isReplayOnly: Boolean
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status', 'risk-object-focus', 'animation-frame-change'])

const route = useRoute()
const router = useRouter()

const isGeneratingReport = ref(false)
const isStarting = ref(false)
const isStopping = ref(false)
const runStatus = ref({})
const runDetail = ref({})
const simulationSnapshot = ref(null)
const configSnapshot = ref(null)
const currentScenarioMode = ref(props.initialScenarioMode || route.query.scenario_mode || 'baseline_mode')
const currentTemplate = ref(props.initialDiffusionTemplate || route.query.diffusion_template || 'marine')
const injectionHistory = ref([])
const isInjecting = ref(false)
const interventionMessage = ref('')
const injection = ref(createInjection())
const selectedRiskObjectId = ref('')
const riskSelectorRef = ref(null)
const riskSelectorOverflow = ref(false)
const canScrollRiskSelectorPrev = ref(false)
const canScrollRiskSelectorNext = ref(false)
const activeRiskDetailTab = ref('chain')
const activeWorkspaceTab = ref('pulse')
const isInterventionPanelOpen = ref(false)
const workspaceShellRef = ref(null)
const workspaceScrollByTab = ref({})
// 层级：长列表默认只显 top-N，按需展开（区域矩阵/子区域/代理体/交互）
const expandedLists = ref({ regions: false, subregions: false, agents: false, interactions: false })
const toggleList = (key) => { expandedLists.value[key] = !expandedLists.value[key] }
const LIST_PREVIEW = { regions: 5, subregions: 5, agents: 5, interactions: 6 }
const lastRunMessage = ref('')
const isPlayingAnimation = ref(false)
const playbackRate = ref(1)
const hasAutoStartedReplay = ref(false)
const hasUserPausedPlayback = ref(false)
const playheadMs = ref(0)

const policyModes = ['restrict', 'relocate', 'subsidize', 'monitor', 'disclose', 'repair', 'ban', 'reopen']

let statusTimer = null
let detailTimer = null
let frameAnimationRaf = null
let lastPlaybackRafAt = null
let statusRefreshInFlight = false
let detailRefreshInFlight = false

const playbackFrames = computed(() => {
  const frames = props.animationData?.frames
  if (Array.isArray(frames) && frames.length > 0) return frames
  return roundSnapshots.value
})

const playbackPayload = computed(() => {
  if (Array.isArray(props.animationData?.frames) && props.animationData.frames.length > 0) {
    return props.animationData
  }
  return {
    frames: playbackFrames.value,
    timeline: { events: [] },
    meta: {
      total_rounds: Math.max(0, playbackFrames.value.length - 1),
      timeline_contract_version: 'legacy',
    },
  }
})

const playbackPlan = computed(() => buildContinuousPlaybackPlan(playbackPayload.value))
const playbackDurationMs = computed(() => Math.max(1, Number(playbackPlan.value?.duration_ms || 1)))

const selectedAnimationFrame = computed(() => {
  if (playbackFrames.value.length === 0) return null
  return buildContinuousPlaybackSnapshot(
    playbackPayload.value,
    playbackPlan.value,
    playheadMs.value,
    {
      isPlaying: isPlayingAnimation.value,
    },
  )
})

const roundIndex = computed(() => Math.max(0, Number(selectedAnimationFrame.value?.playback_frame_index || 0)))

const isReplayPlayback = computed(() => Boolean(props.isReplayOnly || simulationSnapshot.value?.is_replay_only || props.animationData?.meta?.artifact_mode === 'frozen'))
const isCuratedShowcase = computed(() => (
  String(route.query.demo_mode || '') === 'curated_showcase'
  || String(props.animationData?.meta?.generation_mode || '') === 'curated_target_state'
))
const primaryHeatScoreKey = computed(() => (
  isCuratedShowcase.value ? 'healthcare_load' : 'vulnerability_score'
))
const storyChapters = computed(() => {
  const source = props.animationData?.story_chapters || props.animationData?.timeline?.story_chapters || []
  return Array.isArray(source) ? source : []
})
const activeStoryChapter = computed(() => {
  const round = Number(currentRoundNumber.value || 0)
  return storyChapters.value.find((item) => (
    Number(item?.round_start ?? 0) <= round && round <= Number(item?.round_end ?? 0)
  )) || storyChapters.value[0] || null
})
const policyInterventions = computed(() => {
  const source = props.animationData?.policy_interventions || []
  return Array.isArray(source) ? source : []
})

const existingReportId = computed(() => {
  const candidates = [
    route.query.report_id,
    simulationSnapshot.value?.report_id,
    simulationSnapshot.value?.latest_report_id,
    props.animationData?.meta?.report_id
  ]
  for (const candidate of candidates) {
    const value = Array.isArray(candidate) ? candidate[0] : candidate
    const reportId = String(value || '').trim()
    if (reportId) return reportId
  }
  return ''
})

const progressPercent = computed(() => {
  if (selectedAnimationFrame.value && props.animationData?.frames?.length) {
    const total = Number(props.animationData?.meta?.total_rounds || playbackFrames.value.length - 1 || 0)
    const round = Number(selectedAnimationFrame.value.round ?? 0)
    const roundElapsed = Number(selectedAnimationFrame.value.playback_round_elapsed_ms || 0)
    const roundDuration = Math.max(1, Number(selectedAnimationFrame.value.playback_round_duration_ms || 1))
    const current = round + Math.max(0, Math.min(0.999, roundElapsed / roundDuration))
    if (total > 0 && Number.isFinite(current)) {
      return Math.max(0, Math.min(100, Math.round((current / total) * 100)))
    }
  }
  if (playbackDurationMs.value > 1) {
    return Math.max(0, Math.min(100, Math.round((playheadMs.value / playbackDurationMs.value) * 100)))
  }
  const explicitProgress = Number(runStatus.value.progress_percent ?? runDetail.value.progress_percent)
  if (Number.isFinite(explicitProgress) && explicitProgress > 0) {
    return Math.max(0, Math.min(100, Math.round(explicitProgress)))
  }
  const total = Number(runStatus.value.total_rounds || props.maxRounds || roundSnapshots.value.length || 0)
  if (!total) return 0
  const current = Number(currentRoundNumber.value || 0)
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)))
})

const runStageLabel = computed(() => {
  if (runStatus.value.runner_status === 'completed') return '推演结果'
  if (runStatus.value.runner_status === 'failed') return '最后一轮结果'
  if (runStatus.value.runner_status === 'stopped') return '当前轮次'
  if (runStatus.value.runner_status === 'running') return '运行中'
  if (isPlayingAnimation.value) return '回放中'
  if (isStarting.value) return '启动中'
  return '空闲'
})

const actionBarSummary = computed(() => {
  if (canGenerateReport.value) return `${selectedRoundLabel.value} · 推演结果`
  if (runStatus.value.runner_status === 'failed') return '可查看最后一轮结果与运行记录'
  return `${selectedRoundLabel.value} · ${progressPercent.value}%`
})

const canGenerateReport = computed(() => {
  if (isGeneratingReport.value) return false
  if (!props.simulationId) return false
  if (existingReportId.value) return true
  if (isReplayPlayback.value) return true
  return ['completed', 'stopped'].includes(String(runStatus.value.runner_status || ''))
})

const canStop = computed(() => {
  if (!props.simulationId) return false
  if (isReplayPlayback.value) return isPlayingAnimation.value
  return ['running', 'paused'].includes(String(runStatus.value.runner_status || ''))
})

const stopButtonLabel = computed(() => {
  if (isStopping.value) return '停止中...'
  if (isReplayPlayback.value) return isPlayingAnimation.value ? '暂停回放' : '回放已暂停'
  if (runStatus.value.runner_status === 'completed') return '推演结果'
  if (runStatus.value.runner_status === 'stopped') return '推演已停止'
  return '停止推演'
})

const canInject = computed(() => {
  if (!props.simulationId || isInjecting.value || isReplayPlayback.value) return false
  return ['running', 'paused'].includes(String(runStatus.value.runner_status || ''))
})

const reportButtonLabel = computed(() => {
  if (isGeneratingReport.value) return '报告生成中...'
  if (existingReportId.value) return '查看报告'
  if (runStatus.value.runner_status === 'failed') return '等待可用轮次'
  if (!canGenerateReport.value) return '等待推演完成'
  return '生成报告'
})

const uncertaintyLabel = computed(() => {
  const value = runDetail.value.uncertainty_band || runDetail.value.uncertainty || runStatus.value.uncertainty_band
  if (value === undefined || value === null || value === '') return '暂无'
  if (typeof value === 'number') return value.toFixed(2)
  return String(value)
})

const roundSnapshots = computed(() => {
  const source = runDetail.value.round_snapshots || runDetail.value.snapshots || runDetail.value.round_history || []
  return Array.isArray(source) ? source : []
})

const baselineSnapshot = computed(() => {
  if (!isCuratedShowcase.value) return null
  const normalizeBaselineRows = (rows) => (Array.isArray(rows) ? rows : []).map((item) => ({
    ...item,
    ...(item?.state_vector || {}),
    business_state: item?.business_state || item?.state_vector || {},
  }))
  const regions = normalizeBaselineRows(configSnapshot.value?.region_graph)
  const subregions = normalizeBaselineRows(configSnapshot.value?.subregion_graph)
  const agents = normalizeBaselineRows(
    configSnapshot.value?.agent_configs || configSnapshot.value?.actor_profiles
  )
  return {
    round: 0,
    chapter_id: storyChapters.value[0]?.id || '',
    chapter_name: storyChapters.value[0]?.name || '异常出现',
    headline: '城市系统基线',
    regions,
    subregions,
    agents,
    agent_summary: {
      active_agents: agents.length,
      core_agents: agents.filter((item) => item?.representation_level === 'functional').length,
      background_agents: agents.filter((item) => item?.representation_level === 'aggregate').length,
    },
    interactions: { agent_interactions: [], agent_environment_effects: [] },
    feedback: { feedback_propagation: [] },
  }
})

const selectedRoundSnapshot = computed(() => {
  if (props.animationData?.frames?.length) {
    const frameRound = Number(selectedAnimationFrame.value?.round ?? 0)
    if (frameRound === 0) return baselineSnapshot.value
    return roundSnapshots.value.find(item => Number(extractRoundNumber(item, 0)) === frameRound) || runDetail.value.latest_round_snapshot || null
  }
  if (roundSnapshots.value.length === 0) {
    return runDetail.value.latest_round_snapshot || null
  }
  const safeIndex = Math.min(Math.max(roundIndex.value, 0), roundSnapshots.value.length - 1)
  return roundSnapshots.value[safeIndex] || null
})

const currentRoundNumber = computed(() => {
  if (selectedAnimationFrame.value && props.animationData?.frames?.length) {
    const frameRound = Number(selectedAnimationFrame.value.round || 0)
    return Number.isFinite(frameRound) ? frameRound : 0
  }
  if (selectedRoundSnapshot.value) return extractRoundNumber(selectedRoundSnapshot.value, roundIndex.value)
  return runStatus.value.current_round || runStatus.value.current_round_num || 0
})

function syncRoundIndexToRound(round) {
  const targetRound = Number(round || 0)
  if (!targetRound || playbackFrames.value.length === 0) return
  // Timeline playback owns its own visual cursor. Runtime polling may append
  // committed rounds, but it must never pull a paused or buffered story ahead.
  if (props.animationData?.frames?.length || hasUserPausedPlayback.value) return
  const marker = (playbackPlan.value?.rounds || []).find(item => Number(item?.round) === targetRound)
  if (!marker) return
  playheadMs.value = Math.max(0, Math.min(
    playbackDurationMs.value,
    Number(marker.end_ms || marker.start_ms || 0) - 1,
  ))
}

const selectedRoundLabel = computed(() => {
  if (selectedAnimationFrame.value && props.animationData?.frames?.length) {
    return currentRoundNumber.value > 0 ? `R${currentRoundNumber.value}` : '基线'
  }
  return selectedRoundSnapshot.value ? `R${currentRoundNumber.value}` : '实时'
})

const latestSnapshot = computed(() => {
  if (props.animationData?.frames?.length && currentRoundNumber.value === 0) {
    return baselineSnapshot.value
  }
  return selectedRoundSnapshot.value || runDetail.value.latest_round_snapshot || runDetail.value.latest_snapshot || null
})

const runtimeRoundCeiling = computed(() => {
  const round = Number(currentRoundNumber.value)
  return Number.isFinite(round) ? Math.max(0, round) : Number.MAX_SAFE_INTEGER
})

const agentSummary = computed(() => {
  const source = latestSnapshot.value || runDetail.value || {}
  return (
    source.agent_summary ||
    source.latest_round_snapshot?.agent_summary ||
    source.latest_snapshot?.agent_summary ||
    {}
  )
})

const activeAgentCount = computed(() => {
  const value =
    agentSummary.value.active_agents ??
    agentSummary.value.total_active_agents ??
    agentSummary.value.total_agents

  if (value !== undefined && value !== null) {
    return Number(value) || 0
  }

  return agentRows.value.length
})

const environmentEffectCount = computed(() => {
  const value =
    agentSummary.value.environment_effect_count ??
    agentSummary.value.effect_count

  if (value !== undefined && value !== null) {
    return Number(value) || 0
  }

  const source = latestSnapshot.value || runDetail.value || {}
  const effects =
    source.agent_environment_effects ||
    source.interactions?.agent_environment_effects ||
    source.latest_round_snapshot?.interactions?.agent_environment_effects ||
    []

  return Array.isArray(effects) ? effects.length : 0
})

const regionRows = computed(() => {
  const snapshot = latestSnapshot.value || runDetail.value
  const regions = normalizeRegionRows(snapshot)
  const key = primaryHeatScoreKey.value

  return regions
    .map(region => ({
      ...region,
      selectedScore: normalizeScore(region[key]),
      tagline: region.tagline || region.region_type || region.zone || 'region'
    }))
    .sort((a, b) => b.selectedScore - a.selectedScore)
})

const configuredSubregionAgentCount = computed(() => {
  const counts = new Map()
  const profiles = Array.isArray(configSnapshot.value?.actor_profiles)
    ? configSnapshot.value.actor_profiles
    : (Array.isArray(configSnapshot.value?.agent_configs) ? configSnapshot.value.agent_configs : [])
  profiles.forEach(profile => {
    const key = String(profile?.home_subregion_id || '').trim()
    if (key) counts.set(key, (counts.get(key) || 0) + 1)
  })
  return counts
})

const subregionRows = computed(() => {
  const source = latestSnapshot.value || runDetail.value
  const rows = normalizeSubregionRows(source)
  const key = primaryHeatScoreKey.value

  return rows
    .map(item => ({
      ...item,
      agentCount: configuredSubregionAgentCount.value.get(String(item.id)) ?? item.agentCount,
      selectedScore: normalizeScore(item[key])
    }))
    .sort((a, b) => b.selectedScore - a.selectedScore)
})

// 区域/子区域 ID → 名称查表：代理体卡与交互卡别再裸露 jianghan_market_corridor 这类 slug
const regionNameById = computed(() => {
  const m = new Map()
  ;[...regionRows.value, ...subregionRows.value].forEach(r => {
    if (r?.id) m.set(String(r.id), r.name)
  })
  ;(configSnapshot.value?.spatial_anchor_candidates || []).forEach(anchor => {
    const label = anchor?.display_name_zh || anchor?.region_id || ''
    if (anchor?.entity_id && label) m.set(String(anchor.entity_id), label)
    if (anchor?.anchor_id && label) m.set(String(anchor.anchor_id), label)
  })
  return m
})
function resolveRegionName(raw) {
  if (raw === null || raw === undefined || raw === '') return ''
  const key = String(raw)
  return regionNameById.value.get(key)
    || regionNameById.value.get(key.split('::')[0])
    || safeRuntimeCopy(raw, '未知区域')
}

function formatInteractionRegion(raw) {
  const label = resolveRegionName(raw)
  if (!label || /^(?:未命名|未知|暂无|相关)(?:代理体|对象|区域|节点)?$/.test(label)) return ''
  return label
}

const agentActionRows = computed(() => {
  if (selectedRoundSnapshot.value) {
    return normalizeAgentActionRows(selectedRoundSnapshot.value).sort(sortByRoundDesc)
  }
  const maxRound = runtimeRoundCeiling.value
  return normalizeAgentActionRows(runDetail.value)
    .filter(item => item.round <= maxRound)
    .sort(sortByRoundDesc)
})

const latestAgentActionById = computed(() => {
  const map = new Map()
  agentActionRows.value.forEach(item => {
    const key = String(item.agentId ?? '')
    if (key && !map.has(key)) map.set(key, item)
  })
  return map
})

const configuredAgentProfileById = computed(() => {
  const map = new Map()
  const sources = [
    ...(Array.isArray(configSnapshot.value?.agent_configs) ? configSnapshot.value.agent_configs : []),
    ...(Array.isArray(configSnapshot.value?.actor_profiles) ? configSnapshot.value.actor_profiles : [])
  ]
  sources.forEach((profile, index) => {
    const id = profile?.agent_id ?? profile?.user_id ?? index
    const key = String(id)
    map.set(key, {
      ...(map.get(key) || {}),
      ...(profile || {})
    })
  })
  return map
})

const agentRows = computed(() => {
  const source = latestSnapshot.value || runDetail.value
  return normalizeAgentRows(source, primaryHeatScoreKey.value, configuredAgentProfileById.value)
    .map(a => ({
      ...a,
      regionLabel: resolveRegionName(a.regionLabel),
      subregionLabel: resolveRegionName(a.subregionLabel),
      latestAction: latestAgentActionById.value.get(String(a.id)) || null
    }))
    .sort((a, b) => b.selectedScore - a.selectedScore)
})

const selectedRoundInteractions = computed(() => {
  const source = selectedRoundSnapshot.value || latestSnapshot.value || null
  return normalizeAgentInteractions(source).sort(sortByRoundDesc)
})

const agentInteractions = computed(() => {
  const resolveRegions = (list) => list.map(i => ({
    ...i,
    sourceName: runtimeAgentNameById.value.get(String(i.sourceAgentId)) || i.sourceName,
    targetName: runtimeAgentNameById.value.get(String(i.targetAgentId)) || i.targetName,
    sourceRegion: resolveRegionName(i.sourceRegion),
    targetRegion: resolveRegionName(i.targetRegion)
  }))
  if (selectedRoundInteractions.value.length > 0) {
    return resolveRegions(selectedRoundInteractions.value)
  }

  const maxRound = runtimeRoundCeiling.value
  return resolveRegions(
    normalizeAgentInteractions(runDetail.value)
      .filter(item => (item.round || 0) <= maxRound)
      .sort(sortByRoundDesc)
  )
})

const latestInteraction = computed(() => agentInteractions.value[0] || null)

const runtimeAgentNameById = computed(() => {
  const map = new Map()
  agentRows.value.forEach(item => map.set(String(item.id), item.name))
  return map
})

const relationshipStateRows = computed(() => {
  const source = latestSnapshot.value || runDetail.value
  return normalizeRelationshipStateRows(source, runtimeAgentNameById.value)
    .sort((a, b) => b.lastUpdatedRound - a.lastUpdatedRound || b.tension - a.tension)
})

const relationshipEventRows = computed(() => {
  const maxRound = runtimeRoundCeiling.value
  return mergeRuntimeRows(
    normalizeRelationshipEventRows(selectedRoundSnapshot.value || {}, runtimeAgentNameById.value),
    normalizeRelationshipEventRows(runDetail.value, runtimeAgentNameById.value)
  ).filter(item => item.round <= maxRound).sort(sortByRoundDesc)
})

const agentEmergenceRows = computed(() => {
  const maxRound = runtimeRoundCeiling.value
  return mergeRuntimeRows(
    normalizeAgentEmergenceRows(selectedRoundSnapshot.value || {}),
    normalizeAgentEmergenceRows(runDetail.value)
  ).filter(item => item.round <= maxRound).sort(sortByRoundDesc)
})

const combinedRuntimeEvents = computed(() => [
  ...agentEmergenceRows.value.slice(0, 4),
  ...relationshipEventRows.value.slice(0, 8)
].sort(sortByRoundDesc))

const policyExecutionRows = computed(() => {
  const maxRound = runtimeRoundCeiling.value
  return mergeRuntimeRows(
    normalizePolicyExecutionRows(selectedRoundSnapshot.value || {}, runtimeAgentNameById.value),
    normalizePolicyExecutionRows(runDetail.value, runtimeAgentNameById.value)
  ).filter(item => item.round <= maxRound).sort(sortByRoundDesc)
})

const policyExecutionSummary = computed(() => {
  const executed = policyExecutionRows.value.filter(item => item.status === 'executed').length
  const blocked = policyExecutionRows.value.filter(item => item.status === 'blocked').length
  if (policyExecutionRows.value.length === 0) return '当前轮次无到期措施'
  return `${executed} 项已执行 · ${blocked} 项受阻`
})

const relationshipDynamics = computed(() => {
  const rows = relationshipStateRows.value
  const average = key => rows.length > 0
    ? rows.reduce((sum, item) => sum + Number(item[key] || 0), 0) / rows.length
    : 0
  return {
    activeCount: rows.filter(item => item.status === 'active').length,
    trustLabel: formatPercent(average('trust')),
    coordinationLabel: formatPercent(average('coordination')),
    tensionLabel: formatPercent(average('tension'))
  }
})

const dominantInteractionLabel = computed(() => {
  if (agentInteractions.value.length === 0) return '暂无交互'

  const counts = new Map()
  agentInteractions.value.forEach(item => {
    const channel = item.channel || 'interaction'
    counts.set(channel, (counts.get(channel) || 0) + 1)
  })

  const [channel, count] = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0] || []
  return channel ? `${safeRuntimeCopy(channel, '交互')} · ${count}` : '暂无交互'
})

const activeVariableRows = computed(() => {
  return dedupeInterventionRows(
    normalizeInterventionRows(selectedRoundSnapshot.value?.active_variables || latestSnapshot.value?.active_variables, 'active')
  ).sort(sortInterventionRows)
})

const interventionRows = computed(() => {
  const rows = [
    ...normalizeInterventionRows(runDetail.value?.interventions || runDetail.value?.envfish?.interventions, 'accepted'),
    ...activeVariableRows.value,
    ...normalizeInterventionRows(simulationSnapshot.value?.interventions || simulationSnapshot.value?.envfish?.interventions, 'accepted'),
    ...normalizeInterventionRows(
      configSnapshot.value?.initial_interventions || configSnapshot.value?.simulation_config?.initial_interventions,
      'configured'
    ),
    ...injectionHistory.value
  ]

  return dedupeInterventionRows(rows).sort(sortInterventionRows)
})

const agentInteractionScopeLabel = computed(() => {
  if (selectedRoundInteractions.value.length > 0) return `${selectedRoundLabel.value} 快照`
  if (agentInteractions.value.length > 0) return `累计到 ${selectedRoundLabel.value}`
  return '暂无交互'
})

const spreadEvents = computed(() => {
  const source = normalizeEvents(runDetail.value)
  const maxRound = runtimeRoundCeiling.value
  return source.filter(event => (event.round || event.round_num || 0) <= maxRound)
})

const feedbackLoops = computed(() => {
  const loops = runDetail.value.feedback_loops || runDetail.value.loop_summary || runDetail.value.feedback_chain || []
  if (Array.isArray(loops)) return loops.map(localizeFeedbackLoop).filter(Boolean)
  if (typeof loops === 'string') {
    return loops.split('|').map(item => item.trim()).filter(Boolean).map(localizeFeedbackLoop)
  }
  return []
})

function localizeFeedbackLoop(value, index = 0) {
  const text = String(value || '').trim()
  if (!text) return ''
  const translated = translateDisplayToken(text, text)
  if (/[一-鿿]/.test(translated)) return translated

  const normalized = text.toLowerCase()
  if (normalized.includes('restricted access') && normalized.includes('economic')) {
    return '限制进入抑制经济活动，但提升公共信任，形成负反馈。'
  }
  if (normalized.includes('spillover') && normalized.includes('restriction')) {
    return '相邻区域的限制措施产生中等强度外溢。'
  }
  if (normalized.includes('economic loop') && normalized.includes('restriction')) {
    return '限制措施在相邻区域形成相似的经济负反馈。'
  }
  if (normalized.includes('positive feedback')) return '系统记录到持续增强的正反馈链。'
  if (normalized.includes('negative feedback')) return '系统记录到抑制扩散的负反馈链。'
  return `反馈链 ${index + 1}：系统记录到跨区域状态回传。`
}

function arrayValue(value) {
  return Array.isArray(value) ? value : []
}

function normalizeRuntimeRiskObject(raw = {}, index = 0) {
  const confidence = Number(raw.confidence_score ?? raw.confidence ?? 0)
  const evidenceStrength = Number(raw.evidence_strength_score)
  const statement = raw.risk_statement && typeof raw.risk_statement === 'object' ? raw.risk_statement : {}
  const riskId = String(raw.risk_object_id || raw.risk_id || raw.id || `risk_runtime_${index + 1}`)
  return {
    ...raw,
    risk_object_id: riskId,
    risk_id: String(raw.risk_id || riskId),
    risk_contract_version: Number(raw.risk_contract_version) || 1,
    title: safeRuntimeCopy(raw.title || raw.name, `风险对象 ${index + 1}`),
    summary: safeRuntimeCopy(raw.summary || raw.description, '等待风险对象摘要。'),
    why_now: safeRuntimeCopy(raw.why_now || raw.summary, '当前轮次持续观察该风险对象。'),
    primary_family: String(raw.primary_family || raw.risk_type || raw.category || 'other_emergent'),
    primary_family_label: safeRuntimeCopy(raw.primary_family_label, ''),
    tags: uniqueList(arrayValue(raw.tags)).slice(0, 8),
    evidence_strength_score: Number.isFinite(evidenceStrength)
      ? evidenceStrength
      : Math.max(0, Math.min(100, confidence <= 1 ? confidence * 100 : confidence)),
    impact_score: Number(raw.impact_score ?? raw.severity_score ?? 0),
    priority_score: Number(raw.priority_score ?? raw.priority_seed ?? 0),
    risk_statement: {
      ...statement,
      trigger_name: safeRuntimeCopy(statement.trigger_name || arrayValue(raw.root_pressures)[0], '场景触发因素'),
      source_node_ids: uniqueList(arrayValue(statement.source_node_ids)),
      receptor_node_ids: uniqueList(arrayValue(statement.receptor_node_ids)),
      receptor_name: safeRuntimeCopy(statement.receptor_name || arrayValue(raw.chain_steps).at(-1), '主要受影响对象'),
      consequence: safeRuntimeCopy(statement.consequence || raw.consequence || raw.summary, '等待具体后果说明。'),
      region_refs: arrayValue(statement.region_refs),
      entity_refs: arrayValue(statement.entity_refs),
      actor_refs: arrayValue(statement.actor_refs)
    },
    mechanism_node_ids: uniqueList(arrayValue(raw.mechanism_node_ids)),
    mechanism_edge_ids: uniqueList(arrayValue(raw.mechanism_edge_ids || raw.edge_ids)),
    edge_ids: uniqueList([...arrayValue(raw.edge_ids), ...arrayValue(raw.mechanism_edge_ids)]),
    monitoring_metrics: arrayValue(raw.monitoring_metrics).filter(item => item && typeof item === 'object'),
    quality_flags: uniqueList(arrayValue(raw.quality_flags)),
    evidence: arrayValue(raw.evidence).filter(item => item && typeof item === 'object'),
    region_scope: uniqueList(arrayValue(raw.region_scope)),
    primary_regions: uniqueList(arrayValue(raw.primary_regions)),
    source_entity_uuids: uniqueList(arrayValue(raw.source_entity_uuids)),
    source_actor_ids: uniqueList(arrayValue(raw.source_actor_ids)),
    source_actor_names: uniqueList(arrayValue(raw.source_actor_names)),
    root_pressures: uniqueList(arrayValue(raw.root_pressures).map(value => safeRuntimeCopy(value, '')).filter(Boolean)),
    chain_steps: uniqueList(arrayValue(raw.chain_steps).map(value => safeRuntimeCopy(value, '')).filter(Boolean)),
    affected_clusters: arrayValue(raw.affected_clusters),
    scenario_branches: arrayValue(raw.scenario_branches || raw.branch_templates),
    created_round: Number(raw.created_round) || 0,
    lifecycle_status: String(raw.lifecycle_status || raw.runtime_status || raw.status || 'watch')
  }
}

const riskObjects = computed(() => {
  const candidates = [
    runDetail.value?.risk_objects,
    simulationSnapshot.value?.risk_objects,
    configSnapshot.value?.risk_objects,
    runDetail.value?.risk_definitions,
    simulationSnapshot.value?.risk_definitions,
    configSnapshot.value?.risk_definitions
  ]

  for (const items of candidates) {
    if (Array.isArray(items) && items.length > 0) {
      return items
        .map(normalizeRuntimeRiskObject)
        .sort((a, b) => {
          const archivedA = ['dormant', 'resolved'].includes(a.lifecycle_status) ? 1 : 0
          const archivedB = ['dormant', 'resolved'].includes(b.lifecycle_status) ? 1 : 0
          if (archivedA !== archivedB) return archivedA - archivedB
          return Number(b.priority_score || b.runtime_tension || 0) - Number(a.priority_score || a.runtime_tension || 0)
        })
    }
  }

  return []
})

const activeRiskObjectCount = computed(() => riskObjects.value.filter(item => !['dormant', 'resolved'].includes(item.lifecycle_status)).length)
const riskContractVersion = computed(() => {
  const version = Number(
    riskObjects.value[0]?.risk_contract_version ||
    runDetail.value?.risk_contract_version ||
    simulationSnapshot.value?.risk_contract_version ||
    configSnapshot.value?.risk_contract_version
  )
  return Number.isFinite(version) && version > 0 ? version : 1
})

const primaryRiskObjectId = computed(() => {
  return (
    runDetail.value?.primary_risk_object?.risk_object_id ||
    runDetail.value?.risk_objects_summary?.primary_risk_object_id ||
    simulationSnapshot.value?.primary_risk_object?.risk_object_id ||
    simulationSnapshot.value?.risk_objects_summary?.primary_risk_object_id ||
    configSnapshot.value?.primary_risk_object_id ||
    riskObjects.value[0]?.risk_object_id ||
    ''
  )
})

const selectedRiskObject = computed(() => {
  if (riskObjects.value.length === 0) return null
  return riskObjects.value.find(item => item.risk_object_id === selectedRiskObjectId.value) || riskObjects.value[0]
})

const selectedRiskStatement = computed(() => selectedRiskObject.value?.risk_statement || {})
const selectedRiskMechanismSteps = computed(() => {
  const steps = uniqueList(selectedRiskObject.value?.chain_steps || [])
  return steps.length > 2 ? steps.slice(1, -1) : []
})
const selectedRiskEvidence = computed(() => (selectedRiskObject.value?.evidence || []).map((item, index) => ({
  ...item,
  title: safeRuntimeCopy(item.title || item.name, `机制依据 ${index + 1}`),
  summary: safeRuntimeCopy(item.summary || item.description, ''),
  epistemic_status_label: safeRuntimeCopy(item.epistemic_status_label, '')
})))
const selectedRiskMetrics = computed(() => (selectedRiskObject.value?.monitoring_metrics || []).map((item, index) => ({
  ...item,
  label: safeRuntimeCopy(item.label || item.name || item.key, `监测指标 ${index + 1}`)
})))

function scopeBasisLabel(value) {
  return value ? safeRuntimeCopy(translateDisplayToken(value, ''), '') : ''
}

function riskFamilyLabel(item) {
  return safeRuntimeCopy(
    item?.primary_family_label || translateDisplayToken(item?.primary_family || item?.risk_type || 'other_emergent', ''),
    '其他涌现风险'
  )
}

function riskEvidenceScore(item) {
  const value = Number(item?.evidence_strength_score)
  if (Number.isFinite(value)) return Math.round(Math.max(0, Math.min(100, value)))
  const confidence = Number(item?.confidence_score)
  if (!Number.isFinite(confidence)) return 0
  return Math.round(Math.max(0, Math.min(100, confidence <= 1 ? confidence * 100 : confidence)))
}

const selectedRiskEvents = computed(() => {
  if (!selectedRiskObject.value) return []
  const riskId = selectedRiskObject.value.risk_object_id
  const sources = [
    runDetail.value?.risk_events,
    simulationSnapshot.value?.risk_events,
    configSnapshot.value?.risk_events
  ]
  const events = sources.find(items => Array.isArray(items) && items.length > 0) || []
  return events
    .filter(item => item && typeof item === 'object' && String(item.risk_id || item.risk_object_id || item.to_risk_id || '') === riskId)
    .map(item => ({
      ...item,
      summary: safeRuntimeCopy(item.summary || item.description, '风险状态发生变化。')
    }))
    .sort((a, b) => Number(b.round || 0) - Number(a.round || 0))
})

const graphNodes = computed(() => collectGraphNodes(props.graphData))

const graphNodeMap = computed(() => {
  const map = new Map()
  graphNodes.value.forEach(node => {
    if (node?.uuid) {
      map.set(node.uuid, node)
    }
  })
  return map
})

const graphEdgeMap = computed(() => {
  const map = new Map()
  const edges = [
    ...(Array.isArray(props.graphData?.edges) ? props.graphData.edges : []),
    ...(Array.isArray(props.animationData?.layout?.edges) ? props.animationData.layout.edges : [])
  ]
  edges.forEach((edge, index) => {
    const id = edge?.uuid || edge?.id || edge?.edge_id || `${edge?.source_node_uuid || edge?.source || 'source'}-${edge?.target_node_uuid || edge?.target || 'target'}-${index}`
    if (id) {
      map.set(String(id), edge)
    }
  })
  return map
})

const playbackNodeMap = computed(() => {
  const map = new Map(graphNodeMap.value)
  const nodes = Array.isArray(props.animationData?.layout?.nodes) ? props.animationData.layout.nodes : []
  nodes.forEach((node) => {
    const id = node?.uuid || node?.id
    if (id && !map.has(String(id))) {
      map.set(String(id), node)
    }
  })
  return map
})

const playbackPulseStats = computed(() => {
  const frame = selectedAnimationFrame.value || {}
  const events = Array.isArray(frame.propagation_events) ? frame.propagation_events : []
  const edgeStates = Array.isArray(frame.edge_states) ? frame.edge_states : []
  const nodeIds = Array.isArray(frame.focus_ids?.node_ids) ? frame.focus_ids.node_ids : []
  const startedEventCount = Number(frame.playback_started_event_count)
  if (events.length || Number.isFinite(startedEventCount)) {
    const elapsed = Number(frame.playback_elapsed_ms || 0)
    const activeIds = new Set(Array.isArray(frame.active_propagation_event_ids) ? frame.active_propagation_event_ids : [])
    const connectionEvents = events.filter(item => item?.edge_id || (item?.source_node_id && item?.target_node_id))
    return {
      newEdges: Number.isFinite(startedEventCount)
        ? startedEventCount
        : connectionEvents.filter(item => elapsed >= Number(item?.timing?.start_ms || 0)).length,
      activeEdges: connectionEvents.filter(item => activeIds.has(String(item?.event_id || ''))).length,
      focusNodes: nodeIds.length
    }
  }
  return {
    newEdges: edgeStates.filter(item => String(item?.status || '') === 'new').length,
    activeEdges: edgeStates.filter(item => String(item?.status || '') === 'active').length,
    focusNodes: nodeIds.length
  }
})

const playbackPulseRelations = computed(() => {
  const frame = selectedAnimationFrame.value || {}
  const curatedEvents = Array.isArray(frame.visible_events) ? frame.visible_events : []
  if (isCuratedShowcase.value && curatedEvents.length) {
    return curatedEvents.slice(0, 6).map((event, index) => ({
      id: String(event?.id || `curated-event-${currentRoundNumber.value}-${index}`),
      status: 'active',
      statusLabel: '主线推进',
      sourceName: safeRuntimeCopy(event?.title, '本轮主体行动'),
      targetName: '',
      typeLabel: `${safeRuntimeCopy(activeStoryChapter.value?.name, '演化章节')} · ${selectedRoundLabel.value}`,
    }))
  }
  const activeAndTrailEvents = Array.isArray(frame.propagation_events) ? frame.propagation_events : []
  const recentCompletedEvents = Array.isArray(frame.recent_completed_propagation_events)
    ? frame.recent_completed_propagation_events
    : []
  const timelineEventById = new Map()
  ;[...activeAndTrailEvents, ...recentCompletedEvents].forEach((event, index) => {
    const id = String(event?.event_id || event?.id || `timeline-event-${index}`)
    if (!timelineEventById.has(id)) timelineEventById.set(id, event)
  })
  const timelineEvents = [...timelineEventById.values()]
  if (timelineEvents.length) {
    const elapsed = Number(frame.playback_elapsed_ms || 0)
    const activeIds = new Set(Array.isArray(frame.active_propagation_event_ids) ? frame.active_propagation_event_ids : [])
    const trailIds = new Set(Array.isArray(frame.trail_propagation_event_ids) ? frame.trail_propagation_event_ids : [])
    return timelineEvents
      .filter(item => (item?.edge_id || (item?.source_node_id && item?.target_node_id)) && elapsed >= Number(item?.timing?.start_ms || 0))
      .sort((a, b) => {
        const activeDelta = Number(activeIds.has(String(b?.event_id || ''))) - Number(activeIds.has(String(a?.event_id || '')))
        if (activeDelta !== 0) return activeDelta
        const trailDelta = Number(trailIds.has(String(b?.event_id || ''))) - Number(trailIds.has(String(a?.event_id || '')))
        if (trailDelta !== 0) return trailDelta
        return Number(b?.timing?.start_ms || 0) - Number(a?.timing?.start_ms || 0)
      })
      .slice(0, 6)
      .map((event, index) => {
        const edgeId = String(event?.edge_id || '')
        const edge = graphEdgeMap.value.get(edgeId) || {}
        const sourceId = String(event?.source_node_id || edge.source_node_uuid || edge.source || '')
        const targetId = String(event?.target_node_id || edge.target_node_uuid || edge.target || '')
        const sourceNode = playbackNodeMap.value.get(sourceId)
        const targetNode = playbackNodeMap.value.get(targetId)
        const active = activeIds.has(String(event?.event_id || ''))
        return {
          id: String(event?.event_id || `${edgeId || 'event'}-${index}`),
          status: active ? 'active' : 'new',
          statusLabel: active ? '正在延展' : '已经传导',
          sourceName: safeRuntimeCopy(sourceNode?.name || event?.source_name || edge.source_name, '来源节点'),
          targetName: safeRuntimeCopy(targetNode?.name || event?.target_name || edge.target_name, '目标节点'),
          typeLabel: safeRuntimeCopy(
            event?.display_label
              || event?.label_zh
              || event?.summary
              || translateDisplayToken(event?.kind || edge.fact_type || edge.name || 'related_to', ''),
            '关系响应'
          )
        }
      })
  }
  const edgeStates = Array.isArray(frame.edge_states) ? frame.edge_states : []
  const focusEdgeIds = new Set((frame.focus_ids?.edge_ids || []).map(item => String(item || '')).filter(Boolean))
  return edgeStates
    .filter(item => ['new', 'active'].includes(String(item?.status || '')) || focusEdgeIds.has(String(item?.id || '')))
    .sort((a, b) => {
      const statusDelta = relationStatusPriority(b.status) - relationStatusPriority(a.status)
      if (statusDelta !== 0) return statusDelta
      return Number(a.delay_ms || 0) - Number(b.delay_ms || 0)
    })
    .slice(0, 6)
    .map((state, index) => {
      const edge = graphEdgeMap.value.get(String(state.id || '')) || {}
      const sourceId = String(edge.source_node_uuid || edge.source || '')
      const targetId = String(edge.target_node_uuid || edge.target || '')
      const sourceNode = playbackNodeMap.value.get(sourceId)
      const targetNode = playbackNodeMap.value.get(targetId)
      const status = String(state.status || 'steady')
      return {
        id: `${state.id || index}-${status}`,
        status,
        statusLabel: status === 'new' ? '新增' : status === 'active' ? '活跃' : '相关',
        sourceName: safeRuntimeCopy(sourceNode?.name || edge.source_name, '来源节点'),
        targetName: safeRuntimeCopy(targetNode?.name || edge.target_name, '目标节点'),
        typeLabel: safeRuntimeCopy(translateDisplayToken(edge.fact_type || edge.name || 'related_to', ''), '关系')
      }
    })
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

const graphNodeByToken = computed(() => {
  const map = new Map()
  const add = (token, node) => {
    const key = String(token || '').trim().toLowerCase()
    if (key && !map.has(key)) map.set(key, node)
  }
  graphNodes.value.forEach(node => {
    add(node?.uuid, node)
    add(node?.id, node)
    add(node?.key, node)
    add(node?.name, node)
    add(node?.label, node)
    add(node?.username, node)
    add(node?.attributes?.agent_id, node)
    add(node?.attributes?.region_id, node)
    add(node?.attributes?.mechanism_node_id, node)
    add(node?.agent_id, node)
    add(node?.source_entity_uuid, node)
    add(node?.attributes?.source_entity_uuid, node)
  })
  return map
})

function resolveGraphNodeByToken(token) {
  return graphNodeByToken.value.get(String(token || '').trim().toLowerCase()) || null
}

function isInternalDisplayToken(value) {
  const text = String(value || '').trim().toLowerCase()
  return ['blue', 'brown', 'orange', 'green', 'purple', 'cyan', 'red', 'yellow', 'gray', 'grey'].includes(text)
}

const riskObjectEntityNodes = computed(() => {
  if (!selectedRiskObject.value) return []
  const statement = selectedRiskObject.value.risk_statement || {}
  const entityTokens = uniqueList([
    ...(selectedRiskObject.value.mechanism_node_ids || []),
    ...(statement.source_node_ids || []),
    ...(statement.receptor_node_ids || []),
    ...(selectedRiskObject.value.source_entity_uuids || []),
    ...(selectedRiskObject.value.source_actor_ids || []),
    ...(selectedRiskObject.value.source_actor_names || [])
  ])
  const seen = new Set()
  return entityTokens.flatMap((token) => {
    const node = resolveGraphNodeByToken(token)
    if (!node) return []
    const id = String(node.uuid || node.id || node.name || token)
    if (seen.has(id)) return []
    seen.add(id)
    return {
      id,
      uuid: node.uuid || node.id || node.name,
      name: safeRuntimeCopy(node.name || node.label, '关联主体'),
      labels: normalizeLabels(node?.labels),
      summary: safeRuntimeCopy(node?.summary, ''),
      matched: true
    }
  })
})

const riskAffectedSubjectNodes = computed(() => {
  if (!selectedRiskObject.value) return []
  const statement = selectedRiskObject.value.risk_statement || {}
  const refs = [
    ...(statement.entity_refs || []).map(item => ({
      id: item?.entity_uuid || item?.id,
      name: item?.entity_name || item?.name,
      entityType: item?.entity_type || item?.entityType || item?.node_family || item?.type,
      summary: item?.entity_summary || item?.entitySummary || item?.summary,
      labels: item?.labels,
      scopeBasis: item?.scope_basis || item?.scopeBasis,
      epistemicStatus: item?.epistemic_status || item?.epistemicStatus,
      referenceKind: 'entity'
    })),
    ...(statement.actor_refs || []).map(item => ({
      id: item?.actor_id || item?.agent_id,
      name: item?.actor_name || item?.agent_name || item?.name,
      entityType: item?.actor_type || item?.agent_type || item?.node_family,
      summary: [item?.matched_role_demand_label, item?.profession].filter(Boolean).join(' · '),
      labels: item?.labels,
      scopeBasis: item?.scope_basis || item?.scopeBasis,
      epistemicStatus: item?.epistemic_status || item?.epistemicStatus,
      referenceKind: 'actor'
    })),
    ...(statement.receptor_node_ids || []).map(item => ({
      id: item,
      name: statement.receptor_name,
      referenceKind: 'mechanism_receptor',
      labels: ['机制节点', '受体']
    }))
  ]
  const seen = new Set()
  return refs.flatMap((ref, index) => {
    const node = resolveGraphNodeByToken(ref.id) || resolveGraphNodeByToken(ref.name)
    const id = String(node?.uuid || node?.id || ref.id || ref.name || `risk-subject-${index}`)
    if (!id || seen.has(id)) return []
    seen.add(id)
    const name = safeRuntimeCopy(node?.name || node?.label || ref.name, '关联主体')
    if (!name || isInternalDisplayToken(name)) return []
    const referenceLabels = normalizeLabels([ref.entityType, ...arrayValue(ref.labels)])
    return [{
      id,
      uuid: node?.uuid || node?.id || ref.id || '',
      name,
      labels: referenceLabels.length > 0 ? referenceLabels : normalizeLabels(node?.labels),
      summary: safeRuntimeCopy(ref.summary || node?.summary, ''),
      scopeBasisLabel: scopeBasisLabel(ref.scopeBasis),
      epistemicStatus: ref.epistemicStatus || '',
      stateLabel: ref.referenceKind === 'mechanism_receptor'
        ? '受影响对象'
        : ref.referenceKind === 'actor'
          ? (node ? '场景代理体' : '已引用代理体')
          : (node ? '真实实体' : '已校验实体'),
      matched: Boolean(node)
    }]
  })
})

const riskObjectRegionNodes = computed(() => {
  if (!selectedRiskObject.value) return []
  const seen = new Set()

  const statementRegions = (selectedRiskObject.value.risk_statement?.region_refs || []).map(item => ({
    id: item?.region_id || item?.id || item?.region_name || item?.name,
    name: item?.region_name || item?.name || item?.region_id || item?.id,
    scopeBasis: item?.scope_basis || item?.scopeBasis,
    epistemicStatus: item?.epistemic_status || item?.epistemicStatus
  }))
  const legacyRegions = uniqueList([
    ...(selectedRiskObject.value.primary_regions || []),
    ...(selectedRiskObject.value.region_scope || [])
  ]).map(name => ({ id: name, name }))
  const refs = statementRegions.length > 0 ? statementRegions : legacyRegions

  return refs.flatMap((ref, index) => {
    const name = safeRuntimeCopy(ref.name, `作用区域 ${index + 1}`)
    if (!name || isInternalDisplayToken(name)) return []
    const matched = graphNodesByName.value.get(String(name).toLowerCase()) || []
    const node = resolveGraphNodeByToken(ref.id) || resolveGraphNodeByToken(name) || matched[0]
    const dedupeKey = String(node?.uuid || node?.id || name).trim().toLowerCase()
    if (!dedupeKey || seen.has(dedupeKey)) return []
    seen.add(dedupeKey)
    return {
      id: node?.uuid || `risk-region-${index}`,
      name,
      labels: normalizeLabels(node?.labels),
      summary: safeRuntimeCopy(node?.summary, ''),
      scopeBasisLabel: scopeBasisLabel(ref.scopeBasis),
      epistemicStatus: ref.epistemicStatus || '',
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
    nodeIds: uniqueList([
      ...riskObjectEntityNodes.value.map(item => item.uuid),
      ...riskAffectedSubjectNodes.value.map(item => item.uuid)
    ]),
    nodeNames: uniqueList([
      ...riskObjectEntityNodes.value.map(item => item.name),
      ...riskAffectedSubjectNodes.value.map(item => item.name),
      ...riskObjectRegionNodes.value.map(item => item.name)
    ]),
    edgeIds: uniqueList(selectedRiskObject.value.edge_ids || []),
    mode: selectedRiskObject.value.generation_mode || selectedRiskObject.value.mode || 'risk_definition'
  }
})

const workspaceTabs = computed(() => {
  const metaByTab = {
    pulse: `${playbackPulseStats.value.newEdges} 条新增`,
    state: `${regionRows.value.length} 个区域`,
    spread: `${spreadEvents.value.length} 个事件`,
    agents: `${agentRows.value.length} 个主体 · ${relationshipStateRows.value.length} 条关系`,
    risk: `${riskObjects.value.length} 个风险对象`,
  }
  return STEP3_WORKSPACE_TABS.map((item, index) => ({
    ...item,
    panelId: `workspace-panel-${item.value}`,
    index: String(index + 1).padStart(2, '0'),
    meta: metaByTab[item.value],
  }))
})

const activeWorkspaceTabLabel = computed(() => {
  return workspaceTabs.value.find(item => item.value === activeWorkspaceTab.value)?.label || '推演观察视图'
})

function syncRiskSelectorScrollState() {
  const track = riskSelectorRef.value
  if (!track) {
    riskSelectorOverflow.value = false
    canScrollRiskSelectorPrev.value = false
    canScrollRiskSelectorNext.value = false
    return
  }
  const maxScrollLeft = Math.max(0, track.scrollWidth - track.clientWidth)
  const availableWidth = track.closest('.risk-selector-shell')?.clientWidth || track.clientWidth
  riskSelectorOverflow.value = track.scrollWidth > availableWidth + 2
  canScrollRiskSelectorPrev.value = riskSelectorOverflow.value && track.scrollLeft > 2
  canScrollRiskSelectorNext.value = riskSelectorOverflow.value && track.scrollLeft < maxScrollLeft - 2
}

function scrollRiskSelector(direction) {
  const track = riskSelectorRef.value
  if (!track) return
  track.scrollBy({
    left: direction * Math.max(190, track.clientWidth * 0.82),
    behavior: 'smooth'
  })
}

async function revealSelectedRiskObject() {
  await nextTick()
  const track = riskSelectorRef.value
  const activeItem = track?.querySelector('.risk-selector-option.active')
  activeItem?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  syncRiskSelectorScrollState()
}

function selectRiskObject(riskObjectId) {
  selectedRiskObjectId.value = riskObjectId
  activeRiskDetailTab.value = 'chain'
  revealSelectedRiskObject()
}

function handleWorkspaceScroll(event) {
  workspaceScrollByTab.value[activeWorkspaceTab.value] = event.currentTarget?.scrollTop || 0
}

async function selectWorkspaceTab(tab) {
  if (!workspaceTabs.value.some(item => item.value === tab) || tab === activeWorkspaceTab.value) return
  const shell = workspaceShellRef.value
  if (shell) workspaceScrollByTab.value[activeWorkspaceTab.value] = shell.scrollTop
  activeWorkspaceTab.value = tab
  await nextTick()
  if (workspaceShellRef.value) {
    workspaceShellRef.value.scrollTop = workspaceScrollByTab.value[tab] || 0
  }
}

function addLog(msg) {
  emit('add-log', msg)
}

function createInjectionRequestKey() {
  if (globalThis.crypto?.randomUUID) return `inject_${globalThis.crypto.randomUUID()}`
  return `inject_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

function createInjection() {
  return {
    type: 'disaster',
    name: '',
    description: '',
    target_regions_text: '',
    target_nodes_text: '',
    start_round: 0,
    duration_rounds: 3,
    intensity: 70,
    policy_mode: 'restrict'
  }
}

function normalizeScore(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return 0
  return Math.max(0, Math.min(100, Math.round(number)))
}

function formatPercent(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return '暂无'
  if (number <= 1) return `${Math.round(number * 100)}%`
  return `${Math.round(Math.max(0, Math.min(100, number)))}%`
}

function formatTokenLabel(value, fallback = '未分类') {
  const translated = formatTokenLabelZh(value, fallback)
  return safeRuntimeCopy(translated, fallback)
}

function formatStatusLabel(value) {
  const map = {
    accepted: '已接收',
    active: '生效中',
    configured: '预置',
    queued: '排队中'
  }
  return map[String(value || '').toLowerCase()] || formatTokenLabel(value, '变量')
}

function formatVariableTypeLabel(value) {
  const map = {
    disaster: '污染变量',
    policy: '政策变量'
  }
  return map[String(value || '').toLowerCase()] || formatTokenLabel(value, '变量')
}

function formatInlineList(items, fallback = '—') {
  const values = uniqueList(Array.isArray(items) ? items : [])
  return values.length > 0
    ? values.map(item => safeRuntimeCopy(item, '')).filter(Boolean).join(' · ') || fallback
    : fallback
}

function safeRuntimeCopy(value, fallback = '') {
  return safeDisplayText(value, fallback)
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
  return normalizeDisplayLabels(
    uniqueList(Array.isArray(labels) ? labels : []).filter(label => !isInternalDisplayToken(label)),
    3
  )
}

const RUNTIME_STATUS_META = {
  watch: { label: '观察', cls: 'steady' },
  rising: { label: '上升', cls: 'rising' },
  falling: { label: '回落', cls: 'falling' },
  critical: { label: '临界', cls: 'critical' },
  elevated: { label: '偏高', cls: 'elevated' },
  resolved: { label: '已解除', cls: 'resolved' },
  dormant: { label: '休眠', cls: 'dormant' },
  steady: { label: '平稳', cls: 'steady' }
}

function runtimeStatusMeta(value) {
  const key = String(value || '').trim().toLowerCase()
  return RUNTIME_STATUS_META[key] || { label: safeRuntimeCopy(translateDisplayToken(value, ''), '平稳'), cls: 'steady' }
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

function normalizeTension(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return number <= 1 ? Math.round(number * 100) : Math.round(number)
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

function buildTensionSparkline(trace, width = 110, height = 28) {
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
    lastY: lastY.toFixed(1)
  }
}

function formatUncertaintyBand(band) {
  if (!band || typeof band !== 'object') return null
  const center = normalizeTension(band.center)
  if (center === null) return null
  const lower = normalizeTension(band.lower)
  const upper = normalizeTension(band.upper)
  const range = (lower !== null && upper !== null) ? `${lower} – ${upper}` : null
  const label = safeRuntimeCopy(band.label, '')
  return {
    center,
    range,
    label: label && label !== '模型' ? label : '推断区间（非测量值）',
    derived: band.derived !== false
  }
}

function collectGraphNodes(data) {
  if (Array.isArray(data?.nodes)) return data.nodes
  if (Array.isArray(data?.graph?.nodes)) return data.graph.nodes
  return []
}

function extractRoundNumber(snapshot, fallback = 0) {
  return snapshot?.round ?? snapshot?.round_num ?? snapshot?.step ?? fallback + 1
}

function snapshotKey(snapshot, idx) {
  return snapshot?.id || `${extractRoundNumber(snapshot, idx)}-${idx}`
}

function normalizeRegionRows(source) {
  const raw =
    source?.region_states ||
    source?.regions ||
    source?.region_matrix ||
    source?.state_matrix ||
    source?.matrix ||
    []

  const rows = []

  if (Array.isArray(raw)) {
    raw.forEach((item, idx) => {
      if (typeof item === 'string') {
        rows.push({ id: `${idx}`, name: safeRuntimeCopy(item, `区域 ${idx + 1}`) })
        return
      }
      const state = { ...(item.state_vector || {}), ...(item.business_state || {}) }
      const name = item.region || item.region_name || item.name || item.label || item.id || `region_${idx}`
      rows.push({
        id: item.region_id || item.id || `${name}-${idx}`,
        name: safeRuntimeCopy(name, `区域 ${idx + 1}`),
        tagline: safeRuntimeCopy(item.region_type || item.category || item.type || '', '区域'),
        exposure_score: normalizeScore(item.exposure_score ?? item.exposure ?? 0),
        spread_pressure: normalizeScore(item.spread_pressure ?? item.spread ?? 0),
        ecosystem_integrity: normalizeScore(item.ecosystem_integrity ?? item.ecosystem ?? 100),
        livelihood_stability: normalizeScore(item.livelihood_stability ?? item.livelihood ?? 100),
        public_trust: normalizeScore(item.public_trust ?? state.public_trust ?? item.trust ?? 100),
        panic_level: normalizeScore(item.panic_level ?? item.panic ?? 0),
        service_capacity: normalizeScore(item.service_capacity ?? item.service ?? 100),
        response_capacity: normalizeScore(item.response_capacity ?? item.response ?? 100),
        economic_stress: normalizeScore(item.economic_stress ?? item.stress ?? 0),
        vulnerability_score: normalizeScore(item.vulnerability_score ?? item.vulnerability ?? 0),
        exposure_pressure: normalizeScore(item.exposure_pressure ?? state.exposure_pressure ?? item.exposure_score ?? 0),
        detection_visibility: normalizeScore(item.detection_visibility ?? state.detection_visibility ?? 0),
        testing_turnaround: normalizeScore(item.testing_turnaround ?? state.testing_turnaround ?? 0),
        healthcare_load: normalizeScore(item.healthcare_load ?? state.healthcare_load ?? 0),
        mobility_intensity: normalizeScore(item.mobility_intensity ?? state.mobility_intensity ?? 0),
        supply_sufficiency: normalizeScore(item.supply_sufficiency ?? state.supply_sufficiency ?? 0),
        community_support: normalizeScore(item.community_support ?? state.community_support ?? 0)
      })
    })
    return rows
  }

  if (raw && typeof raw === 'object') {
    Object.entries(raw).forEach(([key, value], idx) => {
      if (value && typeof value === 'object') {
        const state = { ...(value.state_vector || {}), ...(value.business_state || {}) }
        rows.push({
          id: key,
          name: safeRuntimeCopy(value.region || value.name || key, `区域 ${idx + 1}`),
          tagline: safeRuntimeCopy(value.region_type || value.category || '', '区域'),
          exposure_score: normalizeScore(value.exposure_score ?? value.exposure ?? 0),
          spread_pressure: normalizeScore(value.spread_pressure ?? value.spread ?? 0),
          ecosystem_integrity: normalizeScore(value.ecosystem_integrity ?? value.ecosystem ?? 100),
          livelihood_stability: normalizeScore(value.livelihood_stability ?? value.livelihood ?? 100),
          public_trust: normalizeScore(value.public_trust ?? state.public_trust ?? value.trust ?? 100),
          panic_level: normalizeScore(value.panic_level ?? value.panic ?? 0),
          service_capacity: normalizeScore(value.service_capacity ?? value.service ?? 100),
          response_capacity: normalizeScore(value.response_capacity ?? value.response ?? 100),
          economic_stress: normalizeScore(value.economic_stress ?? value.stress ?? 0),
          vulnerability_score: normalizeScore(value.vulnerability_score ?? value.vulnerability ?? 0),
          exposure_pressure: normalizeScore(value.exposure_pressure ?? state.exposure_pressure ?? value.exposure_score ?? 0),
          detection_visibility: normalizeScore(value.detection_visibility ?? state.detection_visibility ?? 0),
          testing_turnaround: normalizeScore(value.testing_turnaround ?? state.testing_turnaround ?? 0),
          healthcare_load: normalizeScore(value.healthcare_load ?? state.healthcare_load ?? 0),
          mobility_intensity: normalizeScore(value.mobility_intensity ?? state.mobility_intensity ?? 0),
          supply_sufficiency: normalizeScore(value.supply_sufficiency ?? state.supply_sufficiency ?? 0),
          community_support: normalizeScore(value.community_support ?? state.community_support ?? 0)
        })
      } else {
        rows.push({ id: `${key}-${idx}`, name: safeRuntimeCopy(key, `区域 ${idx + 1}`), selectedScore: normalizeScore(value) })
      }
    })
  }

  return rows
}

function normalizeSubregionRows(source) {
  const raw =
    source?.subregions ||
    source?.subregion_graph ||
    source?.envfish?.subregion_graph ||
    source?.latest_round_snapshot?.subregions ||
    source?.latest_snapshot?.subregions ||
    source?.config?.subregion_graph ||
    source?.simulation_config?.subregion_graph ||
    []

  if (!Array.isArray(raw)) return []

  const parentNameLookup = new Map()
  const parentRaw =
    source?.region_graph ||
    source?.regions ||
    source?.envfish?.region_graph ||
    source?.latest_round_snapshot?.regions ||
    source?.latest_snapshot?.regions ||
    source?.config?.region_graph ||
    source?.simulation_config?.region_graph ||
    []

  if (Array.isArray(parentRaw)) {
    parentRaw.forEach((item) => {
      if (!item || typeof item !== 'object') return
      const parentId = String(item.region_id || item.id || item.uuid || item.name || '')
      if (!parentId) return
      parentNameLookup.set(parentId, item.name || item.region || item.label || parentId)
    })
  }

  return raw.map((item, idx) => {
    if (!item || typeof item !== 'object') {
      return {
        id: `subregion-${idx}`,
        name: safeRuntimeCopy(item, `子区域 ${idx + 1}`),
        tagline: '',
        parent_region_id: '',
        parentName: '',
        distance_band: '',
        agentCount: 0,
        exposure_score: 0,
        spread_pressure: 0,
        ecosystem_integrity: 100,
        livelihood_stability: 100,
        public_trust: 100,
        panic_level: 0,
        service_capacity: 100,
        response_capacity: 100,
        economic_stress: 0,
        vulnerability_score: 0
      }
    }

    const state = { ...(item.state_vector || {}), ...(item.business_state || {}) }
    const name = item.name || item.subregion_name || item.label || item.region_name || `subregion_${idx}`
    const parentId = String(item.parent_region_id || item.parent_id || item.parent_region || '')
    return {
      id: item.region_id || item.id || item.uuid || `${name}-${idx}`,
      name: safeRuntimeCopy(name, `子区域 ${idx + 1}`),
      tagline: safeRuntimeCopy(item.land_use_class || item.region_type || item.distance_band || item.zone || '', '细分区域'),
      parent_region_id: parentId,
      parentName:
        safeRuntimeCopy(
          item.parent_name ||
          item.parent_region_name ||
          parentNameLookup.get(parentId) ||
          parentId ||
          '',
          '宏观区域'
        ),
      landUseLabel: formatLandUseLabel(item.land_use_class || item.region_type || item.zone || ''),
      distanceLabel: formatDistanceLabel(item.distance_band || item.distance || ''),
      distance_band: item.distance_band || item.distance || '',
      agentCount: Array.isArray(item.agent_ids)
        ? item.agent_ids.length
        : Number(item.agent_count || item.count || item.agent_total || 0),
      tags: uniqueList([
        ...(Array.isArray(item.tags) ? item.tags : []),
        item.land_use_class,
        item.distance_band
      ]).slice(0, 6),
      exposure_score: normalizeScore(item.exposure_score ?? item.exposure ?? 0),
      spread_pressure: normalizeScore(item.spread_pressure ?? item.spread ?? 0),
      ecosystem_integrity: normalizeScore(item.ecosystem_integrity ?? item.ecosystem ?? 100),
      livelihood_stability: normalizeScore(item.livelihood_stability ?? item.livelihood ?? 100),
      public_trust: normalizeScore(item.public_trust ?? state.public_trust ?? item.trust ?? 100),
      panic_level: normalizeScore(item.panic_level ?? item.panic ?? 0),
      service_capacity: normalizeScore(item.service_capacity ?? item.service ?? 100),
      response_capacity: normalizeScore(item.response_capacity ?? item.response ?? 100),
      economic_stress: normalizeScore(item.economic_stress ?? item.stress ?? 0),
      vulnerability_score: normalizeScore(item.vulnerability_score ?? item.vulnerability ?? 0),
      exposure_pressure: normalizeScore(item.exposure_pressure ?? state.exposure_pressure ?? item.exposure_score ?? 0),
      detection_visibility: normalizeScore(item.detection_visibility ?? state.detection_visibility ?? 0),
      testing_turnaround: normalizeScore(item.testing_turnaround ?? state.testing_turnaround ?? 0),
      healthcare_load: normalizeScore(item.healthcare_load ?? state.healthcare_load ?? 0),
      mobility_intensity: normalizeScore(item.mobility_intensity ?? state.mobility_intensity ?? 0),
      supply_sufficiency: normalizeScore(item.supply_sufficiency ?? state.supply_sufficiency ?? 0),
      community_support: normalizeScore(item.community_support ?? state.community_support ?? 0)
    }
  })
}

function normalizeAgentRows(source, scoreKey = 'vulnerability_score', configuredProfiles = new Map()) {
  const raw =
    source?.agents ||
    source?.top_agents ||
    source?.agent_states ||
    source?.envfish?.latest_snapshot?.agents ||
    source?.latest_round_snapshot?.agents ||
    source?.latest_snapshot?.agents ||
    source?.agent_configs ||
    source?.actor_profiles ||
    []

  if (!Array.isArray(raw)) return []

  return raw.map((runtimeItem, idx) => {
    const rawId = runtimeItem?.agent_id ?? runtimeItem?.user_id ?? idx
    const configured = configuredProfiles.get(String(rawId)) || {}
    const item = {
      ...configured,
      ...(runtimeItem || {}),
      state_vector: {
        ...(configured.state_vector || {}),
        ...(runtimeItem?.state_vector || {})
      },
      runtime_lifecycle: {
        ...(configured.runtime_lifecycle || {}),
        ...(runtimeItem?.runtime_lifecycle || {})
      },
      capabilities: runtimeItem?.capabilities?.length ? runtimeItem.capabilities : configured.capabilities,
      capability_keys: runtimeItem?.capability_keys?.length ? runtimeItem.capability_keys : configured.capability_keys,
      permission_keys: runtimeItem?.permission_keys?.length ? runtimeItem.permission_keys : configured.permission_keys,
      resource_budget: Object.keys(runtimeItem?.resource_budget || {}).length > 0
        ? runtimeItem.resource_budget
        : configured.resource_budget,
      representation_level: runtimeItem?.representation_level || configured.representation_level,
      archetype_key: runtimeItem?.archetype_key || configured.archetype_key,
      role_type: runtimeItem?.role_type || configured.role_type,
      agent_subtype: runtimeItem?.agent_subtype || configured.agent_subtype,
      home_region_id: runtimeItem?.home_region_id || configured.home_region_id,
      home_subregion_id: runtimeItem?.home_subregion_id || configured.home_subregion_id
    }
    const agentType = canonicalRuntimeAgentFamily(item)
    const rawRoleType = String(item.role_type || '')
    const roleType = item.archetype_key || item.agent_subtype || (
      /^(?:entity|profile|actor|agent)$/i.test(rawRoleType)
        ? item.archetype_key
        : rawRoleType
    ) || item.archetype_key || item.profession || item.entity_type || ''
    const state = { ...(item.state_vector || {}), ...(item.business_state || {}) }
    const selectedScore = normalizeScore(
      state[scoreKey] ?? item[scoreKey] ?? state.vulnerability_score ?? item.focus_score ?? item.exposure_score ?? 0
    )
    const displayName = resolveActorDisplayName(
      item.name,
      runtimeItem?.agent_name,
      configured.name,
      configured.agent_name,
      item.username,
      `代理体 ${idx + 1}`
    )
    const lifecycleStatus = item.runtime_lifecycle?.lifecycle_status || item.lifecycle_status || 'active'
    const rawRepresentation = item.representation_level || (item.is_aggregate ? 'region_aggregate' : 'institution')
    const representation = item.archetype_key === 'ecological_receptor' && rawRepresentation === 'institution'
      ? 'group_representative'
      : rawRepresentation
    const capabilityLabels = uniqueList([
      ...(item.capabilities || []),
      ...(item.capability_keys || [])
    ].map(value => safeRuntimeCopy(translateDisplayToken(value, ''), '')).filter(Boolean))
    const resourceRows = Object.entries(item.resource_budget || {}).map(([key, value]) => {
      const label = safeRuntimeCopy(translateDisplayToken(key, ''), '相对资源')
      return `${label} ${Math.round(Number(value) || 0)}`
    })
    const createdRound = Number(item.created_round ?? item.runtime_lifecycle?.created_round ?? 0) || 0
    const isRuntimeGenerated = createdRound > 0 || /^runtime_/.test(String(item.generation_mode || ''))
    const summary = isRuntimeGenerated
      ? `${displayName}在 R${createdRound} 由运行证据建立，负责${capabilityLabels.slice(0, 3).join('、') || '专项响应'}。${safeRuntimeCopy(item.generation_reason, '')}`
      : safeRuntimeCopy(item.bio || item.persona, `${displayName} 正在根据环境暴露和周边主体行动调整策略。`)
    return {
      id: rawId,
      name: displayName,
      summary,
      provenance: item.provenance || item.profile_provenance || '',
      groundingReason: safeRuntimeCopy(item.grounding_reason, ''),
      family: agentType,
      familyLabel: formatAgentTypeLabel(agentType),
      subtypeLabel: formatTokenLabel(roleType || 'agent', '代理体'),
      lifecycleStatusLabel: formatTokenLabel(lifecycleStatus, '活跃'),
      representationLabel: formatTokenLabel(representation, item.is_aggregate ? '区域聚合' : '机构主体'),
      regionLabel: item.home_region_id || item.primary_region || item.region || '',
      subregionLabel: item.home_subregion_id || item.subregion_id || item.subregion || '',
      selectedScore,
      exposure_score: normalizeScore(state.exposure_score ?? item.exposure_score ?? 0),
      panic_level: normalizeScore(state.panic_level ?? item.panic_level ?? 0),
      public_trust: normalizeScore(state.public_trust ?? item.public_trust ?? 0),
      vulnerability_score: normalizeScore(state.vulnerability_score ?? item.vulnerability_score ?? 0),
      exposure_pressure: normalizeScore(state.exposure_pressure ?? item.exposure_pressure ?? item.exposure_score ?? 0),
      detection_visibility: normalizeScore(state.detection_visibility ?? item.detection_visibility ?? 0),
      testing_turnaround: normalizeScore(state.testing_turnaround ?? item.testing_turnaround ?? 0),
      healthcare_load: normalizeScore(state.healthcare_load ?? item.healthcare_load ?? 0),
      mobility_intensity: normalizeScore(state.mobility_intensity ?? item.mobility_intensity ?? 0),
      supply_sufficiency: normalizeScore(state.supply_sufficiency ?? item.supply_sufficiency ?? 0),
      community_support: normalizeScore(state.community_support ?? item.community_support ?? 0),
      capabilityLabels,
      resourceSummary: resourceRows.slice(0, 2).join(' · '),
      motivations: uniqueList([
        ...(item.goals || []),
        ...(item.motivation_stack || []),
        ...(item.action_space || [])
      ]).slice(0, 4).map(entry => safeRuntimeCopy(translateDisplayToken(entry, ''), '')).filter(Boolean)
    }
  })
}

function canonicalRuntimeAgentFamily(item = {}) {
  const archetypeFamilies = {
    local_government: 'governance',
    industry_regulator: 'governance',
    critical_facility_operator: 'infrastructure',
    healthcare_provider: 'organization',
    environmental_monitoring: 'organization',
    emergency_response: 'organization',
    transport_operator: 'infrastructure',
    affected_population: 'human',
    livelihood_group: 'human',
    community_organization: 'organization',
    supply_logistics: 'organization',
    media_information: 'organization',
    ecological_receptor: 'ecology',
    environmental_carrier: 'ecology'
  }
  const archetypeFamily = archetypeFamilies[String(item?.archetype_key || '').toLowerCase()]
  return archetypeFamily || String(item?.agent_type || item?.node_family || item?.family || 'human').toLowerCase()
}

function normalizeAgentActionRows(source) {
  const raw = source?.action_records || source?.agent_action_decisions || source?.interactions?.action_records || []
  if (!Array.isArray(raw)) return []
  return raw.map((item, index) => {
    const validation = item?.selected_validation || {}
    const accepted = validation.accepted !== false
    const actionKey = item?.selected_action_key || validation.action_key || 'wait'
    return {
      id: String(item?.action_decision_id || item?.id || `${item?.round || 0}-${item?.agent_id ?? index}-${index}`),
      agentId: item?.agent_id ?? index,
      round: Number(item?.round ?? item?.round_number ?? 0) || 0,
      actionLabel: safeRuntimeCopy(
        item?.selected_action_label_zh || validation.action_label_zh || translateDisplayToken(actionKey, ''),
        '保持待命'
      ),
      status: accepted ? 'executed' : 'blocked',
      statusLabel: accepted ? '已通过执行校验' : '执行校验未通过',
      reasons: uniqueList(validation.reasons_zh || validation.reasons || [])
        .map(value => safeRuntimeCopy(value, ''))
        .filter(Boolean)
    }
  })
}

function normalizeRelationshipStateRows(source, agentNames) {
  const raw = source?.relationship_states || source?.interactions?.relationship_states || []
  if (!Array.isArray(raw)) return []
  return raw.map((item, index) => {
    const sourceId = item?.source_agent_id
    const targetId = item?.target_agent_id
    const trust = Math.max(0, Math.min(1, Number(item?.trust) || 0))
    const dependency = Math.max(0, Math.min(1, Number(item?.dependency) || 0))
    const coordination = Math.max(0, Math.min(1, Number(item?.coordination) || 0))
    const tension = Math.max(0, Math.min(1, Number(item?.tension) || 0))
    const status = String(item?.status || 'active')
    return {
      id: String(item?.relationship_state_id || item?.relationship_contract_id || `relationship-${index}`),
      sourceName: agentNames.get(String(sourceId)) || `代理体 ${Number(sourceId) + 1 || index + 1}`,
      targetName: agentNames.get(String(targetId)) || `代理体 ${Number(targetId) + 1 || index + 2}`,
      typeLabel: formatTokenLabel(item?.relationship_type || 'interaction', '互动关系'),
      status,
      statusLabel: formatTokenLabel(status, '活跃'),
      trust,
      dependency,
      coordination,
      tension,
      trustLabel: formatPercent(trust),
      dependencyLabel: formatPercent(dependency),
      coordinationLabel: formatPercent(coordination),
      tensionLabel: formatPercent(tension),
      lastUpdatedRound: Number(item?.last_updated_round || 0)
    }
  })
}

function normalizeRelationshipEventRows(source, agentNames) {
  const raw = source?.relationship_events || source?.interactions?.relationship_events || []
  if (!Array.isArray(raw)) return []
  return raw.map((item, index) => {
    const sourceName = agentNames.get(String(item?.source_agent_id)) || '相关代理体'
    const targetName = agentNames.get(String(item?.target_agent_id)) || '相关代理体'
    const round = Number(item?.round_number ?? item?.round ?? 0) || 0
    const summary = safeRuntimeCopy(
      item?.summary_zh || item?.summary,
      `${sourceName} 与 ${targetName} 的关系状态已更新。`
    )
    return {
      id: String(item?.relationship_event_id || item?.event_id || `relationship-event-${round}-${index}`),
      round,
      effectiveRound: round,
      typeLabel: formatTokenLabel(item?.event_type || 'relationship_updated', '关系更新'),
      summary
    }
  })
}

function normalizeAgentEmergenceRows(source) {
  const snapshotEvents = [
    ...(Array.isArray(source?.agent_emergence?.events) ? source.agent_emergence.events : []),
    ...(Array.isArray(source?.agent_emergence?.activation_events) ? source.agent_emergence.activation_events : [])
  ]
  const raw = snapshotEvents.length > 0
    ? snapshotEvents
    : (Array.isArray(source?.agent_emergence_events) ? source.agent_emergence_events : [])
  return raw.map((item, index) => {
    const round = Number(item?.round ?? item?.round_number ?? 0) || 0
    return {
      id: String(item?.event_id || `agent-emergence-${round}-${index}`),
      round,
      effectiveRound: Number(item?.effective_round ?? round) || round,
      typeLabel: formatTokenLabel(item?.event_type || 'agent_created', '代理体变化'),
      summary: safeRuntimeCopy(item?.summary || item?.summary_zh, '运行证据触发了代理体生命周期变化。')
        .replace(/能力响应单元/g, '专业响应单元')
    }
  })
}

function normalizePolicyExecutionRows(source, agentNames) {
  const raw = source?.policy_execution?.execution_records || source?.policy_execution_events || []
  if (!Array.isArray(raw)) return []
  return raw.map((item, index) => {
    const round = Number(item?.round_number ?? item?.round ?? 0) || 0
    const status = String(item?.execution_status || 'blocked')
    const executorNames = uniqueList(item?.executor_agent_ids || [])
      .map(id => agentNames.get(String(id)) || '')
      .filter(Boolean)
    const targets = uniqueList(item?.target_region_ids || [])
      .map(id => resolveRegionName(id))
      .filter(Boolean)
    return {
      id: String(item?.policy_execution_id || `${item?.policy_id || 'policy'}-${round}-${index}`),
      round,
      status,
      statusLabel: formatTokenLabel(status, status === 'executed' ? '已执行' : '执行受阻'),
      label: safeRuntimeCopy(item?.policy_label_zh, '政策措施'),
      summary: safeRuntimeCopy(item?.summary_zh, status === 'executed' ? '政策措施已在本轮执行。' : '政策措施本轮未能生效。'),
      executorLabel: executorNames.length > 0 ? `执行者：${executorNames.join('、')}` : '执行者待补齐',
      targetLabel: targets.length > 0 ? `作用区域：${targets.join('、')}` : '作用范围待核验'
    }
  })
}

function formatActorDisplayName(value, fallback = '代理体') {
  const raw = String(value || '').trim()
  if (!raw) return fallback
  if (/^agent[_-]?\d*$/i.test(raw)) return fallback
  return safeRuntimeCopy(raw
    .replace(/[_-]\d+$/, '')
    .replace(/_+/g, '·'), fallback)
}

function resolveActorDisplayName(...values) {
  const fallback = String(values.at(-1) || '代理体')
  const selected = values.slice(0, -1).find(value => {
    const raw = String(value || '').trim()
    return raw && !/^(?:未命名代理体|未知代理体|Agent(?:[_\s#-]*\d+)?)$/i.test(raw)
  })
  return formatActorDisplayName(
    String(selected || '').replace(/能力响应单元/g, '专业响应单元'),
    fallback
  )
}

function formatAgentTypeLabel(value) {
  const normalized = String(value || '')
    .toLowerCase()
    .replace(/[_\s-]+/g, '')

  const map = {
    human: '个体',
    humanactor: '个体',
    residentgroup: '个体',
    organization: '组织',
    organizationactor: '组织',
    governance: '治理',
    governmentactor: '治理',
    governanceactor: '治理',
    ecology: '生态',
    ecologicalreceptor: '生态',
    fishstock: '生态',
    carrier: '环境载体',
    environmentalcarrier: '环境载体',
    coastalcurrent: '环境载体',
    infrastructure: '基础设施'
  }
  return map[normalized] || formatTokenLabel(value, '代理体')
}

function normalizeAgentInteractions(source) {
  const raw =
    source?.agent_interactions ||
    source?.interactions?.agent_interactions ||
    source?.envfish?.agent_interactions ||
    source?.latest_round_snapshot?.interactions?.agent_interactions ||
    source?.latest_snapshot?.interactions?.agent_interactions ||
    []

  if (!Array.isArray(raw)) return []

  return raw.map((item, idx) => {
    // 清洗叙述句里嵌入的内部渠道 token（如 governance_hierarchy → 治理层级）
    const rawChannel = String(item.channel || item.interaction_channel || '').trim()
    const channelLabel = safeRuntimeCopy(translateDisplayToken(rawChannel || 'social', ''), '社会')
    const cleanText = (text) => {
      const s = String(text || '')
      return rawChannel ? s.split(rawChannel).join(channelLabel) : s
    }
    return {
      id: item.id || `${item.round || item.round_num || idx}-${idx}`,
      round: item.round || item.round_num || idx + 1,
      channel: channelLabel,
      sourceAgentId: item.source_agent_id ?? item.agent_id ?? '',
      targetAgentId: item.target_agent_id ?? '',
      sourceName: resolveActorDisplayName(item.source_agent_name, item.source_name, item.agent_name, `代理体 ${idx + 1}`),
      targetName: resolveActorDisplayName(item.target_agent_name, item.target_name, ''),
      sourceRegion: formatInteractionRegion(item.source_region_name || item.source_region || item.region),
      targetRegion: formatInteractionRegion(item.target_region_name || item.target_region),
      actionType: safeRuntimeCopy(translateDisplayToken(item.action_type || item.type || '', ''), ''),
      actionLabel: safeRuntimeCopy(translateDisplayToken(item.action_type || item.type || 'interaction', ''), '交互'),
      rationale: safeRuntimeCopy(cleanText(item.rationale || item.description || item.note), '代理体互动'),
      targetDeltaLabel: formatDeltaLabel(item.delta || item.target_delta || {}),
      summary: safeRuntimeCopy(cleanText(item.summary || item.description || item.rationale || item.note), '代理体互动')
    }
  })
}

function normalizeInterventionRows(raw, defaultStatus = 'configured') {
  if (!Array.isArray(raw)) return []

  return raw.map((item, idx) => {
    const entry = item && typeof item === 'object' ? item : {}
    const variable = entry.variable && typeof entry.variable === 'object' ? entry.variable : entry
    const name = safeRuntimeCopy(variable.name || variable.title || entry.name || entry.title, `干预变量 ${idx + 1}`)
    const type = String(variable.type || entry.type || 'variable')
    const mode = String(variable.policy_mode || entry.policy_mode || '')
    const startRound = Number(variable.start_round ?? entry.start_round ?? entry.round ?? 0) || 0
    const duration = Math.max(1, Number(variable.duration_rounds ?? entry.duration_rounds ?? 1) || 1)
    const intensity = normalizeScore(
      variable.intensity_0_100 ??
      variable.intensity ??
      entry.intensity_0_100 ??
      entry.intensity ??
      0
    )
    const targets = uniqueList([
      ...(Array.isArray(variable.target_regions) ? variable.target_regions : []),
      ...(Array.isArray(entry.target_regions) ? entry.target_regions : [])
    ]).map(item => safeRuntimeCopy(resolveRegionName(item), '')).filter(Boolean)
    const status = String(entry.status || variable.status || defaultStatus)
    const sourceOrigin = String(
      variable.source_origin || variable.sourceOrigin || entry.source_origin || entry.sourceOrigin || ''
    ).toLowerCase()
    const isStableContext = sourceOrigin === 'stable_context' || variable.is_stable_context === true || entry.is_stable_context === true
    const summary = safeRuntimeCopy(
      variable.description || entry.message,
      `${formatVariableTypeLabel(type)}作用于${targets.length > 0 ? targets.join(' · ') : '全域'}，持续 ${duration} 轮。`
    )

    return {
      id: String(entry.timestamp || entry.id || variable.variable_id || `${name}-${idx}`),
      key: `${name}-${status}-${startRound}-${duration}-${intensity}-${targets.join('|')}-${mode}`,
      name,
      type,
      mode,
      status,
      statusLabel: formatStatusLabel(status),
      sourceOrigin,
      kindLabel: isStableContext ? '稳态' : '扰动',
      kindClass: isStableContext ? 'stable' : 'perturbation',
      round: Number(entry.round || startRound || 0),
      startRound,
      duration,
      intensity,
      targets,
      summary
    }
  })
}

function sortByRoundDesc(a, b) {
  const roundDelta = Number(b.round || 0) - Number(a.round || 0)
  if (roundDelta !== 0) return roundDelta
  return String(b.id || '').localeCompare(String(a.id || ''))
}

function mergeRuntimeRows(...lists) {
  const rows = new Map()
  lists.flat().forEach((item, index) => {
    if (!item) return
    const key = String(item.id || `${item.round || 0}-${item.typeLabel || 'event'}-${index}`)
    rows.set(key, item)
  })
  return [...rows.values()]
}

function relationStatusPriority(status) {
  if (status === 'active') return 3
  if (status === 'new') return 2
  if (status === 'steady') return 1
  return 0
}

function sortInterventionRows(a, b) {
  const roundDelta = Number(b.round || b.startRound || 0) - Number(a.round || a.startRound || 0)
  if (roundDelta !== 0) return roundDelta
  return String(b.id || '').localeCompare(String(a.id || ''))
}

function dedupeInterventionRows(rows) {
  const seen = new Set()
  return (rows || []).filter(item => {
    const key = item?.key || item?.id
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function formatLandUseLabel(value) {
  return formatLandUseLabelZh(value)
}

function formatDistanceLabel(value) {
  return formatDistanceLabelZh(value)
}

function formatDeltaLabel(delta) {
  if (!delta || typeof delta !== 'object') return ''
  const entries = Object.entries(delta).filter(([, value]) => Number(value) !== 0)
  if (entries.length === 0) return ''
  const [key, value] = entries[0]
  return `${safeRuntimeCopy(translateDisplayToken(key, ''), '状态指标')} ${Number(value).toFixed(1)}`
}

function normalizeEvents(source) {
  const raw =
    source?.spread_events ||
    source?.events ||
    source?.event_log ||
    source?.actions ||
    source?.all_actions ||
    []

  if (!Array.isArray(raw)) return []

  return raw.map((event, idx) => ({
    id: event.id || `${event.round || event.round_num || idx}-${idx}`,
    round: event.round || event.round_num || event.step || idx + 1,
    title: safeRuntimeCopy(event.title || event.event_name || event.label || event.action_type, '扩散事件'),
    label: safeRuntimeCopy(event.label, ''),
    event_type: safeRuntimeCopy(event.event_type || event.type || event.action_type, '状态变化'),
    source: safeRuntimeCopy(resolveRegionName(event.source || event.source_region || event.from), ''),
    target: safeRuntimeCopy(resolveRegionName(event.target || event.target_region || event.to), ''),
    summary: safeRuntimeCopy(event.summary || event.description || event.text || event.rationale || event.message, '系统记录到一次状态变化。'),
    rationale: safeRuntimeCopy(event.rationale || event.reason, ''),
    intensity: event.intensity ?? event.transfer_intensity ?? event.score ?? undefined,
    confidence: event.confidence ?? event.probability ?? undefined
  }))
}

function applyPreset(type) {
  const presets = {
    disaster: {
      type: 'disaster',
      name: '污染激增',
      description: '环境载体出现高强度污染输入，检查扩散链条和首次跨界触发点。',
      target_regions_text: '沿海区,近岸海域',
      target_nodes_text: '海流,鱼类,渔民',
      start_round: currentRoundNumber.value,
      duration_rounds: 4,
      intensity: 85,
      policy_mode: 'restrict'
    },
    policy: {
      type: 'policy',
      name: '强制撤离',
      description: '对高暴露区域实施强制撤离，观察信任、顺从和次生摩擦。',
      target_regions_text: '居民区,高暴露区',
      target_nodes_text: '居民,地方官员,交通网',
      start_round: currentRoundNumber.value,
      duration_rounds: 3,
      intensity: 70,
      policy_mode: 'relocate'
    },
    monitor: {
      type: 'policy',
      name: '监测增强',
      description: '提高检测频率和信息公开，观察辟谣和预警传播效果。',
      target_regions_text: '全域',
      target_nodes_text: '环保局,媒体,医院',
      start_round: currentRoundNumber.value,
      duration_rounds: 2,
      intensity: 45,
      policy_mode: 'monitor'
    }
  }

  const preset = presets[type]
  if (!preset) return
  injection.value = { ...preset }
}

function clearInjection() {
  injection.value = createInjection()
}

const INTERNAL_VARIABLE_NAMES = new Set(['disaster_injection', 'policy_injection'])
let injectionRequestIdentity = { fingerprint: '', key: '' }

function resolveInjectionDisplayName(variable) {
  const rawName = String(variable?.name || '').trim()
  if (rawName && !INTERNAL_VARIABLE_NAMES.has(rawName)) return rawName
  const description = String(variable?.description || '').trim()
  if (description) return description.length > 24 ? `${description.slice(0, 24)}...` : description
  return variable?.type === 'policy' ? '政策变量' : '灾害变量'
}

async function handleInject() {
  if (!canInject.value) return

  isInjecting.value = true
  interventionMessage.value = ''
  try {
    const startRoundValue = injection.value.start_round
    const payload = {
      simulation_id: props.simulationId,
      type: injection.value.type,
      name: resolveInjectionDisplayName(injection.value),
      description: injection.value.description || '',
      target_text: [injection.value.target_regions_text, injection.value.target_nodes_text]
        .map(item => String(item || '').trim())
        .filter(Boolean)
        .join('；'),
      start_round: startRoundValue === '' || startRoundValue == null
        ? currentRoundNumber.value + 1
        : Math.max(0, Number(startRoundValue)),
      duration_rounds: Math.max(1, Number(injection.value.duration_rounds) || 1),
      intensity: normalizeScore(injection.value.intensity),
      policy_mode: injection.value.type === 'policy' ? injection.value.policy_mode : 'restrict'
    }
    const fingerprint = JSON.stringify(payload)
    if (injectionRequestIdentity.fingerprint !== fingerprint) {
      injectionRequestIdentity = { fingerprint, key: createInjectionRequestKey() }
    }
    payload.idempotency_key = injectionRequestIdentity.key

    const res = await injectSimulationVariable(payload)
    if (res.success) {
      const normalized = res.data?.normalized_intervention || payload
      const summary = `${normalized.name} @ R${normalized.start_round} (${normalized.type}, ${normalized.intensity_0_100 ?? normalized.intensity})`
      const localEntry = normalizeInterventionRows([
        {
          round: currentRoundNumber.value,
          status: 'accepted',
          variable: {
            name: normalized.name,
            type: normalized.type,
            description: normalized.description,
            target_regions: normalized.target_regions || [],
            target_nodes: normalized.target_nodes || [],
            start_round: normalized.start_round,
            duration_rounds: normalized.duration_rounds,
            intensity: normalized.intensity_0_100 ?? normalized.intensity,
            policy_mode: normalized.policy_mode
          }
        }
      ], 'accepted')[0]

      if (localEntry) {
        injectionHistory.value.unshift(localEntry)
      }
      interventionMessage.value = ''
      addLog(`✓ 中途变量已注入: ${summary}`)
      await refreshDetail()
    } else {
      interventionMessage.value = '干预内容已保留，可以重新应用。'
      addLog(`✗ 注入失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    interventionMessage.value = '干预内容已保留，可以重新应用。'
    addLog(`✗ 注入异常: ${err.message}`)
  } finally {
    isInjecting.value = false
  }
}

async function startRun() {
  if (!props.simulationId || isStarting.value || isReplayPlayback.value) return

  isStarting.value = true
  emit('update-status', 'processing')
  addLog('正在启动 Kaleido 半定量推演...')

  try {
    const res = await startSimulation({
      simulation_id: props.simulationId,
      engine_mode: 'envfish',
      platform: 'envfish',
      scenario_mode: currentScenarioMode.value,
      diffusion_template: currentTemplate.value,
      max_rounds: props.maxRounds || undefined,
      enable_graph_memory_update: true,
      force: true
    })

    if (res.success && res.data) {
      runStatus.value = res.data
      addLog('✓ Kaleido 推演引擎已启动')
      addLog(`  ├─ PID: ${res.data.process_pid || '-'}`)
      addLog(`  └─ 模式: ${currentScenarioMode.value} / ${currentTemplate.value}`)
      startPolling()
      await refreshStatus()
      await refreshDetail()
    } else {
      emit('update-status', 'error')
      addLog(`✗ 启动失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    emit('update-status', 'error')
    addLog(`✗ 启动异常: ${err.message}`)
  } finally {
    isStarting.value = false
  }
}

async function handleStop() {
  if (!props.simulationId || isStopping.value) return
  if (isReplayPlayback.value) {
    stopAnimationPlayback({ userInitiated: true })
    addLog('冻结演示回放已暂停')
    return
  }

  isStopping.value = true
  try {
    const res = await stopSimulation({ simulation_id: props.simulationId })
    if (res.success) {
      addLog('✓ 推演已停止')
      emit('update-status', 'completed')
      stopPolling()
      await refreshStatus()
      await refreshDetail()
    } else {
      addLog(`停止失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    addLog(`停止异常: ${err.message}`)
  } finally {
    isStopping.value = false
  }
}

async function handleNextStep() {
  if (!props.simulationId) return

  const reportId = existingReportId.value
  if (reportId) {
    addLog(`打开已有报告: ${reportId}`)
    router.push({ name: 'Analysis', params: { reportId }, query: { ...route.query, step: '4' } })
    return
  }

  if (isGeneratingReport.value) {
    addLog('报告生成请求已发送，请稍候...')
    return
  }

  isGeneratingReport.value = true
  addLog('正在生成 Kaleido 报告...')

  try {
    const graphId =
      simulationSnapshot.value?.graph_id ||
      configSnapshot.value?.graph_id ||
      route.query.graph_id ||
      ''
    const simulationRequirement =
      configSnapshot.value?.simulation_requirement ||
      simulationSnapshot.value?.simulation_requirement ||
      route.query.simulation_requirement ||
      ''

    const res = await generateReportAsync({
      simulation_id: props.simulationId,
      graph_id: graphId,
      simulation_requirement: simulationRequirement,
      force_regenerate: !isReplayPlayback.value
    })

    if (res.success && res.data) {
      const reportId = res.data.report_id
      addLog(`✓ 报告生成任务已启动: ${reportId}`)
      router.push({ name: 'Analysis', params: { reportId }, query: { ...route.query, step: '4' } })
    } else {
      addLog(`✗ 报告生成失败: ${res.error || '未知错误'}`)
      isGeneratingReport.value = false
    }
  } catch (err) {
    addLog(`✗ 报告生成异常: ${err.message}`)
    isGeneratingReport.value = false
  }
}

function handleGoBack() {
  emit('go-back')
}

function seekToRound(round) {
  const targetRound = Number(round ?? 0)
  if (targetRound === 0) {
    stopAnimationPlayback({ userInitiated: true })
    playheadMs.value = 0
    return
  }
  const marker = (playbackPlan.value?.rounds || []).find((item) => Number(item?.round) === targetRound)
  if (!marker) return
  stopAnimationPlayback({ userInitiated: true })
  playheadMs.value = Math.max(0, Math.min(playbackDurationMs.value, Number(marker.start_ms || 0)))
}

function seekToStoryChapter(chapter) {
  seekToRound(chapter?.round_start ?? 0)
}

function handleInterventionAction() {
  if (!isCuratedShowcase.value) {
    isInterventionPanelOpen.value = true
    return
  }
  const current = Number(currentRoundNumber.value || 0)
  const nearest = [...policyInterventions.value].sort((left, right) => {
    const leftStart = Number(left?.round_start || 0)
    const rightStart = Number(right?.round_start || 0)
    const leftDistance = current >= leftStart && current <= Number(left?.round_end || leftStart) ? 0 : Math.abs(leftStart - current)
    const rightDistance = current >= rightStart && current <= Number(right?.round_end || rightStart) ? 0 : Math.abs(rightStart - current)
    return leftDistance - rightDistance
  })[0]
  const nearestStart = Number(nearest?.round_start ?? current)
  const nearestEnd = Number(nearest?.round_end ?? nearestStart)
  const focusRound = nearest && current >= nearestStart && current <= nearestEnd
    ? current
    : nearestStart
  if (nearest) seekToRound(focusRound)
  const reportId = existingReportId.value
  if (!reportId) return
  router.push({
    name: 'Analysis',
    params: { reportId },
    query: {
      ...route.query,
      step: '4',
      tab: 'intervention',
      round: String(focusRound),
      ...(nearest?.id ? { policy_id: nearest.id } : {})
    }
  })
}

async function refreshSimulationContext() {
  if (!props.simulationId) return

  try {
    const [simulationRes, configRes] = await Promise.allSettled([
      getSimulation(props.simulationId),
      getSimulationConfig(props.simulationId)
    ])

    if (simulationRes.status === 'fulfilled' && simulationRes.value?.success) {
      simulationSnapshot.value = simulationRes.value.data || null
      currentScenarioMode.value = simulationSnapshot.value?.scenario_mode || currentScenarioMode.value
      currentTemplate.value = simulationSnapshot.value?.diffusion_template || currentTemplate.value
    }

    if (configRes.status === 'fulfilled' && configRes.value?.success && configRes.value.data) {
      configSnapshot.value = configRes.value.data
      if (configRes.value.data.scenario_mode) currentScenarioMode.value = configRes.value.data.scenario_mode
      if (configRes.value.data.diffusion_template) currentTemplate.value = configRes.value.data.diffusion_template
      if (configRes.value.data.time_config?.minutes_per_round) {
        addLog(`时间粒度: ${configRes.value.data.time_config.minutes_per_round} min / round`)
      }
    }
  } catch (err) {
    addLog(`加载推演上下文失败: ${err.message}`)
  }
}

async function refreshStatus() {
  if (!props.simulationId || statusRefreshInFlight) return

  statusRefreshInFlight = true
  try {
    const res = await getRunStatus(props.simulationId)
    if (res.success && res.data) {
      runStatus.value = res.data
      const statusRound = Number(runStatus.value.current_round ?? runStatus.value.current_round_num ?? 0)
      if (statusRound > 0) {
        syncRoundIndexToRound(statusRound)
      }
      if (res.data.runner_status === 'completed' || res.data.runner_status === 'stopped') {
        emit('update-status', 'completed')
        stopPolling()
      } else if (res.data.runner_status === 'failed') {
        emit('update-status', 'error')
        stopPolling()
      }
    }
  } catch (err) {
    console.warn('run status failed', err)
  } finally {
    statusRefreshInFlight = false
  }
}

async function refreshDetail() {
  if (!props.simulationId || detailRefreshInFlight) return

  detailRefreshInFlight = true
  try {
    const res = await getRunStatusDetail(props.simulationId, {
      include_actions: 0,
      include_envfish_raw: 0
    })
    if (res.success && res.data) {
      runDetail.value = res.data
      if (runDetail.value.message && runDetail.value.message !== lastRunMessage.value) {
        lastRunMessage.value = runDetail.value.message
        addLog(runDetail.value.message)
      }

      if (roundSnapshots.value.length > 0) {
        const detailRound = Number(
          runDetail.value.current_round ||
          runDetail.value.latest_round_snapshot?.round ||
          runDetail.value.latest_snapshot?.round ||
          0
        )
        if (detailRound > 0) {
          syncRoundIndexToRound(detailRound)
        }
      }
    }
  } catch (err) {
    console.warn('run detail failed', err)
  } finally {
    detailRefreshInFlight = false
  }
}

function startPolling() {
  stopPolling()
  statusTimer = setInterval(refreshStatus, 2000)
  detailTimer = setInterval(refreshDetail, 3000)
}

function stopPolling() {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
  if (detailTimer) {
    clearInterval(detailTimer)
    detailTimer = null
  }
}

function stopAnimationPlayback({ userInitiated = false } = {}) {
  if (frameAnimationRaf) {
    cancelAnimationFrame(frameAnimationRaf)
    frameAnimationRaf = null
  }
  lastPlaybackRafAt = null
  isPlayingAnimation.value = false
  if (userInitiated) hasUserPausedPlayback.value = true
}

function queueContinuousPlaybackTick() {
  if (!isPlayingAnimation.value || playbackFrames.value.length <= 1 || frameAnimationRaf) return
  const tick = (now) => {
    if (!isPlayingAnimation.value) {
      frameAnimationRaf = null
      lastPlaybackRafAt = null
      return
    }
    if (lastPlaybackRafAt === null) lastPlaybackRafAt = now
    const wallDelta = Math.max(0, Math.min(64, now - lastPlaybackRafAt))
    lastPlaybackRafAt = now
    playheadMs.value = advanceContinuousPlayhead(
      playheadMs.value,
      wallDelta,
      playbackRate.value,
      playbackDurationMs.value,
    )
    if (playheadMs.value >= playbackDurationMs.value) {
      frameAnimationRaf = null
      lastPlaybackRafAt = null
      isPlayingAnimation.value = false
      return
    }
    frameAnimationRaf = requestAnimationFrame(tick)
  }
  frameAnimationRaf = requestAnimationFrame(tick)
}

function toggleAnimationPlayback() {
  if (isPlayingAnimation.value) {
    stopAnimationPlayback({ userInitiated: true })
    return
  }
  if (playbackFrames.value.length <= 1) return
  if (playheadMs.value >= playbackDurationMs.value - 1) playheadMs.value = 0
  hasUserPausedPlayback.value = false
  isPlayingAnimation.value = true
  queueContinuousPlaybackTick()
}

function handlePlaybackScrub(event) {
  stopAnimationPlayback({ userInitiated: true })
  const requested = Number(event?.target?.value || 0)
  playheadMs.value = Math.max(0, Math.min(playbackDurationMs.value, requested))
}

function maybeAutoplayReplay() {
  if (!isReplayPlayback.value) return
  if (hasAutoStartedReplay.value || isPlayingAnimation.value || hasUserPausedPlayback.value) return
  if (playbackFrames.value.length <= 1) return
  hasAutoStartedReplay.value = true
  window.setTimeout(() => {
    if (
      !isReplayPlayback.value
      || isPlayingAnimation.value
      || hasUserPausedPlayback.value
      || playbackFrames.value.length <= 1
    ) return
    toggleAnimationPlayback()
  }, 320)
}

watch(
  () => props.initialScenarioMode,
  (value) => {
    if (value) currentScenarioMode.value = value
  }
)

watch(
  () => props.initialDiffusionTemplate,
  (value) => {
    if (value) currentTemplate.value = value
  }
)

watch(
  () => roundSnapshots.value.length,
  (value) => {
    if (value <= 0 || props.animationData?.frames?.length || hasUserPausedPlayback.value) return
    const lastRound = playbackPlan.value?.rounds?.[playbackPlan.value.rounds.length - 1]
    if (!lastRound) return
    playheadMs.value = Math.max(0, Math.min(playbackDurationMs.value, Number(lastRound.end_ms || 0) - 1))
  }
)

watch(
  () => props.animationData,
  (value, previousValue) => {
    if (!value?.frames?.length) return
    const previousFrameCount = Array.isArray(previousValue?.frames) ? previousValue.frames.length : 0
    const previousTimelineId = String(previousValue?.timeline?.timeline_id || '')
    const nextTimelineId = String(value?.timeline?.timeline_id || '')
    const timelineChanged = Boolean(
      previousTimelineId
      && nextTimelineId
      && previousTimelineId !== nextTimelineId
    )
    const previousPlan = previousFrameCount > 0 ? buildContinuousPlaybackPlan(previousValue) : null
    const previousDuration = Math.max(0, Number(previousPlan?.duration_ms || 0))
    const wasAtBufferedEnd = previousDuration > 0 && playheadMs.value >= previousDuration - 32

    if (timelineChanged) {
      stopAnimationPlayback()
      hasAutoStartedReplay.value = false
      hasUserPausedPlayback.value = false
      playheadMs.value = 0
    } else if (previousFrameCount === 0) {
      playheadMs.value = 0
    } else {
      playheadMs.value = Math.max(0, Math.min(playbackDurationMs.value, playheadMs.value))
    }

    if (
      !isReplayPlayback.value
      && !hasUserPausedPlayback.value
      && value.frames.length > 1
      && (previousFrameCount <= 1 || wasAtBufferedEnd || timelineChanged)
    ) {
      isPlayingAnimation.value = true
      queueContinuousPlaybackTick()
    }
    maybeAutoplayReplay()
  },
  { immediate: true }
)

watch(
  () => props.simulationId,
  () => {
    stopAnimationPlayback()
    hasAutoStartedReplay.value = false
    hasUserPausedPlayback.value = false
    playheadMs.value = 0
  }
)

watch(
  selectedAnimationFrame,
  (frame) => {
    if (props.animationData?.frames?.length) {
      emit('animation-frame-change', frame || null)
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
  selectedRiskObjectId,
  () => {
    revealSelectedRiskObject()
  },
  { flush: 'post' }
)

watch(
  [() => riskObjects.value.length, activeWorkspaceTab],
  async ([, tab]) => {
    if (tab !== 'risk') {
      riskSelectorOverflow.value = false
      return
    }
    await nextTick()
    syncRiskSelectorScrollState()
  },
  { flush: 'post' }
)

watch(
  [riskObjectHighlightPayload, activeWorkspaceTab],
  ([payload, tab]) => {
    emit('risk-object-focus', tab === 'risk'
      ? payload
      : { label: '', riskObjectId: '', nodeIds: [], nodeNames: [] })
  },
  { immediate: true, deep: true }
)

function handleGlobalKeydown(event) {
  if (event.key === 'Escape' && isInterventionPanelOpen.value) {
    isInterventionPanelOpen.value = false
  }
}

function handleStep3Resize() {
  syncRiskSelectorScrollState()
}

onMounted(async () => {
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('resize', handleStep3Resize)
  addLog('Kaleido Step3 初始化')
  await refreshSimulationContext()
  if (isReplayPlayback.value) {
    emit('update-status', 'completed')
    addLog('冻结演示案例已恢复，跳过推演启动，直接进入回放。')
    await refreshStatus()
    await refreshDetail()
    maybeAutoplayReplay()
    return
  }
  await refreshStatus()
  if (runStatus.value.runner_status === 'running') {
    startPolling()
    await refreshDetail()
    return
  }
  if (runStatus.value.runner_status === 'completed' || runStatus.value.runner_status === 'stopped') {
    emit('update-status', 'completed')
    await refreshDetail()
    return
  }
  await startRun()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('resize', handleStep3Resize)
  stopPolling()
  stopAnimationPlayback()
})
</script>

<style scoped>
.envfish-step {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(255, 191, 105, 0.18), transparent 30%),
    radial-gradient(circle at top right, rgba(28, 196, 135, 0.16), transparent 28%),
    linear-gradient(180deg, #fffaf4 0%, #ffffff 100%);
  color: #1e2333;
  container-type: inline-size;
}

.runtime-sticky {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 0 8px;
  background: rgba(255, 250, 244, 0.97);
  backdrop-filter: blur(18px);
}

.story-chapter-nav {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
}

.story-chapter-nav button {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid rgba(23, 48, 86, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  color: #596276;
  text-align: left;
  cursor: pointer;
}

.story-chapter-nav button span {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.story-chapter-nav button strong {
  overflow: hidden;
  color: #27344a;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.story-chapter-nav button.is-active {
  border-color: rgba(31, 106, 84, 0.36);
  background: rgba(31, 106, 84, 0.09);
  box-shadow: inset 0 -2px 0 #1f6a54;
}

@media (max-width: 900px) {
  .story-chapter-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.hero,
.workspace-shell,
.control-panel,
.panel,
.log-shell {
  border: 1px solid rgba(44, 44, 66, 0.08);
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(10px);
  box-shadow: 0 12px 32px rgba(17, 31, 59, 0.06);
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  border-radius: 18px;
}

.eyebrow {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.2em;
  color: #9a6a2f;
}

.hero h2 {
  margin: 5px 0 0;
  font-size: 22px;
  line-height: 1.1;
}

.hero p {
  margin: 0;
  max-width: 680px;
  color: #656779;
}

.hero-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.ghost-btn,
.primary-btn,
.preset-btn,
.secondary-btn,
.text-btn {
  border: none;
  border-radius: 14px;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 700;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.ghost-btn,
.secondary-btn,
.preset-btn {
  background: rgba(29, 39, 58, 0.06);
  color: #27344a;
}

.text-btn {
  padding-inline: 6px;
  background: transparent;
  color: #596276;
}

.intervention-trigger {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #173056;
  background: #eef4ff;
}

.control-count {
  display: inline-grid;
  min-width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 7px;
  background: #173056;
  color: #fff;
  font-size: 10px;
}

.primary-btn {
  background: linear-gradient(135deg, #0f3d63, #f08a24);
  color: #fff;
}

.ghost-btn:hover,
.secondary-btn:hover,
.primary-btn:hover,
.preset-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(31, 57, 98, 0.1);
}

.status-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(72px, 1fr));
  gap: 6px;
}

.status-card {
  min-width: 0;
  border-radius: 12px;
  padding: 9px 10px;
  background: #f7f8fa;
  border: 1px solid rgba(39, 56, 84, 0.06);
}

.status-card span,
.hint,
.panel-title-row span {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7d8393;
}

.status-card strong {
  display: block;
  margin-top: 4px;
  font-size: 14px;
  color: #183058;
}

.status-card.accent {
  background: #eef4ff;
}

.control-panel {
  border-radius: 24px;
  padding: 16px 18px;
}

.runtime-console {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(260px, 1.1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 10px 12px;
  border-radius: 18px;
}

.runtime-timeline {
  min-width: 0;
}

.runtime-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #5f687a;
  font-size: 11px;
}

.runtime-timeline-head strong {
  color: #173056;
  font-size: 12px;
}

.compact-range {
  display: block;
  width: 100%;
  margin: 7px 0 0;
}

.runtime-timeline p {
  margin: 4px 0 0;
  overflow: hidden;
  color: #7d8393;
  font-size: 11px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-controls,
.runtime-playback-buttons {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}

.runtime-controls {
  justify-content: flex-end;
}

.icon-control,
.play-control,
.latest-control {
  height: 36px;
  border: 1px solid rgba(23, 48, 86, 0.12);
  border-radius: 11px;
  background: #fff;
  color: #173056;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
}

.icon-control {
  width: 36px;
}

.play-control {
  min-width: 58px;
  padding: 0 11px;
  background: #173056;
  color: #fff;
}

.latest-control {
  padding: 0 10px;
  background: #fff;
  color: #173056;
}

.icon-control:disabled,
.play-control:disabled,
.latest-control:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.compact-selector {
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: #7d8393;
  font-size: 10px;
}

.compact-selector select {
  height: 36px;
  max-width: 126px;
  padding: 0 28px 0 9px;
  border: 1px solid rgba(23, 48, 86, 0.12);
  border-radius: 11px;
  background: #fff;
  color: #173056;
  font: inherit;
}

.speed-selector select {
  max-width: 92px;
}

.workspace-shell {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
  gap: 14px;
  padding: 14px;
  border-radius: 22px;
  overflow-y: auto;
  overflow-x: hidden;
}

.workspace-topbar {
  display: flex;
  flex-direction: column;
  gap: 18px;
  align-items: stretch;
}

.workspace-copy {
  max-width: 100%;
}

.workspace-copy h3 {
  margin: 10px 0 8px;
  font-size: 24px;
  line-height: 1.15;
  color: #173056;
}

.workspace-copy p {
  margin: 0;
  color: #656779;
  line-height: 1.6;
}

.workspace-eyebrow {
  color: #0f517d;
}

/* tab 从大卡片 → 安静的下划线文字 tab（不再占满一行抢视觉） */
.workspace-tabs {
  display: flex;
  flex-wrap: nowrap;
  gap: 22px;
  width: 100%;
  overflow-x: auto;
  padding: 0 4px;
  border-bottom: 0.5px solid rgba(29, 39, 58, 0.12);
  background: rgba(255, 250, 244, 0.98);
}

.workspace-tab {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  border: none;
  background: transparent;
  padding: 6px 2px 10px;
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  color: #8a93a6;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  transition: color 0.15s ease, border-color 0.15s ease;
  flex: 0 0 auto;
}

.workspace-tab:hover {
  color: #173056;
}

.workspace-tab.active {
  color: #173056;
  border-bottom-color: #173056;
}

.workspace-tab-label {
  font-size: 15px;
  font-weight: 600;
}

.workspace-tab-meta {
  font-size: 12px;
  color: #8a93a6;
}

.workspace-panel {
  flex: 0 0 auto;
  min-height: auto;
  overflow: visible;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.intervention-overlay {
  position: fixed;
  inset: 60px 0 0;
  z-index: 80;
  display: flex;
  justify-content: flex-end;
  background: rgba(18, 29, 46, 0.08);
}

.intervention-drawer {
  width: min(560px, 100%);
  height: 100%;
  overflow-y: auto;
  border-left: 1px solid rgba(23, 48, 86, 0.12);
  background: #fbfbf9;
  box-shadow: -22px 0 64px rgba(20, 33, 61, 0.16);
}

.intervention-drawer-head {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid rgba(23, 48, 86, 0.08);
  background: rgba(251, 251, 249, 0.96);
  backdrop-filter: blur(14px);
}

.intervention-drawer-head h2 {
  margin: 6px 0 0;
  color: #173056;
  font-size: 24px;
}

.intervention-drawer-head p {
  margin: 6px 0 0;
  color: #687185;
  font-size: 12px;
  line-height: 1.5;
}

.drawer-close {
  width: 34px;
  height: 34px;
  border: 1px solid rgba(23, 48, 86, 0.1);
  border-radius: 11px;
  background: #fff;
  color: #47536a;
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
}

.intervention-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 22px 28px;
}

.injection-panel,
.active-intervention-panel {
  padding: 16px;
  border: 1px solid rgba(23, 48, 86, 0.08);
  border-radius: 18px;
  background: #fff;
}

.intervention-message {
  margin: 10px 0 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #eef7f2;
  color: #1f5d45;
  font-size: 12px;
  line-height: 1.45;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-card {
  border-radius: 20px;
  padding: 14px 16px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.summary-card.accent {
  background: #eef4ff;
}

.summary-card span {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7d8393;
}

.summary-card strong {
  display: block;
  margin-top: 8px;
  font-size: 18px;
  color: #173056;
}

.summary-card p {
  margin: 8px 0 0;
  color: #5f6577;
  line-height: 1.5;
  font-size: 13px;
}

.overview-top-grid,
.overview-main-grid,
.inject-grid {
  display: grid;
  gap: 14px;
}

/* 单列纵向流：内容全宽铺开，不再用不等高的双列网格留白 */
.overview-top-grid {
  grid-template-columns: minmax(0, 1fr);
}

.overview-main-grid {
  grid-template-columns: minmax(0, 1fr);
  min-height: auto;
  flex: 0 0 auto;
}

.state-secondary-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr);
  gap: 14px;
}

.inject-grid {
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
  min-height: auto;
  flex: 0 0 auto;
}

.control-panel.embedded,
.pulse-panel,
.log-panel {
  min-height: 0;
}

.pulse-panel,
.log-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pulse-metric {
  border-radius: 18px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.pulse-metric-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  color: #183058;
}

.pulse-metric-head span {
  font-size: 12px;
  color: #677084;
}

.progress-track {
  margin-top: 12px;
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(19, 32, 51, 0.08);
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #f08a24, #113d7a);
}

.pulse-delta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.pulse-delta-card {
  border-radius: 16px;
  padding: 12px;
  background: rgba(248, 251, 255, 0.92);
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.pulse-delta-card span,
.pulse-relation-card span {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7d8393;
}

.pulse-delta-card strong {
  display: block;
  margin-top: 8px;
  color: #173056;
  font-size: 18px;
}

.pulse-relation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pulse-relation-card {
  border-radius: 16px;
  padding: 12px;
  border: 1px solid rgba(29, 39, 58, 0.08);
  background: #fff;
}

.pulse-relation-card.is-new {
  border-color: rgba(240, 138, 36, 0.28);
  background: rgba(255, 248, 235, 0.72);
}

.pulse-relation-card.is-active {
  border-color: rgba(191, 66, 48, 0.26);
  background: rgba(255, 244, 240, 0.76);
}

.pulse-relation-card strong {
  display: block;
  margin-top: 6px;
  color: #173056;
  font-size: 13px;
  line-height: 1.35;
}

.pulse-relation-card p {
  margin: 4px 0 0;
  color: #677084;
  font-size: 12px;
}

.spotlight-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.spotlight-card {
  border-radius: 18px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.spotlight-card span {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7d8393;
}

.spotlight-card strong {
  display: block;
  margin-top: 8px;
  color: #173056;
}

.spotlight-card p {
  margin: 8px 0 0;
  color: #5f6577;
  font-size: 13px;
  line-height: 1.5;
}

.risk-panel-shell {
  border-radius: 24px;
  padding: 16px 18px;
  border: 1px solid rgba(44, 44, 66, 0.08);
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(10px);
  box-shadow: 0 12px 32px rgba(17, 31, 59, 0.06);
}

.control-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.panel-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title-row h3 {
  margin: 0;
  font-size: 16px;
}

.mini-summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.mini-pill {
  border-radius: 16px;
  padding: 10px 12px;
  background: rgba(17, 31, 59, 0.05);
  min-width: 132px;
}

.mini-pill span {
  display: block;
  font-size: 11px;
  color: #7d8393;
}

.mini-pill strong {
  display: block;
  margin-top: 6px;
  color: #183058;
}

.slider-shell {
  margin-top: 14px;
}

.range {
  width: 100%;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #808699;
  margin-top: 8px;
}

.selector-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.selector {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.selector span {
  font-size: 12px;
  color: #4f5568;
}

.selector select,
.form-stack input,
.form-stack select,
.form-stack textarea {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(29, 39, 58, 0.12);
  background: #fff;
  color: #1e2333;
  padding: 10px 12px;
  font: inherit;
}

.playback-buttons {
  flex-direction: row;
  align-items: end;
  flex-wrap: wrap;
}

.mini-btn {
  border-radius: 14px;
  border: 1px solid rgba(29, 39, 58, 0.12);
  background: #1f5d45;
  color: #fff;
  padding: 10px 14px;
  font: inherit;
  font-weight: 800;
  cursor: pointer;
}

.mini-btn.ghost {
  background: #fff;
  color: #27344a;
}

.mini-btn:disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.multi-agent-panel {
  border-radius: 24px;
  padding: 16px 18px;
  border: 1px solid rgba(44, 44, 66, 0.08);
  background: rgba(255, 255, 255, 0.84);
  backdrop-filter: blur(10px);
  box-shadow: 0 12px 32px rgba(17, 31, 59, 0.06);
}

/* 简报式可折叠分节：标题行可点，其余按需展开 */
.briefing-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
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
.briefing-section.collapsed { min-height: 0 !important; }

.multi-agent-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.mini-panel {
  min-width: 0;
  min-height: 0;
  border-radius: 18px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.mini-panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.mini-panel-head h4 {
  margin: 0;
  font-size: 14px;
  color: #173056;
}

.subregion-list,
.agent-leaderboard,
.interaction-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.subregion-card,
.agent-rank-card,
.interaction-card {
  border-radius: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(29, 39, 58, 0.07);
}

.subregion-card-head,
.agent-rank-head,
.interaction-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.subregion-card-head strong,
.agent-rank-name strong,
.interaction-card strong {
  display: block;
  color: #173056;
}

.subregion-card-head > div > span,
.agent-rank-name span {
  display: block;
  margin-top: 4px;
  color: #7d8393;
  font-size: 12px;
}

.subregion-score,
.agent-rank-score,
.interaction-round {
  font-size: 13px;
  font-weight: 800;
  color: #113d7a;
}

.subregion-bar,
.agent-rank-strip {
  margin-top: 10px;
  height: 8px;
  border-radius: 999px;
  background: rgba(19, 32, 51, 0.08);
  overflow: hidden;
}

.subregion-bar-fill,
.agent-rank-strip-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #f08a24, #113d7a);
}

.subregion-meta,
.agent-rank-meta,
.interaction-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  font-size: 11px;
  color: #6f7588;
}

.subregion-meta span,
.agent-rank-meta span,
.interaction-meta span {
  padding: 5px 8px;
  border-radius: 999px;
  background: rgba(17, 31, 59, 0.05);
}

.agent-rank-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.agent-action-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  padding: 8px 0;
  border-top: 1px solid rgba(29, 39, 58, 0.07);
  border-bottom: 1px solid rgba(29, 39, 58, 0.07);
}

.agent-action-line strong {
  color: #173056;
  font-size: 12px;
}

.agent-action-line span {
  color: #6f7588;
  font-size: 10px;
  text-align: right;
}

.runtime-ledger-section {
  min-width: 0;
}

.policy-ledger-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(29, 39, 58, 0.09);
}

.runtime-ledger-list,
.relationship-state-list,
.runtime-event-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.runtime-ledger-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  padding: 11px 0;
  border-bottom: 1px solid rgba(29, 39, 58, 0.07);
}

.runtime-ledger-row:last-child {
  border-bottom: 0;
}

.runtime-ledger-row strong,
.runtime-event-row strong {
  color: #173056;
  font-size: 12px;
}

.runtime-ledger-row p,
.runtime-event-row p {
  margin: 4px 0 0;
  color: #5f6577;
  font-size: 11px;
  line-height: 1.5;
}

.runtime-ledger-round {
  display: inline-block;
  margin-right: 7px;
  color: #113d7a;
  font-size: 10px;
  font-weight: 800;
}

.runtime-ledger-meta {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  max-width: 44%;
}

.runtime-ledger-meta span {
  padding: 4px 7px;
  border-radius: 999px;
  background: rgba(17, 31, 59, 0.05);
  color: #6f7588;
  font-size: 10px;
}

.runtime-ledger-meta span.is-executed {
  background: rgba(31, 93, 69, 0.1);
  color: #1f5d45;
}

.runtime-ledger-meta span.is-blocked {
  background: rgba(191, 66, 48, 0.1);
  color: #a03a2f;
}

.relationship-runtime-panel {
  margin-bottom: 14px;
  padding: 16px 18px;
  border: 1px solid rgba(29, 39, 58, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.88);
}

.relationship-runtime-panel > .panel-title-row > div > p {
  margin: 4px 0 0;
  color: #6f7588;
  font-size: 11px;
  line-height: 1.5;
}

.relationship-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin-top: 14px;
  overflow: hidden;
  border: 1px solid rgba(29, 39, 58, 0.08);
  border-radius: 8px;
  background: rgba(29, 39, 58, 0.08);
}

.relationship-summary-grid > div {
  padding: 10px 12px;
  background: #fff;
}

.relationship-summary-grid span,
.relationship-summary-grid strong {
  display: block;
}

.relationship-summary-grid span {
  color: #7d8393;
  font-size: 10px;
}

.relationship-summary-grid strong {
  margin-top: 5px;
  color: #173056;
  font-size: 16px;
}

.relationship-runtime-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 16px;
}

.relationship-runtime-grid > section + section {
  padding-left: 18px;
  border-left: 1px solid rgba(29, 39, 58, 0.08);
}

.relationship-state-row {
  padding: 9px 0;
  border-bottom: 1px solid rgba(29, 39, 58, 0.07);
}

.relationship-state-row:last-child {
  border-bottom: 0;
}

.relationship-state-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.relationship-state-head strong {
  color: #173056;
  font-size: 12px;
  line-height: 1.4;
}

.relationship-state-head > span {
  color: #6f7588;
  font-size: 10px;
  text-align: right;
}

.relationship-state-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 7px;
}

.relationship-state-metrics span {
  color: #6f7588;
  font-size: 10px;
  white-space: nowrap;
}

.runtime-event-row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 8px;
  padding: 9px 0;
  border-bottom: 1px solid rgba(29, 39, 58, 0.07);
}

.runtime-event-row:last-child {
  border-bottom: 0;
}

.runtime-event-row small {
  display: block;
  margin-top: 4px;
  color: #7d8393;
  font-size: 10px;
}

.interaction-card p,
.subregion-card p,
.agent-rank-card p {
  margin: 8px 0 0;
  color: #5f6577;
  line-height: 1.5;
  font-size: 13px;
}

.interaction-channel {
  padding: 5px 9px;
  border-radius: 999px;
  background: rgba(17, 61, 122, 0.1);
  color: #113d7a;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.agent-rank-card {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.agent-rank-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(17, 31, 59, 0.08);
  border-color: rgba(17, 61, 122, 0.18);
}

.risk-panel-heading {
  margin-bottom: 10px;
}

.risk-selector-shell {
  display: block;
}

.risk-selector-shell.has-overflow-controls {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 30px;
  align-items: center;
  gap: 7px;
}

.risk-selector-nav {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  min-height: 30px;
  padding: 0;
  border: 1px solid rgba(31, 93, 69, 0.2);
  border-radius: 999px;
  background: var(--k-color-surface);
  color: var(--k-color-brand-700);
  font: inherit;
  font-size: 20px;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, opacity 160ms ease;
}

.risk-selector-nav:hover:not(:disabled) {
  border-color: var(--k-color-brand-600);
  background: var(--k-color-brand-050);
}

.risk-selector-nav:focus-visible {
  outline: 2px solid var(--k-color-brand-500);
  outline-offset: 2px;
}

.risk-selector-nav:disabled {
  cursor: default;
  opacity: 0.3;
}

.risk-selector-track {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(190px, 220px);
  gap: 8px;
  overflow-x: auto;
  padding: 2px;
  overscroll-behavior-inline: contain;
  scroll-snap-type: inline proximity;
  scrollbar-width: none;
}

.risk-selector-track::-webkit-scrollbar {
  display: none;
}

.risk-selector-option {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  min-height: 62px;
  padding: 9px 10px;
  overflow: hidden;
  border: 1px solid var(--k-color-border);
  border-radius: 12px;
  background: var(--k-color-surface);
  color: var(--k-color-text);
  text-align: left;
  cursor: pointer;
  scroll-snap-align: start;
  transition: border-color 0.16s ease, background 0.16s ease, box-shadow 0.16s ease;
}

.risk-selector-option:hover {
  border-color: var(--k-color-brand-500);
}

.risk-selector-option:focus-visible {
  outline: 2px solid var(--k-color-brand-500);
  outline-offset: 1px;
}

.risk-selector-option.active {
  border-color: var(--k-color-brand-500);
  background: var(--k-color-brand-050);
  box-shadow: 0 6px 16px rgba(28, 59, 46, 0.08);
}

.risk-selector-index {
  align-self: start;
  padding-top: 2px;
  color: var(--k-color-text-muted);
  font-size: 10px;
  font-weight: 700;
}

.risk-selector-copy {
  min-width: 0;
}

.risk-selector-copy strong {
  display: -webkit-box;
  overflow: hidden;
  color: var(--k-color-text);
  font-size: 12px;
  line-height: 1.38;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.risk-selector-copy small {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: var(--k-color-text-muted);
  font-size: 10px;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cluster-head,
.branch-head,
.subpanel-head,
.node-chip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.risk-primary-tag,
.node-chip-state {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 11px;
  letter-spacing: 0;
}

.risk-primary-tag {
  align-self: start;
  padding: 3px 6px;
  border: 1px solid var(--k-color-border-strong);
  background: transparent;
  color: var(--k-color-brand-700);
  font-size: 10px;
}

.risk-detail h3 {
  display: block;
  margin-top: 10px;
  color: #173056;
}

.risk-detail p,
.node-chip p,
.cluster-card p,
.branch-card p {
  margin: 8px 0 0;
  color: #5f6577;
  line-height: 1.5;
  font-size: 13px;
}

.risk-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  padding-top: 12px;
  border-top: 1px solid var(--k-color-border);
}

.risk-detail-empty {
  grid-column: 1 / -1;
  padding: 12px;
}

.risk-detail-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 12px;
  background: #f1f3f5;
}

.risk-detail-tabs button {
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #697386;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.risk-detail-tabs button.active {
  background: #fff;
  color: #173056;
  box-shadow: 0 4px 12px rgba(17, 31, 59, 0.08);
}

.risk-detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-detail-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.risk-eyebrow {
  color: #0f517d;
}

.risk-metrics {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.mini-pill.runtime-pill {
  border-color: rgba(28, 196, 135, 0.4);
  background: rgba(28, 196, 135, 0.1);
}

.mini-pill.runtime-pill strong {
  color: #0d7a52;
}

/* runtime tension / uncertainty band (additive) */
.risk-runtime-box {
  border-radius: 18px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.risk-runtime-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: #4f5d78;
}

.risk-runtime-head .runtime-hint {
  font-size: 11px;
  color: #8a96b0;
}

.risk-runtime-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
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
.runtime-status-tag.is-resolved { color: #0d7a52; background: rgba(13, 122, 82, 0.08); }
.runtime-status-tag.is-dormant { color: #6a7283; background: rgba(106, 114, 131, 0.08); }

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
  border-top: 1px dashed rgba(29, 39, 58, 0.16);
}

.risk-uncertainty-band .band-label {
  font-size: 11px;
  color: #8a96b0;
}

.risk-uncertainty-band strong {
  color: #1d273a;
  font-variant-numeric: tabular-nums;
}

.risk-uncertainty-band small {
  color: #8a96b0;
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
  margin-right: 6px;
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

.risk-related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}

.risk-related-grid.secondary {
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.risk-causal-chain {
  display: grid;
  grid-template-columns: minmax(110px, 0.8fr) auto minmax(180px, 1.2fr) auto minmax(120px, 0.9fr) auto minmax(180px, 1.25fr);
  gap: 8px;
  align-items: stretch;
}

.risk-causal-node {
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(29, 39, 58, 0.1);
  border-radius: 8px;
  background: #ffffff;
}

.risk-causal-node.mechanism {
  background: rgba(238, 244, 255, 0.8);
}

.risk-causal-node.consequence {
  background: rgba(255, 247, 231, 0.82);
  border-color: rgba(229, 151, 45, 0.2);
}

.risk-causal-node > span {
  display: block;
  margin-bottom: 7px;
  color: #7d8393;
  font-size: 11px;
  font-weight: 700;
}

.risk-causal-node strong {
  display: block;
  overflow-wrap: anywhere;
  color: #1d355b;
  font-size: 13px;
  line-height: 1.45;
}

.risk-causal-arrow {
  align-self: center;
  color: #6881b3;
  font-size: 17px;
  font-weight: 800;
}

.risk-note,
.risk-subpanel {
  border-radius: 18px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.risk-note span,
.subpanel-head span {
  display: block;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7d8393;
}

.risk-note strong {
  display: block;
  margin-top: 8px;
  color: #1d355b;
  line-height: 1.5;
}

.risk-step-pills,
.node-chip-labels,
.branch-list,
.cluster-list,
.node-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.risk-step-pills strong {
  margin: 0;
  padding: 4px 7px;
  border-radius: 5px;
  background: rgba(17, 61, 122, 0.08);
  color: #113d7a;
  font-size: 11px;
  font-weight: 700;
}

.metric-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 11px 12px;
  border: 1px solid rgba(29, 39, 58, 0.07);
  border-radius: 8px;
  background: rgba(248, 250, 253, 0.78);
}

.metric-row strong {
  color: #1d355b;
  font-size: 12px;
}

.metric-row span {
  color: #6f7588;
  font-size: 11px;
  text-align: right;
}

.risk-step-pill {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(17, 61, 122, 0.08);
  color: #113d7a;
  font-size: 12px;
}

.node-chip-list,
.cluster-list,
.branch-list {
  flex-direction: column;
}

.node-chip,
.cluster-card,
.branch-card {
  border-radius: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(29, 39, 58, 0.07);
}

.node-chip.compact {
  padding: 10px 12px;
}

.node-chip-state {
  background: rgba(124, 132, 147, 0.12);
  color: #6a7283;
}

.node-chip-state.matched {
  background: rgba(28, 196, 135, 0.14);
  color: #0c7850;
}

.node-label {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(240, 138, 36, 0.1);
  color: #9a5b11;
  font-size: 11px;
}

.bullet-list {
  margin: 0;
  padding-left: 18px;
  color: #4f5568;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.panel {
  border-radius: 24px;
  padding: 16px;
  min-height: auto;
  overflow: visible;
}

.matrix-head,
.region-row {
  display: grid;
  grid-template-columns: minmax(180px, 1.8fr) repeat(4, minmax(56px, 0.8fr));
  gap: 10px;
  align-items: center;
}

.matrix-head.is-curated,
.region-row.is-curated {
  grid-template-columns: minmax(170px, 1.65fr) repeat(8, minmax(50px, 0.62fr));
}

.matrix-head {
  margin-bottom: 10px;
  font-size: 11px;
  color: #7f8495;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.region-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.region-row {
  padding: 12px 10px;
  border-radius: 18px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.region-meta strong {
  display: block;
  margin-bottom: 4px;
}

.region-meta span {
  display: block;
  font-size: 12px;
  color: #7d8393;
}

.score-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bar-track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: rgba(19, 32, 51, 0.08);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #f08a24, #113d7a);
  border-radius: inherit;
}

.score-text,
.metric {
  font-size: 13px;
  font-weight: 700;
  color: #1e2333;
}

.event-list,
.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.event-card,
.history-card {
  border-radius: 18px;
  padding: 12px 14px;
  background: #ffffff;
  border: 1px solid rgba(29, 39, 58, 0.08);
}

.event-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.event-card p,
.history-card p,
.progress-note {
  margin: 8px 0 0;
  color: #5f6577;
  line-height: 1.5;
  font-size: 13px;
}

.event-pills,
.loop-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.pill,
.loop-pill,
.empty-loop {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(240, 138, 36, 0.1);
  color: #9a5b11;
  font-size: 12px;
}

.loop-box {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed rgba(29, 39, 58, 0.12);
}

.injection-presets,
.action-row,
.field-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.form-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.field-row label,
.form-stack > label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  font-size: 12px;
  color: #4f5568;
}

.injection-panel .action-row {
  margin-top: 14px;
}

.injection-log {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed rgba(29, 39, 58, 0.12);
}

.stage-empty {
  margin-top: 4px;
}

.log-shell {
  border-radius: 24px;
  padding: 16px 18px;
  min-height: auto;
}

.logs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: none;
  overflow: visible;
}

.log-line {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 10px;
  font-size: 12px;
  color: #334055;
}

.log-time {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #808699;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.empty-state {
  padding: 14px;
  border-radius: 16px;
  background: rgba(29, 39, 58, 0.04);
  color: #6f7588;
  font-size: 13px;
}

/* 长列表"展开全部 / 收起"——安静的整行文字按钮，不抢主次 */
.list-expand-btn {
  margin-top: 8px;
  width: 100%;
  border: none;
  background: transparent;
  color: #2f6f6a;
  font-size: 13px;
  font-weight: 600;
  padding: 8px;
  cursor: pointer;
  border-radius: 10px;
  font-family: inherit;
  transition: background 0.15s ease;
}

.list-expand-btn:hover {
  background: rgba(47, 111, 106, 0.08);
}

.empty-state.compact {
  padding: 12px;
  font-size: 12px;
}

@container (max-width: 920px) {
  .runtime-console {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .runtime-controls {
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .runtime-timeline p {
    display: none;
  }

  .workspace-tab-meta {
    display: none;
  }
}

@container (max-width: 700px) {
  .summary-grid,
  .state-secondary-grid,
  .multi-agent-grid,
  .risk-highlight-row,
  .risk-related-grid,
  .risk-related-grid.secondary {
    grid-template-columns: 1fr;
  }

  .risk-causal-chain {
    grid-template-columns: 1fr;
  }

  .risk-causal-arrow {
    justify-self: center;
    transform: rotate(90deg);
  }

}

@media (max-width: 1280px) {
  .workspace-tabs,
  .overview-top-grid,
  .overview-main-grid,
  .inject-grid,
  .multi-agent-grid,
  .risk-highlight-row,
  .risk-related-grid,
  .risk-related-grid.secondary {
    grid-template-columns: 1fr;
  }

  .risk-causal-chain {
    grid-template-columns: 1fr;
  }

  .risk-causal-arrow {
    justify-self: center;
    transform: rotate(90deg);
  }

  .workspace-topbar {
    flex-direction: column;
  }
}

@media (max-width: 960px) {
  .workspace-tab {
    grid-template-columns: 1fr;
  }

  .workspace-tab-index {
    width: 30px;
    height: 30px;
  }

  .control-head,
  .selector-row,
  .risk-detail-top {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .matrix-head,
  .region-row {
    grid-template-columns: minmax(150px, 1.5fr) repeat(4, minmax(44px, 0.7fr));
  }

  .matrix-head.is-curated,
  .region-row.is-curated {
    grid-template-columns: minmax(140px, 1.4fr) repeat(8, minmax(44px, 0.58fr));
  }
}

/* Step 3 visual contract: shared green system, compact controls, one progress rail. */
.envfish-step {
  gap: 12px;
  padding: 14px 16px 0;
  color: var(--k-color-text);
  background: var(--k-color-page);
}

.runtime-sticky {
  flex: 0 0 auto;
  position: relative;
  gap: 6px;
  padding-bottom: 6px;
  background: color-mix(in srgb, var(--k-color-page) 94%, transparent);
}

.hero,
.workspace-shell,
.control-panel,
.panel,
.log-shell {
  border-color: var(--k-color-border);
  background: var(--k-color-surface);
  box-shadow: var(--k-shadow-raised);
}

.runtime-console.runtime-transport {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  min-height: 50px;
  padding: 7px 8px 7px 12px;
  border-radius: var(--k-radius-md);
  box-shadow: none;
}

.runtime-progress-label {
  color: var(--k-color-text-secondary);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.runtime-progress-value {
  min-width: 38px;
  color: var(--k-color-text);
  font-size: 12px;
  text-align: right;
}

.runtime-play-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-width: 70px;
  height: 34px;
  padding: 0 11px;
  border-radius: 10px;
}

.runtime-play-toggle span {
  width: 10px;
  font-size: 10px;
  line-height: 1;
}

.eyebrow,
.workspace-eyebrow {
  color: var(--k-color-brand-600);
}

.status-card,
.summary-card,
.pulse-metric,
.region-row,
.event-card,
.history-card,
.node-chip {
  border-color: var(--k-color-border);
  background: var(--k-color-surface);
}

.status-card.accent,
.summary-card.accent {
  background: var(--k-color-brand-050);
  border-color: var(--k-color-border-strong);
}

.status-card strong,
.runtime-timeline-head strong,
.summary-card strong,
.workspace-copy h3,
.risk-detail h3,
.panel-title-row h3 {
  color: var(--k-color-text);
}

.status-card span,
.hint,
.panel-title-row span,
.summary-card span,
.summary-card p,
.runtime-timeline p,
.region-meta span,
.event-card p,
.history-card p,
.progress-note {
  color: var(--k-color-text-muted);
}

.primary-btn,
.play-control,
.control-count {
  background: var(--k-color-brand-600);
  color: #fff;
}

.primary-btn:hover,
.play-control:hover {
  background: var(--k-color-brand-hover);
}

.ghost-btn,
.secondary-btn,
.preset-btn,
.icon-control,
.latest-control,
.compact-selector select {
  border-color: var(--k-color-border-strong);
  background: var(--k-color-surface);
  color: var(--k-color-text);
}

.intervention-trigger {
  background: var(--k-color-brand-050);
  color: var(--k-color-brand-700);
}

.compact-range {
  height: 18px;
  margin: 0;
  accent-color: var(--k-color-brand-600);
  cursor: pointer;
}

.compact-range:disabled {
  cursor: default;
  opacity: 0.55;
}

.compact-range::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    var(--k-color-brand-600) 0 var(--range-progress),
    var(--k-color-surface-muted) var(--range-progress) 100%
  );
}

.compact-range::-webkit-slider-thumb {
  width: 16px;
  height: 16px;
  margin-top: -6px;
  border: 2px solid var(--k-color-surface);
  border-radius: 50%;
  background: var(--k-color-brand-600);
  box-shadow: 0 1px 4px rgba(16, 35, 29, 0.24);
  -webkit-appearance: none;
}

.workspace-tabs {
  gap: 24px;
  border-color: var(--k-color-border);
  background: color-mix(in srgb, var(--k-color-page) 94%, transparent);
}

.workspace-shell {
  flex: 1 1 0;
}

.step3-action-bar {
  flex: 0 0 auto;
  width: auto;
  margin: -12px -16px 0;
}

.workspace-tab,
.workspace-tab-meta {
  color: var(--k-color-text-muted);
}

.workspace-tab:hover,
.workspace-tab.active {
  color: var(--k-color-brand-700);
}

.workspace-tab.active {
  border-bottom-color: var(--k-color-brand-600);
}

.interaction-channel,
.risk-primary-tag,
.node-label,
.pill,
.loop-pill,
.empty-loop,
.runtime-status-tag,
.node-chip-state,
.node-chip-state.matched {
  border: 1px solid var(--k-color-border-strong);
  border-radius: 999px;
  background: transparent;
  color: var(--k-color-text-secondary);
  letter-spacing: 0;
  text-transform: none;
}

.bar-fill,
.progress-fill,
.subregion-bar-fill,
.agent-rank-strip-fill {
  background: var(--k-color-brand-600);
}

.bar-track,
.progress-track,
.subregion-bar,
.agent-rank-strip {
  background: var(--k-color-surface-muted);
}

.subregion-score,
.agent-rank-score,
.interaction-round,
.tension-sparkline,
.risk-causal-arrow {
  color: var(--k-color-brand-600);
}

.risk-causal-node.mechanism,
.risk-causal-node.consequence {
  border-color: var(--k-color-border-strong);
  background: var(--k-color-brand-050);
}

.risk-step-pills strong,
.subregion-meta span,
.agent-rank-meta span,
.interaction-meta span,
.runtime-turning-tag,
.variable-kind-tag {
  border: 1px solid var(--k-color-border-strong);
  background: transparent;
  color: var(--k-color-text-secondary);
}

.agent-rank-card:hover {
  border-color: var(--k-color-brand-500);
  box-shadow: 0 8px 20px rgba(28, 59, 46, 0.08);
}

.list-expand-btn {
  color: var(--k-color-brand-600);
}

.intervention-overlay {
  background: var(--k-color-overlay);
}

@container (max-width: 920px) {
  .step3-workflow-tabs :deep(.k-workflow-tabs__meta) {
    display: none;
  }

  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .multi-agent-grid,
  .relationship-runtime-grid,
  .risk-causal-chain,
  .risk-related-grid,
  .risk-related-grid.secondary {
    grid-template-columns: 1fr;
  }

  .relationship-runtime-grid > section + section {
    padding-top: 16px;
    padding-left: 0;
    border-top: 1px solid rgba(29, 39, 58, 0.08);
    border-left: 0;
  }

  .risk-causal-arrow {
    justify-self: center;
    transform: rotate(90deg);
  }
}

@container (max-width: 620px) {
  .runtime-console.runtime-transport {
    grid-template-columns: minmax(0, 1fr) auto auto;
    padding-left: 10px;
  }

  .runtime-progress-label {
    display: none;
  }

  .runtime-play-toggle {
    min-width: 64px;
    padding-inline: 9px;
  }

  .risk-selector-track {
    display: grid;
    grid-auto-columns: minmax(170px, 85%);
  }
}

@container (max-width: 520px) {
  .summary-grid,
  .relationship-summary-grid,
  .relationship-state-metrics {
    grid-template-columns: 1fr;
  }

  .runtime-ledger-row {
    grid-template-columns: 1fr;
  }

  .runtime-ledger-meta {
    justify-content: flex-start;
    max-width: none;
  }
}

/* Step 3 typography contract: compact controls, readable data, stable titles. */
.envfish-step3 {
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.step3-workflow-tabs :deep(.k-workflow-tabs__tab),
.runtime-play-toggle,
.primary-btn,
.secondary-btn,
.ghost-btn,
.preset-btn,
.text-btn {
  font-size: var(--k-text-ui);
  line-height: var(--k-leading-ui);
}

.panel-title-row h3,
.workspace-copy h3,
.risk-detail h3 {
  font-size: var(--k-text-section);
  line-height: var(--k-leading-ui);
}

.runtime-progress-label,
.runtime-progress-value,
.hint,
.panel-title-row span,
.summary-card span,
.runtime-timeline p,
.risk-primary-tag {
  font-size: var(--k-text-meta);
  line-height: var(--k-leading-ui);
}

.summary-card strong,
.pulse-delta-card strong,
.status-card strong {
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
}

.summary-card p,
.risk-detail p,
.node-chip p,
.cluster-card p,
.branch-card p,
.empty-state {
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}
</style>
