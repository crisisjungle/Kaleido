# Map-First 实景图谱方案

## 1. 目标

Envfish 新增一条 `map-first` 输入链路，使用户在第一步不再必须上传材料，而是直接：

1. 在地图上选点
2. 设定分析半径
3. 触发周边空间数据、遥感数据、开放生态数据采集
4. 自动生成带空间锚点的实景图谱
5. 在地图视图与纯图谱视图之间切换
6. 将生成结果接入现有 Envfish 环境搭建、模拟、报告流程

核心原则：

- 地图负责提供空间锚点和可观测事实
- 遥感和开放数据负责识别地表、设施、生态载体和环境基线
- LLM 负责结构化归纳、代理节点推断、关系补全和报告组织
- 系统必须明确区分“观测到的事实”和“推断出的节点/边”

## 2. 不做什么

第一版不承诺以下能力：

- 仅凭单时相卫星图还原真实现场全部社会关系
- 自动识别具体物种组成或污染责任主体
- 自动替代现场调查、监测报告和政策文本
- 对所有空间类型做同等精度的识别和推断

说明：

- 用户层面不需要手动选择“地点类型”
- 但系统内部必须自动判别场景类型并切换规则

## 3. 总体产品形态

新增两个并列入口：

- `文档模式`：保留当前上传材料流程
- `地图模式`：新增地图选点，直接生成实景图谱

统一输出一套底层图谱数据，在前端支持双视图：

- `地图实景图谱视图`
  - 节点按真实空间位置或锚点位置显示
  - 底图叠加行政区、遥感覆盖、设施分布、保护地等图层
- `纯图谱视图`
  - 节点按语义关系重排，沿用当前 D3 图谱交互逻辑

两种视图共享同一套节点、边、证据与风险对象数据。

## 4. 现有系统的接入原则

当前 Envfish 主链路是：

1. 上传文档
2. 构建图谱
3. 创建 simulation
4. prepare simulation
5. 进入推演

新增 `map-first` 后，不推翻现有后端，而是在它前面增加一层“地图种子构建”：

1. 地图选点
2. 空间数据采集与遥感分析
3. 生成地图种子图谱 `map_seed_graph`
4. 输出标准化节点、边、区域、环境基线报告
5. 将该结果转成当前 Envfish 可消费的 graph / region / config 输入
6. 后续继续走现有 Step 2-5

换句话说：

- 地图模式不是绕开当前引擎
- 地图模式是自动帮当前引擎先造出一套更强的 seed

## 5. 核心数据分层

### 5.1 节点分层

所有节点必须带 `source_kind`：

- `observed`
  - 直接来自公开空间数据或结构化开放数据
  - 例：河流、水体、湿地、道路、港口、工业区、保护地
- `detected`
  - 来自遥感影像规则或模型识别
  - 例：疑似养殖塘、岸线扰动带、连片建成区、浑浊水体区
- `inferred`
  - 来自 LLM 或规则推断
  - 例：沿岸居民群体、渔民群体、监管主体、游客群体

### 5.2 人类代理节点粒度

第一版采用“中粒度代理节点”，避免过粗也避免伪精确：

- 居民群体
- 生产者/经营者
- 游客/访客
- 监管主体
- 维护/治理主体
- 脆弱群体

每个代理节点都必须有：

- 一个空间锚点
- 一个推断理由
- 一个证据集合
- 一个置信度

### 5.3 边分层

每条边必须带 `relation_origin`：

- `observed_relation`
  - 直接来自空间共现、上下游、相邻、包含、覆盖等事实
- `rule_based_relation`
  - 由规则引擎生成
  - 例：湿地邻接水体，港口连接航运设施
- `llm_inferred_relation`
  - 由 LLM 基于空间事实补全
  - 例：游客压力影响岸线公共空间，居民依赖近岸水体

## 6. 推荐数据源与优先级

优先选用免费或低门槛方案，按“全球通用 + 中国优先增强”组合。

### 6.1 地图与行政区

- 中国优先：天地图
  - 逆地理编码
  - 行政区划
  - 底图与边界补充
- 全球备用：Nominatim
  - 仅作低频查询
  - 必须走缓存，避免违反公开服务限制

### 6.2 设施、水系、道路、兴趣点

- OSM + Overpass API
  - 水系
  - 道路
  - 港口、码头
  - 工业设施
  - 污水处理设施
  - 居住区
  - 旅游和公共设施

### 6.3 地表覆盖与生态载体

- ESA WorldCover
  - 全球 10m 地表覆盖
  - 作为第一版最重要的“生态底图”

### 6.4 遥感影像与指数计算

- Copernicus Data Space
  - Sentinel-2 影像
  - STAC 检索
  - openEO 计算 NDVI、NDWI 等指数

不将 Earth Engine 作为第一版主依赖，原因：

- 接入鉴权和部署复杂度更高
- 与“免费优先、快速落地”目标不完全一致

### 6.5 环境基线

- Open-Meteo
  - 天气、历史天气、海洋天气、空气质量等快速基线

### 6.6 生态与保护地补充

- GBIF
  - 生物多样性发生记录
- Protected Planet v4
  - 保护地边界和属性

### 6.7 后续可扩展数据

- 中国气象数据网
- 中国本地生态监测开放平台
- 高德或商业 POI 服务
- 本地 DEM/河网矢量数据

## 7. Map-First 后端总体架构

新增一条后端链路：

### 7.1 输入

输入参数：

- `lat`
- `lon`
- `radius_m`
- `analysis_preset` 可选
- `time_window` 可选

### 7.2 处理管线

#### Stage A: 地点解析

目标：

- 解析行政区
- 生成分析范围 polygon
- 计算不同尺度 ring

产物：

- `area_of_interest`
- `admin_context`
- `analysis_bbox`

#### Stage B: 空间数据采集

采集：

- OSM 设施和自然要素
- 行政区与保护地
- 气象和环境基线
- 可用的生物多样性记录

产物：

- `raw_spatial_features.json`
- `environment_baseline.json`

#### Stage C: 遥感分析

处理：

- 获取云量合适的 Sentinel-2 影像
- 生成地表覆盖、植被、水体等基础指数
- 识别重点区域：
  - 水体
  - 湿地样区域
  - 连片建成区
  - 疑似养殖塘
  - 岸线带

产物：

- `remote_sensing_summary.json`
- `derived_rasters` 或 `derived_vector_features`

#### Stage D: 场景自动分类

系统内部自动推断区域主要场景：

- coastal
- inland_water
- wetland
- urban_edge
- agricultural
- mixed

说明：

- 这不是给用户增加新概念
- 这是后端内部选择规则模板所必需的步骤

#### Stage E: 节点构建

生成三类节点：

- 生态节点
- 设施节点
- 人类代理节点

规则：

- 生态节点优先来自 observed/detected
- 设施节点来自 observed/detected + 规则清洗
- 人类代理节点来自 LLM + 规则推断

#### Stage F: 关系构建

关系来源：

- 空间邻接
- 包含/覆盖
- 上下游
- 规则依赖
- LLM 补全

输出每条边：

- 证据
- 类型
- 置信度
- 是否可解释

#### Stage G: 基线报告生成

生成一份“地图种子报告”，替代初始上传文档：

- 地点概述
- 生态载体摘要
- 人类设施与活动摘要
- 代理社会主体摘要
- 风险传播路径摘要
- 不确定性说明

#### Stage H: Envfish 接入

把地图种子结果转成当前引擎需要的数据：

- 区域节点
- 角色节点
- 关系边
- 初始环境基线
- 风险对象

## 8. 建议新增后端模块

建议新增以下服务：

- `backend/app/services/map_aoi_builder.py`
  - 负责点位、半径、边界、多尺度 ring
- `backend/app/services/map_source_registry.py`
  - 管理不同数据源调用和缓存策略
- `backend/app/services/spatial_feature_collector.py`
  - OSM、行政区、保护地、POI、气象等采集
- `backend/app/services/remote_sensing_service.py`
  - Sentinel-2 检索、指数计算、影像摘要
- `backend/app/services/map_scene_classifier.py`
  - 自动判断 coastal / inland / wetland / urban 等
- `backend/app/services/map_node_builder.py`
  - 构建 observed / detected / inferred 节点
- `backend/app/services/map_edge_builder.py`
  - 构建空间边与语义边
- `backend/app/services/map_report_builder.py`
  - 生成地图种子报告
- `backend/app/services/map_graph_exporter.py`
  - 输出给现有 graph/simulation 管线

建议新增 API：

- `POST /api/map/seed`
  - 提交地图选点任务
- `POST /api/map/seed/status`
  - 查询任务进度
- `GET /api/map/seed/<seed_id>`
  - 获取地图种子结果
- `GET /api/map/seed/<seed_id>/layers`
  - 获取图层和矢量数据
- `POST /api/map/seed/<seed_id>/to-simulation`
  - 转换为 simulation 并进入现有流程

## 9. 建议新增前端模块

当前前端只有 D3，没有地图 SDK。建议新增地图层能力，但保留当前图谱视图。

### 9.1 首页新增地图模式

首页新增输入切换：

- `文档上传`
- `地图选点`

地图模式只要求：

- 点选位置
- 设置分析半径
- 发起地图建模

### 9.2 新增地图工作台

建议新增：

- `frontend/src/views/MapSeedView.vue`
- `frontend/src/components/MapCanvas.vue`
- `frontend/src/components/MapLayerPanel.vue`
- `frontend/src/components/MapGraphInspector.vue`

### 9.3 双视图切换

在工作台提供：

- `实景图谱`
- `纯图谱`

共享一套数据：

- 地图视图读取 `geometry` / `anchor_point`
- 纯图谱视图沿用当前 D3 force 布局

### 9.4 节点与图层联动

地图上点击节点时：

- 高亮对应边
- 展示证据卡片
- 同步高亮纯图谱中的对应节点

纯图谱点击节点时：

- 地图自动定位到对应节点锚点或几何范围

## 10. 节点与边的统一 Schema

### 10.1 节点

```json
{
  "id": "node_xxx",
  "name": "近岸湿地",
  "category": "ecology|facility|human_proxy|region|risk",
  "subtype": "wetland",
  "source_kind": "observed|detected|inferred",
  "confidence": 0.82,
  "geometry": {
    "type": "Point|Polygon|MultiPolygon",
    "coordinates": []
  },
  "anchor_point": {
    "lat": 0,
    "lon": 0
  },
  "properties": {},
  "evidence": [
    {
      "source": "worldcover",
      "type": "landcover",
      "summary": "Detected wetland-adjacent land cover patch",
      "confidence": 0.84,
      "timestamp": "2026-03-31T00:00:00Z"
    }
  ]
}
```

### 10.2 边

```json
{
  "id": "edge_xxx",
  "source": "node_a",
  "target": "node_b",
  "relation": "adjacent_to|depends_on|regulates|affects|flows_to|uses",
  "relation_origin": "observed_relation|rule_based_relation|llm_inferred_relation",
  "confidence": 0.76,
  "evidence": [
    {
      "source": "osm",
      "summary": "Facility located within 300m of shoreline",
      "confidence": 0.88
    }
  ]
}
```

## 11. LLM 的职责边界

LLM 只做以下事情：

- 将多源事实整理成结构化节点候选
- 在规则约束下生成代理人类节点
- 补全部分语义关系
- 生成地图基线报告
- 输出不确定性说明

LLM 不直接做以下事情：

- 凭空发明高置信度空间对象
- 伪造不存在的设施或保护地
- 将 inferred 节点冒充 observed 节点

所有 LLM 输出必须受约束：

- 输入带原始证据摘要
- 输出 schema 固定
- 置信度必须与证据数量和证据类型挂钩
- 对无证据项强制降置信度

## 12. 风险与限制

### 12.1 识别精度风险

- 卫星图能识别地表和空间设施
- 不能直接识别社会角色
- 部分生态节点只能做代理识别

### 12.2 时效性风险

- 不同数据源更新时间不同
- 遥感影像受云层、潮位、季节影响
- 地图和 POI 数据可能滞后

### 12.3 公开接口风险

- Nominatim 不适合高频生产流量
- 部分接口需要 token
- 不同服务存在速率和并发限制

### 12.4 幻觉风险

- LLM 推断节点和边时若无强约束，会快速偏离真实空间事实
- 因此必须把“证据优先”写进系统规则

## 13. 分阶段落地计划

### Phase 0: 数据模型与双视图底座

目标：

- 定义统一 schema
- 打通地图视图和纯图谱视图共享同一数据

产出：

- 统一 node/edge/evidence schema
- 图谱视图支持 geo anchor

### Phase 1: Map-First MVP

目标：

- 地图选点
- OSM + 行政区 + WorldCover + Open-Meteo
- 生成基础生态节点、设施节点、代理人类节点
- 地图视图与纯图谱视图切换

第一版只保证：

- 可生成“地图基线图谱”
- 可进入现有 simulation 流程

### Phase 2: 遥感增强

目标：

- 接入 Copernicus Data Space
- 使用 Sentinel-2 做指数和重点区识别
- 提升生态节点质量

### Phase 3: 风险传播增强

目标：

- 结合现有 risk object builder
- 自动生成更贴合空间结构的风险对象
- 增强地图上风险传播路径展示

### Phase 4: 人工校正与再训练

目标：

- 允许用户修正节点、锚点、边和类型
- 将修正后的图谱再送入模拟

## 14. 第一批工程任务建议

按优先级建议先做：

1. 定义统一地图图谱 schema
2. 新增 `map_seed` 后端任务模型和状态查询接口
3. 接入天地图或全局 geocoder，完成点位解析
4. 接入 OSM/Overpass，完成基础设施和自然要素采集
5. 接入 WorldCover，完成基础生态分类层
6. 生成第一版 observed/detected/inferred 节点
7. 前端新增地图模式入口和地图视图
8. 实现地图图谱与纯图谱切换
9. 接入现有 simulation create / prepare 流程
10. 再追加 Copernicus 遥感增强

## 15. 最终判断

这个方案可以做，而且适合 Envfish。

但它的正确实现方式不是：

- “卫星图直接识别一切，然后 LLM 顺手补充”

而是：

- “空间数据和遥感先建立可解释事实层”
- “LLM 在事实层之上构建代理节点和语义关系”
- “地图视图和纯图谱视图共享同一套有证据的图谱底层”

只要坚持这一点，`map-first` 不会把当前系统推翻，而会成为当前 Envfish 最强的上游入口。
