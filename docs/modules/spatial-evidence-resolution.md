# 地点识别、空间证据与 R0–R4 分辨率

## 模块边界

本模块负责把 Step 1 的空间骨架和 Step 2 的事件机制需求连接起来。它不负责 Agent 决策，也不把查询到的所有地点都生成成 Agent。

必须区分三组数据：

- `Spatial Catalog`：地图范围内可浏览、可检索的地点与设施目录。
- `Scenario Evidence Set`：当前事件机制和政策真正需要的 R0–R4 证据子集。
- `Agent Anchor Set`：通过证据校验、且确实承担行动或受体角色的设施子集。

地图目录数量、场景证据数量和 Agent 数量不得相互替代。

## 分辨率语义

| 等级 | 含义 | 示例 |
| --- | --- | --- |
| R0 | 整体研究范围 | 城市、跨区域 AOI、海湾 |
| R1 | 大型空间分区 | 区县、流域、海岸带、交通走廊 |
| R2 | 局部功能区 | 街道、社区、工业园、港区 |
| R3 | 真实机构或设施 | 医院、核电站、消防站、监测站 |
| R4 | 依附 R3 的内部建模单元 | 急诊、ICU、备用电源、冷却系统、资源池、合成人群分组 |

R4 不等于从公共地图中获取真实个人。真实 R4 只允许来自机构授权数据或用户资料；没有这些资料时只能建立明确标记为 `synthetic_model` 的模型单元。

## 当前已实现

### Overpass 分批稳定化

`MapSeedManager._collect_spatial_features()` 使用独立批次获取行政范围、水系与生态、居住和工业用地、公共设施、关键基础设施、服务枢纽、道路及公共交通。

缓存记录每个批次的完成状态。部分结果可以保留为证据，但不会提前短路后续查询；下次只补查缺失批次。旧缓存没有批次元数据时，只能作为部分证据使用。所有批次完整执行但没有要素时，可使用 `MAP_SOURCE_NEGATIVE_CACHE_TTL_SECONDS` 的短时负缓存；超时或部分失败绝不能写成“该区域没有设施”。

地图种子新增以下就绪字段：

```text
skeleton_ready
required_category_coverage
readiness.formal_ready
```

兼容字段 `formal_ready` 仍然保留，但新工件必须同时具备公开空间骨架、完整必需批次和有效 Overpass 状态，不能再由一个行政区节点触发。

### Step 2 机制驱动设施计划

`backend/app/services/spatial_evidence.py` 把 `EventMechanismGraph + RoleDemand` 编译为：

- `FacilityQueryPlan`
- `SpatialEvidenceRequest[]`
- `SpatialRefinementSnapshot`
- `R4ModelUnit`

每个 R3 请求包含事件、机制、RoleDemand、能力、区域、设施类别、最低证据等级和停止条件。每个 R4 请求必须引用父级 R3 请求，并限定来源为 `authoritative`、`user_supplied` 或 `synthetic_model`。

Step 2 `/api/simulation/prepare` 当前会持久化：

```text
facility_query_plan.json
spatial_refinement_snapshot.json
```

快照先对照当前 Step 1 目录，区分：

- `covered`：已有满足证据等级的 R3；
- `insufficient_evidence`：有候选，但需要交叉验证或权威资料；
- `missing`：当前目录没有候选；
- `parent_r3_missing`：R4 的父级设施尚未确认；
- `model_input_required`：父级设施已确认，但内部数据或建模输入尚缺。

这些状态是诊断和编排数据，不应直接作为正式业务页的成功/失败文案。

`backend/app/services/mechanism_aware_spatial_refiner.py` 已接入正式
`/prepare` 链路。它使用 Step 1 的 WGS84 中心点和分析半径，对每个 R3
请求分别查询 `SpatialCatalogPort`，再把本地目录结果与 Step 1
`target_catalog` 合并去重。每次目录查询都会在快照中留下
`provider_attempts` 和 `source_versions`；缺少范围、没有命中或目录不可用
都只会形成可审计缺口，不会被解释成“现实中不存在该设施”。R4 仍不会由
这个执行器自动生成。

### 受控 GeoJSON 离线导入

`backend/scripts/import_spatial_catalog.py` 可将已经取得授权、完成坐标和许可核对的 GeoJSON `FeatureCollection` 离线写入嵌入式 SQLite 空间目录。命令会先在内存中校验整份数据，再以单批事务更新目标目录；任一要素无效时不会创建或修改目标数据库。该入口不访问网络，也不负责下载 OSM、Overture 或商业 POI。

```bash
backend/.venv/bin/python backend/scripts/import_spatial_catalog.py facilities.geojson \
  --catalog backend/uploads/spatial_catalog.sqlite3 \
  --source-key official_facilities \
  --provider municipal_authority \
  --evidence-grade A \
  --dataset-version 2026-Q3 \
  --coordinate-system WGS84
```

使用 `--dry-run` 可只校验并输出确定性的 JSON 摘要。摘要包含数据合同版本、要素数量、合并范围、类别和证据等级计数及内容哈希，适合进入导入审计记录。

运行时通过 `SPATIAL_CATALOG_PATH` 指定目录文件，默认位于
`backend/uploads/spatial_catalog.sqlite3`；`SPATIAL_CATALOG_QUERY_LIMIT`
控制单个 R3 请求的最大候选数。正式部署时该路径必须位于持久卷，并纳入
数据版本、备份和回滚，而不能随容器临时文件系统一起销毁。

## 证据等级

| 等级 | 规则 |
| --- | --- |
| A | 官方、机构授权或用户确认 |
| B | 多来源交叉验证 |
| C | 单一正式空间数据源 |
| D | 参考地名、模糊候选或未经验证来源 |
| S | 明确标记的合成模型 |

关键设施和 `facility_required` 默认要求 B 级；普通目录浏览可使用 C 级；D/S 不得作为真实设施结果展示。

## 当前尚未实现

当前代码已经能提出正确的设施取证请求并识别证据缺口，但还没有完成生产级受控空间目录。因此：

- 公共 Overpass 仍是现有实时 OSM 获取来源，不能提供生产 SLA；
- 尚未接入本地 PostGIS 的 OSM/Overture 快照；
- 尚未接入高德、腾讯、百度或行业目录 Provider Adapter；
- `SpatialRefinementSnapshot` 已能查询嵌入式受控目录，但目录内容仍需要通过
  离线导入或未来的受控同步任务维护；它不会静默伪造缺失设施；
- 后台准备任务仍是进程内线程，服务重启时不能断点恢复。

不能把上述未完成项描述成已经可用。

## 下一阶段接入规则

Provider 执行顺序应固定为：

1. 本地受控 PostGIS 目录；
2. 官方或行业目录；
3. 已授权的商业 POI Provider；
4. 公共 Overpass 仅作开发或后台补充。

所有 Provider 必须输出统一字段：规范 ID、中文名称、类别、WGS84 几何、原始坐标系、来源 ID、证据等级、数据集版本、获取时间和许可引用。GCJ-02、BD-09 必须保留原坐标并显式转换，不能直接与 WGS84 混用。

## 维护入口

- 批次采集与缓存：`backend/app/services/map_seed_manager.py`
- 空间选择与就绪判定：`backend/app/services/map_spatial_selection.py`
- Step 2 空间证据合同：`backend/app/services/spatial_evidence.py`
- 嵌入式空间目录：`backend/app/services/spatial_catalog.py`
- 机制驱动目录执行器：`backend/app/services/mechanism_aware_spatial_refiner.py`
- 受控数据离线导入：`backend/scripts/import_spatial_catalog.py`
- Step 2 正式接入：`backend/app/api/simulation.py`
- 场景机制和 RoleDemand：`backend/app/services/scenario_planner.py`

重点测试：

```bash
backend/.venv/bin/python -m pytest \
  backend/tests/test_map_spatial_selection.py \
  backend/tests/test_map_seed_availability.py \
  backend/tests/test_spatial_catalog.py \
  backend/tests/test_import_spatial_catalog_cli.py \
  backend/tests/test_mechanism_aware_spatial_refiner.py \
  backend/tests/test_spatial_evidence.py \
  backend/tests/test_step2_prepare_contract.py -q
```

## 已知风险

- 公共 Overpass 仍可能 429、超时或按资源限制中止；拆分批次只能降低失败面，不能替代受控数据源。
- 批次完成只表示相应查询执行完成，不代表场景所需设施已经找到；场景覆盖必须读取 `SpatialRefinementSnapshot`。
- 单一 OSM/POI 候选不能自动升级为 B 级关键设施证据。
- R4 合成模型必须保存假设与来源标记，不能进入真实设施统计。
- 正式切换本地目录前，需要确定数据更新频率、许可、坐标转换、去重和回滚规则。
- 当前 SQLite 适配器适合本地、单机和确定性夹具；多实例并发写入和大范围
  空间分析应切换到实现同一 `SpatialCatalogPort` 的 PostGIS 适配器。
