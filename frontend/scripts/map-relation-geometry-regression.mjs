import assert from 'node:assert/strict'
import {
  CURATED_FIXTURE_GROUNDING,
  isCuratedFixtureNode,
  isCuratedFixtureRouteEdge,
  normalizeMapAnimationStatus,
  normalizeEdgeGeometryCandidate,
  orientGeometryFromSource,
  resolveEdgeGeometry,
  resolveCuratedFixtureEdgeGrounding,
  sliceGeometryByProgress,
} from '../src/utils/mapRelationGeometry.js'
import { readAnimationMapProjectionMetadata } from '../src/utils/mapProjection.js'

assert.equal(normalizeMapAnimationStatus('hidden'), 'hidden', '未来节点与边的 hidden 状态必须保持不可见')
assert.equal(normalizeMapAnimationStatus('faded'), 'faded', '已出现但衰减的关系应保留 faded 语义')
assert.equal(normalizeMapAnimationStatus('unexpected'), 'steady', '未知旧状态只能回退为稳定底图')

const curatedSourceNode = {
  id: 'region::fixture-source',
  is_geographic: true,
  attributes: {
    lat: 30.6,
    lon: 114.27,
    is_geographic: true,
    placement: 'curated_fixture',
    coordinate_grounding: CURATED_FIXTURE_GROUNDING,
    coordinates_observed: false,
  },
}
assert.equal(isCuratedFixtureNode(curatedSourceNode), true, '显式金标坐标应被识别为可定位的 fixture 节点')
assert.equal(
  isCuratedFixtureNode({
    ...curatedSourceNode,
    attributes: { ...curatedSourceNode.attributes, lat: undefined },
  }),
  false,
  '缺失坐标的 fixture 节点不得获得地理传播资格',
)
assert.equal(
  isCuratedFixtureNode({
    ...curatedSourceNode,
    attributes: { ...curatedSourceNode.attributes, placement: 'synthetic' },
  }),
  false,
  'synthetic 节点不得因顶层 fixture grounding 被放宽为地理节点',
)

const curatedRouteEdge = {
  fact_type: 'transport_edge',
  attributes: {
    is_route_edge: true,
    route_grounding: CURATED_FIXTURE_GROUNDING,
    route_observed: false,
  },
}
assert.equal(isCuratedFixtureRouteEdge(curatedRouteEdge), true, '显式金标 transport route 应允许推演波纹')
assert.equal(
  resolveCuratedFixtureEdgeGrounding(
    { ...curatedSourceNode, kind: 'region' },
    {
      ...curatedSourceNode,
      id: 'region::fixture-target',
      kind: 'region',
      attributes: { ...curatedSourceNode.attributes, lat: 30.7, lon: 114.4 },
    },
    curatedRouteEdge,
  ),
  'curated_fixture',
  '地图仅应把双端 fixture 坐标与显式 transport route 组合提升为金标传播路径',
)
assert.equal(
  resolveCuratedFixtureEdgeGrounding(
    { ...curatedSourceNode, kind: 'region' },
    {
      ...curatedSourceNode,
      id: 'region::fixture-target',
      kind: 'region',
      attributes: { ...curatedSourceNode.attributes, lat: 30.7, lon: 114.4 },
    },
    { fact_type: 'region_neighbor', attributes: {} },
  ),
  'schematic',
  '没有 fixture route grounding 的区域关系只能保留为静态示意',
)
assert.equal(
  isCuratedFixtureRouteEdge({
    fact_type: 'agent_influence',
    attributes: curatedRouteEdge.attributes,
  }),
  false,
  '普通关系边不得借用 fixture grounding 伪装为空间传播路径',
)
assert.equal(
  isCuratedFixtureRouteEdge({
    fact_type: 'transport_edge',
    attributes: { ...curatedRouteEdge.attributes, route_grounding: 'synthetic' },
  }),
  false,
  'synthetic transport edge 不得进入金标空间波纹层',
)

assert.deepEqual(
  readAnimationMapProjectionMetadata({
    source_mode: 'golden_case',
    map_seed_id: null,
    geographic_grounding: CURATED_FIXTURE_GROUNDING,
    data_quality: { status: 'curated_fixture', fixture_ready: true },
    selection_summary: { source: 'golden_fixture' },
    meta: { spatial_fixture_id: 'wuhan' },
  }, {
    source_mode: 'map_seed',
    map_seed_id: 'must-not-leak',
    geographic_grounding: 'map_seed',
    data_quality: { status: 'complete' },
    meta: { projection_version: 'v1' },
  }),
  {
    source_mode: 'golden_case',
    map_seed_id: null,
    geographic_grounding: CURATED_FIXTURE_GROUNDING,
    data_quality: { status: 'curated_fixture', fixture_ready: true },
    selection_summary: { source: 'golden_fixture' },
    meta: { projection_version: 'v1', spatial_fixture_id: 'wuhan' },
  },
  '动画地图重建必须保留 layout 的 grounding、质量、seed 空值与 meta',
)

assert.deepEqual(
  normalizeEdgeGeometryCandidate({
    type: 'LineString',
    coordinates: [['0', '0'], ['bad', 1], [2, 0]],
  }),
  { type: 'LineString', coordinates: [[0, 0], [2, 0]] },
  'LineString 必须归一化数值坐标并丢弃无效点',
)

assert.deepEqual(
  normalizeEdgeGeometryCandidate(JSON.stringify({
    type: 'MultiLineString',
    coordinates: [
      [[0, 0], [2, 0]],
      [[2, 0], [2, 2]],
      [[9, 9]],
    ],
  })),
  {
    type: 'MultiLineString',
    coordinates: [
      [[0, 0], [2, 0]],
      [[2, 0], [2, 2]],
    ],
  },
  'MultiLineString 必须保留有效线段并移除不足两个点的片段',
)

assert.deepEqual(
  orientGeometryFromSource(
    { type: 'LineString', coordinates: [[4, 0], [2, 0], [0, 0]] },
    [0, 0],
  ).coordinates,
  [[0, 0], [2, 0], [4, 0]],
  'LineString 必须从 source 向 target 定向',
)

assert.deepEqual(
  orientGeometryFromSource(
    {
      type: 'MultiLineString',
      coordinates: [
        [[4, 0], [3, 0]],
        [[2, 0], [0, 0]],
      ],
    },
    [0, 0],
  ).coordinates,
  [
    [[0, 0], [2, 0]],
    [[3, 0], [4, 0]],
  ],
  'MultiLineString 反向时必须同时反转线段顺序和每段方向',
)

assert.deepEqual(
  sliceGeometryByProgress(
    { type: 'LineString', coordinates: [[0, 0], [4, 0]] },
    0.25,
  ).coordinates,
  [[0, 0], [1, 0]],
  '直线传播必须按 progress 插值到当前位置',
)

assert.deepEqual(
  sliceGeometryByProgress(
    { type: 'LineString', coordinates: [[0, 0], [2, 0], [2, 2]] },
    0.75,
  ).coordinates,
  [[0, 0], [2, 0], [2, 1]],
  '多段 LineString 必须按累计路径长度截取',
)

assert.deepEqual(
  sliceGeometryByProgress(
    {
      type: 'MultiLineString',
      coordinates: [
        [[0, 0], [2, 0]],
        [[2, 0], [2, 2]],
      ],
    },
    0.75,
  ).coordinates,
  [
    [[0, 0], [2, 0]],
    [[2, 0], [2, 1]],
  ],
  'MultiLineString 必须跨线段按累计长度连续截取',
)

assert.deepEqual(
  resolveEdgeGeometry(
    { lon: 1, lat: 2 },
    { lon: 3, lat: 4 },
    {},
  ),
  {
    type: 'LineString',
    coordinates: [[1, 2], [3, 4]],
  },
  '缺少 geometry 时必须退化为 source-target 直线，不能制造随机折点',
)

assert.deepEqual(
  resolveEdgeGeometry(
    { lon: 0, lat: 0 },
    { lon: 4, lat: 0 },
    { route_geometry: { type: 'LineString', coordinates: [[4, 0], [2, 1], [0, 0]] } },
  ).coordinates,
  [[0, 0], [2, 1], [4, 0]],
  '已有路线 geometry 必须优先使用并按 source 定向',
)

console.log('Map relation geometry regression checks passed.')
