"""Deterministic, focus-aware spatial candidate selection for map seeds.

Collection and selection are deliberately separate concerns.  Public providers
may return many unevenly distributed objects (or fail entirely); this module
turns whatever candidates are available into a small, explainable spatial
skeleton without letting data density silently stand in for user intent.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .effort_contract import effort_stage_budget, normalize_effort_snapshot


PUBLIC_PROVIDERS = {
    "overpass",
    "osm",
    "osm_overpass",
    "worldcover_cog",
}

CONTEXTUAL_PROVIDERS = {
    "esa_worldcover",
    "worldcover",
    "worldcover_wms",
    "reverse_geocode",
    "open_meteo",
    "open-meteo",
}

FALLBACK_PROVIDERS = {
    "local_geographic_gazetteer",
    "curated_fixture",
    "local_fallback",
}

GENERIC_FOCUS_PHRASES = {
    "选定区域",
    "当前区域",
    "分析区域",
    "综合风险",
    "场景背景分析",
    "稳态环境",
    "推演要求",
    "补充背景",
    "事件或稳态基线",
}

FOCUS_CUES = ("重点", "主要", "优先", "只看", "只分析", "就想", "聚焦", "侧重", "关注")
SCOPE_ONLY_CUES = ("画到", "画了", "划到", "覆盖到", "覆盖了", "不扩展", "不看", "排除", "忽略", "仅作为范围")

PLACE_SUFFIX_PATTERN = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9·]{2,24}?(?:市|区|县|街道|镇|乡|湾|河|江|湖|水库|湿地|机场|车站|港|岛|公园|学校|医院|片区|区域|廊道))"
)


@dataclass(frozen=True)
class SelectionContext:
    center_lat: float
    center_lon: float
    radius_m: int
    simulation_requirement: str = ""
    title: str = ""
    requested_location: str = ""
    focus_text: str = ""
    known_entities: str = ""
    analysis_boundaries: str = ""
    focus_mode: str = "auto"
    admin_context: Dict[str, Any] = field(default_factory=dict)

    @property
    def combined_user_text(self) -> str:
        return "\n".join(
            item.strip()
            for item in [
                self.requested_location,
                self.title,
                self.simulation_requirement,
                self.focus_text,
                self.known_entities,
                self.analysis_boundaries,
            ]
            if str(item or "").strip()
        )

    @property
    def explicit_focus_text(self) -> str:
        values = [self.focus_text, self.known_entities, self.analysis_boundaries]
        requirement = str(self.simulation_requirement or "").strip()
        scope_labels = {
            _normalize_text(self.requested_location),
            _normalize_text(self.title),
            _normalize_text(self.admin_context.get("display_name")),
        }
        if requirement and _normalize_text(requirement) not in scope_labels:
            values.append(requirement)
        return "\n".join(str(item or "").strip() for item in values if str(item or "").strip())


@dataclass
class SelectionResult:
    selected_features: List[Dict[str, Any]]
    granularity: str
    focus_terms: List[str]
    diagnostics: Dict[str, Any]


@dataclass(frozen=True)
class SpatialEffortPolicy:
    effort_level: str
    planning_anchor_limit: int
    candidate_pool_limit: int
    targeted_refinement_slots: int
    base_spatial_level: int
    hotspot_spatial_level: int
    spatial_hypothesis_limit: int
    broad_r4_scan_allowed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effort_level": self.effort_level,
            "planning_anchor_limit": self.planning_anchor_limit,
            "candidate_pool_limit": self.candidate_pool_limit,
            "targeted_refinement_slots": self.targeted_refinement_slots,
            "base_spatial_level": self.base_spatial_level,
            "hotspot_spatial_level": self.hotspot_spatial_level,
            "spatial_hypothesis_limit": self.spatial_hypothesis_limit,
            "broad_r4_scan_allowed": self.broad_r4_scan_allowed,
        }


def spatial_policy_from_effort(
    effort_snapshot: Optional[Mapping[str, Any]],
) -> SpatialEffortPolicy:
    resolved = normalize_effort_snapshot(effort_snapshot)
    limits = effort_stage_budget(resolved, "step1")["operation_limits"]
    return SpatialEffortPolicy(
        effort_level=str(resolved["effort_level"]),
        planning_anchor_limit=max(1, int(limits["planning_anchor_limit"])),
        candidate_pool_limit=max(1, int(limits["candidate_pool_limit"])),
        targeted_refinement_slots=max(0, int(limits["targeted_refinement_slots"])),
        base_spatial_level=max(0, min(4, int(limits["base_spatial_level"]))),
        hotspot_spatial_level=max(0, min(4, int(limits["hotspot_spatial_level"]))),
        spatial_hypothesis_limit=max(1, int(limits["spatial_hypothesis_limit"])),
        broad_r4_scan_allowed=bool(limits.get("broad_r4_scan_allowed", False)),
    )


def granularity_for_radius(radius_m: int) -> str:
    radius = max(0, int(radius_m or 0))
    if radius <= 3_000:
        return "site_street"
    if radius <= 15_000:
        return "street_district"
    if radius <= 30_000:
        return "district"
    return "city_region"


def select_spatial_features(
    features: Sequence[Dict[str, Any]],
    *,
    context: SelectionContext,
    limit: int,
    effort_policy: Optional[SpatialEffortPolicy | Mapping[str, Any]] = None,
) -> SelectionResult:
    """Select a small spatial skeleton using intent, quality and coverage.

    The policy is deterministic:

    1. Explicitly named places always lead.
    2. Large AOIs stay at macro granularity unless a fine site is named.
    3. With no explicit focus, spatial sectors and semantic categories receive
       minimum coverage before the remaining score-ranked slots are filled.
    4. Repeated subtypes and already-covered sectors receive diminishing value.
    """

    policy = _normalize_effort_policy(effort_policy)
    requested_limit = max(1, int(limit or 1))
    max_items = min(requested_limit, policy.planning_anchor_limit) if policy else requested_limit
    granularity = granularity_for_radius(context.radius_m)
    user_text = context.combined_user_text
    normalized_user_text = _normalize_text(user_text)
    normalized_focus_text = _normalize_text(context.explicit_focus_text)
    normalized_scope_text = _normalize_text(" ".join([context.requested_location, context.title]))
    focus_terms = _extract_focus_terms(context, features)

    annotated: List[Dict[str, Any]] = []
    for feature in features or []:
        if not _has_coordinates(feature):
            continue
        item = dict(feature)
        tags = dict(item.get("tags") or {})
        item["tags"] = tags
        focus_score, focus_reasons, direct_focus = _focus_score(
            item,
            normalized_user_text=normalized_focus_text,
            focus_terms=focus_terms,
        )
        scope_score = _scope_score(item, normalized_scope_text)
        scenario_score, scenario_reasons = _scenario_score(item, normalized_user_text)
        base_score = (
            float(item.get("importance") or 0) * 1.25
            + float(item.get("confidence") or 0) * 3.0
            + _source_quality_score(item)
            + _distance_score(item, context.radius_m)
            + focus_score
            + scope_score
            + scenario_score
        )
        sector = _sector_for(item, context)
        spatial_level = _spatial_level(item)
        item["selection_score"] = round(base_score, 4)
        item["selection_sector"] = sector
        item["selection_spatial_level"] = spatial_level
        item["selection_spatial_rank"] = _spatial_rank(spatial_level)
        item["selection_focus_score"] = round(focus_score, 4)
        item["selection_scenario_score"] = round(scenario_score, 4)
        item["selection_direct_focus"] = bool(direct_focus)
        item["selection_scope_score"] = round(scope_score, 4)
        item["selection_reasons"] = [*focus_reasons, *scenario_reasons]
        annotated.append(item)

    collected_candidate_count = len(annotated)
    if policy:
        annotated = _bounded_candidate_pool(annotated, policy.candidate_pool_limit)

    explicit_focus = any(float(item.get("selection_focus_score") or 0) > 0 for item in annotated)
    refinement_ids: set[str] = set()
    if policy:
        refinement_ids = _targeted_refinement_ids(annotated, policy)
        allowed = [
            item
            for item in annotated
            if _allowed_for_effort_policy(item, policy=policy, refinement_ids=refinement_ids)
        ]
    else:
        allowed = [
            item
            for item in annotated
            if _allowed_for_granularity(item, granularity=granularity, explicit_focus=explicit_focus)
        ]
    focus_resolution = "not_applicable"
    if explicit_focus:
        # A location mentioned only as circle coverage/exclusion must never be
        # used to fill the result after the actual focus was filtered out.
        allowed = [item for item in allowed if float(item.get("selection_focus_score") or 0) >= 0]
        if any(float(item.get("selection_focus_score") or 0) > 0 for item in allowed):
            focus_resolution = "direct_or_macro"
        else:
            scoped_candidates = [
                item
                for item in (allowed if policy else annotated)
                if float(item.get("selection_focus_score") or 0) > 0
                and not bool(item.get("selection_direct_focus"))
                and item.get("selection_spatial_level") in {"site", "street"}
            ]
            representatives = _bounded_focus_representatives(
                scoped_candidates,
                cap=min(max_items, 6),
            )
            if representatives:
                representative_ids = {
                    str(item.get("feature_id") or "") for item in representatives
                }
                allowed = [
                    *representatives,
                    *[
                        item
                        for item in allowed
                        if str(item.get("feature_id") or "") not in representative_ids
                    ],
                ]
                focus_resolution = "representative_fallback"
            else:
                focus_resolution = "unresolved"
    elif not allowed and not policy:
        allowed = annotated

    selected: List[Dict[str, Any]] = []
    selected_ids: set[str] = set()

    def add(item: Dict[str, Any]) -> bool:
        feature_id = str(item.get("feature_id") or "").strip()
        if not feature_id or feature_id in selected_ids or len(selected) >= max_items:
            return False
        selected.append(item)
        selected_ids.add(feature_id)
        return True

    if explicit_focus:
        focused = sorted(
            (item for item in allowed if float(item.get("selection_focus_score") or 0) > 0),
            key=_selection_sort_key,
        )
        for item in focused:
            add(item)

    # When intent is ambiguous, cover the AOI before following raw importance.
    if not explicit_focus:
        sectors = sorted({str(item.get("selection_sector") or "center") for item in allowed})
        for sector in sectors:
            candidates = [item for item in allowed if item.get("selection_sector") == sector]
            if candidates:
                add(sorted(candidates, key=_selection_sort_key)[0])

        categories = sorted({str(item.get("category") or "other") for item in allowed})
        for category in categories:
            if any(str(item.get("category") or "other") == category for item in selected):
                continue
            candidates = [item for item in allowed if str(item.get("category") or "other") == category]
            if candidates:
                add(sorted(candidates, key=_selection_sort_key)[0])

    while len(selected) < max_items:
        remaining = [
            item
            for item in allowed
            if str(item.get("feature_id") or "") not in selected_ids
        ]
        if not remaining:
            break
        sector_counts = _counts(selected, "selection_sector")
        subtype_counts = _counts(selected, "subtype")
        category_counts = _counts(selected, "category")

        def marginal(item: Dict[str, Any]) -> tuple[float, float, str]:
            sector = str(item.get("selection_sector") or "center")
            subtype = str(item.get("subtype") or "other")
            category = str(item.get("category") or "other")
            diversity_bonus = 0.0
            if sector_counts.get(sector, 0) == 0:
                diversity_bonus += 4.0
            if category_counts.get(category, 0) == 0:
                diversity_bonus += 2.5
            diversity_bonus -= max(0, subtype_counts.get(subtype, 0) - 1) * 1.25
            score = float(item.get("selection_score") or 0) + diversity_bonus
            return (-score, float(item.get("distance_m") or 0), str(item.get("name") or ""))

        add(sorted(remaining, key=marginal)[0])

    diagnostics = {
        "explicit_focus": explicit_focus,
        "focus_mode": str(context.focus_mode or "auto"),
        "candidate_count": len(annotated),
        "collected_candidate_count": collected_candidate_count,
        "eligible_candidate_count": len(allowed),
        "selected_count": len(selected),
        "granularity": granularity,
        "sector_counts": _counts(selected, "selection_sector"),
        "category_counts": _counts(selected, "category"),
        "source_counts": _provider_counts(selected),
        "selection_policy": "explicit_focus_then_spatial_category_balance",
        "focus_resolution": focus_resolution,
        "effort_spatial_policy": policy.to_dict() if policy else None,
        "targeted_refinement_count": len(refinement_ids),
        "targeted_refinement_feature_ids": sorted(refinement_ids),
    }
    return SelectionResult(
        selected_features=selected,
        granularity=granularity,
        focus_terms=focus_terms,
        diagnostics=diagnostics,
    )


def _normalize_effort_policy(
    policy: Optional[SpatialEffortPolicy | Mapping[str, Any]],
) -> Optional[SpatialEffortPolicy]:
    if policy is None:
        return None
    if isinstance(policy, SpatialEffortPolicy):
        return policy
    try:
        return SpatialEffortPolicy(
            effort_level=str(policy.get("effort_level") or "high"),
            planning_anchor_limit=max(1, int(policy["planning_anchor_limit"])),
            candidate_pool_limit=max(1, int(policy["candidate_pool_limit"])),
            targeted_refinement_slots=max(0, int(policy["targeted_refinement_slots"])),
            base_spatial_level=max(0, min(4, int(policy["base_spatial_level"]))),
            hotspot_spatial_level=max(0, min(4, int(policy["hotspot_spatial_level"]))),
            spatial_hypothesis_limit=max(1, int(policy.get("spatial_hypothesis_limit") or 1)),
            broad_r4_scan_allowed=bool(policy.get("broad_r4_scan_allowed", False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("空间选择预算配置无效") from exc


def _bounded_candidate_pool(
    items: Sequence[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    """Bound expensive downstream ranking without dropping named or diverse anchors."""

    max_items = max(1, int(limit or 1))
    if len(items) <= max_items:
        return list(items)
    selected: List[Dict[str, Any]] = []
    selected_ids: set[str] = set()

    def add(item: Dict[str, Any]) -> None:
        feature_id = str(item.get("feature_id") or "").strip()
        if not feature_id or feature_id in selected_ids or len(selected) >= max_items:
            return
        selected.append(item)
        selected_ids.add(feature_id)

    ranked = sorted(items, key=_selection_sort_key)
    for item in ranked:
        if bool(item.get("selection_direct_focus")):
            add(item)
    for sector in sorted({str(item.get("selection_sector") or "center") for item in ranked}):
        candidate = next(
            (item for item in ranked if str(item.get("selection_sector") or "center") == sector),
            None,
        )
        if candidate:
            add(candidate)
    for category in sorted({str(item.get("category") or "other") for item in ranked}):
        candidate = next(
            (item for item in ranked if str(item.get("category") or "other") == category),
            None,
        )
        if candidate:
            add(candidate)
    for item in ranked:
        add(item)
    return selected


def _targeted_refinement_ids(
    items: Sequence[Dict[str, Any]],
    policy: SpatialEffortPolicy,
) -> set[str]:
    if policy.targeted_refinement_slots <= 0:
        return set()
    candidates = [
        item
        for item in items
        if not bool(item.get("selection_direct_focus"))
        and policy.base_spatial_level < int(item.get("selection_spatial_rank") or 0)
        <= policy.hotspot_spatial_level
        and (
            float(item.get("selection_focus_score") or 0) > 0
            or float(item.get("selection_scenario_score") or 0) > 0
        )
    ]
    selected = sorted(candidates, key=_selection_sort_key)[: policy.targeted_refinement_slots]
    return {str(item.get("feature_id") or "") for item in selected if item.get("feature_id")}


def _allowed_for_effort_policy(
    feature: Dict[str, Any],
    *,
    policy: SpatialEffortPolicy,
    refinement_ids: set[str],
) -> bool:
    spatial_rank = int(feature.get("selection_spatial_rank") or 0)
    if spatial_rank <= policy.base_spatial_level:
        return True
    feature_id = str(feature.get("feature_id") or "")
    if feature_id in refinement_ids:
        return True
    # A qualified facility named by the user survives Light/Medium aggregation,
    # but R4 internal units still require a tier that explicitly permits R4.
    named_focus_ceiling = max(3, policy.hotspot_spatial_level)
    if bool(feature.get("selection_direct_focus")) and spatial_rank <= named_focus_ceiling:
        return True
    if spatial_rank >= 4 and policy.broad_r4_scan_allowed:
        return True
    return False


def _bounded_focus_representatives(
    candidates: Sequence[Dict[str, Any]],
    *,
    cap: int,
) -> List[Dict[str, Any]]:
    """Keep a small, diverse sample when a focused city boundary is missing."""
    max_items = max(0, int(cap or 0))
    if max_items == 0:
        return []
    ranked = sorted(candidates, key=_selection_sort_key)
    selected: List[Dict[str, Any]] = []
    selected_ids: set[str] = set()

    def add(item: Dict[str, Any]) -> None:
        feature_id = str(item.get("feature_id") or "")
        if not feature_id or feature_id in selected_ids or len(selected) >= max_items:
            return
        selected.append(item)
        selected_ids.add(feature_id)

    for category in sorted({str(item.get("category") or "other") for item in ranked}):
        candidate = next(
            (item for item in ranked if str(item.get("category") or "other") == category),
            None,
        )
        if candidate:
            add(candidate)
    for sector in sorted({str(item.get("selection_sector") or "center") for item in ranked}):
        candidate = next(
            (item for item in ranked if str(item.get("selection_sector") or "center") == sector),
            None,
        )
        if candidate:
            add(candidate)
    subtype_counts = _counts(selected, "subtype")
    for item in ranked:
        subtype = str(item.get("subtype") or "other")
        if subtype_counts.get(subtype, 0) >= 2:
            continue
        before = len(selected)
        add(item)
        if len(selected) > before:
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
        if len(selected) >= max_items:
            break
    return selected


def summarize_source_status(
    *,
    overpass_status: Dict[str, Any],
    worldcover_status: Dict[str, Any],
    features: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    provider_counts = _provider_counts(features)
    public_count = sum(
        1
        for feature in features or []
        if _provider_of(feature) in PUBLIC_PROVIDERS
        and str(feature.get("source_kind") or "").strip().lower() in {"observed", "detected"}
    )
    contextual_providers = sorted(
        provider
        for provider, count in provider_counts.items()
        if count > 0 and provider in CONTEXTUAL_PROVIDERS
    )
    contextual_count = sum(provider_counts.get(provider, 0) for provider in contextual_providers)
    fallback_features = [
        feature
        for feature in features or []
        if (
            str(feature.get("source_kind") or "").strip().lower() == "reference"
            and _provider_of(feature) not in CONTEXTUAL_PROVIDERS
        )
        or _provider_of(feature) in FALLBACK_PROVIDERS
        or _provider_of(feature) not in PUBLIC_PROVIDERS | CONTEXTUAL_PROVIDERS
    ]
    fallback_providers = sorted({_provider_of(feature) for feature in fallback_features})
    fallback_count = len(fallback_features)
    overpass_ok = str(overpass_status.get("status") or "").lower() in {"completed", "ready", "cached"}
    worldcover_ok = str(worldcover_status.get("status") or "").lower() in {"completed", "ready", "cached"}
    worldcover_analytic_ok = worldcover_ok and str(
        worldcover_status.get("analysis_grade") or ""
    ).lower() not in {"contextual_only", "visualization_only"}

    if overpass_ok and worldcover_analytic_ok and public_count > 0:
        status = "complete"
    elif public_count > 0:
        status = "partial"
    else:
        status = "unavailable"

    provider_failures = summarize_provider_failures(
        overpass_status=overpass_status,
        worldcover_status=worldcover_status,
    )
    blocking_failures = [
        failure for failure in provider_failures if failure["required_for_formal_ready"]
    ]
    formal_ready = bool(public_count > 0)
    if formal_ready:
        availability = {
            "status": "ready",
            "available": True,
            "retryable": False,
            "reason_code": "formal_spatial_data_ready",
            "message": "已取得可用于正式空间判断的公开地理数据。",
            "provider_failures": provider_failures,
        }
    else:
        retryable = any(bool(item.get("retryable")) for item in blocking_failures)
        reason_code = (
            str(blocking_failures[0].get("reason_code") or "formal_provider_unavailable")
            if blocking_failures
            else "no_formal_features_selected"
        )
        availability = {
            "status": "unavailable",
            "available": False,
            "retryable": retryable,
            "reason_code": reason_code,
            "message": (
                "正式地理数据暂时不可用，可以重新获取。"
                if retryable
                else "当前没有取得可用于正式空间判断的地理数据。"
            ),
            "provider_failures": provider_failures,
        }

    return {
        "status": status,
        "formal_ready": formal_ready,
        "availability": availability,
        "retryable": bool(availability["retryable"]),
        "reason_code": availability["reason_code"],
        "provider_failures": provider_failures,
        "public_observation_available": bool(public_count > 0),
        "public_observation_feature_count": public_count,
        "contextual_feature_count": contextual_count,
        "contextual_providers": contextual_providers,
        "fallback_feature_count": fallback_count,
        "fallback_providers": fallback_providers,
        "provider_feature_counts": provider_counts,
        "providers": {
            "overpass": dict(overpass_status or {}),
            "worldcover": dict(worldcover_status or {}),
        },
        "warning": (
            "正式地理数据不可用；参考地点和背景数据仅保留为诊断记录，不得进入正式空间分析。"
            if public_count == 0
            else ""
        ),
    }


def summarize_provider_failures(
    *,
    overpass_status: Dict[str, Any],
    worldcover_status: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return [
        failure
        for failure in [
            _provider_failure(
                overpass_status,
                default_provider="osm_overpass",
                required_for_formal_ready=True,
            ),
            _provider_failure(
                worldcover_status,
                default_provider="worldcover_wms",
                required_for_formal_ready=False,
            ),
        ]
        if failure
    ]


def _provider_failure(
    status: Dict[str, Any],
    *,
    default_provider: str,
    required_for_formal_ready: bool,
) -> Dict[str, Any] | None:
    payload = dict(status or {})
    state = str(payload.get("status") or "unknown").strip().lower()
    if state in {"completed", "ready", "cached"}:
        return None

    raw_error = str(payload.get("error") or payload.get("live_error") or "").strip()
    reason_code, message, retryable = _classify_provider_failure(state, raw_error)
    return {
        "provider": str(payload.get("provider") or default_provider),
        "status": state or "unknown",
        "reason_code": reason_code,
        "message": message,
        "retryable": retryable,
        "required_for_formal_ready": bool(required_for_formal_ready),
        "error": raw_error,
        "attempts": list(payload.get("attempts") or []),
        "batches": list(payload.get("batches") or []),
    }


def _classify_provider_failure(state: str, raw_error: str) -> tuple[str, str, bool]:
    text = str(raw_error or "").strip().lower()
    if state == "empty":
        return "no_usable_features", "数据源响应正常，但本次范围内没有可用要素。", False
    if "no overpass endpoint configured" in text or "not configured" in text:
        return "provider_not_configured", "空间数据源尚未配置。", False
    if "out of memory" in text or "maxsize" in text or "resource limit" in text:
        return "query_resource_limit", "空间查询超过上游资源限制。", False
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return "rate_limited", "空间数据源请求过于频繁。", True
    if "timeout" in text or "timed out" in text or "504" in text:
        return "timeout", "空间数据源请求超时。", True
    if any(token in text for token in ("502", "503", "temporarily unavailable", "service unavailable")):
        return "upstream_unavailable", "空间数据源暂时不可用。", True
    if any(token in text for token in ("connection", "remote end", "reset by peer", "network")):
        return "network_error", "连接空间数据源时网络中断。", True
    if "invalid payload" in text or "invalid response" in text:
        return "invalid_response", "空间数据源返回了无法解析的响应。", True
    if state in {"failed", "unknown"}:
        return "provider_failed", "空间数据源未能返回可用数据。", True
    return "provider_unavailable", "空间数据源当前不可用。", False


def is_valid_proxy_anchor(proxy_role: str, feature: Dict[str, Any]) -> bool:
    """Return whether a spatial feature is valid evidence for a proxy location."""

    role = str(proxy_role or "").strip().lower()
    subtype = str(feature.get("subtype") or "").strip().lower()
    category = str(feature.get("category") or "").strip().lower()
    tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
    provider = str(tags.get("provider") or feature.get("source_provider") or "").strip().lower()

    if subtype == "weather_baseline":
        return False
    explicit_population_anchor = role in {"vulnerable_groups", "residents"} and bool(
        tags.get("population_evidence")
    )
    if provider not in PUBLIC_PROVIDERS and not explicit_population_anchor:
        return False
    if role == "vulnerable_groups":
        if bool(tags.get("population_evidence")):
            return True
        return subtype in {
            "residential",
            "hospital",
            "school",
            "university",
            "community_centre",
            "social_facility",
            "worldcover_50",
        }
    if role == "residents":
        return subtype in {
            "residential",
            "commercial_hub",
            "hospital",
            "school",
            "university",
            "worldcover_50",
        }
    if role == "regulators":
        return subtype in {"townhall", "police", "fire_station", "government", "office_cluster"}
    if role == "maintainers":
        return category in {"facility", "ecology"} and subtype not in {"weather_baseline"}
    return True


def _extract_focus_terms(
    context: SelectionContext,
    features: Sequence[Dict[str, Any]],
) -> List[str]:
    text = context.explicit_focus_text
    normalized_text = _normalize_text(text)
    terms: List[str] = []

    def add(value: Any) -> None:
        token = str(value or "").strip(" ，。；、:：/|-_\n\t")
        if (
            len(token) < 2
            or token in GENERIC_FOCUS_PHRASES
            or token in terms
            or _mention_intent_signal(token, normalized_text) < 0
        ):
            return
        terms.append(token)

    for match in PLACE_SUFFIX_PATTERN.findall(text):
        add(match)

    for feature in features or []:
        name = str(feature.get("name") or "").strip()
        if len(name) >= 2 and _normalize_text(name) in normalized_text:
            add(name)
        tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
        for key in ["addr:city", "addr:district", "city", "district", "local_context"]:
            value = str(tags.get(key) or "").strip()
            if value and _normalize_text(value) in normalized_text:
                add(value)
        for alias in _administrative_aliases(
            [name, tags.get("addr:city"), tags.get("addr:district"), tags.get("city"), tags.get("district")]
        ):
            signal, _reason = _administrative_focus_signal(alias, normalized_text)
            if signal > 0:
                add(alias)

    return terms[:20]


def _focus_score(
    feature: Dict[str, Any],
    *,
    normalized_user_text: str,
    focus_terms: Sequence[str],
) -> tuple[float, List[str], bool]:
    name = str(feature.get("name") or "").strip()
    normalized_name = _normalize_text(name)
    tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
    haystack = _normalize_text(
        " ".join(
            [
                name,
                str(feature.get("summary") or ""),
                str(feature.get("subtype") or ""),
                str(feature.get("category") or ""),
                " ".join(f"{key} {value}" for key, value in tags.items()),
            ]
        )
    )
    score = 0.0
    reasons: List[str] = []
    direct_focus = False
    name_admin_aliases = {_normalize_text(alias) for alias in _administrative_aliases([name])}
    tag_admin_aliases = {
        _normalize_text(alias)
        for alias in _administrative_aliases(
            [tags.get("addr:city"), tags.get("addr:district"), tags.get("city"), tags.get("district")]
        )
    }
    if normalized_name and normalized_name in normalized_user_text:
        if _mention_intent_signal(normalized_name, normalized_user_text) < 0:
            score -= 70.0
            reasons.append("仅为范围/排除项")
        else:
            score += 100.0
            reasons.append("用户输入直接点名")
            direct_focus = True
    # A feature label may be more specific than the user's place phrase, e.g.
    # ``深圳福田区应急医院`` vs ``深圳福田区``.  Preserve the named administrative
    # or geographic prefix instead of requiring the full POI label to match.
    for place_token in PLACE_SUFFIX_PATTERN.findall(name):
        normalized_place = _normalize_text(place_token)
        if (
            len(normalized_place) >= 3
            and normalized_place in normalized_user_text
            and _mention_intent_signal(normalized_place, normalized_user_text) >= 0
        ):
            score += 60.0
            reasons.append(f"匹配地点前缀:{place_token}")
            direct_focus = True
    for term in focus_terms:
        normalized_term = _normalize_text(term)
        if not normalized_term:
            continue
        if _mention_intent_signal(normalized_term, normalized_user_text) < 0:
            continue
        if normalized_term in haystack or (normalized_name and normalized_name in normalized_term):
            score += 24.0
            reasons.append(f"匹配关注地点:{term}")
            if normalized_name and (
                normalized_term in normalized_name or normalized_name in normalized_term
            ):
                is_address_scope_only = (
                    normalized_term in tag_admin_aliases
                    and normalized_term not in name_admin_aliases
                )
                if not is_address_scope_only:
                    direct_focus = True
    # An administrative alias in address tags scopes a POI to the focused
    # city/district, but it does not mean the user directly named that POI.
    # Only an administrative node whose own name carries the alias may use the
    # macro-granularity bypass.
    for alias in _administrative_aliases([name]):
        alias_score, alias_reason = _administrative_focus_signal(alias, normalized_user_text)
        if alias_score == 0:
            continue
        score += alias_score
        reasons.append(alias_reason)
        if alias_score > 0:
            direct_focus = True
    for alias in _administrative_aliases(
        [tags.get("addr:city"), tags.get("addr:district"), tags.get("city"), tags.get("district")]
    ):
        alias_score, alias_reason = _administrative_focus_signal(alias, normalized_user_text)
        if alias_score == 0:
            continue
        score += alias_score
        reasons.append(f"焦点行政范围:{alias_reason}")
    return score, list(dict.fromkeys(reasons)), direct_focus


def _administrative_aliases(values: Iterable[Any]) -> List[str]:
    aliases: List[str] = []
    suffixes = ("特别行政区", "自治区", "自治州", "地区", "市", "区", "县")
    for value in values:
        token = str(value or "").strip()
        for suffix in suffixes:
            if not token.endswith(suffix):
                continue
            alias = token[: -len(suffix)].strip()
            if len(alias) >= 2 and alias not in aliases:
                aliases.append(alias)
            break
    return aliases


def _administrative_focus_signal(alias: str, normalized_user_text: str) -> tuple[float, str]:
    normalized_alias = _normalize_text(alias)
    if not normalized_alias or normalized_alias not in normalized_user_text:
        return 0.0, ""
    intent_signal = _mention_intent_signal(normalized_alias, normalized_user_text)
    if intent_signal > 0:
        return 90.0, f"匹配行政简称重点:{alias}"
    if intent_signal < 0:
        return -70.0, f"仅为范围/排除项:{alias}"
    return 36.0, f"匹配行政简称:{alias}"


def _mention_intent_signal(token: str, normalized_user_text: str) -> int:
    normalized_token = _normalize_text(token)
    clauses = [
        clause
        for clause in re.split(r"[，,。；;]|但是|不过|然而", normalized_user_text)
        if normalized_token and normalized_token in clause
    ]
    if any(any(cue in clause for cue in FOCUS_CUES) for clause in clauses):
        return 1
    if any(any(cue in clause for cue in SCOPE_ONLY_CUES) for clause in clauses):
        return -1
    return 0


def _scenario_score(feature: Dict[str, Any], normalized_user_text: str) -> tuple[float, List[str]]:
    subtype = str(feature.get("subtype") or "").lower()
    category = str(feature.get("category") or "").lower()
    score = 0.0
    reasons: List[str] = []
    mappings = [
        ({"台风", "暴雨", "洪水", "风暴潮", "storm", "typhoon", "flood"}, {"water", "river", "wetland", "coastline", "reservoir", "road_corridor", "hospital"}),
        ({"污染", "废水", "核", "排放", "pollution", "wastewater"}, {"water", "river", "wetland", "reservoir", "wastewater_plant", "industrial"}),
        ({"高温", "热浪", "heat"}, {"residential", "hospital", "school", "park", "worldcover_50", "worldcover_10"}),
        ({"交通", "疏散", "物流", "airport", "transport"}, {"road_corridor", "rail_station", "airport", "transit_stop", "hospital"}),
        ({"生态", "湿地", "栖息地", "ecology", "habitat"}, {"wetland", "protected_area", "forest", "park", "worldcover_10", "worldcover_90", "worldcover_95"}),
    ]
    for text_tokens, subtype_tokens in mappings:
        if not any(_normalize_text(token) in normalized_user_text for token in text_tokens):
            continue
        if subtype in subtype_tokens or category in subtype_tokens:
            score += 8.0
            reasons.append("匹配推演机制")
    return score, list(dict.fromkeys(reasons))


def _scope_score(feature: Dict[str, Any], normalized_scope_text: str) -> float:
    """Use the selected location as a weak scope signal, never as explicit focus."""
    if not normalized_scope_text:
        return 0.0
    name = _normalize_text(feature.get("name"))
    tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
    scope_haystack = _normalize_text(
        " ".join(
            [
                name,
                str(tags.get("addr:city") or ""),
                str(tags.get("addr:district") or ""),
                str(tags.get("city") or ""),
                str(tags.get("district") or ""),
                str(tags.get("local_context") or ""),
            ]
        )
    )
    if name and name in normalized_scope_text:
        return 5.0
    if scope_haystack and any(
        len(token) >= 2 and token in normalized_scope_text
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9·]{2,24}", scope_haystack)
    ):
        return 2.0
    return 0.0


def _allowed_for_granularity(feature: Dict[str, Any], *, granularity: str, explicit_focus: bool) -> bool:
    if granularity != "city_region":
        return True
    if bool(feature.get("selection_direct_focus")):
        return True
    return _spatial_level(feature) in {"city", "district", "region", "macro"}


def _spatial_level(feature: Dict[str, Any]) -> str:
    direct = str(feature.get("spatial_level") or "").strip().lower()
    if direct:
        return direct
    tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
    tagged = str(tags.get("spatial_level") or "").strip().lower()
    if tagged:
        return tagged
    subtype = str(feature.get("subtype") or "").strip().lower()
    if subtype in {"admin_city"}:
        return "city"
    if subtype in {"admin_district"}:
        return "district"
    if subtype in {"subdistrict"}:
        return "street"
    if subtype in {"coastline", "river", "water", "wetland", "protected_area"}:
        return "region"
    return "site"


def _spatial_rank(spatial_level: Any) -> int:
    normalized = str(spatial_level or "").strip().lower()
    if normalized in {"aoi", "city", "macro"}:
        return 0
    if normalized in {"district", "region", "corridor", "basin", "coastal_belt"}:
        return 1
    if normalized in {"street", "subdistrict", "community", "functional_zone"}:
        return 2
    if normalized in {"site", "facility", "institution", "poi"}:
        return 3
    if normalized in {"unit", "subsite", "internal_unit", "population_segment", "resource_pool"}:
        return 4
    return 3


def _source_quality_score(feature: Dict[str, Any]) -> float:
    provider = _provider_of(feature)
    source_kind = str(feature.get("source_kind") or "").strip().lower()
    if provider in FALLBACK_PROVIDERS or source_kind == "reference":
        return -2.0
    if provider in CONTEXTUAL_PROVIDERS:
        return -1.0
    if source_kind == "observed":
        return 4.0
    if source_kind == "detected":
        return 3.0
    return 0.0


def _distance_score(feature: Dict[str, Any], radius_m: int) -> float:
    radius = max(float(radius_m or 0), 1.0)
    distance = max(0.0, float(feature.get("distance_m") or 0))
    return max(0.0, 1.0 - distance / radius) * 3.0


def _sector_for(feature: Dict[str, Any], context: SelectionContext) -> str:
    lat = float(feature.get("lat"))
    lon = float(feature.get("lon"))
    distance = _haversine_m(context.center_lat, context.center_lon, lat, lon)
    if distance <= max(600.0, float(context.radius_m or 0) * 0.08):
        return "center"
    dx = (lon - context.center_lon) * math.cos(math.radians(context.center_lat))
    dy = lat - context.center_lat
    angle = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
    labels = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
    return labels[int(((angle + 22.5) % 360.0) // 45.0)]


def _selection_sort_key(item: Dict[str, Any]) -> tuple[float, float, float, str]:
    return (
        -float(item.get("selection_focus_score") or 0),
        -float(item.get("selection_score") or 0),
        float(item.get("distance_m") or 0),
        str(item.get("name") or ""),
    )


def _counts(items: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for item in items:
        token = str(item.get(key) or "other")
        result[token] = result.get(token, 0) + 1
    return result


def _provider_counts(features: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for feature in features or []:
        provider = _provider_of(feature)
        result[provider] = result.get(provider, 0) + 1
    return result


def _provider_of(feature: Dict[str, Any]) -> str:
    tags = feature.get("tags") if isinstance(feature.get("tags"), dict) else {}
    provider = str(tags.get("provider") or feature.get("provider") or "").strip().lower()
    if provider:
        return provider
    feature_id = str(feature.get("feature_id") or "").lower()
    if feature_id.startswith(("node_", "way_", "relation_")):
        return "overpass"
    return "unknown"


def _has_coordinates(feature: Dict[str, Any]) -> bool:
    try:
        float(feature.get("lat"))
        float(feature.get("lon"))
        return True
    except (TypeError, ValueError):
        return False


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(1e-12, 1 - value)))
