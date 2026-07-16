"""Focused contracts for public display localization boundaries."""

from types import SimpleNamespace

from flask import Flask

from app.api import simulation_bp
from app.api import simulation as simulation_api
from app.services.display_localization import (
    find_public_display_leaks,
    public_error_message,
    sanitize_public_dto,
)
from app.services.report_analysis import ReportAnalysisService


def _simulation_client():
    app = Flask(__name__)
    app.json.ensure_ascii = False
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


def _dirty_artifacts():
    return {
        "engine_mode": "envfish",
        "risk_definitions": [
            {
                "risk_id": "risk_legacy_01",
                "type": "RiskObject",
                "status": "watch",
                "name": "Agent 12",
                "title": "LegacyRiskObject",
                "summary": "Round 1 establishes an initial risk object in region_1.",
                "trigger_conditions": [
                    "pressure_over_limit",
                    "当 region_1 暴露超过阈值",
                ],
            }
        ],
        "region_graph": [
            {
                "region_id": "region_1",
                "name": "R01",
                "description": "Boundary region used by the legacy fixture.",
            }
        ],
        "latest_snapshot": {
            "round": 1,
            "summary": "Round 1 establishes the initial state.",
            "feedback": {
                "feedback_propagation": [
                    {
                        "loop": "agent_pressure_loop",
                        "note": "Agent 2 located_in R01.",
                    }
                ]
            },
        },
    }


def test_recursive_projection_preserves_machine_fields_and_cleans_display_fields():
    dirty = {
        "id": "node_01",
        "type": "RiskObject",
        "status": "active",
        "name": "Agent 12",
        "summary": "Round 1 establishes initial risk object in region_1.",
        "relation_label": "located_in",
        "trigger_conditions": [
            "pressure_over_limit",
            "当 region_1 暴露超过阈值",
        ],
        "nested": [
            {
                "node_id": "node_777",
                "source_node_name": "WaterTreatmentAgent",
                "fact": "Agent 2 located_in R01.",
            }
        ],
    }

    projected = sanitize_public_dto(dirty)

    assert projected["id"] == "node_01"
    assert projected["type"] == "RiskObject"
    assert projected["status"] == "active"
    assert projected["nested"][0]["node_id"] == "node_777"
    assert projected["name"] == "未命名风险对象"
    assert projected["relation_label"] == "位于"
    assert "相关对象" in projected["trigger_conditions"][1]
    assert find_public_display_leaks(projected) == []


def test_risk_scope_provenance_remains_a_machine_enum_for_frontend_localization():
    projected = sanitize_public_dto({
        "risk_statement": {
            "actor_refs": [{
                "actor_id": 2,
                "actor_name": "滨海区居民代表",
                "scope_basis": "receptor_role_demand",
                "primary_region": "feature_region_coast",
            }]
        }
    })

    actor = projected["risk_statement"]["actor_refs"][0]
    assert actor["scope_basis"] == "receptor_role_demand"
    assert actor["primary_region"] == "feature_region_coast"


def test_public_error_rejects_mixed_unknown_backend_english():
    assert public_error_message(
        "连接 timeout 失败",
        "获取运行状态失败，请稍后重试。",
    ) == "获取运行状态失败，请稍后重试。"


def test_public_error_rejects_exception_paths_and_network_addresses():
    assert public_error_message(
        "运行失败: FileNotFoundError [Errno 2] /tmp/run.json",
        "运行失败，请稍后重试。",
    ) == "运行失败，请稍后重试。"
    assert public_error_message(
        "连接失败 at 127.0.0.1:8000/api/run",
        "连接失败，请稍后重试。",
    ) == "连接失败，请稍后重试。"


def test_display_projection_rejects_numeric_and_punctuation_only_names():
    projected = sanitize_public_dto({
        "name": "1527220",
        "nested": {"title": "->"},
    })

    assert projected["name"] == "未命名对象"
    assert projected["nested"]["title"] == "未命名条目"


def test_route_descriptor_preserves_machine_route_name():
    projected = sanitize_public_dto({
        "route": {
            "name": "SimulationRun",
            "params": {"simulationId": "sim_demo_01"},
            "query": {"replay": "1"},
        },
        "card": {"name": "Agent 12"},
    })

    assert projected["route"]["name"] == "SimulationRun"
    assert projected["route"]["params"]["simulationId"] == "sim_demo_01"
    assert projected["card"]["name"] == "未命名代理体"
    assert find_public_display_leaks(projected) == []


def test_generated_reasoning_translates_workflow_step_without_broken_number():
    projected = sanitize_public_dto({
        "hazard_template_reasoning": "复合事件以 Step 2 事件机制图为准。",
    })

    assert projected["hazard_template_reasoning"] == "复合事件以第二步事件机制图为准。"


def test_report_markdown_projection_preserves_layout_and_removes_internal_blocks():
    projected = sanitize_public_dto(
        {
            "markdown_content": (
                "# 风险报告\n\n"
                "<tool_call>\n"
                '{"name": "envfish_summary"}\n'
                "</tool_calls>\n\n"
                "---\n\n"
                "| 指标 | 状态 |\n"
                "| --- | --- |\n"
                "| 生态保护 | crisis_mode |\n\n"
                "采用crisis_mode与marine_current，32个Agent执行RESTRICT；"
                "生态保护 vs. 经济畅通。"
            ),
            "traceback": "Traceback: backend exploded",
        }
    )

    markdown = projected["markdown_content"]
    assert markdown.startswith("# 风险报告\n\n")
    assert "| --- | --- |" in markdown
    assert "| 生态保护 | 灾难态 |" in markdown
    assert "采用灾难态与海洋环流" in markdown
    assert "32个代理体执行限制干预" in markdown
    assert "tool_call" not in markdown.lower()
    assert "envfish_summary" not in markdown.lower()
    assert "crisis_mode" not in markdown
    assert "Agent" not in markdown
    assert "RESTRICT" not in markdown
    assert "traceback" not in projected
    assert find_public_display_leaks(projected) == []


def test_report_markdown_keeps_citation_labels_without_broken_link_fragments():
    projected = sanitize_public_dto({
        "markdown_content": (
            "## 证据索引\n\n"
            "- [世界卫生组织新冠疫情时间线](https://www.who.int/news/item/covidtimeline)（世界卫生组织）"
        )
    })

    markdown = projected["markdown_content"]
    assert "世界卫生组织新冠疫情时间线（世界卫生组织）" in markdown
    assert "https://" not in markdown
    assert "](" not in markdown
    assert find_public_display_leaks(projected) == []


def test_report_summary_keeps_business_prose_when_legacy_aliases_are_present():
    projected = sanitize_public_dto({
        "outline": {
            "summary": (
                "本报告基于crisis_mode场景与generic扩散模板，涉及6个Agent，"
                "形成九龍塘 Kowloon Tong交通物流中断风险。"
            ),
            "sections": [{
                "title": "区域态势",
                "content": "## 区域态势\n\n黄大仙区向九龙塘持续输出扩散压力。",
            }],
        }
    })

    assert projected["outline"]["summary"] == (
        "本报告基于灾难态场景与通用扩散模板，涉及6个代理体，形成九龍塘交通物流中断风险。"
    )
    assert projected["outline"]["sections"][0]["content"] == (
        "## 区域态势\n\n黄大仙区向九龙塘持续输出扩散压力。"
    )
    assert find_public_display_leaks(projected) == []


def test_report_markdown_removes_generation_narration_and_localizes_legacy_artifacts():
    projected = sanitize_public_dto({
        "markdown_content": (
            "## 人类-自然反馈回路\n\n"
            "好的，基于以上四次工具调用的结果，我将整合观测数据，撰写本章节。\n\n"
            "灾难变量为disaster，政策变量为policy，执行environmental_monitoring与information_release。\n\n"
            "目标包括feature_context_admin_district_馬仔坑_ma_chai_hang，"
            "并引用envfish_summary与envfish_feedback_summary。\n\n"
            "目标区域（feature_relation_2800277、feature_context_admin_district_馬仔坑_ma_chai_hang），"
            "目标节点（feature_node_1、proxy_operators、proxy_maintainers）。\n\n"
            "指示物种群发出PANIC_POST信号，车站类型为transit_stop。"
        )
    })

    markdown = projected["markdown_content"]
    assert "我将" not in markdown
    assert "工具调用" not in markdown
    assert "馬仔坑_ma_chai_hang" not in markdown
    assert "灾害事件" in markdown
    assert "政策干预" in markdown
    assert "环境监测与信息发布" in markdown
    assert "推演摘要与反馈摘要" in markdown
    assert "生态压力信号" in markdown
    assert "生态压力信号信号" not in markdown
    assert "交通站点" in markdown
    assert "目标区域（当前分析范围）" in markdown
    assert "目标节点（相关执行主体）" in markdown
    assert "、、" not in markdown
    assert find_public_display_leaks(projected) == []


def test_simulation_blueprint_applies_public_projection_to_legacy_config(monkeypatch):
    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation_config",
        lambda self, simulation_id: {
            "simulation_id": simulation_id,
            "status": "ready",
            "region_graph": [{
                "region_id": "region_1",
                "name": "1527220",
                "description": "Standard cross_region_mechanism_bridge for Agent 2",
            }],
            "generation_reasoning": {
                "summary": "GET /api/private failed at 127.0.0.1:8000",
            },
            "traceback": "Traceback: internal fixture",
        },
    )

    response = _simulation_client().get("/api/simulation/sim_public_config/config")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["data"]["simulation_id"] == "sim_public_config"
    assert payload["data"]["region_graph"][0]["name"] == "未命名区域"
    assert "traceback" not in payload["data"]
    assert find_public_display_leaks(payload["data"]) == []


def test_simulation_blueprint_never_returns_traceback_on_route_failure(monkeypatch):
    def fail_config(self, simulation_id):
        raise FileNotFoundError("/tmp/private/simulation_config.json")

    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation_config",
        fail_config,
    )

    response = _simulation_client().get("/api/simulation/sim_failure/config")
    payload = response.get_json()

    assert response.status_code == 500
    assert payload == {
        "success": False,
        "error": "请求未能完成，请稍后重试。",
    }


def test_run_status_detail_defaults_raw_artifacts_off_and_localizes_projection(monkeypatch):
    class FakeRunState:
        current_round = 1
        rounds = [1]

        @staticmethod
        def to_dict():
            return {
                "simulation_id": "sim_public_01",
                "runner_status": "running",
                "current_round": 1,
                "total_rounds": 2,
                "progress_percent": 50,
                "message": "Agent 1 is processing region_1.",
            }

    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "get_run_state",
        classmethod(lambda cls, simulation_id: FakeRunState()),
    )
    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "get_envfish_artifacts",
        classmethod(lambda cls, simulation_id: _dirty_artifacts()),
    )
    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation",
        lambda self, simulation_id: SimpleNamespace(
            engine_mode="envfish",
            scenario_mode="formal",
            diffusion_template="marine",
            search_mode="fast",
        ),
    )
    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation_config",
        lambda self, simulation_id: {},
    )

    response = _simulation_client().get(
        "/api/simulation/sim_public_01/run-status/detail?include_actions=false"
    )
    assert response.status_code == 200
    payload = response.get_json()
    data = payload["data"]

    assert payload["success"] is True
    assert "envfish" not in data
    assert data["simulation_id"] == "sim_public_01"
    assert data["risk_definitions"][0]["risk_id"] == "risk_legacy_01"
    assert data["risk_definitions"][0]["name"] == "未命名风险对象"
    assert data["region_graph"][0]["region_id"] == "region_1"
    assert find_public_display_leaks(data) == []


def test_run_status_detail_opt_in_raw_bundle_is_still_display_safe(monkeypatch):
    class FakeRunState:
        current_round = 1
        rounds = [1]

        @staticmethod
        def to_dict():
            return {
                "simulation_id": "sim_public_02",
                "runner_status": "running",
                "current_round": 1,
            }

    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "get_run_state",
        classmethod(lambda cls, simulation_id: FakeRunState()),
    )
    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "get_envfish_artifacts",
        classmethod(lambda cls, simulation_id: _dirty_artifacts()),
    )
    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation",
        lambda self, simulation_id: SimpleNamespace(
            engine_mode="envfish",
            scenario_mode="formal",
            diffusion_template="marine",
            search_mode="fast",
        ),
    )
    monkeypatch.setattr(
        simulation_api.SimulationManager,
        "get_simulation_config",
        lambda self, simulation_id: {},
    )

    response = _simulation_client().get(
        "/api/simulation/sim_public_02/run-status/detail"
        "?include_actions=false&include_envfish_raw=true"
    )
    data = response.get_json()["data"]

    assert "envfish" in data
    assert data["envfish"]["risk_definitions"][0]["risk_id"] == "risk_legacy_01"
    assert find_public_display_leaks(data) == []


def test_run_status_detail_does_not_expose_traceback_or_english_exception(monkeypatch):
    def fail_get_run_state(cls, simulation_id):
        raise RuntimeError("Exploded backend fixture for Agent 9")

    monkeypatch.setattr(
        simulation_api.SimulationRunner,
        "get_run_state",
        classmethod(fail_get_run_state),
    )

    response = _simulation_client().get(
        "/api/simulation/sim_failure/run-status/detail"
    )
    payload = response.get_json()

    assert response.status_code == 500
    assert payload == {
        "success": False,
        "error": "获取详细状态失败，请稍后重试。",
    }


def test_step3_graph_animation_and_risk_artifact_endpoints_localize(monkeypatch):
    class FakeManager:
        @staticmethod
        def get_simulation(simulation_id):
            return SimpleNamespace(
                source_mode="artifact",
                map_seed_id=None,
                graph_id="graph_machine_01",
            )

        @staticmethod
        def resolve_artifact_dir(state, create_if_missing=False):
            return "/tmp/sim_public_artifacts"

        @staticmethod
        def _get_simulation_dir(simulation_id):
            return "/tmp/sim_public_artifacts"

    class FakeRealtimeGraphBuilder:
        def __init__(self, sim_dir):
            self.sim_dir = sim_dir

        @staticmethod
        def build():
            return {
                "nodes": [
                    {
                        "uuid": "node_graph_01",
                        "type": "RiskObject",
                        "name": "Agent 4",
                        "summary": "Legacy RiskObject in region_1.",
                    }
                ],
                "edges": [],
                "meta": {"node_count": 1, "edge_count": 0},
            }

    monkeypatch.setattr(simulation_api, "SimulationManager", FakeManager)
    monkeypatch.setattr(
        simulation_api,
        "SimulationRealtimeGraphBuilder",
        FakeRealtimeGraphBuilder,
    )
    monkeypatch.setattr(
        simulation_api,
        "SimulationAnimationService",
        lambda simulation_id: SimpleNamespace(
            get_animation=lambda: {
                "simulation_id": simulation_id,
                "frames": [
                    {
                        "round": 1,
                        "title": "Round 1 RiskObject",
                        "narrative": "Agent 4 entered region_1.",
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        simulation_api,
        "_load_risk_bundle",
        lambda simulation_id: (
            "/tmp/sim_public_artifacts",
            {
                **_dirty_artifacts(),
                "risk_contract_version": 2,
                "risk_generation_audit": {},
                "risk_objects_summary": {"primary_risk_object_id": "risk_legacy_01"},
            },
        ),
    )

    client = _simulation_client()
    graph = client.get(
        "/api/simulation/sim_public_artifacts/graph/realtime"
    ).get_json()["data"]
    animation = client.get(
        "/api/simulation/sim_public_artifacts/animation"
    ).get_json()["data"]
    risks = client.get(
        "/api/simulation/sim_public_artifacts/risk/definitions"
    ).get_json()["data"]

    assert graph["graph_data"]["nodes"][0]["uuid"] == "node_graph_01"
    assert graph["graph_data"]["nodes"][0]["name"] == "未命名风险对象"
    assert animation["simulation_id"] == "sim_public_artifacts"
    assert risks["primary_risk_id"] == "risk_legacy_01"
    assert find_public_display_leaks(graph) == []
    assert find_public_display_leaks(animation) == []
    assert find_public_display_leaks(risks) == []


def test_report_graph_and_tab_public_boundaries_clean_legacy_artifacts():
    service = ReportAnalysisService.__new__(ReportAnalysisService)
    service._load_graph_data = lambda: {
        "graph_id": "graph_legacy_01",
        "nodes": [
            {
                "uuid": "node_legacy_01",
                "name": "Agent 1",
                "labels": ["AdministrativeRegion", "RiskObject"],
                "summary": "Legacy node generated for region_1.",
            }
        ],
        "edges": [
            {
                "uuid": "edge_legacy_01",
                "name": "located_in",
                "fact": "Agent 1 located_in R01.",
                "source_node_uuid": "node_legacy_01",
                "target_node_uuid": "node_legacy_02",
            }
        ],
        "node_count": 1,
        "edge_count": 1,
    }

    graph = service.get_graph_data()

    assert graph["graph_id"] == "graph_legacy_01"
    assert graph["nodes"][0]["uuid"] == "node_legacy_01"
    # ``labels`` remains the machine classification contract; GraphPanel maps
    # it for display.  The singular/companion display fields are localized.
    assert graph["nodes"][0]["labels"] == ["AdministrativeRegion", "RiskObject"]
    assert graph["edges"][0]["source_node_uuid"] == "node_legacy_01"
    assert graph["edges"][0]["name"] == "位于"
    assert find_public_display_leaks(graph) == []

    service._build_regions_tab = lambda: {
        "tab": "regions",
        "regions": [
            {
                "region_id": "region_legacy_01",
                "name": "R01",
                "description": "LegacyRegion used by the fixture.",
            }
        ],
    }
    tab = service.get_tab_data("regions")

    assert tab["regions"][0]["region_id"] == "region_legacy_01"
    assert tab["regions"][0]["name"] == "未命名区域"
    assert find_public_display_leaks(tab) == []
