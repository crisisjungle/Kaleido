"""
Scene material generator.

This service turns lightweight user anchors, uploaded documents, map seed
artifacts, and initial variables into a structured scene seed plus a Markdown
report that can be fed into the existing EnvFish document pipeline.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from ..utils.file_parser import FileParser
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .effort_contract import (
    assert_effort_reference,
    build_effort_snapshot,
    normalize_effort_snapshot,
)
from .map_seed_manager import MapSeedManager
from .semantic_input import SemanticArtifactStore, SemanticInputArtifact, SemanticInputNormalizer
from .text_processor import TextProcessor

logger = get_logger("envfish.scene_material")


SCENE_COMPOSER_SYSTEM_PROMPT = """你是 Kaleido 场景素材生成器。

你的任务是把用户给出的少量信息、上传文档、地图空间事实和初始变量，整理成可上传到 EnvFish 的专业素材报告。

必须遵守：
1. 输出有效 JSON，不要输出 Markdown 代码块之外的额外解释。
2. report_markdown 必须是中文 Markdown。
3. 报告要服务多智能体生态-社会推演，优先写真实区域、主体、设施、环境载体、生态受体、关系句、变量、风险链条或稳态反馈链。
4. 区分事实、推断和用户假设。无法确认的内容必须写入 uncertainties。
5. 不要把“风险、舆情、恐慌、政策、压力、稳定状态”这类抽象概念作为主实体；它们应作为状态、指标或关系属性。
6. 历史事件不能编造具体责任归因；地点稳态不能编造真实具名机构或设施，除非输入或地图事实给出。

JSON 输出结构：
{
  "title": "报告标题",
  "scene_type": "historical_event|stable_environment|hybrid|custom",
  "source_mode": "text_only|document_only|map_only|document_map_hybrid",
  "recommended_simulation_requirement": "推荐进入后续推演的需求描述",
  "locations": [
    {"name": "地点名", "role": "primary_anchor|related_place|facility", "lat": null, "lon": null, "confidence": 0.7, "source": "user|document|map_seed|inferred"}
  ],
  "area_of_interest": {
    "label": "范围名称",
    "center": {"lat": null, "lon": null},
    "radius_m": null,
    "rationale": "范围划定理由"
  },
  "initial_variables": [
    {"name": "变量名", "type": "weather|policy|pollution|traffic|public_health|resource|custom", "description": "变量描述", "direction": "上升|下降|突变|...", "intensity": "极端|高强度|...", "expected_effects": ["影响1"]}
  ],
  "stable_context_variables": [
    {"name": "稳态背景项", "type": "...", "description": "基线/常态背景，非注入扰动"}
  ],
  "assumptions": ["推演假设"],
  "uncertainties": ["不确定性"],
  "report_markdown": "# 标题\\n..."
}

initial_variables 只放会改变系统状态的扰动、压力或干预，例如极端降雨、污染泄漏、限行政策、资源调度；每个变量必须带 direction（方向，如上升/下降/突变）或 intensity（强度，如极端/高强度），否则会被代码降级为稳态背景。不要把基线信息、当前观测值、常态条件或地图事实放进 initial_variables；基线温度、基线湿度、基线降水、基线风速、局地天气基线应放入 stable_context_variables，或写入 report_markdown 的环境基线 / assumptions。代码侧会再次执行同样的纪律校验（机器闸门），不依赖本提示词。
"""


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _is_baseline_context_variable(item: Dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    text = " ".join(
        _safe_text(item.get(key))
        for key in ("name", "title", "description", "summary", "type", "category")
    ).lower()
    if not text:
        return False
    baseline_terms = (
        "基线",
        "稳态",
        "常态",
        "当前",
        "现状",
        "观测",
        "环境背景",
        "weather_baseline",
        "baseline",
    )
    weather_terms = (
        "温度",
        "气温",
        "湿度",
        "降水",
        "降雨",
        "风速",
        "风向",
        "天气",
        "temperature",
        "humidity",
        "precipitation",
        "wind",
        "weather",
    )
    return any(term in text for term in baseline_terms) and any(term in text for term in weather_terms)


# A variable only earns a place in initial_variables (the injected / perturbation
# track) when it carries genuine *change* semantics: a direction (up/down/onset),
# an intensity (强/弱/级别), or an explicit intervention/disturbance verb. Anything
# else is treated as stable-context and moved out of initial_variables so that
# downstream extraction never mistakes a baseline reading for a driver.
_PERTURBATION_DIRECTION_TERMS = (
    "增加", "上升", "升高", "增强", "上调", "加剧", "扩大", "加速", "升级", "激增", "暴增",
    "减少", "下降", "降低", "减弱", "下调", "缓解", "收缩", "减速", "放缓", "骤降", "锐减",
    "突变", "波动", "起伏", "转向", "逆转", "爆发", "骤升", "骤减",
    "increase", "rise", "surge", "spike", "escalate", "intensify", "ramp",
    "decrease", "drop", "decline", "reduce", "fall", "ease", "weaken", "slow",
    "shift", "swing", "reverse", "onset", "outbreak",
)
_PERTURBATION_INTENSITY_TERMS = (
    "极端", "强", "弱", "高强度", "低强度", "重度", "轻度", "严重", "剧烈", "大幅", "小幅",
    "等级", "级别", "阈值", "峰值", "强度", "幅度", "量级",
    "extreme", "severe", "heavy", "intense", "magnitude", "intensity", "level",
    "threshold", "peak",
)
_PERTURBATION_ACTION_TERMS = (
    "限行", "管控", "封控", "调度", "干预", "投放", "泄漏", "排放", "停产", "停运", "关闭",
    "疏散", "撤离", "管制", "施加", "注入", "切断", "中断", "封锁", "扰动", "冲击", "压力",
    "政策", "措施", "事件", "灾害", "异常",
    "policy", "intervention", "shock", "disturbance", "perturbation", "leak",
    "spill", "shutdown", "evacuation", "restriction", "injection", "disruption",
    "lockdown", "deploy",
)


def _variable_text_blob(item: Dict[str, Any]) -> str:
    if not isinstance(item, dict):
        return ""
    parts: List[str] = []
    for key in ("name", "title", "description", "detail", "summary", "type", "category"):
        parts.append(_safe_text(item.get(key)))
    for key in ("expected_effects", "effects"):
        value = item.get(key)
        if isinstance(value, (list, tuple)):
            parts.extend(_safe_text(effect) for effect in value)
    return " ".join(part for part in parts if part).lower()


def _detect_variable_direction(item: Dict[str, Any]) -> Optional[str]:
    """Return an explicit direction string if the variable encodes one."""
    explicit = _safe_text(item.get("direction")).lower()
    if explicit:
        return explicit
    blob = _variable_text_blob(item)
    if not blob:
        return None
    for term in _PERTURBATION_DIRECTION_TERMS:
        if term in blob:
            return term
    return None


def _detect_variable_intensity(item: Dict[str, Any]) -> Optional[str]:
    """Return an intensity / magnitude marker if the variable encodes one."""
    for key in ("intensity", "magnitude", "level", "强度", "幅度"):
        explicit = _safe_text(item.get(key))
        if explicit:
            return explicit.lower()
    blob = _variable_text_blob(item)
    if not blob:
        return None
    for term in _PERTURBATION_INTENSITY_TERMS:
        if term in blob:
            return term
    return None


def _is_true_perturbation_variable(item: Dict[str, Any]) -> bool:
    """A variable is a real injected perturbation only if it has change semantics.

    This is the machine gate that the system prompt previously only *described*.
    Pure baseline / weather-baseline pseudo-variables fail here and are reclassified
    as stable-context, even when they slipped past _is_baseline_context_variable.
    """
    if not isinstance(item, dict):
        return False
    if _is_baseline_context_variable(item):
        return False
    if _detect_variable_direction(item):
        return True
    if _detect_variable_intensity(item):
        return True
    blob = _variable_text_blob(item)
    return any(term in blob for term in _PERTURBATION_ACTION_TERMS)


def _classify_variable(item: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate a normalized variable with its epistemic role and change signal.

    Returns the same dict with additive keys: epistemic_role
    ("perturbation"|"stable_context"), direction, intensity. Contract keys
    (name/type/description/...) are preserved untouched.
    """
    enriched = dict(item) if isinstance(item, dict) else {}
    direction = _detect_variable_direction(enriched)
    intensity = _detect_variable_intensity(enriched)
    is_perturbation = _is_true_perturbation_variable(enriched)
    enriched["direction"] = direction or _safe_text(enriched.get("direction")) or None
    enriched["intensity"] = intensity or _safe_text(enriched.get("intensity")) or None
    enriched["epistemic_role"] = "perturbation" if is_perturbation else "stable_context"
    if not is_perturbation:
        # Flag *why* it was demoted so the UI / downstream can be honest about it.
        enriched["context_reason"] = (
            "缺少方向/强度/扰动语义，按稳态背景处理（非注入变量）"
        )
    return enriched


def _split_variables_by_role(
    variables: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition normalized variables into (perturbations, stable_context)."""
    perturbations: List[Dict[str, Any]] = []
    stable_context: List[Dict[str, Any]] = []
    for item in variables or []:
        if not isinstance(item, dict):
            continue
        classified = _classify_variable(item)
        if classified.get("epistemic_role") == "perturbation":
            perturbations.append(classified)
        else:
            stable_context.append(classified)
    return perturbations, stable_context


def _parse_jsonish(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return fallback


def _normalize_initial_variables(value: Any) -> List[Dict[str, Any]]:
    raw = _parse_jsonish(value, None)
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("variables") if isinstance(raw.get("variables"), list) else [raw]
    else:
        text = _safe_text(value)
        if not text:
            return []
        lines = [line.strip("-• \t") for line in text.splitlines() if line.strip()]
        items = [{"name": line[:48], "description": line} for line in lines]

    normalized = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            item = {"name": item[:48], "description": item}
        if not isinstance(item, dict):
            continue
        name = _safe_text(item.get("name")) or f"初始变量 {index}"
        base = {
            "variable_id": _safe_text(item.get("variable_id") or item.get("input_id")) or f"scene_variable_{index}",
            "input_id": _safe_text(item.get("input_id") or item.get("variable_id")) or f"scene_variable_{index}",
            "name": name,
            "type": _safe_text(item.get("type")) or "custom",
            "description": _safe_text(item.get("description") or item.get("detail")) or name,
            "expected_effects": [
                _safe_text(effect)
                for effect in (item.get("expected_effects") or item.get("effects") or [])
                if _safe_text(effect)
            ],
            "target_regions": [
                _safe_text(region)
                for region in (item.get("target_regions") or item.get("targets") or [])
                if _safe_text(region)
            ],
            "target_region_ids": [
                _safe_text(region)
                for region in (item.get("target_region_ids") or [])
                if _safe_text(region)
            ],
            "target_entity_ids": [
                _safe_text(entity)
                for entity in (item.get("target_entity_ids") or item.get("target_nodes") or [])
                if _safe_text(entity)
            ],
            "atomic_keys": [
                _safe_text(key)
                for key in (item.get("atomic_keys") or [])
                if _safe_text(key)
            ],
            "action_primitives": [
                _safe_text(key)
                for key in (item.get("action_primitives") or [])
                if _safe_text(key)
            ],
            "executor_capability_keys": [
                _safe_text(key)
                for key in (item.get("executor_capability_keys") or [])
                if _safe_text(key)
            ],
            "source_origin": _safe_text(item.get("source_origin")) or "user_input",
        }
        # Carry through any explicit change semantics the caller already provided
        # so the perturbation gate can read them before falling back to text.
        for passthrough in (
            "direction",
            "intensity",
            "intensity_0_100",
            "magnitude",
            "time_window",
            "start_round",
            "duration_rounds",
        ):
            explicit = _safe_text(item.get(passthrough))
            if explicit:
                base[passthrough] = explicit
        # Annotate role/direction/intensity in code (the machine gate), not prompt.
        normalized.append(_classify_variable(base))
    return normalized


def _normalize_points(value: Any) -> List[Dict[str, Any]]:
    raw = _parse_jsonish(value, [])
    if isinstance(raw, dict):
        raw = raw.get("points") or [raw]
    if not isinstance(raw, list):
        return []

    points = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        lat = _coerce_float(item.get("lat") or item.get("latitude"))
        lon = _coerce_float(item.get("lon") or item.get("lng") or item.get("longitude"))
        if lat is None or lon is None:
            continue
        points.append(
            {
                "name": _safe_text(item.get("name") or item.get("label")) or f"地图点位 {index}",
                "role": _safe_text(item.get("role")) or ("primary_anchor" if index == 1 else "related_place"),
                "lat": lat,
                "lon": lon,
                "confidence": float(item.get("confidence") or 0.82),
                "source": _safe_text(item.get("source")) or "user_map",
            }
        )
    return points


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n...(已截断，原文 {len(text)} 字，当前传入 {limit} 字)..."


def _multiline_lines(value: Any) -> List[str]:
    text = _safe_text(value)
    if not text:
        return []
    return [
        line.strip().lstrip("-•").strip()
        for line in text.splitlines()
        if line.strip()
    ]


class SceneMaterialGenerator:
    SCENE_SEEDS_DIR = os.path.join(Config.UPLOAD_FOLDER, "scene_seeds")
    SEED_FILENAME = "scene_seed.json"
    REPORT_FILENAME = "scene_report.md"

    def __init__(self, llm_client: Optional[LLMClient] = None, use_llm: bool = True):
        self.llm_client = llm_client
        if not use_llm:
            self.llm_client = None
        elif self.llm_client is None:
            try:
                self.llm_client = LLMClient()
            except Exception as exc:
                logger.warning(f"Scene composer LLM init failed, fallback mode only: {exc}")

    @classmethod
    def _ensure_root(cls) -> None:
        os.makedirs(cls.SCENE_SEEDS_DIR, exist_ok=True)

    @classmethod
    def _seed_dir(cls, scene_id: str) -> str:
        return os.path.join(cls.SCENE_SEEDS_DIR, scene_id)

    @classmethod
    def _seed_file(cls, scene_id: str, filename: str) -> str:
        return os.path.join(cls._seed_dir(scene_id), filename)

    @classmethod
    def get_seed(cls, scene_id: str) -> Optional[Dict[str, Any]]:
        path = cls._seed_file(scene_id, cls.SEED_FILENAME)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def get_report_text(cls, scene_id: str) -> str:
        path = cls._seed_file(scene_id, cls.REPORT_FILENAME)
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def compose(
        self,
        *,
        payload: Dict[str, Any],
        uploaded_files: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        scene_id = f"scene_{uuid.uuid4().hex[:12]}"
        self._ensure_root()
        os.makedirs(self._seed_dir(scene_id), exist_ok=True)

        document_texts, file_infos = self._extract_uploaded_documents(scene_id, uploaded_files or [])
        selected_points = _normalize_points(payload.get("selected_points"))
        initial_variables = _normalize_initial_variables(payload.get("initial_variables"))
        map_context = self._load_map_context(_safe_text(payload.get("map_seed_id")))
        effort_snapshot = self._resolve_effort_snapshot(payload, map_context)

        input_bundle = self._build_input_bundle(
            scene_id=scene_id,
            payload=payload,
            document_texts=document_texts,
            file_infos=file_infos,
            selected_points=selected_points,
            initial_variables=initial_variables,
            map_context=map_context,
            effort_snapshot=effort_snapshot,
        )

        semantic_artifact = SemanticInputNormalizer(
            llm_client=self.llm_client,
            use_llm=self.llm_client is not None,
        ).normalize_scene(
            payload={**payload, "initial_variables": initial_variables},
            document_texts=document_texts,
            map_context=map_context,
            previous_artifact_ref=payload.get("semantic_artifact_ref"),
        )
        generated = (
            self._generate_with_llm(input_bundle, semantic_artifact)
            or self._fallback_generate(input_bundle, semantic_artifact)
        )
        seed = self._finalize_seed(scene_id, input_bundle, generated, semantic_artifact)
        self._save_seed(seed)
        return seed

    def revise(
        self,
        *,
        scene_id: str,
        instruction: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        seed = self.get_seed(scene_id)
        if not seed:
            raise ValueError(f"场景素材不存在: {scene_id}")
        payload = payload or {}
        instruction = _safe_text(instruction)
        if not instruction:
            raise ValueError("请提供修改说明")

        existing_effort = seed.get("effort_snapshot")
        if existing_effort:
            existing_effort = normalize_effort_snapshot(existing_effort)
            requested_snapshot_id = payload.get("effort_snapshot_id")
            if requested_snapshot_id:
                assert_effort_reference(
                    existing_effort,
                    effort_snapshot_id=requested_snapshot_id,
                    requested_level=payload.get("effort_level"),
                )
        else:
            existing_effort = build_effort_snapshot(
                payload.get("effort_level") or "high",
                effort_snapshot_id=payload.get("effort_snapshot_id"),
            )

        existing_report = _safe_text(payload.get("current_report")) or self.get_report_text(scene_id) or seed.get("report_markdown", "")
        merged_variables = _normalize_initial_variables(payload.get("initial_variables"))
        if not merged_variables:
            merged_variables = seed.get("initial_variables") or []

        semantic_payload = {
            **(seed.get("input") or {}),
            **payload,
            "additional_context": "\n".join(
                item for item in [
                    _safe_text((seed.get("input") or {}).get("additional_context")),
                    f"本次修订要求：{instruction}",
                ] if item
            ),
            "initial_variables": merged_variables,
        }
        semantic_normalizer = SemanticInputNormalizer(
            llm_client=self.llm_client,
            use_llm=self.llm_client is not None,
        )
        map_context = self._load_map_context(_safe_text((seed.get("input") or {}).get("map_seed_id")))
        previous_semantic_ref = seed.get("semantic_artifact_ref")
        if not previous_semantic_ref:
            backfilled_artifact = semantic_normalizer.normalize_scene(
                payload=semantic_payload,
                document_texts=[],
                map_context=map_context,
            )
            previous_semantic_ref = SemanticArtifactStore.public_ref(backfilled_artifact)
        semantic_artifact = semantic_normalizer.normalize_revision(
            instruction=instruction,
            previous_artifact_ref=previous_semantic_ref,
            target_catalog=semantic_normalizer._target_catalog(map_context),
            default_region_ids=semantic_normalizer._default_region_ids(map_context),
        )

        prompt = {
            "task": "Revise an existing EnvFish scene material report.",
            "instruction": instruction,
            "existing_scene_seed": {key: value for key, value in seed.items() if key != "report_markdown"},
            "existing_report_markdown": _truncate(existing_report, 20000),
            "semantic_input": semantic_artifact.model_dump(mode="json"),
            "rules": [
                "Preserve confirmed map locations unless the instruction explicitly changes them.",
                "Keep the report suitable for downstream entity, relation, region, agent, and risk extraction.",
                "Return the same JSON schema as the compose endpoint.",
            ],
        }
        generated = None
        if self.llm_client:
            try:
                generated = self.llm_client.chat_json(
                    messages=[
                        {"role": "system", "content": SCENE_COMPOSER_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                    ],
                    temperature=0.25,
                    max_tokens=7000,
                )
            except Exception as exc:
                logger.warning(f"Scene revision LLM failed, using fallback: {exc}")

        if not generated:
            generated = dict(seed)
            generated["report_markdown"] = self._append_revision_note(existing_report, instruction, merged_variables)
            generated["initial_variables"] = self._semantic_variables(semantic_artifact)

        revised = dict(seed)
        revised.update(self._sanitize_generated_payload(generated))
        revised["scene_id"] = scene_id
        revised["effort_snapshot"] = existing_effort
        revised["semantic_artifact_ref"] = SemanticArtifactStore.public_ref(semantic_artifact)
        revised["semantic_revision"] = semantic_artifact.revision
        revised["scene_semantics"] = semantic_artifact.scene.model_dump(mode="json")
        revised["normalized_event_inputs"] = [item.model_dump(mode="json") for item in semantic_artifact.events]
        revised["normalized_policy_inputs"] = [item.model_dump(mode="json") for item in semantic_artifact.policies]
        revised["updated_at"] = datetime.now().isoformat()
        revised["revision_history"] = [
            *(seed.get("revision_history") or []),
            {
                "instruction": instruction,
                "updated_at": revised["updated_at"],
            },
        ]
        revised["initial_variables"] = self._semantic_variables(semantic_artifact)
        existing_stable_context = list(seed.get("stable_context_variables") or [])
        existing_descriptions = {
            _safe_text(item.get("description"))
            for item in existing_stable_context
            if isinstance(item, dict)
        }
        revised["stable_context_variables"] = [
            *existing_stable_context,
            *[
            {
                "name": item[:48] or "稳态背景",
                "type": "custom",
                "description": item,
                "epistemic_role": "stable_context",
            }
            for item in semantic_artifact.scene.stable_contexts
            if item not in existing_descriptions
            ],
        ]
        self._save_seed(revised)
        return revised

    def _extract_uploaded_documents(self, scene_id: str, uploaded_files: Iterable[Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
        file_dir = self._seed_file(scene_id, "files")
        os.makedirs(file_dir, exist_ok=True)

        document_texts: List[str] = []
        file_infos: List[Dict[str, Any]] = []
        for file in uploaded_files:
            filename = getattr(file, "filename", "") or ""
            if not filename:
                continue
            suffix = Path(filename).suffix.lower()
            if suffix not in FileParser.SUPPORTED_EXTENSIONS:
                continue
            saved_name = f"{uuid.uuid4().hex[:8]}{suffix}"
            path = os.path.join(file_dir, saved_name)
            file.save(path)
            text = TextProcessor.preprocess_text(FileParser.extract_text(path))
            if text:
                document_texts.append(text)
            file_infos.append(
                {
                    "filename": filename,
                    "saved_filename": saved_name,
                    "size": os.path.getsize(path),
                    "text_length": len(text),
                }
            )
        return document_texts, file_infos

    def _load_map_context(self, map_seed_id: str) -> Dict[str, Any]:
        if not map_seed_id:
            return {}
        seed = MapSeedManager.get_seed(map_seed_id) or {}
        graph = MapSeedManager.get_graph_snapshot(map_seed_id) or {}
        report_text = MapSeedManager.get_report_text(map_seed_id)
        layers = MapSeedManager.get_layers(map_seed_id) or {}
        return {
            "map_seed_id": map_seed_id,
            "seed": seed,
            "graph_stats": graph.get("stats") or {},
            "graph_data": graph.get("graph_data") or graph,
            "report_text": report_text,
            "layers_summary": {
                "layer_count": len(layers.get("layers") or []) if isinstance(layers, dict) else 0,
                "center": layers.get("center") if isinstance(layers, dict) else None,
            },
        }

    @staticmethod
    def _resolve_effort_snapshot(
        payload: Dict[str, Any],
        map_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        map_seed = map_context.get("seed") if isinstance(map_context.get("seed"), dict) else {}
        seed_snapshot = map_seed.get("effort_snapshot") if isinstance(map_seed, dict) else None
        requested_id = payload.get("effort_snapshot_id")
        requested_level = payload.get("effort_level")
        if seed_snapshot:
            resolved = normalize_effort_snapshot(seed_snapshot)
            if requested_id:
                assert_effort_reference(
                    resolved,
                    effort_snapshot_id=requested_id,
                    requested_level=requested_level,
                )
            return resolved
        return build_effort_snapshot(
            requested_level or "high",
            effort_snapshot_id=requested_id,
        )

    def _build_input_bundle(
        self,
        *,
        scene_id: str,
        payload: Dict[str, Any],
        document_texts: List[str],
        file_infos: List[Dict[str, Any]],
        selected_points: List[Dict[str, Any]],
        initial_variables: List[Dict[str, Any]],
        map_context: Dict[str, Any],
        effort_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        scene_type = _safe_text(payload.get("scene_type")) or "custom"
        location = _safe_text(payload.get("location"))
        time_scope = _safe_text(payload.get("time_scope"))
        event_or_baseline = _safe_text(payload.get("event_or_baseline"))
        focus = _safe_text(payload.get("focus"))
        additional_context = _safe_text(payload.get("additional_context"))
        known_entities = _safe_text(payload.get("known_entities"))
        analysis_boundaries = _safe_text(payload.get("analysis_boundaries"))
        report_questions = _safe_text(payload.get("report_questions"))
        simulation_requirement = (
            _safe_text(payload.get("simulation_requirement"))
            or report_questions
            or focus
            or event_or_baseline
        )

        return {
            "scene_id": scene_id,
            "scene_type": scene_type,
            "location": location,
            "time_scope": time_scope,
            "event_or_baseline": event_or_baseline,
            "focus": focus,
            "simulation_requirement": simulation_requirement,
            "additional_context": additional_context,
            "known_entities": known_entities,
            "analysis_boundaries": analysis_boundaries,
            "report_questions": report_questions,
            "document_texts": document_texts,
            "uploaded_files": file_infos,
            "selected_points": selected_points,
            "initial_variables": initial_variables,
            "map_context": map_context,
            "effort_snapshot": effort_snapshot,
            "created_at": datetime.now().isoformat(),
        }

    def _generate_with_llm(
        self,
        input_bundle: Dict[str, Any],
        semantic_artifact: SemanticInputArtifact,
    ) -> Optional[Dict[str, Any]]:
        if not self.llm_client:
            return None
        prompt = {
            "task": "Compose an EnvFish scene material report.",
            "semantic_input": semantic_artifact.model_dump(mode="json"),
            "scene_type": input_bundle["scene_type"],
            "selected_points": input_bundle["selected_points"],
            "uploaded_files": input_bundle["uploaded_files"],
            "document_excerpt": _truncate("\n\n---\n\n".join(input_bundle["document_texts"]), 24000),
            "map_context": {
                "map_seed_id": input_bundle["map_context"].get("map_seed_id"),
                "seed_summary": (input_bundle["map_context"].get("seed") or {}).get("summary"),
                "graph_stats": input_bundle["map_context"].get("graph_stats"),
                "map_report_excerpt": _truncate(input_bundle["map_context"].get("report_text") or "", 12000),
                "layers_summary": input_bundle["map_context"].get("layers_summary"),
            },
            "report_required_sections": [
                "0. 文档用途与推演边界",
                "1. 场景摘要",
                "2. 时间范围或稳态周期",
                "3. 区域背景",
                "4. 可建模区域清单",
                "5. 主体与 agent 画像",
                "6. 关键设施与环境载体",
                "7. 关键关系网络",
                "8. 推演变量与指标",
                "9. 风险链条或稳定反馈链",
                "10. 可推演情景分支",
                "11. 分析边界与排除项",
                "12. 重点追问",
                "13. Agent 抽取提示",
                "14. 关键不确定性",
                "15. 参考事实锚点",
            ],
        }
        try:
            return self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SCENE_COMPOSER_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.25,
                max_tokens=8000,
            )
        except Exception as exc:
            logger.warning(f"Scene compose LLM failed, using fallback: {exc}")
            return None

    def _fallback_generate(
        self,
        input_bundle: Dict[str, Any],
        semantic_artifact: SemanticInputArtifact,
    ) -> Dict[str, Any]:
        """Build a source-grounded report from the validated semantic artifact."""
        title_subject = input_bundle["location"] or input_bundle["event_or_baseline"] or "未命名场景"
        scene_label = {
            "historical_event": "历史事件",
            "stable_environment": "环境稳态",
            "hybrid": "混合场景",
        }.get(input_bundle["scene_type"], "自定义场景")
        title = f"{title_subject}{scene_label}素材报告"
        selected_points = input_bundle["selected_points"]
        primary_point = selected_points[0] if selected_points else {}
        map_report = input_bundle["map_context"].get("report_text") or ""
        document_excerpt = _truncate("\n\n".join(input_bundle["document_texts"]), 5000)
        perturbations = self._semantic_variables(semantic_artifact)
        stable_context = [
            {
                "name": item[:48] or "稳态背景",
                "type": "custom",
                "description": item,
                "epistemic_role": "stable_context",
            }
            for item in semantic_artifact.scene.stable_contexts
        ]

        def _echo_lines(value: Any, empty_note: str) -> List[str]:
            lines = [f"- {item}" for item in _multiline_lines(value)]
            return lines or [f"- {empty_note}"]

        known_entity_lines = _echo_lines(
            input_bundle["known_entities"], "用户未提供已知主体 / 设施 / 环境对象。"
        )
        boundary_lines = _echo_lines(
            input_bundle["analysis_boundaries"], "用户未提供明确排除项。"
        )
        report_question_lines = _echo_lines(
            input_bundle["report_questions"], "用户未提供重点追问。"
        )

        source_lines = []
        if input_bundle["uploaded_files"]:
            source_lines.append(f"- 上传文档 {len(input_bundle['uploaded_files'])} 个。")
        if selected_points:
            source_lines.append(f"- 用户标注地图点位 {len(selected_points)} 个。")
        if input_bundle["map_context"].get("map_seed_id"):
            source_lines.append(f"- 已关联地图种子 {input_bundle['map_context']['map_seed_id']}。")
        if not source_lines:
            source_lines.append("- 当前仅使用用户输入文本生成。")

        point_lines = [
            f"- {point['name']}：{point['lat']}, {point['lon']}，角色 {point['role']}。"
            for point in selected_points
        ] or ["- 用户尚未确认地图点位。"]

        event_lines = [f"- **{item.name}**：{item.description}" for item in semantic_artifact.events]
        policy_lines = [f"- **{item.name}**：{item.intent}" for item in semantic_artifact.policies]
        stable_context_lines = [f"- {item}" for item in semantic_artifact.scene.stable_contexts]

        report = "\n".join(
            [
                f"# {title}",
                "",
                "## 场景摘要",
                f"- 场景类型：{scene_label}",
                f"- 核心地点：{semantic_artifact.scene.location or input_bundle['location'] or '当前分析区域'}",
                f"- 推演目标：{semantic_artifact.scene.simulation_requirement or input_bundle['simulation_requirement'] or '分析场景变化及其影响'}",
                "",
                "## 稳态背景",
                *(stable_context_lines or ["- 以用户提供的区域背景为基线。"]),
                "",
                "## 事件与压力",
                *(event_lines or ["- 当前场景以稳态背景为主。"]),
                "",
                "## 政策与干预",
                *(policy_lines or ["- 当前未设置独立政策措施。"]),
                "",
                "## 输入来源",
                *source_lines,
                "",
                "## 区域与空间锚点",
                *point_lines,
                "",
                "## 地图背景",
                map_report.strip() or "分析范围以用户提供的地点、区域背景和场景文本为准。",
                "",
                "## 参考材料",
                document_excerpt or "事实锚点来自当前场景输入。",
                "",
                "## 已知主体、设施与环境对象",
                *known_entity_lines,
                "",
                "## 分析边界",
                *boundary_lines,
                "",
                "## 重点问题",
                *report_question_lines,
            ]
        )

        return {
            "title": title,
            "scene_type": input_bundle["scene_type"],
            "source_mode": self._infer_source_mode(input_bundle),
            "recommended_simulation_requirement": input_bundle["simulation_requirement"] or input_bundle["report_questions"] or input_bundle["focus"] or title,
            "locations": selected_points,
            "area_of_interest": {
                "label": primary_point.get("name") or input_bundle["location"] or title_subject,
                "center": {
                    "lat": primary_point.get("lat"),
                    "lon": primary_point.get("lon"),
                },
                "radius_m": None,
                "rationale": "根据用户已确认输入和地图标注确定的初始分析范围。",
            },
            "initial_variables": perturbations,
            "stable_context_variables": stable_context,
            "assumptions": list(semantic_artifact.assumptions),
            "uncertainties": [],
            "fallback_mode": "honest_skeleton",
            "report_markdown": report,
        }

    def _infer_source_mode(self, input_bundle: Dict[str, Any]) -> str:
        has_doc = bool(input_bundle.get("document_texts"))
        has_map = bool(input_bundle.get("selected_points") or input_bundle.get("map_context", {}).get("map_seed_id"))
        if has_doc and has_map:
            return "document_map_hybrid"
        if has_doc:
            return "document_only"
        if has_map:
            return "map_only"
        return "text_only"

    def _sanitize_generated_payload(self, generated: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(generated, dict):
            generated = {}
        report = _safe_text(generated.get("report_markdown"))
        title = _safe_text(generated.get("title")) or "场景素材报告"
        if not report:
            report = f"# {title}\n\n本报告依据当前场景输入整理分析范围、事件、政策和空间对象。"
        raw_variables = generated.get("initial_variables") if isinstance(generated.get("initial_variables"), list) else []
        # Machine gate: only true perturbations (direction/intensity/change semantics)
        # stay in initial_variables; everything else is demoted to stable_context so
        # downstream extraction does not treat a baseline reading as a driver.
        classified_variables = [
            _classify_variable(item) for item in raw_variables if isinstance(item, dict)
        ]
        initial_variables = [
            item for item in classified_variables if item.get("epistemic_role") == "perturbation"
        ]
        # Honor any stable-context already partitioned upstream (additive contract key).
        carried_context = (
            generated.get("stable_context_variables")
            if isinstance(generated.get("stable_context_variables"), list)
            else []
        )
        stable_context_variables = [
            _classify_variable(item)
            for item in carried_context
            if isinstance(item, dict)
        ] + [
            item for item in classified_variables if item.get("epistemic_role") != "perturbation"
        ]
        return {
            "title": title,
            "scene_type": _safe_text(generated.get("scene_type")) or "custom",
            "source_mode": _safe_text(generated.get("source_mode")) or "text_only",
            "recommended_simulation_requirement": _safe_text(generated.get("recommended_simulation_requirement")) or title,
            "locations": generated.get("locations") if isinstance(generated.get("locations"), list) else [],
            "area_of_interest": generated.get("area_of_interest") if isinstance(generated.get("area_of_interest"), dict) else {},
            "initial_variables": initial_variables,
            "stable_context_variables": stable_context_variables,
            "assumptions": generated.get("assumptions") if isinstance(generated.get("assumptions"), list) else [],
            "uncertainties": generated.get("uncertainties") if isinstance(generated.get("uncertainties"), list) else [],
            "fallback_mode": _safe_text(generated.get("fallback_mode")) or None,
            "report_markdown": report,
        }

    def _finalize_seed(
        self,
        scene_id: str,
        input_bundle: Dict[str, Any],
        generated: Dict[str, Any],
        semantic_artifact: SemanticInputArtifact,
    ) -> Dict[str, Any]:
        sanitized = self._sanitize_generated_payload(generated)
        if not sanitized["locations"] and input_bundle["selected_points"]:
            sanitized["locations"] = input_bundle["selected_points"]
        if not sanitized["initial_variables"] and not sanitized.get("stable_context_variables") and input_bundle["initial_variables"]:
            # Re-run the machine gate against the user-supplied variables so the
            # two tracks stay populated even when the LLM/fallback dropped them.
            perturbations, stable_context = _split_variables_by_role(input_bundle["initial_variables"])
            sanitized["initial_variables"] = perturbations
            sanitized["stable_context_variables"] = stable_context
        if not sanitized["source_mode"]:
            sanitized["source_mode"] = self._infer_source_mode(input_bundle)
        semantic_variables = self._semantic_variables(semantic_artifact)
        if semantic_variables:
            sanitized["initial_variables"] = semantic_variables
        if semantic_artifact.scene.stable_contexts:
            _, source_stable_context = _split_variables_by_role(input_bundle["initial_variables"])
            known_descriptions = {
                _safe_text(item.get("description")) for item in source_stable_context if isinstance(item, dict)
            }
            semantic_stable_context = [
                {
                    "name": item[:48] or "稳态背景",
                    "type": "custom",
                    "description": item,
                    "epistemic_role": "stable_context",
                }
                for item in semantic_artifact.scene.stable_contexts
                if item not in known_descriptions
            ]
            sanitized["stable_context_variables"] = [*source_stable_context, *semantic_stable_context]
        return {
            "scene_id": scene_id,
            "status": "draft",
            "created_at": input_bundle["created_at"],
            "updated_at": datetime.now().isoformat(),
            "effort_snapshot": input_bundle["effort_snapshot"],
            "semantic_artifact_ref": SemanticArtifactStore.public_ref(semantic_artifact),
            "semantic_revision": semantic_artifact.revision,
            "scene_semantics": semantic_artifact.scene.model_dump(mode="json"),
            "normalized_event_inputs": [item.model_dump(mode="json") for item in semantic_artifact.events],
            "normalized_policy_inputs": [item.model_dump(mode="json") for item in semantic_artifact.policies],
            "input": {
                "location": input_bundle["location"],
                "time_scope": input_bundle["time_scope"],
                "event_or_baseline": input_bundle["event_or_baseline"],
                "focus": input_bundle["focus"],
                "additional_context": input_bundle["additional_context"],
                "known_entities": input_bundle["known_entities"],
                "analysis_boundaries": input_bundle["analysis_boundaries"],
                "report_questions": input_bundle["report_questions"],
                "simulation_requirement": input_bundle["simulation_requirement"],
                "uploaded_files": input_bundle["uploaded_files"],
                "map_seed_id": input_bundle["map_context"].get("map_seed_id"),
                "effort_snapshot_id": input_bundle["effort_snapshot"].get("effort_snapshot_id"),
                "selected_points": input_bundle["selected_points"],
            },
            **sanitized,
        }

    @staticmethod
    def _semantic_variables(semantic_artifact: SemanticInputArtifact) -> List[Dict[str, Any]]:
        variables: List[Dict[str, Any]] = []
        for item in semantic_artifact.events:
            variables.append({
                "variable_id": item.input_id,
                "input_id": item.input_id,
                "type": "disaster",
                "name": item.name,
                "description": item.description,
                "direction": item.intensity.direction or None,
                "intensity": item.intensity.label_zh or item.intensity.score,
                "intensity_0_100": item.intensity.score,
                "target_region_ids": list(item.target_region_ids),
                "target_entity_ids": list(item.target_entity_ids),
                "atomic_keys": list(item.atomic_keys),
                "expected_effects": list(item.expected_effects),
                "source_origin": item.source_origin,
                "epistemic_role": "perturbation",
            })
        for item in semantic_artifact.policies:
            variables.append({
                "variable_id": item.input_id,
                "input_id": item.input_id,
                "type": "policy",
                "name": item.name,
                "description": item.intent,
                "intent": item.intent,
                "direction": item.intensity.direction or None,
                "intensity": item.intensity.label_zh or item.intensity.score,
                "intensity_0_100": item.intensity.score,
                "target_region_ids": list(item.target_region_ids),
                "target_entity_ids": list(item.target_entity_ids),
                "action_primitives": list(item.action_primitives),
                "executor_capability_keys": list(item.executor_capability_keys),
                "expected_effects": list(item.expected_effects),
                "source_origin": item.source_origin,
                "epistemic_role": "perturbation",
            })
        return variables

    def _save_seed(self, seed: Dict[str, Any]) -> None:
        scene_id = seed["scene_id"]
        os.makedirs(self._seed_dir(scene_id), exist_ok=True)
        with open(self._seed_file(scene_id, self.SEED_FILENAME), "w", encoding="utf-8") as handle:
            json.dump(seed, handle, ensure_ascii=False, indent=2)
        with open(self._seed_file(scene_id, self.REPORT_FILENAME), "w", encoding="utf-8") as handle:
            handle.write(seed.get("report_markdown") or "")

    def _append_revision_note(
        self,
        existing_report: str,
        instruction: str,
        variables: List[Dict[str, Any]],
    ) -> str:
        variable_lines = [
            f"- {item.get('name')}: {item.get('description')}"
            for item in variables
        ] or ["- 本次修改未提供新的结构化变量。"]
        return "\n".join(
            [
                existing_report.rstrip(),
                "",
                "## 修订说明",
                f"- 用户修改要求: {instruction}",
                "",
                "### 修订后的初始变量",
                *variable_lines,
            ]
        ).strip()
