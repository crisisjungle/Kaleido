<template>
  <div class="demo-restore-page">
    <KaleidoNavBrand to="/" />
    <main class="restore-panel">
      <p class="eyebrow">武汉疫情演示</p>
      <h1>{{ title }}</h1>
      <p>{{ message }}</p>
      <button v-if="failed" class="retry-btn" type="button" @click="restoreDemo">重试</button>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KaleidoNavBrand from '../components/KaleidoNavBrand.vue'
import { restoreGoldenCase } from '../api/goldenCases'
import { hydrateWorkflowFromGoldenCase, resetWorkflowNavigation } from '../store/workflowNavigation'
import { safeDisplayError } from '../utils/displayText'
import { resolveWuhanDemoStep, resolveWuhanDemoVersion } from '../utils/wuhanDemoRouting'

const route = useRoute()
const router = useRouter()
const failed = ref(false)
const message = ref('正在恢复武汉案例，不会调用大模型或启动推演进程。')

const title = computed(() => (failed.value ? '演示恢复失败' : '正在进入武汉案例'))
const requestedStep = computed(() => {
  const step = Number.parseInt(String(route.query.step || ''), 10)
  return [1, 2, 3, 4].includes(step) ? step : null
})
// The product entry now resolves to the complete V2 four-step showcase.
// V1 remains available only through the explicit rollback query.
const requestedVersion = computed(() => resolveWuhanDemoVersion(route.query.version))
const shouldOpenPlayback = computed(() => {
  const playback = String(route.query.playback || route.query.run || '').toLowerCase()
  return requestedStep.value === 3 || ['1', 'true', 'yes', 'on'].includes(playback)
})

async function restoreDemo() {
  failed.value = false
  message.value = requestedVersion.value === 'v2'
    ? '正在恢复武汉 Ultra 目标态案例。'
    : '正在恢复武汉 V1 冻结回放。'

  try {
    const fresh = String(route.query.fresh || '') === '1'
    const caseId = requestedVersion.value === 'v2' ? 'wuhan_covid_v2' : 'wuhan_covid_v1'
    const res = await restoreGoldenCase(caseId, { fresh, reuse: !fresh })
    const stepRoutes = res.data?.step_routes || {}
    const resolvedStep = resolveWuhanDemoStep({
      version: requestedVersion.value,
      requestedStep: requestedStep.value,
      playback: shouldOpenPlayback.value,
      defaultStep: res.data?.default_step
    })
    resetWorkflowNavigation()
    if (res.data?.demo_mode === 'curated_showcase') {
      hydrateWorkflowFromGoldenCase({ stepRoutes, currentStep: resolvedStep })
    }
    const curatedRoute = {
      1: stepRoutes.foundation,
      2: stepRoutes.scenario,
      3: stepRoutes.runtime,
      4: stepRoutes.analysis
    }[resolvedStep]
    if (requestedVersion.value === 'v2') {
      const restoredCaseId = String(res.data?.case_id || '')
      const routeCaseId = String(curatedRoute?.query?.golden_case_id || '')
      if (
        res.data?.demo_mode !== 'curated_showcase'
        || restoredCaseId !== caseId
        || routeCaseId !== caseId
        || !curatedRoute?.name
      ) {
        throw new Error('武汉 V2 四步案例合同不完整')
      }
    }
    const demoRoute = requestedVersion.value === 'v2'
      ? curatedRoute
      : (curatedRoute || (shouldOpenPlayback.value
          ? (res.data?.playback_route || res.data?.route)
          : res.data?.route))
    if (!demoRoute?.name) {
      throw new Error('演示路由缺失')
    }

    await router.replace({
      name: demoRoute.name,
      params: demoRoute.params || {},
      query: {
        ...(demoRoute.query || {}),
        replay: '1',
        report_id: res.data?.report_id || demoRoute.query?.report_id || '',
        demo_mode: res.data?.demo_mode || 'frozen_replay',
        version: requestedVersion.value,
        step: String(resolvedStep)
      }
    })
  } catch (err) {
    failed.value = true
    message.value = safeDisplayError(err, '演示暂时无法进入，请稍后重试。')
  }
}

onMounted(restoreDemo)
</script>

<style scoped>
.demo-restore-page {
  min-height: 100vh;
  padding: 24px;
  background: #F7F4EA;
  color: #173126;
}

.restore-panel {
  width: min(520px, calc(100vw - 48px));
  margin: 24vh auto 0;
}

.eyebrow {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  color: rgba(23, 49, 38, 0.58);
}

h1 {
  margin: 0;
  font-size: 36px;
  line-height: 1.1;
}

p {
  margin: 16px 0 0;
  line-height: 1.7;
  color: rgba(23, 49, 38, 0.72);
}

.retry-btn {
  margin-top: 24px;
  min-height: 42px;
  padding: 0 18px;
  border: 1px solid rgba(23, 49, 38, 0.18);
  border-radius: 8px;
  background: #173126;
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
</style>
