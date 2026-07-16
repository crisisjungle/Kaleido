"""Resolve Step 2 authoritative inputs against a real-world foundation.

The resolver never synthesizes spatial anchors. It either reuses identifiers
already present in the Step 1 catalog or builds a simulation-scoped map seed
and accepts only identifiers returned by that grounded seed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .map_seed_manager import MapSeedManager


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _key(value: Any) -> str:
    # Keep Unicode letters and numbers (for example station suffixes ①/②)
    # so distinct real-world objects do not collapse into one lookup key.
    return "".join(character for character in _text(value).casefold() if character.isalnum())


def _unique(values: Sequence[Any]) -> List[str]:
    if isinstance(values, (str, bytes)):
        values = [item for item in re.split(r"[，,、;；\n]+", str(values)) if _text(item)]
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value)
        marker = _key(item)
        if not item or not marker or marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _foundation_ref(foundation: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: foundation.get(key)
        for key in (
            "artifact_id",
            "contract_version",
            "project_id",
            "graph_id",
            "map_seed_id",
            "content_hash",
        )
        if foundation.get(key) not in (None, "")
    }


class FoundationResolutionError(ValueError):
    def __init__(self, message: str, *, code: str, artifact: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.artifact = dict(artifact or {})


@dataclass
class FoundationResolutionResult:
    foundation: Dict[str, Any]
    event_inputs: List[Dict[str, Any]]
    policy_inputs: List[Dict[str, Any]]
    artifact: Dict[str, Any]
    resolved_map_seed_id: str


class ScenarioFoundationResolver:
    """Check coverage and optionally create a simulation-scoped foundation revision."""

    def __init__(self, map_seed_manager: Optional[MapSeedManager] = None):
        self.map_seed_manager = map_seed_manager or MapSeedManager()

    def resolve(
        self,
        *,
        base_foundation: Mapping[str, Any],
        event_inputs: Sequence[Mapping[str, Any]],
        policy_inputs: Sequence[Mapping[str, Any]],
        simulation_id: str,
        effort_snapshot: Mapping[str, Any],
        scenario_location: str = "",
        foundation_builder: Callable[[str], Dict[str, Any]],
    ) -> FoundationResolutionResult:
        base = dict(base_foundation or {})
        events = [dict(item) for item in (event_inputs or [])]
        policies = [dict(item) for item in (policy_inputs or [])]
        input_hash = _canonical_hash({
            "event_inputs": events,
            "policy_inputs": policies,
            "scenario_location": _text(scenario_location),
            "base_foundation_hash": base.get("content_hash") or "",
        })
        base_ref = _foundation_ref(base)
        resolved_events, event_unresolved, event_invalid_ids = self._resolve_targets(events, base)
        resolved_policies, policy_unresolved, policy_invalid_ids = self._resolve_targets(policies, base)
        unresolved_labels = _unique([*event_unresolved, *policy_unresolved])
        invalid_ids = _unique([*event_invalid_ids, *policy_invalid_ids])
        location_changed = self._location_changed(scenario_location, base.get("location"))
        reasons: List[str] = []
        if unresolved_labels:
            reasons.append("step2_targets_not_covered")
        if invalid_ids:
            reasons.append("step2_target_ids_not_found")
        if location_changed:
            reasons.append("step2_location_outside_foundation")

        if invalid_ids:
            artifact = self._artifact(
                base_ref=base_ref,
                resolved_ref=base_ref,
                input_hash=input_hash,
                status="blocked",
                reasons=reasons,
                unresolved=[*invalid_ids, *unresolved_labels],
            )
            raise FoundationResolutionError(
                "用户指定的目标编号不在已校验现实底座中。",
                code="foundation_target_not_found",
                artifact=artifact,
            )

        if not reasons:
            artifact = self._artifact(
                base_ref=base_ref,
                resolved_ref=base_ref,
                input_hash=input_hash,
                status="reused",
                evidence_sources=self._evidence_sources(base),
            )
            return FoundationResolutionResult(
                foundation=base,
                event_inputs=resolved_events,
                policy_inputs=resolved_policies,
                artifact=artifact,
                resolved_map_seed_id=_text(base.get("map_seed_id")),
            )

        base_seed_id = _text(base.get("map_seed_id"))
        base_seed = MapSeedManager.get_seed(base_seed_id) if base_seed_id else None
        if not base_seed:
            artifact = self._artifact(
                base_ref=base_ref,
                resolved_ref={},
                input_hash=input_hash,
                status="blocked",
                reasons=reasons,
                unresolved=unresolved_labels,
            )
            raise FoundationResolutionError(
                "当前场景缺少可用于补查的现实地图底座。",
                code="foundation_seed_missing",
                artifact=artifact,
            )

        seed_input = base_seed.get("input") if isinstance(base_seed.get("input"), Mapping) else {}
        lat, lon = self._resolve_location(
            scenario_location=scenario_location,
            location_changed=location_changed,
            radius_m=int(seed_input.get("radius_m") or 3000),
            base_lat=seed_input.get("lat"),
            base_lon=seed_input.get("lon"),
            base_ref=base_ref,
            input_hash=input_hash,
            reasons=reasons,
            unresolved=unresolved_labels,
        )
        radius_m = max(500, int(seed_input.get("radius_m") or 3000))
        focus_lines = [
            *(_text(item.get("name") or item.get("title")) for item in events),
            *(_text(item.get("name") or item.get("title")) for item in policies),
        ]
        derived_seed = MapSeedManager.create_seed(
            lat=float(lat),
            lon=float(lon),
            radius_m=radius_m,
            simulation_requirement="；".join(item for item in focus_lines if item),
            title=_text(scenario_location) or _text(base_seed.get("title")) or "推演现实底座补充",
            requested_location=_text(scenario_location) or _text(seed_input.get("requested_location")),
            focus_text="；".join(item for item in focus_lines if item),
            known_entities="；".join(unresolved_labels),
            analysis_boundaries=_text(seed_input.get("analysis_boundaries")),
            focus_mode=_text(seed_input.get("focus_mode")) or "auto",
            effort_snapshot=dict(effort_snapshot or {}),
        )
        derived_seed_id = _text(derived_seed.get("seed_id"))
        MapSeedManager.update_seed(
            derived_seed_id,
            parent_seed_id=base_seed_id,
            simulation_id=simulation_id,
            foundation_scope="simulation",
            foundation_revision_reason=list(reasons),
        )
        try:
            built_seed = self.map_seed_manager.build_seed(derived_seed_id)
        except Exception as exc:
            artifact = self._artifact(
                base_ref=base_ref,
                resolved_ref={"map_seed_id": derived_seed_id},
                input_hash=input_hash,
                status="blocked",
                reasons=reasons,
                unresolved=unresolved_labels,
            )
            raise FoundationResolutionError(
                "现实资料补查未能完成。",
                code="foundation_enrichment_failed",
                artifact=artifact,
            ) from exc
        if not MapSeedManager.is_formal_seed_ready(built_seed):
            artifact = self._artifact(
                base_ref=base_ref,
                resolved_ref={"map_seed_id": derived_seed_id},
                input_hash=input_hash,
                status="blocked",
                reasons=reasons,
                unresolved=unresolved_labels,
                evidence_sources=self._evidence_sources_from_seed(built_seed),
            )
            raise FoundationResolutionError(
                "没有取得足以支撑新地点或目标对象的现实资料。",
                code="foundation_evidence_unavailable",
                artifact=artifact,
            )

        resolved_foundation = foundation_builder(derived_seed_id)
        final_events, event_unresolved, event_invalid_ids = self._resolve_targets(events, resolved_foundation)
        final_policies, policy_unresolved, policy_invalid_ids = self._resolve_targets(policies, resolved_foundation)
        unresolved = _unique([
            *event_unresolved,
            *policy_unresolved,
            *event_invalid_ids,
            *policy_invalid_ids,
        ])
        resolved_ref = _foundation_ref(resolved_foundation)
        added_regions, added_entities = self._added_ids(base, resolved_foundation)
        if unresolved:
            artifact = self._artifact(
                base_ref=base_ref,
                resolved_ref=resolved_ref,
                input_hash=input_hash,
                status="blocked",
                reasons=reasons,
                added_region_ids=added_regions,
                added_entity_ids=added_entities,
                unresolved=unresolved,
                evidence_sources=self._evidence_sources(resolved_foundation),
            )
            raise FoundationResolutionError(
                "补查后仍无法确认用户指定的真实地点或对象。",
                code="foundation_target_unresolved",
                artifact=artifact,
            )

        artifact = self._artifact(
            base_ref=base_ref,
            resolved_ref=resolved_ref,
            input_hash=input_hash,
            status="enriched",
            reasons=reasons,
            added_region_ids=added_regions,
            added_entity_ids=added_entities,
            evidence_sources=self._evidence_sources(resolved_foundation),
        )
        return FoundationResolutionResult(
            foundation=resolved_foundation,
            event_inputs=final_events,
            policy_inputs=final_policies,
            artifact=artifact,
            resolved_map_seed_id=derived_seed_id,
        )

    @staticmethod
    def _catalog(foundation: Mapping[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        by_name: Dict[str, List[Dict[str, Any]]] = {}
        for raw in foundation.get("target_catalog") or []:
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            item_id = _text(item.get("id"))
            if not item_id:
                continue
            by_id[item_id] = item
            aliases = item.get("aliases") or []
            if isinstance(aliases, (str, bytes)):
                aliases = [aliases]
            for label in [item.get("name"), *aliases]:
                marker = _key(label)
                if marker:
                    by_name.setdefault(marker, []).append(item)
        return by_id, by_name

    @classmethod
    def _resolve_targets(
        cls,
        values: Sequence[Mapping[str, Any]],
        foundation: Mapping[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
        by_id, by_name = cls._catalog(foundation)
        resolved: List[Dict[str, Any]] = []
        unresolved_labels: List[str] = []
        invalid_ids: List[str] = []
        for raw in values:
            item = dict(raw)
            region_ids = _unique(item.get("target_region_ids") or item.get("target_regions") or [])
            entity_ids = _unique(item.get("target_entity_ids") or item.get("target_nodes") or [])
            for item_id in [*region_ids, *entity_ids]:
                if item_id not in by_id:
                    invalid_ids.append(item_id)
            labels = _unique(item.get("target_labels") or item.get("target_text") or [])
            for label in labels:
                matches = by_name.get(_key(label), [])
                unique_matches = {str(match.get("id")): match for match in matches}
                explicit_ids = set(region_ids) | set(entity_ids)
                explicitly_anchored = [
                    match for match_id, match in unique_matches.items()
                    if match_id in explicit_ids
                ]
                if len(explicitly_anchored) == 1:
                    continue
                if len(unique_matches) != 1:
                    unresolved_labels.append(label)
                    continue
                match = next(iter(unique_matches.values()))
                match_id = _text(match.get("id"))
                if _text(match.get("kind")).lower() == "region":
                    region_ids.append(match_id)
                else:
                    entity_ids.append(match_id)
            item["target_region_ids"] = _unique(region_ids)
            item["target_entity_ids"] = _unique(entity_ids)
            item["target_labels"] = labels
            resolved.append(item)
        return resolved, _unique(unresolved_labels), _unique(invalid_ids)

    @staticmethod
    def _location_changed(requested: str, current: Any) -> bool:
        requested_key = _key(requested)
        current_key = _key(current)
        if not requested_key:
            return False
        if not current_key:
            return True
        return requested_key not in current_key and current_key not in requested_key

    def _resolve_location(
        self,
        *,
        scenario_location: str,
        location_changed: bool,
        radius_m: int,
        base_lat: Any,
        base_lon: Any,
        base_ref: Mapping[str, Any],
        input_hash: str,
        reasons: Sequence[str],
        unresolved: Sequence[str],
    ) -> Tuple[float, float]:
        if not location_changed:
            try:
                return float(base_lat), float(base_lon)
            except (TypeError, ValueError) as exc:
                raise FoundationResolutionError(
                    "第一步现实底座缺少有效地图中心。",
                    code="foundation_coordinates_missing",
                ) from exc
        candidates = self.map_seed_manager.geocode_location(
            _text(scenario_location),
            limit=3,
            radius_m=radius_m,
        )
        unique: Dict[Tuple[float, float], Dict[str, Any]] = {}
        for candidate in candidates:
            try:
                marker = (round(float(candidate.get("lat")), 4), round(float(candidate.get("lon")), 4))
            except (TypeError, ValueError):
                continue
            unique[marker] = candidate
        if len(unique) != 1:
            artifact = self._artifact(
                base_ref=dict(base_ref),
                resolved_ref={},
                input_hash=input_hash,
                status="blocked",
                reasons=reasons,
                unresolved=[_text(scenario_location), *unresolved],
            )
            raise FoundationResolutionError(
                "新地点无法唯一确认，请返回第一步明确地点和范围。",
                code="foundation_location_ambiguous",
                artifact=artifact,
            )
        candidate = next(iter(unique.values()))
        return float(candidate["lat"]), float(candidate["lon"])

    @classmethod
    def _added_ids(
        cls,
        base: Mapping[str, Any],
        resolved: Mapping[str, Any],
    ) -> Tuple[List[str], List[str]]:
        base_ids, _ = cls._catalog(base)
        resolved_ids, _ = cls._catalog(resolved)
        regions: List[str] = []
        entities: List[str] = []
        for item_id, item in resolved_ids.items():
            if item_id in base_ids:
                continue
            if _text(item.get("kind")).lower() == "region":
                regions.append(item_id)
            else:
                entities.append(item_id)
        return regions, entities

    @staticmethod
    def _evidence_sources(foundation: Mapping[str, Any]) -> List[Dict[str, Any]]:
        sources = foundation.get("evidence_sources") or []
        return [dict(item) for item in sources if isinstance(item, Mapping)]

    @staticmethod
    def _evidence_sources_from_seed(seed: Mapping[str, Any]) -> List[Dict[str, Any]]:
        quality = seed.get("data_quality") if isinstance(seed.get("data_quality"), Mapping) else {}
        providers = quality.get("providers") if isinstance(quality.get("providers"), Mapping) else {}
        return [
            {"source": _text(name), "status": _text(value.get("status"))}
            for name, value in providers.items()
            if isinstance(value, Mapping)
        ]

    @staticmethod
    def _artifact(
        *,
        base_ref: Mapping[str, Any],
        resolved_ref: Mapping[str, Any],
        input_hash: str,
        status: str,
        reasons: Optional[Sequence[str]] = None,
        added_region_ids: Optional[Sequence[str]] = None,
        added_entity_ids: Optional[Sequence[str]] = None,
        unresolved: Optional[Sequence[str]] = None,
        evidence_sources: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return {
            "contract_version": "foundation_resolution.v1",
            "base_foundation_ref": dict(base_ref or {}),
            "resolved_foundation_ref": dict(resolved_ref or {}),
            "step2_input_hash": input_hash,
            "resolution_status": status,
            "enrichment_reasons": list(reasons or []),
            "added_region_ids": list(added_region_ids or []),
            "added_entity_ids": list(added_entity_ids or []),
            "unresolved_targets": list(unresolved or []),
            "evidence_sources": [dict(item) for item in (evidence_sources or [])],
            "created_at": datetime.now().isoformat(),
        }
