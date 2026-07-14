"""
EnvFish region-level simulation runner.

This is a constrained, semi-quantitative eco-social sandbox. It does not solve
physical equations; it produces region-level spread and human-nature feedback
using structured LLM output with deterministic validation and rule-based
fallbacks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
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

from app.services.agent_action_contract import (  # noqa: E402
    AGENT_ACTION_CONTRACT_VERSION,
    action_label_zh,
    consume_action_resources,
    validate_agent_action,
)
from app.services.agent_emergence_detector import AgentEmergenceDetector  # noqa: E402
from app.services.agent_relationship_runtime import (  # noqa: E402
    apply_relationship_event,
    build_interaction_event,
    build_lifecycle_event,
    initialize_relationship_states,
    relationship_contract_id,
    upsert_relationship_state,
)
from app.services.agent_state_mutation import (  # noqa: E402
    apply_state_delta,
    mutation_refs,
    resource_mutation_records,
)
from app.services.effort_contract import build_effort_snapshot, effort_operation_limit  # noqa: E402
from app.services.envfish_models import (  # noqa: E402
    clamp_probability,
    clamp_score,
    dump_json,
    get_template_rules,
    merge_state_vectors,
    normalize_state_vector,
    normalize_transport_family,
    score_band,
)
from app.services.mechanism_simulation_service import (  # noqa: E402
    LLM_MECHANISM_ARCHITECTURE,
    is_llm_mechanism_architecture,
    normalize_simulation_architecture,
)
from app.services.policy_runtime import execute_policy_binding  # noqa: E402
from app.services.risk_artifact_store import load_risk_artifacts, write_risk_artifacts  # noqa: E402
from app.services.risk_definition_builder import RiskDefinitionBuilder  # noqa: E402
from app.services.risk_emergence_detector import RiskEmergenceDetector  # noqa: E402
from app.services.risk_event_engine import RiskEventEngine  # noqa: E402
from app.services.risk_runtime_tracker import RiskRuntimeTracker  # noqa: E402
from app.services.simulation_ipc import CommandType, SimulationIPCServer  # noqa: E402
from app.utils.llm_client import LLMClient  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

if os.path.exists(os.path.join(_project_root, ".env")):
    load_dotenv(os.path.join(_project_root, ".env"))

logger = get_logger("envfish.runtime")


_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_INTERNAL_DISPLAY_PATTERN = re.compile(
    r"(?:(?:agent|entity|region|snapshot|fallback|unknown|unnamed)(?![A-Za-z0-9])|"
    r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+|"
    r"[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]+)+|"
    r"[0-9a-f]{8}-[0-9a-f-]{20,})",
    re.IGNORECASE,
)


def _chinese_display_text(value: Any, fallback: str) -> str:
    """Validate generated display copy while leaving machine fields untouched."""

    text = str(value or "").strip()
    if (
        not text
        or not _CJK_PATTERN.search(text)
        or re.search(r"[A-Za-z]", text)
        or _INTERNAL_DISPLAY_PATTERN.search(text)
    ):
        return fallback
    return text


def _chinese_display_list(value: Any, fallback: List[str], *, limit: int = 8) -> List[str]:
    raw_items = value if isinstance(value, list) else []
    localized = [_chinese_display_text(item, "") for item in raw_items[:limit]]
    localized = [item for item in localized if item]
    return localized or list(fallback[:limit])


def _localized_reason_records(
    value: Any,
    *,
    display_fields: Dict[str, str],
    limit: int,
) -> List[Dict[str, Any]]:
    localized: List[Dict[str, Any]] = []
    for item in (value if isinstance(value, list) else [])[:limit]:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        for field_name, fallback in display_fields.items():
            normalized[field_name] = _chinese_display_text(item.get(field_name), fallback)
        localized.append(normalized)
    return localized


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


def _stable_runtime_event_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(
        parts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def _causal_metadata(
    event_id: str,
    causal_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize only caller-proven causal links.

    Missing context deliberately creates a new root.  In particular, this
    helper never infers parents from a shared round, region, or endpoint.
    """

    context = dict(causal_context or {})
    parent_event_ids: List[str] = []
    for value in context.get("parent_event_ids") or []:
        parent_id = str(value or "").strip()
        if parent_id and parent_id != event_id and parent_id not in parent_event_ids:
            parent_event_ids.append(parent_id)
    root_event_id = str(context.get("root_event_id") or "").strip()
    if not root_event_id:
        root_event_id = parent_event_ids[0] if parent_event_ids else event_id
    try:
        hop = max(0, int(context.get("hop")))
    except (TypeError, ValueError):
        hop = 1 if parent_event_ids else 0
    return {
        "root_event_id": root_event_id,
        "parent_event_ids": parent_event_ids,
        "hop": hop,
    }


def _child_causal_context(event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        return {}
    event_id = str(event.get("event_id") or event.get("relationship_event_id") or "").strip()
    if not event_id:
        return {}
    try:
        hop = max(0, int(event.get("hop") or 0)) + 1
    except (TypeError, ValueError):
        hop = 1
    return {
        "root_event_id": str(event.get("root_event_id") or event_id),
        "parent_event_ids": [event_id],
        "hop": hop,
    }


def normalize_runtime_injection_schedule(
    variable: Dict[str, Any],
    *,
    current_round: int,
) -> Dict[str, Any]:
    """Fill an omitted start round without treating explicit round zero as empty."""

    start_round = variable.get("start_round")
    if start_round is None or start_round == "":
        variable["start_round"] = current_round + 1 if current_round else 1
    else:
        variable["start_round"] = max(0, int(start_round))
    return variable


class EnvFishRuntime:
    def __init__(self, config_path: str, max_rounds: Optional[int] = None, no_wait: bool = False):
        self.config_path = os.path.abspath(config_path)
        with open(self.config_path, "r", encoding="utf-8") as handle:
            self.config = json.load(handle)

        self.sim_dir = os.path.dirname(self.config_path)
        self.no_wait = no_wait
        self.transport_profile = deepcopy(self.config.get("transport_profile") or {})
        self.simulation_architecture = normalize_simulation_architecture(
            self.config.get("simulation_architecture")
        )
        self.is_mechanism_runtime = is_llm_mechanism_architecture(self.simulation_architecture)
        self.scenario_model = deepcopy(self.config.get("scenario_model") or {})
        self.mechanism_graph = deepcopy(self.config.get("mechanism_graph") or {})
        self.scenario_state_schema = deepcopy(self.config.get("scenario_state_schema") or {})
        self.template = normalize_transport_family(
            self.transport_profile.get("primary_family") or self.config.get("diffusion_template", "generic")
        )
        self.template_rules = get_template_rules(self.template)
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
        self.relationship_states = initialize_relationship_states(
            self.agent_relationship_graph,
            self.config.get("relationship_states") or [],
        )
        self.region_agent_index = deepcopy(self.config.get("region_agent_index") or {})
        self.role_demands = deepcopy(self.config.get("role_demands") or [])
        self.policy_execution_plan = deepcopy(self.config.get("policy_execution_plan") or {})
        self.policy_execution_runtime_state = deepcopy(
            self.config.get("policy_execution_runtime_state") or {}
        )
        self.agent_plan_source = str(self.config.get("agent_plan_source") or "").strip()
        planning_input = dict(self.config.get("scenario_planning_input") or {})
        self.scenario_version_ref = {
            "artifact_id": str(planning_input.get("planning_input_id") or self.config.get("simulation_id") or ""),
            "contract_version": str(planning_input.get("contract_version") or "scenario_planning.v2"),
            "content_hash": str(planning_input.get("content_hash") or ""),
        }
        self.effort_snapshot = deepcopy(
            self.config.get("effort_snapshot")
            or build_effort_snapshot(
                "high",
                effort_snapshot_id=f"effort_runtime_{hashlib.sha256(self.sim_dir.encode('utf-8')).hexdigest()[:12]}",
                source="legacy_migration",
            )
        )
        self.agent_emergence_state = deepcopy(self.config.get("agent_emergence_state") or {})
        self.interaction_policies = deepcopy(self.config.get("interaction_policies") or {})
        self.runtime_limits = deepcopy(self.config.get("runtime_limits") or {})
        self.risk_objects = deepcopy(self.config.get("risk_objects") or [])
        self.risk_definitions = deepcopy(self.config.get("risk_definitions") or [])
        self.latest_risk_runtime_state = deepcopy(self.config.get("latest_risk_runtime_state") or {})
        self.diffusion_context = deepcopy(self.config.get("diffusion_context") or {})
        # M6: structured propagation channels (channel -> receptor dim + gain). They
        # MODULATE the diffusion transfer per channel. Read from the transport
        # profile, the diffusion_context, or the hazard recommendation, in that
        # order. Empty => the modulation pass is a graceful no-op (legacy runs).
        self.propagation_channels = self._load_propagation_channels()
        self.propagation_channels_by_id = {
            str(channel.get("channel_id") or "").lower(): channel
            for channel in self.propagation_channels
            if str(channel.get("channel_id") or "").strip()
        }
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
        self.relationship_event_log = os.path.join(self.sim_dir, "relationship_event_ledger.jsonl")
        self.relationship_state_path = os.path.join(self.sim_dir, "latest_relationship_states.json")
        self.state_mutation_log = os.path.join(self.sim_dir, "state_mutation_ledger.jsonl")
        self.round_reasoning_log = os.path.join(self.sim_dir, "round_reasoning_ledger.jsonl")
        self.agent_emergence_log = os.path.join(self.sim_dir, "agent_emergence_ledger.jsonl")
        self.agent_lineage_log = os.path.join(self.sim_dir, "agent_lineage_ledger.jsonl")
        self.agent_candidate_log = os.path.join(self.sim_dir, "agent_candidate_ledger.jsonl")
        self.agent_action_decision_log = os.path.join(self.sim_dir, "agent_action_decision_ledger.jsonl")
        self.policy_execution_log = os.path.join(self.sim_dir, "policy_execution_ledger.jsonl")
        self.policy_execution_state_path = os.path.join(
            self.sim_dir, "latest_policy_execution_state.json"
        )
        self.agent_emergence_state_path = os.path.join(self.sim_dir, "agent_emergence_state.json")
        self.state_matrix_log = os.path.join(self.sim_dir, "round_state_matrix.jsonl")
        self.intervention_log = os.path.join(self.sim_dir, "intervention_log.jsonl")
        self.interview_log = os.path.join(self.sim_dir, "interviews.jsonl")
        self.latest_snapshot_path = os.path.join(self.sim_dir, "latest_round_snapshot.json")
        self.region_graph_path = os.path.join(self.sim_dir, "region_graph_snapshot.json")
        self.subregion_graph_path = os.path.join(self.sim_dir, "subregion_graph_snapshot.json")
        self.transport_edges_path = os.path.join(self.sim_dir, "transport_edges_snapshot.json")

        self.risk_tracker = RiskRuntimeTracker()
        self.agent_emergence_detector = AgentEmergenceDetector()
        self.risk_definition_builder = RiskDefinitionBuilder()
        self.risk_emergence_detector = RiskEmergenceDetector()
        self.risk_event_engine = RiskEventEngine()
        risk_artifacts = load_risk_artifacts(self.sim_dir)
        if risk_artifacts.get("risk_definitions"):
            self.risk_definitions = deepcopy(risk_artifacts.get("risk_definitions") or self.risk_definitions)
        if risk_artifacts.get("latest_risk_runtime_state"):
            self.latest_risk_runtime_state = deepcopy(
                risk_artifacts.get("latest_risk_runtime_state") or self.latest_risk_runtime_state
            )
        if risk_artifacts.get("risk_objects"):
            self.risk_objects = deepcopy(risk_artifacts.get("risk_objects") or self.risk_objects)
        self.risk_events = list(risk_artifacts.get("risk_events") or [])
        self.risk_contract_version = int(
            risk_artifacts.get("risk_contract_version")
            or self.config.get("risk_contract_version")
            or 1
        )
        self.risk_generation_audit = dict(risk_artifacts.get("risk_generation_audit") or self.config.get("risk_generation_audit") or {})
        self.risk_candidate_ledger = list(risk_artifacts.get("risk_candidate_ledger") or [])
        self.risk_generation_notes = list((risk_artifacts.get("risk_objects_summary") or {}).get("generation_notes") or [])

        dump_json(self.region_graph_path, self.region_graph)
        dump_json(self.subregion_graph_path, self.subregion_graph)

        self.region_lookup = {item["region_id"]: item for item in self.region_graph}
        self.region_name_lookup = {
            str(item.get("name") or "").strip().lower(): item["region_id"]
            for item in self.region_graph
            if str(item.get("name") or "").strip()
        }
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
        self.relationships_by_target: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for edge in self.agent_relationship_graph:
            try:
                source_agent_id = int(edge.get("source_agent_id"))
                target_agent_id = int(edge.get("target_agent_id"))
            except Exception:
                continue
            self.relationships_by_source[source_agent_id].append(edge)
            self.relationships_by_target[target_agent_id].append(edge)
        self._rebuild_relationship_state_index()
        dump_json(self.relationship_state_path, self.relationship_states)
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
        self._rebuild_risk_indexes()

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
        self.max_deep_agents_per_round = int(
            effort_operation_limit(self.effort_snapshot, "step3", "deep_agents_per_round")
        )
        self.action_candidates_per_agent = int(
            effort_operation_limit(self.effort_snapshot, "step3", "actions_per_deep_agent")
        )
        self.dynamic_relationship_validation_limit = int(
            effort_operation_limit(
                self.effort_snapshot,
                "step3",
                "dynamic_relationship_validations_per_round",
            )
        )
        if self.agent_plan_source == "agent_v2":
            self.allowed_cross_region_hops = int(
                effort_operation_limit(self.effort_snapshot, "step3", "relationship_hops")
            )
        self.edge_promotion_enabled = bool(self.interaction_policies.get("edge_promotion_enabled", True))
        # M8: relationships are no longer a read-only decoration — an active edge
        # transmits stress between its endpoint regions (state is a byproduct of
        # relationships). Bounded by the state gap and edge strength.
        self.relationship_coupling_enabled = bool(self.interaction_policies.get("relationship_coupling_enabled", True))
        self.relationship_coupling_gain = float(self.interaction_policies.get("relationship_coupling_gain", 0.06))
        self.latest_relationship_coupling: Dict[str, Any] = {"coupled_edges": 0, "total_transfer": 0.0}

        # M7: the scenario mechanism graph used to be written-then-frozen — it
        # never entered the physical loop, so its directions/signs drove nothing.
        # We now let mechanism edges (whose endpoints map to regions) apply a
        # LIGHT, BOUNDED, signed nudge to the target region's pressure dimensions.
        # Guarded behind the mechanism runtime + an explicit flag so legacy runs
        # are unaffected, and a no-op if no edge endpoint resolves to a region.
        self.mechanism_propagation_enabled = bool(
            self.interaction_policies.get("mechanism_propagation_enabled", True)
        )
        self.mechanism_propagation_gain = float(
            self.interaction_policies.get("mechanism_propagation_gain", 0.04)
        )
        self.latest_mechanism_propagation: Dict[str, Any] = {"nudged_edges": 0, "total_nudge": 0.0}
        self._mechanism_region_index: Optional[Dict[str, str]] = None

        # M6: per-channel modulation knobs. `propagation_channel_gain` is a small
        # base multiplier applied on top of each channel's relative gain, bounded
        # so channels inform — never dominate — the transfer.
        self.propagation_channels_enabled = bool(
            self.interaction_policies.get("propagation_channels_enabled", True)
        )
        self.propagation_channel_gain = float(
            self.interaction_policies.get("propagation_channel_gain", 0.5)
        )
        self.latest_propagation_modulation: Dict[str, Any] = {"modulated_transfers": 0, "total_delta": 0.0}

        # M8: every N rounds the LLM is asked to RE-LABEL the live relationship
        # graph (semantic relabels / leverage hints / emergent-pattern notes). It
        # is the only thing the LLM does to relationships; a deterministic fallback
        # runs when there is no LLM so the ledger is never silently empty. Bounded
        # and additive — emitted into the round_reasoning_ledger record only.
        self.relation_relabel_enabled = bool(
            self.interaction_policies.get("relation_relabel_enabled", True)
        )
        self.relation_relabel_interval = max(
            1, int(self.interaction_policies.get("relation_relabel_interval_rounds", 3))
        )
        self.latest_relation_relabel: Dict[str, Any] = {}

        # M8: cap on co-location interaction candidates per actor (keeps the
        # interaction ledger bounded in dense regions).
        self._colocation_candidate_limit = max(
            1, int(self.interaction_policies.get("colocation_candidates_per_agent", 3))
        )

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
                        "rationale": "已将历史相邻区域关系转换为有方向的传输边。",
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

    def _resolve_region_key(self, value: Any) -> str:
        token = str(value or "").strip()
        if not token:
            return ""
        if token in self.region_lookup:
            return token
        return str(self.region_name_lookup.get(token.lower()) or "")

    def _rebuild_risk_indexes(self) -> None:
        self.agent_risk_lookup = defaultdict(list)
        self.risk_actor_lookup = defaultdict(list)
        self.risk_region_lookup = defaultdict(list)

        if self.risk_definitions:
            runtime_by_id = {
                str(item.get("risk_id") or "").strip(): item
                for item in (self.latest_risk_runtime_state.get("risk_states") or [])
                if str(item.get("risk_id") or "").strip()
            }
            for risk in self.risk_definitions:
                if not isinstance(risk, dict):
                    continue
                risk_id = str(risk.get("risk_id") or risk.get("legacy_risk_object_id") or "").strip()
                if not risk_id:
                    continue
                scope = risk.get("scope") or {}
                regions: List[str] = []
                for region_ref in (scope.get("regions") or []) + (runtime_by_id.get(risk_id, {}).get("impacted_regions") or []):
                    region_key = self._resolve_region_key(
                        region_ref.get("region_id") or region_ref.get("region_name")
                    )
                    if region_key and region_key not in regions:
                        regions.append(region_key)
                self.risk_region_lookup[risk_id] = regions

                actor_ids: List[int] = []
                for actor_ref in scope.get("actors") or []:
                    if str(actor_ref.get("actor_id") or "").isdigit():
                        actor_ids.append(int(actor_ref.get("actor_id")))
                for cluster in risk.get("affected_clusters") or []:
                    if not isinstance(cluster, dict):
                        continue
                    for actor_id in cluster.get("actor_ids") or []:
                        if str(actor_id or "").isdigit():
                            actor_ids.append(int(actor_id))
                for actor_ref in runtime_by_id.get(risk_id, {}).get("impacted_actors") or []:
                    if str(actor_ref.get("actor_id") or "").isdigit():
                        actor_ids.append(int(actor_ref.get("actor_id")))
                deduped_actor_ids = sorted(set(actor_ids))
                self.risk_actor_lookup[risk_id] = deduped_actor_ids
                for actor_id in deduped_actor_ids:
                    self.agent_risk_lookup[actor_id].append(risk_id)
            return

        for risk in self.risk_objects:
            if not isinstance(risk, dict):
                continue
            risk_id = str(risk.get("risk_object_id") or risk.get("title") or "").strip()
            if not risk_id:
                continue
            regions = []
            for region_id in (risk.get("primary_regions") or []) + (risk.get("region_scope") or []):
                region_key = self._resolve_region_key(region_id)
                if region_key and region_key not in regions:
                    regions.append(region_key)
            self.risk_region_lookup[risk_id] = regions
            actor_ids: List[int] = []
            for cluster in risk.get("affected_clusters") or []:
                if not isinstance(cluster, dict):
                    continue
                for actor_id in cluster.get("actor_ids") or []:
                    if str(actor_id or "").isdigit():
                        actor_ids.append(int(actor_id))
            deduped_actor_ids = sorted(set(actor_ids))
            self.risk_actor_lookup[risk_id] = deduped_actor_ids
            for actor_id in deduped_actor_ids:
                self.agent_risk_lookup[actor_id].append(risk_id)

    def _persist_runtime_config(self) -> None:
        self.config["injected_variables"] = deepcopy(self.injections)
        self.config["actor_profiles"] = deepcopy(self.actor_profiles)
        self.config["effort_snapshot"] = deepcopy(self.effort_snapshot)
        self.config["agent_emergence_state"] = deepcopy(self.agent_emergence_state)
        self.config["policy_execution_runtime_state"] = deepcopy(
            self.policy_execution_runtime_state
        )
        self.config["runtime_agent_count"] = len(self.actor_profiles)
        self.config["relationship_states"] = deepcopy(self.relationship_states)
        self.config["risk_definitions"] = deepcopy(self.risk_definitions)
        self.config["risk_contract_version"] = int(self.risk_contract_version)
        self.config["risk_generation_audit"] = deepcopy(self.risk_generation_audit)
        self.config["latest_risk_runtime_state"] = deepcopy(self.latest_risk_runtime_state)
        self.config["risk_objects"] = deepcopy(self.risk_objects)
        self.config["primary_risk_object_id"] = str(
            (self.latest_risk_runtime_state.get("primary_active_risk_id") or self.config.get("primary_risk_object_id") or "")
        )
        self.config["primary_active_risk_id"] = str(self.latest_risk_runtime_state.get("primary_active_risk_id") or "")
        dump_json(self.config_path, self.config)
        dump_json(os.path.join(self.sim_dir, "injected_variables.json"), self.injections)
        dump_json(self.agent_emergence_state_path, self.agent_emergence_state)
        dump_json(self.relationship_state_path, self.relationship_states)
        dump_json(self.policy_execution_state_path, self.policy_execution_runtime_state)

    def _execute_policy_plan(self, round_num: int) -> Dict[str, Any]:
        bindings = list((self.policy_execution_plan or {}).get("policy_bindings") or [])
        if not bindings:
            return {
                "contract_version": "policy-execution-runtime.v2",
                "round_number": int(round_num),
                "execution_records": [],
                "state_mutation_records": [],
                "emergent_role_demands": [],
                "summary": {"due_count": 0, "executed_count": 0, "blocked_count": 0},
            }

        previous_event_ids = set(
            str(item or "")
            for item in (self.policy_execution_runtime_state.get("recorded_execution_ids") or [])
            if str(item or "")
        )
        available_region_ids = [*self.region_lookup.keys(), *self.subregion_lookup.keys()]
        execution_records: List[Dict[str, Any]] = []
        state_mutations: List[Dict[str, Any]] = []
        emergent_demands: List[Dict[str, Any]] = []
        for binding in bindings:
            event = execute_policy_binding(
                binding=binding,
                actor_lookup=self.actor_lookup,
                round_number=round_num,
                available_target_region_ids=available_region_ids,
                scenario_version_ref=self.scenario_version_ref,
            )
            if not event:
                continue
            event_id = str(event.get("policy_execution_id") or "")
            if event_id in previous_event_ids:
                continue

            event_mutations: List[Dict[str, Any]] = []
            source_ref = {
                "artifact_id": event_id,
                "contract_version": str(event.get("contract_version") or "policy-execution-event.v2"),
            }
            evidence_refs = [
                f"policy:{event.get('policy_id')}",
                *(f"event:{item}" for item in binding.get("target_event_ids") or []),
                *(f"mechanism:{item}" for item in binding.get("target_mechanism_ids") or []),
            ]
            if event.get("execution_status") == "executed":
                for settlement in event.get("resource_settlements") or []:
                    event_mutations.extend(
                        resource_mutation_records(
                            settlement=settlement,
                            round_number=round_num,
                            source_ref=source_ref,
                            agent_id=settlement.get("agent_id"),
                            evidence_refs=evidence_refs,
                            scenario_version_ref=self.scenario_version_ref,
                            source_type="policy_execution",
                        )
                    )
                for target_region_id in event.get("target_region_ids") or []:
                    target = self.region_lookup.get(str(target_region_id))
                    target_type = "region"
                    if target is None:
                        target = self.subregion_lookup.get(str(target_region_id))
                        target_type = "subregion"
                    if target is None:
                        continue
                    next_vector, records = apply_state_delta(
                        current_vector=target.get("state_vector") or {},
                        delta=event.get("state_effect_delta") or {},
                        round_number=round_num,
                        source_ref=source_ref,
                        target_type=target_type,
                        target_id=target_region_id,
                        evidence_refs=evidence_refs,
                        scenario_version_ref=self.scenario_version_ref,
                        source_type="policy_execution",
                    )
                    target["state_vector"] = next_vector
                    event_mutations.extend(records)
            else:
                missing_capabilities = list(event.get("missing_capability_keys") or [])
                required_capabilities = list(event.get("required_capability_keys") or [])
                demand_capabilities = missing_capabilities or required_capabilities
                if demand_capabilities:
                    emergent_demands.append(
                        {
                            "demand_id": f"runtime_policy_{event.get('policy_id')}_{round_num}",
                            "demand_key": "policy_execution",
                            "label_zh": f"{event.get('policy_label_zh') or '政策措施'}执行能力",
                            "required_capability_keys": demand_capabilities,
                            "required_permissions": [
                                permission
                                for group in event.get("missing_permission_groups") or []
                                for permission in group
                            ],
                            "required_resource_types": list(
                                event.get("missing_resource_keys") or []
                            ),
                            "jurisdiction_region_ids": list(
                                event.get("target_region_ids") or []
                            ),
                            "required_resolution": "organization",
                            "importance": "high",
                            "evidence_score": 78,
                            "impact_score": 70,
                            "evidence_refs": [f"policy_execution:{event_id}"],
                            "source_type": "runtime_policy_execution",
                            "runtime_discovered": True,
                            "created_round": int(round_num),
                        }
                    )

            event["state_mutation_refs"] = mutation_refs(event_mutations)
            event["state_mutation_count"] = len(event_mutations)
            execution_records.append(event)
            state_mutations.extend(event_mutations)
            previous_event_ids.add(event_id)
            append_jsonl(self.policy_execution_log, event)
            for record in event_mutations:
                append_jsonl(self.state_mutation_log, record)

        if any(
            record.get("execution_status") == "executed"
            and any(
                str(region_id) in self.subregion_lookup
                for region_id in record.get("target_region_ids") or []
            )
            for record in execution_records
        ):
            self._roll_up_subregions()

        historical_records = list(
            self.policy_execution_runtime_state.get("recent_execution_records") or []
        )
        historical_records.extend(execution_records)
        self.policy_execution_runtime_state = {
            "contract_version": "policy-execution-runtime.v2",
            "last_round": int(round_num),
            "recorded_execution_ids": sorted(previous_event_ids),
            "recent_execution_records": historical_records[-100:],
            "summary": {
                "recorded_count": len(previous_event_ids),
                "executed_count": sum(
                    1
                    for item in historical_records
                    if item.get("execution_status") == "executed"
                ),
                "blocked_count": sum(
                    1
                    for item in historical_records
                    if item.get("execution_status") == "blocked"
                ),
            },
        }
        dump_json(self.policy_execution_state_path, self.policy_execution_runtime_state)
        return {
            "contract_version": "policy-execution-runtime.v2",
            "round_number": int(round_num),
            "execution_records": execution_records,
            "state_mutation_records": state_mutations,
            "emergent_role_demands": emergent_demands,
            "summary": {
                "due_count": len(execution_records),
                "executed_count": sum(
                    1 for item in execution_records if item.get("execution_status") == "executed"
                ),
                "blocked_count": sum(
                    1 for item in execution_records if item.get("execution_status") == "blocked"
                ),
            },
        }

    def _refresh_risk_runtime(
        self,
        round_num: int,
        snapshot: Optional[Dict[str, Any]] = None,
        refresh_reason: str = "round_refresh",
        append_history: bool = True,
    ) -> Dict[str, Any]:
        previous_bundle = deepcopy(self.latest_risk_runtime_state or {})
        if snapshot:
            next_bundle = self.risk_tracker.refresh(
                risk_definitions=self.risk_definitions,
                snapshot=snapshot,
                previous_bundle=previous_bundle,
                risk_events=self.risk_events,
                primary_hint=str(
                    previous_bundle.get("primary_active_risk_id")
                    or self.config.get("primary_active_risk_id")
                    or self.config.get("primary_risk_object_id")
                    or ""
                ),
                pinned_risk_ids=list(previous_bundle.get("pinned_risk_ids") or []),
                refresh_reason=refresh_reason,
            )
        else:
            next_bundle = self.risk_tracker.build_initial_bundle(
                risk_definitions=self.risk_definitions,
                primary_risk_id=str(
                    self.config.get("primary_active_risk_id")
                    or self.config.get("primary_risk_object_id")
                    or ""
                ),
                source_risk_objects=self.risk_objects,
            )

        transition_events = self.risk_event_engine.build_transition_events(previous_bundle, next_bundle)
        if transition_events:
            self.risk_events.extend(transition_events)
        runtime_events = self.risk_event_engine.build_runtime_events(previous_bundle, next_bundle)
        if runtime_events:
            self.risk_events.extend(runtime_events)

        runtime_metrics = dict(self.risk_generation_audit.get("runtime_metrics") or {})
        sample_count = int(runtime_metrics.get("sample_count") or 0) + 1
        active_count = sum(
            1
            for state in (next_bundle.get("risk_states") or [])
            if str(state.get("status") or "watch") not in {"dormant", "resolved"}
        )
        previous_average = float(runtime_metrics.get("average_active_risk_count") or 0.0)
        runtime_metrics.update({
            "sample_count": sample_count,
            "average_active_risk_count": round(((previous_average * (sample_count - 1)) + active_count) / sample_count, 3),
            "latest_active_risk_count": active_count,
            "emergence_count": int(self.risk_generation_audit.get("emergence_count") or 0),
            "primary_risk_switch_count": int(runtime_metrics.get("primary_risk_switch_count") or 0) + len(transition_events),
        })
        self.risk_generation_audit["runtime_metrics"] = runtime_metrics

        artifacts = write_risk_artifacts(
            sim_dir=self.sim_dir,
            risk_definitions=self.risk_definitions,
            latest_runtime_bundle=next_bundle,
            primary_risk_id=str(
                self.config.get("primary_risk_object_id")
                or next_bundle.get("primary_active_risk_id")
                or ""
            ),
            generation_notes=self.risk_generation_notes,
            risk_events=self.risk_events,
            append_runtime_history=append_history,
            runtime_history_entry=next_bundle,
            risk_contract_version=self.risk_contract_version,
            generation_audit=self.risk_generation_audit,
            candidate_ledger=self.risk_candidate_ledger,
        )
        self.latest_risk_runtime_state = deepcopy(artifacts["latest_risk_runtime_state"])
        self.risk_objects = deepcopy(artifacts["risk_objects"])
        self._rebuild_risk_indexes()
        self._persist_runtime_config()
        return self.latest_risk_runtime_state

    def _detect_runtime_risk_emergence(
        self,
        *,
        round_num: int,
        active_variables: List[Dict[str, Any]],
    ) -> None:
        if self.risk_contract_version < 2:
            return
        runtime_relationships = list(self.agent_relationship_graph)
        runtime_relationships.extend(
            self._serialize_dynamic_edge(edge)
            for edge in self.dynamic_edge_lookup.values()
            if edge.get("status") not in {"expired", "dormant"}
        )
        result = self.risk_emergence_detector.detect(
            existing_definitions=self.risk_definitions,
            previous_runtime_bundle=self.latest_risk_runtime_state,
            current_round=round_num,
            active_variables=active_variables,
            regions=self.region_graph,
            subregions=self.subregion_graph,
            profiles=self.actor_profiles,
            transport_edges=self.transport_edges,
            agent_relationships=runtime_relationships,
            simulation_requirement=self.config.get("simulation_requirement") or "",
        )
        self.risk_definitions = deepcopy(result.risk_definitions)
        self.latest_risk_runtime_state["emergence_candidates"] = deepcopy(result.candidate_state)
        if result.events:
            self.risk_events.extend(result.events)
        if result.candidate_ledger:
            for item in result.candidate_ledger:
                self.risk_candidate_ledger.append({
                    **item,
                    "round": round_num,
                    "timestamp": self._now(),
                })
        if result.created_risk_ids:
            self.risk_generation_audit["emergence_count"] = int(self.risk_generation_audit.get("emergence_count") or 0) + len(result.created_risk_ids)
            self.risk_generation_audit["latest_emergent_risk_ids"] = list(result.created_risk_ids)
            runtime_metrics = dict(self.risk_generation_audit.get("runtime_metrics") or {})
            runtime_metrics["emergence_count"] = int(self.risk_generation_audit["emergence_count"])
            self.risk_generation_audit["runtime_metrics"] = runtime_metrics
        if result.dormant_risk_ids:
            self.risk_generation_audit["latest_dormant_risk_ids"] = list(result.dormant_risk_ids)
        self._rebuild_risk_indexes()

    def _activate_due_runtime_agents(self, round_num: int) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for actor in self.actor_profiles:
            lifecycle = actor.get("runtime_lifecycle") or {}
            lifecycle_status = str(lifecycle.get("lifecycle_status") or "")
            if lifecycle_status not in {"pending_activation", "dormant"}:
                continue
            activation_round = int(
                lifecycle.get("activation_round")
                or actor.get("activation_round")
                or round_num + 1
            )
            if activation_round > round_num:
                continue
            lifecycle["lifecycle_status"] = "active"
            lifecycle["activated_round"] = round_num
            actor["runtime_lifecycle"] = lifecycle
            actor["lifecycle_status"] = "active"
            actor["activation_round"] = activation_round
            event = {
                "event_id": f"agent_activation_{actor.get('agent_id')}_{round_num}",
                "event_type": "agent_activated",
                "agent_id": actor.get("agent_id"),
                "round": round_num,
                "effective_round": round_num,
                "summary": f"{actor.get('name') or '运行期 Agent'} 已在本轮开始参与推演。",
                "timestamp": self._now(),
            }
            events.append(event)
            append_jsonl(self.agent_emergence_log, event)
        return events

    def _detect_runtime_agent_emergence(
        self,
        *,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        interactions: Dict[str, Any],
        feedback: Dict[str, Any],
        policy_execution: Optional[Dict[str, Any]] = None,
        risk_runtime: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result = self.agent_emergence_detector.evaluate(
            current_round=round_num,
            actor_profiles=self.actor_profiles,
            effort_snapshot=self.effort_snapshot,
            role_demands=self.role_demands,
            runtime_signals={
                "active_variables": active_variables,
                "interactions": interactions,
                "feedback": feedback,
                "policy_execution": policy_execution or {},
                "new_dynamic_edges": list(interactions.get("new_dynamic_edges") or []),
            },
            previous_state=self.agent_emergence_state,
        )
        self.actor_profiles = deepcopy(result.actor_profiles)
        self.agent_emergence_state = deepcopy(result.state)
        for item in result.events:
            append_jsonl(self.agent_emergence_log, item)
        for item in result.lineage:
            append_jsonl(self.agent_lineage_log, item)
        for item in result.candidate_ledger:
            append_jsonl(self.agent_candidate_log, item)

        changed_ids = [
            *result.created_agent_ids,
            *result.split_agent_ids,
            *result.activated_agent_ids,
        ]
        if changed_ids:
            self._rebuild_actor_indexes()
            self._rebuild_risk_indexes()
            dump_json(os.path.join(self.sim_dir, "profiles_full.json"), self.actor_profiles)
        self._persist_runtime_config()
        return {
            "contract_version": result.state.get("contract_version"),
            "candidate_count": len(result.state.get("candidates") or {}),
            "created_agent_ids": list(result.created_agent_ids),
            "split_agent_ids": list(result.split_agent_ids),
            "reactivated_agent_ids": list(result.activated_agent_ids),
            "created_or_split_count": int(result.state.get("created_or_split_count") or 0),
            "runtime_agent_total_limit": result.state.get("runtime_agent_total_limit"),
            "runtime_agent_per_round_limit": result.state.get("runtime_agent_per_round_limit"),
            "events": list(result.events),
            "lineage": list(result.lineage),
        }

    def _rebuild_actor_indexes(self) -> None:
        self.actor_lookup = {
            int(item.get("agent_id", index)): item
            for index, item in enumerate(self.actor_profiles)
            if str(item.get("agent_id", index)).lstrip("-").isdigit()
        }
        self.agents_by_region = defaultdict(list)
        self.agents_by_type = defaultdict(list)
        self.agents_by_subtype = defaultdict(list)
        self.agents_by_influence_region = defaultdict(list)
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

    def run(self) -> None:
        self._write_platform_event("twitter", {"event_type": "simulation_start", "timestamp": self._now()})
        self._write_platform_event("reddit", {"event_type": "simulation_start", "timestamp": self._now()})
        self.ipc.start()
        self._write_env_status("alive")
        if not self.latest_risk_runtime_state:
            self._refresh_risk_runtime(round_num=0, snapshot=None, refresh_reason="runtime_bootstrap", append_history=False)

        for round_num in range(1, self.total_rounds + 1):
            self.current_round = round_num
            self._drain_commands()
            agent_activation_events = self._activate_due_runtime_agents(round_num)
            self._advance_dynamic_edges(round_num)

            active_variables = self._active_variables(round_num)
            diffusion = self._environmental_diffusion_update(round_num, active_variables)
            interactions = self._agent_interaction_update(round_num, active_variables, diffusion)
            self._apply_relationship_coupling(round_num)
            self._apply_mechanism_propagation(round_num)
            policy_execution = self._execute_policy_plan(round_num)
            feedback = self._human_nature_feedback_update(round_num, active_variables, diffusion, interactions)
            if isinstance(feedback, dict):
                feedback["detected_feedback_loops"] = self._detect_feedback_loops()
            agent_emergence = self._detect_runtime_agent_emergence(
                round_num=round_num,
                active_variables=active_variables,
                interactions=interactions,
                feedback=feedback,
                policy_execution=policy_execution,
            )
            if agent_activation_events:
                agent_emergence["activation_events"] = agent_activation_events
            snapshot = self._build_snapshot(
                round_num,
                active_variables,
                diffusion,
                interactions,
                feedback,
                policy_execution,
            )
            snapshot["agent_emergence"] = agent_emergence
            self._detect_runtime_risk_emergence(
                round_num=round_num,
                active_variables=active_variables,
            )
            latest_risk_runtime = self._refresh_risk_runtime(
                round_num=round_num,
                snapshot=snapshot,
                refresh_reason="round_refresh",
                append_history=True,
            )
            snapshot["risk_runtime"] = latest_risk_runtime
            if self.is_mechanism_runtime:
                reasoning_record = self._build_round_reasoning_record(
                    round_num=round_num,
                    active_variables=active_variables,
                    diffusion=diffusion,
                    interactions=interactions,
                    feedback=feedback,
                    risk_runtime=latest_risk_runtime,
                    snapshot=snapshot,
                )
                snapshot["reasoning"] = reasoning_record
                append_jsonl(self.round_reasoning_log, reasoning_record)
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

    def _load_propagation_channels(self) -> List[Dict[str, Any]]:
        """Resolve the structured propagation channels for this run.

        Prefers the pre-built ``propagation_channels`` (emitted by the config
        generator) and otherwise rebuilds them from the still-present
        ``secondary_channels`` + ``impact_chain`` so older configs without the new
        field also get channel modulation. Returns ``[]`` when nothing is present,
        which makes the modulation pass a no-op."""
        candidates = (
            (self.transport_profile or {}).get("propagation_channels")
            or (self.diffusion_context or {}).get("propagation_channels")
            or (self.config.get("hazard_template_recommendation") or {}).get("propagation_channels")
            or []
        )
        channels = [dict(channel) for channel in candidates if isinstance(channel, dict)]
        if channels:
            return channels
        secondary = (self.transport_profile or {}).get("secondary_channels") or []
        impact_chain = (self.config.get("hazard_template_recommendation") or {}).get("impact_chain") or []
        if not secondary:
            return []
        try:
            from app.services.envfish_models import build_propagation_channels  # noqa: E402

            return build_propagation_channels(secondary_channels=secondary, impact_chain=impact_chain)
        except Exception:
            return []

    def _channel_modulation_for_transfer(self, transfer: Dict[str, Any]) -> Dict[str, float]:
        """Compute the per-receptor-dimension EXTRA delta a transfer should carry
        because of its propagation channel(s).

        Reads the transfer's resolved ``channel_type`` (set by _validate_transfer
        from the transport edge) and, failing a match, applies the run's channels
        as a scenario-wide carrier set. Returns an additive delta keyed by receptor
        dimension. Bounded by ``propagation_channel_gain`` and the transfer
        intensity; empty when channels are disabled/absent so legacy behavior is
        preserved."""
        if not self.propagation_channels_enabled or not self.propagation_channels:
            return {}
        base_delta = min(18.0, float(transfer.get("transfer_intensity") or 0.0) * 0.18)
        if base_delta <= 0:
            return {}
        gain = max(0.0, float(self.propagation_channel_gain))
        if gain <= 0:
            return {}

        channel_type = str(transfer.get("channel_type") or "").strip().lower()
        matched = self.propagation_channels_by_id.get(channel_type) if channel_type else None
        selected = [matched] if matched else list(self.propagation_channels)
        if not selected:
            return {}

        # Spread the modulation budget across the contributing channels so adding
        # more channels redistributes rather than runs away.
        share = 1.0 / float(len(selected))
        modulation: Dict[str, float] = defaultdict(float)
        for channel in selected:
            receptor_dim = str(channel.get("receptor_dim") or "exposure_score")
            channel_gain = max(0.0, float(channel.get("gain") or 1.0))
            extra = base_delta * gain * share * (channel_gain - 1.0)
            # ecosystem_integrity is a "higher = better" dim: a loading channel
            # erodes it (negative), all others (pressure/exposure) load up.
            if receptor_dim == "ecosystem_integrity":
                modulation[receptor_dim] += -abs(extra)
            else:
                modulation[receptor_dim] += extra
        return {key: round(value, 4) for key, value in modulation.items() if abs(value) > 1e-6}

    def _ensure_spread_event_causality(
        self,
        transfer: Dict[str, Any],
        *,
        round_num: int,
        ordinal: int,
    ) -> Dict[str, Any]:
        """Give every applied transfer an identity without inventing a parent.

        Deterministic fallback transfers already carry an explicit causal chain.
        LLM/legacy transfers that do not carry one become independent roots; a
        common round or region is not sufficient evidence to link them.
        """

        event_id = str(transfer.get("event_id") or "").strip()
        if not event_id:
            simulation_id = str((getattr(self, "config", {}) or {}).get("simulation_id") or "runtime")
            event_id = _stable_runtime_event_id(
                "spread_event",
                simulation_id,
                "applied_transfer",
                int(round_num),
                int(ordinal),
                transfer.get("source_region"),
                transfer.get("target_region"),
                transfer.get("transport_edge_id"),
                transfer.get("channel_type"),
                transfer.get("transfer_intensity"),
                transfer.get("delay_rounds"),
            )
        transfer["event_id"] = event_id
        transfer.update(
            _causal_metadata(
                event_id,
                {
                    "root_event_id": transfer.get("root_event_id"),
                    "parent_event_ids": transfer.get("parent_event_ids") or [],
                    "hop": transfer.get("hop"),
                },
            )
        )
        return transfer

    def _environmental_diffusion_update(
        self,
        round_num: int,
        active_variables: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        due_transfers = [item for item in self.pending_transfers if item["apply_round"] <= round_num]
        self.pending_transfers = [item for item in self.pending_transfers if item["apply_round"] > round_num]
        for ordinal, transfer in enumerate(due_transfers):
            self._ensure_spread_event_causality(
                transfer,
                round_num=round_num,
                ordinal=ordinal,
            )
        llm_result = self._llm_diffusion(round_num, active_variables, due_transfers)
        if not llm_result:
            llm_result = self._fallback_diffusion(round_num, active_variables, due_transfers)

        valid_transfers = []
        for transfer_index, transfer in enumerate(llm_result.get("transfers") or []):
            validated = self._validate_transfer(transfer, active_variables)
            if validated:
                self._ensure_spread_event_causality(
                    validated,
                    round_num=round_num,
                    ordinal=len(due_transfers) + transfer_index,
                )
                valid_transfers.append(validated)
                if validated["delay_rounds"] > 0:
                    scheduled = dict(validated)
                    scheduled["apply_round"] = round_num + int(validated["delay_rounds"])
                    self.pending_transfers.append(scheduled)

        immediate = [transfer for transfer in valid_transfers if transfer["delay_rounds"] <= 0]
        region_updates = defaultdict(lambda: defaultdict(float))
        modulated_transfers = 0
        total_channel_delta = 0.0
        for transfer in due_transfers + immediate:
            target = self.region_lookup.get(transfer["target_region"])
            if not target:
                continue
            delta = min(18.0, transfer["transfer_intensity"] * 0.18)
            region_updates[target["region_id"]]["exposure_score"] += delta
            region_updates[target["region_id"]]["spread_pressure"] += max(3.0, delta * 0.65)
            region_updates[target["region_id"]]["ecosystem_integrity"] -= max(2.0, delta * 0.22)

            # M6: the scenario's propagation channels MODULATE this transfer — a
            # channel adds a small, bounded, channel-specific load to its receptor
            # dimension on top of the base transfer. No-op when channels absent.
            channel_modulation = self._channel_modulation_for_transfer(transfer)
            if channel_modulation:
                modulated_transfers += 1
                for receptor_dim, extra in channel_modulation.items():
                    region_updates[target["region_id"]][receptor_dim] += extra
                    total_channel_delta += abs(extra)
                transfer["channel_modulation"] = channel_modulation

            append_jsonl(
                self.spread_log,
                {
                    "round": round_num,
                    "timestamp": self._now(),
                    "event_id": transfer["event_id"],
                    "root_event_id": transfer["root_event_id"],
                    "parent_event_ids": list(transfer.get("parent_event_ids") or []),
                    "hop": int(transfer.get("hop") or 0),
                    "source_region": transfer["source_region"],
                    "target_region": transfer["target_region"],
                    "transfer_intensity": transfer["transfer_intensity"],
                    "delay_rounds": transfer["delay_rounds"],
                    "persistence": transfer["persistence"],
                    "confidence": transfer["confidence"],
                    "channel_type": transfer.get("channel_type"),
                    "transport_edge_id": transfer.get("transport_edge_id"),
                    "path_edge_ids": (
                        [str(transfer.get("transport_edge_id"))]
                        if transfer.get("transport_edge_id")
                        else []
                    ),
                    "related_edge_ids": [],
                    "source_variable_id": transfer.get("source_variable_id"),
                    "causal_source_type": transfer.get("causal_source_type"),
                    "channel_modulation": transfer.get("channel_modulation") or {},
                    "rationale": transfer["rationale"],
                },
            )
            self._write_action(
                platform="twitter",
                round_num=round_num,
                agent_id=500000 + self._region_index(transfer["source_region"]),
                agent_name=self.region_lookup.get(transfer["source_region"], {}).get("name", "环境扩散"),
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
        self.latest_propagation_modulation = {
            "modulated_transfers": modulated_transfers,
            "total_delta": round(total_channel_delta, 3),
            "channel_count": len(self.propagation_channels),
        }
        return {
            "transfers": valid_transfers,
            "applied_transfers": due_transfers + immediate,
            "region_ranking": ranking,
            "likely_next_impacted_regions": [item["name"] for item in ranking[:3]],
            "propagation_modulation": self.latest_propagation_modulation,
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
                "action_records": [],
                "state_mutation_records": [],
                "relationship_events": [],
                "relationship_states": deepcopy(getattr(self, "relationship_states", [])),
            }

        eligible_profiles = []
        for actor in self.actor_profiles:
            lifecycle = actor.get("runtime_lifecycle") or {}
            lifecycle_status = str(lifecycle.get("lifecycle_status") or "active")
            activation_round = int(lifecycle.get("activation_round") or 0)
            if lifecycle_status in {"dormant", "retired", "pending_activation"}:
                if lifecycle_status != "pending_activation" or activation_round > round_num:
                    continue
            eligible_profiles.append(actor)
        if not eligible_profiles:
            return {
                "active_agent_ids": [],
                "agent_interactions": [],
                "agent_environment_effects": [],
                "turning_points": [],
                "action_records": [],
                "state_mutation_records": [],
                "relationship_events": [],
                "relationship_states": deepcopy(getattr(self, "relationship_states", [])),
            }

        max_active = int(
            self.runtime_limits.get("max_active_agents_per_round")
            or max(12, len(eligible_profiles) // 4)
        )
        if getattr(self, "agent_plan_source", "") == "agent_v2":
            max_active = min(max_active, max(1, int(self.max_deep_agents_per_round)))
        ordered = sorted(
            eligible_profiles,
            key=self._agent_activation_score,
            reverse=True,
        )
        active_agents = ordered[: min(max_active, len(ordered))]

        interactions: List[Dict[str, Any]] = []
        environment_effects: List[Dict[str, Any]] = []
        turning_points: List[str] = []
        new_dynamic_edges: List[Dict[str, Any]] = []
        activated_dynamic_edge_ids: List[str] = []
        relationship_events: List[Dict[str, Any]] = []
        action_records: List[Dict[str, Any]] = []
        state_mutation_records: List[Dict[str, Any]] = []
        llm_search_remaining = self.llm_relation_search_budget
        self._remaining_dynamic_validations = (
            self.dynamic_relationship_validation_limit
            if getattr(self, "agent_plan_source", "") == "agent_v2"
            else 10**9
        )

        for actor in active_agents:
            home_region = self.region_lookup.get(actor.get("primary_region")) or self.region_graph[0]
            home_subregion = self.subregion_lookup.get(actor.get("home_subregion_id") or "")
            actor_id = int(actor.get("agent_id", -1))
            scenario_version_ref = getattr(self, "scenario_version_ref", {})
            action_type, action_decision = self._choose_validated_agent_action(actor, home_region)
            action_bundle = self._action_effects(actor, action_type, home_region)
            action_ref = {
                "artifact_id": f"agent_action_{round_num}_{actor_id}",
                "contract_version": AGENT_ACTION_CONTRACT_VERSION,
            }
            resource_settlement = consume_action_resources(
                actor,
                action_decision["selected_validation"],
            )
            action_decision["resource_settlement"] = resource_settlement
            action_mutations = resource_mutation_records(
                settlement=resource_settlement,
                round_number=round_num,
                source_ref=action_ref,
                agent_id=actor_id,
                evidence_refs=actor.get("evidence_refs") or [],
                scenario_version_ref=scenario_version_ref,
            )
            action_decision.update(
                {
                    "round": round_num,
                    "timestamp": self._now(),
                    "agent_id": actor.get("agent_id"),
                    "agent_name": actor.get("name") or actor.get("username"),
                    "region_id": home_region.get("region_id"),
                }
            )
            emergent_edges, llm_search_remaining = self._maybe_create_dynamic_edges(actor, round_num, llm_search_remaining)
            if emergent_edges:
                new_dynamic_edges.extend(emergent_edges)
                for edge in emergent_edges[:1]:
                    target_name = self.actor_lookup.get(int(edge.get("target_agent_id", -1)), {}).get("name") or edge.get("target_agent_id")
                    turning_points.append(
                        f"{actor.get('name') or actor.get('username')} 与 {target_name} 建立了新的跨区 {edge.get('edge_type')}。"
                    )
            relation_edges = self._candidate_relationship_edges(actor)

            actor["state_vector"], actor_mutations = apply_state_delta(
                current_vector=actor.get("state_vector") or {},
                delta=action_bundle["actor_delta"],
                round_number=round_num,
                source_ref=action_ref,
                target_type="agent",
                target_id=actor_id,
                evidence_refs=actor.get("evidence_refs") or [],
                scenario_version_ref=scenario_version_ref,
            )
            action_mutations.extend(actor_mutations)
            if action_bundle["region_delta"]:
                home_region["state_vector"], region_mutations = apply_state_delta(
                    current_vector=home_region["state_vector"],
                    delta=action_bundle["region_delta"],
                    round_number=round_num,
                    source_ref=action_ref,
                    target_type="region",
                    target_id=home_region.get("region_id"),
                    evidence_refs=actor.get("evidence_refs") or [],
                    scenario_version_ref=scenario_version_ref,
                )
                action_mutations.extend(region_mutations)
                if home_subregion is not None:
                    home_subregion["state_vector"], subregion_mutations = apply_state_delta(
                        current_vector=home_subregion.get("state_vector") or {},
                        delta=action_bundle["region_delta"],
                        round_number=round_num,
                        source_ref=action_ref,
                        target_type="region",
                        target_id=home_subregion.get("region_id"),
                        evidence_refs=actor.get("evidence_refs") or [],
                        scenario_version_ref=scenario_version_ref,
                    )
                    action_mutations.extend(subregion_mutations)
                environment_effects.append(
                    {
                        "agent_id": actor.get("agent_id"),
                        "agent_name": actor.get("name") or actor.get("username"),
                        "action_type": action_type,
                        "action_label_zh": action_label_zh(action_type),
                        "region_id": home_region.get("region_id"),
                        "region_name": home_region.get("name"),
                        "home_subregion_id": home_subregion.get("region_id") if home_subregion else "",
                        "delta": action_bundle["region_delta"],
                    }
                )

            target_actor, selected_edge = self._select_interaction_target(relation_edges, action_type)
            if target_actor and action_bundle["target_delta"]:
                target_actor["state_vector"], target_mutations = apply_state_delta(
                    current_vector=target_actor.get("state_vector") or {},
                    delta=action_bundle["target_delta"],
                    round_number=round_num,
                    source_ref=action_ref,
                    target_type="agent",
                    target_id=target_actor.get("agent_id"),
                    evidence_refs=[
                        *(actor.get("evidence_refs") or []),
                        *((selected_edge or {}).get("evidence") or []),
                    ],
                    scenario_version_ref=scenario_version_ref,
                )
                action_mutations.extend(target_mutations)
                selected_dynamic_edge_id = str(selected_edge.get("edge_id") or "") if selected_edge else ""
                interaction_event_id = _stable_runtime_event_id(
                    "agent_interaction_event",
                    str((getattr(self, "config", {}) or {}).get("simulation_id") or "runtime"),
                    int(round_num),
                    actor.get("agent_id"),
                    target_actor.get("agent_id"),
                    action_type,
                    selected_dynamic_edge_id,
                )
                interaction_causality = _causal_metadata(interaction_event_id)
                if selected_dynamic_edge_id in self.dynamic_edge_lookup:
                    self._activate_dynamic_edge(
                        selected_dynamic_edge_id,
                        round_num,
                        causal_context=_child_causal_context(
                            {"event_id": interaction_event_id, **interaction_causality}
                        ),
                    )
                    activated_dynamic_edge_ids.append(selected_dynamic_edge_id)
                relation_type = None
                if selected_edge:
                    relation_type = selected_edge.get("edge_type") or selected_edge.get("relation_type") or selected_edge.get("name")
                relationship_event = None
                relationship_state = None
                if selected_edge and getattr(self, "agent_plan_source", "") == "agent_v2":
                    confidence = clamp_probability(selected_edge.get("confidence", 0.6))
                    relationship_event = build_interaction_event(
                        round_number=round_num,
                        edge=selected_edge,
                        action_key=action_type,
                        action_label_zh=action_label_zh(action_type),
                        source_action_ref=action_ref,
                        state_mutation_refs=mutation_refs(action_mutations),
                        success_status="success" if confidence >= 0.5 else "partial",
                        scenario_version_ref=scenario_version_ref,
                        causal_context=_child_causal_context(
                            {"event_id": interaction_event_id, **interaction_causality}
                        ),
                    )
                    relationship_state = self._record_relationship_event(
                        selected_edge,
                        relationship_event,
                    )
                    relationship_events.append(relationship_event)
                interaction_record = {
                    "round": round_num,
                    "timestamp": self._now(),
                    "event_id": interaction_event_id,
                    **interaction_causality,
                    "source_agent_id": actor.get("agent_id"),
                    "source_agent_name": actor.get("name") or actor.get("username"),
                    "target_agent_id": target_actor.get("agent_id"),
                    "target_agent_name": target_actor.get("name") or target_actor.get("username"),
                    "action_type": action_type,
                    "action_label_zh": action_label_zh(action_type),
                    "channel": action_bundle["interaction_channel"],
                    "delta": action_bundle["target_delta"],
                    "rationale": action_bundle["rationale"],
                    "relation_type": relation_type,
                    "edge_layer": selected_edge.get("layer", "structural") if selected_edge else "structural",
                    "edge_id": selected_edge.get("edge_id") if selected_edge else None,
                    "path_edge_ids": (
                        [str(selected_edge.get("edge_id"))]
                        if selected_edge and selected_edge.get("edge_id")
                        else []
                    ),
                    "related_edge_ids": [
                        str(edge_id)
                        for edge_id in ((selected_edge or {}).get("mechanism_edge_ids") or [])
                        if str(edge_id or "").strip()
                    ],
                    "source_region_id": home_region.get("region_id"),
                    "target_region_id": target_actor.get("primary_region") or target_actor.get("home_region_id"),
                    "relationship_event_id": (
                        relationship_event.get("relationship_event_id")
                        if relationship_event
                        else ""
                    ),
                    "relationship_state_ref": (
                        {
                            "artifact_id": relationship_state.get("relationship_state_id"),
                            "contract_version": relationship_state.get("contract_version"),
                        }
                        if relationship_state
                        else {}
                    ),
                }
                interactions.append(interaction_record)
                append_jsonl(self.agent_interaction_log, interaction_record)

            action_decision["state_mutation_refs"] = mutation_refs(action_mutations)
            action_records.append(deepcopy(action_decision))
            state_mutation_records.extend(action_mutations)
            if getattr(self, "agent_action_decision_log", ""):
                append_jsonl(self.agent_action_decision_log, action_decision)
            if getattr(self, "state_mutation_log", ""):
                for mutation in action_mutations:
                    append_jsonl(self.state_mutation_log, mutation)

            self._write_action(
                platform="reddit" if actor.get("agent_type") == "human" else "twitter",
                round_num=round_num,
                agent_id=int(actor.get("agent_id", -1)),
                agent_name=actor.get("name") or actor.get("username"),
                action_type=action_type,
                action_args={
                    "action_label_zh": action_label_zh(action_type),
                    "action_contract_version": AGENT_ACTION_CONTRACT_VERSION,
                    "action_validation": action_decision["selected_validation"],
                    "resource_settlement": action_decision["resource_settlement"],
                    "state_mutation_refs": action_decision["state_mutation_refs"],
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
        active_dynamic_edges = [edge for edge in self.dynamic_edge_lookup.values() if edge.get("status") not in ("expired", "dormant")]

        return {
            "active_agent_ids": [int(actor.get("agent_id", -1)) for actor in active_agents],
            "agent_interactions": interactions,
            "agent_environment_effects": environment_effects,
            "new_dynamic_edges": new_dynamic_edges,
            "activated_dynamic_edge_ids": activated_dynamic_edge_ids,
            "relationship_events": relationship_events,
            "relationship_states": deepcopy(getattr(self, "relationship_states", [])),
            "action_records": action_records,
            "state_mutation_records": state_mutation_records,
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
                    "agent_name": actor.get("name") or actor.get("username"),
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

    def _rebuild_relationship_state_index(self) -> None:
        self.relationship_state_lookup = {
            str(item.get("relationship_contract_id") or ""): item
            for item in getattr(self, "relationship_states", [])
            if str(item.get("relationship_contract_id") or "")
        }

    def _ensure_relationship_state(self, edge: Dict[str, Any]) -> Dict[str, Any]:
        self.relationship_states, state = upsert_relationship_state(
            getattr(self, "relationship_states", []),
            edge,
        )
        self._rebuild_relationship_state_index()
        return self.relationship_state_lookup[state["relationship_contract_id"]]

    def _record_relationship_event(self, edge: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        state = self._ensure_relationship_state(edge)
        next_state = apply_relationship_event(state, event)
        contract_id = str(next_state["relationship_contract_id"])
        self.relationship_states = [
            next_state if str(item.get("relationship_contract_id") or "") == contract_id else item
            for item in self.relationship_states
        ]
        self._rebuild_relationship_state_index()
        if getattr(self, "relationship_event_log", ""):
            append_jsonl(self.relationship_event_log, event)
        if getattr(self, "relationship_state_path", ""):
            dump_json(self.relationship_state_path, self.relationship_states)
        return next_state

    def _rebuild_dynamic_edge_index(self) -> None:
        self.dynamic_edges_by_source = defaultdict(list)
        for edge in self.dynamic_edge_lookup.values():
            if edge.get("status") in ("expired", "dormant"):
                continue
            try:
                source_agent_id = int(edge.get("source_agent_id"))
            except Exception:
                continue
            self.dynamic_edges_by_source[source_agent_id].append(edge)

    def _serialize_dynamic_edge(self, edge: Dict[str, Any]) -> Dict[str, Any]:
        edge_id = str(edge.get("edge_id") or "").strip()
        mechanism_edge_ids = [
            str(item)
            for item in (edge.get("mechanism_edge_ids") or [])
            if str(item or "").strip()
        ]
        return {
            "edge_id": edge.get("edge_id"),
            "path_edge_ids": [edge_id] if edge_id else [],
            "related_edge_ids": mechanism_edge_ids,
            "mechanism_edge_ids": mechanism_edge_ids,
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

    def _record_dynamic_edge_event(
        self,
        round_num: int,
        event_type: str,
        edge: Dict[str, Any],
        *,
        causal_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        simulation_id = str((getattr(self, "config", {}) or {}).get("simulation_id") or "runtime")
        event_id = _stable_runtime_event_id(
            "dynamic_edge_event",
            simulation_id,
            edge.get("edge_id"),
            int(round_num),
            event_type,
            edge.get("reconfirm_count"),
            edge.get("status"),
            list((causal_context or {}).get("parent_event_ids") or []),
        )
        event_record = {
            "round": round_num,
            "timestamp": self._now(),
            "event_id": event_id,
            **_causal_metadata(event_id, causal_context),
            "event_type": event_type,
            **self._serialize_dynamic_edge(edge),
        }
        append_jsonl(self.dynamic_edge_log, event_record)
        if (
            getattr(self, "agent_plan_source", "") == "agent_v2"
            and event_type
            in {
                "created",
                "reawakened",
                "updated",
                "activated",
                "promoted",
                "expired",
                "dormant",
            }
        ):
            relationship_event = build_lifecycle_event(
                round_number=round_num,
                edge=edge,
                lifecycle_event_type=event_type,
                scenario_version_ref=getattr(self, "scenario_version_ref", {}),
                causal_context=_child_causal_context(event_record),
            )
            self._record_relationship_event(edge, relationship_event)
        return event_record

    def _advance_dynamic_edges(self, round_num: int) -> None:
        changed = False
        for edge in self.dynamic_edge_lookup.values():
            if edge.get("status") in ("expired", "dormant"):
                continue
            previous_status = edge.get("status") or "active"
            expires_after_round = int(edge.get("expires_after_round") or 0)
            if expires_after_round and round_num > expires_after_round:
                # Relationships are not hard-deleted: they go dormant and keep
                # their history, so they carry scars and can be reawakened.
                self._mark_edge_dormant(edge, round_num, "ttl_elapsed")
                changed = True
                continue

            if edge.get("layer") == "structural" and edge.get("origin") == "runtime_promoted":
                edge["status"] = "stable"
                continue

            last_activated_round = int(edge.get("last_activated_round") or edge.get("created_round") or 0)
            if last_activated_round < round_num - 1:
                decay = clamp_probability(edge.get("decay_per_round") or self.default_dynamic_decay)
                edge["strength"] = clamp_probability(float(edge.get("strength") or 0) * max(0.0, 1.0 - decay))
                if float(edge.get("strength") or 0) >= 0.12:
                    edge["status"] = "cooling"
                else:
                    self._mark_edge_dormant(edge, round_num, "decayed")
            else:
                edge["status"] = "active"

            if edge.get("status") not in (previous_status, "dormant"):
                event_type = "cooling" if edge.get("status") == "cooling" else edge.get("status")
                self._record_dynamic_edge_event(round_num, str(event_type), edge)
                changed = True

        if changed or self.dynamic_edge_lookup:
            self._rebuild_dynamic_edge_index()

    def _mark_edge_dormant(self, edge: Dict[str, Any], round_num: int, reason: str) -> None:
        edge["status"] = "dormant"
        edge["dormant_since_round"] = round_num
        edge.setdefault("history", []).append(
            {
                "round": round_num,
                "event": "dormant",
                "reason": reason,
                "strength": clamp_probability(edge.get("strength") or 0),
            }
        )
        self._record_dynamic_edge_event(round_num, "dormant", edge)

    def _dynamic_edges_for_source(self, source_agent_id: int) -> List[Dict[str, Any]]:
        return list(self.dynamic_edges_by_source.get(int(source_agent_id), []))

    # Interaction channels and how strongly they transmit stress along an edge.
    _COUPLING_CHANNEL_GAIN = {
        "information": 0.5,
        "social": 0.6,
        "community": 0.6,
        "ecological": 1.0,
        "ecology_corridor_signal": 1.0,
        "water_flow": 1.0,
        "transport": 0.8,
        "economic": 0.7,
        "governance": 0.6,
        "mechanism": 0.8,
    }
    # Higher = worse; an upstream-stressed source pushes these UP at the target.
    _COUPLING_PRESSURE_KEYS = ("exposure_score", "spread_pressure", "panic_level", "economic_stress")
    # Higher = better; a degraded source erodes these at the target.
    _COUPLING_PROTECT_KEYS = (
        "ecosystem_integrity",
        "public_trust",
        "service_capacity",
        "response_capacity",
        "livelihood_stability",
    )

    def _apply_relationship_coupling(self, round_num: int) -> Dict[str, Any]:
        """Active dynamic edges transmit stress between their endpoint regions:
        a strong relationship pulls the target region toward the source region's
        stressed state. This is what makes the relationship layer DRIVE state
        instead of being a read-only decoration. The transfer is bounded by the
        state gap and the edge strength, so it cannot run away."""
        if not self.relationship_coupling_enabled:
            return {"coupled_edges": 0, "total_transfer": 0.0}
        coupled = 0
        total_transfer = 0.0
        base_gain = max(0.0, float(self.relationship_coupling_gain))
        for edge in self.dynamic_edge_lookup.values():
            if edge.get("status") != "active":
                continue
            strength = float(edge.get("strength") or 0.0)
            if strength < 0.25:
                continue
            source_region = self.region_lookup.get(edge.get("source_region_id"))
            target_region = self.region_lookup.get(edge.get("target_region_id"))
            if not source_region or not target_region or source_region is target_region:
                continue
            channel = str(edge.get("interaction_channel") or edge.get("edge_type") or "").lower()
            gain = strength * self._COUPLING_CHANNEL_GAIN.get(channel, 0.6) * base_gain
            if gain <= 0:
                continue
            source_state = source_region.get("state_vector") or {}
            target_state = target_region.get("state_vector") or {}
            delta: Dict[str, float] = {}
            for key in self._COUPLING_PRESSURE_KEYS:
                gap = float(source_state.get(key, 50.0)) - float(target_state.get(key, 50.0))
                if gap > 0:
                    delta[key] = round(gap * gain, 3)
            for key in self._COUPLING_PROTECT_KEYS:
                gap = float(target_state.get(key, 50.0)) - float(source_state.get(key, 50.0))
                if gap > 0:
                    delta[key] = round(-gap * gain * 0.5, 3)
            if not delta:
                continue
            target_region["state_vector"] = merge_state_vectors(target_region.get("state_vector") or {}, delta)
            edge["last_coupled_round"] = round_num
            total_transfer += sum(abs(value) for value in delta.values())
            coupled += 1
            if coupled <= 40:
                self._record_dynamic_edge_event(round_num, "coupled", edge)
        summary = {"coupled_edges": coupled, "total_transfer": round(total_transfer, 3)}
        self.latest_relationship_coupling = summary
        return summary

    # Mechanism-edge nudge targets. A positive (amplifying) mechanism edge raises
    # the target region's PRESSURE dims; a negative (dampening) edge lowers them.
    # Bounded by a small gain so the mechanism graph informs — not dominates —
    # the engine. These are the same canonical state keys used elsewhere.
    _MECHANISM_PRESSURE_KEYS = ("spread_pressure", "exposure_score", "panic_level", "economic_stress")
    # Mechanism node types that anchor to a place / region in the graph.
    _MECHANISM_PLACE_NODE_TYPES = {"place", "region", "receptor"}

    def _mechanism_node_region_index(self) -> Dict[str, str]:
        """Map mechanism-graph node ids -> region_id, when a node clearly anchors
        to a known region. We resolve by (a) the conventional ``place_<region>``
        id prefix, (b) an explicit region_id field on the node, or (c) a node name
        that matches a region name. Built once and cached; empty mapping => the
        propagation pass is a graceful no-op (we never invent a region)."""
        if self._mechanism_region_index is not None:
            return self._mechanism_region_index

        index: Dict[str, str] = {}
        nodes = list((self.mechanism_graph or {}).get("nodes") or [])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                continue
            node_type = str(node.get("node_type") or "").strip().lower()
            # (b) explicit region binding wins.
            explicit = str(node.get("region_id") or node.get("home_region_id") or "").strip()
            if explicit and explicit in self.region_lookup:
                index[node_id] = explicit
                continue
            # (a) conventional place_<region_slug> id: compare slugged region ids.
            if node_id.startswith("place_"):
                slug = node_id[len("place_"):]
                for region_id in self.region_lookup:
                    if self._mechanism_slug(region_id) == slug:
                        index[node_id] = region_id
                        break
                if node_id in index:
                    continue
            # (c) name match against region names (only for place-like nodes, to
            # avoid binding a process node to a region by coincidental wording).
            if node_type in self._MECHANISM_PLACE_NODE_TYPES:
                name_key = str(node.get("name") or "").strip().lower()
                region_id = self.region_name_lookup.get(name_key)
                if region_id:
                    index[node_id] = region_id

        self._mechanism_region_index = index
        return index

    @staticmethod
    def _mechanism_slug(value: Any) -> str:
        text = str(value or "").strip().lower()
        out = []
        for ch in text:
            if ch.isalnum() or "一" <= ch <= "鿿":
                out.append(ch)
            else:
                out.append("_")
        slug = "".join(out)
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug.strip("_")

    def _apply_mechanism_propagation(self, round_num: int) -> Dict[str, Any]:
        """LIGHT, GUARDED mechanism-driven state nudge.

        For each mechanism edge with a signed direction whose endpoints both map
        to a known region, nudge the target region's pressure dimensions along the
        edge sign (positive => raise pressure, negative => lower it). The nudge is
        scaled by the edge confidence and a small gain, and is bounded by
        merge_state_vectors' clamp — it can inform but never dominate the engine.

        Conservative by construction: if the mechanism runtime is off, the flag is
        off, or no edge endpoint resolves to a region, this is a graceful no-op and
        the run loop is unaffected (legacy/non-mechanism runs see nothing)."""
        summary = {"nudged_edges": 0, "total_nudge": 0.0}
        if not self.is_mechanism_runtime or not self.mechanism_propagation_enabled:
            self.latest_mechanism_propagation = summary
            return summary

        mechanism_edges = list((self.mechanism_graph or {}).get("edges") or [])
        if not mechanism_edges:
            self.latest_mechanism_propagation = summary
            return summary

        region_index = self._mechanism_node_region_index()
        if not region_index:
            self.latest_mechanism_propagation = summary
            return summary

        base_gain = max(0.0, float(self.mechanism_propagation_gain))
        if base_gain <= 0:
            self.latest_mechanism_propagation = summary
            return summary

        nudged = 0
        total_nudge = 0.0
        for edge in mechanism_edges:
            if not isinstance(edge, dict):
                continue
            direction = str(edge.get("direction") or "").strip().lower()
            if direction == "positive":
                sign = 1.0
            elif direction == "negative":
                sign = -1.0
            else:
                # bidirectional/conditional/unknown carry no defensible sign here.
                continue
            target_region_id = region_index.get(str(edge.get("target") or "").strip())
            if not target_region_id:
                continue
            target_region = self.region_lookup.get(target_region_id)
            if not target_region:
                continue
            confidence = clamp_probability(edge.get("confidence", 0.5))
            magnitude = sign * confidence * base_gain * 100.0
            if magnitude == 0:
                continue
            delta = {key: round(magnitude, 3) for key in self._MECHANISM_PRESSURE_KEYS}
            target_region["state_vector"] = merge_state_vectors(
                target_region.get("state_vector") or {}, delta
            )
            nudged += 1
            total_nudge += abs(magnitude) * len(self._MECHANISM_PRESSURE_KEYS)

        summary = {"nudged_edges": nudged, "total_nudge": round(total_nudge, 3)}
        self.latest_mechanism_propagation = summary
        return summary

    # Channels that tend to DAMPEN (negative feedback) rather than amplify.
    _BALANCING_CHANNELS = {"governance", "response", "service", "mechanism"}

    def _detect_feedback_loops(self, max_length: int = 5, max_loops: int = 12) -> List[Dict[str, Any]]:
        """Detect directed cycles among ACTIVE relationships at the region level —
        the reinforcing/balancing feedback loops that are the heart of systems
        thinking but were never computed (the old feedback tab rendered a fixed
        decorative chain template). Polarity is a transparent channel heuristic,
        explicitly flagged as such."""
        adjacency: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for edge in self.dynamic_edge_lookup.values():
            if edge.get("status") not in ("active", "stable"):
                continue
            src = edge.get("source_region_id")
            dst = edge.get("target_region_id")
            if not src or not dst or src == dst:
                continue
            adjacency[src].append(
                {"to": dst, "channel": str(edge.get("interaction_channel") or edge.get("edge_type") or "")}
            )

        loops: List[Dict[str, Any]] = []
        seen_signatures: set = set()

        def dfs(start: str, current: str, path: List[str], channels: List[str]) -> None:
            if len(loops) >= max_loops:
                return
            for nxt in adjacency.get(current, []):
                target = nxt["to"]
                if target == start and len(path) >= 2:
                    signature = self._loop_signature(path)
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        loops.append(
                            self._build_loop_record(path, channels + [nxt["channel"]], len(loops) + 1)
                        )
                    continue
                if target in path or len(path) >= max_length:
                    continue
                dfs(start, target, path + [target], channels + [nxt["channel"]])

        for node in list(adjacency.keys()):
            if len(loops) >= max_loops:
                break
            dfs(node, node, [node], [])
        return loops

    def _loop_signature(self, cycle: List[str]) -> str:
        # rotation-invariant signature so the same cycle is not counted N times
        rotations = ["||".join(cycle[i:] + cycle[:i]) for i in range(len(cycle))]
        return min(rotations) if rotations else ""

    def _build_loop_record(self, regions: List[str], channels: List[str], index: int) -> Dict[str, Any]:
        names = [self.region_lookup.get(region, {}).get("name", region) for region in regions]
        balancing = any(str(channel).lower() in self._BALANCING_CHANNELS for channel in channels)
        return {
            "loop_id": f"loop_{index}",
            "regions": list(regions),
            "region_names": names,
            "length": len(regions),
            "channels": list(channels),
            "loop_type": "balancing" if balancing else "reinforcing",
            "classification_basis": "heuristic_channel",
        }

    def _candidate_relationship_edges(self, actor: Dict[str, Any]) -> List[Dict[str, Any]]:
        actor_id = int(actor.get("agent_id", -1))
        if actor_id < 0:
            return []

        relation_edges = list(self.relationships_by_source.get(actor_id, []))
        relation_edges.extend(self._dynamic_edges_for_source(actor_id))

        seen_targets = {
            int(edge.get("target_agent_id"))
            for edge in relation_edges
            if str(edge.get("target_agent_id") or "").isdigit()
        }

        if getattr(self, "agent_plan_source", "") != "agent_v2":
            for link_field in ("counterpart_agent_ids", "social_links", "ecology_links"):
                for raw_target_id in actor.get(link_field) or []:
                    if not str(raw_target_id or "").isdigit():
                        continue
                    target_id = int(raw_target_id)
                    if target_id == actor_id or target_id in seen_targets:
                        continue
                    target_actor = self.actor_lookup.get(target_id)
                    if not target_actor:
                        continue
                    relation_edges.append(
                        self._make_fallback_relationship_edge(
                            source_actor=actor,
                            target_actor=target_actor,
                            rationale=f"{actor.get('name') or actor.get('username')} 与 {target_actor.get('name') or target_actor.get('username')} 共享结构化 counterpart 关联。",
                            route_sources=[link_field],
                        )
                    )
                    seen_targets.add(target_id)

            for inbound_edge in self.relationships_by_target.get(actor_id, []):
                if not str(inbound_edge.get("source_agent_id") or "").isdigit():
                    continue
                target_id = int(inbound_edge.get("source_agent_id"))
                if target_id == actor_id or target_id in seen_targets:
                    continue
                target_actor = self.actor_lookup.get(target_id)
                if not target_actor:
                    continue
                relation_edges.append(
                    self._make_fallback_relationship_edge(
                        source_actor=actor,
                        target_actor=target_actor,
                        rationale=inbound_edge.get("rationale")
                        or f"{actor.get('name') or actor.get('username')} 对 {target_actor.get('name') or target_actor.get('username')} 形成反馈影响。",
                        route_sources=["reverse_structural_link"],
                    )
                )
                seen_targets.add(target_id)

        # M8: real runs ship an empty agent_relationship_graph and empty link
        # fields, so the interaction ledger was always empty — agents never had a
        # counterpart to act on. When (and only when) an actor has no candidate so
        # far, fall back to CO-LOCATION: agents that share a region — or whose
        # regions are joined by a transport edge — are plausible interaction
        # partners. This is a routing heuristic (epistemic_status=speculative), it
        # is bounded by `_colocation_candidate_limit`, and it is additive so any
        # run that already carries structural edges is untouched.
        if not relation_edges and getattr(self, "agent_plan_source", "") != "agent_v2":
            relation_edges.extend(
                self._colocation_candidate_edges(actor, seen_targets)
            )

        return relation_edges

    def _colocation_candidate_edges(
        self,
        actor: Dict[str, Any],
        seen_targets: set,
    ) -> List[Dict[str, Any]]:
        """Bounded co-location interaction candidates for an actor with no
        structural / dynamic partner. Prefers same-region peers, then peers one
        transport hop away, capped so a dense region cannot explode the ledger."""
        actor_id = int(actor.get("agent_id", -1))
        if actor_id < 0:
            return []
        home_region_id = str(actor.get("primary_region") or actor.get("home_region_id") or "").strip()
        if not home_region_id:
            return []
        limit = int(getattr(self, "_colocation_candidate_limit", 3) or 3)

        candidate_edges: List[Dict[str, Any]] = []
        local_seen = set(seen_targets)
        local_seen.add(actor_id)

        def _consume(peer: Dict[str, Any], route_source: str) -> bool:
            peer_id = int(peer.get("agent_id", -1))
            if peer_id < 0 or peer_id in local_seen:
                return False
            edge = self._make_fallback_relationship_edge(
                source_actor=actor,
                target_actor=peer,
                rationale=(
                    f"{actor.get('name') or actor.get('username')} 与 "
                    f"{peer.get('name') or peer.get('username')} 同处 {home_region_id}，构成就近互动候选。"
                ),
                route_sources=[route_source],
            )
            edge["layer"] = "colocation"
            edge["epistemic_status"] = "speculative"
            edge["strength"] = 0.38
            edge["confidence"] = 0.35
            candidate_edges.append(edge)
            local_seen.add(peer_id)
            return True

        # (1) same region
        for peer in self.agents_by_region.get(home_region_id, []) or []:
            if len(candidate_edges) >= limit:
                return candidate_edges
            _consume(peer, "shared_region")

        # (2) one transport hop away (regions joined by a transport edge)
        if len(candidate_edges) < limit:
            for transport_edge in self._transport_edges_for_source(home_region_id):
                if len(candidate_edges) >= limit:
                    break
                neighbor_region = str(transport_edge.get("target_region_id") or "").strip()
                if not neighbor_region or neighbor_region == home_region_id:
                    continue
                for peer in self.agents_by_region.get(neighbor_region, []) or []:
                    if len(candidate_edges) >= limit:
                        break
                    _consume(peer, "transport_neighbor")

        return candidate_edges

    def _make_fallback_relationship_edge(
        self,
        source_actor: Dict[str, Any],
        target_actor: Dict[str, Any],
        rationale: str,
        route_sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        source_agent_id = int(source_actor.get("agent_id", -1))
        target_agent_id = int(target_actor.get("agent_id", -1))
        edge_type, interaction_channel = self._infer_dynamic_edge_type(
            source_actor,
            target_actor,
            route_sources or ["counterpart_link"],
        )
        return {
            "edge_id": f"fallback::{source_agent_id}::{target_agent_id}::{edge_type}",
            "source_agent_id": source_agent_id,
            "target_agent_id": target_agent_id,
            "relation_type": edge_type,
            "edge_type": edge_type,
            "interaction_channel": interaction_channel,
            "rationale": rationale,
            "source_region_id": source_actor.get("primary_region") or source_actor.get("home_region_id"),
            "target_region_id": target_actor.get("primary_region") or target_actor.get("home_region_id"),
            "strength": 0.44,
            "confidence": 0.42,
            "layer": "fallback",
        }

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
                    "target_agent_name": target_actor.get("name") or target_actor.get("username"),
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

        if self.risk_contract_version < 2:
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
        source_agent_payload = {
            "agent_id": actor.get("agent_id"),
            "name": actor.get("name") or actor.get("username"),
            "agent_type": actor.get("agent_type"),
            "agent_subtype": actor.get("agent_subtype"),
            "primary_region": source_region_id,
            "state_vector": actor.get("state_vector") or {},
            "influenced_regions": actor.get("influenced_regions") or [],
        }
        if self.risk_contract_version < 2:
            source_agent_payload["risk_object_ids"] = self.agent_risk_lookup.get(int(actor.get("agent_id", -1)), [])
        prompt = {
            "task": "为本轮 EnvFish 推演选择少量可信的跨区域涌现关系，并返回严格 JSON。",
            "round": round_num,
            "search_mode": self.search_mode,
            "source_agent": source_agent_payload,
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
                        "rationale": "简体中文关系生成依据",
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
                "rationale 必须使用简体中文，禁止使用 snake_case、类名、UUID 或内部编号作为显示内容。",
                "edge_type、routing_basis 等机器枚举字段可保留英文，不能直接复制到 rationale。",
                "只返回合法 JSON。",
            ],
        }
        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "只返回紧凑 JSON，并严格使用候选列表。所有展示字段必须是简体中文，禁止显示 snake_case、类名或内部编号。"},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=900,
            )
            proposals = result.get("proposals") if isinstance(result, dict) else []
            localized = []
            for item in proposals if isinstance(proposals, list) else []:
                if not isinstance(item, dict):
                    continue
                normalized = dict(item)
                normalized["rationale"] = _chinese_display_text(
                    item.get("rationale"),
                    "基于跨区域传播路径与候选关系生成。",
                )
                localized.append(normalized)
            return localized
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
                    "rationale": f"第 {round_num} 轮依据跨区域传播路径与候选关系建立临时连接。",
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
        latest_dynamic_event: Optional[Dict[str, Any]] = None

        if edge:
            update_causal_context: Dict[str, Any] = {}
            if edge.get("status") == "dormant":
                # a dormant relationship re-forms: reawaken it, keeping its scar history
                edge.setdefault("history", []).append({"round": round_num, "event": "reawakened", "reason": "关系再次得到确认"})
                edge["reawakened_round"] = round_num
                reawakened_event = self._record_dynamic_edge_event(round_num, "reawakened", edge)
                update_causal_context = _child_causal_context(reawakened_event)
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
            latest_dynamic_event = self._record_dynamic_edge_event(
                round_num,
                "updated",
                edge,
                causal_context=update_causal_context,
            )
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
            latest_dynamic_event = self._record_dynamic_edge_event(round_num, "created", edge)

        self._maybe_promote_edge(
            edge,
            round_num,
            causal_context=_child_causal_context(latest_dynamic_event),
        )
        self._rebuild_dynamic_edge_index()
        return edge

    def _maybe_promote_edge(
        self,
        edge: Dict[str, Any],
        round_num: int,
        *,
        causal_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Promote a repeatedly-reconfirmed, strong relationship into the stable
        structural skeleton — relationships that keep re-forming should consolidate
        instead of jittering create/expire/recreate forever. Lowered to reconfirm
        >= 2 (the old >= 3 + disabled-by-default meant 0 promotions ever fired)."""
        if not self.edge_promotion_enabled or edge.get("layer") == "structural":
            return False
        if (
            int(edge.get("reconfirm_count") or 0) >= 2
            and float(edge.get("strength") or 0) >= 0.55
            and float(edge.get("confidence") or 0) >= 0.6
        ):
            edge["layer"] = "structural"
            edge["origin"] = "runtime_promoted"
            edge["status"] = "stable"
            edge["expires_after_round"] = self.total_rounds + int(edge.get("ttl_rounds") or self.default_dynamic_ttl)
            self._record_dynamic_edge_event(
                round_num,
                "promoted",
                edge,
                causal_context=causal_context,
            )
            return True
        return False

    def _activate_dynamic_edge(
        self,
        edge_id: str,
        round_num: int,
        *,
        causal_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        edge = self.dynamic_edge_lookup.get(edge_id)
        if not edge:
            return None
        edge["last_activated_round"] = round_num
        edge["status"] = "active"
        edge["strength"] = clamp_probability(float(edge.get("strength") or 0) + 0.04)
        edge["confidence"] = clamp_probability(float(edge.get("confidence") or 0) + 0.02)
        edge["expires_after_round"] = max(
            int(edge.get("expires_after_round") or round_num),
            round_num + int(edge.get("ttl_rounds") or self.default_dynamic_ttl) - 1,
        )
        edge["reconfirm_count"] = int(edge.get("reconfirm_count") or 1) + 1
        activated_event = self._record_dynamic_edge_event(
            round_num,
            "activated",
            edge,
            causal_context=causal_context,
        )
        self._maybe_promote_edge(
            edge,
            round_num,
            causal_context=_child_causal_context(activated_event),
        )
        self._rebuild_dynamic_edge_index()
        return activated_event

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
        if getattr(self, "agent_plan_source", "") == "agent_v2":
            remaining = max(0, int(getattr(self, "_remaining_dynamic_validations", 0)))
            if remaining <= 0:
                return [], llm_search_remaining
            candidates = candidates[:remaining]
            self._remaining_dynamic_validations = max(0, remaining - len(candidates))

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

    def _choose_validated_agent_action(
        self,
        actor: Dict[str, Any],
        region: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        if getattr(self, "agent_plan_source", "") != "agent_v2":
            action_key = self._choose_agent_action(actor, region)
            return action_key, {
                "contract_version": "legacy-action-compatibility.v1",
                "decision_mode": "legacy_compatibility",
                "candidate_evaluations": [],
                "selected_action_key": action_key,
                "selected_action_label_zh": action_label_zh(action_key),
                "selected_validation": {
                    "contract_version": "legacy-action-compatibility.v1",
                    "action_key": action_key,
                    "action_label_zh": action_label_zh(action_key),
                    "accepted": True,
                    "rejection_reasons_zh": [],
                    "resource_costs": {},
                },
                "rationale_zh": "历史配置沿用兼容动作选择逻辑。",
            }

        evaluations: List[Dict[str, Any]] = []
        for action_key in self._rank_agent_action_candidates(actor, region):
            validation = validate_agent_action(actor, action_key)
            evaluations.append(validation)
            if validation["accepted"]:
                return action_key, {
                    "contract_version": AGENT_ACTION_CONTRACT_VERSION,
                    "decision_mode": "capability_permission_resource_validated",
                    "candidate_evaluations": evaluations,
                    "selected_action_key": action_key,
                    "selected_action_label_zh": validation["action_label_zh"],
                    "selected_validation": validation,
                    "rationale_zh": "该动作在当前行动空间内，并通过能力、权限与资源校验。",
                }

        wait_validation = validate_agent_action(actor, "wait")
        evaluations.append(wait_validation)
        return "wait", {
            "contract_version": AGENT_ACTION_CONTRACT_VERSION,
            "decision_mode": "capability_permission_resource_validated",
            "candidate_evaluations": evaluations,
            "selected_action_key": "wait",
            "selected_action_label_zh": wait_validation["action_label_zh"],
            "selected_validation": wait_validation,
            "rationale_zh": "当前候选动作均未通过校验，本轮保持待命。",
        }

    def _rank_agent_action_candidates(
        self,
        actor: Dict[str, Any],
        region: Dict[str, Any],
    ) -> List[str]:
        action_space = [
            str(item or "").strip()
            for item in actor.get("action_space") or []
            if str(item or "").strip()
        ]
        state = region.get("state_vector") or {}
        exposure = clamp_score(state.get("exposure_score", 0))
        spread = clamp_score(state.get("spread_pressure", 0))
        ecology = clamp_score(state.get("ecosystem_integrity", 60))
        service = clamp_score(state.get("service_capacity", 60))
        panic = clamp_score(state.get("panic_level", 0))
        priority: List[str] = []
        if exposure >= 65 or spread >= 65:
            priority.extend(
                [
                    "shutdown_line",
                    "mitigate_emission",
                    "enforce_restriction",
                    "evacuate",
                    "patient_triage",
                    "issue_alert",
                    "coordinate_response",
                    "report_hazard",
                    "monitor",
                    "transport_pressure",
                    "stress_signal",
                ]
            )
        if ecology <= 55:
            priority.extend(
                [
                    "deploy_remediation",
                    "sample_collect",
                    "publish_assessment",
                    "stress_signal",
                    "migration_shift",
                    "retain_pollutant",
                    "partial_recovery",
                ]
            )
        if service <= 50:
            priority.extend(
                [
                    "stabilize_services",
                    "reroute",
                    "route_flow",
                    "adjust_supply",
                    "request_transfer",
                    "request_support",
                ]
            )
        if panic >= 55:
            priority.extend(["public_briefing", "issue_notice", "verify", "broadcast"])
        priority.extend(action_space)
        priority.append("observe")
        ranked = list(dict.fromkeys(priority))
        if getattr(self, "agent_plan_source", "") == "agent_v2":
            return ranked[: max(1, int(self.action_candidates_per_agent))]
        return ranked

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
        rationale = (
            f"{actor.get('name') or actor.get('username')} 在当前压力下选择“"
            f"{action_label_zh(action_type)}”。"
        )
        turning_point = ""

        if action == "wait":
            actor_delta = {}
            region_delta = {}
            target_delta = {}
            channel = "self"
        elif action in {"deploy_remediation", "restore_habitat", "volunteer_cleanup", "mitigate_emission"}:
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
            target_delta = {
                "vulnerability_score": 0.8,
                "response_capacity": -0.4 if action in {"stress_signal", "bioaccumulate", "retain_pollutant"} else -0.2,
                "panic_level": 0.4 if action in {"stress_signal", "migration_shift", "migrate", "signal_loss"} else 0.1,
            }
            channel = "ecology"
            turning_point = f"{actor.get('name')} 显示出生态系统已进入更脆弱状态。"
        elif action == "dilute" or action == "partial_recovery":
            actor_delta = {"vulnerability_score": -0.6}
            region_delta = {"exposure_score": -0.8, "ecosystem_integrity": 0.8}
            target_delta = {"vulnerability_score": -0.4, "response_capacity": 0.3}
            channel = "ecology"
        else:
            actor_delta = {"response_capacity": 0.4}
            region_delta = {"public_trust": 0.1}

        # M8: every action carries at least a faint, channel-appropriate effect on
        # its interaction partner, so that when an actor DOES have a counterpart the
        # interaction is real (and recorded) rather than silently dropped because a
        # particular branch left target_delta empty. Channel-typed so the sign is
        # defensible (information builds a little response capacity; media/ecology
        # raise stress). Tiny by design — it never dominates the explicit branches.
        if not target_delta and action != "wait":
            minimal_target = {
                "information": {"response_capacity": 0.3},
                "governance": {"response_capacity": 0.3},
                "environment": {"public_trust": 0.2},
                "media": {"panic_level": 0.3},
                "market": {"economic_stress": 0.3},
                "ecology": {"vulnerability_score": 0.3},
            }
            target_delta = dict(minimal_target.get(channel, {"public_trust": 0.1}))

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
        action = str(action_type or "").lower()
        if action in {"broadcast", "public_campaign", "panic_buy", "question_authority"}:
            preferred_channel = "media"
        elif action in {"issue_alert", "publish_assessment", "public_briefing", "monitor", "report_hazard", "verify"}:
            preferred_channel = "information"
        elif action in {"continue_output", "continue_production", "market_shift", "adjust_supply", "price_signal"}:
            preferred_channel = "market"
        elif action in {"stress_signal", "migration_shift", "migrate", "breed_decline", "signal_loss", "bioaccumulate", "transport_pressure", "retain_pollutant", "dilute", "partial_recovery"}:
            preferred_channel = "ecology"
        else:
            preferred_channel = "governance"
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
                    "agent_name": actor.get("name") or actor.get("username"),
                    "action_type": action_type,
                    "rationale": item.get("rationale", ""),
                    "delta": delta,
                }
            )
            self._write_action(
                platform="reddit",
                round_num=round_num,
                agent_id=agent_id,
                agent_name=actor.get("name") or actor.get("username"),
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
        policy_execution: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        regions = []
        for region in self.region_graph:
            vector = normalize_state_vector(region.get("state_vector") or {})
            scenario_state = self._scenario_state_for_vector(vector)
            regions.append(
                {
                    "region_id": region["region_id"],
                    "name": region["name"],
                    "region_type": region.get("region_type"),
                    "neighbors": region.get("neighbors", []),
                    "state_vector": vector,
                    "scenario_state": scenario_state,
                    **vector,
                    "severity_band": score_band(vector["exposure_score"]),
                    "uncertainty_band": self._uncertainty_band(vector),
                }
            )
        subregions = []
        for region in self.subregion_graph:
            vector = normalize_state_vector(region.get("state_vector") or {})
            scenario_state = self._scenario_state_for_vector(vector)
            subregions.append(
                {
                    "region_id": region["region_id"],
                    "name": region["name"],
                    "region_type": region.get("region_type"),
                    "parent_region_id": region.get("parent_region_id"),
                    "land_use_class": region.get("land_use_class"),
                    "distance_band": region.get("distance_band"),
                    "state_vector": vector,
                    "scenario_state": scenario_state,
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
                "agent_name": actor.get("name") or actor.get("username"),
                "name": actor.get("name"),
                "agent_type": actor.get("agent_type") or actor.get("node_family"),
                "agent_subtype": actor.get("agent_subtype") or actor.get("role_type"),
                "archetype_key": actor.get("archetype_key"),
                "primary_region": actor.get("primary_region"),
                "home_subregion_id": actor.get("home_subregion_id"),
                "influenced_regions": list(actor.get("influenced_regions") or []),
                "capability_keys": list(actor.get("capability_keys") or []),
                "permission_keys": list(actor.get("permission_keys") or []),
                "resource_budget": deepcopy(actor.get("resource_budget") or {}),
                "resource_uncertainty": deepcopy(actor.get("resource_uncertainty") or {}),
                "action_space": list(actor.get("action_space") or []),
                "role_demand_refs": list(actor.get("role_demand_refs") or []),
                "spatial_anchor_refs": deepcopy(actor.get("spatial_anchor_refs") or []),
                "evidence_refs": list(actor.get("evidence_refs") or []),
                "evidence_confidence": actor.get("evidence_confidence"),
                "profile_confidence": actor.get("profile_confidence"),
                "representation_level": actor.get("representation_level"),
                "is_aggregate": bool(actor.get("is_aggregate")),
                "runtime_lifecycle": deepcopy(actor.get("runtime_lifecycle") or {}),
                "lifecycle_status": actor.get("lifecycle_status")
                or (actor.get("runtime_lifecycle") or {}).get("lifecycle_status")
                or "active",
                "goals": list(actor.get("goals") or []),
                "sensitivities": list(actor.get("sensitivities") or []),
                "state_vector": normalize_state_vector(actor.get("state_vector") or {}),
                "scenario_state": self._scenario_state_for_vector(normalize_state_vector(actor.get("state_vector") or {})),
            }
            for actor in self.actor_profiles
        ]
        dynamic_edges = [
            self._serialize_dynamic_edge(edge)
            for edge in self.dynamic_edge_lookup.values()
            if edge.get("status") not in ("expired", "dormant")
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
            "simulation_architecture": self.simulation_architecture,
            "scenario_state_schema": self.scenario_state_schema,
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
            "action_records": list(interactions.get("action_records") or []),
            "state_mutation_records": [
                *(interactions.get("state_mutation_records") or []),
                *((policy_execution or {}).get("state_mutation_records") or []),
            ],
            "relationship_events": list(interactions.get("relationship_events") or []),
            "relationship_states": deepcopy(
                interactions.get("relationship_states")
                or getattr(self, "relationship_states", [])
            ),
            "dynamic_edge_summary": interactions.get("dynamic_edge_summary") or {
                "search_mode": self.search_mode,
                "total_dynamic_edges": len(dynamic_edges),
            },
            "transport_edges": self.transport_edges,
            "diffusion_context": self.diffusion_context,
            "diffusion": diffusion,
            "interactions": interactions,
            "policy_execution": policy_execution or {},
            "feedback": feedback,
            "vulnerability_ranking": vulnerability_ranking,
        }

    def _scenario_state_for_vector(self, vector: Dict[str, Any]) -> Dict[str, float]:
        if not self.scenario_state_schema:
            return {}
        scenario_state: Dict[str, float] = {}
        for key, definition in self.scenario_state_schema.items():
            if not isinstance(definition, dict):
                continue
            legacy_metric = str(definition.get("legacy_metric") or "").strip()
            if legacy_metric and legacy_metric in vector:
                scenario_state[key] = round(clamp_score(vector.get(legacy_metric)), 2)
                continue
            lowered = f"{key} {definition.get('label') or ''} {definition.get('description') or ''}".lower()
            if any(token in lowered for token in ("exposure", "暴露", "受体")):
                metric = "exposure_score"
            elif any(token in lowered for token in ("spread", "pressure", "扩散", "压力", "源头")):
                metric = "spread_pressure"
            elif any(token in lowered for token in ("trust", "panic", "信任", "恐慌", "情绪")):
                metric = "panic_level"
            elif any(token in lowered for token in ("service", "response", "治理", "响应", "服务")):
                metric = "response_capacity"
            elif any(token in lowered for token in ("ecosystem", "ecology", "生态")):
                metric = "ecosystem_integrity"
            else:
                metric = "vulnerability_score"
            scenario_state[key] = round(clamp_score(vector.get(metric)), 2)
        return scenario_state

    def _build_round_reasoning_record(
        self,
        *,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
        interactions: Dict[str, Any],
        feedback: Dict[str, Any],
        risk_runtime: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = self._fallback_round_reasoning(
            round_num=round_num,
            active_variables=active_variables,
            diffusion=diffusion,
            interactions=interactions,
            feedback=feedback,
            risk_runtime=risk_runtime,
            snapshot=snapshot,
        )
        llm_record = self._llm_round_reasoning(
            round_num=round_num,
            active_variables=active_variables,
            diffusion=diffusion,
            interactions=interactions,
            feedback=feedback,
            risk_runtime=risk_runtime,
            snapshot=snapshot,
        )
        record = {**fallback, **(llm_record or {})}
        record.setdefault("round", round_num)
        record.setdefault("timestamp", self._now())
        record.setdefault("simulation_architecture", LLM_MECHANISM_ARCHITECTURE)
        # M8: every N rounds, re-label the live relationship graph (semantic
        # relabels / leverage hints / emergent-pattern notes). Guarded + bounded;
        # deterministic fallback when no LLM. Emitted into the reasoning record so
        # it lands in the round_reasoning_ledger alongside the rest of the round.
        relabel = self._relation_relabel_pass(round_num=round_num, interactions=interactions)
        if relabel:
            record["relation_relabel"] = relabel
        return record

    def _build_relationship_brief(self, interactions: Dict[str, Any]) -> Dict[str, Any]:
        """Compact, bounded snapshot of the live relationship graph for the LLM /
        fallback relabel pass: the strongest active dynamic edges, this round's new
        edges and detected feedback loops. Pure read — never mutates state."""
        active_edges = [
            self._serialize_dynamic_edge(edge)
            for edge in self.dynamic_edge_lookup.values()
            if edge.get("status") not in ("expired", "dormant")
        ]
        active_edges.sort(key=lambda item: float(item.get("strength") or 0.0), reverse=True)
        return {
            "active_edge_count": len(active_edges),
            "top_active_edges": active_edges[:12],
            "new_edges_this_round": list(interactions.get("new_dynamic_edges") or [])[:8],
            "feedback_loops": self._detect_feedback_loops(max_loops=6),
        }

    def _relation_relabel_pass(
        self,
        *,
        round_num: int,
        interactions: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Re-label / annotate the relationship graph. Runs only on relabel rounds.
        Tries the LLM first (guarded), then a deterministic fallback so the ledger
        is never silently empty when there is something to talk about. Additive:
        produces an annotation record, it does not mutate any edge in place."""
        if not getattr(self, "relation_relabel_enabled", False):
            return None
        interval = max(1, int(getattr(self, "relation_relabel_interval", 3)))
        if round_num % interval != 0:
            return None
        brief = self._build_relationship_brief(interactions)
        if not brief.get("top_active_edges") and not brief.get("feedback_loops"):
            return None
        llm_relabel = self._llm_relation_relabel(round_num=round_num, brief=brief)
        if llm_relabel:
            self.latest_relation_relabel = llm_relabel
            return llm_relabel
        fallback = self._fallback_relation_relabel(round_num=round_num, brief=brief)
        self.latest_relation_relabel = fallback
        return fallback

    def _llm_relation_relabel(
        self,
        *,
        round_num: int,
        brief: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not getattr(self, "llm", None):
            return None
        prompt = {
            "task": (
                "重新标注并解释这张持续演化的生态关系图。"
                "只描述结构、方向和作用性质，不得虚构量化数值。"
            ),
            "round": round_num,
            "relationship_brief": brief,
            "schema": {
                "relabels": [
                    {"edge_id": "brief 中的机器编号", "semantic_label": "简体中文短标签", "reason": "简体中文理由"}
                ],
                "leverage_hints": [
                    {"edge_id": "机器编号", "why_leverage": "简体中文控制点说明"}
                ],
                "emergent_patterns": ["一行简体中文涌现模式或反馈环说明"],
            },
            "rules": [
                "只能引用 brief 中已有的 edge_id。",
                "不得虚构事实，只做定性解释。",
                "semantic_label、reason、why_leverage、emergent_patterns 必须使用简体中文。",
                "禁止使用 snake_case、类名、UUID 或内部编号作为显示内容；机器编号只能放在对应 id 字段。",
                "只返回合法 JSON。",
            ],
        }
        try:
            response = self.llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "你负责重标生态关系图。只返回合法 JSON；展示字段必须使用简体中文，保持定性、结构化与诚实，禁止显示内部标识。",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.3,
                max_tokens=1400,
            )
            relabels = _localized_reason_records(
                response.get("relabels") if isinstance(response, dict) else [],
                display_fields={
                    "semantic_label": "结构性关系",
                    "reason": "依据关系结构、方向与端点角色完成重标。",
                },
                limit=12,
            )
            leverage_hints = _localized_reason_records(
                response.get("leverage_hints") if isinstance(response, dict) else [],
                display_fields={"why_leverage": "该关系对本轮结构变化具有较强控制作用。"},
                limit=8,
            )
            return {
                "round": round_num,
                "timestamp": self._now(),
                "participation": "live",
                "fallback_used": False,
                "relabels": relabels,
                "leverage_hints": leverage_hints,
                "emergent_patterns": _chinese_display_list(
                    response.get("emergent_patterns") if isinstance(response, dict) else [],
                    ["关系网络出现新的结构性联动。"],
                ),
            }
        except Exception as exc:
            logger.warning(f"Relation relabel LLM failed, using explicit fallback: round={round_num}, error={exc}")
            return None

    def _fallback_relation_relabel(
        self,
        *,
        round_num: int,
        brief: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deterministic relabel: derive a semantic label from each strong edge's
        channel + endpoints, flag the strongest as leverage, and name any detected
        feedback loop as an emergent pattern. No LLM, no network."""
        channel_labels = {
            "ecology": "生态受体耦合",
            "ecology_corridor_signal": "生态走廊信号",
            "water_flow": "水文输运耦合",
            "media": "舆论传导",
            "information": "信息协同",
            "market": "市场联动",
            "governance": "治理协调",
            "social": "社会联系",
        }
        relabels: List[Dict[str, Any]] = []
        leverage_hints: List[Dict[str, Any]] = []
        for edge in (brief.get("top_active_edges") or [])[:8]:
            channel = str(edge.get("interaction_channel") or edge.get("edge_type") or "").lower()
            label = channel_labels.get(channel, "结构性关系")
            relabels.append(
                {
                    "edge_id": edge.get("edge_id"),
                    "semantic_label": label,
                    "reason": f"依据{label}的方向和端点角色完成确定性重标。",
                    "epistemic_status": "inferred",
                }
            )
        strongest = (brief.get("top_active_edges") or [])[:1]
        for edge in strongest:
            if float(edge.get("strength") or 0.0) >= 0.4:
                leverage_hints.append(
                    {
                        "edge_id": edge.get("edge_id"),
                        "why_leverage": "本轮强度最高的活跃关系，最可能是结构性控制点。",
                    }
                )
        emergent_patterns: List[str] = []
        for loop in (brief.get("feedback_loops") or [])[:4]:
            loop_label = {
                "reinforcing": "强化型",
                "balancing": "平衡型",
                "mixed": "混合型",
            }.get(str(loop.get("loop_type") or "").lower(), "结构性")
            region_count = len(loop.get("regions") or [])
            emergent_patterns.append(
                f"检测到{loop_label}反馈环，涉及 {region_count} 个区域、{int(loop.get('length') or region_count)} 条关系。"
            )
        return {
            "round": round_num,
            "timestamp": self._now(),
            "participation": "fallback_explicit",
            "fallback_used": True,
            "fallback_reason": "relation_relabel_llm_unavailable_or_failed",
            "relabels": relabels,
            "leverage_hints": leverage_hints,
            "emergent_patterns": emergent_patterns,
        }

    def _llm_round_reasoning(
        self,
        *,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
        interactions: Dict[str, Any],
        feedback: Dict[str, Any],
        risk_runtime: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.llm:
            return None
        top_regions = list(snapshot.get("vulnerability_ranking") or [])[:5]
        prompt = {
            "task": "用中文解释这一轮 EnvFish 生态-社会推演，并返回严格 JSON。",
            "round": round_num,
            "scenario_model": self.scenario_model,
            "mechanism_graph": {
                "nodes": list((self.mechanism_graph or {}).get("nodes") or [])[:30],
                "edges": list((self.mechanism_graph or {}).get("edges") or [])[:45],
            },
            "active_variables": active_variables[:8],
            "diffusion_summary": {
                "transfer_count": len(diffusion.get("transfers") or []),
                "applied_transfer_count": len(diffusion.get("applied_transfers") or []),
                "likely_next_impacted_regions": diffusion.get("likely_next_impacted_regions") or [],
            },
            "interaction_summary": interactions.get("dynamic_edge_summary") or {},
            "new_dynamic_edges": list(interactions.get("new_dynamic_edges") or [])[:12],
            "turning_points": list(interactions.get("turning_points") or [])[:8],
            "feedback_turning_points": list(feedback.get("turning_points") or [])[:8],
            "top_regions": top_regions,
            "risk_runtime_summary": {
                "primary_active_risk_id": risk_runtime.get("primary_active_risk_id"),
                "active_count": len(risk_runtime.get("active_risks") or risk_runtime.get("risks") or []),
            },
            "schema": {
                "summary": "一句中文轮次解释",
                "activated_mechanisms": [
                    {
                        "mechanism_edge_id": "id from mechanism_graph if possible",
                        "reason": "中文说明：为什么本轮激活",
                        "affected_regions": ["region_id"],
                        "confidence": 0.0,
                    }
                ],
                "state_change_reasons": [
                    {
                        "target_type": "region|agent|risk",
                        "target_id": "id",
                        "state_variable": "scenario variable or legacy metric",
                        "reason": "中文说明：为什么变化",
                    }
                ],
                "relation_change_reasons": [
                    {
                        "edge_id": "dynamic or structural edge id",
                        "reason": "中文说明：为什么出现、激活或衰减",
                    }
                ],
                "uncertainty_notes": ["中文不确定性说明"],
            },
            "rules": [
                "所有面向用户展示的 summary、reason、uncertainty_notes 必须使用简体中文。",
                "禁止在展示字段中使用 snake_case、类名、UUID、内部编号或 entity/agent/snapshot 等机器词；这些内容只能放在对应机器字段。",
                "尽量引用机制图，但不要编造 payload 中不存在的精确事实。",
                "只返回合法 JSON。",
            ],
        }
        try:
            response = self.llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": "你为生态-社会推演轮次撰写简洁的结构化中文推理。只返回 JSON，不要输出英文解释。",
                    },
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.25,
                max_tokens=1800,
            )
            activated_mechanisms = _localized_reason_records(
                response.get("activated_mechanisms") if isinstance(response, dict) else [],
                display_fields={"reason": "该机制由本轮状态变化触发。"},
                limit=12,
            )
            state_change_reasons = _localized_reason_records(
                response.get("state_change_reasons") if isinstance(response, dict) else [],
                display_fields={"reason": "本轮扩散、互动与反馈共同推动该状态变化。"},
                limit=18,
            )
            relation_change_reasons = _localized_reason_records(
                response.get("relation_change_reasons") if isinstance(response, dict) else [],
                display_fields={"reason": "本轮传播路径与主体互动推动该关系变化。"},
                limit=18,
            )
            return {
                "round": round_num,
                "timestamp": self._now(),
                "simulation_architecture": LLM_MECHANISM_ARCHITECTURE,
                "llm_participation": "live",
                "fallback_used": False,
                "summary": _chinese_display_text(
                    response.get("summary") if isinstance(response, dict) else "",
                    "本轮扩散、主体互动与反馈共同更新了风险态势。",
                ),
                "activated_mechanisms": activated_mechanisms,
                "state_change_reasons": state_change_reasons,
                "relation_change_reasons": relation_change_reasons,
                "uncertainty_notes": _chinese_display_list(
                    response.get("uncertainty_notes") if isinstance(response, dict) else [],
                    ["当前结论受输入资料完整度与推演假设约束。"],
                ),
            }
        except Exception as exc:
            logger.warning(f"Round reasoning LLM failed, using explicit fallback: round={round_num}, error={exc}")
            return None

    def _fallback_round_reasoning(
        self,
        *,
        round_num: int,
        active_variables: List[Dict[str, Any]],
        diffusion: Dict[str, Any],
        interactions: Dict[str, Any],
        feedback: Dict[str, Any],
        risk_runtime: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        top_region = None
        ranking = snapshot.get("vulnerability_ranking") or []
        if ranking:
            top_region = ranking[0]
        top_region_name = _chinese_display_text((top_region or {}).get("name"), "重点区域")
        new_edges = list(interactions.get("new_dynamic_edges") or [])
        activated_mechanisms = []
        mechanism_edges = list((self.mechanism_graph or {}).get("edges") or [])
        for edge in mechanism_edges[:3]:
            activated_mechanisms.append(
                {
                    "mechanism_edge_id": edge.get("id"),
                    "reason": _chinese_display_text(
                        edge.get("mechanism"),
                        "该机制关系被本轮状态变化触发。",
                    ),
                    "affected_regions": [str((top_region or {}).get("region_id") or "")],
                    "confidence": edge.get("confidence", 0.35),
                    "source": "fallback_explicit",
                }
            )
        return {
            "round": round_num,
            "timestamp": self._now(),
            "simulation_architecture": LLM_MECHANISM_ARCHITECTURE,
            "llm_participation": "fallback_explicit",
            "fallback_used": True,
            "fallback_reason": "round_reasoning_llm_unavailable_or_failed",
            "summary": f"{top_region_name} 是本轮最主要的状态变化区域，扩散、互动和反馈共同更新了风险态势。",
            "activated_mechanisms": activated_mechanisms,
            "state_change_reasons": [
                {
                    "target_type": "region",
                    "target_id": str((top_region or {}).get("region_id") or ""),
                    "state_variable": "vulnerability_score",
                    "reason": "基于本轮扩散、主体互动和反馈汇总形成的显式变化解释。",
                }
            ],
            "relation_change_reasons": [
                {
                    "edge_id": edge.get("edge_id"),
                    "reason": _chinese_display_text(
                        edge.get("rationale"),
                        "本轮传播路径与主体互动生成或激活了该动态关系。",
                    ),
                }
                for edge in new_edges[:8]
                if isinstance(edge, dict)
            ],
            "risk_change_reasons": [
                {
                    "risk_id": risk_runtime.get("primary_active_risk_id"),
                    "reason": "风险运行态由本轮状态快照、动态关系和事件共同派生。",
                }
            ],
            "active_variable_count": len(active_variables or []),
            "uncertainty_notes": [
                "当前使用确定性规则维持推演连续性，结论应结合实时模型推理进一步评估。",
            ],
            "feedback_turning_points": _chinese_display_list(
                feedback.get("turning_points") or [],
                ["本轮反馈结构尚未出现明确拐点。"],
            ),
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
            "task": "生成区域级污染传播的受约束 JSON。",
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
                        "rationale": "简体中文传播依据",
                    }
                ]
            },
            "constraints": [
                "只能连接已配置的传播目标或区域自身。",
                "不得生成跨越传播路径的跳跃扩散。",
                "transfer_intensity 必须保持在 0 到 100 之间。",
                "rationale 必须使用简体中文，禁止使用 snake_case、类名、UUID 或内部编号作为显示内容。",
                "没有活跃压力时返回空 transfers 数组。",
            ],
        }
        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "只返回紧凑 JSON 并遵守约束。所有展示字段必须是简体中文，禁止显示 snake_case、类名或内部编号。"},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.2,
                max_tokens=1400,
            )
            if not isinstance(result, dict):
                return None
            transfers = _localized_reason_records(
                result.get("transfers"),
                display_fields={"rationale": "依据已配置的传播路径与区域状态生成。"},
                limit=200,
            )
            return {**result, "transfers": transfers}
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
        simulation_id = str((getattr(self, "config", {}) or {}).get("simulation_id") or "runtime")
        for variable in active_variables:
            source_variable_id = str(
                variable.get("variable_id")
                or variable.get("input_id")
                or _stable_runtime_event_id("variable_ref", variable)
            )
            source_regions = variable.get("target_regions") or [self.region_graph[0]["region_id"]]
            for source in source_regions:
                root_event_id = _stable_runtime_event_id(
                    "spread_event",
                    simulation_id,
                    "fallback_injection",
                    source_variable_id,
                    int(round_num),
                    source,
                )
                transfers.append(
                    {
                        "event_id": root_event_id,
                        "root_event_id": root_event_id,
                        "parent_event_ids": [],
                        "hop": 0,
                        "source_variable_id": source_variable_id,
                        "causal_source_type": "injected_variable",
                        "source_region": source,
                        "target_region": source,
                        "transfer_intensity": clamp_score(variable.get("intensity_0_100", 50)),
                        "delay_rounds": 0,
                        "persistence": clamp_score(self.template_rules["default_persistence"] + variable.get("intensity_0_100", 50) * 0.1),
                        "confidence": 0.62,
                        "rationale": (
                            f"注入变量“{_chinese_display_text(variable.get('name'), '场景变量')}”"
                            "直接对该区域施加压力。"
                        ),
                    }
                )
                outgoing_edges = self._transport_edges_from_region(source)[: self.template_rules["max_neighbor_spread"]]
                for edge in outgoing_edges:
                    attenuation = float(edge.get("attenuation_rate") or 0)
                    travel_time = int(edge.get("travel_time_rounds") or lag)
                    child_event_id = _stable_runtime_event_id(
                        "spread_event",
                        simulation_id,
                        "fallback_transport",
                        root_event_id,
                        edge.get("edge_id"),
                        source,
                        edge.get("target_region_id"),
                    )
                    transfers.append(
                        {
                            "event_id": child_event_id,
                            "root_event_id": root_event_id,
                            "parent_event_ids": [root_event_id],
                            "hop": 1,
                            "source_variable_id": source_variable_id,
                            "causal_source_type": "fallback_propagation",
                            "source_region": source,
                            "target_region": edge.get("target_region_id"),
                            "transfer_intensity": clamp_score(variable.get("intensity_0_100", 50) * decay * max(0.18, 1.0 - attenuation)),
                            "delay_rounds": travel_time,
                            "persistence": clamp_score(self.template_rules["default_persistence"]),
                            "confidence": clamp_probability(edge.get("confidence", 0.56)),
                            "rationale": _chinese_display_text(
                                edge.get("rationale"),
                                "依据传播模板与相邻路径向关联区域扩散。",
                            ),
                        }
                    )
        for due in due_transfers:
            outgoing_edges = self._transport_edges_from_region(due["target_region"])[:1]
            for edge in outgoing_edges:
                attenuation = float(edge.get("attenuation_rate") or 0)
                travel_time = int(edge.get("travel_time_rounds") or lag)
                parent_event_id = str(due.get("event_id") or "").strip()
                root_event_id = str(due.get("root_event_id") or parent_event_id).strip()
                try:
                    child_hop = max(0, int(due.get("hop") or 0)) + 1
                except (TypeError, ValueError):
                    child_hop = 1
                child_event_id = _stable_runtime_event_id(
                    "spread_event",
                    simulation_id,
                    "fallback_secondary_transport",
                    parent_event_id,
                    edge.get("edge_id"),
                    due["target_region"],
                    edge.get("target_region_id"),
                )
                transfers.append(
                    {
                        "event_id": child_event_id,
                        "root_event_id": root_event_id or child_event_id,
                        "parent_event_ids": [parent_event_id] if parent_event_id else [],
                        "hop": child_hop if parent_event_id else 0,
                        "source_variable_id": due.get("source_variable_id"),
                        "causal_source_type": "fallback_propagation",
                        "source_region": due["target_region"],
                        "target_region": edge.get("target_region_id"),
                        "transfer_intensity": clamp_score(
                            due["transfer_intensity"] * decay * 0.8 * max(0.18, 1.0 - attenuation)
                        ),
                        "delay_rounds": travel_time,
                        "persistence": clamp_score(due["persistence"] * decay),
                        "confidence": clamp_probability(edge.get("confidence", 0.5)),
                        "rationale": _chinese_display_text(
                            edge.get("rationale"),
                            "已受影响区域沿既有路径发生次级传播。",
                        ),
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
            "task": "生成生态影响、主体决策和反馈传播的受约束 JSON，所有展示文本必须是简体中文。",
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
                        "note": "中文说明",
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
                        "rationale": "中文说明",
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
                        "loop": "中文反馈环说明",
                    }
                ],
                "turning_points": ["中文拐点说明"],
            },
            "constraints": [
                "所有 note、rationale、loop、turning_points 必须使用简体中文。",
                "禁止在展示字段中使用 snake_case、类名、UUID、内部编号或 entity/agent 等机器词。",
                "所有 delta 保持在 -20 到 20 之间。",
                "只能使用真实 agent_id。",
                "actor decisions 最多 5 条。",
                "只返回合法 JSON。",
            ],
        }
        try:
            result = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "只返回紧凑 JSON。所有面向用户展示的文本字段必须是简体中文，不能夹杂英文句子、snake_case、类名或内部编号。"},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.25,
                max_tokens=1800,
            )
            if not isinstance(result, dict):
                return None
            return {
                **result,
                "ecological_impacts": _localized_reason_records(
                    result.get("ecological_impacts"),
                    display_fields={"note": "暴露压力改变了区域生态与生计状态。"},
                    limit=24,
                ),
                "actor_decisions": _localized_reason_records(
                    result.get("actor_decisions"),
                    display_fields={"rationale": "主体依据本轮风险、资源与协作条件采取行动。"},
                    limit=12,
                ),
                "feedback_propagation": _localized_reason_records(
                    result.get("feedback_propagation"),
                    display_fields={"loop": "本轮状态变化形成了区域反馈传播。"},
                    limit=24,
                ),
                "turning_points": _chinese_display_list(
                    result.get("turning_points"),
                    ["本轮尚未识别出明确的反馈拐点。"],
                ),
            }
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
                    "note": "暴露压力削弱生态完整性，并影响周边生计稳定。",
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
                    "loop": "环境压力 → 生态退化 → 生计波动 → 恐慌/媒体传播 → 市场行为变化",
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
                        "rationale": "治理主体在中等暴露下倾向于信息披露，在高暴露下转向限制措施。",
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
                        "rationale": "受影响主体通过舆情放大或市场行为调整作出反应。",
                    }
                )

        return {
            "ecological_impacts": ecological_impacts,
            "actor_decisions": actor_decisions[:5],
            "feedback_propagation": feedback_propagation,
            "turning_points": [f"第 {round_num} 轮，{item['name']} 的可见压力上升。" for item in top_regions[:2]],
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
        for causal_key in (
            "event_id",
            "root_event_id",
            "parent_event_ids",
            "hop",
            "source_variable_id",
            "causal_source_type",
        ):
            if causal_key in transfer:
                validated[causal_key] = deepcopy(transfer.get(causal_key))
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
                    self.ipc.send_success(command.command_id, {"message": "推演环境正在关闭"})
                elif command.command_type == CommandType.INJECT_VARIABLE:
                    variable = command.args.get("variable") or {}
                    normalize_runtime_injection_schedule(
                        variable,
                        current_round=int(self.current_round or 0),
                    )
                    self.injections.append(variable)
                    reframe_result = self.risk_definition_builder.reframe_runtime(
                        existing_definitions=self.risk_definitions,
                        regions=self.region_graph,
                        profiles=self.actor_profiles,
                        injected_variables=[variable],
                        current_round=self.current_round or int(variable.get("start_round") or 1),
                        scenario_mode=str(self.config.get("scenario_mode") or "baseline_mode"),
                        diffusion_template=self.template,
                    )
                    self.risk_definitions = deepcopy(reframe_result.get("risk_definitions") or self.risk_definitions)
                    variable_events = self.risk_event_engine.build_variable_events(
                        variable=variable,
                        round_num=self.current_round or int(variable.get("start_round") or 1),
                        matched_risk_ids=reframe_result.get("updated_risk_ids") or [],
                        created_risk_ids=reframe_result.get("created_risk_ids") or [],
                    )
                    if variable_events:
                        self.risk_events.extend(variable_events)
                    self._rebuild_risk_indexes()
                    append_jsonl(
                        self.intervention_log,
                        {
                            "timestamp": self._now(),
                            "round": self.current_round,
                            "variable": variable,
                            "status": "accepted",
                            "risk_refresh": {
                                "updated_risk_ids": reframe_result.get("updated_risk_ids") or [],
                                "created_risk_ids": reframe_result.get("created_risk_ids") or [],
                            },
                        },
                    )
                    if self.latest_summary:
                        refreshed = self._refresh_risk_runtime(
                            round_num=self.current_round or int(variable.get("start_round") or 1),
                            snapshot=self.latest_summary,
                            refresh_reason="variable_introduced",
                            append_history=True,
                        )
                        self.latest_summary["risk_runtime"] = refreshed
                        dump_json(self.latest_snapshot_path, self.latest_summary)
                    else:
                        refreshed = self._refresh_risk_runtime(
                            round_num=self.current_round or int(variable.get("start_round") or 1),
                            snapshot=None,
                            refresh_reason="variable_introduced",
                            append_history=True,
                        )
                    self.ipc.send_success(
                        command.command_id,
                        {
                            "message": "变量已加入队列",
                            "variable": variable,
                            "current_round": self.current_round,
                            "risk_refresh": {
                                "updated_risk_ids": reframe_result.get("updated_risk_ids") or [],
                                "created_risk_ids": reframe_result.get("created_risk_ids") or [],
                                "pinned_risk_ids": list(refreshed.get("pinned_risk_ids") or []),
                                "primary_active_risk_id": refreshed.get("primary_active_risk_id"),
                            },
                        },
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
        display_agent_name = _chinese_display_text(
            actor.get("name"),
            f"代理体 {agent_id + 1}",
        )
        display_profession = _chinese_display_text(actor.get("profession"), "场景主体")
        record = {
            "timestamp": self._now(),
            "round": self.current_round,
            "agent_id": agent_id,
            "agent_name": display_agent_name,
            "profession": display_profession,
            "prompt": prompt,
            "response": response,
            "region": _chinese_display_text(region.get("name"), "所属区域"),
        }
        append_jsonl(self.interview_log, record)
        result = {
            f"reddit_{agent_id}": {
                "agent_id": agent_id,
                "agent_name": display_agent_name,
                "profession": display_profession,
                "response": response,
                "answer": response,
            },
            f"twitter_{agent_id}": {
                "agent_id": agent_id,
                "agent_name": display_agent_name,
                "profession": display_profession,
                "response": response,
                "answer": response,
            },
        }
        return {"results": result, "engine_mode": "envfish"}

    def _answer_interview(self, actor: Dict[str, Any], region: Dict[str, Any], prompt: str) -> str:
        if self.llm:
            payload = {
                "task": "以 EnvFish 推演主体的第一人称回答问题，并使用简体中文。",
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
                    "使用第一人称回答。",
                    "严格停留在推演情境内。",
                    "不要提及自己是人工智能模型。",
                    "回答不超过 180 个汉字。",
                    "回答必须使用简体中文，禁止显示 snake_case、类名、UUID 或内部编号。",
                ],
            }
            try:
                answer = self.llm.chat(
                    messages=[
                        {"role": "system", "content": "你正在扮演推演主体。回答必须使用简体中文，简洁、有依据，禁止显示内部标识。"},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    temperature=0.5,
                    max_tokens=300,
                )
                return _chinese_display_text(
                    answer,
                    "我会依据当前区域状态与自身职责审慎行动，并持续观察风险变化。",
                )
            except Exception:
                pass

        exposure = region.get("state_vector", {}).get("exposure_score", 0)
        panic = region.get("state_vector", {}).get("panic_level", 0)
        display_region = _chinese_display_text(region.get("name"), "本地区")
        display_profession = _chinese_display_text(actor.get("profession"), "相关主体")
        return (
            f"我主要关注{display_region}的局势。现在暴露压力大约在 {exposure:.0f}/100，"
            f"社会恐慌大约在 {panic:.0f}/100。以我的角色来看，最明显的问题是"
            f"{display_profession}需要在生态风险和生计压力之间做取舍。"
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
            "agent_name": _chinese_display_text(agent_name, f"代理体 {agent_id + 1}"),
            "action_type": action_type,
            "action_label_zh": action_label_zh(str(action_type or "").lower()),
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
                "process_pid": os.getpid(),
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
