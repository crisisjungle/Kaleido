<template>
  <footer
    class="workflow-action-bar"
    :class="{
      'workflow-action-bar--sticky': sticky,
      'workflow-action-bar--elevated': elevated,
      'workflow-action-bar--compact': compact
    }"
    role="toolbar"
    :aria-label="ariaLabel"
  >
    <div class="workflow-action-bar__summary">
      <slot />
    </div>
    <div class="workflow-action-bar__actions">
      <slot name="actions" />
    </div>
  </footer>
</template>

<script setup>
defineProps({
  sticky: {
    type: Boolean,
    default: false
  },
  elevated: {
    type: Boolean,
    default: false
  },
  compact: Boolean,
  ariaLabel: {
    type: String,
    default: '流程操作'
  }
})
</script>

<style scoped>
.workflow-action-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--k-space-5);
  width: 100%;
  min-height: var(--k-action-bar-min-height);
  padding: 0.875rem 1rem calc(0.875rem + env(safe-area-inset-bottom, 0px));
  border: 0;
  border-top: 1px solid var(--k-color-border);
  border-radius: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.76), #ffffff 34%);
  container-type: inline-size;
}

.workflow-action-bar--sticky {
  position: sticky;
  bottom: 0;
  z-index: var(--k-z-sticky);
}

.workflow-action-bar--elevated {
  box-shadow: none;
}

.workflow-action-bar--compact {
  min-height: 3.75rem;
  padding-top: var(--k-space-2);
  padding-bottom: calc(var(--k-space-2) + env(safe-area-inset-bottom, 0px));
}

.workflow-action-bar__summary {
  min-width: 0;
  color: var(--k-color-text-secondary);
  font-family: var(--k-font-sans);
  font-size: var(--k-text-body);
  line-height: 1.45;
}

.workflow-action-bar__summary:empty {
  display: none;
}

.workflow-action-bar__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--k-space-2);
  min-width: 0;
}

@container (max-width: 38rem) {
  .workflow-action-bar__summary,
  .workflow-action-bar__actions {
    grid-column: 1 / -1;
  }

  .workflow-action-bar__actions {
    flex-wrap: wrap;
    justify-content: stretch;
  }

  .workflow-action-bar__actions :deep(> *) {
    flex: 1 1 auto;
  }
}
</style>
