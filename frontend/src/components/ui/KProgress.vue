<template>
  <div class="k-progress" :class="[`k-progress--${size}`, { 'is-indeterminate': indeterminate }]">
    <div v-if="label || showValue" class="k-progress__header">
      <span v-if="label" class="k-progress__label">{{ label }}</span>
      <span v-if="showValue" class="k-progress__value">{{ resolvedValueText }}</span>
    </div>
    <div
      class="k-progress__track"
      role="progressbar"
      :aria-label="ariaLabel || label || '进度'"
      :aria-valuemin="indeterminate ? undefined : 0"
      :aria-valuemax="indeterminate ? undefined : safeMax"
      :aria-valuenow="indeterminate ? undefined : safeValue"
      :aria-valuetext="indeterminate ? '进行中' : resolvedValueText"
    >
      <span class="k-progress__fill" :style="fillStyle" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: {
    type: Number,
    default: 0
  },
  max: {
    type: Number,
    default: 100
  },
  label: {
    type: String,
    default: ''
  },
  ariaLabel: {
    type: String,
    default: ''
  },
  valueText: {
    type: String,
    default: ''
  },
  showValue: {
    type: Boolean,
    default: true
  },
  indeterminate: Boolean,
  size: {
    type: String,
    default: 'md',
    validator: value => ['sm', 'md', 'lg'].includes(value)
  }
})

const safeMax = computed(() => (Number.isFinite(props.max) && props.max > 0 ? props.max : 100))
const safeValue = computed(() => {
  if (!Number.isFinite(props.value)) return 0
  return Math.min(Math.max(props.value, 0), safeMax.value)
})
const ratio = computed(() => safeValue.value / safeMax.value)
const resolvedValueText = computed(() => props.valueText || `${Math.round(ratio.value * 100)}%`)
const fillStyle = computed(() => (props.indeterminate ? undefined : { transform: `scaleX(${ratio.value})` }))
</script>

<style scoped>
.k-progress {
  width: 100%;
  min-width: 0;
}

.k-progress__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--k-space-3);
  margin-bottom: var(--k-space-2);
}

.k-progress__label {
  min-width: 0;
  overflow: hidden;
  color: var(--k-color-text-secondary);
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  font-weight: 550;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k-progress__value {
  flex: 0 0 auto;
  color: var(--k-color-brand-700);
  font-family: var(--k-font-mono);
  font-size: var(--k-text-body);
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}

.k-progress__track {
  position: relative;
  width: 100%;
  height: 0.5rem;
  overflow: hidden;
  background: var(--k-color-surface-muted);
  border-radius: 999px;
}

.k-progress--sm .k-progress__track {
  height: 0.25rem;
}

.k-progress--lg .k-progress__track {
  height: 0.625rem;
}

.k-progress__fill {
  position: absolute;
  inset: 0;
  background: var(--k-color-brand-600);
  border-radius: inherit;
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform var(--k-transition-base);
}

.k-progress.is-indeterminate .k-progress__fill {
  right: 62%;
  border-radius: inherit;
  transform: translateX(-100%);
  animation: k-progress-indeterminate 1.25s ease-in-out infinite;
}

@keyframes k-progress-indeterminate {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(430%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .k-progress.is-indeterminate .k-progress__fill {
    right: 0;
    opacity: 0.65;
    transform: none;
    animation: none;
  }
}
</style>
