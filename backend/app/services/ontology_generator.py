"""
本体生成器（M3 本体抽取）

哲学定位（与 Kaleido 复杂生态沙盘一致）：
- 本体不是写死的 schema，而是**场景驱动**地现生成；
- **核心是"关系类型 / RELATION 边"**，而非实体列表——关系是一等公民；
- 关系边尽量携带复杂性词汇（channel / direction / sign），与
  validated_relation_graph 的 channel/direction/sign/loop_role/leverage 对齐；
- 诚实优先：结果带 `source` 字段（"llm" vs "deterministic_fallback"），
  不再像旧 stub 那样在无 LLM 时仍谎称"调用 LLM 生成本体"。

返回结构（向后兼容 api/graph.py 的读取）：
    {
        "entity_types": [{"name", "description"}, ...],   # 调用方读取
        "edge_types":   [{"name", "description", ...}, ...],# 调用方读取
        "analysis_summary": str,                            # 调用方读取
        # —— 以下为附加键（additive，调用方忽略也无妨）——
        "source": "llm" | "deterministic_fallback",
        "relation_vocabulary": {...},   # channel/direction/sign 取值空间说明
        "scenario_keywords": [...],     # fallback 用于推断的命中关键词
        "notes": str,
    }
"""

from typing import Any, Dict, List, Optional

from ..config import Config


# 开放实体类型词表（复杂生态本体的候选集合）。
# 任何场景都可在此基础上裁剪/扩展；fallback 据关键词命中挑选子集。
_OPEN_ENTITY_TYPES: Dict[str, str] = {
    "Actor": "参与并施加影响的主体（个人/组织/机构/群体）",
    "Region": "地理或生态空间单元（区域/流域/城市/栖息地）",
    "Resource": "被消耗、争夺或再生的资源（水/能源/资金/物资）",
    "Institution": "规则、政策、治理结构等制度性安排",
    "Infrastructure": "承载流动与服务的工程系统（管网/电网/交通/通信）",
    "Process": "随时间展开的动态过程（扩散/迁移/退化/恢复）",
    "EcologicalReceptor": "承受影响的生态受体（物种/种群/生态系统/人群）",
    "Risk": "风险或影响链路（潜在损害的累积/传导路径）",
    "Threshold": "阈值/临界点（越过即触发状态跃迁的拐点）",
}

# fallback 关键词 -> 额外纳入的实体类型。命中即扩类。
_ENTITY_KEYWORD_HINTS: Dict[str, List[str]] = {
    "Resource": ["水", "水资源", "能源", "电力", "粮食", "资金", "资源", "供给",
                 "water", "energy", "resource", "supply", "food", "fund"],
    "Institution": ["政策", "制度", "治理", "监管", "法规", "政府", "机构",
                    "policy", "institution", "governance", "regulation", "government"],
    "Infrastructure": ["管网", "电网", "交通", "基础设施", "工程", "通信", "医院",
                       "infrastructure", "network", "grid", "transport", "hospital"],
    "Process": ["扩散", "传播", "迁移", "退化", "演化", "过程", "蔓延", "传导",
                "spread", "diffusion", "migration", "degradation", "process", "transmission"],
    "EcologicalReceptor": ["物种", "种群", "生态", "栖息地", "人群", "受体", "鱼", "渔",
                           "species", "population", "ecosystem", "habitat", "receptor"],
    "Threshold": ["阈值", "临界", "拐点", "崩溃", "临界点", "突变",
                  "threshold", "tipping", "critical", "collapse", "breakpoint"],
}

# 关系类型（边）候选库——本体的核心。
# 每条带 channel/direction/sign 复杂性词汇；sign 取 +/-/± 表征强化/抑制/双向。
# (name, description, channel, direction, sign, keywords)
_RELATION_LIBRARY: List[Dict[str, Any]] = [
    {
        "name": "AFFECTS", "description": "一般影响关系（方向性、可正可负）",
        "channel": "generic", "direction": "directed", "sign": "±",
        "keywords": [],  # 始终纳入，作为兜底关系
    },
    {
        "name": "LOCATED_IN", "description": "空间归属（主体位于某区域内）",
        "channel": "spatial", "direction": "directed", "sign": "0",
        "keywords": [],  # 始终纳入
    },
    {
        "name": "TRANSMITS_TO", "description": "沿通道向下游传导（疾病/污染/冲击的传播）",
        "channel": "propagation", "direction": "directed", "sign": "+",
        "keywords": ["传播", "扩散", "蔓延", "传导", "传染", "下游", "spread",
                     "transmission", "diffusion", "propagat", "downstream"],
    },
    {
        "name": "COMPETES_FOR", "description": "对有限资源的争夺（负反馈来源）",
        "channel": "resource", "direction": "undirected", "sign": "-",
        "keywords": ["争夺", "竞争", "抢占", "稀缺", "短缺", "资源", "供给",
                     "compete", "scarcity", "shortage", "resource", "supply"],
    },
    {
        "name": "DEPENDS_ON", "description": "依赖关系（被依赖方失效将向上游回传脆弱性）",
        "channel": "dependency", "direction": "directed", "sign": "+",
        "keywords": ["依赖", "依靠", "供给", "供应链", "支撑", "上游",
                     "depend", "rely", "supply chain", "upstream"],
    },
    {
        "name": "REGULATES", "description": "制度/政策对行为的调控（可抑制可放大）",
        "channel": "institutional", "direction": "directed", "sign": "±",
        "keywords": ["政策", "监管", "调控", "治理", "干预", "管控", "法规",
                     "policy", "regulat", "govern", "interven", "control"],
    },
    {
        "name": "EXPOSES", "description": "暴露关系（将生态受体置于风险通道之下）",
        "channel": "exposure", "direction": "directed", "sign": "+",
        "keywords": ["暴露", "受体", "脆弱", "敏感", "影响人群", "栖息地",
                     "expos", "vulnerab", "receptor", "sensitiv", "habitat"],
    },
    {
        "name": "AMPLIFIES", "description": "正反馈：强化另一关系/状态的强度",
        "channel": "feedback", "direction": "directed", "sign": "+",
        "keywords": ["放大", "强化", "加剧", "正反馈", "恶性循环", "连锁",
                     "amplif", "reinforc", "positive feedback", "vicious", "cascade"],
    },
    {
        "name": "MITIGATES", "description": "负反馈：抑制/缓解另一关系/状态",
        "channel": "feedback", "direction": "directed", "sign": "-",
        "keywords": ["缓解", "抑制", "削弱", "负反馈", "缓冲", "恢复", "修复",
                     "mitigat", "dampen", "negative feedback", "buffer", "recover"],
    },
    {
        "name": "TRIGGERS", "description": "越过阈值后触发状态跃迁（拐点机制）",
        "channel": "threshold", "direction": "directed", "sign": "+",
        "keywords": ["触发", "阈值", "临界", "拐点", "突变", "崩溃",
                     "trigger", "threshold", "tipping", "critical", "collapse"],
    },
]


class OntologyGenerator:
    """场景驱动的本体生成器。

    `generate()` 优先用 LLM（仅当 Config.LLM_API_KEY 配置时实例化 LLMClient）
    产出场景局部、关系类型化的本体；否则回退到确定性 fallback——后者仍比旧
    3 类型 stub 丰富，并据 requirement/text 命中关键词扩类。
    """

    # 旧 stub 的实体数量基线，便于测试断言"比旧版更丰富"。
    _LEGACY_ENTITY_TYPE_COUNT = 3

    def generate(
        self,
        document_texts: Optional[List[str]] = None,
        simulation_requirement: str = "",
        additional_context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        corpus = self._build_corpus(document_texts, simulation_requirement, additional_context)

        # —— LLM 路径：仅当配置了密钥才尝试 —— #
        # 注意：当 source == "llm" 时，api/graph.py:215 的日志
        # "调用 LLM 生成本体定义..." 才是**真实**的；fallback 时它名不副实，
        # 但该日志位于本 agent 不拥有的文件中，无法修改，故在此说明。
        if getattr(Config, "LLM_API_KEY", None):
            llm_result = self._generate_with_llm(
                corpus=corpus,
                document_texts=document_texts,
                simulation_requirement=simulation_requirement,
                additional_context=additional_context,
            )
            if llm_result is not None:
                return llm_result

        # —— 确定性 fallback：无网络/无密钥也可用 —— #
        return self._generate_deterministic(corpus, simulation_requirement)

    # ------------------------------------------------------------------ #
    # LLM 路径
    # ------------------------------------------------------------------ #
    def _generate_with_llm(
        self,
        *,
        corpus: str,
        document_texts: Optional[List[str]],
        simulation_requirement: str,
        additional_context: Optional[Any],
    ) -> Optional[Dict[str, Any]]:
        """尝试用 LLM 生成本体；任何失败都返回 None 让上层回退（诚实降级）。"""
        try:
            from ..utils.llm_client import LLMClient

            client = LLMClient()
            messages = [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": self._user_prompt(corpus, simulation_requirement)},
            ]
            raw = client.chat_json(messages=messages, temperature=0.3, max_tokens=2048)
            normalized = self._normalize_llm_payload(raw, simulation_requirement)
            if normalized is not None:
                return normalized
        except Exception:
            # 网络/密钥/解析任何一步失败 -> 静默降级到 fallback。
            return None
        return None

    def _system_prompt(self) -> str:
        return (
            "你是 Kaleido 复杂生态沙盘的本体设计师。Kaleido 是关系探索工具，不是预测器。"
            "请基于给定材料与推演需求，生成一套**场景局部**的本体定义。"
            "核心是 RELATION（关系/边）类型——关系是一等公民，要刻画通道、方向与正负作用，"
            "并尽量覆盖反馈环（放大/抑制）与阈值触发等复杂性机制。"
            "实体类型可从开放集合中选取：Actor/Region/Resource/Institution/Infrastructure/"
            "Process/EcologicalReceptor/Risk/Threshold。"
            "只输出 JSON，结构为："
            '{"entity_types":[{"name":..,"description":..}],'
            '"edge_types":[{"name":..,"description":..,"channel":..,"direction":..,"sign":..}],'
            '"analysis_summary":..}。'
            "sign 取 \"+\"/\"-\"/\"±\"/\"0\"；direction 取 \"directed\"/\"undirected\"。"
            "实体类型至少 5 种、关系类型至少 5 种；命名用大写下划线（如 TRANSMITS_TO）。"
        )

    def _user_prompt(self, corpus: str, simulation_requirement: str) -> str:
        req = (simulation_requirement or "（未显式提供，请从材料推断）").strip()
        return (
            f"推演需求：{req}\n\n"
            f"材料摘录（已截断）：\n{corpus}\n\n"
            "请输出场景驱动的本体 JSON。"
        )

    def _normalize_llm_payload(
        self, raw: Any, simulation_requirement: str
    ) -> Optional[Dict[str, Any]]:
        """校验并规整 LLM 返回；不达标则返回 None 触发 fallback。"""
        if not isinstance(raw, dict):
            return None

        entity_types = self._coerce_named_list(raw.get("entity_types"))
        edge_types = self._coerce_edge_list(raw.get("edge_types"))

        # 必须真正比旧 stub 丰富，否则不如直接用确定性 fallback。
        if len(entity_types) < self._LEGACY_ENTITY_TYPE_COUNT or not edge_types:
            return None

        summary = raw.get("analysis_summary")
        if not isinstance(summary, str) or not summary.strip():
            summary = simulation_requirement or "已基于材料生成场景本体。"

        return {
            "entity_types": entity_types,
            "edge_types": edge_types,
            "analysis_summary": summary.strip(),
            "source": "llm",
            "relation_vocabulary": self._relation_vocabulary(),
            "scenario_keywords": [],
            "notes": "本体由场景 LLM 现生成（api/graph.py 的“调用 LLM 生成本体”日志在此分支为真实）。",
        }

    @staticmethod
    def _coerce_named_list(value: Any) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        seen = set()
        if not isinstance(value, list):
            return out
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                desc = str(item.get("description", "")).strip()
            elif isinstance(item, str):
                name, desc = item.strip(), ""
            else:
                continue
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({"name": name, "description": desc})
        return out

    @staticmethod
    def _coerce_edge_list(value: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        if not isinstance(value, list):
            return out
        for item in value:
            if not isinstance(item, dict):
                if isinstance(item, str) and item.strip() and item.strip() not in seen:
                    seen.add(item.strip())
                    out.append({"name": item.strip(), "description": "",
                                "channel": "generic", "direction": "directed", "sign": "±"})
                continue
            name = str(item.get("name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({
                "name": name,
                "description": str(item.get("description", "")).strip(),
                "channel": str(item.get("channel", "generic")).strip() or "generic",
                "direction": str(item.get("direction", "directed")).strip() or "directed",
                "sign": str(item.get("sign", "±")).strip() or "±",
            })
        return out

    # ------------------------------------------------------------------ #
    # 确定性 fallback 路径（无 LLM）
    # ------------------------------------------------------------------ #
    def _generate_deterministic(
        self, corpus: str, simulation_requirement: str
    ) -> Dict[str, Any]:
        haystack = corpus.lower()

        # 1) 实体类型：始终包含 4 个核心，再按关键词命中扩类。
        chosen_entities = ["Actor", "Region", "Risk", "Process"]
        matched_keywords: List[str] = []
        for entity_name, keywords in _ENTITY_KEYWORD_HINTS.items():
            hit = next((kw for kw in keywords if kw.lower() in haystack), None)
            if hit:
                matched_keywords.append(hit)
                if entity_name not in chosen_entities:
                    chosen_entities.append(entity_name)

        entity_types = [
            {"name": name, "description": _OPEN_ENTITY_TYPES[name]}
            for name in chosen_entities
            if name in _OPEN_ENTITY_TYPES
        ]

        # 2) 关系类型（核心）：始终含 AFFECTS/LOCATED_IN，再按关键词扩展。
        edge_types: List[Dict[str, Any]] = []
        for rel in _RELATION_LIBRARY:
            keywords = rel["keywords"]
            always = len(keywords) == 0
            hit = always or any(kw.lower() in haystack for kw in keywords)
            if not hit:
                continue
            if not always:
                matched = next((kw for kw in keywords if kw.lower() in haystack), None)
                if matched:
                    matched_keywords.append(matched)
            edge_types.append({
                "name": rel["name"],
                "description": rel["description"],
                "channel": rel["channel"],
                "direction": rel["direction"],
                "sign": rel["sign"],
            })

        summary = self._fallback_summary(simulation_requirement, entity_types, edge_types)

        return {
            "entity_types": entity_types,
            "edge_types": edge_types,
            "analysis_summary": summary,
            "source": "deterministic_fallback",
            "relation_vocabulary": self._relation_vocabulary(),
            "scenario_keywords": sorted(set(matched_keywords)),
            "notes": (
                "未配置 LLM_API_KEY 或 LLM 调用失败，本体由确定性规则据需求/材料关键词生成；"
                "比旧 3 类型 stub 丰富，但仍是启发式，非场景现生成。"
            ),
        }

    @staticmethod
    def _fallback_summary(
        simulation_requirement: str,
        entity_types: List[Dict[str, str]],
        edge_types: List[Dict[str, Any]],
    ) -> str:
        base = (simulation_requirement or "").strip()
        ent_names = "、".join(e["name"] for e in entity_types)
        rel_names = "、".join(e["name"] for e in edge_types)
        head = base if base else "已据材料关键词生成确定性场景本体。"
        return (
            f"{head}（确定性本体：实体类型 {len(entity_types)} 种 [{ent_names}]，"
            f"关系类型 {len(edge_types)} 种 [{rel_names}]）"
        )

    # ------------------------------------------------------------------ #
    # 共用
    # ------------------------------------------------------------------ #
    @staticmethod
    def _relation_vocabulary() -> Dict[str, Any]:
        """关系边复杂性词汇的取值空间说明（与 validated_relation_graph 对齐）。"""
        return {
            "channel": [
                "generic", "spatial", "propagation", "resource", "dependency",
                "institutional", "exposure", "feedback", "threshold",
            ],
            "direction": ["directed", "undirected"],
            "sign": ["+", "-", "±", "0"],
            "note": "sign: + 强化 / - 抑制 / ± 双向或情境依赖 / 0 无作用方向（如纯空间归属）。",
        }

    @staticmethod
    def _build_corpus(
        document_texts: Optional[List[str]],
        simulation_requirement: str,
        additional_context: Optional[Any],
        max_chars: int = 6000,
    ) -> str:
        parts: List[str] = []
        if simulation_requirement:
            parts.append(str(simulation_requirement))
        if additional_context:
            parts.append(str(additional_context))
        if document_texts:
            for text in document_texts:
                if text:
                    parts.append(str(text))
        corpus = "\n\n".join(parts)
        if len(corpus) > max_chars:
            corpus = corpus[:max_chars]
        return corpus
