<template>
  <div class="workflow-shell" :class="`mode-${effectiveViewMode}`">
    <header class="workflow-shell__header">
      <KaleidoNavBrand to="/" />

      <div class="workflow-shell__meta">
        <button
          v-if="showVisualToggle"
          type="button"
          class="workflow-shell__visual-toggle"
          :aria-pressed="effectiveViewMode !== 'workbench'"
          @click="handleVisualToggle"
        >
          <span class="workflow-shell__toggle-icon" aria-hidden="true">▣</span>
          {{ effectiveViewMode === 'workbench' ? expandLabel : collapseLabel }}
        </button>

        <WorkflowStepMenu :current-step="step" :current-name="stepName" />
        <span v-if="statusText" class="workflow-shell__divider" aria-hidden="true"></span>
        <span v-if="statusText" class="workflow-shell__status" :class="`is-${statusTone}`">
          <span class="workflow-shell__status-dot" aria-hidden="true"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <main
      class="workflow-shell__body"
      :style="{ '--workflow-visual-ratio': `${visualRatio}%` }"
    >
      <section class="workflow-shell__visual" :aria-hidden="effectiveViewMode === 'workbench'">
        <slot name="visual" />
      </section>

      <section class="workflow-shell__workbench">
        <slot />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import KaleidoNavBrand from './KaleidoNavBrand.vue'
import WorkflowStepMenu from './WorkflowStepMenu.vue'

const props = defineProps({
  step: { type: Number, required: true },
  stepName: { type: String, required: true },
  statusText: { type: String, default: '就绪' },
  statusTone: {
    type: String,
    default: 'ready',
    validator: value => ['ready', 'processing', 'warning', 'error'].includes(value)
  },
  viewMode: {
    type: String,
    default: 'split',
    validator: value => ['graph', 'map', 'split', 'workbench'].includes(value)
  },
  visualRatio: { type: Number, default: 42 },
  showVisualToggle: { type: Boolean, default: true },
  expandLabel: { type: String, default: '展开图谱' },
  collapseLabel: { type: String, default: '收起图谱' }
})

const emit = defineEmits(['toggle-visual'])
const isNarrow = ref(false)
const narrowVisualOpen = ref(false)
let narrowMediaQuery = null

const effectiveViewMode = computed(() => {
  if (!isNarrow.value) return props.viewMode
  return narrowVisualOpen.value ? 'graph' : 'workbench'
})

function syncNarrowViewport(event) {
  const nextNarrow = Boolean(event?.matches)
  if (nextNarrow !== isNarrow.value) narrowVisualOpen.value = false
  isNarrow.value = nextNarrow
}

function handleVisualToggle() {
  if (isNarrow.value) {
    narrowVisualOpen.value = !narrowVisualOpen.value
    return
  }
  emit('toggle-visual')
}

onMounted(() => {
  narrowMediaQuery = window.matchMedia('(max-width: 760px)')
  syncNarrowViewport(narrowMediaQuery)
  narrowMediaQuery.addEventListener?.('change', syncNarrowViewport)
})

onUnmounted(() => {
  narrowMediaQuery?.removeEventListener?.('change', syncNarrowViewport)
})
</script>

<style scoped>
.workflow-shell {
  height: 100dvh;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  color: var(--k-text, #16352a);
  background: var(--k-page, #f4f7f3);
  font-family: var(--k-font-sans, 'Noto Sans SC', system-ui, sans-serif);
  font-size: var(--k-text-body);
  line-height: var(--k-leading-body);
}

.workflow-shell__header {
  position: relative;
  z-index: 100;
  flex: 0 0 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 0 24px;
  border-bottom: 1px solid var(--k-border, rgba(22, 53, 42, 0.12));
  background: rgba(247, 249, 246, 0.94);
  backdrop-filter: blur(16px);
}

.workflow-shell__meta {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
}

.workflow-shell__visual-toggle {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 13px;
  border: 1px solid var(--k-border-strong, rgba(22, 53, 42, 0.18));
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--k-text, #16352a);
  font: inherit;
  font-size: var(--k-text-meta);
  font-weight: 700;
  cursor: pointer;
  transition: border-color 160ms ease, background 160ms ease, color 160ms ease;
}

.workflow-shell__visual-toggle:hover {
  border-color: var(--k-accent, #2f6f57);
  color: var(--k-accent, #2f6f57);
  background: #fff;
}

.workflow-shell__visual-toggle:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--k-accent, #2f6f57) 42%, transparent);
  outline-offset: 2px;
}

.workflow-shell__toggle-icon {
  font-size: 13px;
  line-height: 1;
}

.workflow-shell__divider {
  width: 1px;
  height: 18px;
  background: var(--k-border, rgba(22, 53, 42, 0.12));
}

.workflow-shell__status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: max-content;
  color: var(--k-text-muted, #64756e);
  font-size: var(--k-text-meta);
  font-weight: 650;
}

.workflow-shell__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: currentColor;
}

.workflow-shell__status.is-ready { color: var(--k-success, #3d8a61); }
.workflow-shell__status.is-processing { color: var(--k-accent, #2f6f57); }
.workflow-shell__status.is-warning { color: var(--k-warning, #a86a26); }
.workflow-shell__status.is-error { color: var(--k-danger, #b94a43); }

.workflow-shell__status.is-processing .workflow-shell__status-dot {
  animation: workflow-status-pulse 1.4s ease-in-out infinite;
}

.workflow-shell__body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, var(--workflow-visual-ratio)) minmax(0, calc(100% - var(--workflow-visual-ratio)));
  overflow: hidden;
  transition: grid-template-columns 260ms ease;
}

.workflow-shell.mode-workbench .workflow-shell__body {
  grid-template-columns: 0 minmax(0, 1fr);
}

.workflow-shell.mode-graph .workflow-shell__body,
.workflow-shell.mode-map .workflow-shell__body {
  grid-template-columns: minmax(0, 1fr) 0;
}

.workflow-shell__visual,
.workflow-shell__workbench {
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.workflow-shell__visual {
  border-right: 1px solid var(--k-border, rgba(22, 53, 42, 0.12));
  background: #fff;
}

.workflow-shell.mode-workbench .workflow-shell__visual,
.workflow-shell.mode-graph .workflow-shell__workbench,
.workflow-shell.mode-map .workflow-shell__workbench {
  visibility: hidden;
  pointer-events: none;
}

@keyframes workflow-status-pulse {
  50% { opacity: 0.35; }
}

@media (max-width: 900px) {
  .workflow-shell__header { padding: 0 14px; }
  .workflow-shell__visual-toggle { width: 36px; padding: 0; }
  .workflow-shell__visual-toggle:not(:focus) { font-size: 0; }
  .workflow-shell__toggle-icon { font-size: 13px; }
  .workflow-shell__meta { gap: 9px; }
  .workflow-shell__divider { display: none; }
}

@media (max-width: 760px) {
  .workflow-shell__header {
    gap: 8px;
    padding-inline: 10px;
  }

  .workflow-shell__meta {
    gap: 4px;
  }

  .workflow-shell__status {
    display: none;
  }

  .workflow-shell__header :deep(.workflow-trigger) {
    gap: 5px;
    padding-inline: 6px;
  }
}

@media (max-width: 430px) {
  .workflow-shell__header :deep(.step-num) {
    display: none;
  }

  .workflow-shell__header :deep(.kaleido-nav-brand__title) {
    font-size: 0.95rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .workflow-shell__body,
  .workflow-shell__visual-toggle { transition: none; }
  .workflow-shell__status.is-processing .workflow-shell__status-dot { animation: none; }
}
</style>
