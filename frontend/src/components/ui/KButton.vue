<template>
  <button
    class="k-button"
    :class="[
      `k-button--${variant}`,
      `k-button--${size}`,
      {
        'k-button--block': block,
        'k-button--icon-only': iconOnly,
        'k-button--loading': loading
      }
    ]"
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    @click="handleClick"
  >
    <span v-if="$slots.leading" class="k-button__icon" aria-hidden="true">
      <slot name="leading" />
    </span>
    <span class="k-button__content">
      <slot />
    </span>
    <span v-if="$slots.trailing" class="k-button__icon" aria-hidden="true">
      <slot name="trailing" />
    </span>
    <span v-if="loading" class="k-button__spinner" aria-hidden="true" />
  </button>
</template>

<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'primary',
    validator: value => ['primary', 'secondary', 'ghost', 'text', 'danger'].includes(value)
  },
  size: {
    type: String,
    default: 'md',
    validator: value => ['sm', 'md', 'lg'].includes(value)
  },
  type: {
    type: String,
    default: 'button',
    validator: value => ['button', 'submit', 'reset'].includes(value)
  },
  disabled: Boolean,
  loading: Boolean,
  block: Boolean,
  iconOnly: Boolean
})

const emit = defineEmits(['click'])

const handleClick = event => {
  if (!props.disabled && !props.loading) emit('click', event)
}
</script>

<style scoped>
.k-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--k-space-2);
  min-width: 0;
  border: 1px solid transparent;
  border-radius: var(--k-radius-sm);
  font-family: var(--k-font-sans);
  font-size: var(--k-text-ui);
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  transition:
    color var(--k-transition-fast),
    background-color var(--k-transition-fast),
    border-color var(--k-transition-fast),
    box-shadow var(--k-transition-fast),
    transform var(--k-transition-fast);
}

.k-button--sm {
  min-height: var(--k-control-height-sm);
  padding: 0 var(--k-space-3);
  font-size: var(--k-text-body);
}

.k-button--md {
  min-height: var(--k-control-height-md);
  padding: 0 1rem;
}

.k-button--lg {
  min-height: var(--k-control-height-lg);
  padding: 0 1.25rem;
  font-size: var(--k-text-ui);
}

.k-button--primary {
  color: #ffffff;
  background: var(--k-color-brand-600);
  border-color: var(--k-color-brand-600);
}

.k-button--primary:hover:not(:disabled) {
  background: var(--k-color-brand-hover);
  border-color: var(--k-color-brand-hover);
}

.k-button--secondary {
  color: var(--k-color-brand-700);
  background: var(--k-color-surface);
  border-color: var(--k-color-border-strong);
}

.k-button--secondary:hover:not(:disabled),
.k-button--ghost:hover:not(:disabled) {
  background: var(--k-color-brand-050);
  border-color: rgba(31, 93, 69, 0.34);
}

.k-button--ghost {
  color: var(--k-color-text-secondary);
  background: transparent;
  border-color: transparent;
}

.k-button--text {
  min-height: auto;
  padding-right: var(--k-space-1);
  padding-left: var(--k-space-1);
  color: var(--k-color-brand-600);
  background: transparent;
  border-color: transparent;
}

.k-button--text:hover:not(:disabled) {
  color: var(--k-color-brand-hover);
  background: transparent;
}

.k-button--danger {
  color: var(--k-color-danger);
  background: var(--k-color-danger-soft);
  border-color: rgba(161, 60, 60, 0.24);
}

.k-button--danger:hover:not(:disabled) {
  background: #f6e3e3;
  border-color: rgba(161, 60, 60, 0.4);
}

.k-button:active:not(:disabled) {
  transform: translateY(1px) scale(0.985);
}

.k-button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--k-color-focus);
}

.k-button:disabled {
  color: var(--k-color-text-disabled);
  background: var(--k-color-surface-muted);
  border-color: var(--k-color-border);
  cursor: not-allowed;
  opacity: 0.78;
}

.k-button--block {
  width: 100%;
}

.k-button--icon-only {
  width: var(--k-control-height-md);
  padding: 0;
}

.k-button--icon-only.k-button--sm {
  width: var(--k-control-height-sm);
}

.k-button--icon-only.k-button--lg {
  width: var(--k-control-height-lg);
}

.k-button__content,
.k-button__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.k-button__icon :deep(svg) {
  width: 1em;
  height: 1em;
  stroke-width: 1.75;
}

.k-button--loading .k-button__content,
.k-button--loading .k-button__icon {
  visibility: hidden;
}

.k-button__spinner {
  position: absolute;
  width: 1rem;
  height: 1rem;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: k-button-spin 700ms linear infinite;
}

@keyframes k-button-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .k-button__spinner {
    animation-duration: 1400ms;
  }
}
</style>
