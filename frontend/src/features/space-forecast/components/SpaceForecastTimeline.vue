<template>
  <section class="timeline-panel">
    <div class="timeline-head">
      <div>
        <h2>时间进程</h2>
        <p>关键碰撞与阈值节点会在这里持续打点。</p>
      </div>
      <span>{{ events.length }} 个节点</span>
    </div>

    <div v-if="events.length" class="event-track">
      <article v-for="event in events" :key="event.id" class="event-item" :class="event.type">
        <span class="event-dot"></span>
        <div>
          <strong>{{ eventLabel(event) }}</strong>
          <p>{{ formatElapsed(event.elapsedMonths) }} · {{ shellLabel(event.shellId) }}</p>
        </div>
      </article>
    </div>

    <div v-else class="empty-state">
      选择碰撞等级和高度带后，首次碰撞会从当前时刻开始。
    </div>
  </section>
</template>

<script setup>
const props = defineProps({
  events: {
    type: Array,
    default: () => []
  }
})

const labels = {
  initial_collision: '首次碰撞',
  follow_on_collision: '后续碰撞',
  cascade_collision: '级联碰撞',
  threshold_reached: '进入凯斯勒阈值',
  operational_collapse: '运营不可用',
  hard_limit: '硬上限停止'
}

const eventLabel = (event) => {
  if (event.type === 'cascade_collision' && event.eventCount > 1) return `${event.eventCount} 次级联碰撞`
  return labels[event.type] || event.title || '事件'
}

const shellLabel = (shellId) => {
  if (!shellId) return '未知壳层'
  return `${shellId} km`
}

const formatElapsed = (months) => {
  const value = Number(months || 0)
  if (value <= 0) return '起点'
  if (value < 12) return `${value} 个月`
  const years = Math.floor(value / 12)
  const rest = value % 12
  return rest ? `${years} 年 ${rest} 个月` : `${years} 年`
}
</script>

<style scoped>
.timeline-panel {
  border: 1px solid rgba(91, 141, 116, 0.22);
  background: rgba(255, 255, 255, 0.88);
  padding: 18px;
  color: #173126;
}

.timeline-head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid rgba(31, 93, 69, 0.12);
  padding-bottom: 12px;
}

h2,
p {
  margin: 0;
}

h2 {
  font-size: 17px;
}

.timeline-head p,
.timeline-head span,
.event-item p,
.empty-state {
  color: #667b70;
  font-size: 12px;
  line-height: 1.6;
}

.event-track {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding-top: 16px;
}

.event-item {
  min-width: 148px;
  border-left: 2px solid rgba(31, 93, 69, 0.18);
  padding-left: 12px;
  position: relative;
}

.event-dot {
  position: absolute;
  left: -7px;
  top: 2px;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #0891b2;
  box-shadow: 0 0 14px rgba(8, 145, 178, 0.5);
}

.event-item.follow_on_collision .event-dot,
.event-item.cascade_collision .event-dot {
  background: #ea580c;
  box-shadow: 0 0 14px rgba(234, 88, 12, 0.5);
}

.event-item.threshold_reached .event-dot {
  background: #e11d48;
  box-shadow: 0 0 14px rgba(225, 29, 72, 0.55);
}

.event-item.hard_limit .event-dot {
  background: #64748b;
  box-shadow: 0 0 14px rgba(100, 116, 139, 0.5);
}

.event-item.operational_collapse .event-dot {
  background: #991b1b;
  box-shadow: 0 0 14px rgba(153, 27, 27, 0.55);
}

strong {
  display: block;
  font-size: 13px;
}

.empty-state {
  padding-top: 14px;
}
</style>
