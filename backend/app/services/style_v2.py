"""
Style Library V2 service.

Implements a sample-driven + JSON-guarded writing pipeline:
1. StyleProfileV2 / StyleBindingV2 / ReviewPolicyV2 persistence
2. Sample retrieval from project knowledge files
3. Style feature extraction from samples
4. Draft generation and rewrite with layered review
"""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config import Config
from ..models.project import ProjectManager
from ..utils.file_parser import FileParser, split_text_into_chunks
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("envfish.style_v2")


TEMPLATE_LINKERS = [
    "总而言之",
    "综上所述",
    "从以上分析可知",
    "首先",
    "其次",
    "最后",
    "一方面",
    "另一方面",
    "客观地说",
    "在这个快节奏的社会",
]


def _now_iso() -> str:
    return datetime.now().isoformat()


def _safe_style_id(raw_id: Optional[str]) -> str:
    if raw_id:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(raw_id)).strip("_")
        if normalized:
            return normalized
    return f"style_{uuid.uuid4().hex[:10]}"


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_scene(scene: Optional[str]) -> str:
    if not scene:
        return "通用"
    return str(scene).strip() or "通用"


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    raw_parts = re.split(r"[。！？!?；;\n]+", text)
    return [p.strip() for p in raw_parts if p.strip()]


def _paragraphs(text: str) -> List[str]:
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if parts:
        return parts
    stripped = text.strip()
    return [stripped] if stripped else []


def _count_substring(text: str, fragment: str) -> int:
    if not text or not fragment:
        return 0
    return text.count(fragment)


def _tokenize_for_overlap(text: str) -> List[str]:
    if not text:
        return []
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    latin = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return chinese + latin


@dataclass
class StyleCoreV2:
    persona: str = ""
    audience: str = ""
    stance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "persona": self.persona,
            "audience": self.audience,
            "stance": self.stance,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StyleCoreV2":
        payload = payload or {}
        return cls(
            persona=str(payload.get("persona", "") or ""),
            audience=str(payload.get("audience", "") or ""),
            stance=str(payload.get("stance", "") or ""),
        )


@dataclass
class StyleWritingV2:
    ordering: str = "先结论后解释"
    sentence_mix: str = "短句为主+少量长句"
    paragraph_rule: str = "每段一个点"
    density: str = "中高信息密度"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ordering": self.ordering,
            "sentence_mix": self.sentence_mix,
            "paragraph_rule": self.paragraph_rule,
            "density": self.density,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StyleWritingV2":
        payload = payload or {}
        return cls(
            ordering=str(payload.get("ordering", "先结论后解释") or "先结论后解释"),
            sentence_mix=str(payload.get("sentence_mix", "短句为主+少量长句") or "短句为主+少量长句"),
            paragraph_rule=str(payload.get("paragraph_rule", "每段一个点") or "每段一个点"),
            density=str(payload.get("density", "中高信息密度") or "中高信息密度"),
        )


@dataclass
class StyleSignalV2:
    text: str
    scene: str = "通用"
    max_per_600_chars: int = 1
    max_per_doc: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "scene": self.scene,
            "max_per_600_chars": self.max_per_600_chars,
            "max_per_doc": self.max_per_doc,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Optional["StyleSignalV2"]:
        payload = payload or {}
        text = str(payload.get("text", "") or "").strip()
        if not text:
            return None
        return cls(
            text=text,
            scene=_normalize_scene(payload.get("scene")),
            max_per_600_chars=max(0, _to_int(payload.get("max_per_600_chars"), 1)),
            max_per_doc=max(0, _to_int(payload.get("max_per_doc"), 1)),
        )


@dataclass
class SoftAntiPatternV2:
    pattern: str
    penalty: int = 8
    rewrite_hint: str = "改成更自然的表达"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "penalty": self.penalty,
            "rewrite_hint": self.rewrite_hint,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Optional["SoftAntiPatternV2"]:
        payload = payload or {}
        pattern = str(payload.get("pattern", "") or "").strip()
        if not pattern:
            return None
        return cls(
            pattern=pattern,
            penalty=max(1, _to_int(payload.get("penalty"), 8)),
            rewrite_hint=str(payload.get("rewrite_hint", "改成更自然的表达") or "改成更自然的表达"),
        )


@dataclass
class StyleAntiPatternsV2:
    hard: List[str] = field(default_factory=list)
    soft: List[SoftAntiPatternV2] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hard": [x for x in self.hard if x],
            "soft": [x.to_dict() for x in self.soft],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StyleAntiPatternsV2":
        payload = payload or {}
        hard_items: List[str] = []
        for item in payload.get("hard", []) or []:
            text = str(item or "").strip()
            if text:
                hard_items.append(text)

        soft_items: List[SoftAntiPatternV2] = []
        raw_soft = payload.get("soft", []) or []
        for item in raw_soft:
            if isinstance(item, dict):
                parsed = SoftAntiPatternV2.from_dict(item)
                if parsed:
                    soft_items.append(parsed)
            elif isinstance(item, str):
                value = item.strip()
                if value:
                    soft_items.append(SoftAntiPatternV2(pattern=value))

        return cls(hard=hard_items, soft=soft_items)


@dataclass
class StyleProfileV2:
    id: str
    core: StyleCoreV2 = field(default_factory=StyleCoreV2)
    writing: StyleWritingV2 = field(default_factory=StyleWritingV2)
    signal_pool: List[StyleSignalV2] = field(default_factory=list)
    anti_patterns: StyleAntiPatternsV2 = field(default_factory=StyleAntiPatternsV2)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "core": self.core.to_dict(),
            "writing": self.writing.to_dict(),
            "signal_pool": [x.to_dict() for x in self.signal_pool],
            "anti_patterns": self.anti_patterns.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StyleProfileV2":
        payload = payload or {}
        return cls(
            id=_safe_style_id(payload.get("id")),
            core=StyleCoreV2.from_dict(payload.get("core") or {}),
            writing=StyleWritingV2.from_dict(payload.get("writing") or {}),
            signal_pool=[
                parsed
                for parsed in [StyleSignalV2.from_dict(item) for item in (payload.get("signal_pool") or [])]
                if parsed
            ],
            anti_patterns=StyleAntiPatternsV2.from_dict(payload.get("anti_patterns") or {}),
            created_at=str(payload.get("created_at", _now_iso()) or _now_iso()),
            updated_at=str(payload.get("updated_at", _now_iso()) or _now_iso()),
        )

    @classmethod
    def from_legacy_dict(cls, payload: Dict[str, Any]) -> "StyleProfileV2":
        payload = payload or {}

        def _normalize_to_list(value: Any) -> List[str]:
            if value is None:
                return []
            if isinstance(value, list):
                return [str(x).strip() for x in value if str(x).strip()]
            text = str(value)
            items = [x.strip() for x in re.split(r"[\n,，、;；]+", text) if x.strip()]
            return items

        core_persona = (
            payload.get("identity_perspective")
            or payload.get("身份与视角")
            or payload.get("identity")
            or payload.get("persona")
            or ""
        )
        writing_rules = (
            payload.get("pace_structure")
            or payload.get("节奏与结构")
            or payload.get("writing")
            or ""
        )
        slogans = (
            payload.get("recommended_phrases")
            or payload.get("推荐口头禅")
            or payload.get("口头禅")
            or []
        )
        taboo = (
            payload.get("taboo_words")
            or payload.get("禁忌词")
            or payload.get("forbidden")
            or []
        )

        signals = [
            StyleSignalV2(text=item)
            for item in _normalize_to_list(slogans)
        ]

        anti_hard = _normalize_to_list(taboo)

        style_id = _safe_style_id(payload.get("id") or payload.get("style_id"))
        now = _now_iso()

        return cls(
            id=style_id,
            core=StyleCoreV2(
                persona=str(core_persona),
                audience=str(payload.get("audience", "") or ""),
                stance=str(payload.get("stance", "") or ""),
            ),
            writing=StyleWritingV2(
                ordering="先结论后解释",
                sentence_mix="短句为主+少量长句",
                paragraph_rule="每段一个点",
                density=str(writing_rules or "中高信息密度"),
            ),
            signal_pool=signals,
            anti_patterns=StyleAntiPatternsV2(
                hard=anti_hard,
                soft=[SoftAntiPatternV2(pattern=item, penalty=8) for item in anti_hard[:8]],
            ),
            created_at=str(payload.get("created_at", now) or now),
            updated_at=now,
        )


@dataclass
class StyleKBRefV2:
    doc_id: str
    scene: str = "通用"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "scene": self.scene,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Optional["StyleKBRefV2"]:
        payload = payload or {}
        doc_id = str(payload.get("doc_id", "") or "").strip()
        if not doc_id:
            return None
        return cls(
            doc_id=doc_id,
            scene=_normalize_scene(payload.get("scene")),
            weight=max(0.01, _to_float(payload.get("weight"), 1.0)),
        )


@dataclass
class RetrievalConfigV2:
    top_k: int = 5
    min_sources: int = 2
    max_quote_chars: int = 220

    def to_dict(self) -> Dict[str, Any]:
        return {
            "top_k": self.top_k,
            "min_sources": self.min_sources,
            "max_quote_chars": self.max_quote_chars,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RetrievalConfigV2":
        payload = payload or {}
        return cls(
            top_k=max(1, _to_int(payload.get("top_k"), 5)),
            min_sources=max(1, _to_int(payload.get("min_sources"), 2)),
            max_quote_chars=max(60, _to_int(payload.get("max_quote_chars"), 220)),
        )


@dataclass
class StyleBindingV2:
    style_id: str
    kb_refs: List[StyleKBRefV2] = field(default_factory=list)
    retrieval: RetrievalConfigV2 = field(default_factory=RetrievalConfigV2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "style_id": self.style_id,
            "kb_refs": [x.to_dict() for x in self.kb_refs],
            "retrieval": self.retrieval.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StyleBindingV2":
        payload = payload or {}
        style_id = _safe_style_id(payload.get("style_id"))
        refs: List[StyleKBRefV2] = []
        for item in payload.get("kb_refs", []) or []:
            if isinstance(item, dict):
                parsed = StyleKBRefV2.from_dict(item)
                if parsed:
                    refs.append(parsed)

        return cls(
            style_id=style_id,
            kb_refs=refs,
            retrieval=RetrievalConfigV2.from_dict(payload.get("retrieval") or {}),
        )


@dataclass
class HardRuleV2:
    id: str
    check: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "check": self.check,
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Optional["HardRuleV2"]:
        payload = payload or {}
        rule_id = str(payload.get("id", "") or "").strip()
        check = str(payload.get("check", "") or "").strip()
        message = str(payload.get("message", "") or "").strip()
        if not rule_id:
            return None
        if not check:
            check = "命中即拒绝"
        if not message:
            message = "触发硬性规则"
        return cls(id=rule_id, check=check, message=message)


@dataclass
class SoftRuleWeightV2:
    id: str
    weight: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Optional["SoftRuleWeightV2"]:
        payload = payload or {}
        rule_id = str(payload.get("id", "") or "").strip()
        if not rule_id:
            return None
        return cls(id=rule_id, weight=max(1, _to_int(payload.get("weight"), 10)))


@dataclass
class ReviewThresholdsV2:
    pass_score: int = 80
    rewrite_score: int = 65

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_score": self.pass_score,
            "rewrite_score": self.rewrite_score,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReviewThresholdsV2":
        payload = payload or {}
        pass_score = _to_int(payload.get("pass_score"), 80)
        rewrite_score = _to_int(payload.get("rewrite_score"), 65)
        pass_score = min(100, max(1, pass_score))
        rewrite_score = min(pass_score, max(1, rewrite_score))
        return cls(pass_score=pass_score, rewrite_score=rewrite_score)


@dataclass
class ReviewPolicyV2:
    hard_rules: List[HardRuleV2] = field(default_factory=list)
    soft_rules: List[SoftRuleWeightV2] = field(default_factory=list)
    thresholds: ReviewThresholdsV2 = field(default_factory=ReviewThresholdsV2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hard_rules": [x.to_dict() for x in self.hard_rules],
            "soft_rules": [x.to_dict() for x in self.soft_rules],
            "thresholds": self.thresholds.to_dict(),
        }

    @classmethod
    def default(cls) -> "ReviewPolicyV2":
        return cls(
            hard_rules=[
                HardRuleV2(
                    id="hard_banned_expression",
                    check="命中即拒绝",
                    message="命中硬性违规表达",
                )
            ],
            soft_rules=[
                SoftRuleWeightV2(id="soft_voice", weight=35),
                SoftRuleWeightV2(id="soft_natural", weight=30),
                SoftRuleWeightV2(id="soft_structure", weight=20),
                SoftRuleWeightV2(id="soft_risk_lang", weight=15),
            ],
            thresholds=ReviewThresholdsV2(pass_score=80, rewrite_score=65),
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ReviewPolicyV2":
        payload = payload or {}
        hard = [
            parsed
            for parsed in [HardRuleV2.from_dict(item) for item in (payload.get("hard_rules") or [])]
            if parsed
        ]
        soft = [
            parsed
            for parsed in [SoftRuleWeightV2.from_dict(item) for item in (payload.get("soft_rules") or [])]
            if parsed
        ]
        if not soft:
            soft = ReviewPolicyV2.default().soft_rules

        return cls(
            hard_rules=hard,
            soft_rules=soft,
            thresholds=ReviewThresholdsV2.from_dict(payload.get("thresholds") or {}),
        )


class StyleLibraryV2Manager:
    """File-backed manager for style v2 assets."""

    ROOT_DIR = os.path.join(Config.UPLOAD_FOLDER, "style_v2")
    PROFILES_DIR = os.path.join(ROOT_DIR, "profiles")
    BINDINGS_DIR = os.path.join(ROOT_DIR, "bindings")
    POLICIES_DIR = os.path.join(ROOT_DIR, "review_policies")

    def __init__(self):
        self._ensure_dirs()

    @classmethod
    def _ensure_dirs(cls):
        os.makedirs(cls.PROFILES_DIR, exist_ok=True)
        os.makedirs(cls.BINDINGS_DIR, exist_ok=True)
        os.makedirs(cls.POLICIES_DIR, exist_ok=True)

    @classmethod
    def _profile_path(cls, style_id: str) -> str:
        return os.path.join(cls.PROFILES_DIR, f"{_safe_style_id(style_id)}.json")

    @classmethod
    def _binding_path(cls, style_id: str) -> str:
        return os.path.join(cls.BINDINGS_DIR, f"{_safe_style_id(style_id)}.json")

    @classmethod
    def _policy_path(cls, style_id: str) -> str:
        return os.path.join(cls.POLICIES_DIR, f"{_safe_style_id(style_id)}.json")

    @staticmethod
    def _read_json(path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write_json(path: str, payload: Dict[str, Any]):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def save_profile(self, profile_payload: Dict[str, Any]) -> StyleProfileV2:
        if "core" in (profile_payload or {}) and "writing" in (profile_payload or {}):
            profile = StyleProfileV2.from_dict(profile_payload)
        else:
            profile = StyleProfileV2.from_legacy_dict(profile_payload or {})

        existing = self.get_profile(profile.id)
        now = _now_iso()
        profile.updated_at = now
        if existing:
            profile.created_at = existing.created_at
        elif not profile.created_at:
            profile.created_at = now

        self._write_json(self._profile_path(profile.id), profile.to_dict())
        return profile

    def get_profile(self, style_id: str) -> Optional[StyleProfileV2]:
        payload = self._read_json(self._profile_path(style_id))
        if not payload:
            return None
        return StyleProfileV2.from_dict(payload)

    def list_profiles(self) -> List[StyleProfileV2]:
        self._ensure_dirs()
        profiles: List[StyleProfileV2] = []
        for filename in os.listdir(self.PROFILES_DIR):
            if not filename.endswith(".json"):
                continue
            payload = self._read_json(os.path.join(self.PROFILES_DIR, filename))
            if not payload:
                continue
            try:
                profiles.append(StyleProfileV2.from_dict(payload))
            except Exception as exc:
                logger.warning(f"跳过损坏风格文件 {filename}: {exc}")
        profiles.sort(key=lambda item: item.updated_at, reverse=True)
        return profiles

    def delete_profile(self, style_id: str) -> bool:
        sid = _safe_style_id(style_id)
        deleted = False
        for path in [self._profile_path(sid), self._binding_path(sid), self._policy_path(sid)]:
            if os.path.exists(path):
                os.remove(path)
                deleted = True
        return deleted

    def save_binding(self, binding_payload: Dict[str, Any]) -> StyleBindingV2:
        binding = StyleBindingV2.from_dict(binding_payload or {})
        self._write_json(self._binding_path(binding.style_id), binding.to_dict())
        return binding

    def get_binding(self, style_id: str) -> Optional[StyleBindingV2]:
        payload = self._read_json(self._binding_path(style_id))
        if not payload:
            return None
        return StyleBindingV2.from_dict(payload)

    def save_review_policy(self, style_id: str, policy_payload: Dict[str, Any]) -> ReviewPolicyV2:
        sid = _safe_style_id(style_id)
        policy = ReviewPolicyV2.from_dict(policy_payload or {})
        self._write_json(self._policy_path(sid), policy.to_dict())
        return policy

    def get_review_policy(self, style_id: str) -> Optional[ReviewPolicyV2]:
        payload = self._read_json(self._policy_path(style_id))
        if not payload:
            return None
        return ReviewPolicyV2.from_dict(payload)

    def get_or_default_review_policy(self, style_id: str) -> ReviewPolicyV2:
        existing = self.get_review_policy(style_id)
        return existing or ReviewPolicyV2.default()

    def list_project_docs(self, project_id: str) -> List[Dict[str, Any]]:
        project = ProjectManager.get_project(project_id)
        if not project:
            return []

        docs: List[Dict[str, Any]] = []
        extracted = ProjectManager.get_extracted_text(project_id)
        if extracted:
            docs.append(
                {
                    "doc_id": f"project:{project_id}:text",
                    "name": "extracted_text",
                    "size": len(extracted),
                    "scene": "通用",
                }
            )

        for meta in project.files or []:
            saved_filename = str(meta.get("saved_filename", "") or "").strip()
            original_filename = str(meta.get("original_filename", "") or "").strip()
            path = str(meta.get("path", "") or "").strip()
            if not saved_filename or not path:
                continue
            docs.append(
                {
                    "doc_id": f"project:{project_id}:file:{saved_filename}",
                    "name": original_filename or saved_filename,
                    "size": _to_int(meta.get("size"), 0),
                    "scene": "通用",
                }
            )

        return docs

    def resolve_doc_text(self, doc_id: str, fallback_project_id: Optional[str] = None) -> str:
        doc_id = str(doc_id or "").strip()
        if not doc_id:
            return ""

        text_match = re.match(r"^project:([^:]+):text$", doc_id)
        if text_match:
            project_id = text_match.group(1)
            return ProjectManager.get_extracted_text(project_id) or ""

        file_match = re.match(r"^project:([^:]+):file:(.+)$", doc_id)
        if file_match:
            project_id = file_match.group(1)
            file_key = file_match.group(2)
            project = ProjectManager.get_project(project_id)
            if not project:
                return ""
            for meta in project.files or []:
                if file_key in {
                    str(meta.get("saved_filename", "") or "").strip(),
                    str(meta.get("original_filename", "") or "").strip(),
                }:
                    path = str(meta.get("path", "") or "").strip()
                    if path and os.path.exists(path):
                        try:
                            return FileParser.extract_text(path)
                        except Exception as exc:
                            logger.warning(f"读取知识库文件失败: {doc_id}, err={exc}")
                            return ""

        if fallback_project_id:
            project = ProjectManager.get_project(fallback_project_id)
            if project:
                for meta in project.files or []:
                    candidates = {
                        str(meta.get("saved_filename", "") or "").strip(),
                        str(meta.get("original_filename", "") or "").strip(),
                    }
                    if doc_id in candidates:
                        path = str(meta.get("path", "") or "").strip()
                        if path and os.path.exists(path):
                            try:
                                return FileParser.extract_text(path)
                            except Exception:
                                return ""

        if os.path.exists(doc_id):
            try:
                return FileParser.extract_text(doc_id)
            except Exception as exc:
                logger.warning(f"从路径读取样稿失败: {doc_id}, err={exc}")

        return ""


class StyleKnowledgeRetrieverV2:
    def __init__(self, manager: Optional[StyleLibraryV2Manager] = None):
        self.manager = manager or StyleLibraryV2Manager()

    def retrieve_samples(
        self,
        task: str,
        scene: str,
        binding: Optional[StyleBindingV2],
        fallback_project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not binding or not binding.kb_refs:
            return []

        scene_normalized = _normalize_scene(scene)
        candidates: List[StyleKBRefV2] = []
        for ref in binding.kb_refs:
            if ref.scene in {"通用", "all", "ALL", scene_normalized}:
                candidates.append(ref)

        if not candidates:
            candidates = list(binding.kb_refs)

        retrieval = binding.retrieval
        scored: List[Dict[str, Any]] = []

        for ref in candidates:
            full_text = self.manager.resolve_doc_text(ref.doc_id, fallback_project_id=fallback_project_id)
            if not full_text.strip():
                continue

            chunks = split_text_into_chunks(full_text, chunk_size=420, overlap=80)
            for chunk in chunks:
                stripped = chunk.strip()
                if not stripped:
                    continue
                score = self._score_chunk(stripped, task) * ref.weight
                scored.append(
                    {
                        "doc_id": ref.doc_id,
                        "scene": ref.scene,
                        "score": score,
                        "snippet": stripped[: retrieval.max_quote_chars],
                    }
                )

        if not scored:
            return []

        scored.sort(key=lambda item: item["score"], reverse=True)
        selected = scored[: retrieval.top_k]

        selected_doc_ids = {item["doc_id"] for item in selected}
        if len(selected_doc_ids) < retrieval.min_sources:
            for item in scored[retrieval.top_k :]:
                if item["doc_id"] in selected_doc_ids:
                    continue
                selected.append(item)
                selected_doc_ids.add(item["doc_id"])
                if len(selected_doc_ids) >= retrieval.min_sources:
                    break

        return selected

    @staticmethod
    def _score_chunk(chunk: str, task: str) -> float:
        tokens = _tokenize_for_overlap(task)
        if not tokens:
            return min(1.0, len(chunk) / 300.0)

        lowered = chunk.lower()
        overlap = 0
        for token in tokens:
            if token and token in lowered:
                overlap += 1

        base = overlap / max(1, len(tokens))
        length_bonus = min(1.0, len(chunk) / 500.0)
        return base * 10.0 + length_bonus


class StyleFeatureExtractorV2:
    @staticmethod
    def extract(snippets: Sequence[str]) -> Dict[str, Any]:
        joined = "\n".join([s for s in snippets if s])
        if not joined.strip():
            return {
                "avg_sentence_len": 0,
                "short_sentence_ratio": 0,
                "long_sentence_ratio": 0,
                "avg_paragraph_len": 0,
                "exclamation_ratio": 0,
                "question_ratio": 0,
                "top_linkers": [],
            }

        sentences = _split_sentences(joined)
        sentence_lengths = [len(s) for s in sentences] or [0]
        paragraphs = _paragraphs(joined)
        paragraph_lengths = [len(p) for p in paragraphs] or [0]

        short_count = len([x for x in sentence_lengths if x <= 20])
        long_count = len([x for x in sentence_lengths if x >= 45])

        linker_rank = []
        for linker in TEMPLATE_LINKERS:
            count = _count_substring(joined, linker)
            if count > 0:
                linker_rank.append((linker, count))
        linker_rank.sort(key=lambda item: item[1], reverse=True)

        total_sentences = max(1, len(sentences))
        return {
            "avg_sentence_len": round(sum(sentence_lengths) / max(1, len(sentence_lengths)), 2),
            "short_sentence_ratio": round(short_count / total_sentences, 4),
            "long_sentence_ratio": round(long_count / total_sentences, 4),
            "avg_paragraph_len": round(sum(paragraph_lengths) / max(1, len(paragraph_lengths)), 2),
            "exclamation_ratio": round((joined.count("!") + joined.count("！")) / total_sentences, 4),
            "question_ratio": round((joined.count("?") + joined.count("？")) / total_sentences, 4),
            "top_linkers": [item[0] for item in linker_rank[:5]],
        }

    @staticmethod
    def to_prompt(features: Dict[str, Any]) -> str:
        if not features:
            return "样稿不足，改为仅遵循结构化风格约束。"

        top_linkers = ", ".join(features.get("top_linkers", [])) or "（无明显模板连词）"
        return "\n".join(
            [
                f"- 平均句长: {features.get('avg_sentence_len', 0)}",
                f"- 短句占比: {features.get('short_sentence_ratio', 0)}",
                f"- 长句占比: {features.get('long_sentence_ratio', 0)}",
                f"- 段落平均长度: {features.get('avg_paragraph_len', 0)}",
                f"- 感叹强度: {features.get('exclamation_ratio', 0)}",
                f"- 提问强度: {features.get('question_ratio', 0)}",
                f"- 常见连接词: {top_linkers}",
            ]
        )


class StyleReviewerV2:
    def evaluate(self, text: str, profile: StyleProfileV2, policy: ReviewPolicyV2) -> Dict[str, Any]:
        hard_hits = self._collect_hard_hits(text, profile, policy)

        soft_scores: Dict[str, Dict[str, Any]] = {}
        weighted_sum = 0.0
        total_weight = 0
        rewrite_suggestions: List[str] = []

        for rule in policy.soft_rules:
            score, penalty, suggestions = self._score_soft_rule(rule.id, text, profile)
            soft_scores[rule.id] = {
                "score": score,
                "penalty": penalty,
                "weight": rule.weight,
            }
            weighted_sum += score * rule.weight
            total_weight += rule.weight
            for suggestion in suggestions:
                if suggestion not in rewrite_suggestions:
                    rewrite_suggestions.append(suggestion)

        total_score = round(weighted_sum / max(1, total_weight), 2)

        if hard_hits:
            decision = "hard_rewrite"
        elif total_score >= policy.thresholds.pass_score:
            decision = "pass"
        elif total_score >= policy.thresholds.rewrite_score:
            decision = "targeted_rewrite"
        else:
            decision = "full_rewrite"

        signal_usage = self._signal_usage(text, profile)

        return {
            "score": total_score,
            "decision": decision,
            "passed": decision == "pass",
            "hard_hits": hard_hits,
            "soft_scores": soft_scores,
            "rewrite_suggestions": rewrite_suggestions,
            "signal_usage": signal_usage,
        }

    def _collect_hard_hits(
        self,
        text: str,
        profile: StyleProfileV2,
        policy: ReviewPolicyV2,
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []

        for pattern in profile.anti_patterns.hard:
            if pattern and pattern in text:
                hits.append(
                    {
                        "id": "hard_pattern",
                        "pattern": pattern,
                        "message": f"命中硬禁表达: {pattern}",
                    }
                )

        for rule in policy.hard_rules:
            matched, detail = self._eval_hard_check(rule.check, text)
            if matched:
                hit = {
                    "id": rule.id,
                    "pattern": detail,
                    "message": rule.message,
                }
                if hit not in hits:
                    hits.append(hit)

        return hits

    def _eval_hard_check(self, check: str, text: str) -> Tuple[bool, str]:
        check = str(check or "").strip()
        if not check:
            return False, ""

        if check.startswith("regex:"):
            pattern = check[len("regex:") :].strip()
            if not pattern:
                return False, ""
            if re.search(pattern, text):
                return True, pattern
            return False, pattern

        if check.startswith("contains:"):
            items = [x.strip() for x in check[len("contains:") :].split("|") if x.strip()]
            for item in items:
                if item in text:
                    return True, item
            return False, "|".join(items)

        if check.startswith("not_contains:"):
            items = [x.strip() for x in check[len("not_contains:") :].split("|") if x.strip()]
            for item in items:
                if item in text:
                    return True, item
            return False, "|".join(items)

        # Fallback: no executable check expression.
        return False, ""

    def _score_soft_rule(self, rule_id: str, text: str, profile: StyleProfileV2) -> Tuple[float, float, List[str]]:
        if rule_id == "soft_voice":
            return self._score_voice(text, profile)
        if rule_id == "soft_natural":
            return self._score_natural(text)
        if rule_id == "soft_structure":
            return self._score_structure(text, profile)
        if rule_id == "soft_risk_lang":
            return self._score_risk_lang(text, profile)
        return 100.0, 0.0, []

    def _score_voice(self, text: str, profile: StyleProfileV2) -> Tuple[float, float, List[str]]:
        sentences = _split_sentences(text)
        if not sentences:
            return 40.0, 60.0, ["正文为空，需重新生成内容"]

        lengths = [len(s) for s in sentences]
        short_ratio = len([x for x in lengths if x <= 20]) / max(1, len(lengths))
        long_ratio = len([x for x in lengths if x >= 45]) / max(1, len(lengths))

        penalty = 0.0
        hints: List[str] = []

        if "短句" in profile.writing.sentence_mix and short_ratio < 0.45:
            penalty += 20
            hints.append("提高短句比例，避免整段都用长句")

        if "长句" in profile.writing.sentence_mix and long_ratio == 0:
            penalty += 10
            hints.append("补一两句长句拉开节奏")

        first_para = _paragraphs(text)[0] if _paragraphs(text) else text
        if "先结论" in profile.writing.ordering and len(first_para) > 240:
            penalty += 14
            hints.append("开头先给结论，再展开解释")

        score = max(0.0, 100.0 - penalty)
        return score, penalty, hints

    def _score_natural(self, text: str) -> Tuple[float, float, List[str]]:
        penalty = 0.0
        hints: List[str] = []

        linker_hits = 0
        for linker in TEMPLATE_LINKERS:
            count = _count_substring(text, linker)
            linker_hits += count

        if linker_hits > 0:
            penalty += min(45, linker_hits * 6)
            hints.append("减少模板连词堆叠，改成自然口语推进")

        starts: Dict[str, int] = {}
        for sentence in _split_sentences(text):
            key = sentence[:4]
            starts[key] = starts.get(key, 0) + 1
        repeated = [k for k, v in starts.items() if k and v >= 3]
        if repeated:
            penalty += min(25, 8 * len(repeated))
            hints.append("避免连续句子同样开头，降低模板感")

        score = max(0.0, 100.0 - penalty)
        return score, penalty, hints

    def _score_structure(self, text: str, profile: StyleProfileV2) -> Tuple[float, float, List[str]]:
        paragraphs = _paragraphs(text)
        penalty = 0.0
        hints: List[str] = []

        if len(paragraphs) < 2:
            penalty += 18
            hints.append("至少拆成两段，提升可读性")

        for para in paragraphs:
            sentence_count = len(_split_sentences(para))
            if sentence_count > 4:
                penalty += 6

        if "每段一个点" in profile.writing.paragraph_rule:
            overloaded = [p for p in paragraphs if len(_split_sentences(p)) > 3]
            if overloaded:
                penalty += min(24, 6 * len(overloaded))
                hints.append("每段聚焦一个点，避免单段信息过载")

        score = max(0.0, 100.0 - penalty)
        return score, penalty, hints

    def _score_risk_lang(self, text: str, profile: StyleProfileV2) -> Tuple[float, float, List[str]]:
        penalty = 0.0
        hints: List[str] = []

        for soft_pattern in profile.anti_patterns.soft:
            count = _count_substring(text, soft_pattern.pattern)
            if count > 0:
                penalty += count * soft_pattern.penalty
                hint = soft_pattern.rewrite_hint or f"减少表达: {soft_pattern.pattern}"
                if hint not in hints:
                    hints.append(hint)

        score = max(0.0, 100.0 - penalty)
        return score, penalty, hints

    def _signal_usage(self, text: str, profile: StyleProfileV2) -> List[Dict[str, Any]]:
        usage: List[Dict[str, Any]] = []
        for signal in profile.signal_pool:
            count = _count_substring(text, signal.text)
            allowed = _allowed_signal_count(len(text), signal)
            usage.append(
                {
                    "text": signal.text,
                    "count": count,
                    "allowed": allowed,
                    "over_budget": count > allowed,
                }
            )
        return usage


class StyleWritingEngineV2:
    def __init__(
        self,
        manager: Optional[StyleLibraryV2Manager] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.manager = manager or StyleLibraryV2Manager()
        self.llm = llm_client
        self.retriever = StyleKnowledgeRetrieverV2(self.manager)
        self.reviewer = StyleReviewerV2()

    def _ensure_llm(self) -> LLMClient:
        if self.llm is None:
            self.llm = LLMClient()
        return self.llm

    def generate(
        self,
        *,
        style_id: str,
        task: str,
        scene: str = "通用",
        project_id: Optional[str] = None,
        draft_text: Optional[str] = None,
        max_rewrite_rounds: int = 2,
    ) -> Dict[str, Any]:
        profile = self.manager.get_profile(style_id)
        if not profile:
            raise ValueError(f"风格不存在: {style_id}")

        binding = self.manager.get_binding(style_id)
        policy = self.manager.get_or_default_review_policy(style_id)

        samples = self.retriever.retrieve_samples(
            task=task,
            scene=scene,
            binding=binding,
            fallback_project_id=project_id,
        )
        feature_obj = StyleFeatureExtractorV2.extract([x["snippet"] for x in samples])

        if draft_text is None:
            draft = self._generate_draft_with_llm(
                task=task,
                profile=profile,
                samples=samples,
                feature_obj=feature_obj,
                scene=scene,
            )
        else:
            draft = str(draft_text)

        draft = self._enforce_signal_budget(draft, profile, scene=scene)

        review = self.reviewer.evaluate(draft, profile, policy)
        rewrites: List[Dict[str, Any]] = []

        rounds = max(0, min(3, int(max_rewrite_rounds)))
        for idx in range(rounds):
            decision = review.get("decision")
            if decision == "pass":
                break

            revised = self._rewrite_with_llm(
                original_text=draft,
                task=task,
                profile=profile,
                review=review,
                feature_obj=feature_obj,
                samples=samples,
                rewrite_mode=decision,
            )
            revised = self._enforce_signal_budget(revised, profile, scene=scene)

            rewrites.append(
                {
                    "round": idx + 1,
                    "mode": decision,
                    "score_before": review.get("score"),
                }
            )

            draft = revised
            review = self.reviewer.evaluate(draft, profile, policy)

        return {
            "text": draft,
            "review": review,
            "trace": {
                "style_id": profile.id,
                "scene": _normalize_scene(scene),
                "sample_count": len(samples),
                "fallback_to_style_only": len(samples) == 0,
                "sources": [
                    {
                        "doc_id": item["doc_id"],
                        "score": round(item["score"], 4),
                    }
                    for item in samples
                ],
                "features": feature_obj,
                "rewrite_rounds": rewrites,
            },
        }

    def review_only(
        self,
        *,
        style_id: str,
        text: str,
    ) -> Dict[str, Any]:
        profile = self.manager.get_profile(style_id)
        if not profile:
            raise ValueError(f"风格不存在: {style_id}")
        policy = self.manager.get_or_default_review_policy(style_id)
        return self.reviewer.evaluate(str(text or ""), profile, policy)

    def _generate_draft_with_llm(
        self,
        *,
        task: str,
        profile: StyleProfileV2,
        samples: List[Dict[str, Any]],
        feature_obj: Dict[str, Any],
        scene: str,
    ) -> str:
        llm = self._ensure_llm()

        sample_blocks = []
        for idx, sample in enumerate(samples[:8], start=1):
            sample_blocks.append(
                f"[{idx}] 来源={sample['doc_id']}\n{sample['snippet']}"
            )
        samples_text = "\n\n".join(sample_blocks) if sample_blocks else "（无可用样稿，直接遵循风格结构约束）"

        signal_desc = []
        for signal in profile.signal_pool:
            signal_desc.append(
                f"- {signal.text}（scene={signal.scene}, max_per_600={signal.max_per_600_chars}, max_per_doc={signal.max_per_doc}）"
            )
        signal_text = "\n".join(signal_desc) if signal_desc else "（无）"

        hard_bans = "\n".join([f"- {x}" for x in profile.anti_patterns.hard]) if profile.anti_patterns.hard else "（无）"

        system_prompt = (
            "你是中文写作助手。任务是输出自然、像真人写作的文本。"
            "必须遵守给定风格结构，不得堆砌口头禅，不得输出模板腔。"
            "禁止直接复用样稿原句，任何连续12字不得与样稿完全一致。"
            "只输出正文，不要解释。"
        )

        user_prompt = f"""写作任务：{task}

风格内核：
- 人设：{profile.core.persona}
- 受众：{profile.core.audience}
- 立场：{profile.core.stance}

写法约束：
- 结构推进：{profile.writing.ordering}
- 句型节奏：{profile.writing.sentence_mix}
- 段落规则：{profile.writing.paragraph_rule}
- 信息密度：{profile.writing.density}

样稿提取特征：
{StyleFeatureExtractorV2.to_prompt(feature_obj)}

候选信号词（可选，不强制）：
{signal_text}
规则：每个信号词必须遵守预算；同一文本不要机械重复。

硬禁表达：
{hard_bans}

当前场景：{_normalize_scene(scene)}

参考样稿片段（仅用于学习写法，不可照抄）：
{samples_text}

请直接输出最终正文。"""

        return llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.45,
            max_tokens=2048,
        )

    def _rewrite_with_llm(
        self,
        *,
        original_text: str,
        task: str,
        profile: StyleProfileV2,
        review: Dict[str, Any],
        feature_obj: Dict[str, Any],
        samples: List[Dict[str, Any]],
        rewrite_mode: str,
    ) -> str:
        llm = self._ensure_llm()

        hard_hits = review.get("hard_hits") or []
        hard_hint = "\n".join([f"- {h.get('message')} ({h.get('pattern')})" for h in hard_hits]) or "（无）"

        rewrite_suggestions = review.get("rewrite_suggestions") or []
        suggestion_hint = "\n".join([f"- {item}" for item in rewrite_suggestions]) or "（无）"

        sample_blocks = []
        for idx, sample in enumerate(samples[:5], start=1):
            sample_blocks.append(f"[{idx}] {sample['snippet']}")
        samples_text = "\n\n".join(sample_blocks) if sample_blocks else "（无）"

        mode_hint = {
            "hard_rewrite": "命中硬规则，必须彻底改写。",
            "targeted_rewrite": "分数中等，定向改写命中问题。",
            "full_rewrite": "分数过低，需整体重写。",
        }.get(rewrite_mode, "请改写文本。")

        system_prompt = (
            "你是中文改写助手。保持核心意思，不改变事实，不添加新事实。"
            "改写目标是更自然、更像作者本人，同时满足风格约束。"
            "只输出改写后的正文。"
        )

        user_prompt = f"""原任务：{task}

改写模式：{mode_hint}

风格结构约束：
- 人设：{profile.core.persona}
- 结构推进：{profile.writing.ordering}
- 句型节奏：{profile.writing.sentence_mix}
- 段落规则：{profile.writing.paragraph_rule}

样稿写法特征：
{StyleFeatureExtractorV2.to_prompt(feature_obj)}

审稿问题：
硬性命中：
{hard_hint}

软性建议：
{suggestion_hint}

参考样稿（仅学写法，不可照抄）：
{samples_text}

待改写文本：
{original_text}

请输出改写后正文。"""

        return llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.35,
            max_tokens=2048,
        )

    def _enforce_signal_budget(self, text: str, profile: StyleProfileV2, scene: str) -> str:
        result = text or ""
        norm_scene = _normalize_scene(scene)

        for signal in profile.signal_pool:
            if signal.scene not in {"通用", "all", "ALL", norm_scene}:
                continue
            allowed = _allowed_signal_count(len(result), signal)
            if allowed < 0:
                allowed = 0
            result = _trim_fragment_occurrences(result, signal.text, allowed)

        return _normalize_punctuation_spaces(result)


def _allowed_signal_count(total_chars: int, signal: StyleSignalV2) -> int:
    if not signal.text:
        return 0
    windows = max(1, math.ceil(max(1, total_chars) / 600))
    per_len_budget = windows * max(0, signal.max_per_600_chars)
    return min(max(0, signal.max_per_doc), per_len_budget)


def _trim_fragment_occurrences(text: str, fragment: str, allowed: int) -> str:
    if not fragment or allowed < 0:
        return text

    pattern = re.escape(fragment)
    matches = list(re.finditer(pattern, text))
    if len(matches) <= allowed:
        return text

    # Keep earliest allowed occurrences and remove the rest.
    kept = 0
    cursor = 0
    pieces: List[str] = []
    for match in matches:
        pieces.append(text[cursor : match.start()])
        if kept < allowed:
            pieces.append(match.group(0))
            kept += 1
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces)


def _normalize_punctuation_spaces(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = normalized.replace(" ，", "，").replace(" 。", "。").replace(" ！", "！")
    normalized = normalized.replace(" ？", "？").replace(" ,", ",").replace(" .", ".")
    normalized = re.sub(r"，{2,}", "，", normalized)
    normalized = re.sub(r"。{2,}", "。", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


__all__ = [
    "StyleCoreV2",
    "StyleWritingV2",
    "StyleSignalV2",
    "SoftAntiPatternV2",
    "StyleAntiPatternsV2",
    "StyleProfileV2",
    "StyleKBRefV2",
    "RetrievalConfigV2",
    "StyleBindingV2",
    "HardRuleV2",
    "SoftRuleWeightV2",
    "ReviewThresholdsV2",
    "ReviewPolicyV2",
    "StyleLibraryV2Manager",
    "StyleKnowledgeRetrieverV2",
    "StyleFeatureExtractorV2",
    "StyleReviewerV2",
    "StyleWritingEngineV2",
]
