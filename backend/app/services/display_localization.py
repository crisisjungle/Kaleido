"""Public DTO display-text localization.

Simulation artifacts intentionally contain machine identifiers and enums.  They
are useful to callers, but legacy artifacts also placed those values in fields
that the frontend renders as prose.  This module keeps the machine contract
intact while making every public display field safe to render in the Chinese
workflow UI.

The projection is deliberately applied only at API/service response boundaries;
stored artifacts are not rewritten and internal matching continues to use the
original identifiers.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple


# Exact machine fields plus suffixes are preserved verbatim.  Nested dictionaries
# are still traversed so their own display fields are localized.
MACHINE_FIELD_NAMES = {
    "id",
    "uuid",
    "key",
    "type",
    "status",
    "code",
    "mode",
    "source",
    "target",
    "tab",
    "platform",
    "labels",
    "scope_basis",
    "primary_region",
    "artifact_name",
    "provenance",
    "evidence_ref",
    "evidence_refs",
}
MACHINE_FIELD_SUFFIXES = (
    "_id",
    "_ids",
    "_uuid",
    "_uuids",
    "_key",
    "_keys",
    "_type",
    "_types",
    "_status",
    "_code",
    "_mode",
)

PRIVATE_FIELD_NAMES = {
    "traceback",
    "stack",
    "stacktrace",
    "exception",
    "debug",
    "semantic_audit",
    "semantic_audit_record",
    "fallback_mode",
    "fallback_reason",
    "processing_mode",
    "repair_attempted",
}

# These fields (including compound forms such as ``source_node_name``) are
# rendered by Step 3 / Step 4 and must never expose an internal token directly.
DISPLAY_FIELD_NAMES = {
    "name",
    "title",
    "label",
    "summary",
    "description",
    "message",
    "error",
    "reason",
    "rationale",
    "note",
    "notes",
    "fact",
    "relation_label",
    "relation_labels",
    "trigger_conditions",
    "headline",
    "narrative",
    "caption",
    "display_name",
    "display_label",
    "content",
    "markdown_content",
    "report_markdown",
    "report_text",
    "text",
    "response",
    "explanation",
    "conclusion",
    "recommendation",
    "recommendations",
    "impact",
    "impacts",
    "loop",
    "turning_points",
    "quality_flags",
    "current_section",
    "risk_statement",
    "outcome",
    "governance_response",
    "friction_points",
    "turning_point",
    "detected_feedback_loops",
    "expected_direct_effects",
    "expected_second_order_effects",
    "source_actor_names",
    "extracted_facts",
    "errors",
    "username",
    "reasoning",
    "reasoning_summary",
    "generation_reasoning",
    "assumption",
    "assumptions",
    "warning",
    "warnings",
    "projection_warnings",
    "goal",
    "goals",
    "sensitivity",
    "sensitivities",
    "bio",
    "persona",
    "motivation",
    "missing_data",
}
DISPLAY_FIELD_SUFFIXES = (
    "_name",
    "_title",
    "_label",
    "_labels",
    "_summary",
    "_description",
    "_message",
    "_reason",
    "_rationale",
    "_note",
    "_fact",
    "_headline",
    "_narrative",
    "_caption",
    "_content",
    "_reasoning",
    "_warning",
    "_warnings",
)


KNOWN_DISPLAY_TERMS = {
    "crisis_mode": "灾难态",
    "baseline_mode": "基线态",
    "marine_current": "海洋环流",
    "generic": "通用",
    "disaster_injection": "灾害扰动",
    "policy_injection": "政策干预",
    "disaster": "灾害事件",
    "policy": "政策干预",
    "transit_stop": "交通站点",
    "environmental_monitoring": "环境监测",
    "information_release": "信息发布",
    "panic_post": "生态压力信号",
    "envfish_summary": "推演摘要",
    "envfish_spread_forecast": "扩散预测",
    "envfish_vulnerability_ranking": "脆弱性排序",
    "envfish_intervention_comparison": "干预对比",
    "envfish_feedback_summary": "反馈摘要",
    "restrict": "限制干预",
    "disclose": "信息公开",
    "agent": "代理体",
    "agents": "代理体",
    "node": "节点",
    "nodes": "节点",
    "object": "对象",
    "objects": "对象",
    "region": "区域",
    "regions": "区域",
    "entity": "实体",
    "entities": "实体",
    "risk": "风险",
    "relation": "关系",
    "related": "关联",
    "related_to": "关联",
    "located_in": "位于",
    "impacts_actor": "影响对象",
    "reports_to": "上报给",
    "depends_on": "依赖",
    "coordinates_with": "协同",
    "administrativeregion": "行政区域",
    "administrative_region": "行政区域",
    "governanceactor": "治理主体",
    "governance_actor": "治理主体",
    "riskobject": "风险对象",
    "risk_object": "风险对象",
    "populationgroup": "人群",
    "population_group": "人群",
    "criticalinfrastructure": "关键基础设施",
    "critical_infrastructure": "关键基础设施",
    "naturalforce": "自然作用",
    "natural_force": "自然作用",
    "ecosystem": "生态系统",
    "governance": "治理",
    "organization": "组织",
    "human": "个体",
    "watch": "关注中",
    "active": "活跃",
    "resolved": "已缓解",
}

_FIELD_FALLBACKS = {
    "title": "未命名条目",
    "label": "其他",
    "summary": "暂无摘要",
    "description": "暂无说明",
    "message": "暂无补充说明",
    "error": "服务暂时不可用，请稍后重试。",
    "reason": "暂无原因说明",
    "rationale": "暂无依据说明",
    "note": "暂无说明",
    "notes": "暂无说明",
    "fact": "关系事实待确认",
    "relation_label": "关联",
    "relation_labels": "关联",
    "trigger_conditions": "触发条件待确认",
    "headline": "暂无可展示内容",
    "narrative": "暂无可展示内容",
    "caption": "暂无说明",
    "content": "暂无可展示内容",
    "text": "暂无可展示内容",
    "response": "暂无可展示内容",
    "explanation": "暂无说明",
    "conclusion": "暂无结论",
    "recommendation": "暂无建议",
    "recommendations": "暂无建议",
    "impact": "影响待确认",
    "impacts": "影响待确认",
    "loop": "反馈关系待确认",
    "turning_points": "关键变化待确认",
    "quality_flags": "需进一步核验",
    "current_section": "正在整理结果",
    "risk_statement": "风险陈述待确认",
    "outcome": "结果待确认",
    "governance_response": "治理响应待确认",
    "friction_points": "关键阻力待确认",
    "turning_point": "关键变化待确认",
    "detected_feedback_loops": "反馈关系待确认",
    "expected_direct_effects": "直接影响待确认",
    "expected_second_order_effects": "次生影响待确认",
    "source_actor_names": "未命名代理体",
    "extracted_facts": "关系事实待确认",
    "errors": "服务暂时不可用，请稍后重试。",
    "username": "未命名代理体",
    "reasoning": "暂无推理说明",
    "reasoning_summary": "暂无推理说明",
    "generation_reasoning": "暂无生成说明",
    "assumption": "规划假设待确认",
    "assumptions": "规划假设待确认",
    "warning": "需进一步核验",
    "warnings": "需进一步核验",
    "projection_warnings": "需进一步核验",
    "goal": "目标待确认",
    "goals": "目标待确认",
    "sensitivity": "关注因素待确认",
    "sensitivities": "关注因素待确认",
    "bio": "暂无画像说明",
    "persona": "暂无画像说明",
    "motivation": "暂无动机说明",
    "missing_data": "待补充数据",
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_PREFIXED_ID_RE = re.compile(
    r"^(?:sim|risk|region|agent|node|object|edge|mech|feature|context|report|graph)"
    r"[_:\-][A-Za-z0-9_\u3400-\u9fff.:\-]+$",
    re.IGNORECASE,
)
_INLINE_PREFIXED_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:sim|risk|region|agent|node|object|edge|mech|feature|context|report|graph)"
    r"[_:\-][A-Za-z0-9_\u3400-\u9fff.:\-]+"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_SHORT_ID_RE = re.compile(r"^(?:R|S|A|N)\d{1,6}$", re.IGNORECASE)
_INLINE_SHORT_ID_RE = re.compile(r"\b(?:R|S|A|N)\d{1,6}\b", re.IGNORECASE)
_AGENT_NUMBER_RE = re.compile(r"^Agent\s*#?\s*\d+$", re.IGNORECASE)
_INLINE_AGENT_NUMBER_RE = re.compile(r"\bAgent\s*#?\s*\d+\b", re.IGNORECASE)
_CLASS_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:Agent|Node|Object|Region)$")
_INLINE_CLASS_NAME_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:Agent|Node|Object|Region)\b")
_SNAKE_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$")
_INLINE_SNAKE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9_])"
)
_ALPHANUMERIC_ID_RE = re.compile(r"^[A-Za-z]+\d+[A-Za-z0-9_.:\-]*$")
_NUMERIC_DISPLAY_RE = re.compile(r"^[\d\s.%‰+\-]+$")
_PUNCTUATION_ONLY_RE = re.compile(r"^[\s,.;:：|/\\\-=<>→←()（）\[\]{}]+$")
_URL_RE = re.compile(r"^(?:https?://|www\.)", re.IGNORECASE)
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{3,}")
_ALLOWED_MIXED_TEXT_TOKENS = {
    "csv",
    "epa",
    "json",
    "kaleido",
    "noaa",
    "osm",
    "pdf",
    "usgs",
    "wms",
}

_MARKDOWN_DISPLAY_FIELDS = {"markdown_content", "report_markdown", "report_text"}
_TECHNICAL_ERROR_RE = re.compile(
    r"(?:Traceback|[A-Za-z]+(?:Error|Exception)|\b(?:GET|POST|PUT|PATCH|DELETE)\b|"
    r"/api/|https?://|\b(?:\d{1,3}\.){3}\d{1,3}\b|"
    r"/(?:tmp|var|private|Users|home|opt|srv|app|etc)/|\\(?:Users|Windows)\\)",
    re.IGNORECASE,
)
_INTERNAL_NARRATION_RE = re.compile(
    r"^(?:好的[，,]?|现在信息已经足够[。！!]?|您说得对[，,]?|让我|接下来)"
    r".*(?:工具调用|调用.{0,12}工具|我将|让我|撰写|生成.{0,8}章节)",
)


def _normalized_field_name(field_name: Any) -> str:
    return str(field_name or "").strip().lower()


def is_machine_field(field_name: Any) -> bool:
    """Return whether a field is part of the machine-facing contract."""

    key = _normalized_field_name(field_name)
    return key in MACHINE_FIELD_NAMES or key.endswith(MACHINE_FIELD_SUFFIXES)


def is_display_field(field_name: Any) -> bool:
    """Return whether a field can be rendered as human-facing text."""

    key = _normalized_field_name(field_name)
    return key in DISPLAY_FIELD_NAMES or key.endswith(DISPLAY_FIELD_SUFFIXES)


def _is_route_descriptor(value: Any) -> bool:
    """Return whether a mapping is a frontend router location contract.

    Router names are machine keys even though the generic field name ``name``
    is normally display copy.  Treating ``SimulationRun`` as prose breaks the
    route before the frontend can render the localized page.
    """

    return bool(
        isinstance(value, Mapping)
        and isinstance(value.get("name"), str)
        and isinstance(value.get("query"), Mapping)
        and ("params" not in value or isinstance(value.get("params"), Mapping))
    )


def _base_display_field(field_name: str) -> str:
    key = _normalized_field_name(field_name)
    if key in DISPLAY_FIELD_NAMES:
        return key
    for suffix in DISPLAY_FIELD_SUFFIXES:
        if key.endswith(suffix):
            return suffix[1:]
    return key


def _infer_name_fallback(raw_text: str, owner: Optional[Mapping[str, Any]]) -> str:
    hints: List[str] = [raw_text]
    if owner:
        hints.extend(str(key) for key in owner.keys())
        for key in ("type", "node_type", "agent_type", "object_type", "labels"):
            value = owner.get(key)
            if isinstance(value, list):
                hints.extend(str(item or "") for item in value)
            elif value is not None:
                hints.append(str(value))
    hint = " ".join(hints).lower()
    if "risk" in hint:
        return "未命名风险对象"
    if "agent" in hint or "actor" in hint:
        return "未命名代理体"
    if "region" in hint or "district" in hint:
        return "未命名区域"
    if "relation" in hint or "edge" in hint:
        return "未命名关系"
    if "node" in hint:
        return "未命名节点"
    if "object" in hint or "entity" in hint:
        return "未命名对象"
    return "未命名对象"


def _fallback_for(field_name: str, raw_text: str, owner: Optional[Mapping[str, Any]]) -> str:
    base = _base_display_field(field_name)
    if base in {"name", "display_name", "username"}:
        return _infer_name_fallback(raw_text, owner)
    if base == "display_label":
        return "其他"
    return _FIELD_FALLBACKS.get(base, "暂无可展示内容")


def _translate_exact_term(text: str) -> Optional[str]:
    normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
    return KNOWN_DISPLAY_TERMS.get(normalized) or KNOWN_DISPLAY_TERMS.get(
        normalized.replace("_", "")
    )


def _class_name_replacement(match: re.Match[str]) -> str:
    token = match.group(0)
    lowered = token.lower()
    if lowered.endswith("agent"):
        return "相关代理体"
    if lowered.endswith("region"):
        return "相关区域"
    if lowered.endswith("node"):
        return "相关节点"
    if lowered.endswith("object"):
        return "相关对象"
    return "相关对象"


def _snake_token_replacement(match: re.Match[str]) -> str:
    token = match.group(0)
    translated = _translate_exact_term(token)
    return translated or "相关项"


def _looks_like_internal_identifier(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return bool(
        _UUID_RE.fullmatch(stripped)
        or _PREFIXED_ID_RE.fullmatch(stripped)
        or _SHORT_ID_RE.fullmatch(stripped)
        or _AGENT_NUMBER_RE.fullmatch(stripped)
        or _CLASS_NAME_RE.fullmatch(stripped)
        or _SNAKE_TOKEN_RE.fullmatch(stripped)
        or _ALPHANUMERIC_ID_RE.fullmatch(stripped)
        or _NUMERIC_DISPLAY_RE.fullmatch(stripped)
        or _PUNCTUATION_ONLY_RE.fullmatch(stripped)
        or _URL_RE.match(stripped)
    )


def _looks_latin_dominant(text: str) -> bool:
    latin_count = len(re.findall(r"[A-Za-z]", text))
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    if latin_count == 0:
        return False
    if cjk_count == 0:
        return True
    return latin_count >= 8 and latin_count > cjk_count


def has_display_text_leak(value: Any) -> bool:
    """Return whether one already-projected display string is still unsafe."""

    text = str(value or "").strip()
    if not text:
        return False
    structural_leak = bool(
        _looks_like_internal_identifier(text)
        or _INLINE_PREFIXED_ID_RE.search(text)
        or _INLINE_AGENT_NUMBER_RE.search(text)
        or _INLINE_SHORT_ID_RE.search(text)
        or _INLINE_CLASS_NAME_RE.search(text)
        or _INLINE_SNAKE_TOKEN_RE.search(text)
        or _looks_latin_dominant(text)
    )
    if structural_leak:
        return True
    if re.search(r"[\u3400-\u9fff]", text):
        return any(
            token.lower() not in _ALLOWED_MIXED_TEXT_TOKENS
            for token in _LATIN_TOKEN_RE.findall(text)
        )
    return False


def sanitize_display_text(
    value: Any,
    *,
    field_name: str,
    owner: Optional[Mapping[str, Any]] = None,
) -> Any:
    """Sanitize one scalar from a known display field.

    Non-string scalars are left untouched.  Empty strings stay empty to avoid
    manufacturing UI copy where the artifact intentionally omitted a value.
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value).strip()
    if not text:
        return ""

    exact = _translate_exact_term(text)
    if exact:
        return exact

    fallback = _fallback_for(field_name, text, owner)
    if _looks_like_internal_identifier(text):
        return fallback

    localized = _INLINE_AGENT_NUMBER_RE.sub("相关代理体", text)
    localized = _INLINE_PREFIXED_ID_RE.sub("相关对象", localized)
    localized = _INLINE_SHORT_ID_RE.sub("相关区域", localized)
    localized = _INLINE_CLASS_NAME_RE.sub(_class_name_replacement, localized)
    localized = _INLINE_SNAKE_TOKEN_RE.sub(_snake_token_replacement, localized)

    # Replace common standalone backend nouns inside otherwise useful Chinese
    # prose.  Longer terms are handled before shorter ones to avoid fragments.
    word_replacements = {
        "Step 1": "第一步",
        "Step 2": "第二步",
        "Step 3": "第三步",
        "Step 4": "第四步",
        "Risk Object": "风险对象",
        "RiskObject": "风险对象",
        "AdministrativeRegion": "行政区域",
        "GovernanceActor": "治理主体",
        "EnvFish": "Kaleido",
        "Agent": "代理体",
        "Node": "节点",
        "Entity": "实体",
        "Region": "区域",
        "Object": "对象",
    }
    for token, label in word_replacements.items():
        localized = re.sub(rf"\b{re.escape(token)}\b", label, localized, flags=re.IGNORECASE)

    # Useful Chinese prose should not collapse to a generic placeholder merely
    # because a legacy artifact contains an unknown English alias. Known terms
    # are translated above; remaining Latin tokens are removed only when the
    # surrounding text still carries Chinese business meaning.
    if re.search(r"[\u3400-\u9fff]", localized):
        localized = re.sub(
            r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9-]*(?![A-Za-z0-9_])",
            lambda match: (
                match.group(0)
                if match.group(0).lower() in _ALLOWED_MIXED_TEXT_TOKENS
                else (_translate_exact_term(match.group(0)) or "")
            ),
            localized,
        )

    localized = re.sub(r"\s+", " ", localized).strip(" \t\r\n,，;；")
    localized = re.sub(r"([\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", r"\1", localized)
    if not localized or has_display_text_leak(localized):
        return fallback
    return localized


def _sanitize_markdown_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    if _INTERNAL_NARRATION_RE.search(stripped):
        return ""
    compact = re.sub(r"\s+", "", stripped)
    if re.fullmatch(r"(?:-{3,}|\*{3,}|_{3,})", compact):
        return stripped
    if "|" in stripped and re.fullmatch(r"[:|\-\s]+", stripped) and re.search(r"-{3,}", stripped):
        return line.rstrip()
    if re.match(r"^</?[A-Za-z][^>]*>$", stripped):
        return ""
    if re.match(r"^[\"']?[A-Za-z_][A-Za-z0-9_-]*[\"']?\s*:\s*", stripped):
        return ""
    if re.fullmatch(r"[{}\[\],]+", stripped):
        return ""

    # Preserve the human-readable citation label before removing the raw URL.
    # Otherwise a Markdown link degrades into visible fragments such as
    # ``[来源标题](`` in the formal report and printed PDF.
    localized = re.sub(
        r"!?\[([^\]]+)\]\((?:https?://|www\.)[^)\s]+\)",
        r"\1",
        line,
        flags=re.IGNORECASE,
    )
    localized = re.sub(r"https?://\S+", "", localized, flags=re.IGNORECASE)
    localized = re.sub(r"/(?:api|v\d+)/[A-Za-z0-9_./?=&%:\-]+", "", localized, flags=re.IGNORECASE)
    localized = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:/\S*)?", "", localized)
    localized = re.sub(
        r"/(?:tmp|var|private|Users|home|opt|srv|app|etc)(?:/[^\s\"'`)<>{}\]]+)+",
        "",
        localized,
        flags=re.IGNORECASE,
    )
    localized = re.sub(r"\[(?:Errno|Error)?\s*\d+\]", "", localized, flags=re.IGNORECASE)
    localized = re.sub(r"</?[A-Za-z][^>]*>", "", localized)

    replacements = {
        "crisis_mode": "灾难态",
        "baseline_mode": "基线态",
        "marine_current": "海洋环流",
        "disaster_injection": "灾害扰动",
        "policy_injection": "政策干预",
        "disaster": "灾害事件",
        "policy": "政策干预",
        "generic": "通用",
        "transit_stop": "交通站点",
        "environmental_monitoring": "环境监测",
        "information_release": "信息发布",
        "PANIC_POST": "生态压力信号",
        "envfish_summary": "推演摘要",
        "envfish_spread_forecast": "扩散预测",
        "envfish_vulnerability_ranking": "脆弱性排序",
        "envfish_intervention_comparison": "干预对比",
        "envfish_feedback_summary": "反馈摘要",
        "RESTRICT": "限制干预",
        "DISCLOSE": "信息公开",
        "EnvFish": "Kaleido",
    }
    for token, label in replacements.items():
        localized = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])",
            label,
            localized,
            flags=re.IGNORECASE,
        )
    localized = re.sub(r"(?<![A-Za-z0-9_])vs\.?(?![A-Za-z0-9_])", "与", localized, flags=re.IGNORECASE)
    localized = re.sub(r"(?<![A-Za-z0-9_])Agents?(?![A-Za-z0-9_])", "代理体", localized, flags=re.IGNORECASE)

    localized = _INLINE_AGENT_NUMBER_RE.sub("相关代理体", localized)
    localized = _INLINE_PREFIXED_ID_RE.sub("", localized)
    localized = _INLINE_SHORT_ID_RE.sub("", localized)
    localized = _INLINE_CLASS_NAME_RE.sub(_class_name_replacement, localized)
    localized = re.sub(
        r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+(?![A-Za-z0-9_])",
        lambda match: _translate_exact_term(match.group(0)) or "",
        localized,
    )

    def replace_latin(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.lower() in _ALLOWED_MIXED_TEXT_TOKENS:
            return token
        return _translate_exact_term(token) or ""

    localized = re.sub(
        r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*(?![A-Za-z0-9_])",
        replace_latin,
        localized,
    )
    localized = re.sub(r"[\"']?[\\/]{2,}[^\s，。；：！？、]*", "", localized)
    localized = re.sub(r"([:：])(?:\s*[:：])+", r"\1", localized)
    localized = re.sub(r"[ \t]+\.[ \t]+", " ", localized)
    localized = re.sub(r"[:：][ \t]*[\"']{1,2}[ \t]*$", "", localized)
    localized = re.sub(
        r"[（(]\s*(?:模拟(?:ID)?\s*[:：])?\s*[）)]",
        "",
        localized,
        flags=re.IGNORECASE,
    )
    localized = re.sub(
        r"包含(?:\s|、|，|,|以及)+等关键节点",
        "包含当前分析范围内的关键节点",
        localized,
    )
    localized = re.sub(
        r"目标区域[（(](?:\s|、|，|,)*[）)]",
        "目标区域（当前分析范围）",
        localized,
    )
    localized = re.sub(
        r"目标节点[（(](?:\s|、|，|,)*[）)]",
        "目标节点（相关执行主体）",
        localized,
    )
    localized = localized.replace("生态压力信号信号", "生态压力信号")
    localized = re.sub(r"[ \t]{2,}", " ", localized)
    localized = re.sub(r"[ \t]+([，。；：！？、])", r"\1", localized)
    localized = re.sub(r"([\u3400-\u9fff])[ \t]+(?=[\u3400-\u9fff])", r"\1", localized)
    localized = localized.rstrip()

    semantic = re.sub(
        r"[\s\d.,，。；;：:！？!?、()（）\[\]{}'\"`~_*+=<>|\\/→←–—%‰#>+\-]+",
        "",
        localized,
    )
    if not semantic:
        return ""
    if re.search(r"[\u3400-\u9fff]", semantic):
        return localized
    if semantic.lower() in _ALLOWED_MIXED_TEXT_TOKENS:
        return localized
    return ""


def sanitize_display_markdown(
    value: Any,
    *,
    field_name: str,
    owner: Optional[Mapping[str, Any]] = None,
) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"<tool_calls?\b[^>]*>[\s\S]*?</tool_calls?>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"```[\s\S]*?```", "", text)
    lines = [_sanitize_markdown_line(line) for line in text.splitlines()]
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result or _fallback_for(field_name, text, owner)


def _sanitize_display_value(
    value: Any,
    *,
    field_name: str,
    owner: Optional[Mapping[str, Any]],
) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _sanitize_display_value(item, field_name=field_name, owner=value)
                if not is_machine_field(key) and not is_display_field(key)
                else _sanitize_field(item, field_name=str(key), owner=value)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        result: List[Any] = []
        seen_strings = set()
        for item in value:
            sanitized = _sanitize_display_value(item, field_name=field_name, owner=owner)
            if sanitized == "":
                continue
            if isinstance(sanitized, str):
                if sanitized in seen_strings:
                    continue
                seen_strings.add(sanitized)
            result.append(sanitized)
        return result
    return sanitize_display_text(value, field_name=field_name, owner=owner)


def _sanitize_field(value: Any, *, field_name: str, owner: Mapping[str, Any]) -> Any:
    # Machine contract fields win over display suffixes.  For example,
    # ``artifact_name`` is a stable lookup key even though it ends in ``_name``.
    if is_machine_field(field_name):
        return sanitize_public_dto(value)
    if _normalized_field_name(field_name) == "name" and _is_route_descriptor(owner):
        return value
    if _normalized_field_name(field_name) in _MARKDOWN_DISPLAY_FIELDS:
        return sanitize_display_markdown(value, field_name=field_name, owner=owner)
    if (
        _normalized_field_name(field_name) == "content"
        and isinstance(value, str)
        and "\n" in value
    ):
        return sanitize_display_markdown(value, field_name=field_name, owner=owner)
    if is_display_field(field_name):
        return _sanitize_display_value(value, field_name=field_name, owner=owner)
    return sanitize_public_dto(value)


def sanitize_public_dto(value: Any) -> Any:
    """Recursively project an internal artifact into a safe public DTO.

    Machine IDs/enums retain their original value.  Display fields are localized
    recursively, including strings inside arrays such as ``trigger_conditions``.
    """

    if isinstance(value, Mapping):
        owner: Dict[str, Any] = dict(value)
        return {
            str(key): _sanitize_field(item, field_name=str(key), owner=owner)
            for key, item in value.items()
            if _normalized_field_name(key) not in PRIVATE_FIELD_NAMES
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_public_dto(item) for item in value]
    return value


def find_public_display_leaks(value: Any, path: str = "$") -> List[Tuple[str, str]]:
    """Collect unsafe values from display fields in a projected DTO.

    This is intentionally lightweight so focused contract tests can assert that
    legacy artifacts no longer leak without treating allowed machine IDs as
    failures.
    """

    leaks: List[Tuple[str, str]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_path = f"{path}.{key}"
            if _normalized_field_name(key) == "name" and _is_route_descriptor(value):
                continue
            if is_machine_field(key):
                leaks.extend(find_public_display_leaks(item, key_path))
            elif is_display_field(key):
                leaks.extend(_find_display_value_leaks(item, key_path))
            else:
                leaks.extend(find_public_display_leaks(item, key_path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            leaks.extend(find_public_display_leaks(item, f"{path}[{index}]"))
    return leaks


def _find_display_value_leaks(value: Any, path: str) -> List[Tuple[str, str]]:
    if isinstance(value, Mapping):
        leaks: List[Tuple[str, str]] = []
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if is_machine_field(key):
                # Machine fields are explicitly allowed even inside a visible
                # compound object such as trigger conditions.
                continue
            leaks.extend(_find_display_value_leaks(item, child_path))
        return leaks
    if isinstance(value, (list, tuple)):
        leaks: List[Tuple[str, str]] = []
        for index, item in enumerate(value):
            leaks.extend(_find_display_value_leaks(item, f"{path}[{index}]"))
        return leaks
    if isinstance(value, str) and has_display_text_leak(value):
        return [(path, value)]
    return []


def public_error_message(error: Any, fallback: str = "服务暂时不可用，请稍后重试。") -> str:
    """Return a safe Chinese public error without exposing exception details."""

    text = str(error or "").strip()
    if _TECHNICAL_ERROR_RE.search(text):
        return fallback
    if text and re.search(r"[\u3400-\u9fff]", text) and not has_display_text_leak(text):
        return text
    return fallback
