<template>
  <section class="control-sidebar" :class="{ 'is-collapsed': collapsed }">
    <button class="collapse-toggle" @click="$emit('update:collapsed', !collapsed)">
      <span class="icon">{{ collapsed ? '❯' : '❮' }}</span>
    </button>

    <div class="sidebar-content">
      <div class="panel-head">
        <h2>太空预测控制</h2>
        <p>预设初始变量并启动级联推演</p>
      </div>

      <div class="control-groups">
        <div class="group">
          <div class="group-header">
            <label>推演起始年份</label>
            <span class="current-value">{{ startYearLabel }}</span>
          </div>
          <div class="year-selector">
            <input
              type="range"
              :min="yearMin"
              :max="yearMax"
              step="1"
              :value="modelValue.startYear"
              :disabled="disabled"
              @input="update('startYear', Number($event.target.value))"
            />
            <div class="range-labels">
              <span>{{ yearMin }}</span>
              <span>{{ yearMax }}</span>
            </div>
          </div>
        </div>

        <div class="group">
          <label>预设碰撞等级</label>
          <div class="type-grid">
            <button
              v-for="type in collisionTypes"
              :key="type.value"
              type="button"
              :class="{ active: type.value === modelValue.collisionType }"
              :disabled="disabled"
              @click="update('collisionType', type.value)"
            >
              {{ type.label }}
            </button>
          </div>
          <div class="type-desc">
            {{ selectedCollision?.description || '选择一个碰撞模板开始' }}
          </div>
        </div>

        <div class="group">
          <label>目标轨道高度</label>
          <div class="type-grid band-grid">
            <button
              v-for="band in shellBands"
              :key="band"
              type="button"
              :class="{ active: band === modelValue.shellBand }"
              :disabled="disabled"
              @click="update('shellBand', band)"
            >
              {{ band }}
            </button>
          </div>
        </div>
      </div>

      <div class="footer-actions">
        <button type="button" class="btn-start" :disabled="disabled" @click="$emit('start')">
          {{ disabled ? '推演进行中' : '开始系统模拟' }}
        </button>
        <button type="button" class="btn-reset" @click="$emit('reset')">重置参数</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true
  },
  collapsed: {
    type: Boolean,
    default: false
  },
  years: {
    type: Array,
    default: () => []
  },
  collisionTypes: {
    type: Array,
    default: () => []
  },
  shellBands: {
    type: Array,
    default: () => []
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'update:collapsed', 'start', 'reset'])

const selectedCollision = computed(() => props.collisionTypes.find((item) => item.value === props.modelValue.collisionType))
const yearMin = computed(() => Math.min(...props.years, 2026))
const yearMax = computed(() => Math.max(...props.years, 2040))
const startYearLabel = computed(() => {
  return `${Math.floor(Number(props.modelValue.startYear || yearMin.value))}`
})

const update = (key, value) => {
  emit('update:modelValue', {
    ...props.modelValue,
    [key]: value
  })
}
</script>

<style scoped>
.control-sidebar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 320px;
  height: 100%;
  background: rgba(8, 10, 15, 0.85);
  backdrop-filter: blur(20px);
  border-right: 1px solid rgba(255, 255, 255, 0.1);
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  pointer-events: auto;
}

.control-sidebar.is-collapsed {
  transform: translateX(-100%);
}

.collapse-toggle {
  position: absolute;
  right: -32px;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 60px;
  background: rgba(8, 10, 15, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-left: none;
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  display: grid;
  place-items: center;
  color: #fff;
  transition: background 0.2s;
}

.collapse-toggle:hover {
  background: rgba(20, 25, 35, 0.95);
}

.sidebar-content {
  padding: 40px 24px;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-head {
  margin-bottom: 48px;
}

.panel-head h2 {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.05em;
  margin: 0 0 8px;
  color: #fff;
}

.panel-head p {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.4);
  margin: 0;
}

.control-groups {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 36px;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}

.group-header label {
  margin-bottom: 0;
}

.current-value {
  font-size: 20px;
  font-weight: 700;
  color: #38bdf8;
  font-variant-numeric: tabular-nums;
}

input[type='range'] {
  -webkit-appearance: none;
  width: 100%;
  height: 20px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  outline: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 0 4px;
}

input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #38bdf8;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.5);
  cursor: grab;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

input[type='range']::-webkit-slider-thumb:hover {
  background: #7dd3fc;
  transform: scale(1.05);
}

input[type='range']::-webkit-slider-thumb:active {
  cursor: grabbing;
  background: #0ea5e9;
  transform: scale(0.95);
}

.range-labels {
  display: flex;
  justify-content: space-between;
  padding: 0 8px;
  margin-top: 4px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

.type-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.03);
  padding: 6px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.band-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.type-grid button {
  min-width: 0;
  height: 38px;
  background: transparent;
  border: 0;
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.type-grid button:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
}

.type-grid button.active {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
  box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.4);
}

.type-desc {
  margin-top: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.3);
  min-height: 40px;
}

.footer-actions {
  display: grid;
  gap: 12px;
  margin-top: auto;
}

.btn-start {
  height: 48px;
  background: #38bdf8;
  color: #000;
  border: none;
  border-radius: 4px;
  font-weight: 800;
  font-size: 15px;
  cursor: pointer;
  transition: transform 0.1s;
}

.btn-start:hover:not(:disabled) {
  background: #7dd3fc;
  transform: translateY(-1px);
}

.btn-start:disabled {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.3);
  cursor: not-allowed;
}

.btn-reset {
  height: 40px;
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.btn-reset:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
}
</style>
