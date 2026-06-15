<template>
  <article class="agent-card">
    <div class="agent-card-header">
      <span class="agent-index">{{ index }}</span>
      <div>
        <strong>{{ displayName }}</strong>
        <p>{{ typeLabel }}</p>
      </div>
    </div>
    <p class="agent-summary">{{ summary }}</p>
    <div class="agent-meta">
      <span v-if="primaryRegion">主区域：{{ primaryRegion }}</span>
      <span v-if="roleLabel">角色：{{ roleLabel }}</span>
      <span v-if="sourceLabel">来源：{{ sourceLabel }}</span>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { formatTokenLabelZh } from '../../utils/displayText'

const props = defineProps({
  agent: {
    type: Object,
    default: () => ({})
  },
  index: {
    type: Number,
    default: 1
  }
})

const displayName = computed(() => props.agent.displayName || props.agent.name || props.agent.agent_name || props.agent.username || `代理体 ${props.index}`)
const typeLabel = computed(() => props.agent.agentTypeLabel || formatTokenLabelZh(props.agent.agent_type || props.agent.type || 'agent'))
const summary = computed(() => props.agent.summary || props.agent.description || props.agent.motivation || '等待场景配置生成后补全代理体画像。')
const primaryRegion = computed(() => props.agent.primaryRegionLabel || props.agent.primary_region || '')
const roleLabel = computed(() => props.agent.roleTypeLabel || props.agent.agent_subtype || '')
const sourceLabel = computed(() => props.agent.sourceLabel || props.agent.source || '')
</script>

<style scoped>
.agent-card {
  min-height: 132px;
  border: 1px solid rgba(23, 49, 38, 0.12);
  border-radius: 8px;
  background: rgba(255, 252, 245, 0.78);
  padding: 14px;
}

.agent-card-header {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.agent-index {
  display: grid;
  place-items: center;
  flex: 0 0 28px;
  height: 28px;
  border-radius: 50%;
  background: #1f5d45;
  color: #fffaf1;
  font-size: 12px;
  font-weight: 700;
}

strong {
  color: #173126;
  font-size: 14px;
}

p {
  margin: 0;
}

.agent-card-header p,
.agent-summary,
.agent-meta {
  color: #647067;
  font-size: 12px;
  line-height: 1.55;
}

.agent-summary {
  margin-top: 10px;
}

.agent-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.agent-meta span {
  border: 1px solid rgba(31, 93, 69, 0.14);
  border-radius: 999px;
  padding: 3px 7px;
}
</style>
