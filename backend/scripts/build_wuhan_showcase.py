#!/usr/bin/env python3
"""Build and validate the curated Wuhan COVID V2 showcase."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any, Dict, Iterable, List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.golden_case_service import GoldenCaseService  # noqa: E402
from app.services.wuhan_showcase_builder import (  # noqa: E402
    WUHAN_V2_ARTIFACT_CONTRACT_VERSION,
    WUHAN_V2_CASE_ID,
    WuhanShowcaseBuilder,
)
from app.services.spatial_evidence import (  # noqa: E402
    FACILITY_QUERY_PLAN_CONTRACT_VERSION,
    SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION,
)


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def fail_if(condition: bool, message: str, errors: List[str]) -> None:
    if condition:
        errors.append(message)


def ids(rows: Iterable[Dict[str, Any]], *keys: str) -> set[str]:
    result: set[str] = set()
    for row in rows:
        for key in keys:
            value = str(row.get(key) or "").strip()
            if value:
                result.add(value)
                break
    return result


def validate_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    config = read_json(manifest["simulation"]["config"])
    animation = read_json(manifest["animation"]["file"])
    runtime = read_json(manifest["artifacts"]["runtime"])
    analysis = read_json(manifest["artifacts"]["analysis"])
    foundation = read_json(manifest["artifacts"]["foundation"])
    scenario = read_json(manifest["artifacts"]["scenario"])
    facility_query_plan = read_json(manifest["artifacts"]["facility_query_plan"])
    spatial_snapshot = read_json(manifest["artifacts"]["spatial_refinement_snapshot"])
    agent_request = read_json(manifest["simulation"]["agent_planning_request"])

    regions = config.get("region_graph") or []
    anchors = config.get("subregion_graph") or []
    agents = config.get("agent_configs") or []
    relationships = config.get("agent_relationship_graph") or []
    frames = animation.get("frames") or []
    layout_nodes = (animation.get("layout") or {}).get("nodes") or []
    layout_edges = (animation.get("layout") or {}).get("edges") or []
    timeline_events = (animation.get("timeline") or {}).get("events") or []
    dynamic_relation_events = runtime.get("relationship_event_ledger") or []
    dynamic_relation_ids = ids(dynamic_relation_events, "edge_id")
    impact_scope = analysis.get("impact_scope") or {}
    evidence_index = analysis.get("evidence_index") or []
    observed_evidence = [item for item in evidence_index if item.get("provenance") == "observed/public_source"]
    curated_evidence = [item for item in evidence_index if item.get("provenance") == "curated_projection"]

    fail_if(manifest.get("artifact_contract_version") != WUHAN_V2_ARTIFACT_CONTRACT_VERSION, "产物合同版本不匹配", errors)
    fail_if(manifest.get("generation_mode") != "curated_target_state", "生成模式必须为策划目标态", errors)
    fail_if(manifest.get("artifact_mode") != "frozen", "案例必须为冻结产物", errors)
    fail_if(manifest.get("default_step") != 1, "默认入口必须为 Step 1", errors)
    fail_if(len(regions) != 12, f"宏观场景数量应为12，实际{len(regions)}", errors)
    fail_if(len(anchors) != 36, f"空间锚点数量应为36，实际{len(anchors)}", errors)
    fail_if(len(agents) != 240, f"Agent数量应为240，实际{len(agents)}", errors)
    fail_if(sum(1 for item in agents if item.get("representation_level") == "functional") != 72, "核心Agent数量应为72", errors)
    fail_if(len({item.get("archetype_id") for item in agents}) < 24, "角色原型少于24种", errors)
    fail_if(len(relationships) != 1800, f"静态关系应为1800，实际{len(relationships)}", errors)
    fail_if(len(layout_nodes) != 288, f"布局节点应为288，实际{len(layout_nodes)}", errors)
    fail_if(not 2000 <= len(layout_edges) <= 2400, f"布局关系应为2000-2400，实际{len(layout_edges)}", errors)
    fail_if(len(frames) != 37 or [item.get("round") for item in frames] != list(range(37)), "必须连续生成R0-R36共37帧", errors)
    fail_if((animation.get("timeline") or {}).get("playback_duration_ms") != 203000, "连续回放时钟必须为203000毫秒", errors)
    fail_if(len(timeline_events) < 696, f"Timeline事件少于696，实际{len(timeline_events)}", errors)
    fail_if(len(runtime.get("round_snapshots") or []) != 36, "运行账本必须恰好36轮", errors)
    fail_if(len(dynamic_relation_ids) != 168, f"动态关系应为168条，实际{len(dynamic_relation_ids)}", errors)
    fail_if(len(dynamic_relation_events) != 216, f"动态关系事件应为216条，实际{len(dynamic_relation_events)}", errors)
    fail_if(
        impact_scope.get("dynamic_relation_count") != len(dynamic_relation_ids),
        "Step 4动态关系数量必须与运行账本一致",
        errors,
    )
    fail_if(
        impact_scope.get("dynamic_relation_event_count") != len(dynamic_relation_events),
        "Step 4动态关系事件数量必须与运行账本一致",
        errors,
    )
    fail_if(len(analysis.get("turning_points") or []) < 6, "Step 4关键转折未填满", errors)
    fail_if(len(analysis.get("risk_outcomes") or []) != 5, "Step 4风险结果应为5项", errors)
    fail_if(len(analysis.get("intervention_observations") or []) != 6, "Step 4政策观察应为6项", errors)
    fail_if(len(evidence_index) != 175, f"Step 4证据索引应为175组，实际{len(evidence_index)}", errors)
    fail_if(len(observed_evidence) != 8, f"公开来源证据应为8组，实际{len(observed_evidence)}", errors)
    fail_if(len(curated_evidence) != 167, f"策划账本证据应为167组，实际{len(curated_evidence)}", errors)
    fail_if(bool(analysis.get("counterfactual_branches")), "V2不得包含反事实分支", errors)
    fail_if(foundation.get("contract_version") != "background-foundation.v2", "Step 1合同不匹配", errors)
    fail_if(scenario.get("contract_version") != "scenario-definition.v2", "Step 2合同不匹配", errors)
    fail_if(runtime.get("contract_version") != "runtime-ledger.v2", "Step 3合同不匹配", errors)
    fail_if(analysis.get("contract_version") != "analysis-bundle.v2", "Step 4合同不匹配", errors)
    fail_if(
        facility_query_plan.get("contract_version") != FACILITY_QUERY_PLAN_CONTRACT_VERSION,
        "设施查询计划合同不匹配",
        errors,
    )
    fail_if(
        spatial_snapshot.get("contract_version") != SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION,
        "空间细化快照合同不匹配",
        errors,
    )
    fail_if(
        (agent_request.get("facility_query_plan_ref") or {}).get("content_hash")
        != facility_query_plan.get("content_hash"),
        "Agent请求未引用设施查询计划",
        errors,
    )
    fail_if(
        (agent_request.get("spatial_refinement_snapshot_ref") or {}).get("content_hash")
        != spatial_snapshot.get("content_hash"),
        "Agent请求未引用空间细化快照",
        errors,
    )
    fail_if(
        int((agent_request.get("spatial_evidence_summary") or {}).get("covered_r3_count") or 0) != 0,
        "策划地点不得计为已核验R3设施",
        errors,
    )
    fail_if(bool(spatial_snapshot.get("selected_r3_features")), "策划地点不得进入R3已选证据", errors)
    fail_if(bool(spatial_snapshot.get("r4_model_units")), "未核验R3设施不得生成R4内部单元", errors)
    fail_if(
        {str(item.get("evidence_grade") or "") for item in spatial_snapshot.get("source_versions") or []}
        != {"D", "S"},
        "V2空间来源必须保留D/S证据等级",
        errors,
    )

    anchor_ids = ids(anchors, "anchor_id", "region_id")
    agent_ids = {str(item.get("agent_id")) for item in agents}
    region_ids = ids(regions, "region_id")
    source_ids = ids(WuhanShowcaseBuilder().source_manifest.get("sources") or [], "id")
    for agent in agents:
        fail_if(str(agent.get("home_subregion_id") or "") not in anchor_ids, f"Agent空间引用悬空: {agent.get('agent_id')}", errors)
        fail_if(not agent.get("storyline_ids"), f"Agent缺少故事线: {agent.get('agent_id')}", errors)
    for relation in relationships:
        fail_if(str(relation.get("source_agent_id")) not in agent_ids or str(relation.get("target_agent_id")) not in agent_ids, f"关系Agent引用悬空: {relation.get('edge_id')}", errors)
    for edge in config.get("transport_edges") or []:
        fail_if(str(edge.get("source_region_id")) not in region_ids or str(edge.get("target_region_id")) not in region_ids, f"交通关系引用悬空: {edge.get('edge_id')}", errors)
    for anchor in anchors:
        for source_ref in anchor.get("source_refs") or []:
            fail_if(str(source_ref) not in source_ids, f"地点来源引用悬空: {anchor.get('anchor_id')}", errors)

    forbidden = ("radiation_monitoring", "road_clearance", "道路清障", "灾害疏散")
    visible_corpus = json.dumps({"foundation": foundation, "scenario": scenario, "analysis": analysis}, ensure_ascii=False)
    for token in forbidden:
        fail_if(token in visible_corpus, f"残留非疫情模板能力: {token}", errors)

    if errors:
        raise RuntimeError("\n".join(f"- {item}" for item in errors))
    return {
        "regions": len(regions),
        "anchors": len(anchors),
        "agents": len(agents),
        "layout_edges": len(layout_edges),
        "frames": len(frames),
        "timeline_events": len(timeline_events),
        "artifact_hashes": manifest.get("artifact_hashes") or {},
    }


def deterministic_check(repeats: int = 3) -> None:
    definition = GoldenCaseService.get_case(WUHAN_V2_CASE_ID)
    signatures = []
    with tempfile.TemporaryDirectory(prefix="kaleido-wuhan-v2-") as temp_root:
        for index in range(repeats):
            root = os.path.join(temp_root, f"build-{index + 1}")
            manifest = WuhanShowcaseBuilder().compile(definition, root)
            animation = read_json(manifest["animation"]["file"])
            signatures.append({
                "artifact_hashes": manifest.get("artifact_hashes") or {},
                "node_ids": [item.get("id") for item in (animation.get("layout") or {}).get("nodes") or []],
                "coordinates": [(item.get("lat"), item.get("lon")) for item in (animation.get("layout") or {}).get("nodes") or []],
                "frame_rounds": [item.get("round") for item in animation.get("frames") or []],
                "timeline_ids": [item.get("id") for item in (animation.get("timeline") or {}).get("events") or []],
            })
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise RuntimeError("同一输入重复构建结果不一致")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate", "verify"), nargs="?", default="verify")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_V2_CASE_ID, force=args.force or args.command == "build")
    summary = validate_manifest(manifest)
    if args.command == "verify":
        deterministic_check(3)
    print(json.dumps({"case_id": WUHAN_V2_CASE_ID, **summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
