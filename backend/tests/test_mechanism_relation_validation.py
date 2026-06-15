"""M7 honest-validation regression tests.

Locks in the fix for the circular `evidence_coverage = 1.0 by construction`
metric: empty evidence used to be backfilled with the placeholder string
`llm_relation_candidate` and then counted as evidence. Now edges are classified
observed / inferred / speculative and only externally-anchored edges count.
"""

from app.services.envfish_models import EnvAgentProfile
from app.services.mechanism_simulation_service import MechanismSimulationPlanner


def _profile(agent_id: int, name: str, region: str) -> EnvAgentProfile:
    return EnvAgentProfile(
        agent_id=agent_id,
        username=f"agent_{agent_id}",
        name=name,
        node_family="EcologicalReceptor",
        role_type="receptor",
        bio="",
        persona="",
        profession="",
        primary_region=region,
    )


def _planner() -> MechanismSimulationPlanner:
    # No LLM client: we only exercise the deterministic validation path.
    return MechanismSimulationPlanner(llm_client=None)


def _anchor():
    planner = _planner()
    context = {
        "document_excerpt": "茅洲河是主要排水路径，污染经水流进入深圳湾。",
        "simulation_requirement": "",
        "regions": [{"name": "茅洲河", "description": ""}, {"name": "深圳湾", "description": ""}],
        "subregions": [],
        "entities": [],
    }
    return planner, planner._build_anchor_index(context, [])


def test_coverage_is_not_one_by_construction():
    planner, anchor_index = _anchor()
    profiles = [_profile(1, "上游源", "茅洲河"), _profile(2, "下游受体", "深圳湾")]
    candidates = [
        # observed: mechanism + evidence reference real named regions
        {
            "source_agent_id": 1,
            "target_agent_id": 2,
            "relation_label": "上游污染影响下游",
            "mechanism": "茅洲河污染经水流影响深圳湾受体。",
            "evidence": ["茅洲河是主要排水路径"],
        },
        # inferred: has a mechanism but evidence is a placeholder (must be stripped)
        {
            "source_agent_id": 1,
            "target_agent_id": 2,
            "relation_label": "次生间接关联",
            "mechanism": "两者可能存在间接关联。",
            "evidence": ["llm_relation_candidate"],
        },
        # speculative: no mechanism, no evidence
        {
            "source_agent_id": 2,
            "target_agent_id": 1,
            "relation_label": "占位边",
            "mechanism": "",
            "evidence": [],
        },
    ]

    edges, ledger = planner._validate_relations(candidates, profiles, anchor_index=anchor_index)
    assert len(edges) == 3

    statuses = sorted(edge.epistemic_status for edge in edges)
    assert statuses == ["inferred", "observed", "speculative"]

    # placeholder evidence must never survive into an edge
    for edge in edges:
        assert "llm_relation_candidate" not in edge.evidence

    graph = planner._validated_relation_graph(edges)
    assert graph["epistemic_breakdown"] == {"observed": 1, "inferred": 1, "speculative": 1}
    # 1 grounded out of 3 -> 0.333, NOT 1.0
    assert graph["evidence_coverage"] == round(1 / 3, 3)
    assert graph["evidence_coverage"] < 1.0
    assert graph["grounded_edge_count"] == 1
    assert graph["speculative_edge_count"] == 1


def test_fallback_edges_are_speculative_and_excluded_from_coverage():
    planner = _planner()
    profiles = [
        _profile(1, "源", "区域A"),
        _profile(2, "受体", "区域B"),
        _profile(3, "旁观", "区域A"),
    ]
    fallback_edges, _ledger = planner._fallback_relation_edges(
        profiles=profiles,
        existing_relationships=[],
        already_seen=set(),
        mechanism_graph={"edges": []},
        target_count=4,
    )
    assert fallback_edges, "expected fallback filler to be produced"
    for edge in fallback_edges:
        assert edge.epistemic_status == "speculative"
        assert edge.validation_status == "speculative_fallback"
        # no fake evidence such as ["fallback_explicit", name, name]
        assert edge.evidence == []

    graph = planner._validated_relation_graph(fallback_edges)
    # all speculative -> zero grounded -> coverage 0.0
    assert graph["evidence_coverage"] == 0.0
    assert graph["speculative_edge_count"] == len(fallback_edges)
