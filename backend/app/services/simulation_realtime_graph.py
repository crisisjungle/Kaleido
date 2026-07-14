"""
EnvFish realtime graph projection for Step2/Step3.

Builds a graph payload that GraphPanel can render directly, using simulation
artifacts generated during prepare/run.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple


# Additive edge-layer taxonomy so the frontend can separate the spatial skeleton
# from causal coupling instead of rendering one undifferentiated hairball.
# "spatial_fact" = grounded structural skeleton (regions, hierarchy, transport,
# agent anchoring); "causal" = inferred/dynamic relationships that carry coupling.
SPATIAL_FACT_FACT_TYPES = {
    "region_neighbor",
    "region_hierarchy",
    "subregion_parent",
    "transport_edge",
    "agent_anchor",
}
CAUSAL_FACT_TYPES = {
    "agent_influence",
    "dynamic_edge",
}


class SimulationRealtimeGraphBuilder:
    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir

    def _edge_layer_for(self, *, fact_type: str, name: str, attributes: Dict[str, Any]) -> str:
        """Classify an edge into the spatial skeleton vs the causal coupling layer.

        Additive only: callers may pass an explicit ``edge_layer`` to override.
        agent_relationship edges are surfaced via the relationships emitter and are
        causal (they encode inferred coupling between agents).
        """
        ft = str(fact_type or "").strip().lower()
        nm = str(name or "").strip().lower()
        if ft in SPATIAL_FACT_FACT_TYPES or nm in {"neighbor_of", "belongs_to", "located_in"}:
            return "spatial_fact"
        if ft in CAUSAL_FACT_TYPES or nm == "influences_region":
            return "causal"
        # Structural agent relationships and any other LLM-derived relation are causal.
        if str(attributes.get("kind") or "").lower() == "structural_agent_relationship":
            return "causal"
        # region_hierarchy via belongs_to handled above; default unknown relations to causal
        # since the spatial skeleton is an explicit, enumerable set.
        return "causal"

    def build(self) -> Dict[str, Any]:
        regions = self._load_json("region_graph_snapshot.json", [])
        subregions = self._load_json("subregion_graph_snapshot.json", [])
        profiles = self._load_json("profiles_full.json", [])
        relationships = self._load_json("agent_relationship_graph.json", [])
        transport_edges = self._load_json("transport_edges.json", [])
        latest_snapshot = self._load_json("latest_round_snapshot.json", {}) or {}
        simulation_config = self._load_json("simulation_config.json", {})
        mechanism_graph = self._load_json("mechanism_graph.json", {}) or {}

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
        if not mechanism_graph:
            mechanism_graph = dict(simulation_config.get("mechanism_graph") or {})

        dynamic_edges = list(latest_snapshot.get("dynamic_edges") or [])
        latest_agents = list(latest_snapshot.get("agents") or [])

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        node_ids: Set[str] = set()
        edge_ids: Set[str] = set()
        agent_node_by_id: Dict[int, str] = {}
        mechanism_nodes = list(mechanism_graph.get("nodes") or [])
        mechanism_edges = list(mechanism_graph.get("edges") or [])

        for region in regions:
            node_id = self._region_node_id(region.get("region_id"))
            if not node_id or node_id in node_ids:
                continue
            node_ids.add(node_id)
            nodes.append(
                {
                    "uuid": node_id,
                    "name": region.get("name") or "未命名区域",
                    "labels": ["Entity", "Region"],
                    "summary": region.get("description") or "",
                    "attributes": {
                        "region_id": region.get("region_id"),
                        "region_type": region.get("region_type"),
                        "layer": region.get("layer") or "macro",
                        "neighbors": list(region.get("neighbors") or []),
                        "lat": region.get("lat"),
                        "lon": region.get("lon"),
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
                    "name": subregion.get("name") or "未命名子区域",
                    "labels": ["Entity", "Region", "Subregion"],
                    "summary": subregion.get("description") or "",
                    "attributes": {
                        "region_id": subregion.get("region_id"),
                        "parent_region_id": subregion.get("parent_region_id"),
                        "region_type": subregion.get("region_type"),
                        "land_use_class": subregion.get("land_use_class"),
                        "distance_band": subregion.get("distance_band"),
                        "layer": subregion.get("layer") or "subregion",
                        "lat": subregion.get("lat"),
                        "lon": subregion.get("lon"),
                    },
                }
            )

        for mechanism_node in mechanism_nodes:
            node_id = str(mechanism_node.get("id") or mechanism_node.get("node_id") or "").strip()
            if not node_id or node_id in node_ids:
                continue
            node_type = str(mechanism_node.get("node_type") or mechanism_node.get("type") or "process").strip().lower()
            node_ids.add(node_id)
            nodes.append(
                {
                    "uuid": node_id,
                    "name": mechanism_node.get("name") or mechanism_node.get("label") or "未命名机制节点",
                    "labels": ["Entity", "MechanismNode", f"mechanism_{node_type}"],
                    "summary": mechanism_node.get("description") or "",
                    "attributes": {
                        "mechanism_node_id": node_id,
                        "node_type": node_type,
                        "confidence": mechanism_node.get("confidence"),
                        "evidence": list(mechanism_node.get("evidence") or []),
                        "origin": "mechanism_graph",
                        "map_hidden": True,
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
            runtime_lifecycle = dict(profile.get("runtime_lifecycle") or {})
            nodes.append(
                {
                    "uuid": node_id,
                    "name": profile.get("name") or profile.get("username") or f"代理体 {agent_id}",
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
                        "generation_mode": profile.get("generation_mode"),
                        "runtime_lifecycle": runtime_lifecycle,
                        "created_round": runtime_lifecycle.get("created_round"),
                        "activation_round": runtime_lifecycle.get("activation_round"),
                        "lifecycle_status": runtime_lifecycle.get("lifecycle_status") or "active",
                        "parent_agent_id": runtime_lifecycle.get("parent_agent_id"),
                        "source_entity_uuid": profile.get("source_entity_uuid"),
                        "lat": profile.get("lat"),
                        "lon": profile.get("lon"),
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
                    "name": actor.get("name") or actor.get("agent_name") or f"代理体 {agent_id}",
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

        mechanism_status_by_id = self._mechanism_epistemic_index(relationships)
        for mechanism_edge in mechanism_edges:
            edge_id = str(mechanism_edge.get("id") or mechanism_edge.get("edge_id") or "").strip()
            source_id = str(mechanism_edge.get("source") or mechanism_edge.get("source_id") or "").strip()
            target_id = str(mechanism_edge.get("target") or mechanism_edge.get("target_id") or "").strip()
            if not edge_id or source_id not in node_ids or target_id not in node_ids:
                continue
            evidence = list(mechanism_edge.get("evidence") or [])
            self._append_edge(
                edges=edges,
                edge_ids=edge_ids,
                edge_id=edge_id,
                source_node_uuid=source_id,
                target_node_uuid=target_id,
                name=mechanism_edge.get("relation_label") or mechanism_edge.get("label") or "机制传导",
                fact_type="mechanism_edge",
                fact=mechanism_edge.get("mechanism") or "",
                attributes={
                    "mechanism_edge_id": edge_id,
                    "mechanism": mechanism_edge.get("mechanism") or "",
                    "trigger_conditions": list(mechanism_edge.get("trigger_conditions") or []),
                    "latency": mechanism_edge.get("latency"),
                    "direction": mechanism_edge.get("direction"),
                    "scope": mechanism_edge.get("scope"),
                    "evidence": evidence,
                    "confidence": mechanism_edge.get("confidence"),
                    "origin": "mechanism_graph",
                    "epistemic_status": mechanism_status_by_id.get(edge_id) or ("inferred" if mechanism_edge.get("mechanism") else "speculative"),
                    "kind": "mechanism_path",
                    "map_hidden": True,
                },
                edge_layer="causal",
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
                    "relation_label": edge.get("relation_label") or edge.get("relation_type"),
                    "mechanism": edge.get("mechanism") or edge.get("rationale"),
                    "trigger_conditions": edge.get("trigger_conditions") or [],
                    "latency": edge.get("latency"),
                    "direction": edge.get("direction"),
                    "scope": edge.get("scope"),
                    "evidence": edge.get("evidence") or [],
                    "confidence": edge.get("confidence"),
                    "mechanism_edge_ids": edge.get("mechanism_edge_ids") or [],
                    "origin": edge.get("origin"),
                    "validation_status": edge.get("validation_status"),
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

        spatial_edge_count = sum(1 for edge in edges if edge.get("edge_layer") == "spatial_fact")
        causal_edge_count = sum(1 for edge in edges if edge.get("edge_layer") == "causal")

        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "region_count": len(regions),
                "subregion_count": len(subregions),
                "agent_count": len(agent_node_by_id),
                "relationship_count": len(relationships),
                "dynamic_edge_count": len(dynamic_edges),
                "mechanism_node_count": len([item for item in mechanism_nodes if str(item.get("id") or item.get("node_id") or "").strip() in node_ids]),
                "mechanism_edge_count": len([item for item in edges if item.get("fact_type") == "mechanism_edge"]),
                "node_count": len(nodes),
                "edge_count": len(edges),
                # Additive: lets the frontend separate skeleton from coupling.
                "spatial_fact_edge_count": spatial_edge_count,
                "causal_edge_count": causal_edge_count,
            },
        }

    def _mechanism_epistemic_index(self, relationships: List[Dict[str, Any]]) -> Dict[str, str]:
        ranks = {"speculative": 0, "inferred": 1, "observed": 2}
        result: Dict[str, str] = {}
        for relationship in relationships:
            status = str(relationship.get("epistemic_status") or "").strip().lower()
            validation = str(relationship.get("validation_status") or "").strip().lower()
            origin = str(relationship.get("origin") or "").strip().lower()
            if "fallback" in validation or "fallback" in origin:
                status = "speculative"
            if status not in ranks:
                status = "inferred" if relationship.get("mechanism") else "speculative"
            for mechanism_edge_id in relationship.get("mechanism_edge_ids") or []:
                edge_id = str(mechanism_edge_id or "").strip()
                if not edge_id:
                    continue
                current = result.get(edge_id)
                if current is None or ranks[status] > ranks[current]:
                    result[edge_id] = status
        return result

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
                    "lat": item.get("lat"),
                    "lon": item.get("lon"),
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
        edge_layer: Optional[str] = None,
    ) -> None:
        edge_key = str(edge_id or "")
        if not edge_key:
            edge_key = f"{source_node_uuid}->{target_node_uuid}:{name}"
        if edge_key in edge_ids:
            return
        edge_ids.add(edge_key)
        attrs = attributes or {}

        # Additive semantic tagging so the frontend can split the spatial skeleton
        # from causal coupling instead of flattening every edge into one hairball.
        layer = str(edge_layer or "").strip() or self._edge_layer_for(
            fact_type=fact_type, name=name, attributes=attrs
        )

        # Surface provenance / epistemic honesty where the source data carries it.
        provenance = (
            attrs.get("origin")
            or attrs.get("relation_origin")
            or ("structural" if layer == "spatial_fact" else None)
        )
        epistemic = (
            attrs.get("epistemic_status")
            or attrs.get("validation_status")
            or ("observed" if layer == "spatial_fact" else "inferred")
        )
        # Surface the interaction/transport channel where present so the frontend
        # can bucket causal edges by channel.
        channel = (
            attrs.get("interaction_channel")
            or attrs.get("channel_type")
            or attrs.get("channel")
        )

        edge_payload: Dict[str, Any] = {
            "uuid": edge_key,
            "name": name or "related_to",
            "fact": fact or "",
            "fact_type": fact_type or "related_to",
            "source_node_uuid": source_node_uuid,
            "target_node_uuid": target_node_uuid,
            "attributes": attrs,
            "dynamic_edge_id": dynamic_edge_id or None,
            # Additive honesty/semantic keys (do not remove keys the frontend reads).
            "edge_layer": layer,
            "provenance": provenance,
            "epistemic": epistemic,
        }
        if channel is not None:
            edge_payload["channel"] = channel
        edges.append(edge_payload)

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
