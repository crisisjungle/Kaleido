<template>
  <div class="history-page">
    <header class="history-topbar">
      <KaleidoNavBrand to="/" />
      <div class="history-actions">
        <RouterLink class="ghost-link" to="/">主页</RouterLink>
        <RouterLink class="primary-link" to="/scene-composer">新建推演</RouterLink>
      </div>
    </header>

    <main class="history-shell">
      <section class="history-hero">
        <span>Simulation Archive</span>
        <h1>推演记录</h1>
        <p>这里直接读取当前项目后端保存的历史模拟。数据还在，本页只是把入口重新接回来。</p>
      </section>

      <section class="history-board" :class="{ empty: !loading && simulations.length === 0 }">
        <div class="board-head">
          <h2>历史项目</h2>
          <button type="button" :disabled="loading" @click="loadHistory">
            {{ loading ? '加载中...' : '刷新' }}
          </button>
        </div>

        <div v-if="loading" class="state-card">正在读取历史记录...</div>
        <div v-else-if="error" class="state-card error">{{ error }}</div>
        <div v-else-if="simulations.length === 0" class="state-card">还没有保存过的推演记录。</div>

        <div v-else class="history-grid">
          <article v-for="item in simulations" :key="item.simulation_id" class="project-card" @click="selected = item">
            <div class="card-header">
              <span class="card-id">{{ shortSimulationId(item.simulation_id) }}</span>
              <span class="card-progress" :class="progressState(item)">
                <span class="status-dot">●</span>
                {{ progressText(item) }}
              </span>
            </div>
            <div class="card-files-wrapper">
              <div v-if="item.files?.length" class="files-list">
                <div v-for="file in item.files.slice(0, 3)" :key="file.filename" class="file-item">
                  <span class="file-tag">{{ fileExt(file.filename) }}</span>
                  <span class="file-name">{{ file.filename }}</span>
                </div>
              </div>
              <div v-else class="files-empty">暂无文件</div>
            </div>
            <h3>{{ titleFor(item) }}</h3>
            <p>{{ item.simulation_requirement || '这个推演没有记录描述。' }}</p>
            <div class="card-footer">
              <span>{{ dateText(item.created_at) }}</span>
              <span>{{ item.status || item.runner_status || 'idle' }}</span>
            </div>
          </article>
        </div>
      </section>
    </main>

    <div v-if="selected" class="modal-overlay" @click.self="selected = null">
      <section class="modal-content">
        <header class="modal-header">
          <div>
            <span class="modal-id">{{ shortSimulationId(selected.simulation_id) }}</span>
            <h2>{{ titleFor(selected) }}</h2>
            <p>{{ dateText(selected.created_at) }}</p>
          </div>
          <button class="modal-close" type="button" @click="selected = null">×</button>
        </header>
        <div class="modal-body">
          <h3>推演说明</h3>
          <p>{{ selected.simulation_requirement || '这个推演没有记录描述。' }}</p>
          <h3>关联文件</h3>
          <div v-if="selected.files?.length" class="modal-files">
            <div v-for="file in selected.files" :key="file.filename" class="modal-file-item">
              <span class="file-tag">{{ fileExt(file.filename) }}</span>
              <span>{{ file.filename }}</span>
            </div>
          </div>
          <div v-else class="modal-empty">暂无文件</div>
        </div>
        <footer class="modal-actions">
          <button type="button" :disabled="!selected.project_id" @click="openProject(selected)">图谱构建</button>
          <button type="button" :disabled="!selected.simulation_id" @click="openSimulation(selected)">环境搭建</button>
          <button type="button" :disabled="!selected.report_id" @click="openReport(selected)">分析报告</button>
        </footer>
      </section>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import { getSimulationHistory } from '../api/simulation'

const router = useRouter()
const simulations = ref([])
const loading = ref(true)
const error = ref('')
const selected = ref(null)

onMounted(loadHistory)

async function loadHistory() {
  loading.value = true
  error.value = ''
  try {
    const res = await getSimulationHistory(40)
    simulations.value = Array.isArray(res.data) ? res.data : []
  } catch (err) {
    error.value = '历史记录读取失败，请确认后端服务已经启动。'
  } finally {
    loading.value = false
  }
}

function shortSimulationId(value) {
  return value ? `SIM_${value.replace('sim_', '').slice(0, 6).toUpperCase()}` : 'SIM_UNKNOWN'
}

function titleFor(item) {
  const text = item.simulation_requirement || item.project_name || item.simulation_id || '未命名模拟'
  return text.length > 24 ? `${text.slice(0, 24)}...` : text
}

function dateText(value) {
  if (!value) return '未知时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mm = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d} ${hh}:${mm}`
}

function progressState(item) {
  const current = Number(item.current_round || 0)
  const total = Number(item.total_rounds || 0)
  if (!total || !current) return 'not-started'
  return current >= total ? 'completed' : 'in-progress'
}

function progressText(item) {
  const current = Number(item.current_round || 0)
  const total = Number(item.total_rounds || 0)
  if (!total) return '未开始'
  return `${current}/${total} 轮`
}

function fileExt(filename = '') {
  const ext = filename.split('.').pop()
  return ext ? ext.toUpperCase().slice(0, 4) : 'FILE'
}

function openProject(item) {
  router.push({ name: 'Process', params: { projectId: item.project_id } })
}

function openSimulation(item) {
  router.push({ name: 'Simulation', params: { simulationId: item.simulation_id } })
}

function openReport(item) {
  router.push({ name: 'Analysis', params: { reportId: item.report_id } })
}
</script>

<style scoped>
.history-page {
  min-height: 100vh;
  color: #173126;
}

.history-topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  background: rgba(247, 244, 234, 0.82);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(23, 49, 38, 0.08);
}

.history-actions {
  display: flex;
  gap: 10px;
}

.ghost-link,
.primary-link,
.board-head button,
.modal-actions button {
  border-radius: 999px;
  min-height: 40px;
  padding: 0 16px;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}

.ghost-link,
.board-head button {
  border: 1px solid rgba(23, 49, 38, 0.12);
  background: rgba(255, 255, 255, 0.58);
  color: #173126;
}

.primary-link,
.modal-actions button {
  border: 0;
  background: #1f5d45;
  color: #fff;
}

.modal-actions button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.history-shell {
  width: min(1280px, calc(100vw - 48px));
  margin: 0 auto;
  padding: 64px 0 96px;
}

.history-hero {
  max-width: 760px;
  margin-bottom: 42px;
}

.history-hero span {
  font-family: JetBrains Mono, monospace;
  color: #1f5d45;
  font-weight: 800;
  text-transform: uppercase;
}

.history-hero h1 {
  margin: 14px 0;
  font-family: Fraunces, Georgia, serif;
  font-size: clamp(48px, 8vw, 100px);
  line-height: 1;
  letter-spacing: 0;
}

.history-hero p {
  color: rgba(23, 49, 38, 0.68);
  font-size: 18px;
  line-height: 1.7;
}

.history-board {
  position: relative;
  padding: 28px;
  border: 1px solid rgba(23, 49, 38, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.58);
  box-shadow: 0 28px 90px rgba(31, 50, 40, 0.1);
}

.board-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 22px;
}

.board-head h2 {
  margin: 0;
  font-size: 22px;
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 18px;
}

.project-card {
  display: flex;
  flex-direction: column;
  min-height: 280px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.project-card:hover {
  transform: translateY(-3px);
  border-color: rgba(31, 93, 69, 0.42);
  box-shadow: 0 18px 36px rgba(17, 40, 31, 0.12);
}

.card-header,
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-family: JetBrains Mono, monospace;
  font-size: 12px;
  color: #6b7280;
}

.card-header {
  padding-bottom: 12px;
  border-bottom: 1px solid #f3f4f6;
}

.card-progress {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
}

.card-progress.completed {
  color: #10b981;
}

.card-progress.in-progress {
  color: #f59e0b;
}

.card-progress.not-started {
  color: #9ca3af;
}

.status-dot {
  font-size: 8px;
}

.card-files-wrapper {
  min-height: 72px;
  margin: 14px 0;
  padding: 10px;
  background: linear-gradient(135deg, #f8f9fa, #f1f3f4);
  border: 1px solid #e8eaed;
  border-radius: 6px;
}

.files-list,
.modal-files {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.file-item,
.modal-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.file-tag {
  flex: 0 0 auto;
  min-width: 34px;
  padding: 3px 5px;
  border-radius: 3px;
  background: #e6f2e8;
  color: #437c50;
  font-family: JetBrains Mono, monospace;
  font-size: 11px;
  font-weight: 800;
  text-align: center;
}

.file-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #4b5563;
  font-size: 13px;
}

.files-empty,
.state-card,
.modal-empty {
  color: #8a968f;
}

.project-card h3 {
  margin: 0 0 8px;
  font-size: 17px;
  color: #111827;
}

.project-card p {
  flex: 1;
  margin: 0 0 18px;
  color: #647067;
  line-height: 1.62;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  padding-top: 12px;
  border-top: 1px solid #f3f4f6;
}

.state-card {
  padding: 54px;
  text-align: center;
  border: 1px dashed rgba(23, 49, 38, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.58);
}

.state-card.error {
  color: #a13c3c;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.38);
  backdrop-filter: blur(6px);
}

.modal-content {
  width: min(620px, 100%);
  max-height: min(760px, calc(100vh - 48px));
  overflow: auto;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.24);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  border-bottom: 1px solid #f3f4f6;
}

.modal-id {
  font-family: JetBrains Mono, monospace;
  color: #6b7280;
  font-size: 13px;
}

.modal-header h2 {
  margin: 8px 0;
  font-size: 22px;
}

.modal-header p {
  margin: 0;
  color: #8a968f;
}

.modal-close {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 8px;
  background: #f4f5f3;
  font-size: 22px;
  cursor: pointer;
}

.modal-body {
  padding: 24px 28px;
}

.modal-body h3 {
  margin: 0 0 10px;
  font-size: 14px;
  color: #6b7280;
}

.modal-body p {
  margin: 0 0 22px;
  line-height: 1.7;
  color: #374151;
}

.modal-actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 20px 28px 28px;
}

@media (max-width: 720px) {
  .history-shell {
    width: min(100vw - 28px, 720px);
    padding-top: 42px;
  }

  .history-topbar {
    padding: 0 16px;
  }

  .history-actions {
    gap: 6px;
  }

  .modal-actions {
    grid-template-columns: 1fr;
  }
}
</style>
