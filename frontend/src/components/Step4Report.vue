<template>
  <section class="report-panel">
    <header class="report-header">
      <div>
        <p class="eyebrow">Report</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="status-pill">{{ statusLabel }}</span>
    </header>

    <div v-if="loading" class="empty-state">正在读取报告...</div>
    <div v-else-if="error" class="empty-state error">{{ error }}</div>
    <article v-else class="report-body" v-html="renderedMarkdown"></article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getReport, getReportProgress } from '../api/report'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps({
  reportId: String,
  simulationId: String,
  systemLogs: Array,
  showNextStep: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['add-log', 'update-status', 'next-step'])

const loading = ref(false)
const error = ref('')
const report = ref(null)
const progress = ref(null)

const title = computed(() => report.value?.outline?.title || 'Kaleido 推演报告')
const statusLabel = computed(() => progress.value?.message || report.value?.status || '等待报告')
const markdown = computed(() => report.value?.markdown_content || report.value?.content || '报告内容正在生成或尚未写入。')
const renderedMarkdown = computed(() => renderMarkdown(markdown.value))

async function loadReport() {
  if (!props.reportId) return
  loading.value = true
  error.value = ''
  try {
    const [reportRes, progressRes] = await Promise.all([
      getReport(props.reportId),
      getReportProgress(props.reportId).catch(() => ({ data: null }))
    ])
    report.value = reportRes.data
    progress.value = progressRes.data
    emit('update-status', report.value?.status || 'loaded')
  } catch (err) {
    error.value = err.message || '报告读取失败'
    emit('add-log', `报告读取失败: ${error.value}`)
  } finally {
    loading.value = false
  }
}

onMounted(loadReport)
watch(() => props.reportId, loadReport)
</script>

<style scoped>
.report-panel {
  width: 100%;
  min-height: 360px;
  border: 1px solid rgba(23, 49, 38, 0.12);
  border-radius: 8px;
  background: rgba(255, 252, 245, 0.86);
  padding: 24px;
  overflow: visible;
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
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h2 {
  margin: 4px 0 0;
  color: #173126;
  font-size: 22px;
}

.status-pill {
  border: 1px solid rgba(31, 93, 69, 0.18);
  border-radius: 999px;
  padding: 6px 10px;
  color: #1f5d45;
  font-size: 12px;
  white-space: nowrap;
}

.empty-state {
  color: #647067;
  line-height: 1.7;
}

.error {
  color: #9c2f2f;
}

.report-body {
  color: #21372d;
  line-height: 1.75;
  overflow: visible;
}

.report-body :deep(h1),
.report-body :deep(h2),
.report-body :deep(h3) {
  margin: 1.1em 0 0.55em;
  color: #173126;
}

.report-body :deep(p) {
  margin: 0.7em 0;
}
</style>
