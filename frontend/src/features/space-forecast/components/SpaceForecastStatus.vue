<template>
  <section class="status-bar">
    <div class="status-tabs">
      <div class="status-tab">
        <label>推演年份</label>
        <span class="value">{{ snapshot.currentYear }}</span>
      </div>
      <div class="status-tab">
        <label>可用卫星</label>
        <span class="value">{{ format(snapshot.activeSatellites) }}</span>
      </div>
      <div class="status-tab">
        <label>预测碰撞率</label>
        <span class="value">{{ snapshot.globalCollisionRatePerYear.toFixed(1) }} <small>次/年</small></span>
      </div>
      <div class="status-tab">
        <label>碎片总量</label>
        <span class="value">{{ format(snapshot.totalDebris) }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  snapshot: {
    type: Object,
    required: true
  }
})

const format = (value) => Math.round(value).toLocaleString('zh-CN')
</script>

<style scoped>
.status-bar {
  width: 100%;
  padding: 8px 20px;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.status-tabs {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 2px;
}

.status-tab {
  padding: 10px 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 140px;
  border-right: 1px solid rgba(255, 255, 255, 0.05);
}

.status-tab:last-of-type {
  border-right: 0;
}

label {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(255, 255, 255, 0.5);
}

.value {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  font-variant-numeric: tabular-nums;
}

.value small {
  font-size: 11px;
  font-weight: 400;
  opacity: 0.6;
}

.value.warning {
  color: #fb923c;
}

</style>
