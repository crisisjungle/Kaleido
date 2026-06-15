"""
Unified animation payload builder for live/frozen simulations.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger
from .simulation_manager import SimulationManager
from .simulation_map_projection import SimulationMapProjectionBuilder
from .simulation_realtime_graph import SimulationRealtimeGraphBuilder

logger = get_logger("envfish.animation")


class SimulationAnimationService:
    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        self.manager = SimulationManager()
        self.state = self.manager.get_simulation(simulation_id)
        if not self.state:
            raise ValueError(f"Simulation not found: {simulation_id}")
        self.sim_dir = self.manager.resolve_artifact_dir(self.state, create_if_missing=False)
        if not self.sim_dir:
            raise ValueError(f"Simulation artifacts not found: {simulation_id}")

    def get_animation(self) -> Dict[str, Any]:
        existing = self._load_existing_animation()
        if existing:
            return self._normalize_animation_payload(existing)
        return self._normalize_animation_payload(self._build_animation_payload())

    def _load_existing_animation(self) -> Optional[Dict[str, Any]]:
        candidates = [
            os.path.join(self.sim_dir, "animation.json"),
            os.path.join(self.sim_dir, "animation", "animation.json"),
            os.path.join(os.path.dirname(self.sim_dir), "animation", "animation.json"),
        ]
        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if isinstance(payload, dict):
                    return payload
            except Exception as exc:
                logger.warning(f"读取 animation payload 失败: {path}, error={exc}")
        return None

    def _build_animation_payload(self) -> Dict[str, Any]:
        simulation_config = self._read_json("simulation_config.json", {}) or {}
        latest_snapshot = self._read_json("latest_round_snapshot.json", {}) or {}
        round_snapshots = self._read_jsonl("round_state_matrix.jsonl")
        risk_events = self._read_jsonl("risk_events.jsonl")
        dynamic_edges = self._read_jsonl("dynamic_edge_ledger.jsonl")
        interactions = self._read_jsonl("agent_interaction_ledger.jsonl")
        round_reasoning = self._read_jsonl("round_reasoning_ledger.jsonl")

        realtime_graph = SimulationRealtimeGraphBuilder(self.sim_dir).build()
        map_projection = SimulationMapProjectionBuilder(
            sim_dir=self.sim_dir,
            simulation_id=self.simulation_id,
            map_seed_id=self.state.map_seed_id if self.state.map_seed_id else None,
            source_mode=self.state.source_mode,
        ).build(realtime_graph, key_edges_only=False)

        layout_nodes = self._build_layout_nodes(realtime_graph, map_projection)
        layout_edges = self._build_layout_edges(realtime_graph)
        total_rounds = int(
            simulation_config.get("time_config", {}).get("total_rounds")
            or self.state.configured_total_rounds
            or len(round_snapshots)
            or 36
        )
        reference_time = (
            simulation_config.get("reference_time")
            or self.state.reference_time
            or latest_snapshot.get("timestamp")
            or ""
        )
        minutes_per_round = int(
            simulation_config.get("time_config", {}).get("minutes_per_round")
            or self.state.configured_minutes_per_round
            or 60
        )

        node_first_seen = self._compute_node_first_seen(layout_nodes)
        edge_first_seen = self._compute_edge_first_seen(layout_edges, dynamic_edges)
        edge_last_active = self._compute_edge_last_active(dynamic_edges)
        interactions_by_round = self._group_by_round(interactions)
        risks_by_round = self._group_by_round(risk_events)
        reasoning_by_round = self._group_by_round(round_reasoning)
        snapshot_by_round = {
            int(item.get("round") or item.get("round_num") or 0): item
            for item in round_snapshots
            if isinstance(item, dict)
        }

        # Precompute the real per-round value map (node_id -> pressure metric) so
        # each frame can carry the actual value AND the delta vs the previous round,
        # instead of inferring status purely from a fabricated reveal order.
        value_map_by_round: Dict[int, Dict[str, float]] = {}
        for round_num, snapshot in snapshot_by_round.items():
            value_map_by_round[round_num] = self._node_values_from_snapshot(snapshot)

        frames: List[Dict[str, Any]] = [
            self._build_frame(
                round_num=0,
                timestamp=self._round_timestamp(reference_time, minutes_per_round, 0),
                snapshot=None,
                interactions=[],
                risk_events=[],
                reasoning=[],
                layout_nodes=layout_nodes,
                layout_edges=layout_edges,
                node_first_seen=node_first_seen,
                edge_first_seen=edge_first_seen,
                edge_last_active=edge_last_active,
                map_projection=map_projection,
                value_map=value_map_by_round.get(0, {}),
                prev_value_map={},
            )
        ]

        for round_num in range(1, total_rounds + 1):
            snapshot = snapshot_by_round.get(round_num)
            if not snapshot and round_num == total_rounds:
                snapshot = latest_snapshot
            value_map = value_map_by_round.get(round_num)
            if value_map is None:
                value_map = self._node_values_from_snapshot(snapshot)
            prev_value_map = self._latest_value_map_before(value_map_by_round, round_num)
            frames.append(
                self._build_frame(
                    round_num=round_num,
                    timestamp=self._round_timestamp(reference_time, minutes_per_round, round_num),
                    snapshot=snapshot,
                    interactions=interactions_by_round.get(round_num, []),
                    risk_events=risks_by_round.get(round_num, []),
                    reasoning=reasoning_by_round.get(round_num, []),
                    layout_nodes=layout_nodes,
                    layout_edges=layout_edges,
                    node_first_seen=node_first_seen,
                    edge_first_seen=edge_first_seen,
                    edge_last_active=edge_last_active,
                    map_projection=map_projection,
                    value_map=value_map,
                    prev_value_map=prev_value_map,
                )
            )

        return {
            "meta": {
                "simulation_id": self.simulation_id,
                "golden_case_id": self.state.golden_case_id,
                "artifact_mode": self.state.artifact_mode,
                "reference_time": reference_time,
                "minutes_per_round": minutes_per_round,
                "total_rounds": total_rounds,
                "default_speed_ms": 1800,
                "speed_options_ms": [1000, 1800, 2600],
                "simulation_architecture": simulation_config.get("simulation_architecture"),
            },
            "layout": {
                "center": map_projection.get("center") or {},
                "zoom_hint": map_projection.get("zoom_hint") or 10,
                "radius_m": map_projection.get("radius_m") or 0,
                "analysis_polygon": map_projection.get("analysis_polygon"),
                "base_layers": list(map_projection.get("layers") or []),
                "nodes": layout_nodes,
                "edges": layout_edges,
            },
            "frames": frames,
        }

    def _normalize_animation_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        meta = dict(payload.get("meta") or {})
        layout = dict(payload.get("layout") or {})
        frames = list(payload.get("frames") or [])

        meta["default_speed_ms"] = int(meta.get("default_speed_ms") or 1800)
        meta["speed_options_ms"] = list(meta.get("speed_options_ms") or [1000, 1800, 2600])

        layout_nodes = list(layout.get("nodes") or [])
        layout_edges = list(layout.get("edges") or [])
        node_by_id = {
            str(item.get("id") or item.get("uuid") or ""): item
            for item in layout_nodes
            if isinstance(item, dict)
        }
        edge_by_id = {
            str(item.get("id") or item.get("uuid") or ""): item
            for item in layout_edges
            if isinstance(item, dict)
        }

        normalized_frames: List[Dict[str, Any]] = []
        for frame in frames:
            if not isinstance(frame, dict):
                continue

            node_states = self._normalize_node_state_delays(
                list(frame.get("node_states") or []),
                node_by_id,
                round_num=int(frame.get("round") or 0),
            )
            edge_states = self._normalize_edge_state_delays(
                list(frame.get("edge_states") or []),
                edge_by_id,
                round_num=int(frame.get("round") or 0),
                node_states=node_states,
            )
            focus_ids = self._build_focus_ids(node_states, edge_states, node_by_id)
            playback_duration_ms = self._frame_playback_duration_ms(
                round_num=int(frame.get("round") or 0),
                node_states=node_states,
                edge_states=edge_states,
                risk_events=list(frame.get("risk_events") or []),
            )

            normalized_frames.append(
                {
                    **frame,
                    "node_states": node_states,
                    "edge_states": edge_states,
                    "focus_ids": focus_ids,
                    "playback_duration_ms": playback_duration_ms,
                    "phase": self._frame_phase_label(
                        round_num=int(frame.get("round") or 0),
                        total_rounds=int(meta.get("total_rounds") or len(frames) or 36),
                        node_states=node_states,
                        edge_states=edge_states,
                        risk_events=list(frame.get("risk_events") or []),
                    ),
                }
            )

        return {
            **payload,
            "meta": meta,
            "layout": layout,
            "frames": normalized_frames,
        }

    def _normalize_node_state_delays(
        self,
        node_states: List[Dict[str, Any]],
        node_by_id: Dict[str, Dict[str, Any]],
        *,
        round_num: int,
    ) -> List[Dict[str, Any]]:
        phase_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in node_states:
            node_id = str(item.get("id") or "")
            layout_node = node_by_id.get(node_id) or {}
            kind = str(layout_node.get("kind") or "").lower()
            status = str(item.get("status") or "steady").lower()
            group_key = self._node_delay_group(round_num=round_num, status=status, kind=kind)
            phase_groups[group_key].append({**item, "_kind": kind, "_status": status})

        group_order = [
            "region",
            "subregion",
            "anchor",
            "new",
            "active",
            "steady",
            "faded",
            "hidden",
        ]
        start_offsets = {
            "region": 0,
            "subregion": 260,
            "anchor": 540,
            "new": 0 if round_num > 0 else 780,
            "active": 280 if round_num > 0 else 1040,
            "steady": 520 if round_num > 0 else 1260,
            "faded": 680 if round_num > 0 else 1420,
            "hidden": 0,
        }
        step_by_group = {
            "region": 110,
            "subregion": 85,
            "anchor": 72,
            "new": 82,
            "active": 62,
            "steady": 26,
            "faded": 18,
            "hidden": 0,
        }

        normalized: List[Dict[str, Any]] = []
        for group in group_order:
            entries = phase_groups.get(group, [])
            if not entries:
                continue
            entries.sort(
                key=lambda item: (
                    self._node_kind_priority(str(item.get("_kind") or "")),
                    int(item.get("first_seen_round") or 0),
                    str(item.get("id") or ""),
                )
            )
            base = start_offsets[group]
            step = step_by_group[group]
            for index, entry in enumerate(entries):
                normalized.append(
                    {
                        key: value
                        for key, value in {
                            **entry,
                            "delay_ms": base + (step * index if group != "hidden" else 0),
                        }.items()
                        if not key.startswith("_")
                    }
                )
        return normalized

    def _normalize_edge_state_delays(
        self,
        edge_states: List[Dict[str, Any]],
        edge_by_id: Dict[str, Dict[str, Any]],
        *,
        round_num: int,
        node_states: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        latest_node_delay = 0
        if node_states:
            latest_node_delay = max(int(item.get("delay_ms") or 0) for item in node_states)

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for item in edge_states:
            edge_id = str(item.get("id") or "")
            layout_edge = edge_by_id.get(edge_id) or {}
            fact_type = str(layout_edge.get("fact_type") or "").lower()
            status = str(item.get("status") or "steady").lower()
            group_key = self._edge_delay_group(round_num=round_num, status=status, fact_type=fact_type)
            grouped[group_key].append({**item, "_fact_type": fact_type, "_status": status})

        group_order = ["structure", "new", "active", "steady", "faded", "hidden"]
        start_offsets = {
            "structure": latest_node_delay + 180,
            "new": latest_node_delay + 260 if round_num == 0 else 180,
            "active": latest_node_delay + 460 if round_num == 0 else 360,
            "steady": latest_node_delay + 680 if round_num == 0 else 540,
            "faded": latest_node_delay + 860 if round_num == 0 else 640,
            "hidden": 0,
        }
        step_by_group = {
            "structure": 45,
            "new": 52,
            "active": 36,
            "steady": 18,
            "faded": 12,
            "hidden": 0,
        }

        normalized: List[Dict[str, Any]] = []
        for group in group_order:
            entries = grouped.get(group, [])
            if not entries:
                continue
            entries.sort(
                key=lambda item: (
                    self._edge_group_priority(str(item.get("_fact_type") or "")),
                    int(item.get("first_seen_round") or 0),
                    str(item.get("id") or ""),
                )
            )
            base = start_offsets[group]
            step = step_by_group[group]
            for index, entry in enumerate(entries):
                normalized.append(
                    {
                        key: value
                        for key, value in {
                            **entry,
                            "delay_ms": base + (step * index if group != "hidden" else 0),
                        }.items()
                        if not key.startswith("_")
                    }
                )
        return normalized

    def _build_focus_ids(
        self,
        node_states: List[Dict[str, Any]],
        edge_states: List[Dict[str, Any]],
        node_by_id: Dict[str, Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        prioritized_nodes = sorted(
            node_states,
            key=lambda item: (
                self._focus_status_priority(str(item.get("status") or "")),
                self._node_kind_priority(str((node_by_id.get(str(item.get("id") or "")) or {}).get("kind") or "")),
                -int(item.get("first_seen_round") or 0),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        prioritized_edges = sorted(
            edge_states,
            key=lambda item: (
                self._focus_status_priority(str(item.get("status") or "")),
                -int(item.get("last_active_round") or 0),
                -int(item.get("first_seen_round") or 0),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )
        return {
            "node_ids": [str(item.get("id") or "") for item in prioritized_nodes if str(item.get("status") or "") in {"new", "active"}][:12],
            "edge_ids": [str(item.get("id") or "") for item in prioritized_edges if str(item.get("status") or "") in {"new", "active"}][:18],
        }

    def _frame_playback_duration_ms(
        self,
        *,
        round_num: int,
        node_states: List[Dict[str, Any]],
        edge_states: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
    ) -> int:
        if round_num == 0:
            return 2600
        new_nodes = sum(1 for item in node_states if str(item.get("status") or "") == "new")
        active_nodes = sum(1 for item in node_states if str(item.get("status") or "") == "active")
        new_edges = sum(1 for item in edge_states if str(item.get("status") or "") == "new")
        active_edges = sum(1 for item in edge_states if str(item.get("status") or "") == "active")
        risk_count = len(risk_events or [])
        duration = 1300 + (new_nodes * 28) + (active_nodes * 12) + (new_edges * 8) + (active_edges * 3) + (risk_count * 220)
        if round_num <= 3:
            duration += 220
        return max(1200, min(2800, int(duration)))

    def _frame_phase_label(
        self,
        *,
        round_num: int,
        total_rounds: int,
        node_states: List[Dict[str, Any]],
        edge_states: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
    ) -> str:
        if round_num == 0:
            return "基线建图"
        if risk_events:
            return "风险脉冲"
        new_count = sum(1 for item in node_states if str(item.get("status") or "") == "new")
        if new_count >= 8:
            return "关系扩张"
        active_count = sum(1 for item in edge_states if str(item.get("status") or "") == "active")
        if active_count >= 12:
            return "网络耦合"
        if round_num >= max(1, total_rounds - 6):
            return "收束复盘"
        return "态势推进"

    def _node_delay_group(self, *, round_num: int, status: str, kind: str) -> str:
        if round_num == 0:
            if kind == "region":
                return "region"
            if kind == "subregion":
                return "subregion"
            return "anchor"
        if status == "new":
            return "new"
        if status == "active":
            return "active"
        if status == "faded":
            return "faded"
        if status == "hidden":
            return "hidden"
        return "steady"

    def _edge_delay_group(self, *, round_num: int, status: str, fact_type: str) -> str:
        if round_num == 0 and fact_type in {"region_neighbor", "region_hierarchy", "belongs_to", "neighbor_of", "transport_edge"}:
            return "structure"
        if status == "new":
            return "new"
        if status == "active":
            return "active"
        if status == "faded":
            return "faded"
        if status == "hidden":
            return "hidden"
        return "steady"

    def _node_kind_priority(self, kind: str) -> int:
        if kind == "region":
            return 4
        if kind == "subregion":
            return 3
        if kind == "agent":
            return 2
        return 1

    def _edge_group_priority(self, fact_type: str) -> int:
        if fact_type in {"dynamic_edge", "affects", "regulates", "cross_region_bridge"}:
            return 4
        if fact_type in {"agent_influence", "influences_region", "supports", "collaborates_with"}:
            return 3
        if fact_type in {"transport_edge", "belongs_to", "region_neighbor", "region_hierarchy"}:
            return 2
        return 1

    def _focus_status_priority(self, status: str) -> int:
        if status == "active":
            return 4
        if status == "new":
            return 3
        if status == "steady":
            return 2
        if status == "faded":
            return 1
        return 0

    def _build_layout_nodes(self, realtime_graph: Dict[str, Any], map_projection: Dict[str, Any]) -> List[Dict[str, Any]]:
        coords_by_id = {
            str(item.get("uuid") or ""): item
            for item in list(map_projection.get("nodes") or [])
            if item.get("uuid")
        }
        nodes: List[Dict[str, Any]] = []
        for index, node in enumerate(list(realtime_graph.get("nodes") or [])):
            node_id = str(node.get("uuid") or node.get("id") or f"node_{index}")
            projection = coords_by_id.get(node_id) or {}
            attrs = dict(node.get("attributes") or {})
            projected_attrs = dict(projection.get("attributes") or {})
            labels = list(node.get("labels") or [])
            nodes.append(
                {
                    "id": node_id,
                    "name": node.get("name") or node_id,
                    "labels": labels,
                    "kind": projection.get("kind") or self._node_kind(node_id, labels),
                    "summary": node.get("summary") or "",
                    "lat": projected_attrs.get("lat"),
                    "lon": projected_attrs.get("lon"),
                    "attributes": {**attrs, **projected_attrs},
                }
            )
        return nodes

    def _build_layout_edges(self, realtime_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        for index, edge in enumerate(list(realtime_graph.get("edges") or [])):
            edge_id = str(edge.get("uuid") or edge.get("id") or f"edge_{index}")
            attrs = dict(edge.get("attributes") or {})
            edges.append(
                {
                    "id": edge_id,
                    "source": edge.get("source_node_uuid") or edge.get("source"),
                    "target": edge.get("target_node_uuid") or edge.get("target"),
                    "name": edge.get("name") or edge.get("fact_type") or "related_to",
                    "fact_type": edge.get("fact_type") or edge.get("name") or "related_to",
                    "fact": edge.get("fact") or "",
                    "attributes": attrs,
                }
            )
        return edges

    def _compute_node_first_seen(self, nodes: List[Dict[str, Any]]) -> Dict[str, int]:
        first_seen: Dict[str, int] = {}
        for node in nodes:
            node_id = str(node.get("id") or "")
            kind = str(node.get("kind") or "")
            attrs = node.get("attributes") or {}
            if kind in {"region", "subregion"}:
                first_seen[node_id] = 0
                continue
            if kind == "agent":
                agent_id = int(attrs.get("agent_id") or 0)
                first_seen[node_id] = min(36, max(1, ((agent_id - 1) // 8) + 1)) if agent_id > 0 else 1
                continue
            first_seen[node_id] = 0
        return first_seen

    def _compute_edge_first_seen(self, edges: List[Dict[str, Any]], dynamic_edges: List[Dict[str, Any]]) -> Dict[str, int]:
        first_seen: Dict[str, int] = {}
        dynamic_round_by_id = {
            str(item.get("edge_id") or ""): int(item.get("created_round") or item.get("round") or 1)
            for item in dynamic_edges
            if isinstance(item, dict)
        }
        for edge in edges:
            edge_id = str(edge.get("id") or "")
            fact_type = str(edge.get("fact_type") or "")
            if fact_type == "dynamic_edge":
                first_seen[edge_id] = dynamic_round_by_id.get(edge_id, 1)
                continue
            if fact_type in {"region_neighbor", "region_hierarchy", "belongs_to", "neighbor_of", "transport_edge"}:
                first_seen[edge_id] = 0
                continue
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            source_first = self._safe_int(source.split("::")[-1])
            target_first = self._safe_int(target.split("::")[-1])
            first_seen[edge_id] = 1 if not source_first or not target_first else 1
        return first_seen

    def _compute_edge_last_active(self, dynamic_edges: List[Dict[str, Any]]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for item in dynamic_edges:
            if not isinstance(item, dict):
                continue
            edge_id = str(item.get("edge_id") or "")
            if not edge_id:
                continue
            result[edge_id] = int(item.get("last_activated_round") or item.get("created_round") or item.get("round") or 0)
        return result

    def _node_values_from_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> Dict[str, float]:
        """Extract the real per-round pressure metric keyed by layout node id.

        Regions/subregions use ``vulnerability_score``; agents use the highest of
        ``vulnerability_score`` / ``panic_level`` from the state vector. This is the
        actual round state, NOT a reveal heuristic.
        """
        values: Dict[str, float] = {}
        if not isinstance(snapshot, dict):
            return values

        for region in list(snapshot.get("regions") or []):
            if not isinstance(region, dict):
                continue
            region_id = str(region.get("region_id") or "").strip()
            if not region_id:
                continue
            score = self._safe_float(region.get("vulnerability_score"))
            if score is None:
                continue
            layer = str(region.get("layer") or "").lower()
            if layer == "subregion" or region.get("parent_region_id"):
                values[f"subregion::{region_id}"] = score
            else:
                values[f"region::{region_id}"] = score

        for sub in list(snapshot.get("subregions") or []):
            if not isinstance(sub, dict):
                continue
            region_id = str(sub.get("region_id") or "").strip()
            if not region_id:
                continue
            score = self._safe_float(sub.get("vulnerability_score"))
            if score is None:
                continue
            values[f"subregion::{region_id}"] = score

        for agent in list(snapshot.get("agents") or []):
            if not isinstance(agent, dict):
                continue
            agent_id = self._safe_int(agent.get("agent_id"))
            if not agent_id:
                continue
            state_vector = agent.get("state_vector") or {}
            vuln = self._safe_float(
                state_vector.get("vulnerability_score")
                if state_vector.get("vulnerability_score") is not None
                else agent.get("vulnerability_score")
            )
            panic = self._safe_float(
                state_vector.get("panic_level")
                if state_vector.get("panic_level") is not None
                else agent.get("panic_level")
            )
            candidates = [value for value in (vuln, panic) if value is not None]
            if not candidates:
                continue
            values[f"agent::{agent_id}"] = max(candidates)

        return values

    def _latest_value_map_before(
        self,
        value_map_by_round: Dict[int, Dict[str, float]],
        round_num: int,
    ) -> Dict[str, float]:
        """Return the most recent populated value map strictly before ``round_num``.

        Rounds can be sparse (not every round writes a snapshot); the delta should be
        measured against the last round that actually carried state.
        """
        for candidate_round in range(round_num - 1, -1, -1):
            candidate = value_map_by_round.get(candidate_round)
            if candidate:
                return candidate
        return {}

    def _state_status_from_value(
        self,
        *,
        kind: str,
        value: Optional[float],
        delta: Optional[float],
    ) -> Optional[str]:
        """Derive an additive status from REAL thresholds on the round value/delta.

        Returns None when no real value is available (so callers can fall back to the
        reveal-order status without pretending state moved).
        """
        if value is None:
            return None
        # Delta-driven movement takes priority: a real numeric drift is the signal.
        if delta is not None:
            if delta >= 1.0:
                return "rising"
            if delta <= -1.0:
                return "falling"
        # No meaningful movement: classify the standing level.
        if value >= 70.0:
            return "critical"
        if value >= 55.0:
            return "elevated"
        return "steady"

    def _build_frame(
        self,
        *,
        round_num: int,
        timestamp: str,
        snapshot: Optional[Dict[str, Any]],
        interactions: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
        reasoning: List[Dict[str, Any]],
        layout_nodes: List[Dict[str, Any]],
        layout_edges: List[Dict[str, Any]],
        node_first_seen: Dict[str, int],
        edge_first_seen: Dict[str, int],
        edge_last_active: Dict[str, int],
        map_projection: Dict[str, Any],
        value_map: Optional[Dict[str, float]] = None,
        prev_value_map: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        latest_agents = list((snapshot or {}).get("agents") or [])
        active_agent_ids = {
            int(item.get("agent_id") or 0)
            for item in latest_agents
            if float((item.get("state_vector") or {}).get("vulnerability_score") or item.get("vulnerability_score") or 0) >= 55
            or float((item.get("state_vector") or {}).get("panic_level") or item.get("panic_level") or 0) >= 35
        }

        current_values = value_map or {}
        previous_values = prev_value_map or {}

        node_states: List[Dict[str, Any]] = []
        for index, node in enumerate(layout_nodes):
            node_id = str(node.get("id") or "")
            kind = str(node.get("kind") or "")
            first_seen = int(node_first_seen.get(node_id, 0))
            status = "hidden"
            if round_num >= first_seen:
                status = "new" if round_num == first_seen else "steady"
            attrs = node.get("attributes") or {}
            if kind == "agent" and int(attrs.get("agent_id") or 0) in active_agent_ids:
                status = "active"

            # Bind the node to its REAL per-round state. value travels in the frame
            # (so the frontend can size radius / color from physics), delta is the
            # drift vs the previous populated round, and state_status comes from real
            # thresholds — the reveal timing above no longer stands in for the state.
            value = current_values.get(node_id)
            prev_value = previous_values.get(node_id)
            delta: Optional[float] = None
            if value is not None and prev_value is not None:
                delta = round(value - prev_value, 4)
            state_status = self._state_status_from_value(kind=kind, value=value, delta=delta)

            node_state: Dict[str, Any] = {
                "id": node_id,
                "status": status,
                "first_seen_round": first_seen,
                "last_active_round": round_num if status == "active" else max(0, round_num - 1),
                "delay_ms": 80 * index if round_num == 0 else 30 * (index % 12),
                # Additive real-state fields (do not remove keys the frontend reads).
                "value": round(value, 4) if value is not None else None,
                "delta": delta,
                "state_status": state_status,
            }
            node_states.append(node_state)

        edge_states: List[Dict[str, Any]] = []
        for index, edge in enumerate(layout_edges):
            edge_id = str(edge.get("id") or "")
            first_seen = int(edge_first_seen.get(edge_id, 0))
            last_active = int(edge_last_active.get(edge_id, 0))
            status = "hidden"
            if round_num >= first_seen:
                status = "new" if round_num == first_seen else "steady"
            if last_active and round_num <= last_active:
                status = "active" if round_num >= first_seen else status
            elif last_active and round_num > last_active:
                status = "faded"
            edge_states.append(
                {
                    "id": edge_id,
                    "status": status,
                    "first_seen_round": first_seen,
                    "last_active_round": last_active,
                    "delay_ms": 45 * index if round_num == 0 else 20 * (index % 16),
                }
            )

        metrics = self._frame_metrics(snapshot, interactions, risk_events)
        narrative = self._frame_narrative(round_num, snapshot, interactions, risk_events)
        latest_reasoning = reasoning[-1] if reasoning else ((snapshot or {}).get("reasoning") or {})
        focus_ids = {
            "node_ids": [item["id"] for item in node_states if item["status"] in {"new", "active"}][:18],
            "edge_ids": [item["id"] for item in edge_states if item["status"] in {"new", "active"}][:24],
        }

        return {
            "round": round_num,
            "timestamp": timestamp,
            "narrative": narrative,
            "metrics": metrics,
            "focus_ids": focus_ids,
            "node_states": node_states,
            "edge_states": edge_states,
            "map_layers": {
                "center": map_projection.get("center") or {},
                "base_layer_count": len(list(map_projection.get("layers") or [])),
            },
            "risk_events": list(risk_events or []),
            "reasoning": latest_reasoning,
            "activated_mechanisms": list(latest_reasoning.get("activated_mechanisms") or []) if isinstance(latest_reasoning, dict) else [],
        }

    def _frame_metrics(
        self,
        snapshot: Optional[Dict[str, Any]],
        interactions: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        agents = list((snapshot or {}).get("agents") or [])
        regions = list((snapshot or {}).get("regions") or [])
        avg_vulnerability = 0.0
        if regions:
            avg_vulnerability = round(
                sum(float(item.get("vulnerability_score") or 0) for item in regions) / len(regions),
                2,
            )
        return {
            "region_count": len(regions),
            "agent_count": len(agents),
            "interaction_count": len(interactions),
            "risk_event_count": len(risk_events),
            "avg_vulnerability_score": avg_vulnerability,
        }

    def _frame_narrative(
        self,
        round_num: int,
        snapshot: Optional[Dict[str, Any]],
        interactions: List[Dict[str, Any]],
        risk_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        regions = list((snapshot or {}).get("regions") or [])
        top_region = None
        if regions:
            top_region = max(regions, key=lambda item: float(item.get("vulnerability_score") or 0))
        top_region_name = (
            top_region.get("name")
            or top_region.get("region_id")
            if isinstance(top_region, dict)
            else "武汉核心区域"
        )
        risk_label = ""
        if risk_events:
            latest_risk = risk_events[-1]
            risk_label = latest_risk.get("title") or latest_risk.get("event_type") or ""
        return {
            "title": f"第 {round_num} 轮态势" if round_num > 0 else "基线建图",
            "summary": (
                f"{top_region_name} 的脆弱性与关注度持续抬升。"
                if round_num > 0
                else "先展示武汉基础区块、交通骨架和关键锚点。"
            ),
            "interaction_summary": interactions[0].get("summary") if interactions else "",
            "risk_summary": risk_label,
        }

    def _round_timestamp(self, reference_time: str, minutes_per_round: int, round_num: int) -> str:
        if not reference_time:
            return ""
        try:
            base = datetime.fromisoformat(reference_time.replace("Z", "+00:00"))
        except Exception:
            return reference_time
        ts = base + timedelta(minutes=minutes_per_round * round_num)
        return ts.isoformat()

    def _group_by_round(self, records: List[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
        grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for item in records:
            if not isinstance(item, dict):
                continue
            round_num = int(item.get("round") or item.get("round_num") or item.get("created_round") or 0)
            grouped[round_num].append(item)
        return grouped

    def _read_json(self, name: str, default: Any) -> Any:
        path = os.path.join(self.sim_dir, name)
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return default

    def _read_jsonl(self, name: str) -> List[Dict[str, Any]]:
        path = os.path.join(self.sim_dir, name)
        if not os.path.exists(path):
            return []
        records: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
        return records

    def _node_kind(self, node_id: str, labels: List[str]) -> str:
        lowered = {str(item).lower() for item in labels}
        if node_id.startswith("region::") or "region" in lowered:
            return "region"
        if node_id.startswith("subregion::") or "subregion" in lowered:
            return "subregion"
        if node_id.startswith("agent::"):
            return "agent"
        return "entity"

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None
