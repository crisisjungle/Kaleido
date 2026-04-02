"""
EnvFish realtime graph projection for Step2/Step3.

Builds a graph payload that GraphPanel can render directly, using simulation
artifacts generated during prepare/run.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple


class SimulationRealtimeGraphBuilder:
    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir

    def build(self) -> Dict[str, Any]:
        regions = self._load_json("region_graph_snapshot.json", [])
        subregions = self._load_json("subregion_graph_snapshot.json", [])
        profiles = self._load_json("profiles_full.json", [])
        relationships = self._load_json("agent_relationship_graph.json", [])
        transport_edges = self._load_json("transport_edges.json", [])
        latest_snapshot = self._load_json("latest_round_snapshot.json", {}) or {}
        simulation_config = self._load_json("simulation_config.json", {})

        # Fallback to config if prepare snapshots are not ready yet.
        if not regions:
            regions = list(simulation_config.get("region_graph") or [])
        if not subregions:
            subregions = list(simulation_config.get("subregion_graph") or [])
        if not relationships:
            relationships = list(simulation_config.get("agent_relationship_graph") or [])
        if not transport_edges:
            transport_edges = list(simulation_config.get("transport_edges") or [])
        if not profiles:
            profiles = self._profiles_from_config(simulation_config)

        dynamic_edges = list(latest_snapshot.get("dynamic_edges") or [])
        latest_agents = list(latest_snapshot.get("agents") or [])

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_ids: Set[str] = set()
        edge_ids: Set[str] = set()
        agent_node_by_id: Dict[int, str] = {}

        for region in regions:
            node_id = self._region_node_id(region.get("region_id"))
            if not node_id or node_id in node_ids:
                continue
            node_ids.add(node_id)
            nodes.append(
                {
                    "uuid": node_id,
                    "name": region.get("name") or region.get("region_id") or "Region",
                    "labels": ["Entity", "Region"],
                    "summary": region.get("description") or "",
                    "attributes": {
                        "region_id": region.get("region_id"),
                        "region_type": region.get("region_type"),
                        "layer": region.get("layer") or "macro",
                        "neighbors": list(region.get("neighbors") or []),
                    },
                }
            )

        for subregion in subregions:
            node_id = self._subregion_node_id(subregion.get("region_id"))
            if not node_id or node_id in node_ids:
                continue
            node_ids.add(node_id)
            nodes.append(
                {
                    "uuid": node_id,
                    "name": subregion.get("name") or subregion.get("region_id") or "Subregion",
                    "labels": ["Entity", "Region", "Subregion"],
                    "summary": subregion.get("description") or "",
                    "attributes": {
                        "region_id": subregion.get("region_id"),
                        "parent_region_id": subregion.get("parent_region_id"),
                        "region_type": subregion.get("region_type"),
                        "land_use_class": subregion.get("land_use_class"),
                        "distance_band": subregion.get("distance_band"),
                        "layer": subregion.get("layer") or "subregion",
                    },
                }
            )

        for profile in profiles:
            agent_id = self._to_int(profile.get("agent_id"))
            if agent_id is None:
                continue
            node_id = self._agent_node_id(agent_id)
            if node_id in node_ids:
                continue
            node_ids.add(node_id)
            agent_node_by_id[agent_id] = node_id
            labels = self._agent_labels(profile)
            nodes.append(
                {
                    "uuid": node_id,
                    "name": profile.get("name") or profile.get("username") or f"Agent {agent_id}",
                    "labels": labels,
                    "summary": profile.get("bio") or profile.get("persona") or "",
                    "attributes": {
                        "agent_id": agent_id,
                        "username": profile.get("username"),
                        "agent_type": profile.get("agent_type"),
                        "agent_subtype": profile.get("agent_subtype"),
                        "role_type": profile.get("role_type"),
                        "node_family": profile.get("node_family"),
                        "home_region_id": profile.get("home_region_id") or profile.get("primary_region"),
                        "home_subregion_id": profile.get("home_subregion_id"),
                        "primary_region": profile.get("primary_region"),
                        "is_synthesized": bool(profile.get("is_synthesized")),
                        "source_entity_uuid": profile.get("source_entity_uuid"),
                    },
                }
            )

        # Ensure runtime agent payloads can still be rendered even if full profiles
        # are temporarily unavailable.
        for actor in latest_agents:
            agent_id = self._to_int(actor.get("agent_id"))
            if agent_id is None:
                continue
            if agent_id in agent_node_by_id:
                continue
            node_id = self._agent_node_id(agent_id)
            if node_id in node_ids:
                continue
            node_ids.add(node_id)
            agent_node_by_id[agent_id] = node_id
            labels = self._agent_labels(actor)
            nodes.append(
                {
                    "uuid": node_id,
                    "name": actor.get("name") or actor.get("agent_name") or f"Agent {agent_id}",
                    "labels": labels,
                    "summary": "",
                    "attributes": {
                        "agent_id": agent_id,
                        "agent_type": actor.get("agent_type"),
                        "agent_subtype": actor.get("agent_subtype"),
                        "primary_region": actor.get("primary_region"),
                        "home_subregion_id": actor.get("home_subregion_id"),
                        "source": "runtime_snapshot",
                    },
                }
            )

        for region in regions:
            source_id = self._region_node_id(region.get("region_id"))
            if not source_id:
                continue
            for neighbor_id in list(region.get("neighbors") or []):
                target_id = self._region_node_id(neighbor_id)
                if source_id == target_id or target_id not in node_ids:
                    continue
                self._append_edge(
                    edges=edges,
                    edge_ids=edge_ids,
                    edge_id=f"region_neighbor::{source_id}->{target_id}",
                    source_node_uuid=source_id,
                    target_node_uuid=target_id,
                    name="neighbor_of",
                    fact_type="region_neighbor",
                    fact="Adjacent region",
                )

        for subregion in subregions:
            subregion_node_id = self._subregion_node_id(subregion.get("region_id"))
            parent_node_id = self._region_node_id(subregion.get("parent_region_id"))
            if not subregion_node_id or not parent_node_id:
                continue
            if subregion_node_id not in node_ids or parent_node_id not in node_ids:
                continue
            self._append_edge(
                edges=edges,
                edge_ids=edge_ids,
                edge_id=f"subregion_parent::{subregion_node_id}->{parent_node_id}",
                source_node_uuid=subregion_node_id,
                target_node_uuid=parent_node_id,
                name="belongs_to",
                fact_type="region_hierarchy",
                fact="Subregion belongs to macro region",
            )

        for edge in transport_edges:
            source_id = self._region_node_id(edge.get("source_region_id"))
            target_id = self._region_node_id(edge.get("target_region_id"))
            if not source_id or not target_id:
                continue
            if source_id not in node_ids or target_id not in node_ids:
                continue
            edge_id = str(edge.get("edge_id") or f"transport::{source_id}->{target_id}")
            self._append_edge(
                edges=edges,
                edge_ids=edge_ids,
                edge_id=edge_id,
                source_node_uuid=source_id,
                target_node_uuid=target_id,
                name=edge.get("channel_type") or "transport_link",
                fact_type="transport_edge",
                fact=edge.get("rationale") or "",
                attributes={
                    "channel_type": edge.get("channel_type"),
                    "travel_time_rounds": edge.get("travel_time_rounds"),
                    "attenuation_rate": edge.get("attenuation_rate"),
                    "retention_factor": edge.get("retention_factor"),
                    "strength": edge.get("strength"),
                    "confidence": edge.get("confidence"),
                },
            )

        for profile in profiles:
            agent_id = self._to_int(profile.get("agent_id"))
            if agent_id is None:
                continue
            agent_node_id = agent_node_by_id.get(agent_id)
            if not agent_node_id:
                continue
            home_subregion = self._subregion_node_id(profile.get("home_subregion_id"))
            home_region = self._region_node_id(profile.get("home_region_id") or profile.get("primary_region"))
            anchor_target = home_subregion if home_subregion in node_ids else home_region
            if anchor_target and anchor_target in node_ids:
                self._append_edge(
                    edges=edges,
                    edge_ids=edge_ids,
                    edge_id=f"agent_anchor::{agent_id}->{anchor_target}",
                    source_node_uuid=agent_node_id,
                    target_node_uuid=anchor_target,
                    name="located_in",
                    fact_type="agent_anchor",
                    fact="Agent is anchored in this region",
                    attributes={
                        "agent_id": agent_id,
                        "home_region_id": profile.get("home_region_id") or profile.get("primary_region"),
                        "home_subregion_id": profile.get("home_subregion_id"),
                    },
                )
            for influenced in list(profile.get("influenced_regions") or [])[:5]:
                influenced_node_id = self._region_node_id(influenced)
                if influenced_node_id not in node_ids:
                    continue
                self._append_edge(
                    edges=edges,
                    edge_ids=edge_ids,
                    edge_id=f"agent_influence::{agent_id}->{influenced_node_id}",
                    source_node_uuid=agent_node_id,
                    target_node_uuid=influenced_node_id,
                    name="influences_region",
                    fact_type="agent_influence",
                    fact="Agent can influence this region",
                    attributes={"agent_id": agent_id, "region_id": influenced},
                )

        for edge in relationships:
            source_id = self._agent_node_id(edge.get("source_agent_id"))
            target_id = self._agent_node_id(edge.get("target_agent_id"))
            if source_id not in node_ids or target_id not in node_ids:
                continue
            edge_id = str(edge.get("edge_id") or f"agent_rel::{source_id}->{target_id}")
            self._append_edge(
                edges=edges,
                edge_ids=edge_ids,
                edge_id=edge_id,
                source_node_uuid=source_id,
                target_node_uuid=target_id,
                name=edge.get("relation_type") or "related_to",
                fact_type=edge.get("relation_type") or "agent_relationship",
                fact=edge.get("rationale") or "",
                attributes={
                    "strength": edge.get("strength"),
                    "interaction_channel": edge.get("interaction_channel"),
                    "source_region_id": edge.get("source_region_id"),
                    "target_region_id": edge.get("target_region_id"),
                    "kind": "structural_agent_relationship",
                },
            )

        for edge in dynamic_edges:
            source_id = self._agent_node_id(edge.get("source_agent_id"))
            target_id = self._agent_node_id(edge.get("target_agent_id"))
            if source_id not in node_ids or target_id not in node_ids:
                continue
            edge_id = str(edge.get("edge_id") or f"dynamic::{source_id}->{target_id}")
            self._append_edge(
                edges=edges,
                edge_ids=edge_ids,
                edge_id=edge_id,
                source_node_uuid=source_id,
                target_node_uuid=target_id,
                name=edge.get("edge_type") or "dynamic_link",
                fact_type="dynamic_edge",
                fact=edge.get("rationale") or "",
                attributes={
                    "dynamic_edge_id": edge_id,
                    "edge_type": edge.get("edge_type"),
                    "interaction_channel": edge.get("interaction_channel"),
                    "layer": edge.get("layer"),
                    "origin": edge.get("origin"),
                    "scope": edge.get("scope"),
                    "strength": edge.get("strength"),
                    "confidence": edge.get("confidence"),
                    "status": edge.get("status"),
                    "created_round": edge.get("created_round"),
                    "last_activated_round": edge.get("last_activated_round"),
                },
                dynamic_edge_id=edge_id,
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "region_count": len(regions),
                "subregion_count": len(subregions),
                "agent_count": len(agent_node_by_id),
                "relationship_count": len(relationships),
                "dynamic_edge_count": len(dynamic_edges),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        }

    def _load_json(self, filename: str, fallback: Any) -> Any:
        path = os.path.join(self.sim_dir, filename)
        if not os.path.exists(path):
            return fallback
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return fallback

    def _profiles_from_config(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        profiles: List[Dict[str, Any]] = []
        for item in list(config.get("agent_configs") or []):
            agent_id = self._to_int(item.get("agent_id"))
            if agent_id is None:
                continue
            profiles.append(
                {
                    "agent_id": agent_id,
                    "username": item.get("agent_name"),
                    "name": item.get("name") or item.get("agent_name"),
                    "node_family": item.get("node_family"),
                    "role_type": item.get("role_type"),
                    "agent_type": item.get("agent_type"),
                    "agent_subtype": item.get("agent_subtype"),
                    "primary_region": item.get("primary_region"),
                    "home_region_id": item.get("home_region_id"),
                    "home_subregion_id": item.get("home_subregion_id"),
                    "influenced_regions": list(item.get("influenced_regions") or []),
                    "bio": item.get("bio") or "",
                    "persona": item.get("persona") or "",
                    "is_synthesized": bool(item.get("is_synthesized")),
                    "source_entity_uuid": item.get("source_entity_uuid"),
                }
            )
        return profiles

    def _append_edge(
        self,
        *,
        edges: List[Dict[str, Any]],
        edge_ids: Set[str],
        edge_id: str,
        source_node_uuid: str,
        target_node_uuid: str,
        name: str,
        fact_type: str,
        fact: str = "",
        attributes: Optional[Dict[str, Any]] = None,
        dynamic_edge_id: str = "",
    ) -> None:
        edge_key = str(edge_id or "")
        if not edge_key:
            edge_key = f"{source_node_uuid}->{target_node_uuid}:{name}"
        if edge_key in edge_ids:
            return
        edge_ids.add(edge_key)
        edges.append(
            {
                "uuid": edge_key,
                "name": name or "related_to",
                "fact": fact or "",
                "fact_type": fact_type or "related_to",
                "source_node_uuid": source_node_uuid,
                "target_node_uuid": target_node_uuid,
                "attributes": attributes or {},
                "dynamic_edge_id": dynamic_edge_id or None,
            }
        )

    def _agent_labels(self, profile: Dict[str, Any]) -> List[str]:
        labels: List[str] = ["Entity"]
        node_family = str(profile.get("node_family") or "").strip()
        agent_type = str(profile.get("agent_type") or "").strip()
        role_type = str(profile.get("role_type") or "").strip()
        if node_family:
            labels.append(node_family)
        if agent_type:
            labels.append(self._title_from_token(agent_type))
        if role_type:
            labels.append(role_type)
        seen: Set[str] = set()
        deduped: List[str] = []
        for label in labels:
            token = str(label or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            deduped.append(token)
        return deduped

    def _title_from_token(self, token: str) -> str:
        text = str(token or "").strip()
        if not text:
            return ""
        return "_".join(part.capitalize() for part in text.replace("-", "_").split("_") if part)

    def _region_node_id(self, region_id: Any) -> str:
        token = str(region_id or "").strip()
        return f"region::{token}" if token else ""

    def _subregion_node_id(self, region_id: Any) -> str:
        token = str(region_id or "").strip()
        return f"subregion::{token}" if token else ""

    def _agent_node_id(self, agent_id: Any) -> str:
        parsed = self._to_int(agent_id)
        return f"agent::{parsed}" if parsed is not None else ""

    def _to_int(self, value: Any) -> Optional[int]:
        try:
            if value in (None, ""):
                return None
            return int(value)
        except Exception:
            return None
