<template>
  <section class="k-mechanism-chain" :class="`is-${density}`" :aria-label="ariaLabel">
    <div class="k-mechanism-chain__viewport">
      <ol class="k-mechanism-chain__track">
        <template v-for="(node, index) in visibleNodes" :key="node.key">
          <li
            class="k-mechanism-chain__node"
            :class="[`is-${node.kind}`, { 'is-omission': node.kind === 'omission' }]"
          >
            <span class="k-mechanism-chain__eyebrow">{{ node.label }}</span>
            <strong>{{ node.text }}</strong>
          </li>
          <li v-if="index < visibleNodes.length - 1" class="k-mechanism-chain__arrow" aria-hidden="true">→</li>
        </template>
      </ol>
    </div>

    <footer v-if="canToggle" class="k-mechanism-chain__footer">
      <span>完整机制链共 {{ nodes.length }} 个节点</span>
      <button type="button" @click="expanded = !expanded">
        {{ expanded ? '收起关键路径' : `展开全部 ${nodes.length} 个节点` }}
      </button>
    </footer>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { MECHANISM_CHAIN_LAYOUT } from '../../config/workflowArchitecture'

const props = defineProps({
  trigger: { type: String, default: '' },
  steps: { type: Array, default: () => [] },
  receptor: { type: String, default: '' },
  consequence: { type: String, default: '' },
  emptyStepLabel: { type: String, default: '机制步骤待补充' },
  ariaLabel: { type: String, default: '机制链' },
})

const expanded = ref(false)

const normalizedSteps = computed(() => props.steps
  .map(item => String(item || '').trim())
  .filter(Boolean))

const nodes = computed(() => {
  const stepNodes = (normalizedSteps.value.length ? normalizedSteps.value : [props.emptyStepLabel]).map((text, index) => ({
    key: `mechanism-${index}-${text}`,
    kind: 'mechanism',
    label: normalizedSteps.value.length > 1 ? `机制 ${index + 1}` : '机制步骤',
    text,
  }))
  return [
    { key: 'trigger', kind: 'trigger', label: '触发源', text: props.trigger || '场景触发因素' },
    ...stepNodes,
    { key: 'receptor', kind: 'receptor', label: '受影响对象', text: props.receptor || '主要受影响对象' },
    { key: 'consequence', kind: 'consequence', label: '具体后果', text: props.consequence || '后果说明待补充' },
  ]
})

const canToggle = computed(() => nodes.value.length > MECHANISM_CHAIN_LAYOUT.overviewMax)
const visibleNodes = computed(() => {
  if (!canToggle.value || expanded.value) return nodes.value
  const head = nodes.value.slice(0, MECHANISM_CHAIN_LAYOUT.collapsedHeadCount)
  const tail = nodes.value.slice(-MECHANISM_CHAIN_LAYOUT.collapsedTailCount)
  const hiddenCount = Math.max(0, nodes.value.length - head.length - tail.length)
  return [
    ...head,
    { key: 'omission', kind: 'omission', label: '中间路径', text: `已折叠 ${hiddenCount} 个节点` },
    ...tail,
  ]
})

const density = computed(() => {
  if (nodes.value.length <= MECHANISM_CHAIN_LAYOUT.completeMax) return 'complete'
  if (nodes.value.length <= MECHANISM_CHAIN_LAYOUT.overviewMax) return 'scrollable'
  return 'long'
})

watch(nodes, () => { expanded.value = false })
</script>

<style scoped>
.k-mechanism-chain {
  min-width: 0;
  display: grid;
  gap: var(--k-space-3, 0.75rem);
}

.k-mechanism-chain__viewport {
  min-width: 0;
  overflow-x: auto;
  padding: 0.2rem 0 0.45rem;
  scrollbar-width: thin;
}

.k-mechanism-chain__track {
  min-width: max-content;
  display: flex;
  align-items: stretch;
  gap: 0.65rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.k-mechanism-chain.is-complete .k-mechanism-chain__track {
  width: 100%;
  min-width: 100%;
}

.k-mechanism-chain.is-complete .k-mechanism-chain__node {
  width: auto;
  min-width: 7rem;
  flex: 1 1 0;
  padding: 0.75rem;
}

.k-mechanism-chain.is-complete .k-mechanism-chain__arrow {
  flex: 0 0 auto;
}

.k-mechanism-chain__node {
  width: clamp(11.5rem, 18vw, 17rem);
  min-height: 7rem;
  display: grid;
  align-content: start;
  gap: 0.65rem;
  padding: 1rem;
  border: 1px solid var(--k-color-border, rgba(22, 53, 42, 0.14));
  border-radius: var(--k-radius-md, 0.75rem);
  background: var(--k-color-surface, #fff);
  color: var(--k-color-text, #16352a);
}

.k-mechanism-chain__node.is-mechanism,
.k-mechanism-chain__node.is-consequence {
  border-color: var(--k-color-border-strong, rgba(47, 111, 87, 0.28));
  background: var(--k-color-brand-050, #eef5f1);
}

.k-mechanism-chain__node.is-omission {
  width: 9.5rem;
  place-content: center;
  text-align: center;
  border-style: dashed;
  color: var(--k-color-text-muted, #64756e);
  background: transparent;
}

.k-mechanism-chain__eyebrow {
  color: var(--k-color-text-muted, #64756e);
  font-size: var(--k-text-meta, 0.75rem);
  font-weight: 650;
  letter-spacing: 0.04em;
}

.k-mechanism-chain__node strong {
  font-size: var(--k-text-ui, 0.94rem);
  line-height: 1.55;
  text-wrap: pretty;
}

.k-mechanism-chain__arrow {
  align-self: center;
  color: var(--k-color-brand-600, #2f6f57);
  font-size: 1.45rem;
  line-height: 1;
}

.k-mechanism-chain__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  color: var(--k-color-text-muted, #64756e);
  font-size: var(--k-text-meta, 0.75rem);
}

.k-mechanism-chain__footer button {
  min-height: 2rem;
  padding: 0 0.75rem;
  border: 1px solid var(--k-color-border-strong, rgba(47, 111, 87, 0.28));
  border-radius: var(--k-radius-sm, 0.5rem);
  background: var(--k-color-surface, #fff);
  color: var(--k-color-brand-700, #245842);
  font: inherit;
  font-weight: 650;
  cursor: pointer;
}

.k-mechanism-chain__footer button:focus-visible {
  outline: 2px solid var(--k-color-brand-500, #3d8a61);
  outline-offset: 2px;
}

@media (max-width: 760px) {
  .k-mechanism-chain__viewport { overflow: visible; }
  .k-mechanism-chain__track {
    min-width: 0;
    display: grid;
    gap: 0.5rem;
  }
  .k-mechanism-chain__node { width: 100%; min-height: 0; }
  .k-mechanism-chain__arrow { justify-self: center; transform: rotate(90deg); }
  .k-mechanism-chain__footer { align-items: flex-start; flex-direction: column; }
}
</style>
