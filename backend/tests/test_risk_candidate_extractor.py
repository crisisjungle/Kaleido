import pytest

from app.services.risk_candidate_extractor import RISK_FAMILIES, RiskCandidateExtractor


def _extract(graph, **kwargs):
    return RiskCandidateExtractor().extract(
        mechanism_graph=graph,
        regions=kwargs.pop(
            "regions",
            [{"region_id": "coast", "name": "滨海区", "region_type": "coastal_zone"}],
        ),
        entities=kwargs.pop(
            "entities",
            [{"uuid": "entity_resident", "name": "滨海区居民", "summary": "真实受影响人群"}],
        ),
        injected_variables=kwargs.pop("injected_variables", []),
        profiles=kwargs.pop("profiles", []),
        validated_relation_graph=kwargs.pop("validated_relation_graph", {}),
        simulation_requirement=kwargs.pop("simulation_requirement", "验证现实机制路径与受影响对象。"),
        **kwargs,
    )


def _grounded_graph():
    return {
        "nodes": [
            {"id": "source", "name": "风暴潮", "node_type": "source", "confidence": 0.9},
            {"id": "process", "name": "海水倒灌", "node_type": "process", "confidence": 0.85},
            {
                "id": "resident",
                "name": "滨海区居民",
                "node_type": "human",
                "description": "滨海区居民出行和居住安全受到影响",
                "confidence": 0.8,
            },
        ],
        "edges": [
            {
                "id": "edge_surge",
                "source": "source",
                "target": "process",
                "mechanism": "风暴潮推动海水进入滨海区",
                "evidence": ["滨海区潮位记录"],
                "confidence": 0.9,
            },
            {
                "id": "edge_exposure",
                "source": "process",
                "target": "resident",
                "mechanism": "海水倒灌增加滨海区居民暴露",
                "evidence": ["滨海区居民现场记录"],
                "confidence": 0.85,
            },
        ],
    }


def test_stable_id_and_v2_contract_are_grounded_and_repeatable():
    first = _extract(_grounded_graph())
    second = _extract(_grounded_graph())

    assert len(first.definitions) == 1
    risk = first.definitions[0]
    assert risk["risk_id"] == second.definitions[0]["risk_id"]
    assert risk["source_signature"] == second.definitions[0]["source_signature"]
    assert risk["risk_contract_version"] == 2
    assert risk["primary_family"] == "health_safety"
    assert risk["risk_statement"]["trigger_name"] == "风暴潮"
    assert risk["risk_statement"]["receptor_name"] == "滨海区居民"
    assert risk["mechanism_node_ids"] == ["source", "process", "resident"]
    assert risk["mechanism_edge_ids"] == ["edge_surge", "edge_exposure"]
    assert risk["monitoring_metrics"]
    assert risk["evidence_strength_score"] >= 40
    assert all(item["epistemic_status"] in {"observed", "inferred"} for item in risk["evidence"])


def test_planner_trace_copy_is_converted_to_a_specific_consequence():
    graph = _grounded_graph()
    graph["nodes"][-1]["name"] = "受影响人群"
    graph["nodes"][-1]["description"] = "用户描述中的“滨海区居民辐射暴露”明确指向受影响人群环节。"

    risk = _extract(graph).definitions[0]

    assert risk["title"] == "滨海区居民暴露与健康风险"
    assert risk["risk_statement"]["consequence"] == "滨海区居民辐射暴露，可能造成健康与安全暴露。"
    assert "明确指向" not in risk["risk_statement"]["consequence"]


def test_grounded_region_scope_excludes_additional_metadata_only_regions():
    result = _extract(
        _grounded_graph(),
        regions=[
            {"region_id": "coast", "name": "滨海区", "region_type": "coastal_zone"},
            {
                "region_id": "central",
                "name": "中心城区",
                "region_type": "residential_zone",
                "description": "人口密集居民生活区",
            },
        ],
    )

    refs = result.definitions[0]["risk_statement"]["region_refs"]
    assert [item["region_name"] for item in refs] == ["滨海区"]
    assert all(item["scope_basis"] != "scene_metadata_inference" for item in refs)


def test_validated_actor_references_keep_role_and_scope_provenance():
    result = _extract(
        _grounded_graph(),
        profiles=[{
            "agent_id": 7,
            "name": "滨海区卫生应急负责人",
            "profession": "卫生应急负责人",
            "primary_region": "滨海区",
            "agent_type": "human",
            "source_entity_uuid": "entity_health_office",
        }],
        validated_relation_graph={
            "edges": [{
                "source_agent_id": 7,
                "target_agent_id": 7,
                "mechanism_edge_ids": ["edge_exposure"],
                "mechanism": "负责滨海区暴露人群的卫生应急响应",
                "epistemic_status": "observed",
                "confidence": 0.9,
            }]
        },
    )

    actor = result.definitions[0]["risk_statement"]["actor_refs"][0]
    assert actor["actor_id"] == 7
    assert actor["actor_name"] == "滨海区卫生应急负责人"
    assert actor["profession"] == "卫生应急负责人"
    assert actor["primary_region"] == "滨海区"
    assert actor["scope_basis"] == "validated_relation"
    assert actor["epistemic_status"] == "observed"


def test_role_demands_scope_actor_refs_to_the_receptor_instead_of_every_relation_actor():
    result = _extract(
        _grounded_graph(),
        profiles=[
            {
                "agent_id": 1,
                "name": "滨海区综合协调员",
                "profession": "应急协调员",
                "role_demand_refs": ["demand_policy"],
            },
            {
                "agent_id": 2,
                "name": "滨海区受影响居民代表",
                "profession": "居民代表",
                "role_demand_refs": ["demand_population"],
            },
            {
                "agent_id": 3,
                "name": "滨海区交通运营主体",
                "profession": "交通运营主体",
                "role_demand_refs": ["demand_transport"],
            },
            {
                "agent_id": 4,
                "name": "新区受影响居民代表",
                "profession": "居民代表",
                "primary_region": "新区",
                "role_demand_refs": ["demand_population"],
            },
        ],
        validated_relation_graph={
            "edges": [
                {
                    "source_agent_id": 1,
                    "target_agent_id": 2,
                    "mechanism_edge_ids": ["edge_surge", "edge_exposure"],
                    "mechanism": "综合协调关系",
                    "epistemic_status": "inferred",
                    "confidence": 0.8,
                },
                {
                    "source_agent_id": 1,
                    "target_agent_id": 3,
                    "mechanism_edge_ids": ["edge_surge", "edge_exposure"],
                    "mechanism": "综合协调关系",
                    "epistemic_status": "inferred",
                    "confidence": 0.8,
                },
            ]
        },
        role_demands=[
            {
                "demand_id": "demand_policy",
                "demand_key": "policy_execution",
                "label_zh": "政策执行能力",
                "caused_by_mechanism_ids": ["edge_surge", "edge_exposure"],
                "caused_by_event_ids": ["source", "process", "resident"],
            },
            {
                "demand_id": "demand_population",
                "demand_key": "affected_population",
                "label_zh": "受影响居民响应能力",
                "caused_by_mechanism_ids": ["edge_exposure"],
                "caused_by_event_ids": ["resident"],
            },
            {
                "demand_id": "demand_transport",
                "demand_key": "transport_continuity",
                "label_zh": "交通连续性能力",
                "caused_by_mechanism_ids": ["edge_exposure"],
                "caused_by_event_ids": ["resident"],
            },
        ],
    )

    actors = result.definitions[0]["risk_statement"]["actor_refs"]
    assert [item["actor_id"] for item in actors] == [2]
    assert actors[0]["matched_role_demand_id"] == "demand_population"
    assert actors[0]["matched_role_demand_label"] == "受影响居民响应能力"
    assert actors[0]["scope_basis"] == "receptor_role_demand"


def test_unrelated_role_demands_do_not_fall_back_to_relation_actors():
    result = _extract(
        _grounded_graph(),
        profiles=[
            {
                "agent_id": 1,
                "name": "滨海区综合协调员",
                "profession": "应急协调员",
                "role_demand_refs": ["demand_policy"],
            },
            {
                "agent_id": 2,
                "name": "滨海区环境载体",
                "profession": "环境传播载体",
                "role_demand_refs": ["demand_carrier"],
            },
        ],
        validated_relation_graph={
            "edges": [{
                "source_agent_id": 1,
                "target_agent_id": 2,
                "mechanism_edge_ids": ["edge_surge", "edge_exposure"],
                "epistemic_status": "inferred",
                "confidence": 0.8,
            }]
        },
        role_demands=[
            {
                "demand_id": "demand_policy",
                "demand_key": "policy_execution",
                "label_zh": "政策执行能力",
                "caused_by_mechanism_ids": ["edge_surge", "edge_exposure"],
                "caused_by_event_ids": ["source", "process", "resident"],
            },
            {
                "demand_id": "demand_carrier",
                "demand_key": "environmental_carrier",
                "label_zh": "环境传播载体",
                "caused_by_mechanism_ids": ["edge_surge", "edge_exposure"],
                "caused_by_event_ids": ["source", "process", "resident"],
            },
        ],
    )

    assert result.definitions[0]["risk_statement"]["actor_refs"] == []


def test_entity_references_preserve_real_source_types_in_the_risk_contract():
    entities = [
        {
            "uuid": "entity_bay",
            "name": "滨海区",
            "labels": ["Entity", "EnvironmentalCarrier"],
            "summary": "风险传播经过的真实近岸水体",
        },
        {
            "uuid": "entity_estuary",
            "name": "海水倒灌",
            "attributes": {"entity_type": "Region"},
            "summary": "风险路径对应的真实空间单元",
        },
        {
            "uuid": "entity_resident",
            "name": "滨海区居民",
            "labels": ["Entity", "HumanActor"],
            "summary": "真实受影响人群",
        },
    ]
    refs = {
        item["entity_uuid"]: item
        for item in RiskCandidateExtractor()._matching_refs(
            "滨海区发生海水倒灌并影响滨海区居民",
            entities,
            "entity",
        )
    }
    assert refs["entity_bay"]["entity_type"] == "EnvironmentalCarrier"
    assert refs["entity_bay"]["labels"] == ["EnvironmentalCarrier"]
    assert refs["entity_bay"]["entity_summary"] == "风险传播经过的真实近岸水体"
    assert refs["entity_estuary"]["entity_type"] == "Region"
    assert refs["entity_resident"]["entity_type"] == "HumanActor"


def test_broad_event_copy_does_not_attach_incompatible_entities_to_every_risk():
    graph = {
        "nodes": [
            {"id": "source", "name": "放射性物质释放", "node_type": "source"},
            {
                "id": "ecology",
                "name": "生态受体影响",
                "node_type": "ecological",
                "description": "深圳湾、珠江口、脆弱群体、机场交通均可能受到影响。",
            },
            {
                "id": "mobility",
                "name": "交通与疏散承压",
                "node_type": "service",
                "description": "深圳湾、珠江口、脆弱群体、机场交通均可能受到影响。",
            },
        ],
        "edges": [
            {
                "id": "ecology_exposure",
                "source": "source",
                "target": "ecology",
                "mechanism": "污染物进入滨海区水体并影响生态受体",
                "evidence": ["深圳湾湿地生态监测记录"],
                "confidence": 0.9,
            },
            {
                "id": "mobility_pressure",
                "source": "source",
                "target": "mobility",
                "mechanism": "污染扩散增加机场交通与疏散压力",
                "evidence": ["深圳宝安国际机场运行记录"],
                "confidence": 0.9,
            },
        ],
    }
    result = _extract(
        graph,
        regions=[
            {
                "region_id": "shenzhen_wetland",
                "name": "深圳湾湿地",
                "region_type": "coastal_zone",
                "tags": ["湿地", "生态敏感"],
            },
            {
                "region_id": "nansha",
                "name": "南沙区",
                "region_type": "city",
                "description": "居民生活与治理响应区域",
            },
            {
                "region_id": "airport_region",
                "name": "深圳宝安国际机场",
                "region_type": "port",
                "tags": ["交通", "机场"],
            },
        ],
        entities=[
            {"uuid": "bay", "name": "深圳湾", "labels": ["Entity", "EnvironmentalCarrier"]},
            {"uuid": "estuary", "name": "珠江口", "labels": ["Entity", "Region"]},
            {
                "uuid": "people",
                "name": "脆弱群体",
                "labels": ["Entity", "HumanActor"],
                "summary": "生态事故中需要优先保护的真实人群",
            },
            {
                "uuid": "airport",
                "name": "深圳宝安国际机场",
                "labels": ["Entity", "Infrastructure"],
                "attributes": {"source_kind": "observed"},
            },
        ],
    )

    risks_by_family = {item["primary_family"]: item for item in result.definitions}
    ecological = risks_by_family["ecological_environment"]
    mobility = risks_by_family["mobility_logistics"]
    assert [
        item["entity_uuid"]
        for item in ecological["risk_statement"]["entity_refs"]
    ] == ["bay"]
    assert [item["region_name"] for item in ecological["risk_statement"]["region_refs"]] == ["深圳湾湿地"]
    assert [item["entity_uuid"] for item in mobility["risk_statement"]["entity_refs"]] == ["airport"]
    assert mobility["risk_statement"]["entity_refs"][0]["scope_basis"] == "scenario_text_mention"
    assert [item["region_name"] for item in mobility["risk_statement"]["region_refs"]] == ["深圳宝安国际机场"]


def test_entity_metadata_inference_resolves_a_real_typed_entity_without_full_name_match():
    refs = RiskCandidateExtractor()._entity_refs_for_candidate(
        path_corpus="污染事件造成机场交通与疏散压力",
        scope_corpus="交通与疏散承压",
        path_nodes=[],
        entities=[
            {
                "uuid": "airport",
                "name": "深圳宝安国际机场",
                "labels": ["Entity", "Infrastructure"],
                "attributes": {"source_kind": "observed"},
            },
            {
                "uuid": "inferred_proxy",
                "name": "机场响应代理",
                "labels": ["Entity", "Infrastructure"],
                "attributes": {"source_kind": "inferred", "category": "human_proxy"},
            },
        ],
        family="mobility_logistics",
    )

    assert [item["entity_uuid"] for item in refs] == ["airport"]
    assert refs[0]["scope_basis"] == "scene_metadata_inference"
    assert refs[0]["epistemic_status"] == "inferred"


def test_dangling_placeholder_internal_and_speculative_paths_are_rejected():
    dangling = _extract(
        {
            "nodes": [{"id": "source", "name": "高温", "node_type": "source"}],
            "edges": [{"id": "missing", "source": "source", "target": "unknown", "mechanism": "高温影响未知对象"}],
        }
    )
    assert dangling.definitions == []
    assert dangling.audit["dangling_reference_count"] == 1

    placeholder = _extract(
        {
            "nodes": [
                {"id": "source", "name": "高温", "node_type": "source"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "placeholder",
                    "source": "source",
                    "target": "resident",
                    "mechanism": "高温增加健康暴露",
                    "evidence": ["fallback"],
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert placeholder.definitions == []
    assert placeholder.audit["invalid_display_reference_count"] == 1

    internal_name = _extract(
        {
            "nodes": [
                {"id": "source", "name": "disaster_injection", "node_type": "source"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "internal",
                    "source": "source",
                    "target": "resident",
                    "mechanism": "扰动增加居民暴露",
                    "evidence": ["滨海区记录"],
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert internal_name.definitions == []

    speculative = _extract(
        {
            "nodes": [
                {"id": "source", "name": "未知扰动", "node_type": "source"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [{"id": "guess", "source": "source", "target": "resident", "confidence": 0.95}],
        }
    )
    assert speculative.definitions == []
    assert any("推测或降级机制边" in item.get("reason", "") for item in speculative.candidate_ledger)

    mixed_speculative = _extract(
        {
            "nodes": [
                {"id": "source", "name": "滨海区风暴潮", "node_type": "source"},
                {"id": "process", "name": "海水倒灌", "node_type": "process"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "observed",
                    "source": "source",
                    "target": "process",
                    "mechanism": "滨海区风暴潮造成海水倒灌",
                    "evidence": ["滨海区潮位记录"],
                    "confidence": 0.9,
                },
                {"id": "speculative", "source": "process", "target": "resident", "confidence": 0.9},
            ],
        }
    )
    assert mixed_speculative.definitions == []
    assert any("推测或降级机制边" in item.get("reason", "") for item in mixed_speculative.candidate_ledger)


def test_duplicate_paths_merge_and_initial_activation_is_capped_at_eight():
    graph = {
        "nodes": [
            {"id": "source", "name": "持续强降雨", "node_type": "source"},
            {"id": "p1", "name": "地表汇流", "node_type": "process"},
            {"id": "p2", "name": "道路积水", "node_type": "process"},
            {"id": "target", "name": "滨海区居民", "node_type": "human"},
        ],
        "edges": [
            {"id": "e1", "source": "source", "target": "p1", "mechanism": "降雨形成汇流", "evidence": ["滨海区降雨记录"], "confidence": 0.9},
            {"id": "e2", "source": "p1", "target": "p2", "mechanism": "汇流造成积水", "evidence": ["滨海区积水记录"], "confidence": 0.85},
            {"id": "e3a", "source": "p2", "target": "target", "mechanism": "积水增加居民暴露", "evidence": ["滨海区居民记录"], "confidence": 0.8},
            {"id": "e3b", "source": "p2", "target": "target", "mechanism": "积水阻断居民出行", "evidence": ["滨海区出行记录"], "confidence": 0.8},
        ],
    }
    merged = _extract(graph)
    assert len(merged.definitions) == 1
    assert len(merged.definitions[0]["mechanism_edge_ids"]) == 3
    assert set(merged.definitions[0]["mechanism_edge_ids"][:2]) == {"e1", "e2"}
    assert merged.definitions[0]["mechanism_edge_ids"][-1] in {"e3a", "e3b"}
    assert merged.definitions[0]["risk_statement"]["mechanism_edge_ids"] == merged.definitions[0]["mechanism_edge_ids"]
    assert set(merged.definitions[0]["mechanism_node_ids"]) == {"source", "p1", "p2", "target"}
    alternatives = merged.definitions[0]["alternative_mechanism_paths"]
    assert len(alternatives) == 2
    assert {
        edge_id
        for path in alternatives
        for edge_id in path["mechanism_edge_ids"]
    } == {"e1", "e2", "e3a", "e3b"}

    nodes = [{"id": "source", "name": "污染释放", "node_type": "source"}]
    edges = []
    for index in range(10):
        receptor_id = f"resident_{index}"
        nodes.append({"id": receptor_id, "name": f"滨海区居民群体{index + 1}", "node_type": "human", "confidence": 0.8})
        edges.append({
            "id": f"edge_{index}",
            "source": "source",
            "target": receptor_id,
            "mechanism": f"污染影响滨海区居民群体{index + 1}",
            "evidence": ["滨海区监测记录"],
            "confidence": 0.9,
        })
    capped = _extract({"nodes": nodes, "edges": edges}, max_active_risks=20)
    assert len(capped.definitions) == 8
    assert capped.audit["validated_candidate_count"] == 10
    assert len(capped.audit["inactive_validated_risk_ids"]) == 2


def test_inline_internal_tokens_and_generic_region_actor_expansion_are_rejected():
    embedded_internal = _extract(
        {
            "nodes": [
                {"id": "source", "name": "disaster_injection 已触发", "node_type": "source"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "internal_sentence",
                    "source": "source",
                    "target": "resident",
                    "mechanism": "扰动增加居民暴露",
                    "evidence": ["滨海区监测记录"],
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert embedded_internal.definitions == []
    assert embedded_internal.audit["invalid_display_reference_count"] == 1

    embedded_placeholder = _extract(
        {
            "nodes": [
                {"id": "source", "name": "高温", "node_type": "source"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "placeholder_sentence",
                    "source": "source",
                    "target": "resident",
                    "mechanism": "高温增加居民暴露",
                    "evidence": ["该关系来自 fallback_explicit 占位结果"],
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert embedded_placeholder.definitions == []


def test_only_mechanism_linked_actors_are_attached_and_duplicate_region_names_are_collapsed():
    result = _extract(
        _grounded_graph(),
        regions=[
            {"region_id": "coast", "name": "滨海区"},
            {"region_id": "coast_sub", "name": "滨海区"},
        ],
        profiles=[
            {"agent_id": 1, "name": "潮位监测员", "primary_region": "滨海区"},
            {"agent_id": 2, "name": "社区响应员", "primary_region": "滨海区"},
            {"agent_id": 3, "name": "未关联商户", "primary_region": "滨海区"},
        ],
        validated_relation_graph={
            "edges": [
                {
                    "source_agent_id": 1,
                    "target_agent_id": 2,
                    "mechanism_edge_ids": ["edge_surge", "edge_exposure"],
                    "epistemic_status": "observed",
                },
                {
                    "source_agent_id": 3,
                    "target_agent_id": 1,
                    "mechanism_edge_ids": ["edge_surge"],
                    "epistemic_status": "speculative",
                    "origin": "fallback_explicit",
                },
            ]
        },
    )
    risk = result.definitions[0]
    assert {item["actor_id"] for item in risk["scope"]["actors"]} == {1, 2}
    assert len(risk["scope"]["regions"]) == 1
    assert risk["scope"]["regions"][0]["region_name"] == "滨海区"


def test_speculative_actor_relation_does_not_downgrade_an_independent_mechanism_edge():
    result = _extract(
        {
            "nodes": [
                {"id": "source", "name": "外部扰动", "node_type": "source"},
                {"id": "process", "name": "介质传播", "node_type": "process"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "independent",
                    "source": "source",
                    "target": "process",
                    "mechanism": "扰动经介质传播",
                    "evidence": ["独立机制假设"],
                    "confidence": 0.9,
                },
                {
                    "id": "grounded",
                    "source": "process",
                    "target": "resident",
                    "mechanism": "介质传播增加滨海区居民暴露",
                    "evidence": ["滨海区现场记录"],
                    "confidence": 0.9,
                },
            ],
        },
        validated_relation_graph={
            "edges": [
                {
                    "mechanism_edge_ids": ["independent"],
                    "epistemic_status": "speculative",
                    "origin": "fallback_explicit",
                }
            ]
        },
    )

    assert len(result.definitions) == 1
    assert [item["epistemic_status"] for item in result.definitions[0]["evidence"]] == ["inferred", "observed"]


def test_region_matching_uses_real_source_features_not_shared_background_copy():
    result = _extract(
        {
            "nodes": [
                {"id": "source", "name": "伶仃洋释放源", "node_type": "source"},
                {"id": "process", "name": "污染扩散到深圳湾", "node_type": "process"},
                {"id": "wetland", "name": "深圳湾湿地生态受体", "node_type": "ecological"},
            ],
            "edges": [
                {
                    "id": "release",
                    "source": "source",
                    "target": "process",
                    "mechanism": "伶仃洋污染物沿水体扩散到深圳湾",
                    "evidence": ["伶仃洋监测记录"],
                    "confidence": 0.9,
                },
                {
                    "id": "exposure",
                    "source": "process",
                    "target": "wetland",
                    "mechanism": "污染物增加深圳湾湿地生态暴露",
                    "evidence": ["深圳湾生态记录"],
                    "confidence": 0.9,
                },
            ],
        },
        regions=[
            {
                "region_id": "south_water",
                "name": "南侧近岸水域",
                "description": "由 伶仃洋水域、珠江口 等 2 个空间要素归并出的近岸水域。用于表达珠江口伶仃洋区域。",
            },
            {
                "region_id": "east_wetland",
                "name": "东侧湿地生态带",
                "description": "由 深圳湾、香港湿地公园周边 等 2 个空间要素归并出的湿地生态带。用于表达珠江口伶仃洋区域。",
            },
            {
                "region_id": "north_water",
                "name": "北侧近岸水域",
                "description": "由 茅洲河 等 1 个空间要素归并出的近岸水域。用于表达珠江口伶仃洋区域。",
            },
        ],
    )

    assert [item["region_name"] for item in result.definitions[0]["scope"]["regions"]] == [
        "南侧近岸水域",
        "东侧湿地生态带",
    ]


def test_candidate_without_a_resolvable_scene_region_stays_in_the_audit_ledger():
    result = _extract(
        {
            "nodes": [
                {"id": "source", "name": "山火", "node_type": "source"},
                {"id": "resident", "name": "山区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "smoke",
                    "source": "source",
                    "target": "resident",
                    "mechanism": "山火烟尘增加山区居民暴露",
                    "evidence": ["山区居民监测记录"],
                    "confidence": 0.9,
                }
            ],
        },
        regions=[{"region_id": "coast", "name": "滨海区"}],
        entities=[{"uuid": "mountain_residents", "name": "山区居民"}],
    )

    assert result.definitions == []
    assert any("真实作用区域" in item.get("reason", "") for item in result.candidate_ledger)


def test_unresolvable_document_citation_is_removed_and_marked_without_losing_the_mechanism():
    result = _extract(
        {
            "nodes": [
                {"id": "source", "name": "污染释放", "node_type": "source"},
                {"id": "process", "name": "水体扩散", "node_type": "process"},
                {"id": "resident", "name": "滨海区居民", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "release",
                    "source": "source",
                    "target": "process",
                    "mechanism": "污染物从释放源进入水体",
                    "evidence": ["场景素材报告第10节：污染释放"],
                    "confidence": 0.9,
                },
                {
                    "id": "exposure",
                    "source": "process",
                    "target": "resident",
                    "mechanism": "水体扩散增加滨海区居民暴露",
                    "evidence": ["滨海区监测记录"],
                    "confidence": 0.9,
                },
            ],
        },
        document_text="## 1. 场景范围\n滨海区监测记录",
    )

    risk = result.definitions[0]
    assert [item["epistemic_status"] for item in risk["evidence"]] == ["inferred", "observed"]
    assert risk["evidence"][0]["summary"] == "机制推断：污染物从释放源进入水体"
    assert "第10节" not in risk["evidence"][0]["summary"]
    assert "unresolved_source_citation_removed" in risk["quality_flags"]
    assert "unresolved_source_citation_removed" in result.audit["quality_flags"]


def test_only_cross_region_three_node_feedback_becomes_compound_cascade():
    graph = {
        "nodes": [
            {"id": "a", "name": "滨海区供应压力", "node_type": "source"},
            {"id": "b", "name": "新区物流延迟", "node_type": "process"},
            {"id": "c", "name": "滨海区居民需求", "node_type": "human"},
        ],
        "edges": [
            {"id": "ab", "source": "a", "target": "b", "mechanism": "供应压力增加物流延迟", "evidence": ["滨海区供应记录"], "confidence": 0.9, "scope": "cross_region"},
            {"id": "bc", "source": "b", "target": "c", "mechanism": "物流延迟影响居民需求", "evidence": ["新区物流记录"], "confidence": 0.85},
            {"id": "ca", "source": "c", "target": "a", "mechanism": "居民需求反向放大供应压力", "evidence": ["滨海区需求记录"], "confidence": 0.85},
        ],
    }
    result = _extract(
        graph,
        regions=[
            {"region_id": "coast", "name": "滨海区"},
            {"region_id": "new", "name": "新区"},
        ],
    )
    compounds = [item for item in result.definitions if item["primary_family"] == "compound_cascade"]
    assert len(compounds) == 1
    assert compounds[0]["quality_flags"] == ["validated_cross_region_feedback_loop"]
    assert len(compounds[0]["mechanism_node_ids"]) == 3
    assert compounds[0]["title"] == "滨海区供应压力与滨海区居民需求相互放大风险"

    local_graph = {**graph, "edges": [{**item, "scope": "local"} for item in graph["edges"]]}
    local = _extract(local_graph, regions=[{"region_id": "coast", "name": "滨海区"}])
    assert not any(item["primary_family"] == "compound_cascade" for item in local.definitions)


def test_incomplete_event_graph_never_falls_back_to_map_neighbour_cycles():
    result = _extract(
        {
            "source": "scenario_mechanism_graph",
            "nodes": [
                {
                    "id": "event_wind_signal",
                    "name": "8号风球袭港",
                    "node_type": "source",
                    "target_region_ids": ["南山区", "元朗区"],
                }
            ],
            "edges": [],
        },
        regions=[
            {"region_id": "南山区", "name": "南山区", "region_type": "city"},
            {"region_id": "深圳湾", "name": "深圳湾", "region_type": "coastal_zone"},
            {"region_id": "香港湿地公园周边", "name": "香港湿地公园周边", "region_type": "residential_zone"},
            {"region_id": "元朗区", "name": "元朗区", "region_type": "residential_zone"},
        ],
        entities=[
            {"uuid": "wetland", "name": "香港湿地公园周边", "labels": ["Entity", "EcologicalReceptor"]},
            {"uuid": "bay", "name": "深圳湾", "labels": ["Entity", "EnvironmentalCarrier"]},
        ],
        transport_edges=[
            {
                "edge_id": "neighbor_nanshan_bay",
                "source_region_id": "南山区",
                "target_region_id": "深圳湾",
                "channel_type": "environmental_link",
                "origin": "rule_inferred",
                "evidence": {"ordering": "neighbor_fallback"},
                "confidence": 0.52,
            },
            {
                "edge_id": "neighbor_bay_nanshan",
                "source_region_id": "深圳湾",
                "target_region_id": "南山区",
                "channel_type": "environmental_link",
                "origin": "rule_inferred",
                "evidence": {"ordering": "neighbor_fallback"},
                "confidence": 0.52,
            },
        ],
    )

    assert result.definitions == []
    assert result.audit["graph_source"] == "scenario_mechanism_graph"
    assert result.audit["zero_reason"] == "场景尚未形成引用完整的机制关系"


def test_map_neighbour_cycles_are_rejected_instead_of_becoming_compound_risks():
    region_names = ["南山区", "深圳湾", "香港湿地公园周边", "元朗区"]
    transport_edges = []
    for source, target in (
        ("南山区", "深圳湾"),
        ("深圳湾", "香港湿地公园周边"),
        ("香港湿地公园周边", "元朗区"),
        ("元朗区", "南山区"),
    ):
        transport_edges.append({
            "edge_id": f"transport_{source}_{target}",
            "source_region_id": source,
            "target_region_id": target,
            "channel_type": "environmental_link",
            "origin": "rule_inferred",
            "evidence": {"ordering": "neighbor_fallback"},
            "confidence": 0.52,
        })

    result = _extract(
        {},
        regions=[{"region_id": name, "name": name} for name in region_names],
        entities=[],
        transport_edges=transport_edges,
    )

    assert result.definitions == []
    assert any(
        item.get("reason") == "地图空间邻接或运输连通关系不能单独构成风险因果路径"
        for item in result.candidate_ledger
    )


def test_short_typhoon_paths_produce_specific_ecology_and_mobility_risks():
    result = _extract(
        {
            "nodes": [
                {
                    "id": "typhoon",
                    "name": "8号风球袭港",
                    "node_type": "hazard",
                    "confidence": 0.82,
                    "target_region_ids": [
                        "region_深圳市南山区周边",
                        "feature_context_admin_district_南山区",
                    ],
                },
                {
                    "id": "wind",
                    "name": "持续强风影响",
                    "node_type": "process",
                    "confidence": 0.82,
                    "target_region_ids": ["feature_context_admin_district_南山区"],
                },
                {
                    "id": "surge",
                    "name": "风暴潮与沿海淹没",
                    "node_type": "hazard",
                    "confidence": 0.7,
                    "target_region_ids": ["region_深圳市南山区周边"],
                },
                {
                    "id": "traffic",
                    "name": "交通与疏散系统",
                    "node_type": "service",
                    "confidence": 0.7,
                    "target_region_ids": ["feature_context_admin_district_南山区"],
                },
                {
                    "id": "ecology",
                    "name": "敏感生态系统",
                    "node_type": "ecological",
                    "confidence": 0.7,
                    "target_region_ids": ["region_深圳市南山区周边"],
                },
            ],
            "edges": [
                {"id": "wind_field", "source": "typhoon", "target": "wind", "mechanism": "台风风场形成持续强风", "evidence": ["风球对应持续强风条件"], "confidence": 0.82},
                {"id": "traffic_disruption", "source": "wind", "target": "traffic", "mechanism": "持续强风降低交通与疏散能力", "evidence": ["强风超过交通安全运行条件"], "confidence": 0.7},
                {"id": "coastal_inundation", "source": "typhoon", "target": "surge", "mechanism": "台风驱动风暴潮", "evidence": ["台风风场推高近岸水位"], "confidence": 0.7},
                {"id": "wetland_disturbance", "source": "surge", "target": "ecology", "mechanism": "风暴潮扰动沿海湿地生态受体", "evidence": ["沿海增水进入湿地生态空间"], "confidence": 0.7},
            ],
        },
        regions=[
            {
                "region_id": "nanshan_logistics",
                "name": "南山区·物流接口带",
                "parent_region_id": "南山区",
                "region_type": "industrial_logistics_zone",
                "land_use_class": "transport",
                "layer": "subregion",
            },
            {
                "region_id": "nanshan_transition",
                "name": "南山区·综合过渡区",
                "parent_region_id": "南山区",
                "region_type": "transition_zone",
                "land_use_class": "urban",
                "tags": ["transition", "urban"],
                "layer": "subregion",
            },
            {"region_id": "shenzhen_bay", "name": "深圳湾", "region_type": "coastal_zone", "tags": ["湿地", "生态"]},
            {"region_id": "hk_wetland", "name": "香港湿地公园周边", "region_type": "wetland", "tags": ["保护区"]},
        ],
        entities=[
            {
                "uuid": "feature_context_admin_district_南山区",
                "name": "南山区",
                "labels": ["Entity", "Region"],
            },
            {"uuid": "wetland", "name": "香港湿地公园周边", "labels": ["Entity", "EcologicalReceptor"], "summary": "湿地生态与候鸟栖息地"},
            {"uuid": "bay", "name": "深圳湾", "labels": ["Entity", "EnvironmentalCarrier"], "summary": "重要海湾与湿地生态空间"},
        ],
        simulation_requirement="8号风球袭港，停工停学。",
    )

    risks = {item["primary_family"]: item for item in result.definitions}
    assert set(risks) == {"ecological_environment", "mobility_logistics"}
    assert risks["ecological_environment"]["title"] == "香港湿地公园周边功能受损风险"
    assert risks["ecological_environment"]["risk_statement"]["receptor_name"] == "香港湿地公园周边"
    assert {
        item["region_id"]
        for item in risks["ecological_environment"]["risk_statement"]["region_refs"]
    } == {"shenzhen_bay", "hk_wetland"}
    assert risks["mobility_logistics"]["title"] == "南山区·物流接口带交通与疏散系统中断风险"
    assert risks["mobility_logistics"]["risk_statement"]["region_refs"][0]["region_id"] == "nanshan_logistics"
    assert "nanshan_transition" not in {
        item["region_id"]
        for item in risks["mobility_logistics"]["risk_statement"]["region_refs"]
    }
    assert all(item["primary_family"] != "compound_cascade" for item in result.definitions)


def test_runtime_agent_coordination_cycle_is_not_a_compound_risk():
    result = _extract(
        {},
        regions=[
            {"region_id": "coast", "name": "滨海区"},
            {"region_id": "port", "name": "港口区"},
            {"region_id": "city", "name": "中心城区"},
        ],
        entities=[],
        profiles=[
            {"agent_id": 1, "name": "滨海区应急协调员", "primary_region": "滨海区", "profession": "应急协调员"},
            {"agent_id": 2, "name": "港口区应急协调员", "primary_region": "港口区", "profession": "应急协调员"},
            {"agent_id": 3, "name": "中心城区应急协调员", "primary_region": "中心城区", "profession": "应急协调员"},
        ],
        agent_relationships=[
            {
                "edge_id": "dynamic::1::2::governance_coordination",
                "source_agent_id": 1,
                "target_agent_id": 2,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["滨海区与港口区临时协调记录"],
            },
            {
                "edge_id": "dynamic::2::3::governance_coordination",
                "source_agent_id": 2,
                "target_agent_id": 3,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["港口区与中心城区临时协调记录"],
            },
            {
                "edge_id": "dynamic::3::1::governance_coordination",
                "source_agent_id": 3,
                "target_agent_id": 1,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["中心城区与滨海区临时协调记录"],
            },
        ],
    )

    assert result.definitions == []
    assert any(
        item.get("reason") == "纯主体协同关系闭环不构成风险因果反馈"
        for item in result.candidate_ledger
    )


def test_runtime_agent_coordination_chain_is_not_a_risk_path():
    result = _extract(
        {},
        regions=[
            {"region_id": "coast", "name": "滨海区"},
            {"region_id": "port", "name": "港口区"},
            {"region_id": "city", "name": "中心城区"},
        ],
        entities=[],
        profiles=[
            {"agent_id": 1, "name": "滨海区应急协调员", "primary_region": "滨海区", "profession": "应急协调员"},
            {"agent_id": 2, "name": "港口区应急协调员", "primary_region": "港口区", "profession": "应急协调员"},
            {"agent_id": 3, "name": "中心城区应急协调员", "primary_region": "中心城区", "profession": "应急协调员"},
        ],
        agent_relationships=[
            {
                "edge_id": "dynamic::1::2::governance_coordination",
                "source_agent_id": 1,
                "target_agent_id": 2,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["滨海区与港口区临时协调记录"],
            },
            {
                "edge_id": "dynamic::2::3::governance_coordination",
                "source_agent_id": 2,
                "target_agent_id": 3,
                "edge_type": "governance_coordination",
                "origin": "heuristic_emergent",
                "scope": "cross_region",
                "confidence": 0.8,
                "evidence": ["港口区与中心城区临时协调记录"],
            },
        ],
    )

    assert result.definitions == []
    assert any(
        item.get("reason") == "纯主体关系路径缺少压力源、传播过程和真实受体"
        for item in result.candidate_ledger
    )


def test_taxonomy_is_controlled_but_tags_remain_scenario_specific():
    result = _extract(
        _grounded_graph(),
        scenario_state_schema={
            "resident_safety_exposure": {
                "label": "居民安全暴露",
                "description": "滨海区居民在倒灌过程中的安全暴露程度。",
                "polarity": "higher_is_worse",
                "legacy_metric": "exposure_score",
            }
        },
    )
    risk = result.definitions[0]
    assert risk["primary_family"] in RISK_FAMILIES
    assert risk["tags"]
    assert any("滨海区居民" in tag or "海水倒灌" in tag for tag in risk["tags"])
    assert all(item not in {"blue", "brown", "disaster_injection"} for item in risk["tags"])
    assert risk["monitoring_metrics"][0]["key"] == "resident_safety_exposure"
    assert risk["monitoring_metrics"][0]["legacy_metric"] == "exposure_score"


def test_monitoring_metrics_prefer_the_specific_receptor_over_generic_health_words():
    result = _extract(
        {
            "nodes": [
                {"id": "source", "name": "污染释放", "node_type": "source"},
                {"id": "process", "name": "污染水体接触", "node_type": "process"},
                {"id": "receptor", "name": "滨海区脆弱群体健康风险", "node_type": "human"},
            ],
            "edges": [
                {
                    "id": "spread",
                    "source": "source",
                    "target": "process",
                    "mechanism": "污染物进入滨海区水体",
                    "evidence": ["滨海区水体记录"],
                    "confidence": 0.9,
                },
                {
                    "id": "contact",
                    "source": "process",
                    "target": "receptor",
                    "mechanism": "污染水体接触增加滨海区脆弱群体暴露",
                    "evidence": ["滨海区健康记录"],
                    "confidence": 0.9,
                },
            ],
        },
        scenario_state_schema={
            "ecosystem_health": {"label": "生态系统健康指数", "description": "生态系统健康状态"},
            "public_panic": {"label": "公众恐慌指数", "description": "居民和游客的恐慌程度"},
            "vulnerable_group_exposure": {"label": "脆弱群体暴露风险", "description": "老年人和儿童的暴露程度"},
        },
    )

    assert result.definitions[0]["monitoring_metrics"][0]["key"] == "vulnerable_group_exposure"
    assert "生态系统健康指数" not in [item["label"] for item in result.definitions[0]["monitoring_metrics"]]


@pytest.mark.parametrize(
    ("source_name", "process_name", "receptor_name", "receptor_type", "expected_family"),
    [
        ("近海放射性核素释放", "洋流输运与沉积", "滨海区湿地生态受体", "ecological", "ecological_environment"),
        ("长期少雨", "土壤含水率持续下降", "滨海区森林生态受体", "ecological", "ecological_environment"),
        ("放射性物质释放", "污染物海洋传播", "滨海区人群暴露", "receptor", "health_safety"),
        ("放射性物质释放", "污染物海洋传播", "滨海区交通与疏散承压", "service", "mobility_logistics"),
        ("放射性物质释放", "污染物海洋传播", "滨海区渔业与海产品污染", "receptor", "resource_supply"),
        ("放射性物质释放", "污染物海洋传播", "滨海区科学城科研活动中断", "receptor", "infrastructure_continuity"),
        ("跨区封控政策", "应急资源重新调度", "滨海区政府应急响应", "governance", "governance_response"),
        ("未经核实的污染消息", "社交媒体重复传播", "滨海区公众信任", "receptor", "information_trust"),
    ],
)
def test_nuclear_ecology_policy_and_information_scenarios_stay_specific(
    source_name,
    process_name,
    receptor_name,
    receptor_type,
    expected_family,
):
    result = _extract(
        {
            "nodes": [
                {"id": "source", "name": source_name, "node_type": "source", "confidence": 0.9},
                {"id": "process", "name": process_name, "node_type": "process", "confidence": 0.85},
                {
                    "id": "receptor",
                    "name": receptor_name,
                    "node_type": receptor_type,
                    "description": (
                        "完整场景同时包含湿地生态、人群暴露、机场港口交通、渔业供应、"
                        "科研设施、公众信任和政府治理压力。"
                    ),
                    "confidence": 0.8,
                },
            ],
            "edges": [
                {"id": "edge_1", "source": "source", "target": "process", "mechanism": f"{source_name}引起{process_name}", "evidence": ["滨海区来源记录"], "confidence": 0.9},
                {"id": "edge_2", "source": "process", "target": "receptor", "mechanism": f"{process_name}作用于{receptor_name}", "evidence": ["滨海区监测记录"], "confidence": 0.85},
            ],
        }
    )
    assert result.definitions
    risk = result.definitions[0]
    assert risk["primary_family"] == expected_family
    assert receptor_name.replace("生态受体", "") in risk["title"]
    assert source_name in risk["risk_statement"]["trigger_name"]
    assert receptor_name == risk["risk_statement"]["receptor_name"]
    assert risk["title"] not in {
        "水位与生态服务耦合风险",
        "交通与关键设施可达性风险",
        "预警响应与公共服务承压风险",
        "居民与游客暴露风险",
        "生态恢复与长期退化风险",
    }


def test_deterministic_titles_do_not_repeat_an_already_concrete_consequence():
    extractor = RiskCandidateExtractor()

    assert extractor._deterministic_title(
        {"name": "交通与疏散承压"},
        "mobility_logistics",
    ) == "交通与疏散承压风险"
    assert extractor._deterministic_title(
        {"name": "生态受体影响"},
        "ecological_environment",
    ) == "生态受体影响风险"
