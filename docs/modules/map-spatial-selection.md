# 地图空间识别与选点稳定逻辑

## 目标与适用范围

地图上的圆只定义分析范围（AOI），不等于“圈内所有地点都重要”，也不等于“离圆心最近的点就是中心对象”。本模块负责把用户意图、空间范围和不同质量的数据源收敛为一组数量有限、可解释、可复现的地图种子节点。该结果会继续影响区域/子区域划分、Agent 生成与落点、风险对象以及后续推演，因此 Step 1 的选点是整个流程的数据契约，不是单纯的地图装饰。

稳定的含义包括：

- 同一输入、同一候选集得到确定性结果；
- 用户明确点名的地点优先于圆心距离和数据密度；
- 用户未指定焦点时，不让 OSM 数据更密集的一侧垄断名额；
- 公网数据失败时返回明确的“不可用”和诊断原因，不把参考结果伪装成已完成；
- 推断节点和合成坐标不能冒充真实地理落点。

## 核心判断顺序

系统按以下顺序判断“选哪些、哪些是重点”：

1. 读取用户输入，包括 `requested_location`、标题、推演要求、`focus_text`、已知实体、分析边界和焦点模式。
2. 识别用户直接点名的城市、区县、街道、海湾、河流、湿地、医院、学校、港口等地点，并与候选名称、行政前缀和地址标签匹配；常见行政简称会规范化，例如“深圳”匹配“深圳市”。“就想/重点/优先”所在子句加权，“画到/覆盖到/不扩展”所在子句不作为焦点。
3. 根据半径确定默认空间粒度，过滤与该尺度不相称的细碎候选。
4. 对候选计算综合分数：用户焦点、场景机制相关性、来源质量、重要度、置信度和与圆心的相对距离共同参与，距离不是唯一标准。
5. 用户明确点名时，命中的候选先进入最终集合；即使它比另一个城市的候选更远，也不能被近距离高密度点挤掉。
   - 城市简称只限定焦点城市，不等于直接点名该城市的所有 POI。
   - 若数据源缺少焦点城市的宏观行政节点，只从该城市的正焦点 POI 中按类别、方向和子类型最多保留 6 个代表，并剔除“画到/覆盖到/不扩展”的负焦点城市；不得用 28 个同城 POI 填满名额。
6. 用户没有明确焦点时，先覆盖中心及八方向空间扇区，再补齐生态、设施、行政等语义类别，最后才按边际分数补满名额；重复子类型会受到递减惩罚。
7. 将最终选择及原因写入 `selection_summary`，保留焦点词、粒度、各方向/类别/来源计数、`focus_resolution` 和每个节点的 `selection_score`、`selection_reasons`，供界面解释与回归测试。`focus_resolution=representative_fallback` 表示缺少焦点宏观边界而启用了受限代表点；`unresolved` 表示没有足够候选可支持用户焦点。

这套顺序解决的是“用户画到了广州和深圳，但文本重点是深圳”的问题：圆负责限定可分析范围，文本负责决定范围内的注意力。若文本没有给出重点，系统才采用空间与类别均衡策略，不能把某一侧的 POI 密度当成用户意图。

## 半径与默认粒度

| 分析半径 | 默认粒度 | 默认选择倾向 |
| --- | --- | --- |
| `0–3 km` | `site_street` | 具体场所、社区、道路、街道级节点 |
| `3–15 km` | `street_district` | 街道与区级骨架，保留有意义的场所 |
| `15–30 km` | `district` | 区县和区域性生态/设施节点 |
| `>30 km` | `city_region` | 城市、区县、区域和宏观廊道 |

当半径超过 30 km 时，未被用户点名的街道和单体场所默认不参与最终选择，避免 50 km 范围内出现几十个零散街道/POI。用户若明确点名“深圳湾湿地”“凤凰实验学校”等具体场所，该地点可以穿透宏观粒度限制，作为焦点优先保留。

粒度是默认筛选尺度，不是行政级别的硬编码答案。生态对象可在大范围内以海岸、河流、湿地或保护区等区域载体参与；单体设施则需要明确焦点或更小半径。

## 候选收集与最终选择必须分离

`MapSeedManager` 负责尽量收集较大的候选池，`map_spatial_selection.py` 负责从候选池中做确定性收敛。两者不能重新合并成“数据源返回什么就直接画什么”的逻辑。

候选池当前包含：

- Overpass/OSM 的自然、水系、土地利用、关键公共设施、交通、保护区和行政边界；
- WorldCover WMS 派生的地表覆盖斑块，仅作为背景分类上下文；
- 逆地理编码产生的行政上下文锚点；
- 环境/天气基线；
- 武汉金标夹具或本地地名表等版本化参考数据。

候选合并后先去重，再过滤到 AOI；随后才做焦点识别、尺度过滤、评分、方向/类别覆盖和数量限制。这样，数据收集可以为了召回率扩大，最终图谱仍保持有限、均衡和可解释。

大范围 Overpass 查询使用 `named_macro` 配置：先通过 `is_in` 获取中心点所在行政边界，再用一批有上限的区域边界查询补充周边城市/保护区；不再用一个大 `nwr around` 联合查询扫描圆内所有 POI。较小范围使用 `named_local` 配置，按行政、水生态、设施、交通四个主题分批，并对中等半径的细粒度查询设置采样半径上限。不要通过无差别增加查询标签来修复“缺点”，这会放大公共实例的资源压力和区域数据密度偏差。

## Overpass 与 WorldCover 的稳定性和降级

### Overpass

公共 Overpass 实例资源有限，会按负载调度请求。大半径 `around` 查询、过宽标签集合、大量关系/几何和较大的 `timeout`/`maxsize` 都可能导致网关 504、服务端拒绝、排队超时或客户端 HTTP 超时。504 通常意味着请求与当时可用资源不匹配，不代表 AOI 内没有 OSM 数据。

当前稳定措施：

- 大范围先查中心点所属行政边界，再查有限的区域边界，避免一次大联合查询触发内存上限；小范围按主题分批；
- 查询超时和 HTTP 超时分别由 `OVERPASS_QUERY_TIMEOUT_SECONDS`、`OVERPASS_HTTP_TIMEOUT_SECONDS` 控制；
- 查询声明内存由 `OVERPASS_MAXSIZE_BYTES` 控制，默认 64 MiB；提高声明不能替代拆小查询；
- `OVERPASS_ENDPOINTS` 支持多个端点，默认逐个尝试，也允许生产环境切换到受控或自托管实例；
- 每个主题批次分别记录端点、耗时、错误、原始要素数和批次状态，不再只留下一个模糊的“失败”；
- 同位置、近似半径和相同查询配置的 7 天内缓存优先返回，避免每次重复冲击公共实例；无缓存才发起现场请求；
- 公共端点失败且无缓存时，地图种子状态必须为 `unavailable`，不能把参考数据记为成功。

面向持续生产负载，稳定性的最终解法仍是受控/自托管 Overpass 或预构建区域索引，而不是无限增加公共镜像和重试次数。Overpass 官方也明确说明公共实例是有限共享资源，应用或重负载应考虑自己的实例：[Overpass API Commons](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html)。

### WorldCover

当前接入的是 WorldCover WMS `GetMap`。它可能因上游连接关闭、超时、服务波动或返回非预期图像而失败；当前优先读取缓存，无缓存时按 `WORLDCOVER_WMS_TIMEOUT_SECONDS` 和 `WORLDCOVER_WMS_ATTEMPTS` 做有上限的短请求（默认 10 秒、1 次）。缓存仍不可用时，遥感层为空并保留明确错误；由于 WMS 仅为上下文，它的失败不阻断已经由 OSM 正式证据支持的结果。

2026-07-13 排查确认，旧默认契约 `services.terrascope.be/wms/v2 + WMS 1.1.1 + WORLDCOVER_2021_MAP + 2021-12-31` 已不符合 ESA 当前数据访问页指向的服务。现在默认改为 `https://titiler.terrascope.be/wms` / WMS `1.3.0` / `esa-worldcover-map-10m-2021-v2_map` / `2021-01-01`，并将 URL、版本、图层和时间都暴露为环境配置。这修复了“请求本身已过期”的可用性问题，但不改变 WMS 的证据等级。

更重要的是，WMS 返回的是用于制图显示的 RGB 图像，不是适合数值分析的原始分类栅格。因此即使请求成功，当前 WMS 节点也标记为 `contextual_only`，不能单独把一次地图种子判定为正式空间事实。ESA 官方建议分析场景使用 Cloud Optimized GeoTIFF（COG）数据：[WorldCover Data Access](https://esa-worldcover.org/en/data-access)。后续若需要可审计的地表覆盖面积、类别边界和变化判断，应迁移到 COG/自托管栅格读取，并将 provider 标记为 `worldcover_cog`，不能继续对 WMS 像素颜色赋予分析级含义。

### 缓存规则

公网空间缓存按 provider、经纬度约 0.001° 桶、500 m 半径桶和查询配置生成键。默认 TTL 为 7 天，由 `MAP_SOURCE_CACHE_TTL_SECONDS` 调整。缓存命中返回 `status=cached`、缓存年龄、原始采集诊断、cache key 和 `cache_policy=fresh_cache_first`，便于区分“实时成功”与“使用了历史结果”。缓存提高可用性，但不能消除数据陈旧风险。

## 数据来源与证据语义

`source_kind` 表达节点如何产生；provider 质量表达它是否足以支持正式空间判断。两者不能混为一谈。

| `source_kind` | 语义 | 可否当作本轮真实落点 |
| --- | --- | --- |
| `observed` | 从结构化来源直接取得的地点/设施/行政/环境节点 | 视 provider 而定；OSM 可作为公开空间观测，逆地理和天气只算上下文 |
| `detected` | 从遥感或图像分类识别的斑块 | 视产品和分析等级而定；当前 WorldCover WMS 只是上下文 |
| `reference` | 本地地名表、金标夹具或静态参考点 | 只能用于补充召回、命名和降级，不计作本轮公网观测 |
| `inferred` | 根据规则或 LLM 推导的群体、治理主体或关系节点 | 不是实地调查结果；只有锚定到合格空间证据时才有近似位置 |

因此，“节点显示在地图上”不等于“已经证实”。前端和报告必须分层显示公开空间要素、遥感上下文、参考地名和推断代理节点。`reference` 应使用弱化样式；合成位置应标记为非地理落点。

## 数据质量状态与正式可用条件

`data_quality` 至少包含 provider 状态、各 provider 特征数、公开观测数、上下文数、参考/降级数、告警和 `formal_ready`。

- `complete`：Overpass 可用、分析级 WorldCover 可用且存在公开空间观测。当前 WMS 不是分析级，因此在迁移到 COG 前通常不能达到这一完整条件。
- `partial`：最终入选骨架已有公开正式观测，但某个辅助来源或类别仍不足；结果可以进入正式流程，同时必须展示缺失来源。
- `unavailable`：最终入选骨架没有公开正式观测；即使仍有逆地理、天气、WMS 背景或本地参考点，也不能称为已完成。
- `formal_ready=true`：最终入选的空间骨架中至少存在公开分析级空间观测，且当前查询策略要求的所有 Overpass 类别/批次均已完整执行；仅仅出现一个行政区或某个公开节点、或只有部分批次返回，都不能让结果变成正式可用。
- `formal_ready=false`：地图种子最终状态为 `unavailable`，仅保存诊断图层/报告用于排错；不得把结果描述成“已完成公开地理与卫星事实识别”，也不得让参考地名或天气中心点伪装成正式证据。

地图种子采用二元门槛：只有 `status=ready && data_quality.formal_ready=true` 才可进入正式推演；否则统一为 `status=unavailable`。异步任务不会把不可用结果记为 completed，而会以失败终态携带结构化 `availability`。状态接口同时返回 `available`、`retryable`、`reason_code` 和 `provider_failures`；每个 provider 失败包含是否为正式门槛、归一化原因、可否重试、原始错误、尝试和批次诊断。旧的 `status=ready/formal_ready=false` 记录在 API 层也会归一化为不可用。诊断文件仍保留，但默认图谱、图层和报告访问器不会把它们交给下游，项目创建与 seed-to-simulation 接口会硬阻断。

`formal_ready=true` 只表示已经取得合格的地点或行政空间骨架，不等于已经有足够证据判定“滨海/湿地/城市/农业/混合”等区域类型。区域类型另有 `scene_classification.classification_ready` 门槛：只统计来自正式 provider 的环境类要素，行政边界、逆地理上下文和 WorldCover WMS 背景不能把“没有类型证据”默认成“混合区域”。类型证据不足时，界面不展示区域类型卡片；这只是内部诚实性约束，不作为第三种用户状态或警告占据地图。

## “能否稳定提供”的产品结论

- 当前默认公网模式可以通过轻量查询、短重试和新鲜缓存提高成功率，但公共 Overpass 和第三方 WMS 没有 Kaleido 可控的 SLA，不能对首次查询或任意新地区承诺 100% 可用。
- 正式产品遵循 `docs/modules/result-first-output.md`：取得合格空间数据时直接展示地图与区域结果，不再额外宣告“已取得地理数据”；尚无可交付空间结果时保留用户输入，并提供“重新获取”或“调整范围”等任务动作。provider 成败、重试、不可用原因和数据源诊断保留在测试、运维与审计面，不作为正式业务结果或成功/失败标签展示。
- 若需要可承诺的生产稳定性，必须把正式链路改为受控 OSM 区域快照/自托管 Overpass 或 PostGIS 索引，并将 WorldCover COG 缓存到受控对象存储；公网服务只做后台刷新，不再位于用户关键路径。

## 区域与子区域生成规则

最终选中的空间节点才进入区域生成。区域生成器按 water、transport、industrial、ecology、urban、open 等宏观类型加权并聚类；水体进一步区分 coast、river、reservoir 和 open water，避免把海岛、河流和水库混成一个泛化“东侧湿地生态带”。

区域名称优先使用聚类中权重最高的真实命名要素；`observed` 优先于 `reference`，`reference` 又优先于仅能产生类别名的 `detected`。只有没有合格真实名称时才使用道路、城市、方向和类型组合的兜底名称。参考节点允许辅助分区，但权重低于现场公开观测，不能因为本地地名表恰好集中在深圳就让深圳一侧垄断所有区域。

子区域必须从父区域的空间与证据上下文派生。若缺少真实锚点，可以在父区域周围做确定性合成布局，但要标记为 synthetic/geographic false，不能反向写成真实地点。

## 脆弱群体与 Agent 落点约束

“脆弱群体”不是圆心默认节点，也不能锚定到天气基线。它只有在以下证据存在时才允许获得近似地点：

- 住宅、医院、学校、大学、社区中心、社会服务设施；
- 分析级 WorldCover COG built-up 证据（当前 WMS 不满足）；
- 或带有明确 `population_evidence` 的候选。

若没有合格锚点，脆弱群体仍可作为区域级推断主体存在，但经纬度为空、`spatial_precision=area_only`，不得绘制在圆心。存在合格锚点时标记为 `site_approximate`，它仍是推断群体，不是已调查的人口点。

Agent 的生成与投影遵循以下边界：

- `inferred` Agent 本身不能凭空制造人类活动证据；角色与数量由分析级 observed/detected 的环境原型和证据等级约束，reference 只可在 `formal_ready=true` 时补充命名或环境上下文，不能单独制造居民或产业证据；
- 优先解析 Agent 的 `home_subregion_id`，其次是 `home_region_id`/`primary_region`；
- 真实锚点只允许从 `formal_ready=true` 且 provider 位于公开分析级白名单的 `observed` 或 `detected` 节点中选择，`reference`、上下文、未知 provider 和其他 Agent 不能成为真实锚点；
- 子区域 Agent 的真实锚点搜索半径为 AOI 半径的 10%，限制在 0.8–3 km；区域 Agent 为 18%，限制在 1.5–6 km；
- 没有解析出的 home 节点时，不得在全 AOI 中哈希到一个任意真实点；没有合格邻域锚点时，只能在 home 区域附近生成稳定的合成坐标并标记为非地理落点；
- HumanActor、GovernmentActor、OrganizationActor 默认选择陆地/设施锚点，只有明确表示船舶、航运或海洋载体时才可落在水域。

这些约束防止“属于广州/某子区域的 Agent 被投到深圳或海岛上”，也防止多个 Agent 因全局哈希集中到数据更密的一侧。

## 可解释性与回归要求

每次地图种子构建应保留：

- `overpass_summary` 和 `remote_sensing_summary` 的每次尝试、错误、耗时、缓存状态和查询配置；
- `data_quality` 的正式可用判断和 provider 计数；
- `selection_summary` 的焦点词、粒度、候选/入选数量、方向/类别/来源覆盖；
- 节点级来源、provider、空间级别、选择分数、选择理由、锚点 ID 和空间精度。

最低回归场景包括：

- 50 km 圆同时覆盖广州和深圳，但用户明确写深圳时，深圳焦点优先；
- 没有焦点时，四象限/八方向和多个类别都有基础覆盖；
- 大半径默认排除未点名的街道/单体场所，点名后允许进入；
- Overpass 与 WorldCover 同时失败时，本地地名表只能保留为诊断，结果为 `unavailable` 且 `formal_ready=false`；
- 天气基线不能成为脆弱群体锚点；
- Agent 不能跨出其 home 区域/子区域邻域寻找真实锚点。

## 维护入口

- 选点合同、粒度、焦点和质量判断：`backend/app/services/map_spatial_selection.py`
- 候选收集、缓存、图谱、图层和报告：`backend/app/services/map_seed_manager.py`
- Provider、超时和缓存配置：`backend/app/config.py`
- 地图种子 API：`backend/app/api/map_seed.py`
- 区域/子区域与 Agent 证据生成：`backend/app/services/env_profile_generator.py`
- 地图投影与 Agent 邻域落点：`backend/app/services/simulation_map_projection.py`
- Step 1 输入传递与质量提示：`frontend/src/views/SceneComposerView.vue`
- 地图证据样式与合成位置提示：`frontend/src/components/MapRelationPanel.vue`
- 核心合同测试：`backend/tests/test_map_spatial_selection.py`、`backend/tests/test_map_seed_availability.py`、`backend/tests/test_map_agent_generation.py`、`backend/tests/test_simulation_map_projection.py`
- 数据源失败原因的中文呈现：`frontend/src/utils/mapDataQuality.js`

## 已知风险与后续工作

- 公共 Overpass 没有生产 SLA；正式环境应建设受控实例、区域镜像或离线索引。
- WorldCover WMS 只能做背景上下文；迁移 COG 前，遥感不能成为正式可用性的唯一依据。
- 当前缓存按近似位置和半径复用，提升了稳定性但可能带来最长一个 TTL 的陈旧数据；高时效灾情对象需要独立实时源。
- OSM 在不同城市和地区的标注密度、名称完整度和行政边界质量不一致；空间/类别均衡只能降低偏差，不能补齐不存在的数据。
- 中文地点抽取目前支持常见行政后缀简称、候选名称和地址标签匹配；非行政俗称、跨语言名称及“我主要看右边/靠海一侧”等相对表达仍需更强的实体解析或用户显式确认。
- 新地图种子同时记录 `skeleton_ready`、`required_category_coverage` 和兼容字段 `formal_ready`。`formal_ready` 只有在公开空间骨架存在、当前查询策略的必需批次全部完成且 Overpass 状态有效时才为真；一个行政区或任意公开节点不能再单独触发正式就绪。
- 批次完成不等于场景设施覆盖。Step 2 通过 `FacilityQueryPlan` 和 `SpatialRefinementSnapshot` 另行判断医院、核设施、监测站、避难设施等 R3/R4 需求，详见 `docs/modules/spatial-evidence-resolution.md`。
- `formal_ready=false` 已在地图种子状态、任务状态、派生文件访问器、项目创建和 seed-to-simulation 接口上硬阻断；若未来允许人工确认覆盖，必须设计独立、可审计的显式流程，不能重新复用 `ready`。
- 历史 seed 若没有 `data_quality`，一律按 `formal_ready=false/status=unknown` 处理；其既有坐标会显示为示意位置（AOI 范围节点除外），重新生成区域时只保留单一 AOI，不再沿用旧参考点聚类。
- 本次规则改变地图种子和下游空间合同。若冻结 Demo 依赖旧合同，应提升 golden artifact contract version 并刷新夹具；纯样式变化仍应留在共享组件中。

## 历史

- 2026-07-12：建立用户意图优先的确定性选点合同；拆分候选收集与最终选择；增加半径粒度、无焦点空间/类别覆盖、provider 缓存与质量门槛；区分 reference/observed/detected/inferred；收紧脆弱群体和 Agent 的空间落点。
- 2026-07-13：将地图种子收紧为 `ready`/`unavailable` 二元契约；补充 provider 失败原因和可重试信息；不可用结果禁止创建项目或进入模拟；Overpass 改为大范围行政边界轻查询、小范围主题分批、64 MiB 可配置声明和新鲜缓存优先；WorldCover WMS 迁移到官方当前 TiTiler 1.3.0 契约且继续只作上下文；行政边界和 WMS 背景不再触发伪“混合区域”判定。
