import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import {
  MECHANISM_CHAIN_LAYOUT,
  STEP2_WORKSPACE_TABS,
  STEP3_WORKSPACE_TABS,
  STEP4_ANALYSIS_TABS,
  WORKFLOW_STEPS,
} from '../src/config/workflowArchitecture.js'
import {
  getWorkflowSteps,
  hydrateWorkflowFromGoldenCase,
  resetWorkflowNavigation,
} from '../src/store/workflowNavigation.js'
import {
  resolveWuhanDemoStep,
  resolveWuhanDemoVersion,
} from '../src/utils/wuhanDemoRouting.js'

assert.deepEqual(WORKFLOW_STEPS.map(item => item.label), ['背景定义', '场景生成', '推演运行', '分析与报告'])
assert.deepEqual(STEP2_WORKSPACE_TABS.map(item => item.label), ['演化计划', '机制模型', '空间结构', '主体系统', '风险假设'])
assert.deepEqual(STEP3_WORKSPACE_TABS.map(item => item.label), ['本轮演化', '空间状态', '传播机制', '主体响应', '风险对象'])
assert.deepEqual(STEP4_ANALYSIS_TABS.map(item => item.label), ['结论与建议', '关键转折', '风险结果', '政策观察', '证据与边界'])
assert.equal(STEP4_ANALYSIS_TABS.some(item => item.id === 'report'), false)
assert.equal(MECHANISM_CHAIN_LAYOUT.completeMax, 6)
assert.equal(MECHANISM_CHAIN_LAYOUT.overviewMax, 10)
assert.equal(resolveWuhanDemoVersion(undefined), 'v2')
assert.equal(resolveWuhanDemoVersion('v1'), 'v1')
assert.equal(resolveWuhanDemoStep({ version: undefined, defaultStep: 1 }), 1)
assert.equal(resolveWuhanDemoStep({ version: 'v2', requestedStep: 4, defaultStep: 1 }), 4)
assert.equal(resolveWuhanDemoStep({ version: 'v2', playback: true, defaultStep: 1 }), 3)
assert.equal(resolveWuhanDemoStep({ version: 'v1', requestedStep: 4, defaultStep: 1 }), 2)

resetWorkflowNavigation()
hydrateWorkflowFromGoldenCase({
  currentStep: 2,
  stepRoutes: {
    foundation: {
      name: 'SceneComposer',
      query: {
        demo_mode: 'curated_showcase',
        golden_case_id: 'wuhan_covid_v2',
        simulation_id: 'sim_wuhan_v2',
        step: '1',
      },
    },
    scenario: {
      name: 'Simulation',
      params: { simulationId: 'sim_wuhan_v2' },
      query: { step: '2' },
    },
  },
})
const hydratedFoundationRoute = getWorkflowSteps().find(item => item.step === 1)?.route
assert.equal(hydratedFoundationRoute?.name, 'SceneComposer')
assert.deepEqual(hydratedFoundationRoute?.query, {
  demo_mode: 'curated_showcase',
  golden_case_id: 'wuhan_covid_v2',
  simulation_id: 'sim_wuhan_v2',
  step: '1',
})
resetWorkflowNavigation()
assert.equal(getWorkflowSteps().find(item => item.step === 1)?.route, null)

const [step2Source, step3Source, analysisSource, composerSource, mainSource, simulationSource, simulationRunSource, reportSource, wuhanDemoSource] = await Promise.all([
  readFile(new URL('../src/components/KaleidoStep2.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/components/KaleidoStep3.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/views/AnalysisView.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/views/SceneComposerView.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/views/MainView.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/views/SimulationView.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/views/SimulationRunView.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/components/Step4Report.vue', import.meta.url), 'utf8'),
  readFile(new URL('../src/views/WuhanDemoView.vue', import.meta.url), 'utf8'),
])

assert.match(step2Source, /初始关系骨架/)
assert.match(step2Source, /运行准备检查/)
assert.match(step2Source, /readinessBlockingCount/)
assert.match(step2Source, /showReadinessDetails = ref\(false\)/)
assert.match(step2Source, /aria-controls="step2-readiness-details"/)
assert.match(step2Source, /v-show="showReadinessDetails"/)
assert.match(step2Source, /class="readiness-disclosure"/)
assert.match(step2Source, /handleReadinessCheck/)
assert.match(step2Source, /readinessBlockingCount > 0 \? 'step2-readiness-summary'/)
assert.doesNotMatch(step2Source, /class="readiness-panel-head"/)
assert.doesNotMatch(step2Source, /value:\s*'relations'/)
assert.match(step3Source, /关系演化与角色涌现/)
assert.doesNotMatch(step3Source, /label:\s*'关系与风险'/)
assert.match(analysisSource, /report-delivery-overlay/)
assert.match(analysisSource, /causality_boundary/)
assert.match(analysisSource, /riskOutcomesTab\.risk_outcomes/)
assert.match(analysisSource, /risk-outcomes/)
assert.match(analysisSource, /analysis-bundle/)
assert.match(analysisSource, /证据索引与解释边界/)
assert.match(analysisSource, /可追溯证据索引/)
assert.match(analysisSource, /policyEventsForDisplay/)
assert.match(analysisSource, /dynamicRelationMetric/)
assert.match(analysisSource, /impact_scope\?\.dynamic_relation_count/)
assert.match(analysisSource, /await ensureTabLoaded\('analysis-bundle'\)\s+await ensureActiveViewLoaded\(nextTab\)/)
assert.doesNotMatch(composerSource, />推演变量</)
assert.match(composerSource, /KaleidoWorkflowShell/)
assert.doesNotMatch(composerSource, /<header class="topbar">/)
assert.match(mainSource, /handoffToCanonicalStep2/)
assert.match(mainSource, /name: 'Simulation'/)
assert.doesNotMatch(simulationSource, /router\.push\(\{ name: 'Process'/)
assert.match(simulationSource, /query: \{ \.\.\.route\.query, step: '1', restore: '1' \}/)
assert.match(simulationRunSource, /const query = \{ \.\.\.route\.query, step: '2' \}/)
assert.match(wuhanDemoSource, /wuhan_covid_v2/)
assert.match(wuhanDemoSource, /default_step/)
assert.match(wuhanDemoSource, /resolveWuhanDemoVersion/)
assert.match(wuhanDemoSource, /resetWorkflowNavigation/)
assert.match(wuhanDemoSource, /武汉 V2 四步案例合同不完整/)
assert.match(composerSource, /getGoldenCaseArtifact/)
assert.match(composerSource, /route\.query\.simulation_id/)
assert.match(composerSource, /已锁定背景输入/)
assert.match(composerSource, /curatedResearchQuestions/)
assert.match(composerSource, /curatedStateDimensions/)
assert.match(composerSource, /curatedFoundationError/)
assert.match(composerSource, /assertCuratedFoundationContract/)
assert.match(composerSource, /report-content-scroll/)
assert.match(composerSource, /武汉案例副本 · 可编辑/)
assert.match(step3Source, /primaryHeatScoreKey/)
assert.match(step3Source, /baselineSnapshot/)
for (const label of ['暴露压力', '发现可见度', '检测时效', '医疗负荷', '流动强度', '物资充足度', '社区支持度', '公共信任度']) {
  assert.match(step3Source, new RegExp(label))
}
assert.doesNotMatch(step3Source, /currentRoundNumber\.value \|\| Number\.MAX_SAFE_INTEGER/)
assert.match(step3Source, /查看介入节点/)
assert.match(reportSource, /导出 Markdown/)
assert.match(reportSource, /打印 \/ PDF/)
assert.match(reportSource, /URL\.createObjectURL/)
assert.match(reportSource, /window\.print\(\)/)

console.log('workflow architecture regression passed')
