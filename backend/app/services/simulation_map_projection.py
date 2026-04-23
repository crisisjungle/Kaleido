"""
Map projection builder for Step2/Step3 realtime graph payloads.

This service projects abstract EnvFish graph nodes/edges onto map coordinates.
When map-seed artifacts are available, projection is anchored by map-seed spatial
facts. Otherwise it falls back to deterministic synthetic placement.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .map_seed_manager import MapSeedManager


class SimulationMapProjectionBuilder:
    KEY_RELATION_TOKENS = {
        "dynamic_edge",
        "agent_influence",
        "influences_region",
        "depends_on",
        "affects",
        "exposed_to",
        "regulates",
        "monitors",
        "uses",
        "supports",
        "blocks",
        "collaborates_with",
    }

    NON_KEY_RELATION_TOKENS = {
        "agent_anchor",
        "region_neighbor",
        "region_hierarchy",
        "belongs_to",
        "neighbor_of",
    }

    def __init__(
        self,
        *,
        sim_dir: str,
        simulation_id: str,
        map_seed_id: Optional[str] = None,
        source_mode: str = "graph",
    ) -> None:
        self.sim_dir = sim_dir
        self.simulation_id = simulation_id
        self.map_seed_id = str(map_seed_id or "").strip() or None
        self.source_mode = str(source_mode or "graph")

    def build(self, graph_data: Dict[str, Any], *, key_edges_only: bool = True) -> Dict[str, Any]:
        graph_nodes = list((graph_data or {}).get("nodes") or [])
        graph_edges = list((graph_data or {}).get("edges") or [])
        map_layers_payload: Dict[str, Any] = {}

        if self.map_seed_id:
            map_layers_payload = MapSeedManager.get_layers(self.map_seed_id) or {}

        context = self._build_context(map_layers_payload=map_layers_payload)
        projected_nodes = self._project_nodes(graph_nodes, context)
        projected_edges, key_edge_count = self._project_edges(
            graph_edges,
            projected_nodes,
            key_edges_only=key_edges_only,
        )

        center = context.get("center") or self._average_center(projected_nodes) or {"lat": 20.0, "lon": 0.0}
        radius_m = int(context.get("radius_m") or 0)

        return {
            "simulation_id": self.simulation_id,
            "source_mode": self.source_mode,
            "map_seed_id": self.map_seed_id,
            "center": center,
            "radius_m": radius_m,
            "zoom_hint": self._zoom_hint_from_radius(radius_m),
            "analysis_polygon": context.get("analysis_polygon"),
            "layers": list(context.get("layers") or []),
            "nodes": projected_nodes,
            "edges": projected_edges,
            "meta": {
                "key_edges_only": bool(key_edges_only),
                "input_node_count": len(graph_nodes),
                "input_edge_count": len(graph_edges),
                "node_count": len(projected_nodes),
                "edge_count": len(projected_edges),
                "key_edge_count": key_edge_count,
                "has_map_seed_context": bool(self.map_seed_id and map_layers_payload),
                "water_polygon_count": len(context.get("water_geometries") or []),
                "anchor_point_count": len(context.get("anchor_points") or []),
            },
        }

    def _build_context(self, *, map_layers_payload: Dict[str, Any]) -> Dict[str, Any]:
        center_payload = map_layers_payload.get("center") or {}
        center = {
            "lat": self._to_float(center_payload.get("lat") or center_payload.get("latitude"), 20.0),
            "lon": self._to_float(center_payload.get("lon") or center_payload.get("lng") or center_payload.get("longitude"), 0.0),
        }

        anchor_points = self._collect_anchor_points(map_layers_payload)
        if anchor_points:
            if not map_layers_payload.get("center"):
                lat_avg = sum(point["lat"] for point in anchor_points) / len(anchor_points)
                lon_avg = sum(point["lon"] for point in anchor_points) / len(anchor_points)
                center = {"lat": round(lat_avg, 6), "lon": round(lon_avg, 6)}

        water_geometries = self._collect_water_geometries(map_layers_payload)
        water_zones = self._collect_water_zones(anchor_points, water_geometries)
        return {
            "center": center,
            "radius_m": int(map_layers_payload.get("radius_m") or 0),
            "analysis_polygon": map_layers_payload.get("analysis_polygon"),
            "layers": list(map_layers_payload.get("layers") or []),
            "anchor_points": anchor_points,
            "water_geometries": water_geometries,
            "water_zones": water_zones,
        }

    def _collect_anchor_points(self, map_layers_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        points: List[Dict[str, Any]] = []
        for item in list(map_layers_payload.get("feature_points") or []):
            lat = self._to_float(item.get("lat"))
            lon = self._to_float(item.get("lon"))
            if lat is None or lon is None:
                continue
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "name": str(item.get("name") or ""),
                    "category": str(item.get("category") or ""),
                    "subtype": str(item.get("subtype") or ""),
                    "source_kind": str(item.get("source_kind") or ""),
                }
            )

        for item in list(map_layers_payload.get("graph_nodes") or []):
            lat = self._to_float(item.get("lat"))
            lon = self._to_float(item.get("lon"))
            if lat is None or lon is None:
                continue
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "name": str(item.get("name") or ""),
                    "category": str(item.get("category") or ""),
                    "subtype": str(item.get("subtype") or ""),
                    "source_kind": str(item.get("source_kind") or ""),
                }
            )

        for layer in list(map_layers_payload.get("layers") or []):
            if str(layer.get("type") or "").lower() != "geojson":
                continue
            geojson = layer.get("data") or {}
            for feature in list(geojson.get("features") or []):
                geometry = feature.get("geometry") or {}
                props = feature.get("properties") or {}
                lat = None
                lon = None
                geometry_type = str(geometry.get("type") or "")
                if geometry_type in {"Polygon", "MultiPolygon"}:
                    centroid = self._geometry_centroid(geometry)
                    if centroid:
                        lon, lat = centroid
                elif geometry_type == "Point":
                    coords = list(geometry.get("coordinates") or [])
                    if len(coords) >= 2:
                        lon = self._to_float(coords[0])
                        lat = self._to_float(coords[1])
                if lat is None or lon is None:
                    continue
                points.append(
                    {
                        "lat": lat,
                        "lon": lon,
                        "name": str(props.get("name") or layer.get("name") or ""),
                        "category": str(props.get("class_name") or layer.get("name") or ""),
                        "subtype": str(props.get("class_code") or layer.get("id") or ""),
                        "source_kind": "detected",
                    }
                )

        deduped: List[Dict[str, Any]] = []
        for point in points:
            keep = True
            for existing in deduped:
                if abs(point["lat"] - existing["lat"]) < 1e-6 and abs(point["lon"] - existing["lon"]) < 1e-6:
                    keep = False
                    break
            if keep:
                deduped.append(point)
        return deduped

    def _collect_water_geometries(self, map_layers_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        geometries: List[Dict[str, Any]] = []
        for layer in list(map_layers_payload.get("layers") or []):
            if str(layer.get("type") or "").lower() != "geojson":
                continue
            geojson = layer.get("data") or {}
            features = list(geojson.get("features") or [])
            for feature in features:
                if not self._is_water_feature(layer, feature):
                    continue
                geometry = feature.get("geometry") or {}
                if not isinstance(geometry, dict):
                    continue
                geometry_type = str(geometry.get("type") or "")
                if geometry_type not in {"Polygon", "MultiPolygon"}:
                    continue
                if geometry.get("coordinates"):
                    geometries.append(geometry)
        return geometries

    def _collect_water_zones(
        self,
        anchor_points: Sequence[Dict[str, Any]],
        water_geometries: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, float]]:
        zones: List[Dict[str, float]] = []
        for point in anchor_points:
            tags = self._tags_from_anchor(point)
            if "water" not in tags:
                continue
            zones.append({"lat": point["lat"], "lon": point["lon"], "radius_m": 220.0})

        # For polygon-only water layers, add conservative circles around centroids.
        for geometry in water_geometries:
            centroid = self._geometry_centroid(geometry)
            if not centroid:
                continue
            zones.append({"lat": centroid[1], "lon": centroid[0], "radius_m": 300.0})

        deduped: List[Dict[str, float]] = []
        for zone in zones:
            keep = True
            for existing in deduped:
                distance = self._haversine_m(zone["lat"], zone["lon"], existing["lat"], existing["lon"])
                if distance < 160.0:
                    keep = False
                    break
            if keep:
                deduped.append(zone)
        return deduped

    def _project_nodes(self, nodes: Sequence[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        normalized_nodes: List[Dict[str, Any]] = []
        position_by_id: Dict[str, Tuple[float, float]] = {}
        node_meta_by_id: Dict[str, Dict[str, Any]] = {}
        region_by_key: Dict[str, str] = {}
        subregion_by_key: Dict[str, str] = {}
        used_points: List[Tuple[float, float]] = []

        # Normalize and keep any existing coordinates first.
        for index, node in enumerate(nodes):
            node_id = str(node.get("uuid") or node.get("id") or f"node_{index}")
            attributes = dict(node.get("attributes") or {})
            lat = self._to_float(attributes.get("lat") or attributes.get("latitude") or attributes.get("y"))
            lon = self._to_float(attributes.get("lon") or attributes.get("lng") or attributes.get("longitude") or attributes.get("x"))
            kind = self._node_kind(node_id=node_id, labels=node.get("labels"))
            normalized = {
                "uuid": node_id,
                "name": str(node.get("name") or node_id),
                "labels": list(node.get("labels") or []),
                "summary": str(node.get("summary") or ""),
                "attributes": attributes,
                "kind": kind,
                "source_node": node,
            }
            if lat is not None and lon is not None:
                position_by_id[node_id] = (lat, lon)
                used_points.append((lat, lon))
            normalized_nodes.append(normalized)

            region_id = str(attributes.get("region_id") or "").strip()
            if kind == "region" and region_id:
                region_by_key[region_id] = node_id
                region_by_key[str(normalized["name"])] = node_id
            if kind == "subregion" and region_id:
                subregion_by_key[region_id] = node_id
                subregion_by_key[str(normalized["name"])] = node_id
            node_meta_by_id[node_id] = normalized

        # Region placement.
        for item in normalized_nodes:
            node_id = item["uuid"]
            if node_id in position_by_id or item["kind"] != "region":
                continue
            lat, lon = self._place_region_node(item, context=context, used_points=used_points)
            position_by_id[node_id] = (lat, lon)
            used_points.append((lat, lon))

        # Subregion placement.
        for item in normalized_nodes:
            node_id = item["uuid"]
            if node_id in position_by_id or item["kind"] != "subregion":
                continue
            lat, lon = self._place_subregion_node(
                item,
                context=context,
                region_by_key=region_by_key,
                position_by_id=position_by_id,
                used_points=used_points,
            )
            position_by_id[node_id] = (lat, lon)
            used_points.append((lat, lon))

        # Agent placement.
        for item in normalized_nodes:
            node_id = item["uuid"]
            if node_id in position_by_id or item["kind"] != "agent":
                continue
            lat, lon = self._place_agent_node(
                item,
                context=context,
                region_by_key=region_by_key,
                subregion_by_key=subregion_by_key,
                node_meta_by_id=node_meta_by_id,
                position_by_id=position_by_id,
                used_points=used_points,
            )
            position_by_id[node_id] = (lat, lon)
            used_points.append((lat, lon))

        # Any remaining node types.
        for item in normalized_nodes:
            node_id = item["uuid"]
            if node_id in position_by_id:
                continue
            lat, lon = self._place_generic_node(item, context=context, used_points=used_points)
            position_by_id[node_id] = (lat, lon)
            used_points.append((lat, lon))

        projected_nodes: List[Dict[str, Any]] = []
        for item in normalized_nodes:
            node_id = item["uuid"]
            lat, lon = position_by_id.get(node_id, (None, None))
            if lat is None or lon is None:
                continue
            attributes = dict(item["attributes"])
            attributes["lat"] = round(lat, 6)
            attributes["lon"] = round(lon, 6)
            attributes["map_kind"] = item["kind"]
            attributes["map_projected"] = not bool(item["attributes"].get("lat") and item["attributes"].get("lon"))
            projected_nodes.append(
                {
                    "uuid": node_id,
                    "name": item["name"],
                    "labels": item["labels"],
                    "summary": item["summary"],
                    "kind": item["kind"],
                    "attributes": attributes,
                }
            )

        return projected_nodes

    def _place_region_node(
        self,
        node: Dict[str, Any],
        *,
        context: Dict[str, Any],
        used_points: List[Tuple[float, float]],
    ) -> Tuple[float, float]:
        attributes = node.get("attributes") or {}
        region_type = str(attributes.get("region_type") or "")
        desired_tags = self._desired_tags_for_region(region_type)
        require_water = self._prefers_water(region_type, fallback_name=node.get("name"))
        candidates = self._select_anchor_candidates(
            context=context,
            desired_tags=desired_tags,
            require_water=require_water,
        )
        if candidates:
            index = self._stable_hash_mod(f"region::{node['uuid']}", len(candidates))
            candidate = candidates[index]
            lat, lon = candidate["lat"], candidate["lon"]
            return self._resolve_conflict(
                lat=lat,
                lon=lon,
                used_points=used_points,
                min_distance_m=300.0,
                context=context,
                require_water=require_water,
                stable_key=node["uuid"],
            )
        return self._radial_fallback(
            center=context["center"],
            stable_key=f"region-fallback::{node['uuid']}",
            used_points=used_points,
            min_distance_m=320.0,
            context=context,
            require_water=require_water,
            radius_m=1200.0,
        )

    def _place_subregion_node(
        self,
        node: Dict[str, Any],
        *,
        context: Dict[str, Any],
        region_by_key: Dict[str, str],
        position_by_id: Dict[str, Tuple[float, float]],
        used_points: List[Tuple[float, float]],
    ) -> Tuple[float, float]:
        attributes = node.get("attributes") or {}
        parent_ref = str(attributes.get("parent_region_id") or "").strip()
        parent_id = region_by_key.get(parent_ref) or region_by_key.get(str(node.get("name") or "").split("·")[0])
        parent_position = position_by_id.get(parent_id) if parent_id else None
        if not parent_position:
            parent_position = (context["center"]["lat"], context["center"]["lon"])

        distance_band = str(attributes.get("distance_band") or "").lower()
        region_radius = max(float(context.get("radius_m") or 0), 3000.0)
        if distance_band in {"near", "inner"}:
            radius_m = max(600.0, min(region_radius * 0.16, 3800.0))
        elif distance_band in {"mid", "medium"}:
            radius_m = max(900.0, min(region_radius * 0.24, 4400.0))
        elif distance_band in {"far", "outer"}:
            radius_m = max(1200.0, min(region_radius * 0.34, 5200.0))
        else:
            radius_m = max(800.0, min(region_radius * 0.2, 4200.0))

        region_type = str(attributes.get("region_type") or "")
        require_water = self._prefers_water(region_type, fallback_name=node.get("name"))
        return self._radial_fallback(
            center={"lat": parent_position[0], "lon": parent_position[1]},
            stable_key=f"subregion::{node['uuid']}",
            used_points=used_points,
            min_distance_m=max(140.0, radius_m * 0.18),
            context=context,
            require_water=require_water,
            radius_m=radius_m,
        )

    def _place_agent_node(
        self,
        node: Dict[str, Any],
        *,
        context: Dict[str, Any],
        region_by_key: Dict[str, str],
        subregion_by_key: Dict[str, str],
        node_meta_by_id: Dict[str, Dict[str, Any]],
        position_by_id: Dict[str, Tuple[float, float]],
        used_points: List[Tuple[float, float]],
    ) -> Tuple[float, float]:
        attributes = node.get("attributes") or {}
        home_subregion = str(attributes.get("home_subregion_id") or "").strip()
        home_region = str(attributes.get("home_region_id") or attributes.get("primary_region") or "").strip()

        anchor_id = None
        if home_subregion:
            anchor_id = subregion_by_key.get(home_subregion)
        if not anchor_id and home_region:
            anchor_id = region_by_key.get(home_region)

        if anchor_id and anchor_id in position_by_id:
            base_lat, base_lon = position_by_id[anchor_id]
        else:
            base_lat = context["center"]["lat"]
            base_lon = context["center"]["lon"]

        anchor_token = ""
        if anchor_id and anchor_id in node_meta_by_id:
            anchor_attributes = node_meta_by_id[anchor_id].get("attributes") or {}
            anchor_token = " ".join(
                [
                    str(node_meta_by_id[anchor_id].get("name") or ""),
                    str(anchor_attributes.get("region_type") or ""),
                    str(anchor_attributes.get("land_use_class") or ""),
                    str(anchor_attributes.get("distance_band") or ""),
                ]
            )

        require_water = self._prefers_water(
            anchor_token or str(home_region),
            fallback_name=node.get("name"),
        )
        region_radius = max(float(context.get("radius_m") or 0), 3000.0)
        agent_radius = max(260.0, min(region_radius * 0.06, 1400.0))
        return self._radial_fallback(
            center={"lat": base_lat, "lon": base_lon},
            stable_key=f"agent::{node['uuid']}",
            used_points=used_points,
            min_distance_m=max(70.0, agent_radius * 0.14),
            context=context,
            require_water=require_water,
            radius_m=agent_radius,
        )

    def _place_generic_node(
        self,
        node: Dict[str, Any],
        *,
        context: Dict[str, Any],
        used_points: List[Tuple[float, float]],
    ) -> Tuple[float, float]:
        attributes = node.get("attributes") or {}
        source_kind = str(attributes.get("source_kind") or "")
        if source_kind:
            desired_tags = self._desired_tags_for_region(source_kind)
            candidates = self._select_anchor_candidates(
                context=context,
                desired_tags=desired_tags,
                require_water=self._prefers_water(source_kind, fallback_name=node.get("name")),
            )
            if candidates:
                index = self._stable_hash_mod(f"generic::{node['uuid']}", len(candidates))
                lat, lon = candidates[index]["lat"], candidates[index]["lon"]
                return self._resolve_conflict(
                    lat=lat,
                    lon=lon,
                    used_points=used_points,
                    min_distance_m=65.0,
                    context=context,
                    require_water=self._prefers_water(source_kind, fallback_name=node.get("name")),
                    stable_key=node["uuid"],
                )
        return self._radial_fallback(
            center=context["center"],
            stable_key=f"generic-fallback::{node['uuid']}",
            used_points=used_points,
            min_distance_m=70.0,
            context=context,
            require_water=False,
            radius_m=600.0,
        )

    def _project_edges(
        self,
        edges: Sequence[Dict[str, Any]],
        projected_nodes: Sequence[Dict[str, Any]],
        *,
        key_edges_only: bool,
    ) -> Tuple[List[Dict[str, Any]], int]:
        node_by_id = {str(node.get("uuid")): node for node in projected_nodes}
        projected_edges: List[Dict[str, Any]] = []
        key_count = 0
        for index, edge in enumerate(edges):
            edge_id = str(edge.get("uuid") or edge.get("id") or f"edge_{index}")
            source_id = str(edge.get("source_node_uuid") or edge.get("source") or "")
            target_id = str(edge.get("target_node_uuid") or edge.get("target") or "")
            source_node = node_by_id.get(source_id)
            target_node = node_by_id.get(target_id)
            if not source_node or not target_node:
                continue

            is_key = self._is_key_edge(edge)
            if is_key:
                key_count += 1
            if key_edges_only and not is_key:
                continue

            attributes = dict(edge.get("attributes") or {})
            attributes["is_key_interaction"] = is_key
            projected_edges.append(
                {
                    "uuid": edge_id,
                    "name": str(edge.get("name") or edge.get("fact_type") or "related_to"),
                    "fact_type": str(edge.get("fact_type") or edge.get("name") or "related_to"),
                    "fact": str(edge.get("fact") or ""),
                    "source_node_uuid": source_id,
                    "target_node_uuid": target_id,
                    "source_node_name": source_node.get("name"),
                    "target_node_name": target_node.get("name"),
                    "source_lat": source_node.get("attributes", {}).get("lat"),
                    "source_lon": source_node.get("attributes", {}).get("lon"),
                    "target_lat": target_node.get("attributes", {}).get("lat"),
                    "target_lon": target_node.get("attributes", {}).get("lon"),
                    "attributes": attributes,
                    "is_key_interaction": is_key,
                }
            )
        return projected_edges, key_count

    def _node_kind(self, *, node_id: str, labels: Any) -> str:
        if node_id.startswith("region::"):
            return "region"
        if node_id.startswith("subregion::"):
            return "subregion"
        if node_id.startswith("agent::"):
            return "agent"

        normalized_labels = {str(item or "").strip().lower() for item in (labels or [])}
        if "subregion" in normalized_labels:
            return "subregion"
        if "region" in normalized_labels:
            return "region"
        if "humanactor" in normalized_labels or "organizationactor" in normalized_labels or "governmentactor" in normalized_labels:
            return "agent"
        return "entity"

    def _select_anchor_candidates(
        self,
        *,
        context: Dict[str, Any],
        desired_tags: Sequence[str],
        require_water: bool,
    ) -> List[Dict[str, Any]]:
        anchor_points = list(context.get("anchor_points") or [])
        if not anchor_points:
            return []

        desired_set = {str(item).lower() for item in desired_tags if str(item).strip()}
        matched: List[Dict[str, Any]] = []
        dry_fallback: List[Dict[str, Any]] = []
        wet_fallback: List[Dict[str, Any]] = []
        for point in anchor_points:
            tags = self._tags_from_anchor(point)
            in_water = "water" in tags
            if require_water and not in_water:
                continue
            if require_water and in_water:
                wet_fallback.append(point)
            if not require_water and in_water:
                wet_fallback.append(point)
                continue

            if desired_set and tags.intersection(desired_set):
                matched.append(point)
            else:
                dry_fallback.append(point)

        if matched:
            return matched
        if dry_fallback:
            return dry_fallback

        if require_water:
            if wet_fallback:
                return wet_fallback
            return [point for point in anchor_points if self._point_in_water(point["lat"], point["lon"], context)]

        dry_points = [point for point in anchor_points if not self._point_in_water(point["lat"], point["lon"], context)]
        if dry_points:
            return dry_points
        return wet_fallback or anchor_points

    def _desired_tags_for_region(self, token: str) -> List[str]:
        text = str(token or "").lower()
        if any(word in text for word in ["water", "marine", "coast", "port", "river", "harbor", "海", "水"]):
            return ["water"]
        if any(word in text for word in ["forest", "ecology", "green", "wetland", "林", "生态"]):
            return ["forest", "eco"]
        if any(word in text for word in ["agri", "farm", "crop", "农", "耕"]):
            return ["farmland", "eco"]
        if any(word in text for word in ["urban", "built", "residential", "industrial", "commercial", "city", "建成", "居住", "工业"]):
            return ["built", "social"]
        return []

    def _tags_from_anchor(self, point: Dict[str, Any]) -> set[str]:
        tags: set[str] = set()
        text = " ".join(
            [
                str(point.get("name") or ""),
                str(point.get("category") or ""),
                str(point.get("subtype") or ""),
                str(point.get("source_kind") or ""),
            ]
        ).lower()
        if "worldcover_80" in text or "water" in text or "水" in text or "海" in text:
            tags.add("water")
        if "worldcover_10" in text or "forest" in text or "tree" in text or "林" in text:
            tags.add("forest")
        if "worldcover_40" in text or "farm" in text or "agri" in text or "农" in text:
            tags.add("farmland")
        if "worldcover_50" in text or "built" in text or "urban" in text or "industry" in text or "建成" in text:
            tags.add("built")
        if "human" in text or "resident" in text or "community" in text or "gov" in text or "social" in text or "人" in text:
            tags.add("social")
        if not tags:
            tags.add("eco")
        return tags

    def _prefers_water(self, token: str, *, fallback_name: Any = "") -> bool:
        text = f"{token or ''} {fallback_name or ''}".lower()
        return any(word in text for word in ["water", "marine", "coast", "port", "river", "harbor", "sea", "海", "水"])

    def _resolve_conflict(
        self,
        *,
        lat: float,
        lon: float,
        used_points: List[Tuple[float, float]],
        min_distance_m: float,
        context: Dict[str, Any],
        require_water: bool,
        stable_key: str,
    ) -> Tuple[float, float]:
        if self._is_valid_point(lat, lon, context=context, require_water=require_water) and not self._is_too_close(
            lat, lon, used_points, min_distance_m
        ):
            return round(lat, 6), round(lon, 6)

        hash_value = self._stable_hash(f"resolve::{stable_key}")
        for attempt in range(24):
            radius_m = min_distance_m + 18.0 * (attempt + 1)
            angle = (hash_value % 360) * math.pi / 180.0 + attempt * 0.73
            cand_lat, cand_lon = self._offset_by_meters(lat, lon, radius_m, angle)
            if not self._is_valid_point(cand_lat, cand_lon, context=context, require_water=require_water):
                continue
            if self._is_too_close(cand_lat, cand_lon, used_points, min_distance_m):
                continue
            return round(cand_lat, 6), round(cand_lon, 6)

        snapped = self._snap_to_domain(
            lat=lat,
            lon=lon,
            context=context,
            require_water=require_water,
            stable_key=f"snap::{stable_key}",
        )
        if snapped:
            snap_lat, snap_lon = snapped
            if not self._is_too_close(snap_lat, snap_lon, used_points, min_distance_m):
                return round(snap_lat, 6), round(snap_lon, 6)

        return round(lat, 6), round(lon, 6)

    def _radial_fallback(
        self,
        *,
        center: Dict[str, float],
        stable_key: str,
        used_points: List[Tuple[float, float]],
        min_distance_m: float,
        context: Dict[str, Any],
        require_water: bool,
        radius_m: float,
    ) -> Tuple[float, float]:
        base_lat = self._to_float(center.get("lat"), 20.0)
        base_lon = self._to_float(center.get("lon"), 0.0)
        hash_value = self._stable_hash(stable_key)

        for attempt in range(48):
            layer = 1 + attempt // 8
            local_radius = radius_m + layer * 90.0
            angle = (hash_value % 360) * math.pi / 180.0 + attempt * (math.pi / 4.0)
            cand_lat, cand_lon = self._offset_by_meters(base_lat, base_lon, local_radius, angle)
            if not self._is_valid_point(cand_lat, cand_lon, context=context, require_water=require_water):
                continue
            if self._is_too_close(cand_lat, cand_lon, used_points, min_distance_m):
                continue
            return round(cand_lat, 6), round(cand_lon, 6)

        snapped = self._snap_to_domain(
            lat=base_lat,
            lon=base_lon,
            context=context,
            require_water=require_water,
            stable_key=f"fallback-snap::{stable_key}",
        )
        if snapped:
            snap_lat, snap_lon = snapped
            if not self._is_too_close(snap_lat, snap_lon, used_points, min_distance_m):
                return round(snap_lat, 6), round(snap_lon, 6)

        # Final fallback keeps the node visible even when strict domain check fails.
        return round(base_lat, 6), round(base_lon, 6)

    def _snap_to_domain(
        self,
        *,
        lat: float,
        lon: float,
        context: Dict[str, Any],
        require_water: bool,
        stable_key: str,
    ) -> Optional[Tuple[float, float]]:
        if self._is_valid_point(lat, lon, context=context, require_water=require_water):
            return lat, lon

        hash_value = self._stable_hash(stable_key)
        for attempt in range(80):
            radius_m = 40.0 + attempt * 45.0
            angle = (hash_value % 360) * math.pi / 180.0 + attempt * 0.61
            cand_lat, cand_lon = self._offset_by_meters(lat, lon, radius_m, angle)
            if self._is_valid_point(cand_lat, cand_lon, context=context, require_water=require_water):
                return cand_lat, cand_lon
        return None

    def _is_valid_point(self, lat: float, lon: float, *, context: Dict[str, Any], require_water: bool) -> bool:
        in_water_zone = self._point_in_water_zone(lat, lon, context)
        if require_water:
            if context.get("water_zones"):
                return in_water_zone
            if context.get("water_geometries"):
                return self._point_in_water(lat, lon, context)
            return True
        if context.get("water_zones"):
            return not in_water_zone
        return True

    def _point_in_water_zone(self, lat: float, lon: float, context: Dict[str, Any]) -> bool:
        for zone in list(context.get("water_zones") or []):
            distance = self._haversine_m(lat, lon, zone["lat"], zone["lon"])
            if distance <= float(zone.get("radius_m") or 0):
                return True
        return False

    def _is_too_close(
        self,
        lat: float,
        lon: float,
        used_points: Sequence[Tuple[float, float]],
        min_distance_m: float,
    ) -> bool:
        for other_lat, other_lon in used_points:
            if self._haversine_m(lat, lon, other_lat, other_lon) < min_distance_m:
                return True
        return False

    def _offset_by_meters(self, lat: float, lon: float, radius_m: float, angle_rad: float) -> Tuple[float, float]:
        dx = radius_m * math.cos(angle_rad)
        dy = radius_m * math.sin(angle_rad)
        lat_offset = dy / 111320.0
        lon_offset = dx / max(math.cos(math.radians(lat)) * 111320.0, 1e-6)
        return lat + lat_offset, lon + lon_offset

    def _point_in_water(self, lat: float, lon: float, context: Dict[str, Any]) -> bool:
        for geometry in list(context.get("water_geometries") or []):
            geometry_type = str(geometry.get("type") or "")
            coords = geometry.get("coordinates") or []
            if geometry_type == "Polygon":
                if self._point_in_polygon(lon, lat, coords):
                    return True
            elif geometry_type == "MultiPolygon":
                for polygon in coords:
                    if self._point_in_polygon(lon, lat, polygon):
                        return True
        return False

    def _geometry_centroid(self, geometry: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        geometry_type = str(geometry.get("type") or "")
        coords = geometry.get("coordinates") or []
        points: List[Tuple[float, float]] = []
        if geometry_type == "Polygon":
            for ring in coords[:1]:
                for item in ring:
                    if not isinstance(item, list) or len(item) < 2:
                        continue
                    points.append((self._to_float(item[0], 0.0), self._to_float(item[1], 0.0)))
        elif geometry_type == "MultiPolygon":
            for polygon in coords:
                ring = polygon[0] if polygon else []
                for item in ring:
                    if not isinstance(item, list) or len(item) < 2:
                        continue
                    points.append((self._to_float(item[0], 0.0), self._to_float(item[1], 0.0)))
        if not points:
            return None
        lon_avg = sum(item[0] for item in points) / len(points)
        lat_avg = sum(item[1] for item in points) / len(points)
        return lon_avg, lat_avg

    def _point_in_polygon(self, lon: float, lat: float, polygon: Sequence[Any]) -> bool:
        if not polygon:
            return False
        outer_ring = polygon[0] if isinstance(polygon[0], list) else polygon
        if not self._point_in_ring(lon, lat, outer_ring):
            return False
        for hole in polygon[1:]:
            if self._point_in_ring(lon, lat, hole):
                return False
        return True

    def _point_in_ring(self, lon: float, lat: float, ring: Sequence[Any]) -> bool:
        if not ring or len(ring) < 3:
            return False
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi = self._to_float(ring[i][0], 0.0)
            yi = self._to_float(ring[i][1], 0.0)
            xj = self._to_float(ring[j][0], 0.0)
            yj = self._to_float(ring[j][1], 0.0)
            intersects = ((yi > lat) != (yj > lat)) and (
                lon < (xj - xi) * (lat - yi) / max((yj - yi), 1e-12) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    def _is_water_feature(self, layer: Dict[str, Any], feature: Dict[str, Any]) -> bool:
        layer_tokens = " ".join(
            [
                str(layer.get("id") or ""),
                str(layer.get("name") or ""),
                str(layer.get("note") or ""),
            ]
        ).lower()
        props = feature.get("properties") or {}
        feature_tokens = " ".join(
            [
                str(props.get("class_code") or ""),
                str(props.get("class_name") or ""),
                str(props.get("name") or ""),
            ]
        ).lower()

        if "worldcover_80" in layer_tokens or "class_code 80" in feature_tokens or "class_code:80" in feature_tokens:
            return True
        return any(token in (layer_tokens + " " + feature_tokens) for token in ["water", "marine", "coast", "海", "水"])

    def _is_key_edge(self, edge: Dict[str, Any]) -> bool:
        fact_type = str(edge.get("fact_type") or "").strip().lower()
        name = str(edge.get("name") or "").strip().lower()
        attributes = dict(edge.get("attributes") or {})
        relation_tokens = {fact_type, name}

        if relation_tokens.intersection(self.KEY_RELATION_TOKENS):
            return True
        if relation_tokens.intersection(self.NON_KEY_RELATION_TOKENS):
            return False

        if str(attributes.get("kind") or "").lower() == "structural_agent_relationship":
            strength = self._to_float(attributes.get("strength"), 0.0) or 0.0
            return strength >= 0.45 or bool(attributes.get("interaction_channel"))

        if fact_type == "transport_edge":
            strength = self._to_float(attributes.get("strength"), 0.0) or 0.0
            return strength >= 0.75

        confidence = self._to_float(attributes.get("confidence"), 0.0) or 0.0
        relation_origin = str(attributes.get("relation_origin") or "").strip().lower()
        if relation_origin and confidence >= 0.5:
            return True

        return confidence >= 0.68

    def _average_center(self, nodes: Sequence[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        coords = []
        for node in nodes:
            attributes = node.get("attributes") or {}
            lat = self._to_float(attributes.get("lat"))
            lon = self._to_float(attributes.get("lon"))
            if lat is None or lon is None:
                continue
            coords.append((lat, lon))
        if not coords:
            return None
        lat_avg = sum(item[0] for item in coords) / len(coords)
        lon_avg = sum(item[1] for item in coords) / len(coords)
        return {"lat": round(lat_avg, 6), "lon": round(lon_avg, 6)}

    def _zoom_hint_from_radius(self, radius_m: int) -> int:
        if radius_m <= 0:
            return 9
        if radius_m <= 3000:
            return 12
        if radius_m <= 10000:
            return 11
        if radius_m <= 20000:
            return 10
        if radius_m <= 50000:
            return 9
        return 8

    def _stable_hash(self, value: str) -> int:
        payload = f"{self.simulation_id}:{value}".encode("utf-8")
        return int(hashlib.sha256(payload).hexdigest()[:12], 16)

    def _stable_hash_mod(self, value: str, modulo: int) -> int:
        if modulo <= 0:
            return 0
        return self._stable_hash(value) % modulo

    def _to_float(self, value: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except Exception:
            return default

    def _haversine_m(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(1.0 - a, 1e-12)))
        return radius * c
