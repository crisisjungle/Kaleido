export const WORKFLOW_STEPS = Object.freeze([
  { step: 1, key: 'foundation', label: '背景定义', question: '我们正在研究什么现实系统？' },
  { step: 2, key: 'scenario', label: '场景生成', question: '准备让这个系统经历什么？' },
  { step: 3, key: 'runtime', label: '推演运行', question: '系统正在发生什么变化？' },
  { step: 4, key: 'analysis', label: '分析与报告', question: '这些变化意味着什么？' },
])

export const STEP2_WORKSPACE_TABS = Object.freeze([
  { value: 'plan', label: '演化计划' },
  { value: 'mechanism', label: '机制模型' },
  { value: 'region', label: '空间结构' },
  { value: 'agents', label: '主体系统' },
  { value: 'risk', label: '风险假设' },
])

export const STEP3_WORKSPACE_TABS = Object.freeze([
  { value: 'pulse', label: '本轮演化' },
  { value: 'state', label: '空间状态' },
  { value: 'spread', label: '传播机制' },
  { value: 'agents', label: '主体响应' },
  { value: 'risk', label: '风险对象' },
])

export const STEP4_ANALYSIS_TABS = Object.freeze([
  { id: 'conclusion', label: '结论与建议' },
  { id: 'evolution', label: '关键转折' },
  { id: 'mechanisms', label: '风险结果' },
  { id: 'intervention', label: '政策观察' },
  { id: 'node-explore', label: '证据与边界' },
])

export const MECHANISM_CHAIN_LAYOUT = Object.freeze({
  completeMax: 6,
  overviewMax: 10,
  collapsedHeadCount: 4,
  collapsedTailCount: 3,
})
