<template>
  <div v-if="summary" class="modal-overlay" @click.self="$emit('close')">
    <section class="result-modal" :class="{ unresolved: summary.reason === 'hard_limit' }">
      <header class="modal-header">
        <div>
          <h2>推演结论</h2>
          <p>{{ summary.reasonText }}</p>
        </div>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </header>

      <div class="modal-body">
        <div class="stats-grid">
          <div class="stat-item">
            <label>推演总时长</label>
            <span class="value">{{ summary.elapsed }}</span>
          </div>
          <div class="stat-item">
            <label>碰撞总数</label>
            <span class="value">{{ Number(summary.collisionCount || 0).toLocaleString('zh-CN') }} <small>次</small></span>
          </div>
          <div class="stat-item">
            <label>级联触发壳层</label>
            <span class="value">{{ summary.triggerShell }}</span>
          </div>
          <div class="stat-item">
            <label>进入凯斯勒阈值</label>
            <span class="value">{{ summary.thresholdReached ? summary.yearReached : '未触发' }}</span>
          </div>
          <div class="stat-item highlight">
            <label>碎片净增长</label>
            <span class="value">{{ summary.debrisGrowth }}</span>
          </div>
        </div>

        <div class="narrative-box">
          <p>{{ summary.narrative }}</p>
        </div>
      </div>

      <footer class="modal-footer">
        <button class="reset-btn" @click="$emit('reset')">重置推演场景</button>
      </footer>
    </section>
  </div>
</template>

<script setup>
defineProps({
  summary: {
    type: Object,
    default: null
  }
})

defineEmits(['reset', 'close'])
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.result-modal {
  width: 100%;
  max-width: 540px;
  background: #0f172a;
  border: 1px solid rgba(225, 29, 72, 0.4);
  box-shadow: 0 0 40px rgba(225, 29, 72, 0.2);
  display: flex;
  flex-direction: column;
}

.result-modal.unresolved {
  border-color: rgba(100, 116, 139, 0.4);
  box-shadow: 0 0 40px rgba(100, 116, 139, 0.2);
}

.modal-header {
  padding: 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.modal-header h2 {
  margin: 0 0 4px;
  font-size: 20px;
  color: #fff;
}

.modal-header p {
  margin: 0;
  font-size: 14px;
  color: #94a3b8;
}

.close-btn {
  background: none;
  border: none;
  color: #94a3b8;
  font-size: 20px;
  cursor: pointer;
  padding: 4px;
}

.modal-body {
  padding: 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-item.highlight {
  grid-column: span 2;
  padding-top: 12px;
  border-top: 1px dashed rgba(255, 255, 255, 0.1);
}

.stat-item label {
  font-size: 12px;
  color: #64748b;
  text-transform: uppercase;
}

.stat-item .value {
  font-size: 18px;
  font-weight: 700;
  color: #f1f5f9;
}

.stat-item .value small {
  font-size: 12px;
  font-weight: 400;
  opacity: 0.6;
}

.stat-item.highlight .value {
  color: #ef4444;
  font-size: 24px;
}

.narrative-box {
  background: rgba(255, 255, 255, 0.03);
  padding: 16px;
  border-radius: 4px;
  border-left: 3px solid #ef4444;
}

.narrative-box p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: #cbd5e1;
}

.modal-footer {
  padding: 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  justify-content: flex-end;
}

.reset-btn {
  background: #ef4444;
  color: #fff;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
}

.reset-btn:hover {
  background: #dc2626;
}
</style>
