"""
EnvFish region-level simulation runner.

This is a constrained, semi-quantitative eco-social sandbox. It does not solve
physical equations; it produces region-level spread and human-nature feedback
using structured LLM output with deterministic validation and rule-based
fallbacks.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, ".."))
_project_root = os.path.abspath(os.path.join(_backend_dir, ".."))
sys.path.insert(0, _backend_dir)

from dotenv import load_dotenv

from app.services.envfish_models import (  # noqa: E402
    DEFAULT_TEMPLATE_RULES,
    clamp_probability,
    clamp_score,
    dump_json,
    merge_state_vectors,
    normalize_state_vector,
    score_band,
)
from app.services.simulation_ipc import CommandType, SimulationIPCServer  # noqa: E402
from app.utils.llm_client import LLMClient  # noqa: E402

if os.path.exists(os.path.join(_project_root, ".env")):
    load_dotenv(os.path.join(_project_root, ".env"))


def append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_search_mode(value: Any) -> str:
    normalized = str(value or "fast").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"deep", "deepsearch"}:
        return "deep_search"
    if normalized == "deep_search":
        return "deep_search"
    return "fast"


class EnvFishRuntime:
    def __init__(self, config_path: str, max_rounds: Optional[int] = None, no_wait: bool = False):
        self.config_path = os.path.abspath(config_path)
        with open(self.config_path, "r", encoding="utf-8") as handle:
            self.config = json.load(handle)

        self.sim_dir = os.path.dirname(self.config_path)
        self.no_wait = no_wait
        self.template = self.config.get("diffusion_template", "generic")
        self.template_rules = DEFAULT_TEMPLATE_RULES.get(self.template, DEFAULT_TEMPLATE_RULES["generic"])
        total_rounds = int(self.config.get("time_config", {}).get("total_rounds", 8))
        self.total_rounds = min(total_rounds, max_rounds) if max_rounds else total_rounds
        self.minutes_per_round = int(self.config.get("time_config", {}).get("minutes_per_round", 60))
        self.reference_time = str(self.config.get("reference_time") or "")
        self.temporal_profile = deepcopy(self.config.get("temporal_profile") or {})
        self.region_graph = deepcopy(self.config.get("region_graph") or [])
        self.subregion_graph = deepcopy(self.config.get("subregion_graph") or [])
        self.transport_edges = deepcopy(self.config.get("transport_edges") or [])
        self.actor_profiles = deepcopy(self.config.get("actor_profiles") or self.config.get("agent_configs") or [])
        self.agent_relationship_graph = deepcopy(self.config.get("agent_relationship_graph") or [])
        self.region_agent_index = deepcopy(self.config.get("region_agent_index") or {})
        self.interaction_policies = deepcopy(self.config.get("interaction_policies") or {})
        self.runtime_limits = deepcopy(self.config.get("runtime_limits") or {})
        self.risk_objects = deepcopy(self.config.get("risk_objects") or [])
        self.diffusion_context = deepcopy(self.config.get("diffusion_context") or {})
        self.search_mode = normalize_search_mode(
            self.config.get("search_mode") or self.interaction_policies.get("search_mode") or "fast"
        )
        self.injections = deepcopy(self.config.get("injected_variables") or [])
        self.current_round = 0
        self.latest_summary = {}
        self.pending_transfers: List[Dict[str, Any]] = []
        self.closed = False

        self.twitter_dir = os.path.join(self.sim_dir, "twitter")
        self.reddit_dir = os.path.join(self.sim_dir, "reddit")
        os.makedirs(self.twitter_dir, exist_ok=True)
        os.makedirs(self.reddit_dir, exist_ok=True)

        self.twitter_log = os.path.join(self.twitter_dir, "actions.jsonl")
        self.reddit_log = os.path.join(self.reddit_dir, "actions.jsonl")
        self.spread_log = os.path.join(self.sim_dir, "spread_event_ledger.jsonl")
        self.agent_interaction_log = os.path.join(self.sim_dir, "agent_interaction_ledger.jsonl")
        self.dynamic_edge_log = os.path.join(self.sim_dir, "dynamic_edge_ledger.jsonl")
        self.state_matrix_log = os.path.join(self.sim_dir, "round_state_matrix.jsonl")
        self.intervention_log = os.path.join(self.sim_dir, "intervention_log.jsonl")
        self.interview_log = os.path.join(self.sim_dir, "interviews.jsonl")
        self.latest_snapshot_path = os.path.join(self.sim_dir, "latest_round_snapshot.json")
        self.region_graph_path = os.path.join(self.sim_dir, "region_graph_snapshot.json")
        self.subregion_graph_path = os.path.join(self.sim_dir, "subregion_graph_snapshot.json")
        self.transport_edges_path = os.path.join(self.sim_dir, "transport_edges_snapshot.json")

        dump_json(self.region_graph_path, self.region_graph)
        dump_json(self.subregion_graph_path, self.subregion_graph)

        self.region_lookup = {item["region_id"]: item for item in self.region_graph}
        self.subregion_lookup = {item["region_id"]: item for item in self.subregion_graph}
        self.transport_edges = self._normalize_transport_edges(self.transport_edges)
        if not self.transport_edges:
            self.transport_edges = self._build_legacy_transport_edges()
        self.transport_edges_by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._rebuild_transport_edge_index()
        dump_json(self.transport_edges_path, self.transport_edges)
        self.actor_lookup = {int(item.get("agent_id", idx)): item for idx, item in enumerate(self.actor_profiles)}
        self.agents_by_region: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.agents_by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.agents_by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.agents_by_influence_region: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.relationships_by_source: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for edge in self.agent_relationship_graph:
            try:
                self.relationships_by_source[int(edge.get("source_agent_id"))].append(edge)
            except Exception:
                continue
        for actor in self.actor_profiles:
            primary_region = str(actor.get("primary_region") or actor.get("home_region_id") or "")
            if primary_region:
                self.agents_by_region[primary_region].append(actor)
            agent_type = str(actor.get("agent_type") or "").lower()
            agent_subtype = str(actor.get("agent_subtype") or "").lower()
            if agent_type:
                self.agents_by_type[agent_type].append(actor)
            if agent_subtype:
                self.agents_by_subtype[agent_subtype].append(actor)
            for region_id in actor.get("influenced_regions") or []:
                region_key = str(region_id or "").strip()
                if region_key:
                    self.agents_by_influence_region[region_key].append(actor)

        self.agent_risk_lookup: Dict[int, List[str]] = defaultdict(list)
        self.risk_actor_lookup: Dict[str, List[int]] = defaultdict(list)
        self.risk_region_lookup: Dict[str, List[str]] = defaultdict(list)
        for risk in self.risk_objects:
            if not isinstance(risk, dict):
                continue
            risk_id = str(risk.get("risk_object_id") or risk.get("title") or "").strip()
            if not risk_id:
                continue
            regions = []
            for region_id in (risk.get("primary_regions") or []) + (risk.get("region_scope") or []):
                region_key = str(region_id or "").strip()
                if region_key and region_key not in regions:
                    regions.append(region_key)
            self.risk_region_lookup[risk_id] = regions
            actor_ids: List[int] = []
            for cluster in risk.get("affected_clusters") or []:
                if not isinstance(cluster, dict):
                    continue
                for actor_id in cluster.get("actor_ids") or []:
                    if isinstance(actor_id, int):
                        actor_ids.append(actor_id)
                    elif str(actor_id or "").isdigit():
                        actor_ids.append(int(actor_id))
            deduped_actor_ids = sorted(set(actor_ids))
            self.risk_actor_lookup[risk_id] = deduped_actor_ids
            for actor_id in deduped_actor_ids:
                self.agent_risk_lookup[actor_id].append(risk_id)

        self.dynamic_edge_lookup: Dict[str, Dict[str, Any]] = {}
        self.dynamic_edges_by_source: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

        self.ipc = SimulationIPCServer(self.sim_dir)
        self.llm = None
        try:
            self.llm = LLMClient()
        except Exception:
            self.llm = None

        self.default_dynamic_ttl = int(self.interaction_policies.get("dynamic_edge_ttl_rounds") or 2)
        self.default_dynamic_decay = clamp_probability(
            self.interaction_policies.get("dynamic_edge_decay_per_round") or 0.2
        )
        self.cross_region_candidate_limit = int(
            self.interaction_policies.get("cross_region_candidates_per_agent")
            or self.runtime_limits.get("cross_region_candidates_per_agent")
            or 4
        )
        self.max_new_dynamic_edges_per_agent = int(
            self.interaction_policies.get("max_new_dynamic_edges_per_agent")
            or self.runtime_limits.get("max_new_dynamic_edges_per_agent")
            or 1
        )
        self.allowed_cross_region_hops = int(self.interaction_policies.get("allowed_cross_region_hops") or 1)
        self.llm_relation_search_budget = int(self.interaction_policies.get("llm_relation_search_budget") or 0)
        self.edge_promotion_enabled = bool(self.interaction_policies.get("edge_promotion_enabled"))

        for region in self.region_graph:
            region["state_vector"] = normalize_state_vector(region.get("state_vector") or {})
        for subregion in self.subregion_graph:
            subregion["state_vector"] = normalize_state_vector(subregion.get("state_vector") or {})
        for actor in self.actor_profiles:
            actor["state_vector"] = normalize_state_vector(actor.get("state_vector") or {})

    def _normalize_transport_edges(self, edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges or []:
            source = str(edge.get("source_region_id") or edge.get("source_region") or "").strip()
            target = str(edge.get("target_region_id") or edge.get("target_region") or "").strip()
            if source not in self.region_lookup or target not in self.region_lookup or source == target:
                continue
            channel = str(edge.get("channel_type") or edge.get("edge_type") or "environmental_link").strip()
            key = (source, target, channel)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "edge_id": str(edge.get("edge_id") or f"transport_{channel}_{source}_{target}"),
                    "source_region_id": source,
                    "target_region_id": target,
                    "channel_type": channel,
                    "directionality": str(edge.get("directionality") or "directed"),
                    "origin": str(edge.get("origin") or "config"),
                    "travel_time_rounds": max(0, int(edge.get("travel_time_rounds") or edge.get("delay_rounds") or 0)),
                    "attenuation_rate": clamp_probability(edge.get("attenuation_rate", 0.16)),
                    "retention_factor": clamp_probability(edge.get("retention_factor", 0.08)),
                    "barrier_factor": clamp_probability(edge.get("barrier_factor", 0.0)),
                    "strength": clamp_probability(edge.get("strength", 0.6)),
                    "confidence": clamp_probability(edge.get("confidence", 0.55)),
                    "evidence": dict(edge.get("evidence") or {}),
                    "rationale": str(edge.get("rationale") or ""),
                    "metadata": dict(edge.get("metadata") or {}),
                }
            )
        return normalized

    def _build_legacy_transport_edges(self) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for region in self.region_graph:
            source = str(region.get("region_id") or "").strip()
            for target in region.get("neighbors", []) or []:
                target_region = str(target or "").strip()
                key = (source, target_region, "environmental_link")
                if source not in self.region_lookup or target_region not in self.region_lookup or key in seen:
                    continue
                seen.add(key)
                edges.append(
                    {
                        "edge_id": f"legacy_neighbor_{source}_{target_region}",
                        "source_region_id": source,
                        "target_region_id": target_region,
                        "channel_type": "environmental_link",
                        "directionality": "directed",
                        "origin": "legacy_neighbor",
                        "travel_time_rounds": 1,
                        "attenuation_rate": 0.16,
                        "retention_factor": 0.08,
                        "barrier_factor": 0.0,
                        "strength": 0.6,
                        "confidence": 0.42,
                        "evidence": {"fallback": "region_neighbors"},
                        "rationale": "Legacy neighbor adjacency converted into directional transport edge.",
                        "metadata": {},
                    }
                )
        return edges

    def _rebuild_transport_edge_index(self) -> None:
        self.transport_edges_by_source = defaultdict(list)
        for edge in self.transport_edges:
            source = str(edge.get("source_region_id") or "").strip()
            if source:
                self.transport_edges_by_source[source].append(edge)

    def _transport_edges_for_source(self, region_id: str) -> List[Dict[str, Any]]:
        return list(self.transport_edges_by_source.get(str(region_id or "").strip(), []))

    def run(self) -> None:
        self._write_platform_event("twitter", {"event_type": "simulation_start", "timestamp": self._now()})
        self._write_platform_event("reddit", {"event_type": "simulation_start", "timestamp": self._now()})
        self.ipc.start()
        self._write_env_status("alive")

        for round_num in range(1, self.total_rounds + 1):
            self.current_round = round_num
            self._drain_commands()
            self._advance_dynamic_edges(round_num)

            active_variables = self._active_variables(round_num)
            diffusion = self._environmental_diffusion_update(round_num, active_variables)
            interactions = self._agent_interaction_update(round_num, active_variables, diffusion)
            feedback = self._human_nature_feedback_update(round_num, active_variables, diffusion, interactions)
            snapshot = self._build_snapshot(round_num, active_variables, diffusion, interactions, feedback)
            self.latest_summary = snapshot

            append_jsonl(self.state_matrix_log, snapshot)
            dump_json(self.latest_snapshot_path, snapshot)

            simulated_hours = round(round_num * self.minutes_per_round / 60, 2)
            self._write_platform_event(
                "twitter",
                {
                    "event_type": "round_end",
                    "round": round_num,
                    "simulated_hours": simulated_hours,
                    "timestamp": self._now(),
                },
            )
            self._write_platform_event(
                "reddit",
                {
                    "event_type": "round_end",
                    "round": round_num,
                    "simulated_hours": simulated_hours,
                    "timestamp": self._now(),
                },
            )

            self._inter_round_poll()

        self._write_platform_event(
            "twitter",
            {
                "event_type": "simulation_end",
                "round": self.total_rounds,
                "total_rounds": self.total_rounds,
                "timestamp": self._now(),
            },
        )
        self._write_platform_event(
            "reddit",
            {
                "event_type": "simulation_end",
                "round": self.total_rounds,
                "total_rounds": self.total_rounds,
                "timestamp": self._now(),
            },
        )

        if self.no_wait:
            self._write_env_status("stopped")
            self.ipc.stop()
            return

        while not self.closed:
            self._drain_commands()
            time.sleep(0.4)

        self._write_env_status("stopped")
        self.ipc.stop()

    def _environmental_diffusion_update(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        due_transfers = [item for item in self.pending_transfers if item["apply_round"] <= round_num]
        self.pending_transfers = [item for item in self.pending_transfers if item["apply_round"] > round_num]
        llm_result = self._llm_diffusion(round_num, active_variables, due_transfers)
        if not llm_result:
            llm_result = self._fallback_diffusion(round_num, active_variables, due_transfers)

        valid_transfers = []
        for transfer in llm_result.get("transfers") or []:
            validated = self._validate_transfer(transfer, active_variables)
            if validated:
                valid_transfers.append(validated)
                if validated["delay_rounds"] > 0:
                    scheduled = dict(validated)
                    scheduled["apply_round"] = round_num + int(validated["delay_rounds"])
                    self.pending_transfers.append(scheduled)

        immediate = [transfer for transfer in valid_transfers if transfer["delay_rounds"] <= 0]
        region_updates = defaultdict(lambda: defaultdict(float))
        for transfer in due_transfers + immediate:
            target = self.region_lookup.get(transfer["target_region"])
            if not target:
                continue
            delta = min(18.0, transfer["transfer_intensity"] * 0.18)
            region_updates[target["region_id"]]["exposure_score"] += delta
            region_updates[target["region_id"]]["spread_pressure"] += max(3.0, delta * 0.65)
            region_updates[target["region_id"]]["ecosystem_integrity"] -= max(2.0, delta * 0.22)

            append_jsonl(
                self.spread_log,
                {
                    "round": round_num,
                    "timestamp": self._now(),
                    "source_region": transfer["source_region"],
                    "target_region": transfer["target_region"],
                    "transfer_intensity": transfer["transfer_intensity"],
                    "delay_rounds": transfer["delay_rounds"],
                    "persistence": transfer["persistence"],
                    "confidence": transfer["confidence"],
                    "rationale": transfer["rationale"],
                },
            )
            self._write_action(
                platform="twitter",
                round_num=round_num,
                agent_id=500000 + self._region_index(transfer["source_region"]),
                agent_name=self.region_lookup.get(transfer["source_region"], {}).get("name", "EnvField"),
                action_type="SPREAD_UPDATE",
                action_args=transfer,
                result=transfer["rationale"],
            )

        for region_id, deltas in region_updates.items():
            region = self.region_lookup.get(region_id)
            if region:
                region["state_vector"] = merge_state_vectors(region["state_vector"], deltas)

        ranking = sorted(
            [
                {
                    "region_id": region["region_id"],
                    "name": region["name"],
                    "exposure_score": region["state_vector"]["exposure_score"],
                    "severity_band": score_band(region["state_vector"]["exposure_score"]),
                }
                for region in self.region_graph
            ],
            key=lambda item: item["exposure_score"],
            reverse=True,
        )
        return {
            "transfers": valid_transfers,
            "applied_transfers": due_transfers + immediate,
            "region_ranking": ranking,
            "likely_next_impacted_regions": [item["name"] for item in ranking[:3]],
        }

    def _agent_interaction_update(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
    ) -> Dict[str, Any]:
        del active_variables, diffusion
        if not self.actor_profiles:
            return {
                "active_agent_ids": [],
                "agent_interactions": [],
                "agent_environment_effects": [],
                "turning_points": [],
            }

        max_active = int(self.runtime_limits.get("max_active_agents_per_round") or max(12, len(self.actor_profiles) // 4))
        ordered = sorted(
            self.actor_profiles,
            key=self._agent_activation_score,
            reverse=True,
        )
        active_agents = ordered[: min(max_active, len(ordered))]

        interactions: List[Dict[str, Any]] = []
        environment_effects: List[Dict[str, Any]] = []
        turning_points: List[str] = []
        new_dynamic_edges: List[Dict[str, Any]] = []
        activated_dynamic_edge_ids: List[str] = []
        llm_search_remaining = self.llm_relation_search_budget

        for actor in active_agents:
            home_region = self.region_lookup.get(actor.get("primary_region")) or self.region_graph[0]
            home_subregion = self.subregion_lookup.get(actor.get("home_subregion_id") or "")
            actor_id = int(actor.get("agent_id", -1))
            action_type = self._choose_agent_action(actor, home_region)
            action_bundle = self._action_effects(actor, action_type, home_region)
            emergent_edges, llm_search_remaining = self._maybe_create_dynamic_edges(actor, round_num, llm_search_remaining)
            if emergent_edges:
                new_dynamic_edges.extend(emergent_edges)
                for edge in emergent_edges[:1]:
                    target_name = self.actor_lookup.get(int(edge.get("target_agent_id", -1)), {}).get("name") or edge.get("target_agent_id")
                    turning_points.append(
                        f"{actor.get('name') or actor.get('username')} 与 {target_name} 建立了新的跨区 {edge.get('edge_type')}。"
                    )
            relation_edges = self.relationships_by_source.get(actor_id, []) + self._dynamic_edges_for_source(actor_id)

            actor["state_vector"] = merge_state_vectors(actor.get("state_vector") or {}, action_bundle["actor_delta"])
            if action_bundle["region_delta"]:
                home_region["state_vector"] = merge_state_vectors(home_region["state_vector"], action_bundle["region_delta"])
                if home_subregion is not None:
                    home_subregion["state_vector"] = merge_state_vectors(
                        home_subregion.get("state_vector") or {},
                        action_bundle["region_delta"],
                    )
                environment_effects.append(
                    {
                        "agent_id": actor.get("agent_id"),
                        "agent_name": actor.get("username") or actor.get("name"),
                        "action_type": action_type,
                        "region_id": home_region.get("region_id"),
                        "region_name": home_region.get("name"),
                        "home_subregion_id": home_subregion.get("region_id") if home_subregion else "",
                        "delta": action_bundle["region_delta"],
                    }
                )

            target_actor, selected_edge = self._select_interaction_target(relation_edges, action_type)
            if target_actor and action_bundle["target_delta"]:
                target_actor["state_vector"] = merge_state_vectors(
                    target_actor.get("state_vector") or {},
                    action_bundle["target_delta"],
                )
                selected_dynamic_edge_id = str(selected_edge.get("edge_id") or "") if selected_edge else ""
                if selected_dynamic_edge_id in self.dynamic_edge_lookup:
                    self._activate_dynamic_edge(selected_dynamic_edge_id, round_num)
                    activated_dynamic_edge_ids.append(selected_dynamic_edge_id)
                relation_type = None
                if selected_edge:
                    relation_type = selected_edge.get("edge_type") or selected_edge.get("relation_type") or selected_edge.get("name")
                interaction_record = {
                    "round": round_num,
                    "timestamp": self._now(),
                    "source_agent_id": actor.get("agent_id"),
                    "source_agent_name": actor.get("username") or actor.get("name"),
                    "target_agent_id": target_actor.get("agent_id"),
                    "target_agent_name": target_actor.get("username") or target_actor.get("name"),
                    "action_type": action_type,
                    "channel": action_bundle["interaction_channel"],
                    "delta": action_bundle["target_delta"],
                    "rationale": action_bundle["rationale"],
                    "relation_type": relation_type,
                    "edge_layer": selected_edge.get("layer", "structural") if selected_edge else "structural",
                    "edge_id": selected_edge.get("edge_id") if selected_edge else None,
                    "source_region_id": home_region.get("region_id"),
                    "target_region_id": target_actor.get("primary_region") or target_actor.get("home_region_id"),
                }
                interactions.append(interaction_record)
                append_jsonl(self.agent_interaction_log, interaction_record)

            self._write_action(
                platform="reddit" if actor.get("agent_type") == "human" else "twitter",
                round_num=round_num,
                agent_id=int(actor.get("agent_id", -1)),
                agent_name=actor.get("username") or actor.get("name"),
                action_type=action_type.upper(),
                action_args={
                    "region_delta": action_bundle["region_delta"],
                    "target_delta": action_bundle["target_delta"],
                    "home_region": home_region.get("region_id"),
                    "home_subregion": home_subregion.get("region_id") if home_subregion else "",
                    "new_dynamic_edges": [edge.get("edge_id") for edge in emergent_edges],
                },
                result=action_bundle["rationale"],
            )
            if action_bundle["turning_point"]:
                turning_points.append(action_bundle["turning_point"])

        self._roll_up_subregions()
        active_dynamic_edges = [edge for edge in self.dynamic_edge_lookup.values() if edge.get("status") != "expired"]

        return {
            "active_agent_ids": [int(actor.get("agent_id", -1)) for actor in active_agents],
            "agent_interactions": interactions,
            "agent_environment_effects": environment_effects,
            "new_dynamic_edges": new_dynamic_edges,
            "activated_dynamic_edge_ids": activated_dynamic_edge_ids,
            "dynamic_edge_summary": {
                "search_mode": self.search_mode,
                "total_dynamic_edges": len(active_dynamic_edges),
                "new_edges_this_round": len(new_dynamic_edges),
                "activated_edges_this_round": len(activated_dynamic_edge_ids),
                "llm_relation_search_used": max(0, self.llm_relation_search_budget - llm_search_remaining),
            },
            "top_active_agents": [
                {
                    "agent_id": actor.get("agent_id"),
                    "agent_name": actor.get("username") or actor.get("name"),
                    "agent_type": actor.get("agent_type") or actor.get("node_family"),
                    "primary_region": actor.get("primary_region"),
                    "state_vector": actor.get("state_vector"),
                }
                for actor in active_agents[:10]
            ],
            "turning_points": turning_points[:8],
        }

    def _agent_activation_score(self, actor: Dict[str, Any]) -> float:
        region = self.region_lookup.get(actor.get("primary_region"), {})
        vector = actor.get("state_vector") or {}
        region_vector = region.get("state_vector") or {}
        return (
            clamp_score(region_vector.get("exposure_score", 0)) * 0.4
            + clamp_score(vector.get("vulnerability_score", 0)) * 0.25
            + clamp_score(region_vector.get("panic_level", 0)) * 0.15
            + clamp_score(vector.get("response_capacity", 0)) * 0.1
            + clamp_score(vector.get("economic_stress", 0)) * 0.1
        )

    def _reachable_regions(self, start_region: str, max_hops: int) -> List[str]:
        region_id = str(start_region or "").strip()
        if not region_id or region_id not in self.region_lookup or max_hops <= 0:
            return []
        seen = {region_id}
        frontier = [region_id]
        reached: List[str] = []
        for _ in range(max_hops):
            next_frontier: List[str] = []
            for current in frontier:
                for neighbor in self.region_lookup.get(current, {}).get("neighbors", []) or []:
                    neighbor_id = str(neighbor or "").strip()
                    if not neighbor_id or neighbor_id in seen:
                        continue
                    seen.add(neighbor_id)
                    reached.append(neighbor_id)
                    next_frontier.append(neighbor_id)
            if not next_frontier:
                break
            frontier = next_frontier
        return reached

    def _merge_dynamic_evidence(self, base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base or {})
        for key, value in (extra or {}).items():
            if value in (None, "", [], {}):
                continue
            if isinstance(value, list):
                existing = list(merged.get(key) or [])
                merged[key] = list(dict.fromkeys(existing + value))
            elif isinstance(value, dict):
                bucket = dict(merged.get(key) or {})
                bucket.update(value)
                merged[key] = bucket
            else:
                merged[key] = value
        return merged

    def _rebuild_dynamic_edge_index(self) -> None:
        self.dynamic_edges_by_source = defaultdict(list)
        for edge in self.dynamic_edge_lookup.values():
            if edge.get("status") == "expired":
                continue
            try:
                source_agent_id = int(edge.get("source_agent_id"))
            except Exception:
                continue
            self.dynamic_edges_by_source[source_agent_id].append(edge)

    def _serialize_dynamic_edge(self, edge: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "edge_id": edge.get("edge_id"),
            "source_agent_id": edge.get("source_agent_id"),
            "target_agent_id": edge.get("target_agent_id"),
            "source_region_id": edge.get("source_region_id"),
            "target_region_id": edge.get("target_region_id"),
            "edge_type": edge.get("edge_type"),
            "interaction_channel": edge.get("interaction_channel"),
            "layer": edge.get("layer"),
            "origin": edge.get("origin"),
            "scope": edge.get("scope"),
            "strength": clamp_probability(edge.get("strength") or 0),
            "confidence": clamp_probability(edge.get("confidence") or 0),
            "ttl_rounds": int(edge.get("ttl_rounds") or self.default_dynamic_ttl),
            "decay_per_round": clamp_probability(edge.get("decay_per_round") or self.default_dynamic_decay),
            "created_round": int(edge.get("created_round") or 0),
            "last_activated_round": int(edge.get("last_activated_round") or 0),
            "expires_after_round": int(edge.get("expires_after_round") or 0),
            "status": edge.get("status") or "active",
            "routing_basis": list(edge.get("routing_basis") or []),
            "evidence": dict(edge.get("evidence") or {}),
            "rationale": edge.get("rationale") or "",
            "reconfirm_count": int(edge.get("reconfirm_count") or 0),
        }

    def _record_dynamic_edge_event(self, round_num: int, event_type: str, edge: Dict[str, Any]) -> None:
        append_jsonl(
            self.dynamic_edge_log,
            {
                "round": round_num,
                "timestamp": self._now(),
                "event_type": event_type,
                **self._serialize_dynamic_edge(edge),
            },
        )

    def _advance_dynamic_edges(self, round_num: int) -> None:
        changed = False
        for edge in self.dynamic_edge_lookup.values():
            if edge.get("status") == "expired":
                continue
            previous_status = edge.get("status") or "active"
            expires_after_round = int(edge.get("expires_after_round") or 0)
            if expires_after_round and round_num > expires_after_round:
                edge["status"] = "expired"
                self._record_dynamic_edge_event(round_num, "expired", edge)
                changed = True
                continue

            if edge.get("layer") == "structural" and edge.get("origin") == "runtime_promoted":
                edge["status"] = "stable"
                continue

            last_activated_round = int(edge.get("last_activated_round") or edge.get("created_round") or 0)
            if last_activated_round < round_num - 1:
                decay = clamp_probability(edge.get("decay_per_round") or self.default_dynamic_decay)
                edge["strength"] = clamp_probability(float(edge.get("strength") or 0) * max(0.0, 1.0 - decay))
                edge["status"] = "cooling" if float(edge.get("strength") or 0) >= 0.12 else "expired"
            else:
                edge["status"] = "active"

            if edge.get("status") != previous_status:
                event_type = "cooling" if edge.get("status") == "cooling" else edge.get("status")
                self._record_dynamic_edge_event(round_num, str(event_type), edge)
                changed = True

        if changed or self.dynamic_edge_lookup:
            self._rebuild_dynamic_edge_index()

    def _dynamic_edges_for_source(self, source_agent_id: int) -> List[Dict[str, Any]]:
        return list(self.dynamic_edges_by_source.get(int(source_agent_id), []))

    def _infer_dynamic_edge_type(
        self,
        actor: Dict[str, Any],
        target_actor: Dict[str, Any],
        route_sources: List[str],
    ) -> tuple[str, str]:
        source_type = str(actor.get("agent_type") or "").lower()
        source_subtype = str(actor.get("agent_subtype") or "").lower()
        target_type = str(target_actor.get("agent_type") or "").lower()
        target_subtype = str(target_actor.get("agent_subtype") or "").lower()
        media_roles = {"journalist", "scientist", "activist"}

        if "media_reach" in route_sources and (source_subtype in media_roles or target_subtype in media_roles):
            return "media_link", "media"
        if "ecology" in {source_type, target_type} or "carrier" in {source_type, target_type}:
            return "ecology_corridor_signal", "ecology"
        if "governance_hierarchy" in route_sources and "governance" in {source_type, target_type}:
            return "governance_coordination", "governance"
        if "governance" in {source_type, target_type} and source_type in {"governance", "organization"}:
            return "governance_coordination", "governance"
        if "media_reach" in route_sources:
            return "media_link", "information"
        if "organization" in {source_type, target_type} or source_subtype in {"plant_operator", "market_association", "shop_owner", "worker"} or target_subtype in {"plant_operator", "market_association", "shop_owner", "worker"}:
            return "market_link", "market"
        return "response_bridge", "information"

    def _collect_cross_region_candidates(self, actor: Dict[str, Any], round_num: int) -> List[Dict[str, Any]]:
        del round_num
        source_agent_id = int(actor.get("agent_id", -1))
        source_region_id = str(actor.get("primary_region") or actor.get("home_region_id") or "").strip()
        if source_agent_id <= 0 or not source_region_id:
            return []

        reachable_regions = self._reachable_regions(source_region_id, self.allowed_cross_region_hops)
        influenced_regions = [
            str(region_id or "").strip()
            for region_id in actor.get("influenced_regions") or []
            if str(region_id or "").strip() and str(region_id or "").strip() != source_region_id
        ]
        allowed_regions = set(reachable_regions) | set(influenced_regions)
        existing_targets = {
            int(edge.get("target_agent_id"))
            for edge in self.relationships_by_source.get(source_agent_id, []) + self._dynamic_edges_for_source(source_agent_id)
            if str(edge.get("target_agent_id") or "").isdigit()
        }
        candidates_by_id: Dict[int, Dict[str, Any]] = {}

        def add_candidate(
            target_actor: Dict[str, Any],
            route_source: str,
            evidence: Optional[Dict[str, Any]] = None,
            bonus: float = 0.0,
        ) -> None:
            try:
                target_agent_id = int(target_actor.get("agent_id"))
            except Exception:
                return
            if target_agent_id <= 0 or target_agent_id == source_agent_id or target_agent_id in existing_targets:
                return
            target_region_id = str(target_actor.get("primary_region") or target_actor.get("home_region_id") or "").strip()
            if not target_region_id or target_region_id == source_region_id:
                return
            if allowed_regions and target_region_id not in allowed_regions and route_source != "shared_risk_object":
                return

            activation_weight = self._agent_activation_score(target_actor) / 100.0
            priority = 0.18 * activation_weight + bonus
            if target_region_id in influenced_regions:
                priority += 0.12
            if str(target_actor.get("agent_type") or "").lower() == str(actor.get("agent_type") or "").lower():
                priority += 0.05
            if target_region_id in reachable_regions:
                priority += 0.08

            entry = candidates_by_id.setdefault(
                target_agent_id,
                {
                    "target_agent_id": target_agent_id,
                    "target_agent_name": target_actor.get("username") or target_actor.get("name"),
                    "target_region_id": target_region_id,
                    "target_agent_type": target_actor.get("agent_type") or target_actor.get("node_family"),
                    "target_agent_subtype": target_actor.get("agent_subtype") or target_actor.get("role_type"),
                    "route_sources": [],
                    "evidence": {},
                    "score": 0.0,
                },
            )
            if route_source not in entry["route_sources"]:
                entry["route_sources"].append(route_source)
            entry["score"] += priority
            entry["evidence"] = self._merge_dynamic_evidence(entry.get("evidence") or {}, evidence or {})

        for region_id in reachable_regions:
            for target_actor in self.agents_by_region.get(region_id, []):
                add_candidate(
                    target_actor,
                    "neighbor_region",
                    evidence={"neighbor_region": region_id},
                    bonus=0.14,
                )

        relevant_risk_ids = set(self.agent_risk_lookup.get(source_agent_id, []))
        for risk_id, regions in self.risk_region_lookup.items():
            if source_region_id in regions:
                relevant_risk_ids.add(risk_id)
        for risk_id in relevant_risk_ids:
            for target_agent_id in self.risk_actor_lookup.get(risk_id, []):
                target_actor = self.actor_lookup.get(target_agent_id)
                if not target_actor:
                    continue
                add_candidate(
                    target_actor,
                    "shared_risk_object",
                    evidence={"risk_object_ids": [risk_id]},
                    bonus=0.24,
                )

        actor_type = str(actor.get("agent_type") or "").lower()
        actor_subtype = str(actor.get("agent_subtype") or "").lower()
        governance_targets = self.agents_by_type.get("governance", []) + self.agents_by_type.get("organization", [])
        if actor_type in {"governance", "organization"}:
            for target_actor in governance_targets:
                target_region_id = str(target_actor.get("primary_region") or "").strip()
                if target_region_id == source_region_id:
                    continue
                if allowed_regions and target_region_id not in allowed_regions:
                    continue
                add_candidate(
                    target_actor,
                    "governance_hierarchy",
                    evidence={"reachable_regions": sorted(allowed_regions)[:6]},
                    bonus=0.18,
                )
        elif actor_subtype in {"scientist", "journalist", "activist"}:
            for target_actor in self.agents_by_type.get("governance", []):
                target_region_id = str(target_actor.get("primary_region") or "").strip()
                if target_region_id == source_region_id:
                    continue
                if allowed_regions and target_region_id not in allowed_regions:
                    continue
                add_candidate(
                    target_actor,
                    "governance_hierarchy",
                    evidence={"reachable_regions": sorted(allowed_regions)[:6]},
                    bonus=0.08,
                )

        media_sources = {"scientist", "journalist", "activist"}
        if str(actor.get("agent_subtype") or "").lower() in media_sources or str(actor.get("agent_type") or "").lower() in {"human", "governance", "organization"}:
            media_targets = (
                self.agents_by_subtype.get("scientist", [])
                + self.agents_by_subtype.get("journalist", [])
                + self.agents_by_subtype.get("activist", [])
                + self.agents_by_type.get("governance", [])
            )
            for target_actor in media_targets:
                add_candidate(
                    target_actor,
                    "media_reach",
                    evidence={"influenced_regions": influenced_regions[:6]},
                    bonus=0.12,
                )

        candidates = list(candidates_by_id.values())
        candidates.sort(
            key=lambda item: (
                len(item.get("route_sources") or []),
                float(item.get("score") or 0),
                item.get("target_agent_name") or "",
            ),
            reverse=True,
        )
        return candidates[: self.cross_region_candidate_limit]

    def _llm_dynamic_edge_search(
        self,
        actor: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        round_num: int,
    ) -> List[Dict[str, Any]]:
        if not self.llm or not candidates or self.max_new_dynamic_edges_per_agent <= 0:
            return []
        source_region_id = str(actor.get("primary_region") or actor.get("home_region_id") or "").strip()
        prompt = {
            "task": "Select a small number of plausible cross-region emergent edges for this EnvFish round.",
            "round": round_num,
            "search_mode": self.search_mode,
            "source_agent": {
                "agent_id": actor.get("agent_id"),
                "name": actor.get("username") or actor.get("name"),
                "agent_type": actor.get("agent_type"),
                "agent_subtype": actor.get("agent_subtype"),
                "primary_region": source_region_id,
                "state_vector": actor.get("state_vector") or {},
                "influenced_regions": actor.get("influenced_regions") or [],
                "risk_object_ids": self.agent_risk_lookup.get(int(actor.get("agent_id", -1)), []),
            },
            "candidate_targets": candidates,
            "schema": {
                "proposals": [
                    {
                        "target_agent_id": 0,
                        "edge_type": "governance_coordination|market_link|media_link|ecology_corridor_signal|response_bridge",
                        "strength": 0.0,
                        "confidence": 0.0,
                        "ttl_rounds": 2,
                        "routing_basis": ["neighbor_region"],
                        "rationale": "string",
                    }
                ]
            },
            "constraints": [
                f"Use at most {self.max_new_dynamic_edges_per_agent} proposals.",
                "Only use target_agent_id values from candidate_targets.",
                "Only create cross-region edges.",
                "Keep strength and confidence between 0 and 1.",
                "Keep ttl_rounds between 1 and 5.",
                "Prefer candidates with multiple routing_basis entries.",
                "Return valid JSON only.",
            ],
        }
        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Return compact JSON only. Respect the candidate list strictly."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=900,
            )
            proposals = result.get("proposals") or []
            return [item for item in proposals if isinstance(item, dict)]
        except Exception:
            return []

    def _fallback_dynamic_edge_search(
        self,
        actor: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        round_num: int,
    ) -> List[Dict[str, Any]]:
        if not candidates or self.max_new_dynamic_edges_per_agent <= 0:
            return []
        source_region = self.region_lookup.get(actor.get("primary_region") or "", {})
        region_vector = source_region.get("state_vector") or {}
        stress_score = (
            clamp_score(region_vector.get("exposure_score", 0)) * 0.45
            + clamp_score(region_vector.get("panic_level", 0)) * 0.25
            + clamp_score(actor.get("state_vector", {}).get("vulnerability_score", 0)) * 0.3
        )
        proposal_cap = self.max_new_dynamic_edges_per_agent
        if stress_score < 50 and self.search_mode == "fast":
            proposal_cap = 0
        elif stress_score < 72:
            proposal_cap = min(1, proposal_cap)
        elif stress_score >= 88 and self.search_mode == "deep_search":
            proposal_cap = min(2, proposal_cap)
        if proposal_cap <= 0:
            return []

        proposals: List[Dict[str, Any]] = []
        candidate_window = candidates[: max(proposal_cap * 3, proposal_cap)]
        if not candidate_window:
            return []
        offset = (int(actor.get("agent_id", 0)) + round_num) % len(candidate_window)
        ordered_candidates = candidate_window[offset:] + candidate_window[:offset]
        selected_candidates = ordered_candidates[:proposal_cap]

        for candidate in selected_candidates:
            target_actor = self.actor_lookup.get(int(candidate.get("target_agent_id", -1)))
            if not target_actor:
                continue
            edge_type, _ = self._infer_dynamic_edge_type(actor, target_actor, candidate.get("route_sources") or [])
            strength = clamp_probability(
                0.34
                + min(0.3, float(candidate.get("score") or 0) * 0.35)
                + (0.12 if "shared_risk_object" in (candidate.get("route_sources") or []) else 0.0)
            )
            confidence = clamp_probability(
                0.5
                + 0.08 * len(candidate.get("route_sources") or [])
                + (0.06 if self.search_mode == "deep_search" else 0.0)
            )
            ttl_rounds = min(5, max(1, self.default_dynamic_ttl + (1 if "shared_risk_object" in (candidate.get("route_sources") or []) and self.search_mode == "deep_search" else 0)))
            proposals.append(
                {
                    "target_agent_id": candidate.get("target_agent_id"),
                    "edge_type": edge_type,
                    "strength": strength,
                    "confidence": confidence,
                    "ttl_rounds": ttl_rounds,
                    "routing_basis": candidate.get("route_sources") or [],
                    "rationale": (
                        f"Round {round_num} cross-region bridge triggered by "
                        f"{' + '.join(candidate.get('route_sources') or ['neighbor_region'])}."
                    ),
                }
            )
        return proposals

    def _upsert_dynamic_edge(
        self,
        source_actor: Dict[str, Any],
        target_actor: Dict[str, Any],
        proposal: Dict[str, Any],
        candidate: Dict[str, Any],
        round_num: int,
        origin: str,
    ) -> Optional[Dict[str, Any]]:
        source_agent_id = int(source_actor.get("agent_id", -1))
        target_agent_id = int(target_actor.get("agent_id", -1))
        source_region_id = str(source_actor.get("primary_region") or source_actor.get("home_region_id") or "").strip()
        target_region_id = str(target_actor.get("primary_region") or target_actor.get("home_region_id") or "").strip()
        if source_agent_id <= 0 or target_agent_id <= 0 or not source_region_id or not target_region_id:
            return None
        if source_agent_id == target_agent_id or source_region_id == target_region_id:
            return None

        route_sources = [
            str(item).strip()
            for item in proposal.get("routing_basis") or candidate.get("route_sources") or []
            if str(item).strip()
        ]
        if not route_sources:
            return None
        edge_type, interaction_channel = self._infer_dynamic_edge_type(source_actor, target_actor, route_sources)
        edge_type = str(proposal.get("edge_type") or edge_type).strip() or edge_type
        strength = clamp_probability(proposal.get("strength") or 0.45)
        confidence = clamp_probability(proposal.get("confidence") or 0.55)
        ttl_rounds = min(5, max(1, int(proposal.get("ttl_rounds") or self.default_dynamic_ttl)))
        edge_id = f"dynamic::{source_agent_id}::{target_agent_id}::{edge_type}"
        evidence = self._merge_dynamic_evidence(candidate.get("evidence") or {}, proposal.get("evidence") or {})
        edge = self.dynamic_edge_lookup.get(edge_id)

        if edge:
            edge["strength"] = clamp_probability(max(float(edge.get("strength") or 0), strength))
            edge["confidence"] = clamp_probability(max(float(edge.get("confidence") or 0), confidence))
            edge["ttl_rounds"] = max(int(edge.get("ttl_rounds") or 1), ttl_rounds)
            edge["last_activated_round"] = round_num
            edge["expires_after_round"] = max(
                int(edge.get("expires_after_round") or round_num),
                round_num + edge["ttl_rounds"] - 1,
            )
            edge["status"] = "active"
            edge["origin"] = origin or edge.get("origin") or "heuristic_emergent"
            edge["routing_basis"] = list(dict.fromkeys((edge.get("routing_basis") or []) + route_sources))
            edge["evidence"] = self._merge_dynamic_evidence(edge.get("evidence") or {}, evidence)
            edge["rationale"] = str(proposal.get("rationale") or edge.get("rationale") or "")
            edge["reconfirm_count"] = int(edge.get("reconfirm_count") or 1) + 1
            self._record_dynamic_edge_event(round_num, "updated", edge)
        else:
            edge = {
                "edge_id": edge_id,
                "source_agent_id": source_agent_id,
                "target_agent_id": target_agent_id,
                "source_region_id": source_region_id,
                "target_region_id": target_region_id,
                "edge_type": edge_type,
                "interaction_channel": interaction_channel,
                "layer": "dynamic",
                "origin": origin,
                "scope": "cross_region",
                "directionality": "directed",
                "strength": strength,
                "confidence": confidence,
                "ttl_rounds": ttl_rounds,
                "decay_per_round": clamp_probability(self.default_dynamic_decay),
                "created_round": round_num,
                "last_activated_round": round_num,
                "expires_after_round": round_num + ttl_rounds - 1,
                "status": "active",
                "routing_basis": route_sources,
                "evidence": evidence,
                "rationale": str(proposal.get("rationale") or ""),
                "reconfirm_count": 1,
            }
            self.dynamic_edge_lookup[edge_id] = edge
            self._record_dynamic_edge_event(round_num, "created", edge)

        self._rebuild_dynamic_edge_index()
        return edge

    def _activate_dynamic_edge(self, edge_id: str, round_num: int) -> None:
        edge = self.dynamic_edge_lookup.get(edge_id)
        if not edge:
            return
        edge["last_activated_round"] = round_num
        edge["status"] = "active"
        edge["strength"] = clamp_probability(float(edge.get("strength") or 0) + 0.04)
        edge["confidence"] = clamp_probability(float(edge.get("confidence") or 0) + 0.02)
        edge["expires_after_round"] = max(
            int(edge.get("expires_after_round") or round_num),
            round_num + int(edge.get("ttl_rounds") or self.default_dynamic_ttl) - 1,
        )
        edge["reconfirm_count"] = int(edge.get("reconfirm_count") or 1) + 1
        if (
            self.edge_promotion_enabled
            and int(edge.get("reconfirm_count") or 0) >= 3
            and float(edge.get("strength") or 0) >= 0.62
            and float(edge.get("confidence") or 0) >= 0.7
        ):
            edge["layer"] = "structural"
            edge["origin"] = "runtime_promoted"
            edge["status"] = "stable"
            edge["expires_after_round"] = self.total_rounds + int(edge.get("ttl_rounds") or self.default_dynamic_ttl)
        self._record_dynamic_edge_event(round_num, "activated", edge)
        self._rebuild_dynamic_edge_index()

    def _maybe_create_dynamic_edges(
        self,
        actor: Dict[str, Any],
        round_num: int,
        llm_search_remaining: int,
    ) -> tuple[List[Dict[str, Any]], int]:
        if self.max_new_dynamic_edges_per_agent <= 0:
            return [], llm_search_remaining
        candidates = self._collect_cross_region_candidates(actor, round_num)
        if not candidates:
            return [], llm_search_remaining

        proposals: List[Dict[str, Any]] = []
        origin = "heuristic_emergent"
        if self.llm and llm_search_remaining > 0:
            proposals = self._llm_dynamic_edge_search(actor, candidates, round_num)
            llm_search_remaining -= 1
            if proposals:
                origin = "llm_emergent"
        if not proposals:
            proposals = self._fallback_dynamic_edge_search(actor, candidates, round_num)

        created_edges: List[Dict[str, Any]] = []
        candidate_lookup = {int(item.get("target_agent_id", -1)): item for item in candidates}
        for proposal in proposals[: self.max_new_dynamic_edges_per_agent]:
            try:
                target_agent_id = int(proposal.get("target_agent_id"))
            except Exception:
                continue
            candidate = candidate_lookup.get(target_agent_id)
            target_actor = self.actor_lookup.get(target_agent_id)
            if not candidate or not target_actor:
                continue
            edge = self._upsert_dynamic_edge(actor, target_actor, proposal, candidate, round_num, origin)
            if edge:
                created_edges.append(self._serialize_dynamic_edge(edge))
        return created_edges, llm_search_remaining

    def _choose_agent_action(self, actor: Dict[str, Any], region: Dict[str, Any]) -> str:
        action_space = actor.get("action_space") or ["monitor"]
        agent_type = actor.get("agent_type") or "human"
        subtype = str(actor.get("agent_subtype") or "")
        exposure = clamp_score(region.get("state_vector", {}).get("exposure_score", 0))
        eco = clamp_score(region.get("state_vector", {}).get("ecosystem_integrity", 60))

        if agent_type == "governance":
            if exposure >= 65:
                return "enforce_restriction"
            if eco <= 55:
                return "deploy_remediation"
            return "issue_alert" if "issue_alert" in action_space else action_space[0]
        if agent_type == "organization":
            if subtype == "plant_operator":
                return "mitigate_emission" if exposure >= 60 else "continue_output"
            if subtype == "conservation_station":
                return "restore_habitat"
            return "public_briefing" if exposure >= 45 and "public_briefing" in action_space else action_space[0]
        if agent_type == "human":
            if subtype in {"scientist", "journalist"}:
                return "publish_assessment" if subtype == "scientist" else "broadcast"
            if subtype == "activist":
                return "volunteer_cleanup" if eco <= 55 else "petition"
            if subtype in {"worker", "field_observer"}:
                return "report_hazard" if exposure >= 55 else action_space[0]
            return "panic_buy" if exposure >= 70 and "panic_buy" in action_space else action_space[0]
        if agent_type == "carrier":
            return "transport_pressure" if exposure >= 55 else "dilute"
        return "stress_signal" if eco <= 60 else action_space[0]

    def _action_effects(
        self,
        actor: Dict[str, Any],
        action_type: str,
        region: Dict[str, Any],
    ) -> Dict[str, Any]:
        del region
        impact = actor.get("impact_profile") or {}
        panic = float(impact.get("panic_delta", 0))
        trust = float(impact.get("trust_delta", 0))
        economic = float(impact.get("economic_delta", 0))
        ecology = float(impact.get("ecology_delta", 0))
        action = action_type.lower()
        actor_delta: Dict[str, Any] = {}
        region_delta: Dict[str, Any] = {}
        target_delta: Dict[str, Any] = {}
        channel = "social"
        rationale = f"{actor.get('name') or actor.get('username')} 在当前压力下选择 {action_type}。"
        turning_point = ""

        if action in {"deploy_remediation", "restore_habitat", "volunteer_cleanup", "mitigate_emission"}:
            actor_delta = {"response_capacity": 2.0, "panic_level": -1.0}
            region_delta = {
                "ecosystem_integrity": max(1.0, ecology if ecology > 0 else 1.2),
                "public_trust": max(0.6, trust if trust > 0 else 0.8),
                "panic_level": -0.8,
                "economic_stress": 0.2,
            }
            channel = "environment"
            turning_point = f"{actor.get('name')} 开始对 {actor.get('primary_region')} 采取修复行动。"
        elif action in {"issue_alert", "publish_assessment", "public_briefing", "monitor", "report_hazard", "verify"}:
            actor_delta = {"response_capacity": 1.2, "public_trust": 0.4}
            region_delta = {"public_trust": max(0.3, trust if trust > 0 else 0.6), "panic_level": 0.2}
            target_delta = {"response_capacity": 0.6, "public_trust": 0.4}
            channel = "information"
        elif action in {"broadcast", "panic_buy", "question_authority", "public_campaign"}:
            actor_delta = {"panic_level": 1.4, "public_trust": -0.4}
            region_delta = {"panic_level": max(1.0, abs(panic) or 1.0), "public_trust": -max(0.4, abs(trust) or 0.4)}
            target_delta = {"panic_level": 0.8}
            channel = "media"
            turning_point = f"{actor.get('name')} 放大了 {actor.get('primary_region')} 的情绪波动。"
        elif action in {"continue_output", "continue_production", "market_shift", "adjust_supply", "price_signal"}:
            actor_delta = {"economic_stress": 0.8, "response_capacity": -0.2}
            region_delta = {
                "economic_stress": max(0.8, economic if economic > 0 else 1.0),
                "livelihood_stability": -0.4 if action in {"continue_output", "continue_production"} else 0.3,
                "ecosystem_integrity": ecology if ecology < 0 else -0.6,
            }
            channel = "market"
        elif action in {"enforce_restriction", "coordinate_response", "evacuate", "stabilize_services", "halt_line", "shutdown_line", "fine_operator"}:
            actor_delta = {"response_capacity": 1.5, "economic_stress": 0.4}
            region_delta = {
                "exposure_score": -1.2,
                "spread_pressure": -1.0,
                "public_trust": max(0.4, trust if trust > 0 else 0.5),
                "economic_stress": max(0.2, economic if economic > 0 else 0.5),
            }
            target_delta = {"response_capacity": -0.2, "economic_stress": 0.6}
            channel = "governance"
        elif action in {"stress_signal", "migration_shift", "migrate", "breed_decline", "signal_loss", "bioaccumulate", "transport_pressure", "retain_pollutant"}:
            actor_delta = {"vulnerability_score": 1.2}
            region_delta = {
                "ecosystem_integrity": ecology if ecology < 0 else -1.2,
                "spread_pressure": 1.0 if action in {"transport_pressure", "retain_pollutant"} else 0.4,
                "vulnerability_score": 0.9,
            }
            channel = "ecology"
            turning_point = f"{actor.get('name')} 显示出生态系统已进入更脆弱状态。"
        elif action == "dilute" or action == "partial_recovery":
            actor_delta = {"vulnerability_score": -0.6}
            region_delta = {"exposure_score": -0.8, "ecosystem_integrity": 0.8}
            channel = "ecology"
        else:
            actor_delta = {"response_capacity": 0.4}
            region_delta = {"public_trust": 0.1}

        return {
            "actor_delta": actor_delta,
            "region_delta": region_delta,
            "target_delta": target_delta,
            "interaction_channel": channel,
            "rationale": rationale,
            "turning_point": turning_point,
        }

    def _select_interaction_target(
        self,
        relation_edges: List[Dict[str, Any]],
        action_type: str,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if not relation_edges:
            return None, None
        preferred_channel = "media" if action_type in {"broadcast", "public_campaign"} else "governance"
        ordered = sorted(
            relation_edges,
            key=lambda item: (
                1 if item.get("interaction_channel") == preferred_channel else 0,
                1 if item.get("layer") == "dynamic" else 0,
                float(item.get("confidence") or 0),
                float(item.get("strength") or 0),
            ),
            reverse=True,
        )
        for edge in ordered:
            target = self.actor_lookup.get(int(edge.get("target_agent_id", -1)))
            if target:
                return target, edge
        return None, None

    def _roll_up_subregions(self) -> None:
        if not self.subregion_graph:
            return
        by_parent: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for subregion in self.subregion_graph:
            parent_id = subregion.get("parent_region_id")
            if parent_id:
                by_parent[parent_id].append(subregion)

        for region_id, items in by_parent.items():
            region = self.region_lookup.get(region_id)
            if not region or not items:
                continue
            aggregate = {}
            for key in region.get("state_vector", {}).keys():
                aggregate[key] = round(sum(item.get("state_vector", {}).get(key, 0.0) for item in items) / len(items), 2)
            region["state_vector"] = normalize_state_vector(
                merge_state_vectors(region.get("state_vector") or {}, {
                    "exposure_score": aggregate.get("exposure_score", 0) - region.get("state_vector", {}).get("exposure_score", 0),
                    "spread_pressure": aggregate.get("spread_pressure", 0) - region.get("state_vector", {}).get("spread_pressure", 0),
                    "ecosystem_integrity": aggregate.get("ecosystem_integrity", 0) - region.get("state_vector", {}).get("ecosystem_integrity", 0),
                    "public_trust": aggregate.get("public_trust", 0) - region.get("state_vector", {}).get("public_trust", 0),
                    "panic_level": aggregate.get("panic_level", 0) - region.get("state_vector", {}).get("panic_level", 0),
                    "economic_stress": aggregate.get("economic_stress", 0) - region.get("state_vector", {}).get("economic_stress", 0),
                    "livelihood_stability": aggregate.get("livelihood_stability", 0) - region.get("state_vector", {}).get("livelihood_stability", 0),
                })
            )

    def _human_nature_feedback_update(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
        interactions: Dict[str, Any],
    ) -> Dict[str, Any]:
        llm_result = self._llm_feedback(round_num, active_variables, diffusion)
        if not llm_result:
            llm_result = self._fallback_feedback(round_num, active_variables, diffusion)

        actor_decisions = []
        ecological_impacts = []
        feedback_propagation = []

        for item in llm_result.get("ecological_impacts") or []:
            region = self.region_lookup.get(item.get("region_id"))
            if not region:
                continue
            delta = {
                "ecosystem_integrity": -abs(float(item.get("ecosystem_integrity_delta", 0))),
                "vulnerability_score": abs(float(item.get("vulnerability_delta", 0))),
                "livelihood_stability": -abs(float(item.get("livelihood_delta", 0))),
            }
            region["state_vector"] = merge_state_vectors(region["state_vector"], delta)
            ecological_impacts.append(
                {
                    "region_id": region["region_id"],
                    "region_name": region["name"],
                    "note": item.get("note", ""),
                    "delta": delta,
                }
            )
            self._write_action(
                platform="twitter",
                round_num=round_num,
                agent_id=600000 + self._region_index(region["region_id"]),
                agent_name=region["name"],
                action_type="ECO_IMPACT",
                action_args=delta,
                result=item.get("note", ""),
            )

        for item in llm_result.get("actor_decisions") or []:
            agent_id = int(item.get("agent_id", -1))
            actor = self.actor_lookup.get(agent_id)
            if not actor:
                continue
            delta = {
                "panic_level": float(item.get("panic_delta", 0)),
                "public_trust": float(item.get("trust_delta", 0)),
                "economic_stress": float(item.get("economic_delta", 0)),
                "response_capacity": float(item.get("response_delta", 0)),
            }
            actor["state_vector"] = merge_state_vectors(actor["state_vector"], delta)
            action_type = str(item.get("action_type") or "DECISION")
            actor_decisions.append(
                {
                    "agent_id": agent_id,
                    "agent_name": actor.get("username") or actor.get("name"),
                    "action_type": action_type,
                    "rationale": item.get("rationale", ""),
                    "delta": delta,
                }
            )
            self._write_action(
                platform="reddit",
                round_num=round_num,
                agent_id=agent_id,
                agent_name=actor.get("username") or actor.get("name"),
                action_type=action_type,
                action_args=delta,
                result=item.get("rationale", ""),
            )

        for item in llm_result.get("feedback_propagation") or []:
            region = self.region_lookup.get(item.get("region_id"))
            if not region:
                continue
            delta = {
                "panic_level": float(item.get("panic_delta", 0)),
                "public_trust": float(item.get("trust_delta", 0)),
                "economic_stress": float(item.get("economic_delta", 0)),
                "livelihood_stability": float(item.get("livelihood_delta", 0)),
                "service_capacity": float(item.get("service_delta", 0)),
            }
            region["state_vector"] = merge_state_vectors(region["state_vector"], delta)
            feedback_propagation.append(
                {
                    "region_id": region["region_id"],
                    "region_name": region["name"],
                    "delta": delta,
                    "loop": item.get("loop", ""),
                }
            )

        return {
            "ecological_impacts": ecological_impacts,
            "actor_decisions": actor_decisions,
            "feedback_propagation": feedback_propagation,
            "turning_points": [
                *(llm_result.get("turning_points") or []),
                *(interactions.get("turning_points") or []),
            ],
        }

    def _build_snapshot(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
        interactions: Dict[str, Any],
        feedback: Dict[str, Any],
    ) -> Dict[str, Any]:
        regions = []
        for region in self.region_graph:
            vector = normalize_state_vector(region.get("state_vector") or {})
            regions.append(
                {
                    "region_id": region["region_id"],
                    "name": region["name"],
                    "region_type": region.get("region_type"),
                    "neighbors": region.get("neighbors", []),
                    "state_vector": vector,
                    **vector,
                    "severity_band": score_band(vector["exposure_score"]),
                    "uncertainty_band": self._uncertainty_band(vector),
                }
            )
        subregions = []
        for region in self.subregion_graph:
            vector = normalize_state_vector(region.get("state_vector") or {})
            subregions.append(
                {
                    "region_id": region["region_id"],
                    "name": region["name"],
                    "region_type": region.get("region_type"),
                    "parent_region_id": region.get("parent_region_id"),
                    "land_use_class": region.get("land_use_class"),
                    "distance_band": region.get("distance_band"),
                    "state_vector": vector,
                    **vector,
                    "severity_band": score_band(vector["exposure_score"]),
                }
            )
        vulnerability_ranking = sorted(
            [
                {
                    "region_id": item["region_id"],
                    "name": item["name"],
                    "vulnerability_score": item["state_vector"]["vulnerability_score"],
                    "exposure_score": item["state_vector"]["exposure_score"],
                }
                for item in regions
            ],
            key=lambda item: (item["vulnerability_score"], item["exposure_score"]),
            reverse=True,
        )
        agent_states = [
            {
                "agent_id": actor.get("agent_id"),
                "agent_name": actor.get("username") or actor.get("name"),
                "name": actor.get("name"),
                "agent_type": actor.get("agent_type") or actor.get("node_family"),
                "agent_subtype": actor.get("agent_subtype") or actor.get("role_type"),
                "primary_region": actor.get("primary_region"),
                "home_subregion_id": actor.get("home_subregion_id"),
                "state_vector": normalize_state_vector(actor.get("state_vector") or {}),
            }
            for actor in self.actor_profiles
        ]
        dynamic_edges = [
            self._serialize_dynamic_edge(edge)
            for edge in self.dynamic_edge_lookup.values()
            if edge.get("status") != "expired"
        ]
        dynamic_edges.sort(
            key=lambda item: (
                item.get("layer") != "structural",
                -float(item.get("strength") or 0),
                str(item.get("edge_id") or ""),
            )
        )
        return {
            "round": round_num,
            "timestamp": self._now(),
            "search_mode": self.search_mode,
            "active_variables": active_variables,
            "regions": regions,
            "subregions": subregions,
            "top_regions": regions[:3],
            "agents": agent_states,
            "top_agents": sorted(
                agent_states,
                key=lambda item: (
                    item["state_vector"].get("vulnerability_score", 0),
                    item["state_vector"].get("exposure_score", 0),
                ),
                reverse=True,
            )[:12],
            "agent_summary": {
                "total_agents": len(agent_states),
                "active_agents": len(interactions.get("active_agent_ids") or []),
                "interaction_count": len(interactions.get("agent_interactions") or []),
                "environment_effect_count": len(interactions.get("agent_environment_effects") or []),
                "dynamic_edge_count": len(dynamic_edges),
            },
            "dynamic_edges": dynamic_edges,
            "dynamic_edge_summary": interactions.get("dynamic_edge_summary") or {
                "search_mode": self.search_mode,
                "total_dynamic_edges": len(dynamic_edges),
            },
            "transport_edges": self.transport_edges,
            "diffusion_context": self.diffusion_context,
            "diffusion": diffusion,
            "interactions": interactions,
            "feedback": feedback,
            "vulnerability_ranking": vulnerability_ranking,
        }

    def _transport_route_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "edge_id": edge.get("edge_id"),
                "source_region_id": edge.get("source_region_id"),
                "target_region_id": edge.get("target_region_id"),
                "channel_type": edge.get("channel_type"),
                "travel_time_rounds": edge.get("travel_time_rounds"),
                "attenuation_rate": edge.get("attenuation_rate"),
                "retention_factor": edge.get("retention_factor"),
            }
            for edge in self.transport_edges[: min(24, len(self.transport_edges))]
        ]

    def _transport_edges_from_region(self, region_id: str) -> List[Dict[str, Any]]:
        return self._transport_edges_for_source(region_id)

    def _transport_edge_between(self, source_region_id: str, target_region_id: str) -> Optional[Dict[str, Any]]:
        target_key = str(target_region_id or "").strip()
        for edge in self._transport_edges_from_region(source_region_id):
            if str(edge.get("target_region_id") or "").strip() == target_key:
                return edge
        return None

    def _llm_diffusion(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        due_transfers: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self.llm:
            return None
        prompt = {
            "task": "Return constrained JSON for region-level pollution spread.",
            "round": round_num,
            "template": self.template,
            "rules": self.template_rules,
            "regions": [
                {
                    "region_id": region["region_id"],
                    "name": region["name"],
                    "neighbors": region.get("neighbors", []),
                    "transport_targets": [
                        {
                            "target_region_id": edge.get("target_region_id"),
                            "channel_type": edge.get("channel_type"),
                            "travel_time_rounds": edge.get("travel_time_rounds"),
                        }
                        for edge in self._transport_edges_from_region(region["region_id"])
                    ],
                    "state_vector": region.get("state_vector", {}),
                }
                for region in self.region_graph
            ],
            "transport_routes": self._transport_route_summary(),
            "active_variables": active_variables,
            "due_transfers": due_transfers,
            "schema": {
                "transfers": [
                    {
                        "source_region": "region_id",
                        "target_region": "region_id",
                        "transfer_intensity": 0,
                        "delay_rounds": 0,
                        "persistence": 0,
                        "confidence": 0.5,
                        "rationale": "string",
                    }
                ]
            },
            "constraints": [
                "Only connect configured transport targets or self.",
                "No teleporting spread.",
                "Keep transfer_intensity between 0 and 100.",
                "If there is no active pressure, return an empty transfer list.",
            ],
        }
        try:
            return self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Return compact JSON only. Respect constraints."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=1400,
            )
        except Exception:
            return None

    def _fallback_diffusion(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        due_transfers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        transfers = []
        decay = self.template_rules["default_decay"]
        lag = self.template_rules["default_lag_rounds"]
        for variable in active_variables:
            source_regions = variable.get("target_regions") or [self.region_graph[0]["region_id"]]
            for source in source_regions:
                transfers.append(
                    {
                        "source_region": source,
                        "target_region": source,
                        "transfer_intensity": clamp_score(variable.get("intensity_0_100", 50)),
                        "delay_rounds": 0,
                        "persistence": clamp_score(self.template_rules["default_persistence"] + variable.get("intensity_0_100", 50) * 0.1),
                        "confidence": 0.62,
                        "rationale": f"Direct pressure from injected variable {variable.get('name')}.",
                    }
                )
                outgoing_edges = self._transport_edges_from_region(source)[: self.template_rules["max_neighbor_spread"]]
                for edge in outgoing_edges:
                    attenuation = float(edge.get("attenuation_rate") or 0)
                    travel_time = int(edge.get("travel_time_rounds") or lag)
                    transfers.append(
                        {
                            "source_region": source,
                            "target_region": edge.get("target_region_id"),
                            "transfer_intensity": clamp_score(variable.get("intensity_0_100", 50) * decay * max(0.18, 1.0 - attenuation)),
                            "delay_rounds": travel_time,
                            "persistence": clamp_score(self.template_rules["default_persistence"]),
                            "confidence": clamp_probability(edge.get("confidence", 0.56)),
                            "rationale": edge.get("rationale") or f"Template-driven diffusion from {source} to connected region.",
                        }
                    )
        for due in due_transfers:
            outgoing_edges = self._transport_edges_from_region(due["target_region"])[:1]
            for edge in outgoing_edges:
                attenuation = float(edge.get("attenuation_rate") or 0)
                travel_time = int(edge.get("travel_time_rounds") or lag)
                transfers.append(
                    {
                        "source_region": due["target_region"],
                        "target_region": edge.get("target_region_id"),
                        "transfer_intensity": clamp_score(
                            due["transfer_intensity"] * decay * 0.8 * max(0.18, 1.0 - attenuation)
                        ),
                        "delay_rounds": travel_time,
                        "persistence": clamp_score(due["persistence"] * decay),
                        "confidence": clamp_probability(edge.get("confidence", 0.5)),
                        "rationale": edge.get("rationale") or "Secondary propagation from already impacted region.",
                    }
                )
        return {"transfers": transfers}

    def _llm_feedback(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.llm:
            return None
        top_regions = diffusion.get("region_ranking", [])[:4]
        top_actors = sorted(
            self.actor_profiles,
            key=lambda actor: actor.get("state_vector", {}).get("vulnerability_score", 0),
            reverse=True,
        )[:8]
        prompt = {
            "task": "Produce constrained JSON for ecological impact, actor decisions, and feedback propagation.",
            "round": round_num,
            "active_variables": active_variables,
            "top_regions": top_regions,
            "top_actors": top_actors,
            "schema": {
                "ecological_impacts": [
                    {
                        "region_id": "region_id",
                        "ecosystem_integrity_delta": 0,
                        "vulnerability_delta": 0,
                        "livelihood_delta": 0,
                        "note": "string",
                    }
                ],
                "actor_decisions": [
                    {
                        "agent_id": 0,
                        "action_type": "DISCLOSE|PANIC_POST|MARKET_SHIFT|RESTRICT|RELOCATE",
                        "panic_delta": 0,
                        "trust_delta": 0,
                        "economic_delta": 0,
                        "response_delta": 0,
                        "rationale": "string",
                    }
                ],
                "feedback_propagation": [
                    {
                        "region_id": "region_id",
                        "panic_delta": 0,
                        "trust_delta": 0,
                        "economic_delta": 0,
                        "livelihood_delta": 0,
                        "service_delta": 0,
                        "loop": "string",
                    }
                ],
                "turning_points": ["string"],
            },
            "constraints": [
                "Keep all deltas between -20 and 20.",
                "Use real agent_id values only.",
                "Keep at most 5 actor decisions.",
                "Return valid JSON only.",
            ],
        }
        try:
            return self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "Return compact JSON only."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.25,
                max_tokens=1800,
            )
        except Exception:
            return None

    def _fallback_feedback(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
    ) -> Dict[str, Any]:
        top_regions = diffusion.get("region_ranking", [])[:3]
        ecological_impacts = []
        feedback_propagation = []
        for item in top_regions:
            ecological_impacts.append(
                {
                    "region_id": item["region_id"],
                    "ecosystem_integrity_delta": clamp_score(item["exposure_score"] * 0.08, 0, 20),
                    "vulnerability_delta": clamp_score(item["exposure_score"] * 0.05, 0, 20),
                    "livelihood_delta": clamp_score(item["exposure_score"] * 0.04, 0, 20),
                    "note": "Exposure degrades ecological integrity and nearby livelihoods.",
                }
            )
            feedback_propagation.append(
                {
                    "region_id": item["region_id"],
                    "panic_delta": min(16, item["exposure_score"] * 0.07),
                    "trust_delta": -min(14, item["exposure_score"] * 0.05),
                    "economic_delta": min(16, item["exposure_score"] * 0.06),
                    "livelihood_delta": -min(14, item["exposure_score"] * 0.05),
                    "service_delta": -min(10, item["exposure_score"] * 0.03),
                    "loop": "environment -> ecology -> livelihood -> panic/media -> market behavior",
                }
            )

        actor_decisions = []
        for actor in self.actor_profiles[: min(5, len(self.actor_profiles))]:
            primary_region = self.region_lookup.get(actor.get("primary_region"))
            if not primary_region:
                continue
            exposure = primary_region.get("state_vector", {}).get("exposure_score", 0)
            if actor.get("node_family") == "GovernmentActor":
                actor_decisions.append(
                    {
                        "agent_id": actor["agent_id"],
                        "action_type": "DISCLOSE" if exposure < 60 else "RESTRICT",
                        "panic_delta": -4 if exposure < 60 else 3,
                        "trust_delta": 4 if exposure < 60 else -2,
                        "economic_delta": 2 if exposure >= 60 else 0,
                        "response_delta": 5,
                        "rationale": "Authorities react by disclosure in moderate cases and restrictions in severe cases.",
                    }
                )
            elif actor.get("node_family") in {"HumanActor", "OrganizationActor"}:
                actor_decisions.append(
                    {
                        "agent_id": actor["agent_id"],
                        "action_type": "MARKET_SHIFT" if exposure > 45 else "PANIC_POST",
                        "panic_delta": 4 if exposure > 35 else 2,
                        "trust_delta": -2,
                        "economic_delta": 5 if exposure > 45 else 1,
                        "response_delta": -1,
                        "rationale": "Affected actors react through rumor amplification or adaptive market behavior.",
                    }
                )

        return {
            "ecological_impacts": ecological_impacts,
            "actor_decisions": actor_decisions[:5],
            "feedback_propagation": feedback_propagation,
            "turning_points": [f"Round {round_num} increased visible stress in {item['name']}" for item in top_regions[:2]],
        }

    def _validate_transfer(self, transfer: Dict[str, Any], active_variables: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        source = transfer.get("source_region")
        target = transfer.get("target_region")
        if source not in self.region_lookup or target not in self.region_lookup:
            return None
        transport_edge = None
        if source != target:
            transport_edge = self._transport_edge_between(source, target)
            if not transport_edge:
                return None
        default_persistence = self.template_rules["default_persistence"]
        if transport_edge:
            default_persistence = clamp_score(
                default_persistence * max(0.2, 1.0 - float(transport_edge.get("attenuation_rate") or 0))
                + 20.0 * float(transport_edge.get("retention_factor") or 0)
            )
        validated = {
            "source_region": source,
            "target_region": target,
            "transfer_intensity": clamp_score(transfer.get("transfer_intensity", 0)),
            "delay_rounds": max(
                0,
                int(
                    transfer.get(
                        "delay_rounds",
                        (transport_edge or {}).get("travel_time_rounds", 0),
                    )
                ),
            ),
            "persistence": clamp_score(transfer.get("persistence", default_persistence)),
            "confidence": clamp_probability(transfer.get("confidence", (transport_edge or {}).get("confidence", 0.5))),
            "rationale": str(transfer.get("rationale", "")),
        }
        if transport_edge:
            validated["channel_type"] = transport_edge.get("channel_type")
            validated["transport_edge_id"] = transport_edge.get("edge_id")
        if not active_variables and validated["transfer_intensity"] > 18:
            validated["transfer_intensity"] = 18
        return validated

    def _active_variables(self, round_num: int) -> List[Dict[str, Any]]:
        active = []
        for variable in self.injections:
            start = int(variable.get("start_round", 1))
            duration = int(variable.get("duration_rounds", 1))
            if start <= round_num < start + duration:
                active.append(variable)
        return active

    def _drain_commands(self) -> None:
        while True:
            command = self.ipc.poll_commands()
            if not command:
                return
            try:
                if command.command_type == CommandType.CLOSE_ENV:
                    self.closed = True
                    self.ipc.send_success(command.command_id, {"message": "EnvFish environment closing"})
                elif command.command_type == CommandType.INJECT_VARIABLE:
                    variable = command.args.get("variable") or {}
                    if "start_round" not in variable or not variable["start_round"]:
                        variable["start_round"] = self.current_round + 1 if self.current_round else 1
                    self.injections.append(variable)
                    append_jsonl(
                        self.intervention_log,
                        {
                            "timestamp": self._now(),
                            "round": self.current_round,
                            "variable": variable,
                            "status": "accepted",
                        },
                    )
                    self.ipc.send_success(
                        command.command_id,
                        {"message": "variable queued", "variable": variable, "current_round": self.current_round},
                    )
                elif command.command_type == CommandType.INTERVIEW:
                    result = self._interview_single(
                        agent_id=int(command.args.get("agent_id", -1)),
                        prompt=str(command.args.get("prompt", "")),
                    )
                    self.ipc.send_success(command.command_id, result)
                elif command.command_type == CommandType.BATCH_INTERVIEW:
                    interviews = command.args.get("interviews") or []
                    results = {}
                    for item in interviews:
                        result = self._interview_single(
                            agent_id=int(item.get("agent_id", -1)),
                            prompt=str(item.get("prompt", "")),
                        )
                        if result.get("results"):
                            results.update(result["results"])
                    self.ipc.send_success(
                        command.command_id,
                        {"results": results, "engine_mode": "envfish", "interviews_count": len(interviews)},
                    )
                else:
                    self.ipc.send_error(command.command_id, f"Unsupported command: {command.command_type}")
            except Exception as exc:
                self.ipc.send_error(command.command_id, str(exc))

    def _inter_round_poll(self) -> None:
        started = time.time()
        while time.time() - started < 0.9:
            self._drain_commands()
            time.sleep(0.15)

    def _interview_single(self, agent_id: int, prompt: str) -> Dict[str, Any]:
        actor = self.actor_lookup.get(agent_id)
        if not actor:
            raise ValueError(f"Unknown agent_id: {agent_id}")
        region = self.region_lookup.get(actor.get("primary_region"), {})
        response = self._answer_interview(actor, region, prompt)
        record = {
            "timestamp": self._now(),
            "round": self.current_round,
            "agent_id": agent_id,
            "agent_name": actor.get("username") or actor.get("name"),
            "profession": actor.get("profession"),
            "prompt": prompt,
            "response": response,
            "region": region.get("name"),
        }
        append_jsonl(self.interview_log, record)
        result = {
            f"reddit_{agent_id}": {
                "agent_id": agent_id,
                "agent_name": actor.get("username") or actor.get("name"),
                "profession": actor.get("profession"),
                "response": response,
                "answer": response,
            },
            f"twitter_{agent_id}": {
                "agent_id": agent_id,
                "agent_name": actor.get("username") or actor.get("name"),
                "profession": actor.get("profession"),
                "response": response,
                "answer": response,
            },
        }
        return {"results": result, "engine_mode": "envfish"}

    def _answer_interview(self, actor: Dict[str, Any], region: Dict[str, Any], prompt: str) -> str:
        if self.llm:
            payload = {
                "task": "Answer in first person as an EnvFish simulated actor.",
                "actor": {
                    "name": actor.get("name"),
                    "username": actor.get("username"),
                    "profession": actor.get("profession"),
                    "node_family": actor.get("node_family"),
                    "persona": actor.get("persona"),
                    "bio": actor.get("bio"),
                    "state_vector": actor.get("state_vector"),
                },
                "region": {
                    "name": region.get("name"),
                    "state_vector": region.get("state_vector"),
                },
                "latest_summary": self.latest_summary.get("feedback", {}),
                "question": prompt,
                "rules": [
                    "Respond in first person.",
                    "Stay within the simulation context.",
                    "Do not mention being an AI model.",
                    "Keep the answer under 180 words.",
                ],
            }
            try:
                return self.llm.chat(
                    messages=[
                        {"role": "system", "content": "You are roleplaying a simulation actor. Be concise and grounded."},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    temperature=0.5,
                    max_tokens=300,
                )
            except Exception:
                pass

        exposure = region.get("state_vector", {}).get("exposure_score", 0)
        panic = region.get("state_vector", {}).get("panic_level", 0)
        return (
            f"我主要关注 {region.get('name', '本地区')} 的局势。现在暴露压力大约在 {exposure:.0f}/100，"
            f"社会恐慌大约在 {panic:.0f}/100。以我的角色来看，最明显的问题是"
            f"{actor.get('profession', actor.get('role_type', '相关主体'))}需要在生态风险和生计压力之间做取舍。"
        )

    def _write_action(
        self,
        platform: str,
        round_num: int,
        agent_id: int,
        agent_name: str,
        action_type: str,
        action_args: Dict[str, Any],
        result: str = "",
    ) -> None:
        payload = {
            "round": round_num,
            "timestamp": self._now(),
            "agent_id": agent_id,
            "agent_name": agent_name,
            "action_type": action_type,
            "action_args": action_args,
            "result": result,
            "success": True,
            "platform": platform,
        }
        append_jsonl(self.twitter_log if platform == "twitter" else self.reddit_log, payload)

    def _write_platform_event(self, platform: str, payload: Dict[str, Any]) -> None:
        append_jsonl(self.twitter_log if platform == "twitter" else self.reddit_log, payload)

    def _write_env_status(self, status: str) -> None:
        dump_json(
            os.path.join(self.sim_dir, "env_status.json"),
            {
                "status": status,
                "timestamp": self._now(),
                "engine_mode": "envfish",
                "twitter_available": True,
                "reddit_available": True,
            },
        )

    def _region_index(self, region_id: str) -> int:
        for index, region in enumerate(self.region_graph):
            if region["region_id"] == region_id:
                return index
        return 0

    def _uncertainty_band(self, vector: Dict[str, Any]) -> Dict[str, Any]:
        trust = clamp_score(vector.get("public_trust", 50))
        exposure = clamp_score(vector.get("exposure_score", 0))
        confidence = clamp_probability((trust / 100 * 0.3) + (1 - exposure / 100) * 0.4 + 0.3)
        return {
            "confidence": confidence,
            "label": "higher" if confidence >= 0.7 else "medium" if confidence >= 0.45 else "low",
        }

    def _now(self) -> str:
        return datetime.now().isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--max-rounds", type=int)
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()

    runtime = EnvFishRuntime(config_path=args.config, max_rounds=args.max_rounds, no_wait=args.no_wait)
    runtime.run()


if __name__ == "__main__":
    random.seed(42)
    main()
