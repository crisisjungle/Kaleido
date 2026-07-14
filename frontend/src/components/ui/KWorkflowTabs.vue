<template>
  <div
    class="k-workflow-tabs"
    :class="[
      `k-workflow-tabs--${variant}`,
      { 'k-workflow-tabs--equal': equalWidth, 'k-workflow-tabs--collapsible': collapseOnNarrow }
    ]"
    :style="{ '--k-tab-count': Math.max(items.length, 1) }"
  >
    <div class="k-workflow-tabs__list" role="tablist" :aria-label="ariaLabel">
      <button
        v-for="(item, index) in items"
        :id="tabId(index)"
        :key="itemKey(item, index)"
        class="k-workflow-tabs__tab"
        :class="{ 'is-active': isActive(item, index) }"
        type="button"
        role="tab"
        :aria-selected="isActive(item, index)"
        :aria-controls="item.panelId || undefined"
        :tabindex="isActive(item, index) ? 0 : -1"
        :disabled="disabled || item.disabled"
        @click="selectItem(item, index)"
        @keydown="handleKeydown($event, index)"
      >
        <span class="k-workflow-tabs__label">{{ item.label }}</span>
        <span v-if="item.meta" class="k-workflow-tabs__meta">{{ item.meta }}</span>
      </button>
    </div>

    <label class="k-workflow-tabs__select-wrap">
      <span class="k-visually-hidden">{{ ariaLabel }}</span>
      <select
        class="k-workflow-tabs__select"
        :value="selectValue"
        :disabled="disabled"
        @change="selectFromNative"
      >
        <option
          v-for="(item, index) in items"
          :key="itemKey(item, index)"
          :value="String(itemValue(item, index))"
          :disabled="item.disabled"
        >
          {{ item.meta ? `${item.label} · ${item.meta}` : item.label }}
        </option>
      </select>
    </label>
  </div>
</template>

<script setup>
import { computed, useId } from 'vue'

const props = defineProps({
  items: {
    type: Array,
    default: () => []
  },
  modelValue: {
    type: [String, Number, Boolean],
    default: undefined
  },
  variant: {
    type: String,
    default: 'rich',
    validator: value => ['rich', 'compact'].includes(value)
  },
  ariaLabel: {
    type: String,
    default: '工作流视图'
  },
  equal: {
    type: Boolean,
    default: undefined
  },
  collapseOnNarrow: {
    type: Boolean,
    default: true
  },
  disabled: Boolean
})

const emit = defineEmits(['update:modelValue', 'change'])
const instanceId = useId().replace(/[^a-zA-Z0-9_-]/g, '')

const itemValue = (item, index) => item.value ?? item.key ?? item.id ?? index
const itemKey = (item, index) => item.key ?? item.id ?? item.value ?? index
const firstEnabled = computed(() => props.items.findIndex(item => !item.disabled))
const activeIndex = computed(() => {
  const matched = props.items.findIndex((item, index) => Object.is(itemValue(item, index), props.modelValue))
  return matched >= 0 ? matched : firstEnabled.value
})
const equalWidth = computed(() => props.equal ?? props.variant === 'rich')
const selectValue = computed(() => {
  if (activeIndex.value < 0) return ''
  return String(itemValue(props.items[activeIndex.value], activeIndex.value))
})

const tabId = index => `k-workflow-tab-${instanceId}-${index}`
const isActive = (_item, index) => index === activeIndex.value

const selectItem = (item, index) => {
  if (props.disabled || item.disabled) return
  const value = itemValue(item, index)
  emit('update:modelValue', value)
  emit('change', value, item)
}

const selectFromNative = event => {
  const index = props.items.findIndex((item, itemIndex) => String(itemValue(item, itemIndex)) === event.target.value)
  if (index >= 0) selectItem(props.items[index], index)
}

const handleKeydown = (event, currentIndex) => {
  const enabledIndexes = props.items
    .map((item, index) => ({ item, index }))
    .filter(entry => !entry.item.disabled)
    .map(entry => entry.index)

  if (!enabledIndexes.length) return
  const currentPosition = Math.max(enabledIndexes.indexOf(currentIndex), 0)
  let targetIndex

  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    targetIndex = enabledIndexes[(currentPosition + 1) % enabledIndexes.length]
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    targetIndex = enabledIndexes[(currentPosition - 1 + enabledIndexes.length) % enabledIndexes.length]
  } else if (event.key === 'Home') {
    targetIndex = enabledIndexes[0]
  } else if (event.key === 'End') {
    targetIndex = enabledIndexes.at(-1)
  } else {
    return
  }

  event.preventDefault()
  selectItem(props.items[targetIndex], targetIndex)
  document.getElementById(tabId(targetIndex))?.focus()
}
</script>

<style scoped>
.k-workflow-tabs {
  width: 100%;
  min-width: 0;
  container-type: inline-size;
}

.k-workflow-tabs__list {
  display: flex;
  align-items: stretch;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.k-workflow-tabs__list::-webkit-scrollbar {
  display: none;
}

.k-workflow-tabs--equal .k-workflow-tabs__list {
  display: grid;
  grid-template-columns: repeat(var(--k-tab-count), minmax(0, 1fr));
}

.k-workflow-tabs--equal .k-workflow-tabs__tab {
  width: 100%;
  min-width: 0;
}

.k-workflow-tabs__tab {
  position: relative;
  min-width: max-content;
  color: var(--k-color-text-muted);
  background: transparent;
  border: 0;
  font-family: var(--k-font-sans);
  text-align: left;
  cursor: pointer;
  transition:
    color var(--k-transition-fast),
    background-color var(--k-transition-fast),
    box-shadow var(--k-transition-fast);
}

.k-workflow-tabs__tab:disabled {
  color: var(--k-color-text-disabled);
  cursor: not-allowed;
}

.k-workflow-tabs__tab:focus-visible {
  z-index: 1;
  outline: none;
  box-shadow: inset 0 0 0 2px var(--k-color-brand-500);
}

.k-workflow-tabs--rich .k-workflow-tabs__list {
  gap: var(--k-space-1);
  padding-bottom: var(--k-space-3);
  border-bottom: 1px solid var(--k-color-border);
}

.k-workflow-tabs--rich .k-workflow-tabs__tab {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.25rem;
  min-height: 4rem;
  padding: 0.75rem 1rem;
  border-radius: var(--k-radius-md);
}

.k-workflow-tabs--rich .k-workflow-tabs__tab:hover:not(:disabled):not(.is-active) {
  color: var(--k-color-brand-700);
  background: var(--k-color-brand-050);
}

.k-workflow-tabs--rich .k-workflow-tabs__tab.is-active {
  color: #ffffff;
  background: var(--k-color-brand-600);
}

.k-workflow-tabs--rich .k-workflow-tabs__label {
  font-size: var(--k-text-ui);
  font-weight: 650;
  line-height: 1.25;
}

.k-workflow-tabs--rich .k-workflow-tabs__meta {
  overflow: hidden;
  font-size: var(--k-text-meta);
  font-weight: 450;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.78;
}

.k-workflow-tabs--compact .k-workflow-tabs__list {
  gap: 1.75rem;
  border-bottom: 1px solid var(--k-color-border);
}

.k-workflow-tabs--compact .k-workflow-tabs__tab {
  display: inline-flex;
  align-items: center;
  gap: var(--k-space-2);
  min-height: 3rem;
  padding: 0 var(--k-space-1);
  font-size: var(--k-text-ui);
  font-weight: 600;
}

.k-workflow-tabs--compact .k-workflow-tabs__tab::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: var(--k-color-brand-600);
  content: '';
  opacity: 0;
  transform: scaleX(0.3);
  transform-origin: center;
  transition:
    opacity var(--k-transition-fast),
    transform var(--k-transition-fast);
}

.k-workflow-tabs--compact .k-workflow-tabs__tab:hover:not(:disabled),
.k-workflow-tabs--compact .k-workflow-tabs__tab.is-active {
  color: var(--k-color-brand-700);
}

.k-workflow-tabs--compact .k-workflow-tabs__tab.is-active::after {
  opacity: 1;
  transform: scaleX(1);
}

.k-workflow-tabs--compact .k-workflow-tabs__meta {
  color: var(--k-color-text-muted);
  font-size: var(--k-text-meta);
  font-weight: 500;
}

.k-workflow-tabs__select-wrap {
  display: none;
}

.k-workflow-tabs__select {
  width: 100%;
  height: var(--k-control-height-md);
  padding: 0 2.25rem 0 0.75rem;
  color: var(--k-color-text);
  background: var(--k-color-surface);
  border: 1px solid var(--k-color-border-strong);
  border-radius: var(--k-radius-sm);
  font: 600 var(--k-text-ui)/1 var(--k-font-sans);
}

.k-workflow-tabs__select:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--k-color-focus);
}

@container (max-width: 34rem) {
  .k-workflow-tabs--collapsible .k-workflow-tabs__list {
    display: none;
  }

  .k-workflow-tabs--collapsible .k-workflow-tabs__select-wrap {
    display: block;
  }
}
</style>
