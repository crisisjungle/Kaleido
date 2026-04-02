# EnvFish 动态跨区关系网络方案

## 1. 目标

EnvFish 当前已经具备：

1. 区域级扩散与反馈推演
2. 区域内部的多 agent 关系与动作更新
3. 风险对象、报告、结果分析与节点探索

下一阶段不再把“跨区域作用”主要压缩为单一 diffusion，而是引入：

- 可动态长出的跨区 agent 关系
- 多层网络并行运行
- 可解释的默认投影视图

核心判断：

- `动态长边` 必须是产品理念核心，不应假设系统可以穷举所有关系模板
- 但 `动态长边` 不能等于 `所有 agent 在全图无约束自由连边`
- 终局应是 `高拟真引擎 + 可解释沙盘投影`

## 2. 当前系统的真实形态

### 2.1 当前分层

当前引擎实际上已经是一个简化的双层系统：

- `区域内 agent 关系层`
  - 关系主要按 `home_subregion_id` 在局部生成
  - 常见边为：
    - `human -> governance / organization`
    - `human -> ecology / carrier`
    - `organization / governance -> ecology`
    - 少量 `human -> human community_link`
- `区域级扩散层`
  - 跨区域压力传播主要由 region diffusion 负责
  - 扩散被限制为 `self or neighbor`
  - 不允许 teleporting spread

### 2.2 当前简化的优点

- 可解释性强
- 计算量稳定
- 适合快速生成报告与结果页
- 可以让区域态势、反馈链和角色透镜在 UI 中保持清晰

### 2.3 当前简化的不足

- 跨区 agent 互动过弱
- 区域之间除主 agent/邻接外，缺少真实世界中的跨层联系
- 供应链、治理协同、通勤/流动、媒体传播、生态廊道等关系被压扁进 region diffusion
- “谁影响了谁”与“什么通过场扩散影响了谁”没有被明确分层表达

## 3. 终局产品形态

终局不建议二选一：

- 不是纯可解释沙盘
- 也不是无约束复杂系统

建议终局为：

- `引擎层` 偏高拟真复杂系统
- `交互层 / 报告层` 偏可解释沙盘

即：

- 底层允许多层网络、动态边、跨区关系与时序涌现
- 面向用户的默认视图必须仍能回答：
  - 为什么出现这条关系
  - 这条关系来自什么证据或什么轮次
  - 它是稳定结构，还是临时涌现
  - 它对哪些状态变化产生了贡献

## 4. 目标架构：五层并行系统

### 4.1 Field Diffusion Layer

处理连续场、载体和扩散：

- 水体 / 洋流 / 空气 / 土壤 / 生物载体
- 污染、营养盐、生态压力、热浪、烟羽等

特点：

- 以 region / subregion 为主要计算单元
- 适合表达“场”和“流”
- 不负责解释全部社会关系

### 4.2 Structural Network Layer

处理相对稳定的跨区结构边：

- 供应链
- 通勤 / 人流
- 治理协同
- 媒体传播
- 产业依赖
- 生态廊道
- 基础设施联动

特点：

- 可以来自规则、数据、已有图谱、LLM 初始推断
- 属于较稳定的“底图”
- 是动态长边的候选路由基础

### 4.3 Dynamic Edge Layer

处理在仿真运行中动态出现的新关系：

- 新协作
- 新冲突
- 临时信息通道
- 新的治理协调链
- 新的跨区供应或替代链
- 新的舆论放大链

特点：

- 由 LLM 在运行过程中决策生成
- 但必须经过候选路由和约束验证
- 具备生命周期，不默认永久存在

### 4.4 Agent Interaction Layer

处理 agent 在每轮中的离散动作：

- 选择行动
- 选择目标
- 写入交互记录
- 更新局部状态
- 激发或衰减边

特点：

- 依赖结构边与动态边提供可交互路由
- 不直接在全图无约束搜索目标

### 4.5 Region State Layer

处理聚合结果：

- region / subregion 状态向量
- 风险对象
- 报告指标
- 结果分析卡片

特点：

- 是上面几层共同作用后的聚合投影
- 不再是唯一桥梁

## 5. 关键原则

### 5.1 放权给 LLM，但不是裸放权

应允许 LLM 在运行中长出新边。

不应允许：

- 任意跨全图搜索
- 永久保留所有新边
- 不记录证据与理由
- 不区分稳定边和临时边

正确方式是：

1. 系统先给出候选路由
2. LLM 在候选中判断是否需要长新边
3. 系统验证、写入、衰减、淘汰

### 5.2 边必须有来源

每条边都必须可解释，至少带：

- 来源类型
- 创建轮次
- 创建理由
- 触发证据
- 生命周期参数

### 5.3 边必须会死亡

动态边如果只增不减，图最终会失控。

因此动态边必须支持：

- TTL
- decay
- inactive aging
- repeated confirmation
- merge / consolidate

### 5.4 默认视图必须可读

多层网络可以复杂，但前端默认不能直接把所有边平铺给用户。

默认视图必须：

- 强调关键跨区桥
- 能切换不同 layer
- 支持按时间过滤
- 能区分 `结构边` 和 `涌现边`

## 6. 动态边 Schema

建议新增统一结构 `SimulationEdge`，覆盖稳定边与动态边。

```json
{
  "edge_id": "edge_xxx",
  "source_agent_id": 11,
  "target_agent_id": 78,
  "source_region_id": "A",
  "target_region_id": "B",
  "edge_type": "governance_coordination",
  "layer": "dynamic",
  "origin": "llm_emergent",
  "scope": "cross_region",
  "directionality": "directed",
  "strength": 0.72,
  "confidence": 0.68,
  "ttl_rounds": 3,
  "decay_per_round": 0.18,
  "created_round": 5,
  "last_activated_round": 6,
  "expires_after_round": 8,
  "status": "active",
  "routing_basis": [
    "shared_risk_object",
    "neighbor_region",
    "governance_escalation"
  ],
  "evidence": {
    "risk_object_ids": ["risk_eco_social_cascade"],
    "event_refs": ["interaction_ledger:124"],
    "state_signals": {
      "source_region_panic": 61.2,
      "target_region_trust": 42.8
    }
  },
  "rationale": "源区域监管主体因共享风险对象与相邻区域服务压力，向目标区域发起协同处置。",
  "activation_effects": {
    "target_delta_hint": {
      "response_capacity": 0.8,
      "public_trust": 0.3
    },
    "region_delta_hint": {
      "service_capacity": 0.4
    }
  }
}
```

### 6.1 字段约束

- `layer`
  - `structural`
  - `dynamic`
  - `diffusion_bridge`
- `origin`
  - `seed_rule`
  - `seed_llm`
  - `runtime_llm`
  - `runtime_promoted`
- `scope`
  - `intra_subregion`
  - `intra_region`
  - `cross_region`
- `status`
  - `active`
  - `cooling`
  - `expired`
  - `promoted`

### 6.2 稳定边与动态边的区别

- 稳定边：
  - TTL 可为空
  - 默认长期存在
  - 来自 seed 结构
- 动态边：
  - 必须有 `created_round`
  - 必须有 `ttl_rounds`
  - 必须有 `routing_basis`
  - 必须有 `rationale`

## 7. 候选路由系统

### 7.1 为什么必须有候选路由

如果不做候选路由，所有 agent 跨区自由找目标将导致：

- 候选对数量接近 `O(N^2)`
- LLM 判断成本暴涨
- 网络迅速高连通
- 难以解释和验证

候选路由的作用不是替 LLM 穷举关系模板，而是把搜索空间压缩到“合理可达”的范围。

### 7.2 候选来源

第一版建议支持以下 route source：

- `neighbor_region`
  - 相邻区域或相邻子区域
- `shared_risk_object`
  - 共同被同一 risk object 命中
- `shared_supply_chain`
  - 同一产业链上游 / 下游
- `mobility_corridor`
  - 人流 / 物流 / 通勤通道
- `governance_hierarchy`
  - 监管层级、属地协同、跨区联席
- `media_reach`
  - 媒体、平台、意见节点的覆盖范围
- `ecological_corridor`
  - 水系、栖息地、迁徙带、生态缓冲联系
- `shared_event_memory`
  - 最近几轮被同一事件或同一 turning point 同时激活

### 7.3 候选路由构造方式

每轮为每个 active agent 构造候选池：

1. 本地边
2. 结构层直接邻居
3. 共享 risk object 的跨区节点
4. 与其 `influenced_regions` 重合的边界角色
5. 最近两轮与其状态联动显著的异区节点

### 7.4 第一版预算建议

每个 active agent 每轮只允许进入有限候选池：

- `local_candidates <= 8`
- `cross_region_candidates <= 6`
- `new_edge_proposals <= 2`

这不是最终上限，而是第一版防爆参数。

## 8. 动态长边生命周期

### 8.1 生命周期阶段

动态边建议分四段：

1. `proposed`
   - 本轮由 LLM 提出
2. `active`
   - 已通过验证并进入交互图
3. `cooling`
   - 一段时间未被激活，强度衰减
4. `expired`
   - 超出 TTL 或长期无激活而移除

### 8.2 边生成流程

每轮流程建议为：

1. 选 active agents
2. 构造候选池
3. 让 LLM 在候选池中输出：
   - 是否建立新边
   - 边类型
   - 方向
   - 强度
   - TTL
   - 理由
4. 系统做硬验证
5. 写入边表
6. 参与本轮或下一轮互动

### 8.3 系统验证规则

建议第一版硬约束：

- 不允许 source == target
- 不允许目标不在候选池
- `strength` 必须在 `[0,1]`
- `ttl_rounds` 必须在 `[1,5]`
- 同类型重复边先 merge，不盲目新增
- 若缺少 evidence，则不落盘，只记为 rejected proposal

### 8.4 边晋升机制

如果一条动态边连续多轮被激活，可晋升为半稳定边：

- 条件示例：
  - `reconfirm_count >= 3`
  - `average_confidence >= 0.7`
  - `average_strength >= 0.6`

晋升后：

- `origin = runtime_promoted`
- `layer = structural`
- 不再受短 TTL 约束
- 但仍可继续衰减或被删除

## 9. 为什么不能直接“所有 agent 无限制跨区”

### 9.1 计算问题

即使不调用 LLM，全图搜索的目标选择成本也会上升。

当前引擎是：

- 每轮只激活部分 agent
- 每个 agent 从已有稀疏出边里选目标

改成自由跨区后：

- 目标候选会从稀疏邻居变成全图
- 需要更多排序、过滤、匹配、记忆计算

### 9.2 LLM 成本问题

真正昂贵的是让 LLM 决定：

- 哪些边该出现
- 为什么该出现
- 边有多强
- 能活多久

如果全图自由搜索，这一层成本会失控。

### 9.3 系统稳定性问题

不受限的动态生边会造成：

- 网络过快高连通
- 几乎所有节点都能互相影响
- 区域边界失去意义
- diffusion 与 agent interaction 混成一团

### 9.4 解释性问题

最终用户会问：

- 这轮变化主要是扩散造成的，还是跨区协调造成的？
- 这条边为什么出现？
- 这条边为何只出现两轮？

如果没有 route basis、TTL 和 evidence，这些问题回答不了。

## 10. 解释层与前端投影

终局 UI 不能直接把所有 layer 平铺为一个 force graph。

建议默认提供四种投影：

### 10.1 Default Explain View

默认展示：

- 稳定结构边
- 当前轮活跃的关键动态边
- 关键 diffusion bridge

隐藏：

- 低强度边
- 即将过期但无影响边
- 重复局部社区边

### 10.2 Layer View

支持按 layer 切换：

- diffusion
- structural
- dynamic
- full

### 10.3 Cross-Region Bridge View

专门展示：

- 哪些 agent 在跨区承担桥接作用
- 哪些 risk object 正在连接多个区块
- 哪些边是本轮新增

### 10.4 Time Playback View

支持：

- 边的出现、增强、衰减、消亡
- 新边与区域状态变化的对照

## 11. 三阶段实施路线

### Phase 1：可控跨区候选 + 动态短命边

目标：

- 在不推翻现有引擎的前提下引入最小闭环

做什么：

- 新增统一 edge schema
- 增加 `structural route candidates`
- 每轮允许少量 `runtime_llm` 跨区新边
- 给新边加 `ttl / decay / evidence / rationale`
- 结果分析页区分 `stable vs emergent`

先不做：

- 全图自由找目标
- 大规模多跳跨区搜索
- 自动长期记忆沉淀

### Phase 2：多层网络并行运行

目标：

- 让 diffusion、structural、dynamic 三层真正并行

做什么：

- 把 cross-region interaction 从 region diffusion 中拆出来
- 支持 shared risk / supply / governance / media route
- 引入 edge promotion
- 支持跨层归因

### Phase 3：高拟真引擎 + 可解释投影

目标：

- 形成终局产品能力

做什么：

- 动态路由学习
- 结构边与动态图联合记忆
- 前端多视图投影
- 对报告和节点探索提供“边的生成史”

## 12. 第一阶段建议落点

如果只做一个最有价值的第一步，建议优先落：

- `跨区候选路由 + 动态短命边`

原因：

- 这是“放权给 LLM”的最小闭环
- 不需要马上重写 diffusion 层
- 可以直接改善当前图谱里“区块割裂”的问题
- 同时还能保住现有结果页和报告页的解释性

## 13. 第一阶段具体改动建议

建议涉及以下模块：

- `backend/app/services/envfish_models.py`
  - 新增统一 edge model
- `backend/app/services/env_profile_generator.py`
  - 增加跨区 structural route seed
- `backend/scripts/run_envfish_simulation.py`
  - 增加 candidate routing
  - 增加 runtime edge proposal / validation / ttl decay
- `backend/app/services/report_analysis.py`
  - 区分结构边和动态边
- `frontend/src/components/GraphPanel.vue`
  - 增加 layer 过滤与 emergent 标记

## 14. 需要先定死的决策

在开始第一阶段编码前，建议锁定以下默认值：

- 每个 active agent 每轮最多新增几条跨区边
  - 建议默认 `2`
- 动态边 TTL 默认多少轮
  - 建议默认 `3`
- 哪些 route source 第一版必须上线
  - 建议：
    - `neighbor_region`
    - `shared_risk_object`
    - `governance_hierarchy`
    - `media_reach`
- 哪些边可以晋升为结构边
  - 建议第一版只允许：
    - `governance_coordination`
    - `market_link`
    - `media_link`
    - `ecology_corridor_signal`

## 15. 最终结论

EnvFish 的终局不应是：

- 只靠 diffusion 管跨区
- 或让所有 agent 无约束跨区自由连边

EnvFish 的终局应是：

- `diffusion layer` 处理场和载体
- `structural layer` 处理稳定跨区结构
- `dynamic layer` 让 LLM 在运行中长出新边
- `interaction layer` 沿候选路由产生离散互动
- `explain layer` 将复杂引擎投影为用户可读的沙盘

一句话总结：

> 终局应是“高拟真引擎 + 可解释投影”，动态长边是核心能力，但必须建立在候选路由、生命周期和多层解释之上。
