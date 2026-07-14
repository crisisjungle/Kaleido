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
    <div v-if="capabilityLabels.length" class="agent-capability-preview" aria-label="核心能力">
      <span v-for="label in capabilityLabels.slice(0, 3)" :key="label">{{ label }}</span>
      <span v-if="capabilityLabels.length > 3">+{{ capabilityLabels.length - 3 }}</span>
    </div>
    <div class="agent-meta">
      <span v-if="primaryRegion">主区域：{{ primaryRegion }}</span>
      <span v-if="roleLabel">角色：{{ roleLabel }}</span>
      <span v-if="sourceLabel">来源：{{ sourceLabel }}</span>
    </div>
    <div class="agent-profile-status">
      <span>{{ lifecycleLabel }}</span>
      <span>{{ representationLabel }}</span>
      <span v-if="confidenceLabel">档案置信度 {{ confidenceLabel }}</span>
      <span v-if="isAggregate">聚合主体</span>
    </div>

    <details v-if="hasProfileDetails" class="agent-profile-details">
      <summary>查看完整档案</summary>
      <div class="profile-section">
        <strong>能力与行动边界</strong>
        <div class="profile-chip-list">
          <span v-for="label in capabilityLabels" :key="`cap-${label}`">{{ label }}</span>
          <span v-for="label in actionLabels" :key="`action-${label}`" class="action-chip">可执行：{{ label }}</span>
        </div>
      </div>
      <div class="profile-section">
        <strong>权限边界</strong>
        <div class="profile-chip-list">
          <span v-for="label in permissionLabels" :key="`permission-${label}`">{{ label }}</span>
          <span v-if="permissionLabels.length === 0" class="muted-chip">无行政强制权限</span>
        </div>
      </div>
      <div v-if="resourceRows.length" class="profile-section">
        <strong>初始资源</strong>
        <dl class="resource-list">
          <div v-for="resource in resourceRows" :key="resource.key">
            <dt>{{ resource.label }}</dt>
            <dd>{{ resource.value }}<small v-if="resource.uncertainty"> · {{ resource.uncertainty }}</small></dd>
          </div>
        </dl>
      </div>
      <div class="profile-section profile-evidence">
        <strong>建档依据</strong>
        <p>{{ evidenceSummary }}</p>
        <p v-if="generationReason">{{ generationReason }}</p>
      </div>
    </details>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { formatTokenLabelZh, sanitizeDisplayCopy } from '../../utils/displayText'

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

const safeOptional = (value, fallback) => value ? sanitizeDisplayCopy(value, fallback) : ''

const displayName = computed(() => sanitizeDisplayCopy(
  props.agent.displayName || props.agent.name || props.agent.agent_name || props.agent.username,
  `代理体 ${props.index}`
))
const typeLabel = computed(() => sanitizeDisplayCopy(
  props.agent.agentTypeLabel || formatTokenLabelZh(props.agent.agent_type || props.agent.type || 'agent'),
  '代理体'
))
const summary = computed(() => sanitizeDisplayCopy(
  props.agent.summary || props.agent.description || props.agent.motivation,
  '等待场景配置生成后补全代理体画像。'
))
const primaryRegion = computed(() => safeOptional(props.agent.primaryRegionLabel || props.agent.primary_region, '未知区域'))
const roleLabel = computed(() => safeOptional(formatTokenLabelZh(props.agent.roleTypeLabel || props.agent.agent_subtype || '', ''), '其他角色'))
const sourceLabel = computed(() => safeOptional(formatTokenLabelZh(props.agent.sourceLabel || props.agent.source || '', ''), '系统配置'))

const localizedTokens = (values, limit = 12) => {
  const result = []
  ;(Array.isArray(values) ? values : []).forEach((value) => {
    const label = sanitizeDisplayCopy(formatTokenLabelZh(value, ''), '')
    if (label && !result.includes(label)) result.push(label)
  })
  return result.slice(0, limit)
}

const capabilityLabels = computed(() => localizedTokens(
  props.agent.capabilityLabels?.length ? props.agent.capabilityLabels : props.agent.capabilityKeys,
  10
))
const permissionLabels = computed(() => localizedTokens(props.agent.permissionKeys, 10))
const actionLabels = computed(() => localizedTokens(props.agent.actionSpace, 8))
const lifecycleLabel = computed(() => sanitizeDisplayCopy(
  formatTokenLabelZh(props.agent.lifecycleStatus || 'active', '活跃'),
  '活跃'
))
const representationLabel = computed(() => sanitizeDisplayCopy(
  formatTokenLabelZh(props.agent.representationLevel || (props.agent.isAggregate ? 'aggregate_allowed' : 'organization'), '组织级'),
  props.agent.isAggregate ? '聚合表示' : '组织级'
))
const isAggregate = computed(() => Boolean(props.agent.isAggregate))
const confidenceLabel = computed(() => {
  const raw = Number(props.agent.profileConfidence ?? props.agent.evidenceConfidence)
  if (!Number.isFinite(raw)) return ''
  const percent = raw <= 1 ? raw * 100 : raw
  return `${Math.max(0, Math.min(100, Math.round(percent)))}%`
})
const resourceRows = computed(() => {
  const budget = props.agent.resourceBudget && typeof props.agent.resourceBudget === 'object'
    ? props.agent.resourceBudget
    : {}
  const uncertainty = props.agent.resourceUncertainty && typeof props.agent.resourceUncertainty === 'object'
    ? props.agent.resourceUncertainty
    : {}
  return Object.entries(budget).slice(0, 10).map(([key, value]) => {
    const range = Array.isArray(uncertainty[key]) ? uncertainty[key] : []
    return {
      key,
      label: sanitizeDisplayCopy(formatTokenLabelZh(key, ''), '相对资源'),
      value: Number.isFinite(Number(value)) ? Math.round(Number(value) * 10) / 10 : '待核验',
      uncertainty: range.length >= 2 ? `估计范围 ${Math.round(Number(range[0]))}–${Math.round(Number(range[1]))}` : ''
    }
  })
})
const generationReason = computed(() => safeOptional(props.agent.generationReason, '由场景角色需求生成。'))
const evidenceSummary = computed(() => {
  const evidenceCount = Array.isArray(props.agent.evidenceRefs) ? props.agent.evidenceRefs.length : 0
  const demandCount = Array.isArray(props.agent.roleDemandRefs) ? props.agent.roleDemandRefs.length : 0
  const parts = []
  if (demandCount) parts.push(`覆盖 ${demandCount} 项角色需求`)
  if (evidenceCount) parts.push(`引用 ${evidenceCount} 项证据`)
  return parts.length ? parts.join('，') : '当前为明确标记的低证据或聚合档案。'
})
const hasProfileDetails = computed(() => Boolean(
  capabilityLabels.value.length ||
  permissionLabels.value.length ||
  actionLabels.value.length ||
  resourceRows.value.length ||
  props.agent.generationReason ||
  props.agent.roleDemandRefs?.length
))
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

.agent-capability-preview,
.agent-profile-status,
.profile-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-capability-preview {
  margin-top: 10px;
}

.agent-capability-preview span,
.agent-profile-status span,
.profile-chip-list span {
  border-radius: 4px;
  background: rgba(31, 93, 69, 0.08);
  color: #315b49;
  padding: 3px 6px;
  font-size: 11px;
  line-height: 1.35;
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

.agent-profile-status {
  margin-top: 8px;
}

.agent-profile-status span {
  background: rgba(91, 105, 96, 0.08);
  color: #647067;
}

.agent-profile-details {
  margin-top: 12px;
  border-top: 1px solid rgba(23, 49, 38, 0.1);
  padding-top: 9px;
}

.agent-profile-details summary {
  cursor: pointer;
  color: #1f5d45;
  font-size: 12px;
  font-weight: 650;
}

.profile-section {
  margin-top: 12px;
}

.profile-section > strong {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
}

.profile-chip-list .action-chip {
  background: rgba(43, 94, 140, 0.09);
  color: #315a78;
}

.profile-chip-list .muted-chip {
  background: rgba(91, 105, 96, 0.08);
  color: #6d766f;
}

.resource-list {
  display: grid;
  gap: 5px;
  margin: 0;
}

.resource-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(23, 49, 38, 0.07);
  padding-bottom: 4px;
  color: #647067;
  font-size: 11px;
}

.resource-list dt,
.resource-list dd {
  margin: 0;
}

.resource-list dd {
  color: #173126;
  text-align: right;
}

.resource-list small {
  color: #7a847d;
  font-size: 10px;
}

.profile-evidence p {
  color: #647067;
  font-size: 11px;
  line-height: 1.55;
}
</style>
