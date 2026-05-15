<template>
  <component
    :is="componentTag"
    v-bind="componentProps"
    class="kaleido-nav-brand"
    :class="`is-${tone}`"
    @click="$emit('click')"
  >
    <span class="kaleido-nav-brand__title">KALEIDO</span>
  </component>
</template>

<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  to: {
    type: [String, Object],
    default: null
  },
  tone: {
    type: String,
    default: 'dark'
  }
})

defineEmits(['click'])

const componentTag = computed(() => (props.to ? RouterLink : 'button'))
const componentProps = computed(() => (props.to ? { to: props.to } : { type: 'button' }))
</script>

<style scoped>
.kaleido-nav-brand {
  display: inline-flex;
  align-items: center;
  min-height: 2.5rem;
  padding: 0;
  border: 0;
  background: transparent;
  color: #10231d;
  text-decoration: none;
  cursor: pointer;
}

.kaleido-nav-brand__title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.125rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  line-height: 1;
  text-transform: uppercase;
}

.kaleido-nav-brand.is-light {
  color: #f8fafc;
}
</style>
