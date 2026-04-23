<template>
  <section v-if="points.length" class="charts-panel" :class="{ 'is-collapsed': collapsed }">
    <button class="collapse-toggle" @click="$emit('update:collapsed', !collapsed)">
      <span class="icon">{{ collapsed ? '❮' : '❯' }}</span>
    </button>
    <div class="sidebar-content">
      <div class="panel-head">
        <h2>推演图表</h2>
        <p>以首次碰撞后的状态为起点，持续记录碰撞率、碰撞总数、受事故影响剩余卫星和碎片总量。</p>
      </div>

      <div class="chart-list">
      <article v-for="chart in charts" :key="chart.key" class="chart-card">
        <div class="chart-header">
          <div>
            <h3>{{ chart.title }}</h3>
            <p>当前 {{ chart.format(latestValue(chart.key)) }} {{ chart.unit }}</p>
          </div>
          <strong :style="{ color: chart.color }">
            {{ deltaValue(chart) }}
          </strong>
        </div>

        <svg viewBox="0 0 260 82" preserveAspectRatio="none" role="img" :aria-label="chart.title">
          <line x1="0" y1="74" x2="260" y2="74" stroke="rgba(31,93,69,.14)" />
          <polyline
            :points="polyline(chart.key)"
            fill="none"
            :stroke="chart.color"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>

        <div class="axis">
          <span>{{ points[0]?.label }}</span>
          <span>{{ points[points.length - 1]?.label }}</span>
        </div>
      </article>
      </div>
    </div>
  </section>
</template>

<script setup>
const props = defineProps({
  points: {
    type: Array,
    default: () => []
  },
  collapsed: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:collapsed'])

const charts = [
  {
    key: 'collisionRate',
    title: '碰撞率增加',
    unit: '次/年',
    color: '#0891b2',
    format: (value) => Number(value || 0).toFixed(2)
  },
  {
    key: 'collisionCount',
    title: '碰撞总数',
    unit: '次',
    color: '#ea580c',
    format: (value) => Math.round(value || 0).toLocaleString('zh-CN')
  },
  {
    key: 'survivingActiveSatellites',
    title: '受事故影响剩余卫星',
    unit: '颗',
    color: '#10b981',
    format: (value) => Math.round(value || 0).toLocaleString('zh-CN')
  },
  {
    key: 'totalDebris',
    title: '轨道总碎片数',
    unit: '个',
    color: '#e11d48',
    format: (value) => Math.round(value || 0).toLocaleString('zh-CN')
  }
]

const latestValue = (key) => props.points[props.points.length - 1]?.[key] ?? 0

const deltaValue = (chart) => {
  const first = props.points[0]?.[chart.key] ?? 0
  const latest = latestValue(chart.key)
  const delta = latest - first
  return `${delta >= 0 ? '+' : ''}${chart.format(delta)}`
}

const polyline = (key) => {
  const values = props.points.map((point) => Number(point[key] || 0))
  if (!values.length) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(1, max - min)
  return values
    .map((value, index) => {
      const x = values.length <= 1 ? 260 : (index / (values.length - 1)) * 260
      const y = 74 - ((value - min) / span) * 64
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}
</script>

<style scoped>
.charts-panel {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 320px;
  height: 100%;
  background: rgba(8, 10, 15, 0.85);
  backdrop-filter: blur(20px);
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  color: #fff;
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  pointer-events: auto;
}

.charts-panel.is-collapsed {
  transform: translateX(100%);
}

.collapse-toggle {
  position: absolute;
  left: -32px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 60px;
  background: rgba(8, 10, 15, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-right: none;
  border-radius: 8px 0 0 8px;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: #fff;
  transition: background 0.2s;
}

.collapse-toggle:hover {
  background: rgba(20, 25, 35, 0.95);
}

.sidebar-content {
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.panel-head {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 14px;
}

h2,
h3,
p {
  margin: 0;
}

h2 {
  font-size: 18px;
}

.panel-head p,
.chart-header p,
.axis {
  color: rgba(255, 255, 255, 0.4);
  font-size: 12px;
}

.chart-list {
  display: grid;
  gap: 18px;
  margin-top: 18px;
}

.chart-card {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 16px;
}

.chart-card:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 10px;
}

h3 {
  font-size: 14px;
}

svg {
  display: block;
  width: 100%;
  height: 82px;
}

.axis {
  display: flex;
  justify-content: space-between;
}
</style>
