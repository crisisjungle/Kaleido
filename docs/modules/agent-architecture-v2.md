# Agent Architecture V2

## 当前能力

Agent V2 已进入共享正式流程，不再是地图节点补齐器。当前主链为：

```text
锁定 EffortSnapshot
-> 地图空间证据与 EventMechanismGraph
-> RoleDemand
-> AgentArchetype 匹配
-> AgentInstance 建档与空间放置
-> AgentPlan / PlacementPlan / ResolutionPlan
-> PolicyExecutionPlan 与 Risk Object 作用域
-> 每轮行动、关系、政策、涌现和风险观察
```

核心边界如下：

1. Agent 必须由场景角色需求、空间证据和执行边界共同产生，不使用目标数量补齐。
2. `AgentArchetype` 是主体类型、角色、能力、权限和资源边界的权威来源；旧地图/模板生成器只提供候选与证据，不能覆盖 V2 类型。
3. 设施、实体、政策目标和旧名称先归一化到正式区域 ID。无法解析的引用进入审计字段，不能伪装成确定地点，也不能默认落到列表中的第一个区域。
4. Agent 档案、实例初始状态和逐轮运行状态分离，任何状态变化都通过追加式记录保存。
5. Risk Object 只读取统一状态和已发生行动，不进入 Agent 候选、行动决策或涌现判断。
6. 运行时支持休眠 Agent 激活、聚合 Agent 拆分和临时 Agent 创建；新 Agent 在发现轮结束后建档，下一轮生效。

完整设计和五档限制总表见 [Agent 整体架构 V2 重构计划](../plans/agent-architecture-v2-plan.md)。

## Step 1 到 Step 2

Step 1 的 AOI 决定分析边界，Effort 决定可投入的空间候选、规划锚点、热点下钻和定向细化预算。地图渲染数量与规划证据数量分离，界面折叠节点不得裁掉 Agent 规划输入。

`ScenarioPlanner` 从事件链与机制图提取 `RoleDemand`。每条需求至少描述：

- 所需能力、辖区和空间分辨率；
- 对应事件、机制和受影响对象；
- 重要性、证据与无法覆盖时的原因；
- 政策执行所需能力，但不预先绑定具体 Agent。

`AgentPlannerV2` 对需求进行兼容合并、原型匹配、候选选择和实例放置。只有空间、资源、容量或治理独立性会改变结果时才拆成多个同类 Agent；证据只到区域级时，实例必须标记为 `region_aggregate` 或 `group_representative`，不能生成虚构的具体机构。

正式输出包括：

- `AgentPlan`：实例档案、覆盖的 RoleDemand、生成依据与审计摘要；
- `PlacementPlan`：主区域、影响区域、空间证据和未解析引用；
- `ResolutionPlan`：聚合、代表、子单元或设施级表示及其拆分条件；
- `PolicyExecutionPlan`：政策触发条件、候选执行者、能力匹配、目标区域和未绑定原因。

每个 Agent 档案保存角色目标、生命周期、表示粒度、能力、权限、资源及不确定性、约束、影响区域、角色需求引用、证据引用和生成理由。Step 2 以比较表展示摘要，展开行才显示完整档案。

## Step 3 每轮顺序

运行器使用固定顺序，避免风险结果反向污染 Agent 决策：

1. 激活本轮到期的新 Agent。
2. 应用变量并计算物理扩散。
3. 选择深度 Agent，生成并校验候选行动。
4. 执行通过能力、权限、资源、生命周期和前置条件校验的行动，并记录状态变更。
5. 根据真实互动更新关系事件、关系状态和机制传播。
6. 执行满足触发条件且已有合格执行者的政策计划。
7. 计算反馈。
8. 根据新的能力缺口执行 Agent 涌现判断。
9. 固化本轮快照。
10. Risk Object 读取快照，执行风险涌现与状态刷新。

行动失败也必须记录原因；不能因为模型提出了某动作就默认执行。关系只因可解释事件变化，不能因共处一地或共用风险标签自动增强。当前关系状态维护信任、依赖、协调和张力，并保存对应的 `RelationshipEvent`。

## 运行时 Agent 涌现

涌现检测输入是本轮新证据、行动失败产生的能力缺口、跨区协调缺口和结构化 `capability_gaps`，不是 Risk Object ID。解析顺序固定为：

1. 激活已经存在但休眠的合格 Agent；
2. 只从同一 `AgentArchetype` 的现有聚合 Agent 拆出独立子 Agent，并保持父子资源守恒；
3. 证据仍无法覆盖时，创建权限受限的临时 Agent。

普通候选需连续两轮出现，且证据分不低于 `60`、影响分不低于 `50`。关键候选只有在证据和影响均不低于 `80` 时可立即解析。创建与拆分受 Effort 的整场和单轮上限约束；激活已有 Agent 不消耗新增名额。

跨原型能力缺口不得借用不相关聚合主体的身份、档案、权限或资源。例如环境监测聚合主体不能拆成医疗主体；此类缺口必须进入临时 Agent 路径。临时 Agent 默认只能观察、协调和建议，`authority` 为零。没有权限证据时，即使名称包含监管含义，也不能自动获得执法权。所有创建、拆分、唤醒、谱系和候选处理结果都写入追加式账本，历史轮次不回写。

## 风险与政策边界

- Risk Object 可以引用 Agent、关系和机制边形成观察与归因，但不能创建 Agent。
- 风险涌现可以暴露能力缺口，缺口仍需由独立的 Agent 涌现门槛判断。
- 政策先由 `PolicyExecutionPlan` 匹配执行能力和作用区域；没有合格执行者时保留为未绑定计划，不编造执行结果。
- 政策执行改变统一场景状态、Agent 资源或关系状态；风险对象只在后续快照读取这些变化。
- 运行时新增灾害变量的用户入口暂未开放，现有合同保留未来 `ScenarioPatch` 向后续轮次追加事件、机制和 Agent 需求的能力。

## 持久化与界面

运行期追加维护：

- `agent_action_decision_ledger.jsonl`：行动候选、校验和执行结果；
- `state_mutation_ledger.jsonl`：Agent、区域和关系状态变更；
- `relationship_event_ledger.jsonl` 与关系状态快照：动态关系依据；
- `policy_execution_ledger.jsonl`：政策触发、执行者、目标和结果；
- `agent_emergence_state.json`：候选连续轮次、已解析签名和 Effort 使用量；
- `agent_emergence_ledger.jsonl`：创建、拆分、唤醒和正式激活事件；
- `agent_lineage_ledger.jsonl`：父子谱系、需求依据、创建轮和生效轮；
- `agent_candidate_ledger.jsonl`：待观察、覆盖、延后、容量缺口和解析原因。

Step 2 显示角色需求覆盖、未覆盖需求、新建聚合 Agent、政策执行绑定和完整建档依据。Step 3 的 Agent 工作台显示生命周期、表示粒度、能力、相对资源和最近行动；“关系与风险”显示关系状态、关系事件、Agent 生命周期事件和风险结果。机器枚举必须经过中文显示映射。

## Effort 执行状态

同一个不可变 `EffortSnapshot` 已控制地图候选/锚点/细化槽位、Step 2 机制与 Agent 规划上限、Step 3 深度 Agent、行动候选、关系搜索、动态验证、并行分支和运行时 Agent 新增上限。

`BudgetLedger` 已具备预留、结算、软硬上限和缺失 usage 处理合同，但尚未包住每一个 LLM 和外部检索调用。Step 4 的反事实、敏感性和预算审计次数目前仍是已冻结合同，不能描述为全部执行完成。

## 维护入口

| 能力 | 代码入口 | 聚焦测试 |
| --- | --- | --- |
| Effort 快照与阶段限制 | `backend/app/services/effort_contract.py` | `backend/tests/test_effort_contract.py` |
| 预算预留与结算 | `backend/app/services/budget_ledger.py` | `backend/tests/test_budget_ledger.py` |
| 地图空间细化 | `backend/app/services/map_spatial_selection.py`、`map_seed_manager.py` | `backend/tests/test_map_spatial_selection.py` |
| Agent 原型与正式规划 | `backend/app/services/scenario_planning/agent_archetypes.py`、`agent_planner.py` | `backend/tests/test_agent_planner_v2.py` |
| 政策执行者绑定 | `backend/app/services/scenario_planning/policy_execution_planner.py` | `backend/tests/test_policy_execution_planner.py` |
| 行动与状态变更 | `backend/app/services/agent_action_contract.py`、`agent_state_mutation.py` | 对应合同测试 |
| 动态关系 | `backend/app/services/agent_relationship_runtime.py` | `backend/tests/test_agent_relationship_runtime.py` |
| 运行期 Agent 涌现 | `backend/app/services/agent_emergence_detector.py` | `backend/tests/test_agent_emergence_detector.py` |
| 政策运行 | `backend/app/services/policy_runtime.py` | `backend/tests/test_policy_runtime.py` |
| 运行器集成与持久化 | `backend/scripts/run_envfish_simulation.py` | `backend/tests/test_runtime_agent_emergence_integration.py` |
| Step 2/3 解释界面 | `frontend/src/components/KaleidoStep2.vue`、`KaleidoStep3.vue` | 前端构建、中文泄漏和浏览器回归 |

## 已知限制

- Step 1 尚未完成按 EventMechanismGraph 发起的定向外部补查、完整 R4 内部单元证据和多空间假设比较。
- 开放式的新机制端点发现还没有形成“发现 -> 外部取证 -> 新 RoleDemand”的完整闭环。
- Token 账本和 Step 4 高强度分析尚未全部接线。
- 武汉冻结案例按既定范围继续读取 V1 数据；共享组件保持兼容，未来迁移正式 Agent 数据合同时必须提升 golden artifact contract version。

## 修改纪律

- 改 Effort 数值必须同步更新合同测试和计划总表。
- 不得用 Effort 改变 AOI、灾害严重度、真实时间跨度、证据门槛、权限门槛或活跃风险上限 `8`。
- 不得恢复目标 Agent 数量或数量补齐逻辑。
- 新字段的显示文本必须为简体中文，机器枚举不得直接渲染。
- 新增、拆分、唤醒、行动和关系变化必须追加记录，不得重写历史快照。

## 历史

- 2026-07-13：建立五档 Effort、地图空间细化和运行时 Agent 涌现底座。
- 2026-07-13：完成 RoleDemand、AgentArchetype、AgentInstance、政策执行绑定、行动校验、状态变更、动态关系和风险只读边界的共享正式链路。
- 2026-07-13：补齐 Step 2 建档审计与 Step 3 Agent/关系/政策解释界面，武汉冻结案例继续保持 V1 兼容。
