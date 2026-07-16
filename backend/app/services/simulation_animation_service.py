"""
Unified animation payload builder for live/frozen simulations.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..utils.logger import get_logger
from .simulation_manager import SimulationManager
from .simulation_map_projection import SimulationMapProjectionBuilder
from .simulation_realtime_graph import SimulationRealtimeGraphBuilder

logger = get_logger("envfish.animation")


TIMELINE_CONTRACT_VERSION = "simulation-playback-timeline.v3"
PREVIOUS_TIMELINE_CONTRACT_VERSION = "simulation-playback-timeline.v2"
ANIMATION_CONTRACT_VERSION = "simulation-animation.v2"
EDGE_REFERENCE_CONTRACT_VERSION = "split-path-related.v1"

# V3 owns one canonical story clock across every committed round.  The fixed
# minimum keeps a committed round segment stable when later rounds are appended;
# events may extend a segment when their causal chain needs more room.
_TIMELINE_ROUND_MIN_DURATION_MS = 5000
_TIMELINE_EMPTY_ROUND_DURATION_MS = 900

_PRIMARY_TIMELINE_LEDGERS = (
    "spread_event_ledger.jsonl",
    "dynamic_edge_ledger.jsonl",
    "agent_interaction_ledger.jsonl",
    "relationship_event_ledger.jsonl",
)

_TIMELINE_PHASE_ORDER = {
    "environment_diffusion": 10,
    "agent_response": 20,
    "relationship_change": 30,
    "risk_change": 40,
    "legacy_playback": 90,
}

_TIMELINE_PHASE_TIMING = {
    "environment_diffusion": (0, 1000),
    "agent_response": (1300, 1000),
    "relationship_change": (2600, 1100),
    "risk_change": (4000, 700),
    "legacy_playback": (0, 4500),
}

_TIMELINE_KIND_ORDER = {
    "spread_applied": 10,
    "agent_interaction": 20,
    "dynamic_edge_created": 30,
    "dynamic_edge_reawakened": 31,
    "dynamic_edge_activated": 32,
    "dynamic_edge_promoted": 33,
    "dynamic_edge_updated": 34,
    "dynamic_edge_coupled": 35,
    "relationship_event": 40,
    "dynamic_edge_cooling": 50,
    "dynamic_edge_dormant": 51,
    "dynamic_edge_expired": 52,
    "risk_transition": 60,
    "legacy_frame": 90,
}

_DYNAMIC_EVENT_DISPLAY = {
    "created": ("动态关系建立", "源主体与目标主体之间建立了新的动态关系。"),
    "reawakened": ("动态关系重新激活", "休眠关系获得新的运行证据并重新激活。"),
    "activated": ("动态关系激活", "既有动态关系在本轮被实际调用。"),
    "promoted": ("动态关系升级", "动态关系满足持续性条件并完成升级。"),
    "updated": ("动态关系更新", "动态关系依据本轮运行证据完成更新。"),
    "coupled": ("关系耦合传递", "源区域状态通过动态关系传递至目标区域。"),
    "cooling": ("动态关系进入冷却", "动态关系活跃度下降并进入冷却阶段。"),
    "dormant": ("动态关系转为休眠", "动态关系因时效或证据衰减转为休眠。"),
    "expired": ("动态关系失效", "动态关系已超过有效期，不再参与当前传播。"),
}

_RELATIONSHIP_EVENT_DISPLAY = {
    "information_disclosure": ("信息披露影响关系", "主体间的信息披露改变了当前关系状态。"),
    "cooperation": ("协作关系响应", "主体协作行为更新了关系状态。"),
    "request": ("支持请求进入关系网", "主体请求通过既有关系向目标传递。"),
    "resource_coordination": ("资源协调影响关系", "资源协调行为更新了主体间关系。"),
    "constraint_enforcement": ("约束措施影响关系", "约束措施改变了主体间的运行关系。"),
    "challenge": ("质询行为影响关系", "质询行为改变了关系张力与信任状态。"),
    "relationship_activated": ("关系进入活跃状态", "关系获得运行证据并进入活跃状态。"),
    "relationship_promoted": ("关系完成升级", "关系满足持续性条件并完成升级。"),
    "relationship_interrupted": ("关系暂时中断", "关系因时效或证据衰减转为休眠。"),
    "relationship_updated": ("关系状态更新", "关系依据本轮运行事件完成更新。"),
    "interaction": ("主体关系发生互动", "主体互动更新了当前关系状态。"),
}


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

    def get_animation(
        self,
        after_cursor: Optional[int] = None,
        after_round: Optional[int] = None,
        timeline_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self._load_existing_animation()
        if existing:
            payload = self._normalize_animation_payload(existing)
        else:
            payload = self._normalize_animation_payload(self._build_animation_payload())
        if after_cursor is None and after_round is None and timeline_id is None:
            return payload
        return self._filter_timeline_after_cursor(
            payload,
            after_cursor=after_cursor,
            after_round=after_round,
            timeline_id=timeline_id,
        )

    def _filter_timeline_after_cursor(
        self,
        payload: Dict[str, Any],
        after_cursor: Optional[int],
        after_round: Optional[int] = None,
        timeline_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        safe_cursor = (
            max(0, self._safe_int(after_cursor))
            if after_cursor is not None
            else None
        )
        safe_round = (
            max(0, self._safe_int(after_round))
            if after_round is not None
            else None
        )
        timeline = dict(payload.get("timeline") or {})
        current_timeline_id = str(timeline.get("timeline_id") or "")
        requested_timeline_id = str(timeline_id or "").strip() or None
        head = dict(timeline.get("head") or {})
        head_cursor = int(head.get("cursor") or timeline.get("cursor") or 0)
        head_round = int(
            head.get("checkpoint_round")
            or head.get("round")
            or timeline.get("latest_round")
            or 0
        )
        head_global_ms = int(
            head.get("global_end_ms")
            or (timeline.get("clock") or {}).get("committed_end_ms")
            or 0
        )
        reset_reason = ""
        if requested_timeline_id and requested_timeline_id != current_timeline_id:
            reset_reason = "timeline_changed"
        elif safe_cursor is not None and safe_cursor > head_cursor:
            reset_reason = "cursor_ahead_of_head"
        elif safe_round is not None and safe_round > head_round:
            reset_reason = "round_ahead_of_head"

        if reset_reason:
            timeline["events"] = []
            timeline["rounds"] = []
            timeline["window"] = {
                "mode": "reset",
                "timeline_id": current_timeline_id,
                "epoch_id": str(timeline.get("epoch_id") or ""),
                "requested_timeline_id": requested_timeline_id,
                "after_cursor": safe_cursor,
                "after_round": safe_round,
                "ack_cursor": safe_cursor,
                "next_cursor": head_cursor,
                "head_cursor": head_cursor,
                "head_round": head_round,
                "head_global_ms": head_global_ms,
                "returned_count": 0,
                "returned_frame_count": 0,
                "returned_round_count": 0,
                "has_more": False,
                "reset_required": True,
                "reset_reason": reset_reason,
                "frames_included": False,
                "layout_included": False,
            }
            return {
                "meta": dict(payload.get("meta") or {}),
                "timeline": timeline,
            }

        events = [
            dict(item)
            for item in list(timeline.get("events") or [])
            if isinstance(item, dict)
            and (
                (
                    safe_cursor is not None
                    and int(item.get("sequence") or 0) > safe_cursor
                )
                or (
                    safe_cursor is None
                    and safe_round is not None
                    and int(item.get("round") or 0) > safe_round
                )
            )
        ]
        frames = [
            dict(frame)
            for frame in list(payload.get("frames") or [])
            if isinstance(frame, dict)
            and safe_round is not None
            and int(frame.get("round") or 0) > safe_round
        ]
        round_segments = [
            dict(segment)
            for segment in list(timeline.get("rounds") or [])
            if isinstance(segment, dict)
            and (
                (
                    safe_cursor is not None
                    and int(segment.get("end_cursor") or 0) > safe_cursor
                )
                or (
                    safe_round is not None
                    and int(segment.get("round") or 0) > safe_round
                )
            )
        ]
        timeline["events"] = events
        timeline["rounds"] = round_segments
        next_cursor = (
            int(events[-1].get("sequence") or 0)
            if events
            else min(safe_cursor, head_cursor)
            if safe_cursor is not None
            else head_cursor
        )
        returned_start_ms = min(
            [
                int((event.get("timing") or {}).get("global_start_ms") or 0)
                for event in events
            ]
            + [int(segment.get("start_ms") or 0) for segment in round_segments],
            default=head_global_ms,
        )
        returned_end_ms = max(
            [
                int((event.get("timing") or {}).get("global_end_ms") or 0)
                for event in events
            ]
            + [int(segment.get("end_ms") or 0) for segment in round_segments],
            default=head_global_ms,
        )
        timeline["window"] = {
            "mode": "delta",
            "timeline_id": current_timeline_id,
            "epoch_id": str(timeline.get("epoch_id") or ""),
            "requested_timeline_id": requested_timeline_id,
            "after_cursor": safe_cursor,
            "after_round": safe_round,
            "ack_cursor": safe_cursor,
            "next_cursor": next_cursor,
            "head_cursor": head_cursor,
            "head_round": head_round,
            "head_global_ms": head_global_ms,
            "returned_count": len(events),
            "returned_frame_count": len(frames),
            "returned_round_count": len(round_segments),
            "returned_start_ms": returned_start_ms,
            "returned_end_ms": returned_end_ms,
            "has_more": False,
            "reset_required": False,
            "reset_reason": "",
            "frames_included": bool(frames),
            "layout_included": bool(events or frames),
        }
        # Cursor reads are an incremental transport contract.  Re-sending every
        # historical frame on each poll made frozen/demo runs needlessly large
        # (and the current client already merges a cursor response into the
        # initial full payload).  Keep a fresh layout only when new events exist
        # so newly materialized nodes/edges can still be resolved by renderers.
        window_payload: Dict[str, Any] = {
            "meta": dict(payload.get("meta") or {}),
            "timeline": timeline,
        }
        if frames:
            window_payload["frames"] = frames
        if events or frames:
            window_payload["layout"] = dict(payload.get("layout") or {})
        return window_payload

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
        spread_events = self._read_jsonl("spread_event_ledger.jsonl")
        dynamic_edges = self._read_jsonl("dynamic_edge_ledger.jsonl")
        interactions = self._read_jsonl("agent_interaction_ledger.jsonl")
        relationship_events = self._read_jsonl("relationship_event_ledger.jsonl")
        risk_events = self._read_jsonl("risk_events.jsonl")
        round_reasoning = self._read_jsonl("round_reasoning_ledger.jsonl")
        snapshot_by_round = {
            int(item.get("round") or item.get("round_num") or 0): item
            for item in round_snapshots
            if isinstance(item, dict)
        }
        completed_rounds = set(snapshot_by_round)
        committed_dynamic_edges = self._records_for_completed_rounds(
            dynamic_edges,
            completed_rounds,
        )
        committed_interactions = self._records_for_completed_rounds(
            interactions,
            completed_rounds,
        )
        committed_risk_events = self._records_for_completed_rounds(
            risk_events,
            completed_rounds,
        )
        committed_reasoning = self._records_for_completed_rounds(
            round_reasoning,
            completed_rounds,
        )

        realtime_graph = SimulationRealtimeGraphBuilder(self.sim_dir).build()
        map_projection = SimulationMapProjectionBuilder(
            sim_dir=self.sim_dir,
            simulation_id=self.simulation_id,
            map_seed_id=self.state.map_seed_id if self.state.map_seed_id else None,
            source_mode=self.state.source_mode,
        ).build(realtime_graph, key_edges_only=False)

        layout_nodes = self._build_layout_nodes(realtime_graph, map_projection)
        layout_edges = self._build_layout_edges(realtime_graph)
        allow_legacy_fallback = bool(
            getattr(self.state, "is_replay_only", False)
            or str(getattr(self.state, "artifact_mode", "live") or "live") == "frozen"
        )
        all_dynamic_ids = {
            str(record.get("edge_id") or record.get("relationship_contract_id") or "")
            for record in dynamic_edges
            if isinstance(record, dict)
        }
        committed_dynamic_ids = {
            str(record.get("edge_id") or record.get("relationship_contract_id") or "")
            for record in committed_dynamic_edges
            if isinstance(record, dict)
        }
        layout_edges = [
            edge
            for edge in layout_edges
            if str(edge.get("fact_type") or "") != "dynamic_edge"
            or str(edge.get("id") or "") not in all_dynamic_ids
            or str(edge.get("id") or "") in committed_dynamic_ids
        ]
        is_live_artifact = not allow_legacy_fallback
        if is_live_artifact:
            layout_nodes, layout_edges = self._filter_layout_to_completed_rounds(
                layout_nodes,
                layout_edges,
                round_snapshots=round_snapshots,
                completed_rounds=completed_rounds,
            )
        layout_edges = self._merge_historical_dynamic_edges(
            layout_nodes,
            layout_edges,
            committed_dynamic_edges,
        )
        timeline = self._build_timeline(
            spread_events=spread_events,
            dynamic_edge_events=dynamic_edges,
            agent_interactions=interactions,
            relationship_events=relationship_events,
            risk_events=risk_events,
            frames=[],
            layout_nodes=layout_nodes,
            layout_edges=layout_edges,
            completed_rounds=completed_rounds,
            allow_legacy_fallback=allow_legacy_fallback,
        )
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
        edge_first_seen = self._compute_edge_first_seen(layout_edges, committed_dynamic_edges)
        edge_last_active = self._compute_edge_last_active(committed_dynamic_edges)
        active_nodes_by_round, active_edges_by_round = self._timeline_activity_by_round(timeline)
        use_timeline_activity = timeline.get("source_mode") == "observed_ledgers"
        interactions_by_round = self._group_by_round(committed_interactions)
        risks_by_round = self._group_by_round(committed_risk_events)
        reasoning_by_round = self._group_by_round(committed_reasoning)
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
                active_node_ids=active_nodes_by_round.get(0, set()) if use_timeline_activity else None,
                active_edge_ids=active_edges_by_round.get(0, set()) if use_timeline_activity else None,
            )
        ]

        frame_rounds = (
            range(1, total_rounds + 1)
            if allow_legacy_fallback
            else sorted(round_num for round_num in completed_rounds if round_num > 0)
        )
        for round_num in frame_rounds:
            snapshot = snapshot_by_round.get(round_num)
            if allow_legacy_fallback and not snapshot and round_num == total_rounds:
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
                    active_node_ids=active_nodes_by_round.get(round_num, set()) if use_timeline_activity else None,
                    active_edge_ids=active_edges_by_round.get(round_num, set()) if use_timeline_activity else None,
                )
            )

        if allow_legacy_fallback and timeline.get("source_mode") != "observed_ledgers":
            timeline = self._build_timeline(
                spread_events=spread_events,
                dynamic_edge_events=dynamic_edges,
                agent_interactions=interactions,
                relationship_events=relationship_events,
                risk_events=risk_events,
                frames=[
                    frame
                    for frame in frames
                    if int(frame.get("round") or 0) == 0
                    or int(frame.get("round") or 0) in completed_rounds
                ],
                layout_nodes=layout_nodes,
                layout_edges=layout_edges,
                completed_rounds=completed_rounds,
                allow_legacy_fallback=True,
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
                "animation_contract_version": ANIMATION_CONTRACT_VERSION,
                "timeline_contract_version": TIMELINE_CONTRACT_VERSION,
            },
            "layout": {
                "simulation_id": self.simulation_id,
                "source_mode": map_projection.get("source_mode") or self.state.source_mode or "graph",
                "map_seed_id": map_projection.get("map_seed_id"),
                "geographic_grounding": map_projection.get("geographic_grounding") or "",
                "data_quality": dict(map_projection.get("data_quality") or {}),
                "selection_summary": dict(map_projection.get("selection_summary") or {}),
                "meta": dict(map_projection.get("meta") or {}),
                "center": map_projection.get("center") or {},
                "zoom_hint": map_projection.get("zoom_hint") or 10,
                "radius_m": map_projection.get("radius_m") or 0,
                "analysis_polygon": map_projection.get("analysis_polygon"),
                "base_layers": list(map_projection.get("layers") or []),
                "nodes": layout_nodes,
                "edges": layout_edges,
            },
            "frames": frames,
            "timeline": timeline,
        }

    def _normalize_animation_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return payload

        meta = dict(payload.get("meta") or {})
        layout = dict(payload.get("layout") or {})
        frames = list(payload.get("frames") or [])
        is_live_artifact = self._is_live_artifact()
        round_snapshots = (
            self._read_jsonl("round_state_matrix.jsonl")
            if getattr(self, "sim_dir", None)
            else []
        )
        completed_rounds = {
            int(item.get("round") or item.get("round_num") or 0)
            for item in round_snapshots
            if isinstance(item, dict)
        }
        if is_live_artifact:
            frames = [
                frame
                for frame in frames
                if isinstance(frame, dict)
                and (
                    int(frame.get("round") or 0) == 0
                    or int(frame.get("round") or 0) in completed_rounds
                )
            ]

        meta["default_speed_ms"] = int(meta.get("default_speed_ms") or 1800)
        meta["speed_options_ms"] = list(meta.get("speed_options_ms") or [1000, 1800, 2600])
        meta["animation_contract_version"] = ANIMATION_CONTRACT_VERSION
        meta["timeline_contract_version"] = TIMELINE_CONTRACT_VERSION

        layout_nodes = list(layout.get("nodes") or [])
        layout_edges = list(layout.get("edges") or [])
        historical_dynamic_edges = (
            self._read_jsonl("dynamic_edge_ledger.jsonl")
            if getattr(self, "sim_dir", None)
            else []
        )
        existing_timeline = payload.get("timeline")
        if is_live_artifact and self._is_timeline_payload(existing_timeline):
            existing_timeline = self._filter_timeline_to_completed_rounds(
                dict(existing_timeline),
                completed_rounds,
            )
        if self._is_timeline_payload(existing_timeline):
            existing_timeline = self._normalize_timeline_edge_references(
                dict(existing_timeline)
            )
            committed_timeline_edge_ids = {
                str(edge_id)
                for event in list((existing_timeline or {}).get("events") or [])
                if isinstance(event, dict)
                for edge_id in list(event.get("edge_ids") or [])
                if edge_id not in (None, "")
            }
            all_historical_dynamic_ids = {
                str(
                    record.get("edge_id")
                    or record.get("relationship_contract_id")
                    or ""
                )
                for record in historical_dynamic_edges
                if isinstance(record, dict)
            }
            layout_edges = [
                edge
                for edge in layout_edges
                if str(edge.get("fact_type") or "") != "dynamic_edge"
                or str(edge.get("id") or "") not in all_historical_dynamic_ids
                or str(edge.get("id") or "") in committed_timeline_edge_ids
            ]
            historical_dynamic_edges = [
                record
                for record in historical_dynamic_edges
                if str(
                    record.get("edge_id")
                    or record.get("relationship_contract_id")
                    or ""
                )
                in committed_timeline_edge_ids
            ]
        layout_edges = self._merge_historical_dynamic_edges(
            layout_nodes,
            layout_edges,
            historical_dynamic_edges,
        )
        if is_live_artifact:
            layout_nodes, layout_edges = self._filter_layout_to_completed_rounds(
                layout_nodes,
                layout_edges,
                round_snapshots=round_snapshots,
                completed_rounds=completed_rounds,
            )
        layout["nodes"] = layout_nodes
        layout["edges"] = layout_edges
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

        timeline = existing_timeline
        if not self._is_timeline_payload(timeline):
            sources = self._read_timeline_sources()
            timeline = self._build_timeline(
                spread_events=sources["spread_event_ledger.jsonl"],
                dynamic_edge_events=sources["dynamic_edge_ledger.jsonl"],
                agent_interactions=sources["agent_interaction_ledger.jsonl"],
                relationship_events=sources["relationship_event_ledger.jsonl"],
                risk_events=sources["risk_events.jsonl"],
                frames=normalized_frames,
                layout_nodes=layout_nodes,
                layout_edges=layout_edges,
                completed_rounds=completed_rounds if is_live_artifact else None,
                allow_legacy_fallback=not is_live_artifact,
            )
        else:
            timeline = self._normalize_timeline_edge_references(
                dict(timeline),
                references=self._build_timeline_reference_index(
                    layout_nodes,
                    layout_edges,
                ),
            )

        timeline_rounds = {
            int(frame.get("round") or 0)
            for frame in normalized_frames
            if isinstance(frame, dict)
        }
        timeline_rounds.update(
            int(segment.get("round") or 0)
            for segment in list((timeline or {}).get("rounds") or [])
            if isinstance(segment, dict)
        )
        if is_live_artifact and completed_rounds:
            timeline_rounds.update(completed_rounds)
            timeline_rounds.add(0)
        timeline = self._compose_global_timeline(
            dict(timeline),
            round_numbers=timeline_rounds,
        )

        event_ids_by_round: Dict[int, List[str]] = defaultdict(list)
        for event in list(timeline.get("events") or []):
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("id") or "")
            if event_id:
                event_ids_by_round[int(event.get("round") or 0)].append(event_id)
        normalized_frames = [
            {
                **frame,
                "timeline_event_ids": list(event_ids_by_round.get(int(frame.get("round") or 0), [])),
            }
            for frame in normalized_frames
        ]

        return {
            **payload,
            "meta": meta,
            "layout": layout,
            "frames": normalized_frames,
            "timeline": timeline,
        }

    def _is_timeline_payload(self, timeline: Any) -> bool:
        return bool(
            isinstance(timeline, dict)
            and timeline.get("contract_version")
            in {TIMELINE_CONTRACT_VERSION, PREVIOUS_TIMELINE_CONTRACT_VERSION}
            and isinstance(timeline.get("events"), list)
        )

    def _normalize_timeline_edge_references(
        self,
        timeline: Dict[str, Any],
        references: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Upgrade older V2 events to typed edge references without inventing paths.

        A single legacy edge remains compatible because it cannot imply a false
        next hop. Multiple untyped ``edge_ids`` are evidence references, never
        an ordered route. In particular, relationship ``mechanism_edge_ids``
        must not be animated as consecutive geographic or topological hops.
        """

        normalized_events: List[Dict[str, Any]] = []
        for raw_event in list(timeline.get("events") or []):
            if not isinstance(raw_event, dict):
                continue
            event = dict(raw_event)
            has_split_contract = (
                "path_edge_ids" in event or "related_edge_ids" in event
            )
            legacy_edge_ids = self._unique_strings(
                [event.get("edge_id"), *list(event.get("edge_ids") or [])]
            )
            if has_split_contract:
                path_edge_ids = self._unique_strings(event.get("path_edge_ids") or [])
                related_edge_ids = self._unique_strings(
                    event.get("related_edge_ids") or []
                )
            elif len(legacy_edge_ids) == 1 or bool(
                event.get("edge_ids_are_ordered_path")
            ):
                path_edge_ids = legacy_edge_ids
                related_edge_ids = []
            else:
                path_edge_ids = []
                related_edge_ids = legacy_edge_ids

            path_edge_id_set = set(path_edge_ids)
            related_edge_ids = [
                edge_id
                for edge_id in related_edge_ids
                if edge_id not in path_edge_id_set
            ]
            grounding = event.get("grounding")
            if path_edge_ids and references is not None:
                source = event.get("source") or {}
                target = event.get("target") or {}
                source_node = str(next(iter(source.get("node_ids") or []), ""))
                target_node = str(next(iter(target.get("node_ids") or []), ""))
                if not self._edge_path_is_continuous(
                    path_edge_ids,
                    references,
                    source_node,
                    target_node,
                ):
                    related_edge_ids = self._unique_strings(
                        [*related_edge_ids, *path_edge_ids]
                    )
                    path_edge_ids = []
                    grounding = {
                        **(grounding if isinstance(grounding, dict) else {}),
                        "reference_quality": "unresolved",
                    }
            normalized_events.append(
                {
                    **event,
                    **({"grounding": grounding} if grounding is not None else {}),
                    "edge_reference_contract": EDGE_REFERENCE_CONTRACT_VERSION,
                    "path_edge_ids": path_edge_ids,
                    "related_edge_ids": related_edge_ids,
                    "edge_ids": self._unique_strings(
                        [*path_edge_ids, *related_edge_ids]
                    ),
                }
            )
        return {
            **timeline,
            "edge_reference_contract": EDGE_REFERENCE_CONTRACT_VERSION,
            "events": normalized_events,
        }

    def _is_live_artifact(self) -> bool:
        state = getattr(self, "state", None)
        if state is None:
            # Deterministic fixture projectors intentionally instantiate this
            # service without SimulationManager state; preserve their full replay.
            return False
        return not bool(getattr(state, "is_replay_only", False)) and str(
            getattr(state, "artifact_mode", "live") or "live"
        ) != "frozen"

    def _filter_timeline_to_completed_rounds(
        self,
        timeline: Dict[str, Any],
        completed_rounds: Iterable[int],
    ) -> Dict[str, Any]:
        committed = {int(round_num) for round_num in completed_rounds}
        events = [
            dict(event)
            for event in list(timeline.get("events") or [])
            if isinstance(event, dict)
            and (
                int(event.get("round") or 0) == 0
                or int(event.get("round") or 0) in committed
            )
        ]
        fallback_count = sum(
            1
            for event in events
            if bool((event.get("grounding") or {}).get("fallback"))
        )
        rounds = [
            dict(segment)
            for segment in list(timeline.get("rounds") or [])
            if isinstance(segment, dict)
            and (
                int(segment.get("round") or 0) == 0
                or int(segment.get("round") or 0) in committed
            )
        ]
        return {
            **timeline,
            "cursor": max(
                (self._safe_int(event.get("sequence")) for event in events),
                default=0,
            ),
            "event_count": len(events),
            "observed_event_count": len(events) - fallback_count,
            "fallback_event_count": fallback_count,
            "latest_round": max(committed, default=0),
            "rounds": rounds,
            "events": events,
        }

    def _read_timeline_sources(self) -> Dict[str, List[Dict[str, Any]]]:
        names = (*_PRIMARY_TIMELINE_LEDGERS, "risk_events.jsonl")
        if not getattr(self, "sim_dir", None):
            return {name: [] for name in names}
        return {name: self._read_jsonl(name) for name in names}

    def _build_timeline(
        self,
        *,
        spread_events: Sequence[Dict[str, Any]],
        dynamic_edge_events: Sequence[Dict[str, Any]],
        agent_interactions: Sequence[Dict[str, Any]],
        relationship_events: Sequence[Dict[str, Any]],
        risk_events: Sequence[Dict[str, Any]],
        frames: Sequence[Dict[str, Any]],
        layout_nodes: Sequence[Dict[str, Any]],
        layout_edges: Sequence[Dict[str, Any]],
        completed_rounds: Optional[Iterable[int]] = None,
        allow_legacy_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Project append-only runtime ledgers into one deterministic playback timeline.

        The timeline is additive: legacy ``frames`` remain unchanged for existing
        clients.  Ledger records are authoritative.  Frame-derived events are used
        only when a run has no primary runtime ledger, and every such event is
        explicitly marked as a legacy fallback.
        """

        source_records = {
            "spread_event_ledger.jsonl": list(spread_events or []),
            "dynamic_edge_ledger.jsonl": list(dynamic_edge_events or []),
            "agent_interaction_ledger.jsonl": list(agent_interactions or []),
            "relationship_event_ledger.jsonl": list(relationship_events or []),
            "risk_events.jsonl": list(risk_events or []),
        }
        allowed_rounds = (
            {int(item) for item in completed_rounds}
            if completed_rounds is not None
            else None
        )

        def eligible(record: Dict[str, Any]) -> bool:
            if allowed_rounds is None:
                return True
            round_num = self._event_round(record)
            return round_num == 0 or round_num in allowed_rounds

        references = self._build_timeline_reference_index(layout_nodes, layout_edges)
        events: List[Dict[str, Any]] = []

        for index, record in enumerate(source_records["spread_event_ledger.jsonl"]):
            if isinstance(record, dict) and eligible(record):
                events.append(self._project_spread_event(record, index, references))
        for index, record in enumerate(source_records["agent_interaction_ledger.jsonl"]):
            if isinstance(record, dict) and eligible(record):
                events.append(self._project_agent_interaction(record, index, references))
        for index, record in enumerate(source_records["dynamic_edge_ledger.jsonl"]):
            if isinstance(record, dict) and eligible(record):
                events.append(self._project_dynamic_edge_event(record, index, references))
        for index, record in enumerate(source_records["relationship_event_ledger.jsonl"]):
            if isinstance(record, dict) and eligible(record):
                events.append(self._project_relationship_event(record, index, references))

        primary_event_count = len(events)
        primary_record_count = sum(
            len(source_records[name]) for name in _PRIMARY_TIMELINE_LEDGERS
        )
        for index, record in enumerate(source_records["risk_events.jsonl"]):
            if isinstance(record, dict) and eligible(record):
                events.append(self._project_risk_event(record, index, references))

        observed_event_count = len(events)
        fallback_event_count = 0
        if allow_legacy_fallback and primary_event_count == 0 and primary_record_count == 0:
            observed_rounds = {int(item.get("round") or 0) for item in events}
            for index, frame in enumerate(frames or []):
                if not isinstance(frame, dict):
                    continue
                round_num = int(frame.get("round") or 0)
                if round_num in observed_rounds:
                    continue
                events.append(self._project_legacy_frame(frame, index))
                fallback_event_count += 1

        finalized = self._finalize_timeline_events(events)
        if primary_event_count > 0:
            source_mode = "observed_ledgers"
            grounding_mode = "observed"
        elif primary_record_count > 0:
            source_mode = "awaiting_completed_round"
            grounding_mode = "observed_pending"
        elif observed_event_count > 0 and fallback_event_count > 0:
            source_mode = "mixed_legacy_fallback"
            grounding_mode = "mixed"
        elif observed_event_count > 0:
            source_mode = "observed_supplemental_ledger"
            grounding_mode = "observed"
        elif allow_legacy_fallback:
            source_mode = "legacy_frame_fallback"
            grounding_mode = "legacy_fallback"
        else:
            source_mode = "awaiting_runtime_ledgers"
            grounding_mode = "observed_pending"

        source_counts = {name: len(records) for name, records in source_records.items()}
        missing_ledgers = [name for name in _PRIMARY_TIMELINE_LEDGERS if source_counts.get(name, 0) == 0]
        committed_round_numbers = {
            int(frame.get("round") or 0)
            for frame in frames or []
            if isinstance(frame, dict)
        }
        if allowed_rounds is not None:
            committed_round_numbers.update(allowed_rounds)
            committed_round_numbers.add(0)
        return self._compose_global_timeline(
            {
                "contract_version": TIMELINE_CONTRACT_VERSION,
                "edge_reference_contract": EDGE_REFERENCE_CONTRACT_VERSION,
                "source_mode": source_mode,
                "grounding": {
                    "mode": grounding_mode,
                    "missing_ledgers": missing_ledgers,
                    "fallback_used": fallback_event_count > 0,
                },
                "source_counts": source_counts,
                "generated_from": [name for name, count in source_counts.items() if count > 0],
                "event_count": len(finalized),
                "observed_event_count": observed_event_count,
                "fallback_event_count": fallback_event_count,
                "events": finalized,
            },
            round_numbers=committed_round_numbers,
        )

    def _compose_global_timeline(
        self,
        timeline: Dict[str, Any],
        *,
        round_numbers: Optional[Iterable[int]] = None,
    ) -> Dict[str, Any]:
        """Add the V3 canonical clock without removing V2 event fields.

        ``timing.start_ms`` remains the V2 round-local offset.  V3 adds an
        explicit local alias plus absolute global bounds.  Completed rounds are
        represented as immutable segments, including rounds with no event, so a
        live client can advance its round checkpoint independently of the event
        cursor.

        This projector is append-stable when newly committed data belongs to a
        later round: previous event ids, sequences, local timing, global timing,
        and round segments remain byte-for-byte unchanged.  Preventing a late
        write into an already committed round still requires a persisted runtime
        commit index; this read-side projector intentionally does not fabricate
        such a commit boundary.
        """

        raw_events = [
            dict(event)
            for event in list(timeline.get("events") or [])
            if isinstance(event, dict)
        ]
        sequence_values = [
            self._safe_int(event.get("sequence")) for event in raw_events
        ]
        has_stable_sequence = (
            bool(raw_events)
            and all(value > 0 for value in sequence_values)
            and len(set(sequence_values)) == len(sequence_values)
        )
        if has_stable_sequence:
            events = [
                event
                for _, event in sorted(
                    enumerate(raw_events),
                    key=lambda item: (
                        self._safe_int(item[1].get("sequence")),
                        item[0],
                    ),
                )
            ]
        else:
            events = raw_events
            for sequence, event in enumerate(events, start=1):
                event["sequence"] = sequence

        requested_rounds = {
            max(0, self._safe_int(round_num))
            for round_num in (round_numbers or [])
        }
        requested_rounds.update(
            max(0, self._safe_int(event.get("round"))) for event in events
        )
        ordered_rounds = sorted(requested_rounds)
        events_by_round: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for event in events:
            events_by_round[max(0, self._safe_int(event.get("round")))].append(event)

        upgrading_v2 = (
            timeline.get("contract_version") == PREVIOUS_TIMELINE_CONTRACT_VERSION
        )
        phase_counts: Dict[Tuple[int, str], int] = defaultdict(int)
        phase_offsets: Dict[Tuple[int, str], int] = defaultdict(int)
        if upgrading_v2:
            for event in events:
                phase_counts[
                    (
                        max(0, self._safe_int(event.get("round"))),
                        str(event.get("phase") or "legacy_playback"),
                    )
                ] += 1

        epoch_id, timeline_id = self._timeline_identity()
        event_end_by_id: Dict[str, int] = {}
        last_global_start_ms = 0
        committed_cursor = 0
        round_start_ms = 0
        segments: List[Dict[str, Any]] = []

        for round_num in ordered_rounds:
            round_events = sorted(
                events_by_round.get(round_num, []),
                key=lambda event: self._safe_int(event.get("sequence")),
            )
            start_cursor = committed_cursor
            round_event_end_ms = round_start_ms
            for event in round_events:
                timing = dict(event.get("timing") or {})
                if upgrading_v2:
                    phase = str(event.get("phase") or "legacy_playback")
                    phase_key = (round_num, phase)
                    phase_sequence = phase_offsets[phase_key]
                    phase_offsets[phase_key] += 1
                    phase_start, phase_window = _TIMELINE_PHASE_TIMING.get(
                        phase,
                        _TIMELINE_PHASE_TIMING["legacy_playback"],
                    )
                    phase_count = max(1, phase_counts[phase_key])
                    phase_step = min(160, max(1, phase_window // phase_count))
                    global_offset_ms = phase_start + phase_sequence * phase_step
                    # Preserve the V2 round-local field exactly.  Only the new
                    # absolute V3 clock uses the more readable phase placement.
                    local_start_ms = max(
                        0,
                        self._safe_int(
                            timing.get("local_start_ms")
                            if timing.get("local_start_ms") is not None
                            else timing.get("start_ms")
                        ),
                    )
                    duration_ms = self._timeline_event_duration_ms(
                        str(event.get("kind") or "")
                    )
                else:
                    local_start_ms = max(
                        0,
                        self._safe_int(
                            timing.get("local_start_ms")
                            if timing.get("local_start_ms") is not None
                            else timing.get("start_ms")
                        ),
                    )
                    duration_ms = max(
                        1,
                        self._safe_int(timing.get("duration_ms"))
                        or self._timeline_event_duration_ms(
                            str(event.get("kind") or "")
                        ),
                    )
                    global_offset_ms = local_start_ms
                parent_end_ms = max(
                    (
                        event_end_by_id.get(str(parent_id or ""), 0)
                        for parent_id in list(event.get("parent_event_ids") or [])
                    ),
                    default=0,
                )
                global_start_ms = max(
                    round_start_ms + global_offset_ms,
                    parent_end_ms,
                    last_global_start_ms,
                )
                global_end_ms = global_start_ms + duration_ms
                timing.update(
                    {
                        # V2 compatibility: start_ms is intentionally local.
                        "start_ms": local_start_ms,
                        "local_start_ms": local_start_ms,
                        "duration_ms": duration_ms,
                        "global_start_ms": global_start_ms,
                        "global_end_ms": global_end_ms,
                    }
                )
                event["timing"] = timing
                event_id = str(event.get("id") or "")
                if event_id:
                    event_end_by_id[event_id] = global_end_ms
                last_global_start_ms = global_start_ms
                committed_cursor = max(
                    committed_cursor,
                    self._safe_int(event.get("sequence")),
                )
                round_event_end_ms = max(round_event_end_ms, global_end_ms)

            minimum_duration_ms = (
                _TIMELINE_ROUND_MIN_DURATION_MS
                if round_events
                else _TIMELINE_EMPTY_ROUND_DURATION_MS
            )
            round_end_ms = max(
                round_start_ms + minimum_duration_ms,
                round_event_end_ms,
            )
            event_ids = [str(event.get("id") or "") for event in round_events]
            start_sequence = (
                self._safe_int(round_events[0].get("sequence"))
                if round_events
                else start_cursor
            )
            end_sequence = (
                self._safe_int(round_events[-1].get("sequence"))
                if round_events
                else committed_cursor
            )
            epoch_token = epoch_id.rsplit("::", 1)[-1]
            segments.append(
                {
                    "round": round_num,
                    "checkpoint_id": f"checkpoint::{epoch_token}::{round_num}",
                    "event_ids": event_ids,
                    "event_count": len(round_events),
                    # V2 compatibility fields retained on the richer segment.
                    "start_sequence": start_sequence,
                    "end_sequence": end_sequence,
                    "start_cursor": start_cursor,
                    "end_cursor": committed_cursor,
                    "start_ms": round_start_ms,
                    "end_ms": round_end_ms,
                    "duration_ms": round_end_ms - round_start_ms,
                }
            )
            round_start_ms = round_end_ms

        cursor = max(
            (self._safe_int(event.get("sequence")) for event in events),
            default=0,
        )
        latest_round = segments[-1]["round"] if segments else 0
        committed_end_ms = segments[-1]["end_ms"] if segments else 0
        checkpoint_id = segments[-1]["checkpoint_id"] if segments else ""
        fallback_count = sum(
            1
            for event in events
            if bool((event.get("grounding") or {}).get("fallback"))
        )
        return {
            **timeline,
            "contract_version": TIMELINE_CONTRACT_VERSION,
            "compatible_contract_versions": [PREVIOUS_TIMELINE_CONTRACT_VERSION],
            "edge_reference_contract": EDGE_REFERENCE_CONTRACT_VERSION,
            "timeline_id": timeline_id,
            "epoch_id": epoch_id,
            "clock": {
                "unit": "ms",
                "origin_ms": 0,
                "canonical_rate": 1.0,
                "duration_ms": committed_end_ms,
                "committed_end_ms": committed_end_ms,
                "default_round_duration_ms": _TIMELINE_ROUND_MIN_DURATION_MS,
                "empty_round_duration_ms": _TIMELINE_EMPTY_ROUND_DURATION_MS,
            },
            "head": {
                "cursor": cursor,
                "round": latest_round,
                "checkpoint_round": latest_round,
                "checkpoint_id": checkpoint_id,
                "global_end_ms": committed_end_ms,
                "event_count": len(events),
            },
            "cursor": cursor,
            "event_count": len(events),
            "observed_event_count": int(
                timeline.get("observed_event_count")
                if timeline.get("observed_event_count") is not None
                else len(events) - fallback_count
            ),
            "fallback_event_count": int(
                timeline.get("fallback_event_count")
                if timeline.get("fallback_event_count") is not None
                else fallback_count
            ),
            "latest_round": latest_round,
            "rounds": segments,
            "events": events,
        }

    def _timeline_identity(self) -> Tuple[str, str]:
        simulation_id = str(getattr(self, "simulation_id", "") or "unknown")
        state = getattr(self, "state", None)
        created_at = str(getattr(state, "created_at", "") or "")
        epoch_digest = hashlib.sha1(
            json.dumps(
                [simulation_id, created_at],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        epoch_id = f"epoch::{epoch_digest}"
        timeline_digest = hashlib.sha1(
            json.dumps(
                [epoch_id, TIMELINE_CONTRACT_VERSION],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        return epoch_id, f"timeline::{timeline_digest}"

    def _finalize_timeline_events(self, events: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ordered = sorted(
            [dict(item) for item in events if isinstance(item, dict)],
            key=lambda item: (
                int(item.get("round") or 0),
                int(item.get("_phase_order") or 999),
                int(item.get("_kind_order") or 999),
                str((item.get("timing") or {}).get("timestamp") or ""),
                int(item.get("_record_order") or 0),
                str(item.get("id") or ""),
            ),
        )
        alias_to_event_id: Dict[str, str] = {}
        child_alias_to_parent_id: Dict[str, str] = {}
        for event in ordered:
            event_id = str(event.get("id") or "")
            if event_id:
                alias_to_event_id[event_id] = event_id
            for alias in event.get("_aliases") or []:
                alias_text = str(alias or "").strip()
                if alias_text and alias_text not in alias_to_event_id:
                    alias_to_event_id[alias_text] = event_id
            for alias in event.get("_child_aliases") or []:
                alias_text = str(alias or "").strip()
                if alias_text and alias_text not in child_alias_to_parent_id:
                    child_alias_to_parent_id[alias_text] = event_id

        round_offsets: Dict[int, int] = defaultdict(int)
        phase_offsets: Dict[Tuple[int, str], int] = defaultdict(int)
        phase_counts: Dict[Tuple[int, str], int] = defaultdict(int)
        for event in ordered:
            phase_counts[(int(event.get("round") or 0), str(event.get("phase") or ""))] += 1
        finalized: List[Dict[str, Any]] = []
        for sequence, event in enumerate(ordered, start=1):
            round_num = int(event.get("round") or 0)
            round_sequence = round_offsets[round_num]
            round_offsets[round_num] += 1
            phase = str(event.get("phase") or "")
            phase_key = (round_num, phase)
            phase_sequence = phase_offsets[phase_key]
            phase_offsets[phase_key] += 1
            phase_start, phase_window = _TIMELINE_PHASE_TIMING.get(phase, (0, 1800))
            phase_count = max(1, phase_counts[phase_key])
            phase_step = min(160, max(1, phase_window // phase_count))
            parents = []
            for alias in event.get("_parent_aliases") or []:
                resolved = alias_to_event_id.get(str(alias or "").strip())
                if resolved and resolved != event.get("id") and resolved not in parents:
                    parents.append(resolved)
            for alias in event.get("_aliases") or []:
                resolved = child_alias_to_parent_id.get(str(alias or "").strip())
                if resolved and resolved != event.get("id") and resolved not in parents:
                    parents.append(resolved)
            root_alias = str(event.get("_root_alias") or "").strip()
            root_event_id = alias_to_event_id.get(root_alias) if root_alias else None
            timing = dict(event.get("timing") or {})
            timing["start_ms"] = phase_start + phase_sequence * phase_step
            timing["duration_ms"] = self._timeline_event_duration_ms(str(event.get("kind") or ""))
            causal_fields: Dict[str, Any] = {}
            if root_event_id:
                causal_fields["root_event_id"] = root_event_id
                if event.get("_hop") is not None:
                    causal_fields["hop"] = int(event["_hop"])
            finalized.append(
                {
                    key: value
                    for key, value in {
                        **event,
                        "sequence": sequence,
                        "round_sequence": round_sequence,
                        "parent_event_ids": parents,
                        "timing": timing,
                        **causal_fields,
                    }.items()
                    if not key.startswith("_")
                }
            )
        return finalized

    def _timeline_event_duration_ms(self, kind: str) -> int:
        if kind == "spread_applied":
            return 1500
        if kind == "agent_interaction":
            return 1300
        if kind.startswith("dynamic_edge_"):
            return 1300
        if kind == "relationship_event":
            return 1300
        if kind == "risk_transition":
            return 1500
        return 1400

    def _base_timeline_event(
        self,
        *,
        kind: str,
        phase: str,
        record: Dict[str, Any],
        record_order: int,
        source_ledger: str,
        source: Dict[str, List[Any]],
        target: Dict[str, List[Any]],
        path_edge_ids: Sequence[str],
        related_edge_ids: Sequence[str],
        intensity: Optional[float],
        confidence: Optional[float],
        display_title: str,
        display_summary: str,
        timing_extra: Optional[Dict[str, Any]] = None,
        reference_quality: str = "resolved",
        fallback: bool = False,
    ) -> Dict[str, Any]:
        event_id = self._stable_timeline_event_id(kind, record, record_order)
        ordered_path_edge_ids = self._unique_strings(path_edge_ids)
        path_edge_id_set = set(ordered_path_edge_ids)
        evidence_edge_ids = [
            edge_id
            for edge_id in self._unique_strings(related_edge_ids)
            if edge_id not in path_edge_id_set
        ]
        timing = {
            "timestamp": str(record.get("timestamp") or record.get("occurred_at") or ""),
            **(timing_extra or {}),
        }
        return {
            "id": event_id,
            "round": self._event_round(record),
            "phase": phase,
            "kind": kind,
            "source": source,
            "target": target,
            # ``path_edge_ids`` is an ordered, continuous route.  Only this
            # field may be staggered as source -> path -> target animation.
            # ``related_edge_ids`` names evidence or relationships affected by
            # the event; it must never be interpreted as the next route hop.
            "edge_reference_contract": EDGE_REFERENCE_CONTRACT_VERSION,
            "path_edge_ids": ordered_path_edge_ids,
            "related_edge_ids": evidence_edge_ids,
            # Additive compatibility union for layout/reference consumers.  New
            # playback code must use the two typed fields above.
            "edge_ids": self._unique_strings(
                [*ordered_path_edge_ids, *evidence_edge_ids]
            ),
            "parent_event_ids": [],
            "timing": timing,
            "intensity": intensity,
            "confidence": confidence,
            "grounding": {
                "mode": "legacy_fallback" if fallback else "observed",
                "source_ledger": source_ledger,
                "fallback": fallback,
                "reference_quality": reference_quality,
            },
            "display": {
                "title_zh": self._safe_chinese_display(display_title, "推演事件"),
                "summary_zh": self._safe_chinese_display(display_summary, "本轮推演状态发生变化。"),
            },
            "_phase_order": _TIMELINE_PHASE_ORDER.get(phase, 999),
            "_kind_order": _TIMELINE_KIND_ORDER.get(kind, 999),
            "_record_order": record_order,
            "_aliases": self._event_aliases(record),
            "_parent_aliases": self._explicit_parent_aliases(record),
            "_root_alias": str(record.get("root_event_id") or "").strip(),
            "_hop": self._optional_nonnegative_int(record.get("hop")),
        }

    def _project_spread_event(
        self,
        record: Dict[str, Any],
        record_order: int,
        references: Dict[str, Any],
    ) -> Dict[str, Any]:
        source_region = record.get("source_region") or record.get("source_region_id")
        target_region = record.get("target_region") or record.get("target_region_id")
        source_node = self._resolve_region_node(source_region, references)
        target_node = self._resolve_region_node(target_region, references)
        path_edge_ids, related_edge_ids, edge_quality = self._resolve_spread_event_edges(
            record,
            references,
            source_node,
            target_node,
        )
        source_label = self._safe_chinese_name(source_region, "源区域")
        target_label = self._safe_chinese_name(target_region, "目标区域")
        return self._base_timeline_event(
            kind="spread_applied",
            phase="environment_diffusion",
            record=record,
            record_order=record_order,
            source_ledger="spread_event_ledger.jsonl",
            source=self._reference_bundle(
                node_ids=[source_node],
                region_ids=[source_region],
                region_node_ids=[source_node],
            ),
            target=self._reference_bundle(
                node_ids=[target_node],
                region_ids=[target_region],
                region_node_ids=[target_node],
            ),
            path_edge_ids=path_edge_ids,
            related_edge_ids=related_edge_ids,
            intensity=self._number(record.get("transfer_intensity")),
            confidence=self._number(record.get("confidence")),
            display_title="环境扩散到达目标区域",
            display_summary=f"{source_label}的影响沿传播通道到达{target_label}。",
            timing_extra={
                "delay_rounds": self._safe_int(record.get("delay_rounds")),
                "persistence": self._number(record.get("persistence")),
            },
            reference_quality=self._combine_reference_quality(
                self._reference_quality(
                    [source_region, target_region], [source_node, target_node]
                ),
                edge_quality,
            ),
        )

    def _project_agent_interaction(
        self,
        record: Dict[str, Any],
        record_order: int,
        references: Dict[str, Any],
    ) -> Dict[str, Any]:
        source_agent = record.get("source_agent_id")
        target_agent = record.get("target_agent_id")
        source_region = record.get("source_region_id") or record.get("source_region_name")
        target_region = record.get("target_region_id") or record.get("target_region_name")
        source_node = self._resolve_agent_node(source_agent, references)
        target_node = self._resolve_agent_node(target_agent, references)
        source_region_node = self._resolve_region_node(source_region, references)
        target_region_node = self._resolve_region_node(target_region, references)
        path_edge_ids, related_edge_ids, edge_quality = self._resolve_interaction_event_edges(
            record,
            references,
            source_node,
            target_node,
        )
        action_label = self._safe_chinese_display(
            record.get("action_label_zh"),
            self._action_label_zh(record.get("action_type")),
        )
        event = self._base_timeline_event(
            kind="agent_interaction",
            phase="agent_response",
            record=record,
            record_order=record_order,
            source_ledger="agent_interaction_ledger.jsonl",
            source=self._reference_bundle(
                node_ids=[source_node],
                agent_ids=[source_agent],
                region_ids=[source_region],
                region_node_ids=[source_region_node],
            ),
            target=self._reference_bundle(
                node_ids=[target_node],
                agent_ids=[target_agent],
                region_ids=[target_region],
                region_node_ids=[target_region_node],
            ),
            path_edge_ids=path_edge_ids,
            related_edge_ids=related_edge_ids,
            intensity=self._interaction_intensity(record.get("delta")),
            confidence=self._number(record.get("confidence")),
            display_title="主体响应事件",
            display_summary=f"源主体对目标主体执行{action_label}，并更新相关状态。",
            timing_extra={},
            reference_quality=self._combine_reference_quality(
                self._reference_quality(
                    [source_agent, target_agent], [source_node, target_node]
                ),
                edge_quality,
            ),
        )
        event["_child_aliases"] = self._unique_strings(
            [record.get("relationship_event_id")]
        )
        return event

    def _project_dynamic_edge_event(
        self,
        record: Dict[str, Any],
        record_order: int,
        references: Dict[str, Any],
    ) -> Dict[str, Any]:
        event_type = self._dynamic_event_type(record)
        kind = f"dynamic_edge_{event_type}" if event_type in _DYNAMIC_EVENT_DISPLAY else "dynamic_edge_updated"
        title, summary = _DYNAMIC_EVENT_DISPLAY.get(event_type, _DYNAMIC_EVENT_DISPLAY["updated"])
        source_agent = record.get("source_agent_id")
        target_agent = record.get("target_agent_id")
        source_region = record.get("source_region_id")
        target_region = record.get("target_region_id")
        source_node = self._resolve_agent_node(source_agent, references)
        target_node = self._resolve_agent_node(target_agent, references)
        source_region_node = self._resolve_region_node(source_region, references)
        target_region_node = self._resolve_region_node(target_region, references)
        path_edge_ids, related_edge_ids, edge_quality = self._resolve_interaction_event_edges(
            record,
            references,
            source_node,
            target_node,
        )
        return self._base_timeline_event(
            kind=kind,
            phase="relationship_change",
            record=record,
            record_order=record_order,
            source_ledger="dynamic_edge_ledger.jsonl",
            source=self._reference_bundle(
                node_ids=[source_node],
                agent_ids=[source_agent],
                region_ids=[source_region],
                region_node_ids=[source_region_node],
            ),
            target=self._reference_bundle(
                node_ids=[target_node],
                agent_ids=[target_agent],
                region_ids=[target_region],
                region_node_ids=[target_region_node],
            ),
            path_edge_ids=path_edge_ids,
            related_edge_ids=related_edge_ids,
            intensity=self._number(record.get("strength")),
            confidence=self._number(record.get("confidence")),
            display_title=title,
            display_summary=summary,
            timing_extra={
                "created_round": self._safe_int(record.get("created_round")),
                "last_activated_round": self._safe_int(record.get("last_activated_round")),
                "expires_after_round": self._safe_int(record.get("expires_after_round")),
                "ttl_rounds": self._safe_int(record.get("ttl_rounds")),
            },
            reference_quality=self._combine_reference_quality(
                self._reference_quality(
                    [source_agent, target_agent], [source_node, target_node]
                ),
                edge_quality,
            ),
        )

    def _project_relationship_event(
        self,
        record: Dict[str, Any],
        record_order: int,
        references: Dict[str, Any],
    ) -> Dict[str, Any]:
        event_type = str(record.get("event_type") or "relationship_updated").strip().lower()
        title, fallback_summary = _RELATIONSHIP_EVENT_DISPLAY.get(
            event_type,
            _RELATIONSHIP_EVENT_DISPLAY["relationship_updated"],
        )
        source_agent = record.get("source_agent_id")
        target_agent = record.get("target_agent_id")
        source_node = self._resolve_agent_node(source_agent, references)
        target_node = self._resolve_agent_node(target_agent, references)
        path_edge_ids, related_edge_ids, edge_quality = self._resolve_interaction_event_edges(
            record,
            references,
            source_node,
            target_node,
        )
        event = self._base_timeline_event(
            kind="relationship_event",
            phase="relationship_change",
            record=record,
            record_order=record_order,
            source_ledger="relationship_event_ledger.jsonl",
            source=self._reference_bundle(node_ids=[source_node], agent_ids=[source_agent]),
            target=self._reference_bundle(node_ids=[target_node], agent_ids=[target_agent]),
            path_edge_ids=path_edge_ids,
            related_edge_ids=related_edge_ids,
            intensity=self._interaction_intensity(record.get("resource_transfer")),
            confidence=self._number(record.get("confidence")),
            display_title=title,
            display_summary=self._safe_chinese_display(record.get("summary_zh"), fallback_summary),
            timing_extra={},
            reference_quality=self._combine_reference_quality(
                self._reference_quality(
                    [source_agent, target_agent], [source_node, target_node]
                ),
                edge_quality,
            ),
        )
        # ``relationship_event_id`` names this relationship-ledger record.  In
        # interaction ledgers the same field points to the relationship event
        # produced by that action, so it must not be a universal event alias.
        event["_aliases"] = self._unique_strings(
            [*(event.get("_aliases") or []), record.get("relationship_event_id")]
        )
        return event

    def _project_risk_event(
        self,
        record: Dict[str, Any],
        record_order: int,
        references: Dict[str, Any],
    ) -> Dict[str, Any]:
        risk_id = record.get("risk_id")
        risk_node = self._resolve_generic_node(risk_id, references)
        from_status = self._risk_status_zh(record.get("from_status"))
        to_status = self._risk_status_zh(record.get("to_status"))
        fallback_summary = (
            f"风险状态由{from_status}转为{to_status}。"
            if record.get("from_status") or record.get("to_status")
            else "风险状态依据本轮运行结果完成更新。"
        )
        return self._base_timeline_event(
            kind="risk_transition",
            phase="risk_change",
            record=record,
            record_order=record_order,
            source_ledger="risk_events.jsonl",
            source=self._reference_bundle(),
            target=self._reference_bundle(node_ids=[risk_node], risk_ids=[risk_id]),
            path_edge_ids=[],
            related_edge_ids=[],
            intensity=self._number(record.get("runtime_tension")),
            confidence=self._number(record.get("confidence")),
            display_title="风险状态发生变化",
            display_summary=self._safe_chinese_display(record.get("summary"), fallback_summary),
            timing_extra={},
            reference_quality="resolved" if risk_node else "partial",
        )

    def _project_legacy_frame(self, frame: Dict[str, Any], record_order: int) -> Dict[str, Any]:
        focus = frame.get("focus_ids") or {}
        node_ids = list(focus.get("node_ids") or [])
        edge_ids = list(focus.get("edge_ids") or [])
        round_num = int(frame.get("round") or 0)
        record = {
            "round": round_num,
            "timestamp": frame.get("timestamp") or "",
            "frame_focus_nodes": node_ids,
            "frame_focus_edges": edge_ids,
        }
        legacy_path_edge_ids = edge_ids if len(self._unique_strings(edge_ids)) == 1 else []
        legacy_related_edge_ids = [] if legacy_path_edge_ids else edge_ids
        return self._base_timeline_event(
            kind="legacy_frame",
            phase="legacy_playback",
            record=record,
            record_order=record_order,
            source_ledger="frames",
            source=self._reference_bundle(),
            target=self._reference_bundle(node_ids=node_ids),
            path_edge_ids=legacy_path_edge_ids,
            related_edge_ids=legacy_related_edge_ids,
            intensity=None,
            confidence=None,
            display_title=f"第 {round_num} 轮历史回放" if round_num > 0 else "历史基线回放",
            display_summary="该事件由旧版动画帧兼容生成，缺少可验证的运行账本。",
            timing_extra={},
            reference_quality="legacy_unknown",
            fallback=True,
        )

    def _build_timeline_reference_index(
        self,
        layout_nodes: Sequence[Dict[str, Any]],
        layout_edges: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        node_index: Dict[str, str] = {}
        agent_index: Dict[str, str] = {}
        region_index: Dict[str, str] = {}
        edge_index: Dict[str, str] = {}
        edge_pairs: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        edges_by_id: Dict[str, Dict[str, Any]] = {}

        def register(index: Dict[str, str], value: Any, resolved: str) -> None:
            token = self._lookup_token(value)
            if token and token not in index:
                index[token] = resolved

        for node in layout_nodes or []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or node.get("uuid") or "").strip()
            if not node_id:
                continue
            attrs = node.get("attributes") or {}
            for value in (node_id, node.get("name"), attrs.get("name")):
                register(node_index, value, node_id)
            for value in (attrs.get("agent_id"), attrs.get("source_agent_id")):
                register(agent_index, value, node_id)
            for value in (
                attrs.get("region_id"),
                attrs.get("subregion_id"),
                attrs.get("home_region_id"),
                node.get("name"),
            ):
                register(region_index, value, node_id)
            if node_id.startswith("agent::"):
                register(agent_index, node_id.split("::", 1)[1], node_id)
            if node_id.startswith(("region::", "subregion::")):
                register(region_index, node_id.split("::", 1)[1], node_id)

        for edge in layout_edges or []:
            if not isinstance(edge, dict):
                continue
            edge_id = str(edge.get("id") or edge.get("uuid") or "").strip()
            if not edge_id:
                continue
            edges_by_id[edge_id] = dict(edge)
            attrs = edge.get("attributes") or {}
            for value in (
                edge_id,
                attrs.get("edge_id"),
                attrs.get("relationship_contract_id"),
            ):
                register(edge_index, value, edge_id)
            source = str(edge.get("source") or edge.get("source_node_uuid") or "").strip()
            target = str(edge.get("target") or edge.get("target_node_uuid") or "").strip()
            if source and target and edge_id not in edge_pairs[(source, target)]:
                edge_pairs[(source, target)].append(edge_id)

        return {
            "nodes": node_index,
            "agents": agent_index,
            "regions": region_index,
            "edges": edge_index,
            "edge_pairs": edge_pairs,
            "edges_by_id": edges_by_id,
        }

    def _resolve_agent_node(self, value: Any, references: Dict[str, Any]) -> str:
        token = self._lookup_token(value)
        if not token:
            return ""
        resolved = references.get("agents", {}).get(token) or references.get("nodes", {}).get(token)
        if resolved:
            return str(resolved)
        direct = str(value or "").strip()
        return direct if direct.startswith("agent::") else ""

    def _resolve_region_node(self, value: Any, references: Dict[str, Any]) -> str:
        token = self._lookup_token(value)
        if not token:
            return ""
        resolved = references.get("regions", {}).get(token) or references.get("nodes", {}).get(token)
        if resolved:
            return str(resolved)
        direct = str(value or "").strip()
        return direct if direct.startswith(("region::", "subregion::")) else ""

    def _resolve_generic_node(self, value: Any, references: Dict[str, Any]) -> str:
        token = self._lookup_token(value)
        if not token:
            return ""
        return str(references.get("nodes", {}).get(token) or "")

    def _resolve_event_edges(
        self,
        record: Dict[str, Any],
        references: Dict[str, Any],
        source_nodes: Sequence[str],
        target_nodes: Sequence[str],
    ) -> List[str]:
        explicit_values: List[Any] = []
        for key in ("edge_id", "relationship_edge_id", "relationship_contract_id"):
            if record.get(key) not in (None, ""):
                explicit_values.append(record.get(key))
        explicit_values.extend(list(record.get("edge_ids") or []))
        resolved: List[str] = []
        for value in explicit_values:
            token = self._lookup_token(value)
            known = references.get("edges", {}).get(token)
            resolved.append(str(known or value or ""))
        if explicit_values:
            # A ledger-provided edge is authoritative.  Adding every parallel
            # source-target edge here turns one observed interaction into several
            # visually false propagation paths.
            return self._unique_strings(resolved)
        for source in source_nodes:
            for target in target_nodes:
                resolved.extend(references.get("edge_pairs", {}).get((str(source), str(target)), []))
        return self._unique_strings(resolved)

    def _resolve_edge_values(
        self,
        values: Sequence[Any],
        references: Dict[str, Any],
    ) -> List[str]:
        resolved: List[str] = []
        for value in values:
            token = self._lookup_token(value)
            known = references.get("edges", {}).get(token)
            resolved.append(str(known or value or ""))
        return self._unique_strings(resolved)

    def _edge_path_is_continuous(
        self,
        edge_ids: Sequence[str],
        references: Dict[str, Any],
        source_node: str,
        target_node: str,
    ) -> bool:
        """Prove that an ordered multi-edge route is directionally continuous."""

        ordered = self._unique_strings(edge_ids)
        if not ordered:
            return True
        edges_by_id = references.get("edges_by_id", {})
        previous_target = ""
        for index, edge_id in enumerate(ordered):
            edge = edges_by_id.get(edge_id) or {}
            edge_source = str(edge.get("source") or "")
            edge_target = str(edge.get("target") or "")
            if not edge_source or not edge_target:
                return False
            if index == 0 and source_node and edge_source != str(source_node):
                return False
            if previous_target and edge_source != previous_target:
                return False
            previous_target = edge_target
        return not target_node or previous_target == str(target_node)

    def _resolve_spread_event_edges(
        self,
        record: Dict[str, Any],
        references: Dict[str, Any],
        source_node: str,
        target_node: str,
    ) -> Tuple[List[str], List[str], str]:
        related = self._resolve_edge_values(
            [
                *list(record.get("related_edge_ids") or []),
                *list(record.get("mechanism_edge_ids") or []),
            ],
            references,
        )
        explicit_path_values = list(record.get("path_edge_ids") or [])
        if explicit_path_values:
            resolved_path = self._resolve_edge_values(explicit_path_values, references)
            if self._edge_path_is_continuous(
                resolved_path,
                references,
                source_node,
                target_node,
            ):
                return resolved_path, related, self._edge_reference_quality(
                    record, [*resolved_path, *related], references
                )
            return [], self._unique_strings([*related, *resolved_path]), "unresolved"

        transport_edge_id = record.get("transport_edge_id")
        if transport_edge_id not in (None, ""):
            resolved_transport = self._resolve_edge_values(
                [transport_edge_id], references
            )
            if self._edge_path_is_continuous(
                resolved_transport,
                references,
                source_node,
                target_node,
            ):
                return resolved_transport, related, self._edge_reference_quality(
                    record, [*resolved_transport, *related], references
                )
            return [], self._unique_strings([*related, *resolved_transport]), "unresolved"

        primary_values = [
            record.get(key)
            for key in ("edge_id", "relationship_edge_id", "relationship_contract_id")
            if record.get(key) not in (None, "")
        ]
        if primary_values:
            resolved_primary = self._resolve_edge_values(primary_values, references)
            selected = resolved_primary[:1]
            related = self._unique_strings([*related, *resolved_primary[1:]])
            if self._edge_path_is_continuous(
                selected,
                references,
                source_node,
                target_node,
            ):
                return selected, related, self._edge_reference_quality(
                    record, [*selected, *related], references
                )
            return [], self._unique_strings([*related, *selected]), "unresolved"

        legacy_values = list(record.get("edge_ids") or [])
        if legacy_values:
            resolved_legacy = self._resolve_edge_values(legacy_values, references)
            declares_ordered_path = bool(record.get("edge_ids_are_ordered_path")) or str(
                record.get("path_contract") or record.get("edge_path_contract") or ""
            ).strip() in {"ordered_continuous_path.v1", "ordered_contiguous_path.v1"}
            if len(resolved_legacy) == 1 or declares_ordered_path:
                if self._edge_path_is_continuous(
                    resolved_legacy,
                    references,
                    source_node,
                    target_node,
                ):
                    return resolved_legacy, related, self._edge_reference_quality(
                        record, [*resolved_legacy, *related], references
                    )
                return [], self._unique_strings([*related, *resolved_legacy]), "unresolved"
            related = self._unique_strings([*related, *resolved_legacy])
            return [], related, self._edge_reference_quality(record, related, references)

        if not source_node or not target_node:
            return [], related, "unresolved"
        if source_node == target_node:
            return [], related, "resolved"

        candidates = list(
            references.get("edge_pairs", {}).get((str(source_node), str(target_node)), [])
        )
        if not candidates:
            return [], related, "unresolved"
        edges_by_id = references.get("edges_by_id", {})
        requested_channel = self._lookup_token(record.get("channel_type"))

        def score(edge_id: str) -> Tuple[int, str]:
            edge = edges_by_id.get(edge_id) or {}
            attrs = edge.get("attributes") or {}
            fact_type = self._lookup_token(edge.get("fact_type"))
            edge_channel = self._lookup_token(
                attrs.get("channel_type") or edge.get("name")
            )
            if fact_type == "transport_edge" and requested_channel and edge_channel == requested_channel:
                return (3, edge_id)
            if fact_type == "transport_edge":
                return (2, edge_id)
            return (1, edge_id)

        selected = sorted(candidates, key=lambda edge_id: (-score(edge_id)[0], score(edge_id)[1]))[0]
        selected_edge = edges_by_id.get(selected) or {}
        quality = (
            "resolved"
            if self._lookup_token(selected_edge.get("fact_type")) == "transport_edge"
            else "partial"
        )
        return [selected], related, quality

    def _resolve_interaction_event_edges(
        self,
        record: Dict[str, Any],
        references: Dict[str, Any],
        source_node: str,
        target_node: str,
    ) -> Tuple[List[str], List[str], str]:
        related = self._resolve_edge_values(
            [
                *list(record.get("related_edge_ids") or []),
                *list(record.get("mechanism_edge_ids") or []),
            ],
            references,
        )
        explicit_path_values = list(record.get("path_edge_ids") or [])
        if explicit_path_values:
            resolved_path = self._resolve_edge_values(explicit_path_values, references)
            if self._edge_path_is_continuous(
                resolved_path,
                references,
                source_node,
                target_node,
            ):
                return resolved_path, related, self._edge_reference_quality(
                    record, [*resolved_path, *related], references
                )
            return [], self._unique_strings([*related, *resolved_path]), "unresolved"

        primary_values = [
            record.get(key)
            for key in ("edge_id", "relationship_edge_id", "relationship_contract_id")
            if record.get(key) not in (None, "")
        ]
        if primary_values:
            resolved_primary = self._resolve_edge_values(primary_values, references)
            selected = resolved_primary[:1]
            related = self._unique_strings([*related, *resolved_primary[1:]])
            if self._edge_path_is_continuous(
                selected,
                references,
                source_node,
                target_node,
            ):
                return selected, related, self._edge_reference_quality(
                    record, [*selected, *related], references
                )
            return [], self._unique_strings([*related, *selected]), "unresolved"

        legacy_values = list(record.get("edge_ids") or [])
        if legacy_values:
            resolved_legacy = self._resolve_edge_values(legacy_values, references)
            declares_ordered_path = bool(record.get("edge_ids_are_ordered_path")) or str(
                record.get("path_contract") or record.get("edge_path_contract") or ""
            ).strip() in {"ordered_continuous_path.v1", "ordered_contiguous_path.v1"}
            if len(resolved_legacy) == 1 or declares_ordered_path:
                if self._edge_path_is_continuous(
                    resolved_legacy,
                    references,
                    source_node,
                    target_node,
                ):
                    return resolved_legacy, related, self._edge_reference_quality(
                        record, [*resolved_legacy, *related], references
                    )
                return [], self._unique_strings([*related, *resolved_legacy]), "unresolved"
            related = self._unique_strings([*related, *resolved_legacy])
            return [], related, self._edge_reference_quality(record, related, references)

        resolved = self._resolve_event_edges(
            record,
            references,
            [source_node] if source_node else [],
            [target_node] if target_node else [],
        )
        if len(resolved) <= 1:
            return resolved, related, "resolved" if resolved else "not_applicable"

        requested_tokens = {
            self._lookup_token(record.get("channel")),
            self._lookup_token(record.get("relation_type")),
            self._lookup_token(record.get("edge_layer")),
        }
        requested_tokens.discard("")
        edges_by_id = references.get("edges_by_id", {})
        matched = []
        for edge_id in resolved:
            edge = edges_by_id.get(edge_id) or {}
            attrs = edge.get("attributes") or {}
            edge_tokens = {
                self._lookup_token(edge.get("name")),
                self._lookup_token(edge.get("fact_type")),
                self._lookup_token(attrs.get("edge_type")),
                self._lookup_token(attrs.get("interaction_channel")),
                self._lookup_token(attrs.get("channel")),
                self._lookup_token(attrs.get("layer")),
            }
            if requested_tokens.intersection(edge_tokens):
                matched.append(edge_id)
        if len(matched) == 1:
            return matched, related, "resolved"
        # Old fixtures may prove only the endpoint pair, not which parallel
        # relationship carried the action.  Choose one stable path for rendering
        # and state the ambiguity instead of presenting all paths as observed.
        return [(matched or resolved)[0]], related, "partial"

    def _edge_reference_quality(
        self,
        record: Dict[str, Any],
        edge_ids: Sequence[str],
        references: Dict[str, Any],
    ) -> str:
        explicit_values = [
            record.get("edge_id"),
            record.get("relationship_edge_id"),
            record.get("relationship_contract_id"),
            record.get("transport_edge_id"),
            *list(record.get("edge_ids") or []),
            *list(record.get("path_edge_ids") or []),
            *list(record.get("related_edge_ids") or []),
            *list(record.get("mechanism_edge_ids") or []),
        ]
        has_explicit = any(value not in (None, "") for value in explicit_values)
        if not edge_ids:
            return "unresolved" if has_explicit else "not_applicable"
        known_count = sum(
            1
            for edge_id in edge_ids
            if self._lookup_token(edge_id) in references.get("edges", {})
            or str(edge_id) in references.get("edges_by_id", {})
        )
        if known_count == len(edge_ids):
            return "resolved"
        if known_count > 0:
            return "partial"
        return "unresolved"

    def _combine_reference_quality(self, *qualities: str) -> str:
        relevant = [quality for quality in qualities if quality and quality != "not_applicable"]
        if not relevant:
            return "not_applicable"
        if "unresolved" in relevant:
            return "unresolved"
        if "partial" in relevant:
            return "partial"
        return "resolved"

    def _reference_bundle(
        self,
        *,
        node_ids: Sequence[Any] = (),
        agent_ids: Sequence[Any] = (),
        region_ids: Sequence[Any] = (),
        region_node_ids: Sequence[Any] = (),
        risk_ids: Sequence[Any] = (),
    ) -> Dict[str, List[Any]]:
        return {
            "node_ids": self._unique_strings(node_ids),
            "agent_ids": self._unique_scalars(agent_ids),
            "region_ids": self._unique_strings(region_ids),
            "region_node_ids": self._unique_strings(region_node_ids),
            "risk_ids": self._unique_strings(risk_ids),
        }

    def _timeline_activity_by_round(
        self,
        timeline: Dict[str, Any],
    ) -> Tuple[Dict[int, set], Dict[int, set]]:
        nodes_by_round: Dict[int, set] = defaultdict(set)
        edges_by_round: Dict[int, set] = defaultdict(set)
        for event in list((timeline or {}).get("events") or []):
            if not isinstance(event, dict) or (event.get("grounding") or {}).get("fallback"):
                continue
            round_num = int(event.get("round") or 0)
            for side in (event.get("source") or {}, event.get("target") or {}):
                nodes_by_round[round_num].update(str(item) for item in side.get("node_ids") or [] if item)
                nodes_by_round[round_num].update(str(item) for item in side.get("region_node_ids") or [] if item)
            edges_by_round[round_num].update(str(item) for item in event.get("edge_ids") or [] if item)
        return nodes_by_round, edges_by_round

    def _stable_timeline_event_id(self, kind: str, record: Dict[str, Any], record_order: int) -> str:
        canonical = json.dumps(
            {"kind": kind, "record": record, "occurrence": record_order},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:18]
        return f"timeline_event::{kind}::{digest}"

    def _event_aliases(self, record: Dict[str, Any]) -> List[str]:
        return self._unique_strings(
            record.get(key)
            for key in (
                "id",
                "event_id",
                "action_event_id",
                "timeline_event_id",
            )
        )

    def _dynamic_event_type(self, record: Dict[str, Any]) -> str:
        raw_type = str(record.get("event_type") or "").strip().lower()
        if raw_type in _DYNAMIC_EVENT_DISPLAY:
            return raw_type
        # Frozen pre-V2 ledgers stored the lifecycle transition in ``status``.
        # Preserve that observed meaning instead of flattening every old edge to
        # a generic update event.
        status = str(record.get("status") or "").strip().lower()
        legacy_status_map = {
            "created": "created",
            "active": "activated",
            "activated": "activated",
            "reawakened": "reawakened",
            "promoted": "promoted",
            "cooling": "cooling",
            "dormant": "dormant",
            "expired": "expired",
        }
        return legacy_status_map.get(status, "updated")

    def _explicit_parent_aliases(self, record: Dict[str, Any]) -> List[str]:
        refs: List[Any] = []
        for key in (
            "parent_event_ids",
            "cause_event_ids",
            "source_event_ids",
            "trigger_event_ids",
        ):
            value = record.get(key)
            if isinstance(value, (list, tuple, set)):
                refs.extend(value)
            elif value not in (None, ""):
                refs.append(value)
        for key in ("parent_event_ref", "cause_event_ref", "source_event_ref", "source_action_ref"):
            value = record.get(key)
            if isinstance(value, dict):
                refs.append(value.get("artifact_id") or value.get("event_id") or value.get("id"))
        return self._unique_strings(refs)

    def _event_round(self, record: Dict[str, Any]) -> int:
        return self._safe_int(
            record.get("round")
            or record.get("round_num")
            or record.get("round_number")
            or record.get("created_round")
            or 0
        )

    def _lookup_token(self, value: Any) -> str:
        return str(value or "").strip().lower()

    def _reference_quality(self, raw_values: Sequence[Any], resolved_values: Sequence[Any]) -> str:
        raw_count = sum(1 for item in raw_values if item not in (None, ""))
        resolved_count = sum(1 for item in resolved_values if item not in (None, ""))
        if raw_count == 0:
            return "not_applicable"
        if resolved_count >= raw_count:
            return "resolved"
        if resolved_count > 0:
            return "partial"
        return "unresolved"

    def _safe_chinese_display(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        if (
            text
            and "_" not in text
            and "::" not in text
            and re.search(r"[\u3400-\u9fff]", text)
            and not re.search(r"[A-Za-z_]{3,}", text)
        ):
            return text
        return fallback

    def _safe_chinese_name(self, value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        if (
            text
            and "_" not in text
            and "::" not in text
            and re.search(r"[\u3400-\u9fff]", text)
            and not re.search(r"[A-Za-z_]{3,}", text)
        ):
            return text
        return fallback

    def _action_label_zh(self, value: Any) -> str:
        return {
            "monitor": "监测响应",
            "coordinate": "协调响应",
            "issue_alert": "发布预警",
            "public_briefing": "公开说明",
            "coordinate_response": "协调响应",
            "stabilize_services": "稳定公共服务",
            "evacuate": "疏散响应",
            "deploy_remediation": "部署修复措施",
            "request_support": "请求支援",
            "adjust_supply": "调整资源供给",
            "enforce_restriction": "执行限制措施",
        }.get(str(value or "").strip().lower(), "响应行动")

    def _risk_status_zh(self, value: Any) -> str:
        return {
            "watch": "观察",
            "elevated": "升高",
            "critical": "严重",
            "resolved": "缓解",
            "dormant": "休眠",
            "active": "活跃",
        }.get(str(value or "").strip().lower(), "当前状态")

    def _interaction_intensity(self, value: Any) -> Optional[float]:
        numeric = self._number(value)
        if numeric is not None:
            return numeric
        if isinstance(value, dict):
            candidates = [abs(float(item)) for item in value.values() if isinstance(item, (int, float))]
            return round(max(candidates), 6) if candidates else None
        return None

    def _number(self, value: Any) -> Optional[float]:
        if isinstance(value, bool) or value in (None, ""):
            return None
        try:
            return round(float(value), 6)
        except (TypeError, ValueError):
            return None

    def _unique_strings(self, values: Iterable[Any]) -> List[str]:
        result: List[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    def _unique_scalars(self, values: Iterable[Any]) -> List[Any]:
        result: List[Any] = []
        for value in values:
            if value in (None, "") or value in result:
                continue
            result.append(value)
        return result

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

    def _filter_layout_to_completed_rounds(
        self,
        layout_nodes: Sequence[Dict[str, Any]],
        layout_edges: Sequence[Dict[str, Any]],
        *,
        round_snapshots: Sequence[Dict[str, Any]],
        completed_rounds: Iterable[int],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Hide runtime graph writes newer than the committed frame watermark.

        Runtime graph artifacts and ledgers can be flushed while a round is still
        executing.  ``round_state_matrix.jsonl`` is the frame commit boundary, so
        live layout projection may expose only objects whose explicit lifecycle is
        at or before its latest completed round.  Baseline objects without runtime
        lifecycle fields remain visible.  Runtime-snapshot-only Agents get the
        additional guard that they must occur in a committed snapshot; no identity
        or numeric-ID ordering is used as a substitute for lifecycle evidence.
        """

        committed = {max(0, int(round_num)) for round_num in completed_rounds}
        watermark = max(committed, default=0)
        committed_agent_ids = {
            self._lookup_token(agent.get("agent_id"))
            for snapshot in round_snapshots or []
            if isinstance(snapshot, dict)
            and int(snapshot.get("round") or snapshot.get("round_num") or 0) in committed
            for agent in list(snapshot.get("agents") or [])
            if isinstance(agent, dict) and agent.get("agent_id") not in (None, "")
        }

        visibility_keys = (
            "created_round",
            "first_seen_round",
            "activation_round",
            "activated_round",
            "available_from_round",
            "active_since_round",
        )

        def visibility_round(item: Dict[str, Any]) -> int:
            attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            lifecycle = (
                attrs.get("runtime_lifecycle")
                if isinstance(attrs.get("runtime_lifecycle"), dict)
                else {}
            )
            values: List[int] = []
            for container in (item, attrs, lifecycle):
                for key in visibility_keys:
                    value = container.get(key)
                    if value in (None, ""):
                        continue
                    try:
                        parsed = int(value)
                    except (TypeError, ValueError):
                        continue
                    if parsed > 0:
                        values.append(parsed)
            return max(values, default=0)

        visible_nodes: List[Dict[str, Any]] = []
        visible_node_ids: set[str] = set()
        for node in layout_nodes or []:
            if not isinstance(node, dict) or visibility_round(node) > watermark:
                continue
            attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
            if (
                str(node.get("kind") or "") == "agent"
                and str(attrs.get("source") or "") == "runtime_snapshot"
                and self._lookup_token(attrs.get("agent_id")) not in committed_agent_ids
            ):
                continue
            node_id = str(node.get("id") or "")
            if not node_id:
                continue
            visible_nodes.append(dict(node))
            visible_node_ids.add(node_id)

        visible_edges = [
            dict(edge)
            for edge in layout_edges or []
            if isinstance(edge, dict)
            and visibility_round(edge) <= watermark
            and str(edge.get("source") or "") in visible_node_ids
            and str(edge.get("target") or "") in visible_node_ids
        ]
        return visible_nodes, visible_edges

    def _merge_historical_dynamic_edges(
        self,
        layout_nodes: Sequence[Dict[str, Any]],
        layout_edges: Sequence[Dict[str, Any]],
        dynamic_edge_events: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Keep timeline-referenced dynamic edges renderable after they go dormant.

        The realtime graph intentionally represents the latest active state, while
        animation playback spans the whole ledger.  This historical union adds a
        minimal edge definition only when the current layout no longer contains
        an observed dynamic edge; it does not reactivate that edge in runtime state.
        """

        merged = [dict(edge) for edge in layout_edges or [] if isinstance(edge, dict)]
        if not dynamic_edge_events:
            return merged
        references = self._build_timeline_reference_index(layout_nodes, merged)
        records_by_edge: Dict[str, List[Dict[str, Any]]] = {}
        for record in dynamic_edge_events:
            if not isinstance(record, dict):
                continue
            edge_id = str(
                record.get("edge_id")
                or record.get("relationship_contract_id")
                or ""
            ).strip()
            if edge_id:
                records_by_edge.setdefault(edge_id, []).append(record)

        for edge_id, records in records_by_edge.items():
            if self._lookup_token(edge_id) in references.get("edges", {}):
                continue
            record = {**records[0], **records[-1]}
            source_node = self._resolve_agent_node(record.get("source_agent_id"), references)
            target_node = self._resolve_agent_node(record.get("target_agent_id"), references)
            if not source_node or not target_node:
                continue
            merged.append(
                {
                    "id": edge_id,
                    "source": source_node,
                    "target": target_node,
                    "name": "历史动态关系",
                    "fact_type": "dynamic_edge",
                    "fact": "该关系来自推演运行账本，用于回放已发生的关系变化。",
                    "attributes": {
                        "edge_id": edge_id,
                        "edge_type": record.get("edge_type"),
                        "interaction_channel": record.get("interaction_channel"),
                        "origin": record.get("origin"),
                        "scope": record.get("scope"),
                        "strength": self._number(record.get("strength")),
                        "confidence": self._number(record.get("confidence")),
                        "status": record.get("status"),
                        "historical_timeline_edge": True,
                        "label_zh": "历史动态关系",
                        "runtime_lifecycle": {
                            "created_round": self._safe_int(record.get("created_round")),
                            "last_activated_round": self._safe_int(record.get("last_activated_round")),
                            "expires_after_round": self._safe_int(record.get("expires_after_round")),
                        },
                    },
                }
            )
            # Keep the local index current in case another ledger alias refers to
            # the same historical edge later in this pass.
            references["edges"][self._lookup_token(edge_id)] = edge_id
            references["edges_by_id"][edge_id] = merged[-1]
            references["edge_pairs"].setdefault((source_node, target_node), []).append(edge_id)
        return merged

    def _compute_node_first_seen(self, nodes: List[Dict[str, Any]]) -> Dict[str, int]:
        first_seen: Dict[str, int] = {}
        for node in nodes:
            node_id = str(node.get("id") or "")
            attrs = node.get("attributes") or {}
            lifecycle = attrs.get("runtime_lifecycle") or {}
            lifecycle_round = self._safe_int(
                lifecycle.get("created_round")
                or lifecycle.get("activation_round")
                or lifecycle.get("active_since_round")
                or lifecycle.get("available_from_round")
                or attrs.get("created_round")
                or 0
            )
            # Formal Step-2 entities exist at the Step-3 baseline. Only runtime-created
            # entities have a later first-seen round. Agent numeric IDs are identity,
            # never a substitute for a propagation order.
            first_seen[node_id] = max(0, lifecycle_round)
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
            # Static graph relationships are part of the baseline definition. They
            # must not all be fabricated as a round-1 propagation wave.
            first_seen[edge_id] = 0
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
        active_node_ids: Optional[set] = None,
        active_edge_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        latest_agents = list((snapshot or {}).get("agents") or [])
        active_agent_ids = set()
        if active_node_ids is None:
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
            if active_node_ids is not None and node_id in active_node_ids:
                status = "active"
            elif kind == "agent" and int(attrs.get("agent_id") or 0) in active_agent_ids:
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
            if active_edge_ids is not None:
                if edge_id in active_edge_ids and round_num >= first_seen:
                    status = "active"
                elif last_active and round_num > last_active:
                    status = "faded"
            else:
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

    def _records_for_completed_rounds(
        self,
        records: Iterable[Dict[str, Any]],
        completed_rounds: Iterable[int],
    ) -> List[Dict[str, Any]]:
        committed = {int(round_num) for round_num in completed_rounds}
        return [
            record
            for record in records
            if isinstance(record, dict)
            and (self._event_round(record) == 0 or self._event_round(record) in committed)
        ]

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

    def _optional_nonnegative_int(self, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            parsed = int(value)
        except Exception:
            return None
        return parsed if parsed >= 0 else None

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None
