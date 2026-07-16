#!/usr/bin/env python3
"""
Build and validate the Wuhan golden case frozen replay artifacts.

The script is intentionally safe by default: scaffold/freeze/validate never call
LLM clients. The high-cost live golden run should be wired here only after the
downstream data contracts are stable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.golden_case_service import (  # noqa: E402
    GoldenCaseService,
    WUHAN_ARTIFACT_CONTRACT_VERSION,
    WUHAN_CASE_ID,
    WUHAN_SPATIAL_FIXTURE_ID,
    WUHAN_SPATIAL_GROUNDING,
)
from app.services.simulation_animation_service import (  # noqa: E402
    ANIMATION_CONTRACT_VERSION,
    TIMELINE_CONTRACT_VERSION,
)
from app.services.spatial_evidence import (  # noqa: E402
    FACILITY_QUERY_PLAN_CONTRACT_VERSION,
    SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION,
)


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _require(condition: bool, message: str, errors: List[str]) -> None:
    if not condition:
        errors.append(message)


def scaffold(force: bool = False) -> Dict[str, Any]:
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID, force=force)
    print(f"[scaffold] ready: {manifest['case_id']} -> {GoldenCaseService.case_root(WUHAN_CASE_ID)}")
    return manifest


def full_run(execute_live: bool = False) -> Dict[str, Any]:
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    if execute_live:
        raise RuntimeError(
            "Live LLM golden run is not enabled in this script yet. "
            "Finalize the downstream data contracts first, then wire the normal runner here explicitly."
        )
    print("[full_run] skipped live LLM run; using deterministic scaffold artifacts for frozen replay.")
    return manifest


def freeze() -> Dict[str, Any]:
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    manifest_path = os.path.join(GoldenCaseService.case_root(WUHAN_CASE_ID), "manifest.json")
    manifest["freeze_status"] = "frozen_replay_ready"
    manifest["freeze_note"] = "确定性冻结回放产物；构建过程未调用在线模型。"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(f"[freeze] manifest updated: {manifest_path}")
    return manifest


def validate() -> Dict[str, Any]:
    manifest = GoldenCaseService.ensure_scaffold(WUHAN_CASE_ID)
    errors: List[str] = []
    sim_dir = manifest["simulation"]["dir"]
    required_files = [
        os.path.join(GoldenCaseService.case_root(WUHAN_CASE_ID), "manifest.json"),
        manifest["scene"]["scene_seed"],
        manifest["simulation"]["config"],
        manifest["simulation"]["latest_snapshot"],
        manifest["simulation"]["scenario_planning_input"],
        manifest["simulation"]["mechanism_graph"],
        manifest["simulation"]["temporal_plan"],
        manifest["simulation"]["policy_plan"],
        manifest["simulation"]["role_demands"],
        manifest["simulation"]["agent_planning_request"],
        manifest["simulation"]["facility_query_plan"],
        manifest["simulation"]["spatial_refinement_snapshot"],
        manifest["simulation"]["spread_event_ledger"],
        manifest["report"]["markdown"],
        manifest["report"]["outline"],
        manifest["animation"]["file"],
        os.path.join(sim_dir, "animation.json"),
        os.path.join(sim_dir, "round_state_matrix.jsonl"),
        os.path.join(sim_dir, "agent_interaction_ledger.jsonl"),
        os.path.join(sim_dir, "dynamic_edge_ledger.jsonl"),
        os.path.join(sim_dir, "risk_events.jsonl"),
    ]
    for path in required_files:
        _require(os.path.exists(path), f"missing required artifact: {path}", errors)

    config = _read_json(manifest["simulation"]["config"], {})
    state = _read_json(os.path.join(sim_dir, "state.json"), {})
    planning = _read_json(manifest["simulation"]["scenario_planning_input"], {})
    mechanism_graph = _read_json(manifest["simulation"]["mechanism_graph"], {})
    temporal_plan = _read_json(manifest["simulation"]["temporal_plan"], {})
    policy_plan = _read_json(manifest["simulation"]["policy_plan"], [])
    role_demands = _read_json(manifest["simulation"]["role_demands"], [])
    agent_request = _read_json(manifest["simulation"]["agent_planning_request"], {})
    facility_query_plan = _read_json(manifest["simulation"]["facility_query_plan"], {})
    spatial_snapshot = _read_json(manifest["simulation"]["spatial_refinement_snapshot"], {})
    injected_variables = _read_json(os.path.join(sim_dir, "injected_variables.json"), [])
    regions = _read_json(os.path.join(sim_dir, "region_graph_snapshot.json"), [])
    transport_edges = _read_json(os.path.join(sim_dir, "transport_edges.json"), [])
    spread_events = _read_jsonl(manifest["simulation"]["spread_event_ledger"])
    profiles = _read_json(os.path.join(sim_dir, "profiles_full.json"), [])
    relationships = _read_json(os.path.join(sim_dir, "agent_relationship_graph.json"), [])
    animation = _read_json(manifest["animation"]["file"], {})
    simulation_animation = _read_json(os.path.join(sim_dir, "animation.json"), {})
    frames = animation.get("frames") or []
    layout = animation.get("layout") or {}
    nodes = layout.get("nodes") or []
    edges = layout.get("edges") or []
    timeline = animation.get("timeline") or {}
    timeline_events = timeline.get("events") or []

    _require(config.get("scenario_mode") == "crisis_mode", "scenario_mode must be crisis_mode", errors)
    _require(config.get("hazard_template_id") == "pest_disease_ecology", "hazard template mismatch", errors)
    _require(config.get("diffusion_template") == "bio_ecological_transmission", "diffusion template mismatch", errors)
    _require(config.get("search_mode") == "deep_search", "search_mode must be deep_search", errors)
    _require(
        config.get("simulation_architecture") == "llm_mechanism_v1",
        "simulation_architecture must be llm_mechanism_v1",
        errors,
    )
    _require(
        manifest.get("artifact_contract_version") == WUHAN_ARTIFACT_CONTRACT_VERSION,
        "artifact contract version mismatch",
        errors,
    )
    _require(
        config.get("artifact_contract_version") == WUHAN_ARTIFACT_CONTRACT_VERSION,
        "simulation config artifact contract version mismatch",
        errors,
    )
    _require(config.get("reference_time") == "2019-12-22T00:00:00+08:00", "reference_time mismatch", errors)
    _require((config.get("time_config") or {}).get("total_rounds") == 36, "total_rounds must be 36", errors)
    _require((config.get("time_config") or {}).get("minutes_per_round") == 4320, "minutes_per_round must be 4320", errors)
    effort_snapshot = config.get("effort_snapshot") or {}
    _require(effort_snapshot.get("effort_level") == "high", "golden effort level must be high", errors)
    _require(effort_snapshot.get("locked") is True, "golden effort snapshot must be locked", errors)
    _require(
        planning.get("contract_version") == "scenario_planning.v2",
        "scenario planning contract mismatch",
        errors,
    )
    _require(bool(planning.get("planning_input_id")), "scenario planning input id missing", errors)
    _require(len(str(planning.get("content_hash") or "")) == 64, "scenario planning content hash missing", errors)
    _require(
        config.get("scenario_planning_input") == planning,
        "simulation config does not embed the frozen scenario planning input",
        errors,
    )
    _require(
        config.get("event_mechanism_graph") == mechanism_graph,
        "event mechanism graph mismatch",
        errors,
    )
    _require(config.get("mechanism_graph") == mechanism_graph, "runtime mechanism graph mismatch", errors)
    _require(config.get("temporal_plan") == temporal_plan, "temporal plan mismatch", errors)
    _require(config.get("policy_plan") == policy_plan, "policy plan mismatch", errors)
    _require(config.get("role_demands") == role_demands, "role demand mismatch", errors)
    _require(
        config.get("assumptions") == planning.get("assumptions"),
        "scenario assumptions mismatch",
        errors,
    )
    _require(config.get("agent_plan_source") == "legacy_adapter", "agent plan source mismatch", errors)
    _require(agent_request.get("agent_plan_source") == "legacy_adapter", "agent adapter artifact mismatch", errors)
    _require(
        (agent_request.get("scenario_planning_ref") or {}).get("content_hash") == planning.get("content_hash"),
        "agent adapter does not reference the frozen planning hash",
        errors,
    )
    _require(
        facility_query_plan.get("contract_version") == FACILITY_QUERY_PLAN_CONTRACT_VERSION,
        "facility query plan contract mismatch",
        errors,
    )
    _require(
        spatial_snapshot.get("contract_version") == SPATIAL_REFINEMENT_SNAPSHOT_CONTRACT_VERSION,
        "spatial refinement snapshot contract mismatch",
        errors,
    )
    _require(
        (agent_request.get("facility_query_plan_ref") or {}).get("content_hash")
        == facility_query_plan.get("content_hash"),
        "agent adapter facility query plan reference mismatch",
        errors,
    )
    _require(
        (agent_request.get("spatial_refinement_snapshot_ref") or {}).get("content_hash")
        == spatial_snapshot.get("content_hash"),
        "agent adapter spatial snapshot reference mismatch",
        errors,
    )
    _require(
        int((agent_request.get("spatial_evidence_summary") or {}).get("covered_r3_count") or 0) == 0,
        "synthetic fixture candidates must not be counted as covered R3 evidence",
        errors,
    )
    _require(
        not (spatial_snapshot.get("selected_r3_features") or []),
        "synthetic fixture candidates must not be selected as R3 evidence",
        errors,
    )
    _require(
        not (spatial_snapshot.get("r4_model_units") or []),
        "R4 units must not be synthesized from unresolved V1 fixture candidates",
        errors,
    )
    _require(
        {str(item.get("evidence_grade") or "") for item in spatial_snapshot.get("source_versions") or []}
        == {"S"},
        "V1 spatial fixture source must retain evidence grade S",
        errors,
    )
    _require(
        state.get("planning_content_hash") == planning.get("content_hash"),
        "frozen state planning hash mismatch",
        errors,
    )
    _require(state.get("effort_snapshot") == effort_snapshot, "frozen state effort snapshot mismatch", errors)
    _require(len(mechanism_graph.get("nodes") or []) >= 6, "mechanism graph node count too low", errors)
    _require(len(mechanism_graph.get("edges") or []) >= 5, "mechanism graph edge count too low", errors)
    _require(temporal_plan.get("total_rounds") == 36, "Step 2 temporal plan must cover 36 rounds", errors)
    _require(len(policy_plan) == 3, "Step 2 policy plan must contain 3 measures", errors)
    _require(len(role_demands) >= 5, "Step 2 role demand count too low", errors)
    _require(len(profiles) >= 240, f"agent count too low: {len(profiles)}", errors)
    _require(len(relationships) >= 800, f"relationship edge count too low: {len(relationships)}", errors)
    _require(len(nodes) >= 200, f"animation node count too low: {len(nodes)}", errors)
    _require(len(edges) >= 800, f"animation edge count too low: {len(edges)}", errors)
    _require(
        layout.get("geographic_grounding") == WUHAN_SPATIAL_GROUNDING,
        "animation layout spatial grounding mismatch",
        errors,
    )
    _require(layout.get("map_seed_id") is None, "golden layout must not claim a map seed", errors)
    _require(
        (layout.get("data_quality") or {}).get("spatial_fixture_id") == WUHAN_SPATIAL_FIXTURE_ID
        and (layout.get("data_quality") or {}).get("fixture_ready") is True
        and (layout.get("data_quality") or {}).get("observed") is False,
        "golden layout fixture quality metadata missing",
        errors,
    )
    for node in nodes:
        attrs = node.get("attributes") or {}
        _require(
            node.get("is_geographic") is True
            and attrs.get("is_geographic") is True
            and attrs.get("placement") == "curated_fixture"
            and attrs.get("coordinate_grounding") == WUHAN_SPATIAL_GROUNDING
            and attrs.get("coordinates_observed") is False
            and attrs.get("spatial_fixture_id") == WUHAN_SPATIAL_FIXTURE_ID,
            f"golden layout node spatial grounding missing: {node.get('id')}",
            errors,
        )
    for edge in [item for item in edges if item.get("fact_type") == "transport_edge"]:
        attrs = edge.get("attributes") or {}
        _require(
            attrs.get("is_route_edge") is True
            and attrs.get("route_grounding") == WUHAN_SPATIAL_GROUNDING
            and attrs.get("route_observed") is False
            and attrs.get("spatial_fixture_id") == WUHAN_SPATIAL_FIXTURE_ID,
            f"golden transport route grounding missing: {edge.get('id')}",
            errors,
        )
    _require(len(frames) == 37, f"animation frame count must be 37, got {len(frames)}", errors)
    _require((frames[0] or {}).get("round") == 0 if frames else False, "frame 0 baseline missing", errors)
    _require((frames[-1] or {}).get("round") == 36 if frames else False, "frame 36 missing", errors)
    _require(animation == simulation_animation, "animation artifact copies are not identical", errors)
    _require(
        (animation.get("meta") or {}).get("animation_contract_version") == ANIMATION_CONTRACT_VERSION,
        "animation contract version mismatch",
        errors,
    )
    _require(
        (animation.get("meta") or {}).get("timeline_contract_version") == TIMELINE_CONTRACT_VERSION,
        "animation timeline meta version mismatch",
        errors,
    )
    _require(
        (animation.get("meta") or {}).get("artifact_contract_version") == WUHAN_ARTIFACT_CONTRACT_VERSION,
        "animation golden artifact contract version mismatch",
        errors,
    )
    _require(
        timeline.get("contract_version") == TIMELINE_CONTRACT_VERSION,
        "embedded timeline contract mismatch",
        errors,
    )
    _require(
        timeline.get("source_mode") == "curated_fixture_ledgers",
        "golden timeline must identify curated fixture ledgers",
        errors,
    )
    _require(
        timeline.get("edge_reference_contract") == "split-path-related.v1",
        "golden timeline split edge contract missing",
        errors,
    )
    _require(
        (timeline.get("grounding") or {}).get("mode") == "curated_deterministic_fixture",
        "golden timeline grounding must be curated_deterministic_fixture",
        errors,
    )
    _require(
        (timeline.get("grounding") or {}).get("projection") == "golden_fixture_projection",
        "golden timeline projection marker missing",
        errors,
    )
    _require(int(timeline.get("observed_event_count") or 0) == 0, "golden fixture must not claim observed events", errors)
    _require(int(timeline.get("fallback_event_count") or 0) == 0, "timeline fallback events are not allowed", errors)
    _require(len(timeline_events) >= 600, f"timeline event count too low: {len(timeline_events)}", errors)
    event_ids = [str(event.get("id") or "") for event in timeline_events]
    _require(len(event_ids) == len(set(event_ids)), "timeline event ids are not unique", errors)
    _require(
        [int(event.get("sequence") or 0) for event in timeline_events]
        == list(range(1, len(timeline_events) + 1)),
        "timeline sequences are not contiguous",
        errors,
    )
    edge_ids = {str(edge.get("id") or "") for edge in edges}
    timeline_edge_refs = {
        str(edge_id)
        for event in timeline_events
        for edge_id in event.get("edge_ids") or []
        if str(edge_id or "")
    }
    _require(
        timeline_edge_refs.issubset(edge_ids),
        f"timeline has missing layout edge refs: {sorted(timeline_edge_refs - edge_ids)[:5]}",
        errors,
    )
    for event in timeline_events:
        path_edge_ids = [str(item) for item in event.get("path_edge_ids") or [] if str(item)]
        related_edge_ids = [str(item) for item in event.get("related_edge_ids") or [] if str(item)]
        _require(
            event.get("edge_reference_contract") == "split-path-related.v1",
            f"timeline split edge contract missing: {event.get('id')}",
            errors,
        )
        _require(
            not set(path_edge_ids).intersection(related_edge_ids),
            f"timeline path/related edge refs overlap: {event.get('id')}",
            errors,
        )
        _require(
            list(event.get("edge_ids") or []) == [*path_edge_ids, *related_edge_ids],
            f"timeline compatibility edge union diverged: {event.get('id')}",
            errors,
        )
    event_id_set = set(event_ids)
    parent_refs = {
        str(parent_id)
        for event in timeline_events
        for parent_id in event.get("parent_event_ids") or []
        if str(parent_id or "")
    }
    root_refs = {
        str(event.get("root_event_id") or "")
        for event in timeline_events
        if str(event.get("root_event_id") or "")
    }
    _require(parent_refs.issubset(event_id_set), "timeline has unresolved parent refs", errors)
    _require(root_refs.issubset(event_id_set), "timeline has unresolved root refs", errors)

    region_ids = {str(item.get("region_id") or "") for item in regions}
    layout_node_ids = {str(node.get("id") or "") for node in nodes}
    transport_by_id = {
        str(edge.get("edge_id") or ""): edge
        for edge in transport_edges
        if str(edge.get("edge_id") or "")
    }
    variable_by_id = {
        str(item.get("variable_id") or ""): item
        for item in injected_variables
        if str(item.get("variable_id") or "")
    }
    spread_ids = [str(event.get("event_id") or "") for event in spread_events]
    spread_by_id = {str(event.get("event_id") or ""): event for event in spread_events}
    _require(bool(spread_events), "spread event ledger must not be empty", errors)
    _require(len(spread_ids) == len(set(spread_ids)), "spread event ids are not unique", errors)
    roots = [event for event in spread_events if int(event.get("hop") or 0) == 0]
    _require(len(roots) == 1, f"spread ledger must contain one root, got {len(roots)}", errors)
    if roots:
        root = roots[0]
        _require(root.get("source_region") == "jianghan_market_corridor", "spread root source mismatch", errors)
        _require(root.get("target_region") == "jianghan_market_corridor", "spread root target mismatch", errors)
        _require(root.get("root_event_id") == root.get("event_id"), "spread root must reference itself", errors)
        _require(not list(root.get("parent_event_ids") or []), "spread root must not have a parent", errors)
        variable = variable_by_id.get(str(root.get("source_variable_id") or "")) or {}
        _require(
            "jianghan_market_corridor" in list(variable.get("target_regions") or []),
            "spread root is not grounded in the injected Jianghan variable",
            errors,
        )
    for spread in spread_events:
        event_id = str(spread.get("event_id") or "")
        hop = int(spread.get("hop") or 0)
        round_num = int(spread.get("round") or 0)
        source_region = str(spread.get("source_region") or "")
        target_region = str(spread.get("target_region") or "")
        parent_ids = [str(item) for item in spread.get("parent_event_ids") or [] if str(item)]
        _require(bool(event_id), "spread event id missing", errors)
        _require(0 <= round_num <= 36, f"spread round out of bounds: {event_id}", errors)
        _require(source_region in region_ids, f"spread source region missing: {source_region}", errors)
        _require(target_region in region_ids, f"spread target region missing: {target_region}", errors)
        _require(f"region::{source_region}" in layout_node_ids, f"spread source layout node missing: {source_region}", errors)
        _require(f"region::{target_region}" in layout_node_ids, f"spread target layout node missing: {target_region}", errors)
        _require(
            spread.get("causal_source_type") == "golden_fixture_projection"
            and spread.get("grounding_mode") == "curated_deterministic_fixture"
            and spread.get("observed") is False,
            f"spread grounding is dishonest or incomplete: {event_id}",
            errors,
        )
        _require(str(spread.get("source_variable_id") or "") in variable_by_id, f"spread variable ref missing: {event_id}", errors)
        _require(
            list(spread.get("path_edge_ids") or [])
            == ([str(spread.get("transport_edge_id"))] if spread.get("transport_edge_id") else []),
            f"spread path edge refs diverged: {event_id}",
            errors,
        )
        _require(not list(spread.get("related_edge_ids") or []), f"spread related edge refs must be empty: {event_id}", errors)
        if hop == 0:
            continue
        _require(len(parent_ids) == 1, f"spread child must have one explicit parent: {event_id}", errors)
        parent = spread_by_id.get(parent_ids[0]) if parent_ids else None
        _require(parent is not None, f"spread parent ref missing: {event_id}", errors)
        edge_id = str(spread.get("transport_edge_id") or "")
        edge = transport_by_id.get(edge_id)
        _require(edge is not None, f"spread transport edge ref missing: {event_id}", errors)
        _require(spread.get("edge_id") == edge_id, f"spread layout edge alias mismatch: {event_id}", errors)
        if parent:
            _require(hop == int(parent.get("hop") or 0) + 1, f"spread hop discontinuity: {event_id}", errors)
            _require(spread.get("root_event_id") == parent.get("root_event_id"), f"spread root changed: {event_id}", errors)
            _require(source_region == parent.get("target_region"), f"spread chain endpoint mismatch: {event_id}", errors)
        if edge:
            travel_time = max(1, int(edge.get("travel_time_rounds") or 1))
            _require(edge.get("directionality") == "directed", f"spread edge is not directed: {edge_id}", errors)
            _require(edge.get("source_region_id") == source_region, f"spread edge source mismatch: {event_id}", errors)
            _require(edge.get("target_region_id") == target_region, f"spread edge target mismatch: {event_id}", errors)
            _require(int(spread.get("delay_rounds") or 0) == travel_time, f"spread travel delay mismatch: {event_id}", errors)
            if parent:
                _require(round_num == int(parent.get("round") or 0) + travel_time, f"spread arrival round mismatch: {event_id}", errors)

    diffusion_events = [event for event in timeline_events if event.get("phase") == "environment_diffusion"]
    diffusion_by_id = {str(event.get("id") or ""): event for event in diffusion_events}
    _require(len(diffusion_events) == len(spread_events) > 0, "timeline diffusion count does not match spread ledger", errors)
    _require(max((int(event.get("hop") or 0) for event in diffusion_events), default=0) >= 3, "timeline lacks a multi-hop diffusion chain", errors)
    for event in diffusion_events:
        event_id = str(event.get("id") or "")
        hop = int(event.get("hop") or 0)
        parents = [str(item) for item in event.get("parent_event_ids") or [] if str(item)]
        source_regions = {str(item) for item in (event.get("source") or {}).get("region_ids") or []}
        target_regions = {str(item) for item in (event.get("target") or {}).get("region_ids") or []}
        source_nodes = {str(item) for item in (event.get("source") or {}).get("node_ids") or []}
        target_nodes = {str(item) for item in (event.get("target") or {}).get("node_ids") or []}
        _require(len(source_regions) == 1 and source_regions.issubset(region_ids), f"timeline diffusion source ref missing: {event_id}", errors)
        _require(len(target_regions) == 1 and target_regions.issubset(region_ids), f"timeline diffusion target ref missing: {event_id}", errors)
        _require(bool(source_nodes) and source_nodes.issubset(layout_node_ids), f"timeline diffusion source node missing: {event_id}", errors)
        _require(bool(target_nodes) and target_nodes.issubset(layout_node_ids), f"timeline diffusion target node missing: {event_id}", errors)
        _require(0 <= int(event.get("round") or 0) <= 36, f"timeline diffusion round out of bounds: {event_id}", errors)
        _require(
            (event.get("grounding") or {}).get("mode") == "curated_deterministic_fixture"
            and (event.get("grounding") or {}).get("projection") == "golden_fixture_projection"
            and (event.get("grounding") or {}).get("observed") is False,
            f"timeline diffusion grounding is dishonest: {event_id}",
            errors,
        )
        cause = event.get("cause") or {}
        _require(cause.get("type") == "golden_fixture_projection", f"timeline diffusion cause missing: {event_id}", errors)
        _require(str(cause.get("source_variable_id") or "") in variable_by_id, f"timeline diffusion variable ref missing: {event_id}", errors)
        root_id = str(event.get("root_event_id") or "")
        _require(root_id in diffusion_by_id, f"timeline diffusion root unresolved: {event_id}", errors)
        if hop == 0:
            _require(root_id == event_id and not parents, f"timeline diffusion root metadata invalid: {event_id}", errors)
            _require(not list(event.get("path_edge_ids") or []), f"timeline diffusion root must not have path refs: {event_id}", errors)
            _require(not list(event.get("related_edge_ids") or []), f"timeline diffusion root must not have related refs: {event_id}", errors)
        else:
            _require(len(parents) == 1 and parents[0] in diffusion_by_id, f"timeline diffusion parent unresolved: {event_id}", errors)
            parent = diffusion_by_id.get(parents[0]) if parents else None
            if parent:
                _require(hop == int(parent.get("hop") or 0) + 1, f"timeline diffusion hop discontinuity: {event_id}", errors)
                _require(root_id == parent.get("root_event_id"), f"timeline diffusion root changed: {event_id}", errors)
            cause_edge_id = str(cause.get("transport_edge_id") or "")
            cause_edge = transport_by_id.get(cause_edge_id)
            _require(cause_edge is not None, f"timeline diffusion transport edge missing: {event_id}", errors)
            _require(list(event.get("path_edge_ids") or []) == [cause_edge_id], f"timeline diffusion path refs diverged: {event_id}", errors)
            _require(not list(event.get("related_edge_ids") or []), f"timeline diffusion related refs must be empty: {event_id}", errors)
            if parent and cause_edge:
                travel_time = max(1, int(cause_edge.get("travel_time_rounds") or 1))
                _require(int(event.get("round") or 0) == int(parent.get("round") or 0) + travel_time, f"timeline diffusion time order invalid: {event_id}", errors)
    _require(
        all(isinstance(frame.get("timeline_event_ids"), list) for frame in frames),
        "every animation frame must carry timeline_event_ids",
        errors,
    )

    animation_digest = _sha256(manifest["animation"]["file"])
    simulation_animation_digest = _sha256(os.path.join(sim_dir, "animation.json"))
    spread_digest = _sha256(manifest["simulation"]["spread_event_ledger"])
    _require(animation_digest == simulation_animation_digest, "animation copy hashes differ", errors)
    summary = {
        "case_id": manifest["case_id"],
        "agents": len(profiles),
        "relationships": len(relationships),
        "animation_nodes": len(nodes),
        "animation_edges": len(edges),
        "animation_frames": len(frames),
        "timeline_contract_version": timeline.get("contract_version"),
        "timeline_events": len(timeline_events),
        "diffusion_events": len(diffusion_events),
        "diffusion_max_hop": max((int(event.get("hop") or 0) for event in diffusion_events), default=0),
        "animation_sha256": animation_digest,
        "spread_ledger_sha256": spread_digest,
        "mechanism_nodes": len(mechanism_graph.get("nodes") or []),
        "mechanism_edges": len(mechanism_graph.get("edges") or []),
        "policy_plans": len(policy_plan),
        "role_demands": len(role_demands),
        "errors": errors,
    }
    if errors:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(f"[validate] ok: {json.dumps(summary, ensure_ascii=False)}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Wuhan golden frozen replay artifacts.")
    parser.add_argument(
        "--stage",
        choices=["scaffold", "full_run", "freeze", "validate", "all"],
        default="scaffold",
        help="Pipeline stage to run. all = scaffold -> full_run -> freeze -> validate.",
    )
    parser.add_argument("--force", action="store_true", help="Regenerate scaffold artifacts from scratch.")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Reserved for the future high-cost LLM run; currently raises unless wired explicitly.",
    )
    args = parser.parse_args()

    if args.stage == "scaffold":
        scaffold(force=args.force)
    elif args.stage == "full_run":
        full_run(execute_live=args.execute_live)
    elif args.stage == "freeze":
        freeze()
    elif args.stage == "validate":
        validate()
    elif args.stage == "all":
        scaffold(force=args.force)
        full_run(execute_live=args.execute_live)
        freeze()
        validate()


if __name__ == "__main__":
    main()
