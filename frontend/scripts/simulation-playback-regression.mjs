import assert from 'node:assert/strict'
import {
  advanceContinuousPlayhead,
  buildContinuousPlaybackPlan,
  buildContinuousPlaybackSnapshot,
  buildPlaybackFrame,
  buildPropagationState,
  buildTimelineBaseState,
  getFrameTimelineDuration,
  getTimelineEvents,
  mergeAnimationPayload,
  mergeTimelinePulseState,
  reconcileVisibleGraphSelection,
  selectPairFallbackEdgeIds,
} from '../src/utils/simulationPlayback.js'

const hiddenTimelineBase = buildTimelineBaseState({
  id: 'future-node',
  status: 'hidden',
  raw_animation_status: 'hidden',
  first_seen_round: 5,
}, {
  hasTimeline: true,
  currentRound: 3,
})
assert.equal(hiddenTimelineBase.status, 'hidden', 'Timeline V2 不得把后端隐藏的未来节点提升为 steady')
assert.equal(hiddenTimelineBase.animation_progress, 0, '未来节点不得在时间水位之前预先显示')
assert.equal(hiddenTimelineBase.animation_due, false, '未来节点在当前轮不得进入可见底图')

const futureTimelineBase = buildTimelineBaseState({
  id: 'future-edge',
  status: 'steady',
  raw_animation_status: 'steady',
  first_seen_round: 8,
}, {
  hasTimeline: true,
  currentRound: 7,
})
assert.equal(futureTimelineBase.status, 'hidden', '即使状态异常为 steady，first_seen_round 仍必须守住未来边时间水位')

const revealedTimelineBase = buildTimelineBaseState({
  id: 'current-edge',
  status: 'active',
  raw_animation_status: 'active',
  first_seen_round: 8,
}, {
  hasTimeline: true,
  currentRound: 8,
})
assert.equal(revealedTimelineBase.status, 'steady', '已到达当前轮的结构应作为稳定底图，由传播层单独负责脉冲')

const fadedTimelineBase = buildTimelineBaseState({
  id: 'expired-edge',
  status: 'faded',
  raw_animation_status: 'faded',
  first_seen_round: 2,
  last_active_round: 5,
}, {
  hasTimeline: true,
  currentRound: 8,
})
assert.equal(fadedTimelineBase.status, 'faded', '真实关系生命周期的 faded 状态不得被提升为 steady')

const hiddenPulseMerge = mergeTimelinePulseState(hiddenTimelineBase, {
  status: 'active',
  raw_animation_status: 'active',
  animation_progress: 0.8,
  propagation_event_id: 'stale-future-reference',
})
assert.equal(hiddenPulseMerge.status, 'hidden', '旧时间线即使引用未来节点也不得越过 hidden 生命周期水位')
assert.equal(hiddenPulseMerge.animation_progress, 0, 'future hidden 节点不得被传播脉冲恢复可见进度')
assert.equal(hiddenPulseMerge.propagation_event_id, undefined, '被拒绝的未来脉冲不得污染底图状态')

const payload = {
  timeline: {
    contract_version: 'propagation.v2',
    events: [
      {
        id: 'spread-1',
        round: 1,
        kind: 'spread',
        source: { node_ids: ['region-a'] },
        target: { node_ids: ['region-b'] },
        edge_ids: ['edge-a-b'],
        hop: 0,
        timing: { start_ms: 0, duration_ms: 1000 },
        intensity: 0.8,
        confidence: 0.9,
        grounding: { mode: 'observed' },
        display: { title_zh: '水域扩散', summary_zh: '影响从源水域传导至目标水域。' },
      },
      {
        id: 'response-1',
        round: 1,
        kind: 'relationship',
        source: { node_ids: ['region-b'] },
        target: { node_ids: ['agent-c'] },
        edge_ids: ['edge-b-c'],
        parent_event_ids: ['spread-1'],
        hop: 1,
        timing: { start_ms: 900, duration_ms: 900 },
        intensity: 0.6,
        confidence: 0.75,
        grounding: { mode: 'inferred_sequence' },
        display: { title_zh: '主体响应', summary_zh: '目标水域变化触发主体响应。' },
      },
    ],
  },
}

assert.equal(getTimelineEvents(payload).length, 2, '时间线必须稳定读取扁平事件')
assert.equal(getFrameTimelineDuration(payload, { round: 1 }, 1400), 1880, '播放时长必须覆盖最后一个真实事件')

const midFrame = buildPlaybackFrame(payload, {
  round: 1,
  focus_ids: { node_ids: ['legacy-node'], edge_ids: ['legacy-edge'] },
}, {
  elapsedMs: 500,
  durationMs: 2000,
  isPlaying: true,
})

assert.deepEqual(midFrame.focus_ids.edge_ids, ['edge-a-b'], '焦点只能指向当前传播边，不能整轮全红')
assert.deepEqual(midFrame.focus_ids.node_ids, ['region-a'], '传播尚未到达时不得提前点亮目标节点')
assert.equal(midFrame.playback_is_playing, true)

const midState = buildPropagationState(midFrame)
assert.equal(midState.edgeStates.get('edge-a-b').status, 'active')
assert(midState.edgeStates.get('edge-a-b').animation_progress > 0, '传播边必须按时间推进')
assert(midState.edgeStates.get('edge-a-b').animation_progress < 1, '传播边未到终点前不得整条显示')
assert.equal(midState.nodeStates.get('region-a').propagation_role, 'source')
assert(!midState.nodeStates.has('region-b'), '目标节点必须等到传播到达阶段才响应')

const arrivalFrame = buildPlaybackFrame(payload, { round: 1 }, {
  elapsedMs: 850,
  durationMs: 2000,
  isPlaying: true,
})
const arrivalState = buildPropagationState(arrivalFrame)
assert.deepEqual(arrivalFrame.focus_ids.node_ids, ['region-a', 'region-b'], '传播到达后才允许点亮目标节点')
assert.equal(arrivalState.nodeStates.get('region-b').propagation_role, 'target', '目标到达阶段必须呈现响应脉冲')

const lateFrame = buildPlaybackFrame(payload, { round: 1 }, {
  elapsedMs: 1400,
  durationMs: 2000,
})
const lateState = buildPropagationState(lateFrame)
assert(!lateState.edgeStates.has('edge-a-b'), '事件结束后传播路径必须回落到底图，不能永久累积为 new')
assert.equal(lateState.edgeStates.get('edge-b-c').status, 'active', '下一跳必须接续成为当前传播')
assert.deepEqual(lateFrame.focus_ids.edge_ids, ['edge-b-c'], '焦点必须随传播跳转')

const endedState = buildPropagationState(buildPlaybackFrame(payload, { round: 1 }, {
  elapsedMs: 1900,
  durationMs: 2000,
}))
assert.equal(endedState.edgeStates.size, 0, '整轮事件结束后不得残留任何传播边状态')
assert.equal(endedState.nodeStates.size, 0, '整轮事件结束后不得残留任何传播节点状态')

const gapFrame = buildPlaybackFrame({
  timeline: {
    events: [
      {
        id: 'gap-a',
        round: 4,
        kind: 'spread',
        source: { node_ids: ['gap-source'] },
        target: { node_ids: ['gap-middle'] },
        edge_ids: ['gap-edge-a'],
        timing: { start_ms: 0, duration_ms: 300 },
      },
      {
        id: 'gap-b',
        round: 4,
        kind: 'response',
        source: { node_ids: ['gap-middle'] },
        target: { node_ids: ['gap-target'] },
        edge_ids: ['gap-edge-b'],
        timing: { start_ms: 900, duration_ms: 300 },
      },
    ],
  },
}, {
  round: 4,
  focus_ids: { node_ids: ['legacy-node'], edge_ids: ['legacy-edge'] },
}, {
  elapsedMs: 600,
  durationMs: 1400,
})
assert.deepEqual(gapFrame.active_propagation_event_ids, [], '传播间隙不得把已经结束的事件伪装成当前事件')
assert.deepEqual(gapFrame.focus_ids.node_ids, [], '传播间隙必须只保留低亮底图，不得恢复整轮旧焦点')
assert.deepEqual(gapFrame.focus_ids.edge_ids, [], '传播间隙不得让旧焦点关系重新变红')

const fallback = buildPlaybackFrame({}, {
  round: 2,
  focus_ids: { node_ids: ['node-2'], edge_ids: ['edge-2'] },
}, {
  elapsedMs: 300,
  durationMs: 1400,
})
assert.deepEqual(fallback.focus_ids.edge_ids, ['edge-2'], '旧动画无时间线时必须保持兼容')

const denseEvents = Array.from({ length: 30 }, (_, index) => ({
  id: `dense-${index}`,
  round: 3,
  phase: index < 20 ? 'environment_diffusion' : 'relationship_change',
  kind: index < 20 ? 'spread_applied' : 'relationship_event',
  source: { node_ids: [`source-${index}`] },
  target: { node_ids: [`target-${index}`] },
  edge_ids: [`edge-${index}`],
  sequence: index + 1,
  timing: { start_ms: index * 5, duration_ms: 760 },
  display: { title_zh: '传播事件', summary_zh: '传播事件进入关系网络。' },
}))
const denseFrame = buildPlaybackFrame({ timeline: { events: denseEvents } }, { round: 3 }, {
  elapsedMs: 900,
  durationMs: 2400,
  isPlaying: true,
})
assert.equal(denseFrame.propagation_events.length, 18, '高密度轮次必须限制可读的传播前沿')
assert(denseFrame.active_propagation_event_ids.length <= 3, '同一时刻最多保留三条可读传播路径')
assert(
  denseFrame.propagation_events.some(event => event.phase === 'relationship_change'),
  '高密度抽样必须保留后续关系阶段，不能只展示最早一类事件',
)

const phaseBalancedFrame = buildPlaybackFrame({
  timeline: {
    events: [
      ...Array.from({ length: 2 }, (_, index) => ({
        id: `balanced-diffusion-${index}`,
        round: 9,
        phase: 'environment_diffusion',
        kind: 'spread_applied',
        source: { node_ids: ['outbreak-source'] },
        target: { node_ids: [`diffusion-target-${index}`] },
        path_edge_ids: [`diffusion-edge-${index}`],
        related_edge_ids: [],
        timing: { start_ms: index * 40, duration_ms: 900 },
      })),
      ...Array.from({ length: 8 }, (_, index) => ({
        id: `balanced-agent-${index}`,
        round: 9,
        phase: 'agent_response',
        kind: 'agent_interaction',
        source: { node_ids: [`agent-source-${index}`] },
        target: { node_ids: [`agent-target-${index}`] },
        path_edge_ids: [`agent-edge-${index}`],
        related_edge_ids: [],
        timing: { start_ms: 80 + (index * 20), duration_ms: 900 },
      })),
      ...Array.from({ length: 4 }, (_, index) => ({
        id: `balanced-relation-${index}`,
        round: 9,
        phase: 'relationship_change',
        kind: 'dynamic_edge_created',
        source: { node_ids: [`relation-source-${index}`] },
        target: { node_ids: [`relation-target-${index}`] },
        path_edge_ids: [`relation-edge-${index}`],
        related_edge_ids: [],
        timing: { start_ms: 120 + (index * 20), duration_ms: 900 },
      })),
    ],
  },
}, { round: 9 }, {
  elapsedMs: 300,
  durationMs: 1600,
  isPlaying: true,
})
assert.equal(phaseBalancedFrame.active_propagation_event_ids.length, 3, '阶段轮询后仍必须遵守三条并发上限')
assert(
  phaseBalancedFrame.active_propagation_event_ids.includes('balanced-diffusion-0'),
  '尚未结束的爆发扩散主波不得被较晚启动的 Agent 事件挤出当前传播层',
)
assert(
  phaseBalancedFrame.active_propagation_event_ids.some(id => id.startsWith('balanced-agent-'))
    && phaseBalancedFrame.active_propagation_event_ids.some(id => id.startsWith('balanced-relation-')),
  '并发选择仍需同时保留主体响应与关系变化阶段',
)

const explicitDenseEvents = [
  {
    id: 'explicit-parent',
    round: 8,
    hop: 0,
    phase: 'environment_diffusion',
    source: { node_ids: ['explicit-source'] },
    target: { node_ids: ['explicit-middle'] },
    edge_ids: ['explicit-parent-edge'],
    timing: { start_ms: 700, duration_ms: 400 },
  },
  {
    id: 'explicit-child',
    round: 8,
    hop: 3,
    phase: 'relationship_change',
    parent_event_ids: ['explicit-parent'],
    source: { node_ids: ['explicit-middle'] },
    target: { node_ids: ['explicit-target'] },
    edge_ids: ['explicit-child-edge'],
    timing: { start_ms: 1200, duration_ms: 300 },
  },
  {
    id: 'legacy-child',
    round: 8,
    hop: 4,
    phase: 'relationship_change',
    parent_event_ids: ['explicit-parent'],
    source: { node_ids: ['explicit-middle'] },
    target: { node_ids: ['legacy-target'] },
    edge_ids: ['legacy-child-edge'],
  },
  ...Array.from({ length: 5 }, (_, index) => ({
    id: `explicit-density-${index}`,
    round: 8,
    hop: index % 2,
    phase: index % 2 ? 'agent_interaction' : 'dynamic_edge_lifecycle',
    source: { node_ids: [`density-source-${index}`] },
    target: { node_ids: [`density-target-${index}`] },
    edge_ids: [`density-edge-${index}`],
    timing: { start_ms: 100 + (index * 180), duration_ms: 260 + index },
  })),
]
const explicitDenseFrame = buildPlaybackFrame({ timeline: { events: explicitDenseEvents } }, { round: 8 }, {
  elapsedMs: 0,
  durationMs: 2400,
})
const explicitParent = explicitDenseFrame.propagation_events.find(event => event.event_id === 'explicit-parent')
const explicitChild = explicitDenseFrame.propagation_events.find(event => event.event_id === 'explicit-child')
const legacyChild = explicitDenseFrame.propagation_events.find(event => event.event_id === 'legacy-child')
assert.equal(explicitParent.timing.start_ms, 700, '高密度轮次不得覆盖父事件的显式开始时间')
assert.equal(explicitParent.timing.duration_ms, 400, '高密度轮次不得覆盖父事件的显式持续时间')
assert.equal(explicitChild.timing.start_ms, 1200, '跨 hop/phase 的子事件必须保留后端显式时序')
assert.equal(explicitChild.timing.duration_ms, 300, '跨 hop/phase 的子事件必须保留后端显式时长')
assert(
  legacyChild.timing.start_ms >= explicitParent.timing.start_ms + explicitParent.timing.duration_ms,
  '缺少 timing 的 legacy 子事件不得早于父事件结束',
)
assert.deepEqual(
  explicitDenseFrame.propagation_events
    .filter(event => Number.isFinite(event.timing?.source_start_ms))
    .map(event => event.timing.start_ms),
  explicitDenseFrame.propagation_events
    .filter(event => Number.isFinite(event.timing?.source_start_ms))
    .map(event => event.timing.start_ms)
    .slice()
    .sort((left, right) => left - right),
  '显式 start_ms 必须决定跨 hop/phase 的播放排序',
)

const concurrentPayload = {
  timeline: {
    events: Array.from({ length: 12 }, (_, index) => ({
      id: `concurrent-${index}`,
      round: 9,
      kind: 'agent_interaction',
      source: { node_ids: [`concurrent-source-${index}`] },
      target: { node_ids: [`concurrent-target-${index}`] },
      timing: { start_ms: 0, duration_ms: 1000 },
    })),
  },
}
const concurrentFrame = buildPlaybackFrame(concurrentPayload, { round: 9 }, {
  elapsedMs: 500,
  durationMs: 1200,
})
const concurrentState = buildPropagationState(concurrentFrame)
assert.equal(concurrentFrame.active_propagation_event_ids.length, 3, '当前传播事件必须受统一三条并发上限约束')
assert.equal(concurrentState.pairStates.size, 3, '左侧图谱必须只渲染右侧当前波所列的同一批事件')
const mapConcurrentState = buildPropagationState(concurrentFrame, {
  maxActiveEvents: 2,
  maxTrailEvents: 2,
})
assert.equal(mapConcurrentState.pairStates.size, 2, '地图必须在共享故事顺序中最多突出两条前景传播路径')

const explicitParallelFrame = buildPlaybackFrame({
  timeline: {
    events: [{
      id: 'parallel-explicit',
      round: 5,
      kind: 'relationship',
      source: { node_ids: ['parallel-source'] },
      target: { node_ids: ['parallel-target'] },
      edge_id: 'parallel-edge-a',
      timing: { start_ms: 0, duration_ms: 1000 },
    }],
  },
}, { round: 5 }, { elapsedMs: 500, durationMs: 1200 })
const explicitParallelState = buildPropagationState(explicitParallelFrame)
assert(explicitParallelState.edgeStates.has('parallel-edge-a'), '显式边必须进入按 ID 匹配的传播状态')
assert(!explicitParallelState.edgeStates.has('parallel-edge-b'), '同端点的另一条平行边不得被显式事件点亮')
assert.equal(explicitParallelState.pairStates.size, 0, '显式边事件不得再写端点对回退状态')

const multiEdgeFrame = buildPlaybackFrame({
  timeline: {
    events: [{
      id: 'multi-edge-explicit',
      round: 6,
      kind: 'relationship',
      source: { node_ids: ['multi-source'] },
      target: { node_ids: ['multi-target'] },
      path_edge_ids: ['multi-edge-a', 'multi-edge-b', 'multi-edge-c'],
      related_edge_ids: [],
      timing: { start_ms: 0, duration_ms: 1000 },
    }],
  },
}, { round: 6 }, { elapsedMs: 500, durationMs: 1200 })
const multiEdgeState = buildPropagationState(multiEdgeFrame)
assert.deepEqual(
  multiEdgeFrame.propagation_events[0].edge_ids,
  ['multi-edge-a', 'multi-edge-b', 'multi-edge-c'],
  '复数有序 path_edge_ids 必须完整保留在播放事件中',
)
assert.deepEqual(
  multiEdgeFrame.focus_ids.edge_ids,
  ['multi-edge-b'],
  '复数真实边必须按后端顺序逐段推进，不能同时成为当前焦点',
)
assert.equal(multiEdgeState.edgeStates.get('multi-edge-a').animation_progress, 1, '已经走过的路径段必须完整留痕')
assert(multiEdgeState.edgeStates.get('multi-edge-b').animation_progress < 1, '当前路径段必须保持局部生长进度')
assert.notEqual(
  multiEdgeState.edgeStates.get('multi-edge-a').timeline_delay_ms,
  multiEdgeState.edgeStates.get('multi-edge-b').timeline_delay_ms,
  '复数 path_edge_ids 必须具有顺序错开的路径起点',
)
assert(!multiEdgeState.edgeStates.has('multi-edge-c'), '尚未到达的路径段不得提前点亮')
assert(!multiEdgeState.edgeStates.has('multi-edge-unlisted'), '未列入 edge_ids 的边绝不得进入传播状态')
assert.equal(multiEdgeState.pairStates.size, 0, '复数显式边也不得扩散到未引用平行边')

const splitReferenceFrame = buildPlaybackFrame({
  timeline: {
    events: [{
      id: 'relationship-split-edges',
      round: 6,
      kind: 'relationship_event',
      source: { node_ids: ['relation-source'] },
      target: { node_ids: ['relation-target'] },
      path_edge_ids: ['relationship-main-edge'],
      related_edge_ids: ['mechanism-evidence-a', 'mechanism-evidence-b'],
      mechanism_edge_ids: ['mechanism-evidence-a', 'mechanism-evidence-b'],
      timing: { start_ms: 0, duration_ms: 1000 },
    }],
  },
}, { round: 6 }, { elapsedMs: 500, durationMs: 1200 })
const splitReferenceState = buildPropagationState(splitReferenceFrame)
assert(splitReferenceState.edgeStates.has('relationship-main-edge'), '关系事件的单一主关系边仍必须按单段路径增长')
assert(!splitReferenceState.edgeStates.has('mechanism-evidence-a'), '机制证据边不得冒充传播的下一跳')
assert(!splitReferenceState.edgeStates.has('mechanism-evidence-b'), '复数机制证据边不得被串成有序路径')
assert.deepEqual(splitReferenceFrame.focus_ids.edge_ids, ['relationship-main-edge'], '焦点只能跟随 path_edge_ids')

const untypedMultiEdgeFrame = buildPlaybackFrame({
  timeline: {
    events: [{
      id: 'legacy-untyped-edge-set',
      round: 6,
      kind: 'relationship_event',
      source: { node_ids: ['legacy-related-source'] },
      target: { node_ids: ['legacy-related-target'] },
      edge_ids: ['legacy-related-a', 'legacy-related-b'],
      timing: { start_ms: 0, duration_ms: 1000 },
    }],
  },
}, { round: 6 }, { elapsedMs: 500, durationMs: 1200 })
const untypedMultiEdgeState = buildPropagationState(untypedMultiEdgeFrame)
assert.deepEqual(untypedMultiEdgeFrame.propagation_events[0].path_edge_ids, [], '无有序契约的 legacy 多边集合不得升级为 path')
assert.deepEqual(
  untypedMultiEdgeFrame.propagation_events[0].related_edge_ids,
  ['legacy-related-a', 'legacy-related-b'],
  '无有序契约的 legacy 多边集合只可作为关联引用',
)
assert.equal(untypedMultiEdgeState.edgeStates.size, 0, 'legacy 多边集合不得进入逐段路径动画')
assert.equal(untypedMultiEdgeState.pairStates.size, 0, '已有相关边集合时不得另造端点对传播桥')

const pairFallbackFrame = buildPlaybackFrame({
  timeline: {
    events: [{
      id: 'legacy-pair-fallback',
      round: 7,
      kind: 'relationship',
      source: { node_ids: ['legacy-source'] },
      target: { node_ids: ['legacy-target'] },
      timing: { start_ms: 0, duration_ms: 1000 },
    }],
  },
}, { round: 7 }, { elapsedMs: 500, durationMs: 1200 })
const pairFallbackState = buildPropagationState(pairFallbackFrame)
assert.equal(pairFallbackState.edgeStates.size, 0, '无边 ID 的旧事件不得伪造具体边')
assert(pairFallbackState.pairStates.has('legacy-source->legacy-target'), '只有无任何边 ID 时才允许端点对回退')
assert.equal(
  pairFallbackState.pairStates.get('legacy-source->legacy-target').propagation_grounding,
  'schematic/partial',
  '无边 ID 的中性桥接必须明确标记为示意且部分锚定',
)
const fallbackVisualEdgeIds = selectPairFallbackEdgeIds([
  { uuid: 'legacy-edge-z', source_node_uuid: 'legacy-source', target_node_uuid: 'legacy-target' },
  { uuid: 'legacy-edge-a', source_node_uuid: 'legacy-source', target_node_uuid: 'legacy-target' },
], pairFallbackState.pairStates)
assert.deepEqual(
  [...fallbackVisualEdgeIds],
  ['legacy-edge-a'],
  '无边 ID 且同端点有多条业务边时只能选择一条确定性的中性可视路径',
)

const crossRoundPayload = {
  frames: [
    { round: 0, node_states: [], edge_states: [], focus_ids: { node_ids: [], edge_ids: [] } },
    { round: 1, node_states: [], edge_states: [], focus_ids: { node_ids: [], edge_ids: [] } },
  ],
  timeline: {
    contract_version: 'simulation-playback-timeline.v2',
    events: [
      {
        id: 'cross-round-parent',
        round: 0,
        phase: 'environment_diffusion',
        kind: 'spread_applied',
        source: { node_ids: ['cross-source'] },
        target: { node_ids: ['cross-middle'] },
        path_edge_ids: ['cross-parent-edge'],
        related_edge_ids: [],
        timing: { start_ms: 0, duration_ms: 600 },
      },
      {
        id: 'cross-round-child',
        round: 1,
        phase: 'environment_diffusion',
        kind: 'spread_applied',
        parent_event_ids: ['cross-round-parent'],
        source: { node_ids: ['cross-middle'] },
        target: { node_ids: ['cross-target'] },
        path_edge_ids: ['cross-child-edge'],
        related_edge_ids: [],
        timing: { start_ms: 0, duration_ms: 600 },
      },
    ],
  },
}
const crossRoundPlan = buildContinuousPlaybackPlan(crossRoundPayload)
assert.equal(crossRoundPlan.source_mode, 'compiled_v2_round_segments', 'Timeline V2 必须进入连续 round 段兼容编译')
assert.equal(crossRoundPlan.rounds[1].start_ms, crossRoundPlan.rounds[0].end_ms, '相邻轮次必须共享一个无空帧的全局边界')
const plannedCrossParent = crossRoundPlan.events.find(event => event.event_id === 'cross-round-parent')
const plannedCrossChild = crossRoundPlan.events.find(event => event.event_id === 'cross-round-child')
assert(
  plannedCrossChild.timing.global_start_ms >= plannedCrossParent.timing.global_end_ms,
  '跨轮子事件不得在父传播完成前启动',
)
const crossBoundarySnapshot = buildContinuousPlaybackSnapshot(
  crossRoundPayload,
  crossRoundPlan,
  crossRoundPlan.rounds[1].start_ms + 100,
  { isPlaying: true },
)
assert.equal(crossBoundarySnapshot.round, 1, '全局 playhead 跨过 checkpoint 后必须派生下一轮')
assert(
  crossBoundarySnapshot.playback_global_elapsed_ms > crossRoundPlan.rounds[0].end_ms,
  '跨轮后全局 playhead 不得归零',
)
assert.equal(crossBoundarySnapshot.playback_round_elapsed_ms, 100, '轮内 elapsed 只能作为状态投影的派生值')
assert(
  crossBoundarySnapshot.trail_propagation_event_ids.includes('cross-round-parent'),
  '跨轮子事件启动时必须保留父路径的低亮视觉记忆',
)
const crossBoundaryState = buildPropagationState(crossBoundarySnapshot)
assert.equal(crossBoundaryState.edgeStates.get('cross-parent-edge')?.status, 'faded', '父路径 trail 必须降级为低亮而不是重新激活')

const v3Payload = {
  frames: [{ round: 0 }, { round: 1 }],
  timeline: {
    contract_version: 'simulation-playback-timeline.v3',
    clock: {
      unit: 'millisecond',
      basis: 'committed_story_clock',
      committed_start_ms: 1000,
      committed_end_ms: 7000,
    },
    head: { cursor: 2, checkpoint_round: 1, committed_end_ms: 7000 },
    rounds: [
      { round: 0, start_ms: 1000, end_ms: 3000, duration_ms: 2000, start_cursor: 0, end_cursor: 1, checkpoint_id: 'checkpoint-0' },
      { round: 1, start_ms: 3000, end_ms: 7000, duration_ms: 4000, start_cursor: 1, end_cursor: 2, checkpoint_id: 'checkpoint-1' },
    ],
    events: [
      {
        id: 'v3-parent',
        round: 0,
        kind: 'spread_applied',
        source: { node_ids: ['v3-source'] },
        target: { node_ids: ['v3-middle'] },
        path_edge_ids: ['v3-parent-edge'],
        timing: { local_start_ms: 200, global_start_ms: 1200, duration_ms: 1000, global_end_ms: 2200 },
      },
      {
        id: 'v3-child',
        round: 1,
        kind: 'spread_applied',
        parent_event_ids: ['v3-parent'],
        source: { node_ids: ['v3-middle'] },
        target: { node_ids: ['v3-target'] },
        path_edge_ids: ['v3-child-edge'],
        timing: { local_start_ms: 200, global_start_ms: 3200, duration_ms: 1200, global_end_ms: 4400 },
      },
    ],
  },
}
const v3Plan = buildContinuousPlaybackPlan(v3Payload)
assert.equal(v3Plan.source_mode, 'timeline_v3_global_clock', 'Timeline V3 的后端 global clock 必须优先于前端 fallback')
assert.equal(v3Plan.duration_ms, 6000, 'V3 committed clock 必须归一化为一个连续播放区间')
assert.equal(v3Plan.rounds[1].start_ms, 2000, 'V3 round checkpoint 必须相对 committed_start_ms 归一化')
assert.equal(v3Plan.events[0].timing.global_start_ms, 200, 'V3 event global timing 必须保持后端权威相对位置')
assert.equal(v3Plan.events[1].timing.global_start_ms, 2200, 'V3 子事件不得被 V2 编译器重新排期')
const v3Snapshot = buildContinuousPlaybackSnapshot(v3Payload, v3Plan, 2300, { isPlaying: true })
assert.equal(v3Snapshot.round, 1)
assert.equal(v3Snapshot.playback_global_elapsed_ms, 2300)
assert.equal(v3Snapshot.playback_started_event_count, 2, '已延展关系必须按全局 playhead 单调累计，不能随 trail 消失回落')
const settledV3Snapshot = buildContinuousPlaybackSnapshot(v3Payload, v3Plan, 5000, { isPlaying: true })
assert.equal(settledV3Snapshot.propagation_events.length, 0, 'renderer 不得在传播完成后持续接收历史事件')
assert.equal(settledV3Snapshot.playback_started_event_count, 2, '传播间隙的累计关系数不得回落为零')
assert.deepEqual(
  settledV3Snapshot.recent_completed_propagation_events.map(event => event.event_id),
  ['v3-child', 'v3-parent'],
  '传播间隙仍须为右栏保留最近完成的主链，而不是重新清空故事',
)

const pausedAt = 3500
const normalAdvance = advanceContinuousPlayhead(pausedAt, 100, 0.5, 10000)
const fasterAdvance = advanceContinuousPlayhead(normalAdvance, 100, 2, 10000)
assert.equal(normalAdvance, 3550, '恢复播放必须从暂停 playhead 继续，不能回到轮首')
assert.equal(fasterAdvance, 3750, '切换播放速率只能改变后续增量，不能重启当前轮次')

const canonicalPacingPayload = {
  frames: Array.from({ length: 10 }, (_, round) => ({ round })),
  timeline: {
    contract_version: 'simulation-playback-timeline.v2',
    events: Array.from({ length: 10 }, (_, round) => (
      Array.from({ length: 12 }, (_, index) => ({
        id: `canonical-${round}-${index}`,
        round,
        phase: index < 3 ? 'environment_diffusion' : index < 9 ? 'agent_response' : 'relationship_change',
        kind: index < 3 ? 'spread_applied' : index < 9 ? 'agent_interaction' : 'relationship_event',
        source: { node_ids: [`canonical-source-${round}-${index}`] },
        target: { node_ids: [`canonical-target-${round}-${index}`] },
        path_edge_ids: [`canonical-edge-${round}-${index}`],
        timing: {
          start_ms: index < 3 ? index * 160 : index < 9 ? 520 + (index - 3) * 80 : 1040 + (index - 9) * 160,
          duration_ms: index < 3 ? 760 : index < 9 ? 560 : 520,
        },
      }))
    )).flat(),
  },
}
const canonicalPacingPlan = buildContinuousPlaybackPlan(canonicalPacingPayload)
assert(
  canonicalPacingPlan.duration_ms >= 45000 && canonicalPacingPlan.duration_ms <= 60000,
  `十轮 canonical 故事节奏应在约 45-60 秒，实际为 ${canonicalPacingPlan.duration_ms}ms`,
)

const mergedPayload = mergeAnimationPayload({
  frames: [{ round: 1, marker: 'history-1' }, { round: 2, marker: 'history-2' }],
  timeline: { cursor: 2, events: [{ id: 'history-event', round: 2, sequence: 2 }] },
}, {
  frames: [{ round: 2, marker: 'incoming-replacement' }, { round: 3, marker: 'incoming-3' }],
  timeline: { cursor: 3, events: [{ id: 'incoming-event', round: 3, sequence: 3 }] },
})
assert.deepEqual(mergedPayload.frames.map(frame => frame.round), [1, 2, 3], '增量帧必须按轮次稳定合并')
assert.equal(mergedPayload.frames[1].marker, 'history-2', '重复轮次不得替换已经播放的历史帧')

const mergedV3Payload = mergeAnimationPayload({
  frames: [{ round: 0 }],
  timeline: {
    contract_version: 'simulation-playback-timeline.v3',
    timeline_id: 'timeline::stable',
    clock: { committed_end_ms: 3000 },
    head: { cursor: 1, checkpoint_round: 0 },
    rounds: [{ round: 0, start_ms: 0, end_ms: 3000, duration_ms: 3000, checkpoint_id: 'checkpoint-0' }],
    events: [{ id: 'stable-0', round: 0, sequence: 1 }],
  },
}, {
  frames: [{ round: 1 }],
  timeline: {
    contract_version: 'simulation-playback-timeline.v3',
    timeline_id: 'timeline::stable',
    clock: { committed_end_ms: 7000 },
    head: { cursor: 2, checkpoint_round: 1 },
    rounds: [{ round: 1, start_ms: 3000, end_ms: 7000, duration_ms: 4000, checkpoint_id: 'checkpoint-1' }],
    events: [{ id: 'stable-1', round: 1, sequence: 2 }],
  },
})
assert.equal(mergedV3Payload.timeline.timeline_id, 'timeline::stable')
assert.equal(mergedV3Payload.timeline.clock.committed_end_ms, 7000, '增量合并必须推进 V3 committed clock')
assert.deepEqual(
  mergedV3Payload.timeline.rounds.map(round => round.checkpoint_id),
  ['checkpoint-0', 'checkpoint-1'],
  '增量合并不得丢失 V3 round checkpoint 元数据',
)

const laterRoundSelectionGraph = {
  nodes: [
    { uuid: 'steady-node', name: '稳定节点', attributes: { animation_status: 'steady' } },
    { uuid: 'visible-target', name: '当前节点', attributes: { animation_status: 'steady' } },
    { uuid: 'future-node', name: '后续节点', attributes: { animation_status: 'active' } },
  ],
  edges: [
    { uuid: 'future-edge', source_node_uuid: 'steady-node', target_node_uuid: 'future-node', attributes: { animation_status: 'active' } },
    { uuid: 'endpoint-leak-edge', source_node_uuid: 'steady-node', target_node_uuid: 'future-node', fact_type: 'RELATED', attributes: { animation_status: 'steady' } },
    { uuid: 'parallel-visible', source_node_uuid: 'steady-node', target_node_uuid: 'visible-target', name: '当前关系', fact_type: 'RELATED', fact: '当前事实', attributes: { animation_status: 'steady', current_only: true } },
    { uuid: 'parallel-future', source_node_uuid: 'steady-node', target_node_uuid: 'visible-target', name: '未来关系', fact_type: 'RELATED', fact: '未来事实', attributes: { animation_status: 'active', future_only: 'secret' } },
    { uuid: 'self-future-a', source_node_uuid: 'future-node', target_node_uuid: 'future-node', fact_type: 'SELF_LOOP', attributes: { animation_status: 'active' } },
    { uuid: 'self-future-b', source_node_uuid: 'future-node', target_node_uuid: 'future-node', fact_type: 'SELF_LOOP', attributes: { animation_status: 'active' } },
  ],
}
const rewoundSelectionGraph = {
  nodes: [
    { uuid: 'steady-node', name: '稳定节点', attributes: { animation_status: 'steady' } },
    { uuid: 'visible-target', name: '当前节点', attributes: { animation_status: 'steady' } },
    { uuid: 'future-node', name: '后续节点', attributes: { animation_status: 'hidden' } },
  ],
  edges: [
    { uuid: 'future-edge', source_node_uuid: 'steady-node', target_node_uuid: 'future-node', attributes: { animation_status: 'hidden' } },
    { uuid: 'endpoint-leak-edge', source_node_uuid: 'steady-node', target_node_uuid: 'future-node', fact_type: 'RELATED', attributes: { animation_status: 'steady' } },
    { uuid: 'parallel-visible', source_node_uuid: 'steady-node', target_node_uuid: 'visible-target', name: '当前关系', fact_type: 'RELATED', fact: '当前事实', attributes: { animation_status: 'steady', current_only: true } },
    { uuid: 'parallel-future', source_node_uuid: 'steady-node', target_node_uuid: 'visible-target', name: '未来关系', fact_type: 'RELATED', fact: '未来事实', attributes: { animation_status: 'hidden', future_only: 'secret' } },
    { uuid: 'self-future-a', source_node_uuid: 'future-node', target_node_uuid: 'future-node', fact_type: 'SELF_LOOP', attributes: { animation_status: 'hidden' } },
    { uuid: 'self-future-b', source_node_uuid: 'future-node', target_node_uuid: 'future-node', fact_type: 'SELF_LOOP', attributes: { animation_status: 'hidden' } },
  ],
}
assert.equal(
  reconcileVisibleGraphSelection({ type: 'node', data: laterRoundSelectionGraph.nodes[2] }, rewoundSelectionGraph),
  null,
  '后续轮次选中的节点在回拨到首次出现前必须清除，不能通过名称或详情泄漏未来结构',
)
assert.equal(
  reconcileVisibleGraphSelection({ type: 'edge', data: laterRoundSelectionGraph.edges[0] }, rewoundSelectionGraph),
  null,
  '后续轮次选中的关系在回拨到首次出现前必须清除',
)
assert.equal(
  reconcileVisibleGraphSelection({ type: 'edge', data: laterRoundSelectionGraph.edges[1] }, rewoundSelectionGraph),
  null,
  '关系自身为 steady 也不得绕过 hidden 源/目标节点的时间水位',
)
assert.equal(
  reconcileVisibleGraphSelection({
    type: 'edge',
    data: {
      uuid: 'removed-future-edge',
      source_node_uuid: 'steady-node',
      target_node_uuid: 'future-node',
      fact_type: 'RELATED',
    },
  }, rewoundSelectionGraph),
  null,
  '带稳定 ID 的已删除关系不得回退匹配同端点的另一条可见关系',
)
const survivingParallelSelection = reconcileVisibleGraphSelection({
  type: 'edge',
  data: {
    isParallelGroup: true,
    name: '未来关系（2）',
    fact: '未来事实',
    source_name: '未来来源',
    target_name: '未来目标',
    attributes: { future_only: 'secret' },
    parallelEdges: [laterRoundSelectionGraph.edges[3], laterRoundSelectionGraph.edges[2]],
  },
}, rewoundSelectionGraph)
assert.equal(survivingParallelSelection.data.parallelEdges.length, 1, '并行关系组只能保留当前轮仍可见的成员')
assert.equal(survivingParallelSelection.data.parallelEdges[0].uuid, 'parallel-visible')
assert.equal(survivingParallelSelection.data.name, '当前关系', '部分幸存关系组必须从当前成员重建名称')
assert.equal(survivingParallelSelection.data.fact, '当前事实', '部分幸存关系组不得保留未来首边的事实')
assert.equal(survivingParallelSelection.data.attributes.future_only, undefined, '部分幸存关系组不得保留未来首边属性')
assert.equal(survivingParallelSelection.data.source_name, '稳定节点', '关系组来源名称必须来自当前可见节点')
assert.equal(survivingParallelSelection.data.target_name, '当前节点', '关系组目标名称必须来自当前可见节点')
assert.equal(
  reconcileVisibleGraphSelection({
    type: 'edge',
    data: {
      isSelfLoopGroup: true,
      selfLoopEdges: [laterRoundSelectionGraph.edges[4], laterRoundSelectionGraph.edges[5]],
    },
  }, rewoundSelectionGraph),
  null,
  '合并自环组的全部成员在当前轮隐藏时必须清除选择',
)

console.log('Simulation playback timeline regression checks passed.')
