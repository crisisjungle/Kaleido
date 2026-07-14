<template>
  <section class="report-panel">
    <header class="report-header">
      <div>
        <p class="eyebrow">正式交付</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="status-pill" :class="statusTone">{{ statusLabel }}</span>
    </header>

    <div v-if="loading && !report" class="empty-state">正在读取报告...</div>

    <div v-else-if="error && !report" class="empty-state error report-read-error">
      <span>报告内容正在整理，可以继续查看结果分析。</span>
      <button type="button" class="report-refresh-btn" @click="refreshReport">重新读取</button>
    </div>

    <div v-else-if="isFailed" class="generation-state is-failed">
      <div class="generation-state-head">
        <div>
          <strong>当前报告内容</strong>
          <p>可以继续查看已生成的结果分析；重新读取会使用现有推演数据整理报告。</p>
        </div>
        <button type="button" class="report-refresh-btn" @click="refreshReport">重新读取状态</button>
      </div>
    </div>

    <div v-else-if="!hasReportContent" class="generation-state">
      <div class="generation-state-head">
        <div>
          <strong>{{ generationTitle }}</strong>
          <p>{{ generationMessage }}</p>
        </div>
      </div>
      <KProgress :value="progressPercent" label="正式报告生成进度" aria-label="正式报告生成进度" />
      <div class="generation-meta">
        <span v-if="progress?.current_section">正在生成：{{ safeReportText(progress.current_section, '当前章节') }}</span>
        <span v-else>页面会自动刷新，不需要重复进入报告。</span>
        <span v-if="completedSectionCount">{{ completedSectionCount }} 个章节</span>
      </div>
    </div>

    <article v-else class="report-body" v-html="renderedMarkdown"></article>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getReport, getReportProgress } from '../api/report'
import { sanitizeDisplayCopy, sanitizeDisplayMarkdown } from '../utils/displayText'
import { renderMarkdown } from '../utils/markdown'
import KProgress from './ui/KProgress.vue'

const REPORT_POLL_INTERVAL_MS = 3000
const TERMINAL_REPORT_STATUSES = new Set(['completed', 'failed'])

const props = defineProps({
  reportId: String,
  simulationId: String,
  systemLogs: Array
})

const emit = defineEmits(['add-log', 'update-status'])

const loading = ref(false)
const error = ref('')
const report = ref(null)
const progress = ref(null)
let pollTimer = null
let loadInFlightReportId = ''
let requestSequence = 0
let isUnmounted = false

const INVALID_REPORT_COPY = new Set(['内部标识', '未命名项', '内容待本地化'])
const safeReportText = (value, fallback = '') => {
  const text = sanitizeDisplayCopy(value, '').trim()
  return !text || INVALID_REPORT_COPY.has(text) ? fallback : text
}

const title = computed(() => safeReportText(report.value?.outline?.title, 'Kaleido 推演报告'))
const reportStatus = computed(() => {
  const savedStatus = String(report.value?.status || '')
  const progressStatus = String(progress.value?.status || '')
  if (TERMINAL_REPORT_STATUSES.has(savedStatus)) return savedStatus
  if (TERMINAL_REPORT_STATUSES.has(progressStatus)) return progressStatus
  return progressStatus || savedStatus || 'pending'
})
const statusLabel = computed(() => {
  const labels = {
    pending: '等待生成',
    planning: '规划报告结构',
    generating: '生成正式报告',
    completed: '正式报告',
    failed: '报告内容整理中',
  }
  return labels[reportStatus.value] || '等待报告'
})
const statusTone = computed(() => ({
  'is-complete': reportStatus.value === 'completed',
  'is-working': reportStatus.value !== 'completed',
}))
const markdown = computed(() => sanitizeDisplayMarkdown(
  report.value?.markdown_content || report.value?.content || '',
  '',
))

function normalizeMarkdownLabel(value) {
  return String(value || '')
    .trim()
    .replace(/^#{1,6}\s+/, '')
    .replace(/^(?:\*\*|__)(.*)(?:\*\*|__)$/, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

function dedupeReportMarkdown(source, reportTitle) {
  const expectedTitle = normalizeMarkdownLabel(reportTitle)
  const lines = String(source || '').replace(/\r\n?/g, '\n').split('\n')
  let firstContentSeen = false
  let previousHeading = ''

  return lines.filter((line) => {
    const trimmed = line.trim()
    const text = normalizeMarkdownLabel(trimmed)
    const isHeading = /^#{1,6}\s+/.test(trimmed)

    if (!text) return true

    if (!firstContentSeen) {
      firstContentSeen = true
      if (isHeading && expectedTitle && text === expectedTitle) {
        previousHeading = ''
        return false
      }
    }

    if (isHeading) {
      previousHeading = text
      return true
    }

    if (previousHeading && text === previousHeading) {
      previousHeading = ''
      return false
    }

    previousHeading = ''
    return true
  }).join('\n')
}

const displayMarkdown = computed(() => dedupeReportMarkdown(markdown.value, title.value))
const hasReportContent = computed(() => Boolean(displayMarkdown.value.trim()))
const renderedMarkdown = computed(() => renderMarkdown(displayMarkdown.value))
const isFailed = computed(() => reportStatus.value === 'failed')
const progressPercent = computed(() => {
  const value = Number(progress.value?.progress ?? (reportStatus.value === 'completed' ? 100 : 0))
  if (!Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value)))
})
const completedSectionCount = computed(() => Array.isArray(progress.value?.completed_sections) ? progress.value.completed_sections.length : 0)
const generationTitle = computed(() => reportStatus.value === 'completed' ? '正文正在同步' : '正式报告生成中')
const generationMessage = computed(() => {
  if (reportStatus.value === 'completed') return '正在读取报告正文。'
  return safeReportText(progress.value?.message, '分析结果已经可以查看，正式报告仍在后台生成。')
})
const failureMessage = computed(() => safeReportText(
  report.value?.error || progress.value?.message,
  '当前报告内容可根据现有推演数据重新整理。'
))

function requestErrorMessage(err, fallback) {
  const backendMessage = err?.response?.data?.error || err?.response?.data?.message
  return safeReportText(backendMessage, fallback)
}

function stopPolling() {
  if (pollTimer) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

function shouldKeepPolling() {
  if (reportStatus.value === 'failed') return false
  return reportStatus.value !== 'completed' || !hasReportContent.value
}

function scheduleNextPoll() {
  stopPolling()
  if (isUnmounted || !props.reportId || !shouldKeepPolling()) return
  pollTimer = window.setTimeout(() => loadReport({ showLoading: false }), REPORT_POLL_INTERVAL_MS)
}

async function loadReport({ showLoading = false } = {}) {
  const requestedReportId = props.reportId
  if (!requestedReportId || loadInFlightReportId === requestedReportId) return
  const requestId = ++requestSequence
  loadInFlightReportId = requestedReportId
  if (showLoading && !report.value) loading.value = true
  try {
    const [reportRes, progressRes] = await Promise.all([
      getReport(requestedReportId),
      getReportProgress(requestedReportId).catch(() => ({ data: null }))
    ])
    if (requestId !== requestSequence || props.reportId !== requestedReportId) return
    report.value = reportRes.data
    progress.value = progressRes.data
    error.value = ''
    emit('update-status', reportStatus.value)
  } catch (err) {
    if (requestId !== requestSequence || props.reportId !== requestedReportId) return
    error.value = requestErrorMessage(err, '报告读取失败，请稍后重试。')
    emit('add-log', `报告读取失败：${error.value}`)
  } finally {
    if (requestId !== requestSequence || props.reportId !== requestedReportId) return
    loading.value = false
    loadInFlightReportId = ''
    scheduleNextPoll()
  }
}

function refreshReport() {
  stopPolling()
  loadReport({ showLoading: !report.value })
}

function handleVisibilityChange() {
  if (document.visibilityState !== 'visible' || !shouldKeepPolling()) return
  stopPolling()
  loadReport({ showLoading: false })
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
  loadReport({ showLoading: true })
})

watch(
  () => props.reportId,
  (nextId, previousId) => {
    if (!nextId || nextId === previousId) return
    stopPolling()
    requestSequence += 1
    loadInFlightReportId = ''
    report.value = null
    progress.value = null
    error.value = ''
    loadReport({ showLoading: true })
  }
)

onBeforeUnmount(() => {
  isUnmounted = true
  requestSequence += 1
  stopPolling()
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>

<style scoped>
.report-panel {
  width: 100%;
  min-height: 360px;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 20px 4px 28px;
  overflow: visible;
  color: var(--k-color-text);
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.report-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.eyebrow {
  color: #6d7d6f;
  font-size: var(--k-text-meta);
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h2 {
  margin: 4px 0 0;
  color: #173126;
  font-size: var(--k-text-title);
  line-height: var(--k-leading-tight);
}

.status-pill {
  border: 1px solid rgba(31, 93, 69, 0.18);
  border-radius: 999px;
  padding: 6px 10px;
  color: #1f5d45;
  font-size: var(--k-text-meta);
  white-space: nowrap;
}

.status-pill.is-working {
  border-color: var(--k-color-border-strong);
  background: transparent;
  color: var(--k-color-brand-600);
}

.status-pill.is-complete {
  border-color: rgba(5, 150, 105, 0.2);
  background: rgba(5, 150, 105, 0.08);
  color: #047857;
}

.status-pill.is-failed {
  border-color: rgba(185, 28, 28, 0.2);
  background: rgba(185, 28, 28, 0.08);
  color: #b91c1c;
}

.empty-state {
  color: #647067;
  line-height: 1.7;
}

.error {
  color: #9c2f2f;
}

.report-read-error,
.generation-state-head,
.generation-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.generation-state {
  padding: 22px;
  border-radius: 16px;
  background: var(--k-color-brand-050);
  border: 1px solid var(--k-color-border);
}

.generation-state.is-failed {
  background: rgba(185, 28, 28, 0.05);
  border-color: rgba(185, 28, 28, 0.16);
}

.generation-state strong {
  color: #173126;
  font-size: var(--k-text-section);
}

.generation-state p {
  margin: 6px 0 0;
  color: #647067;
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.generation-state :deep(.k-progress) {
  margin: 18px 0 12px;
}

.generation-meta {
  align-items: baseline;
  color: #647067;
  font-size: var(--k-text-meta);
}

.report-refresh-btn {
  flex: 0 0 auto;
  border: 1px solid rgba(23, 49, 38, 0.18);
  border-radius: 8px;
  padding: 8px 12px;
  background: #ffffff;
  color: #173126;
  font: inherit;
  font-size: var(--k-text-ui);
  font-weight: 700;
  cursor: pointer;
}

.report-refresh-btn:hover {
  background: #f2f6f2;
}

.report-refresh-btn:focus-visible {
  outline: 2px solid var(--k-color-brand-600);
  outline-offset: 2px;
}

.report-body {
  color: #21372d;
  font-size: var(--k-text-body);
  line-height: var(--k-leading-reading);
  overflow: visible;
}

.report-body :deep(h1),
.report-body :deep(h2),
.report-body :deep(h3) {
  margin: 1.1em 0 0.55em;
  color: #173126;
  line-height: var(--k-leading-tight);
}

.report-body :deep(h1) { font-size: var(--k-text-display); }
.report-body :deep(h2) { font-size: var(--k-text-title); }
.report-body :deep(h3) { font-size: var(--k-text-section); }

.report-body :deep(p) {
  margin: 0.7em 0;
}

@media (max-width: 720px) {
  .report-header,
  .report-read-error,
  .generation-state-head,
  .generation-meta {
    align-items: flex-start;
    flex-direction: column;
  }

  .report-panel {
    padding: 16px 0 24px;
  }
}
</style>
