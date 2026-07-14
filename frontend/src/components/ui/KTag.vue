<template>
  <span
    class="k-tag"
    :class="[`k-tag--${tone}`, `k-tag--${variant}`, `k-tag--${size}`]"
    :style="maxWidth ? { maxWidth } : undefined"
  >
    <span class="k-tag__label"><slot /></span>
    <button
      v-if="removable"
      class="k-tag__remove"
      type="button"
      :aria-label="removeLabel"
      @click.stop="emit('remove')"
    >
      <span aria-hidden="true">×</span>
    </button>
  </span>
</template>

<script setup>
defineProps({
  tone: {
    type: String,
    default: 'neutral',
    validator: value => ['neutral', 'brand', 'success', 'warning', 'danger'].includes(value)
  },
  variant: {
    type: String,
    default: 'outline',
    validator: value => ['outline', 'status'].includes(value)
  },
  size: {
    type: String,
    default: 'sm',
    validator: value => ['sm', 'md'].includes(value)
  },
  maxWidth: {
    type: String,
    default: ''
  },
  removable: Boolean,
  removeLabel: {
    type: String,
    default: '移除标签'
  }
})

const emit = defineEmits(['remove'])
</script>

<style scoped>
.k-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
  max-width: 100%;
  color: var(--k-color-text-secondary);
  background: transparent;
  border: 1px solid var(--k-color-border-strong);
  border-radius: 999px;
  font-family: var(--k-font-sans);
  font-weight: 500;
  line-height: 1;
  vertical-align: middle;
}

.k-tag--sm {
  min-height: 1.5rem;
  padding: 0 0.5625rem;
  font-size: var(--k-text-meta);
}

.k-tag--md {
  min-height: 1.75rem;
  padding: 0 0.6875rem;
  font-size: var(--k-text-body);
}

.k-tag--brand {
  color: var(--k-color-brand-700);
  border-color: rgba(31, 93, 69, 0.38);
}

.k-tag--success {
  color: var(--k-color-success);
  border-color: rgba(35, 118, 83, 0.36);
}

.k-tag--warning {
  color: var(--k-color-warning);
  border-color: rgba(154, 103, 0, 0.34);
}

.k-tag--danger {
  color: var(--k-color-danger);
  border-color: rgba(161, 60, 60, 0.34);
}

.k-tag--status.k-tag--neutral {
  background: var(--k-color-surface-muted);
}

.k-tag--status.k-tag--brand {
  background: var(--k-color-brand-100);
}

.k-tag--status.k-tag--success {
  background: var(--k-color-success-soft);
}

.k-tag--status.k-tag--warning {
  background: var(--k-color-warning-soft);
}

.k-tag--status.k-tag--danger {
  background: var(--k-color-danger-soft);
}

.k-tag__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.k-tag__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1rem;
  height: 1rem;
  margin-right: -0.25rem;
  color: currentColor;
  background: transparent;
  border: 0;
  border-radius: 50%;
  font: inherit;
  line-height: 1;
  cursor: pointer;
  opacity: 0.7;
}

.k-tag__remove:hover {
  background: var(--k-color-pressed);
  opacity: 1;
}

.k-tag__remove:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 1px;
}
</style>
