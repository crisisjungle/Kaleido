import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  safeDisplayError,
  safeDisplayText,
  safeDisplayToken,
  sanitizeDisplayCopy,
  sanitizeDisplayMarkdown,
} from '../src/utils/displayText.js'
import { normalizeDominantRegions } from '../src/utils/analysisDisplay.js'

assert.equal(
  safeDisplayText('feature_relation_1527220', '地图节点'),
  '地图节点',
  '未知机器标识不得原样回退',
)

assert.equal(
  safeDisplayText('feature_context_admin_district_南山区', '作用区域'),
  '南山区',
  '机器前缀与中文名称混合时只能保留中文业务名称',
)

assert.equal(
  safeDisplayText('feature_context_admin_city_深圳市', '作用区域'),
  '深圳市',
  '城市背景内部前缀不得进入用户界面',
)

assert.equal(
  safeDisplayToken('transport_environmental_link_元朗区_深圳湾', '机制关系'),
  '元朗区 · 深圳湾',
  '混合关系标识只能保留中文关系两端',
)

assert.equal(
  safeDisplayText('risk_v2_xxx_南山区复合级联风险', '风险对象'),
  '南山区复合级联风险',
  '风险对象内部版本前缀不得进入标题',
)

assert.deepEqual(
  normalizeDominantRegions([
    { region_name: '未命名区域', score: 80 },
    { region_name: 'unknown_region_id', score: 70 },
    { region_name: 'jianghan_market_corridor', score: 60 },
    { region_name: '江岸医疗带', score: 50 },
  ], value => ({ jianghan_market_corridor: '江汉市场走廊' })[value] || ''),
  [
    { region_name: 'jianghan_market_corridor', score: 60, display_name: '江汉市场走廊' },
    { region_name: '江岸医疗带', score: 50, display_name: '江岸医疗带' },
  ],
  '角色透镜只能展示可解析的中文区域名，不得渲染占位区域或内部 ID',
)

assert.doesNotMatch(
  safeDisplayText('GET /api/simulation/prepare failed', '请求失败'),
  /GET|api|simulation|prepare|failed/i,
  '接口路径和英文调用信息不得进入正文',
)

assert.equal(
  safeDisplayToken('550e8400-e29b-41d4-a716-446655440000', '其他'),
  '其他',
  'UUID 不得作为可见标签',
)

assert.equal(
  safeDisplayToken('vulnerability_score', '状态指标'),
  '脆弱性',
  '已知状态枚举必须翻译',
)

for (const placeholder of ['未命名节点', '未命名区域', '未命名子区域', '未命名代理体', '未命名关系']) {
  assert.equal(
    safeDisplayText(placeholder, '关联'),
    '关联',
    `历史占位词不得进入可见界面：${placeholder}`,
  )
}

assert.equal(
  safeDisplayError(new Error('Network Error'), '网络连接失败'),
  '网络连接失败',
  '英文网络异常必须回到中文提示',
)

assert.equal(
  safeDisplayError(
    { response: { data: { error: 'POST /api/simulation/prepare failed' } } },
    '提交失败',
  ),
  '提交失败',
  '后端调用路径不得作为错误提示',
)

assert.match(
  sanitizeDisplayCopy('# 风险报告\n\n当前区域风险上升。'),
  /当前区域风险上升/,
  '中文 Markdown 正文必须保留',
)

assert.equal(
  sanitizeDisplayCopy('复合事件以 Step 2 事件机制图为准。'),
  '复合事件以第二步事件机制图为准。',
  '流程步骤名不得被清洗成孤立数字',
)

assert.doesNotMatch(
  safeDisplayText('Unnamed Entity', '未命名对象'),
  /Unnamed|Entity/,
  '英文占位类名不得进入界面',
)

for (const machineOnly of ['mech_1 -> mech_2', 'node_1 → node_2', 'source_id=abc_123', '12345']) {
  assert.equal(
    safeDisplayText(machineOnly, '安全回退'),
    '安全回退',
    `机器串清洗后不得留下标点或纯数字：${machineOnly}`,
  )
}

assert.equal(
  safeDisplayError(
    new Error("运行失败: FileNotFoundError [Errno 2] No such file: '/tmp/run.json'"),
    '运行失败，请稍后重试。',
  ),
  '运行失败，请稍后重试。',
  '异常类名和本地路径不得残留在中文错误中',
)

assert.equal(
  safeDisplayError(new Error('连接失败 at 127.0.0.1:8000/api/run'), '连接失败，请稍后重试。'),
  '连接失败，请稍后重试。',
  'IP、端口和接口路径不得残留在中文错误中',
)

assert.equal(
  safeDisplayError(
    new Error('No match for {"name":"SimulationRun","params":{"simulationId":"sim_demo_01"}}'),
    '演示恢复失败，请稍后重试。',
  ),
  '演示恢复失败，请稍后重试。',
  '路由对象或序列化响应不得直接显示在错误页',
)

assert.equal(
  safeDisplayError(
    new Error("No match for { name: 'SimulationRun', params: { simulationId: 'sim_demo_01' } }"),
    '演示恢复失败，请稍后重试。',
  ),
  '演示恢复失败，请稍后重试。',
  'JavaScript 对象格式的路由异常也不得进入错误页',
)

const sanitizedMarkdown = sanitizeDisplayMarkdown(
  '# 风险报告\n\n<tool_call>\n{"name":"envfish_summary"}\n</tool_calls>\n\n---\n\n| 指标 | 状态 |\n| --- | --- |\n| 生态保护 | crisis_mode |\n\n采用crisis_mode与marine_current，32个Agent执行RESTRICT；生态保护 vs. 经济畅通。',
)
assert.match(sanitizedMarkdown, /# 风险报告[\s\S]*\| --- \| --- \|/, '报告标题、分隔与表格结构必须保留')
assert.match(sanitizedMarkdown, /采用灾难态与海洋环流/, '报告中文正文必须保留')
assert.doesNotMatch(
  sanitizedMarkdown,
  /tool_call|envfish_summary|crisis_mode|marine_current|\bAgent\b|RESTRICT|\bvs\b/i,
  '旧报告中的工具调用、内部枚举和英文动作不得进入正文',
)

const readSource = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')
const sceneComposerSource = readSource('../src/views/SceneComposerView.vue')
const step2Source = readSource('../src/components/KaleidoStep2.vue')
const step3Source = readSource('../src/components/KaleidoStep3.vue')
const graphPanelSource = readSource('../src/components/GraphPanel.vue')
const step1GraphSource = readSource('../src/components/Step1GraphBuild.vue')
const workflowActionBarSource = readSource('../src/components/ui/WorkflowActionBar.vue')
const mainViewSource = readSource('../src/views/MainView.vue')
const historyViewSource = readSource('../src/views/HistoryView.vue')
const analysisViewSource = readSource('../src/views/AnalysisView.vue')
const step4ReportSource = readSource('../src/components/Step4Report.vue')
const simulationViewSource = readSource('../src/views/SimulationView.vue')
const simulationRunViewSource = readSource('../src/views/SimulationRunView.vue')
const workflowStepMenuSource = readSource('../src/components/WorkflowStepMenu.vue')
const visualTokensSource = readSource('../src/styles/tokens.css')

assert.match(
  step3Source,
  /startRoundValue === '' \|\| startRoundValue == null[\s\S]*Math\.max\(0, Number\(startRoundValue\)\)/,
  'Step 3 必须把显式 start_round=0 原样提交，只在未提供轮次时使用下一轮',
)
assert.match(
  step3Source,
  /injectionRequestIdentity[\s\S]*idempotency_key = injectionRequestIdentity\.key/,
  'Step 3 同一干预草稿必须复用稳定请求键，避免重试产生重复记录',
)
assert.doesNotMatch(
  step3Source,
  /start_round:\s*Number\(injection\.value\.start_round\)\s*\|\|/,
  'Step 3 不得用真假值回退吞掉零轮次',
)

assert.doesNotMatch(
  sceneComposerSource,
  />\s*(?:Advanced|Effort)\s*<|`Effort:|\bLocked\b/,
  'Step 1 不得恢复英文高级入口或把机器投入字段直接上屏',
)

assert.match(sceneComposerSource, /EFFORT_DISPLAY_LABELS[\s\S]*light:\s*'Light'/, 'Step 1 必须保留用户指定的英文 Light 档位')
assert.match(sceneComposerSource, /EFFORT_DISPLAY_LABELS[\s\S]*ultra:\s*'Ultra'/, 'Step 1 必须保留用户指定的英文 Ultra 档位')
assert.match(
  sceneComposerSource,
  /const effortLabel = computed\(\(\) => EFFORT_DISPLAY_LABELS\[effortOption\.value\.value\]/,
  'Step 1 可见投入档位必须从显式产品文案映射读取，不能直接信任后端机器值',
)
assert.match(
  sceneComposerSource,
  /label:\s*'Light'[\s\S]*label:\s*'Medium'[\s\S]*label:\s*'High'[\s\S]*label:\s*'Extra High'[\s\S]*label:\s*'Ultra'/,
  'Step 1 五档分析强度必须保持用户指定的英文产品文案',
)
assert.match(sceneComposerSource, /\|\|\s*'High'/, 'Step 1 默认分析强度必须显示为 High')

for (const token of [
  '--k-text-caption',
  '--k-text-meta',
  '--k-text-body',
  '--k-text-ui',
  '--k-text-section',
  '--k-text-title',
  '--k-text-display',
]) {
  assert.match(visualTokensSource, new RegExp(`${token}:`), `共享视觉规范缺少字号 token：${token}`)
}
assert.match(sceneComposerSource, /\.scene-composer-page\s*\{[^}]*font-size:\s*var\(--k-text-body\)/s, 'Step 1 必须使用共享正文基准字号')
assert.match(step2Source, /\.envfish-step2\s*\{[^}]*font-size:\s*var\(--k-text-body\)/s, 'Step 2 必须使用共享正文基准字号')
assert.match(step3Source, /\.envfish-step3\s*\{[^}]*font-size:\s*var\(--k-text-body\)/s, 'Step 3 必须使用共享正文基准字号')
assert.match(analysisViewSource, /\.analysis-panel\s*\{[^}]*font-size:\s*var\(--k-text-body\)/s, 'Step 4 必须使用共享正文基准字号')
assert.match(analysisViewSource, /\.narrative-block p[\s\S]*font-size:\s*var\(--k-text-body\)/, 'Step 4 轮次叙事正文必须使用共享正文字号')
assert.match(step4ReportSource, /\.report-body\s*\{[^}]*font-size:\s*var\(--k-text-body\)/s, '正式报告正文必须使用共享正文字号')
assert.match(step4ReportSource, /function dedupeReportMarkdown\([\s\S]*text === expectedTitle[\s\S]*text === previousHeading/, '正式报告必须去重页眉标题和紧邻章节标题的重复正文')
assert.match(step4ReportSource, /renderMarkdown\(displayMarkdown\.value\)/, '正式报告必须渲染去重后的正文')
assert.match(analysisViewSource, /\.source-badge\s*\{[^}]*border:\s*1px solid var\(--k-color-border-strong\)[^}]*background:\s*transparent/s, 'Step 4 来源标签必须使用弱化描边样式')

assert.doesNotMatch(
  step2Source,
  /class="progress-bar"|\bRoleDemand\b|Agent\s*规划/,
  'Step 2 不得恢复旧进度条或内部规划类型名',
)
assert.match(step2Source, /<KProgress\b/, 'Step 2 生成态必须使用共享进度组件')
assert.doesNotMatch(
  step2Source,
  /本次自动规划采用的假设|scenario-assumptions/,
  'Step 2 不得把内部自动规划假设作为结果模块展示',
)
assert.match(
  step2Source,
  /class="risk-preview-list"/,
  'Step 2 风险对象必须保留紧凑横向选择区',
)
assert.doesNotMatch(
  step2Source,
  /class="risk-object-tags"/,
  'Step 2 风险详情不得恢复全量标签墙',
)
assert.doesNotMatch(
  step2Source,
  /definitions\.slice\(0,\s*8\)|legacy\.slice\(0,\s*8\)/,
  'Step 2 风险选择不得把 Ultra 多风险结果静默截断为 8 个',
)
assert.match(
  step2Source,
  /aria-label="向左浏览风险对象"[\s\S]*aria-label="向右浏览风险对象"/,
  'Step 2 多风险横向轨道必须提供鼠标可用的左右按钮',
)
assert.ok(
  (step2Source.match(/v-if="riskSelectorOverflow"/g) || []).length >= 2,
  '风险轨道未溢出时不得常驻左右按钮',
)
assert.match(step2Source, /<WorkflowActionBar\b/, 'Step 2 必须使用共享固定底部操作带')
assert.match(
  step2Source,
  /\.envfish-step2 > \.workspace-shell\s*\{[^}]*border:\s*0;[^}]*border-radius:\s*0;[^}]*background:\s*transparent;[^}]*box-shadow:\s*none;/,
  'Step 2 滚动工作区不得恢复为嵌套的巨型圆角卡片',
)
assert.match(
  workflowActionBarSource,
  /border-radius:\s*0;[\s\S]*bottom:\s*0;/,
  '共享流程底栏必须贴底且不渲染成圆角悬浮容器',
)
assert.match(
  step3Source,
  /class="control-panel runtime-console runtime-transport"/,
  'Step 3 必须保留单行推演播放器',
)
assert.doesNotMatch(
  step3Source,
  /<span>当前轮次<\/span>|<span>运行阶段<\/span>|<span>场景状态<\/span>|<span>模拟时间<\/span>|<span>状态维度<\/span>|<span>速度<\/span>|>最新<\/button>|aria-label="上一轮"|aria-label="下一轮"/,
  'Step 3 不得恢复重复状态卡、额外轮次按钮或实现参数选择器',
)
assert.match(
  step3Source,
  /class="risk-selector-track"/,
  'Step 3 风险区必须保留横向紧凑选择器',
)
assert.doesNotMatch(
  step3Source,
  /class="risk-object-picker"|<select[^>]+aria-label="选择风险对象"/,
  'Step 3 风险区不得在窄屏退回原生下拉选择器',
)
assert.match(
  step3Source,
  /aria-label="向左浏览风险对象"[\s\S]*aria-label="向右浏览风险对象"/,
  'Step 3 多风险横向轨道必须提供鼠标可用的左右按钮',
)
assert.ok(
  (step3Source.match(/v-if="riskSelectorOverflow"/g) || []).length >= 2,
  'Step 3 风险轨道未溢出时不得常驻左右按钮',
)
assert.match(step3Source, /class="risk-detail"/, 'Step 3 风险区必须保留选中对象详情')
assert.doesNotMatch(
  step3Source,
  /class="(?:risk-card-list|risk-object-card)"|主要风险对象/,
  'Step 3 不得恢复纵向风险卡片墙或重复的主要风险概览',
)
assert.doesNotMatch(step1GraphSource, /GraphRAG构建/, '旧图谱构建组件也不得保留英文产品词')
assert.doesNotMatch(step1GraphSource, /POST\s+\/api\//, '旧图谱构建组件不得显示接口路径')
assert.doesNotMatch(mainViewSource, /ref\('workbench'\)/, 'Step 2 默认必须保留地图与配置双栏')
assert.doesNotMatch(
  mainViewSource,
  /Ontology generation failed|No pending files found|Uploading and analyzing docs|Loading project|Project loaded|Graph build task|Graph data|Task ID/,
  'Step 2 入口不得恢复英文运行文案',
)
assert.doesNotMatch(
  historyViewSource,
  /Simulation Archive|SIM_UNKNOWN|`SIM_\$\{/,
  '历史页不得显示英文标题或内部模拟标识',
)
assert.doesNotMatch(
  graphPanelSource,
  /data\.fact_type\s*\|\|\s*'Unknown'|data\.name\s*\|\|\s*'RELATED_TO'/,
  '图谱详情不得用英文关系占位作为显示回退',
)
assert.match(
  analysisViewSource,
  /class="evolution-view-tabs"[\s\S]*?:collapse-on-narrow="false"[\s\S]*?aria-label="演化复盘视角"/,
  'Step 4 四个复盘视角必须始终使用横向选项卡',
)
assert.match(
  analysisViewSource,
  /GENERIC_REPORT_SUMMARIES[\s\S]*concreteReportSummary[\s\S]*reportSummaryText/,
  'Step 4 必须过滤旧报告占位摘要，并优先展示可用的业务结论',
)
assert.doesNotMatch(
  analysisViewSource,
  /overviewSummaryText[\s\S]{0,400}sanitizeDisplayCopy\([\s\S]{0,120}['"]暂无摘要['"]/,
  'Step 4 顶部摘要不得把暂无摘要作为正式业务结果',
)
assert.doesNotMatch(
  analysisViewSource,
  /class="subview-select"|<select[^>]*:value="evolutionView"/,
  'Step 4 四个固定复盘视角不得恢复为下拉框',
)
assert.ok(
  (analysisViewSource.match(/:collapse-on-narrow="false"/g) || []).length >= 2,
  'Step 4 主选项卡和复盘选项卡在窄宽下都不得退化为下拉框',
)
assert.match(
  analysisViewSource,
  /class="role-comparison"[\s\S]*?group\.visible_dominant_regions\[0\]\.display_name/,
  'Step 4 角色透镜必须使用扁平对比行和过滤后的首要区域',
)
assert.doesNotMatch(
  analysisViewSource,
  /class="(?:role-card|risk-mechanism-summary|subview-switch)"/,
  'Step 4 不得恢复角色卡片墙、机制统计卡或旧子视图容器',
)
assert.match(
  analysisViewSource,
  /v-for="item in mechanismsTab\.scenario_model\.state_variables"/,
  'Step 4 必须展示全部场景状态变量，不能静默截断最后一项',
)
assert.doesNotMatch(
  analysisViewSource,
  /state_variables[^\n]*\.slice\(0,\s*5\)/,
  'Step 4 场景状态变量不得恢复五项硬截断',
)
for (const nonEmptyGuard of [
  'mechanismsTab.scenario_model?.state_variables?.length',
  'mechanismsTab.mechanism_graph?.edges?.length',
  'mechanismsTab.relation_samples?.length',
  'mechanismsTab.round_reasoning?.length',
  'mechanismsTab.simulation_audit?.quality_flags?.length',
]) {
  assert.match(
    analysisViewSource,
    new RegExp(`v-if="${nonEmptyGuard.replace(/[?.]/g, '\\$&')}"\\s+class="mechanism-section"`),
    `Step 4 机制分段必须按真实数据决定是否显示：${nonEmptyGuard}`,
  )
}
assert.doesNotMatch(
  analysisViewSource,
  /safeVisibleText\(region\.region_name,\s*['"]未知区域['"]\)/,
  'Step 4 角色透镜不得用未知区域占位词补造主受影响区域',
)
assert.match(
  analysisViewSource,
  /\.analysis-hero,[\s\S]*?\.analysis-state\s*\{[^}]*border:\s*0;[^}]*border-radius:\s*0;[^}]*background:\s*transparent;[^}]*box-shadow:\s*none;/,
  'Step 4 分析分段不得恢复为层层嵌套的外层卡片',
)
assert.match(
  step4ReportSource,
  /\.report-panel\s*\{[^}]*border:\s*0;[^}]*border-radius:\s*0;[^}]*background:\s*transparent;/,
  'Step 4 正式报告不得再包一层圆角报告卡片',
)
assert.doesNotMatch(
  [step2Source, step3Source, simulationViewSource, simulationRunViewSource, analysisViewSource, step4ReportSource, workflowStepMenuSource].join('\n'),
  /可运行场景已经生成|场景配置已完成|推演播放已完成|分析与正式报告已完成|报告任务已经完成|报告任务未能完成/,
  '正式流程不得用成功或失败声明替代业务结果',
)
assert.doesNotMatch(
  step2Source,
  /已确认 · 已生成|已确认 · 生成中|已确认 · 等待生成|模拟入口已就绪，可以生成场景配置/,
  'Step 2 不得在业务界面汇报内部确认或生成状态',
)
assert.match(
  mainViewSource,
  /hasPersistedSemanticInput[\s\S]*normalizedEventInputs:[\s\S]*semanticInput\.events[\s\S]*normalizedPolicyInputs:[\s\S]*semanticInput\.policies/,
  'Step 2 必须优先使用项目持久化语义工件，而不是页面恢复状态',
)
assert.match(
  step2Source,
  /sourceInputId:[\s\S]*input_id: variable\.sourceInputId \|\| variable\.id/,
  '事件卡和政策卡应使用独立本地 ID，同时提交原始语义输入 ID',
)
assert.doesNotMatch(
  step3Source,
  /placeholder="[^"]*,[^"]*"/,
  '运行时目标输入不得用英文逗号示例暗示前端拆分语义',
)
assert.match(
  sceneComposerSource,
  /GENERIC_AREA_LABELS[\s\S]*?concreteAreaLabel[\s\S]*?areaNamePreview/,
  '地点展示必须过滤泛化地图标签并保留用户地点原文',
)
assert.doesNotMatch(
  sceneComposerSource,
  /已定位到 \$\{resolvedAreaLabel\}|部分辅助来源未返回|WorldCover 当前仅作背景显示/,
  '正式 Step 1 不得展示识别成功或空间数据源处理过程',
)

console.log('displayText leakage regression: ok')
