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
from .map_seed_manager import MapSeedManager
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
    {"name": "变量名", "type": "weather|policy|pollution|traffic|public_health|resource|custom", "description": "变量描述", "expected_effects": ["影响1"]}
  ],
  "assumptions": ["推演假设"],
  "uncertainties": ["不确定性"],
  "report_markdown": "# 标题\\n..."
}
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
        normalized.append(
            {
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
            }
        )
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

        input_bundle = self._build_input_bundle(
            scene_id=scene_id,
            payload=payload,
            document_texts=document_texts,
            file_infos=file_infos,
            selected_points=selected_points,
            initial_variables=initial_variables,
            map_context=map_context,
        )

        generated = self._generate_with_llm(input_bundle) or self._fallback_generate(input_bundle)
        seed = self._finalize_seed(scene_id, input_bundle, generated)
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

        existing_report = _safe_text(payload.get("current_report")) or self.get_report_text(scene_id) or seed.get("report_markdown", "")
        merged_variables = _normalize_initial_variables(payload.get("initial_variables"))
        if not merged_variables:
            merged_variables = seed.get("initial_variables") or []

        prompt = {
            "task": "Revise an existing EnvFish scene material report.",
            "instruction": instruction,
            "existing_scene_seed": {key: value for key, value in seed.items() if key != "report_markdown"},
            "existing_report_markdown": _truncate(existing_report, 20000),
            "updated_initial_variables": merged_variables,
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
            generated["initial_variables"] = merged_variables

        revised = dict(seed)
        revised.update(self._sanitize_generated_payload(generated))
        revised["scene_id"] = scene_id
        revised["updated_at"] = datetime.now().isoformat()
        revised["revision_history"] = [
            *(seed.get("revision_history") or []),
            {
                "instruction": instruction,
                "updated_at": revised["updated_at"],
            },
        ]
        if merged_variables:
            revised["initial_variables"] = merged_variables
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
            "created_at": datetime.now().isoformat(),
        }

    def _generate_with_llm(self, input_bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.llm_client:
            return None
        prompt = {
            "task": "Compose an EnvFish scene material report.",
            "scene_input": {
                "scene_type": input_bundle["scene_type"],
                "location": input_bundle["location"],
                "time_scope": input_bundle["time_scope"],
                "event_or_baseline": input_bundle["event_or_baseline"],
                "focus": input_bundle["focus"],
                "simulation_requirement": input_bundle["simulation_requirement"],
                "additional_context": input_bundle["additional_context"],
                "known_entities": input_bundle["known_entities"],
                "analysis_boundaries": input_bundle["analysis_boundaries"],
                "report_questions": input_bundle["report_questions"],
                "selected_points": input_bundle["selected_points"],
                "initial_variables": input_bundle["initial_variables"],
                "uploaded_files": input_bundle["uploaded_files"],
            },
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

    def _fallback_generate(self, input_bundle: Dict[str, Any]) -> Dict[str, Any]:
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
        variables = input_bundle["initial_variables"]
        known_entity_lines = [
            f"- {item}"
            for item in _multiline_lines(input_bundle["known_entities"])
        ] or ["- 暂未提供已知主体、设施或环境对象。"]
        boundary_lines = [
            f"- {item}"
            for item in _multiline_lines(input_bundle["analysis_boundaries"])
        ] or ["- 暂未提供明确排除项，默认围绕当前地点、半径和文档事实展开。"]
        report_question_lines = [
            f"- {item}"
            for item in _multiline_lines(input_bundle["report_questions"])
        ] or ["- 暂未提供重点追问，默认围绕稳态结构、关键关系和潜在扰动展开。"]

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
        ] or ["- 暂无确认地图点位；建议后续在地图上补充主锚点。"]
        variable_lines = [
            f"- {item['name']}：{item['description']}"
            for item in variables
        ] or ["- 暂无初始变量；可继续添加天气、政策、人流、污染、资源调度等变量。"]
        relation_lines = [
            "- 主区域承载居民、管理者、设施运营者和环境受体。",
            "- 交通、人流、物资流和信息流连接区域内外主体。",
            "- 初始变量会改变主体行为、设施负荷、环境状态和治理响应。",
        ]
        if selected_points:
            relation_lines.insert(0, f"- {primary_point.get('name')} 是当前场景的主要空间锚点。")

        report = "\n".join(
            [
                f"# {title}",
                "",
                "## 0. 文档用途与推演边界",
                "本报告由场景素材生成器生成，用于进入 EnvFish 后续图谱构建、环境搭建、agent 生成和多轮推演流程。",
                "报告中的地图、文档和用户变量需要在进入正式推演前由用户确认；不确定内容应作为推演假设，而不是事实结论。",
                "",
                "## 1. 场景摘要",
                f"- 场景类型: {scene_label}",
                f"- 地点: {input_bundle['location'] or '未明确'}",
                f"- 时间范围/稳态周期: {input_bundle['time_scope'] or '未明确'}",
                f"- 事件或稳态描述: {input_bundle['event_or_baseline'] or '未明确'}",
                f"- 重点关系 / 关注问题: {input_bundle['focus'] or '未明确'}",
                f"- 补充背景线索: {input_bundle['additional_context'] or '未提供'}",
                f"- 已知主体 / 设施 / 环境对象: {input_bundle['known_entities'] or '未提供'}",
                "",
                "## 2. 输入来源",
                *source_lines,
                "",
                "## 3. 区域背景",
                "当前区域背景由用户输入、上传文档和地图空间事实共同构成。后续推演应优先围绕已确认点位和文档中的真实地点展开。",
                *point_lines,
                "",
                "### 补充背景线索",
                input_bundle["additional_context"] or "当前未提供额外背景线索。",
                "",
                "## 4. 地图稳态与空间事实",
                map_report.strip() or "当前尚未生成地图稳态报告。若需要更强区域 grounding，请先在地图上选点并生成地图种子。",
                "",
                "## 5. 文档材料摘要",
                document_excerpt or "当前没有上传文档摘录。",
                "",
                "## 6. 主体与 agent 画像",
                "### 用户已知对象",
                *known_entity_lines,
                "",
                "- 居民或使用者：受环境状态、设施可达性、政策规则和信息传播影响。",
                "- 管理主体：负责监测、管控、维护、通告和资源协调。",
                "- 设施运营者：维持基础设施、交通、供应或服务节点运行。",
                "- 环境受体：包括水体、植被、动物栖息地、空气或土壤等可被推演的受影响对象。",
                "",
                "## 7. 关键关系网络",
                *relation_lines,
                "",
                "## 8. 初始变量",
                *variable_lines,
                "",
                "## 9. 推演变量与指标",
                "- 区域暴露水平、设施负荷、生态完整性、居民活动强度、治理响应速度、信息透明度、资源供应稳定性。",
                "",
                "## 10. 可推演情景分支",
                "- 基线情景：维持当前输入变量和空间稳态。",
                "- 强扰动情景：提高一个或多个初始变量强度，观察区域、主体和设施的连锁反应。",
                "- 干预情景：加入治理、资源、交通、监测或信息通告干预。",
                "",
                "## 11. 分析边界与排除项",
                *boundary_lines,
                "",
                "## 12. 重点追问",
                *report_question_lines,
                "",
                "## 13. Agent 抽取提示",
                "- 优先抽取真实区域、地图点位、设施、组织、人群和环境受体。",
                "- 将风险、压力、信任、舆情和稳定性作为状态指标，不要作为核心实体。",
                "",
                "## 14. 关键不确定性",
                "- 当前报告包含模板兜底内容，需用户确认关键事实。",
                "- 地图点位、文档地点和真实行政范围可能存在偏差。",
                "- 初始变量的强度、时间窗和影响方向需要在后续推演前进一步校准。",
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
                "rationale": "根据用户输入和地图标注确定的初始分析范围。",
            },
            "initial_variables": variables,
            "assumptions": ["部分内容由模板兜底生成，需用户在预览阶段确认。"],
            "uncertainties": ["缺少充分文档或地图事实时，主体与关系会偏模板化。"],
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
            report = f"# {title}\n\n当前没有生成报告正文，请补充场景信息后重试。"
        return {
            "title": title,
            "scene_type": _safe_text(generated.get("scene_type")) or "custom",
            "source_mode": _safe_text(generated.get("source_mode")) or "text_only",
            "recommended_simulation_requirement": _safe_text(generated.get("recommended_simulation_requirement")) or title,
            "locations": generated.get("locations") if isinstance(generated.get("locations"), list) else [],
            "area_of_interest": generated.get("area_of_interest") if isinstance(generated.get("area_of_interest"), dict) else {},
            "initial_variables": generated.get("initial_variables") if isinstance(generated.get("initial_variables"), list) else [],
            "assumptions": generated.get("assumptions") if isinstance(generated.get("assumptions"), list) else [],
            "uncertainties": generated.get("uncertainties") if isinstance(generated.get("uncertainties"), list) else [],
            "report_markdown": report,
        }

    def _finalize_seed(
        self,
        scene_id: str,
        input_bundle: Dict[str, Any],
        generated: Dict[str, Any],
    ) -> Dict[str, Any]:
        sanitized = self._sanitize_generated_payload(generated)
        if not sanitized["locations"] and input_bundle["selected_points"]:
            sanitized["locations"] = input_bundle["selected_points"]
        if not sanitized["initial_variables"] and input_bundle["initial_variables"]:
            sanitized["initial_variables"] = input_bundle["initial_variables"]
        if not sanitized["source_mode"]:
            sanitized["source_mode"] = self._infer_source_mode(input_bundle)
        return {
            "scene_id": scene_id,
            "status": "draft",
            "created_at": input_bundle["created_at"],
            "updated_at": datetime.now().isoformat(),
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
                "selected_points": input_bundle["selected_points"],
            },
            **sanitized,
        }

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
                "- 当前为无 LLM 兜底修订，建议继续补充具体段落要求后重新生成。",
                "",
                "### 修订后的初始变量",
                *variable_lines,
            ]
        ).strip()
