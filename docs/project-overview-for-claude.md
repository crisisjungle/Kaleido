# Kaleido 项目总览与 Claude 审阅说明

生成日期：2026-06-12  
用途：给 Claude 最新模型进行项目审阅、架构评估、产品判断和后续重构建议。

> 说明：本文以当前仓库实现为主。关于“最早从 Mirofish 获得灵感”的部分来自本次需求提供的项目背景，当前仓库内没有单独记录这一段历史；文中会将其作为项目源起描述，而不是代码证据。

## 1. 一句话概括

Kaleido 是一个面向生态、社会、治理和风险联动场景的多智能体推演系统。它把真实材料、地图空间事实、用户设定变量和大模型推理结合起来，形成一个可配置、可运行、可回放、可解释、可继续追问的“生态推演沙盘”。

当前实现不是单纯聊天应用，也不是普通数据看板，而是一个前后端分离的实验型推演工作台：

- 前端：Vue 3 + Vite 的单页应用，提供场景生成、图谱/地图联动、推演播放、结果分析、武汉冻结演示和太空碎片预测等入口。
- 后端：Flask + Python 服务，负责文件解析、图谱构建、地图种子、Agent/区域/风险对象生成、EnvFish 半定量推演、报告生成、节点分析和黄金案例恢复。
- 数据层：当前主要是文件态持久化，项目、任务、仿真、报告、地图种子、黄金案例等都落在 `backend/app/uploads` 或配置的上传目录中。
- AI 能力：使用 OpenAI SDK 兼容格式接入 LLM，支持 Qwen、DeepSeek V4 等；使用 Zep Cloud 构建或读取知识图谱。

## 2. 项目源起与演进脉络

### 2.1 Mirofish 灵感阶段

项目最早的灵感来自 Mirofish。这里的核心启发可以概括为：把复杂系统中的环境、主体、变量、反馈和扩散过程做成一个可视化、可操作、可演化的动态场，而不是把它们只写成静态报告。

Kaleido 对这个灵感做了扩展：

- 从“可视化灵感”扩展到“真实材料驱动的推演”。
- 从单一图景扩展到“图谱、地图、Agent、风险对象、时间轮次、报告和追问”的完整链路。
- 从观察系统扩展到可注入变量、可播放过程、可定位节点、可回看证据的推演工作台。

代码中仍大量保留 `envfish` 命名，例如日志名、内部引擎名、存储 key、服务文件和运行脚本。这说明项目历史上经历过 EnvFish 到 Kaleido 的品牌和产品形态转换。

### 2.2 早期 EnvFish / OASIS 社交模拟阶段

仓库中仍保留 OASIS Twitter、Reddit、双平台并行模拟脚本：

- `backend/scripts/run_twitter_simulation.py`
- `backend/scripts/run_reddit_simulation.py`
- `backend/scripts/run_parallel_simulation.py`
- `backend/scripts/action_logger.py`

但当前 `backend/pyproject.toml` 和 `backend/requirements.txt` 中 OASIS 相关依赖是注释状态，说明它们更多是历史路径或兼容遗留。当前主线已经转为 `run_envfish_simulation.py`，也就是 Kaleido 自己的区域级、半定量、生态社会耦合推演引擎。

### 2.3 Kaleido 产品化阶段

README 和首页都把项目定位为：

> 面向生态推演的多智能体环境仿真引擎。

首页已经重做为 Kaleido 控制台，入口包括：

- 开启推演流程
- 武汉疫情演示
- 太空预测
- 历史记录

README 仍描述“5 步工作流”：图谱构建、环境搭建、多轮模拟、报告生成、深度互动。当前前端实际导航更像 4 个聚合阶段：

1. 背景生成
2. 场景设计
3. 开始模拟 / 推演播放
4. 报告互动 / 结果分析

这不是矛盾，更像是产品表达从“内部工程步骤”收敛到“用户任务阶段”。

### 2.4 关键功能扩展节点

根据 `docs/modules` 现有历史记录和当前代码，可以看到几个明确节点：

1. 2026-05-21：Step 2 场景设计被拆成“参数确认”和“生成结果展示”两个阶段。用户先确认参数，之后查看风险对象、区域、Agent 和关系骨架。
2. 2026-05-21：取消用户手动选择 baseline/crisis，前端根据变量推断场景模式。
3. 2026-05-21：引入自动时间计划和 hazard template 推荐。
4. 2026-05-21：把原来的机制测试开关折叠进搜索模式，快速搜索走 `legacy_envfish_v1`，深度搜索走 `llm_mechanism_v1`。
5. 2026-05-21：风险对象从单一兼容字段扩展为多风险对象，包含作用区域、主体簇、链路步骤、转折点、证据和干预模板。
6. 2026-05-23：Step 2 地图改为共享实时投影，武汉冻结演示和正式生成流程共用同一套图谱/地图渲染路径。
7. 2026-05-23：明确武汉演示不是单独产品路径，而是正式流程的快速视觉夹具。
8. 2026-05-23：引入黄金案例 artifact contract version，正式数据契约变更时需要刷新武汉 fixture。
9. 2026-05-23：Step 3 回放改为稳定底图加聚焦脉冲，帧变化更新节点和边的状态，而不是重建整张图。
10. 2026-05-23：地图布局从模板化三角/放射状布局改为确定性地理扰动和角色感知布局。

## 3. 当前特殊功能设想

### 3.1 地图优先的场景生成

入口：`/scene-composer`  
核心文件：

- `frontend/src/views/SceneComposerView.vue`
- `frontend/src/components/LeafletMapPicker.vue`
- `backend/app/api/map_seed.py`
- `backend/app/services/map_seed_manager.py`
- `backend/app/api/scene_material.py`
- `backend/app/services/scene_material_generator.py`

用户可以输入地点或在地图上选点，设置分析半径，然后系统生成地图种子和背景素材报告。地图种子会尝试整合：

- Nominatim 正向/逆向地理编码
- Overpass / OSM 空间要素
- ESA WorldCover 2021 土地覆盖识别
- Open-Meteo 当前天气基线
- 本地 curated fallback 地理索引

这些内容会被整理成：

- 区域名称
- AOI 范围
- 空间特征节点
- 地图图层
- 环境基线
- 场景分类
- 地图种子报告

之后场景素材报告会被转成 Markdown 文件，并进入原有图谱构建和推演链路。

### 3.2 多风险对象与风险运行态

核心文件：

- `backend/app/services/risk_definition_builder.py`
- `backend/app/services/risk_projection.py`
- `backend/app/services/risk_runtime_tracker.py`
- `backend/app/services/risk_event_engine.py`
- `frontend/src/components/KaleidoStep2.vue`
- `frontend/src/components/KaleidoStep3.vue`

系统会在准备仿真时生成多个风险定义，而不是一个泛化风险标签。每个风险对象通常包含：

- `severity_score`：0-100 的场景影响分
- `confidence_score`：0-1 的依据置信度
- `actionability_score`：0-100 的可监测/可干预程度
- 作用区域
- 相关实体或 Agent
- 影响主体簇
- 风险链路步骤
- 转折点
- 证据
- 干预模板
- 场景分支

运行中还支持：

- 风险 pin
- 风险 reframe
- 变量注入后生成风险事件
- 按轮次刷新风险运行态

### 3.3 `llm_mechanism_v1` 深度机制推演

核心文件：

- `backend/app/services/mechanism_simulation_service.py`
- `backend/app/services/env_simulation_config_generator.py`
- `frontend/src/components/KaleidoStep2.vue`
- `frontend/src/views/AnalysisView.vue`

快速搜索默认走 `legacy_envfish_v1`。深度搜索会启用 `llm_mechanism_v1`，让 LLM 生成或辅助生成：

- 场景状态变量
- 机制图谱
- Agent blueprints
- 候选关系
- 关系发现 ledger
- 校验后的关系图
- simulation audit
- round reasoning ledger

结果分析页中有“机制推演”标签，专门呈现这些机制工件。

### 3.4 武汉疫情黄金案例冻结回放

入口：`/demo/wuhan`  
核心文件：

- `frontend/src/views/WuhanDemoView.vue`
- `backend/app/api/golden_cases.py`
- `backend/app/services/golden_case_service.py`
- `backend/scripts/build_wuhan_golden_run.py`
- `docs/modules/wuhan-demo.md`

这是一个不调用 LLM、不调用 Zep、不启动真实模拟 runner 的冻结演示案例。它会恢复轻量的 project、simulation、report handle，指向确定性本地 artifact。

当前武汉案例配置：

- case id：`wuhan_covid_v1`
- reference time：`2019-12-22T00:00:00+08:00`
- total rounds：36
- minutes per round：4320
- hazard template：`pest_disease_ecology`
- diffusion template：`bio_ecological_transmission`
- search mode：`deep_search`
- target agents：240
- artifact contract version：`2026-05-23.organic-map-layout.v1`

这个案例的定位不是“专门做一个武汉页面”，而是用一个稳定 fixture 快速验证正式 Step 2/3 的地图、图谱、关系、风险对象和回放行为。

### 3.5 统一结果分析与节点探索

入口：`/analysis/:reportId`  
核心文件：

- `frontend/src/views/AnalysisView.vue`
- `backend/app/api/report.py`
- `backend/app/services/report_analysis.py`
- `backend/app/services/report_agent.py`

分析页包含七个标签：

- 区域态势
- 机制推演
- 反馈环
- 角色透镜
- 轮次叙事
- 节点探索
- 报告

节点探索支持：

- 点击图谱节点查看上下文
- 深度探索节点
- 与节点相关上下文聊天
- 结合反馈、机制、风险对象和轮次状态做解释

### 3.6 太空碎片 / 凯斯勒阈值预测模块

入口：`/space-forecast`  
核心文件：

- `frontend/src/views/SpaceForecastView.vue`
- `frontend/src/features/space-forecast/core/*`
- `frontend/src/features/space-forecast/three/*`
- `frontend/public/models/nasa-satellite-fleet/*`
- `frontend/public/models/nasa-satellite-kit/*`

这是一个 Three.js 驱动的独立实验模块，模拟轨道碰撞、碎片级联和凯斯勒阈值。它使用 NASA 3D 模型资产、Earth texture、轨道壳层、碰撞特效和指标面板。

它当前与生态推演主线共用 Kaleido 品牌和前端路由，但数据和后端主流程基本独立。可以把它理解为 Kaleido “复杂系统预测沙盘”方向的第二类样板。

## 4. 技术栈

### 4.1 根项目

文件：`package.json`

- Node.js：`>=18`
- 根脚本：
  - `npm run setup`
  - `npm run setup:backend`
  - `npm run setup:all`
  - `npm run dev`
  - `npm run build`
  - `npm run verify`
  - `npm run verify:backend`
  - `npm run test:space-forecast`
- 并发启动工具：`concurrently`
- License：AGPL-3.0

### 4.2 前端

文件：`frontend/package.json`

核心栈：

- Vue 3
- Vue Router 4
- Vite 7
- Axios
- D3
- Leaflet
- Three.js
- 3d-force-graph
- three-spritetext

前端构成：

- `frontend/src/views`：页面级路由
- `frontend/src/components`：Kaleido 主流程组件、图谱组件、地图组件
- `frontend/src/api`：API 封装
- `frontend/src/store`：轻量 session/local 状态桥接
- `frontend/src/features/space-forecast`：太空碎片预测模块
- `frontend/public/models`：3D 模型资产
- `frontend/public/textures`：贴图资产

### 4.3 后端

文件：

- `backend/pyproject.toml`
- `backend/requirements.txt`

核心栈：

- Python 3.11+
- Flask
- Flask-CORS
- Gunicorn
- OpenAI SDK
- Zep Cloud SDK
- Pydantic
- PyMuPDF
- Pillow
- python-dotenv
- charset-normalizer / chardet
- pytest

后端构成：

- `backend/app/api`：Flask blueprint API
- `backend/app/services`：核心业务服务
- `backend/app/models`：文件态 Project、Task 模型
- `backend/app/utils`：LLM、日志、文件解析、原子写入等工具
- `backend/scripts`：EnvFish runtime、历史 OASIS runner、武汉黄金案例构建脚本
- `backend/tests`：稳定性、风险对象、地图投影、黄金案例、LLM fallback 等测试

### 4.4 外部服务和数据源

- LLM：OpenAI SDK 兼容接口，默认配置示例为 DashScope `qwen-plus`，也支持 DeepSeek V4。
- LLM fallback：支持备用 API key、base url 和 model。
- Zep Cloud：用于知识图谱创建、ontology 设置、episode 写入、节点/边读取。
- Nominatim：地图正向/逆向地理编码。
- Overpass API：OSM 空间要素采集。
- ESA WorldCover 2021：土地覆盖遥感识别。
- Open-Meteo：天气基线。

### 4.5 部署

文件：

- `Dockerfile`
- `Dockerfile.backend`
- `frontend/Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `frontend/nginx.conf`

当前有两种部署形态：

1. 单容器开发/快速运行：根 `Dockerfile` 安装前后端依赖并运行 `npm run dev`。
2. 生产拆分：`docker-compose.prod.yml` 使用 backend + frontend 两个服务，前端 nginx 反代 `/api` 和 `/health` 到 backend。

生产 backend 命令：

```bash
uv run gunicorn --bind 0.0.0.0:5001 --workers 1 --threads 4 --timeout 300 app:create_app()
```

注意：当前生产配置是单 worker、多线程。结合文件态存储，这是相对保守的选择。

## 5. 功能架构

### 5.1 用户主流程

当前用户主流程可以描述为：

1. 背景生成
   - 输入地点、稳态描述、变量、重点关系、边界、问题和资料。
   - 地图选点并生成 map seed。
   - 生成背景素材报告。
   - 把报告作为 Markdown 文件进入后续图谱流程。

2. 图谱构建
   - 上传/生成的文本经过文件解析和预处理。
   - 当前 `OntologyGenerator` 实现返回默认本体，接口注释和 README 中仍保留“LLM 生成本体”的表述。
   - GraphBuilder 使用 Zep 创建 graph，设置 ontology，按 chunk 写入 episode，等待处理后读取图谱。

3. 场景设计
   - 创建 simulation handle。
   - 用户确认变量、时间计划、搜索模式、hazard template、传播模板等。
   - 后端从 Zep 或 map seed 读取实体，生成区域、子区域、Agent、关系、风险对象和 simulation config。
   - 前端展示风险对象、区域划分、代理体配置和关系骨架。

4. 推演播放
   - 后端启动 `run_envfish_simulation.py` 子进程。
   - Runtime 按轮次推进环境扩散、Agent 互动、人类-自然反馈、动态关系、风险运行态。
   - 前端 Step 3 显示轮次、关系变化、风险状态、Agent 面板和聚焦图谱脉冲。

5. 报告和结果分析
   - ReportAgent 根据 EnvFish 工件和工具生成报告。
   - AnalysisView 汇总区域态势、反馈环、角色透镜、机制推演、轮次叙事、节点探索和完整报告。

### 5.2 后端 API 分层

Flask blueprint：

- `/api/graph`
  - 项目管理
  - 上传文件并生成本体
  - 构建 Zep 图谱
  - 获取任务状态
  - 读取图谱数据

- `/api/map`
  - 地点编码
  - 点位逆地理解析
  - 创建地图种子任务
  - 查询地图种子状态
  - 获取地图种子、图层
  - 将地图种子转成 simulation

- `/api/scene`
  - 生成场景素材报告
  - 获取 scene seed
  - 按说明修订 scene seed

- `/api/simulation`
  - 创建 simulation
  - 准备 simulation
  - 查询准备状态
  - 获取实时图谱、地图投影、动画
  - 风险定义、风险运行态、风险事件、风险 pin/reframe
  - 启动、停止、变量注入
  - 查询运行状态、详情、actions、timeline、posts、comments
  - Agent interview 相关接口

- `/api/report`
  - 同步/异步生成报告
  - 报告进度、章节、日志
  - 分析图谱、总览、tab 数据
  - 节点上下文、节点探索、节点聊天

- `/api/golden-cases`
  - 列出黄金案例
  - 恢复冻结案例

- `/api/control`
  - 强制停止所有 AI 推演任务

### 5.3 数据与 artifact 布局

当前持久化主要靠文件系统。

常见目录：

- `backend/app/uploads/projects`
- `backend/app/uploads/tasks`
- `backend/app/uploads/simulations`
- `backend/app/uploads/reports`
- `backend/app/uploads/map_seeds`
- `backend/app/uploads/scene_seeds`
- `backend/app/uploads/golden_runs`

常见 simulation artifact：

- `state.json`
- `simulation_config.json`
- `profiles_full.json`
- `reddit_profiles.json`
- `twitter_profiles.csv`
- `region_graph_snapshot.json`
- `subregion_graph_snapshot.json`
- `agent_relationship_graph.json`
- `transport_edges.json`
- `grounding_summary.json`
- `diffusion_context.json`
- `risk_definitions.json`
- `latest_risk_runtime_state.json`
- `risk_runtime_state.jsonl`
- `risk_events.jsonl`
- `round_state_matrix.jsonl`
- `agent_interaction_ledger.jsonl`
- `dynamic_edge_ledger.jsonl`
- `round_reasoning_ledger.jsonl`
- `latest_round_snapshot.json`
- `animation.json`

文件态系统的优点：

- 调试直观。
- 工件可复现、可复制、可冻结。
- 与黄金案例 fixture 很契合。

风险：

- 并发写入和跨进程一致性需要持续小心。
- 多 worker 或多实例部署会复杂化。
- 上传和工件目录需要明确备份、清理和访问控制策略。
- 当前仓库中已经有部分 `backend/app/uploads` 历史文件被 Git 跟踪，虽然 `.gitignore` 后续忽略了 `backend/uploads/`，但实际路径是 `backend/app/uploads/`，需要确认是否应该纳入忽略规则或转为明确 fixtures。

## 6. 核心服务说明

### 6.1 `SceneMaterialGenerator`

作用：把用户输入、上传资料、地图点位、地图种子和初始变量整理成可进入 EnvFish 的场景素材报告。

输出：

- `scene_seed.json`
- `scene_report.md`
- title
- scene type
- source mode
- 推荐 simulation requirement
- locations
- area of interest
- initial variables
- assumptions
- uncertainties
- report markdown

重要规则：

- 初始变量只放真正会改变系统状态的扰动、压力或干预。
- 天气基线、稳态、当前观测值、地图事实不应被当成 injected variables。
- LLM 不可用时有 fallback 生成路径。

### 6.2 `MapSeedManager`

作用：从地图点位构建空间事实层。

主要能力：

- 地点搜索和逆地理解析
- 半径感知区域命名
- OSM / Overpass 空间要素采集
- ESA WorldCover 土地覆盖识别
- Open-Meteo 环境基线
- 场景类型分类
- 地图图层生成
- 地图图谱快照生成
- 从 map seed 创建 Project

重要规则：

- 区域命名要受半径影响。
- 选点中心有强锚点时，优先用中心锚点命名。
- 可用于命名的范围外信息，不应作为范围内节点渲染。

### 6.3 `GraphBuilderService`

作用：将文本材料送入 Zep 构建知识图谱。

流程：

1. 创建 graph id，例如 `envfish_xxx`
2. 设置 ontology
3. 文本分块
4. 批量写入 Zep episode
5. 等待 Zep 处理
6. 读取节点和边

注意：`OntologyGenerator` 当前代码返回默认本体：

- Entity types：Region、Actor、Risk
- Edge types：AFFECTS、LOCATED_IN

这与 API 注释中的“调用 LLM 生成本体”存在实现差异，建议 Claude 审阅时重点检查。

### 6.4 `SimulationManager`

作用：创建、保存、准备 simulation。

准备阶段会生成：

- regions
- subregions
- transport edges
- profiles / agents
- agent relationships
- risk definitions
- risk runtime initial bundle
- simulation config
- mechanism artifacts

它支持两类实体来源：

- `graph`：从 Zep 读取实体
- `map_seed`：从地图种子图谱读取实体

### 6.5 `EnvProfileGenerator`

作用：从实体和地图证据生成区域、子区域、生态社会 Agent、传播边和关系。

值得注意的能力：

- 根据地图证据判断环境 archetype，比如 ocean sparse、urban 等。
- 在纯海域场景中限制居民、商业、社区等社会主体生成。
- 为 Agent 保留 evidence refs。
- 支持 LLM profile 生成，也有规则 fallback。

### 6.6 `MechanismSimulationPlanner`

作用：深度搜索模式下让 LLM 生成场景机制模型。

输出：

- `scenario_model.json`
- `mechanism_graph.json`
- `agent_blueprints.json`
- `validated_relation_graph.json`
- `simulation_audit.json`
- `relation_discovery_ledger.jsonl`

该模块是 additive 的，默认仍保留 legacy pipeline。

### 6.7 `EnvFishRuntime`

文件：`backend/scripts/run_envfish_simulation.py`

定位：区域级半定量生态社会推演沙盘。它不求解真实物理方程，而是使用结构化 LLM 输出、确定性校验和规则 fallback 生成区域扩散、人类行为和反馈链。

每一轮大致执行：

1. 推进动态关系生命周期。
2. 解析当前轮生效变量。
3. 更新环境扩散。
4. 更新 Agent 互动。
5. 更新人类-自然反馈。
6. 生成 round snapshot。
7. 刷新风险运行态。
8. 如果启用机制架构，记录 round reasoning。
9. 写入 JSON / JSONL 工件。
10. 通过 IPC 等待或处理后续命令。

### 6.8 `SimulationRunner`

作用：管理 EnvFish runtime 子进程和运行状态。

能力：

- 启动模拟
- 停止模拟
- 清理运行日志
- 读取 run state
- 读取 EnvFish artifacts
- 读取 interview 历史
- 管理 stdout/stderr
- 进程退出清理

### 6.9 `ReportAgent` 和 `ReportAnalysisService`

ReportAgent 负责生成报告，提供工具式信息源，例如：

- envfish summary
- spread forecast
- vulnerability ranking
- feedback summary
- intervention comparison
- interview agents

ReportAnalysisService 则把报告和仿真 artifacts 聚合给前端分析页：

- overview
- graph data
- regions tab
- mechanisms tab
- feedback tab
- roles tab
- narrative tab
- node context
- node explore
- node chat

## 7. 前端功能设计

### 7.1 路由

当前路由：

- `/`：首页和入口编排
- `/scene-composer`：背景生成
- `/process/:projectId?`：项目处理和 Step 2 工作台
- `/simulation/:simulationId`：场景设计
- `/simulation/:simulationId/start`：推演播放
- `/analysis/:reportId`：结果分析
- `/report/:reportId`：重定向到 analysis 的 report tab
- `/interaction/:reportId`：重定向到 analysis 的 node-explore tab
- `/demo/wuhan`：武汉冻结演示恢复入口
- `/history`：历史记录
- `/space-forecast`：太空预测

### 7.2 主要组件

- `GraphPanel.vue`
  - 支持图谱、地图、3D 图谱等视图。
  - 支持节点选中、节点动作、风险高亮、动画状态。

- `MapRelationPanel.vue`
  - 地图关系层展示。
  - 与后端 realtime graph / map projection 数据契约相关。

- `LeafletMapPicker.vue`
  - 地图选点、半径选择、地理分析入口。

- `KaleidoStep2.vue`
  - 推演参数、风险对象预览、区域划分、代理体配置、关系骨架。
  - 根据变量推断场景模式、hazard template 和自动时间计划。
  - 提交后调用 prepare。

- `KaleidoStep3.vue`
  - 推演运行、播放、风险态、Agent 互动、变量注入、报告生成入口。

- `AnalysisView.vue`
  - 统一结果分析页。

- `SpaceScene.vue`
  - Three.js 太空碎片场景。

### 7.3 前端状态桥接

项目没有引入 Pinia/Vuex，当前使用轻量模块：

- `pendingUpload.js`
  - 临时保存由 Scene Composer 生成的 Markdown 文件和推演需求。

- `sceneSeedBridge.js`
  - 使用 sessionStorage 把 scene seed context 绑定到 project 或 simulation。

- `workflowNavigation.js`
  - 保存 4 步导航状态和 Scene Composer snapshot。

这套方式适合本地和单用户流程，但如果未来要多用户、跨设备或服务端恢复，需要后端化。

## 8. 测试与验证现状

根脚本：

```bash
npm run verify
```

会执行：

1. `cd backend && uv run pytest`
2. `cd frontend && npm run build`
3. `cd frontend && npm run test:space-forecast`

后端测试覆盖点：

- 文件态状态和启动恢复
- TaskManager 生命周期
- health 和 task status API
- SimulationState 创建读取
- LLM fallback
- 地图区域命名
- 地图种子 Agent 生成
- 风险对象生成和 legacy 投影
- 仿真地图投影
- 武汉黄金案例恢复、fresh handle、contract refresh、非模板化地图布局

空间预测有独立回归脚本：

- `frontend/scripts/space-forecast-regression.mjs`

本文档为文档新增，未执行全量测试。

## 9. 当前实现中值得 Claude 重点审阅的问题

### 9.1 产品一致性

- README 仍写 5 步，前端主流程现在是 4 个聚合阶段。需要决定最终对外表达。
- Space Forecast 是否属于 Kaleido 主产品的一部分，还是一个独立展示模块。
- 武汉疫情演示作为生态推演产品 fixture 是否合理，是否容易让用户误解产品领域。
- “Mirofish -> EnvFish -> Kaleido”的叙事需要正式写进项目文档，避免只停留在对话里。

### 9.2 架构和并发

- 当前数据层主要是文件系统，适合单机原型，但多用户、多实例、高并发时风险较高。
- Gunicorn 生产配置是 1 worker + 4 threads，这与文件态存储相对匹配；如果扩展 worker 数会带来一致性问题。
- TaskExecutor 是 in-process background thread，不是持久队列。服务重启会把处理中任务标记失败。
- SimulationRunner 依赖子进程和本地文件日志，需要明确部署、回收和权限边界。

### 9.3 LLM 和图谱依赖

- LLM 调用成本、失败、空 JSON、fallback、安全降级需要持续测试。
- Zep 图谱构建是外部依赖，当前有重试，但仍需考虑 quota、延迟和 API 变化。
- `OntologyGenerator` 当前返回默认本体，和“LLM 生成 ontology”的产品说明不一致。

### 9.4 安全

- Flask CORS 当前对 `/api/*` 放开 `origins: *`。
- 没有看到认证、授权、用户隔离。
- 上传文件会落盘，当前支持 PDF/MD/TXT，但还需审查文件大小、恶意文件、路径、清理策略。
- Report/Simulation artifacts 可能包含敏感材料摘要，需要明确访问控制。

### 9.5 数据契约

- Step 2、Step 3、Analysis、Wuhan fixture 依赖大量 JSON artifact 契约。
- 已有 artifact contract version 机制，但目前只对武汉黄金案例显式管理。
- 建议将正式 simulation artifact schema 文档化，并补充 schema-level 校验。

### 9.6 地理与环境数据可信度

- OSM、WorldCover、Open-Meteo 都是 best-effort 外部数据源。
- WorldCover 是 2021 土地覆盖，不是实时遥感。
- 地理编码可能失败或偏移，当前有本地 fallback，但需要 UI 上区分事实、检测和推断。
- 代码里已有 observed/detected/inferred 思路，建议在产品层继续强化。

### 9.7 前端工程

- `VITE_PUBLIC_LAUNCH_MODE` 在 `.env.example` 和 Docker 中存在，但当前搜索未看到前端实际消费逻辑。
- App 背景中使用 `Math.random()` 初始化装饰球。当前项目是 CSR，不涉及 SSR hydration；如果未来引入 SSR，需要避免非确定性渲染。
- 大型组件如 `KaleidoStep2.vue`、`KaleidoStep3.vue`、`GraphPanel.vue` 文件较大，后续可按稳定契约拆分。

## 10. 建议 Claude 审阅任务

可以把下面这段作为给 Claude 的审阅提示：

```text
请作为资深产品架构师和全栈工程审阅者，审阅 Kaleido 项目。

重点不是只找语法问题，而是从以下角度给出判断：

1. 产品定位是否清晰：从 Mirofish 灵感发展到 Kaleido 生态推演沙盘，这条叙事是否成立。
2. 当前 4 阶段/5 步流程是否需要统一表达。
3. Vue + Flask + 文件态 artifacts + LLM + Zep 的技术路线是否适合当前阶段。
4. 地图种子、风险对象、LLM 机制推演、冻结黄金案例、节点探索、太空预测这些功能设想之间是否有主次关系，哪些应进入主线，哪些应作为实验模块。
5. 文件态存储、后台线程、子进程、外部 API、CORS、上传文件和无认证状态有哪些高风险点。
6. 哪些模块应该优先重构，哪些暂时不要动。
7. 如果要把项目推进到可长期维护的版本，应优先补哪些文档、schema、测试和部署规则。

请给出：
- 总体判断
- 高风险问题
- 低成本高收益改进
- 中长期架构建议
- 不建议现在做的过度工程化方向
```

## 11. 推荐下一步沉淀

建议继续补充以下项目文档：

- `docs/architecture.md`：系统架构、数据流、服务边界。
- `docs/data-contracts/simulation-artifacts.md`：simulation artifacts schema。
- `docs/data-contracts/map-seed.md`：地图种子 schema。
- `docs/data-contracts/risk-objects.md`：风险对象 schema。
- `docs/operations/deployment.md`：生产部署、回滚、健康检查、上传目录备份。
- `docs/operations/security.md`：上传、鉴权、CORS、敏感材料处理。
- `docs/modules/space-forecast.md`：太空预测模块定位和维护入口。
- `docs/project-history.md`：正式记录 Mirofish -> EnvFish -> Kaleido 的项目发展线。

## 12. 当前仓库状态备注

审阅时需要注意：

- 当前 Git 历史只有 `Initial commit`，不能依赖 commit log 还原项目演进。
- 工作区存在大量未提交改动和新增文件，包括 `AGENTS.md`、`docs/modules/*`、武汉 demo、测试和若干上传 artifacts。
- 本文档基于当前工作区文件，而不只是 `origin/main`。
- `backend/app/uploads` 中有部分历史文件已经被 Git 跟踪，也有部分本地未跟踪文件；建议后续明确 fixtures 与运行数据的边界。

