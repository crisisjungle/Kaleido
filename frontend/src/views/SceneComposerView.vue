<template>
  <KaleidoWorkflowShell
    class="scene-composer-page"
    :step="1"
    step-name="背景定义"
    :status-text="stepStatusText"
    :status-tone="stepStatusTone"
    :view-mode="viewMode"
    :visual-ratio="56"
    collapse-label="收起地图"
    expand-label="展开地图"
    @toggle-visual="toggleMapCollapse"
  >
      <section class="setup-column">
        <div class="setup-scroll" :class="{ 'has-report': showReportStage }">
          <section v-if="isCuratedShowcase && !showReportStage" class="panel curated-foundation-state">
            <div class="curated-foundation-state-inner">
              <h2>{{ curatedFoundationLoading ? '正在恢复武汉背景' : '武汉背景暂未加载' }}</h2>
              <p>{{ curatedFoundationLoading ? '正在读取已锁定的地点、时间、系统基线、事实资料和研究边界。' : curatedFoundationError }}</p>
              <button
                v-if="!curatedFoundationLoading"
                class="primary-btn"
                type="button"
                @click="loadCuratedFoundation"
              >
                重新加载武汉背景
              </button>
            </div>
          </section>

          <section v-else-if="!showReportStage" class="panel setup-panel" :class="{ 'compact-mode': !showReportStage }">
            <div class="setup-form">
              <div class="foundation-section-heading">
                <span>01</span>
                <div><strong>空间范围</strong><small>确认研究对象真正发生在哪里</small></div>
              </div>
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

              <div class="foundation-section-heading">
                <span>02</span>
                <div><strong>系统基线</strong><small>描述事件发生前的常态结构和约束</small></div>
              </div>
              <label class="field field-grow">
                <span>当前系统基线</span>
                <textarea
                  v-model="form.eventOrBaseline"
                  rows="4"
                  placeholder="说明这个地点在当前时间背景下的常态结构、生态基线、活动节奏和关键约束。"
                ></textarea>
              </label>

              <div class="foundation-section-heading">
                <span>03</span>
                <div><strong>事实与资料</strong><small>补充可验证的来源、主体、设施和环境对象</small></div>
              </div>
              <div class="field">
                <span>上传参考文档（选填）</span>
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

              <label class="field">
                <span>已知主体 / 设施 / 环境对象（选填）</span>
                <textarea
                  v-model="form.knownEntities"
                  rows="4"
                  placeholder="- 社区居民、游客、环卫部门&#10;- 医院、污水厂、港口、地铁站&#10;- 河流、湿地、海岸带、栖息地"
                ></textarea>
              </label>

              <div class="foundation-section-heading">
                <span>04</span>
                <div><strong>研究问题与边界</strong><small>说明希望回答什么，以及明确不分析什么</small></div>
              </div>
              <section class="advanced-panel research-boundary-panel">
                <label class="field">
                  <span>研究问题、关注对象与排除范围（选填）</span>
                  <textarea
                    v-model="form.additionalContext"
                    rows="6"
                    placeholder="关注的关系/问题、已知背景与事实、分析边界与排除项、希望报告重点回答的问题——都写在这里即可。&#10;例：&#10;- 关注游客活动、滨海生态与公园管理之间的关系&#10;- 只分析当前片区稳态，不扩展到全市&#10;- 希望报告回答：哪些生态受体最敏感、哪些扰动最先打破平衡"
                  ></textarea>
                </label>

                <label v-if="advancedOpen" class="field">
                  <span>准备在下一步设计的场景目标</span>
                  <textarea
                    v-model="form.simulationRequirement"
                    rows="3"
                    placeholder="例：围绕滨海公园高峰期人流、设施负荷与生态受体之间的扰动传播进行推演。"
                  ></textarea>
                </label>

              </section>
            </div>

            <div class="setup-actions">
              <p v-if="message" class="message">{{ message }}</p>

              <div class="button-row setup-action-row">
                <button class="advanced-toggle setup-advanced-toggle" type="button" @click="advancedOpen = !advancedOpen">
                  {{ advancedOpen ? '收起研究边界' : '补充研究边界' }}
                </button>

                <div class="setup-primary-actions">
                  <details ref="effortMenuRef" class="effort-menu" @keydown.esc.stop="closeEffortMenu">
                  <summary
                    class="effort-trigger"
                    :title="`分析强度：${effortLabel}`"
                    :aria-label="`分析强度：${effortLabel}`"
                  >
                    <svg class="brain-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none">
                      <path d="M9.5 4A2.5 2.5 0 0 1 12 6.5v11a2.5 2.5 0 0 1-4.96.44A2.5 2.5 0 0 1 6.5 13H6a2.5 2.5 0 0 1-.8-4.87A3 3 0 0 1 9.5 4Z" />
                      <path d="M14.5 4A2.5 2.5 0 0 0 12 6.5v11a2.5 2.5 0 0 0 4.96.44A2.5 2.5 0 0 0 17.5 13h.5a2.5 2.5 0 0 0 .8-4.87A3 3 0 0 0 14.5 4Z" />
                      <path d="M9 13h3M12 6.5h2M6.5 13H9M5.2 8.13H8M14 17.5h3M14 13h3.5M14 8.5h4" />
                    </svg>
                    <span class="effort-trigger-label">分析强度</span>
                    <span class="effort-trigger-value">{{ effortLabel }}</span>
                    <svg class="effort-chevron" aria-hidden="true" viewBox="0 0 16 16" fill="none">
                      <path d="m4 6 4 4 4-4" />
                    </svg>
                  </summary>

                  <div class="effort-popover" @click.stop>
                    <div class="effort-popover-head">
                      <span>分析强度</span>
                      <span class="effort-current-level">
                        <svg class="brain-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none">
                          <path d="M9.5 4A2.5 2.5 0 0 1 12 6.5v11a2.5 2.5 0 0 1-4.96.44A2.5 2.5 0 0 1 6.5 13H6a2.5 2.5 0 0 1-.8-4.87A3 3 0 0 1 9.5 4Z" />
                          <path d="M14.5 4A2.5 2.5 0 0 0 12 6.5v11a2.5 2.5 0 0 0 4.96.44A2.5 2.5 0 0 0 17.5 13h.5a2.5 2.5 0 0 0 .8-4.87A3 3 0 0 0 14.5 4Z" />
                          <path d="M9 13h3M12 6.5h2M6.5 13H9M5.2 8.13H8M14 17.5h3M14 13h3.5M14 8.5h4" />
                        </svg>
                        <strong>{{ effortLabel }}</strong>
                      </span>
                    </div>

                    <div class="effort-track-shell">
                      <div class="effort-track-rail" aria-hidden="true">
                        <div class="effort-track-fill" :style="{ width: effortFillWidth }"></div>
                      </div>
                      <input
                        class="effort-slider"
                        type="range"
                        min="0"
                        :max="EFFORT_OPTIONS.length - 1"
                        step="1"
                        :value="effortIndex"
                        :disabled="effortLocked"
                        aria-label="分析强度"
                        :aria-valuetext="effortLabel"
                        @input="handleEffortSliderInput"
                      />
                      <span
                        v-for="(option, index) in EFFORT_OPTIONS"
                        :key="option.value"
                        class="effort-track-dot"
                        :class="{ 'is-active': index <= effortIndex }"
                        aria-hidden="true"
                      ></span>
                    </div>
                  </div>
                  </details>

                  <button class="primary-btn" type="button" :disabled="composeDisabled" @click="composeBackground">
                    {{ backgroundActionLabel }}
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section v-else class="panel report-panel" :class="{ 'is-generating': composing }">
            <div class="panel-head report-panel-head">
              <div class="report-title-row">
                <button v-if="composing || hasComposeError" class="icon-back-btn" type="button" @click="returnToSetup" title="返回参数设置">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline></svg>
                </button>
                <h2>{{ isCuratedShowcase ? '武汉案例基础' : '背景基础审阅' }}</h2>
              </div>
              <div class="panel-head-actions">
                <span v-if="effortLocked" class="effort-lock-badge">
                  <svg class="brain-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none">
                    <path d="M9.5 4A2.5 2.5 0 0 1 12 6.5v11a2.5 2.5 0 0 1-4.96.44A2.5 2.5 0 0 1 6.5 13H6a2.5 2.5 0 0 1-.8-4.87A3 3 0 0 1 9.5 4Z" />
                    <path d="M14.5 4A2.5 2.5 0 0 0 12 6.5v11a2.5 2.5 0 0 0 4.96.44A2.5 2.5 0 0 0 17.5 13h.5a2.5 2.5 0 0 0 .8-4.87A3 3 0 0 0 14.5 4Z" />
                    <path d="M9 13h3M12 6.5h2M6.5 13H9M5.2 8.13H8M14 17.5h3M14 13h3.5M14 8.5h4" />
                  </svg>
                  分析强度 {{ effortLabel }} · 已锁定
                </span>
                <span class="status-pill">{{ isCuratedShowcase ? '只读案例' : reportStageLabel }}</span>
              </div>
            </div>

            <div class="report-content-scroll" :class="{ 'is-curated': isCuratedShowcase }">
            <div v-if="isCuratedShowcase" class="curated-foundation-summary">
              <div><strong>108</strong><span>天历史窗口</span></div>
              <div><strong>6</strong><span>个城市系统</span></div>
              <div><strong>36</strong><span>个空间锚点</span></div>
              <p>公开事实约束日期与地点；主体行动、关系和连续状态为明确标注的策划推演。</p>
            </div>

            <section v-if="isCuratedShowcase" class="curated-locked-inputs" aria-label="武汉案例已锁定背景输入">
              <div class="curated-input-head">
                <div>
                  <span>第 1 步已填充</span>
                  <h3>已锁定背景输入</h3>
                </div>
                <span class="curated-config-badge">已配置 · 只读</span>
              </div>

              <div class="curated-input-grid">
                <article class="curated-input-card">
                  <span class="curated-input-index">01 · 空间范围</span>
                  <strong>{{ curatedLocationLabel }}</strong>
                  <p>{{ curatedMacroScenarioCount }}个宏观场景 · {{ curatedAnchorNames.length }}个差异化锚点 · 45公里分析范围</p>
                </article>

                <article class="curated-input-card">
                  <span class="curated-input-index">02 · 时间窗口</span>
                  <strong>{{ curatedTimeScope }}</strong>
                  <p>2019-12-22 至 2020-04-08，共108天；36轮，每轮3天。</p>
                </article>

                <article class="curated-input-card is-wide">
                  <span class="curated-input-index">03 · 系统基线</span>
                  <strong>六个城市系统与八项业务状态已配置</strong>
                  <div class="curated-chip-list">
                    <span v-for="item in curatedCitySystems" :key="`system-${item}`">{{ item }}</span>
                  </div>
                  <div class="curated-chip-list is-state-list">
                    <span v-for="item in curatedStateDimensions" :key="`state-${item}`">{{ item }}</span>
                  </div>
                </article>

                <article class="curated-input-card is-wide">
                  <span class="curated-input-index">04 · 主体、设施与资料</span>
                  <strong>36个空间锚点 · {{ curatedSourceRefs.length }}项公开来源</strong>
                  <div class="curated-chip-list">
                    <span v-for="item in curatedAnchorPreview" :key="`anchor-preview-${item}`">{{ item }}</span>
                    <span v-if="curatedAnchorNames.length > curatedAnchorPreview.length">+{{ curatedAnchorNames.length - curatedAnchorPreview.length }}</span>
                  </div>
                  <details class="curated-input-details">
                    <summary>查看全部{{ curatedAnchorNames.length }}个空间锚点</summary>
                    <div class="curated-chip-list is-expanded">
                      <span v-for="item in curatedAnchorNames" :key="`anchor-${item}`">{{ item }}</span>
                    </div>
                  </details>
                </article>

                <article class="curated-input-card is-wide">
                  <span class="curated-input-index">05 · 研究问题与边界</span>
                  <strong>三个研究问题已经写入</strong>
                  <ol class="curated-question-list">
                    <li v-for="item in curatedResearchQuestions" :key="item">{{ item }}</li>
                  </ol>
                  <p class="curated-boundary-note">{{ curatedSourceBoundary }}</p>
                  <details class="curated-input-details">
                    <summary>查看{{ curatedBoundaries.length }}条分析边界与{{ curatedDataGaps.length }}项数据缺口</summary>
                    <ul class="curated-boundary-list">
                      <li v-for="item in curatedBoundaries" :key="`boundary-${item}`">{{ item }}</li>
                      <li v-for="item in curatedDataGaps" :key="`gap-${item}`">数据缺口：{{ item }}</li>
                    </ul>
                  </details>
                </article>
              </div>
            </section>

            <div v-if="!reportStepDone" class="task-stepper">
              <div class="task-step" :class="getStepClass('map')">
                <div class="task-step-head" @click="toggleTask('map')">
                  <div class="task-step-icon">
                    <span v-if="mapEvidenceUnavailable || mapSeedStatus === 'failed'">!</span>
                    <span v-else-if="mapSeedStatus === 'ready'">✓</span>
                    <span v-else-if="mapSeedStatus === 'processing' || mapSeedLoading" class="spinner"></span>
                    <span v-else>1</span>
                  </div>
                  <strong>区域定位与地理分析</strong>
                  <span class="task-step-status">{{ mapSeedStatusLabel }}</span>
                  <button class="expand-btn">{{ expandedTask === 'map' ? '↑' : '↓' }}</button>
                </div>
                <div class="task-step-body" v-show="expandedTask === 'map'">
                  <template v-if="mapEvidenceUnavailable">
                    <p class="spatial-failure-summary">
                      当前展示您圈定的分析范围和底图；区域类型、地点节点与代理位置将在地理数据更新后补充。
                    </p>
                    <button
                      class="map-retry-btn"
                      type="button"
                      :disabled="composing || mapSeedLoading"
                      @click.stop="retrySpatialData"
                    >
                      {{ composing || mapSeedLoading ? '正在处理...' : '重新获取地理数据' }}
                    </button>
                    <small class="map-retry-note">完成后会同步更新背景报告。</small>
                  </template>
                  <p v-else>{{ sanitizeDisplayCopy(mapSeedMessage, '正在提取区域内特征锚点和空间网络') }}</p>
                </div>
              </div>

              <div class="task-step" :class="getStepClass('plan')">
                <div class="task-step-head" @click="toggleTask('plan')">
                  <div class="task-step-icon">
                    <span v-if="planStepDone">✓</span>
                    <span v-else-if="planStepActive" class="spinner"></span>
                    <span v-else>2</span>
                  </div>
                  <strong>背景线索与大纲规划</strong>
                  <span class="task-step-status">{{ planStepStatusLabel }}</span>
                  <button class="expand-btn">{{ expandedTask === 'plan' ? '↑' : '↓' }}</button>
                </div>
                <div class="task-step-body" v-show="expandedTask === 'plan'">
                  <p>整合地图特征、已知实体和输入条件，规划报告结构与核心要素。</p>
                </div>
              </div>

              <div class="task-step" :class="getStepClass('report')">
                <div class="task-step-head" @click="toggleTask('report')">
                  <div class="task-step-icon">
                    <span v-if="reportStepDone">✓</span>
                    <span v-else-if="reportStepActive" class="spinner"></span>
                    <span v-else>3</span>
                  </div>
                  <strong>背景报告生成与排版</strong>
                  <span class="task-step-status">{{ reportStepStatusLabel }}</span>
                  <button class="expand-btn">{{ expandedTask === 'report' ? '↑' : '↓' }}</button>
                </div>
                <div class="task-step-body" v-show="expandedTask === 'report'">
                  <p>{{ message || '正在逐段落生成并排版为 Markdown 格式...' }}</p>
                </div>
              </div>
            </div>

            <div class="report-surface">
              <div
                v-if="renderedReportMarkdown"
                class="report-preview prose-markdown"
                v-html="renderedReportMarkdown"
              ></div>
              <div v-else class="report-preview-empty">
                结构化背景基础将在这里呈现。
              </div>
            </div>

            <section v-if="isCuratedShowcase && curatedSourceRefs.length" class="curated-source-section">
              <div class="curated-source-head">
                <strong>公开来源入口</strong>
                <span>{{ curatedSourceRefs.length }} 项</span>
              </div>
              <div class="curated-source-list">
                <a
                  v-for="source in curatedSourceRefs"
                  :key="source.id"
                  :href="source.url"
                  target="_blank"
                  rel="noreferrer"
                >
                  <span>{{ safeDisplayText(source.publisher, '公开机构') }}</span>
                  <strong>{{ safeDisplayText(source.title, '公开来源') }}</strong>
                </a>
              </div>
            </section>

            <div class="typing-status" v-if="composing || reportTyping">
              <span class="typing-dot"></span>
              <span>{{ composing ? '正在生成背景素材报告...' : '正在逐步排版报告...' }}</span>
            </div>

            <label v-if="!isCuratedShowcase" class="field">
              <span>补充修改说明</span>
              <textarea
                v-model="revisionInstruction"
                rows="3"
                placeholder="例：把重点改成台风天气下游客疏散和海岸线设施风险。"
              ></textarea>
            </label>
            </div>

            <div class="button-row report-actions">
              <button v-if="hasComposeError" class="secondary-btn" type="button" @click="returnToSetup">
                返回修改参数
              </button>
              <button v-if="hasComposeError" class="primary-btn" type="button" :disabled="composeDisabled" @click="retryComposeBackground">
                重新生成背景
              </button>
              <button v-if="!isCuratedShowcase" class="secondary-btn" type="button" :disabled="!sceneId || revising || !revisionInstruction.trim()" @click="reviseReport">
                {{ revising ? '修改中...' : '按说明修改背景基础' }}
              </button>
              <button v-if="isCuratedShowcase" class="secondary-btn" type="button" @click="copyCuratedAsNew">
                复制为新推演
              </button>
              <button class="primary-btn" type="button" :disabled="!reportMarkdown.trim()" @click="enterProcess">
                {{ isCuratedShowcase ? '查看场景设计' : '进入场景生成' }}
              </button>
            </div>
          </section>
        </div>
      </section>

      <template #visual>
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
                :layers="displayMapLayers"
                :read-only="showReportStage || isCuratedShowcase"
                @pick="handlePickPoint"
              />
            </div>

            <div v-if="showMapDataFailure" class="map-overlay map-data-failure">
              <strong>未取得可靠地理数据</strong>
              <p>仅显示您圈定的分析范围和底图；本轮没有生成区域类型判断。</p>
              <button type="button" :disabled="composing || mapSeedLoading" @click="retrySpatialData">
                {{ composing || mapSeedLoading ? '正在处理...' : '重新获取' }}
              </button>
            </div>

            <div v-else-if="showMapAnalysisSummary" class="map-overlay map-analysis-summary">
              <div class="analysis-summary-head">
                <span>区域类型分析</span>
                <strong>{{ primarySceneLabel }}</strong>
              </div>
              <div class="analysis-score-list">
                <span v-for="item in sceneScoreItems" :key="item.key" class="analysis-score-chip">
                  {{ item.label }} {{ item.score }}
                </span>
              </div>
            </div>

            <div v-if="!showReportStage && !isCuratedShowcase" class="map-overlay radius-overlay">
              <div class="radius-header">
                <span>分析半径</span>
                <strong>{{ radiusMetersDisplay }}</strong>
              </div>
              <input v-model.number="radiusMeters" type="range" min="1000" max="50000" step="500" />
            </div>

          </div>
        </div>
      </section>
      </template>
  </KaleidoWorkflowShell>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoWorkflowShell from '../components/KaleidoWorkflowShell.vue'
import LeafletMapPicker from '../components/LeafletMapPicker.vue'
import { getGoldenCaseArtifact } from '../api/goldenCases'
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
import {
  clearSceneComposerSnapshot,
  getSceneComposerSnapshot,
  getWorkflowSteps,
  markWorkflowStep,
  resetWorkflowNavigation,
  saveSceneComposerSnapshot
} from '../store/workflowNavigation'
import { renderMarkdown } from '../utils/markdown'
import { buildSpatialProviderRows, isSpatialEvidenceUnavailable } from '../utils/mapDataQuality'
import { safeDisplayError, safeDisplayText, sanitizeDisplayCopy } from '../utils/displayText'

const router = useRouter()
const route = useRoute()
const viewMode = ref('split')
const DEFAULT_CENTER = [22.5431, 114.0579]
const EFFORT_OPTIONS = [
  { value: 'light', label: 'Light' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'extra_high', label: 'Extra High' },
  { value: 'ultra', label: 'Ultra' }
]
const EFFORT_DISPLAY_LABELS = Object.freeze({
  light: 'Light',
  medium: 'Medium',
  high: 'High',
  extra_high: 'Extra High',
  ultra: 'Ultra'
})
const EFFORT_FILL_WIDTHS = [
  '1rem',
  'calc(25% + 0.5rem)',
  '50%',
  'calc(75% - 0.5rem)',
  'calc(100% - 1rem)'
]

const form = ref({
  location: '',
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
const mapSceneClassification = ref(null)
const mapSeedDataQuality = ref(null)
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
const composeErrorMessage = ref('')
const showReportStage = ref(false)
const reportTyping = ref(false)
const effortLevel = ref('high')
const effortLocked = ref(false)
const effortSnapshot = ref(null)
const effortMenuRef = ref(null)
const curatedFoundation = ref(null)
const curatedFoundationLoading = ref(false)
const curatedFoundationError = ref('')
const isCuratedShowcase = computed(() => (
  String(route.query.demo_mode || '') === 'curated_showcase'
  && Boolean(String(route.query.golden_case_id || '').trim())
))
const curatedSourceRefs = computed(() => (
  Array.isArray(curatedFoundation.value?.source_refs)
    ? curatedFoundation.value.source_refs.filter((item) => item?.url)
    : []
))
const curatedLocationLabel = computed(() => safeDisplayText(
  curatedFoundation.value?.area_of_interest?.location,
  '武汉市'
))
const curatedTimeScope = computed(() => safeDisplayText(
  curatedFoundation.value?.baseline_state?.time_scope || curatedFoundation.value?.time_scope,
  '2019-12-22 至 2020-04-08（108天）'
))
const curatedMacroScenarioCount = computed(() => {
  const regions = curatedFoundation.value?.area_of_interest?.regions
  return Array.isArray(regions) && regions.length ? regions.length : 12
})
const curatedAnchorNames = computed(() => (
  Array.isArray(curatedFoundation.value?.spatial_anchors)
    ? curatedFoundation.value.spatial_anchors
      .map((item) => safeDisplayText(item?.name, ''))
      .filter(Boolean)
    : []
))
const curatedAnchorPreview = computed(() => curatedAnchorNames.value.slice(0, 8))
const curatedCitySystems = computed(() => {
  const systems = curatedFoundation.value?.city_systems
    || curatedFoundation.value?.baseline_state?.city_systems
    || []
  return (Array.isArray(systems) ? systems : [])
    .map((item) => safeDisplayText(typeof item === 'object' ? item?.name : item, ''))
    .filter(Boolean)
})
const curatedStateDimensions = computed(() => (
  Array.isArray(curatedFoundation.value?.baseline_state?.state_dimensions)
    ? curatedFoundation.value.baseline_state.state_dimensions
      .map((item) => safeDisplayText(item?.name, ''))
      .filter(Boolean)
    : []
))
const curatedResearchQuestions = computed(() => (
  Array.isArray(curatedFoundation.value?.research_questions)
    ? curatedFoundation.value.research_questions.map((item) => safeDisplayText(item, '')).filter(Boolean)
    : []
))
const curatedBoundaries = computed(() => (
  Array.isArray(curatedFoundation.value?.analysis_boundaries)
    ? curatedFoundation.value.analysis_boundaries.map((item) => safeDisplayText(item, '')).filter(Boolean)
    : []
))
const curatedDataGaps = computed(() => (
  Array.isArray(curatedFoundation.value?.open_data_gaps)
    ? curatedFoundation.value.open_data_gaps.map((item) => safeDisplayText(item, '')).filter(Boolean)
    : []
))
const curatedSourceBoundary = computed(() => safeDisplayText(
  curatedFoundation.value?.source_boundary,
  '公开来源约束历史日期、地点与已发生措施；行动和连续状态为策划推演。'
))

function toggleMapCollapse() {
  viewMode.value = viewMode.value === 'workbench' ? 'split' : 'workbench'
}

const effortIndex = computed(() => {
  const index = EFFORT_OPTIONS.findIndex((option) => option.value === effortLevel.value)
  return index >= 0 ? index : 2
})
const effortOption = computed(() => EFFORT_OPTIONS[effortIndex.value] || EFFORT_OPTIONS[2])
const effortLabel = computed(() => EFFORT_DISPLAY_LABELS[effortOption.value.value] || 'High')
const effortFillWidth = computed(() => EFFORT_FILL_WIDTHS[effortIndex.value] || '50%')
const effortSnapshotId = computed(() => String(
  effortSnapshot.value?.effort_snapshot_id
  || effortSnapshot.value?.snapshot_id
  || ''
).trim())

// --- Task Stepper Logic ---
const expandedTask = ref('map')
const mapEvidenceUnavailable = computed(() => (
  !isCuratedShowcase.value && isSpatialEvidenceUnavailable(mapSeedDataQuality.value)
))
const spatialProviderRows = computed(() => buildSpatialProviderRows(mapSeedDataQuality.value))
const toggleTask = (task) => {
  expandedTask.value = expandedTask.value === task ? '' : task
}

const hasReportArtifact = computed(() => reportMarkdown.value.trim().length > 0)
const planStepDone = computed(() => reportTyping.value || hasReportArtifact.value || (composing.value && mapSeedStatus.value === 'ready'))
const planStepActive = computed(() => composing.value && mapSeedStatus.value === 'ready' && !reportTyping.value && !hasReportArtifact.value)
const planStepStatusLabel = computed(() => {
  if (planStepDone.value) return ''
  if (planStepActive.value) return '规划中'
  return '待开始'
})

const reportStepDone = computed(() => !composing.value && !reportTyping.value && hasReportArtifact.value)
const reportStepActive = computed(() => reportTyping.value || (composing.value && mapSeedStatus.value === 'ready'))
const hasComposeError = computed(() => !composing.value && !reportStepDone.value && (
  mapSeedStatus.value === 'failed' || String(composeErrorMessage.value || '').trim().length > 0
))
const reportStepStatusLabel = computed(() => {
  if (hasComposeError.value) return '待调整'
  if (reportStepDone.value) return ''
  if (reportStepActive.value) return '生成中'
  return '待开始'
})

const stepStatusTone = computed(() => {
  if (isCuratedShowcase.value && curatedFoundationError.value) return 'error'
  if (isCuratedShowcase.value && curatedFoundationLoading.value) return 'processing'
  if (hasComposeError.value) return 'error'
  if (composing.value || reportTyping.value || mapSeedLoading.value || mapSeedStatus.value === 'processing') return 'processing'
  return 'ready'
})

const stepStatusText = computed(() => {
  if (isCuratedShowcase.value && curatedFoundationError.value) return '背景待恢复'
  if (isCuratedShowcase.value && curatedFoundationLoading.value) return '正在恢复背景'
  if (isCuratedShowcase.value && curatedFoundation.value) return '已配置'
  if (hasComposeError.value) return '输入已保留'
  if (composing.value || reportTyping.value) return '背景生成中'
  if (mapSeedLoading.value || mapSeedStatus.value === 'processing') return '区域分析中'
  if (reportStepDone.value) return '背景报告'
  return '等待配置'
})

const getStepClass = (step) => {
  if (step === 'map') {
    if (mapSeedStatus.value === 'ready') {
      return mapEvidenceUnavailable.value ? 'failed' : 'done'
    }
    if (mapSeedStatus.value === 'failed') return 'failed'
    if (mapSeedStatus.value === 'processing' || mapSeedLoading.value) return 'active'
    return 'pending'
  }
  if (step === 'report' && hasComposeError.value) return 'failed'
  if (step === 'plan') {
    if (planStepDone.value) return 'done'
    if (planStepActive.value) return 'active'
    return 'pending'
  }
  if (step === 'report') {
    if (reportStepDone.value) return 'done'
    if (reportStepActive.value) return 'active'
    return 'pending'
  }
}

watch([mapSeedStatus, mapSeedLoading], () => {
  if (mapSeedStatus.value === 'processing' || mapSeedLoading.value) expandedTask.value = 'map'
})
watch(planStepActive, (val) => {
  if (val) expandedTask.value = 'plan'
})
watch(reportStepActive, (val) => {
  if (val) expandedTask.value = 'report'
})
// --------------------------

let suppressLocationWatcher = false
let locationResolveTimer = null
let pointResolveTimer = null
let geocodeRequestId = 0
let reverseRequestId = 0
let reportTypingTimer = null
let reportTypingRequestId = 0
let restoringSnapshot = false

const radiusMetersDisplay = computed(() => {
  if (radiusMeters.value >= 1000) return `${(radiusMeters.value / 1000).toFixed(1)} km`
  return `${radiusMeters.value} m`
})

function normalizeEffortLevel(value, fallback = 'high') {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
  return EFFORT_OPTIONS.some((option) => option.value === normalized)
    ? normalized
    : fallback
}

function selectEffort(level) {
  if (effortLocked.value) return
  effortLevel.value = normalizeEffortLevel(level, effortLevel.value)
}

function handleEffortSliderInput(event) {
  if (effortLocked.value) return
  const index = Math.max(0, Math.min(
    EFFORT_OPTIONS.length - 1,
    Number(event?.target?.value) || 0
  ))
  selectEffort(EFFORT_OPTIONS[index].value)
}

function closeEffortMenu() {
  if (effortMenuRef.value) effortMenuRef.value.open = false
}

function handleEffortMenuOutsideClick(event) {
  if (!effortMenuRef.value?.open || effortMenuRef.value.contains(event.target)) return
  closeEffortMenu()
}

function syncEffortFromPayload(payload, { lockOnSuccess = false } = {}) {
  const source = payload?.data && typeof payload.data === 'object' ? payload.data : payload
  const rawSnapshot = source?.effort_snapshot && typeof source.effort_snapshot === 'object'
    ? source.effort_snapshot
    : null
  const snapshotId = String(
    rawSnapshot?.effort_snapshot_id
    || rawSnapshot?.snapshot_id
    || source?.effort_snapshot_id
    || ''
  ).trim()
  const responseLevel = normalizeEffortLevel(
    rawSnapshot?.effort_level
    || rawSnapshot?.level
    || source?.effort_level,
    effortLevel.value
  )

  if (rawSnapshot || snapshotId) {
    effortSnapshot.value = {
      ...(effortSnapshot.value || {}),
      ...(rawSnapshot || {}),
      ...(snapshotId ? { effort_snapshot_id: snapshotId } : {}),
      effort_level: responseLevel,
      locked: rawSnapshot?.locked !== false
    }
  }
  effortLevel.value = responseLevel
  if (lockOnSuccess || rawSnapshot?.locked === true || snapshotId) {
    effortLocked.value = true
    if (!effortSnapshot.value) {
      effortSnapshot.value = {
        effort_level: responseLevel,
        effort_label: effortLabel.value,
        locked: true,
        source: 'accepted_without_snapshot'
      }
    }
    saveComposerSnapshot()
  }
}

function formatCurrentTimeScope(date = new Date()) {
  const pad = (value) => String(value).padStart(2, '0')
  const year = date.getFullYear()
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hours = pad(date.getHours())
  const minutes = pad(date.getMinutes())
  return `当前时间（${year}-${month}-${day} ${hours}:${minutes}）`
}

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

const mapSeedFocusText = computed(() => {
  const sections = [
    ['推演要求', form.value.simulationRequirement],
    ['重点关注', form.value.focus],
    ['补充背景', form.value.additionalContext],
    ['事件或稳态基线', form.value.eventOrBaseline],
    ['报告问题', form.value.reportQuestions]
  ]
  const seen = new Set()
  return sections
    .map(([label, value]) => [label, String(value || '').trim()])
    .filter(([, value]) => {
      if (!value || seen.has(value)) return false
      seen.add(value)
      return true
    })
    .map(([label, value]) => `${label}：${value}`)
    .join('\n')
})

const composeDisabled = computed(() => {
  if (composing.value || locationResolving.value) return true
  if (!selectedPoint.value) return true
  return !(
    form.value.location.trim() ||
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
  if (composing.value) return '生成中...'
  return '生成背景'
})

const GENERIC_AREA_LABELS = new Set(['其他', '其他区域', '未知区域', '未命名区域', '暂无摘要'])

function concreteAreaLabel(value, fallback = '') {
  const candidate = safeDisplayText(value, '').trim()
  return candidate && !GENERIC_AREA_LABELS.has(candidate) ? candidate : String(fallback || '').trim()
}

const areaNamePreview = computed(() => {
  const userLocation = form.value.location.trim()
  if (userLocation && locationSyncMode.value === 'manual') return userLocation
  return autoAreaLabel.value || userLocation || '尚未确定分析区域'
})

const mapPointLabel = computed(() => {
  if (!selectedPoint.value) return '未定位'
  return areaNamePreview.value !== '尚未确定分析区域' ? areaNamePreview.value : '已锁定地图点位'
})

const mapMetaHint = computed(() => {
  if (showReportStage.value && selectedPoint.value) {
    if (mapEvidenceUnavailable.value) {
      return `${radiusMetersDisplay.value} 分析范围 · 仅显示圈定范围与底图`
    }
    return `${radiusMetersDisplay.value} 分析范围 · 点击区域或节点查看详情`
  }
  if (selectedPoint.value) return `${radiusMetersDisplay.value} 分析范围 · ${selectedPoint.value.lat.toFixed(5)}, ${selectedPoint.value.lon.toFixed(5)}`
  return '输入地点或点击地图锁定中心点'
})

const mapSeedStatusLabel = computed(() => {
  if (mapSeedLoading.value || mapSeedStatus.value === 'processing') return '分析中'
  if (mapSeedStatus.value === 'ready') {
    return mapEvidenceUnavailable.value ? '可重新获取地理数据' : '地理数据'
  }
  if (mapSeedStatus.value === 'failed') return '可重新获取地理数据'
  return '待开始'
})

const reportStageLabel = computed(() => {
  if (composing.value) return '生成中'
  if (reportTyping.value) return '排版中'
  if (reportMarkdown.value.trim()) return `${reportMarkdown.value.length} 字`
  return '待开始'
})

const SCENE_TYPE_LABELS = {
  coastal: '滨海岸线',
  inland_water: '内陆水系',
  wetland: '湿地生态',
  urban_edge: '城市边缘',
  agricultural: '农业空间',
  mixed: '混合区域',
  unknown: '暂不判断'
}

const primarySceneLabel = computed(() => {
  const key = String(mapSceneClassification.value?.primary_scene || '').trim()
  return SCENE_TYPE_LABELS[key] || (key ? '其他区域' : '待判定')
})

const sceneScoreItems = computed(() => {
  const scores = mapSceneClassification.value?.scores || {}
  return Object.entries(scores)
    .map(([key, value]) => ({
      key,
      label: SCENE_TYPE_LABELS[key] || '其他区域',
      score: Number(value) || 0
    }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 4)
})

const showMapAnalysisSummary = computed(() => (
  !mapEvidenceUnavailable.value
  && mapSeedDataQuality.value?.formal_ready === true
  && mapSceneClassification.value?.classification_ready === true
  && Boolean(mapSceneClassification.value?.primary_scene)
  && (showReportStage.value || mapSeedStatus.value === 'ready')
))

const showMapDataFailure = computed(() => (
  mapEvidenceUnavailable.value
  && (showReportStage.value || mapSeedStatus.value === 'ready')
))

const displayMapLayers = computed(() => {
  if (isCuratedShowcase.value) return mapLayers.value
  if (!mapEvidenceUnavailable.value) return mapLayers.value
  return mapLayers.value.filter((layer) => layer.id === 'analysis-area')
})

const previewReportMarkdown = computed(() => {
  if (reportMarkdown.value.trim()) {
    return displayedReportMarkdown.value.trim() ? displayedReportMarkdown.value : reportMarkdown.value
  }
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
  return rawLayers.map((layer, index) => {
    const layerName = safeDisplayText(layer.name || layer.title, `地图图层 ${index + 1}`)
    const layerNote = safeDisplayText(layer.note || layer.description, '')
    return {
      id: layer.id || layer.layer_id || `layer_${index}`,
      name: layerName,
      type: layer.type || layer.kind || (Array.isArray(layer.points) ? 'points' : 'geojson'),
      color: layer.color || ['#1f5d45', '#0f766e', '#d97706', '#2563eb'][index % 4],
      visible: layer.visible !== false,
      note: layerNote,
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
            popupTitle: safeDisplayText(item.popupTitle || item.label || item.name || layerName, '地图节点'),
            popupSummary: safeDisplayText(item.popupSummary || layerNote, ''),
            popupMeta: {
              layerName,
              layerNote,
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
    }
  })
}

function resetMapAnalysis(statusMessage = '等待背景生成时触发区域地理分析') {
  mapLayers.value = []
  mapSeedId.value = ''
  mapSeedTaskId.value = ''
  mapSeedStatus.value = 'idle'
  mapSeedLoading.value = false
  mapSeedMessage.value = statusMessage
  mapSceneClassification.value = null
  mapSeedDataQuality.value = null
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
      locationMessage.value = `请补充“${query}”的行政区或附近地标`
      return
    }

    selectedPoint.value = {
      lat: Number(primary.lat),
      lon: Number(primary.lon)
    }
    mapCenter.value = [selectedPoint.value.lat, selectedPoint.value.lon]
    const resolvedAreaLabel = concreteAreaLabel(primary.area_label || primary.display_name, query)
    autoAreaLabel.value = resolvedAreaLabel
    resolvedAdminContext.value = primary.admin_context || null
    resetMapAnalysis('地点已定位，背景生成时会启动区域分析')
    locationMessage.value = `地图范围：${resolvedAreaLabel}`
  } catch (error) {
    if (requestId !== geocodeRequestId) return
    locationMessage.value = '地点输入已保留，可以补充行政区或在地图上选点'
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

    autoAreaLabel.value = concreteAreaLabel(res.data.area_label, form.value.location)
    resolvedAdminContext.value = res.data.admin_context || null
    if (updateField) {
      updateLocationValue(autoAreaLabel.value || form.value.location || '', 'auto')
    }
    locationMessage.value = autoAreaLabel.value
      ? `区域范围：${autoAreaLabel.value}`
      : '当前地图点位与分析半径'
  } catch (error) {
    if (requestId !== reverseRequestId) return
    locationMessage.value = '点位已保留，可以直接使用当前范围'
  } finally {
    if (requestId === reverseRequestId) {
      locationResolving.value = false
    }
  }
}

async function handlePickPoint(point) {
  if (isCuratedShowcase.value) return
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
    if (res.data.data_quality) mapSeedDataQuality.value = res.data.data_quality
    if (status === 'ready' || status === 'completed') {
      mapSeedStatus.value = 'ready'
      return
    }
    if (status === 'failed' || status === 'cancelled') {
      mapSeedStatus.value = 'failed'
      mapSeedLoading.value = false
      throw new Error(res.data.error || (status === 'cancelled' ? '区域分析已停止' : '区域分析失败'))
    }
    if (status === 'unavailable') {
      mapSeedStatus.value = 'failed'
      mapSeedLoading.value = false
      throw new Error(
        res.data.availability?.message
        || res.data.message
        || '未取得可靠地理数据，请重新获取。'
      )
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
    syncEffortFromPayload(seed)
    const input = seed.input || {}
    if (!selectedPoint.value && input.lat && input.lon) {
      selectedPoint.value = { lat: Number(input.lat), lon: Number(input.lon) }
      mapCenter.value = [selectedPoint.value.lat, selectedPoint.value.lon]
    }
    if (seed.admin_context) {
      resolvedAdminContext.value = seed.admin_context
    }
    if (seed.scene_classification) {
      mapSceneClassification.value = seed.scene_classification
    }
    mapSeedDataQuality.value = seed.data_quality || null
    if (seed.area_of_interest?.label) {
      const areaLabel = concreteAreaLabel(seed.area_of_interest.label, form.value.location || autoAreaLabel.value)
      autoAreaLabel.value = areaLabel
      if (!form.value.location.trim() || locationSyncMode.value === 'auto') {
        updateLocationValue(areaLabel || form.value.location, 'auto')
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
      simulation_requirement: derivedSimulationRequirement.value,
      requested_location: form.value.location.trim() || autoAreaLabel.value,
      focus_text: mapSeedFocusText.value,
      known_entities: form.value.knownEntities.trim(),
      analysis_boundaries: form.value.analysisBoundaries.trim(),
      focus_mode: 'auto',
      effort_level: effortLevel.value,
      ...(effortSnapshotId.value ? { effort_snapshot_id: effortSnapshotId.value } : {})
    })
    if (!res.success || !res.data) {
      throw new Error(res.error || '区域分析任务启动失败')
    }

    mapSeedId.value = res.data.seed_id
    mapSeedTaskId.value = res.data.task_id || ''
    syncEffortFromPayload(res.data, { lockOnSuccess: true })
    await waitForMapSeedReady()
    await loadMapSeedArtifacts()
    if (mapEvidenceUnavailable.value) {
      mapSeedMessage.value = '当前展示用户圈定范围和底图；区域节点将在地理数据更新后补充。'
    } else if (mapSeedDataQuality.value?.status === 'partial') {
      mapSeedMessage.value = '当前空间骨架依据地点、边界与交通数据形成。'
    } else {
      mapSeedMessage.value = '区域地理数据'
    }
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
  data.append('time_scope', formatCurrentTimeScope())
  data.append('event_or_baseline', form.value.eventOrBaseline)
  data.append('focus', form.value.focus)
  data.append('additional_context', form.value.additionalContext)
  data.append('known_entities', form.value.knownEntities)
  data.append('analysis_boundaries', form.value.analysisBoundaries)
  data.append('report_questions', form.value.reportQuestions)
  data.append('simulation_requirement', derivedSimulationRequirement.value)
  data.append('initial_variables_text', initialVariablesText.value)
  data.append('initial_variables', JSON.stringify(parseVariables(initialVariablesText.value)))
  data.append('effort_level', effortLevel.value)
  if (effortSnapshotId.value) data.append('effort_snapshot_id', effortSnapshotId.value)
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
  composeErrorMessage.value = ''
  showReportStage.value = true
  clearReportTyping()
  if (!hasReportArtifact.value) {
    displayedReportMarkdown.value = ''
  }
  message.value = '正在准备区域背景...'

  try {
    await resolveAreaNameFromPoint({
      updateField: !form.value.location.trim() || locationSyncMode.value === 'auto'
    })
    await ensureMapSeedReady()
    expandedTask.value = 'report'
    message.value = '正在生成背景素材报告...'

    const res = await composeSceneMaterial(buildFormData())
    if (res.success && res.data) {
      const nextReportMarkdown = sanitizeDisplayCopy(res.data.report_markdown || '', '').trim()
      if (!nextReportMarkdown) {
        throw new Error('missing_scene_report_markdown')
      }
      syncEffortFromPayload(res.data, { lockOnSuccess: true })
      applySceneSeed(res.data)
      message.value = ''
      return
    }
    throw new Error('missing_scene_material_payload')
  } catch (error) {
    clearReportTyping()
    composeErrorMessage.value = '输入已保留，可以重新生成背景。'
    if (!hasReportArtifact.value) {
      displayedReportMarkdown.value = ''
    }
    if (mapSeedStatus.value === 'processing') {
      mapSeedStatus.value = 'failed'
      mapSeedMessage.value = '区域范围已保留，可以重新分析。'
    }
    message.value = composeErrorMessage.value
    expandedTask.value = mapSeedStatus.value === 'failed' ? 'map' : 'report'
  } finally {
    composing.value = false
  }
}

function retryComposeBackground() {
  resetMapAnalysis('准备重新启动区域地理分析')
  message.value = ''
  composeErrorMessage.value = ''
  composeBackground()
}

function retrySpatialData() {
  if (composing.value || mapSeedLoading.value) return
  expandedTask.value = 'map'
  retryComposeBackground()
}

async function reviseReport() {
  if (!sceneId.value || revising.value || !revisionInstruction.value.trim()) return
  revising.value = true
  message.value = '正在按说明修改背景报告...'

  try {
    const res = await reviseSceneMaterial(sceneId.value, {
      instruction: revisionInstruction.value,
      current_report: reportMarkdown.value,
      initial_variables_text: initialVariablesText.value,
      initial_variables: parseVariables(initialVariablesText.value),
      semantic_artifact_ref: sceneSeed.value?.semantic_artifact_ref || undefined,
      effort_level: effortLevel.value,
      effort_snapshot_id: effortSnapshotId.value || undefined
    })
    if (res.success && res.data) {
      syncEffortFromPayload(res.data)
      applySceneSeed(res.data)
      revisionInstruction.value = ''
      message.value = ''
    }
  } catch (error) {
    message.value = '修改内容已保留，可以重新应用。'
  } finally {
    revising.value = false
  }
}

function applySceneSeed(seed) {
  syncEffortFromPayload(seed)
  sceneSeed.value = seed
  sceneId.value = seed.scene_id || sceneId.value
  reportMarkdown.value = sanitizeDisplayCopy(seed.report_markdown || '', '')
  showReportStage.value = true
  startReportTyping(reportMarkdown.value, { reset: true, interval: 10 })
  if (seed.recommended_simulation_requirement && !form.value.simulationRequirement.trim()) {
    form.value.simulationRequirement = safeDisplayText(seed.recommended_simulation_requirement, '')
  }
}

function returnToSetup() {
  showReportStage.value = false
}

function enterProcess() {
  const curatedSimulationId = String(route.query.simulation_id || '').trim()
  if (isCuratedShowcase.value && curatedSimulationId) {
    saveComposerSnapshot()
    router.push({
      name: 'Simulation',
      params: { simulationId: curatedSimulationId },
      query: { ...route.query, step: '2', restore: undefined }
    })
    return
  }

  const step2 = getWorkflowSteps().find(item => Number(item.step) === 2)
  const cachedRoute = step2?.visited && step2.route?.name ? step2.route : null
  const cachedProjectId = cachedRoute?.params?.projectId
  const canReuseCachedStep2 = Boolean(cachedRoute) && (
    cachedRoute.name === 'Simulation' ||
    (cachedRoute.name === 'Process' && cachedProjectId && cachedProjectId !== 'new')
  )

  if (canReuseCachedStep2) {
    saveComposerSnapshot()
    router.push(cachedRoute)
    return
  }

  if (isCuratedShowcase.value) {
    message.value = '案例路由暂不可用，请从武汉案例入口重新进入。'
    return
  }

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
    normalizedEventInputs: Array.isArray(sceneSeed.value?.suggested_event_inputs)
      ? sceneSeed.value.suggested_event_inputs
      : (Array.isArray(sceneSeed.value?.normalized_event_inputs) ? sceneSeed.value.normalized_event_inputs : []),
    normalizedPolicyInputs: Array.isArray(sceneSeed.value?.suggested_policy_inputs)
      ? sceneSeed.value.suggested_policy_inputs
      : (Array.isArray(sceneSeed.value?.normalized_policy_inputs) ? sceneSeed.value.normalized_policy_inputs : []),
    selectedPoints,
    mapSeedId: mapSeedId.value || sceneSeed.value?.map_seed_id || '',
    areaLabel: areaNamePreview.value || autoAreaLabel.value || form.value.location || '',
    radiusMeters: Number(radiusMeters.value) || 0,
    effortLevel: effortLevel.value,
    effortLocked: effortLocked.value,
    effortSnapshotId: effortSnapshotId.value,
    effortSnapshot: effortSnapshot.value ? { ...effortSnapshot.value } : null,
    sceneId: sceneId.value,
    semanticArtifactRef: sceneSeed.value?.semantic_artifact_ref || null,
    semanticRevision: Number(sceneSeed.value?.semantic_revision || 0)
  })
  saveComposerSnapshot()
  router.push({ name: 'Process', params: { projectId: 'new' } })
}

async function copyCuratedAsNew() {
  if (!isCuratedShowcase.value || !reportMarkdown.value.trim()) return
  const editableSnapshot = {
    ...buildComposerSnapshot(),
    mapSeedId: '',
    mapSeedTaskId: '',
    mapSeedStatus: 'idle',
    mapSeedMessage: '已复制武汉研究范围；生成背景时会重新核对区域地理数据。',
    mapSeedDataQuality: null,
    sceneId: '',
    sceneSeed: null,
    reportMarkdown: '',
    displayedReportMarkdown: '',
    revisionInstruction: '',
    message: '',
    composeErrorMessage: '',
    showReportStage: false,
    effortLocked: false,
    effortSnapshot: null,
    effortSnapshotId: ''
  }
  const copyRoute = {
    name: 'SceneComposer',
    query: { restore: '1', copied_from: 'wuhan_covid_v2' }
  }
  resetWorkflowNavigation()
  saveSceneComposerSnapshot(editableSnapshot)
  markWorkflowStep(1, {
    visited: true,
    status: 'active',
    forceStatus: true,
    summary: '武汉案例副本 · 可编辑',
    route: copyRoute
  })
  await router.push(copyRoute)
  curatedFoundation.value = null
  curatedFoundationError.value = ''
  restoreComposerSnapshot()
}

function assertCuratedFoundationContract(foundation) {
  const baseline = foundation?.baseline_state || {}
  const systems = foundation?.city_systems || baseline.city_systems || []
  const location = String(foundation?.area_of_interest?.location || '')
  const valid = Boolean(String(foundation?.foundation_id || '').trim())
    && location.includes('武汉')
    && Array.isArray(foundation?.spatial_anchors)
    && foundation.spatial_anchors.length === 36
    && Array.isArray(systems)
    && systems.length === 6
    && Array.isArray(baseline.state_dimensions)
    && baseline.state_dimensions.length === 8
    && Array.isArray(foundation?.source_refs)
    && foundation.source_refs.length >= 8
    && Array.isArray(foundation?.research_questions)
    && foundation.research_questions.length >= 3
    && Boolean(String(foundation?.report_markdown || '').trim())
  if (!valid) {
    throw new Error('武汉案例基础数据不完整，请重新恢复案例。')
  }
}

async function loadCuratedFoundation() {
  const caseId = String(route.query.golden_case_id || '').trim()
  if (!caseId) return
  curatedFoundationLoading.value = true
  curatedFoundationError.value = ''
  message.value = ''
  form.value.location = '武汉市'
  selectedPoint.value = { lat: 30.5928, lon: 114.3055 }
  mapCenter.value = [30.5928, 114.3055]
  radiusMeters.value = 45000
  locationSyncMode.value = 'auto'
  autoAreaLabel.value = '武汉市'
  locationMessage.value = '武汉市 · 108天历史窗口'
  try {
    const res = await getGoldenCaseArtifact(caseId, 'foundation')
    const foundation = res.data || {}
    assertCuratedFoundationContract(foundation)
    const anchors = Array.isArray(foundation.spatial_anchors) ? foundation.spatial_anchors : []
    const baseline = foundation.baseline_state || {}
    const systemNames = (foundation.city_systems || baseline.city_systems || [])
      .map((item) => safeDisplayText(typeof item === 'object' ? item?.name : item, ''))
      .filter(Boolean)
    const stateDimensions = (baseline.state_dimensions || [])
      .map((item) => ({
        name: safeDisplayText(item?.name, ''),
        direction: {
          lower_is_better: '压力越低越好',
          higher_is_better: '能力越高越好',
          contextual: '随阶段解释'
        }[String(item?.direction || '')] || '按阶段观察'
      }))
      .filter((item) => item.name)
    const researchQuestions = (foundation.research_questions || [])
      .map((item) => safeDisplayText(item, ''))
      .filter(Boolean)
    const analysisBoundaries = (foundation.analysis_boundaries || [])
      .map((item) => safeDisplayText(item, ''))
      .filter(Boolean)
    const dataGaps = (foundation.open_data_gaps || [])
      .map((item) => safeDisplayText(item, ''))
      .filter(Boolean)
    const sourceBoundary = safeDisplayText(foundation.source_boundary, '')
    const timeScope = safeDisplayText(
      baseline.time_scope || foundation.time_scope,
      '2019-12-22 至 2020-04-08（108天）'
    )

    curatedFoundation.value = foundation
    form.value.location = foundation.area_of_interest?.location || '武汉市'
    form.value.eventOrBaseline = [
      `时间窗口：${timeScope}`,
      `城市系统：${systemNames.join('；')}`,
      `状态口径：${stateDimensions.map((item) => item.name).join('、')}`,
      `背景说明：${safeDisplayText(foundation.summary, '武汉疫情城市系统背景')}`
    ].join('\n')
    form.value.focus = systemNames.map((item) => `- ${item}`).join('\n')
    form.value.knownEntities = anchors
      .map((item) => `- ${safeDisplayText(item.name, '空间锚点')}`)
      .join('\n')
    form.value.additionalContext = [
      sourceBoundary ? `事实与推演边界：${sourceBoundary}` : '',
      ...dataGaps.map((item) => `数据缺口：${item}`)
    ].filter(Boolean).join('\n')
    form.value.analysisBoundaries = analysisBoundaries.map((item) => `- ${item}`).join('\n')
    form.value.reportQuestions = researchQuestions.map((item) => `- ${item}`).join('\n')
    form.value.simulationRequirement = '复盘六个城市系统在36轮中的行动、关系、风险和资源状态变化。'
    initialVariablesText.value = stateDimensions
      .map((item) => `- ${item.name}：${item.direction}`)
      .join('\n')
    mapLayers.value = [{
      id: 'curated-wuhan-anchors',
      name: '武汉案例空间锚点',
      type: 'points',
      color: '#1f6a54',
      visible: true,
      note: '真实公开地点、区级聚合空间与功能网络',
      data: anchors.map((item) => ({
        id: item.anchor_id || item.region_id,
        name: safeDisplayText(item.name, '空间锚点'),
        label: safeDisplayText(item.name, '空间锚点'),
        lat: Number(item.lat),
        lon: Number(item.lon),
        popupTitle: safeDisplayText(item.name, '空间锚点'),
        popupSummary: safeDisplayText(item.anchor_type || item.boundary_note, '武汉案例空间锚点')
      })).filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lon))
    }]
    mapSeedStatus.value = 'ready'
    mapSeedMessage.value = '已加载36个策划型空间锚点。'
    mapSeedDataQuality.value = { status: 'curated_showcase', formal_ready: false, fixture_ready: true }
    sceneId.value = foundation.foundation_id || `foundation::${caseId}`
    sceneSeed.value = {
      scene_id: sceneId.value,
      title: foundation.title || '武汉疫情城市系统复盘',
      report_markdown: foundation.report_markdown || '',
      recommended_simulation_requirement: form.value.simulationRequirement,
      effort_snapshot: foundation.effort_snapshot_ref || {}
    }
    reportMarkdown.value = sanitizeDisplayCopy(foundation.report_markdown || '', '')
    displayedReportMarkdown.value = reportMarkdown.value
    showReportStage.value = true
    effortLevel.value = 'ultra'
    effortLocked.value = true
    effortSnapshot.value = foundation.effort_snapshot_ref || null
    markWorkflowStep(1, {
      visited: true,
      status: 'active',
      forceStatus: true,
      summary: '研究范围与事实边界',
      route: { name: 'SceneComposer', query: { ...route.query } }
    })
  } catch (error) {
    curatedFoundation.value = null
    showReportStage.value = false
    curatedFoundationError.value = safeDisplayError(error, '武汉案例基础暂时无法加载，请重新加载。')
    message.value = curatedFoundationError.value
  } finally {
    curatedFoundationLoading.value = false
  }
}

function resetComposer() {
  restoringSnapshot = true
  clearTimers()
  geocodeRequestId += 1
  reverseRequestId += 1
  form.value = {
    location: '',
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
  composeErrorMessage.value = ''
  showReportStage.value = false
  effortLevel.value = 'high'
  effortLocked.value = false
  effortSnapshot.value = null
  clearReportTyping()
  clearSceneComposerSnapshot()
  resetWorkflowNavigation()
  markWorkflowStep(1, {
    visited: true,
    status: 'active',
    summary: '正在编辑背景',
    route: { name: 'SceneComposer', query: { restore: '1' } }
  })
  window.setTimeout(() => {
    restoringSnapshot = false
    saveComposerSnapshot()
  }, 0)
}

function buildComposerSnapshot() {
  return {
    form: { ...form.value },
    initialVariablesText: initialVariablesText.value,
    selectedPoint: selectedPoint.value ? { ...selectedPoint.value } : null,
    mapCenter: [...mapCenter.value],
    radiusMeters: radiusMeters.value,
    mapLayers: mapLayers.value,
    mapSeedId: mapSeedId.value,
    mapSeedTaskId: mapSeedTaskId.value,
    mapSeedStatus: mapSeedStatus.value,
    mapSeedMessage: mapSeedMessage.value,
    mapSceneClassification: mapSceneClassification.value,
    mapSeedDataQuality: mapSeedDataQuality.value,
    autoAreaLabel: autoAreaLabel.value,
    resolvedAdminContext: resolvedAdminContext.value,
    sceneId: sceneId.value,
    sceneSeed: sceneSeed.value,
    reportMarkdown: reportMarkdown.value,
    displayedReportMarkdown: displayedReportMarkdown.value,
    revisionInstruction: revisionInstruction.value,
    message: message.value,
    composeErrorMessage: composeErrorMessage.value,
    showReportStage: showReportStage.value,
    advancedOpen: advancedOpen.value,
    locationSyncMode: locationSyncMode.value,
    locationMessage: locationMessage.value,
    effortLevel: effortLevel.value,
    effortLocked: effortLocked.value,
    effortSnapshot: effortSnapshot.value ? { ...effortSnapshot.value } : null,
    effortSnapshotId: effortSnapshotId.value
  }
}

function saveComposerSnapshot() {
  if (isCuratedShowcase.value) return
  if (restoringSnapshot) return
  saveSceneComposerSnapshot(buildComposerSnapshot())
}

function restoreComposerSnapshot() {
  const snapshot = getSceneComposerSnapshot()
  if (!snapshot) {
    markWorkflowStep(1, {
      visited: true,
      status: 'active',
      summary: '正在编辑背景',
      route: { name: 'SceneComposer', query: { restore: '1' } }
    })
    return
  }

  restoringSnapshot = true
  form.value = {
    ...form.value,
    ...(snapshot.form || {})
  }
  initialVariablesText.value = snapshot.initialVariablesText || ''
  selectedPoint.value = snapshot.selectedPoint || null
  mapCenter.value = Array.isArray(snapshot.mapCenter) ? snapshot.mapCenter : [...DEFAULT_CENTER]
  radiusMeters.value = Number(snapshot.radiusMeters) || 3000
  mapLayers.value = Array.isArray(snapshot.mapLayers) ? snapshot.mapLayers : []
  mapSeedId.value = snapshot.mapSeedId || ''
  mapSeedTaskId.value = snapshot.mapSeedTaskId || ''
  mapSeedStatus.value = snapshot.mapSeedStatus || 'idle'
  mapSeedMessage.value = safeDisplayText(snapshot.mapSeedMessage, '等待背景生成时触发区域地理分析')
  mapSceneClassification.value = snapshot.mapSceneClassification || null
  mapSeedDataQuality.value = snapshot.mapSeedDataQuality || null
  autoAreaLabel.value = snapshot.autoAreaLabel || ''
  resolvedAdminContext.value = snapshot.resolvedAdminContext || null
  sceneId.value = snapshot.sceneId || ''
  sceneSeed.value = snapshot.sceneSeed || null
  reportMarkdown.value = sanitizeDisplayCopy(snapshot.reportMarkdown || '', '')
  displayedReportMarkdown.value = sanitizeDisplayCopy(snapshot.reportMarkdown || snapshot.displayedReportMarkdown || '', '')
  revisionInstruction.value = snapshot.revisionInstruction || ''
  message.value = safeDisplayText(snapshot.message, '')
  composeErrorMessage.value = safeDisplayError(snapshot.composeErrorMessage, '')
  showReportStage.value = Boolean(snapshot.showReportStage || snapshot.reportMarkdown)
  advancedOpen.value = Boolean(snapshot.advancedOpen)
  locationSyncMode.value = snapshot.locationSyncMode || 'empty'
  locationMessage.value = safeDisplayText(snapshot.locationMessage, '输入地点会自动定位地图，也可以直接在地图上选点。')
  const restoredEffortSnapshot = snapshot.effortSnapshot && typeof snapshot.effortSnapshot === 'object'
    ? snapshot.effortSnapshot
    : null
  effortLevel.value = normalizeEffortLevel(
    snapshot.effortLevel
    || restoredEffortSnapshot?.effort_level
    || restoredEffortSnapshot?.level,
    'high'
  )
  const hasLegacyGeneratedArtifact = Boolean(
    snapshot.mapSeedId
    || snapshot.sceneId
    || String(snapshot.reportMarkdown || '').trim()
  )
  effortLocked.value = Boolean(
    snapshot.effortLocked
    || snapshot.effortSnapshotId
    || restoredEffortSnapshot?.effort_snapshot_id
    || restoredEffortSnapshot?.snapshot_id
    || restoredEffortSnapshot?.locked
    || hasLegacyGeneratedArtifact
  )
  effortSnapshot.value = restoredEffortSnapshot
    ? {
        ...restoredEffortSnapshot,
        effort_level: effortLevel.value,
        locked: effortLocked.value
      }
    : effortLocked.value
      ? {
          ...(snapshot.effortSnapshotId ? { effort_snapshot_id: snapshot.effortSnapshotId } : {}),
          effort_level: effortLevel.value,
          effort_label: effortLabel.value,
          locked: true,
          source: hasLegacyGeneratedArtifact ? 'legacy_migration' : 'restored_snapshot'
        }
      : null
  window.setTimeout(() => {
    restoringSnapshot = false
  }, 0)
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
  if (restoringSnapshot || isCuratedShowcase.value) return
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

watch(
  [
    form,
    initialVariablesText,
    selectedPoint,
    mapCenter,
    radiusMeters,
    mapLayers,
    mapSeedId,
    mapSeedTaskId,
    mapSeedStatus,
    mapSeedMessage,
    mapSeedDataQuality,
    autoAreaLabel,
    resolvedAdminContext,
    sceneId,
    sceneSeed,
    reportMarkdown,
    displayedReportMarkdown,
    revisionInstruction,
    message,
    showReportStage,
    advancedOpen,
    locationSyncMode,
    locationMessage,
    effortLevel,
    effortLocked,
    effortSnapshot
  ],
  saveComposerSnapshot,
  { deep: true }
)

onMounted(async () => {
  document.addEventListener('click', handleEffortMenuOutsideClick)
  if (isCuratedShowcase.value) {
    await loadCuratedFoundation()
    return
  }
  if (route.query.restore === '1') {
    restoreComposerSnapshot()
  } else {
    resetComposer()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleEffortMenuOutsideClick)
  saveComposerSnapshot()
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

.curated-foundation-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 0 16px;
}

.curated-foundation-summary > div {
  display: grid;
  gap: 3px;
  padding: 12px;
  border: 1px solid rgba(23, 49, 38, 0.12);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.54);
}

.curated-foundation-summary strong {
  font-size: 24px;
  line-height: 1;
  color: #1f6a54;
}

.curated-foundation-summary span,
.curated-foundation-summary p {
  font-size: 12px;
  color: rgba(23, 49, 38, 0.68);
}

.curated-source-section {
  display: grid;
  gap: 10px;
  padding: 14px 0 2px;
  border-top: 1px solid rgba(23, 49, 38, 0.1);
}

.curated-source-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: rgba(23, 49, 38, 0.66);
  font-size: 12px;
}

.curated-source-head strong { color: #173126; }

.curated-source-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.curated-source-list a {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(23, 49, 38, 0.1);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.5);
  color: #173126;
  text-decoration: none;
}

.curated-source-list a:hover { border-color: rgba(31, 106, 84, 0.42); }
.curated-source-list span { color: rgba(23, 49, 38, 0.58); font-size: 11px; }
.curated-source-list strong { font-size: 12px; line-height: 1.45; }

.curated-foundation-summary p {
  grid-column: 1 / -1;
  margin: 2px 0 0;
  line-height: 1.6;
}

.curated-foundation-state {
  min-height: 420px;
  display: grid;
  place-items: center;
}

.curated-foundation-state-inner {
  width: min(520px, 100%);
  display: grid;
  justify-items: start;
  gap: 12px;
}

.curated-foundation-state-inner h2,
.curated-foundation-state-inner p {
  margin: 0;
}

.curated-foundation-state-inner p {
  color: rgba(23, 49, 38, 0.68);
  line-height: 1.7;
}

.curated-locked-inputs {
  display: grid;
  gap: 12px;
  padding: 16px 0;
  border-top: 1px solid rgba(23, 49, 38, 0.1);
}

.curated-input-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.curated-input-head > div {
  display: grid;
  gap: 3px;
}

.curated-input-head span {
  color: rgba(23, 49, 38, 0.58);
  font-size: 11px;
}

.curated-input-head h3 {
  margin: 0;
  font-size: 17px;
}

.curated-config-badge {
  min-width: max-content;
  padding: 6px 10px;
  border: 1px solid rgba(31, 106, 84, 0.2);
  border-radius: 999px;
  background: rgba(31, 106, 84, 0.07);
  color: #1f6a54 !important;
  font-weight: 700;
}

.curated-input-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.curated-input-card {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 8px;
  padding: 14px;
  border: 1px solid rgba(23, 49, 38, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.5);
}

.curated-input-card.is-wide {
  grid-column: 1 / -1;
}

.curated-input-card > strong {
  color: #173126;
  font-size: 14px;
  line-height: 1.5;
}

.curated-input-card > p {
  margin: 0;
  color: rgba(23, 49, 38, 0.68);
  font-size: 12px;
  line-height: 1.65;
}

.curated-input-index {
  color: #1f6a54;
  font-size: 11px;
  font-weight: 800;
}

.curated-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.curated-chip-list span {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 4px 8px;
  border: 1px solid rgba(23, 49, 38, 0.1);
  border-radius: 7px;
  background: rgba(247, 249, 246, 0.86);
  color: rgba(23, 49, 38, 0.78);
  font-size: 11px;
  line-height: 1.35;
}

.curated-chip-list.is-state-list span {
  border-color: rgba(31, 106, 84, 0.16);
  color: #1f6a54;
}

.curated-input-details {
  color: rgba(23, 49, 38, 0.72);
  font-size: 12px;
}

.curated-input-details summary {
  width: max-content;
  cursor: pointer;
  color: #1f6a54;
  font-weight: 700;
}

.curated-chip-list.is-expanded,
.curated-boundary-list {
  margin-top: 10px;
}

.curated-question-list,
.curated-boundary-list {
  display: grid;
  gap: 6px;
  margin-bottom: 0;
  padding-left: 20px;
  color: rgba(23, 49, 38, 0.78);
  font-size: 12px;
  line-height: 1.55;
}

.curated-boundary-note {
  padding: 10px 12px;
  border-left: 3px solid rgba(31, 106, 84, 0.42);
  background: rgba(31, 106, 84, 0.05);
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

.topbar-meta {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
}

.topbar-divider {
  width: 1px;
  height: 18px;
  background: rgba(16, 35, 29, 0.12);
}

.scene-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: max-content;
  color: #64756e;
  font-size: 12px;
  font-weight: 650;
}

.scene-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
}

.scene-status.is-ready { color: #3d8a61; }
.scene-status.is-processing { color: #2f6f57; }
.scene-status.is-error { color: #b94a43; }
.scene-status.is-processing .scene-status-dot { animation: pulse-dot 1.4s ease-in-out infinite; }
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

.setup-column {
  min-width: 0;
  height: 100%;
  padding: 0.75rem;
  overflow: hidden;
}

.setup-scroll {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  height: 100%;
  min-height: 100%;
  overflow: hidden;
}

.setup-scroll:not(.has-report) {
  overflow: hidden;
}

.setup-scroll.has-report {
  overflow: hidden;
}

.map-column {
  min-width: 0;
  height: 100%;
  padding: 0.75rem;
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
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.setup-panel.compact-mode {
  height: 100%;
  min-height: 0;
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
  min-height: 0;
  margin-right: -0.35rem;
  padding-right: 0.35rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  scrollbar-color: rgba(16, 35, 29, 0.2) transparent;
}

.foundation-section-heading {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr);
  align-items: start;
  gap: 0.75rem;
  margin-top: 0.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--k-color-border, rgba(22, 53, 42, 0.12));
}

.foundation-section-heading:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.foundation-section-heading > span {
  color: var(--k-color-brand-600, #2f6f57);
  font-size: var(--k-text-meta, 0.75rem);
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

.foundation-section-heading div {
  display: grid;
  gap: 0.2rem;
}

.foundation-section-heading strong {
  color: var(--k-color-text, #16352a);
  font-size: var(--k-text-ui, 0.94rem);
}

.foundation-section-heading small {
  color: var(--k-color-text-muted, #64756e);
  line-height: 1.5;
}

.setup-form::-webkit-scrollbar,
.setup-scroll.has-report::-webkit-scrollbar {
  width: 6px;
}

.setup-form::-webkit-scrollbar-track,
.setup-scroll.has-report::-webkit-scrollbar-track {
  background: transparent;
}

.setup-form::-webkit-scrollbar-thumb,
.setup-scroll.has-report::-webkit-scrollbar-thumb {
  border-radius: 10px;
  background-color: rgba(16, 35, 29, 0.15);
}

.effort-lock-badge {
  display: inline-flex;
  align-items: center;
  min-height: 2rem;
  gap: 0.35rem;
  padding: 0 0.72rem;
  border-radius: 999px;
  background: rgba(23, 76, 58, 0.09);
  color: #174c3a;
  font-size: 0.8rem;
  font-weight: 800;
  white-space: nowrap;
}

.effort-menu {
  position: relative;
  flex: none;
}

.effort-menu > summary {
  list-style: none;
}

.effort-menu > summary::-webkit-details-marker {
  display: none;
}

.effort-trigger {
  display: inline-flex;
  height: 2.25rem;
  align-items: center;
  gap: 0.32rem;
  padding: 0 0.55rem;
  border: 1px solid rgba(16, 35, 29, 0.12);
  border-radius: 11px;
  background: rgba(242, 245, 243, 0.98);
  color: #173126;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}

.brain-icon {
  width: 0.9rem;
  height: 0.9rem;
  flex: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.effort-trigger .brain-icon {
  color: #1f7d5d;
}

.effort-trigger-label,
.effort-trigger-value {
  font-size: 0.72rem;
  line-height: 1;
  white-space: nowrap;
}

.effort-trigger-label {
  font-weight: 750;
}

.effort-trigger-value {
  color: rgba(16, 35, 29, 0.55);
  font-weight: 650;
}

.effort-chevron {
  width: 0.7rem;
  height: 0.7rem;
  flex: none;
  color: rgba(16, 35, 29, 0.5);
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform 0.18s ease;
}

.effort-menu[open] .effort-chevron {
  transform: rotate(180deg);
}

.effort-trigger:hover,
.effort-menu[open] .effort-trigger {
  border-color: rgba(31, 125, 93, 0.28);
  background: #edf5f0;
  box-shadow: 0 8px 20px rgba(18, 86, 62, 0.12);
  transform: translateY(-1px);
}

.effort-trigger:active {
  transform: translateY(0) scale(0.98);
}

.effort-trigger:focus-visible {
  outline: 3px solid rgba(36, 151, 243, 0.2);
  outline-offset: 2px;
}

.effort-popover {
  position: absolute;
  right: 0;
  bottom: calc(100% + 0.5rem);
  z-index: 30;
  width: min(16rem, calc(100vw - 1.5rem));
  padding: 0.68rem 0.75rem 0.78rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  background: #2a2a2a;
  color: #f4f7f5;
  box-shadow: 0 16px 34px rgba(0, 0, 0, 0.28);
  transform-origin: bottom right;
  animation: effort-popover-in 0.18s ease-out;
}

@keyframes effort-popover-in {
  from { opacity: 0; transform: translateY(6px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.effort-popover-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.58rem;
}

.effort-popover-head > span:first-child {
  color: rgba(255, 255, 255, 0.55);
  font-size: 0.78rem;
  font-weight: 500;
}

.effort-current-level {
  display: inline-flex;
  align-items: center;
  gap: 0.28rem;
  color: #56aef6;
}

.effort-current-level .brain-icon {
  width: 0.82rem;
  height: 0.82rem;
  filter: drop-shadow(0 0 10px rgba(45, 157, 244, 0.3));
}

.effort-current-level strong {
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.72rem;
  font-weight: 650;
  white-space: nowrap;
}

.effort-track-shell {
  position: relative;
  height: 2rem;
  isolation: isolate;
}

.effort-track-rail {
  position: absolute;
  z-index: 0;
  top: 50%;
  right: 0;
  left: 0;
  height: 1.75rem;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  background: #454545;
  transform: translateY(-50%);
  box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.06), inset 0 -8px 22px rgba(0, 0, 0, 0.08);
}

.effort-track-fill {
  position: relative;
  height: 100%;
  overflow: hidden;
  border-radius: 999px;
  background: linear-gradient(102deg, #2497f3 0%, #43a5ff 52%, #7668f7 100%);
  box-shadow: 0 0 22px rgba(54, 154, 255, 0.34);
  transition: width 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}

.effort-track-fill::after {
  position: absolute;
  inset: 0;
  content: '';
  background:
    radial-gradient(circle at 11% 35%, rgba(255, 255, 255, 0.95) 0 1.4px, transparent 1.8px),
    radial-gradient(circle at 18% 68%, rgba(255, 255, 255, 0.72) 0 2px, transparent 2.5px),
    radial-gradient(circle at 33% 26%, rgba(255, 255, 255, 0.7) 0 1px, transparent 1.5px),
    radial-gradient(circle at 48% 63%, rgba(255, 255, 255, 0.88) 0 1.5px, transparent 2px),
    radial-gradient(circle at 62% 32%, rgba(255, 255, 255, 0.62) 0 1px, transparent 1.5px),
    radial-gradient(circle at 79% 57%, rgba(255, 255, 255, 0.78) 0 1.2px, transparent 1.7px);
  animation: effort-stars-float 3.8s ease-in-out infinite alternate;
}

@keyframes effort-stars-float {
  to { transform: translate3d(5px, -2px, 0); opacity: 0.78; }
}

.effort-slider {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 2rem;
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  box-shadow: none;
  cursor: pointer;
  appearance: none;
}

.effort-slider:focus {
  outline: none;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.effort-slider:focus-visible::-webkit-slider-thumb {
  box-shadow: 0 0 0 5px rgba(45, 157, 244, 0.2), 0 7px 20px rgba(0, 0, 0, 0.25);
}

.effort-slider::-webkit-slider-runnable-track {
  height: 1.75rem;
  border-radius: 999px;
  background: transparent;
}

.effort-slider::-webkit-slider-thumb {
  width: 2rem;
  height: 2rem;
  margin-top: -0.125rem;
  border: 0;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 7px 20px rgba(0, 0, 0, 0.24);
  appearance: none;
}

.effort-slider::-moz-range-track {
  height: 1.75rem;
  border-radius: 999px;
  background: transparent;
}

.effort-slider::-moz-range-progress {
  height: 1.75rem;
  border-radius: 999px;
  background: transparent;
}

.effort-slider::-moz-range-thumb {
  width: 2rem;
  height: 2rem;
  border: 0;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
}

.effort-track-dot {
  position: absolute;
  z-index: 1;
  top: 50%;
  width: 0.3rem;
  height: 0.3rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.36);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.effort-track-dot:nth-of-type(1) { left: 1rem; }
.effort-track-dot:nth-of-type(2) { left: calc(25% + 0.5rem); }
.effort-track-dot:nth-of-type(3) { left: 50%; }
.effort-track-dot:nth-of-type(4) { left: calc(75% - 0.5rem); }
.effort-track-dot:nth-of-type(5) { left: calc(100% - 1rem); }

.effort-track-dot.is-active {
  background: rgba(255, 255, 255, 0.82);
}

.field-grow {
  flex: 0 0 auto;
  min-height: auto;
}

.field-grow textarea {
  flex: none;
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
  position: relative;
  z-index: 8;
  flex: none;
  margin-top: auto;
  padding: 0.8rem 0 0.1rem;
  border-top: 1px solid rgba(16, 35, 29, 0.1);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72), #ffffff 32%);
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

.setup-actions .button-row,
.report-actions {
  justify-content: flex-end;
}

.setup-action-row {
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.65rem;
}

.setup-action-row .primary-btn {
  min-height: 2.25rem;
  padding: 0 0.8rem;
  border-radius: 10px;
  font-size: 0.78rem;
}

.message {
  margin: 1rem 0 0;
  color: #174c3a;
  line-height: 1.6;
}

.report-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  margin-bottom: 0;
  overflow: hidden;
}

.report-content-scroll {
  flex: 1 1 auto;
  min-height: 0;
  padding-right: 0.2rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.report-content-scroll .report-surface {
  flex: none;
  min-height: 12rem;
  overflow: visible;
}

.report-actions {
  position: relative;
  z-index: 2;
  flex: none;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(16, 35, 29, 0.1);
  background: rgba(255, 255, 255, 0.96);
}

.report-title-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.icon-back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.2rem;
  height: 2.2rem;
  border-radius: 50%;
  border: 1px solid rgba(16, 35, 29, 0.18);
  background: transparent;
  color: #10231d;
  cursor: pointer;
  transition: all 0.2s ease;
  padding: 0;
}

.icon-back-btn:hover {
  background: rgba(16, 35, 29, 0.05);
}

.task-stepper {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  margin-top: 1.25rem;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 18px;
  border: 1px solid rgba(16, 35, 29, 0.08);
  padding: 0.5rem;
}

.task-step {
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  transition: background 0.2s;
}

.task-step.active {
  background: rgba(245, 249, 244, 0.9);
}

.task-step.failed {
  background: rgba(254, 242, 242, 0.88);
}

.task-step-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  cursor: pointer;
  user-select: none;
}

.task-step-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: rgba(16, 35, 29, 0.06);
  color: rgba(16, 35, 29, 0.4);
  font-size: 0.8rem;
  font-weight: 700;
}

.task-step.active .task-step-icon {
  background: rgba(31, 125, 93, 0.1);
  color: #1f7d5d;
}

.task-step.done .task-step-icon {
  background: #1f7d5d;
  color: #fff;
}

.task-step.failed .task-step-icon {
  background: #b91c1c;
  color: #fff;
}

.task-step-head strong {
  font-size: 0.95rem;
  color: #10231d;
  flex: 1;
}

.task-step-status {
  font-size: 0.85rem;
  color: rgba(16, 35, 29, 0.5);
}

.task-step.active .task-step-status {
  color: #1f7d5d;
  font-weight: 700;
}

.task-step.failed .task-step-status {
  color: #b91c1c;
  font-weight: 700;
}

.expand-btn {
  background: none;
  border: none;
  color: rgba(16, 35, 29, 0.4);
  cursor: pointer;
  padding: 0 0.25rem;
  font-size: 0.9rem;
}

.task-step-body {
  padding: 0 1rem 1rem 3rem;
  font-size: 0.9rem;
  color: rgba(16, 35, 29, 0.65);
  line-height: 1.5;
}

.spatial-failure-summary {
  margin: 0;
  color: #991b1b;
  font-weight: 650;
}

.provider-status-list {
  display: grid;
  gap: 0.55rem;
  margin: 0.75rem 0;
  padding: 0;
  list-style: none;
}

.provider-status-list li {
  display: grid;
  grid-template-columns: minmax(8.5rem, 0.34fr) 1fr;
  gap: 0.65rem;
  padding-top: 0.55rem;
  border-top: 1px solid rgba(153, 27, 27, 0.12);
}

.provider-status-list strong {
  color: #7f1d1d;
}

.map-retry-btn,
.map-data-failure button {
  min-height: 2.2rem;
  padding: 0 0.85rem;
  border: 1px solid rgba(153, 27, 27, 0.22);
  border-radius: 10px;
  background: #fff;
  color: #991b1b;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.map-retry-btn:disabled,
.map-data-failure button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.map-retry-note {
  margin-left: 0.65rem;
  color: rgba(16, 35, 29, 0.55);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
.spinner {
  display: block;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.report-surface {
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 1rem;
  padding: 1.15rem 1.2rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
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
  position: sticky;
  bottom: -1px;
  z-index: 8;
  flex: none;
  align-items: center;
  margin-top: auto;
  padding: 0.8rem 0 0.1rem;
  border-top: 1px solid rgba(16, 35, 29, 0.1);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.72), #ffffff 32%);
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
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  height: 100%;
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

.map-analysis-summary {
  left: 1rem;
  bottom: 1rem;
  width: min(24rem, calc(100% - 2rem));
  padding: 0.85rem 0.95rem;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(16, 35, 29, 0.1);
  box-shadow: 0 14px 32px rgba(16, 35, 29, 0.14);
}

.map-data-failure {
  left: 1rem;
  bottom: 1rem;
  width: min(27rem, calc(100% - 2rem));
  padding: 0.9rem 1rem;
  border-radius: 14px;
  background: rgba(255, 247, 247, 0.95);
  border: 1px solid rgba(153, 27, 27, 0.2);
  box-shadow: 0 14px 32px rgba(72, 19, 19, 0.14);
}

.map-data-failure strong {
  color: #991b1b;
}

.map-data-failure p {
  margin: 0.35rem 0 0.65rem;
  color: rgba(69, 10, 10, 0.72);
  font-size: 0.84rem;
  line-height: 1.5;
}

.analysis-summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.86rem;
  color: rgba(16, 35, 29, 0.68);
}

.analysis-summary-head strong {
  color: #10231d;
  font-size: 0.98rem;
}

.analysis-score-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.55rem;
}

.analysis-score-chip {
  display: inline-flex;
  align-items: center;
  min-height: 1.6rem;
  padding: 0 0.55rem;
  border-radius: 999px;
  background: transparent;
  border: 1px solid rgba(23, 76, 58, 0.22);
  color: #174c3a;
  font-size: 0.78rem;
  font-weight: 700;
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
  .setup-column,
  .map-column { padding: 0.6rem; }
}

@media (max-width: 720px) {
  .curated-input-grid {
    grid-template-columns: 1fr;
  }

  .curated-input-card.is-wide {
    grid-column: auto;
  }

  .curated-input-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .topbar,
  .topbar-step,
  .panel-head,
  .map-head,
  .button-row {
    flex-direction: column;
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

  .setup-action-row {
    flex-direction: row;
    justify-content: flex-end;
  }
}

/* Step 1 typography contract: one shared scale, no browser-default body copy. */
.scene-composer-page {
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.panel-head h2,
.map-head h2 {
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
}

.panel-kicker,
.field-hint,
.status-label,
.scene-status,
.effort-trigger-label,
.effort-trigger-value,
.eyebrow {
  font-size: var(--k-text-meta);
}

.field > span,
.advanced-toggle,
.primary-btn,
.secondary-btn,
.ghost-link {
  font-size: var(--k-text-ui);
  line-height: var(--k-leading-ui);
}

.setup-action-row .primary-btn,
.upload-box strong,
.map-meta strong {
  font-size: var(--k-text-ui);
  line-height: var(--k-leading-ui);
}

.map-meta small {
  font-size: var(--k-text-meta);
  line-height: var(--k-leading-ui);
}

.setup-form input,
.setup-form textarea,
.setup-form p,
.prose-markdown,
.map-analysis-summary,
.map-data-failure {
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.prose-markdown :deep(.md-h2) { font-size: var(--k-text-title); }
.prose-markdown :deep(.md-h3) { font-size: var(--k-text-section); }
.prose-markdown :deep(.md-h4),
.prose-markdown :deep(.md-h5) { font-size: var(--k-text-ui); }

/* Keep the form header clear; secondary disclosure sits in the bottom action row. */
.setup-action-row {
  flex-wrap: nowrap;
  justify-content: space-between;
}

.setup-advanced-toggle {
  flex: 0 0 auto;
  min-height: var(--k-control-height-sm);
  margin-right: auto;
  padding-inline: var(--k-space-2);
  border-color: transparent;
  border-radius: var(--k-radius-sm);
  background: transparent;
  color: var(--k-color-text-secondary);
  font-weight: var(--k-weight-semibold);
  transition: background var(--k-transition-fast), color var(--k-transition-fast);
}

.setup-advanced-toggle:hover {
  border-color: transparent;
  background: var(--k-color-brand-050);
  color: var(--k-color-brand-700);
}

.setup-primary-actions {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--k-space-2);
  margin-left: auto;
}

@media (max-width: 720px) {
  .setup-action-row {
    flex-wrap: wrap;
    justify-content: space-between;
  }

  .setup-primary-actions {
    margin-left: auto;
  }
}
</style>
