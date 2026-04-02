<template>
  <article class="agent-card" :class="[`family-${familyClass}`, { fallback: agent.isFallback }]">
    <div class="agent-card-head">
      <div class="agent-card-index mono">A{{ displayIndex }}</div>
      <div class="agent-card-title">
        <strong>{{ agent.displayName }}</strong>
        <span class="agent-card-handle">{{ agent.handle }}</span>
      </div>
      <div class="agent-card-badges">
        <span class="agent-badge">{{ agent.familyLabel }}</span>
        <span class="agent-badge muted">{{ agent.roleTypeLabel }}</span>
      </div>
    </div>

    <p class="agent-card-summary">
      {{ summaryText }}
    </p>

    <div class="agent-card-meta">
      <div class="meta-item">
        <span>主区域</span>
        <strong>{{ primaryRegionLabel }}</strong>
      </div>
      <div class="meta-item">
        <span>锚点</span>
        <strong>{{ agent.influencedRegionsCount }}</strong>
      </div>
      <div class="meta-item">
        <span>状态</span>
        <strong>{{ agent.stateBand }}</strong>
      </div>
      <div class="meta-item">
        <span>倾向</span>
        <strong>{{ agent.stanceLabel }}</strong>
      </div>
    </div>

    <div class="agent-card-section">
      <div class="agent-card-section-label">动机</div>
      <div class="chip-row">
        <span v-for="goal in goals" :key="goal" class="mini-chip">{{ goal }}</span>
        <span v-if="goals.length === 0" class="mini-chip ghost">暂无动机</span>
      </div>
    </div>

    <div class="agent-card-section">
      <div class="agent-card-section-label">敏感项</div>
      <div class="chip-row">
        <span v-for="item in sensitivities" :key="item" class="mini-chip soft">{{ item }}</span>
        <span v-if="sensitivities.length === 0" class="mini-chip ghost">暂无敏感项</span>
      </div>
    </div>

    <div class="agent-card-foot">
      <span>{{ agent.sourceLabel }}</span>
      <span>{{ agent.stateSignal }}</span>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  agent: {
    type: Object,
    required: true
  },
  index: {
    type: Number,
    default: 0
  }
})

const displayIndex = computed(() => props.index || 0)
const familyClass = computed(() => props.agent?.familyClass || 'other')
const summaryText = computed(() => props.agent?.summary || props.agent?.bio || props.agent?.persona || '暂无简介')
const primaryRegionLabel = computed(() => props.agent?.primaryRegionLabel || 'Unknown region')
const goals = computed(() => Array.isArray(props.agent?.goals) ? props.agent.goals.slice(0, 3) : [])
const sensitivities = computed(() => Array.isArray(props.agent?.sensitivities) ? props.agent.sensitivities.slice(0, 2) : [])
</script>

<style scoped>
.agent-card {
  --agent-accent: #2d5be3;
  border-radius: 20px;
  padding: 16px;
  border: 1px solid rgba(20, 33, 61, 0.08);
  border-top: 3px solid var(--agent-accent);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(245, 248, 255, 0.88));
  box-shadow: 0 10px 24px rgba(17, 31, 59, 0.05);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-card.fallback {
  border-style: dashed;
}

.agent-card.family-human {
  --agent-accent: #2f6de2;
}

.agent-card.family-organization {
  --agent-accent: #d46b2f;
}

.agent-card.family-ecology {
  --agent-accent: #1fb07a;
}

.agent-card.family-governance {
  --agent-accent: #7b54dd;
}

.agent-card.family-infrastructure {
  --agent-accent: #5468ff;
}

.agent-card.family-region {
  --agent-accent: #3357a8;
}

.agent-card.family-other {
  --agent-accent: #7382a3;
}

.agent-card-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: flex-start;
}

.agent-card-index {
  border-radius: 999px;
  padding: 4px 8px;
  background: rgba(47, 110, 255, 0.08);
  color: #2d5be3;
  font-size: 10px;
  font-weight: 800;
}

.agent-card-title strong {
  display: block;
  color: #16315a;
  font-size: 16px;
}

.agent-card-handle {
  display: block;
  margin-top: 4px;
  color: #7382a3;
  font-size: 12px;
}

.agent-card-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}

.agent-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(47, 110, 255, 0.1);
  color: #3357a8;
}

.agent-badge.muted {
  background: rgba(24, 48, 88, 0.06);
  color: #5d687f;
}

.agent-card-summary {
  margin: 0;
  color: #51607d;
  line-height: 1.55;
  font-size: 13px;
}

.agent-card-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.meta-item {
  padding: 10px 12px;
  border-radius: 16px;
  background: rgba(245, 248, 255, 0.9);
  border: 1px solid rgba(20, 33, 61, 0.06);
}

.meta-item span,
.agent-card-section-label {
  display: block;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #7382a3;
}

.meta-item strong {
  display: block;
  margin-top: 6px;
  color: #16315a;
  font-size: 13px;
}

.agent-card-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mini-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 5px 8px;
  background: rgba(47, 110, 255, 0.1);
  color: #3357a8;
  font-size: 11px;
  font-weight: 700;
}

.mini-chip.soft {
  background: rgba(28, 196, 135, 0.1);
  color: #13805c;
}

.mini-chip.ghost {
  background: rgba(24, 48, 88, 0.06);
  color: #7b86a3;
}

.agent-card-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #7b86a3;
  font-size: 11px;
}

@media (max-width: 900px) {
  .agent-card-head {
    grid-template-columns: 1fr;
  }

  .agent-card-badges {
    justify-content: flex-start;
  }

  .agent-card-meta {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
