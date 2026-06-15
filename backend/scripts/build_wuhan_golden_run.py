#!/usr/bin/env python3
"""
Build and validate the Wuhan golden case frozen replay artifacts.

The script is intentionally safe by default: scaffold/freeze/validate never call
LLM clients. The high-cost live golden run should be wired here only after the
downstream data contracts are stable.
"""

from __future__ import annotations

import argparse
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
)


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


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
    manifest["freeze_note"] = "Deterministic scaffold artifacts; no live LLM run has been consumed."
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
    profiles = _read_json(os.path.join(sim_dir, "profiles_full.json"), [])
    relationships = _read_json(os.path.join(sim_dir, "agent_relationship_graph.json"), [])
    animation = _read_json(manifest["animation"]["file"], {})
    frames = animation.get("frames") or []
    nodes = (animation.get("layout") or {}).get("nodes") or []
    edges = (animation.get("layout") or {}).get("edges") or []

    _require(config.get("scenario_mode") == "crisis_mode", "scenario_mode must be crisis_mode", errors)
    _require(config.get("hazard_template_id") == "pest_disease_ecology", "hazard template mismatch", errors)
    _require(config.get("diffusion_template") == "bio_ecological_transmission", "diffusion template mismatch", errors)
    _require(config.get("search_mode") == "deep_search", "search_mode must be deep_search", errors)
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
    _require(len(profiles) >= 240, f"agent count too low: {len(profiles)}", errors)
    _require(len(relationships) >= 800, f"relationship edge count too low: {len(relationships)}", errors)
    _require(len(nodes) >= 200, f"animation node count too low: {len(nodes)}", errors)
    _require(len(edges) >= 800, f"animation edge count too low: {len(edges)}", errors)
    _require(len(frames) == 37, f"animation frame count must be 37, got {len(frames)}", errors)
    _require((frames[0] or {}).get("round") == 0 if frames else False, "frame 0 baseline missing", errors)
    _require((frames[-1] or {}).get("round") == 36 if frames else False, "frame 36 missing", errors)

    summary = {
        "case_id": manifest["case_id"],
        "agents": len(profiles),
        "relationships": len(relationships),
        "animation_nodes": len(nodes),
        "animation_edges": len(edges),
        "animation_frames": len(frames),
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
