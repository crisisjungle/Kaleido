<template>
  <div class="envfish-step envfish-step2">
    <section ref="workspaceShellRef" class="workspace-shell">
      <header v-if="isConfigurationPhase" class="setup-header">
        <div>
          <div class="briefing-kicker">第 2 步 · 场景配置</div>
          <h2>确认推演输入</h2>
        </div>
        <div class="setup-header-meta">
          <span class="effort-lock-badge">⚡ {{ effortSnapshotLabel }} · 已锁定</span>
          <div class="setup-step-marker" aria-label="当前流程：配置输入">
            <span class="is-current">1 配置输入</span>
            <span>2 系统生成</span>
            <span>3 审阅结果</span>
          </div>
        </div>
      </header>

      <div v-if="phase === 'error'" class="prepare-error" role="alert">
        <strong>调整场景输入</strong>
        <p>{{ prepareMessageLabel || '输入已保留，可以修改后重新生成。' }}</p>
      </div>

      <!-- 场景简报：一句话讲清整个场景 + 常驻"进入推演" -->
      <header v-if="isReviewPhase" class="briefing-header">
        <div class="briefing-head-copy">
          <div class="briefing-kicker">场景简报</div>
          <h2 class="briefing-title">{{ scenarioReviewTitle }}</h2>
          <p class="briefing-summary-line">{{ sceneSummaryLine }}</p>
        </div>
        <span class="effort-lock-badge">⚡ {{ effortSnapshotLabel }} · 已锁定</span>
      </header>

      <div v-if="isReviewPhase" class="briefing-stats">
        <span class="briefing-stats-label">场景概览</span>
        <div class="briefing-stat-row">
          <div class="briefing-stat"><strong>{{ riskObjects.length }}</strong><span>风险对象</span></div>
          <div class="briefing-stat"><strong>{{ regionRecords.length }}</strong><span>区域</span></div>
          <div class="briefing-stat"><strong>{{ agentCards.length }}</strong><span>代理体</span></div>
          <div class="briefing-stat"><strong>{{ relationSummary.total }}</strong><span>关系</span></div>
        </div>
      </div>

      <aside v-if="isReviewPhase && showLockedInputs" class="locked-input-sheet">
        <div class="locked-input-head">
          <div>
            <span class="section-order">输入快照</span>
            <h3>本次生成使用的参数</h3>
          </div>
          <button class="text-btn" type="button" @click="showLockedInputs = false">关闭</button>
        </div>
        <div class="locked-input-grid">
          <div><span>时间计划</span><strong>{{ temporalProfileLabel }} · {{ maxRounds }} 轮</strong></div>
          <div>
            <span>推理投入</span>
            <strong>⚡ {{ effortSnapshotLabel }} · 已锁定</strong>
          </div>
          <div><span>灾害事件</span><strong>{{ eventInputs.length }} 项</strong></div>
          <div><span>政策措施</span><strong>{{ policyInputs.length }} 项</strong></div>
        </div>
        <div v-if="eventInputs.length || policyInputs.length" class="locked-variable-list">
          <article v-for="(event, index) in eventInputs" :key="event.id">
            <span>事件 {{ String(index + 1).padStart(2, '0') }}</span>
            <strong>{{ resolveVariableDisplayName(event) }}</strong>
            <p>{{ event.description || '未填写事件描述' }}</p>
          </article>
          <article v-for="policy in policyInputs" :key="policy.id">
            <span>政策措施</span>
            <strong>{{ resolveVariableDisplayName(policy) }}</strong>
            <p>{{ policy.intent || '未填写政策意图' }}</p>
          </article>
        </div>
      </aside>

      <section v-if="phase === 'preparing'" class="preparing-workspace" aria-live="polite">
        <div class="preparing-copy">
          <div class="briefing-kicker">第 2 步 · 系统生成</div>
          <h2>正在把输入转换为可推演场景</h2>
          <p>{{ prepareMessageLabel || '正在生成正式代理体、区域、关系和风险配置。' }}</p>
        </div>

        <KProgress
          class="preparing-progress"
          :value="prepareProgress"
          :label="`当前步骤 · ${prepareStageLabel}`"
          aria-label="场景配置生成进度"
          size="lg"
        />

        <ol class="generation-steps">
          <li
            v-for="step in generationSteps"
            :key="step.label"
            :class="{ 'is-complete': step.complete, 'is-current': step.current }"
          >
            <span>{{ step.index }}</span>
            <div><strong>{{ step.label }}</strong><small>{{ step.note }}</small></div>
          </li>
        </ol>

        <div class="graph-waiting-guide">
          <strong>生成期间可以继续看左侧图谱</strong>
          <p>确认地图范围与核心实体是否符合预期；这里不提前展示尚未生成完成的风险或代理体结果。</p>
        </div>
      </section>

      <KWorkflowTabs
        v-if="isReviewPhase"
        class="result-tabs"
        :model-value="activeWorkspaceTab"
        :items="workspaceTabs"
        variant="rich"
        aria-label="场景生成结果"
        @update:model-value="selectResultTab"
      />

      <section
        v-if="isConfigurationPhase"
        class="briefing-section bsec-parameters panel workspace-panel parameters"
      >
        <div class="panel-title-row briefing-head static-head">
          <div>
            <span class="section-order">输入阶段</span>
            <h3>事件与政策输入</h3>
          </div>
          <span class="hint">{{ paramsSummaryLine }}</span>
        </div>

        <div class="grounding-box parameter-lock-note">
          <p>{{ parameterIntroCopy }}</p>
        </div>

        <aside v-if="stableContextVariables.length > 0" class="catalog stable-context-section scene-goal-section">
          <div class="panel-title-row">
            <div>
              <span class="section-order">场景目标摘要</span>
              <h3>沿用第一步确认的背景范围</h3>
            </div>
            <span class="hint">{{ stableContextVariables.length }} 项 · 只读</span>
          </div>
          <div class="stable-context-list">
            <article v-for="item in stableContextVariables" :key="item.key" class="stable-context-card">
              <div class="stable-context-head">
                <strong>{{ safeDisplayText(item.name, '稳态背景') }}</strong>
                <span v-if="item.epistemicRole" class="stable-context-role">{{ displayToken(item.epistemicRole) }}</span>
              </div>
              <p v-if="item.description">{{ safeDisplayText(item.description, '背景说明已记录。') }}</p>
            </article>
          </div>
        </aside>

        <section class="catalog parameter-stage primary-condition-section event-input-section">
          <div class="panel-title-row parameter-stage-head">
            <div>
              <span class="section-order">01 · 按发生顺序</span>
              <h3>灾害事件<span class="variable-kind-tag perturbation">可编辑</span></h3>
              <p>只描述事件本身及其作用对象；时间演化与影响尺度由系统统一规划。</p>
            </div>
            <div class="action-row compact">
              <button class="ghost-btn" :disabled="!canEditParameters" @click="addEventInput">+ 添加灾害事件</button>
            </div>
          </div>

          <div v-if="eventInputs.length" class="variable-list">
            <article v-for="(event, index) in eventInputs" :key="event.id" class="variable-card event-input-card">
              <div class="variable-header">
                <div>
                  <span class="variable-index">事件 {{ String(index + 1).padStart(2, '0') }}</span>
                  <strong>{{ event.name || '未命名灾害事件' }}</strong>
                  <div class="variable-badges">
                    <span v-if="event.uiOrigin === 'seed'" class="variable-badge origin">来自背景定义</span>
                    <span v-else-if="event.uiOrigin === 'system_split'" class="variable-badge origin">系统拆分 · 可编辑</span>
                    <span v-else class="variable-badge manual">本步新增</span>
                  </div>
                </div>
                <div class="event-order-actions" aria-label="调整事件顺序">
                  <button
                    v-if="compoundEventParts(event).length > 1"
                    type="button"
                    class="split-event-btn"
                    :disabled="!canEditParameters"
                    @click="splitCompoundEventInput(event.id)"
                  >智能拆分</button>
                  <button type="button" :disabled="!canEditParameters || index === 0" @click="moveEventInput(index, -1)">上移</button>
                  <button type="button" :disabled="!canEditParameters || index === eventInputs.length - 1" @click="moveEventInput(index, 1)">下移</button>
                  <button type="button" class="remove-btn" :disabled="!canEditParameters || eventInputs.length === 1" @click="removeInput(event.id)">删除</button>
                </div>
              </div>

              <label>
                事件名称
                <input v-model="event.name" type="text" placeholder="例：近海放射性物质释放" :disabled="!canEditParameters" />
              </label>

              <label>
                事件描述
                <textarea v-model="event.description" rows="3" placeholder="描述发生了什么，以及它可能如何传播或影响环境与社会。" :disabled="!canEditParameters"></textarea>
              </label>

              <div class="field-row">
                <label>
                  目标区域
                  <select v-model="event.targetRegionId" :disabled="!canEditParameters">
                    <option value="">{{ variableRegionOptions.length ? '由系统判断或选择区域' : '由系统判断' }}</option>
                    <option v-for="option in variableRegionOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label>
                  目标节点
                  <select v-model="event.targetNodeId" :disabled="!canEditParameters">
                    <option value="">{{ variableNodeOptions.length ? '由系统判断或选择节点' : '由系统判断' }}</option>
                    <option v-for="option in variableNodeOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
              </div>
            </article>
          </div>
          <div v-else class="empty-state compact">至少添加一个灾害事件，系统才能规划后续演化。</div>
        </section>

        <section class="catalog parameter-stage policy-input-section">
          <div class="panel-title-row parameter-stage-head">
            <div>
              <span class="section-order">02 · 可选输入</span>
              <h3>政策措施</h3>
              <p>描述准备采取什么措施、希望实现什么效果，以及主要作用对象。</p>
            </div>
            <div class="action-row compact">
              <button class="ghost-btn" :disabled="!canEditParameters" @click="addPolicyInput">+ 添加政策措施</button>
            </div>
          </div>

          <div v-if="policyInputs.length" class="variable-list policy-input-list">
            <article v-for="policy in policyInputs" :key="policy.id" class="variable-card policy-input-card">
              <div class="variable-header">
                <div>
                  <span class="variable-index">政策措施</span>
                  <strong>{{ policy.name || '未命名政策措施' }}</strong>
                  <div class="variable-badges">
                    <span v-if="policy.uiOrigin === 'seed'" class="variable-badge origin">来自背景定义</span>
                    <span v-else class="variable-badge manual">本步新增</span>
                  </div>
                </div>
                <button type="button" class="remove-btn" :disabled="!canEditParameters" @click="removeInput(policy.id)">删除</button>
              </div>

              <label>
                政策名称
                <input v-model="policy.name" type="text" placeholder="例：加强近岸水质监测与信息公开" :disabled="!canEditParameters" />
              </label>
              <label>
                政策意图
                <textarea v-model="policy.intent" rows="3" placeholder="说明希望缓解什么问题或改变什么行为。" :disabled="!canEditParameters"></textarea>
              </label>
              <div class="field-row">
                <label>
                  目标区域
                  <select v-model="policy.targetRegionId" :disabled="!canEditParameters">
                    <option value="">{{ variableRegionOptions.length ? '由系统判断或选择区域' : '由系统判断' }}</option>
                    <option v-for="option in variableRegionOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label>
                  目标设施或对象
                  <select v-model="policy.targetNodeId" :disabled="!canEditParameters">
                    <option value="">{{ variableNodeOptions.length ? '由系统判断或选择对象' : '由系统判断' }}</option>
                    <option v-for="option in variableNodeOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
              </div>
            </article>
          </div>
          <div v-else class="empty-state compact">没有预设政策时可以留空，系统会先推演灾害事件的自然演化。</div>
        </section>

        <section class="catalog parameter-stage automatic-plan-section">
          <div class="panel-title-row parameter-stage-head">
            <div>
              <span class="section-order">03 · 系统自动计划</span>
              <h3>{{ automaticPlanTitle }}</h3>
              <p>{{ automaticPlanDescription }}</p>
            </div>
            <span class="hint">{{ automaticPlanStatusLabel }}</span>
          </div>
          <div class="automatic-plan-grid">
            <article
              v-for="card in automaticPlanCards"
              :key="card.key"
              :class="{ 'has-generated-plan': card.generated }"
            >
              <span>{{ card.label }}</span>
              <strong>{{ card.value }}</strong>
              <p>{{ card.description }}</p>
            </article>
          </div>
        </section>

        <details class="catalog advanced-strategy">
          <summary class="advanced-strategy-summary">
            <div>
              <span class="section-order">04 · 高级设置 · 可选</span>
              <strong>纠正时间计划</strong>
              <small>{{ temporalProfileLabel }} · {{ totalCoverageLabel }} · {{ timePlanMode === 'manual' ? '已纠正' : '系统规划' }}</small>
            </div>
            <span class="advanced-strategy-toggle" aria-hidden="true"></span>
          </summary>

          <div class="advanced-strategy-body">
            <section class="advanced-subsection time-range-section">
              <div class="panel-title-row parameter-stage-head">
                <div>
                  <h3>时间计划</h3>
                  <p>只有系统规划的时间尺度明显不符合事件节奏时才需要纠正。</p>
                </div>
                <span class="hint">{{ timePlanMode === 'manual' ? '已纠正' : '系统规划' }}</span>
              </div>
              <div class="summary-grid">
                <div class="summary-card"><span>每轮步长</span><strong>{{ temporalProfileLabel }}</strong></div>
                <div class="summary-card"><span>推演轮次</span><strong>{{ maxRounds }}</strong></div>
                <div class="summary-card"><span>总覆盖时长</span><strong>{{ totalCoverageLabel }}</strong></div>
              </div>
              <div class="field-row">
                <label>
                  步长单位
                  <select v-model="timeStepUnit" :disabled="!canEditParameters" @change="markTimePlanManual">
                    <option v-for="option in timePlanUnitOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                </label>
                <label>
                  每轮步长
                  <input v-model.number="timeStepSize" type="number" min="1" :disabled="!canEditParameters" @input="markTimePlanManual" />
                </label>
                <label>
                  总覆盖时长（{{ timePlanUnitLabel }}）
                  <input v-model.number="totalCoverageAmount" type="number" :min="timeStepSize" :disabled="!canEditParameters" @input="markTimePlanManual" />
                </label>
              </div>
            </section>

            <section class="advanced-subsection event-window-overrides">
              <div class="panel-title-row parameter-stage-head">
                <div>
                  <h3>事件计划纠正</h3>
                  <p>全部留空时由系统安排。只有你掌握明确时间或强度信息时才需要填写。</p>
                </div>
                <span class="hint">按事件单独覆盖</span>
              </div>
              <div class="event-override-list">
                <article v-for="event in eventInputs" :key="`override-${event.id}`">
                  <strong>{{ event.name || '未命名灾害事件' }}</strong>
                  <div class="field-row">
                    <label>
                      起始阶段（轮，可空）
                      <input v-model.number="event.advancedStartRound" type="number" min="0" placeholder="系统安排" :disabled="!canEditParameters" @input="markTimePlanManual" />
                    </label>
                    <label>
                      持续阶段（轮，可空）
                      <input v-model.number="event.advancedDurationRounds" type="number" min="1" placeholder="系统安排" :disabled="!canEditParameters" @input="markTimePlanManual" />
                    </label>
                    <label>
                      推导强度（0–100，可空）
                      <input v-model.number="event.advancedIntensity" type="number" min="0" max="100" placeholder="系统推导" :disabled="!canEditParameters" @input="markTimePlanManual" />
                    </label>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </details>
      </section>

      <section
        v-if="isReviewPhase && activeWorkspaceTab === 'agents'"
        class="briefing-section bsec-agents panel workspace-panel agents"
      >
        <div class="region-section-head agent-section-head">
          <div>
            <h3>代理体配置</h3>
            <p>{{ agentCards.length }} 个代理体 · {{ agentSourceLabel }}</p>
          </div>
          <span class="region-coverage-note">{{ agentConfigStatusLabel }}</span>
        </div>

        <div v-if="agentCategorySummaryLabel" class="agent-category-summary">
          <span>类型分布</span>
          <strong>{{ agentCategorySummaryLabel }}</strong>
        </div>

        <div v-if="agentPlanAudit.available" class="agent-plan-audit" aria-label="代理体建档审计">
          <div>
            <span>角色需求覆盖</span>
            <strong>{{ agentPlanAudit.coveredDemandCount }} / {{ agentPlanAudit.roleDemandCount }}</strong>
          </div>
          <div>
            <span>待补能力需求</span>
            <strong>{{ agentPlanAudit.unresolvedDemandCount }}</strong>
          </div>
          <div>
            <span>新建聚合代理体</span>
            <strong>{{ agentPlanAudit.aggregateAgentCount }}</strong>
          </div>
          <div>
            <span>政策执行绑定</span>
            <strong>{{ agentPlanAudit.boundPolicyCount }} / {{ agentPlanAudit.policyCount }}</strong>
          </div>
          <p>{{ agentPlanAuditDescription }}</p>
          <div v-if="agentPlanAudit.unresolvedDemands.length" class="agent-plan-unresolved">
            <strong>待补需求原因</strong>
            <span v-for="item in agentPlanAudit.unresolvedDemands" :key="item.key">
              {{ item.label }}：{{ item.reason }}
            </span>
          </div>
        </div>

        <div v-if="agentCards.length > 0" class="agent-table-shell">
          <div class="agent-table-head" aria-hidden="true">
            <span>序号</span>
            <span>名称</span>
            <span>类型</span>
            <span>主区域</span>
            <span></span>
          </div>
          <div class="agent-table-body">
            <div
              v-for="(agent, index) in pagedAgentCards"
              :key="agent.agentKey"
              class="agent-table-entry"
              :class="{ 'is-expanded': expandedAgentKey === agent.agentKey }"
            >
              <button
                type="button"
                class="agent-table-row"
                :aria-expanded="expandedAgentKey === agent.agentKey"
                :aria-controls="`agent-detail-${agentPageStartIndex + index}`"
                @click="toggleAgentDetail(agent.agentKey)"
              >
                <span class="agent-table-index mono">A{{ String(agentPageStartIndex + index + 1).padStart(3, '0') }}</span>
                <strong class="agent-table-name">{{ agent.displayName }}</strong>
                <span class="agent-table-text">{{ agent.agentTypeLabel || agent.familyLabel }}</span>
                <span class="agent-table-text agent-table-region">{{ agent.primaryRegionLabel || '未指定区域' }}</span>
                <span class="agent-row-action">{{ expandedAgentKey === agent.agentKey ? '收起' : '查看' }}</span>
              </button>
              <div
                v-if="expandedAgentKey === agent.agentKey"
                :id="`agent-detail-${agentPageStartIndex + index}`"
                class="agent-table-detail"
              >
                <p>{{ agent.summary || '当前代理体暂无补充说明。' }}</p>
                <div class="agent-profile-badges">
                  <span>{{ agent.lifecycleStatusLabel }}</span>
                  <span>{{ agent.representationLabel }}</span>
                  <span v-if="agent.isAggregate">聚合代理体</span>
                  <span>档案置信度 {{ agent.profileConfidenceLabel }}</span>
                </div>
                <dl class="agent-profile-facts">
                  <div><dt>角色</dt><dd>{{ agent.roleTypeLabel || agent.familyLabel }}</dd></div>
                  <div><dt>原型</dt><dd>{{ agent.archetypeLabel }}</dd></div>
                  <div><dt>配置来源</dt><dd>{{ agent.sourceLabel }}</dd></div>
                  <div><dt>影响区域</dt><dd>{{ agent.influencedRegionsCount || 0 }} 个</dd></div>
                  <div><dt>角色需求</dt><dd>{{ agent.roleDemandCount }} 项</dd></div>
                  <div><dt>证据锚点</dt><dd>{{ agent.evidenceCount }} 项</dd></div>
                </dl>
                <div class="agent-profile-sections">
                  <section>
                    <h4>能力与行动边界</h4>
                    <div class="agent-profile-chip-row">
                      <span v-for="item in agent.capabilityLabels" :key="`capability-${item}`">{{ item }}</span>
                      <span v-if="agent.capabilityLabels.length === 0" class="is-empty">暂无已核验能力</span>
                    </div>
                    <p>可执行行动：{{ agent.actionLabels.length > 0 ? agent.actionLabels.join('、') : '仅保持观察与待命' }}</p>
                  </section>
                  <section>
                    <h4>权限与资源</h4>
                    <div class="agent-profile-chip-row">
                      <span v-for="item in agent.permissionLabels" :key="`permission-${item}`">{{ item }}</span>
                      <span v-if="agent.permissionLabels.length === 0" class="is-empty">没有额外授权</span>
                    </div>
                    <p>{{ agent.resourceSummary }}</p>
                  </section>
                  <section class="agent-profile-basis">
                    <h4>建档依据</h4>
                    <p>{{ agent.generationReason }}</p>
                    <small>空间锚点 {{ agent.spatialAnchorCount }} 项 · 权限证据 {{ agent.authorityEvidenceCount }} 项 · 创建轮次 R{{ agent.createdRound }}</small>
                  </section>
                </div>
              </div>
            </div>
          </div>
          <nav class="agent-pagination" aria-label="代理体分页">
            <span>{{ agentPageStartIndex + 1 }}–{{ agentPageEndIndex }} / {{ agentCards.length }} 个</span>
            <div>
              <button type="button" :disabled="agentPage <= 1" @click="setAgentPage(agentPage - 1)">上一页</button>
              <strong>第 {{ agentPage }} / {{ agentTotalPages }} 页</strong>
              <button type="button" :disabled="agentPage >= agentTotalPages" @click="setAgentPage(agentPage + 1)">下一页</button>
            </div>
          </nav>
        </div>
        <div v-else class="empty-state">
          当前配置里还没有可展示的代理体，系统会在后续用图谱节点生成临时预览。
        </div>

      </section>

      <section
        v-if="isReviewPhase && activeWorkspaceTab === 'relations'"
        class="briefing-section bsec-relations panel workspace-panel relations"
      >
        <div class="panel-title-row briefing-head static-head">
          <h3>{{ relationSectionTitle }}</h3>
          <span class="hint">{{ relationSourceLabel }}</span>
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
              v-for="item in relationSummary.types.slice(0, 5)"
              :key="item.label"
              class="chip relation-chip"
            >
              {{ item.displayLabel }} · {{ item.count }}
            </span>
            <span v-if="relationSummary.types.length > 5" class="chip relation-chip">+{{ relationSummary.types.length - 5 }}</span>
            <span v-if="relationSummary.types.length === 0" class="empty-chip">
              当前关系按场景机制和空间范围组织。
            </span>
          </div>
        </div>

        <div class="catalog" v-if="relationSummary.channels.length > 0">
          <div class="catalog-title">互动渠道</div>
          <div class="chip-wrap">
            <span
              v-for="item in relationSummary.channels.slice(0, 4)"
              :key="item.label"
              class="chip relation-chip"
            >
              {{ item.displayLabel }} · {{ item.count }}
            </span>
            <span v-if="relationSummary.channels.length > 4" class="chip relation-chip">+{{ relationSummary.channels.length - 4 }}</span>
          </div>
        </div>


        <!-- 区域与代理体归属矩阵已并入「区域划分」tab（同源 regionAnchorMatrix），此处不再重复渲染 -->

        <div class="catalog" v-if="relationSummary.sampleEdges.length > 0">
          <div class="catalog-title">关系列表 · 前 {{ relationSummary.sampleEdges.length }} / {{ relationSummary.total }}</div>
          <div class="grounding-box">
            <div class="relation-edge-list">
              <div v-for="edge in relationSummary.sampleEdges" :key="edge.key" class="relation-edge-row">
                <strong>{{ safeDisplayText(edge.summary, '关系边') }}</strong>
                <span class="relation-edge-type">{{ edge.displayLabel }}</span>
                <small>{{ safeDisplayText(edge.rationale, edge.hint) }}<template v-if="edge.channelLabel || edge.strengthLabel"> · {{ [edge.channelLabel, edge.strengthLabel && `强度 ${edge.strengthLabel}`].filter(Boolean).join(' · ') }}</template></small>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="isReviewPhase && activeWorkspaceTab === 'region'"
        class="briefing-section bsec-region panel workspace-panel region"
      >
        <div class="region-section-head">
          <div>
            <h3>区域划分</h3>
            <p>{{ regionSourceLabel }} · {{ regionOverviewLabel }}</p>
          </div>
          <span class="region-coverage-note">覆盖 {{ regionCoverageLabel }}</span>
        </div>

        <div v-if="environmentBaselineRows.length" class="region-baseline-strip" aria-label="环境基线">
          <span class="region-baseline-label">环境基线</span>
          <span v-for="item in environmentBaselineRows" :key="item.key" class="region-baseline-item">
            {{ item.label }} <strong>{{ item.value }}</strong>
          </span>
          <span class="region-baseline-source">{{ environmentBaselineSourceLabel }}</span>
        </div>

        <div v-if="regionAnchorMatrix.length > 0" class="region-table-shell">
          <div class="region-table-head" aria-hidden="true">
            <span>区域</span>
            <span>层级</span>
            <span>关联代理体</span>
            <span>邻接</span>
            <span>主要属性</span>
            <span></span>
          </div>
          <button
            v-for="(region, index) in regionAnchorMatrix"
            :key="region.regionKey"
            type="button"
            class="region-table-row"
            @click="openRegionDetail(region.regionKey)"
          >
            <span class="region-identity-cell">
              <small class="mono">R{{ String(index + 1).padStart(2, '0') }}</small>
              <strong>{{ region.displayName }}</strong>
              <em>{{ region.regionTypeLabel }}</em>
            </span>
            <span class="region-table-text">{{ region.layerLabel }}</span>
            <span class="region-table-number"><strong>{{ region.agentCount }}</strong><small>个</small></span>
            <span class="region-table-number"><strong>{{ region.neighborCount }}</strong><small>个</small></span>
            <span class="region-preview-tags">
              <KTag v-for="tag in (region.previewTags || [])" :key="tag" tone="brand" variant="outline" size="sm">{{ tag }}</KTag>
              <KTag v-if="region.remainingTagCount > 0" tone="neutral" variant="outline" size="sm">+{{ region.remainingTagCount }}</KTag>
              <span v-if="!(region.previewTags || []).length" class="region-no-tag">未标注</span>
            </span>
            <span class="region-row-action">查看</span>
          </button>
        </div>
        <div v-else class="empty-state">
          当前没有可展示的区域配置。
        </div>
      </section>

      <template v-if="selectedRegion">
        <button class="region-drawer-backdrop" type="button" aria-label="关闭区域详情" @click="closeRegionDetail"></button>
        <aside class="region-detail-drawer" role="dialog" aria-modal="true" aria-labelledby="region-detail-title">
          <header class="region-drawer-head">
            <div>
              <span class="section-order">区域详情</span>
              <h3 id="region-detail-title">{{ selectedRegion.displayName }}</h3>
              <p>{{ selectedRegion.regionTypeLabel }} · {{ selectedRegion.layerLabel }}</p>
            </div>
            <button class="region-drawer-close" type="button" @click="closeRegionDetail">关闭</button>
          </header>

          <p v-if="selectedRegion.description" class="region-drawer-summary">{{ selectedRegion.description }}</p>

          <dl class="region-detail-metrics">
            <div><dt>关联代理体</dt><dd>{{ selectedRegion.agentCount }} 个</dd></div>
            <div><dt>相邻区域</dt><dd>{{ selectedRegion.neighborCount }} 个</dd></div>
            <div><dt>区域层级</dt><dd>{{ selectedRegion.subregionLabel }}</dd></div>
            <div><dt>配置来源</dt><dd>{{ regionSourceLabel }}</dd></div>
          </dl>

          <section v-if="selectedRegion.agentNames?.length" class="region-detail-block">
            <h4>关联代理体</h4>
            <p>{{ selectedRegion.agentNames.join('、') }}</p>
          </section>

          <section v-for="group in (selectedRegion.visibleTagGroups || [])" :key="group.key" class="region-detail-block">
            <h4>{{ group.label }}</h4>
            <p>{{ group.items.join('、') }}</p>
          </section>

          <section v-if="selectedRegion.neighbors?.length" class="region-detail-block">
            <h4>相邻区域</h4>
            <p>{{ selectedRegion.neighbors.join('、') }}</p>
          </section>
        </aside>
      </template>

      <section
        v-if="isReviewPhase && activeWorkspaceTab === 'risk'"
        class="briefing-section bsec-risk panel workspace-panel risk-preview-shell"
      >
      <div class="panel-title-row briefing-head static-head">
        <h3>风险定义与机制依据</h3>
        <span class="hint">{{ riskObjects.length }} 个 · 只读定义</span>
      </div>

      <div v-if="scenarioPlanningInput" class="scenario-plan-review">
        <article>
          <span>事件机制图</span>
          <strong>{{ mechanismNodes.length }} 个节点 · {{ mechanismEdges.length }} 条边</strong>
        </article>
        <article>
          <span>自动时间计划</span>
          <strong>{{ safeDisplayText(scenarioPlanningInput.temporal_plan?.coverage_label_zh, `${temporalProfileLabel} · ${maxRounds} 轮`) }}</strong>
        </article>
        <article>
          <span>政策作用计划</span>
          <strong>{{ scenarioPolicyPlan.length }} 项</strong>
        </article>
        <article>
          <span>角色能力需求</span>
          <strong>{{ scenarioRoleDemands.length }} 类</strong>
        </article>
      </div>

      <div v-if="riskObjects.length > 0" class="risk-preview-grid">
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
            class="risk-preview-list"
            :class="{ 'is-short-list': riskObjects.length <= 4 }"
            :style="{ '--risk-short-count': Math.max(1, riskObjects.length) }"
            aria-label="风险对象选择"
            @scroll.passive="syncRiskSelectorScrollState"
          >
            <button
              v-for="(item, index) in riskObjects"
              :key="item.risk_object_id"
              type="button"
              class="risk-preview-card"
              :class="{ active: item.risk_object_id === selectedRiskObjectId }"
              :aria-pressed="item.risk_object_id === selectedRiskObjectId"
              @click="selectedRiskObjectId = item.risk_object_id"
            >
              <div class="risk-selector-head">
                <span class="risk-selector-index">{{ String(index + 1).padStart(2, '0') }}</span>
                <span>{{ displayToken(item.mode || 'watch') }} · {{ riskFamilyLabel(item) }}</span>
                <span v-if="item.risk_object_id === primaryRiskObjectId" class="risk-selector-primary">主要</span>
              </div>
              <strong>{{ item.title }}</strong>
              <small class="risk-selector-meta">
                影响 {{ normalizeScore(item.impact_score ?? item.severity_score) }} · 证据 {{ riskEvidenceScore(item) }}
              </small>
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

        <div v-if="selectedRiskObject" class="risk-preview-detail">
          <div class="risk-detail-top">
            <div>
              <div class="eyebrow risk-eyebrow">
                {{ selectedRiskObject.mode === 'incident' ? '事件预览' : '观察预览' }} · {{ riskFamilyLabel(selectedRiskObject) }}
              </div>
              <h3>{{ selectedRiskObject.title }}</h3>
              <p v-if="!isRiskPlaceholderText(selectedRiskObject.summary || selectedRiskObject.why_now)">{{ selectedRiskObject.summary || selectedRiskObject.why_now }}</p>
            </div>

            <div class="risk-score-strip">
              <div class="summary-card compact">
                <span>影响潜力</span>
                <strong>{{ normalizeScore(selectedRiskObject.impact_score ?? selectedRiskObject.severity_score) }}</strong>
              </div>
              <div class="summary-card compact">
                <span>证据充分度</span>
                <strong>{{ riskEvidenceScore(selectedRiskObject) }}</strong>
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

          <div class="risk-causal-chain" aria-label="风险对象机制链">
            <div class="risk-causal-node">
              <span>触发源</span>
              <strong>{{ safeDisplayText(selectedRiskStatement.trigger_name || selectedRiskObject.root_pressures?.[0], '场景触发因素') }}</strong>
            </div>
            <span class="risk-causal-arrow" aria-hidden="true">→</span>
            <div class="risk-causal-node mechanism">
              <span>机制步骤</span>
              <div class="risk-step-list">
                <strong v-for="step in selectedRiskMechanismSteps" :key="step">{{ displayToken(step) }}</strong>
                <strong v-if="selectedRiskMechanismSteps.length === 0">{{ selectedRiskObject.mechanism_edge_ids?.length || 0 }} 条已校验机制边</strong>
              </div>
            </div>
            <span class="risk-causal-arrow" aria-hidden="true">→</span>
            <div class="risk-causal-node">
              <span>受影响对象</span>
              <strong>{{ safeDisplayText(selectedRiskStatement.receptor_name, '主要受影响对象') }}</strong>
            </div>
            <span class="risk-causal-arrow" aria-hidden="true">→</span>
            <div class="risk-causal-node consequence">
              <span>具体后果</span>
              <strong>{{ safeDisplayText(selectedRiskStatement.consequence || selectedRiskObject.summary, '等待具体后果说明。') }}</strong>
            </div>
          </div>

          <div class="risk-node-grid">
              <section class="risk-mini-panel">
                <div class="catalog-title">受影响主体与受体</div>
                <div class="node-list">
                  <article v-for="node in riskAffectedSubjectNodes" :key="node.id" class="node-card">
                    <div class="node-card-head">
                      <strong>
                        <span
                          v-if="provenanceMeta(node.provenance)"
                          class="provenance-dot"
                          :class="`is-${provenanceMeta(node.provenance).cls}`"
                          :title="`来源：${provenanceMeta(node.provenance).label}`"
                        ></span>
                        {{ safeDisplayText(node.name, '关联主体') }}
                      </strong>
                      <span class="node-state" :class="{ matched: node.matched }">{{ node.stateLabel }}</span>
                    </div>
                    <div v-if="node.labels.length || node.scopeBasisLabel" class="node-meta-line">
                      <span v-for="label in node.labels.slice(0, 2)" :key="label">{{ displayToken(label) }}</span>
                      <span v-if="node.labels.length > 2">另有 {{ node.labels.length - 2 }} 项</span>
                      <span v-if="node.scopeBasisLabel">{{ node.scopeBasisLabel }}</span>
                    </div>
                    <p v-if="node.summary" class="node-card-summary">{{ node.summary }}</p>
                  </article>
                  <div v-if="riskAffectedSubjectNodes.length === 0" class="empty-state compact">当前对象没有可展示的受影响主体。</div>
                </div>
              </section>

              <section class="risk-mini-panel">
                <div class="catalog-title">作用区域</div>
                <div class="node-list">
                  <article v-for="region in riskObjectRegionNodes" :key="region.id" class="node-card">
                    <div class="node-card-head">
                      <strong>{{ safeDisplayText(region.name, '作用区域') }}</strong>
                      <span class="node-state" :class="{ matched: region.matched }">{{ region.matched ? '地图区域' : '已校验区域' }}</span>
                    </div>
                    <div v-if="region.labels.length || region.scopeBasisLabel" class="node-meta-line">
                      <span v-for="label in region.labels.slice(0, 2)" :key="label">{{ displayToken(label) }}</span>
                      <span v-if="region.labels.length > 2">另有 {{ region.labels.length - 2 }} 项</span>
                      <span v-if="region.scopeBasisLabel">{{ region.scopeBasisLabel }}</span>
                    </div>
                  </article>
                  <div v-if="riskObjectRegionNodes.length === 0" class="empty-state compact">当前机制路径未引用区域节点。</div>
                </div>
              </section>
          </div>

          <div class="risk-node-grid secondary">
              <section class="risk-mini-panel">
                <div class="catalog-title">证据与认识状态</div>
                <div class="risk-evidence-list">
                  <article v-for="item in selectedRiskEvidence" :key="item.evidence_id || item.title" class="risk-evidence-item">
                    <div class="node-card-head">
                      <strong>{{ safeDisplayText(item.title, '机制依据') }}</strong>
                      <span class="evidence-status">{{ safeDisplayText(item.epistemic_status_label, displayToken(item.epistemic_status, '机制推断')) }}</span>
                    </div>
                    <p>{{ safeDisplayText(item.summary, formatInlineList(item.extracted_facts, '暂无证据摘要')) }}</p>
                  </article>
                  <div v-if="selectedRiskEvidence.length === 0" class="empty-state compact">当前对象没有可展示的证据条目。</div>
                </div>
              </section>

              <section class="risk-mini-panel">
                <div class="catalog-title">专属监测指标</div>
                <div class="risk-metric-list">
                  <article v-for="metric in selectedRiskMetrics" :key="metric.key || metric.label" class="risk-metric-item">
                    <strong>{{ safeDisplayText(metric.label, '监测指标') }}</strong>
                    <span>升高 {{ metric.thresholds?.elevated ?? 52 }} · 危急 {{ metric.thresholds?.critical ?? 72 }} · 解除 {{ metric.thresholds?.resolved ?? 35 }}</span>
                  </article>
                  <div v-if="selectedRiskMetrics.length === 0" class="empty-state compact">当前对象尚未配置专属监测指标。</div>
                </div>
              </section>
          </div>

          <div v-if="selectedRiskQualityLabels.length" class="risk-quality-row">
            <span>需复核</span>
            <p>{{ selectedRiskQualityLabels.join('、') }}</p>
          </div>
        </div>
      </div>

      <div v-else class="empty-state">
        当前场景没有通过证据校验的风险对象，可返回输入补充事实或调整范围。
      </div>
    </section>
    </section>

    <WorkflowActionBar
      v-if="isReviewPhase"
      class="step2-action-bar review-action-bar"
      :sticky="false"
      :elevated="false"
      :compact="true"
      aria-label="场景结果操作"
    >
      <div class="action-summary">
        <span>场景配置</span>
        <strong>{{ riskObjects.length }} 个风险对象 · {{ regionRecords.length }} 个区域 · {{ agentCards.length }} 个代理体 · {{ relationSummary.total }} 条关系</strong>
      </div>
      <template #actions>
        <button class="secondary-btn" type="button" @click="showLockedInputs = !showLockedInputs">
          {{ showLockedInputs ? '收起已锁定输入' : '查看已锁定输入' }}
        </button>
        <button class="primary-btn" :disabled="!isReady" @click="handleNextStep">进入推演 →</button>
      </template>
    </WorkflowActionBar>

    <WorkflowActionBar
      v-if="isConfigurationPhase"
      class="step2-action-bar"
      :sticky="false"
      :elevated="false"
      :compact="true"
      aria-label="场景配置操作"
    >
      <div class="action-summary">
        <span>{{ phase === 'error' ? '可以修改输入后重试' : '确认后将锁定本次输入' }}</span>
        <strong>{{ paramsSummaryLine }}</strong>
      </div>
      <template #actions>
        <button class="secondary-btn" @click="$emit('go-back')">返回图谱构建</button>
        <button class="primary-btn" :disabled="!canPrepare" @click="handlePrepare">
          {{ prepareActionLabel }}
        </button>
      </template>
    </WorkflowActionBar>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { getPrepareStatus, getSimulationConfig, getSimulationConfigRealtime, prepareSimulation, getSimulation } from '../api/simulation'
import KProgress from './ui/KProgress.vue'
import KTag from './ui/KTag.vue'
import KWorkflowTabs from './ui/KWorkflowTabs.vue'
import WorkflowActionBar from './ui/WorkflowActionBar.vue'
import { formatTokenLabelZh, normalizeDisplayLabels, safeDisplayError, safeDisplayText, safeDisplayToken, sanitizeDisplayCopy, translateDisplayToken } from '../utils/displayText'

const props = defineProps({
  simulationId: String,
  projectData: Object,
  graphData: Object,
  simulationData: Object,
  sceneSeedContext: Object,
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
  { value: 'generic', label: '通用生态危机', family: 'generic', badge: '通用', description: '用于承载尚未细分的局地扩散、生态承压与社会响应。', impactChain: '局地扩散 · 生态承压 · 社会响应' }
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

const timePlanUnitOptions = [
  { value: 'hour', label: '小时', minutes: 60 },
  { value: 'day', label: '天', minutes: 1440 },
  { value: 'week', label: '周', minutes: 10080 },
  { value: 'month', label: '月', minutes: 43200 },
  { value: 'quarter', label: '季度', minutes: 129600 },
  { value: 'year', label: '年', minutes: 525600 }
]

const scenarioMode = ref(props.initialScenarioMode || 'baseline_mode')
const diffusionTemplate = ref(props.initialDiffusionTemplate || 'marine_current')
const hazardTemplateId = ref('generic')
const hazardTemplateMode = ref('auto')
const hazardTemplateReasoning = ref('')
const FIXED_SIMULATION_ARCHITECTURE = 'llm_mechanism_v1'
const FIXED_SEARCH_MODE = 'deep_search'
const temporalPreset = ref('standard')
const configuredMinutesPerRound = ref(60)
const timePlanMode = ref('auto')
const timeStepUnit = ref('hour')
const timeStepSize = ref(1)
const timePlanReasoning = ref('')
const referenceTimeLocal = ref('')
const maxRounds = ref(36)
const activeWorkspaceTab = ref('risk')
const selectedRegionKey = ref('')
const agentPage = ref(1)
const expandedAgentKey = ref('')
const workspaceShellRef = ref(null)
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
const showLockedInputs = ref(false)

const resolvedSimulationArchitecture = computed(() => FIXED_SIMULATION_ARCHITECTURE)
const isReady = computed(() => phase.value === 'ready')
const isConfigurationPhase = computed(() => phase.value === 'idle' || phase.value === 'error')
const isReviewPhase = computed(() => phase.value === 'ready')
const isParameterLocked = computed(() => phase.value === 'preparing' || isReady.value)
const canEditParameters = computed(() => !isParameterLocked.value && !isPreparing.value)
const shouldShowDisplayTabs = computed(() => isReviewPhase.value)

const parameterStatusLabel = computed(() => {
  if (isReady.value) return '场景结果'
  if (phase.value === 'preparing') return '场景生成'
  if (hasSubmittedParameters.value) return '场景生成'
  return '场景输入'
})

const parameterIntroCopy = computed(() => {
  if (isParameterLocked.value) {
    return '参数已经确认，后续内容只作为生成结果展示；如需改变场景，请回到上一阶段重新生成图谱入口。'
  }
  return '先按顺序填写灾害事件，再补充需要预设的政策措施。时间范围由系统规划，仅在高级设置中纠正明显不合适的时间尺度。'
})

const eventInputs = computed(() => injectedVariables.value.filter(item => item.type !== 'policy'))
const policyInputs = computed(() => injectedVariables.value.filter(item => item.type === 'policy'))

let progressTimer = null
let configTimer = null

const graphNodes = computed(() => collectGraphNodes(props.graphData))
const graphEdges = computed(() => collectGraphEdges(props.graphData))
const environmentBaseline = computed(() => extractEnvironmentBaseline(graphNodes.value))
const environmentBaselineRows = computed(() => buildEnvironmentBaselineRows(environmentBaseline.value))
const environmentBaselineSourceLabel = computed(() => {
  if (!environmentBaseline.value) return '等待地图基线'
  const provider = environmentBaseline.value.provider === 'open-meteo'
    ? '开放天气服务'
    : safeDisplayToken(environmentBaseline.value.provider, '环境数据服务')
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

const timePlanUnitLabel = computed(() => {
  return timePlanUnitOptions.find(option => option.value === timeStepUnit.value)?.label || timeStepUnit.value
})

const totalCoverageAmount = computed({
  get() {
    return Math.max(1, Number(maxRounds.value) || 1) * Math.max(1, Number(timeStepSize.value) || 1)
  },
  set(value) {
    const coverage = Math.max(1, Number(value) || 1)
    const step = Math.max(1, Number(timeStepSize.value) || 1)
    maxRounds.value = Math.max(4, Math.ceil(coverage / step))
  }
})

const totalCoverageLabel = computed(() => {
  return `${totalCoverageAmount.value}${timePlanUnitLabel.value}`
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

const scenarioPlanningInput = computed(() => {
  const candidates = [
    resolvedConfig.value?.scenario_planning_input,
    configRealtime.value?.scenario_planning_input,
    configRealtime.value?.config?.scenario_planning_input,
    configSnapshot.value?.scenario_planning_input,
    configSnapshot.value?.config?.scenario_planning_input,
    simulationSnapshot.value?.scenario_planning_input,
    simulationSnapshot.value?.config?.scenario_planning_input,
    props.simulationData?.scenario_planning_input,
    props.simulationData?.config?.scenario_planning_input
  ]
  return candidates.find(item => item && typeof item === 'object' && Object.keys(item).length > 0) || null
})

const mechanismGraph = computed(() => scenarioPlanningInput.value?.event_mechanism_graph || {})
const mechanismNodes = computed(() => asArray(mechanismGraph.value?.nodes))
const mechanismEdges = computed(() => asArray(mechanismGraph.value?.edges))
const scenarioRoleDemands = computed(() => asArray(
  scenarioPlanningInput.value?.role_demands || resolvedConfig.value?.role_demands
))
const scenarioPolicyPlan = computed(() => asArray(
  scenarioPlanningInput.value?.policy_plan || resolvedConfig.value?.policy_plan
))
const resolvedAgentPlan = computed(() => {
  const candidates = [
    resolvedConfig.value?.agent_plan,
    configRealtime.value?.agent_plan,
    configRealtime.value?.config?.agent_plan,
    configSnapshot.value?.agent_plan,
    simulationSnapshot.value?.agent_plan,
    props.simulationData?.agent_plan,
    props.simulationData?.config?.agent_plan
  ]
  return candidates.find(item => item && typeof item === 'object' && Object.keys(item).length > 0) || {}
})
const resolvedPolicyExecutionPlan = computed(() => {
  const candidates = [
    resolvedConfig.value?.policy_execution_plan,
    configRealtime.value?.policy_execution_plan,
    configRealtime.value?.config?.policy_execution_plan,
    configSnapshot.value?.policy_execution_plan,
    simulationSnapshot.value?.policy_execution_plan,
    props.simulationData?.policy_execution_plan,
    props.simulationData?.config?.policy_execution_plan
  ]
  return candidates.find(item => item && typeof item === 'object' && Object.keys(item).length > 0) || {}
})
const agentPlanAudit = computed(() => {
  const plan = resolvedAgentPlan.value
  const generation = plan?.generation_audit || {}
  const roleCoverage = asArray(plan?.role_coverage)
  const unresolvedRaw = asArray(plan?.unresolved_demands)
  const policySummary = resolvedPolicyExecutionPlan.value?.summary || {}
  const policyBindings = asArray(resolvedPolicyExecutionPlan.value?.policy_bindings)
  const roleDemandCount = Number(generation.role_demand_count ?? plan?.role_demands?.length ?? roleCoverage.length) || 0
  const coveredDemandCount = Number(
    generation.covered_role_demand_count ??
    roleCoverage.filter(item => ['covered', 'partial'].includes(String(item?.status || ''))).length
  ) || 0
  const unresolvedDemandCount = Number(
    generation.unresolved_role_demand_count ?? plan?.unresolved_demands?.length ?? 0
  ) || 0
  const aggregateAgentCount = Number(generation.created_as_region_aggregate_count ?? 0) || 0
  const boundPolicyCount = Number(
    policySummary.bound_count ?? policyBindings.filter(item => String(item?.binding_status || '') === 'bound').length
  ) || 0
  const policyCount = Number(policySummary.policy_count ?? policySummary.total_count ?? policyBindings.length) || 0
  const unresolvedDemands = unresolvedRaw.map((item, index) => ({
    key: String(item?.unresolved_demand_id || item?.role_demand_id || `unresolved-${index}`),
    label: safeDisplayText(item?.label_zh || item?.role_key, '未覆盖能力需求'),
    reason: safeDisplayText(item?.reason_zh, displayToken(item?.reason_code, '缺少匹配证据')),
    reasonCode: String(item?.reason_code || ''),
    targetRegionId: String(item?.target_region_id || '')
  }))
  return {
    available: Boolean(Object.keys(plan || {}).length || Object.keys(resolvedPolicyExecutionPlan.value || {}).length),
    roleDemandCount,
    coveredDemandCount,
    unresolvedDemandCount,
    aggregateAgentCount,
    boundPolicyCount,
    policyCount,
    selectedAgentCount: Number(generation.selected_agent_count ?? plan?.planned_agents?.length ?? 0) || 0,
    plannedAgentLimit: Number(generation.planned_agent_limit ?? 0) || 0,
    candidateProfileCount: Number(generation.candidate_profile_count ?? 0) || 0,
    unresolvedDemands,
    budgetDeferredCount: unresolvedDemands.filter(item => item.reasonCode === 'budget_deferred').length
  }
})
const agentPlanAuditDescription = computed(() => {
  if (!agentPlanAudit.value.available) return ''
  if (agentPlanAudit.value.unresolvedDemandCount > 0) {
    if (agentPlanAudit.value.budgetDeferredCount > 0) {
      return `按角色需求、空间证据与执行能力生成；${agentPlanAudit.value.budgetDeferredCount} 项需求达到当前分析强度的代理体上限。`
    }
    return '按角色需求、空间证据与执行能力生成；当前待补项主要因为缺少匹配的正式空间、机构或设施证据，不是由预设目标数量补齐。'
  }
  return '按角色需求、空间证据与执行能力生成；代理体数量不是预设目标数，已覆盖当前角色能力需求。'
})
const effortSnapshot = computed(() => {
  const candidates = [
    resolvedConfig.value?.effort_snapshot,
    resolvedConfig.value?.effort_snapshot_ref,
    configRealtime.value?.effort_snapshot,
    configRealtime.value?.effort_snapshot_ref,
    configRealtime.value?.config?.effort_snapshot,
    configRealtime.value?.config?.effort_snapshot_ref,
    simulationSnapshot.value?.effort_snapshot,
    simulationSnapshot.value?.effort_snapshot_ref,
    simulationSnapshot.value?.config?.effort_snapshot,
    simulationSnapshot.value?.config?.effort_snapshot_ref,
    props.simulationData?.effort_snapshot,
    props.simulationData?.effortSnapshot,
    props.simulationData?.effort_snapshot_ref,
    props.simulationData?.scene_seed_context?.effort_snapshot,
    props.simulationData?.scene_seed_context?.effortSnapshot,
    props.simulationData?.sceneSeedContext?.effort_snapshot,
    props.simulationData?.sceneSeedContext?.effortSnapshot,
    props.sceneSeedContext?.effort_snapshot,
    props.sceneSeedContext?.effortSnapshot,
    props.projectData?.effort_snapshot,
    props.projectData?.effortSnapshot,
    props.projectData?.scene_seed?.effort_snapshot,
    props.projectData?.scene_seed?.effortSnapshot,
    props.projectData?.sceneSeed?.effort_snapshot,
    props.projectData?.sceneSeed?.effortSnapshot
  ]
  const snapshot = candidates.find(item => item && typeof item === 'object' && Object.keys(item).length > 0) || {}
  const legacyId = firstNonEmptyString(
    snapshot.effort_snapshot_id,
    snapshot.snapshot_id,
    resolvedConfig.value?.effort_snapshot_id,
    configRealtime.value?.effort_snapshot_id,
    configRealtime.value?.config?.effort_snapshot_id,
    simulationSnapshot.value?.effort_snapshot_id,
    simulationSnapshot.value?.config?.effort_snapshot_id,
    props.simulationData?.effort_snapshot_id,
    props.simulationData?.effortSnapshotId,
    props.simulationData?.scene_seed_context?.effort_snapshot_id,
    props.simulationData?.scene_seed_context?.effortSnapshotId,
    props.simulationData?.sceneSeedContext?.effort_snapshot_id,
    props.simulationData?.sceneSeedContext?.effortSnapshotId,
    props.sceneSeedContext?.effort_snapshot_id,
    props.sceneSeedContext?.effortSnapshotId,
    props.projectData?.effort_snapshot_id,
    props.projectData?.effortSnapshotId,
    props.projectData?.scene_seed?.effort_snapshot_id,
    props.projectData?.scene_seed?.effortSnapshotId,
    props.projectData?.sceneSeed?.effort_snapshot_id,
    props.projectData?.sceneSeed?.effortSnapshotId
  )
  return legacyId && !snapshot.effort_snapshot_id
    ? { ...snapshot, effort_snapshot_id: legacyId }
    : snapshot
})

const effortSnapshotId = computed(() => firstNonEmptyString(effortSnapshot.value?.effort_snapshot_id))
const effortSnapshotLabel = computed(() => {
  const explicit = firstNonEmptyString(effortSnapshot.value?.effort_label)
  const labels = {
    light: '轻量',
    medium: '标准',
    high: '深入',
    extra_high: '高强度',
    'extra-high': '高强度',
    ultra: '极致'
  }
  const level = firstNonEmptyString(effortSnapshot.value?.effort_level).toLowerCase()
  if (labels[level]) return labels[level]
  const legacyLabels = {
    '轻量': '轻量',
    '标准': '标准',
    '深入': '深入',
    '极高': '高强度',
    '最高': '极致',
    '高强度': '高强度',
    '极致': '极致'
  }
  if (legacyLabels[explicit]) return legacyLabels[explicit]
  const explicitLevel = explicit.toLowerCase().replace(/^effort\s+/, '').replace(/\s+/g, '_')
  if (labels[explicitLevel]) return labels[explicitLevel]
  return '深入'
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

const AGENT_PAGE_SIZE = 12
const agentTotalPages = computed(() => Math.max(1, Math.ceil(agentCards.value.length / AGENT_PAGE_SIZE)))
const agentPageStartIndex = computed(() => (agentPage.value - 1) * AGENT_PAGE_SIZE)
const agentPageEndIndex = computed(() => Math.min(agentPageStartIndex.value + AGENT_PAGE_SIZE, agentCards.value.length))
const pagedAgentCards = computed(() => agentCards.value.slice(agentPageStartIndex.value, agentPageEndIndex.value))
const agentCategorySummaryLabel = computed(() => agentCategoryGroups.value
  .filter(group => group.count > 0)
  .map(group => `${group.label} ${group.count}`)
  .join(' · '))

function setAgentPage(page) {
  const nextPage = Math.min(Math.max(1, Number(page) || 1), agentTotalPages.value)
  if (nextPage === agentPage.value) return
  agentPage.value = nextPage
  expandedAgentKey.value = ''
}

function toggleAgentDetail(agentKey) {
  expandedAgentKey.value = expandedAgentKey.value === agentKey ? '' : agentKey
}

watch(() => agentCards.value.length, () => {
  if (agentPage.value > agentTotalPages.value) agentPage.value = agentTotalPages.value
  if (expandedAgentKey.value && !agentCards.value.some(agent => agent.agentKey === expandedAgentKey.value)) {
    expandedAgentKey.value = ''
  }
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
  if (agentSourceMode.value === 'agent_configs') {
    return agentPlanAudit.value.unresolvedDemandCount > 0 ? '部分覆盖' : '正式配置'
  }
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
  const pairs = new Set()
  regionRecords.value.forEach((region) => {
    const source = normalizeKey(region.displayName || region.regionKey)
    ;(region.neighbors || []).forEach((neighbor) => {
      const target = normalizeKey(neighbor)
      if (!source || !target || source === target) return
      pairs.add([source, target].sort().join('::'))
    })
  })
  return pairs.size
})

const regionCoveredCount = computed(() => {
  return regionAnchorMatrix.value.filter((region) => region.agentCount > 0).length
})

const regionCoverageLabel = computed(() => {
  if (regionAnchorMatrix.value.length === 0) return '0%'
  const percentage = Math.round((regionCoveredCount.value / Math.max(regionAnchorMatrix.value.length, 1)) * 100)
  return `${percentage}%`
})

const regionOverviewLabel = computed(() => {
  const parts = [`${regionAnchorMatrix.value.length} 个区域`]
  if (regionCoveredCount.value > 0) parts.push(`${regionCoveredCount.value} 个已关联代理体`)
  if (regionNeighborLinks.value > 0) parts.push(`${regionNeighborLinks.value} 条邻接`)
  return parts.join(' · ')
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

const regionAnchorTotal = computed(() => {
  return regionAnchorMatrix.value.reduce((total, region) => total + Number(region.agentCount || 0), 0)
})

const selectedRegion = computed(() => {
  if (!selectedRegionKey.value) return null
  return regionAnchorMatrix.value.find((region) => region.regionKey === selectedRegionKey.value) || null
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
  const graphFamilies = categorizeNodes(graphNodes.value)
  const graphEntities = [
    ...graphFamilies.infrastructure,
    ...graphFamilies.organization,
    ...graphFamilies.governance,
    ...graphFamilies.human,
    ...graphFamilies.ecology
  ].map((node) => ({
    value: firstNonEmptyString(node?.uuid, node?.id, node?.entity_uuid, node?.key),
    label: safeDisplayText(firstNonEmptyString(node?.name, node?.label, node?.title), '未命名对象'),
    detail: displayToken(getNodeType(node), '图谱对象')
  }))
  const generatedAgents = agentCards.value.map((agent) => ({
    value: String(agent.sourceEntityUuid || agent.agentId || '').trim(),
    label: agent.displayName,
    detail: `${agent.familyLabel}${agent.primaryRegionLabel ? ` · ${agent.primaryRegionLabel}` : ''}`
  }))

  return [...graphEntities, ...generatedAgents]
    .map((item) => {
      const value = String(item.value || '').trim()
      if (!value || seen.has(value)) return null
      seen.add(value)
      return {
        value,
        label: `${item.label} · ${item.detail}`
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

const normalizedPlanningEvents = computed(() => asArray(scenarioPlanningInput.value?.normalized_user_events))

const eventChainPreview = computed(() => {
  const names = uniqueList(
    eventInputs.value
      .map(item => sanitizeDisplayCopy(resolveVariableDisplayName(item)))
      .filter(Boolean)
  )
  if (names.length === 0) return '等待填写灾害事件'
  if (names.length <= 3) return names.join(' → ')
  return `${names.slice(0, 3).join(' → ')} → 另 ${names.length - 3} 项`
})

const automaticPlanHasGeneratedResult = computed(() => Boolean(scenarioPlanningInput.value))

const automaticPlanStatusLabel = computed(() => {
  if (automaticPlanHasGeneratedResult.value) return '规划摘要'
  if (phase.value === 'preparing') return '生成中'
  return '确认后生成实际判定'
})

const automaticPlanTitle = computed(() => {
  return automaticPlanHasGeneratedResult.value
    ? '机制、时间与角色能力规划'
    : '确认后生成机制、时间与角色能力规划'
})

const automaticPlanDescription = computed(() => {
  if (automaticPlanHasGeneratedResult.value) {
    return '这里显示当前机制、时间窗和角色能力需求摘要，完整内容在审阅标签中查看。'
  }
  return '这里先核对系统将要判定的内容；真正的机制图、时间窗、强度和角色能力需求会在生成后写入结果。'
})

const compoundEventCandidateCount = computed(() => {
  return eventInputs.value.filter(event => compoundEventParts(event).length > 1).length
})

const automaticPlanCards = computed(() => {
  if (automaticPlanHasGeneratedResult.value) {
    return [
      {
        key: 'generated-mechanism',
        label: '事件机制图',
        value: `${mechanismNodes.value.length} 个节点 · ${mechanismEdges.value.length} 条边`,
        description: '已根据输入事件建立因果、触发与传播关系。',
        generated: true
      },
      {
        key: 'generated-temporal',
        label: '时间与强度',
        value: safeDisplayText(
          scenarioPlanningInput.value?.temporal_plan?.coverage_label_zh,
          `${temporalProfileLabel.value} · ${maxRounds.value} 轮`
        ),
        description: '已生成事件阶段、传播延迟、持续周期与作用窗口。',
        generated: true
      },
      {
        key: 'generated-role-demand',
        label: '下游能力需求',
        value: `${scenarioRoleDemands.value.length} 类角色能力 · ${scenarioPolicyPlan.value.length} 项政策计划`,
        description: '已提取需要哪些角色能力，不在这里预设代理体数量。',
        generated: true
      }
    ]
  }

  const eventCount = eventInputs.value.length
  const policyCount = policyInputs.value.length
  const splitHint = compoundEventCandidateCount.value
    ? `其中 ${compoundEventCandidateCount.value} 项可能继续拆分。`
    : '如存在复合描述，生成时会自动拆成原子事件。'

  return [
    {
      key: 'pending-events',
      label: '事件链输入',
      value: eventChainPreview.value,
      description: `${eventCount} 项灾害事件将按顺序解析；${splitHint}`,
      generated: false
    },
    {
      key: 'pending-temporal',
      label: '待判定内容',
      value: '机制图 · 时间窗 · 强度',
      description: `${timePlanMode.value === 'manual' ? '将按已纠正的时间尺度' : '将按系统时间尺度'}生成阶段、传播延迟、持续周期与影响强度。`,
      generated: false
    },
    {
      key: 'pending-role-demand',
      label: '生成后输出',
      value: policyCount ? `角色能力需求 · ${policyCount} 项政策计划` : '角色能力需求 · 自然演化',
      description: '先提取所需角色能力和政策作用机制，再交给下游代理体规划。',
      generated: false
    }
  ]
})

const scenarioReviewTitle = computed(() => {
  const names = uniqueList(
    (normalizedPlanningEvents.value.length ? normalizedPlanningEvents.value : eventInputs.value)
      .map(item => sanitizeDisplayCopy(firstNonEmptyString(item?.name, item?.label_zh)))
      .filter(Boolean)
  )
  if (names.length === 0) return '已生成场景'
  if (names.length === 1) return names[0]
  const compact = names.length <= 3 ? names.join(' → ') : `${names.slice(0, 3).join(' → ')}等`
  return `复合事件：${compact}`
})

const sceneSummaryLine = computed(() => {
  const temporal = firstNonEmptyString(
    safeDisplayText(scenarioPlanningInput.value?.temporal_plan?.coverage_label_zh, ''),
    `${temporalProfileLabel.value} · ${maxRounds.value} 轮`
  )
  const graphSummary = mechanismNodes.value.length
    ? `${mechanismNodes.value.length} 个事件节点 · ${mechanismEdges.value.length} 条机制边`
    : safeDisplayToken(scenarioMode.value, '场景')
  return [graphSummary, temporal, effortSnapshotLabel.value].filter(Boolean).join(' · ')
})
const paramsSummaryLine = computed(() => {
  return [
    `${eventInputs.value.length} 个灾害事件`,
    `${policyInputs.value.length} 项政策措施`,
    temporalProfileLabel.value
  ].join(' · ')
})

const workspaceTabs = computed(() => {
  return [
    {
      value: 'risk',
      label: '风险定义',
      meta: `${riskObjects.value.length} 个对象 · ${primaryRiskObjectId.value ? '已聚焦' : '待生成'}`
    },
    {
      value: 'region',
      label: '区域结构',
      meta: `${regionRecords.value.length} 个区域 · ${regionAnchorTotal.value} 个锚点`
    },
    {
      value: 'agents',
      label: '代理体配置',
      meta: `${agentCards.value.length} 个 · ${agentSourceLabel.value}`
    },
    {
      value: 'relations',
      label: '关系网络',
      meta: `${relationSummary.value.total} 条 · ${relationSummary.value.types.length} 类`
    },
  ]
})

async function selectResultTab(tab) {
  if (!workspaceTabs.value.some(item => item.value === tab) || tab === activeWorkspaceTab.value) return
  activeWorkspaceTab.value = tab
  await nextTick()
  const shell = workspaceShellRef.value
  const tabs = shell?.querySelector('.result-tabs')
  if (shell && tabs) shell.scrollTop = Math.max(0, tabs.offsetTop - 6)
  if (tab === 'risk') await revealSelectedRiskObject()
}

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
const riskSelectorRef = ref(null)
const riskSelectorOverflow = ref(false)
const canScrollRiskSelectorPrev = ref(false)
const canScrollRiskSelectorNext = ref(false)

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
    left: direction * Math.max(180, track.clientWidth * 0.82),
    behavior: 'smooth'
  })
}

async function revealSelectedRiskObject() {
  await nextTick()
  const track = riskSelectorRef.value
  const activeItem = track?.querySelector('.risk-preview-card.active')
  activeItem?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  syncRiskSelectorScrollState()
}

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
            const text = safeDisplayText(item, '')
            return text ? { name: text, key: `stable-${index}` } : null
          }
          return {
            key: toDisplayString(item.id || item.variable_id || item.name || `stable-${index}`, `stable-${index}`),
            name: safeDisplayText(item.name || item.title || item.label, `稳态背景 ${index + 1}`),
            description: safeDisplayText(item.description || item.summary, ''),
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

function safeDisplayName(value, fallback = '') {
  const raw = String(value ?? '').trim()
  if (!raw) return fallback
  const withoutInternalPrefix = raw
    .replace(/^(?:feature_context_admin_(?:district|city)|feature_context|feature_relation|context_admin_(?:district|city))[_:\-]*/i, '')
    .trim()
  const candidate = withoutInternalPrefix || raw
  if (/^\d+$/.test(candidate)) return fallback
  if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(candidate)) return fallback
  if (/^(?:agent|node|entity|region|risk|feature|relation|context)[_-][a-z0-9_-]+$/i.test(candidate)) return fallback
  return safeDisplayText(candidate, fallback)
}

const INTERNAL_VARIABLE_NAMES = new Set(['disaster_injection', 'policy_injection'])

function resolveVariableDisplayName(variable) {
  const rawName = String(variable?.name || '').trim()
  if (rawName && !INTERNAL_VARIABLE_NAMES.has(rawName)) {
    return safeDisplayName(rawName, variable?.type === 'policy' ? '政策变量' : '灾害变量')
  }
  const description = safeDisplayText(variable?.description, '')
  if (description) return description.length > 24 ? `${description.slice(0, 24)}...` : description
  return variable?.type === 'policy' ? '政策变量' : '灾害变量'
}

function normalizeRegionRef(value) {
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? { region_id: text, region_name: safeDisplayName(text, '') } : null
  }
  if (!value || typeof value !== 'object') return null
  const regionId = firstNonEmptyString(value.region_id, value.regionId, value.id, value.key, value.uuid, value.code)
  const regionName = safeDisplayName(firstNonEmptyString(value.region_name, value.regionName, value.name, value.label, value.title), '')
  if (!regionId && !regionName) return null
  return {
    region_id: regionId || regionName,
    region_name: regionName,
    region_type: firstNonEmptyString(value.region_type, value.regionType, value.type),
    scope_basis: firstNonEmptyString(value.scope_basis, value.scopeBasis),
    epistemic_status: firstNonEmptyString(value.epistemic_status, value.epistemicStatus)
  }
}

function normalizeEntityRef(value) {
  if (typeof value === 'string') {
    const text = value.trim()
    return text ? { entity_uuid: text, entity_name: safeDisplayName(text, '') } : null
  }
  if (!value || typeof value !== 'object') return null
  const entityUuid = firstNonEmptyString(value.entity_uuid, value.entityUuid, value.uuid, value.id, value.key)
  const entityName = safeDisplayName(firstNonEmptyString(value.entity_name, value.entityName, value.name, value.label, value.title), '')
  const entityType = firstNonEmptyString(
    value.entity_type,
    value.entityType,
    value.node_family,
    value.nodeFamily,
    value.type
  )
  if (!entityUuid && !entityName) return null
  return {
    entity_uuid: entityUuid || entityName,
    entity_name: entityName,
    entity_type: entityType,
    entity_summary: safeDisplayText(firstNonEmptyString(value.entity_summary, value.entitySummary, value.summary, value.description), ''),
    labels: uniqueList(asArray(value.labels).map(String)),
    scope_basis: firstNonEmptyString(value.scope_basis, value.scopeBasis),
    epistemic_status: firstNonEmptyString(value.epistemic_status, value.epistemicStatus)
  }
}

function scopeBasisLabel(value) {
  return value ? displayToken(value, '') : ''
}

function normalizeActorRef(value) {
  if (typeof value === 'number' || typeof value === 'string') {
    const text = String(value).trim()
    return text ? { actor_id: text, actor_name: safeDisplayName(text, '') } : null
  }
  if (!value || typeof value !== 'object') return null
  const actorId = firstNonEmptyString(value.actor_id, value.actorId, value.agent_id, value.agentId, value.id, value.key)
  const actorName = safeDisplayName(firstNonEmptyString(value.actor_name, value.actorName, value.agent_name, value.agentName, value.name, value.username, value.label), '')
  if (!actorId && !actorName) return null
  return {
    actor_id: actorId || actorName,
    actor_name: actorName,
    actor_type: firstNonEmptyString(value.actor_type, value.actorType, value.agent_type, value.agentType, value.node_family, value.nodeFamily),
    profession: safeDisplayText(firstNonEmptyString(value.profession, value.role_name, value.roleName), ''),
    matched_role_demand_id: firstNonEmptyString(value.matched_role_demand_id, value.matchedRoleDemandId),
    matched_role_demand_label: safeDisplayText(firstNonEmptyString(value.matched_role_demand_label, value.matchedRoleDemandLabel), ''),
    primary_region: safeDisplayName(firstNonEmptyString(value.primary_region, value.primaryRegion, value.home_region_id, value.homeRegionId), ''),
    labels: uniqueList(asArray(value.labels).map(String)),
    scope_basis: firstNonEmptyString(value.scope_basis, value.scopeBasis),
    epistemic_status: firstNonEmptyString(value.epistemic_status, value.epistemicStatus)
  }
}

function normalizeClusterRef(value) {
  if (!value || typeof value !== 'object') return value
  return {
    ...value,
    cluster_id: firstNonEmptyString(value.cluster_id, value.clusterId, value.id, value.key, value.name),
    name: safeDisplayName(firstNonEmptyString(value.name, value.label, value.title), '影响群簇'),
    primary_regions: uniqueList(asArray(value.primary_regions).map(String)),
    actor_ids: uniqueList(asArray(value.actor_ids).map(String)).map(item => Number(item) || item),
    dependency_profile: uniqueList(asArray(value.dependency_profile).map(String)),
    early_loss_signals: uniqueList(asArray(value.early_loss_signals).map(String))
  }
}

function normalizeRiskEvidenceItem(item, index = 0) {
  if (!item || typeof item !== 'object') return null
  return {
    ...item,
    title: safeDisplayText(item.title || item.name, `机制依据 ${index + 1}`),
    summary: safeDisplayText(item.summary || item.description, ''),
    epistemic_status_label: safeDisplayText(item.epistemic_status_label, '')
  }
}

function normalizeRiskMetricItem(item, index = 0) {
  if (!item || typeof item !== 'object') return null
  const label = safeDisplayText(item.label || item.name, `监测指标 ${index + 1}`)
  return {
    ...item,
    key: firstNonEmptyString(item.key, item.metric_key, `metric_${index + 1}`),
    label,
    thresholds: item.thresholds && typeof item.thresholds === 'object' ? item.thresholds : {}
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
    const ref = normalizeActorRef(item)
    return ref ? [ref] : []
  }).filter(Boolean).map(item => JSON.stringify(item))).map(item => JSON.parse(item))

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
  const evidenceStrengthScore = Number.isFinite(Number(raw.evidence_strength_score))
    ? Number(raw.evidence_strength_score)
    : Math.round(Math.max(0, Math.min(100, confidenceScore <= 1 ? confidenceScore * 100 : confidenceScore)))
  const statementSource = raw.risk_statement && typeof raw.risk_statement === 'object' ? raw.risk_statement : {}
  const statementRegions = asArray(statementSource.region_refs).flatMap(item => {
    const ref = normalizeRegionRef(item)
    return ref ? [ref] : []
  })
  const statementEntities = asArray(statementSource.entity_refs).flatMap(item => {
    const ref = normalizeEntityRef(item)
    return ref ? [ref] : []
  })
  const statementActors = asArray(statementSource.actor_refs).flatMap(item => {
    const ref = normalizeActorRef(item)
    return ref ? [ref] : []
  })
  const riskStatement = {
    ...statementSource,
    trigger_name: safeDisplayText(firstNonEmptyString(statementSource.trigger_name, rootPressures[0]), '场景触发因素'),
    source_node_ids: uniqueList(asArray(statementSource.source_node_ids).map(String)),
    receptor_node_ids: uniqueList(asArray(statementSource.receptor_node_ids).map(String)),
    receptor_name: safeDisplayText(firstNonEmptyString(statementSource.receptor_name, resolvedChainSteps.at(-1)), '主要受影响对象'),
    consequence: safeDisplayText(firstNonEmptyString(statementSource.consequence, raw.consequence, raw.summary), '等待具体后果说明。'),
    region_refs: statementRegions,
    entity_refs: statementEntities,
    actor_refs: statementActors
  }
  const monitoringMetrics = asArray(raw.monitoring_metrics)
    .map(normalizeRiskMetricItem)
    .filter(Boolean)

  return {
    ...raw,
    risk_object_id: firstNonEmptyString(raw.risk_id, raw.risk_object_id, raw.id, `risk_definition_${index + 1}`),
    risk_id: firstNonEmptyString(raw.risk_id, raw.risk_object_id, raw.id, `risk_definition_${index + 1}`),
    title: safeDisplayText(firstNonEmptyString(raw.title, raw.name, raw.label, raw.summary), `风险定义 ${index + 1}`),
    summary: safeDisplayText(firstNonEmptyString(raw.summary, raw.description, raw.summary_text), '场景定义完成后会在此展示风险链路摘要。'),
    why_now: safeDisplayText(firstNonEmptyString(raw.why_now, raw.trigger_summary, raw.summary), '当前风险定义已就绪，等待推演运行态刷新。'),
    risk_type: riskType,
    risk_contract_version: Number(raw.risk_contract_version) || 1,
    generation_mode: firstNonEmptyString(raw.generation_mode, 'legacy'),
    primary_family: firstNonEmptyString(raw.primary_family, riskType),
    primary_family_label: safeDisplayText(raw.primary_family_label, ''),
    tags: uniqueList(asArray(raw.tags).map(String)).slice(0, 8),
    mode,
    status: firstNonEmptyString(raw.status, 'tracked'),
    time_horizon: firstNonEmptyString(raw.time_horizon, raw.horizon, '30d'),
    region_scope: uniqueList(scopeRegions.map(item => item.region_name || item.region_id)),
    primary_regions: uniqueList([
      ...asArray(raw.primary_regions).map(value => normalizeRegionRef(value)?.region_name).filter(Boolean),
      ...scopeRegions.slice(0, 2).map(item => item.region_name || item.region_id)
    ]),
    severity_score: severityScore,
    impact_score: Number.isFinite(Number(raw.impact_score)) ? Number(raw.impact_score) : severityScore,
    evidence_strength_score: evidenceStrengthScore,
    confidence_score: confidenceScore,
    actionability_score: Number.isFinite(Number(raw.actionability_score))
      ? Number(raw.actionability_score)
      : Math.round(Math.max(0, Math.min(100, prioritySeed * 85))),
    novelty_score: Number.isFinite(Number(raw.novelty_score))
      ? Number(raw.novelty_score)
      : 0,
    root_pressures: rootPressures.map(item => safeDisplayText(item, '')).filter(Boolean),
    chain_steps: resolvedChainSteps,
    turning_points: turningPoints,
    amplifiers: uniqueList(asArray(raw.amplifiers).map(String)),
    buffers: uniqueList(asArray(raw.buffers).map(String)),
    source_entity_uuids: uniqueList(scopeEntities.map(item => item.entity_uuid)),
    source_actor_ids: uniqueList(scopeActors.map(item => item.actor_id)),
    source_actor_names: uniqueList(scopeActors.map(item => item.actor_name)),
    evidence: asArray(raw.evidence).map(normalizeRiskEvidenceItem).filter(Boolean),
    affected_clusters: asArray(raw.affected_clusters).map(normalizeClusterRef),
    intervention_options: interventionTemplates,
    scenario_branches: branchTemplates,
    mechanism_node_ids: uniqueList(asArray(raw.mechanism_node_ids).map(String)),
    mechanism_edge_ids: uniqueList(asArray(raw.mechanism_edge_ids).map(String)),
    monitoring_metrics: monitoringMetrics,
    quality_flags: uniqueList(asArray(raw.quality_flags).map(String)),
    source_signature: firstNonEmptyString(raw.source_signature),
    created_round: Number(raw.created_round) || 0,
    risk_statement: riskStatement,
    edge_ids: uniqueList([...collectRiskEdgeIds(raw, chainTemplate), ...asArray(raw.mechanism_edge_ids).map(String)]),
    scope_regions: uniqueList([...scopeRegions, ...statementRegions].map(item => JSON.stringify(item))).map(item => JSON.parse(item)),
    scope_entities: uniqueList([...scopeEntities, ...statementEntities].map(item => JSON.stringify(item))).map(item => JSON.parse(item)),
    scope_actors: uniqueList([...scopeActors, ...statementActors].map(item => JSON.stringify(item))).map(item => JSON.parse(item)),
    trigger_rules: raw.trigger_rules || {},
    priority_seed: prioritySeed,
    highlight_mode: 'risk_definition',
    source_kind: 'definition'
  }
}

function normalizeLegacyRiskObject(raw = {}, index = 0) {
  const confidenceScore = Number(raw.confidence_score || 0)
  const statementSource = raw.risk_statement && typeof raw.risk_statement === 'object' ? raw.risk_statement : {}
  const riskStatement = {
    ...statementSource,
    trigger_name: safeDisplayText(statementSource.trigger_name || asArray(raw.root_pressures)[0], '场景触发因素'),
    receptor_name: safeDisplayText(statementSource.receptor_name || asArray(raw.chain_steps).at(-1), '主要受影响对象'),
    consequence: safeDisplayText(statementSource.consequence || raw.consequence || raw.summary, '等待具体后果说明。')
  }
  const legacyRegions = [...asArray(raw.region_scope), ...asArray(raw.primary_regions)]
    .map(normalizeRegionRef)
    .filter(Boolean)
  return {
    ...raw,
    risk_object_id: firstNonEmptyString(raw.risk_object_id, raw.risk_id, raw.id, `risk_legacy_${index + 1}`),
    risk_id: firstNonEmptyString(raw.risk_id, raw.risk_object_id, raw.id, `risk_legacy_${index + 1}`),
    title: safeDisplayText(firstNonEmptyString(raw.title, raw.name), `风险对象 ${index + 1}`),
    summary: safeDisplayText(firstNonEmptyString(raw.summary, raw.description), '等待风险对象摘要。'),
    why_now: safeDisplayText(firstNonEmptyString(raw.why_now, raw.summary), '等待风险对象摘要。'),
    risk_type: firstNonEmptyString(raw.risk_type, raw.category, 'legacy'),
    risk_contract_version: Number(raw.risk_contract_version) || 1,
    generation_mode: firstNonEmptyString(raw.generation_mode, 'legacy'),
    primary_family: firstNonEmptyString(raw.primary_family, raw.risk_type, raw.category, 'other_emergent'),
    primary_family_label: safeDisplayText(raw.primary_family_label, ''),
    tags: uniqueList(asArray(raw.tags).map(String)).slice(0, 8),
    mode: firstNonEmptyString(raw.mode, 'watch'),
    status: firstNonEmptyString(raw.status, 'candidate'),
    time_horizon: firstNonEmptyString(raw.time_horizon, '30d'),
    region_scope: uniqueList(legacyRegions.map(item => item.region_name).filter(Boolean)),
    primary_regions: uniqueList(asArray(raw.primary_regions).map(value => normalizeRegionRef(value)?.region_name).filter(Boolean)).slice(0, 2),
    severity_score: normalizeScore(raw.severity_score),
    confidence_score: confidenceScore,
    evidence_strength_score: Number.isFinite(Number(raw.evidence_strength_score))
      ? Number(raw.evidence_strength_score)
      : Math.round(Math.max(0, Math.min(100, confidenceScore <= 1 ? confidenceScore * 100 : confidenceScore))),
    actionability_score: normalizeScore(raw.actionability_score),
    novelty_score: normalizeScore(raw.novelty_score),
    root_pressures: uniqueList(asArray(raw.root_pressures).map(item => safeDisplayText(item, '')).filter(Boolean)),
    chain_steps: uniqueList(asArray(raw.chain_steps).map(String)),
    turning_points: uniqueList(asArray(raw.turning_points).map(String)),
    amplifiers: uniqueList(asArray(raw.amplifiers).map(String)),
    buffers: uniqueList(asArray(raw.buffers).map(String)),
    source_entity_uuids: uniqueList(asArray(raw.source_entity_uuids).map(String)),
    source_actor_ids: uniqueList(asArray(raw.source_actor_ids).map(String)),
    source_actor_names: uniqueList(asArray(raw.source_actor_names).map(item => safeDisplayName(item, '')).filter(Boolean)),
    evidence: asArray(raw.evidence).map(normalizeRiskEvidenceItem).filter(Boolean),
    risk_statement: riskStatement,
    mechanism_node_ids: uniqueList(asArray(raw.mechanism_node_ids).map(String)),
    mechanism_edge_ids: uniqueList(asArray(raw.mechanism_edge_ids).map(String)),
    monitoring_metrics: asArray(raw.monitoring_metrics).map(normalizeRiskMetricItem).filter(Boolean),
    quality_flags: uniqueList(asArray(raw.quality_flags).map(String)),
    source_signature: firstNonEmptyString(raw.source_signature),
    created_round: Number(raw.created_round) || 0,
    affected_clusters: asArray(raw.affected_clusters).map(normalizeClusterRef),
    intervention_options: asArray(raw.intervention_options),
    scenario_branches: asArray(raw.scenario_branches),
    edge_ids: uniqueList([...asArray(raw.edge_ids), ...asArray(raw.edgeIds)].map(String)),
    scope_regions: legacyRegions,
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

const riskContractVersion = computed(() => {
  const objectVersion = Number(riskObjects.value[0]?.risk_contract_version)
  if (Number.isFinite(objectVersion) && objectVersion > 0) return objectVersion
  for (const source of riskSourceCandidates.value) {
    const version = Number(source?.risk_contract_version || source?.risk_manifest?.risk_contract_version)
    if (Number.isFinite(version) && version > 0) return version
  }
  return 1
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

const selectedRiskStatement = computed(() => selectedRiskObject.value?.risk_statement || {})
const selectedRiskEvidence = computed(() => selectedRiskObject.value?.evidence || [])
const selectedRiskMetrics = computed(() => selectedRiskObject.value?.monitoring_metrics || [])
const selectedRiskQualityLabels = computed(() => uniqueList(
  asArray(selectedRiskObject.value?.quality_flags)
    .map(item => displayToken(item, ''))
    .filter(Boolean)
))
const selectedRiskMechanismSteps = computed(() => {
  const steps = uniqueList(selectedRiskObject.value?.chain_steps || [])
  if (steps.length <= 2) return []
  return steps.slice(1, -1)
})

function riskFamilyLabel(item) {
  return safeDisplayText(item?.primary_family_label, '')
    || displayToken(item?.primary_family || item?.risk_type, '其他涌现风险')
}

function riskEvidenceScore(item) {
  const score = Number(item?.evidence_strength_score)
  if (Number.isFinite(score)) return Math.round(Math.max(0, Math.min(100, score)))
  const confidence = Number(item?.confidence_score)
  if (!Number.isFinite(confidence)) return 0
  return Math.round(Math.max(0, Math.min(100, confidence <= 1 ? confidence * 100 : confidence)))
}

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
      name: safeDisplayName(node.name || node.label, '关联主体'),
      labels: normalizeLabels(node.labels),
      provenance: node?.provenance || node?.attributes?.provenance || '',
      matched: true
    }
  })
})

const riskAffectedSubjectNodes = computed(() => {
  if (!selectedRiskObject.value) return []
  const statement = selectedRiskObject.value.risk_statement || {}
  const refs = [
    ...(statement.entity_refs || []).map(item => ({
      id: item.entity_uuid,
      name: item.entity_name,
      entityType: item.entity_type,
      summary: item.entity_summary,
      labels: item.labels,
      scopeBasis: item.scope_basis,
      epistemicStatus: item.epistemic_status,
      referenceKind: 'entity'
    })),
    ...(statement.actor_refs || []).map(item => ({
      id: item.actor_id,
      name: item.actor_name,
      entityType: item.actor_type || item.agent_type || item.node_family,
      summary: [item.matched_role_demand_label, item.profession].filter(Boolean).join(' · '),
      labels: item.labels,
      scopeBasis: item.scope_basis,
      epistemicStatus: item.epistemic_status,
      referenceKind: 'actor'
    })),
    ...(selectedRiskObject.value.scope_entities || []).map(item => ({
      id: item.entity_uuid,
      name: item.entity_name,
      entityType: item.entity_type,
      summary: item.entity_summary,
      labels: item.labels,
      scopeBasis: item.scope_basis,
      epistemicStatus: item.epistemic_status,
      referenceKind: 'entity'
    })),
    ...(selectedRiskObject.value.scope_actors || []).map(item => ({
      id: item.actor_id,
      name: item.actor_name,
      entityType: item.actor_type || item.agent_type || item.node_family,
      summary: [item.matched_role_demand_label, item.profession].filter(Boolean).join(' · '),
      labels: item.labels,
      scopeBasis: item.scope_basis,
      epistemicStatus: item.epistemic_status,
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
    const name = safeDisplayName(firstNonEmptyString(node?.name, node?.label, ref.name), '')
    if (!name || isInternalDisplayToken(name)) return []
    const referenceLabels = normalizeLabels([ref.entityType, ...asArray(ref.labels)])
    return [{
      id,
      uuid: node?.uuid || node?.id || ref.id || '',
      name,
      labels: referenceLabels.length > 0 ? referenceLabels : normalizeLabels(node?.labels),
      summary: safeDisplayText(firstNonEmptyString(ref.summary, node?.summary, node?.description), ''),
      provenance: node?.provenance || node?.attributes?.provenance || '',
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

  const scopeRegions = Array.isArray(selectedRiskObject.value.scope_regions) && selectedRiskObject.value.scope_regions.length > 0
    ? selectedRiskObject.value.scope_regions
    : (selectedRiskObject.value.risk_statement?.region_refs?.length
      ? selectedRiskObject.value.risk_statement.region_refs
      : uniqueList([
        ...(selectedRiskObject.value.primary_regions || []),
        ...(selectedRiskObject.value.region_scope || [])
      ]).map(name => ({ region_id: name, region_name: name })))

  return scopeRegions.flatMap((ref, index) => {
    const regionName = safeDisplayName(ref.region_name, '')
    if (!regionName || isInternalDisplayToken(regionName)) return []
    const tokenMatch = resolveGraphNodeByToken(ref.region_id) || resolveGraphNodeByToken(regionName)
    const matched = [
      ...(tokenMatch ? [tokenMatch] : []),
      ...(graphNodesByName.value.get(regionName.toLowerCase()) || []),
      ...(ref.region_id ? graphNodesByName.value.get(String(ref.region_id).toLowerCase()) || [] : [])
    ]
    const node = matched[0]
    const dedupeKey = String(node?.uuid || node?.id || regionName).trim().toLowerCase()
    if (!dedupeKey || seen.has(dedupeKey)) return []
    seen.add(dedupeKey)
    return {
      id: node?.uuid || `risk-region-${index}`,
      name: regionName,
      labels: normalizeLabels(node?.labels),
      scopeBasisLabel: scopeBasisLabel(ref.scope_basis),
      epistemicStatus: ref.epistemic_status || '',
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
      ...riskAffectedSubjectNodes.value.map(item => item.name),
      ...riskObjectRegionNodes.value.map(item => item.name)
    ]),
    edgeIds: uniqueList(selectedRiskObject.value.edge_ids || []),
    mode: selectedRiskObject.value.highlight_mode || selectedRiskObject.value.source_kind || selectedRiskObject.value.mode || 'risk_definition'
  }
})

const canPrepare = computed(() => {
  return Boolean(props.simulationId) &&
    Boolean(effortSnapshotId.value) &&
    eventInputs.value.length > 0 &&
    eventInputs.value.every(item => Boolean(String(item.name || '').trim())) &&
    !isPreparing.value &&
    (!isParameterLocked.value || phase.value === 'error')
})

const prepareActionLabel = computed(() => {
  if (!props.simulationId) return '等待图谱完成'
  if (!effortSnapshotId.value) return '正在读取投入快照'
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
  if (!effortSnapshotId.value) {
    return '正在读取第一步锁定的分析强度，加载完成后即可生成。'
  }
  if (isPreparing.value || phase.value === 'preparing') {
    return '正在生成正式代理体、区域、关系和风险配置。'
  }
  if (phase.value === 'ready') {
    return '当前显示风险对象、代理体、区域与关系；参数区保持锁定。'
  }
  if (phase.value === 'error') {
    return '输入和参数已保留，可以调整后重新生成。'
  }
  return '确认后会锁定当前参数，并开始生成后续展示内容。'
})

const prepareStageLabel = computed(() => {
  if (!props.simulationId) return '等待入口'
  if (phase.value === 'ready') return '场景结果'
  if (phase.value === 'preparing') return safeDisplayToken(prepareStage.value || 'processing', '处理中')
  if (phase.value === 'error') return '待调整'
  return '空闲'
})

const prepareMessageLabel = computed(() => {
  if (phase.value === 'error') return '输入已保留，可以修改后重新生成。'
  if (phase.value === 'preparing') return '正在生成事件机制、政策动作、空间范围和代理体配置。'
  if (phase.value === 'ready') return ''
  return '确认输入后生成可编辑的场景配置。'
})

const generationSteps = computed(() => {
  const progress = clamp(Number(prepareProgress.value) || 0, 0, 100)
  const definitions = [
    { label: '解析复合事件', note: '拆分用户输入并保留来源、顺序与作用对象', start: 0, end: 14 },
    { label: '构建机制与传播图', note: '组合原子机制，建立因果边与多介质传播分支', start: 14, end: 31 },
    { label: '生成时间和空间计划', note: '推导事件阶段、传播延迟、持续周期与作用范围', start: 31, end: 48 },
    { label: '提取角色能力需求', note: '形成角色需求，不预设代理体数量', start: 48, end: 62 },
    { label: '生成代理体与关系', note: '根据场景规划生成正式配置', start: 62, end: 85 },
    { label: '装配和校验场景', note: '校验中文展示与完整性，准备四个审阅视图', start: 85, end: 101 }
  ]
  return definitions.map((step, index) => ({
    ...step,
    index: String(index + 1).padStart(2, '0'),
    complete: progress >= step.end || progress === 100,
    current: progress >= step.start && progress < step.end
  }))
})

const payloadPreview = computed(() => {
  return JSON.stringify({
    simulation_id: props.simulationId,
    engine_mode: 'envfish',
    simulation_architecture: resolvedSimulationArchitecture.value,
    scenario_mode: scenarioMode.value,
    event_inputs: serializeEventInputs(),
    policy_inputs: serializePolicyInputs(),
    advanced_overrides: buildAdvancedOverrides(),
    effort_snapshot_id: effortSnapshotId.value || null
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
  const semanticKeys = new Set(
    variables.flatMap(variable => Array.isArray(variable?.atomicKeys) ? variable.atomicKeys : [])
  )
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

  const semanticTemplateRules = [
    { id: 'coastal_radioactive_release', all: ['marine_spread', 'radioactive_release'] },
    { id: 'radioactive_fallout', keys: ['air_spread'] },
    { id: 'industrial_toxic_release', keys: ['chemical_release'] },
    { id: 'inland_water_contamination', keys: ['river_spread', 'surface_spread'] },
    { id: 'earthquake_secondary_cascade', keys: ['earthquake', 'landslide', 'liquefaction', 'secondary_fire'] },
    { id: 'tsunami_inundation', keys: ['tsunami'] },
    { id: 'flood_storm_surge', keys: ['flood', 'storm_surge', 'heavy_rain'] }
  ]
  const semanticRule = semanticTemplateRules.find(rule => (
    Array.isArray(rule.all)
      ? rule.all.every(key => semanticKeys.has(key))
      : rule.keys.some(key => semanticKeys.has(key))
  ))
  const legacyRule = semanticKeys.size === 0
    ? rules.find((rule) => rule.tokens.some((token) => corpus.includes(token)))
    : null
  const template = hazardTemplates.find((item) => item.value === (semanticRule?.id || legacyRule?.id)) || hazardTemplates[hazardTemplates.length - 1]
  const hasInput = Boolean(corpus.trim())
  return {
    template,
    reasoning: hasInput
      ? `场景机制采用 ${template.label}。`
      : '场景机制采用通用生态压力链。'
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
  if (!userAdjustedTimePlan.value) {
    assignTimePlan(deriveAutomaticTimePlan(recommendation.template.value, injectedVariables.value), 'auto')
  }
}

function markTimePlanManual() {
  userAdjustedTimePlan.value = true
  timePlanMode.value = 'manual'
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
      prepareMessage.value = ''
    }
    return
  }

  if (phase.value === 'error') {
    hasSubmittedParameters.value = true
    prepareProgress.value = clamp(Number(prepareProgress.value) || 0, 0, 100)
    if (!prepareMessage.value) {
      prepareMessage.value = '输入已保留，可以修改后重新生成。'
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
    intent: '',
    targetText: '',
    targetRegionId: '',
    targetNodeId: '',
    advancedStartRound: '',
    advancedDurationRounds: '',
    advancedIntensity: '',
    sourceOrigin: 'manual'
  }
}

function normalizeExternalVariable(variable, index = 0, options = {}) {
  if (!variable || typeof variable !== 'object') return null
  if (isBaselineContextVariable(variable)) return null
  const rawType = String(variable.type || variable.input_type || variable.kind || '').toLowerCase()
  const type = rawType === 'policy' || rawType === 'policy_measure' || Boolean(variable.policy_mode || variable.policyMode)
    ? 'policy'
    : 'disaster'
  const targetRegions = Array.isArray(variable.target_region_ids)
    ? variable.target_region_ids
    : Array.isArray(variable.target_regions)
      ? variable.target_regions
      : Array.isArray(variable.targetRegions)
        ? variable.targetRegions
      : toDisplayString(variable.target_region || variable.targetRegion, '')
        ? [variable.target_region || variable.targetRegion]
        : []
  const targetNodes = Array.isArray(variable.target_entity_ids)
    ? variable.target_entity_ids
    : Array.isArray(variable.target_nodes)
      ? variable.target_nodes
      : Array.isArray(variable.targetNodes)
        ? variable.targetNodes
      : toDisplayString(variable.target_node || variable.targetNode, '')
        ? [variable.target_node || variable.targetNode]
        : []
  const sourceOrigin = toDisplayString(variable.source_origin || variable.sourceOrigin || options.sourceOrigin, options.sourceOrigin || 'manual')
  const sourceInputId = String(
    variable.source_input_id
    || variable.sourceInputId
    || variable.input_id
    || variable.variable_id
    || variable.event_id
    || variable.policy_id
    || variable.id
    || ''
  ).trim()
  const localPrefix = type === 'policy' ? 'policy:' : 'event:'
  const rawLocalId = String(variable.local_id || variable.localId || variable.id || sourceInputId || buildVariableId())
  const localId = rawLocalId.startsWith(localPrefix) ? rawLocalId : `${localPrefix}${rawLocalId}`

  return {
    id: localId,
    sourceInputId: sourceInputId || rawLocalId,
    type,
    name: safeDisplayName(variable.name || variable.title, `${type === 'policy' ? '政策措施' : '灾害事件'} ${index + 1}`),
    description: safeDisplayText(variable.description || variable.summary, ''),
    intent: safeDisplayText(variable.intent || variable.policy_intent || variable.description, ''),
    targetText: safeDisplayText(
      variable.target || variable.policy_target || variable.target_text || [
        ...targetRegions.map(item => toDisplayString(item, '')),
        ...targetNodes.map(item => toDisplayString(item, ''))
      ].filter(Boolean).join('、'),
      ''
    ),
    targetRegionId: toDisplayString(targetRegions[0], ''),
    targetNodeId: toDisplayString(targetNodes[0], ''),
    targetRegionIds: [...targetRegions],
    targetEntityIds: [...targetNodes],
    advancedStartRound: variable.advanced_start_round ?? variable.advancedStartRound ?? variable.start_round ?? variable.time?.start_round ?? '',
    advancedDurationRounds: variable.advanced_duration_rounds ?? variable.advancedDurationRounds ?? variable.duration_rounds ?? variable.time?.duration_rounds ?? '',
    advancedIntensity: variable.advanced_intensity ?? variable.advancedIntensity ?? variable.intensity_0_100 ?? variable.intensity?.score ?? '',
    intensityDirection: toDisplayString(variable.direction || variable.intensity?.direction, ''),
    intensityLabel: toDisplayString(variable.intensity_label || variable.intensity?.label_zh, ''),
    atomicKeys: Array.isArray(variable.atomic_keys) ? [...variable.atomic_keys] : [],
    openConcept: toDisplayString(variable.open_concept, ''),
    actionPrimitives: Array.isArray(variable.action_primitives) ? [...variable.action_primitives] : [],
    executorCapabilityKeys: Array.isArray(variable.executor_capability_keys) ? [...variable.executor_capability_keys] : [],
    expectedEffects: Array.isArray(variable.expected_effects) ? [...variable.expected_effects] : [],
    targetEventKeys: Array.isArray(variable.target_event_keys) ? [...variable.target_event_keys] : [],
    rawText: toDisplayString(variable.raw_text, ''),
    sourceOrigin,
    uiOrigin: toDisplayString(variable.ui_origin || variable.uiOrigin || options.sourceOrigin, sourceOrigin)
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

function applyPreparedInputs(eventSource, policySource, options = {}) {
  const events = (Array.isArray(eventSource) ? eventSource : []).map(item => ({ ...item, type: 'disaster' }))
  const policies = (Array.isArray(policySource) ? policySource : []).map(item => ({ ...item, type: 'policy' }))
  injectedVariables.value = buildInitialVariables([...events, ...policies], options)
  syncVariableSelections()
}

function serializeEventInput(variable, index) {
  const targetRegionIds = Array.from(new Set([
    ...(Array.isArray(variable.targetRegionIds) ? variable.targetRegionIds : []),
    variable.targetRegionId
  ].map(item => String(item || '').trim()).filter(Boolean)))
  const targetEntityIds = Array.from(new Set([
    ...(Array.isArray(variable.targetEntityIds) ? variable.targetEntityIds : []),
    variable.targetNodeId
  ].map(item => String(item || '').trim()).filter(Boolean)))
  return {
    input_id: variable.sourceInputId || variable.id,
    order: index + 1,
    name: resolveVariableDisplayName(variable),
    description: variable.description || '',
    target_region_ids: targetRegionIds,
    target_entity_ids: targetEntityIds,
    atomic_keys: Array.isArray(variable.atomicKeys) ? variable.atomicKeys : [],
    open_concept: variable.openConcept || '',
    expected_effects: Array.isArray(variable.expectedEffects) ? variable.expectedEffects : [],
    time: {
      start_round: variable.advancedStartRound === '' ? null : Number(variable.advancedStartRound),
      duration_rounds: variable.advancedDurationRounds === '' ? null : Number(variable.advancedDurationRounds)
    },
    intensity: {
      score: variable.advancedIntensity === '' ? null : Number(variable.advancedIntensity),
      direction: variable.intensityDirection || '',
      label_zh: variable.intensityLabel || ''
    },
    raw_text: variable.rawText || '',
    source_origin: variable.sourceOrigin || 'manual'
  }
}

function serializePolicyInput(variable, index) {
  const targetRegionIds = Array.from(new Set([
    ...(Array.isArray(variable.targetRegionIds) ? variable.targetRegionIds : []),
    variable.targetRegionId
  ].map(item => String(item || '').trim()).filter(Boolean)))
  const targetEntityIds = Array.from(new Set([
    ...(Array.isArray(variable.targetEntityIds) ? variable.targetEntityIds : []),
    variable.targetNodeId
  ].map(item => String(item || '').trim()).filter(Boolean)))
  return {
    input_id: variable.sourceInputId || variable.id,
    order: index + 1,
    name: resolveVariableDisplayName(variable),
    intent: variable.intent || '',
    target_region_ids: targetRegionIds,
    target_entity_ids: targetEntityIds,
    action_primitives: Array.isArray(variable.actionPrimitives) ? variable.actionPrimitives : [],
    executor_capability_keys: Array.isArray(variable.executorCapabilityKeys) ? variable.executorCapabilityKeys : [],
    expected_effects: Array.isArray(variable.expectedEffects) ? variable.expectedEffects : [],
    target_event_keys: Array.isArray(variable.targetEventKeys) ? variable.targetEventKeys : [],
    time: {
      start_round: variable.advancedStartRound === '' ? null : Number(variable.advancedStartRound),
      duration_rounds: variable.advancedDurationRounds === '' ? null : Number(variable.advancedDurationRounds)
    },
    intensity: {
      score: variable.advancedIntensity === '' ? null : Number(variable.advancedIntensity),
      direction: variable.intensityDirection || '',
      label_zh: variable.intensityLabel || ''
    },
    raw_text: variable.rawText || '',
    source_origin: variable.sourceOrigin || 'manual'
  }
}

function serializeEventInputs() {
  return eventInputs.value.map(serializeEventInput)
}

function serializePolicyInputs() {
  return policyInputs.value.map(serializePolicyInput)
}

function buildAdvancedOverrides() {
  if (timePlanMode.value !== 'manual') return {}
  const eventOverrides = Object.fromEntries(
    eventInputs.value.flatMap((event) => {
      const override = {}
      if (event.advancedStartRound !== '' && event.advancedStartRound !== null && event.advancedStartRound !== undefined) {
        override.start_round = Math.max(0, Number(event.advancedStartRound) || 0)
      }
      if (event.advancedDurationRounds !== '' && event.advancedDurationRounds !== null && event.advancedDurationRounds !== undefined) {
        override.duration_rounds = Math.max(1, Number(event.advancedDurationRounds) || 1)
      }
      if (event.advancedIntensity !== '' && event.advancedIntensity !== null && event.advancedIntensity !== undefined) {
        override.intensity = clamp(Number(event.advancedIntensity) || 0, 0, 100)
      }
      return Object.keys(override).length > 0 ? [[event.sourceInputId || event.id, override]] : []
    })
  )
  return {
    step_unit: timeStepUnit.value,
    step_value: Math.max(1, Number(timeStepSize.value) || 1),
    total_rounds: Math.max(4, Number(maxRounds.value) || 4),
    ...(Object.keys(eventOverrides).length ? { event_overrides: eventOverrides } : {})
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
  if (Number.isNaN(number)) return '暂无'
  if (number <= 1) return `${Math.round(number * 100)}%`
  return `${Math.round(Math.max(0, Math.min(100, number)))}%`
}

function formatInlineList(items, fallback = '—') {
  const values = uniqueList(Array.isArray(items) ? items : [])
  return values.length > 0
    ? values.map(item => displayToken(sanitizeDisplayCopy(item))).join(' · ')
    : fallback
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
    const label = localizedDisplayText(getNodeLabel(node, ''), `图谱对象 ${index + 1}`)
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
    const label = localizedDisplayText(agent?.displayName || agent?.username || agent?.handle, `代理体 ${index + 1}`)
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
  if (!normalized) return localizedDisplayText(value, '未知区域')
  const found = lookup.get(normalized)
  return found?.displayName || found?.name || found?.label || localizedDisplayText(value, '未知区域')
}

function resolveRegionKey(value, lookup) {
  const normalized = normalizeKey(value)
  if (!normalized) return ''
  const found = lookup.get(normalized)
  return found?.regionKey || found?.region_id || found?.regionId || normalized
}

function humanizeSnakeCase(value, fallback = '') {
  return displayToken(toDisplayString(value, fallback), fallback)
}

function displayToken(value, fallback = '') {
  return safeDisplayToken(value, fallback || '其他')
}

function localizedDisplayText(value, fallback = '') {
  return safeDisplayText(value, fallback)
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
  return map[normalized] || `${displayToken(raw, '其他')}层`
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
    },
    relation: {
      displayLabel: '关联',
      hint: '表示两个节点之间存在一条已知关系。'
    },
    relatedto: {
      displayLabel: '关联',
      hint: '表示两个节点之间存在一条已知关系。'
    },
    neighbor: {
      displayLabel: '相邻',
      hint: '表示两个区域在空间上相邻或存在边界联系。'
    },
    contains: {
      displayLabel: '包含',
      hint: '表示前者包含后者这一子区域、对象或层级。'
    },
    hostsagent: {
      displayLabel: '承载代理体',
      hint: '表示该区域或对象承载了对应代理体。'
    },
    anchorsagent: {
      displayLabel: '锚定代理体',
      hint: '表示代理体被锚定到该区域或对象。'
    },
    focuseson: {
      displayLabel: '关注',
      hint: '表示前者重点关注或监测后者。'
    },
    impactsactor: {
      displayLabel: '影响主体',
      hint: '表示前者对后者这一主体形成影响。'
    },
    informationtransfer: {
      displayLabel: '信息传递',
      hint: '表示预警、报告、通知或公开信息在主体之间流转。'
    },
    governanceregulation: {
      displayLabel: '治理调控',
      hint: '表示监管、调控、限制或治理动作会影响另一方。'
    },
    receptorexposure: {
      displayLabel: '受体暴露',
      hint: '表示人群、生态或产业受体暴露在某类压力或风险下。'
    },
    facilitydependency: {
      displayLabel: '设施依赖',
      hint: '表示主体依赖某项设施、服务、供应或基础系统。'
    },
    riskimpact: {
      displayLabel: '风险影响',
      hint: '表示灾害、污染或压力会影响另一对象。'
    },
    spatialassociation: {
      displayLabel: '空间关联',
      hint: '表示两个对象之间存在位置、邻接或空间范围关系。'
    },
    generalassociation: {
      displayLabel: '一般关联',
      hint: '表示两个节点之间存在关系，但当前数据没有给出更细类型。'
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
  const label = safeDisplayText(band.label, '')
  return {
    center,
    range,
    label: label && label !== '模型' ? label : '推断区间（非测量值）',
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
  if (!stateVector || typeof stateVector !== 'object') return '暂无状态'
  const exposure = normalizeScore(stateVector.exposure_score)
  const trust = normalizeScore(stateVector.public_trust)
  const stress = normalizeScore(stateVector.economic_stress || stateVector.vulnerability_score)
  if (!exposure && !trust && !stress) return '暂无状态'
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
    const displayName = localizedDisplayText(region?.name || region?.label || region?.title, `区域 ${index + 1}`)
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
      displayName,
      name: displayName,
      regionTypeLabel: humanizeSnakeCase(region?.region_type || region?.subregion_type || region?.layer || 'region', '区域'),
      layerLabel: formatLayerLabel(region?.layer),
      subregionLabel: humanizeSnakeCase(region?.subregion_type || region?.land_use_class || region?.distance_band || region?.region_type || 'general', '综合'),
      summary: localizedDisplayText(region?.description || region?.summary || region?.notes || region?.tags?.[0], '暂无区域描述'),
      tags: uniqueList(rawTags.map((item) => displayToken(item, '')).filter(Boolean)),
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
    const displayName = localizedDisplayText(node?.label || node?.name, `区域 ${index + 1}`)
    const rawTags = uniqueList([
      node?.type,
      node?.entity_type,
      node?.category,
      ...(node?.tags || [])
    ])
    return {
      regionKey,
      region_id: regionKey,
      displayName,
      name: displayName,
      regionTypeLabel: humanizeSnakeCase(node?.type || node?.entity_type || node?.category || 'region', '区域'),
      layerLabel: '图谱区域层',
      subregionLabel: '图谱节点',
      summary: localizedDisplayText(node?.description || node?.summary || node?.label, '来自图谱的区域骨架'),
      tags: uniqueList(rawTags.map((item) => displayToken(item, '')).filter(Boolean)),
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
  const archetypeFamily = archetypeFamilies[String(agent?.archetype_key || '').toLowerCase()]
  if (archetypeFamily) return archetypeFamily
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
  const candidates = uniqueList([
    ...toList(agent.home_region_id),
    ...toList(agent.primary_region),
    ...toList(agent.region_id),
    ...toList(agent.region),
    ...toList(agent.location),
    ...toList(agent.coverage_region_ids),
    ...toList(agent.influenced_regions)
  ])
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

  const fallbackValue = localizedDisplayText(candidates[0], '')
  return {
    key: normalizeKey(fallbackValue),
    label: fallbackValue || '跨区域主体'
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
    const displayName = localizedDisplayText(agent?.name || agent?.username || agent?.agent_name || agent?.entity_name, `代理体 ${index + 1}`)
    const rawAgentKey = agent?.agent_id ?? agent?.user_id ?? agent?.uuid ?? agent?.source_entity_uuid ?? agent?.username ?? displayName ?? `agent-${index}`
    const agentKey = normalizeKey(rawAgentKey)
    const capabilityLabels = uniqueList([
      ...(agent?.capabilities || []),
      ...(agent?.capability_keys || [])
    ].map(item => displayToken(item, '')).filter(Boolean))
    const permissionLabels = uniqueList((agent?.permission_keys || [])
      .map(item => displayToken(item, ''))
      .filter(Boolean))
    const actionLabels = uniqueList([
      ...(agent?.action_space_zh || []),
      ...(agent?.action_space || [])
    ].map(item => displayToken(item, '')).filter(Boolean))
    const resourceBudget = agent?.resource_budget && typeof agent.resource_budget === 'object'
      ? agent.resource_budget
      : {}
    const resourceUncertainty = agent?.resource_uncertainty && typeof agent.resource_uncertainty === 'object'
      ? agent.resource_uncertainty
      : {}
    const resourceRows = Object.entries(resourceBudget).map(([key, value]) => {
      const bounds = Array.isArray(resourceUncertainty[key]) ? resourceUncertainty[key] : []
      const range = bounds.length >= 2
        ? `，区间 ${Math.round(Number(bounds[0]) || 0)}–${Math.round(Number(bounds[1]) || 0)}`
        : ''
      return `${displayToken(key, '相对资源')} ${Math.round(Number(value) || 0)}${range}`
    })
    const profileConfidence = Number(agent?.profile_confidence ?? agent?.evidence_confidence ?? 0)
    const lifecycleStatus = agent?.runtime_lifecycle?.lifecycle_status || agent?.lifecycle_status || 'active'
    const representation = agent?.representation_level || (agent?.is_aggregate ? 'region_aggregate' : 'institution')
    const rawRoleType = String(agent?.role_type || '')
    const roleType = /^(?:entity|profile|actor|agent)$/i.test(rawRoleType)
      ? (agent?.archetype_key || family)
      : (rawRoleType || agent?.archetype_key || agent?.profession || agent?.node_family || 'profile')
    return {
      agentKey: agentKey || `agent-${index}`,
      agentId: agent?.agent_id ?? agent?.user_id ?? index,
      displayName,
      username: toDisplayString(agent?.username || agent?.agent_name || displayName, displayName),
      handle: agent?.username ? `@${agent.username}` : `@${normalizeKey(displayName) || `agent_${index + 1}`}`,
      agentTypeLabel: familyLabel(family),
      familyKey: family,
      familyLabel: familyLabel(family),
      familyClass: family,
      roleTypeLabel: displayToken(roleType, '档案'),
      archetypeLabel: displayToken(agent?.archetype_key || agent?.agent_subtype || agent?.role_type || family, familyLabel(family)),
      sourceLabel: '模拟配置',
      summary: localizedDisplayText(agent?.bio || agent?.persona || agent?.summary, `${displayName} 锚定于 ${primaryRegion.label}`),
      bio: localizedDisplayText(agent?.bio, ''),
      persona: localizedDisplayText(agent?.persona, ''),
      profession: displayToken(agent?.profession || agent?.role_type || agent?.node_family || familyLabel(family), familyLabel(family)),
      primaryRegionKey: primaryRegion.key,
      primaryRegionLabel: primaryRegion.label,
      primaryRegionText: primaryRegion.label,
      influencedRegionKeys: uniqueList(agent?.influenced_regions || []).map((item) => normalizeKey(item)),
      influencedRegionLabels: influencedRegions,
      influencedRegionsCount: influencedRegions.length,
      goals,
      sensitivities,
      capabilityLabels,
      permissionLabels,
      actionLabels,
      resourceRows,
      resourceSummary: resourceRows.length > 0
        ? `相对资源：${resourceRows.join('；')}`
        : '当前没有可核验的专属资源预算。',
      lifecycleStatusLabel: displayToken(lifecycleStatus, '活跃'),
      representationLabel: displayToken(representation, agent?.is_aggregate ? '区域聚合' : '机构主体'),
      profileConfidenceLabel: `${Math.round(Math.max(0, Math.min(1, profileConfidence)) * 100)}%`,
      isAggregate: Boolean(agent?.is_aggregate),
      roleDemandCount: uniqueList(agent?.role_demand_refs || []).length,
      evidenceCount: uniqueList(agent?.evidence_refs || []).length,
      spatialAnchorCount: uniqueList(agent?.spatial_anchor_refs || []).length,
      authorityEvidenceCount: uniqueList(agent?.authority_evidence_refs || []).length,
      createdRound: Math.max(0, Number(agent?.created_round) || 0),
      generationReason: localizedDisplayText(
        agent?.generation_reason || agent?.grounding_reason,
        '依据当前区域、角色需求与可核验能力生成。'
      ),
      stateVector: agent?.state_vector || {},
      stateSignal: summarizeStateVector(agent?.state_vector || {}),
      stateBand: bandFromScore(agent?.state_vector?.vulnerability_score || agent?.state_vector?.exposure_score),
      stanceLabel: deriveStanceLabel(agent),
      sourceEntityUuid: agent?.source_entity_uuid || '',
      sourceEntityType: displayToken(agent?.source_entity_type || '', ''),
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
      const displayName = localizedDisplayText(node?.label || node?.name, `图谱对象 ${index + 1}`)
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
        archetypeLabel: familyLabel(key),
        sourceLabel: '图谱预览',
        summary: localizedDisplayText(node?.description || node?.summary || node?.label, `${displayName} 由图谱骨架推断生成`),
        bio: localizedDisplayText(node?.description || node?.summary, ''),
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
        capabilityLabels: [],
        permissionLabels: [],
        actionLabels: [],
        resourceRows: [],
        resourceSummary: '图谱预览尚未生成正式资源预算。',
        lifecycleStatusLabel: '待正式建档',
        representationLabel: '图谱节点预览',
        profileConfidenceLabel: '待评估',
        isAggregate: false,
        roleDemandCount: 0,
        evidenceCount: 0,
        spatialAnchorCount: 0,
        authorityEvidenceCount: 0,
        createdRound: 0,
        generationReason: '由第一步图谱骨架提供预览，尚未经过正式角色需求与能力校验。',
        stateVector: node?.state_vector || {},
        stateSignal: summarizeStateVector(node?.state_vector || {}),
        stateBand: bandFromScore(node?.state_vector?.vulnerability_score || node?.state_vector?.exposure_score),
        stanceLabel: '中立',
        sourceEntityUuid: node?.uuid || node?.id || '',
        sourceEntityType: displayToken(node?.entity_type || node?.type || '', ''),
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

    const tagGroups = region.tagGroups || categorizeRegionTags(region.tags)
    const allTags = uniqueList(tagGroups.flatMap(group => group.items || []))
    const previewTags = allTags.slice(0, 2)
    return {
      regionKey: region.regionKey,
      displayName: region.displayName,
      summary: matchingAgents.length > 0
        ? `${matchingAgents.length} 个代理体锚定于此`
        : region.summary,
      agentCount: matchingAgents.length,
      agentNames: uniqueList(matchingAgents.map(agent => agent.displayName || agent.name).filter(Boolean)).slice(0, 8),
      topFamilies,
      neighbors: region.neighbors || [],
      neighborCount: region.neighborCount,
      regionTypeLabel: region.regionTypeLabel,
      layerLabel: region.layerLabel,
      subregionLabel: region.subregionLabel,
      tags: region.tags,
      description: region.summary || '暂无区域描述',
      tagGroups,
      visibleTagGroups: tagGroups.filter(group => (group.items || []).length > 0),
      previewTags,
      remainingTagCount: Math.max(0, allTags.length - previewTags.length),
      carriers: region.carriers,
      stateVector: region.stateVector,
      primaryRegionLabel: resolveRegionLabel(region.regionKey, regionLookup)
    }
  })
}

function getEdgeLabel(edge) {
  const candidates = [
    edge?.relation_label,
    edge?.relationLabel,
    edge?.relation_type,
    edge?.relationType,
    edge?.fact_type,
    edge?.factType,
    edge?.relation_kind,
    edge?.relationKind,
    edge?.relation,
    edge?.relationship,
    edge?.edge_type,
    edge?.edgeType,
    edge?.kind,
    edge?.type,
    edge?.label
  ]
  for (const candidate of candidates) {
    const label = displayToken(candidate, '')
    if (isUsableRelationLabel(label)) return label
  }
  const nameLabel = displayToken(edge?.name, '')
  if (isUsableRelationLabel(nameLabel) && /关系|关联|连接|影响|依赖|监管|上报|位于|包含|相邻|传导|流向|承载|锚定/.test(nameLabel)) {
    return nameLabel
  }
  return '关联'
}

function isGenericRelationLabel(label) {
  const normalized = normalizeKey(label)
  return !normalized || ['关联', '关系', '相关', 'related', 'relatedto', 'relation', 'relationship'].includes(normalized)
}

function isUsableRelationLabel(value) {
  const label = String(value || '').trim()
  if (!label) return false
  if (/^(未命名节点|未命名风险对象|未命名对象|未命名关系|其他类型|其他)$/.test(label)) return false
  if (/^(?:node|agent|entity|region|risk|feature)[_-]/i.test(label)) return false
  if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(label)) return false
  return true
}

function endpointFallback(prefix, index) {
  if (prefix === 'source' || prefix === 'from' || prefix === 'head' || prefix === 'start') {
    return `源节点 ${index + 1}`
  }
  return `目标节点 ${index + 1}`
}

function endpointCandidateValues(edge, prefix) {
  const nested = edge?.[prefix]
  const values = [
    edge?.[`${prefix}_name`],
    edge?.[`${prefix}Name`],
    edge?.[`${prefix}_label`],
    edge?.[`${prefix}Label`],
    edge?.[`${prefix}_title`],
    edge?.[`${prefix}Title`],
    edge?.[`${prefix}_node_name`],
    edge?.[`${prefix}NodeName`],
    edge?.[`${prefix}_entity_name`],
    edge?.[`${prefix}EntityName`],
    edge?.[`${prefix}_agent_name`],
    edge?.[`${prefix}AgentName`],
    edge?.[`${prefix}_display_name`],
    edge?.[`${prefix}DisplayName`],
    edge?.[`${prefix}_node_uuid`],
    edge?.[`${prefix}NodeUuid`],
    edge?.[`${prefix}_uuid`],
    edge?.[`${prefix}Uuid`],
    edge?.[`${prefix}_entity_uuid`],
    edge?.[`${prefix}EntityUuid`],
    edge?.[`${prefix}_agent_id`],
    edge?.[`${prefix}AgentId`],
    edge?.[`${prefix}_id`],
    edge?.[`${prefix}Id`]
  ]
  if (nested && typeof nested === 'object') {
    values.push(
      nested.display_name,
      nested.displayName,
      nested.name,
      nested.label,
      nested.title,
      nested.node_name,
      nested.nodeName,
      nested.entity_name,
      nested.entityName,
      nested.agent_name,
      nested.agentName,
      nested.uuid,
      nested.id,
      nested.node_id,
      nested.nodeId,
      nested.entity_uuid,
      nested.entityUuid,
      nested.agent_id,
      nested.agentId
    )
  } else {
    values.push(nested)
  }
  return values
}

function getEdgeEndpoint(edge, prefixes, lookup, index) {
  for (const prefix of prefixes) {
    for (const candidate of endpointCandidateValues(edge, prefix)) {
      const normalized = normalizeKey(candidate)
      if (!normalized) continue
      const lookupValue = lookup.get(normalized)
      const displayValue = lookupValue || safeDisplayName(candidate, '')
      if (displayValue) return displayValue
    }
  }
  return endpointFallback(prefixes[0], index)
}

function inferRelationDisplayLabel(edge, source, target, baseLabel) {
  if (!isGenericRelationLabel(baseLabel)) return baseLabel
  const text = [
    source,
    target,
    edge?.relation_label,
    edge?.relation_type,
    edge?.fact_type,
    edge?.name,
    edge?.kind,
    edge?.type,
    edge?.rationale,
    edge?.summary,
    edge?.description,
    edge?.interaction_channel,
    edge?.channel
  ].map(item => String(item || '')).join(' ')

  if (/预警|信息|发布|广播|通报|上报|报告|披露|通知/.test(text)) return 'information_transfer'
  if (/监管|监督|调控|管控|治理|水务|政府|部门|管理|限制|执法/.test(text)) return 'governance_regulation'
  if (/受体|暴露|居民|游客|农户|人群|生态|鸟类|栖息|渔业/.test(text)) return 'receptor_exposure'
  if (/排水|系统|医院|港口|电站|交通|地铁|设施|供应|服务|依赖|承载/.test(text)) return 'facility_dependency'
  if (/台风|风暴|洪水|污染|释放|灾害|风险|影响|扰动|压力/.test(text)) return 'risk_impact'
  if (/位于|所在|相邻|邻接|周边|锚定|承载于/.test(text)) return 'spatial_association'
  return 'general_association'
}

function summarizeRelations(edges) {
  const lookup = buildEntityLookup(graphNodes.value, agentCards.value)
  const labelCounts = new Map()
  const channelCounts = new Map()
  const sampleEdges = []
  let crossRegionCount = 0

  ;(edges || []).forEach((edge, index) => {
    const rawLabel = getEdgeLabel(edge)
    const source = getEdgeEndpoint(edge, ['source', 'from', 'head', 'start'], lookup, index)
    const target = getEdgeEndpoint(edge, ['target', 'to', 'tail', 'end'], lookup, index)
    const label = inferRelationDisplayLabel(edge, source, target, rawLabel)
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
    if (sampleEdges.length < 18) {
      const channelLabel = channel ? safeDisplayToken(channel, '') : ''
      // 清洗 rationale 句子里嵌入的内部渠道 token（如 governance_hierarchy）
      const rawRationale = toDisplayString(edge?.rationale || '', '')
      const localizedRationale = channel
        ? rawRationale.split(channel).join(translateDisplayToken(channel, channelLabel))
        : rawRationale
      const rationale = safeDisplayText(localizedRationale, relationMeta.hint)
      sampleEdges.push({
        key: `${label}-${index}`,
        label,
        displayLabel: relationMeta.displayLabel,
        hint: relationMeta.hint,
        summary: `${source} → ${target}`,
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
      .map(([label, count]) => ({ label, count, displayLabel: safeDisplayToken(label, '综合') }))
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

function addEventInput() {
  injectedVariables.value.push(createVariable('disaster'))
}

function compoundEventParts(event) {
  const description = String(event?.description || '').trim()
  const name = String(event?.name || '').trim()
  const source = description.length >= name.length ? description : name
  if (!source) return []
  return source
    .replace(/[。；;]/g, '｜')
    .replace(/(?:，|,)?\s*(随后|继而|进而|之后|并通过|并进一步|并导致|导致|造成|引发|从而|最终)\s*/g, '｜')
    .split('｜')
    .map(item => item.replace(/^(发生|出现|形成|使得|使)/, '').trim())
    .filter(item => item.length >= 2)
    .filter((item, index, values) => values.indexOf(item) === index)
}

function splitCompoundEventInput(id) {
  if (!canEditParameters.value) return
  const sourceIndex = injectedVariables.value.findIndex(item => item.id === id && item.type !== 'policy')
  if (sourceIndex < 0) return
  const source = injectedVariables.value[sourceIndex]
  const parts = compoundEventParts(source)
  if (parts.length <= 1) return
  const replacements = parts.map((part, index) => ({
    ...createVariable('disaster'),
    name: part.length > 28 ? `${part.slice(0, 28)}…` : part,
    description: part,
    targetRegionId: source.targetRegionId || '',
    targetNodeId: source.targetNodeId || '',
    sourceOrigin: index === 0 ? source.sourceOrigin : 'system_split'
  }))
  injectedVariables.value.splice(sourceIndex, 1, ...replacements)
}

function addPolicyInput() {
  injectedVariables.value.push(createVariable('policy'))
}

function removeInput(id) {
  const target = injectedVariables.value.find(variable => variable.id === id)
  if (target?.type !== 'policy' && eventInputs.value.length === 1) return
  injectedVariables.value = injectedVariables.value.filter(variable => variable.id !== id)
}

function moveEventInput(index, direction) {
  if (!canEditParameters.value) return
  const events = [...eventInputs.value]
  const nextIndex = index + direction
  if (index < 0 || nextIndex < 0 || nextIndex >= events.length) return
  ;[events[index], events[nextIndex]] = [events[nextIndex], events[index]]
  injectedVariables.value = [...events, ...policyInputs.value]
}

function inputPayloadRoot(payload) {
  return payload?.config && typeof payload.config === 'object' ? payload.config : (payload || {})
}

function hasPreparedInputPayload(payload) {
  const root = inputPayloadRoot(payload)
  return Array.isArray(root.event_inputs) || Array.isArray(root.policy_inputs)
}

function applyInputsFromPayload(payload, options = {}) {
  const root = inputPayloadRoot(payload)
  if (hasPreparedInputPayload(root)) {
    applyPreparedInputs(root.event_inputs || [], root.policy_inputs || [], options)
    return true
  }
  if (Array.isArray(root.injected_variables) && root.injected_variables.length > 0) {
    applyInjectedVariables(root.injected_variables, options)
    return true
  }
  return false
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
      applyInputsFromPayload(simulationSnapshot.value, { sourceOrigin: 'runtime' })
      if (simulationSnapshot.value?.scenario_mode) scenarioMode.value = simulationSnapshot.value.scenario_mode
      if (simulationSnapshot.value?.hazard_template_id) {
        applyHazardTemplate(simulationSnapshot.value, simulationSnapshot.value.hazard_template_mode || 'auto')
      }
      if (simulationSnapshot.value?.transport_profile?.primary_family) {
        diffusionTemplate.value = simulationSnapshot.value.transport_profile.primary_family
      }
      if (simulationSnapshot.value?.diffusion_template) diffusionTemplate.value = simulationSnapshot.value.diffusion_template
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
      applyInputsFromPayload(configRes.value.data, { sourceOrigin: 'runtime' })
      if (configRes.value.data.scenario_mode) scenarioMode.value = configRes.value.data.scenario_mode
      if (configRes.value.data.hazard_template_recommendation || configRes.value.data.hazard_template_id) {
        applyHazardTemplate(configRes.value.data.hazard_template_recommendation || configRes.value.data, configRes.value.data.hazard_template_mode || 'auto')
      }
      if (configRes.value.data.transport_profile?.primary_family) {
        diffusionTemplate.value = configRes.value.data.transport_profile.primary_family
      }
      if (configRes.value.data.diffusion_template) diffusionTemplate.value = configRes.value.data.diffusion_template
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
      applyInputsFromPayload(realtimeRes.value.data, { sourceOrigin: 'runtime' })
      if (realtimeRes.value.data.generation_stage_label || realtimeRes.value.data.current_stage_name || realtimeRes.value.data.generation_stage) {
        prepareStage.value = realtimeRes.value.data.generation_stage_label || realtimeRes.value.data.current_stage_name || realtimeRes.value.data.generation_stage
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
  if (!effortSnapshotId.value) {
    prepareMessage.value = '正在读取第一步锁定的分析强度，请稍后再试'
    addLog('场景配置未提交：尚未取得投入快照')
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
    `${autoTriggered ? '自动' : '手动'}提交 Kaleido 场景配置: ${eventInputs.value.length} 个灾害事件 / ${policyInputs.value.length} 项政策措施 / ${effortSnapshotLabel.value} / 内部 ${FIXED_SEARCH_MODE}`
  )

  try {
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      engine_mode: 'envfish',
      simulation_architecture: resolvedSimulationArchitecture.value,
      scenario_mode: scenarioMode.value,
      event_inputs: serializeEventInputs(),
      policy_inputs: serializePolicyInputs(),
      advanced_overrides: buildAdvancedOverrides(),
      effort_snapshot_id: effortSnapshotId.value || null,
      semantic_artifact_ref: props.sceneSeedContext?.semanticArtifactRef || undefined
    })

    if (res.success && res.data) {
      if (res.data.progress !== undefined) {
        prepareProgress.value = clamp(Number(res.data.progress) || 0, 0, 100)
      }
      if (res.data.generation_stage_label || res.data.generation_stage) {
        prepareStage.value = res.data.generation_stage_label || res.data.generation_stage
      }
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
      if (res.data.already_prepared) {
        prepareProgress.value = 100
        prepareMessage.value = ''
        addLog('✓ 场景配置已存在，直接复用')
        await bootstrapSimulation()
        phase.value = 'ready'
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
      prepareMessage.value = '输入已保留，可以修改后重新生成。'
      emit('update-status', 'error')
      addLog(`✗ 场景配置提交失败: ${res.error || '未知错误'}`)
    }
  } catch (err) {
    phase.value = 'error'
    prepareMessage.value = '输入已保留，可以修改后重新生成。'
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
        prepareProgress.value = 100
        prepareMessage.value = ''
        emit('update-status', 'completed')
        addLog('✓ Kaleido 场景配置完成')
        stopTimers()
        await fetchConfigRealtime()
        phase.value = 'ready'
      } else if (data.status === 'failed' || data.status === 'cancelled') {
        phase.value = 'error'
        prepareMessage.value = '输入已保留，可以修改后重新生成。'
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
      applyInputsFromPayload(res.data, { sourceOrigin: 'runtime' })
      if (res.data.generation_stage_label || res.data.current_stage_name || res.data.generation_stage) {
        prepareStage.value = res.data.generation_stage_label || res.data.current_stage_name || res.data.generation_stage
      }
      if (res.data.progress !== undefined) prepareProgress.value = clamp(Number(res.data.progress) || 0, 0, 100)
      if (res.data.message) prepareMessage.value = res.data.message
      if (res.data.scenario_mode) scenarioMode.value = res.data.scenario_mode
      if (res.data.hazard_template_recommendation || res.data.hazard_template_id) {
        applyHazardTemplate(res.data.hazard_template_recommendation || res.data, res.data.hazard_template_mode || hazardTemplateMode.value)
      }
      if (res.data.transport_profile?.primary_family) diffusionTemplate.value = res.data.transport_profile.primary_family
      if (res.data.diffusion_template) diffusionTemplate.value = res.data.diffusion_template
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
    diffusionTemplate: diffusionTemplate.value,
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
    eventCount: eventInputs.value.length,
    policyCount: policyInputs.value.length,
    eventInputs: serializeEventInputs(),
    policyInputs: serializePolicyInputs(),
    advancedOverrides: buildAdvancedOverrides(),
    effortSnapshotId: effortSnapshotId.value || undefined
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
  () => props.initialInjectedVariables,
  (value) => {
    const hasPersistedInputs = hasPreparedInputPayload(configSnapshot.value) ||
      Boolean(configSnapshot.value?.injected_variables?.length)
    const hasRealtimeInputs = hasPreparedInputPayload(configRealtime.value) ||
      Boolean(inputPayloadRoot(configRealtime.value)?.injected_variables?.length)
    if (!hasPersistedInputs && !hasRealtimeInputs) {
      applyInjectedVariables(value, { sourceOrigin: 'seed' })
    }
  },
  { deep: true }
)

watch(
  () => props.simulationId,
  async (value, previousValue) => {
    if (!value || value === previousValue) return
    prepareMessage.value = '场景配置入口'
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
    if (visible && !['risk', 'region', 'agents', 'relations'].includes(activeWorkspaceTab.value)) {
      activeWorkspaceTab.value = 'risk'
    }
    if (!visible) showLockedInputs.value = false
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
  selectedRiskObjectId,
  () => {
    revealSelectedRiskObject()
  },
  { flush: 'post' }
)

watch(
  () => riskObjects.value.length,
  async () => {
    await nextTick()
    syncRiskSelectorScrollState()
  },
  { flush: 'post' }
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

function handleStep2Keydown(event) {
  if (event.key === 'Escape' && showLockedInputs.value) showLockedInputs.value = false
}

function handleStep2Resize() {
  syncRiskSelectorScrollState()
}

onMounted(async () => {
  window.addEventListener('keydown', handleStep2Keydown)
  window.addEventListener('resize', handleStep2Resize)
  addLog('Kaleido Step2 初始化')
  await bootstrapSimulation()
  if (props.simulationId) emitPhaseStatus()
  await revealSelectedRiskObject()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleStep2Keydown)
  window.removeEventListener('resize', handleStep2Resize)
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
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(88, 159, 255, 0.18), transparent 32%),
    radial-gradient(circle at top right, rgba(28, 196, 135, 0.16), transparent 30%),
    linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
  color: #132033;
}

.hero,
.workspace-shell,
.progress-shell,
.configuration-action-bar {
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
  background: #ffffff;
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
  flex: 1;
  min-height: 0;
  border-radius: 24px;
  padding: 18px;
  overflow-x: hidden;
  overflow-y: auto;
}

/* ===== Step 2 信息架构：配置输入 → 系统生成 → 结果审阅 ===== */
.setup-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 28px;
  padding: 4px 2px 2px;
}

.setup-header h2,
.preparing-copy h2 {
  margin: 6px 0 8px;
  color: #173056;
  font-size: 24px;
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.setup-header p,
.preparing-copy p {
  max-width: 640px;
  margin: 0;
  color: #5d687f;
  font-size: 13px;
  line-height: 1.6;
}

.setup-header-meta {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.effort-lock-badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 6px 10px;
  border: 1px solid rgba(56, 94, 166, 0.18);
  border-radius: 999px;
  background: #eef3ff;
  color: #345287;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.setup-step-marker {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}

.setup-step-marker span {
  padding: 7px 10px;
  border-radius: 10px;
  background: #f1f4f7;
  color: #8791a4;
  font-size: 11px;
  font-weight: 700;
}

.setup-step-marker .is-current {
  background: #173056;
  color: #ffffff;
}

.prepare-error {
  padding: 13px 15px;
  border-left: 3px solid #c45b43;
  border-radius: 8px 14px 14px 8px;
  background: #fff4f0;
  color: #7e372b;
}

.prepare-error p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

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
.review-header-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
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

.briefing-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  user-select: none;
}

.static-head {
  cursor: default;
}

.static-head > div {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.section-order {
  color: #9c7038;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.parameter-stage {
  padding-top: 18px;
  border-top: 1px solid rgba(20, 33, 61, 0.09);
}

.primary-condition-section {
  margin-top: 18px;
  padding: 17px;
  border: 0;
  border-radius: 16px;
  background: #faf8f3;
  box-shadow: inset 3px 0 0 #9c7038;
}

.policy-input-section {
  margin-top: 18px;
  padding: 17px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 16px;
  background: #f6f8fb;
}

.parameter-stage-head {
  align-items: flex-start;
}

.parameter-stage-head > div:first-child {
  max-width: 620px;
}

.parameter-stage-head h3 {
  margin: 5px 0 0;
  color: #173056;
  font-size: 16px;
}

.parameter-stage-head p {
  margin: 6px 0 0;
  color: #687489;
  font-size: 12px;
  line-height: 1.5;
}

.parameter-stage-head .action-row {
  flex: none;
  margin-top: 0;
}

.stable-context-section {
  padding: 12px 14px;
  border-radius: 13px;
  background: #f6f7f8;
}

.scene-goal-section {
  margin-top: 16px;
  border: 1px solid rgba(20, 33, 61, 0.08);
}

.stable-context-section .panel-title-row {
  margin-bottom: 10px;
}

.time-range-section {
  margin-top: 20px;
}

.automatic-plan-section {
  margin-top: 18px;
  padding: 17px;
  border: 1px solid rgba(52, 82, 135, 0.12);
  border-radius: 16px;
  background: #f8f9fc;
}

.automatic-plan-grid,
.scenario-plan-review {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.automatic-plan-grid article,
.scenario-plan-review article {
  padding: 12px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 13px;
  background: #ffffff;
}

.automatic-plan-grid article.has-generated-plan {
  border-color: rgba(23, 76, 58, 0.18);
  background: #f7fbf8;
}

.automatic-plan-grid span,
.scenario-plan-review span {
  display: block;
  color: #8490a5;
  font-size: 10px;
  letter-spacing: 0.06em;
}

.automatic-plan-grid strong,
.scenario-plan-review strong {
  display: block;
  margin-top: 6px;
  color: #233a5c;
  font-size: 12px;
  line-height: 1.45;
}

.automatic-plan-grid p {
  margin: 6px 0 0;
  color: #6c778b;
  font-size: 11px;
  line-height: 1.5;
}

.scenario-plan-review {
  display: flex;
  gap: 0;
  margin-bottom: 12px;
  overflow-x: auto;
  border-block: 1px solid rgba(20, 33, 61, 0.08);
}

.scenario-plan-review article {
  min-width: 145px;
  flex: 1 0 0;
  padding: 9px 12px;
  border: 0;
  border-right: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 0;
}

.scenario-plan-review article:last-child {
  border-right: 0;
}

.event-override-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.event-override-list article {
  padding: 12px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 13px;
  background: #ffffff;
}

.event-override-list article > strong {
  display: block;
  margin-bottom: 10px;
  color: #233a5c;
  font-size: 12px;
}

.event-override-list .field-row {
  margin-bottom: 0;
}

.advanced-strategy {
  overflow: hidden;
  border: 1px solid rgba(20, 33, 61, 0.1);
  border-radius: 15px;
  background: #f8f9fa;
}

.advanced-strategy-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  cursor: pointer;
  list-style: none;
  transition: background 0.18s ease;
}

.advanced-strategy-summary::-webkit-details-marker {
  display: none;
}

.advanced-strategy-summary:hover {
  background: #f2f4f6;
}

.advanced-strategy-summary:focus-visible {
  outline: 2px solid #2d5be3;
  outline-offset: -2px;
}

.advanced-strategy-summary strong,
.advanced-strategy-summary small {
  display: block;
}

.advanced-strategy-summary strong {
  margin-top: 4px;
  color: #233a5c;
  font-size: 14px;
}

.advanced-strategy-summary small {
  margin-top: 4px;
  color: #7b8498;
  font-size: 10px;
}

.advanced-strategy-toggle {
  flex: none;
  color: #52647d;
  font-size: 0;
  font-weight: 700;
}

.advanced-strategy-toggle::after {
  content: '展开设置';
  font-size: 11px;
}

.advanced-strategy[open] .advanced-strategy-toggle::after {
  content: '收起设置';
}

.advanced-strategy-body {
  padding: 2px 16px 16px;
  border-top: 1px solid rgba(20, 33, 61, 0.08);
  background: #ffffff;
}

.advanced-subsection {
  padding-top: 16px;
}

.advanced-subsection + .advanced-subsection {
  margin-top: 16px;
  border-top: 1px solid rgba(20, 33, 61, 0.07);
}

.advanced-subsection .panel-title-row {
  margin-bottom: 10px;
}

.locked-input-sheet {
  position: fixed;
  top: 60px;
  right: 0;
  bottom: 0;
  z-index: 60;
  width: min(520px, 100%);
  overflow-y: auto;
  padding: 22px;
  border: 1px solid rgba(20, 33, 61, 0.09);
  border-radius: 0;
  background: #f7f8f6;
  box-shadow: -22px 0 64px rgba(20, 33, 61, 0.16);
}

.locked-input-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.locked-input-head h3 {
  margin: 5px 0 0;
  color: #173056;
  font-size: 16px;
}

.text-btn {
  border: 0;
  background: transparent;
  color: #4a607c;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.locked-input-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.locked-input-grid > div,
.locked-variable-list article {
  padding: 11px 12px;
  border-radius: 12px;
  background: #ffffff;
}

.locked-input-grid span,
.locked-variable-list span {
  display: block;
  color: #8490a5;
  font-size: 10px;
}

.locked-input-grid strong,
.locked-variable-list strong {
  display: block;
  margin-top: 5px;
  color: #233a5c;
  font-size: 12px;
}

.snapshot-id {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #8a94a6;
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.locked-variable-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.locked-variable-list p {
  margin: 5px 0 0;
  color: #66738a;
  font-size: 11px;
  line-height: 1.45;
}

.preparing-workspace {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 100%;
  max-width: 760px;
  width: 100%;
  margin: auto;
  padding: 24px 4px 36px;
}

.preparing-progress {
  margin-top: 34px;
}

.generation-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}

.generation-steps li {
  display: flex;
  gap: 9px;
  padding: 12px;
  border-radius: 13px;
  background: #f2f4f6;
  color: #9099a9;
}

.generation-steps li > span {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  font-weight: 800;
}

.generation-steps strong,
.generation-steps small {
  display: block;
}

.generation-steps strong {
  color: inherit;
  font-size: 12px;
}

.generation-steps small {
  margin-top: 5px;
  font-size: 10px;
  line-height: 1.4;
}

.generation-steps li.is-current {
  background: #e9f0fb;
  color: #214d84;
  box-shadow: inset 0 0 0 1px rgba(33, 77, 132, 0.16);
}

.generation-steps li.is-complete {
  background: #eef5ef;
  color: #426e50;
}

.graph-waiting-guide {
  margin-top: 18px;
  padding: 14px 16px;
  border-left: 3px solid #9c7038;
  border-radius: 8px 14px 14px 8px;
  background: #f7f3eb;
}

.graph-waiting-guide strong {
  color: #5f4a2d;
  font-size: 13px;
}

.graph-waiting-guide p {
  margin: 5px 0 0;
  color: #7d6c55;
  font-size: 12px;
  line-height: 1.5;
}

.result-tabs {
  position: sticky;
  top: -18px;
  z-index: 4;
  padding: 10px 0 8px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(20, 33, 61, 0.08);
}

.result-tabs :deep(.k-workflow-tabs__list) {
  gap: 4px;
  padding-bottom: 0;
  border-bottom: 0;
}

.result-tabs :deep(.k-workflow-tabs__tab) {
  min-width: 0;
  min-height: 58px;
  padding: 10px 11px;
  border-radius: 8px;
  text-align: left;
}

.result-tabs :deep(.k-workflow-tabs__label) {
  font-size: 13px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.result-tabs :deep(.k-workflow-tabs__meta) {
  overflow: hidden;
  font-size: 10px;
  line-height: 1.3;
  opacity: 0.72;
  overflow-wrap: anywhere;
  white-space: normal;
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
  background: #ffffff;
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
  background: #eef4ff;
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
  background: #ffffff;
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
  background: #ffffff;
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
  background: #eef4ff;
}

.auto-template-card {
  border-radius: 18px;
  border: 1px solid rgba(47, 110, 255, 0.22);
  background: #ffffff;
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
  background: #ffffff;
}

.variable-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.event-order-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 6px;
}

.event-order-actions button {
  border: 0;
  border-radius: 10px;
  padding: 7px 9px;
  background: rgba(24, 48, 88, 0.06);
  color: #41516b;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 700;
}

.event-order-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.4;
}

.event-order-actions .remove-btn {
  color: #8d3f3f;
}

.event-input-card > label,
.policy-input-card > label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 11px;
  color: #4e5b70;
  font-size: 12px;
  font-weight: 700;
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
.relation-grid {
  display: grid;
  gap: 12px;
}

.region-grid,
.relation-grid {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
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

.relation-edge-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.relation-edge-row {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(76px, 0.28fr) minmax(260px, 1.1fr);
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(20, 33, 61, 0.06);
}

.relation-edge-row strong {
  overflow: hidden;
  color: #16315a;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.relation-edge-row .relation-edge-type {
  color: #5d687f;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}

.relation-edge-row small {
  overflow: hidden;
  color: #7b86a0;
  font-size: 11px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  display: block;
}

.risk-selector-shell {
  display: block;
}

.risk-selector-shell.has-overflow-controls {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) 30px;
  gap: 7px;
  align-items: center;
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
  background: #fff;
  color: var(--step-accent-strong, #174c3a);
  font: inherit;
  font-size: 20px;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, opacity 160ms ease;
}

.risk-selector-nav:hover:not(:disabled) {
  border-color: var(--step-accent, #1f5d45);
  background: var(--k-color-brand-050, #f3f7f4);
}

.risk-selector-nav:focus-visible {
  outline: 2px solid var(--step-accent, #1f5d45);
  outline-offset: 2px;
}

.risk-selector-nav:disabled {
  cursor: default;
  opacity: 0.3;
}

.risk-preview-list {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(160px, 1fr);
  gap: 8px;
  max-width: 100%;
  overflow-x: auto;
  scroll-behavior: smooth;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
}

.risk-preview-list::-webkit-scrollbar {
  display: none;
}

.risk-preview-list.is-short-list {
  grid-auto-flow: initial;
  grid-template-columns: repeat(var(--risk-short-count), minmax(0, 1fr));
  overflow-x: hidden;
  scroll-snap-type: none;
}

.node-list,
.cluster-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.risk-preview-card {
  width: 100%;
  min-width: 0;
  min-height: 78px;
  text-align: left;
  border-radius: 10px;
  border: 1px solid rgba(20, 33, 61, 0.1);
  background: #ffffff;
  padding: 10px 12px;
  cursor: pointer;
  scroll-snap-align: start;
  transition: background 0.18s ease, border-color 0.18s ease;
}

.risk-preview-card:hover,
.risk-preview-card.active {
  border-color: rgba(31, 93, 69, 0.45);
}

.risk-preview-card.active {
  background: var(--k-color-brand-050, #f3f7f4);
}

.risk-selector-head,
.risk-detail-top,
.risk-score-strip,
.node-card-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.risk-selector-head {
  justify-content: flex-start;
  gap: 5px;
  color: #6d7d74;
  font-size: 10px;
  line-height: 1.2;
  white-space: nowrap;
}

.risk-selector-index {
  color: var(--step-accent-strong, #174c3a);
  font-variant-numeric: tabular-nums;
  font-weight: 800;
}

.risk-selector-primary {
  margin-left: auto;
  color: var(--step-accent-strong, #174c3a);
  font-weight: 800;
}

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

.risk-preview-card strong,
.risk-preview-detail h3 {
  display: block;
  margin-top: 6px;
  color: #16315a;
}

.risk-preview-card strong {
  display: -webkit-box;
  min-height: 2.7em;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.risk-selector-meta {
  display: block;
  margin-top: 5px;
  overflow: hidden;
  color: #6d7d74;
  font-size: 10px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  margin-top: 12px;
  padding-top: 14px;
  border-top: 1px solid rgba(20, 33, 61, 0.08);
}

.risk-causal-chain {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) 18px minmax(0, 1.1fr) 18px minmax(0, 0.9fr) 18px minmax(0, 1.4fr);
  gap: 8px;
  align-items: stretch;
  max-width: 100%;
  overflow: visible;
}

.risk-causal-node {
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(20, 33, 61, 0.1);
  border-radius: 8px;
  background: #ffffff;
}

.risk-causal-node.mechanism {
  border-color: rgba(31, 93, 69, 0.2);
  background: var(--k-color-brand-050, #f3f7f4);
}

.risk-causal-node.consequence {
  border-color: rgba(31, 93, 69, 0.2);
  background: var(--k-color-brand-050, #f3f7f4);
}

.risk-causal-node > span,
.risk-quality-row > span {
  display: block;
  margin-bottom: 7px;
  color: #7382a3;
  font-size: 11px;
  font-weight: 700;
}

.risk-causal-node strong {
  display: block;
  overflow-wrap: anywhere;
  color: #183058;
  font-size: 13px;
  line-height: 1.45;
}

.risk-causal-arrow {
  align-self: center;
  color: var(--step-accent, #1f5d45);
  font-size: 17px;
  font-weight: 800;
}

.risk-object-tags,
.risk-quality-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.risk-quality-row {
  align-items: baseline;
  padding-top: 10px;
  border-top: 1px solid rgba(20, 33, 61, 0.08);
}

.risk-quality-row > span {
  margin: 0;
}

.risk-quality-row p {
  margin: 0;
  color: #5f6f66;
  font-size: 11px;
  line-height: 1.5;
}

.risk-eyebrow {
  color: #4f69a5;
}

.risk-note-box,
.risk-mini-panel {
  padding: 12px 0 0;
  border: 0;
  border-top: 1px solid rgba(20, 33, 61, 0.1);
  border-radius: 0;
  background: transparent;
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
  padding: 10px 0;
  border-block: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 0;
  background: transparent;
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
  display: block;
  margin-top: 3px;
}

.risk-step-list strong {
  display: block;
  margin: 0;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: #183058;
  font-size: 11px;
  font-weight: 700;
}

.risk-step-list strong + strong {
  margin-top: 5px;
  padding-top: 5px;
  border-top: 1px solid rgba(31, 93, 69, 0.12);
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
.cluster-mini-card,
.risk-evidence-item,
.risk-metric-item {
  padding: 10px 0;
  border: 0;
  border-bottom: 1px solid rgba(20, 33, 61, 0.08);
  border-radius: 0;
  background: transparent;
}

.node-card:last-child,
.cluster-mini-card:last-child,
.risk-evidence-item:last-child,
.risk-metric-item:last-child {
  border-bottom: 0;
}

.risk-evidence-list,
.risk-metric-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.risk-evidence-item p {
  margin: 7px 0 0;
  color: #5e6782;
  font-size: 12px;
  line-height: 1.5;
}

.node-card-summary {
  margin: 7px 0 0;
  color: #5e6782;
  font-size: 12px;
  line-height: 1.5;
}

.node-card-head > strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.node-meta-line {
  display: flex;
  min-width: 0;
  gap: 0;
  margin-top: 5px;
  overflow: hidden;
  color: #6d7d74;
  font-size: 10px;
  line-height: 1.35;
  white-space: nowrap;
}

.node-meta-line span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-meta-line span + span::before {
  content: "·";
  margin: 0 5px;
  color: #a4afa8;
}

.evidence-status {
  flex: none;
  color: #6d7d74;
  font-size: 10px;
  white-space: nowrap;
}

.risk-metric-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.risk-metric-item strong {
  color: #183058;
  font-size: 12px;
}

.risk-metric-item span {
  color: #687793;
  font-size: 11px;
  text-align: right;
}

.empty-state.compact {
  padding: 10px;
  border-radius: 8px;
  font-size: 12px;
}

.node-state {
  flex: none;
  border: 1px solid rgba(31, 93, 69, 0.22);
  background: transparent;
  color: var(--step-accent-strong, #174c3a);
  white-space: nowrap;
}

.node-state.matched {
  border-color: rgba(31, 93, 69, 0.28);
  background: transparent;
  color: var(--step-accent-strong, #174c3a);
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

.configuration-action-bar {
  position: sticky;
  bottom: 0;
  z-index: 8;
  display: flex;
  flex: none;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 13px 16px;
  border-radius: 18px;
  box-shadow: 0 -8px 28px rgba(17, 31, 59, 0.08);
}

.configuration-action-bar .action-row {
  flex-wrap: nowrap;
  margin-top: 0;
}

.action-summary span,
.action-summary strong {
  display: block;
}

.action-summary span {
  color: #7b8498;
  font-size: 10px;
}

.action-summary strong {
  margin-top: 4px;
  color: #233a5c;
  font-size: 12px;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

@media (max-width: 1280px) {
  .risk-node-grid {
    grid-template-columns: minmax(0, 1fr);
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

  .locked-input-grid,
  .generation-steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .setup-header,
  .briefing-header,
  .parameter-stage-head,
  .configuration-action-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .setup-step-marker,
  .review-header-actions,
  .parameter-stage-head .action-row {
    justify-content: flex-start;
  }

  .briefing-stats {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }

  .variable-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .risk-detail-top {
    align-items: stretch;
    flex-direction: column;
  }

  .risk-score-strip {
    width: 100%;
  }

  .event-order-actions {
    width: 100%;
  }

  .configuration-action-bar .action-row {
    justify-content: stretch;
  }

  .configuration-action-bar .action-row button {
    flex: 1;
  }
}

/* 统一为 Kaleido 绿色工作台：蓝色仅来自旧规则，此处集中收口。 */
.envfish-step {
  --step-accent: var(--k-color-brand-600, #1f5d45);
  --step-accent-strong: var(--k-color-brand-700, #174c3a);
  --step-text: var(--k-color-text, #10231d);
  --step-muted: var(--k-color-text-muted, #6d7d74);
  --step-border: var(--k-color-border, #dce4df);
  padding: 14px;
  gap: 12px;
  color: var(--step-text);
  background: var(--k-color-page, #f4f6f3);
}

.workspace-shell,
.configuration-action-bar,
.hero,
.progress-shell {
  border-color: var(--step-border);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 28px rgba(28, 59, 46, 0.07);
}

.workspace-shell {
  gap: 13px;
  padding: 16px;
  border-radius: 18px;
}

.setup-header h2,
.preparing-copy h2,
.briefing-title,
.briefing-stat strong,
.panel-title-row h3,
.region-section-head h3,
.risk-detail-top h3,
.summary-card strong,
.action-summary strong,
.metric-value,
.workspace-copy h3,
.region-table-row strong,
.region-detail-drawer h3,
.region-detail-drawer h4 {
  color: var(--step-text);
}

.setup-header p,
.preparing-copy p,
.briefing-summary-line,
.briefing-stats-label,
.hint,
.catalog-title,
.action-summary span,
.region-section-head p,
.region-table-text,
.region-detail-drawer p,
.region-detail-drawer dt,
.region-no-tag {
  color: var(--step-muted);
}

.effort-lock-badge,
.setup-step-marker span,
.chip,
.grounding-item,
.empty-chip,
.variable-index,
.mode-tag,
.template-badge,
.risk-mode-tag,
.risk-family-tag,
.risk-primary-tag,
.node-state,
.mini-tag,
.runtime-status-tag,
.runtime-turning-tag {
  border: 1px solid rgba(31, 93, 69, 0.24);
  background: transparent;
  color: var(--step-accent-strong);
  box-shadow: none;
}

.setup-step-marker .is-current,
.generation-steps li.is-current {
  border-color: var(--step-accent);
  background: var(--k-color-brand-050, #f3f7f4);
  color: var(--step-accent-strong);
  box-shadow: inset 0 0 0 1px rgba(31, 93, 69, 0.1);
}

.summary-card,
.metric-card,
.automatic-plan-grid article,
.scenario-plan-review article,
.variable-card,
.mode-card,
.template-card,
.auto-template-card,
.node-card,
.cluster-mini-card,
.risk-evidence-item,
.risk-metric-item,
.risk-preview-card,
.relation-edge-row,
.grounding-box,
.payload-box {
  border-color: var(--step-border);
  background: var(--k-color-surface, #fff);
}

.panel,
.workspace-panel,
.risk-preview-shell {
  border-color: var(--step-border);
  background: var(--k-color-surface, #fff);
  box-shadow: none;
}

.primary-btn {
  border: 1px solid var(--step-accent);
  background: var(--step-accent);
  color: #fff;
}

.secondary-btn,
.ghost-btn,
.remove-btn {
  border: 1px solid var(--step-border);
  background: #fff;
  color: var(--step-text);
}

.primary-btn:hover,
.secondary-btn:hover,
.ghost-btn:hover,
.risk-preview-card:hover,
.mode-card:hover,
.template-card:hover {
  border-color: var(--step-accent);
  box-shadow: 0 8px 20px rgba(28, 59, 46, 0.1);
}

.mode-card.active,
.template-card.active,
.risk-preview-card.active,
.node-card.active {
  border-color: rgba(31, 93, 69, 0.45);
  background: var(--k-color-brand-050, #f3f7f4);
  box-shadow: none;
}

.configuration-action-bar {
  bottom: 0;
  border-radius: 14px;
  box-shadow: 0 -8px 24px rgba(28, 59, 46, 0.08);
}

.step2-action-bar {
  flex: 0 0 auto;
  width: auto;
  margin: -12px -14px -14px;
}

/*
 * The right workbench is already the page surface. Keep this element as the
 * single scroll boundary, but do not draw a second rounded card around it.
 */
.envfish-step2 > .workspace-shell {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.region-section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.region-section-head h3,
.region-section-head p {
  margin: 0;
}

.region-section-head p {
  margin-top: 5px;
  font-size: 12px;
}

.region-coverage-note {
  flex: none;
  padding: 4px 8px;
  border: 1px solid rgba(31, 93, 69, 0.24);
  border-radius: 999px;
  color: var(--step-accent-strong);
  font-size: 11px;
  font-weight: 700;
}

.region-baseline-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 9px 11px;
  overflow-x: auto;
  border: 1px solid var(--step-border);
  border-radius: 10px;
  background: var(--k-color-surface-subtle, #f7f9f7);
  color: var(--step-muted);
  font-size: 11px;
  white-space: nowrap;
}

.region-baseline-label,
.region-baseline-item strong {
  color: var(--step-text);
  font-weight: 700;
}

.region-baseline-source {
  margin-left: auto;
}

.region-table-shell {
  overflow-x: auto;
  border: 1px solid var(--step-border);
  border-radius: 12px;
  background: #fff;
}

.region-table-head,
.region-table-row {
  display: grid;
  grid-template-columns: minmax(180px, 1.6fr) 90px 86px 70px minmax(150px, 1fr) 48px;
  align-items: center;
  gap: 10px;
  min-width: 780px;
  padding: 10px 12px;
}

.region-table-head {
  border-bottom: 1px solid var(--step-border);
  background: var(--k-color-surface-subtle, #f7f9f7);
  color: var(--step-muted);
  font-size: 10px;
  font-weight: 700;
}

.region-table-row {
  width: 100%;
  border: 0;
  border-bottom: 1px solid var(--step-border);
  background: #fff;
  color: var(--step-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.region-table-row:last-child { border-bottom: 0; }
.region-table-row:hover { background: var(--k-color-brand-050, #f3f7f4); }
.region-table-row:focus-visible { outline: 2px solid var(--step-accent); outline-offset: -2px; }

.region-identity-cell {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 2px 8px;
  align-items: baseline;
}

.region-identity-cell small { grid-row: 1 / span 2; color: var(--step-muted); }
.region-identity-cell strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.region-identity-cell em { color: var(--step-muted); font-size: 10px; font-style: normal; }

.region-table-number strong { font-size: 15px; }
.region-table-number small { margin-left: 3px; color: var(--step-muted); }
.region-preview-tags { display: flex; min-width: 0; gap: 5px; overflow: hidden; }
.region-row-action { color: var(--step-accent); font-size: 11px; font-weight: 700; text-align: right; }

.agent-category-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 11px;
  border: 1px solid var(--step-border);
  border-radius: 10px;
  background: var(--k-color-surface-subtle, #f7f9f7);
  color: var(--step-muted);
  font-size: 11px;
}

.agent-category-summary span {
  flex: none;
  color: var(--step-text);
  font-weight: 700;
}

.agent-category-summary strong {
  min-width: 0;
  color: var(--step-muted);
  font-size: 11px;
  font-weight: 500;
}

.agent-table-shell {
  overflow-x: auto;
  border: 1px solid var(--step-border);
  border-radius: 12px;
  background: #fff;
}

.agent-plan-audit {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 10px 0 14px;
  overflow: hidden;
  border: 1px solid var(--step-border);
  border-radius: 8px;
  background: var(--step-border);
}

.agent-plan-audit > div {
  min-width: 0;
  padding: 10px 12px;
  background: #fff;
}

.agent-plan-audit span,
.agent-plan-audit strong {
  display: block;
}

.agent-plan-audit span {
  color: var(--step-muted);
  font-size: 10px;
}

.agent-plan-audit strong {
  margin-top: 4px;
  color: var(--step-text);
  font-size: 15px;
}

.agent-plan-audit > p {
  grid-column: 1 / -1;
  margin: 0;
  padding: 8px 12px;
  background: var(--k-color-brand-050, #f3f7f4);
  color: var(--step-muted);
  font-size: 11px;
  line-height: 1.5;
}

.agent-plan-unresolved {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 9px 12px 10px;
  background: #fffaf0;
  color: #7a5630;
  font-size: 11px;
  line-height: 1.45;
}

.agent-plan-unresolved strong {
  margin: 0;
  color: #5f3e17;
  font-size: 11px;
}

.agent-plan-unresolved span {
  color: #7a5630;
}

.agent-table-head,
.agent-table-row {
  display: grid;
  grid-template-columns: 64px minmax(180px, 1.5fr) minmax(110px, 0.8fr) minmax(140px, 1fr) 44px;
  align-items: center;
  gap: 10px;
  min-width: 620px;
  padding: 10px 12px;
}

.agent-table-head {
  border-bottom: 1px solid var(--step-border);
  background: var(--k-color-surface-subtle, #f7f9f7);
  color: var(--step-muted);
  font-size: 10px;
  font-weight: 700;
}

.agent-table-body {
  min-width: 620px;
  max-height: min(34vh, 280px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.agent-table-entry {
  border-bottom: 1px solid var(--step-border);
  background: #fff;
}

.agent-table-entry:last-child {
  border-bottom: 0;
}

.agent-table-entry.is-expanded {
  background: var(--k-color-brand-050, #f3f7f4);
}

.agent-table-row {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--step-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 160ms ease;
}

.agent-table-row:hover {
  background: var(--k-color-brand-050, #f3f7f4);
}

.agent-table-row:focus-visible {
  outline: 2px solid var(--step-accent);
  outline-offset: -2px;
}

.agent-table-index {
  color: var(--step-muted);
  font-size: 11px;
}

.agent-table-name,
.agent-table-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-table-name {
  color: var(--step-text);
  font-size: 13px;
  font-weight: 700;
}

.agent-table-text {
  color: var(--step-muted);
  font-size: 12px;
}

.agent-row-action {
  color: var(--step-accent);
  font-size: 11px;
  font-weight: 700;
  text-align: right;
}

.agent-table-detail {
  padding: 12px 12px 14px 86px;
  border-top: 1px solid rgba(31, 93, 69, 0.12);
}

.agent-table-detail p {
  margin: 0;
  color: var(--step-muted);
  font-size: 12px;
  line-height: 1.6;
}

.agent-profile-badges,
.agent-profile-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-profile-badges {
  margin-top: 10px;
}

.agent-profile-badges span,
.agent-profile-chip-row span {
  padding: 4px 7px;
  border: 1px solid rgba(31, 93, 69, 0.14);
  border-radius: 999px;
  background: #fff;
  color: var(--step-text);
  font-size: 10px;
  line-height: 1.2;
}

.agent-profile-chip-row span.is-empty {
  color: var(--step-muted);
}

.agent-table-detail dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 12px 0 0;
}

.agent-table-detail dl div {
  min-width: 0;
}

.agent-table-detail dt,
.agent-table-detail dd {
  margin: 0;
}

.agent-profile-sections {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(31, 93, 69, 0.12);
}

.agent-profile-sections section {
  min-width: 0;
}

.agent-profile-sections h4 {
  margin: 0 0 8px;
  color: var(--step-text);
  font-size: 11px;
}

.agent-profile-sections section > p {
  margin-top: 8px;
  font-size: 11px;
}

.agent-profile-sections .agent-profile-basis {
  grid-column: 1 / -1;
}

.agent-profile-basis small {
  display: block;
  margin-top: 6px;
  color: var(--step-muted);
  font-size: 10px;
}

.agent-table-detail dt {
  color: var(--step-muted);
  font-size: 10px;
}

.agent-table-detail dd {
  margin-top: 4px;
  overflow: hidden;
  color: var(--step-text);
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 620px;
  padding: 10px 12px;
  border-top: 1px solid var(--step-border);
  background: var(--k-color-surface-subtle, #f7f9f7);
  color: var(--step-muted);
  font-size: 11px;
}

.agent-pagination > div {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-pagination strong {
  color: var(--step-text);
  font-variant-numeric: tabular-nums;
}

.agent-pagination button {
  border: 1px solid var(--step-border);
  border-radius: 7px;
  padding: 6px 9px;
  background: #fff;
  color: var(--step-text);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease;
}

.agent-pagination button:hover:not(:disabled) {
  border-color: var(--step-accent);
  background: var(--k-color-brand-050, #f3f7f4);
}

.agent-pagination button:focus-visible {
  outline: 2px solid var(--step-accent);
  outline-offset: 2px;
}

.agent-pagination button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.region-drawer-backdrop {
  position: fixed;
  inset: 60px 0 0;
  z-index: 70;
  border: 0;
  background: rgba(16, 35, 29, 0.26);
}

.region-detail-drawer {
  position: fixed;
  top: 60px;
  right: 0;
  bottom: 0;
  z-index: 71;
  width: min(460px, 92vw);
  padding: 20px;
  overflow-y: auto;
  border-left: 1px solid var(--step-border);
  background: #fff;
  box-shadow: -18px 0 46px rgba(28, 59, 46, 0.16);
}

.region-drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--step-border);
}

.region-drawer-head h3 { margin: 4px 0 0; }
.region-drawer-head p { margin: 4px 0 0; font-size: 12px; }
.region-drawer-close { border: 1px solid var(--step-border); border-radius: 8px; padding: 7px 10px; background: #fff; color: var(--step-text); cursor: pointer; }
.region-drawer-summary { line-height: 1.65; }

.region-detail-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 16px 0;
}

.region-detail-metrics div { padding: 10px; border: 1px solid var(--step-border); border-radius: 10px; }
.region-detail-metrics dt { font-size: 10px; }
.region-detail-metrics dd { margin: 5px 0 0; color: var(--step-text); font-weight: 700; }
.region-detail-block { padding: 13px 0; border-top: 1px solid var(--step-border); }
.region-detail-block h4 { margin: 0; font-size: 12px; }
.region-detail-block p { margin: 6px 0 0; line-height: 1.65; }

/* 风险定义保持“选择—链路—依据”的单一阅读层级，避免旧卡片层层套叠。 */
.risk-preview-card:hover,
.risk-preview-card.active {
  box-shadow: none;
}

.risk-score-strip {
  flex: none;
  align-items: stretch;
  gap: 0;
}

.risk-score-strip .summary-card {
  min-width: 86px;
  padding: 2px 12px;
  border: 0;
  border-left: 1px solid var(--step-border);
  border-radius: 0;
  background: transparent;
}

.risk-score-strip .summary-card span {
  color: var(--step-muted);
  font-size: 10px;
  letter-spacing: 0;
  text-transform: none;
}

.risk-score-strip .summary-card strong {
  margin-top: 3px;
  color: var(--step-text);
  font-size: 17px;
}

.risk-mini-panel .node-card,
.risk-mini-panel .risk-evidence-item,
.risk-mini-panel .risk-metric-item {
  border-color: var(--step-border);
  background: transparent;
}

.risk-mini-panel .catalog-title {
  color: var(--step-text);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: none;
}

@media (max-width: 760px) {
  .envfish-step { padding: 8px; }
  .workspace-shell { padding: 12px; }
  .region-section-head { flex-direction: column; }
  .region-detail-metrics { grid-template-columns: 1fr; }
  .agent-category-summary,
  .agent-pagination {
    align-items: flex-start;
    flex-direction: column;
  }
  .agent-table-detail {
    padding-left: 12px;
  }
  .agent-table-detail dl {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .agent-plan-audit,
  .agent-profile-sections {
    grid-template-columns: 1fr;
  }
  .agent-profile-sections .agent-profile-basis {
    grid-column: auto;
  }
}

/* Step 2 typography contract shared with the other workflow workbenches. */
.envfish-step2 {
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.setup-header h2,
.preparing-copy h2,
.briefing-title {
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
}

.panel-title-row h3,
.region-section-head h3,
.risk-detail-top h3,
.workspace-copy h3,
.region-detail-drawer h3 {
  font-size: var(--k-text-section);
  line-height: var(--k-leading-ui);
}

.briefing-stat strong,
.risk-score-strip .summary-card strong,
.metric-value {
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
}

.briefing-kicker,
.effort-lock-badge,
.hint,
.catalog-title,
.section-order,
.summary-card span,
.risk-selector-head,
.risk-selector-meta,
.region-detail-metrics dt {
  font-size: var(--k-text-caption);
  line-height: var(--k-leading-ui);
}

.briefing-summary-line,
.setup-header p,
.preparing-copy p,
.risk-detail-top p,
.region-drawer-summary,
.region-detail-block p {
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.result-tabs :deep(.k-workflow-tabs__label),
.primary-btn,
.secondary-btn,
.ghost-btn,
.text-btn {
  font-size: var(--k-text-ui);
  line-height: var(--k-leading-ui);
}

.result-tabs :deep(.k-workflow-tabs__meta),
.action-summary span {
  font-size: var(--k-text-meta);
  line-height: var(--k-leading-ui);
}

.scenario-plan-review span,
.risk-score-strip .summary-card span,
.node-state,
.node-meta-line,
.evidence-status {
  font-size: var(--k-text-caption);
  line-height: var(--k-leading-ui);
}
</style>
