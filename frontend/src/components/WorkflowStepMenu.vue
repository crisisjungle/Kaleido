<template>
  <div class="workflow-menu" ref="menuRef">
    <button class="workflow-trigger" type="button" @click="open = !open">
      <span class="step-num">Step {{ currentStep }}/4</span>
      <span class="step-name">{{ currentName }}</span>
      <span class="chevron" :class="{ open }">⌄</span>
    </button>

    <div v-if="open" class="workflow-popover">
      <button
        v-for="item in visibleSteps"
        :key="item.step"
        class="workflow-item"
        :class="{ active: item.step === currentStep, disabled: !item.visited && item.step !== currentStep }"
        type="button"
        :disabled="!item.visited && item.step !== currentStep"
        @click="goToStep(item)"
      >
        <span class="item-index">{{ String(item.step).padStart(2, '0') }}</span>
        <span class="item-main">
          <strong>{{ item.name }}</strong>
          <small>{{ item.summary || statusLabel(item) }}</small>
        </span>
        <span class="item-status" :class="item.status || 'todo'">{{ item.step === currentStep ? '当前' : statusLabel(item) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getWorkflowSteps } from '../store/workflowNavigation'

const props = defineProps({
  currentStep: {
    type: Number,
    required: true
  },
  currentName: {
    type: String,
    required: true
  }
})

const router = useRouter()
const open = ref(false)
const menuRef = ref(null)
const steps = getWorkflowSteps()

const visibleSteps = computed(() => steps)

function statusLabel(item) {
  if (item.status === 'done') return '已完成'
  if (item.status === 'active') return '进行中'
  if (item.visited) return '已访问'
  return '未开始'
}

function goToStep(item) {
  if (!item.visited && item.step !== props.currentStep) return
  open.value = false
  if (item.step === props.currentStep) return
  if (item.route?.name) {
    router.push(item.route)
  }
}

function handleDocumentClick(event) {
  if (!menuRef.value?.contains(event.target)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})
</script>

<style scoped>
.workflow-menu {
  position: relative;
}

.workflow-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  font: inherit;
}

.workflow-trigger:hover,
.workflow-trigger:focus-visible {
  background: rgba(255, 255, 255, 0.72);
  border-color: rgba(16, 35, 29, 0.08);
  outline: none;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
  white-space: nowrap;
}

.step-name {
  font-weight: 700;
  color: #000;
  white-space: nowrap;
}

.chevron {
  color: #6b7280;
  transition: transform 0.18s ease;
}

.chevron.open {
  transform: rotate(180deg);
}

.workflow-popover {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: 320px;
  padding: 8px;
  border-radius: 14px;
  border: 1px solid rgba(16, 35, 29, 0.1);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 48px rgba(16, 35, 29, 0.16);
  z-index: 300;
}

.workflow-item {
  width: 100%;
  display: grid;
  grid-template-columns: 36px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.workflow-item:hover:not(:disabled),
.workflow-item.active {
  background: rgba(16, 35, 29, 0.06);
}

.workflow-item:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.item-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #eef2f0;
  color: #17372e;
  font-size: 12px;
  font-weight: 800;
}

.item-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.item-main strong,
.item-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-main small {
  color: #6b7280;
}

.item-status {
  font-size: 12px;
  color: #6b7280;
}

.item-status.done {
  color: #0f766e;
}

.item-status.active {
  color: #d97706;
}
</style>
