<template>
  <div class="legend-container">
    <!-- Mini floating button -->
    <button class="legend-trigger" @click="isOpen = true" title="查看图例">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M4 6h16M4 12h16M4 18h7" />
      </svg>
    </button>

    <!-- Legend Modal -->
    <Transition name="fade-slide">
      <div v-if="isOpen" class="legend-modal-overlay" @click.self="isOpen = false">
        <div class="legend-modal">
          <header class="modal-header">
            <h3>仿真模型图例</h3>
            <button class="btn-close" @click="isOpen = false">&times;</button>
          </header>
          
          <div class="modal-body">
            <div class="legend-section">
              <h4 class="section-title">卫星模型类别 (Satellite Models)</h4>
              <div v-for="item in satelliteModelItems" :key="item.label" class="legend-row model-row">
                <span class="model-icon" :class="item.icon" aria-hidden="true">
                  <span class="model-body"></span>
                  <span v-if="item.icon === 'winged'" class="panel left"></span>
                  <span v-if="item.icon === 'winged'" class="panel right"></span>
                  <span v-if="item.icon === 'long-panel'" class="long-panel-bar"></span>
                  <span v-if="item.icon === 'cubesat'" class="cube-panel"></span>
                  <span v-if="item.icon === 'dish'" class="dish-cone"></span>
                  <span v-if="item.icon === 'compact'" class="compact-panel"></span>
                  <span v-if="item.icon === 'wreckage'" class="shard shard-a"></span>
                  <span v-if="item.icon === 'wreckage'" class="shard shard-b"></span>
                </span>
                <div class="text">
                  <span class="label">{{ item.label }}</span>
                  <p class="desc">{{ item.desc }}</p>
                </div>
              </div>
            </div>

            <div class="legend-section">
              <h4 class="section-title">碎片与云层 (Debris & Clouds)</h4>
              <div v-for="item in particleItems" :key="item.label" class="legend-row">
                <span class="dot" :class="item.type" :style="{ background: item.color }"></span>
                <div class="text">
                  <span class="label">{{ item.label }}</span>
                  <p class="desc">{{ item.desc }}</p>
                </div>
              </div>
            </div>
          </div>
          
          <footer class="modal-footer">
            <p>卫星形态用于区分任务类别与状态，碎片云用于表现凯斯勒级联后的高密度轨道壳层。</p>
          </footer>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const isOpen = ref(false)

const satelliteModelItems = [
  {
    label: '大型任务卫星',
    icon: 'winged',
    desc: '展开式太阳翼平台。代表遥感、测绘、科学载荷等仍可控的活跃卫星。'
  },
  {
    label: '长面板通信卫星',
    icon: 'long-panel',
    desc: '长太阳翼或桁架结构。代表通信、中继、宽幅供电平台。'
  },
  {
    label: '立方星 / 小卫星',
    icon: 'cubesat',
    desc: '紧凑盒式平台。代表 CubeSat、小型商业星座和低成本实验卫星。'
  },
  {
    label: '天线载荷卫星',
    icon: 'dish',
    desc: '带碟形天线或外伸载荷。代表观测、通信、导航增强类卫星。'
  },
  {
    label: '紧凑平台卫星',
    icon: 'compact',
    desc: '短翼紧凑母线。代表小型但仍处于工作状态的在轨平台。'
  },
  {
    label: '失效卫星 / 大型残骸',
    icon: 'wreckage',
    desc: '破碎母线、太阳翼残片和结构碎片。代表失控卫星、末级火箭与碰撞后的大型残骸。'
  }
]

const particleItems = [
  { 
    label: '大型碎片', 
    color: '#fb923c', 
    type: 'glow',
    desc: '高亮度橙点。代表 >10cm 的独立可监测碎片。' 
  },
  { 
    label: '轨道碎片云', 
    color: '#bae6fd', 
    type: 'cloud',
    desc: '淡蓝色环绕雾团。代表碎片极高密度分布的危险轨道层。' 
  },
  { 
    label: '微小颗粒', 
    color: '#94a3b8', 
    type: 'fine',
    desc: '灰色离散粒子。代表数以亿计无法监控的微米级碎散物。' 
  }
]
</script>

<style scoped>
.legend-container {
  pointer-events: auto;
}

.legend-trigger {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: rgba(8, 10, 15, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #fff;
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: all 0.3s;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.legend-trigger:hover {
  background: rgba(20, 25, 30, 0.9);
  border-color: rgba(56, 189, 248, 0.5);
}

.legend-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: grid;
  place-items: center;
  z-index: 2000;
  padding: 24px;
}

.legend-modal {
  width: 100%;
  max-width: 520px;
  max-height: min(760px, calc(100vh - 48px));
  background: rgba(15, 20, 30, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.modal-header {
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
}

.btn-close {
  background: transparent;
  border: none;
  font-size: 24px;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
}

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
  max-height: calc(100vh - 188px);
}

.legend-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  margin: 0;
  font-size: 11px;
  text-transform: uppercase;
  color: #38bdf8;
  letter-spacing: 0.1em;
  font-weight: 700;
}

.legend-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.model-row {
  min-height: 44px;
}

.model-icon {
  position: relative;
  width: 52px;
  height: 34px;
  flex-shrink: 0;
  margin-top: 2px;
  display: block;
  color: #38bdf8;
}

.model-icon::after {
  content: '';
  position: absolute;
  inset: 4px 2px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(56, 189, 248, 0.28), transparent 64%);
  filter: blur(4px);
}

.model-icon span {
  position: absolute;
  display: block;
  z-index: 1;
}

.model-body {
  left: 21px;
  top: 11px;
  width: 12px;
  height: 12px;
  background: #dbeafe;
  border: 1px solid rgba(255, 255, 255, 0.65);
  border-radius: 2px;
  box-shadow: 0 0 8px rgba(186, 230, 253, 0.45);
}

.panel {
  top: 13px;
  width: 18px;
  height: 8px;
  background: #38bdf8;
  border-radius: 1px;
}

.panel.left {
  left: 2px;
  transform: rotate(-18deg);
}

.panel.right {
  right: 2px;
  transform: rotate(18deg);
}

.long-panel .model-body {
  left: 23px;
  top: 10px;
  width: 10px;
  height: 14px;
  background: #bfdbfe;
}

.long-panel-bar {
  left: 3px;
  top: 16px;
  width: 46px;
  height: 5px;
  background: linear-gradient(90deg, #0ea5e9, #7dd3fc);
  border-radius: 1px;
}

.cubesat .model-body {
  left: 19px;
  top: 8px;
  width: 16px;
  height: 16px;
  background: #a7f3d0;
  transform: rotate(8deg);
}

.cube-panel {
  right: 6px;
  top: 13px;
  width: 13px;
  height: 7px;
  background: #67e8f9;
  border-radius: 1px;
  transform: rotate(-10deg);
}

.dish .model-body {
  left: 14px;
  top: 11px;
  width: 13px;
  height: 12px;
  background: #bae6fd;
}

.dish-cone {
  left: 29px;
  top: 9px;
  width: 16px;
  height: 16px;
  border: 2px solid #f8fafc;
  border-left: 0;
  border-bottom-color: transparent;
  border-radius: 50%;
  transform: rotate(-12deg);
}

.compact .model-body {
  left: 18px;
  top: 10px;
  width: 17px;
  height: 12px;
  background: #fef08a;
}

.compact-panel {
  left: 10px;
  bottom: 6px;
  width: 34px;
  height: 5px;
  background: #22d3ee;
  border-radius: 1px;
}

.wreckage {
  color: #facc15;
}

.wreckage .model-body {
  left: 18px;
  top: 11px;
  width: 16px;
  height: 11px;
  background: #facc15;
  transform: rotate(-18deg) skewX(-14deg);
  border-color: rgba(254, 240, 138, 0.6);
}

.shard {
  background: #e2e8f0;
  border-radius: 1px;
}

.shard-a {
  left: 5px;
  top: 13px;
  width: 14px;
  height: 4px;
  transform: rotate(26deg);
}

.shard-b {
  right: 7px;
  bottom: 10px;
  width: 11px;
  height: 5px;
  transform: rotate(-32deg);
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}

.dot.glow {
  box-shadow: 0 0 10px currentColor;
}

.dot.cloud {
  width: 16px;
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(90deg, transparent, currentColor, transparent) !important;
  opacity: 0.6;
}

.dot.fine {
  width: 4px;
  height: 4px;
  margin-left: 3px;
}

.text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.label {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
}

.desc {
  margin: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
  line-height: 1.5;
}

.modal-footer {
  padding: 16px 24px;
  background: rgba(255, 255, 255, 0.02);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.modal-footer p {
  margin: 0;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  text-align: center;
}

/* Transitions */
.fade-slide-enter-active, .fade-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-slide-enter-from, .fade-slide-leave-to {
  opacity: 0;
  transform: scale(0.9) translateY(20px);
}
</style>
